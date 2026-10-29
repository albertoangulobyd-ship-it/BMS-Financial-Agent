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
(§4), y las relaciones de una factura en su ficha. Desde el paso 9, la lista
y el detalle de las ordenes de compra (§6) y el bloque de PO de la vista de
un Objeto (§5). Desde el paso 10, lo que sale del planning: las horas de la
vista de un Objeto (trabajo.horas_objeto), lo trabajado sin facturar de un
cliente (V6), lo planificado y lo sin facturar de una PO (P8, P10) y, en la
ficha de una factura, su traza a los turnos (conciliacion.traza).

Lo que el §12 pide de busqueda y filtros (§18) y el resto de vistas son del
paso 12; aqui esta lo que la consola minima necesita.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from . import (
    campos,
    conciliacion,
    excepciones,
    flujo_caja,
    hallazgos,
    prioridad,
    relaciones,
    revision,
    trabajo,
)
from . import ordenes_compra as po_
from .reglas import instantanea as instantaneas
from .reglas import ordenes as reglas_ordenes
from .reglas import turnos as reglas_turnos
from .reglas.tarifas import por_sentido
from .almacen.unidades import de_cent, de_e4, de_mil, de_pb
from .dominio import (
    ESTADOS_PENDIENTES,
    FUENTES_MANUALES,
    Calidad,
    EstadoPago,
    EstadoRevision,
    Fuente,
    Prioridad,
    TipoFactura,
)

_ORDEN_CALIDAD = (Calidad.FALTANTE.value, Calidad.DISCREPANCIA.value, Calidad.ANOMALIA.value,
                  Calidad.DUDOSO.value, Calidad.VERIFICADO.value)

# Las siete fuentes de un valor (§13), como las lee quien usa la consola.
ETIQUETA_FUENTE = {
    Fuente.EXTRACCION.value: "Extraído del documento",
    Fuente.IMPORTACION.value: "Importado de otro sistema",
    Fuente.PLANNING.value: "Del planning",
    Fuente.MAESTRO.value: "Del maestro",
    Fuente.MANUAL_ENTRADA.value: "Entrado a mano",
    Fuente.MANUAL_CORRECCION.value: "Corregido a mano",
    Fuente.CALCULADO.value: "Calculado por el sistema",
}


# Como se llama cada campo en la ficha (revision final): el identificador de la columna
# (base_cent, tipo_iva_pb) queda para quien programa, en el `campo` de cada uno.
ETIQUETA_CAMPO = {
    "numero": "Número", "proveedor_id": "Proveedor (del maestro)",
    "cliente_id": "Cliente (del maestro)", "contacto_id": "Contacto",
    "emisor_nombre_doc": "Emisor (impreso)", "emisor_direccion_doc": "Dirección del emisor",
    "emisor_kvk_doc": "KvK del emisor", "emisor_btw_doc": "BTW-id del emisor",
    "receptor_nombre_doc": "Destinatario (impreso)", "receptor_btw_doc": "BTW-id del destinatario",
    "contacto_nombre_doc": "Contacto (impreso)", "fecha_factura": "Fecha de la factura",
    "fecha_recepcion": "Recibida el", "fecha_envio": "Enviada el",
    "periodo_inicio": "Periodo desde", "periodo_fin": "Periodo hasta",
    "fecha_vencimiento": "Vence (impreso)", "plazo_pago_dias": "Plazo de pago (días)",
    "condiciones_pago_doc": "Condiciones de pago (impresas)", "base_cent": "Base (sin IVA)",
    "iva_cent": "IVA", "total_cent": "Total", "tipo_iva_pb": "Tipo de IVA",
    "tratamiento_iva": "Régimen de IVA", "kor_mencionada": "Menciona la KOR",
    "autoliquidacion_mencionada": "Menciona IVA trasladado (verlegd)",
    "referencia_pago": "Referencia de pago", "iban_doc": "IBAN impreso (no se paga a él)",
    "moneda_doc": "Moneda", "notas_doc": "Notas del documento",
    "descripcion_doc": "Descripción", "objeto_doc": "Objeto (impreso)",
    "recurso_doc": "Persona o recurso (impreso)", "unidad_doc": "Unidad (impresa)",
    "semana_doc": "Semana (impresa)", "tipo_turno_doc": "Tipo de turno (impreso)",
    "fecha_inicio": "Desde", "fecha_fin": "Hasta", "fecha_trabajo": "Día de trabajo",
    "cantidad_mil": "Cantidad", "tarifa_e4": "Tarifa", "importe_cent": "Importe",
    "objeto_id": "Objeto", "recurso_id": "Persona o recurso", "orden_compra_id": "PO",
    "horas_mil": "Horas", "facturable": "Facturable",
}


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


# ------------------------------------------------------------ los hallazgos para la app (paso 15)
#
# Cada hallazgo que sale de aqui lleva, ademas de su titulo y su detalle en
# espanol (los de la CLI y la auditoria), lo que su regla comparo (`valores`, de
# hallazgo.valores_json, los mismos que van en su huella) y su `resultado`. Con
# eso la app de la oficina escribe el detalle en neerlandes o en ingles
# (bms_agent.textos) sin traducir ninguna frase. Un hallazgo es siempre un fallo
# de su regla: lo que no se pudo mirar (sin_datos) no abre ninguno, y la ficha de
# una factura lo da aparte (`reglas_sin_datos`).

FALLO = "fallo"
SIN_DATOS = "sin_datos"
# Lo mas urgente primero: lo abierto antes que lo que ya no se ve y que lo aceptado,
# y dentro, lo que bloquea antes que lo que retiene y que lo que avisa.
_ORDEN_ESTADO = {"abierto": 0, "desaparecido": 1, "aceptado": 2}
_ORDEN_SEVERIDAD = {"bloqueo": 0, "retencion": 1, "aviso": 2}


def valores_de(fila: Any) -> dict[str, Any]:
    """Los valores de un hallazgo o de una evaluacion (vacio si no lleva)."""
    texto = fila["valores_json"]
    return json.loads(texto) if texto else {}


def razon(h: Any) -> dict[str, Any]:
    """Un hallazgo como lo pinta la app en una lista: su regla, su gravedad y sus valores."""
    return {"id": h["id"], "regla": h["regla"], "severidad": h["severidad"],
            "estado": h["estado"], "resultado": FALLO, "valores": valores_de(h)}


def _clave_razon(r: dict[str, Any]) -> tuple[int, int, int]:
    return (_ORDEN_ESTADO.get(r["estado"], 3), _ORDEN_SEVERIDAD.get(r["severidad"], 3), r["id"])


def _razones_por_factura(conn: sqlite3.Connection) -> dict[int, list[dict[str, Any]]]:
    """Los hallazgos pendientes de cada factura (los suyos y los que la senalan), lo mas
    urgente primero.

    Es el "por que" de cada fila de las listas: los `motivos` de la prioridad son
    frases en espanol, y la app no los ensena. Sacarles un gemelo estructurado
    pediria tocar las dos caches de prioridad (factura_estado y prioridad) y sus
    vistas; de los hallazgos de la fila, con sus valores, la app escribe lo mismo
    en neerlandes o en ingles.
    """
    objetivos: dict[int, set[int]] = defaultdict(set)
    for hallazgo_id, fila_id in conn.execute(
            "SELECT hallazgo_id, fila_id FROM hallazgo_objetivo WHERE tabla = 'factura'"):
        objetivos[hallazgo_id].add(fila_id)
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    salida: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for h in conn.execute(f"SELECT id, regla, severidad, estado, factura_id, valores_json "
                          f"FROM hallazgo WHERE estado IN ({marcas}) ORDER BY id",
                          sorted(ESTADOS_PENDIENTES)):
        facturas = objetivos.get(h["id"], set()) | (
            {h["factura_id"]} if h["factura_id"] is not None else set())
        for factura_id in facturas:
            salida[factura_id].append(razon(h))
    for lista in salida.values():
        lista.sort(key=_clave_razon)
    return salida


def _razones_por_parte(conn: sqlite3.Connection) -> dict[str, dict[int, list[dict[str, Any]]]]:
    """Los hallazgos pendientes de cada proveedor, cliente, Objeto y PO, lo mas urgente primero
    (contrato 2.1): el "por que" de cada fila de sus listas en la app.

    Los de un proveedor o un cliente son los de sus facturas y los que lo senalan a el (lo
    sin facturar de un cliente, V6 y V8, no es de ninguna factura); los de un Objeto, los de
    las facturas que le imputan algo; los de una PO, los que la senalan (P5-P10). Como en las
    facturas, los `motivos` de la prioridad son frases en espanol y la app no los ensena.
    """
    partes_de_factura: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for f in conn.execute("SELECT id, proveedor_id, cliente_id FROM factura"):
        if f["proveedor_id"] is not None:
            partes_de_factura[f["id"]].append(("proveedor", f["proveedor_id"]))
        if f["cliente_id"] is not None:
            partes_de_factura[f["id"]].append(("cliente", f["cliente_id"]))
    for factura_id, objeto_id in conn.execute(
            "SELECT DISTINCT factura_id, objeto_id FROM factura_imputacion "
            "WHERE retirada_en IS NULL AND objeto_id IS NOT NULL"):
        partes_de_factura[factura_id].append(("objeto", objeto_id))
    directas: dict[int, set[tuple[str, int]]] = defaultdict(set)
    facturas: dict[int, set[int]] = defaultdict(set)
    tablas = ("proveedor", "cliente", "objeto", "orden_compra")
    for hallazgo_id, tabla, fila_id in conn.execute(
            "SELECT hallazgo_id, tabla, fila_id FROM hallazgo_objetivo"):
        if tabla == "factura":
            facturas[hallazgo_id].add(fila_id)
        elif tabla in tablas:
            directas[hallazgo_id].add((tabla, fila_id))
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    salida: dict[str, dict[int, list[dict[str, Any]]]] = {t: defaultdict(list) for t in tablas}
    for h in conn.execute(f"SELECT id, regla, severidad, estado, tabla, fila_id, factura_id, "
                          f"valores_json FROM hallazgo WHERE estado IN ({marcas}) ORDER BY id",
                          sorted(ESTADOS_PENDIENTES)):
        destinos = set(directas.get(h["id"], set()))
        if h["tabla"] in tablas:
            destinos.add((h["tabla"], h["fila_id"]))
        de_facturas = facturas.get(h["id"], set()) | (
            {h["factura_id"]} if h["factura_id"] is not None else set())
        for factura_id in de_facturas:
            destinos.update(partes_de_factura.get(factura_id, ()))
        for tabla, fila_id in destinos:
            salida[tabla][fila_id].append(razon(h))
    for por_fila in salida.values():
        for lista in por_fila.values():
            lista.sort(key=_clave_razon)
    return salida


def _sin_datos_de(conn: sqlite3.Connection, factura_id: int) -> list[dict[str, Any]]:
    """Las reglas que no pudieron mirar una factura (evaluacion sin_datos), en el orden del
    catalogo: lo que "Sin objeciones en lo comprobado; N reglas sin datos" no dice."""
    from .reglas.catalogo import CATALOGO

    orden = {r.id: i for i, r in enumerate(CATALOGO)}
    filas = conn.execute("SELECT regla, clave, detalle, valores_json FROM evaluacion "
                         "WHERE tabla = 'factura' AND fila_id = ? AND resultado = ?",
                         (factura_id, SIN_DATOS)).fetchall()
    filas.sort(key=lambda e: (orden.get(e["regla"], len(orden)), e["clave"]))
    return [{"regla": e["regla"], "clave": e["clave"], "resultado": SIN_DATOS,
             "detalle": e["detalle"], "valores": valores_de(e)} for e in filas]


# ------------------------------------------------------------ la lista

def _pendientes_por_factura(conn: sqlite3.Connection) -> dict[int, tuple[int, int]]:
    """(pendientes, de ellos aceptados) por factura."""
    cuentas: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for factura_id, _clave, _huella, estado, _anulacion in revision.pendientes_por_factura(conn):
        cuentas[factura_id][0] += 1
        if estado == "aceptado":
            cuentas[factura_id][1] += 1
    return {f: (c[0], c[1]) for f, c in cuentas.items()}


