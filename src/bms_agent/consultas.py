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

Lo que el §12 pide de busqueda y filtros (§18) y el resto de vistas son del
paso 12; aqui esta lo que la consola minima necesita.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from . import campos, excepciones, hallazgos, prioridad, revision
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
