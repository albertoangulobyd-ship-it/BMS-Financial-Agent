"""La medicion de precision es la salida de la fase 0, asi que tiene tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from bms_agent.scoring import Report, format_report, score_document

EXTRACTION = {
    "supplier_name": "Bouwtechniek Van Dijk BV",
    "invoice_number": "2026-4471",
    "invoice_date": "2026-09-15",
    "vat_amount_raw": "1.835,40",
    "total_incl_vat_raw": "10.575,40",
    "service_period_start": "2026-08-31",
    "service_period_end": "2026-09-06",
    "iban": "NL02ABNA0123456789",
    "kvk_number": None,
}


def test_una_extraccion_correcta_puntua_entera() -> None:
    expected = {
        "supplier_name": "Bouwtechniek Van Dijk BV",
        "invoice_number": "2026-4471",
        "invoice_date": "2026-09-15",
        "vat_amount": "1.835,40",
        "total_incl_vat": "10.575,40",
    }
    score = score_document("f.pdf", EXTRACTION, expected)
    assert score.mismatches == []


def test_los_importes_se_comparan_por_valor_no_por_texto() -> None:
    """10575,40 y 10.575,40 son el mismo importe escrito de dos formas."""
    score = score_document("f.pdf", EXTRACTION, {"total_incl_vat": "10575,40"})
    assert score.fields[0].ok


def test_las_fechas_se_comparan_por_valor_no_por_formato() -> None:
    score = score_document("f.pdf", EXTRACTION, {"invoice_date": "15-09-2026"})
    assert score.fields[0].ok


def test_el_texto_ignora_mayusculas_y_espacios_sobrantes() -> None:
    score = score_document(
        "f.pdf", EXTRACTION, {"supplier_name": "bouwtechniek  van dijk bv"}
    )
    assert score.fields[0].ok


def test_el_iban_ignora_los_espacios() -> None:
    score = score_document("f.pdf", EXTRACTION, {"iban": "NL02 ABNA 0123 4567 89"})
    assert score.fields[0].ok


def test_detectar_una_ausencia_cuenta_como_acierto() -> None:
    """La factura no lleva KvK y la extraccion lo deja vacio: es correcto."""
    score = score_document("f.pdf", EXTRACTION, {"kvk_number": None})
    assert score.fields[0].ok


def test_inventar_un_campo_ausente_es_un_fallo() -> None:
    inventado = {**EXTRACTION, "kvk_number": "12345678"}
    score = score_document("f.pdf", inventado, {"kvk_number": None})
    assert not score.fields[0].ok


def test_omitir_un_campo_presente_es_un_fallo() -> None:
    score = score_document("f.pdf", EXTRACTION, {"kvk_number": "12345678"})
    assert not score.fields[0].ok


def test_confundir_millares_con_decimales_es_un_fallo() -> None:
    """El error que mas dinero cuesta tiene que contar como fallo."""
    mal = {**EXTRACTION, "total_incl_vat_raw": "10,57"}
    score = score_document("f.pdf", mal, {"total_incl_vat": "10.575,40"})
    assert not score.fields[0].ok


def test_un_campo_desconocido_en_las_respuestas_es_un_error() -> None:
    with pytest.raises(KeyError):
        score_document("f.pdf", EXTRACTION, {"campo_inventado": "x"})


def test_la_precision_critica_solo_cuenta_los_campos_criticos() -> None:
    expected = {
        "supplier_name": "Bouwtechniek Van Dijk BV",  # critico, acierta
        "invoice_number": "OTRO-NUMERO",              # critico, falla
        "iban": "NL99BANK0000000000",                 # no critico, falla
    }
    report = Report(documents=[score_document("f.pdf", EXTRACTION, expected)])
    assert report.critical_accuracy() == Decimal("50.00")


def test_el_informe_nombra_el_documento_y_el_campo_que_fallan() -> None:
    report = Report(
        documents=[score_document("f.pdf", EXTRACTION, {"invoice_number": "X-1"})]
    )
    text = format_report(report)
    assert "f.pdf" in text and "invoice_number" in text
    assert "objetivo 98.00%" in text


def test_el_tipo_de_iva_se_compara_con_y_sin_el_signo() -> None:
    """Regresion: '21%' contra '21%' se contaba como fallo."""
    extraction = {"vat_rate_raw": "21%"}
    assert score_document("f.pdf", extraction, {"vat_rate": "21%"}).fields[0].ok
    assert score_document("f.pdf", extraction, {"vat_rate": "21"}).fields[0].ok
    assert score_document("f.pdf", {"vat_rate_raw": "9%"}, {"vat_rate": "21%"}).fields[0].ok is False
