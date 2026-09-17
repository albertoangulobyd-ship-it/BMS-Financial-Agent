"""La conversion de importes es donde se pierde dinero sin que nadie lo vea."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from bms_agent.parsing import (
    ParseError,
    normalize_iban,
    parse_amount,
    parse_iso_date,
    parse_percentage,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Formato neerlandes: punto de millares, coma decimal.
        ("8.740,00", "8740.00"),
        ("1.234,56", "1234.56"),
        ("12.345.678,90", "12345678.90"),
        ("8740,00", "8740.00"),
        ("7,5", "7.5"),
        ("0,00", "0"),
        # Formato anglosajon: los dos separadores, el ultimo manda.
        ("8,740.00", "8740.00"),
        ("1,234.56", "1234.56"),
        # Un solo separador con una o dos cifras detras: decimal.
        ("1234.56", "1234.56"),
        ("37.5", "37.5"),
        # Un solo separador con tres cifras detras: millares.
        ("1.234", "1234"),
        ("1,234", "1234"),
        # Sin separador.
        ("8740", "8740"),
        # Moneda y espacios.
        ("€ 8.740,00", "8740.00"),
        ("EUR 1.234,56", "1234.56"),
        (" 8.740,00 ", "8740.00"),
        # Signos, incluido el negativo detras de algunos exportes contables.
        ("-1.234,56", "-1234.56"),
        ("1.234,56-", "-1234.56"),
        ("+1.234,56", "1234.56"),
    ],
)
def test_parse_amount(raw: str, expected: str) -> None:
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "abc",
        "1.2345",          # cuatro cifras tras el separador: ambiguo
        "1.23.456",        # agrupacion de millares invalida
        "12.34,567",       # cola decimal imposible
    ],
)
def test_parse_amount_rechaza_lo_ambiguo(raw: str) -> None:
    """Preferimos una factura retenida a un importe adivinado."""
    with pytest.raises(ParseError):
        parse_amount(raw)


def test_parse_amount_no_confunde_millares_con_decimales() -> None:
    """El caso que rompe un pago: 8.740,00 euros no son 8,74."""
    assert parse_amount("8.740,00") == Decimal("8740.00")
    assert parse_amount("8.740,00") != Decimal("8.74")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("21%", "21"), ("21 %", "21"), ("21,0%", "21.0"), ("9", "9"), ("0%", "0")],
)
def test_parse_percentage(raw: str, expected: str) -> None:
    assert parse_percentage(raw) == Decimal(expected)


def test_parse_percentage_rechaza_fuera_de_rango() -> None:
    with pytest.raises(ParseError):
        parse_percentage("210%")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-15", date(2026, 9, 15)),
        ("15-09-2026", date(2026, 9, 15)),
        ("15/09/2026", date(2026, 9, 15)),
        ("1-9-2026", date(2026, 9, 1)),
    ],
)
def test_parse_iso_date(raw: str, expected: date) -> None:
    assert parse_iso_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "15 september 2026", "2026-13-01", "31-02-2026"])
def test_parse_iso_date_rechaza_lo_que_no_resuelve(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_iso_date(raw)


def test_normalize_iban() -> None:
    assert normalize_iban("nl02 abna 0123 4567 89") == "NL02ABNA0123456789"
