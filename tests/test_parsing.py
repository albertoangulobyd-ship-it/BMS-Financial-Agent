"""La conversion de importes es donde se pierde dinero sin que nadie lo vea."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from bms_agent.parsing import (
    ParseError,
    detectar_moneda,
    es_unidad_hora,
    normalize_iban,
    parse_amount,
    parse_importe,
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


def test_iva_trasladado_no_cuenta_como_dato_ausente() -> None:
    """Una factura con btw verlegd no tiene tipo, y eso es lo correcto."""
    from bms_agent.checks import check_vat_amount

    resultado = check_vat_amount({
        "vat_regime": "reverse_charged", "vat_amount_raw": "0,00",
        "subtotal_excl_vat_raw": "1.520,00", "vat_rate_raw": None,
    })
    assert resultado.status == "no aplica"
    assert not resultado.failed


def test_cobrar_iva_con_traslado_de_deuda_es_un_fallo() -> None:
    """Regla E4: con el IVA trasladado no se puede repercutir."""
    from bms_agent.checks import check_vat_amount

    resultado = check_vat_amount({
        "vat_regime": "reverse_charged", "vat_amount_raw": "319,20",
        "subtotal_excl_vat_raw": "1.520,00", "vat_rate_raw": "21%",
    })
    assert resultado.failed
    assert resultado.rule == "E4"


def test_el_modulo_97_acepta_ibanes_reales() -> None:
    from bms_agent.checks import validar_iban

    assert validar_iban("NL91ABNA0417164300")
    assert validar_iban("NL91 ABNA 0417 1643 00")
    assert validar_iban("nl91abna0417164300")
    assert validar_iban("DE89370400440532013000")


def test_el_modulo_97_rechaza_lo_inventado() -> None:
    from bms_agent.checks import validar_iban

    assert not validar_iban("NL91ABNA0417164301")   # un digito cambiado
    assert not validar_iban("NL02ABNA0123456780")   # control incorrecto
    assert not validar_iban("")
    assert not validar_iban("NL91")
    assert not validar_iban("NL91ABNA04171643!!")


def test_la_aritmetica_de_linea_detecta_un_importe_mal() -> None:
    from bms_agent.checks import check_line_arithmetic

    bueno = check_line_arithmetic({"lines": [
        {"quantity_raw": "37,50", "unit_rate_raw": "42,50", "line_total_raw": "1.593,75"}]})
    assert bueno.status == "ok"

    malo = check_line_arithmetic({"lines": [
        {"quantity_raw": "37,50", "unit_rate_raw": "42,50", "line_total_raw": "1.953,75"}]})
    assert malo.failed


# --- moneda (X1) ---

@pytest.mark.parametrize(
    ("raw", "esperada"),
    [
        ("€ 8.740,00", "EUR"),
        ("1.234,56 EUR", "EUR"),
        ("2.500,00 euro", "EUR"),
        ("8.740,00", None),
        ("$2,500.00", "USD"),
        ("US$ 2,500.00", "USD"),
        ("USD 1,250.00", "USD"),
        ("C$ 10.00", "CAD"),
        ("£ 99.00", "GBP"),
        ("1.234,56 CHF", "CHF"),
        ("1.000,00 kr", "KR"),
        ("EUR 100,00 ($ 108.00)", "USD"),   # dos monedas: gana la que no es euro
        (None, None),
        # El codigo pegado a los digitos: con \b no habia limite de palabra.
        ("USD2,500.00", "USD"),
        ("2,500.00USD", "USD"),
        ("GBP99.00", "GBP"),
        ("CHF100.00", "CHF"),
        ("2.500,00EUR", "EUR"),
        # El prefijo del "$" decide el pais; uno desconocido no es USD.
        ("R$ 100", "BRL"),
        ("CAD$100", "CAD"),
        ("MX$ 5,00", "MXN"),
        ("XY$ 3.00", "$"),
    ],
)
def test_detectar_moneda(raw, esperada) -> None:
    assert detectar_moneda(raw) == esperada


@pytest.mark.parametrize("raw", ["$2,500.00", "USD 1.250,00", "£ 99.00", "1.000,00 kr",
                                 "USD2,500.00", "2,500.00USD", "CHF100.00", "R$ 100"])
def test_un_importe_en_otra_moneda_no_se_lee_como_euros(raw: str) -> None:
    """Antes "$2,500.00" daba 2500 y la factura sumaba como si fueran euros."""
    with pytest.raises(ParseError, match="no en euros"):
        parse_amount(raw)


def test_parse_importe_devuelve_el_valor_y_su_moneda() -> None:
    assert parse_importe("$2,500.00") == (Decimal("2500.00"), "USD")
    assert parse_importe("€ 8.740,00") == (Decimal("8740.00"), "EUR")
    assert parse_importe("8.740,00") == (Decimal("8740.00"), None)
    with pytest.raises(ParseError):
        parse_importe("USD 1.2345")


def test_el_euro_pegado_a_los_digitos_se_lee() -> None:
    assert parse_amount("2.500,00EUR") == Decimal("2500.00")
    assert parse_amount("EUR2.500,00") == Decimal("2500.00")


def test_parse_importe_lee_los_dolares_con_prefijo() -> None:
    """Antes "R$ 100" no se podia leer y la puntuacion no comparaba un BRL."""
    assert parse_importe("R$ 100") == (Decimal("100"), "BRL")
    assert parse_importe("CAD$100") == (Decimal("100"), "CAD")


def test_la_puntuacion_no_da_por_bueno_un_importe_sin_su_moneda() -> None:
    """Perder el "$" al copiar es perder lo que decide si suma en los totales."""
    from bms_agent.scoring import score_document

    def acierta(esperado, extraido):
        return score_document("f.pdf", {"total_incl_vat_raw": extraido},
                              {"total_incl_vat": esperado}).fields[0].ok

    assert acierta("$2,500.00", "$2,500.00")
    assert acierta("€ 1.234,56", "1.234,56")          # sin marcador cuenta como euro
    assert not acierta("$2,500.00", "2.500,00")


# --- horas ---

@pytest.mark.parametrize(
    "unidad", ["uur", "Uur", "uren", "UREN", "u", "u.", "uren (avond)", "manuren",
               "h", "hrs", "hours", "Std.", "uurtarief"],
)
def test_es_unidad_hora(unidad: str) -> None:
    assert es_unidad_hora(unidad)


@pytest.mark.parametrize("unidad", ["dag", "dagen", "stuk", "km", "m2", "week", "", None])
def test_lo_que_no_es_hora_no_cuenta_como_hora(unidad) -> None:
    assert not es_unidad_hora(unidad)


# --- etiquetas de IVA y moneda en las comprobaciones ---

def test_cobrar_iva_con_kor_es_e3_no_e4() -> None:
    """El catalogo llama E3 a la KOR con IVA; E4 es el traslado de la deuda."""
    from bms_agent.checks import check_vat_amount

    resultado = check_vat_amount({
        "vat_regime": "kor_exempt", "vat_amount_raw": "319,20",
        "subtotal_excl_vat_raw": "1.520,00", "vat_rate_raw": "21%",
    })
    assert resultado.failed
    assert resultado.rule == "E3"


def test_x1_marca_una_factura_en_dolares() -> None:
    from bms_agent.checks import check_currency, run_checks

    factura = {"subtotal_excl_vat_raw": "$2,500.00", "vat_amount_raw": "$0.00",
               "total_incl_vat_raw": "$2,500.00",
               "lines": [{"unit_rate_raw": "$125.00", "line_total_raw": "$2,500.00"}]}
    resultado = check_currency(factura)
    assert resultado.failed and resultado.rule == "X1"
    assert "USD" in resultado.detail
    assert "X1" in [c.rule for c in run_checks(factura) if c.failed]


def test_x1_mira_tambien_las_lineas() -> None:
    from bms_agent.checks import check_currency

    factura = {"total_incl_vat_raw": "1.000,00",
               "lines": [{"unit_rate_raw": "£ 50.00", "line_total_raw": "1.000,00"}]}
    assert check_currency(factura).failed


def test_x1_da_por_buena_una_factura_en_euros_y_no_evalua_sin_importes() -> None:
    from bms_agent.checks import check_currency

    assert check_currency({"total_incl_vat_raw": "€ 1.000,00", "lines": []}).status == "ok"
    assert check_currency({"total_incl_vat_raw": "1.000,00"}).status == "ok"
    assert check_currency({"lines": []}).status == "sin datos"


def test_x1_marca_el_codigo_pegado_a_los_digitos() -> None:
    """Con "USD2,500.00" en todos los importes, X1 decia "ok: Importes en euros"."""
    from bms_agent.checks import check_currency

    for literal in ("USD2,500.00", "2,500.00USD", "CHF100.00"):
        factura = {"total_incl_vat_raw": literal,
                   "lines": [{"unit_rate_raw": literal, "line_total_raw": literal}]}
        resultado = check_currency(factura)
        assert resultado.failed, literal


def test_x1_no_da_por_euros_lo_que_no_ha_podido_leer() -> None:
    """Sin marcador y sin ningun importe legible, la moneda no se sabe."""
    from bms_agent.checks import check_currency

    resultado = check_currency({"total_incl_vat_raw": "Fr. 2'500.00",
                                "lines": [{"line_total_raw": "Fr. 2'500.00"}]})
    assert resultado.status == "sin datos"
    assert check_currency({"total_incl_vat_raw": "€ 2.500,00x"}).status == "ok"
