"""El flujo de caja (paso 7): lo esperado por ventanas, lo movido y el estimado aparte.

Puerta del paso 7: las ventanas se prueban con un `hoy` fijo que cruza de
domingo a lunes (2026-10-18 -> 2026-10-19) y de fin de mes (2026-10-31 ->
2026-11-01). `hoy` se inyecta: nada de aqui mira el reloj.
"""

from __future__ import annotations

from datetime import date

import pytest
from conftest import CUENTA_PROPIA, apunte, camt053, cuentas_propias, factura_de, \
    importar_camt, persona

from bms_agent import flujo_caja, servicios
from bms_agent.flujo_caja import ENTRADA, SALIDA, Movido, Partida, calcular, direccion, ventanas
from bms_agent.reloj import mes_de, semana_de

DOMINGO = date(2026, 10, 18)
LUNES = date(2026, 10, 19)
FIN_DE_MES = date(2026, 10, 31)
PRIMERO = date(2026, 11, 1)


def _partidas() -> list[Partida]:
    return [
        Partida(1, SALIDA, date(2026, 10, 17), 1000),        # sabado
        Partida(2, SALIDA, DOMINGO, 2000),
        Partida(3, SALIDA, LUNES, 4000),
        Partida(4, ENTRADA, date(2026, 10, 25), 8000),        # domingo de la semana siguiente
        Partida(5, ENTRADA, FIN_DE_MES, 16000),
        Partida(6, SALIDA, PRIMERO, 32000),
        Partida(7, ENTRADA, date(2026, 11, 17), 64000),
        Partida(8, SALIDA, date(2026, 11, 18), 128000),
        Partida(9, ENTRADA, None, 256000),                    # sin vencimiento: no se adivina
    ]


def test_semana_y_mes_del_reloj() -> None:
    assert semana_de(DOMINGO) == (date(2026, 10, 12), DOMINGO)
    assert semana_de(LUNES) == (LUNES, date(2026, 10, 25))
    assert mes_de(FIN_DE_MES) == (date(2026, 10, 1), FIN_DE_MES)
    assert mes_de(PRIMERO) == (PRIMERO, date(2026, 11, 30))
    assert mes_de(date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))


def test_de_domingo_a_lunes_la_semana_empieza_otra_vez() -> None:
    domingo = calcular(_partidas(), [], DOMINGO)
    assert domingo["ventanas"]["semana"] == ["2026-10-18", "2026-10-18"]
    salida, entrada = domingo["esperado"]["salida"], domingo["esperado"]["entrada"]
    assert (salida["vencido"], salida["semana"]) == (1000, 2000)
    assert entrada["semana"] == 0
    lunes = calcular(_partidas(), [], LUNES)
    assert lunes["ventanas"]["semana"] == ["2026-10-19", "2026-10-25"]
    salida, entrada = lunes["esperado"]["salida"], lunes["esperado"]["entrada"]
    # Lo del domingo ya esta vencido; el lunes y el domingo siguiente son de esta semana.
    assert (salida["vencido"], salida["semana"]) == (3000, 4000)
    assert entrada["semana"] == 8000
    assert lunes["esperado"]["neto"]["semana"] == 8000 - 4000


def test_de_fin_de_mes_al_primero_el_mes_empieza_otra_vez() -> None:
    fin = calcular(_partidas(), [], FIN_DE_MES)
    assert fin["ventanas"]["mes"] == ["2026-10-31", "2026-10-31"]
    assert fin["ventanas"]["proximos_30"] == ["2026-10-31", "2026-11-29"]
    entrada, salida = fin["esperado"]["entrada"], fin["esperado"]["salida"]
    assert (entrada["mes"], salida["mes"]) == (16000, 0)
    assert (entrada["proximos_30"], salida["proximos_30"]) == (16000 + 64000, 32000 + 128000)
    assert entrada["vencido"] == 8000 and salida["vencido"] == 1000 + 2000 + 4000
    primero = calcular(_partidas(), [], PRIMERO)
    assert primero["ventanas"]["mes"] == ["2026-11-01", "2026-11-30"]
    entrada, salida = primero["esperado"]["entrada"], primero["esperado"]["salida"]
    assert (entrada["mes"], salida["mes"]) == (64000, 32000 + 128000)
    assert entrada["vencido"] == 8000 + 16000
    # Los proximos 30 dias cuentan hoy: del 1 al 30 de noviembre.
    assert primero["ventanas"]["proximos_30"] == ["2026-11-01", "2026-11-30"]


def test_el_total_lo_lleva_todo_y_lo_sin_fecha_va_aparte() -> None:
    resultado = calcular(_partidas(), [], LUNES)
    entrada, salida = resultado["esperado"]["entrada"], resultado["esperado"]["salida"]
    assert entrada["total"] == 8000 + 16000 + 64000 + 256000
    assert salida["total"] == 1000 + 2000 + 4000 + 32000 + 128000
    assert (entrada["sin_fecha"], salida["sin_fecha"]) == (256000, 0)
    assert resultado["esperado"]["neto"]["total"] == entrada["total"] - salida["total"]
    # Sin periodo pedido, la ventana no existe (no es cero).
    assert entrada["periodo"] is None and resultado["esperado"]["neto"]["periodo"] is None


