"""La base de las pruebas en el navegador se puede hacer cualquier dia (scripts/crear_demo_e2e.py).

El extracto de las pruebas necesita facturas abiertas que el escenario de la base de prueba no
tiene todos los dias (los lunes, a primeros y a fin de mes). El script elige el dia mas cercano
a hoy que las tiene con demo.facturas, que es puro: aqui se comprueba, dia a dia de 2026 a 2033,
que siempre hay uno a DIAS_ATRAS o menos; que el plan dice lo mismo que la base hecha de verdad;
y que los numeros por papel que reciben las pruebas existen en la base.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from bms_agent import demo
from bms_agent.reloj import RelojFijo

RAIZ = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("crear_demo_e2e",
                                                  RAIZ / "scripts" / "crear_demo_e2e.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


SCRIPT = _script()


def _reloj(dia: date) -> RelojFijo:
    return RelojFijo(datetime(dia.year, dia.month, dia.day, 10, tzinfo=timezone.utc))


def test_cualquier_dia_de_ocho_anos_tiene_uno_cerca_con_lo_que_pide_el_extracto():
    inicio, fin = date(2026, 1, 1), date(2033, 12, 31)
    dia = inicio - timedelta(days=SCRIPT.DIAS_ATRAS)
    bueno: dict[date, bool] = {}
    while dia <= fin:
        bueno[dia] = SCRIPT.falta_en_el_plan(_reloj(dia)) is None
        dia += timedelta(days=1)
    peor, sin_dia = 0, []
    dia = inicio
    while dia <= fin:
        atras = next((n for n in range(SCRIPT.DIAS_ATRAS + 1)
                      if bueno[dia - timedelta(days=n)]), None)
        if atras is None:
            sin_dia.append(dia)
        else:
            peor = max(peor, atras)
        dia += timedelta(days=1)
    assert sin_dia == []
    # Lo que dice el comentario de DIAS_ATRAS (y el registro): hasta 12 dias atras.
    assert peor == 12
    # Y hay dias en que hoy no basta (el problema existe; si desaparece, sobra la busqueda).
    assert not all(bueno.values())


@pytest.mark.parametrize(("dia", "falta"), [
    # Un lunes: la del puerto de la semana pasada aun no ha salido.
    (date(2026, 11, 9), "2 facturas abiertas del puerto, y hacen falta tres"),
    # A primeros de mes la del gemeentehuis se cobra "hoy".
    (date(2026, 11, 3), "ninguna factura abierta de el gemeentehuis (pendiente)"),
    (date(2026, 11, 10), None),
])
def test_el_plan_dice_lo_mismo_que_la_base_hecha(tmp_path, dia, falta):
    reloj = _reloj(dia)
    assert SCRIPT.falta_en_el_plan(reloj) == falta
    ruta = tmp_path / "demo.sqlite3"
    demo.crear(ruta, reloj=reloj, btw_sin_presentar=True)
    assert SCRIPT._falta_para_el_extracto(ruta) == falta
    if falta is None:
        conn = sqlite3.connect(ruta)
        try:
            numeros = {fila[0] for fila in conn.execute("SELECT numero FROM factura")}
            trimestres = dict(conn.execute(
                "SELECT ano || '-T' || trimestre, estado FROM periodo_btw").fetchall())
        finally:
            conn.close()
        papeles = SCRIPT.numeros_de_las_pruebas(reloj)
        # Cada numero por papel es una factura de esa base.
        for papel, valor in papeles.items():
            if papel == "vatQuarter":
                continue
            for numero in valor if isinstance(valor, list) else [valor]:
                assert numero in numeros, (papel, numero)
        # El ultimo trimestre terminado, listo y sin presentar aunque su plazo (31-10) paso; los
        # de antes, presentados.
        assert papeles["vatQuarter"] == "2026-T3"
        assert trimestres == {"2026-T1": "presentado", "2026-T2": "presentado",
                              "2026-T3": "listo_revision"}


def test_sin_la_opcion_la_base_de_prueba_presenta_lo_vencido(tmp_path):
    """`bms-agent demo crear` no cambia: lo que vencio, presentado."""
    ruta = tmp_path / "demo.sqlite3"
    demo.crear(ruta, reloj=_reloj(date(2026, 11, 10)))
    conn = sqlite3.connect(ruta)
    try:
        estados = {fila[0] for fila in conn.execute("SELECT estado FROM periodo_btw")}
    finally:
        conn.close()
    assert estados == {"presentado"}


def test_los_numeros_por_papel_salen_todos_los_dias_de_un_ano():
    dia = date(2026, 1, 1)
    while dia < date(2027, 1, 1):
        papeles = SCRIPT.numeros_de_las_pruebas(_reloj(dia))
        # Las pruebas usan tres de J. Voorbeeld antes de la repetida.
        assert len(papeles["voorbeeldEarlier"]) >= 3, dia
        assert papeles["testpersoonOld"] != papeles["testpersoonRecent"], dia
        dia += timedelta(days=1)


def test_dias_posibles_va_del_mas_cercano_al_mas_lejano():
    ahora = datetime(2026, 11, 9, 10, tzinfo=timezone.utc)
    posibles = SCRIPT.dias_posibles(ahora)
    assert posibles == sorted(posibles) and posibles[0] == 12