def _objetos_por_factura(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """Los codigos de los Objetos a los que imputa cada factura (sus imputaciones activas)."""
    salida: dict[int, list[str]] = defaultdict(list)
    for factura_id, codigo in conn.execute(
            "SELECT DISTINCT i.factura_id, o.codigo FROM factura_imputacion AS i "
            "JOIN objeto AS o ON o.id = i.objeto_id WHERE i.retirada_en IS NULL "
            "ORDER BY i.factura_id, o.codigo"):
        salida[factura_id].append(codigo)
    return salida


def _filas_listado(conn: sqlite3.Connection, donde: str = "",
                   parametros: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Las facturas de v_factura_listado que cumplen `donde`, la mas urgente primero.

    `donde` solo lo escriben listado() y buscar() con fragmentos fijos de este
    modulo; los valores van siempre en `parametros`.
    """
    pendientes = _pendientes_por_factura(conn)
    excepciones_ = {f["fila_id"]: (f["id"], f["estado"]) for f in conn.execute(
        "SELECT id, fila_id, estado FROM excepcion WHERE tabla = 'factura' "
        "AND estado <> 'resuelta'")}
    objetos_ = _objetos_por_factura(conn)
    razones = _razones_por_factura(conn)
    # Contrato 2.3: la rev de cada factura, para que una orden desde una lista (apuntar un pago
    # con su linea del banco) lleve la que la persona vio.
    revs = dict(conn.execute("SELECT id, rev FROM factura").fetchall())
    # Contrato 2.4 (revision del paso 16): la fuente que manda en lo pagado (banco, exact o
    # manual), de la vista de los saldos, para que "pagada" vaya siempre con su fuente
    # tambien en las listas (y lo apuntado a mano, con el aviso K3 de sus razones).
    fuentes = dict(conn.execute("SELECT factura_id, fuente_pago FROM v_factura_saldo"
                                ).fetchall())
    total = campos.campo("factura", "total_cent")
    filas = []
    for f in conn.execute(f"SELECT * FROM v_factura_listado{' WHERE ' + donde if donde else ''}",
                          parametros):
        n_pendientes, aceptados = pendientes.get(f["id"], (0, 0))
        excepcion = excepciones_.get(f["id"])
        filas.append({
            "id": f["id"], "rev": revs.get(f["id"]), "numero": f["numero"],
            "sentido": f["sentido"], "tipo": f["tipo"],
            "contraparte": f["contraparte"],
            "proveedor_id": f["proveedor_id"], "cliente_id": f["cliente_id"],
            "fecha_factura": f["fecha_factura"], "vencimiento": f["vencimiento"],
            "periodo_desde": f["periodo_desde"], "periodo_hasta": f["periodo_hasta"],
            "base_cent": f["base_cent"], "total_cent": f["total_cent"],
            "total": texto_de(total, f["total_cent"]),
            "pendiente_cent": f["pendiente_cent"], "pendiente": texto_de(total, f["pendiente_cent"]),
            "anulada": bool(f["anulada"]), "fusionada_en_id": f["fusionada_en_id"],
            "sustituida_por": f["sustituida_por"], "cuenta": bool(f["cuenta"]),
            "objetos": objetos_.get(f["id"], []),
            "nivel": f["nivel"] or prioridad.NORMAL, "puntos": f["puntos"] or 0,
            "suelo": f["suelo"] or prioridad.NORMAL,
            "motivos": json.loads(f["motivos_json"]) if f["motivos_json"] else [],
            "estado_revision": f["estado_revision"], "calidad": f["calidad"],
            "estado_pago": f["estado_pago"], "dias_vencida": f["dias_vencida"],
            "fuente_pago": fuentes.get(f["id"]),
            "editada": bool(f["editada"]), "suplementada": bool(f["suplementada"]),
            "corregida": bool(f["corregida"]), "sin_resolver": f["sin_resolver"] or 0,
            "dudosos": f["dudosos"] or 0, "pendientes": n_pendientes, "aceptados": aceptados,
            "sin_datos": f["sin_datos"] or 0,
            "etiqueta": revision.etiqueta_sistema(n_pendientes, aceptados, f["sin_datos"] or 0,
                                                  (f["sin_resolver"] or 0) + (f["dudosos"] or 0)),
            "excepcion": {"id": excepcion[0], "estado": excepcion[1]} if excepcion else None,
            # Contrato 2.1: sus hallazgos pendientes, lo mas urgente primero, para el
            # "por que" de la app en neerlandes o en ingles.
            "razones": razones.get(f["id"], []),
        })
    filas.sort(key=_clave_prioridad)
    return filas


def _clave_prioridad(r: dict[str, Any]) -> tuple:
    """El orden de todas las listas (§8): nivel, puntos, vencimiento, importe e id."""
    return prioridad.clave_orden(
        r["nivel"], r["puntos"], date.fromisoformat(r["vencimiento"]) if r["vencimiento"] else None,
        r["base_cent"] if r["base_cent"] is not None else r["total_cent"], r["id"])


def listado(conn: sqlite3.Connection, *, nivel: str | None = None,
            limite: int | None = None) -> list[dict[str, Any]]:
    """Las facturas, la mas urgente primero, con lo que la consola ensena en la lista."""
    filas = (_filas_listado(conn, "nivel = ?", (nivel,)) if nivel is not None
             else _filas_listado(conn))
    return filas[:limite] if limite is not None else filas


def excepciones_abiertas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Las excepciones sin resolver, la mas urgente primero."""
    nombres = _nombres(conn)
    prioridades = {f["entidad_id"]: f for f in conn.execute(
        "SELECT * FROM prioridad WHERE entidad = 'excepcion'")}
    salida = []
    for e in excepciones.sin_resolver(conn):
        p = prioridades.get(e["id"])
        suyos = excepciones.hallazgos_de(conn, e["id"])
        salida.append({
            **_excepcion(e, nombres),
            "nivel": p["nivel"] if p else prioridad.NORMAL, "puntos": p["puntos"] if p else 0,
            "motivos": json.loads(p["motivos_json"]) if p else [],
            "vencimiento": p["vencimiento"] if p else None,
            "importe_cent": p["importe_cent"] if p else None,
            "hallazgos": [h["id"] for h in suyos],
            # Contrato 2.1: los mismos hallazgos con su regla y sus valores (el titulo de
            # la excepcion es una frase en espanol).
            "razones": sorted((razon(h) for h in suyos), key=_clave_razon),
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
               solo: tuple[str, ...] | None = None,
               motivos: dict[tuple[str, int, str], str | None] | None = None,
               ) -> list[dict[str, Any]]:
    """Cada campo de una fila con su valor, su original, su fuente y sus marcas.

    Desde el paso 12 lleva tambien la etiqueta de su fuente (las siete del
    §13, como se leen en la consola), la referencia de esa fuente (la
    extraccion o la importacion concreta) y, si una persona lo cambio, el
    motivo que escribio (`motivos`: el del ultimo cambio de cada campo).
    """
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
            "etiqueta": ETIQUETA_CAMPO.get(nombre, nombre),
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
            "fuente_texto": ETIQUETA_FUENTE.get(estado.fuente or "", None),
            "fuente_ref": p["fuente_ref"] if p else None,
            "motivo": (motivos or {}).get(clave) if estado.editado else None,
        })
    return salida


def _ultimos_motivos(conn: sqlite3.Connection,
                     factura_id: int) -> dict[tuple[str, int, str], str | None]:
    """El motivo del ultimo cambio de cada campo de una factura y de sus hijas (§11)."""
    return {(tabla, fila_id, campo): motivo for tabla, fila_id, campo, motivo in conn.execute(
        "SELECT tabla, fila_id, campo, motivo FROM cambio_campo WHERE factura_id = ? "
        "ORDER BY id", (factura_id,))}


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
    motivos = _ultimos_motivos(conn, factura_id)

    lineas = []
    for linea in conn.execute("SELECT * FROM factura_linea WHERE factura_id = ? "
                              "ORDER BY orden, id", (factura_id,)):
        imputaciones = []
        for imp in conn.execute("SELECT * FROM factura_imputacion WHERE linea_id = ? "
                                "ORDER BY id", (linea["id"],)):
            objeto = conn.execute("SELECT codigo, nombre FROM objeto WHERE id = ?",
                                  (imp["objeto_id"],)).fetchone() if imp["objeto_id"] else None
            orden = conn.execute("SELECT numero FROM orden_compra WHERE id = ?",
                                 (imp["orden_compra_id"],)).fetchone() if imp[
                "orden_compra_id"] else None
            recurso = conn.execute("SELECT nombre FROM recurso WHERE id = ?",
                                   (imp["recurso_id"],)).fetchone() if imp["recurso_id"] else None
            imputaciones.append({
                "id": imp["id"], "rev": imp["rev"], "retirada": imp["retirada_en"] is not None,
                "objeto_id": imp["objeto_id"],
                "objeto": f"{objeto['codigo']}" if objeto else None,
                "orden_compra_id": imp["orden_compra_id"],
                "orden_compra": orden["numero"] if orden else None,
                "recurso_id": imp["recurso_id"], "recurso": recurso["nombre"] if recurso else None,
                "importe": _euros(imp["importe_cent"]), "horas": _horas_texto(imp["horas_mil"]),
                "campos": _campos_de(conn, "factura_imputacion", imp, sentido, de_hallazgos,
                                     sin_resolver, nombres,
                                     solo=("objeto_id", "recurso_id", "orden_compra_id",
                                           "horas_mil", "importe_cent", "facturable"),
                                     motivos=motivos),
            })
        lineas.append({
            "id": linea["id"], "rev": linea["rev"], "orden": linea["orden"],
            "retirada": linea["retirada_en"] is not None,
            "campos": _campos_de(conn, "factura_linea", linea, sentido, de_hallazgos,
                                 sin_resolver, nombres,
                                 solo=("descripcion_doc", "objeto_doc", "recurso_doc",
                                       "unidad_doc", "semana_doc", "tipo_turno_doc",
                                       "fecha_inicio", "fecha_fin", "fecha_trabajo",
                                       "cantidad_mil", "tarifa_e4", "importe_cent",
                                       "tipo_iva_pb"), motivos=motivos),
            "imputaciones": imputaciones,
        })
    referencias = [{"id": r["id"], "rev": r["rev"], "etiqueta": r["etiqueta_doc"],
                    "valor": r["valor_doc"], "clase": r["clase"],
                    "orden_compra_id": r["orden_compra_id"],
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
            # 2.1: las segundas firmas que ya hay y aun valen (para quien, de quien, el plazo
            # firmado y cuando caducan): la app ofrece aceptar solo a quien tiene la suya.
            "firmas": [{"solicitante_id": f["solicitante_id"], "firmante_id": f["usuario_id"],
                        "firmante": nombres.get(f["usuario_id"]),
                        "vigente_hasta": f["vigente_hasta"], "caduca_en": f["caduca_en"]}
                       for f in hallazgos.firmas_vigentes(conn, h)],
            "primera_vez_en": h["primera_vez_en"], "objetivos": objetivos.get(h["id"], []),
            "resultado": FALLO, "valores": valores_de(h),
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
                             nombres, motivos=motivos),
        "lineas": lineas, "referencias": referencias, "hallazgos": lista_hallazgos,
        # Contrato 2.1: lo que las reglas no pudieron mirar, con sus valores.
        "reglas_sin_datos": _sin_datos_de(conn, factura_id),
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
        # Paso 10: de cada imputacion, los turnos del planning con que se concilio.
        "conciliacion": conciliacion.traza(conn, factura_id),
        # Revision final: lo pagado (para confirmar o retirar un pago desde la consola), el
        # original (se descarga, y queda en la auditoria) y de donde sale su vencimiento.
        "pagos": _pagos_de_factura(conn, factura_id),
        "original": _original_de(conn, factura["documento_id"]),
        "vencimiento": _vencimiento_de(conn, factura, estado),
    }


def _pagos_de_factura(conn: sqlite3.Connection, factura_id: int) -> list[dict[str, Any]]:
    """Cada pago apuntado de una factura (propuesto, confirmado o retirado), con su rev.

    Contrato 2.3 (paso 16): tambien quien lo confirmo o lo apunto (`persona`, solo si fue
    una persona: lo que caso el banco solo no lleva nombre) y cuando, su `motivo` (lo que
    escribio esa persona: texto), el documento que lo prueba (`evidencia_documento_id`), el
    dia y el importe de su linea del banco, y de uno retirado, quien y por que
    (`retirada_por`, `motivo_retirada`). Asi la ficha dice "apuntado a mano por Ana" y
    ensena la linea al lado del pago.
    """
    from . import pagos

    personas = dict(conn.execute("SELECT id, nombre FROM usuario WHERE es_sistema = 0")
                    .fetchall())
    # Quien retiro un pago y por que: el motivo va en su evento (retirar no lo escribe en la
    # fila), el ultimo de cada pago.
    retiradas = {e["fila_id"]: (personas.get(e["usuario_id"]), e["motivo"]) for e in conn.execute(
        "SELECT fila_id, usuario_id, motivo FROM evento WHERE tabla = 'aplicacion_pago' "
        "AND tipo = 'pago_retirado' AND factura_id = ? ORDER BY id", (factura_id,))}
    return [{"id": a["id"], "rev": a["rev"], "estado": a["estado"], "fuente": a["fuente"],
             "metodo": a["metodo"], "importe_cent": a["importe_cent"],
             "importe": _euros(a["importe_cent"]), "fecha_pago": a["fecha_pago"],
             "movimiento_id": a["movimiento_id"], "regla": a["regla"],
             "concepto": a["concepto_doc"], "contraparte": a["contraparte_nombre_doc"],
             "persona": personas.get(a["confirmada_por"]),
             "confirmada_en": a["confirmada_en"], "retirada_en": a["retirada_en"],
             "motivo": a["motivo"], "evidencia_documento_id": a["evidencia_documento_id"],
             "movimiento_fecha": a["fecha_contable"],
             "movimiento_importe_cent": a["importe_movimiento"],
             "movimiento_importe": _euros(a["importe_movimiento"]),
             "retirada_por": retiradas.get(a["id"], (None, None))[0],
             "motivo_retirada": retiradas.get(a["id"], (None, None))[1]}
            for a in pagos.de_factura(conn, factura_id)["aplicaciones"]]


def _original_de(conn: sqlite3.Connection, documento_id: int | None) -> dict[str, Any] | None:
    """El original de una factura: si esta guardado, se descarga desde la consola
    (GET /api/v2/facturas/N/original) o con `bms-agent original`."""
    if documento_id is None:
        return None
    d = conn.execute("SELECT id, nombre_original, tipo_mime, bytes, sha256, ruta_cas "
                     "FROM documento WHERE id = ?", (documento_id,)).fetchone()
    if d is None:
        return None
    return {"documento_id": d["id"], "nombre": d["nombre_original"], "tipo": d["tipo_mime"],
            "bytes": d["bytes"], "sha256": d["sha256"], "guardado": d["ruta_cas"] is not None}


def _vencimiento_de(conn: sqlite3.Connection, factura: sqlite3.Row,
                    estado: sqlite3.Row | None) -> dict[str, Any]:
    """El vencimiento efectivo y de donde sale (§13): el impreso, o la fecha mas el plazo, del
    maestro antes que del papel (instantanea.vencimientos). Si sale del plazo acordado en el
    maestro, la fuente es el maestro, con el proveedor o el cliente de donde viene."""
    fecha = estado["vencimiento"] if estado is not None else None
    fuente, referencia, plazo = None, None, None
    procedencias = campos.procedencia(conn, "factura", factura["id"])
    if factura["fecha_vencimiento"] is not None:
        fuente = (procedencias.get("fecha_vencimiento") or {}).get("fuente")
    elif fecha is not None:
        tabla = "proveedor" if factura["sentido"] == "entrante" else "cliente"
        parte_id = factura["proveedor_id"] if tabla == "proveedor" else factura["cliente_id"]
        acordado = conn.execute(f"SELECT plazo_pago_dias FROM {tabla} WHERE id = ?",
                                (parte_id,)).fetchone() if parte_id is not None else None
        propio = procedencias.get("plazo_pago_dias")
        del_papel = (propio is not None and propio["fuente"] == Fuente.CALCULADO.value
                     and propio["fuente_ref"] == "condiciones_pago_doc")
        if acordado is not None and acordado[0] is not None and (
                factura["plazo_pago_dias"] is None or del_papel):
            fuente, referencia, plazo = Fuente.MAESTRO.value, f"{tabla}:{parte_id}", acordado[0]
        else:
            fuente, plazo = (propio or {}).get("fuente"), factura["plazo_pago_dias"]
    return {"fecha": fecha, "fuente": fuente, "fuente_texto": ETIQUETA_FUENTE.get(fuente or ""),
            "fuente_ref": referencia, "plazo_dias": plazo}


def _planning(conn: sqlite3.Connection) -> Any:
    """La instantanea de hoy si hay algun planning importado; None si no (las vistas dicen
    entonces sin datos, nunca cero)."""
    from .almacen import reloj_de
    from .politica import politica_reglas

    if not instantaneas.fotos_planning(conn):
        return None
    return instantaneas.construir(conn, hoy=reloj_de(conn).hoy(),
                                  politica=politica_reglas(conn))


def personas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Las personas activas, para asignar una excepcion; con sus roles (contrato 2.1: la lista
    de personas de Instellingen, para quien administra)."""
    from .permisos import roles_de

    return [{"id": f["id"], "nombre": f["nombre"], "roles": roles_de(conn, f["id"])}
            for f in conn.execute("SELECT id, nombre FROM usuario WHERE es_sistema = 0 "
                                  "AND activo = 1 ORDER BY nombre")]


def recursos(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Las personas y recursos del maestro (los de las lineas de horas), para imputar una linea a
    uno de ellos desde la consola."""
    return [{"id": f["id"], "nombre": f["nombre"], "tipo": f["tipo"],
             "activo": bool(f["activo"])} for f in conn.execute(
        "SELECT id, nombre, tipo, activo FROM recurso ORDER BY activo DESC, nombre, id")]


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


def _abonos_sin_enlazar(lectura: _Lectura, facturas: list[Any]) -> list[Any]:
    """Los abonos que aun no se enlazaron a su factura (R4) y acreditan algo: los que la
    vista de una parte resta de lo pendiente y la cartera da aparte. Una sola definicion
    para las dos."""
    from .estados import EN_JUEGO

    return [f for f in facturas if _cuenta(f) and f.total_cent is not None
            and f.total_cent < 0 and f.pendiente_cent is not None and f.pendiente_cent < 0
            and f.estado(lectura.hoy) in EN_JUEGO]


def _partidas_por_parte(lectura: _Lectura, partidas: list[Any],
                        columna: str) -> dict[int | None, list[Any]]:
    """Las partidas de la cartera (flujo_caja.datos: lo que queda de cada deuda) por empresa
    (`columna`: proveedor_id o cliente_id; None, sin empresa del maestro). La cartera y las
    listas y vistas de las partes cuentan lo pendiente de una empresa con esta misma
    funcion: una sola cifra de "pendiente" en toda la app (revision del paso 16)."""
    por_id = {f.id: f for f in lectura.facturas}
    salida: dict[int | None, list[Any]] = defaultdict(list)
    for p in partidas:
        factura = por_id.get(p.factura_id)
        salida[getattr(factura, columna) if factura is not None else None].append(p)
    return salida


def _deudas_por_parte(conn: sqlite3.Connection, lectura: _Lectura,
                      tabla: str) -> dict[int | None, int]:
    """Lo que queda de las deudas de cada proveedor (o cliente), en centimos: lo que dice la
    cartera de cada empresa (`partes[].pendiente_cent`), de las mismas partidas."""
    sentido, columna = _PARTES[tabla]
    direccion = SENTIDOS_CARTERA[sentido][0]
    partidas = [p for p in flujo_caja.datos(conn)[0] if p.direccion == direccion]
    return {parte: sum(p.importe_cent for p in suyas)
            for parte, suyas in _partidas_por_parte(lectura, partidas, columna).items()}


def _deuda_y_abonos(lectura: _Lectura, facturas: list[Any], deuda: int) -> dict[str, Any]:
    """Contrato 2.4: lo pendiente de una parte partido en sus dos piezas. `deuda_cent` es lo
    que queda de sus facturas (la cifra de la cartera, "Openstaand" en la app) y
    `abonos_sin_enlazar_cent` lo que acreditan sus abonos sin enlazar (cero o negativo).
    `pendiente_cent` (de siempre) es la suma de las dos: la vista resta esos abonos desde la
    migracion 0017, a proposito, y no cambia."""
    abonos = _abonos_sin_enlazar(lectura, facturas)
    abonado = sum(f.pendiente_cent for f in abonos)
    return {"deuda_cent": deuda, "deuda": _euros(deuda),
            "abonos_sin_enlazar_cent": abonado, "abonos_sin_enlazar": _euros(abonado),
            "abonos_sin_enlazar_facturas": len(abonos)}


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
                               "estado": h["estado"], "factura_id": h["factura_id"],
                               "resultado": FALLO, "valores": valores_de(h)})
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


def _impresos(conn: sqlite3.Connection,
              proveedor_id: int | None = None) -> dict[int, dict[str, dict[str, Any]]]:
    """Los IBAN que han impreso las facturas de cada proveedor (o de uno), por IBAN.

    La primera y la ultima fecha son las de las facturas fechadas: una sin
    fecha legible cuenta en el numero, pero no deja la primera sin fecha.
    """
    from .reglas.normas import normalizar_iban

    impresos: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for proveedor, iban, fecha in conn.execute(
            "SELECT proveedor_id, iban_doc, fecha_factura FROM factura "
            "WHERE proveedor_id IS NOT NULL AND (? IS NULL OR proveedor_id = ?) "
            "AND iban_doc IS NOT NULL ORDER BY fecha_factura IS NULL, fecha_factura, id",
            (proveedor_id, proveedor_id)):
        clave = normalizar_iban(iban) or iban
        visto = impresos[proveedor].setdefault(
            clave, {"iban": clave, "primera": fecha, "ultima": fecha, "facturas": 0})
        visto["primera"] = visto["primera"] or fecha
        visto["ultima"] = fecha or visto["ultima"]
        visto["facturas"] += 1
    return impresos


