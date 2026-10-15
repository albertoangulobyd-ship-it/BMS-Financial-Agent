"""Lo que se lee para la consola, la CLI y /api/v2: listas y el detalle de una factura.

Solo lee. La lista de facturas sale ordenada por prioridad (prioridad.py:
nivel, puntos, vencimiento, importe, id) con sus marcas de revision, calidad
y edicion manual, de la cache factura_estado. El detalle de una factura
junta, campo a campo, el valor actual, el original y su literal impreso, la
fuente, si es dudoso, si esta verificado, si esta sin resolver y su calidad;
y ademas sus lineas e imputaciones, sus hallazgos, su excepcion, sus
revisiones, sus notas y su historia.

Todo lo que viene de un documento (nombres, descripciones, notas del PDF) va
tal cual, como datos: quien lo pinta lo pone como texto (consola_assets.py,
textContent), nunca como HTML. Los importes van en enteros (centimos, ...) y
tambien como texto ya formateado.

Desde el paso 8, ademas, la vista de cada proveedor (§3) y de cada cliente
(§4), y las relaciones de una factura en su ficha.

Lo que el §12 pide de busqueda y filtros (§18) y el resto de vistas son del
paso 12; aqui esta lo que la consola minima necesita.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from . import campos, excepciones, hallazgos, prioridad, relaciones, revision
from .almacen.unidades import de_cent, de_e4, de_mil, de_pb
from .dominio import ESTADOS_PENDIENTES, FUENTES_MANUALES, Calidad

_ORDEN_CALIDAD = (Calidad.FALTANTE.value, Calidad.DISCREPANCIA.value, Calidad.ANOMALIA.value,
                  Calidad.DUDOSO.value, Calidad.VERIFICADO.value)


def _decimal_texto(valor: Decimal, decimales: int | None = None) -> str:
    """Con punto de millares y coma decimal: 2.902,79."""
    texto = f"{valor:,.{decimales}f}" if decimales is not None else f"{valor:,f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _compacto(valor: Decimal) -> Decimal:
    """Sin ceros de mas: 37,500 horas es 37,5 y 21,00 % es 21 %."""
    return valor.quantize(Decimal(1)) if valor == valor.to_integral_value() else valor.normalize()


def texto_de(definicion: campos.Campo, valor: Any) -> str | None:
    """Un valor de columna como se lee en la empresa: 2.902,79, 37,5, 42,50, 21 %."""
    if valor is None:
        return None
    tipo = definicion.tipo
    if tipo == campos.CENT:
        return _decimal_texto(de_cent(valor), 2)
    if tipo == campos.E4:
        tarifa = de_e4(valor)
        return _decimal_texto(tarifa, 2 if tarifa == tarifa.quantize(Decimal("0.01")) else 4)
    if tipo == campos.MIL:
        return _decimal_texto(_compacto(de_mil(valor)))
    if tipo == campos.PB:
        return f"{_decimal_texto(_compacto(de_pb(valor)))} %"
    if tipo == campos.BOOL:
        return "sí" if valor else "no"
    return str(valor)


def entrada_de(definicion: campos.Campo, valor: Any) -> str | None:
    """Un valor de columna tal como se vuelve a escribir en un formulario (2902.79, si, 2026-09-15)."""
    if valor is None:
        return None
    conversor = {campos.CENT: de_cent, campos.MIL: de_mil, campos.E4: de_e4,
                 campos.PB: de_pb}.get(definicion.tipo)
    if conversor is not None:
        return str(_compacto(conversor(valor))) if definicion.tipo != campos.CENT else str(
            conversor(valor))
    if definicion.tipo == campos.BOOL:
        return "si" if valor else "no"
    return str(valor)


def _nombres(conn: sqlite3.Connection) -> dict[int, str]:
    return {f[0]: f[1] for f in conn.execute("SELECT id, nombre FROM usuario")}


# ------------------------------------------------------------ la lista

def _pendientes_por_factura(conn: sqlite3.Connection) -> dict[int, tuple[int, int]]:
    """(pendientes, de ellos aceptados) por factura."""
    cuentas: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for factura_id, _clave, _huella, estado, _anulacion in revision.pendientes_por_factura(conn):
        cuentas[factura_id][0] += 1
        if estado == "aceptado":
            cuentas[factura_id][1] += 1
    return {f: (c[0], c[1]) for f, c in cuentas.items()}


def listado(conn: sqlite3.Connection, *, nivel: str | None = None,
            limite: int | None = None) -> list[dict[str, Any]]:
    """Las facturas, la mas urgente primero, con lo que la consola ensena en la lista."""
    pendientes = _pendientes_por_factura(conn)
    excepciones_ = {f["fila_id"]: (f["id"], f["estado"]) for f in conn.execute(
        "SELECT id, fila_id, estado FROM excepcion WHERE tabla = 'factura' "
        "AND estado <> 'resuelta'")}
    filas = []
    for f in conn.execute(
            "SELECT f.id, f.numero, f.sentido, f.emisor_nombre_doc, f.receptor_nombre_doc, "
            "f.fecha_factura, f.base_cent, f.total_cent, f.anulada, f.fusionada_en_id, "
            "e.* FROM factura AS f LEFT JOIN factura_estado AS e ON e.factura_id = f.id"):
        if nivel is not None and f["nivel"] != nivel:
            continue
        n_pendientes, aceptados = pendientes.get(f["id"], (0, 0))
        excepcion = excepciones_.get(f["id"])
        filas.append({
            "id": f["id"], "numero": f["numero"], "sentido": f["sentido"],
            "contraparte": (f["emisor_nombre_doc"] if f["sentido"] == "entrante"
                            else f["receptor_nombre_doc"]),
            "fecha_factura": f["fecha_factura"], "vencimiento": f["vencimiento"],
            "base_cent": f["base_cent"], "total_cent": f["total_cent"],
            "total": texto_de(campos.campo("factura", "total_cent"), f["total_cent"]),
            "anulada": bool(f["anulada"]), "fusionada_en_id": f["fusionada_en_id"],
            "nivel": f["nivel"] or prioridad.NORMAL, "puntos": f["puntos"] or 0,
            "suelo": f["suelo"] or prioridad.NORMAL,
            "motivos": json.loads(f["motivos_json"]) if f["motivos_json"] else [],
            "estado_revision": f["estado_revision"], "calidad": f["calidad"],
            "estado_pago": f["estado_pago"], "dias_vencida": f["dias_vencida"],
            "editada": bool(f["editada"]), "suplementada": bool(f["suplementada"]),
            "corregida": bool(f["corregida"]), "sin_resolver": f["sin_resolver"] or 0,
            "dudosos": f["dudosos"] or 0, "pendientes": n_pendientes, "aceptados": aceptados,
            "sin_datos": f["sin_datos"] or 0,
            "etiqueta": revision.etiqueta_sistema(n_pendientes, aceptados, f["sin_datos"] or 0,
                                                  (f["sin_resolver"] or 0) + (f["dudosos"] or 0)),
            "excepcion": {"id": excepcion[0], "estado": excepcion[1]} if excepcion else None,
        })
    filas.sort(key=lambda r: prioridad.clave_orden(
        r["nivel"], r["puntos"], date.fromisoformat(r["vencimiento"]) if r["vencimiento"] else None,
        r["base_cent"] if r["base_cent"] is not None else r["total_cent"], r["id"]))
    return filas[:limite] if limite is not None else filas


def excepciones_abiertas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Las excepciones sin resolver, la mas urgente primero."""
    nombres = _nombres(conn)
    prioridades = {f["entidad_id"]: f for f in conn.execute(
        "SELECT * FROM prioridad WHERE entidad = 'excepcion'")}
    salida = []
    for e in excepciones.sin_resolver(conn):
        p = prioridades.get(e["id"])
        salida.append({
            **_excepcion(e, nombres),
            "nivel": p["nivel"] if p else prioridad.NORMAL, "puntos": p["puntos"] if p else 0,
            "motivos": json.loads(p["motivos_json"]) if p else [],
            "vencimiento": p["vencimiento"] if p else None,
            "importe_cent": p["importe_cent"] if p else None,
            "hallazgos": [h["id"] for h in excepciones.hallazgos_de(conn, e["id"])],
        })
    salida.sort(key=lambda r: prioridad.clave_orden(
        r["nivel"], r["puntos"], date.fromisoformat(r["vencimiento"]) if r["vencimiento"] else None,
        r["importe_cent"], r["id"]))
    return salida


