"""Primeras reglas del catalogo de validacion: las de aritmetica.

Son las reglas D2, D3 y D4 de validacion-facturas.md, y son las unicas que
se pueden aplicar hoy: no necesitan el planning ni el maestro de Exact, solo
lo que pone la propia factura.

Un dato que falta no es un fallo. Es un hallazgo distinto, y se distingue:
una regla sin los datos para evaluarse queda como no evaluable, no como
incumplida. Confundir las dos cosas llena el informe de rojos que no lo son.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .parsing import ParseError, parse_amount, parse_percentage

# Tolerancias de redondeo, en euros. Documentadas en validacion-facturas.md.
TOLERANCE_LINE = Decimal("0.01")
TOLERANCE_INVOICE = Decimal("0.02")


@dataclass(frozen=True)
class CheckResult:
    rule: str
    label: str
    status: str  # "ok" | "fallo" | "sin datos"
    detail: str

    @property
    def failed(self) -> bool:
        return self.status == "fallo"


def _amount(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return parse_amount(str(raw))
    except ParseError:
        return None


def _euros(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def check_lines_sum(extraction: dict[str, Any]) -> CheckResult:
    """D2: la suma de las lineas cuadra con la base imponible."""
    subtotal = _amount(extraction.get("subtotal_excl_vat_raw"))
    lines = extraction.get("lines") or []

    if subtotal is None:
        return CheckResult("D2", "Suma de líneas", "sin datos", "No hay base imponible legible.")
    if not lines:
        return CheckResult("D2", "Suma de líneas", "sin datos", "La factura no tiene líneas.")

    total = Decimal(0)
    for line in lines:
        value = _amount(line.get("line_total_raw"))
        if value is None:
            return CheckResult(
                "D2", "Suma de líneas", "sin datos",
                "Alguna línea no tiene importe legible.",
            )
        total += value

    tolerance = TOLERANCE_LINE * len(lines) + TOLERANCE_INVOICE
    difference = abs(total - subtotal)
    if difference <= tolerance:
        return CheckResult("D2", "Suma de líneas", "ok", f"{_euros(total)} = base imponible.")
    return CheckResult(
        "D2", "Suma de líneas", "fallo",
        f"Las líneas suman {_euros(total)} y la base dice {_euros(subtotal)}.",
    )


NO_VAT_REGIMES = {"reverse_charged", "kor_exempt"}


def check_vat_amount(extraction: dict[str, Any]) -> CheckResult:
    """D3: base por tipo da la cuota.

    Con IVA trasladado o con KOR no hay tipo que aplicar, y eso no es un dato
    que falte: es el estado correcto de la factura. Pero si en ese regimen
    aparece una cuota distinta de cero, eso si es la regla E4 incumplida.
    """
    regime = extraction.get("vat_regime")
    if regime in NO_VAT_REGIMES:
        charged = _amount(extraction.get("vat_amount_raw"))
        etiqueta = "IVA trasladado" if regime == "reverse_charged" else "KOR"
        if charged is not None and charged != 0:
            return CheckResult(
                "E4", "Cuota de IVA", "fallo",
                f"Con {etiqueta} no debería repercutirse IVA y la factura cobra {_euros(charged)}.",
            )
        return CheckResult(
            "D3", "Cuota de IVA", "no aplica",
            f"Sin IVA repercutido por el régimen declarado ({etiqueta}).",
        )

    subtotal = _amount(extraction.get("subtotal_excl_vat_raw"))
    vat = _amount(extraction.get("vat_amount_raw"))
    rate_raw = extraction.get("vat_rate_raw")

    rate = None
    if rate_raw is not None:
        try:
            rate = parse_percentage(str(rate_raw))
        except ParseError:
            rate = None

    if subtotal is None or vat is None or rate is None:
        return CheckResult("D3", "Cuota de IVA", "sin datos", "Falta la base, el tipo o la cuota.")

    expected = (subtotal * rate / Decimal(100)).quantize(Decimal("0.01"))
    if abs(expected - vat) <= TOLERANCE_INVOICE:
        return CheckResult("D3", "Cuota de IVA", "ok", f"{_euros(subtotal)} al {rate}% = {_euros(vat)}.")
    return CheckResult(
        "D3", "Cuota de IVA", "fallo",
        f"Al {rate}% deberían ser {_euros(expected)} y la factura dice {_euros(vat)}.",
    )


def check_total(extraction: dict[str, Any]) -> CheckResult:
    """D4: base mas cuota da el total."""
    subtotal = _amount(extraction.get("subtotal_excl_vat_raw"))
    vat = _amount(extraction.get("vat_amount_raw"))
    total = _amount(extraction.get("total_incl_vat_raw"))

    if subtotal is None or vat is None or total is None:
        return CheckResult("D4", "Total", "sin datos", "Falta la base, la cuota o el total.")

    expected = subtotal + vat
    if abs(expected - total) <= TOLERANCE_INVOICE:
        return CheckResult("D4", "Total", "ok", f"{_euros(subtotal)} + {_euros(vat)} = {_euros(total)}.")
    return CheckResult(
        "D4", "Total", "fallo",
        f"Base y cuota suman {_euros(expected)} y el total dice {_euros(total)}.",
    )


CRITICAL_FIELDS = {
    "supplier_name": "nombre del proveedor",
    "invoice_number": "número de factura",
    "invoice_date": "fecha de factura",
    "total_incl_vat_raw": "total",
}


def check_required_fields(extraction: dict[str, Any]) -> CheckResult:
    """Version reducida de A1, B1, C2 y D1: los campos sin los que no se puede seguir."""
    missing = [
        label for field, label in CRITICAL_FIELDS.items() if not extraction.get(field)
    ]
    if not missing:
        return CheckResult("A/B/C", "Campos obligatorios", "ok", "Están todos.")
    return CheckResult(
        "A/B/C", "Campos obligatorios", "fallo",
        "Falta " + ", ".join(missing) + ".",
    )


def run_checks(extraction: dict[str, Any]) -> list[CheckResult]:
    """Todas las comprobaciones que hoy se pueden hacer sin sistemas externos."""
    return [
        check_required_fields(extraction),
        check_lines_sum(extraction),
        check_vat_amount(extraction),
        check_total(extraction),
    ]