def _con_registro(impresos: dict[str, dict[str, Any]],
                  registro: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Los IBAN impresos, cada uno con si esta en el registro de cuentas del proveedor.

    Lo que trae una factura y el registro no tiene es lo que F3 pide verificar.
    """
    from .reglas.normas import normalizar_iban

    registradas = {normalizar_iban(c["iban"]) for c in registro}
    return [{**visto, "en_el_registro": visto["iban"] in registradas}
            for visto in impresos.values()]


def _ibanes(conn: sqlite3.Connection, proveedor_id: int) -> dict[str, Any]:
    """Las cuentas del registro (con su estado) y los IBAN que han impreso sus facturas."""
    registro = [c for c in cuentas(conn) if c["proveedor_id"] == proveedor_id]
    impresos = _impresos(conn, proveedor_id).get(proveedor_id, {})
    return {"registro": registro, "impresos": _con_registro(impresos, registro)}


def registro_de_cuentas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Por proveedor: el telefono al que se llama, sus cuentas y lo impreso fuera del registro.

    Es lo que `iban listar` ensena. Quien verifica necesita las tres cosas a
    la vez: el numero del maestro (el unico al que se llama), el estado de
    cada cuenta y la cuenta que una factura trae y nadie ha verificado
    todavia (F3), que no esta en el registro hasta que alguien la verifica o
    la rechaza.
    """
    por_proveedor: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for c in cuentas(conn):
        por_proveedor[c["proveedor_id"]].append(c)
    impresos = _impresos(conn)
    salida = []
    for fila in conn.execute("SELECT id, nombre, telefono_verificacion FROM proveedor "
                             "ORDER BY nombre, id"):
        registro = por_proveedor.get(fila["id"], [])
        fuera = [v for v in _con_registro(impresos.get(fila["id"], {}), registro)
                 if not v["en_el_registro"]]
        if registro or fuera:
            salida.append({"proveedor_id": fila["id"], "proveedor": fila["nombre"],
                           "telefono_verificacion": fila["telefono_verificacion"],
                           "cuentas": registro, "sin_registrar": fuera})
    return salida


# Lo que se cambia con su propia orden y no con corregir_maestro.
_CON_SU_ORDEN = {"telefono_verificacion"}


def _corregibles(tabla: str, fila: sqlite3.Row) -> list[dict[str, Any]]:
    """Los campos de un proveedor o un cliente que una persona puede corregir en la consola
    (corregir_maestro): en una fila de Exact o de TRNSPRNT, solo los que esos sistemas no
    traen (lo suyo se corrige alli y lo trae la siguiente importacion)."""
    de_fuera = bool(fila["exact_id"] or fila["trnsprnt_id"])
    salida = []
    for nombre, definicion in campos.REGISTRO[tabla].items():
        if not definicion.editable or nombre in campos.ESTRUCTURA.get(tabla, ()):
            continue
        if nombre in _CON_SU_ORDEN or (definicion.externo and de_fuera):
            continue
        salida.append({"campo": nombre, "etiqueta": ETIQUETA_CAMPO.get(nombre, nombre),
                       "texto": texto_de(definicion, fila[nombre]),
                       "entrada": entrada_de(definicion, fila[nombre])})
    return salida


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
        **_deuda_y_abonos(lectura, facturas,
                          _deudas_por_parte(conn, lectura, tabla).get(parte_id, 0)),
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
    vista["rev"] = fila["rev"]
    vista["corregibles"] = _corregibles(tabla, fila)
    # Contrato 2.2 (paso 16): la ficha de la carpeta en el archivo de la app. Lo que el
    # maestro tiene (KvK, correo de facturacion y direccion: el de clientes no guarda ni
    # correo ni direccion, y van null), sus personas de contacto, sus PO y, de un cliente,
    # sus Objetos. El telefono de un contacto no es el de verificar una cuenta: ese es
    # `telefono_verificacion`, del maestro de proveedores.
    columnas = fila.keys()
    vista["kvk"] = fila["kvk"]
    vista["email_facturacion"] = fila["email_facturacion"] if "email_facturacion" in columnas \
        else None
    vista["direccion"] = fila["direccion"] if "direccion" in columnas else None
    vista["contactos"] = _contactos(conn, tabla, parte_id)
    vista["ordenes_compra"] = [o for o in ordenes_compra(conn)
                               if o["parte"]["tabla"] == tabla and o["parte"]["id"] == parte_id]
    vista["documentos"] = len(_documentos(conn, tabla, parte_id).get(parte_id, []))
    if tabla == "cliente":
        vista["objetos"] = [{"id": o["id"], "codigo": o["codigo"], "nombre": o["nombre"],
                             "activo_desde": o["activo_desde"], "activo_hasta": o["activo_hasta"]}
                            for o in conn.execute(
                                "SELECT id, codigo, nombre, activo_desde, activo_hasta "
                                "FROM objeto WHERE cliente_id = ? ORDER BY codigo, id",
                                (parte_id,))]
    if tabla == "proveedor":
        vista["ibanes"] = _ibanes(conn, parte_id)
        # El numero al que se llama para verificar una cuenta (uso-v1.md): el del maestro, no
        # el de ninguna factura.
        vista["telefono_verificacion"] = fila["telefono_verificacion"]
    else:
        vista["trabajo_sin_facturar"] = _sin_facturar(conn, parte_id)
    return vista


def _contactos(conn: sqlite3.Connection, tabla: str, parte_id: int) -> list[dict[str, Any]]:
    """Las personas de contacto de un proveedor o un cliente (del maestro), las activas
    primero."""
    return [{"id": c["id"], "nombre": c["nombre"], "email": c["email"],
             "telefono": c["telefono"], "funcion": c["funcion"], "activo": bool(c["activo"])}
            for c in conn.execute(
                f"SELECT id, nombre, email, telefono, funcion, activo FROM contacto "
                f"WHERE {tabla}_id = ? ORDER BY activo DESC, nombre, id", (parte_id,))]


def _sin_facturar(conn: sqlite3.Connection, cliente_id: int) -> dict[str, Any]:
    """§4 "Potential unbilled work": lo que dicen los V6 sin cerrar del cliente (trabajo
    validado facturable sin facturar pasado su periodo y su gracia). Sin planning no hay con
    que contarlo: sin datos, nunca cero (cero diria que no hay nada sin facturar)."""
    if not instantaneas.fotos_planning(conn):
        return {"estado": "sin_datos",
                "detalle": "No se ha importado ningún planning de TRNSPRNT: no se puede saber "
                           "qué trabajo falta por facturar (V6)."}
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    periodos = []
    for h in conn.execute(
            f"SELECT id, estado, detalle, valores_json FROM hallazgo WHERE regla = 'V6' "
            f"AND tabla = 'cliente' AND fila_id = ? AND estado IN ({marcas}) ORDER BY id",
            (cliente_id, *sorted(ESTADOS_PENDIENTES))):
        valores = json.loads(h["valores_json"] or "{}")
        periodos.append({"hallazgo_id": h["id"], "estado": h["estado"],
                         "regla": "V6", "resultado": FALLO, "valores": valores,
                         "detalle": h["detalle"], "objeto_id": valores.get("objeto"),
                         "desde": valores.get("desde"), "hasta": valores.get("hasta"),
                         "horas_mil": valores.get("horas_mil"),
                         "horas": _horas_texto(valores.get("horas_mil")),
                         "valor_cent": valores.get("valor_cent"),
                         "valor": _euros(valores.get("valor_cent")),
                         "estimado": bool(valores.get("estimado"))})
    horas = sum(p["horas_mil"] or 0 for p in periodos)
    valor = sum(p["valor_cent"] or 0 for p in periodos)
    return {"estado": "ok", "periodos": periodos, "horas_mil": horas,
            "horas": _horas_texto(horas), "valor_cent": valor, "valor": _euros(valor),
            "estimado": any(p["estimado"] for p in periodos)}


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
    razones = _razones_por_parte(conn)[tabla]
    documentos = _documentos(conn, tabla)
    deudas = _deudas_por_parte(conn, lectura, tabla)
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
            # Contrato 2.4: lo de la cartera y los abonos sin enlazar, aparte.
            **_deuda_y_abonos(lectura, facturas, deudas.get(fila["id"], 0)),
            "vencido_cent": resumen["vencido_cent"], "vencido": resumen["vencido"],
            "ano_facturado_cent": resumen["ano_facturado"]["total_cent"],
            "siempre_facturado_cent": resumen["siempre_facturado"]["total_cent"],
            # 2.1: sus facturas sin importe en euros (otra moneda, X1): fuera de las sumas, asi
            # que un "0,00 pendiente" no quiere decir "no se debe nada".
            "sin_importe": resumen["sin_importe"],
            "nivel": p["nivel"], "puntos": p["puntos"], "motivos": p["motivos"],
            # Contrato 2.1: sus hallazgos pendientes, para el "por que" de la app.
            "razones": razones.get(fila["id"], []),
            # Contrato 2.2: cuantos documentos tiene su carpeta (GET .../N/documentos).
            "documentos": len(documentos.get(fila["id"], [])),
            # 2.5: cuantos de esos son facturas (o abonos): las dos cifras, de la misma carpeta.
            "documentos_factura": sum(1 for d in documentos.get(fila["id"], [])
                                      if d["vinculo"]["tabla"] == "factura"),
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


# ------------------------------------------------------------ ordenes de compra (paso 9)

def _pct(puntos: int) -> str:
    """Puntos basicos como porcentaje con coma (8125 es "81,25 %")."""
    signo = "-" if puntos < 0 else ""
    return f"{signo}{abs(puntos) // 100},{abs(puntos) % 100:02d} %"


def _iso(dia: date | None) -> str | None:
    return dia.isoformat() if dia else None


def _nombres_de_partes(conn: sqlite3.Connection) -> dict[tuple[str, int], str]:
    return {(tabla, fila_id): nombre for tabla, fila_id, nombre in conn.execute(
        "SELECT 'cliente', id, nombre FROM cliente UNION ALL "
        "SELECT 'proveedor', id, nombre FROM proveedor")}


def _cifras(orden: Any, lista: list[Any]) -> dict[str, Any]:
    """Valor vigente, consumido, restante y porcentajes de una PO (§6, PO spend)."""
    s = po_.situacion(orden, lista)
    return {"valor_cent": s.valor_cent, "valor": _euros(s.valor_cent),
            "consumido_cent": s.consumido_cent, "consumido": _euros(s.consumido_cent),
            "restante_cent": s.restante_cent, "restante": _euros(s.restante_cent),
            "consumido_pb": s.consumido_pb, "consumido_pct": _pct(s.consumido_pb),
            "restante_pb": s.restante_pb, "restante_pct": _pct(s.restante_pb)}


def _cabecera_po(orden: Any, nombres: dict[tuple[str, int], str]) -> dict[str, Any]:
    return {"id": orden.id, "numero": orden.numero, "lado": orden.lado,
            "parte": {"tabla": orden.lado, "id": orden.parte_id,
                      "nombre": nombres.get((orden.lado, orden.parte_id))},
            "fecha_emision": _iso(orden.fecha_emision), "fecha_inicio": _iso(orden.fecha_inicio),
            "fecha_fin": _iso(orden.fecha_fin), "cerrada": orden.cerrada}


def ordenes_compra(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Las PO con su valor vigente, lo consumido, lo que queda y su prioridad (§6, §8)."""
    ordenes = po_.ordenes(conn)
    if not ordenes:
        return []
    cargos = po_.cargos(conn)
    nombres = _nombres_de_partes(conn)
    prioridades = _prioridades(conn, "orden_compra")
    razones = _razones_por_parte(conn)["orden_compra"]
    salida, claves = [], {}
    for orden in ordenes.values():
        p = prioridades.get(orden.id, _SIN_PRIORIDAD)
        salida.append({**_cabecera_po(orden, nombres), **_cifras(orden, cargos.get(orden.id, [])),
                       "nivel": p["nivel"], "puntos": p["puntos"], "motivos": p["motivos"],
                       "razones": razones.get(orden.id, [])})
        claves[orden.id] = prioridad.clave_orden(
            p["nivel"], p["puntos"], date.fromisoformat(p["vencimiento"])
            if p["vencimiento"] else None, p["importe_cent"], orden.id)
    salida.sort(key=lambda f: (claves[f["id"]][:-1], f["fecha_fin"] is None,
                               f["fecha_fin"] or "", f["numero"], f["id"]))
    return salida


def _modificaciones(conn: sqlite3.Connection, po_id: int) -> list[dict[str, Any]]:
    return [{"id": f["id"], "fecha": f["fecha"], "valor_nuevo_cent": f["valor_nuevo_cent"],
             "valor_nuevo": _euros(f["valor_nuevo_cent"]),
             "fecha_fin_nueva": f["fecha_fin_nueva"], "motivo": f["motivo"],
             "usuario": f["usuario"], "en": f["en"], "importacion_id": f["importacion_id"],
             "documento_id": f["documento_id"]}
            for f in conn.execute(
                "SELECT m.*, u.nombre AS usuario FROM orden_compra_modificacion AS m "
                "JOIN usuario AS u ON u.id = m.usuario_id WHERE m.orden_compra_id = ? "
                "ORDER BY m.fecha, m.id", (po_id,))]


def _avisos_po(conn: sqlite3.Connection, po_id: int) -> dict[str, Any]:
    """Los hallazgos sin cerrar de la PO y los que la senalan, y sus excepciones abiertas."""
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    hallazgos_ = [{"id": h["id"], "regla": h["regla"], "titulo": h["titulo"],
                   "detalle": h["detalle"], "severidad": h["severidad"], "estado": h["estado"],
                   "factura_id": h["factura_id"], "resultado": FALLO, "valores": valores_de(h)}
                  for h in conn.execute(
                      f"SELECT * FROM hallazgo WHERE estado IN ({marcas}) AND ((tabla = "
                      "'orden_compra' AND fila_id = ?) OR id IN (SELECT hallazgo_id FROM "
                      "hallazgo_objetivo WHERE tabla = 'orden_compra' AND fila_id = ?)) "
                      "ORDER BY id", (*sorted(ESTADOS_PENDIENTES), po_id, po_id))]
    excepciones_ = [{"id": e["id"], "estado": e["estado"], "titulo": e["titulo"]}
                    for e in conn.execute(
                        "SELECT id, estado, titulo FROM excepcion WHERE estado <> 'resuelta' "
                        "AND tabla = 'orden_compra' AND fila_id = ? ORDER BY id", (po_id,))]
    activos = [h for h in hallazgos_ if h["estado"] != "aceptado"]
    return {"activos": len(activos), "aceptados": len(hallazgos_) - len(activos),
            "hallazgos": hallazgos_, "excepciones": excepciones_}


# Lo que depende del planning: sin ningun planning importado, sin datos, nunca
# cero (cero diria que no hay nada planificado ni trabajado sin facturar).
_SIN_PLANNING = {
    "planificado": {"estado": "sin_datos",
                    "detalle": "No se ha importado ningún planning de TRNSPRNT: no se sabe qué "
                               "trabajo hay planificado (P8)."},
    "sin_facturar": {"estado": "sin_datos",
                     "detalle": "No se ha importado ningún planning de TRNSPRNT: no se sabe qué "
                                "trabajo falta por facturar (P10)."},
}


def _esperado_po(conn: sqlite3.Connection, po_id: int) -> dict[str, Any]:
    """Lo trabajado sin facturar y lo planificado de una PO, valorados como en P8 y P10 (a la
    tarifa pactada de su lado o, si no, a la del turno en el planning)."""
    foto = _planning(conn)
    if foto is None:
        return dict(_SIN_PLANNING)
    orden = next((o for o in foto.ordenes if o.id == po_id), None)
    if orden is None:
        return dict(_SIN_PLANNING)
    lista = reglas_ordenes.turnos_de_po(foto).get(po_id, [])
    conciliado = reglas_turnos.conciliado(foto, reglas_ordenes.SENTIDO_DE_LADO[orden.lado])
    sin_facturar, planificado, sin_tarifa = reglas_ordenes.esperado(
        foto, orden, lista, conciliado, por_sentido(foto.tarifas))
    nota = f"{sin_tarifa} turno(s) sin tarifa no suman." if sin_tarifa else None
    return {"planificado": {"estado": "ok", "valor_cent": planificado,
                            "valor": _euros(planificado), "nota": nota},
            "sin_facturar": {"estado": "ok", "valor_cent": sin_facturar,
                             "valor": _euros(sin_facturar), "nota": nota},
            "turnos": len(lista)}


def orden_compra(conn: sqlite3.Connection, po_id: int) -> dict[str, Any]:
    """El detalle de una PO (§6): sus datos, lo consumido factura a factura en el orden del §7,
    sus modificaciones, la prevision de agotamiento y sus avisos. LookupError si no existe."""
    from .almacen import reloj_de
    from .politica import politica_reglas

    ordenes = po_.ordenes(conn)
    if po_id not in ordenes:
        raise LookupError(f"no hay orden de compra {po_id}")
    orden = ordenes[po_id]
    fila = conn.execute("SELECT fuente, documento_id, rev, valor_original_cent FROM orden_compra "
                        "WHERE id = ?", (po_id,)).fetchone()
    lista = po_.cargos(conn, po_id).get(po_id, [])
    numeros = dict(conn.execute(
        f"SELECT id, numero FROM factura WHERE id IN ({', '.join('?' * len(lista)) or 'NULL'})",
        tuple(c.factura_id for c in lista)).fetchall())
    hoy = reloj_de(conn).hoy()
    politica = politica_reglas(conn)
    p = po_.prevision(orden, lista, hoy, politica.po_semanas_ritmo)
    objetos_ = [{"id": f["id"], "codigo": f["codigo"], "nombre": f["nombre"]}
                for f in conn.execute(
                    "SELECT o.id, o.codigo, o.nombre FROM orden_compra_objeto AS x "
                    "JOIN objeto AS o ON o.id = x.objeto_id WHERE x.orden_compra_id = ? "
                    "AND x.retirada_en IS NULL ORDER BY o.codigo", (po_id,))]
    return {
        **_cabecera_po(orden, _nombres_de_partes(conn)), "hoy": hoy.isoformat(),
        "fuente": fila["fuente"], "documento_id": fila["documento_id"], "rev": fila["rev"],
        "valor_original_cent": fila["valor_original_cent"],
        "valor_original": _euros(fila["valor_original_cent"]),
        "fecha_fin_original": _iso(orden.fecha_fin_original),
        **_cifras(orden, lista),
        "objetos": objetos_,
        "modificaciones": _modificaciones(conn, po_id),
        "facturas": [{"factura_id": c.factura_id, "numero": numeros.get(c.factura_id),
                      "fecha_factura": _iso(c.fecha), "importe_cent": c.importe_cent,
                      "importe": _euros(c.importe_cent), "quedaba_cent": antes,
                      "quedaba": _euros(antes)}
                     for c, antes in po_.antes_de_cada(orden, lista)],
        "prevision": {"desde": p.desde.isoformat(), "dias": p.dias,
                      "semanas": politica.po_semanas_ritmo,
                      "consumido_ventana_cent": p.consumido_cent,
                      "consumido_ventana": _euros(p.consumido_cent),
                      "agotamiento": _iso(p.agotamiento)},
        **_esperado_po(conn, po_id),
        "avisos": _avisos_po(conn, po_id),
        "prioridad": _prioridades(conn, "orden_compra").get(po_id, _SIN_PRIORIDAD),
    }


def objeto(conn: sqlite3.Connection, objeto_id: int, *, desde: date | None = None,
           hasta: date | None = None) -> dict[str, Any]:
    """La vista de un Objeto (§5): su ficha, sus PO (paso 9), sus horas (paso 10) y, desde el
    paso 12, sus ingresos, costes y margen y sus facturas.

    Las PO del Objeto son las que lo cubren y aquellas a las que se imputa
    trabajo suyo. Lo cubre una PO que lo nombra (orden_compra_objeto) y una
    abierta de su cliente que no nombra ninguno: una PO sin Objetos cubre
    cualquiera de su parte (como en P3). De cada una, lo consumido y lo que
    queda de la PO entera, y lo que ha consumido este Objeto. Las horas, por
    semana ISO, y lo esperado por cobrar y por pagar salen de
    trabajo.horas_objeto. Lo economico (ingresos, costes, margen) lo explica
    `_economia_objeto`; `desde` y `hasta` son el periodo de "Revenue" del
    §5 (por defecto, el mes en curso hasta hoy).
    """
    fila = conn.execute(
        "SELECT o.*, c.nombre AS cliente FROM objeto AS o LEFT JOIN cliente AS c "
        "ON c.id = o.cliente_id WHERE o.id = ?", (objeto_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay Objeto {objeto_id}")
    ordenes = po_.ordenes(conn)
    del_objeto = po_.cargos(conn, objeto_id=objeto_id)
    cliente_id = fila["cliente_id"]

    def cubre(orden: Any) -> bool:
        return objeto_id in orden.objetos or (
            not orden.objetos and orden.lado == "cliente" and cliente_id is not None
            and orden.parte_id == cliente_id)

    relacionadas = ({o.id for o in ordenes.values()
                     if objeto_id in o.objetos or (cubre(o) and not o.cerrada)}
                    | set(del_objeto))
    cargos = po_.cargos(conn) if relacionadas else {}
    nombres = _nombres_de_partes(conn)
    filas = []
    for po_id in sorted(relacionadas, key=lambda i: (ordenes[i].lado, ordenes[i].numero, i)):
        orden = ordenes[po_id]
        propio = sum(c.importe_cent for c in del_objeto.get(po_id, []))
        filas.append({**_cabecera_po(orden, nombres), **_cifras(orden, cargos.get(po_id, [])),
                      "cubre_objeto": cubre(orden),
                      "consumido_objeto_cent": propio, "consumido_objeto": _euros(propio)})
    resumen = {}
    for lado in ("cliente", "proveedor"):
        de_lado = [f for f in filas if f["lado"] == lado and not f["cerrada"]]
        valor = sum(f["valor_cent"] for f in de_lado)
        consumido = sum(f["consumido_cent"] for f in de_lado)
        resumen[lado] = {"ordenes": len(de_lado), "valor_cent": valor, "valor": _euros(valor),
                         "consumido_cent": consumido, "consumido": _euros(consumido),
                         "restante_cent": valor - consumido,
                         "restante": _euros(valor - consumido)}
    foto = _foto_de_hoy(conn)
    horas = _horas_objeto(conn, objeto_id, foto)
    return {
        "id": objeto_id, "codigo": fila["codigo"], "nombre": fila["nombre"],
        "cliente": {"id": fila["cliente_id"], "nombre": fila["cliente"]},
        "requiere_po": None if fila["requiere_po"] is None else bool(fila["requiere_po"]),
        "activo_desde": fila["activo_desde"], "activo_hasta": fila["activo_hasta"],
        "ordenes_compra": filas, "ordenes_resumen": resumen,
        "horas": horas,
        "economia": _economia_objeto(conn, objeto_id, foto, desde, hasta),
        "facturas": _facturas_de_objeto(conn, objeto_id),
        "prioridad": _prioridades(conn, "objeto").get(objeto_id, _SIN_PRIORIDAD),
    }


def _foto_de_hoy(conn: sqlite3.Connection) -> Any:
    """La instantanea de hoy (la de las reglas), con o sin planning."""
    from .almacen import reloj_de
    from .politica import politica_reglas

    return _planning(conn) or instantaneas.construir(conn, hoy=reloj_de(conn).hoy(),
                                                     politica=politica_reglas(conn))


def _horas_objeto(conn: sqlite3.Connection, objeto_id: int, foto: Any) -> dict[str, Any]:
    """Las horas del Objeto por semana y lo esperado de el (trabajo.horas_objeto), con lo que
    queda de cada factura abierta (flujo_caja.datos)."""
    partidas, _movidos = flujo_caja.datos(conn)
    pendientes = {p.factura_id: (p.direccion, p.importe_cent) for p in partidas}
    salida = trabajo.horas_objeto(foto, objeto_id, pendientes)
    for fila in (*salida["semanas"], salida["total"]):
        for clave in [c for c in fila if c.endswith("_mil")]:
            fila[clave.removesuffix("_mil")] = _horas_texto(fila[clave])
    esperado = salida["esperado"]
    for clave in [c for c in esperado if c.endswith("_cent")]:
        esperado[clave.removesuffix("_cent")] = _euros(esperado[clave])
    return salida



# ============================================================ paso 12
#
# Lo economico de cada Objeto (§5), la busqueda con sus filtros (§18), el panel
# principal (§17), la historia de una factura (§12) y el contrato v2 que leen
# /api/v2 y `bms-agent export --v2` (docs/integracion-web.md).

# La version del contrato v2. Sube el menor (2.1) cuando se anade una clave y el
# mayor (3.0) cuando una cambia de forma o desaparece: un sitio propio puede
# ignorar lo que no conoce, pero no adivinar lo que se le quito. El 2.1 (paso 15)
# anade a cada hallazgo sus `valores` y su `resultado`, a cada factura de las listas
# y a cada excepcion sus `razones`, y a la ficha sus `reglas_sin_datos`: con eso la
# app escribe los textos en neerlandes o en ingles (bms_agent.textos). El 2.2 (paso
# 16) anade las lecturas de Cuentas por cobrar y por pagar (la cartera, los pagos
# propuestos, las lineas del banco) y del archivo (los documentos de una parte y su
# descarga; desde la revision del paso 16, solo de los que enlaza un registro), lo del
# maestro en la vista de una parte y el filtro `tipo`. El 2.3 (paso 16) anade a cada
# pago de una factura quien y por que, y su linea del banco, y a la cartera lo que toca
# hasta el domingo (`esta_semana`) y los avisos de pago. El 2.4
# (revision del paso 16) anade a cada factura de las listas la fuente de lo pagado
# (`fuente_pago`) y a cada proveedor y cliente, en su lista y en su vista, lo que dice la
# cartera (`deuda_cent`) y sus abonos sin enlazar (`abonos_sin_enlazar_cent`), aparte.
CONTRATO_V2 = "2.5"


def _pb(parte: int, todo: int) -> int | None:
    """Un cociente en puntos basicos (redondeo a la mitad hacia arriba); None sin divisor."""
    if not todo:
        return None
    signo = -1 if (parte < 0) != (todo < 0) else 1
    return signo * ((abs(parte) * 10000 * 2 + abs(todo)) // (2 * abs(todo)))


def _cifras_economia(ingresos: int, costes: int, horas_venta: int = 0,
                     horas_compra: int = 0) -> dict[str, Any]:
    """Ingresos, costes, margen y margen sobre ingresos, sin IVA, con sus textos."""
    margen = ingresos - costes
    margen_pb = _pb(margen, ingresos)
    return {"ingresos_cent": ingresos, "ingresos": _euros(ingresos),
            "costes_cent": costes, "costes": _euros(costes),
            "margen_cent": margen, "margen": _euros(margen),
            "margen_pb": margen_pb, "margen_pct": None if margen_pb is None else _pct(margen_pb),
            "horas_venta_mil": horas_venta, "horas_venta": _horas_texto(horas_venta),
            "horas_compra_mil": horas_compra, "horas_compra": _horas_texto(horas_compra)}


def _economia_por_objeto(conn: sqlite3.Connection, desde: date | None = None,
                         hasta: date | None = None) -> dict[int | None, dict[str, int]]:
    """Ingresos, costes y horas de cada Objeto (None: lo imputado sin Objeto) entre dos fechas
    de factura, de las mismas imputaciones que v_objeto_periodo.

    Sin fechas, de siempre: la suma de todos los meses de la vista, tambien
    los de facturas sin fecha. Con fechas, solo las facturas fechadas en el
    periodo (una sin fecha no es de ningun periodo).
    """
    if desde is None and hasta is None:
        filas = conn.execute(
            "SELECT objeto_id, sum(ingresos_cent), sum(costes_cent), sum(horas_venta_mil), "
            "sum(horas_compra_mil) FROM v_objeto_periodo GROUP BY objeto_id").fetchall()
    else:
        filas = conn.execute(
            "SELECT i.objeto_id, "
            "sum(CASE WHEN i.sentido = 'saliente' THEN coalesce(i.importe_cent, 0) ELSE 0 END), "
            "sum(CASE WHEN i.sentido = 'entrante' THEN coalesce(i.importe_cent, 0) ELSE 0 END), "
            "sum(CASE WHEN i.sentido = 'saliente' THEN coalesce(i.horas_mil, 0) ELSE 0 END), "
            "sum(CASE WHEN i.sentido = 'entrante' THEN coalesce(i.horas_mil, 0) ELSE 0 END) "
            "FROM v_imputacion_vigente AS i JOIN factura AS f ON f.id = i.factura_id "
            "WHERE f.base_cent IS NOT NULL AND i.fecha_factura >= ? AND i.fecha_factura <= ? "
            "GROUP BY i.objeto_id",
            ((desde or date.min).isoformat(), (hasta or date.max).isoformat())).fetchall()
    return {f[0]: {"ingresos": f[1] or 0, "costes": f[2] or 0, "horas_venta": f[3] or 0,
                   "horas_compra": f[4] or 0} for f in filas}


def _de(economia: dict[int | None, dict[str, int]], clave: int | None) -> dict[str, Any]:
    e = economia.get(clave, {})
    return _cifras_economia(e.get("ingresos", 0), e.get("costes", 0), e.get("horas_venta", 0),
                            e.get("horas_compra", 0))


def _economia_objeto(conn: sqlite3.Connection, objeto_id: int, foto: Any,
                     desde: date | None, hasta: date | None) -> dict[str, Any]:
    """Lo economico de un Objeto (§5): ingresos (lo facturado al cliente), costes (lo que
    facturan los proveedores) y margen bruto, sin IVA.

    De las imputaciones que cuentan (ni anuladas, ni fusionadas, ni
    sustituidas) de facturas con base conocida, por la fecha de factura: el
    periodo pedido (por defecto, el mes en curso hasta hoy), el ano hasta hoy y
    de siempre, mes a mes (v_objeto_periodo) y semana a semana por los dias de
    trabajo (trabajo.importes_por_semana, como sus horas). La suma de los meses
    y la de las semanas es lo de siempre. Atribuir por la fecha de la factura
    o por el periodo trabajado es la pregunta 10 del §12, todavia abierta: el
    mes va por la fecha de factura (como el ano y el BTW) y la semana por el
    trabajo (como las horas).
    """
    hoy = foto.hoy
    if (desde is None) != (hasta is None):
        # Un solo extremo no es un periodo: rellenar el otro con el mes en curso
        # daba un periodo al reves (hasta en septiembre, desde el 1 de octubre)
        # o uno que nadie pidio. Como flujo_caja.calcular: los dos o ninguno.
        raise ValueError("un periodo lleva desde y hasta (o ninguno: el mes en curso)")
    desde_ = desde or hoy.replace(day=1)
    hasta_ = hasta or hoy
    if desde_ > hasta_:
        raise ValueError("el periodo empieza despues de terminar")
    por_mes = [{"mes": f["mes"], **_cifras_economia(f["ingresos_cent"], f["costes_cent"],
                                                     f["horas_venta_mil"], f["horas_compra_mil"]),
                "facturas_venta": f["facturas_venta"], "facturas_compra": f["facturas_compra"]}
               for f in conn.execute(
                   "SELECT * FROM v_objeto_periodo WHERE objeto_id = ? "
                   "ORDER BY mes = 'sin_fecha', mes", (objeto_id,))]
    semanas = trabajo.importes_por_semana(foto, objeto_id)
    por_semana = [{"semana": s, **_cifras_economia(semanas[s]["ingresos_cent"],
                                                   semanas[s]["costes_cent"],
                                                   semanas[s]["horas_venta_mil"],
                                                   semanas[s]["horas_compra_mil"])}
                  for s in sorted(semanas, key=lambda s: (s == trabajo.SIN_SEMANA, s))]
    return {
        "periodo": {"desde": desde_.isoformat(), "hasta": hasta_.isoformat(),
                    **_de(_economia_por_objeto(conn, desde_, hasta_), objeto_id)},
        "ano": {"ano": hoy.year, **_de(_economia_por_objeto(conn, hoy.replace(month=1, day=1),
                                                            hoy), objeto_id)},
        "siempre": _de(_economia_por_objeto(conn), objeto_id),
        "por_mes": por_mes, "por_semana": por_semana,
    }


def _facturas_de_objeto(conn: sqlite3.Connection, objeto_id: int) -> dict[str, list]:
    """Las facturas con algo imputado al Objeto (§5 "Related incoming/outgoing invoices"), con
    lo que le imputan, la mas reciente primero. Las que no cuentan (anuladas, sustituidas)
    salen con `cuenta` falso; las copias fusionadas no salen."""
    salida: dict[str, list] = {"entrantes": [], "salientes": []}
    for f in conn.execute(
            "SELECT l.id, l.sentido, l.numero, l.contraparte, l.fecha_factura, l.estado_pago, "
            "l.pendiente_cent, l.cuenta, sum(coalesce(i.importe_cent, 0)) AS importe, "
            "sum(coalesce(i.horas_mil, 0)) AS horas FROM factura_imputacion AS i "
            "JOIN v_factura_listado AS l ON l.id = i.factura_id "
            "WHERE i.objeto_id = ? AND i.retirada_en IS NULL AND l.fusionada_en_id IS NULL "
            "GROUP BY l.id ORDER BY l.fecha_factura IS NULL, l.fecha_factura DESC, l.id DESC",
            (objeto_id,)):
        salida["entrantes" if f["sentido"] == "entrante" else "salientes"].append({
            "id": f["id"], "numero": f["numero"], "contraparte": f["contraparte"],
            "fecha_factura": f["fecha_factura"], "estado_pago": f["estado_pago"],
            "cuenta": bool(f["cuenta"]), "importe_objeto_cent": f["importe"],
            "importe_objeto": _euros(f["importe"]), "horas_mil": f["horas"],
            "horas": _horas_texto(f["horas"])})
    return salida


def _base_y_sin_imputar(conn: sqlite3.Connection, sentido: str) -> tuple[int, int, int]:
    """(base, facturas, base sin imputar) de las facturas de un sentido que cuentan, con base.

    "Sin imputar" es, factura a factura, lo que su base no reparte entre
    imputaciones: una factura sin lineas, o con lineas que no suman la base (I1,
    D2). Junto con lo imputado sin Objeto es lo que no es de ningun Objeto.
    """
    fila = conn.execute(
        "SELECT coalesce(sum(l.base_cent), 0), count(*), coalesce(sum(l.base_cent - coalesce(("
        "SELECT sum(i.importe_cent) FROM v_imputacion_vigente AS i WHERE i.factura_id = l.id), "
        "0)), 0) FROM v_factura_listado AS l WHERE l.sentido = ? AND l.cuenta "
        "AND l.base_cent IS NOT NULL", (sentido,)).fetchone()
    return fila[0], fila[1], fila[2]


def objetos_resumen(conn: sqlite3.Connection) -> dict[str, Any]:
    """Los Objetos con sus ingresos, costes y margen (del ano y de siempre), y lo que no es de
    ningun Objeto, de modo que todo cuadra con la base total (puerta del paso 12).

    Lo facturado a los clientes por Objeto, mas lo imputado sin Objeto, mas lo
    que las bases de las ventas no imputan a ninguna linea, es la base de todas
    las ventas que cuentan; igual con las compras. `sin_base` cuenta las
    facturas que no tienen base (Q1; o X1, porque en otra moneda se lee sin
    importes): no entran en ninguna de esas sumas hasta que se corrigen.
    """
    from .almacen import reloj_de

    hoy = reloj_de(conn).hoy()
    siempre = _economia_por_objeto(conn)
    ano = _economia_por_objeto(conn, hoy.replace(month=1, day=1), hoy)
    prioridades = _prioridades(conn, "objeto")
    razones = _razones_por_parte(conn)["objeto"]
    filas = []
    for o in conn.execute("SELECT o.id, o.codigo, o.nombre, o.cliente_id, c.nombre AS cliente "
                          "FROM objeto AS o LEFT JOIN cliente AS c ON c.id = o.cliente_id "
                          "ORDER BY o.codigo, o.id"):
        p = prioridades.get(o["id"], _SIN_PRIORIDAD)
        filas.append({"id": o["id"], "codigo": o["codigo"], "nombre": o["nombre"],
                      "cliente_id": o["cliente_id"], "cliente": o["cliente"],
                      "siempre": _de(siempre, o["id"]), "ano": _de(ano, o["id"]),
                      "nivel": p["nivel"], "puntos": p["puntos"],
                      "razones": razones.get(o["id"], [])})
    venta_base, venta_n, venta_sin = _base_y_sin_imputar(conn, "saliente")
    compra_base, compra_n, compra_sin = _base_y_sin_imputar(conn, "entrante")
    sin_objeto = siempre.get(None, {})
    sin_base = conn.execute(
        "SELECT count(*) FROM v_factura_listado WHERE cuenta AND base_cent IS NULL").fetchone()[0]
    return {
        "hoy": hoy.isoformat(), "ano": hoy.year, "objetos": filas,
        "sin_objeto": {
            "imputado": _cifras_economia(sin_objeto.get("ingresos", 0),
                                         sin_objeto.get("costes", 0),
                                         sin_objeto.get("horas_venta", 0),
                                         sin_objeto.get("horas_compra", 0)),
            "sin_imputar": _cifras_economia(venta_sin, compra_sin),
            "total": _cifras_economia(sin_objeto.get("ingresos", 0) + venta_sin,
                                      sin_objeto.get("costes", 0) + compra_sin),
        },
        "totales": {**_cifras_economia(venta_base, compra_base), "facturas_venta": venta_n,
                    "facturas_compra": compra_n, "sin_base": sin_base},
    }


# ------------------------------------------------------------ la busqueda (§18)
#
# Cada filtro es un fragmento de SQL fijo de este modulo, con sus valores como
# parametros: lo que escribe quien busca nunca entra en el texto de la
# consulta. Un nombre que no esta en FILTROS (ni en los de pagina) se rechaza,
# y un valor que no se entiende tambien: una busqueda que ignora en silencio un
# filtro mal escrito ensena facturas que no son las que se pidieron.
#
# Lo que depende del estado (pago, revision, prioridad, calidad, ediciones) se
# lee de la cache factura_estado, que rehace cada pasada del motor y la diaria:
# la respuesta dice de que dia es (`estado_del`) y si es el de hoy (`al_dia`).


class FiltroNoValido(ValueError):
    """Un filtro que no existe, o con un valor que no se entiende (un 400 en /api/v2)."""


@dataclass(frozen=True)
class Filtro:
    """Un filtro de la busqueda: su nombre, lo que pide del §18, que valores admite y como se
    traduce a un fragmento fijo con sus parametros."""

    nombre: str
    seccion: str
    descripcion: str
    tipo: str
    traducir: Any
    valores: tuple[str, ...] = ()


def _uno(nombre: str, valores: list[str]) -> str:
    if len(valores) != 1 or not valores[0].strip():
        raise FiltroNoValido(f"{nombre}: lleva un valor")
    return valores[0].strip()


def _elegidos(nombre: str, valores: list[str], admitidos: tuple[str, ...]) -> list[str]:
    elegidos = [v.strip() for texto in valores for v in texto.split(",") if v.strip()]
    if not elegidos:
        raise FiltroNoValido(f"{nombre}: lleva al menos un valor")
    raros = sorted(set(elegidos) - set(admitidos))
    if raros:
        raise FiltroNoValido(f"{nombre}: {', '.join(raros)} no es ninguno de "
                             f"{', '.join(admitidos)}")
    return sorted(set(elegidos), key=admitidos.index)


# El mayor entero que guarda SQLite: uno mayor no es un id de nada y, como
# parametro, sqlite3 lo rechaza con OverflowError (ni un 400 ni un aviso claro).
_ENTERO_MAXIMO = ENTERO_MAXIMO = 2 ** 63 - 1


def _entero(nombre: str, valores: list[str]) -> int:
    texto = _uno(nombre, valores)
    if not (texto.isascii() and texto.isdigit()):
        raise FiltroNoValido(f"{nombre}: {texto!r} no es un numero entero")
    if len(texto) > 19 or int(texto) > _ENTERO_MAXIMO:
        raise FiltroNoValido(f"{nombre}: {texto!r} es demasiado grande")
    return int(texto)


def _dia(nombre: str, valores: list[str]) -> str:
    texto = _uno(nombre, valores)
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError:
        raise FiltroNoValido(f"{nombre}: {texto!r} no es una fecha AAAA-MM-DD") from None


def _si(nombre: str, valores: list[str]) -> bool:
    texto = _uno(nombre, valores).lower()
    if texto not in ("si", "sí", "no"):
        raise FiltroNoValido(f"{nombre}: es si o no, no {texto!r}")
    return texto != "no"


_IMPORTE_FILTRO = re.compile(r"^\d{1,12}([.,]\d{1,2})?$")


def _cent(nombre: str, valores: list[str]) -> int:
    """Un importe en euros, sin signo ni separador de miles (10000 o 10000,50)."""
    texto = _uno(nombre, valores)
    if not _IMPORTE_FILTRO.match(texto):
        raise FiltroNoValido(f"{nombre}: {texto!r} no es un importe (se escribe 10000 o "
                             "10000,50, sin separador de miles)")
    from .almacen.unidades import a_cent

    return a_cent(Decimal(texto.replace(",", ".")))


def _marcas(n: int) -> str:
    return ", ".join("?" * n)


def _por_valor(columna: str, admitidos: tuple[str, ...]):
    """Una columna de la cache que tiene que ser uno de unos valores (una lista)."""
    def traducir(nombre: str, valores: list[str]) -> tuple[str, tuple]:
        elegidos = _elegidos(nombre, valores, admitidos)
        return f"{columna} IN ({_marcas(len(elegidos))})", tuple(elegidos)
    return traducir


def _si_no(si: str, no: str):
    """Un filtro de si o no: dos fragmentos fijos, sin valores."""
    def traducir(nombre: str, valores: list[str]) -> tuple[str, tuple]:
        return (si if _si(nombre, valores) else no), ()
    return traducir


def _comparar(fragmento: str, leer):
    """Un fragmento con un solo valor, leido y comprobado por `leer`."""
    def traducir(nombre: str, valores: list[str]) -> tuple[str, tuple]:
        valor = leer(nombre, valores)
        return fragmento, (valor,) * fragmento.count("?")
    return traducir


def _numero(nombre: str, valores: list[str]) -> tuple[str, tuple]:
    from .parsing import normalizar_referencia

    normal = normalizar_referencia(_uno(nombre, valores))
    if not normal:
        raise FiltroNoValido(f"{nombre}: no queda nada que buscar")
    return "instr(coalesce(numero_norm, ''), ?) > 0", (normal,)


def pliegue(texto: Any) -> str:
    """Un texto sin mayusculas para comparar, igual en Python y en SQL.

    El lower() de SQLite solo pliega las letras ASCII: "ÖZTÜRK" quedaba
    "Öztürk" con la O mayuscula y nadie lo encontraba escribiendolo bien. Por
    eso la busqueda registra esta funcion en la conexion (`_registrar_pliegue`)
    y la usa a los dos lados: casefold despues de NFKC, para que "ß" y "ss" o
    una letra con su acento compuesto o separado sean lo mismo.
    """
    return unicodedata.normalize("NFKC", str(texto or "")).casefold()


def _registrar_pliegue(conn: sqlite3.Connection) -> None:
    conn.create_function("pliegue", 1, pliegue, deterministic=True)


def _texto(nombre: str, valores: list[str]) -> tuple[str, tuple]:
    buscado = pliegue(_uno(nombre, valores))
    return ("(instr(pliegue(numero), ?) > 0 "
            "OR instr(pliegue(contraparte), ?) > 0)"), (buscado, buscado)


def _po(nombre: str, valores: list[str]) -> tuple[str, tuple]:
    from .parsing import normalizar_referencia

    normal = normalizar_referencia(_uno(nombre, valores))
    if not normal:
        raise FiltroNoValido(f"{nombre}: no queda nada que buscar")
    return ("(id IN (SELECT r.factura_id FROM factura_referencia AS r "
            "WHERE r.retirada_en IS NULL AND r.valor_norm = ? "
            "AND (r.clase = 'po' OR r.orden_compra_id IS NOT NULL)) "
            "OR id IN (SELECT i.factura_id FROM factura_imputacion AS i "
            "JOIN orden_compra AS o ON o.id = i.orden_compra_id "
            "WHERE i.retirada_en IS NULL AND o.numero_norm = ?))"), (normal, normal)


def _trimestre(nombre: str, valores: list[str]) -> tuple[str, tuple]:
    from . import btw

    texto = _uno(nombre, valores)
    try:
        inicio, fin = btw.periodo_de(*btw.leer_etiqueta(texto))
    except ValueError as exc:
        raise FiltroNoValido(f"{nombre}: {exc}") from None
    return "fecha_factura >= ? AND fecha_factura <= ?", (inicio.isoformat(), fin.isoformat())


_CALIDADES = (*_ORDEN_CALIDAD, "neutra")


def _calidad(nombre: str, valores: list[str]) -> tuple[str, tuple]:
    """Una o varias calidades de la factura; "neutra" es la que no tiene ninguna marca (nunca
    verde: §14)."""
    elegidos = _elegidos(nombre, valores, _CALIDADES)
    marcadas = [v for v in elegidos if v != "neutra"]
    partes = [f"calidad IN ({_marcas(len(marcadas))})"] if marcadas else []
    if "neutra" in elegidos:
        partes.append("calidad IS NULL")
    return f"({' OR '.join(partes)})", tuple(marcadas)


_EDICIONES = {"editada": "editada = 1", "suplementada": "suplementada = 1",
              "corregida": "corregida = 1", "sin_resolver": "sin_resolver > 0"}


def _edicion(nombre: str, valores: list[str]) -> tuple[str, tuple]:
    """Con alguna de las marcas de edicion manual pedidas (§11): editada, suplementada,
    corregida o con cambios sin resolver."""
    elegidos = _elegidos(nombre, valores, tuple(_EDICIONES))
    return f"({' OR '.join(_EDICIONES[v] for v in elegidos)})", ()


_EN_JUEGO_SQL = "estado_pago IN ('pendiente', 'vencida')"
_DEL_CLIENTE = ("(cliente_id = ? OR id IN (SELECT i.factura_id FROM factura_imputacion AS i "
                "JOIN objeto AS o ON o.id = i.objeto_id WHERE i.retirada_en IS NULL "
                "AND o.cliente_id = ?))")
_DEL_OBJETO = ("id IN (SELECT factura_id FROM factura_imputacion WHERE retirada_en IS NULL "
               "AND objeto_id = ?)")
_DE_LA_PO = ("(id IN (SELECT factura_id FROM factura_imputacion WHERE retirada_en IS NULL "
             "AND orden_compra_id = ?) OR id IN (SELECT factura_id FROM factura_referencia "
             "WHERE retirada_en IS NULL AND orden_compra_id = ?))")

FILTROS: dict[str, Filtro] = {f.nombre: f for f in (
    Filtro("numero", "Invoice number", "Parte del número de factura, sin espacios, puntos, "
           "guiones ni barras (2026-4471 encuentra 2026 4471)", "texto", _numero),
    Filtro("texto", "—", "Parte del número o del nombre impreso de la contraparte", "texto",
           _texto),
    Filtro("sentido", "—", "Compras (entrante) o ventas (saliente)", "lista",
           _por_valor("sentido", ("entrante", "saliente")), ("entrante", "saliente")),
    # Paso 16 (contrato 2.2): el "Tipo de documento" del archivo de la app.
    Filtro("tipo", "—", "Factura o abono (nota de crédito)", "lista",
           _por_valor("tipo", tuple(TipoFactura.valores())), tuple(TipoFactura.valores())),
    Filtro("proveedor_id", "Provider", "Del proveedor del maestro", "entero",
           _comparar("proveedor_id = ?", _entero)),
    Filtro("cliente_id", "Client", "Del cliente: sus ventas y las compras imputadas a un Objeto "
           "suyo", "entero", _comparar(_DEL_CLIENTE, _entero)),
    Filtro("objeto_id", "Object", "Con alguna línea imputada al Objeto", "entero",
           _comparar(_DEL_OBJETO, _entero)),
    Filtro("orden_compra_id", "PO", "Imputada a la PO registrada, o que la imprime", "entero",
           _comparar(_DE_LA_PO, _entero)),
    Filtro("po", "PO", "Con ese número de PO impreso o imputado", "texto", _po),
    Filtro("fecha_desde", "Period", "Fecha de factura desde (incluida)", "fecha",
           _comparar("fecha_factura >= ?", _dia)),
    Filtro("fecha_hasta", "Period", "Fecha de factura hasta (incluida)", "fecha",
           _comparar("fecha_factura <= ?", _dia)),
    Filtro("periodo_desde", "Period", "Periodo de prestación que llega a ese día o después",
           "fecha", _comparar("periodo_hasta >= ?", _dia)),
    Filtro("periodo_hasta", "Period", "Periodo de prestación que empieza ese día o antes",
           "fecha", _comparar("periodo_desde <= ?", _dia)),
    Filtro("trimestre", "Period", "Fecha de factura en el trimestre del BTW (2026-T3)",
           "trimestre", _trimestre),
    Filtro("vence_desde", "Due date", "Vencimiento efectivo desde (incluido)", "fecha",
           _comparar("vencimiento >= ?", _dia)),
    Filtro("vence_hasta", "Due date", "Vencimiento efectivo hasta (incluido)", "fecha",
           _comparar("vencimiento <= ?", _dia)),
    Filtro("estado_pago", "Payment status", "Uno o varios estados de pago", "lista",
           _por_valor("estado_pago", tuple(EstadoPago.valores())),
           tuple(EstadoPago.valores())),
    Filtro("estado_revision", "Review status", "Uno o varios estados de revisión", "lista",
           _por_valor("estado_revision", tuple(EstadoRevision.valores())),
           tuple(EstadoRevision.valores())),
    Filtro("nivel", "Priority", "Uno o varios niveles de prioridad", "lista",
           _por_valor("nivel", tuple(Prioridad.valores())), tuple(Prioridad.valores())),
    Filtro("calidad", "Data-quality status", "Una o varias calidades de dato (neutra: sin "
           "ninguna marca)", "lista", _calidad, _CALIDADES),
    Filtro("edicion", "Manual edits", "Con alguna de esas marcas de edición manual", "lista",
           _edicion, tuple(_EDICIONES)),
    Filtro("pendiente", "Outstanding", "Pendiente de pago o de cobro (también vencida)",
           "si_no", _si_no(_EN_JUEGO_SQL, f"NOT coalesce({_EN_JUEGO_SQL}, 0)")),
    Filtro("vencida", "Overdue", "Vencida y sin pagar", "si_no",
           _si_no("estado_pago = 'vencida'", "coalesce(estado_pago, '') <> 'vencida'")),
    Filtro("pagada", "Paid", "Pagada (o cobrada)", "si_no",
           _si_no("estado_pago = 'pagada'", "coalesce(estado_pago, '') <> 'pagada'")),
    Filtro("anulada_acreditada", "Cancelled / credited", "Anulada (a mano, por un abono o "
           "porque otra la sustituye) o acreditada por sus abonos", "si_no",
           _si_no("estado_pago IN ('anulada', 'acreditada')",
                  "coalesce(estado_pago, '') NOT IN ('anulada', 'acreditada')")),
    Filtro("excepcion", "—", "Con una excepción abierta", "si_no",
           _si_no("excepcion_id IS NOT NULL", "excepcion_id IS NULL")),
    Filtro("importe_min", "—", "Importe sin IVA (en valor absoluto) desde", "importe",
           _comparar("abs(importe_cent) >= ?", _cent)),
    Filtro("importe_max", "—", "Importe sin IVA (en valor absoluto) hasta", "importe",
           _comparar("abs(importe_cent) <= ?", _cent)),
)}

# Lo que no filtra sino ordena y pagina.
ORDENES_BUSQUEDA = ("prioridad", "fecha", "vencimiento", "importe", "numero")
PAGINA_BUSQUEDA = ("orden", "limite", "pagina")
LIMITE_BUSQUEDA = 1000


def _ordenar(filas: list[dict[str, Any]], orden: str) -> list[dict[str, Any]]:
    if orden == "fecha":
        # La mas reciente primero; las que no tienen fecha, al final.
        fechadas = sorted((r for r in filas if r["fecha_factura"]),
                          key=lambda r: (r["fecha_factura"], r["id"]), reverse=True)
        return fechadas + sorted((r for r in filas if not r["fecha_factura"]),
                                 key=lambda r: r["id"], reverse=True)
    if orden == "vencimiento":
        return sorted(filas, key=lambda r: (r["vencimiento"] is None, r["vencimiento"] or "",
                                            r["id"]))
    if orden == "importe":
        return sorted(filas, key=lambda r: (-abs(r["base_cent"] if r["base_cent"] is not None
                                                 else r["total_cent"] or 0), r["id"]))
    if orden == "numero":
        return sorted(filas, key=lambda r: (r["numero"] is None, r["numero"] or "", r["id"]))
    return filas


def estado_del(conn: sqlite3.Connection) -> str | None:
    """El `hoy` de la ultima pasada terminada del motor: de cuando es la cache de estado."""
    fila = conn.execute("SELECT hoy FROM ejecucion_reglas WHERE terminada_en IS NOT NULL "
                        "ORDER BY id DESC LIMIT 1").fetchone()
    return fila[0] if fila else None


def buscar(conn: sqlite3.Connection, peticion: dict[str, Any] | None = None) -> dict[str, Any]:
    """Las facturas que cumplen todos los filtros pedidos (§18), en el orden pedido.

    `peticion` es {nombre: valor o lista de valores}, como llega de una URL o de
    la CLI. Los filtros se suman (y); dentro de uno de lista, basta uno de sus
    valores (o). FiltroNoValido si un nombre no existe o un valor no se
    entiende. Devuelve la pagina pedida y, de todas las que cumplen, cuantas
    son y lo que suman (`_suma_busqueda`: solo las que cuentan, compras y
    ventas por separado). Un valor que no es texto (un id entero desde Python)
    vale como su texto.
    """
    from .almacen import reloj_de

    peticion = dict(peticion or {})
    valores = {k: ([str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)])
               for k, v in peticion.items() if v is not None}
    raros = sorted(set(valores) - set(FILTROS) - set(PAGINA_BUSQUEDA))
    if raros:
        raise FiltroNoValido(f"filtro desconocido: {', '.join(raros)} (los que hay: "
                             f"{', '.join(FILTROS)})")
    partes, parametros, aplicados = [], [], {}
    for nombre, filtro in FILTROS.items():
        if nombre not in valores:
            continue
        fragmento, suyos = filtro.traducir(nombre, valores[nombre])
        partes.append(fragmento)
        parametros.extend(suyos)
        aplicados[nombre] = valores[nombre][0] if len(valores[nombre]) == 1 else valores[nombre]
    orden = _uno("orden", valores["orden"]) if "orden" in valores else "prioridad"
    if orden not in ORDENES_BUSQUEDA:
        raise FiltroNoValido(f"orden: {orden!r} no es ninguno de {', '.join(ORDENES_BUSQUEDA)}")
    limite = _entero("limite", valores["limite"]) if "limite" in valores else 200
    pagina = _entero("pagina", valores["pagina"]) if "pagina" in valores else 1
    if not 1 <= limite <= LIMITE_BUSQUEDA or pagina < 1:
        raise FiltroNoValido(f"limite va de 1 a {LIMITE_BUSQUEDA} y pagina empieza en 1")
    _registrar_pliegue(conn)
    filas = _ordenar(_filas_listado(conn, " AND ".join(partes), tuple(parametros)), orden)
    del_dia = estado_del(conn)
    return {
        "filtros": aplicados, "orden": orden, "limite": limite, "pagina": pagina,
        "total": len(filas), "suma": _suma_busqueda(filas),
        "estado_del": del_dia, "al_dia": del_dia == reloj_de(conn).hoy().isoformat(),
        "facturas": filas[(pagina - 1) * limite:pagina * limite],
    }


def _cifras_busqueda(filas: list[dict[str, Any]]) -> dict[str, Any]:
    """Lo que suman unas facturas de un mismo sentido que cuentan: total, base y lo pendiente
    (lo que queda de las pendientes y vencidas), con sus textos."""
    total = sum(r["total_cent"] or 0 for r in filas)
    base = sum(r["base_cent"] or 0 for r in filas)
    pendiente = sum(r["pendiente_cent"] or 0 for r in filas
                    if r["estado_pago"] in ("pendiente", "vencida"))
    return {"facturas": len(filas), "total_cent": total, "total": _euros(total),
            "base_cent": base, "base": _euros(base), "pendiente_cent": pendiente,
            "pendiente": _euros(pendiente)}


def _suma_busqueda(filas: list[dict[str, Any]]) -> dict[str, Any]:
    """Lo que suma lo encontrado, con la misma regla que las vistas de las partes.

    Solo suman las facturas que cuentan (ni anuladas, ni copias fusionadas, ni
    sustituidas: `_cuenta`, `v_*_totales`); las demas se cuentan aparte en
    `no_cuentan`, para que una busqueda por proveedor de lo mismo que su
    vista. Compras y ventas van por separado: lo pendiente de una compra es lo
    que BMS debe y el de una venta lo que le deben, y sumarlos no es ninguna
    cifra. Arriba, `total_cent`, `base_cent` y `pendiente_cent` son los del
    unico sentido encontrado; si hay de los dos, null (se leen en `compras` y
    `ventas`).
    """
    cuentan = [r for r in filas if r["cuenta"]]
    compras = _cifras_busqueda([r for r in cuentan if r["sentido"] == "entrante"])
    ventas = _cifras_busqueda([r for r in cuentan if r["sentido"] == "saliente"])
    mezcla = bool(compras["facturas"] and ventas["facturas"])
    unica = ventas if ventas["facturas"] and not compras["facturas"] else compras
    salida: dict[str, Any] = {"cuentan": len(cuentan), "no_cuentan": len(filas) - len(cuentan),
                              "mezcla": mezcla, "compras": compras, "ventas": ventas}
    for clave in ("total", "base", "pendiente"):
        salida[f"{clave}_cent"] = None if mezcla else unica[f"{clave}_cent"]
        salida[clave] = None if mezcla else unica[clave]
    return salida


def filtros() -> list[dict[str, Any]]:
    """Los filtros de la busqueda, para la consola, la CLI y /api/v2/contrato."""
    return [{"nombre": f.nombre, "seccion": f.seccion, "descripcion": f.descripcion,
             "tipo": f.tipo, "valores": list(f.valores)} for f in FILTROS.values()]


# ------------------------------------------------------------ el panel principal (§17)
#
# Siete bloques: lo que entra, lo que sale, la caja, la facturacion, las PO, el
# BTW y lo que pide atencion. Cada cifra sale del mismo sitio que la vista que
# la detalla: lo esperado del flujo de caja (flujo_caja.datos: lo que queda de
# cada factura en juego por su vencimiento efectivo), las PO de
# ordenes_compra, el BTW de btw.resumen, lo vencido y lo pendiente del mismo
# saldo que las vistas de proveedores y clientes (estados.facturas) y los
# avisos de los hallazgos. Con el `hoy` del reloj del almacen.
#
# "Entrante" y "saliente" cambian de sentido entre el §1 (facturas de compra y
# de venta) y el §7 (dinero que entra y que sale): huecos.md, ambiguedad (a).
# Aqui el dinero es dinero (lo que entra se cobra: lo que queda de las ventas;
# lo que sale se paga: lo que queda de las compras) y lo vencido se dice por
# clase de factura: compras vencidas y ventas vencidas. Solo cuentan las deudas
# (reglas.pagos.vence): un abono sin enlazar, tambien el de un proveedor, no es
# un cobro con fecha y no entra en `dinero_entra` (la cartera lo da aparte).

# Los hallazgos que pide el panel en "atencion", por lo que aportan a la
# prioridad (catalogo) y, si no aportan nada especial, por su calidad. Cada
# regla va a una sola categoria: la suma de las categorias es la de todos los
# hallazgos pendientes.
_CATEGORIAS = (
    ("iban", "IBAN cambiado o sin verificar"),
    ("duplicados", "Posibles duplicados"),
    ("iva", "IVA"),
    ("planning", "Diferencias con el planning"),
    ("sin_facturar", "Trabajo sin facturar y periodos sin factura"),
    ("ordenes_compra", "Órdenes de compra"),
    ("vencidas", "Vencidas sin pagar (K1)"),
    ("faltan_datos", "Faltan datos"),
    ("lecturas_dudosas", "Lecturas dudosas"),
    ("otros", "Otras discrepancias y anomalías"),
)


def categoria_de(regla_id: str) -> str:
    """La categoria del panel de una regla del catalogo (§17, "Attention Required")."""
    from .dominio import EntradaPrioridad as E
    from .reglas import catalogo

    try:
        regla = catalogo.regla(regla_id)
    except (KeyError, LookupError):
        return "otros"
    entrada = regla.entrada_prioridad
    if entrada == E.IBAN.value:
        return "iban"
    if entrada in (E.DUPLICADO_EXACTO.value, E.DUPLICADO.value):
        return "duplicados"
    if entrada in (E.IVA_DURA.value, E.IVA_BLANDA.value):
        return "iva"
    if entrada == E.PLANNING.value:
        return "planning"
    if entrada in (E.TRABAJO_SIN_FACTURAR.value, E.FACTURACION_AUSENTE.value):
        return "sin_facturar"
    if entrada in (E.LIMITE_PO.value, E.LIMITE_PO_DURO.value, E.CADUCIDAD_PO.value):
        return "ordenes_compra"
    if entrada == E.DIAS_VENCIDA.value:
        return "vencidas"
    if regla.calidad == Calidad.FALTANTE.value:
        return "faltan_datos"
    if regla_id == "Q2":
        return "lecturas_dudosas"
    return "otros"


def _hallazgos_pendientes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    marcas = _marcas(len(ESTADOS_PENDIENTES))
    return conn.execute(f"SELECT id, regla, estado, tabla, fila_id, factura_id, valores_json "
                        f"FROM hallazgo WHERE estado IN ({marcas}) ORDER BY id",
                        sorted(ESTADOS_PENDIENTES)).fetchall()


def _facturas_de_hallazgos(conn: sqlite3.Connection) -> dict[int, set[int]]:
    """Las facturas de cada hallazgo: la suya y las de sus objetivos."""
    salida: dict[int, set[int]] = defaultdict(set)
    for hallazgo_id, fila_id in conn.execute(
            "SELECT hallazgo_id, fila_id FROM hallazgo_objetivo WHERE tabla = 'factura'"):
        salida[hallazgo_id].add(fila_id)
    return salida


def _bloque_dinero(caja: dict[str, Any], partidas: list[Any], direccion: str,
                   hoy: date) -> dict[str, Any]:
    """Lo que se espera cobrar (o pagar): pendiente, vencido y por ventanas, con cuantas
    facturas."""
    esperado = caja["esperado"][direccion]
    propias = [p for p in partidas if p.direccion == direccion]
    salida: dict[str, Any] = {
        "facturas": len(propias),
        "vencidas": sum(1 for p in propias if p.fecha is not None and p.fecha < hoy),
    }
    for clave, ventana in (("pendiente", "total"), ("vencido", "vencido"), ("semana", "semana"),
                           ("mes", "mes"), ("proximos_30", "proximos_30"),
                           ("sin_fecha", "sin_fecha")):
        salida[f"{clave}_cent"] = esperado[ventana]
        salida[clave] = _euros(esperado[ventana])
    return salida


def _bloque_caja(caja: dict[str, Any]) -> dict[str, Any]:
    """§17 "Cash Position": lo esperado que entra, lo que sale y el neto, por ventana, lo que
    movio el banco este mes, y el estimado del planning aparte (decision 22)."""
    esperado = caja["esperado"]
    ventanas = {}
    for ventana in ("vencido", "semana", "mes", "proximos_30", "total"):
        entrada, salida_ = esperado["entrada"][ventana], esperado["salida"][ventana]
        ventanas[ventana] = {"entrada_cent": entrada, "salida_cent": salida_,
                             "neto_cent": entrada - salida_, "entrada": _euros(entrada),
                             "salida": _euros(salida_), "neto": _euros(entrada - salida_)}
    real = caja["real"]
    estimado = dict(caja["estimado"])
    for clave in [c for c, v in estimado.items() if c.endswith("_cent") and v is not None]:
        estimado[clave.removesuffix("_cent")] = _euros(estimado[clave])
    return {"ventanas": ventanas, "fechas": caja["ventanas"],
            "cobrado_mes_cent": real["cobrado"]["mes"], "pagado_mes_cent": real["pagado"]["mes"],
            "cobrado_mes": _euros(real["cobrado"]["mes"]),
            "pagado_mes": _euros(real["pagado"]["mes"]),
            "estimado": estimado}


def _bloque_facturacion(conn: sqlite3.Connection,
                        pendientes: list[sqlite3.Row]) -> dict[str, Any]:
    """§17 "Billing": el trabajo sin facturar (V6), la facturacion que falta (V8, periodos
    sin ninguna factura, y V5, horas validadas que no estan en una factura que cubre su
    periodo) y las diferencias con el planning (G y V). Sin planning, sin datos: nunca cero.

    V5 va con la facturacion que falta y no con las diferencias: es lo que el
    §7 llama "Missing billable hours" y el §8 "Missing billing (V5, V8)".
    `categoria_de` lo pone en "sin_facturar" por lo mismo.
    """
    if not instantaneas.fotos_planning(conn):
        detalle = ("No se ha importado ningún planning de TRNSPRNT: no se sabe qué trabajo "
                   "falta por facturar, qué periodos no tienen factura ni qué no cuadra con "
                   "el planning.")
        return {"estado": "sin_datos", "detalle": detalle}
    sin_facturar = [h for h in pendientes if h["regla"] == "V6"]
    periodos = [h for h in pendientes if h["regla"] == "V8"]
    horas_fuera = [h for h in pendientes if h["regla"] == "V5"]
    planning = [h for h in pendientes if categoria_de(h["regla"]) == "planning"]
    valor = sum(json.loads(h["valores_json"] or "{}").get("valor_cent") or 0
                for h in sin_facturar)
    horas = sum(json.loads(h["valores_json"] or "{}").get("horas_mil") or 0
                for h in sin_facturar)
    valor_planning = sum(json.loads(h["valores_json"] or "{}").get("valor_cent") or 0
                         for h in planning)
    return {
        "estado": "ok",
        "sin_facturar": {"periodos": len(sin_facturar), "valor_cent": valor,
                         "valor": _euros(valor), "horas_mil": horas,
                         "horas": _horas_texto(horas),
                         "estimado": any(json.loads(h["valores_json"] or "{}").get("estimado")
                                         for h in sin_facturar),
                         "clientes": sorted({h["fila_id"] for h in sin_facturar})},
        "periodos_sin_factura": [{"hallazgo_id": h["id"], "cliente_id": h["fila_id"],
                                  "estado": h["estado"], "regla": "V8", "resultado": FALLO,
                                  "valores": valores_de(h),
                                  **{k: json.loads(h["valores_json"] or "{}").get(k)
                                     for k in ("ciclo", "desde", "hasta")}}
                                 for h in periodos],
        "horas_sin_facturar": [_horas_sin_facturar(h) for h in horas_fuera],
        "diferencias_planning": {"hallazgos": len(planning),
                                 "aceptados": sum(1 for h in planning
                                                  if h["estado"] == "aceptado"),
                                 "facturas": len({h["factura_id"] for h in planning
                                                  if h["factura_id"] is not None}),
                                 "valor_cent": valor_planning, "valor": _euros(valor_planning)},
    }


def _horas_sin_facturar(h: sqlite3.Row) -> dict[str, Any]:
    """Un V5 pendiente: la venta, su Objeto, el periodo que cobra y las horas (y su valor
    estimado) que el planning tiene validadas en ese periodo y ninguna linea cubre."""
    valores = json.loads(h["valores_json"] or "{}")
    return {"hallazgo_id": h["id"], "factura_id": h["fila_id"], "estado": h["estado"],
            "regla": "V5", "resultado": FALLO, "valores": valores,
            "objeto_id": valores.get("objeto"), "desde": valores.get("desde"),
            "hasta": valores.get("hasta"), "horas_mil": valores.get("horas_mil"),
            "horas": _horas_texto(valores.get("horas_mil")),
            "valor_cent": valores.get("valor_cent"), "valor": _euros(valores.get("valor_cent")),
            "estimado": bool(valores.get("estimado"))}


# Lo que dice que una PO esta cerca de su limite, de su fin o de agotarse: sus
# avisos con la condicion viva (abiertos o aceptados; desaparecido ya no lo es).
# Solo de las PO activas: una que ya caduco no esta "cerca de caducar" (P7
# sigue abierto despues de su fin, con SIN_DATOS o con el FALLO "caduco"), y va
# a `caducadas`.
_PO_ESTADO = {"cerca_del_limite": ("P5",), "cerca_de_caducar": ("P7",),
              "agotamiento_previsto": ("P8", "P9", "P10")}


def _cifras_po(ordenes: list[dict[str, Any]]) -> dict[str, Any]:
    valor = sum(o["valor_cent"] for o in ordenes)
    consumido = sum(o["consumido_cent"] for o in ordenes)
    return {"activas": len(ordenes), "valor_cent": valor, "valor": _euros(valor),
            "consumido_cent": consumido, "consumido": _euros(consumido),
            "restante_cent": valor - consumido, "restante": _euros(valor - consumido)}


def _bloque_po(conn: sqlite3.Connection, pendientes: list[sqlite3.Row],
               hoy: date) -> dict[str, Any]:
    """§17 "PO": de las PO activas de cada lado, el valor, lo consumido y lo que queda (sin
    IVA); y las que estan cerca de su limite, de caducar o de agotarse antes de su fin, y las
    que ya caducaron con un P7 pendiente.

    Los dos lados no se suman: una PO de cliente es lo que BMS puede facturar y
    una de proveedor lo que un proveedor puede facturar a BMS (como la vista
    del Objeto, `ordenes_resumen`).
    """
    lista = ordenes_compra(conn)
    hoy_ = hoy.isoformat()
    activas = [o for o in lista if not o["cerrada"]
               and (o["fecha_fin"] is None or o["fecha_fin"] >= hoy_)]
    activas_ids = {o["id"] for o in activas}
    por_id = {o["id"]: o for o in lista}
    salida: dict[str, Any] = {
        "activas": len(activas),
        **{lado: _cifras_po([o for o in activas if o["lado"] == lado])
           for lado in ("cliente", "proveedor")},
    }

    def fila(i: int) -> dict[str, Any]:
        o = por_id[i]
        return {"id": i, "numero": o["numero"], "lado": o["lado"], "parte": o["parte"]["nombre"],
                "consumido_pct": o["consumido_pct"], "restante": o["restante"],
                "fecha_fin": o["fecha_fin"]}

    def con_aviso(reglas: tuple[str, ...]) -> set[int]:
        return {h["fila_id"] for h in pendientes if h["regla"] in reglas
                and h["tabla"] == "orden_compra" and h["estado"] != "desaparecido"
                and h["fila_id"] in por_id}

    for clave, reglas in _PO_ESTADO.items():
        salida[clave] = [fila(i) for i in sorted(con_aviso(reglas) & activas_ids)]
    salida["caducadas"] = [fila(i) for i in sorted(con_aviso(("P7",)))
                           if not por_id[i]["cerrada"] and por_id[i]["fecha_fin"] is not None
                           and por_id[i]["fecha_fin"] < hoy_]
    return salida


def _bloque_btw(conn: sqlite3.Connection, hoy: date) -> dict[str, Any]:
    """§17 "VAT / BTW": el trimestre en curso (ingresos, IVA repercutido, deducible, lo que
    sale a pagar o a devolver), el proximo plazo sin presentar que no ha pasado y cuantos
    trimestres tienen el plazo pasado sin la presentacion anotada."""
    from . import btw

    resumen = btw.resumen(conn, hoy)
    actual = resumen["actual"]
    cifras = actual["cifras"]
    plazos = [*resumen["por_presentar"], *([actual] if actual["estado"] != "presentado"
                                           else [])]
    por_venir = [t for t in plazos if t["dias_para_limite"] >= 0]
    proximo = min(por_venir, key=lambda t: t["limite_presentacion"]) if por_venir else None
    return {
        "trimestre": actual["etiqueta"], "estado": actual["estado"],
        "ingresos_cent": cifras["ingresos_cent"], "ingresos": _euros(cifras["ingresos_cent"]),
        "iva_repercutido_cent": cifras["5a"], "iva_repercutido": _euros(cifras["5a"]),
        "iva_deducible_cent": cifras["5b"], "iva_deducible": _euros(cifras["5b"]),
        "saldo_cent": cifras["5c"], "saldo": _euros(cifras["5c"]),
        "a_pagar_cent": cifras["a_pagar_cent"], "a_devolver_cent": cifras["a_devolver_cent"],
        "limite_presentacion": actual["limite_presentacion"],
        "limite_pago": actual["limite_pago"], "revisar": len(actual["revisar"]),
        "proximo_plazo": None if proximo is None else {
            "trimestre": proximo["etiqueta"], "estado": proximo["estado"],
            "limite_presentacion": proximo["limite_presentacion"],
            "dias_para_limite": proximo["dias_para_limite"]},
        "plazos_pasados": [t["etiqueta"] for t in plazos if t["dias_para_limite"] < 0],
        "por_presentar": [{"trimestre": t["etiqueta"], "estado": t["estado"],
                           "limite_presentacion": t["limite_presentacion"],
                           "dias_para_limite": t["dias_para_limite"]}
                          for t in resumen["por_presentar"]],
        "configuracion_confirmada": resumen["configuracion"]["confirmada"],
    }


def _vencidas(lectura: _Lectura, sentido: str) -> dict[str, Any]:
    """Las facturas de un sentido vencidas y sin pagar: cuantas, lo que queda y las 20 que mas
    llevan vencidas.

    Una en otra moneda (X1) cuenta como vencida, porque lo esta, pero no suma:
    no tiene importe en euros (`sin_importe`).
    """
    from .estados import VENCIDA

    hoy = lectura.hoy
    lista = [f for f in lectura.facturas if f.sentido == sentido and _cuenta(f)
             and f.estado(hoy) == VENCIDA]
    lista.sort(key=lambda f: (f.vencimiento or hoy, f.id))
    pendiente = sum(f.pendiente_cent or 0 for f in lista)
    return {"facturas": len(lista), "pendiente_cent": pendiente, "pendiente": _euros(pendiente),
            "sin_importe": sum(1 for f in lista if f.pendiente_cent is None),
            "lista": [{"id": f.id, "numero": f.numero, "contraparte": f.parte,
                       "vencimiento": _iso(f.vencimiento),
                       "dias": (hoy - f.vencimiento).days if f.vencimiento else None,
                       "pendiente_cent": f.pendiente_cent, "pendiente": _euros(f.pendiente_cent)}
                      for f in lista[:20]]}


def _bloque_atencion(conn: sqlite3.Connection, lectura: _Lectura,
                     pendientes: list[sqlite3.Row]) -> dict[str, Any]:
    """§17 "Attention Required": las compras y ventas vencidas, los hallazgos pendientes por
    categoria (los activos y, aparte, los aceptados), las excepciones abiertas y cuantas
    facturas estan bloqueadas o son urgentes."""
    objetivos = _facturas_de_hallazgos(conn)
    categorias = {clave: {"clave": clave, "titulo": titulo, "activos": 0, "aceptados": 0,
                          "reglas": defaultdict(int), "facturas": set()}
                  for clave, titulo in _CATEGORIAS}
    for h in pendientes:
        c = categorias[categoria_de(h["regla"])]
        if h["estado"] == "aceptado":
            c["aceptados"] += 1
            continue
        c["activos"] += 1
        c["reglas"][h["regla"]] += 1
        c["facturas"] |= objetivos.get(h["id"], set()) | (
            {h["factura_id"]} if h["factura_id"] is not None else set())
    niveles = dict(conn.execute("SELECT nivel, count(*) FROM factura_estado GROUP BY nivel"))
    excepciones_ = dict(conn.execute("SELECT estado, count(*) FROM excepcion "
                                     "WHERE estado <> 'resuelta' GROUP BY estado"))
    return {
        "compras_vencidas": _vencidas(lectura, "entrante"),
        "ventas_vencidas": _vencidas(lectura, "saliente"),
        "categorias": [{**c, "reglas": dict(sorted(c["reglas"].items())),
                        "facturas": len(c["facturas"]),
                        "factura_ids": sorted(c["facturas"])[:50]}
                       for c in categorias.values()],
        "hallazgos": sum(c["activos"] for c in categorias.values()),
        "aceptados": sum(c["aceptados"] for c in categorias.values()),
        "excepciones": {"abiertas": sum(excepciones_.values()), "por_estado": excepciones_},
        "bloqueadas": niveles.get(Prioridad.BLOQUEADA.value, 0),
        "urgentes": niveles.get(Prioridad.URGENTE.value, 0),
        "atencion": niveles.get(Prioridad.ATENCION.value, 0),
    }


def panel(conn: sqlite3.Connection) -> dict[str, Any]:
    """El panel principal (§17), con el `hoy` del reloj del almacen."""
    lectura = _leer(conn)
    hoy = lectura.hoy
    leidos = flujo_caja.datos(conn)
    caja = flujo_caja.flujo(conn, hoy, leidos=leidos)
    pendientes = _hallazgos_pendientes(conn)
    del_dia = estado_del(conn)
    return {
        "contrato": CONTRATO_V2, "hoy": hoy.isoformat(),
        "estado_del": del_dia, "al_dia": del_dia == hoy.isoformat(),
        "fuentes_caducadas": [f for f in fuentes(conn) if f["caducada"]],
        "dinero_entra": _bloque_dinero(caja, leidos[0], flujo_caja.ENTRADA, hoy),
        "dinero_sale": _bloque_dinero(caja, leidos[0], flujo_caja.SALIDA, hoy),
        "caja": _bloque_caja(caja),
        "facturacion": _bloque_facturacion(conn, pendientes),
        "ordenes_compra": _bloque_po(conn, pendientes, hoy),
        "btw": _bloque_btw(conn, hoy),
        "atencion": _bloque_atencion(conn, lectura, pendientes),
    }


# ------------------------------------------------------------ cobrar y pagar (paso 16)
#
# Lo que la app ensena en "Cuentas por cobrar" y "Cuentas por pagar": la cartera
# de un lado (lo que nos deben o lo que debemos, desde cuando y de quien), los
# pagos que el banco propuso y esperan a una persona, y las lineas del banco
# sin casar. Solo leen: confirmar, retirar o apuntar un pago son ordenes
# (pagos.py), y nada de aqui paga, aprueba ni prepara una transferencia.
#
# La cartera sale de las mismas partidas que el panel (flujo_caja.datos: lo que
# queda de cada deuda en juego, por su vencimiento efectivo) y sus totales de
# la misma funcion (`_bloque_dinero`): la tarjeta del inicio, la cabecera de la
# pantalla, los tramos y las empresas dicen los mismos centimos, porque son la
# misma lista de partidas repartida de tres formas. Solo cuentan las deudas
# (reglas.pagos.vence): un abono sin enlazar no es un cobro con fecha y va
# aparte (R4), y lo que no esta en euros (X1) no suma en ningun sitio.
#
# "saliente" es la cartera de las ventas (lo que nos deben: por cobrar) y
# "entrante" la de las compras (lo que debemos: por pagar), como el `sentido`
# de una factura y de la busqueda.

SENTIDOS_CARTERA = {"saliente": (flujo_caja.ENTRADA, "cliente", "cliente_id"),
                    "entrante": (flujo_caja.SALIDA, "proveedor", "proveedor_id")}

# Los tramos de antiguedad: dias de retraso desde el vencimiento efectivo, con los dos
# extremos incluidos (None: sin limite). "al_corriente" es lo que aun no ha vencido (vence
# hoy o despues: el panel tampoco lo cuenta como vencido); "sin_fecha", lo que no tiene
# vencimiento (ni impreso ni plazo: no se adivina). Los seis suman lo pendiente.
TRAMOS = (("al_corriente", None, 0), ("1_30", 1, 30), ("31_60", 31, 60), ("61_90", 61, 90),
          ("mas_de_90", 91, None))
SIN_FECHA = "sin_fecha"

# Lo que retiene una factura: un hallazgo activo (ni aceptado ni cerrado) que bloquea o
# retiene. Un aviso (K1 "vencida sin pagar", K7...) no retiene: dice algo, no para nada.
_RETIENEN = frozenset({"bloqueo", "retencion"})


def sentido_cartera(texto: str | None) -> str:
    """El `sentido` de la cartera: obligatorio, porque sumar lo que nos deben con lo que
    debemos no es ninguna cifra. ValueError (un 400) si falta o no es uno de los dos."""
    if not texto or not texto.strip():
        raise FiltroNoValido("sentido: lleva un valor (saliente: por cobrar; entrante: por "
                             "pagar)")
    if texto.strip() not in SENTIDOS_CARTERA:
        raise FiltroNoValido(f"sentido: {texto!r} no es ninguno de "
                             f"{', '.join(SENTIDOS_CARTERA)}")
    return texto.strip()


def tramo_de(dias: int | None) -> str:
    """El tramo de antiguedad de una partida por sus dias de retraso (None: sin fecha)."""
    if dias is None:
        return SIN_FECHA
    for clave, desde, hasta in TRAMOS:
        if (desde is None or dias >= desde) and (hasta is None or dias <= hasta):
            return clave
    raise AssertionError(f"ningun tramo para {dias} dias")   # los tramos cubren todo entero


def _limites_tramo(hoy: date, desde: int | None, hasta: int | None) -> tuple[str | None,
                                                                            str | None]:
    """Los vencimientos de un tramo (vence_desde, vence_hasta, incluidos), para abrir la
    busqueda filtrada: un retraso de `desde` dias vence `desde` dias antes de hoy."""
    vence_hasta = None if desde is None else (hoy - timedelta(days=desde)).isoformat()
    vence_desde = None if hasta is None else (hoy - timedelta(days=hasta)).isoformat()
    return vence_desde, vence_hasta


def _suma(partidas: list[Any]) -> dict[str, Any]:
    importe = sum(p.importe_cent for p in partidas)
    return {"facturas": len(partidas), "importe_cent": importe, "importe": _euros(importe)}


def _retenidas(conn: sqlite3.Connection,
               razones_por_factura: dict[int, list[dict[str, Any]]] | None = None) -> set[int]:
    """Las facturas retenidas: con un hallazgo activo que bloquea o retiene, o Bloqueadas
    (tambien si alguien la subio a mano)."""
    if razones_por_factura is None:
        razones_por_factura = _razones_por_factura(conn)
    salida = {factura_id for factura_id, razones in razones_por_factura.items()
              if any(r["estado"] != "aceptado" and r["severidad"] in _RETIENEN
                     for r in razones)}
    salida.update(f[0] for f in conn.execute(
        "SELECT factura_id FROM factura_estado WHERE nivel = ?", (Prioridad.BLOQUEADA.value,)))
    return salida


# Los avisos de pagos raros que la pantalla de cobrar o pagar ensena aparte (revision de
# Aurora §8.4 c): pago distinto del saldo (K2), apuntado a mano sin rastro en el banco (K3),
# pagada dos veces (K4), pagada estando Bloqueada (K5), banco y Exact no coinciden (K8) y
# pagos en una factura que no cuenta (K9). K1 (vencida) ya es lo vencido, K6 es de un
# extracto y K7 de una linea del banco (sin_casar): no son de una factura.
AVISOS_PAGO = ("K2", "K3", "K4", "K5", "K8", "K9")


def _avisos_pago(lectura: _Lectura, sentido: str, razones: dict[int, list[dict[str, Any]]],
                 nombres: dict[int, str], columna: str) -> list[dict[str, Any]]:
    """Por regla, las facturas de un sentido con ese aviso de pago activo (ni aceptado ni
    cerrado), en el orden de AVISOS_PAGO; las reglas sin ninguna, fuera."""
    por_regla: dict[str, list[Any]] = defaultdict(list)
    for f in sorted(lectura.facturas, key=lambda f: f.id):
        if f.sentido != sentido:
            continue
        reglas = {r["regla"] for r in razones.get(f.id, ()) if r["estado"] != "aceptado"}
        for regla in AVISOS_PAGO:
            if regla in reglas:
                por_regla[regla].append(f)
    return [{"regla": regla, "facturas": [
                {"id": f.id, "numero": f.numero, "parte_id": getattr(f, columna),
                 "parte": nombres.get(getattr(f, columna)) or f.parte}
                for f in por_regla[regla]]}
            for regla in AVISOS_PAGO if por_regla[regla]]


def _plazo_corto(plazos: dict[str, Any]) -> dict[str, Any]:
    return {"pagadas": plazos["pagadas"], "media_dias": plazos["media_dias"],
            "tarde": plazos["tarde"]}


def cartera(conn: sqlite3.Connection, sentido: str) -> dict[str, Any]:
    """Lo que nos deben (saliente) o lo que debemos (entrante): los totales del panel,
    la antiguedad por tramos, cada empresa, lo retenido y lo que espera aparte.

    `totales` es `panel.dinero_entra` (o `dinero_sale`) al centimo: sale de las mismas
    partidas con la misma funcion. Los tramos y las empresas reparten esas mismas partidas,
    asi que suman lo pendiente; lo vencido son los tramos de 1 dia en adelante. Las
    facturas sin proveedor (o cliente) del maestro van juntas en una fila con `id` null,
    para que las empresas sumen el total.

    Aparte, sin sumar: los pagos propuestos por el banco que esperan a una persona
    (`por_confirmar`), lo del banco sin casar en este sentido (`sin_casar`: ingresos para
    cobrar, cargos para pagar), los abonos sin enlazar (R4) y cuantas facturas en juego no
    tienen importe en euros (X1).
    """
    from . import pagos, politica
    from .estados import EN_JUEGO
    from .reglas.pagos import tolerancia_cent

    sentido = sentido_cartera(sentido)
    direccion, tabla, columna = SENTIDOS_CARTERA[sentido]
    lectura = _leer(conn)
    hoy = lectura.hoy
    partidas, movidos = flujo_caja.datos(conn)
    # Lo mismo que hace flujo_caja.flujo para el panel, sin el estimado del planning (que
    # no entra en lo esperado): calcular es puro y la cartera no lee nada mas.
    caja = flujo_caja.calcular(partidas, movidos, hoy)
    propias = [p for p in partidas if p.direccion == direccion]
    por_id = {f.id: f for f in lectura.facturas}
    razones_f = _razones_por_factura(conn)
    retenidas = _retenidas(conn, razones_f)

    por_tramo: dict[str, list[Any]] = {clave: [] for clave, _d, _h in TRAMOS}
    por_tramo[SIN_FECHA] = []
    for p in propias:
        por_tramo[tramo_de(None if p.fecha is None else (hoy - p.fecha).days)].append(p)
    # Por empresa, con la funcion que usan tambien las listas y las vistas de las partes.
    por_parte = {parte: [(p, None if p.fecha is None else (hoy - p.fecha).days) for p in suyas]
                 for parte, suyas in _partidas_por_parte(lectura, propias, columna).items()}

    tramos = []
    for clave, desde, hasta in (*TRAMOS, (SIN_FECHA, None, None)):
        vence_desde, vence_hasta = ((None, None) if clave == SIN_FECHA
                                    else _limites_tramo(hoy, desde, hasta))
        tramos.append({"clave": clave, "dias_desde": desde, "dias_hasta": hasta,
                       "vence_desde": vence_desde, "vence_hasta": vence_hasta,
                       **_suma(por_tramo[clave])})

    facturas_de: dict[int, list[Any]] = defaultdict(list)
    for f in lectura.facturas:
        if getattr(f, columna) is not None:
            facturas_de[getattr(f, columna)].append(f)
    nombres = {f["id"]: f["nombre"] for f in conn.execute(f"SELECT id, nombre FROM {tabla}")}
    prioridades = _prioridades(conn, tabla)
    razones = _razones_por_parte(conn)[tabla]
    partes, claves = [], {}
    for parte_id, suyas in por_parte.items():
        vencidas = [(p, d) for p, d in suyas if d is not None and d > 0]
        pendiente = sum(p.importe_cent for p, _d in suyas)
        vencido = sum(p.importe_cent for p, _d in vencidas)
        retenido = sum(p.importe_cent for p, _d in suyas if p.factura_id in retenidas)
        prio = prioridades.get(parte_id, _SIN_PRIORIDAD) if parte_id is not None else None
        partes.append({
            "id": parte_id, "nombre": nombres.get(parte_id) if parte_id is not None else None,
            "facturas": len(suyas), "vencidas": len(vencidas),
            "pendiente_cent": pendiente, "pendiente": _euros(pendiente),
            "vencido_cent": vencido, "vencido": _euros(vencido),
            "retenido_cent": retenido, "retenido": _euros(retenido),
            "mas_antigua_dias": max((d for _p, d in vencidas), default=None),
            "nivel": prio["nivel"] if prio else None, "puntos": prio["puntos"] if prio else None,
            "razones": razones.get(parte_id, []) if parte_id is not None else [],
            "plazo_de_pago": (_plazo_corto(_plazos(lectura, facturas_de.get(parte_id, [])))
                              if parte_id is not None else None),
        })
        claves[parte_id] = (parte_id is None, prioridad.clave_orden(
            prio["nivel"], prio["puntos"], date.fromisoformat(prio["vencimiento"])
            if prio["vencimiento"] else None, prio["importe_cent"], 0)[:-1] if prio else (),
            -vencido, -pendiente)
    # Como las listas (§8): la prioridad de la empresa; a igualdad, lo vencido y lo
    # pendiente, y el nombre. La fila sin empresa del maestro, al final.
    partes.sort(key=lambda r: (*claves[r["id"]], r["nombre"] or "", r["id"] or 0))

    propuestas = [(sentido_, importe) for sentido_, importe in conn.execute(
        "SELECT f.sentido, a.importe_cent FROM aplicacion_pago AS a "
        "JOIN factura AS f ON f.id = a.factura_id WHERE a.estado = 'propuesta'")
        if sentido_ == sentido]
    tolerancia = tolerancia_cent(politica.politica_reglas(conn).tolerancia_pago)
    entra = direccion == flujo_caja.ENTRADA
    abiertos = [m.resto_cent for m in pagos.movimientos_abiertos(conn, tolerancia)
                if (m.resto_cent > 0) == entra]
    abonos = sorted(_abonos_sin_enlazar(lectura, [f for f in lectura.facturas
                                                   if f.sentido == sentido]),
                    key=lambda f: (f.fecha_factura or date.min, f.id))
    abonado = sum(f.pendiente_cent for f in abonos)
    movido = caja["real"]["cobrado" if entra else "pagado"]["mes"]
    del_dia = estado_del(conn)
    # Lo que toca hasta el domingo: lo vencido y lo que vence esta semana (la ventana
    # `semana` del panel), cada factura con si esta retenida y por que. En "Por pagar" es
    # lo limpio y lo retenido de la semana (revision §8.4); suma lo vencido mas la semana.
    domingo = date.fromisoformat(caja["ventanas"]["semana"][1])
    semana = sorted((p for p in propias if p.fecha is not None and p.fecha <= domingo),
                    key=lambda p: (p.fecha, p.factura_id))
    niveles = dict(conn.execute("SELECT factura_id, nivel FROM factura_estado").fetchall())
    return {
        "sentido": sentido, "hoy": hoy.isoformat(),
        "estado_del": del_dia, "al_dia": del_dia == hoy.isoformat(),
        "totales": _bloque_dinero(caja, partidas, direccion, hoy),
        "fechas": caja["ventanas"],
        "movido_mes_cent": movido, "movido_mes": _euros(movido),
        "tramos": tramos,
        # Contrato 2.3: lo retenido tambien factura a factura, con por que (en "Por pagar",
        # lo que esta parado y no vence esta semana tambien se ve).
        "retenido": {**_suma([p for p in propias if p.factura_id in retenidas]),
                     "lista": [_fila_semana(p, por_id.get(p.factura_id), hoy, columna, nombres,
                                            True, niveles, razones_f.get(p.factura_id, []))
                               for p in sorted((p for p in propias if p.factura_id in retenidas),
                                               key=lambda p: (p.fecha or date.max,
                                                              p.factura_id))]},
        "sin_retener": _suma([p for p in propias if p.factura_id not in retenidas]),
        "partes": partes,
        "por_confirmar": {"pagos": len(propuestas),
                          "importe_cent": sum(abs(i) for _s, i in propuestas),
                          "importe": _euros(sum(abs(i) for _s, i in propuestas))},
        "sin_casar": {"movimientos": len(abiertos),
                      "importe_cent": sum(abs(r) for r in abiertos),
                      "importe": _euros(sum(abs(r) for r in abiertos))},
        "abonos_sin_enlazar": {
            "facturas": len(abonos), "importe_cent": abonado, "importe": _euros(abonado),
            "lista": [{"id": f.id, "numero": f.numero, "contraparte": f.parte,
                       "parte_id": getattr(f, columna), "parte": nombres.get(getattr(f, columna)),
                       "fecha_factura": _iso(f.fecha_factura),
                       "pendiente_cent": f.pendiente_cent, "pendiente": _euros(f.pendiente_cent)}
                      for f in abonos]},
        "sin_importe": sum(1 for f in lectura.facturas
                           if f.sentido == sentido and _cuenta(f) and f.pendiente_cent is None
                           and f.estado(hoy) in EN_JUEGO),
        "esta_semana": {
            "hasta": domingo.isoformat(),
            "retenido": _suma([p for p in semana if p.factura_id in retenidas]),
            "sin_retener": _suma([p for p in semana if p.factura_id not in retenidas]),
            "facturas": [_fila_semana(p, por_id.get(p.factura_id), hoy, columna, nombres,
                                      p.factura_id in retenidas, niveles,
                                      razones_f.get(p.factura_id, []))
                         for p in semana]},
        "avisos_pago": _avisos_pago(lectura, sentido, razones_f, nombres, columna),
    }


def _fila_semana(p: Any, factura: Any, hoy: date, columna: str, nombres: dict[int, str],
                 retenida: bool, niveles: dict[int, str],
                 razones: list[dict[str, Any]]) -> dict[str, Any]:
    """Una factura de lo que toca hasta el domingo: lo que queda, su vencimiento, los dias
    de retraso (negativos: los que faltan), si esta retenida y sus hallazgos pendientes."""
    parte_id = getattr(factura, columna) if factura is not None else None
    return {"id": p.factura_id, "numero": factura.numero if factura is not None else None,
            "parte_id": parte_id,
            "parte": (nombres.get(parte_id) if parte_id is not None else None)
            or (factura.parte if factura is not None else None),
            "pendiente_cent": p.importe_cent, "pendiente": _euros(p.importe_cent),
            "vencimiento": _iso(p.fecha), "dias": None if p.fecha is None else (hoy - p.fecha).days,
            "retenida": retenida, "nivel": niveles.get(p.factura_id),
            "razones": [r for r in razones if r["estado"] != "aceptado"]}


def _coincidencias(regla: str | None) -> dict[str, bool]:
    """En que coincidieron el movimiento y la factura al casarlos (pagos.casar lo apunta en
    `regla`: "referencia+importe"...): el porque de una propuesta, con su si o su no."""
    vistas = set((regla or "").split("+"))
    return {nombre: nombre in vistas for nombre in ("referencia", "importe", "contraparte")}


def propuestas_pago(conn: sqlite3.Connection, sentido: str | None = None) -> list[dict[str, Any]]:
    """Los pagos que el banco propuso (dos de tres coincidencias, o las tres con el importe
    solo dentro de la tolerancia) y esperan a una persona: confirmar_pago o retirar_pago, con
    su `rev`. Cada uno con la linea del banco al lado de la factura y las tres coincidencias.

    `sentido` (de la factura) deja solo las de las ventas o las de las compras. El texto del
    banco (contraparte, concepto) es de un tercero: va tal cual, como texto.
    """
    if sentido is not None:
        sentido = sentido_cartera(sentido)
    lectura = _leer(conn)
    por_id = {f.id: f for f in lectura.facturas}
    nombres = _nombres_de_partes(conn)
    salida = []
    for a in conn.execute(
            "SELECT a.id, a.rev, a.factura_id, a.movimiento_id, a.importe_cent, a.fecha_pago, "
            "a.regla, f.sentido, f.tipo, f.numero, f.proveedor_id, f.cliente_id, f.total_cent, "
            "m.fecha_contable, m.importe_cent AS importe_movimiento, m.contraparte_iban, "
            "m.contraparte_nombre_doc, m.concepto_doc, m.referencia_estructurada, "
            "m.referencia_e2e FROM aplicacion_pago AS a JOIN factura AS f ON f.id = a.factura_id "
            "LEFT JOIN movimiento_bancario AS m ON m.id = a.movimiento_id "
            "WHERE a.estado = 'propuesta' ORDER BY a.fecha_pago, a.id"):
        if sentido is not None and a["sentido"] != sentido:
            continue
        f = por_id.get(a["factura_id"])
        tabla, parte_id = (("proveedor", a["proveedor_id"]) if a["sentido"] == "entrante"
                           else ("cliente", a["cliente_id"]))
        entra = flujo_caja.direccion(a["sentido"], a["importe_cent"]) == flujo_caja.ENTRADA
        salida.append({
            "id": a["id"], "rev": a["rev"], "lado": "cobro" if entra else "pago",
            "importe_cent": a["importe_cent"], "importe": _euros(a["importe_cent"]),
            "fecha_pago": a["fecha_pago"], "regla": a["regla"],
            "coincidencias": _coincidencias(a["regla"]),
            "factura": {
                "id": a["factura_id"], "numero": a["numero"], "sentido": a["sentido"],
                "tipo": a["tipo"], "contraparte": f.parte if f else None,
                "proveedor_id": a["proveedor_id"], "cliente_id": a["cliente_id"],
                "parte": nombres.get((tabla, parte_id)) if parte_id is not None else None,
                "total_cent": a["total_cent"], "total": _euros(a["total_cent"]),
                "pendiente_cent": f.pendiente_cent if f else None,
                "pendiente": _euros(f.pendiente_cent) if f else None,
                "vencimiento": _iso(f.vencimiento) if f else None,
                "estado_pago": f.estado(lectura.hoy) if f else None},
            "movimiento": None if a["movimiento_id"] is None else {
                "id": a["movimiento_id"], "fecha": a["fecha_contable"],
                "importe_cent": a["importe_movimiento"], "importe": _euros(a["importe_movimiento"]),
                "contraparte": a["contraparte_nombre_doc"],
                "contraparte_iban": a["contraparte_iban"], "concepto": a["concepto_doc"],
                "referencia": a["referencia_estructurada"],
                "referencia_e2e": a["referencia_e2e"]},
        })
    return salida


PARAMETROS_MOVIMIENTOS = ("sin_casar", "signo", "desde", "hasta", "texto", "limite")
SIGNOS = ("entrada", "salida")


def movimientos_banco(conn: sqlite3.Connection,
                      datos: dict[str, str] | None = None) -> dict[str, Any]:
    """Las lineas del banco, la mas reciente primero: por defecto solo las sin casar (lo que
    queda de ellas sin ninguna factura, propuesta ni confirmada), para elegir una al apuntar
    un pago (marcar_pagada con su movimiento_id) o para ver lo que K7 avisara.

    Sin casar es lo mismo que mira casar (pagos.movimientos_abiertos, con la tolerancia de
    la politica): ni los traspasos entre cuentas propias ni lo que va a un beneficiario
    conocido, que no pagan facturas, ni lo que no esta en euros (X1). Con `sin_casar=no`,
    todas, cada una con lo que le queda y si es `propia`.

    Filtros (los de /api/v2/movimientos): `signo` (entrada: ingresos; salida: cargos),
    `desde` y `hasta` (fecha contable, incluidas), `texto` (en la contraparte o el concepto,
    sin mayusculas) y `limite` (de 1 a 1000, 200). `total` y las sumas son de todas las que
    cumplen, no solo de las que caben en el limite.
    """
    from . import pagos, politica
    from .almacen import reloj_de
    from .reglas.pagos import tolerancia_cent

    datos = dict(datos or {})
    raros = sorted(set(datos) - set(PARAMETROS_MOVIMIENTOS))
    if raros:
        raise FiltroNoValido(f"filtro desconocido: {', '.join(raros)}")
    sin_casar = _si("sin_casar", [datos["sin_casar"]]) if "sin_casar" in datos else True
    signo = datos.get("signo")
    if signo is not None and signo not in SIGNOS:
        raise FiltroNoValido(f"signo: {signo!r} no es ninguno de {', '.join(SIGNOS)}")
    desde = _dia("desde", [datos["desde"]]) if "desde" in datos else None
    hasta = _dia("hasta", [datos["hasta"]]) if "hasta" in datos else None
    texto = pliegue(_uno("texto", [datos["texto"]])) if "texto" in datos else None
    limite = _entero("limite", [datos["limite"]]) if "limite" in datos else 200
    if not 1 <= limite <= LIMITE_BUSQUEDA:
        raise FiltroNoValido(f"limite va de 1 a {LIMITE_BUSQUEDA}")

    hoy = reloj_de(conn).hoy()
    tolerancia = tolerancia_cent(politica.politica_reglas(conn).tolerancia_pago)
    abiertos = {m.id: m.resto_cent for m in pagos.movimientos_abiertos(conn, tolerancia)}
    aplicado = pagos.aplicado_por_movimiento(conn)
    ajenas = pagos.ajenas(conn)
    cuentas: dict[int, dict[str, int]] = defaultdict(lambda: {"confirmada": 0, "propuesta": 0})
    for movimiento_id, estado, n in conn.execute(
            "SELECT movimiento_id, estado, count(*) FROM aplicacion_pago "
            "WHERE movimiento_id IS NOT NULL GROUP BY movimiento_id, estado"):
        cuentas[movimiento_id][estado] = n
    filas = []
    for m in conn.execute("SELECT * FROM movimiento_bancario "
                          "ORDER BY fecha_contable DESC, id DESC"):
        importe = m["importe_cent"]
        abierto = m["id"] in abiertos
        if sin_casar and not abierto:
            continue
        if signo is not None and (importe is None or (importe > 0) != (signo == "entrada")):
            continue
        if (desde is not None and m["fecha_contable"] < desde) or (
                hasta is not None and m["fecha_contable"] > hasta):
            continue
        if texto is not None and texto not in pliegue(m["contraparte_nombre_doc"]) \
                and texto not in pliegue(m["concepto_doc"]):
            continue
        resto = (abiertos[m["id"]] if abierto
                 else None if importe is None else importe - aplicado.get(m["id"], 0))
        filas.append({
            "id": m["id"], "fecha": m["fecha_contable"], "fecha_valor": m["fecha_valor"],
            "importe_cent": importe, "importe": _euros(importe), "moneda": m["moneda"],
            "importe_crudo": m["importe_crudo"] if importe is None else None,
            "abierto": abierto, "resto_cent": resto, "resto": _euros(resto),
            "propia": m["contraparte_iban"] is not None and m["contraparte_iban"] in ajenas,
            "contraparte": m["contraparte_nombre_doc"], "contraparte_iban": m["contraparte_iban"],
            "concepto": m["concepto_doc"], "referencia": m["referencia_estructurada"],
            "referencia_e2e": m["referencia_e2e"], "cuenta_propia_iban": m["cuenta_propia_iban"],
            "confirmadas": cuentas[m["id"]]["confirmada"],
            "propuestas": cuentas[m["id"]]["propuesta"],
            "dias": (hoy - date.fromisoformat(m["fecha_contable"])).days,
        })

    def suma(entrada: bool) -> dict[str, Any]:
        propias = [r for r in filas if r["importe_cent"] is not None
                   and (r["importe_cent"] > 0) == entrada]
        importe = sum(r["importe_cent"] for r in propias)
        sin_casar_ = sum(r["resto_cent"] for r in propias if r["abierto"])
        return {"movimientos": len(propias), "importe_cent": importe, "importe": _euros(importe),
                "sin_casar_cent": sin_casar_, "sin_casar": _euros(sin_casar_)}

    return {"hoy": hoy.isoformat(),
            "filtros": {"sin_casar": "si" if sin_casar else "no",
                        **{k: v for k, v in datos.items() if k not in ("sin_casar", "limite")}},
            "limite": limite, "total": len(filas), "entradas": suma(True),
            "salidas": suma(False), "lista": filas[:limite]}


# ------------------------------------------------------------ los documentos de una parte
#
# Lo que el archivo de la app ensena en la carpeta de un cliente o un proveedor (paso 16):
# los documentos que el sistema ya enlaza a la parte, sin ninguna tabla nueva. Los
# originales de sus facturas y abonos (factura.documento_id), los justificantes de los
# pagos apuntados a mano (aplicacion_pago.evidencia_documento_id) y las hojas de sus PO y
# de sus modificaciones (orden_compra.documento_id, orden_compra_modificacion.documento_id).
# Una fila por enlace: el mismo documento sale dos veces si lo enlazan dos registros. Los
# contratos y lo que no es de ningun registro no estan (decision 7 de la revision de Aurora).
# El nombre del fichero lo puso quien lo mando: es texto de un tercero.

TIPOS_DOCUMENTO = ("factura_compra", "factura_venta", "abono_compra", "abono_venta",
                   "justificante_pago", "orden_compra", "modificacion_po")


def _tipo_de_factura(sentido: str, tipo: str) -> str:
    compra = sentido == "entrante"
    if tipo == "nota_credito":
        return "abono_compra" if compra else "abono_venta"
    return "factura_compra" if compra else "factura_venta"


def _fila_documento(d: sqlite3.Row, tipo: str, fecha: str | None, numero: str | None,
                    importe: int | None, vinculo: dict[str, Any],
                    estado_pago: str | None = None) -> dict[str, Any]:
    return {"id": d["documento_id"], "tipo": tipo, "fecha": fecha, "numero": numero,
            "importe_cent": importe, "importe": _euros(importe), "estado_pago": estado_pago,
            "nombre": d["nombre_original"], "tipo_mime": d["tipo_mime"], "bytes": d["bytes"],
            "guardado": d["ruta_cas"] is not None, "sha256": d["sha256"],
            "registrado_en": d["registrado_en"], "vinculo": vinculo}


_COLUMNAS_DOCUMENTO = ("d.id AS documento_id, d.nombre_original, d.tipo_mime, d.bytes, "
                       "d.ruta_cas, d.sha256, d.registrado_en")


def _documentos(conn: sqlite3.Connection, tabla: str, parte_id: int | None = None,
                estados: dict[int, str | None] | None = None) -> dict[int, list[dict[str, Any]]]:
    """Los documentos enlazados a cada parte de `tabla` (o solo a `parte_id`), por parte. Las
    facturas son las de la vista de la parte (las de su columna, como `lectura.de`)."""
    _sentido, columna = _PARTES[tabla]
    filtro, parametros = (" = ?", (parte_id,)) if parte_id is not None else (" IS NOT NULL", ())
    estados = estados or {}
    salida: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for d in conn.execute(
            f"SELECT f.{columna} AS parte_id, f.id AS factura_id, f.sentido, f.tipo, f.numero, "
            f"f.fecha_factura, f.total_cent, {_COLUMNAS_DOCUMENTO} FROM factura AS f "
            f"JOIN documento AS d ON d.id = f.documento_id WHERE f.{columna}{filtro}",
            parametros):
        salida[d["parte_id"]].append(_fila_documento(
            d, _tipo_de_factura(d["sentido"], d["tipo"]), d["fecha_factura"], d["numero"],
            d["total_cent"], {"tabla": "factura", "id": d["factura_id"],
                              "factura_id": d["factura_id"]},
            estados.get(d["factura_id"])))
    for d in conn.execute(
            f"SELECT f.{columna} AS parte_id, a.id AS aplicacion_id, a.factura_id, a.fecha_pago, "
            f"a.importe_cent, a.estado, a.fuente, f.numero, {_COLUMNAS_DOCUMENTO} "
            f"FROM aplicacion_pago AS a JOIN factura AS f ON f.id = a.factura_id "
            f"JOIN documento AS d ON d.id = a.evidencia_documento_id WHERE f.{columna}{filtro}",
            parametros):
        salida[d["parte_id"]].append(_fila_documento(
            d, "justificante_pago", d["fecha_pago"], d["numero"], d["importe_cent"],
            {"tabla": "aplicacion_pago", "id": d["aplicacion_id"], "factura_id": d["factura_id"],
             "estado": d["estado"], "fuente": d["fuente"]}))
    for d in conn.execute(
            f"SELECT o.{columna} AS parte_id, o.id AS orden_id, o.numero, o.fecha_emision, "
            f"o.valor_original_cent, {_COLUMNAS_DOCUMENTO} FROM orden_compra AS o "
            f"JOIN documento AS d ON d.id = o.documento_id WHERE o.lado = ? "
            f"AND o.{columna}{filtro}", (tabla, *parametros)):
        salida[d["parte_id"]].append(_fila_documento(
            d, "orden_compra", d["fecha_emision"], d["numero"], d["valor_original_cent"],
            {"tabla": "orden_compra", "id": d["orden_id"], "orden_compra_id": d["orden_id"]}))
    for d in conn.execute(
            f"SELECT o.{columna} AS parte_id, m.id AS modificacion_id, o.id AS orden_id, "
            f"o.numero, m.fecha, m.valor_nuevo_cent, {_COLUMNAS_DOCUMENTO} "
            f"FROM orden_compra_modificacion AS m JOIN orden_compra AS o "
            f"ON o.id = m.orden_compra_id JOIN documento AS d ON d.id = m.documento_id "
            f"WHERE o.lado = ? AND o.{columna}{filtro}", (tabla, *parametros)):
        salida[d["parte_id"]].append(_fila_documento(
            d, "modificacion_po", d["fecha"], d["numero"], d["valor_nuevo_cent"],
            {"tabla": "orden_compra_modificacion", "id": d["modificacion_id"],
             "orden_compra_id": d["orden_id"]}))
    for parte, filas in salida.items():
        # Lo mas reciente primero (a igualdad, el documento mas nuevo); sin fecha, al final.
        fechadas = sorted((r for r in filas if r["fecha"]), key=lambda r: (r["fecha"], r["id"]),
                          reverse=True)
        salida[parte] = fechadas + sorted((r for r in filas if not r["fecha"]),
                                          key=lambda r: r["id"], reverse=True)
    return salida


def documentos_de_parte(conn: sqlite3.Connection, tabla: str, parte_id: int) -> dict[str, Any]:
    """La carpeta de un cliente o un proveedor en el archivo: cada documento que el sistema
    ya le enlaza, el mas reciente primero, con su tipo, fecha, numero, tamano y el registro
    al que va unido. Se descarga (y queda en la auditoria) con GET
    /api/v2/documentos/N/original. LookupError si la parte no existe."""
    fila = _parte(conn, tabla, parte_id)
    lectura = _leer(conn)
    estados = {f.id: f.estado(lectura.hoy) for f in lectura.facturas}
    documentos = _documentos(conn, tabla, parte_id, estados).get(parte_id, [])
    return {"parte": {"tabla": tabla, "id": parte_id, "nombre": fila["nombre"]},
            "total": len(documentos), "documentos": documentos}


# Lo que enlaza un documento a un registro de la app: lo mismo que llena la carpeta de una
# parte (_documentos). Los ficheros de una importacion (importacion.documento_id: los
# maestros con sus IBAN, la planificacion, los extractos del banco) no estan aqui.
_DOCUMENTO_ENLAZADO = (
    "EXISTS (SELECT 1 FROM factura WHERE documento_id = d.id) "
    "OR EXISTS (SELECT 1 FROM aplicacion_pago WHERE evidencia_documento_id = d.id) "
    "OR EXISTS (SELECT 1 FROM orden_compra WHERE documento_id = d.id) "
    "OR EXISTS (SELECT 1 FROM orden_compra_modificacion WHERE documento_id = d.id)")


def documento_de_descarga(conn: sqlite3.Connection, documento_id: int) -> sqlite3.Row:
    """El documento que se descarga con /api/v2/documentos/N/original. LookupError si no
    existe o si ningun registro lo enlaza.

    Por que solo los enlazados: la ruta es la de la carpeta de una parte (lo que el sistema
    ya enlaza: el original de una factura o un abono, el justificante de un pago, la hoja de
    una PO o de su modificacion). Los ids son correlativos; sin este limite, cualquiera que
    pueda ver facturas (tambien el rol consulta) contaria hacia arriba y bajaria los ficheros
    de las importaciones: el maestro de proveedores con cada IBAN y su telefono de
    verificacion, la lista del personal, la planificacion y cada extracto del banco. Un
    extracto solo se baja si alguien lo dio como justificante de un pago. Lo que no se
    enlaza contesta como lo que no existe (404, sin evento): no se dice si el id existe."""
    fila = conn.execute("SELECT d.id, d.nombre_original, d.tipo_mime, d.sha256 "
                        f"FROM documento AS d WHERE d.id = ? AND ({_DOCUMENTO_ENLAZADO})",
                        (documento_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay documento {documento_id} en ninguna carpeta")
    return fila


# ------------------------------------------------------------ la historia de una factura (§12)

def _valor_texto(tabla: str, campo: str, crudo: str | None) -> tuple[Any, str | None]:
    """Un valor de cambio_campo (JSON) y su texto como lo lee la empresa."""
    if crudo is None:
        return None, None
    valor = json.loads(crudo)
    definicion = campos.REGISTRO.get(tabla, {}).get(campo)
    if definicion is None:
        return valor, None if valor is None else str(valor)
    try:
        return valor, texto_de(definicion, valor)
    except (TypeError, ValueError, ArithmeticError):
        return valor, str(valor)


def historial_factura(conn: sqlite3.Connection, factura_id: int) -> dict[str, Any]:
    """Todo lo que ha pasado con una factura (§12), del registro encadenado de auditoria.

    - el original: el documento guardado (su hash, si esta en el almacen o
      falta) y cada extraccion que se hizo de el, con la vigente marcada;
    - los eventos que la tocan, en orden, cada uno con quien lo pidio, quien
      lo hizo, cuando, el motivo y sus cambios campo a campo (valor anterior y
      nuevo, fuente anterior y nueva y motivo): el historial de cambios;
    - las revisiones (quien, cuando, con que resultado y si siguen valiendo);
    - cada hallazgo que la toco, abierto o ya cerrado, con su historia
      (detectado, cambio de evidencia, cerrado, aceptado, reabierto...) y sus
      anulaciones: el historial de resolucion de avisos;
    - sus excepciones, tambien las resueltas, y sus notas;
    - sus relaciones, en los dos sentidos: la factura que abona, sustituye o
      corrige y la que la abona, la sustituye o la corrige. Los eventos de una
      relacion llevan la factura de origen; los de las que tienen esta de
      destino (que la abonaron, por ejemplo) tambien salen en su historia.
    """
    factura = conn.execute("SELECT * FROM factura WHERE id = ?", (factura_id,)).fetchone()
    if factura is None:
        raise LookupError(f"no hay factura {factura_id}")
    nombres = _nombres(conn)
    documento = None
    if factura["documento_id"] is not None:
        d = conn.execute("SELECT * FROM documento WHERE id = ?",
                         (factura["documento_id"],)).fetchone()
        documento = {"id": d["id"], "sha256": d["sha256"], "nombre": d["nombre_original"],
                     "conservado": d["ruta_cas"] is not None, "origen": d["origen"],
                     "via": d["ruta_declarada"], "recibido_en": d["recibido_en"],
                     "registrado_en": d["registrado_en"]}
    extracciones = [{"id": e["id"], "modelo": e["modelo"], "prompt": e["prompt_version"],
                     "esquema": e["schema_version"], "via": e["via"],
                     "extraido_en": e["extraido_en"],
                     "vigente": e["id"] == factura["extraccion_vigente_id"]}
                    for e in conn.execute("SELECT * FROM extraccion WHERE documento_id = ? "
                                          "ORDER BY id", (factura["documento_id"],))]
    # Una relacion se escribe con la factura de origen (el abono, la que sustituye):
    # los eventos de las que la tienen de destino tambien son historia suya.
    relaciones_ = [dict(r) for r in conn.execute(
        "SELECT r.*, o.numero AS origen_numero, d.numero AS destino_numero "
        "FROM factura_relacion AS r JOIN factura AS o ON o.id = r.origen_id "
        "JOIN factura AS d ON d.id = r.destino_id "
        "WHERE r.origen_id = ? OR r.destino_id = ? ORDER BY r.id", (factura_id, factura_id))]
    ids_relacion = [r["id"] for r in relaciones_]
    de_relaciones = (f"OR (c.tabla = 'factura_relacion' AND c.fila_id IN "
                     f"({_marcas(len(ids_relacion))}))" if ids_relacion else "")
    eventos: dict[int, dict[str, Any]] = {}
    for e in conn.execute(
            "SELECT * FROM evento WHERE factura_id = ? UNION SELECT e.* FROM evento AS e "
            f"JOIN cambio_campo AS c ON c.evento_id = e.id WHERE c.factura_id = ? {de_relaciones} "
            "ORDER BY id", (factura_id, factura_id, *ids_relacion)):
        eventos[e["id"]] = {"id": e["id"], "en": e["en"], "tipo": e["tipo"],
                            "resultado": e["resultado"], "usuario": nombres.get(e["usuario_id"]),
                            "actor": nombres.get(e["actor"]), "persona": e["usuario_id"] is not None,
                            "motivo": e["motivo"], "cambios": []}
    for c in conn.execute(f"SELECT * FROM cambio_campo AS c WHERE c.factura_id = ? "
                          f"{de_relaciones} ORDER BY c.id", (factura_id, *ids_relacion)):
        if c["evento_id"] not in eventos:
            continue
        anterior, anterior_texto = _valor_texto(c["tabla"], c["campo"], c["valor_anterior"])
        nuevo, nuevo_texto = _valor_texto(c["tabla"], c["campo"], c["valor_nuevo"])
        eventos[c["evento_id"]]["cambios"].append({
            "tabla": c["tabla"], "fila_id": c["fila_id"], "campo": c["campo"], "rev": c["rev"],
            "anterior": anterior, "anterior_texto": anterior_texto,
            "nuevo": nuevo, "nuevo_texto": nuevo_texto,
            "fuente_anterior": c["fuente_anterior"], "fuente_nueva": c["fuente_nueva"],
            "fuente_texto": ETIQUETA_FUENTE.get(c["fuente_nueva"]), "motivo": c["motivo"]})
    huella = revision.huella_contenido(conn, factura_id)
    revisiones = [{"id": r["id"], "resultado": r["resultado"],
                   "usuario": nombres.get(r["usuario_id"]), "en": r["en"], "nota": r["nota"],
                   "autorrevisada": bool(r["autorrevisada"]),
                   "vigente": r["resultado"] == "revisada" and r["huella_contenido"] == huella}
                  for r in conn.execute("SELECT * FROM revision WHERE factura_id = ? ORDER BY id",
                                        (factura_id,))]
    hallazgos_ = []
    for h in conn.execute(
            "SELECT * FROM hallazgo WHERE factura_id = ? OR id IN (SELECT hallazgo_id FROM "
            "hallazgo_objetivo WHERE tabla = 'factura' AND fila_id = ?) ORDER BY id",
            (factura_id, factura_id)):
        hallazgos_.append({
            "id": h["id"], "regla": h["regla"], "titulo": h["titulo"], "estado": h["estado"],
            "severidad": h["severidad"], "detalle": h["detalle"],
            "resultado": FALLO, "valores": valores_de(h),
            "primera_vez_en": h["primera_vez_en"],
            "eventos": [{"tipo": e["tipo"], "estado": e["estado"], "en": e["en"],
                         "usuario": nombres.get(e["usuario_id"]), "nota": e["nota"],
                         "causa_evento_id": e["causa_evento_id"]}
                        for e in conn.execute("SELECT * FROM hallazgo_evento WHERE hallazgo_id = ? "
                                              "ORDER BY id", (h["id"],))],
            "anulaciones": [{"motivo": a["motivo"], "usuario": nombres.get(a["usuario_id"]),
                             "en": a["en"], "vigente_hasta": a["vigente_hasta"],
                             "segunda_firma": nombres.get(a["segunda_firma_usuario_id"]),
                             "autoaprobada": bool(a["autoaprobada"])}
                            for a in conn.execute("SELECT * FROM anulacion WHERE hallazgo_id = ? "
                                                  "ORDER BY id", (h["id"],))],
        })
    excepciones_ = [_excepcion(e, nombres) for e in conn.execute(
        "SELECT * FROM excepcion WHERE (tabla = 'factura' AND fila_id = ?) OR factura_id = ? "
        "ORDER BY id", (factura_id, factura_id))]
    notas = [{"id": n["id"], "texto": n["texto"], "usuario": nombres.get(n["usuario_id"]),
              "en": n["en"]}
             for n in conn.execute("SELECT * FROM nota WHERE tabla = 'factura' AND fila_id = ? "
                                   "ORDER BY id", (factura_id,))]
    relaciones_salida = [{
        "id": r["id"], "tipo": r["tipo"], "estado": r["estado"], "fuente": r["fuente"],
        "papel": "origen" if r["origen_id"] == factura_id else "destino",
        "otra_id": r["destino_id"] if r["origen_id"] == factura_id else r["origen_id"],
        "otra_numero": (r["destino_numero"] if r["origen_id"] == factura_id
                        else r["origen_numero"]),
        "importe_cent": r["importe_cent"], "importe": _euros(r["importe_cent"]),
        "retirada": r["retirada_en"] is not None} for r in relaciones_]
    return {"factura_id": factura_id, "numero": factura["numero"], "documento": documento,
            "extracciones": extracciones, "relaciones": relaciones_salida,
            "eventos": list(eventos.values()),
            "revisiones": revisiones, "hallazgos": hallazgos_, "excepciones": excepciones_,
            "notas": notas}


# ------------------------------------------------------------ el contrato v2
#
# Lo que devuelve `bms-agent export --v2` y GET /api/v2/exportar: todo lo que
# un sitio propio necesita para pintar el panel, la busqueda y las vistas, en
# una sola lectura. Esta escrito, clave a clave, en docs/integracion-web.md
# ("El contrato v2"), y un test comprueba que lo que sale es lo que dice.
# Importes en enteros (centimos, milesimas de hora, puntos basicos) con su
# texto al lado; nunca un numero con decimales. No lleva ningun IBAN: los da
# la vista de un proveedor (/api/v2/proveedores/N), con token y solo a la
# consola (serve.py los enmascara para cualquier otro origen).

CLAVES_V2 = {
    "": ("contrato", "generado_en", "hoy", "estado_del", "al_dia", "panel", "facturas",
         "proveedores", "clientes", "objetos", "ordenes_compra", "btw", "flujo_caja",
         "excepciones", "fuentes", "filtros"),
    "panel": ("contrato", "hoy", "estado_del", "al_dia", "fuentes_caducadas", "dinero_entra",
              "dinero_sale", "caja", "facturacion", "ordenes_compra", "btw", "atencion"),
    "panel.dinero_entra": ("facturas", "vencidas", "pendiente_cent", "vencido_cent",
                           "semana_cent", "mes_cent", "proximos_30_cent", "sin_fecha_cent"),
    "panel.dinero_sale": ("facturas", "vencidas", "pendiente_cent", "vencido_cent",
                          "semana_cent", "mes_cent", "proximos_30_cent", "sin_fecha_cent"),
    "panel.caja": ("ventanas", "fechas", "cobrado_mes_cent", "pagado_mes_cent", "estimado"),
    "panel.ordenes_compra": ("activas", "cliente", "proveedor", "cerca_del_limite",
                             "cerca_de_caducar", "caducadas", "agotamiento_previsto"),
    "panel.ordenes_compra.cliente": ("activas", "valor_cent", "consumido_cent", "restante_cent"),
    "panel.ordenes_compra.proveedor": ("activas", "valor_cent", "consumido_cent",
                                       "restante_cent"),
    "panel.btw": ("trimestre", "estado", "ingresos_cent", "iva_repercutido_cent",
                  "iva_deducible_cent", "saldo_cent", "limite_presentacion", "limite_pago",
                  "proximo_plazo", "por_presentar"),
    "panel.atencion": ("compras_vencidas", "ventas_vencidas", "categorias", "hallazgos",
                       "aceptados", "excepciones", "bloqueadas", "urgentes", "atencion"),
    "facturas[]": ("id", "numero", "sentido", "tipo", "contraparte", "proveedor_id",
                   "cliente_id", "fecha_factura", "vencimiento", "periodo_desde",
                   "periodo_hasta", "base_cent", "total_cent", "pendiente_cent", "estado_pago",
                   "estado_revision", "calidad", "nivel", "puntos", "motivos", "editada",
                   "suplementada", "corregida", "sin_resolver", "cuenta", "objetos",
                   "etiqueta", "razones", "fuente_pago"),
    "proveedores[]": ("id", "nombre", "facturas", "pendiente_cent", "vencido_cent", "nivel",
                      "razones", "deuda_cent", "abonos_sin_enlazar_cent"),
    "clientes[]": ("id", "nombre", "facturas", "pendiente_cent", "vencido_cent", "nivel",
                   "razones", "deuda_cent", "abonos_sin_enlazar_cent"),
    "objetos": ("objetos", "sin_objeto", "totales"),
    "ordenes_compra[]": ("id", "numero", "lado", "parte", "valor_cent", "consumido_cent",
                         "restante_cent", "fecha_fin", "cerrada", "nivel", "razones"),
    "btw": ("hoy", "actual", "por_presentar", "anteriores", "ano_hasta_hoy"),
    "flujo_caja": ("hoy", "ventanas", "esperado", "real", "estimado"),
}


# Un IBAN dentro de un texto: seguido (NL75INGB0002445689) o en grupos de cuatro
# (NL75 INGB 0002 4456 89). Los mensajes de las reglas F2, F3, F5, F6 y F10 lo
# escriben entero, y de ahi llega a los motivos de la prioridad y a los avisos.
_IBAN_EN_TEXTO = re.compile(
    r"\b[A-Z]{2}\d{2}(?:[A-Z0-9]{11,30}|(?: [A-Z0-9]{4}){2,7}(?: [A-Z0-9]{1,3})?)\b")
# Y como lo escribe una persona o lo trae un PDF en sus notas: en minusculas, con
# puntos, guiones o espacios en cualquier sitio (nl75-ingb-0002-4456-89,
# NL 75 INGB 0002 445689). Esta forma suelta casa tambien con cosas que no son
# un IBAN, asi que solo se enmascara lo que pasa el digito de control.
_SEPARADORES = re.compile(r"[ .\-]")
_IBAN_SUELTO = re.compile(r"(?i)\b[a-z]{2}[ .\-]?\d{2}(?:[ .\-]?[a-z0-9]){11,30}")
# Las dos cifras seguidas que lleva todo IBAN, en las dos formas: una clave sin ellas
# (casi todas: "pendiente_cent") no se mira.
_DOS_CIFRAS = re.compile(r"\d\d")


def enmascarar_iban(iban: str) -> str:
    """'NL75INGB0002445689' es 'NL..5689': el pais y las cuatro ultimas cifras, lo que basta
    para reconocer una cuenta al telefono y no basta para pagarle."""
    compacto = _SEPARADORES.sub("", "".join(iban.split())).upper()
    return f"{compacto[:2]}..{compacto[-4:]}"


def ibanes_en(texto: str) -> list[str]:
    """Los IBAN que lleva un texto, donde sea que esten y como sea que esten escritos."""
    sueltos = [iban for m in _IBAN_SUELTO.finditer(texto)
               if (iban := _iban_al_principio(m.group(0))[1]) is not None]
    return sueltos + [m.group(0) for m in _IBAN_EN_TEXTO.finditer(texto)]


def _iban_al_principio(texto: str) -> tuple[int, str | None]:
    """El IBAN valido mas largo con que empieza un trozo de forma suelta: hasta donde llega y
    el IBAN compacto (None si no hay ninguno). La forma suelta se come lo que venga detras
    ("NL75...89 en 2026"): se prueba de lo mas largo a lo mas corto hasta dar con uno que
    pase el modulo 97."""
    from .reglas.bancaria import validar_iban

    for fin in range(len(texto), 0, -1):
        if not texto[fin - 1].isalnum():
            continue
        compacto = _SEPARADORES.sub("", texto[:fin]).upper()
        if len(compacto) < 15:
            break
        if validar_iban(compacto):
            return fin, compacto
    return 0, None


def _suelto(encontrado: re.Match[str]) -> str:
    """Un trozo de forma suelta con su IBAN enmascarado, y lo que sigue tal cual."""
    texto = encontrado.group(0)
    fin, compacto = _iban_al_principio(texto)
    return texto if compacto is None else enmascarar_iban(compacto) + texto[fin:]


def sin_ibanes(valor: Any) -> Any:
    """Una copia de `valor` (dict, lista o texto) con cada IBAN de cada texto enmascarado.

    Es la ultima pasada de lo que sale hacia un sitio propio (el contrato v2 y
    las lecturas de /api/v2 desde otro origen): los IBAN no solo estan en el
    registro de cuentas, tambien en los textos de los avisos y en los motivos.
    Primero lo que tiene forma suelta y pasa el digito de control (en
    minusculas, con puntos o guiones, agrupado como sea); despues lo que tiene
    la forma de siempre aunque no lo pase (un IBAN mal copiado tambien es de
    alguien).

    Desde el paso 15 cada hallazgo lleva sus `valores`, que en F2-F10 y K4 son
    IBAN enteros (o listas de ellos): se enmascaran como cualquier texto, y
    tambien las claves de un objeto, por si una regla llegara a usar un IBAN de
    clave.
    """
    if isinstance(valor, str):
        valor = _IBAN_SUELTO.sub(_suelto, valor)
        return _IBAN_EN_TEXTO.sub(lambda m: enmascarar_iban(m.group(0)), valor)
    if isinstance(valor, dict):
        return {sin_ibanes(k) if isinstance(k, str) and _DOS_CIFRAS.search(k) else k:
                sin_ibanes(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [sin_ibanes(v) for v in valor]
    return valor


def exportar_v2(conn: sqlite3.Connection) -> dict[str, Any]:
    """El contrato v2 entero, con el `hoy` del reloj del almacen (docs/integracion-web.md).

    Sin ningun IBAN: los que llevan los textos (motivos, avisos) salen
    enmascarados (`sin_ibanes`), y `comprobar_v2` lo mira.
    """
    from . import btw
    from .almacen import reloj_de
    from .reloj import marca

    reloj = reloj_de(conn)
    hoy = reloj.hoy()
    del_dia = estado_del(conn)
    return sin_ibanes({
        "contrato": CONTRATO_V2, "generado_en": marca(reloj.ahora()), "hoy": hoy.isoformat(),
        "estado_del": del_dia, "al_dia": del_dia == hoy.isoformat(),
        "panel": panel(conn),
        "facturas": _filas_listado(conn),
        "proveedores": proveedores(conn), "clientes": clientes(conn),
        "objetos": objetos_resumen(conn), "ordenes_compra": ordenes_compra(conn),
        "btw": btw.resumen(conn, hoy), "flujo_caja": flujo_caja.flujo(conn, hoy),
        "excepciones": excepciones_abiertas(conn), "fuentes": fuentes(conn),
        "filtros": filtros(),
    })


def comprobar_v2(datos: dict[str, Any]) -> list[str]:
    """Lo que no cumple el contrato v2 de un export: claves que faltan, un numero con decimales,
    un IBAN en cualquier texto (entero o dentro de una frase) o una version que no es la de
    este codigo. Vacio si lo cumple."""
    errores = []
    if datos.get("contrato") != CONTRATO_V2:
        errores.append(f"contrato {datos.get('contrato')!r}, se esperaba {CONTRATO_V2!r}")
    for camino, claves in CLAVES_V2.items():
        if camino.endswith("[]"):
            lista = datos.get(camino[:-2])
            if not isinstance(lista, list):
                errores.append(f"{camino[:-2]}: no es una lista")
                continue
            for i, fila in enumerate(lista):
                faltan = [c for c in claves if c not in fila]
                if faltan:
                    errores.append(f"{camino[:-2]}[{i}]: faltan {', '.join(faltan)}")
            continue
        bloque: Any = datos
        for parte in [p for p in camino.split(".") if p]:
            bloque = bloque.get(parte) if isinstance(bloque, dict) else None
        if not isinstance(bloque, dict):
            errores.append(f"{camino or 'raiz'}: no es un objeto")
            continue
        faltan = [c for c in claves if c not in bloque]
        if faltan:
            errores.append(f"{camino or 'raiz'}: faltan {', '.join(faltan)}")

    def sin_decimales(valor: Any, camino: str) -> None:
        if isinstance(valor, float):
            errores.append(f"{camino}: un numero con decimales ({valor})")
        elif isinstance(valor, str) and ibanes_en(valor):
            errores.append(f"{camino}: lleva un IBAN ({enmascarar_iban(ibanes_en(valor)[0])})")
        elif isinstance(valor, dict):
            for k, v in valor.items():
                if isinstance(k, str) and ibanes_en(k):
                    errores.append(f"{camino}: una clave lleva un IBAN "
                                   f"({enmascarar_iban(ibanes_en(k)[0])})")
                sin_decimales(v, f"{camino}.{k}")
        elif isinstance(valor, list):
            for i, v in enumerate(valor):
                sin_decimales(v, f"{camino}[{i}]")

    sin_decimales(datos, "")
    return errores


# ------------------------------------------------------------ la app local (paso 15)
#
# Dos lecturas que solo pinta la app de la oficina: lo que ha costado leer los PDF (la
# pantalla "Facturen lezen", que no lanza nada) y la identidad de la empresa
# (Instellingen). Las dos son de solo lectura y no llaman a nadie.

_MICRO = Decimal(1_000_000)
MAX_PASADAS = 10


def _micro(coste: Decimal | None) -> int | None:
    """Dolares (con seis decimales, pricing.estimate_cost) en millonesimas enteras: el
    contrato no lleva numeros con decimales."""
    return None if coste is None else int(coste * _MICRO)


def lectura_pdf(conn: sqlite3.Connection) -> dict[str, Any]:
    """Lo que ha costado leer los PDF y lo que costaria leer uno mas, de lo que guarda el
    almacen (cada extraccion con su consumo, extraccion.uso_json): lo mismo que dice
    `bms-agent coste`, sin contar nada con la API (esto no tiene red).

    La consola no lee PDF (no tiene internet): los lee el lector, con el acceso directo
    "Leer facturas", que ensena lo que va a costar antes de pagar. Aqui solo se mira.

    Paso 17 (contrato 2.5): ademas, la lectura pedida desde la app (lectura.para_la_app):
    `solicitud`, `pasada_en_curso` y `ultima_pasada`.
    """
    from statistics import median

    from . import config, coste, lectura
    from .pricing import estimate_cost

    documentos = coste.documentos_del_almacen(conn)
    costes = [d.coste for d in documentos if d.coste is not None]
    completo = bool(documentos) and len(costes) == len(documentos)
    total = sum(costes, Decimal(0)) if completo else None
    modelo = config.model_id()
    estimacion = None
    entradas = [d.entrada for d in documentos if d.entrada]
    if entradas:
        salida = coste.estimar_salida(documentos, modelo=modelo, esquema=config.SCHEMA_VERSION,
                                      esfuerzo=config.effort())
        entrada = int(median(entradas))
        bajo, alto = (estimate_cost(modelo, entrada, salida.bajo),
                      estimate_cost(modelo, entrada, salida.alto))
        if bajo is not None and alto is not None:
            estimacion = {"por_documento_bajo_usd_micro": _micro(bajo),
                          "por_documento_alto_usd_micro": _micro(alto),
                          "medida": salida.medida}
    pasadas = coste.agrupar_en_pasadas(documentos)[:MAX_PASADAS]
    leidos = conn.execute("SELECT count(DISTINCT documento_id) FROM extraccion").fetchone()[0]
    return {
        "modelo": modelo, "extracciones": len(documentos), "documentos": leidos,
        "coste_usd_micro": _micro(total),
        "por_documento_usd_micro": _micro((total / len(documentos)).quantize(Decimal("0.000001")))
        if total is not None else None,
        "ultima": max((d.cuando.isoformat() for d in documentos if d.cuando), default=None),
        "pasadas": [{"desde": p.desde.isoformat() if p.desde else None,
                     "hasta": p.hasta.isoformat() if p.hasta else None,
                     "documentos": len(p.documentos), "coste_usd_micro": _micro(p.coste)}
                    for p in pasadas],
        "estimacion": estimacion,
        **lectura.para_la_app(conn),
    }


def empresa(conn: sqlite3.Connection) -> dict[str, Any]:
    """La identidad de BM Support BV tal como la usan las reglas (la politica vigente de
    empresa.yaml): nombre, otros nombres, btw-id, KvK y sus cuentas propias. Se cambia con
    `bms-agent empresa fijar` (empresa.bat), no desde la app."""
    from . import politica

    e = politica.empresa(conn)
    return {"nombre": e.nombre, "otros_nombres": list(e.otros_nombres), "btw_id": e.btw_id,
            "kvk": e.kvk, "cuentas_propias": list(e.cuentas_propias),
            "completa": bool(e.btw_id and e.kvk and e.cuentas_propias)}