def _excepcion(e: sqlite3.Row, nombres: dict[int, str]) -> dict[str, Any]:
    return {
        "id": e["id"], "rev": e["rev"], "titulo": e["titulo"], "descripcion": e["descripcion"],
        "tabla": e["tabla"], "fila_id": e["fila_id"], "factura_id": e["factura_id"],
        "estado": e["estado"], "responsable_id": e["responsable_id"],
        "responsable": nombres.get(e["responsable_id"]),
        "esperando_a": e["esperando_a"], "fecha_seguimiento": e["fecha_seguimiento"],
        "resolucion": e["resolucion"], "resolucion_notas": e["resolucion_notas"],
        "creada_en": e["creada_en"], "creada_por": nombres.get(e["creada_por"]),
        "resuelta_en": e["resuelta_en"], "resuelta_por": nombres.get(e["resuelta_por"]),
    }


# ------------------------------------------------------------ el detalle

def _calidad_de(marcas: set[str]) -> str | None:
    for nivel in _ORDEN_CALIDAD:
        if nivel in marcas:
            return nivel
    return None


def _campos_de(conn: sqlite3.Connection, tabla: str, fila: sqlite3.Row, sentido: str | None,
               de_hallazgos: dict[tuple[str, int, str], set[str]],
               sin_resolver: set[tuple[str, int, str]], nombres: dict[int, str],
               solo: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Cada campo de una fila con su valor, su original, su fuente y sus marcas."""
    procedencias = campos.procedencia(conn, tabla, fila["id"])
    salida = []
    for nombre, definicion in campos.REGISTRO[tabla].items():
        if solo is not None and nombre not in solo:
            continue
        p = procedencias.get(nombre)
        estado = campos.estado_campo(p)
        clave = (tabla, fila["id"], nombre)
        marcas = set(de_hallazgos.get(clave, ()))
        valor = fila[nombre]
        obligatorio = sentido is not None and sentido in definicion.obligatorio
        if obligatorio and valor is None and (p is None or p["valor_original_crudo"] is None):
            marcas.add(Calidad.FALTANTE.value)
        pendiente = estado.sin_resolver or clave in sin_resolver
        if pendiente:
            marcas.add(Calidad.DISCREPANCIA.value)
        if estado.dudoso:
            marcas.add(Calidad.DUDOSO.value)
        if estado.verificado:
            marcas.add(Calidad.VERIFICADO.value)
        original = p["valor_original"] if p else None
        automatico = p["valor_automatico"] if p else None
        salida.append({
            "tabla": tabla, "fila_id": fila["id"], "campo": nombre, "tipo": definicion.tipo,
            "valor": valor, "texto": texto_de(definicion, valor),
            "entrada": entrada_de(definicion, valor),
            "fuente": estado.fuente, "original": original,
            "original_texto": texto_de(definicion, original) if p else None,
            "original_crudo": p["valor_original_crudo"] if p else None,
            "fuente_original": p["fuente_original"] if p else None,
            "automatico": automatico, "automatico_texto": texto_de(definicion, automatico),
            "editado": estado.editado, "suplementado": estado.suplementado,
            "corregido": estado.corregido, "sin_resolver": pendiente,
            "dudoso": estado.dudoso, "verificado": estado.verificado,
            "calidad": _calidad_de(marcas),
            "cambiado_por": nombres.get(p["cambiado_por"]) if p else None,
            "cambiado_en": p["cambiado_en"] if p else None,
            "verificado_por": nombres.get(p["verificado_por"]) if p else None,
            "editable": definicion.editable and nombre not in campos.ESTRUCTURA.get(tabla, ()),
            "critico": definicion.critico, "obligatorio": obligatorio,
            "revertible": estado.editado,
        })
    return salida


def detalle(conn: sqlite3.Connection, factura_id: int) -> dict[str, Any]:
    """Todo lo de una factura que la consola ensena en su ficha."""
    factura = conn.execute("SELECT * FROM factura WHERE id = ?", (factura_id,)).fetchone()
    if factura is None:
        raise LookupError(f"no hay factura {factura_id}")
    nombres = _nombres(conn)
    sentido = factura["sentido"]
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    hallazgos_ = conn.execute(
        f"SELECT * FROM hallazgo WHERE estado IN ({marcas}) AND (factura_id = ? OR id IN "
        "(SELECT hallazgo_id FROM hallazgo_objetivo WHERE tabla = 'factura' AND fila_id = ?)) "
        "ORDER BY id", (*sorted(ESTADOS_PENDIENTES), factura_id, factura_id)).fetchall()
    de_hallazgos: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    objetivos: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for h in hallazgos_:
        for o in conn.execute("SELECT tabla, fila_id, campo, papel FROM hallazgo_objetivo "
                              "WHERE hallazgo_id = ? ORDER BY id", (h["id"],)):
            objetivos[h["id"]].append(dict(o))
            if o["campo"] and h["calidad"] and h["estado"] != "aceptado":
                de_hallazgos[(o["tabla"], o["fila_id"], o["campo"])].add(h["calidad"])
    sin_resolver = revision.estado_de_campos(conn).get(
        factura_id, revision.CamposFactura()).sin_resolver

    lineas = []
    for linea in conn.execute("SELECT * FROM factura_linea WHERE factura_id = ? "
                              "ORDER BY orden, id", (factura_id,)):
        imputaciones = []
        for imp in conn.execute("SELECT * FROM factura_imputacion WHERE linea_id = ? "
                                "ORDER BY id", (linea["id"],)):
            objeto = conn.execute("SELECT codigo, nombre FROM objeto WHERE id = ?",
                                  (imp["objeto_id"],)).fetchone() if imp["objeto_id"] else None
            imputaciones.append({
                "id": imp["id"], "rev": imp["rev"], "retirada": imp["retirada_en"] is not None,
                "objeto_id": imp["objeto_id"],
                "objeto": f"{objeto['codigo']}" if objeto else None,
                "campos": _campos_de(conn, "factura_imputacion", imp, sentido, de_hallazgos,
                                     sin_resolver, nombres,
                                     solo=("objeto_id", "recurso_id", "horas_mil",
                                           "importe_cent", "facturable")),
            })
        lineas.append({
            "id": linea["id"], "rev": linea["rev"], "orden": linea["orden"],
            "retirada": linea["retirada_en"] is not None,
            "campos": _campos_de(conn, "factura_linea", linea, sentido, de_hallazgos,
                                 sin_resolver, nombres,
                                 solo=("descripcion_doc", "objeto_doc", "unidad_doc",
                                       "fecha_inicio", "fecha_fin", "fecha_trabajo",
                                       "cantidad_mil", "tarifa_e4", "importe_cent",
                                       "tipo_iva_pb")),
            "imputaciones": imputaciones,
        })
    referencias = [{"id": r["id"], "rev": r["rev"], "etiqueta": r["etiqueta_doc"],
                    "valor": r["valor_doc"], "clase": r["clase"],
                    "retirada": r["retirada_en"] is not None}
                   for r in conn.execute("SELECT * FROM factura_referencia WHERE factura_id = ? "
                                         "ORDER BY id", (factura_id,))]
    lista_hallazgos = []
    for h in hallazgos_:
        lista_hallazgos.append({
            "id": h["id"], "clave": h["clave"], "regla": h["regla"], "titulo": h["titulo"],
            "detalle": h["detalle"], "severidad": h["severidad"], "estado": h["estado"],
            "huella": h["huella"], "anulable": bool(h["anulable"]),
            "pegajosa": bool(h["pegajosa"]), "calidad": h["calidad"],
            # Si anularlo pide la firma de otra persona (la regla, un bloqueo o el
            # importe): la consola le ofrece entonces firmar_anulacion.
            "segunda_firma": hallazgos.requiere_segunda_firma(conn, h),
            "primera_vez_en": h["primera_vez_en"], "objetivos": objetivos.get(h["id"], []),
        })
    excepcion = excepciones.abierta_de(conn, "factura", factura_id)
    estado = conn.execute("SELECT * FROM factura_estado WHERE factura_id = ?",
                          (factura_id,)).fetchone()
    huella = revision.huella_contenido(conn, factura_id)
    revisiones = [{
        "id": r["id"], "resultado": r["resultado"], "usuario": nombres.get(r["usuario_id"]),
        "en": r["en"], "nota": r["nota"], "autorrevisada": bool(r["autorrevisada"]),
        "vigente": r["resultado"] == "revisada" and r["huella_contenido"] == huella,
    } for r in conn.execute("SELECT * FROM revision WHERE factura_id = ? ORDER BY id DESC",
                            (factura_id,))]
    notas = [{"id": n["id"], "texto": n["texto"], "usuario": nombres.get(n["usuario_id"]),
              "en": n["en"]}
             for n in conn.execute("SELECT * FROM nota WHERE tabla = 'factura' AND fila_id = ? "
                                   "ORDER BY id", (factura_id,))]
    historia = [{"id": e["id"], "en": e["en"], "tipo": e["tipo"], "resultado": e["resultado"],
                 "usuario": nombres.get(e["usuario_id"]), "actor": nombres.get(e["actor"]),
                 "motivo": e["motivo"]}
                for e in conn.execute("SELECT * FROM evento WHERE factura_id = ? ORDER BY id",
                                      (factura_id,))]
    n_pendientes = len(hallazgos_)
    aceptados = sum(1 for h in hallazgos_ if h["estado"] == "aceptado")
    sin_datos = estado["sin_datos"] if estado else 0
    pendientes_campo = (estado["sin_resolver"] + estado["dudosos"]) if estado else 0
    return {
        "id": factura_id, "rev": factura["rev"], "sentido": sentido, "numero": factura["numero"],
        "contraparte": (factura["emisor_nombre_doc"] if sentido == "entrante"
                        else factura["receptor_nombre_doc"]),
        "anulada": bool(factura["anulada"]), "fusionada_en_id": factura["fusionada_en_id"],
        "notas_doc": factura["notas_doc"], "huella_contenido": huella,
        "campos": _campos_de(conn, "factura", factura, sentido, de_hallazgos, sin_resolver,
                             nombres),
        "lineas": lineas, "referencias": referencias, "hallazgos": lista_hallazgos,
        "excepcion": ({**_excepcion(excepcion, nombres),
                       "hallazgos": [h["id"] for h in excepciones.hallazgos_de(
                           conn, excepcion["id"])]} if excepcion else None),
        "estado": ({k: estado[k] for k in estado.keys() if k != "motivos_json"}
                   | {"motivos": json.loads(estado["motivos_json"])}) if estado else None,
        "etiqueta": revision.etiqueta_sistema(n_pendientes, aceptados, sin_datos,
                                              pendientes_campo),
        "pide_revision": revision.lo_que_pide_revision(conn, factura_id),
        "revisiones": revisiones, "notas": notas, "historia": historia,
        # Paso 8: con que otras facturas esta relacionada (propuesto, confirmado o
        # rechazado) y que facturas nombra el documento.
        "relaciones": relaciones.de_factura(conn, factura_id),
        "citas": [{"id": c["id"], "numero": c["numero_doc"], "relacion": c["relacion_doc"],
                   "texto": c["texto_doc"], "retirada": c["retirada_en"] is not None}
                  for c in conn.execute("SELECT * FROM factura_cita WHERE factura_id = ? "
                                        "ORDER BY id", (factura_id,))],
    }


def personas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Las personas activas, para asignar una excepcion."""
    return [{"id": f["id"], "nombre": f["nombre"]} for f in conn.execute(
        "SELECT id, nombre FROM usuario WHERE es_sistema = 0 AND activo = 1 ORDER BY nombre")]


def objetos(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Los Objetos, para cambiar la imputacion de una linea."""
    return [{"id": f["id"], "codigo": f["codigo"], "nombre": f["nombre"]} for f in conn.execute(
        "SELECT id, codigo, nombre FROM objeto ORDER BY codigo")]


def manuales(conn: sqlite3.Connection, factura_id: int) -> list[tuple[str, int, str]]:
    """Los campos de una factura con un valor de una persona (para la CLI)."""
    salida = []
    for tabla in revision.TABLAS_DE_FACTURA:
        columna = "id" if tabla == "factura" else "factura_id"
        for fila_id, campo in conn.execute(
                f"SELECT p.fila_id, p.campo FROM procedencia_campo AS p JOIN {tabla} AS t "
                f"ON t.id = p.fila_id WHERE p.tabla = ? AND t.{columna} = ? AND p.fuente IN "
                f"({', '.join('?' * len(FUENTES_MANUALES))}) ORDER BY p.fila_id, p.campo",
                (tabla, factura_id, *sorted(FUENTES_MANUALES))):
            salida.append((tabla, fila_id, campo))
    return salida


# ------------------------------------------------------------ paso 5: cuentas y fuentes

def cuentas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """El registro de cuentas de los proveedores, con su estado como lo ve la pasada.

    El IBAN entero: la consola interna lo ensena (decision 23); solo la
    proyeccion del portal lo enmascara.
    """
    from . import politica
    from .reglas import bancaria
    from .reglas import instantanea as lecturas

    politica_ = politica.politica_reglas(conn)
    telefonos: dict[int, list[Any]] = defaultdict(list)
    for t in lecturas.telefonos(conn):
        telefonos[t.proveedor_id].append(t)
    nombres = {f[0]: f[1] for f in conn.execute("SELECT id, nombre FROM proveedor")}
    salida = []
    for cuenta in lecturas.cuentas(conn):
        if cuenta.titular != "proveedor":
            continue
        estado = bancaria.estado_cuenta(cuenta, telefonos.get(cuenta.parte_id, ()), politica_)
        salida.append({
            "id": cuenta.id, "proveedor_id": cuenta.parte_id,
            "proveedor": nombres.get(cuenta.parte_id, ""), "iban": cuenta.iban,
            "primera_fuente": cuenta.primera_fuente, "estado": estado.estado,
            "en_exact": estado.en_exact, "pagable": estado.pagable,
            "cambios": [t for t, _e, _i in estado.cambios],
            "ineficaz": estado.ineficaz[1] if estado.ineficaz else None,
        })
    return salida


def fuentes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Lo ultimo aceptado de cada fuente y tipo, su edad y si esta pasada (el aviso de Z1)."""
    from datetime import date as _date

    from . import politica
    from .almacen import reloj_de
    from .reglas.base import FRESCURA, edad
    from .reglas.instantanea import lotes

    politica_ = politica.politica_reglas(conn)
    hoy: _date = reloj_de(conn).hoy()
    ultimos: dict[tuple[str, str], Any] = {}
    for lote in lotes(conn):
        if lote.estado in ("aceptada", "parcial"):
            ultimos[(lote.fuente, lote.tipo)] = lote
    salida = []
    for (fuente, tipo), lote in sorted(ultimos.items()):
        limite = getattr(politica_, FRESCURA[fuente]) if fuente in FRESCURA else None
        dias = edad(lote, hoy, fuente)
        salida.append({
            "fuente": fuente, "tipo": tipo, "importacion_id": lote.id,
            "exportado": lote.exportado.isoformat() if lote.exportado else None,
            "edad": dias, "unidad": "dias laborables" if fuente == "banco" else "dias",
            "limite": limite, "caducada": None if limite is None else dias > limite,
        })
    return salida


# ------------------------------------------------------------ paso 8: proveedores y clientes
#
# La vista de un proveedor (§3) y la de un cliente (§4): lo pendiente, lo
# vencido, lo facturado y lo pagado (del ano y de siempre), lo gastado o
# facturado y las horas por Objeto, el historial de facturas y de pagos, el
# importe tipico, el plazo de pago y los retrasos, y los avisos activos.
#
# Sale de lo mismo que las reglas y la cache de estado (estados.facturas: el
# vencimiento efectivo, el saldo con la fuente que manda y lo acreditado por
# los abonos confirmados), con el `hoy` del reloj del almacen: por eso lo
# pendiente de un proveedor es, por construccion, la suma de lo pendiente de
# sus facturas abiertas. Solo cuenta lo que cuenta: ni anuladas, ni copias
# fusionadas, ni sustituidas o corregidas por otra (el historial las ensena
# con su estado). El ano es el natural, por la fecha de la factura (lo
# facturado) o la del pago (lo pagado). En una venta, "pagado" es lo cobrado.

_PARTES = {"proveedor": ("entrante", "proveedor_id"), "cliente": ("saliente", "cliente_id")}


def _euros(cent: int | None) -> str | None:
    return texto_de(campos.campo("factura", "total_cent"), cent)


def _horas_texto(mil: int | None) -> str | None:
    return texto_de(campos.campo("factura_imputacion", "horas_mil"), mil)


def _cuenta(f: Any) -> bool:
    """Si una factura cuenta en los totales: ni anulada, ni copia, ni sustituida."""
    return not (f.anulada or f.fusionada or f.sustituida)


def _pago_cuenta(f: Any) -> bool:
    """Si lo pagado de una factura cuenta en lo pagado: tambien el de una sustituida.

    Una factura sustituida o corregida sale de lo facturado y de lo pendiente,
    pero si ya se pago el dinero salio del banco: esconderlo haria ver la nueva
    como la unica deuda y nada pagado (R3 lo dice).
    """
    return not (f.anulada or f.fusionada)


def _mediana(valores: list[int]) -> int | None:
    if not valores:
        return None
    orden = sorted(valores)
    mitad = len(orden) // 2
    return orden[mitad] if len(orden) % 2 else (orden[mitad - 1] + orden[mitad]) // 2


def _media(valores: list[int]) -> int | None:
    return (sum(valores) + len(valores) // 2) // len(valores) if valores else None


@dataclass(frozen=True)
class _Lectura:
    """Lo que leen todas las vistas, una vez: hoy, las facturas y sus pagos."""

    hoy: date
    facturas: list[Any]
    pagos: dict[int, list[Any]]

    def de(self, columna: str, parte_id: int) -> list[Any]:
        return [f for f in self.facturas if getattr(f, columna) == parte_id]

    def pagos_de(self, f: Any) -> list[Any]:
        """Los pagos de la fuente que manda en esa factura (banco, Exact o a mano)."""
        return [a for a in self.pagos.get(f.id, ()) if a.estado == "confirmada"
                and a.fuente == f.fuente_pago]


def _leer(conn: sqlite3.Connection) -> _Lectura:
    from . import estados, politica
    from .almacen import reloj_de
    from .reglas import instantanea
    from .reglas.pagos import tolerancia_cent

    tolerancia = tolerancia_cent(politica.politica_reglas(conn).tolerancia_pago)
    pagos: dict[int, list[Any]] = defaultdict(list)
    for a in instantanea.aplicaciones(conn):
        pagos[a.factura_id].append(a)
    return _Lectura(reloj_de(conn).hoy(), estados.facturas(conn, tolerancia), pagos)


def _abiertas(lectura: _Lectura, facturas: list[Any]) -> list[Any]:
    """Las facturas que se deben (o nos deben): pendientes o vencidas, con su saldo en euros."""
    from .estados import EN_JUEGO

    return [f for f in facturas if _cuenta(f) and f.pendiente_cent is not None
            and f.estado(lectura.hoy) in EN_JUEGO]


def _sumas(facturas: list[Any], campo: str) -> int:
    return sum(getattr(f, campo) or 0 for f in facturas)


def _resumen(conn: sqlite3.Connection, lectura: _Lectura, facturas: list[Any]) -> dict[str, Any]:
    """Los importes de una contraparte: pendiente, vencido, del ano y de siempre."""
    from .estados import VENCIDA

    hoy = lectura.hoy
    cuentan = [f for f in facturas if _cuenta(f)]
    abiertas = _abiertas(lectura, facturas)
    vencidas = [f for f in abiertas if f.estado(hoy) == VENCIDA]
    del_ano = [f for f in cuentan if f.fecha_factura is not None
               and f.fecha_factura.year == hoy.year]
    bases = _bases(conn, [f.id for f in cuentan])
    pagos = [a for f in facturas if _pago_cuenta(f) for a in lectura.pagos_de(f)]
    pagado_ano = sum(a.importe_cent for a in pagos if a.fecha_pago.year == hoy.year)
    pendiente = _sumas(abiertas, "pendiente_cent")
    vencido = _sumas(vencidas, "pendiente_cent")
    return {
        "facturas": len(cuentan),
        "pendiente_cent": pendiente, "pendiente": _euros(pendiente), "abiertas": len(abiertas),
        "vencido_cent": vencido, "vencido": _euros(vencido), "vencidas": len(vencidas),
        "ano": hoy.year,
        "ano_facturado": _totales(del_ano, bases), "ano_pagado_cent": pagado_ano,
        "ano_pagado": _euros(pagado_ano),
        "siempre_facturado": _totales(cuentan, bases),
        "siempre_pagado_cent": sum(a.importe_cent for a in pagos),
        "siempre_pagado": _euros(sum(a.importe_cent for a in pagos)),
        "sin_importe": sum(1 for f in cuentan if f.total_cent is None),
    }


def _bases(conn: sqlite3.Connection, ids: list[int]) -> dict[int, tuple[Any, Any, str]]:
    """(base, IVA, tipo) de cada factura: el total ya lo trae estados.facturas."""
    salida = {}
    for inicio in range(0, len(ids), 500):
        trozo = ids[inicio:inicio + 500]
        for id_, base, iva, tipo in conn.execute(
                f"SELECT id, base_cent, iva_cent, tipo FROM factura WHERE id IN "
                f"({', '.join('?' * len(trozo))})", trozo):
            salida[id_] = (base, iva, tipo)
    return salida


def _totales(facturas: list[Any], bases: dict[int, tuple[Any, Any, str]]) -> dict[str, Any]:
    base = sum(bases[f.id][0] or 0 for f in facturas)
    iva = sum(bases[f.id][1] or 0 for f in facturas)
    total = _sumas(facturas, "total_cent")
    return {"facturas": len(facturas), "base_cent": base, "iva_cent": iva, "total_cent": total,
            "base": _euros(base), "total": _euros(total)}


def _plazos(lectura: _Lectura, facturas: list[Any]) -> dict[str, Any]:
    """Cuanto se tarda en pagar (o en cobrar) y los pagos que llegaron tarde.

    Una factura cuenta si esta pagada (saldada con dinero, no solo con un
    abono): su dia de pago es el del ultimo pago de la fuente que manda. Llega
    tarde si ese dia es posterior a su vencimiento efectivo.
    """
    dias, tarde = [], []
    for f in facturas:
        pagos = lectura.pagos_de(f)
        if not (_cuenta(f) and f.pagada and pagos and f.fecha_factura is not None):
            continue
        pagada_el = max(a.fecha_pago for a in pagos)
        dias.append((pagada_el - f.fecha_factura).days)
        if f.vencimiento is not None and pagada_el > f.vencimiento:
            tarde.append({"factura_id": f.id, "numero": f.numero,
                          "vencimiento": f.vencimiento.isoformat(),
                          "pagada_el": pagada_el.isoformat(),
                          "dias": (pagada_el - f.vencimiento).days})
    tarde.sort(key=lambda t: t["pagada_el"], reverse=True)
    return {"pagadas": len(dias), "media_dias": _media(dias), "mediana_dias": _mediana(dias),
            "tarde": len(tarde), "media_dias_tarde": _media([t["dias"] for t in tarde]),
            "retrasos": tarde}


def _importe_tipico(conn: sqlite3.Connection, facturas: list[Any]) -> dict[str, Any]:
    """La media y la mediana de lo que vale una factura (sin IVA; los abonos no cuentan)."""
    bases = _bases(conn, [f.id for f in facturas])
    importes = []
    for f in facturas:
        base, _iva, tipo = bases[f.id]
        importe = base if base is not None else f.total_cent
        if _cuenta(f) and tipo == "factura" and importe is not None:
            importes.append(importe)
    media, mediana = _media(importes), _mediana(importes)
    return {"facturas": len(importes), "media_cent": media, "media": _euros(media),
            "mediana_cent": mediana, "mediana": _euros(mediana)}


def _por_objeto(conn: sqlite3.Connection, columna: str, parte_id: int,
                hoy: date) -> list[dict[str, Any]]:
    """Lo gastado (o facturado) y las horas por Objeto, de las imputaciones que cuentan."""
    filas = conn.execute(
        f"SELECT i.objeto_id, o.codigo, o.nombre, sum(coalesce(i.importe_cent, 0)) AS importe, "
        f"sum(coalesce(i.horas_mil, 0)) AS horas, "
        f"sum(CASE WHEN substr(i.fecha_factura, 1, 4) = ? THEN coalesce(i.importe_cent, 0) "
        f"ELSE 0 END) AS importe_ano, count(DISTINCT i.factura_id) AS facturas "
        f"FROM v_imputacion_vigente AS i LEFT JOIN objeto AS o ON o.id = i.objeto_id "
        f"WHERE i.{columna} = ? GROUP BY i.objeto_id ORDER BY importe DESC, o.codigo",
        (str(hoy.year), parte_id)).fetchall()
    return [{"objeto_id": f["objeto_id"], "objeto": f["codigo"] or "(sin Objeto)",
             "nombre": f["nombre"], "facturas": f["facturas"],
             "importe_cent": f["importe"], "importe": _euros(f["importe"]),
             "importe_ano_cent": f["importe_ano"], "horas_mil": f["horas"],
             "horas": _horas_texto(f["horas"])} for f in filas]


def _historial(conn: sqlite3.Connection, lectura: _Lectura,
               facturas: list[Any]) -> list[dict[str, Any]]:
    """Todas sus facturas (sin las copias fusionadas), la mas reciente primero, con su estado."""
    bases = _bases(conn, [f.id for f in facturas])
    salida = []
    for f in sorted((f for f in facturas if not f.fusionada),
                    key=lambda f: (f.fecha_factura or date.min, f.id), reverse=True):
        salida.append({
            "id": f.id, "numero": f.numero, "tipo": bases[f.id][2],
            "fecha_factura": f.fecha_factura.isoformat() if f.fecha_factura else None,
            "vencimiento": f.vencimiento.isoformat() if f.vencimiento else None,
            "total_cent": f.total_cent, "total": _euros(f.total_cent),
            "pagado_cent": f.pagado_cent, "acreditado_cent": f.acreditado_cent,
            "pendiente_cent": f.pendiente_cent if _cuenta(f) else None,
            "estado_pago": f.estado(lectura.hoy), "cuenta": _cuenta(f),
            "sustituida": f.sustituida,
        })
    return salida


def _pagos(lectura: _Lectura, facturas: list[Any]) -> list[dict[str, Any]]:
    """Cada pago (o cobro) de sus facturas, de la fuente que manda, el mas reciente primero."""
    salida = [{"aplicacion_id": a.id, "factura_id": f.id, "numero": f.numero,
               "fecha": a.fecha_pago.isoformat(), "importe_cent": a.importe_cent,
               "importe": _euros(a.importe_cent), "fuente": a.fuente,
               "movimiento_id": a.movimiento_id}
              for f in facturas if _pago_cuenta(f) for a in lectura.pagos_de(f)]
    salida.sort(key=lambda p: (p["fecha"], p["aplicacion_id"]), reverse=True)
    return salida


def _avisos(conn: sqlite3.Connection, tabla: str, parte_id: int,
            facturas: list[Any]) -> dict[str, Any]:
    """Los hallazgos sin cerrar de sus facturas y de el mismo, y sus excepciones abiertas."""
    ids = {f.id for f in facturas}
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    apuntan = {f[0] for f in conn.execute(
        "SELECT hallazgo_id FROM hallazgo_objetivo WHERE tabla = ? AND fila_id = ?",
        (tabla, parte_id))}
    hallazgos_ = []
    for h in conn.execute(
            f"SELECT * FROM hallazgo WHERE estado IN ({marcas}) ORDER BY id",
            sorted(ESTADOS_PENDIENTES)):
        if (h["factura_id"] in ids or (h["tabla"] == tabla and h["fila_id"] == parte_id)
                or h["id"] in apuntan):
            hallazgos_.append({"id": h["id"], "regla": h["regla"], "titulo": h["titulo"],
                               "detalle": h["detalle"], "severidad": h["severidad"],
                               "estado": h["estado"], "factura_id": h["factura_id"]})
    excepciones_ = [{"id": e["id"], "estado": e["estado"], "titulo": e["titulo"]}
                    for e in conn.execute(
                        "SELECT id, estado, titulo FROM excepcion WHERE estado <> 'resuelta' "
                        "AND ((tabla = ? AND fila_id = ?) OR (tabla = 'factura' AND fila_id IN "
                        f"({', '.join('?' * len(ids)) or 'NULL'}))) ORDER BY id",
                        (tabla, parte_id, *sorted(ids)))]
    activos = [h for h in hallazgos_ if h["estado"] != "aceptado"]
    return {"activos": len(activos), "aceptados": len(hallazgos_) - len(activos),
            "bloqueos": sum(1 for h in activos if h["severidad"] == "bloqueo"),
            "hallazgos": hallazgos_, "excepciones": excepciones_}


def _ibanes(conn: sqlite3.Connection, proveedor_id: int) -> dict[str, Any]:
    """Las cuentas del registro (con su estado) y los IBAN que han impreso sus facturas.

    La primera y la ultima fecha son las de las facturas fechadas: una sin
    fecha legible cuenta en el numero, pero no deja la primera sin fecha.
    """
    from .reglas.normas import normalizar_iban

    impresos: dict[str, dict[str, Any]] = {}
    for iban, fecha in conn.execute(
            "SELECT iban_doc, fecha_factura FROM factura WHERE proveedor_id = ? "
            "AND iban_doc IS NOT NULL ORDER BY fecha_factura IS NULL, fecha_factura, id",
            (proveedor_id,)):
        clave = normalizar_iban(iban) or iban
        visto = impresos.setdefault(clave, {"iban": clave, "primera": fecha, "ultima": fecha,
                                            "facturas": 0})
        visto["primera"] = visto["primera"] or fecha
        visto["ultima"] = fecha or visto["ultima"]
        visto["facturas"] += 1
    return {"registro": [c for c in cuentas(conn) if c["proveedor_id"] == proveedor_id],
            "impresos": list(impresos.values())}


def _parte(conn: sqlite3.Connection, tabla: str, parte_id: int) -> sqlite3.Row:
    fila = conn.execute(f"SELECT * FROM {tabla} WHERE id = ?", (parte_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay {tabla} {parte_id}")
    return fila


def _vista(conn: sqlite3.Connection, tabla: str, parte_id: int) -> dict[str, Any]:
    _sentido, columna = _PARTES[tabla]
    fila = _parte(conn, tabla, parte_id)
    lectura = _leer(conn)
    facturas = lectura.de(columna, parte_id)
    vista = {
        "id": parte_id, "nombre": fila["nombre"], "exact_id": fila["exact_id"],
        "btw_id": fila["btw_id"], "activo": bool(fila["activo"]),
        "plazo_pago_dias": fila["plazo_pago_dias"], "hoy": lectura.hoy.isoformat(),
        **_resumen(conn, lectura, facturas),
        "abiertas_detalle": [{"id": f.id, "numero": f.numero,
                              "vencimiento": f.vencimiento.isoformat() if f.vencimiento else None,
                              "pendiente_cent": f.pendiente_cent,
                              "pendiente": _euros(f.pendiente_cent),
                              "estado_pago": f.estado(lectura.hoy)}
                             for f in _abiertas(lectura, facturas)],
        "por_objeto": _por_objeto(conn, columna, parte_id, lectura.hoy),
        "importe_tipico": _importe_tipico(conn, facturas),
        "plazo_de_pago": _plazos(lectura, facturas),
        "historial": _historial(conn, lectura, facturas),
        "pagos": _pagos(lectura, facturas),
        "avisos": _avisos(conn, tabla, parte_id, facturas),
    }
    vista["prioridad"] = _prioridades(conn, tabla).get(parte_id, _SIN_PRIORIDAD)
    if tabla == "proveedor":
        vista["ibanes"] = _ibanes(conn, parte_id)
    else:
        # §4 "Potential unbilled work": lo trabajado que no se ha facturado sale del
        # planning (V6, paso 10). Hasta entonces no hay con que contarlo: sin datos, nunca
        # cero (cero diria que no hay nada sin facturar).
        vista["trabajo_sin_facturar"] = {
            "estado": "sin_datos",
            "detalle": "Sin el planning no se puede saber qué trabajo falta por facturar "
                       "(llega con el paso 10, V6)."}
    return vista


# Lo que dice la cache de prioridad de una parte sin nada pendiente: normal, sin puntos.
_SIN_PRIORIDAD = {"nivel": "normal", "puntos": 0, "motivos": [], "vencimiento": None,
                  "importe_cent": None}


def _prioridades(conn: sqlite3.Connection, tabla: str) -> dict[int, dict[str, Any]]:
    """El nivel, los puntos y los motivos de cada proveedor o cliente (la cache prioridad).

    Los calcula estados.recalcular con prioridad.agregar (lo mas urgente de
    sus facturas y lo que se le suba a mano); aqui solo se leen, como la
    ficha de una factura lee factura_estado.
    """
    return {fila["entidad_id"]: {"nivel": fila["nivel"], "puntos": fila["puntos"],
                                 "motivos": json.loads(fila["motivos_json"]),
                                 "vencimiento": fila["vencimiento"],
                                 "importe_cent": fila["importe_cent"]}
            for fila in conn.execute("SELECT entidad_id, nivel, puntos, motivos_json, "
                                     "vencimiento, importe_cent FROM prioridad "
                                     "WHERE entidad = ?", (tabla,))}


def proveedor(conn: sqlite3.Connection, proveedor_id: int) -> dict[str, Any]:
    """La vista de un proveedor (§3). LookupError si no existe."""
    return _vista(conn, "proveedor", proveedor_id)


def cliente(conn: sqlite3.Connection, cliente_id: int) -> dict[str, Any]:
    """La vista de un cliente (§4). LookupError si no existe."""
    return _vista(conn, "cliente", cliente_id)


def _lista(conn: sqlite3.Connection, tabla: str) -> list[dict[str, Any]]:
    _sentido, columna = _PARTES[tabla]
    lectura = _leer(conn)
    por_parte: dict[int, list[Any]] = defaultdict(list)
    for f in lectura.facturas:
        if getattr(f, columna) is not None:
            por_parte[getattr(f, columna)].append(f)
    prioridades = _prioridades(conn, tabla)
    salida = []
    claves = {}
    for fila in conn.execute(f"SELECT id, nombre, exact_id, activo FROM {tabla} "
                             "ORDER BY nombre, id"):
        facturas = por_parte.get(fila["id"], [])
        resumen = _resumen(conn, lectura, facturas)
        p = prioridades.get(fila["id"], _SIN_PRIORIDAD)
        salida.append({
            "id": fila["id"], "nombre": fila["nombre"], "exact_id": fila["exact_id"],
            "activo": bool(fila["activo"]), "facturas": resumen["facturas"],
            "pendiente_cent": resumen["pendiente_cent"], "pendiente": resumen["pendiente"],
            "vencido_cent": resumen["vencido_cent"], "vencido": resumen["vencido"],
            "ano_facturado_cent": resumen["ano_facturado"]["total_cent"],
            "siempre_facturado_cent": resumen["siempre_facturado"]["total_cent"],
            "nivel": p["nivel"], "puntos": p["puntos"], "motivos": p["motivos"],
        })
        claves[fila["id"]] = prioridad.clave_orden(
            p["nivel"], p["puntos"], date.fromisoformat(p["vencimiento"])
            if p["vencimiento"] else None, p["importe_cent"], fila["id"])
    # El orden de todas las listas (§8): nivel, puntos, vencimiento, importe. A igualdad
    # (las que no tienen nada pendiente), por nombre.
    orden = {fila["id"]: i for i, fila in enumerate(salida)}
    salida.sort(key=lambda f: (claves[f["id"]][:-1], orden[f["id"]]))
    return salida


def proveedores(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Los proveedores con lo que se les debe, lo vencido y lo facturado."""
    return _lista(conn, "proveedor")


def clientes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Los clientes con lo que deben, lo vencido y lo facturado."""
    return _lista(conn, "cliente")
