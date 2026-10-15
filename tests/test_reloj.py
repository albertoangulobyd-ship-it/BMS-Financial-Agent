"""reloj.py: la semana ISO, que cruza el ano y de la que dependen B2 y el planning (paso 10)."""

from __future__ import annotations

from datetime import date

import pytest

from bms_agent.reloj import semana_iso


@pytest.mark.parametrize("dia, esperada", [
    (date(2026, 9, 15), "2026-W38"),
    (date(2027, 1, 1), "2026-W53"),        # el ano ISO no es el del dia
    (date(2027, 1, 3), "2026-W53"),
    (date(2027, 1, 4), "2027-W01"),
    (date(2024, 12, 30), "2025-W01"),      # ni hacia atras
    (date(2026, 1, 1), "2026-W01"),
    (date(2025, 12, 28), "2025-W52"),
    (date(2020, 12, 31), "2020-W53"),
    (date(2026, 3, 2), "2026-W10"),        # dos cifras siempre
])
def test_semana_iso(dia, esperada) -> None:
    assert semana_iso(dia) == esperada
