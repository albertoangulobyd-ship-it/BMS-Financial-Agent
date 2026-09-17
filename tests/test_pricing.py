"""El coste se estima con las tarifas publicadas, nunca se inventa."""

from __future__ import annotations

from decimal import Decimal

from bms_agent.pricing import estimate_cost, format_cost_summary


def test_estimacion_con_tarifa_conocida() -> None:
    # 1M de entrada a 5 y 1M de salida a 25 son 30 dolares.
    assert estimate_cost("claude-opus-5", 1_000_000, 1_000_000) == Decimal("30.000000")


def test_estimacion_proporcional() -> None:
    # 3.000 entrada + 1.000 salida en Opus 5: 0,015 + 0,025.
    assert estimate_cost("claude-opus-5", 3_000, 1_000) == Decimal("0.040000")


def test_sonnet_es_mas_barato_que_opus() -> None:
    opus = estimate_cost("claude-opus-5", 3_000, 1_000)
    sonnet = estimate_cost("claude-sonnet-5", 3_000, 1_000)
    haiku = estimate_cost("claude-haiku-4-5", 3_000, 1_000)
    assert haiku < sonnet < opus


def test_modelo_desconocido_no_inventa_precio() -> None:
    assert estimate_cost("modelo-que-no-existe", 1000, 1000) is None


def test_el_resumen_lo_dice_cuando_no_hay_tarifa() -> None:
    texto = format_cost_summary("modelo-que-no-existe", 3, 1000, 500)
    assert "no hay estimacion" in texto
    assert "$" not in texto


def test_el_resumen_proyecta_a_cien_documentos() -> None:
    texto = format_cost_summary("claude-opus-5", 10, 30_000, 10_000)
    assert "por cada 100" in texto
    assert "$4.00" in texto  # 0,04 por documento
