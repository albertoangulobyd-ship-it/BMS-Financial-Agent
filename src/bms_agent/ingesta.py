"""La unica via de entrada de un documento, para la CLI y para el servidor.

Un PDF entra asi, y solo asi:

1. se guarda en el almacen de documentos (por su hash, sin pisar nada);
2. se extrae segun la politica de cache (lo ya leido no se vuelve a pagar);
3. la extraccion vigente se convierte en filas tipadas (factura, lineas,
   imputaciones, referencias, desglose de IVA) a traves de campos.py, con la
   procedencia de cada campo y su literal impreso.

La direccion (compra o venta) la decide la via de entrada (documento.
ruta_declarada), nunca el modelo: un PDF que llega por la carpeta de
facturas recibidas es una factura entrante diga lo que diga.

Los literales se leen aqui, con parsing.py, y nunca se redondea: un importe
que no se puede leer, o que no cabe exacto en su escala, queda vacio y
dudoso con su literal, para que una persona lo mire. Una factura que no
esta en euros (X1) deja todos sus importes vacios: no entra en ninguna suma.

Una extraccion nueva del mismo documento (un --force, otra version) pasa a
vigente como hasta ahora (la mas reciente, la regla de load_records) y se
aplica como fuente automatica: lo que una persona corrigio no se pisa, solo
queda apuntado el nuevo valor automatico. La puerta de activacion del paso
6 sustituira esta regla.

Nada de aqui llama a la API: tipar es determinista y se puede repetir.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import campos, compat
from .almacen import transaccion, usuario_sistema
from .almacen.extracciones import en_orden_de_out
from .almacen.unidades import json_canonico, sha256_texto
from .campos import Automatico, Leido
from .checks import check_currency
from .dominio import FUENTES_AUTOMATICAS, Fuente, Sentido, TipoFactura, TratamientoIva
from .parsing import (
    ParseError,
    detectar_moneda,
    parse_amount,
    parse_iso_date,
    parse_percentage,
)
from .reloj import ZONA_EMPRESA

# documento.ruta_declarada -> sentido de la factura. Lo que llega por otra
# via (maestro, banco, planning) no es una factura que tipar aqui.
SENTIDO_DE_RUTA = {"entrante": Sentido.ENTRANTE.value, "saliente": Sentido.SALIENTE.value}

REGIMEN = {
    "standard": TratamientoIva.ESTANDAR.value,
    "reverse_charged": TratamientoIva.AUTOLIQUIDACION.value,
    "kor_exempt": TratamientoIva.KOR.value,
    "unknown": TratamientoIva.DESCONOCIDO.value,
}
REGIMEN_INVERSO = {v: k for k, v in REGIMEN.items()}

# Como se lee cada literal. Los de dinero dependen de la moneda de la factura.
TEXTO = "texto"
IMPORTE = "importe"
CANTIDAD = "cantidad"
TARIFA = "tarifa"
PORCENTAJE = "porcentaje"
FECHA = "fecha"
ENTERO = "entero"
BOOLEANO = "booleano"
REGIMEN_IVA = "regimen"
DINERO = frozenset({IMPORTE, TARIFA})

# Clave de la extraccion -> (columna de factura, como se lee). Las de v1 y
# las que anade v2; las de v2 llegan vacias de una extraccion v1 (compat).
CABECERA: tuple[tuple[str, str, str], ...] = (
    ("supplier_name", "emisor_nombre_doc", TEXTO),
    ("supplier_address", "emisor_direccion_doc", TEXTO),
    ("kvk_number", "emisor_kvk_doc", TEXTO),
    ("vat_number", "emisor_btw_doc", TEXTO),
    ("invoice_number", "numero", TEXTO),
    ("invoice_date", "fecha_factura", FECHA),
    ("service_period_start", "periodo_inicio", FECHA),
    ("service_period_end", "periodo_fin", FECHA),
    ("subtotal_excl_vat_raw", "base_cent", IMPORTE),
    ("vat_rate_raw", "tipo_iva_pb", PORCENTAJE),
    ("vat_amount_raw", "iva_cent", IMPORTE),
    ("total_incl_vat_raw", "total_cent", IMPORTE),
    ("vat_regime", "tratamiento_iva", REGIMEN_IVA),
    ("kor_mentioned", "kor_mencionada", BOOLEANO),
    ("reverse_charge_mentioned", "autoliquidacion_mencionada", BOOLEANO),
    ("iban", "iban_doc", TEXTO),
    ("payment_reference", "referencia_pago", TEXTO),
    ("due_date", "fecha_vencimiento", FECHA),
    ("document_notes", "notas_doc", TEXTO),
    ("recipient_name", "receptor_nombre_doc", TEXTO),
    ("recipient_vat_number", "receptor_btw_doc", TEXTO),
    ("payment_terms_raw", "condiciones_pago_doc", TEXTO),
)
# El contacto impreso es el del otro lado: el del emisor en una compra, el
# "t.a.v." del receptor en una venta.
CONTACTO = {Sentido.ENTRANTE.value: "supplier_contact_person",
            Sentido.SALIENTE.value: "recipient_contact_person"}

LINEA: tuple[tuple[str, str, str], ...] = (
    ("description", "descripcion_doc", TEXTO),
    ("quantity_raw", "cantidad_mil", CANTIDAD),
    ("unit", "unidad_doc", TEXTO),
    ("unit_rate_raw", "tarifa_e4", TARIFA),
    ("line_total_raw", "importe_cent", IMPORTE),
    ("location", "objeto_doc", TEXTO),
    ("week_number", "semana_doc", ENTERO),
    ("period_start", "fecha_inicio", FECHA),
    ("period_end", "fecha_fin", FECHA),
    ("employee_name", "recurso_doc", TEXTO),
    ("work_date", "fecha_trabajo", FECHA),
    ("rate_type_raw", "tipo_turno_doc", TEXTO),
    ("vat_rate_raw", "tipo_iva_pb", PORCENTAJE),
)

IVA_V2: tuple[tuple[str, str, str], ...] = (
    ("rate_raw", "tipo_iva_pb", PORCENTAJE),
    ("base_raw", "base_cent", IMPORTE),
    ("vat_raw", "cuota_cent", IMPORTE),
)


# ------------------------------------------------------------- literales

def leer_literal(lector: str, crudo: Any, *, en_euros: bool = True, dudoso: bool = False) -> Leido:
    """Un literal de la extraccion como valor tipado, con el literal al lado.

    Lo que no se puede leer sin adivinar queda vacio y dudoso. El dinero de
    una factura que no esta en euros queda vacio (no dudoso: se leyo bien,
    pero no son euros).
    """
    if crudo is None:
        return Leido(None, crudo=None, dudoso=dudoso)
    try:
        if lector == TEXTO:
            if not isinstance(crudo, str):
                raise ParseError(f"se esperaba texto: {crudo!r}")
            return Leido(crudo, crudo=crudo, dudoso=dudoso)
        if lector in DINERO and not en_euros:
            return Leido(None, crudo=crudo, dudoso=dudoso)
        if lector in (IMPORTE, TARIFA, CANTIDAD):
            return Leido(parse_amount(str(crudo)), crudo=crudo, dudoso=dudoso)
        if lector == PORCENTAJE:
            return Leido(parse_percentage(str(crudo)), crudo=crudo, dudoso=dudoso)
        if lector == FECHA:
            return Leido(parse_iso_date(str(crudo)), crudo=crudo, dudoso=dudoso)
        if lector == ENTERO:
            if isinstance(crudo, bool):
                raise ParseError(f"no es un numero: {crudo!r}")
            if isinstance(crudo, int):
                return Leido(crudo, crudo=crudo, dudoso=dudoso)
            if isinstance(crudo, str) and crudo.strip().isdigit():
                return Leido(int(crudo.strip()), crudo=crudo, dudoso=dudoso)
            raise ParseError(f"no es un numero entero: {crudo!r}")
        if lector == BOOLEANO:
            if isinstance(crudo, bool):
                return Leido(crudo, crudo=crudo, dudoso=dudoso)
            raise ParseError(f"no es verdadero ni falso: {crudo!r}")
        if lector == REGIMEN_IVA:
            if crudo in REGIMEN:
                return Leido(REGIMEN[crudo], crudo=crudo, dudoso=dudoso)
            raise ParseError(f"regimen desconocido: {crudo!r}")
    except ParseError:
        return Leido(None, crudo=crudo, dudoso=True)
    raise AssertionError(f"lector desconocido {lector}")


def _dudosos(extraccion: dict[str, Any]) -> tuple[set[str], dict[int, set[str]], set[str]]:
    """low_confidence_fields repartido en cabecera, lineas concretas y lineas sin indice.

    v1 da nombres de campo ("vat_number"); v2 rutas ("lines[3].location").
    Un nombre de campo de linea sin indice vale para todas las lineas: no se
    sabe cual, y dudar de mas cuesta una mirada.
    """
    cabecera: set[str] = set()
    por_linea: dict[int, set[str]] = {}
    todas: set[str] = set()
    claves_linea = {c for c, _col, _l in LINEA}
    for ruta in extraccion.get("low_confidence_fields") or []:
        if not isinstance(ruta, str):
            continue
        if ruta.startswith("lines[") and "]." in ruta:
            indice, _, clave = ruta[len("lines["):].partition("].")
            if indice.isdigit():
                por_linea.setdefault(int(indice), set()).add(clave)
            continue
        if ruta in claves_linea:
            todas.add(ruta)
        cabecera.add(ruta)
    return cabecera, por_linea, todas


def en_euros(leida: compat.ExtraccionLeida) -> tuple[bool, str | None]:
    """Si la factura se puede sumar en euros, y la moneda que no lo es.

    Con v2 manda currency_raw si lo trae; si no, y siempre en v1, se mira el
    literal de cada importe (checks.check_currency, la regla X1).
    """
    moneda = leida.datos.get("currency_raw")
    if isinstance(moneda, str) and moneda.strip():
        codigo = detectar_moneda(moneda) or moneda.strip().upper()
        if codigo not in ("EUR", "EURO"):
            return False, codigo
    resultado = check_currency(leida.datos)
    if not resultado.failed:
        return True, None
    otras = sorted({m for m in (detectar_moneda(v) for v in _literales(leida.datos))
                    if m not in (None, "EUR")})
    return False, ", ".join(otras) or None


def _literales(datos: dict[str, Any]) -> list[str]:
    valores = [datos.get(c) for c in
               ("subtotal_excl_vat_raw", "vat_amount_raw", "total_incl_vat_raw")]
    for linea in datos.get("lines") or []:
        if isinstance(linea, dict):
            valores += [linea.get("unit_rate_raw"), linea.get("line_total_raw")]
    return [str(v) for v in valores if v not in (None, "")]


# ------------------------------------------------------------- la vigente

def vigentes_por_documento(conn: sqlite3.Connection) -> dict[int, int]:
    """La extraccion vigente de cada documento: documento_id -> extraccion_id.

    Es la regla de load_records (la mas reciente por extracted_at; en
    empate, la que va despues en out/), la misma que registros_legado: asi
    lo que se tipa es lo que veia el panel.
    """
    from .report import vigentes

    filas = en_orden_de_out(conn)
    leidos = [json.loads(f["contenido_json"]) for f in filas]
    elegidos = {id(p) for p in vigentes(leidos)}
    resultado: dict[int, int] = {}
    for fila, payload in zip(filas, leidos):
        if id(payload) in elegidos:
            resultado[fila["documento_id"]] = fila["id"]
    return resultado


# ------------------------------------------------------------- tipar

@dataclass(frozen=True)
class Tipado:
    documento_id: int
    factura_id: int | None
    accion: str           # creada | actualizada | sin_cambios | omitido | error
    detalle: str = ""


def _cabecera(
    leida: compat.ExtraccionLeida, sentido: str,
) -> tuple[dict[str, Leido], bool, str | None]:
    datos = leida.datos
    euros, moneda = en_euros(leida)
    dudosos, _por_linea, _todas = _dudosos(datos)
    valores: dict[str, Leido] = {}
    for clave, columna, lector in CABECERA:
        valores[columna] = leer_literal(lector, datos.get(clave), en_euros=euros,
                                        dudoso=clave in dudosos)
    clave_contacto = CONTACTO[sentido]
    valores["contacto_nombre_doc"] = leer_literal(
        TEXTO, datos.get(clave_contacto), dudoso=clave_contacto in dudosos)

    tipo_doc = datos.get("document_type")
    if tipo_doc is not None:
        tipo = (TipoFactura.NOTA_CREDITO.value if tipo_doc == "credit_note"
                else TipoFactura.FACTURA.value)
        valores["tipo"] = Leido(tipo, crudo=tipo_doc)
    else:
        # v1 no dice que es el documento: un total negativo es un abono.
        total = valores["total_cent"].valor
        base = valores["base_cent"].valor
        negativo = any(isinstance(v, Decimal) and v < 0 for v in (total, base))
        valores["tipo"] = Leido(
            TipoFactura.NOTA_CREDITO.value if negativo else TipoFactura.FACTURA.value,
            fuente=Fuente.CALCULADO.value, ref="signo_del_total")
    if isinstance(datos.get("currency_raw"), str):
        valores["moneda_doc"] = Leido(datos["currency_raw"], crudo=datos["currency_raw"])
    elif not euros:
        valores["moneda_doc"] = Leido(moneda, fuente=Fuente.CALCULADO.value, ref="x1_literales")
    else:
        valores["moneda_doc"] = Leido(None, fuente=Fuente.CALCULADO.value, ref="x1_literales")
    return valores, euros, moneda


def ref_linea(extraccion_id: int, indice: int) -> str:
    """La referencia de un valor de la linea `indice` (desde 0) de una extraccion.

    Va en la procedencia de cada campo de la linea: legado.py encuentra asi
    el literal impreso aunque la linea ya no este en la misma posicion.
    """
    return f"extraccion:{extraccion_id}:lines[{indice}]"


def _lineas(
    leida: compat.ExtraccionLeida, euros: bool, extraccion_id: int,
) -> list[dict[str, Leido]]:
    _cabecera_dudosa, por_linea, todas = _dudosos(leida.datos)
    lineas = []
    for indice, linea in enumerate(leida.datos.get("lines") or []):
        if not isinstance(linea, dict):
            continue
        dudosas = por_linea.get(indice, set()) | todas
        ref = ref_linea(extraccion_id, indice)
        valores = {
            columna: replace(leer_literal(lector, linea.get(clave), en_euros=euros,
                                          dudoso=clave in dudosas), ref=ref)
            for clave, columna, lector in LINEA
        }
        valores["huella_linea"] = Leido(
            sha256_texto(json_canonico({"orden": indice + 1, "linea": _sin_floats(linea)})),
            fuente=Fuente.CALCULADO.value, ref="huella")
        lineas.append(valores)
    return lineas


def _sin_floats(valor: Any) -> Any:
    """Una linea como la escribio el extractor, para su huella (sin floats sueltos)."""
    if isinstance(valor, float):
        return repr(valor)
    if isinstance(valor, dict):
        return {k: _sin_floats(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sin_floats(v) for v in valor]
    return valor


def _referencias(leida: compat.ExtraccionLeida) -> list[tuple[int | None, dict[str, Leido]]]:
    """Cada referencia impresa con su etiqueta (v2): (indice de linea o None, valores)."""
    resultado = []
    for referencia in leida.datos.get("references") or []:
        if isinstance(referencia, dict) and isinstance(referencia.get("value"), str):
            resultado.append((None, {
                "etiqueta_doc": leer_literal(TEXTO, referencia.get("label")),
                "valor_doc": leer_literal(TEXTO, referencia.get("value")),
            }))
    for indice, linea in enumerate(leida.datos.get("lines") or []):
        if isinstance(linea, dict) and isinstance(linea.get("order_reference_raw"), str):
            resultado.append((indice, {
                "etiqueta_doc": Leido(None),
                "valor_doc": leer_literal(TEXTO, linea["order_reference_raw"]),
            }))
    return resultado


def _desglose(leida: compat.ExtraccionLeida, euros: bool) -> list[dict[str, Leido]]:
    filas = []
    for entrada in leida.datos.get("vat_breakdown") or []:
        if isinstance(entrada, dict):
            filas.append({columna: leer_literal(lector, entrada.get(clave), en_euros=euros)
                          for clave, columna, lector in IVA_V2})
    return filas


def _fecha_recepcion(documento: sqlite3.Row) -> Leido:
    """Solo si se sabe de verdad cuando llego (correo, ingesta), no por la fecha del fichero."""
    if documento["recibido_fuente"] not in ("correo", "ingesta") or not documento["recibido_en"]:
        return Leido(None)
    dia = datetime.fromisoformat(documento["recibido_en"]).astimezone(ZoneInfo(ZONA_EMPRESA)).date()
    return Leido(dia, fuente=Fuente.CALCULADO.value, ref=f"documento:{documento['id']}")


def _de_la_extraccion(conn: sqlite3.Connection, tabla: str, fila_id: int) -> bool:
    """La fila la puso una extraccion y nadie la ha tocado a mano."""
    fuentes = {f[0] for f in conn.execute(
        "SELECT fuente FROM procedencia_campo WHERE tabla = ? AND fila_id = ?", (tabla, fila_id))}
    return not (fuentes & {Fuente.MANUAL_ENTRADA.value, Fuente.MANUAL_CORRECCION.value})


def tipar_documento(
    conn: sqlite3.Connection, documento_id: int, *, extraccion_id: int | None = None,
) -> Tipado:
    """Convierte la extraccion vigente de un documento en su factura tipada.

    Si la factura ya existe con esa extraccion, no hace nada. Si existe con
    otra, aplica la nueva como fuente automatica (lo manual se queda).
    """
    documento = conn.execute("SELECT * FROM documento WHERE id = ?", (documento_id,)).fetchone()
    if documento is None:
        raise LookupError(f"no hay documento {documento_id}")
    sentido = SENTIDO_DE_RUTA.get(documento["ruta_declarada"])
    if sentido is None:
        return Tipado(documento_id, None, "omitido",
                      f"llego por la via {documento['ruta_declarada']}: no es una factura")
    if extraccion_id is None:
        extraccion_id = vigentes_por_documento(conn).get(documento_id)
    if extraccion_id is None:
        return Tipado(documento_id, None, "omitido", "no tiene extraccion")
    extraccion = conn.execute("SELECT * FROM extraccion WHERE id = ?", (extraccion_id,)).fetchone()
    existente = conn.execute(
        "SELECT * FROM factura WHERE documento_id = ? AND origen = 'extraccion'", (documento_id,)
    ).fetchone()
    if existente is not None and existente["extraccion_vigente_id"] == extraccion_id:
        return Tipado(documento_id, existente["id"], "sin_cambios")

    registro = json.loads(extraccion["contenido_json"])
    try:
        leida = compat.leer_registro(registro)
    except ValueError as exc:
        return Tipado(documento_id, None, "omitido", str(exc))

    origen = Automatico(Fuente.EXTRACCION.value, usuario_sistema(conn, "extractor"),
                        ref=f"extraccion:{extraccion_id}")
    cabecera, euros, _moneda = _cabecera(leida, sentido)
    lineas = _lineas(leida, euros, extraccion_id)
    referencias = _referencias(leida)
    desglose = _desglose(leida, euros)
    calculado = Fuente.CALCULADO.value
    datos = {"documento_id": documento_id, "extraccion_id": extraccion_id,
             "schema_version": leida.schema_version}

    with campos.orden(conn, origen, tipo="factura_tipada" if existente is None
                      else "factura_reextraida", datos=datos) as o:
        estructura = {"extraccion_vigente_id": Leido(extraccion_id, fuente=calculado,
                                                     ref=f"extraccion:{extraccion_id}")}
        if existente is None:
            factura_id = o.crear("factura", {
                "sentido": Leido(sentido, fuente=calculado,
                                 ref=f"ruta:{documento['ruta_declarada']}"),
                "origen": Leido("extraccion", fuente=calculado),
                "documento_id": Leido(documento_id, fuente=calculado,
                                      ref=f"documento:{documento_id}"),
                **estructura, **cabecera,
                **({"fecha_recepcion": _fecha_recepcion(documento)}
                   if sentido == Sentido.ENTRANTE.value else {}),
            })
            o.factura_id = factura_id
            ids = _crear_lineas(o, factura_id, lineas, desde=1)
            _crear_hijas(o, factura_id, referencias, desglose, ids)
            detalle = f"{len(lineas)} lineas"
            accion = "creada"
        else:
            factura_id = existente["id"]
            o.tabla, o.fila_id, o.factura_id = "factura", factura_id, factura_id
            o.fijar("factura", factura_id, {**estructura, **cabecera})
            conflictos, por_indice = _actualizar_lineas(o, conn, factura_id, lineas)
            conflictos_hijas = _actualizar_hijas(o, conn, factura_id, referencias, desglose,
                                                 por_indice)
            if conflictos_hijas:
                o.datos["filas_con_edicion_manual_sin_casar"] = conflictos_hijas
            if conflictos:
                o.datos["lineas_con_edicion_manual_sin_casar"] = conflictos
            detalle = f"{len(lineas)} lineas"
            if conflictos:
                detalle += f"; {len(conflictos)} lineas con ediciones manuales se conservan"
            accion = "actualizada"
    return Tipado(documento_id, factura_id, accion, detalle)


def _crear_lineas(
    o: campos.Orden, factura_id: int, lineas: list[dict[str, Leido]], *, desde: int,
) -> dict[int, int]:
    """Cada linea con su imputacion por defecto. Devuelve indice en `lineas` -> linea_id."""
    calculado = Fuente.CALCULADO.value
    ids = {}
    for indice, valores in enumerate(lineas):
        linea_id = o.crear("factura_linea", {
            "factura_id": Leido(factura_id, fuente=calculado),
            "orden": Leido(desde + indice, fuente=calculado), **valores,
        })
        o.crear("factura_imputacion", {
            "factura_id": Leido(factura_id, fuente=calculado),
            "linea_id": Leido(linea_id, fuente=calculado),
        })
        ids[indice] = linea_id
    return ids


def _crear_hijas(o: campos.Orden, factura_id: int,
                 referencias: list[tuple[int | None, dict[str, Leido]]],
                 desglose: list[dict[str, Leido]], lineas: dict[int, int]) -> None:
    calculado = Fuente.CALCULADO.value
    for indice, valores in referencias:
        extra = {}
        if indice is not None and indice in lineas:
            extra["linea_id"] = Leido(lineas[indice], fuente=calculado)
        o.crear("factura_referencia", {"factura_id": Leido(factura_id, fuente=calculado),
                                       **extra, **valores})
    for valores in desglose:
        o.crear("factura_iva", {"factura_id": Leido(factura_id, fuente=calculado), **valores})


def _actualizar_lineas(
    o: campos.Orden, conn: sqlite3.Connection, factura_id: int, lineas: list[dict[str, Leido]],
) -> tuple[list[int], dict[int, int]]:
    """Casa por posicion las lineas de la extraccion nueva con las que puso una extraccion.

    Se casan todas las que puso una extraccion, tambien las que una persona
    excluyo: si se dejaran fuera, cada linea detras de la excluida se
    correria un puesto y la excluida volveria como activa. Una excluida
    casada recibe los valores nuevos y sigue excluida. Las que retiro una
    extraccion anterior porque ya no venian no cuentan: estan al final, y si
    vuelven a venir entran como lineas nuevas.

    Cada campo sigue la regla de siempre: lo que una persona corrigio no se
    pisa. Las lineas que ya no vienen se retiran (con su imputacion), salvo
    que una persona las haya editado: esas se conservan y se devuelven
    (casarlas por su huella es del paso 6, y mientras tanto no se pierde lo
    que una persona escribio). Una linea anadida a mano no se toca.

    Devuelve las conservadas (su orden) y, para cada indice de la extraccion
    nueva, la linea con la que caso o que se creo.
    """
    previas = _de_extracciones(conn, "factura_linea", factura_id)
    por_indice = {}
    for indice, (fila, valores) in enumerate(zip(previas, lineas)):
        o.fijar("factura_linea", fila["id"], valores)
        por_indice[indice] = fila["id"]
    ocupados = {f["orden"] for f in conn.execute(
        "SELECT orden FROM factura_linea WHERE factura_id = ?", (factura_id,))}
    for indice, valores in enumerate(lineas[len(previas):], start=len(previas)):
        orden = indice + 1 if indice + 1 not in ocupados else max(ocupados) + 1
        ocupados.add(orden)
        por_indice[indice] = _crear_lineas(o, factura_id, [valores], desde=orden)[0]
    conflictos = []
    for fila in previas[len(lineas):]:
        if fila["retirada_en"] is not None:
            continue
        if not _de_la_extraccion(conn, "factura_linea", fila["id"]):
            conflictos.append(fila["orden"])
            continue
        o.retirar("factura_linea", fila["id"])         # y su imputacion (campos)
    return conflictos, por_indice


def _de_extracciones(conn: sqlite3.Connection, tabla: str, factura_id: int) -> list[sqlite3.Row]:
    """Las filas de una hija de la factura que puso una extraccion, en su orden.

    Las activas y las que retiro una persona; no las que retiro una
    extraccion porque ya no venian, ni las que creo una persona.
    """
    orden = "orden, id" if tabla == "factura_linea" else "id"
    filas = conn.execute(
        f"SELECT * FROM {tabla} WHERE factura_id = ? ORDER BY {orden}", (factura_id,)).fetchall()
    resultado = []
    for fila in filas:
        procedencia = campos.procedencia(conn, tabla, fila["id"])
        alta = procedencia.get("factura_id")
        if alta is None or alta["fuente_original"] not in FUENTES_AUTOMATICAS:
            continue
        retirada = procedencia.get("retirada_en")
        if fila["retirada_en"] is not None and (
                retirada is None or retirada["fuente"] in FUENTES_AUTOMATICAS):
            continue
        resultado.append(fila)
    return resultado


def _actualizar_hijas(o: campos.Orden, conn: sqlite3.Connection, factura_id: int,
                      referencias: list[tuple[int | None, dict[str, Leido]]],
                      desglose: list[dict[str, Leido]], lineas: dict[int, int]) -> list[str]:
    """Referencias y desglose de IVA, casados por posicion como las lineas.

    Igual que las lineas: entran en el casado todas las filas que puso una
    extraccion, tambien las que una persona edito o retiro (si se dejaran
    fuera, los valores nuevos caerian en la fila de al lado y se duplicaria
    una). Lo que una persona puso en una fila no se pisa; una fila editada
    que ya no viene se conserva y se devuelve. Una referencia nueva de una
    linea se ata a la linea con la que caso ese indice (`lineas`).
    """
    conflictos = []
    for tabla, nuevas in (("factura_referencia", referencias),
                          ("factura_iva", [(None, v) for v in desglose])):
        existentes = _de_extracciones(conn, tabla, factura_id)
        for fila, (_indice, valores) in zip(existentes, nuevas):
            o.fijar(tabla, fila["id"], valores)
        for fila in existentes[len(nuevas):]:
            if fila["retirada_en"] is not None:
                continue
            if not _de_la_extraccion(conn, tabla, fila["id"]):
                conflictos.append(f"{tabla}:{fila['id']}")
                continue
            o.retirar(tabla, fila["id"])
        sobrantes = nuevas[len(existentes):]
        if tabla == "factura_referencia":
            _crear_hijas(o, factura_id, sobrantes, [], lineas)
        else:
            _crear_hijas(o, factura_id, [], [v for _i, v in sobrantes], lineas)
    return conflictos


def tipar_pendientes(conn: sqlite3.Connection) -> list[Tipado]:
    """Tipa cada documento cuya extraccion vigente no esta aun en su factura.

    Cada documento va en su propia transaccion (o SAVEPOINT): un documento
    que no se puede tipar queda apuntado como error y no deshace los demas.
    """
    resultados = []
    vigentes = vigentes_por_documento(conn)
    for documento_id, extraccion_id in sorted(vigentes.items()):
        try:
            with transaccion(conn):
                resultados.append(tipar_documento(conn, documento_id, extraccion_id=extraccion_id))
        except (sqlite3.Error, ValueError, TypeError, LookupError) as exc:
            resultados.append(Tipado(documento_id, None, "error", f"{type(exc).__name__}: {exc}"))
    return resultados


def reconciliar_referencias(conn: sqlite3.Connection, *, actor: int | None = None) -> int:
    """Vuelve a resolver proveedor, cliente, Objeto y recurso con los maestros de ahora.

    Lo llama quien cambia un maestro (la semilla de tarifas, las
    importaciones del paso 5): una factura tipada antes de que existiera su
    Objeto se imputa ahora. Un valor puesto a mano no se pisa. Devuelve
    cuantos campos cambiaron.
    """
    origen = Automatico(Fuente.CALCULADO.value, actor or usuario_sistema(conn, "motor"),
                        ref="maestros")
    with campos.orden(conn, origen, tipo="referencias_recalculadas") as o:
        for fila in conn.execute(
            "SELECT id FROM factura WHERE fusionada_en_id IS NULL ORDER BY id"
        ).fetchall():
            o.recalcular("factura", fila["id"], ("proveedor_id", "cliente_id"))
        for fila in conn.execute(
            "SELECT id FROM factura_imputacion WHERE retirada_en IS NULL ORDER BY id"
        ).fetchall():
            o.recalcular("factura_imputacion", fila["id"], ("objeto_id", "recurso_id"))
    return sum(1 for e in o.resultado.efectos if e.accion in ("cambiado", "alta"))


# ------------------------------------------------------------- la pasada

@dataclass
class ResultadoIngesta:
    tipados: list[Tipado] = field(default_factory=list)
    # La pasada del motor de reglas con la que acaba la ingesta (hallazgos.Diferencia).
    recalculo: Any = None

    def cuenta(self, accion: str) -> int:
        return sum(1 for t in self.tipados if t.accion == accion)

    @property
    def errores(self) -> list[Tipado]:
        return [t for t in self.tipados if t.accion == "error"]


def ingestar_pasada(
    client: Any,
    pdfs: Iterable[str | Path],
    out_dir: str | Path,
    *,
    almacen: Any,
    ruta: str = "entrante",
    resultado_pasada: Any = None,
    tipar: Callable[[sqlite3.Connection], list[Tipado]] = tipar_pendientes,
    **opciones: Any,
) -> tuple[Any, ResultadoIngesta]:
    """La entrada completa de una carpeta: almacen, extraccion segun la cache y filas tipadas.

    Es lo que ejecutan `extract` y el boton del servidor. La extraccion y la
    evidencia van primero, documento a documento (lo pagado no se pierde
    aunque tipar falle); despues se tipa todo lo pendiente, sin API, y se
    recalculan las reglas, las dos cosas en una transaccion (cada documento
    en su SAVEPOINT): o queda tipado con sus hallazgos al dia, o nada.
    """
    from .extract import extraer_pasada
    from .hallazgos import recalcular

    if ruta not in SENTIDO_DE_RUTA:
        raise ValueError(f"via de entrada desconocida: {ruta!r}")
    pasada = extraer_pasada(client, pdfs, out_dir, almacen=almacen, ruta=ruta,
                            resultado=resultado_pasada, **opciones)
    with transaccion(almacen.conn):
        resultado = ResultadoIngesta(tipar(almacen.conn))
        resultado.recalculo = recalcular(almacen.conn, motivo="ingesta")
    return pasada, resultado