def test_un_periodo_pedido_lleva_tambien_lo_que_vencio_en_el() -> None:
    resultado = calcular(_partidas(), [], LUNES, desde=date(2026, 10, 15),
                         hasta=date(2026, 10, 31))
    assert resultado["ventanas"]["periodo"] == ["2026-10-15", "2026-10-31"]
    entrada, salida = resultado["esperado"]["entrada"], resultado["esperado"]["salida"]
    assert (entrada["periodo"], salida["periodo"]) == (8000 + 16000, 1000 + 2000 + 4000)
    with pytest.raises(ValueError):
        calcular([], [], LUNES, desde=date(2026, 10, 15))
    with pytest.raises(ValueError):
        calcular([], [], LUNES, desde=date(2026, 10, 31), hasta=date(2026, 10, 1))


def test_lo_movido_de_la_semana_y_el_mes_hasta_hoy() -> None:
    movidos = [Movido(1, SALIDA, date(2026, 10, 11), 100),      # domingo de la semana pasada
               Movido(2, SALIDA, date(2026, 10, 12), 200),      # lunes de esta
               Movido(3, ENTRADA, DOMINGO, 400),
               Movido(4, ENTRADA, date(2026, 9, 30), 800)]       # el mes pasado
    domingo = calcular([], movidos, DOMINGO)
    assert domingo["real"]["ventanas"]["semana"] == ["2026-10-12", "2026-10-18"]
    assert (domingo["real"]["pagado"]["semana"], domingo["real"]["cobrado"]["semana"]) == (
        200, 400)
    assert (domingo["real"]["pagado"]["mes"], domingo["real"]["cobrado"]["mes"]) == (300, 400)
    lunes = calcular([], movidos, LUNES)
    assert (lunes["real"]["pagado"]["semana"], lunes["real"]["cobrado"]["semana"]) == (0, 0)
    primero = calcular([], movidos, PRIMERO)
    assert (primero["real"]["pagado"]["mes"], primero["real"]["cobrado"]["mes"]) == (0, 0)
    assert lunes["real"]["pagado"]["periodo"] is None


def test_el_estimado_va_aparte_y_sin_datos_no_es_cero() -> None:
    resultado = calcular(_partidas(), [], LUNES)
    assert resultado["estimado"]["importe_cent"] is None
    assert "planning" in resultado["estimado"]["nota"]


def test_la_direccion_de_cada_factura() -> None:
    assert direccion("entrante", 100) == SALIDA          # una compra se paga
    assert direccion("saliente", 100) == ENTRADA         # una venta se cobra
    assert direccion("entrante", -100) == ENTRADA        # un abono de un proveedor
    assert direccion("saliente", -100) == SALIDA         # un abono a un cliente
    assert ventanas(LUNES)["periodo"] is None


def test_el_flujo_del_almacen_con_un_pago_parcial(tipado) -> None:
    conn = tipado.conn
    ana = persona(conn, "Ana", "administrador")
    cuentas_propias(tipado, ana, CUENTA_PROPIA)
    antes = flujo_caja.flujo(conn, date(2026, 10, 14))
    # La USD (X1) no entra en ninguna suma; el abono de Van Dijk es una entrada.
    usd = factura_de(conn, "NW-2026-0042")
    partidas, _ = flujo_caja.datos(conn)
    assert usd not in {p.factura_id for p in partidas}
    abono = next(p for p in partidas if p.factura_id == factura_de(conn, "CN-2026-031"))
    assert (abono.direccion, abono.importe_cent) == (ENTRADA, 12251)
    # Ana apunta 1000 de la 2026-4471 (vence el 15): quedan 1902,79 esta semana.
    f = factura_de(conn, "2026-4471")
    servicios.ejecutar(conn, "marcar_pagada", {
        "factura_id": f, "importe": "1000,00", "fecha_pago": "2026-10-13",
        "rev": conn.execute("SELECT rev FROM factura WHERE id = ?", (f,)).fetchone()[0],
        "motivo": "Anticipo en efectivo"}, usuario_id=ana)
    despues = flujo_caja.flujo(conn, date(2026, 10, 14))
    assert (antes["esperado"]["salida"]["semana"] - despues["esperado"]["salida"]["semana"]
            ) == 100000
    assert despues["real"]["pagado"]["semana"] == 100000
    assert despues["estimado"]["importe_cent"] is None
    assert despues["fuentes"] == ["banco", "exact", "manual"]
    # Un movimiento que no casa con nada no es un pago de ninguna factura.
    importar_camt(tipado, ana, camt053(apunte("-5.00", "2026-10-13")))
    assert flujo_caja.flujo(conn, date(2026, 10, 14))["real"] == despues["real"]
