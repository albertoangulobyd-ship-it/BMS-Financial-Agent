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

Una extraccion nueva del mismo documento pasa a vigente como hasta ahora (la
mas reciente, la regla de load_records) y se aplica como fuente automatica:
lo que una persona corrigio no se pisa, solo queda apuntado el nuevo valor
automatico (y si lo contradice, el campo queda sin resolver: M1). Desde el
paso 6, lo que lee `bms-agent reextraer`, y lo que relee `extract --force` o
`--estricta` de un documento cuya vigente es de otras versiones, es una
candidata y no cuenta para la vigente hasta que una persona la activa
despues de la puerta de puntuacion (reextraccion.py).

Las lineas de la extraccion nueva se casan con las que ya habia por su
huella de contenido (descripcion, cantidad, unidad, tarifa e importe,
normalizados), no por su posicion: una linea de mas o de menos no corre las
ediciones de una persona a la linea de al lado. Una linea editada por una
persona (o excluida, o con su imputacion o su referencia cambiada) solo se
casa por su huella; si no se puede, se conserva y queda apuntada en
linea_sin_casar, y la regla M2 la convierte en hallazgo.

Nada de aqui llama a la API: tipar es determinista y se puede repetir.
"""

from __future__ import annotations

import json
import re
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
from .dominio import (
    FUENTES_AUTOMATICAS,
    Fuente,
    RelacionCitada,
    Sentido,
    TipoFactura,
    TratamientoIva,
)
from .identidad import reconciliar_referencias  # noqa: F401 (su sitio de antes)
from .parsing import (
    ParseError,
    detectar_moneda,
    parse_amount,
    parse_iso_date,
    parse_percentage,
    parse_plazo_pago,
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

# document_type (v2) -> factura.tipo, solo cuando el documento lo declara.
# Una correccion o una sustitucion es una factura; que sustituya a otra es
# una relacion propuesta (paso 8), no otro tipo.
TIPO_DECLARADO = {
    "invoice": TipoFactura.FACTURA.value,
    "corrected_invoice": TipoFactura.FACTURA.value,
    "replacement_invoice": TipoFactura.FACTURA.value,
    "credit_note": TipoFactura.NOTA_CREDITO.value,
}

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

# Paso 8: las facturas que el documento nombra (related_invoices de v2), tal
# como las nombra. Que una sea una relacion lo propone relaciones.py casando el
# numero con una factura de la misma contraparte; nunca lo deduce el modelo.
CITA: tuple[tuple[str, str, str], ...] = (
    ("invoice_number", "numero_doc", TEXTO),
    ("invoice_date", "fecha_doc", FECHA),
    ("relation_text", "texto_doc", TEXTO),
)
RELACIONES_CITADAS = frozenset(RelacionCitada.valores())


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
    # Con una extraccion nueva: los valores manuales que contradice (quedan
    # sin resolver, M1) como "tabla:fila:campo", y las lineas editadas que no
    # se pudieron casar con ninguna linea nueva (M2).
    contradichos: tuple[str, ...] = ()
    sin_casar: tuple[int, ...] = ()


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
    # El plazo lo calcula el codigo del literal impreso (spec §10), nunca el
    # modelo; si no se puede leer sin adivinar, queda vacio. Es lo que dice el
    # proveedor: el vencimiento (estados.py) lo usa solo si el maestro no
    # tiene plazo acordado. Una v1 no trae condiciones y no escribe nada.
    if leida.solicitado("payment_terms_raw"):
        valores["plazo_pago_dias"] = Leido(_plazo(datos.get("payment_terms_raw")),
                                           fuente=Fuente.CALCULADO.value,
                                           ref="condiciones_pago_doc")
    clave_contacto = CONTACTO[sentido]
    valores["contacto_nombre_doc"] = leer_literal(
        TEXTO, datos.get(clave_contacto), dudoso=clave_contacto in dudosos)

    valores["tipo"] = _tipo(datos.get("document_type"), valores)
    if isinstance(datos.get("currency_raw"), str):
        valores["moneda_doc"] = Leido(datos["currency_raw"], crudo=datos["currency_raw"])
    elif not euros:
        valores["moneda_doc"] = Leido(moneda, fuente=Fuente.CALCULADO.value, ref="x1_literales")
    else:
        valores["moneda_doc"] = Leido(None, fuente=Fuente.CALCULADO.value, ref="x1_literales")
    return valores, euros, moneda


def _tipo(tipo_doc: Any, valores: dict[str, Leido]) -> Leido:
    """factura.tipo: lo que el documento declara, si su signo impreso lo confirma.

    v1 no dice que es el documento, y un v2 que no lo declara (unknown) o
    que se declara anulacion tampoco dice si es una factura o un abono:
    decide el signo del total, como en v1. Lo declarado es un texto que
    copia el modelo de lo que escribio el proveedor: un "CREDITNOTA" impreso
    en una factura positiva la sacaria de B4 (un abono no cobra un periodo)
    y de U1. Por eso lo declarado solo vale si el signo de la base o del
    total lo confirma; si lo contradice, decide el signo y el total queda
    dudoso, para que Q2 retenga la factura hasta que una persona lo mire.
    Sin importes legibles no hay signo con que contradecirlo.
    """
    importes = [v for v in (valores["total_cent"].valor, valores["base_cent"].valor)
                if isinstance(v, Decimal)]
    negativo = any(v < 0 for v in importes)
    por_signo = TipoFactura.NOTA_CREDITO.value if negativo else TipoFactura.FACTURA.value
    declarado = TIPO_DECLARADO.get(tipo_doc) if isinstance(tipo_doc, str) else None
    if declarado is not None and (not importes or declarado == por_signo):
        return Leido(declarado, crudo=tipo_doc)
    if declarado is not None:
        valores["total_cent"] = replace(valores["total_cent"], dudoso=True)
        return Leido(por_signo, crudo=tipo_doc, fuente=Fuente.CALCULADO.value,
                     ref="signo_contra_declarado")
    return Leido(por_signo, fuente=Fuente.CALCULADO.value, ref="signo_del_total")


def _plazo(crudo: Any) -> int | None:
    if not isinstance(crudo, str):
        return None
    try:
        return parse_plazo_pago(crudo)
    except ParseError:
        return None


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
        valores["huella_linea"] = Leido(huella_de_leidos(valores), fuente=Fuente.CALCULADO.value,
                                        ref="huella")
        lineas.append(valores)
    return lineas


# ------------------------------------------------------------- huella de linea
#
# La huella de una linea es lo que dice: descripcion, cantidad, unidad,
# tarifa e importe, normalizados (sin mayusculas ni signos en el texto, los
# numeros sin ceros de mas). No lleva la posicion ni las claves que anade una
# version del esquema: la misma linea leida por v1 y por v2, o leida en otra
# posicion porque otra linea aparecio delante, da la misma huella. Es lo que
# permite llevar las ediciones de una persona a la linea que les toca cuando
# llega una lectura nueva (spec §10).

_COLUMNAS_HUELLA = ("descripcion_doc", "cantidad_mil", "unidad_doc", "tarifa_e4", "importe_cent")
_ESCALA_HUELLA = {"cantidad_mil": -3, "tarifa_e4": -4, "importe_cent": -2}


def _parte_huella(valor: Any, crudo: Any = None) -> str | None:
    if isinstance(valor, Decimal):
        return format(valor.normalize(), "f") if valor else "0"
    if isinstance(valor, str):
        return "".join(c for c in valor.casefold() if c.isalnum()) or None
    if valor is None and crudo is not None:
        # Un literal que no se pudo leer: cuenta como lo que pone.
        return "?" + "".join(str(crudo).split())
    return None if valor is None else str(valor)


def huella_linea(partes: dict[str, Any]) -> str:
    """La huella de contenido de una linea, de sus cinco valores ya normalizados."""
    return sha256_texto(json_canonico({c: partes.get(c) for c in _COLUMNAS_HUELLA}))


def huella_de_leidos(valores: dict[str, Leido]) -> str:
    """La huella de una linea tal como la lee una extraccion."""
    return huella_linea({c: _parte_huella(valores[c].valor, valores[c].crudo)
                         for c in _COLUMNAS_HUELLA})


def huella_de_fila(fila: Any) -> str:
    """La huella de una linea con sus valores actuales (los corregidos, si los hay)."""
    partes = {}
    for columna in _COLUMNAS_HUELLA:
        valor = fila[columna]
        if columna in _ESCALA_HUELLA and valor is not None:
            valor = Decimal(valor).scaleb(_ESCALA_HUELLA[columna])
        partes[columna] = _parte_huella(valor)
    return huella_linea(partes)


_REF_LINEA = re.compile(r"^extraccion:(\d+):lines\[(\d+)\]$")


def huella_de_su_lectura(conn: sqlite3.Connection, linea_id: int,
                         cache: dict[int, Any] | None = None) -> str | None:
    """La huella de una linea recalculada de la ultima lectura automatica que la puso.

    huella_linea guarda la de la lectura que creo la linea, pero en un
    almacen de antes del paso 6 lleva la definicion de entonces (la posicion
    y el JSON crudo), y huella_de_fila no puede reproducir un literal que no
    se pudo leer ("?n.v.t."): ese valor no esta en la fila. La referencia de
    la procedencia (extraccion:N:lines[i]) dice de que linea de que lectura
    salio, y de ahi se lee con la definicion de ahora. None si no se sabe.
    """
    cache = {} if cache is None else cache
    procedencia = campos.procedencia(conn, "factura_linea", linea_id)
    for columna in _COLUMNAS_HUELLA:
        datos = procedencia.get(columna) or {}
        ref = datos.get("fuente_automatica_ref") or datos.get("fuente_ref")
        m = _REF_LINEA.match(ref or "")
        if m:
            break
    else:
        return None
    extraccion_id, indice = int(m.group(1)), int(m.group(2))
    if extraccion_id not in cache:
        fila = conn.execute("SELECT contenido_json FROM extraccion WHERE id = ?",
                            (extraccion_id,)).fetchone()
        try:
            leida = compat.leer_registro(json.loads(fila[0])) if fila else None
        except ValueError:
            leida = None
        cache[extraccion_id] = (leida, en_euros(leida)[0]) if leida else None
    if cache[extraccion_id] is None:
        return None
    leida, euros = cache[extraccion_id]
    lineas = leida.datos.get("lines") or []
    if indice >= len(lineas) or not isinstance(lineas[indice], dict):
        return None
    valores = {columna: leer_literal(lector, lineas[indice].get(clave), en_euros=euros)
               for clave, columna, lector in LINEA if columna in _COLUMNAS_HUELLA}
    return huella_de_leidos(valores)


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


def _citas(leida: compat.ExtraccionLeida) -> list[dict[str, Leido]]:
    """Cada factura que el documento nombra, con la relacion que enuncia (v2).

    Una relacion que no es de la lista (o que no se dijo) queda "unknown": no
    se adivina por los importes (regla 9 del prompt, decision 20).
    """
    filas = []
    for entrada in leida.datos.get("related_invoices") or []:
        if not isinstance(entrada, dict):
            continue
        valores = {columna: leer_literal(lector, entrada.get(clave))
                   for clave, columna, lector in CITA}
        relacion = entrada.get("stated_relation")
        valores["relacion_doc"] = Leido(
            relacion if relacion in RELACIONES_CITADAS else RelacionCitada.DESCONOCIDA.value,
            crudo=relacion)
        filas.append(valores)
    return filas


# Los documentos que entran leyendo una carpeta (extract, la consola): el dia en que el
# sistema los registro es el dia en que llegaron a el.
_LLEGAN_AL_LEERLOS = frozenset({"carpeta"})


def _fecha_recepcion(documento: sqlite3.Row) -> Leido:
    """Cuando llego la factura, si se sabe de verdad: nunca por la fecha del fichero.

    Por correo o por una ingesta que lo apunta, su instante. Leida de una
    carpeta (extract, la consola), el dia en que el sistema la registro
    (documento.registrado_en): es cuando llego al sistema, y la fecha del
    fichero (mtime) la cambia cualquier copia. Lo que viene de out/ (una
    extraccion de antes, origen out_v1) se registro al migrar, no al llegar:
    queda sin fecha, para que la escriba una persona si importa.
    """
    if documento["recibido_fuente"] in ("correo", "ingesta") and documento["recibido_en"]:
        instante = documento["recibido_en"]
    elif documento["origen"] in _LLEGAN_AL_LEERLOS:
        instante = documento["registrado_en"]
    else:
        return Leido(None)
    dia = datetime.fromisoformat(instante).astimezone(ZoneInfo(ZONA_EMPRESA)).date()
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
    citas = _citas(leida)
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
            _crear_hijas(o, factura_id, referencias, desglose, ids, citas)
            detalle = f"{len(lineas)} lineas"
            accion = "creada"
        else:
            factura_id = existente["id"]
            o.tabla, o.fila_id, o.factura_id = "factura", factura_id, factura_id
            o.fijar("factura", factura_id, {**estructura, **cabecera})
            conflictos, por_indice = _actualizar_lineas(o, conn, factura_id, lineas)
            conflictos_hijas = _actualizar_hijas(o, conn, factura_id, referencias, desglose,
                                                 por_indice, citas)
            if conflictos_hijas:
                o.datos["filas_con_edicion_manual_sin_casar"] = conflictos_hijas
            if conflictos:
                o.datos["lineas_con_edicion_manual_sin_casar"] = [c.orden for c in conflictos]
            detalle = f"{len(lineas)} lineas"
            if conflictos:
                detalle += f"; {len(conflictos)} lineas con ediciones manuales se conservan"
            accion = "actualizada"
    if existente is None:
        return Tipado(documento_id, factura_id, accion, detalle)
    contradichos = tuple(sorted(
        f"{e.tabla}:{e.fila_id}:{e.campo}" for e in o.resultado.efectos
        if e.accion == "solo_automatico" and e.discrepancia))
    for conflicto in conflictos:
        _apuntar_sin_casar(conn, factura_id, extraccion_id, conflicto)
    return Tipado(documento_id, factura_id, accion, detalle, contradichos,
                  tuple(c.linea_id for c in conflictos))


@dataclass(frozen=True)
class _SinCasar:
    """Una linea editada por una persona que la extraccion nueva no trae."""

    linea_id: int
    orden: int
    excluida: bool
    campos: tuple[str, ...]


def _apuntar_sin_casar(conn: sqlite3.Connection, factura_id: int, extraccion_id: int,
                       linea: _SinCasar) -> None:
    """Apunta la linea en linea_sin_casar, con su evento (que lleva la foto), para M2.

    Va despues de la orden que tipo la factura: la base exige que la factura
    tenga ya esta extraccion como vigente.
    """
    from .almacen import reloj_de
    from .auditoria import registrar
    from .reloj import marca

    fila = {"factura_id": factura_id, "linea_id": linea.linea_id,
            "extraccion_id": extraccion_id, "excluida": int(linea.excluida),
            "campos_json": json_canonico(list(linea.campos)),
            "en": marca(reloj_de(conn).ahora())}
    evento = registrar(conn, tipo="linea_sin_casar", actor=usuario_sistema(conn, "extractor"),
                       tabla="factura_linea", fila_id=linea.linea_id, factura_id=factura_id,
                       datos={"orden": linea.orden, "fila": fila})
    conn.execute(
        "INSERT INTO linea_sin_casar (factura_id, linea_id, extraccion_id, excluida, "
        "campos_json, en, evento_id) VALUES (:factura_id, :linea_id, :extraccion_id, "
        ":excluida, :campos_json, :en, :evento_id)", {**fila, "evento_id": evento})


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
                 desglose: list[dict[str, Leido]], lineas: dict[int, int],
                 citas: list[dict[str, Leido]] = ()) -> None:
    calculado = Fuente.CALCULADO.value
    for indice, valores in referencias:
        extra = {}
        if indice is not None and indice in lineas:
            extra["linea_id"] = Leido(lineas[indice], fuente=calculado)
        o.crear("factura_referencia", {"factura_id": Leido(factura_id, fuente=calculado),
                                       **extra, **valores})
    for valores in desglose:
        o.crear("factura_iva", {"factura_id": Leido(factura_id, fuente=calculado), **valores})
    for valores in citas:
        o.crear("factura_cita", {"factura_id": Leido(factura_id, fuente=calculado), **valores})


def _actualizar_lineas(
    o: campos.Orden, conn: sqlite3.Connection, factura_id: int, lineas: list[dict[str, Leido]],
) -> tuple[list[_SinCasar], dict[int, int]]:
    """Casa las lineas de la extraccion nueva con las que puso una extraccion, por su huella.

    Entran en el casado todas las que puso una extraccion, tambien las que
    una persona excluyo (una excluida casada recibe los valores nuevos y
    sigue excluida). Las que retiro una extraccion anterior porque ya no
    venian no cuentan: si vuelven a venir, entran como lineas nuevas.

    Primero por huella, en orden: la de la lectura que la puso (huella_linea,
    y la misma recalculada de esa lectura, que es la unica en un almacen de
    antes del paso 6) o la de sus valores de ahora (una correccion de una
    persona puede ser justo lo que la lectura nueva lee bien). Despues, solo
    para las que nadie ha tocado, por posicion: la misma posicion impresa, leida de otra forma,
    es la misma linea, y asi su imputacion no cambia de fila. Una linea que
    una persona edito no se casa por posicion: si su huella no aparece, no se
    sabe cual es, y aplicar sus ediciones a otra seria peor que conservarla.

    Cada campo sigue la regla de siempre: lo que una persona corrigio no se
    pisa. Las que ya no vienen se retiran (con su imputacion) si nadie las
    toco; las editadas se conservan y se devuelven para linea_sin_casar (M2).
    Una linea anadida a mano no se toca.

    Devuelve las conservadas y, para cada indice de la extraccion nueva, la
    linea con la que caso o que se creo.
    """
    previas = _de_extracciones(conn, "factura_linea", factura_id)
    huellas = [v["huella_linea"].valor for v in lineas]
    libres = list(range(len(lineas)))
    casadas: dict[int, int] = {}
    lecturas: dict[int, Any] = {}
    for fila in previas:
        propias = {fila["huella_linea"], huella_de_fila(fila),
                   huella_de_su_lectura(conn, fila["id"], lecturas)} - {None}
        indice = next((j for j in libres if huellas[j] in propias), None)
        if indice is not None:
            casadas[fila["id"]] = indice
            libres.remove(indice)
    ediciones = {f["id"]: _ediciones_de_linea(conn, f["id"]) for f in previas
                 if f["id"] not in casadas}
    for fila in previas:
        indice = fila["orden"] - 1
        if fila["id"] not in casadas and not ediciones[fila["id"]] and indice in libres:
            casadas[fila["id"]] = indice
            libres.remove(indice)

    por_indice = {}
    for fila in previas:
        if fila["id"] in casadas:
            o.fijar("factura_linea", fila["id"], lineas[casadas[fila["id"]]])
            por_indice[casadas[fila["id"]]] = fila["id"]
    ocupados = {f["orden"] for f in conn.execute(
        "SELECT orden FROM factura_linea WHERE factura_id = ?", (factura_id,))}
    for indice in libres:
        orden = indice + 1 if indice + 1 not in ocupados else max(ocupados) + 1
        ocupados.add(orden)
        por_indice[indice] = _crear_lineas(o, factura_id, [lineas[indice]], desde=orden)[0]
    conflictos = []
    for fila in previas:
        if fila["id"] in casadas:
            continue
        if ediciones[fila["id"]]:
            if fila["retirada_en"] is not None and _excluida_por_su_m2(conn, fila["id"]):
                continue
            conflictos.append(_SinCasar(fila["id"], fila["orden"],
                                        fila["retirada_en"] is not None,
                                        tuple(ediciones[fila["id"]])))
            continue
        o.retirar("factura_linea", fila["id"])         # y su imputacion (campos)
    return conflictos, por_indice


def _excluida_por_su_m2(conn: sqlite3.Connection, linea_id: int) -> bool:
    """La linea ya salio sin casar estando activa, y una persona la excluyo despues.

    Es lo que pide su M2 ("excluyela si ya no existe"): la decision esta
    tomada, y una lectura posterior que tampoco la trae no tiene nada nuevo
    que preguntar. Volver a apuntarla reabriria el M2 que la persona cerro.
    Una linea que ya estaba excluida cuando salio sin casar (excluida = 1)
    sigue apuntandose: su exclusion no se ha llevado a ninguna linea nueva, y
    lo que la cierra es una anulacion con motivo.
    """
    ultima = conn.execute("SELECT excluida FROM linea_sin_casar WHERE linea_id = ? "
                          "ORDER BY id DESC LIMIT 1", (linea_id,)).fetchone()
    return ultima is not None and ultima[0] == 0


def _ediciones_de_linea(conn: sqlite3.Connection, linea_id: int) -> list[str]:
    """Lo que una persona cambio de una linea: sus campos, su exclusion, su imputacion o su referencia.

    Vacio si nadie la toco. "tabla.campo" de cada valor que tiene una fuente
    manual, de la linea y de las filas que cuelgan de ella.
    """
    filas = [("factura_linea", linea_id)]
    for tabla in ("factura_imputacion", "factura_referencia"):
        filas += [(tabla, f[0]) for f in conn.execute(
            f"SELECT id FROM {tabla} WHERE linea_id = ?", (linea_id,))]
    manuales = (Fuente.MANUAL_ENTRADA.value, Fuente.MANUAL_CORRECCION.value)
    ediciones = set()
    for tabla, fila_id in filas:
        for (campo,) in conn.execute(
                "SELECT campo FROM procedencia_campo WHERE tabla = ? AND fila_id = ? "
                "AND fuente IN (?, ?)", (tabla, fila_id, *manuales)):
            ediciones.add(f"{tabla}.{campo}")
    return sorted(ediciones)


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
                      desglose: list[dict[str, Leido]], lineas: dict[int, int],
                      citas: list[dict[str, Leido]] = ()) -> list[str]:
    """Referencias y desglose de IVA: las de la cabecera por posicion, las de linea con su linea.

    Entran en el casado todas las filas que puso una extraccion, tambien las
    que una persona edito o retiro (si se dejaran fuera, los valores nuevos
    caerian en la fila de al lado y se duplicaria una). Lo que una persona
    puso en una fila no se pisa; una fila editada que ya no viene se conserva
    y se devuelve.

    Una referencia de linea no se casa por su posicion en la lista: va con
    la linea con la que caso su indice (`lineas`, por huella). Si esa linea
    ya tenia una referencia de una extraccion, es esa fila la que recibe el
    valor nuevo (y la correccion de una persona sigue en su linea); si no,
    se crea. Por posicion, una linea nueva delante correria cada referencia
    a la linea de al lado.
    """
    conflictos = []
    existentes = _de_extracciones(conn, "factura_referencia", factura_id)
    de_cabecera = [(None, v) for i, v in referencias if i is None]
    conflictos += _casar_por_posicion(
        o, conn, factura_id, "factura_referencia",
        [f for f in existentes if f["linea_id"] is None], de_cabecera, lineas)
    por_linea: dict[int, sqlite3.Row] = {}
    for fila in existentes:
        if fila["linea_id"] is not None:
            por_linea.setdefault(fila["linea_id"], fila)
    usadas: set[int] = set()
    nuevas = []
    for indice, valores in referencias:
        if indice is None:
            continue
        fila = por_linea.get(lineas.get(indice))
        if fila is not None and fila["id"] not in usadas:
            o.fijar("factura_referencia", fila["id"], valores)
            usadas.add(fila["id"])
        else:
            nuevas.append((indice, valores))
    for fila in existentes:
        if fila["linea_id"] is not None and fila["id"] not in usadas:
            conflictos += _retirar_si_no_es_de_persona(o, conn, "factura_referencia", fila)
    _crear_hijas(o, factura_id, nuevas, [], lineas)
    conflictos += _casar_por_posicion(
        o, conn, factura_id, "factura_iva", _de_extracciones(conn, "factura_iva", factura_id),
        [(None, v) for v in desglose], lineas)
    conflictos += _casar_por_posicion(
        o, conn, factura_id, "factura_cita", _de_extracciones(conn, "factura_cita", factura_id),
        [(None, v) for v in citas], lineas)
    return conflictos


def _retirar_si_no_es_de_persona(o: campos.Orden, conn: sqlite3.Connection, tabla: str,
                                 fila: sqlite3.Row) -> list[str]:
    """Retira una fila que ya no viene; la que toco una persona se conserva y se devuelve."""
    if fila["retirada_en"] is not None:
        return []
    if not _de_la_extraccion(conn, tabla, fila["id"]):
        return [f"{tabla}:{fila['id']}"]
    o.retirar(tabla, fila["id"])
    return []


def _casar_por_posicion(o: campos.Orden, conn: sqlite3.Connection, factura_id: int, tabla: str,
                        existentes: list[sqlite3.Row],
                        nuevas: list[tuple[int | None, dict[str, Leido]]],
                        lineas: dict[int, int]) -> list[str]:
    """Las filas de la cabecera (referencias sin linea, desglose de IVA, citas), por su posicion."""
    conflictos = []
    for fila, (_indice, valores) in zip(existentes, nuevas):
        o.fijar(tabla, fila["id"], valores)
    for fila in existentes[len(nuevas):]:
        conflictos += _retirar_si_no_es_de_persona(o, conn, tabla, fila)
    sobrantes = nuevas[len(existentes):]
    if tabla == "factura_referencia":
        _crear_hijas(o, factura_id, sobrantes, [], lineas)
    elif tabla == "factura_cita":
        _crear_hijas(o, factura_id, [], [], lineas, [v for _i, v in sobrantes])
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

