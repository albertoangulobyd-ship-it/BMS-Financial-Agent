"""Medicion de la precision de extraccion contra respuestas escritas a mano.

Esta es la salida de la fase 0. La condicion para pasar a la fase 1 es que
los campos criticos acierten al menos el 98 por ciento sobre un conjunto de
facturas reales.

Un campo que el documento no lleva y que la extraccion deja vacio cuenta
como acierto: reconocer una ausencia es la respuesta correcta.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .parsing import (
    ParseError,
    normalize_iban,
    parse_amount,
    parse_iso_date,
    parse_percentage,
)

# Los campos que decide la metrica de salida de la fase 0.
CRITICAL_FIELDS = (
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "vat_amount",
    "total_incl_vat",
    "service_period_start",
    "service_period_end",
)

# Nombre logico en el fichero de respuestas -> ruta en la extraccion.
_FIELD_SOURCE = {
    "supplier_name": "supplier_name",
    "supplier_address": "supplier_address",
    "kvk_number": "kvk_number",
    "vat_number": "vat_number",
    "invoice_number": "invoice_number",
    "invoice_date": "invoice_date",
    "service_period_start": "service_period_start",
    "service_period_end": "service_period_end",
    "subtotal_excl_vat": "subtotal_excl_vat_raw",
    "vat_rate": "vat_rate_raw",
    "vat_amount": "vat_amount_raw",
    "total_incl_vat": "total_incl_vat_raw",
    "vat_regime": "vat_regime",
    "iban": "iban",
    "due_date": "due_date",
}


def _cmp_text(expected: str, actual: str) -> bool:
    return " ".join(str(expected).split()).casefold() == " ".join(str(actual).split()).casefold()


def _cmp_amount(expected: str, actual: str) -> bool:
    try:
        return parse_amount(expected) == parse_amount(actual)
    except ParseError:
        return False


def _cmp_date(expected: str, actual: str) -> bool:
    try:
        return parse_iso_date(expected) == parse_iso_date(actual)
    except ParseError:
        return False


def _cmp_percentage(expected: str, actual: str) -> bool:
    """El tipo lleva el signo de porcentaje, que parse_amount no admite."""
    try:
        return parse_percentage(expected) == parse_percentage(actual)
    except ParseError:
        return False


def _cmp_iban(expected: str, actual: str) -> bool:
    try:
        return normalize_iban(expected) == normalize_iban(actual)
    except ParseError:
        return False


_COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "invoice_date": _cmp_date,
    "service_period_start": _cmp_date,
    "service_period_end": _cmp_date,
    "due_date": _cmp_date,
    "subtotal_excl_vat": _cmp_amount,
    "vat_amount": _cmp_amount,
    "total_incl_vat": _cmp_amount,
    "vat_rate": _cmp_percentage,
    "iban": _cmp_iban,
}


@dataclass
class FieldResult:
    field: str
    expected: Any
    actual: Any
    ok: bool


@dataclass
class DocumentScore:
    source_name: str
    fields: list[FieldResult]

    @property
    def mismatches(self) -> list[FieldResult]:
        return [f for f in self.fields if not f.ok]


@dataclass
class Report:
    documents: list[DocumentScore]

    def per_field(self) -> dict[str, tuple[int, int]]:
        """Por campo: (aciertos, total evaluado)."""
        tally: dict[str, list[int]] = {}
        for doc in self.documents:
            for result in doc.fields:
                entry = tally.setdefault(result.field, [0, 0])
                entry[1] += 1
                entry[0] += int(result.ok)
        return {k: (v[0], v[1]) for k, v in sorted(tally.items())}

    def critical_accuracy(self) -> Decimal:
        hits = total = 0
        for doc in self.documents:
            for result in doc.fields:
                if result.field in CRITICAL_FIELDS:
                    total += 1
                    hits += int(result.ok)
        if total == 0:
            return Decimal(0)
        return (Decimal(hits) / Decimal(total) * 100).quantize(Decimal("0.01"))


def load_ground_truth(path: str | Path) -> dict[str, dict[str, Any]]:
    """Lee las respuestas escritas a mano, indexadas por nombre de fichero."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: se esperaba un mapa de fichero a campos")
    return data


def score_document(
    source_name: str, extraction: dict[str, Any], expected: dict[str, Any]
) -> DocumentScore:
    """Compara una extraccion con su respuesta escrita a mano."""
    results: list[FieldResult] = []

    for field_name, expected_value in expected.items():
        source_key = _FIELD_SOURCE.get(field_name)
        if source_key is None:
            raise KeyError(
                f"{source_name}: campo desconocido en las respuestas: {field_name!r}"
            )

        actual_value = extraction.get(source_key)

        if expected_value is None or actual_value is None:
            # Ausencia esperada y ausencia detectada es un acierto.
            ok = expected_value is None and actual_value is None
        else:
            comparator = _COMPARATORS.get(field_name, _cmp_text)
            ok = comparator(expected_value, actual_value)

        results.append(
            FieldResult(
                field=field_name, expected=expected_value, actual=actual_value, ok=ok
            )
        )

    return DocumentScore(source_name=source_name, fields=results)


def format_report(report: Report) -> str:
    """Informe de texto. Es lo que se mira cada dia durante la fase 0."""
    lines: list[str] = []
    per_field = report.per_field()
    width = max((len(k) for k in per_field), default=10)

    lines.append("Precision por campo")
    lines.append("-" * (width + 22))
    for name, (hits, total) in per_field.items():
        pct = (hits / total * 100) if total else 0.0
        marker = "  " if name not in CRITICAL_FIELDS else "* "
        lines.append(f"{marker}{name.ljust(width)}  {hits:>3}/{total:<3}  {pct:6.2f}%")
    lines.append("")
    lines.append(f"Campos criticos (*): {report.critical_accuracy()}%  | objetivo 98.00%")
    lines.append(f"Documentos evaluados: {len(report.documents)}")

    failures = [(d.source_name, f) for d in report.documents for f in d.mismatches]
    if failures:
        lines.append("")
        lines.append(f"Discrepancias ({len(failures)})")
        lines.append("-" * (width + 22))
        for source_name, result in failures:
            lines.append(
                f"  {source_name} · {result.field}\n"
                f"      esperado: {result.expected!r}\n"
                f"      extraido: {result.actual!r}"
            )

    return "\n".join(lines)
