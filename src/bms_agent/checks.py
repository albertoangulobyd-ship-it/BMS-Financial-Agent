"""Las comprobaciones de una factura sola, sobre el diccionario que escribe el extractor.

Son las reglas Q1 (en su version reducida), X1, D2, D2b, D3, D4, E3, E4 y F1
para el contrato v1 de siempre: el informe por fichas, el panel y
/api/datos las leen de aqui con estas etiquetas y estos textos, y la foto de
referencia no cambia. La aritmetica ya no vive aqui: cada funcion lee los
literales con parsing.py y llama a la comprobacion de fondo de reglas/, la
misma que el motor de reglas evalua sobre el almacen. Asi no hay dos
formas de sumar unas lineas.

Un dato que falta no es un fallo. Es un hallazgo distinto, y se distingue:
una regla sin los datos para evaluarse queda como no evaluable, no como
incumplida. Confundir las dos cosas llena el informe de rojos que no lo son.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .parsing import ParseError, detectar_moneda, parse_amount, parse_percentage
from .reglas import aritmetica, bancaria, calidad, iva
from .reglas.base import FALLO, NO_APLICA, SIN_DATOS, Comprobacion, Politica, euros_texto

# Tolerancias de redondeo, en euros. Documentadas en validacion-facturas.md;
# las del motor estan en reglas.base.Politica, con estos mismos valores.
TOLERANCE_LINE = Decimal("0.01")
TOLERANCE_INVOICE = Decimal("0.02")
POLITICA_V1 = Politica(tolerancia_linea=TOLERANCE_LINE, tolerancia_factura=TOLERANCE_INVOICE)

# El contrato v1 escribe los estados con espacio.
_ESTADO_V1 = {SIN_DATOS: "sin datos", NO_APLICA: "no aplica"}


@dataclass(frozen=True)
class CheckResult:
    rule: str
    label: str
    status: str  # "ok" | "fallo" | "sin datos" | "no aplica"
    detail: str

    @property
    def failed(self) -> bool:
        return self.status == "fallo"


def _v1(rule: str, label: str, comprobacion: Comprobacion) -> CheckResult:
    estado = comprobacion.resultado
    return CheckResult(rule, label, _ESTADO_V1.get(estado, estado), comprobacion.detalle)


def _amount(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return parse_amount(str(raw))
    except ParseError:
        return None


_euros = euros_texto


def check_lines_sum(extraction: dict[str, Any]) -> CheckResult:
    """D2: la suma de las lineas cuadra con la base imponible."""
    lineas = extraction.get("lines") or []
    importes = [_amount(linea.get("line_total_raw")) for linea in lineas]
    return _v1("D2", "Suma de líneas", aritmetica.suma_lineas(
        _amount(extraction.get("subtotal_excl_vat_raw")), importes, POLITICA_V1))


# El regimen v1 que no repercute IVA, y como lo llama el almacen.
NO_VAT_REGIMES = {"reverse_charged": "autoliquidacion", "kor_exempt": "kor"}


def check_vat_amount(extraction: dict[str, Any]) -> CheckResult:
    """D3: base por tipo da la cuota.

    Con IVA trasladado o con KOR no hay tipo que aplicar, y eso no es un dato
    que falte: es el estado correcto de la factura. Pero si en ese regimen
    aparece una cuota distinta de cero, eso si es una regla incumplida, y no
    la misma: E3 con la KOR, E4 con el IVA trasladado. Antes las dos salian
    como E4, y el catalogo y el panel no hablaban de lo mismo.
    """
    regime = extraction.get("vat_regime")
    if regime in NO_VAT_REGIMES:
        etiqueta = iva.ETIQUETA_REGIMEN[NO_VAT_REGIMES[regime]]
        charged = _amount(extraction.get("vat_amount_raw"))
        if charged is not None:
            comprobacion = iva.iva_indebido(etiqueta, charged)
            if comprobacion.resultado == FALLO:
                return _v1("E4" if regime == "reverse_charged" else "E3", "Cuota de IVA",
                           comprobacion)
        return _v1("D3", "Cuota de IVA", iva.sin_iva_por_regimen(etiqueta))

    rate_raw = extraction.get("vat_rate_raw")
    rate = None
    if rate_raw is not None:
        try:
            rate = parse_percentage(str(rate_raw))
        except ParseError:
            rate = None
    return _v1("D3", "Cuota de IVA", iva.cuota_por_tipo(
        _amount(extraction.get("subtotal_excl_vat_raw")),
        _amount(extraction.get("vat_amount_raw")), rate, POLITICA_V1))


def check_total(extraction: dict[str, Any]) -> CheckResult:
    """D4: base mas cuota da el total."""
    return _v1("D4", "Total", aritmetica.total(
        _amount(extraction.get("subtotal_excl_vat_raw")), _amount(extraction.get("vat_amount_raw")),
        _amount(extraction.get("total_incl_vat_raw")), POLITICA_V1))


CRITICAL_FIELDS = {
    "supplier_name": "nombre del proveedor",
    "invoice_number": "número de factura",
    "invoice_date": "fecha de factura",
    "total_incl_vat_raw": "total",
}


def check_required_fields(extraction: dict[str, Any]) -> CheckResult:
    """Version reducida de A1, B1, C2 y D1: los campos sin los que no se puede seguir.

    Es la del contrato v1, con su lista corta y su etiqueta "A/B/C". La Q1
    del motor (reglas/calidad.py) pide la lista entera del §7 por sentido.
    """
    return _v1("A/B/C", "Campos obligatorios", calidad.campos_que_faltan(
        [(label, bool(extraction.get(field))) for field, label in CRITICAL_FIELDS.items()]))


def run_checks(extraction: dict[str, Any]) -> list[CheckResult]:
    """Todas las comprobaciones que hoy se pueden hacer sin sistemas externos."""
    return [
        check_required_fields(extraction),
        check_line_arithmetic(extraction),
        check_lines_sum(extraction),
        check_vat_amount(extraction),
        check_total(extraction),
        check_iban(extraction),
        check_currency(extraction),
    ]


validar_iban = bancaria.validar_iban


def check_iban(extraction: dict[str, Any]) -> CheckResult:
    """F1: el IBAN impreso es sintacticamente valido."""
    return _v1("F1", "IBAN", bancaria.iban(extraction.get("iban")))


def check_line_arithmetic(extraction: dict[str, Any]) -> CheckResult:
    """D2b: cantidad por tarifa da el importe de cada linea."""
    lineas = extraction.get("lines") or []
    comprobacion, _fallidas = aritmetica.aritmetica_lineas(
        [(indice, _amount(l.get("quantity_raw")), _amount(l.get("unit_rate_raw")),
          _amount(l.get("line_total_raw"))) for indice, l in enumerate(lineas, start=1)],
        POLITICA_V1)
    return _v1("D2b", "Aritmetica de linea", comprobacion)


IMPORTES_CABECERA = ("subtotal_excl_vat_raw", "vat_amount_raw", "total_incl_vat_raw")
IMPORTES_LINEA = ("unit_rate_raw", "line_total_raw")


def _literales_de_importe(extraction: dict[str, Any]) -> list[str]:
    literales = [extraction.get(c) for c in IMPORTES_CABECERA]
    for linea in extraction.get("lines") or []:
        literales += [linea.get(c) for c in IMPORTES_LINEA]
    return [str(v) for v in literales if v not in (None, "")]


def check_currency(extraction: dict[str, Any]) -> CheckResult:
    """X1: la factura esta en euros.

    El esquema v1 no pide la moneda, asi que se mira el literal de cada
    importe con detectar_moneda. La moneda se decide para la factura entera,
    no importe a importe (reglas.calidad.moneda): por eso quien suma (panel,
    informe, proyeccion, simulador) mira en_euros y deja fuera la factura
    entera, no solo los literales con el marcador.

    Solo se da por buena cuando algun importe se lee como euro (con su
    marcador o sin ninguno, que es como imprime una factura neerlandesa). Si
    ningun literal se puede leer, no se sabe en que moneda esta: "sin datos",
    no un "ok" que nadie ha comprobado.
    """
    literales = _literales_de_importe(extraction)
    monedas = [detectar_moneda(v) for v in literales]
    otras = sorted({m for m in monedas if m not in (None, "EUR")})
    en_euro = "EUR" in monedas or any(_amount(v) is not None for v in literales)
    return _v1("X1", "Moneda", calidad.moneda(bool(literales), otras, en_euro))


def en_euros(extraction: dict[str, Any]) -> bool:
    """La factura puede entrar en una suma en euros: X1 no falla.

    Es el unico predicado que deben usar los agregados. Un literal sin
    marcador en una factura cuyo total dice "$" son dolares, no euros, y
    parse_amount, que solo ve un literal, no puede saberlo.
    """
    return not check_currency(extraction).failed
