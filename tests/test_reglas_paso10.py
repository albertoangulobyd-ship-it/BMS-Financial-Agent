"""Las reglas del paso 10 sin base: el planning contra lo facturado.

Las instantaneas llevan, ademas de lo de los pasos anteriores, los turnos
que valen (`turnos`), las fotos aceptadas del planning (`fotos_planning`),
lo conciliado de cada imputacion (`conciliaciones`) y los ciclos de
facturacion (`ciclos`). Hoy es el 2026-10-14 (test_reglas.HOY) salvo donde
se dice. Puertas del paso 10 que viven aqui:

- la comparacion elige su nivel: persona o Objeto, y dia, semana o periodo;
- la semana impresa sin ano en una factura de enero es la del ano anterior;
- la tolerancia: 0,25 h pasa y 0,26 h no;
- un turno cancelado no cuenta;
- el trabajo sin facturar aparece solo pasado el fin de su periodo y su gracia;
- un recargo de noche a su tarifa pactada no da G3;
- una foto mas nueva que cambia una semana facturada da V9 (y G7).

Los constructores y `escenarios()` los usa tambien test_pureza_reglas.py.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from decimal import Decimal

import pytest
from test_reglas import HOY, linea
from test_reglas_paso5 import lote
from test_reglas_paso8 import venta
from test_reglas_paso9 import compra, imp, inst, objeto, orden, tarifa

from bms_agent.reglas import catalogo, turnos
from bms_agent.reglas.base import (
    Ciclo,
    Conciliacion,
    FotoPlanning,
    Instantanea,
    Politica,
    Relacion,
    Turno,
)

LUNES = date(2026, 10, 5)                 # 2026-W41
OCTUBRE = (date(2026, 9, 1), date(2026, 12, 31))


# ------------------------------------------------------------ constructores

def turno(id_: int, fecha: date = LUNES, *, horas: int = 8000, estado: str = "validado",
          recurso: int | None = 5, objeto: int | None = 8, proveedor: int | None = 7,
          cliente: int | None = 3, nivel: str = "dia", dias: int = 1,
          tipo: str | None = None, facturable: bool | None = True, compra_e4: int | None = None,
          venta_e4: int | None = None, po: int | None = None, externo: str | None = None,
          importacion: int = 1, inicio: str | None = "07:00", fin: str | None = "15:00",
          servicio: str | None = None) -> Turno:
    """Un turno validado (o en el estado que se diga) del recurso 5 del proveedor 7, en el
    Objeto 8 del cliente 3."""
    aprobadas = horas if estado == "validado" else None
    realizadas = horas if estado in ("realizado", "validado") else None
    return Turno(id_, importacion, externo or f"D-{id_}", False, nivel, fecha, dias, inicio,
                 fin, horas, realizadas, aprobadas, estado, objeto, recurso, proveedor, cliente,
                 servicio, tipo, facturable, compra_e4, venta_e4, po)


def semanal(id_: int, lunes: date = LUNES, horas: int = 40000, dias: int = 5, **cambios) -> Turno:
    """Una fila de la exportacion semanal (el lunes de su semana y sus dias con horas)."""
    return turno(id_, lunes, horas=horas, nivel="semana", dias=dias, inicio=None, fin=None,
                 **cambios)


def foto(importacion: int = 1, desde: date = OCTUBRE[0], hasta: date = OCTUBRE[1],
         exportado: date = HOY, huecos: tuple[tuple[date, date], ...] = ()) -> FotoPlanning:
    return FotoPlanning(importacion, exportado, desde, hasta, huecos)


def ciclo(id_: int, *, cliente: int | None = 3, objeto_id: int | None = None,
          frecuencia: str = "semanal", ancla: date | None = date(2026, 1, 5), gracia: int = 3,
          desde: date | None = None, hasta: date | None = None) -> Ciclo:
    return Ciclo(id_, cliente, objeto_id, frecuencia, ancla, gracia, desde, hasta)


def conciliado(id_: int, imputacion: int, factura: int, t: Turno, horas: int | None = None,
               nivel: str = "recurso_dia") -> Conciliacion:
    return Conciliacion(id_, imputacion, factura, t,
                        turnos.horas_referencia(t) if horas is None else horas, nivel)


def trabajo(f, *, dia: date | None = LUNES, hasta: date | None = None, horas: int = 8000,
            recurso: int | None = 5, objeto_id: int | None = 8, tipo: str | None = None,
            tarifa_e4: int = 425000, semana: int | None = None, po: int | None = None,
            servicio: str | None = None, periodo: tuple[date, date] | bool = True):
    """La factura con una linea de trabajo (de id el de la factura por diez) de esos dias, y su
    imputacion (de id el de la linea mas mil). El periodo de la cabecera es el de la linea
    (`periodo` True), el que se diga, o el que ya tenia la factura (False)."""
    hasta = hasta or dia
    if periodo is True and dia is not None:
        f = dataclasses.replace(f, periodo_inicio=dia, periodo_fin=hasta)
    elif isinstance(periodo, tuple):
        f = dataclasses.replace(f, periodo_inicio=periodo[0], periodo_fin=periodo[1])
    una = linea(f.id * 10, cantidad_mil=horas, tarifa_e4=tarifa_e4,
                importe_cent=horas * tarifa_e4 // 100000,
                fecha_trabajo=dia if dia == hasta else None,
                fecha_inicio=dia if dia != hasta else None,
                fecha_fin=hasta if dia != hasta else None, semana_doc=semana)
    return dataclasses.replace(f, lineas=(una,), imputaciones=(
        imp(una.id + 1000, una.id, po=po, importe=una.importe_cent, objeto=objeto_id,
            recurso=recurso, horas=horas, turno=tipo, servicio=servicio),))


def plan(*facturas, turnos_=(), fotos=(foto(),), conciliaciones=(), ciclos=(), tarifas=(),
         ordenes=(), objetos=(), relaciones=(), lotes=(), politica: Politica | None = None,
         hoy: date = HOY) -> Instantanea:
    base = inst(*facturas, ordenes=ordenes, tarifas=tarifas, objetos=objetos,
                relaciones=relaciones, politica=politica)
    return dataclasses.replace(base, hoy=hoy, turnos=tuple(turnos_), fotos_planning=tuple(fotos),
                               conciliaciones=tuple(conciliaciones), ciclos=tuple(ciclos),
                               lotes=tuple(lotes))


def resultados(regla_id: str, instantanea: Instantanea) -> list:
    return list(catalogo.regla(regla_id).evaluar(instantanea))


def de(regla_id: str, instantanea: Instantanea, fila_id: int, tabla: str = "factura") -> list:
    return [r for r in resultados(regla_id, instantanea)
            if r.fila_id == fila_id and r.tabla == tabla]


def uno(regla_id: str, instantanea: Instantanea, fila_id: int, tabla: str = "factura"):
    [resultado] = de(regla_id, instantanea, fila_id, tabla)
    return resultado


def fallos(regla_id: str, instantanea: Instantanea) -> list:
    return [r for r in resultados(regla_id, instantanea) if r.resultado == "fallo"]


# ============================================================ sin planning

DEL_PLANNING = ("G1", "G2", "G4", "G5", "G7", "V1", "V3", "V5", "V6", "V8", "V9", "B5")


@pytest.mark.parametrize("regla_id", DEL_PLANNING)
def test_sin_ningun_planning_cada_regla_da_un_solo_sin_datos(regla_id) -> None:
    """Hasta que llega una importacion del planning: sin datos, nunca ok, y uno solo (no uno
    por factura, que llenaria la cache)."""
    instantanea = plan(trabajo(compra(1)), trabajo(venta(2)), fotos=())
    [r] = resultados(regla_id, instantanea)
    assert (r.resultado, r.tabla, r.fila_id) == ("sin_datos", "planning", 0)
    assert "planning" in r.detalle


def test_sin_planning_g6_conserva_lo_pactado_y_p8_p10_esperan() -> None:
    instantanea = plan(trabajo(compra(1), tipo="nacht"), fotos=(),
                       tarifas=[tarifa(1, 442500, proveedor=7, turno="nacht")],
                       ordenes=[orden(1, lado="proveedor", parte=7)])
    g6 = resultados("G6", instantanea)
    assert {(r.tabla, r.resultado) for r in g6} == {("factura", "ok"), ("planning", "sin_datos")}
    for regla_id in ("P8", "P10"):
        [r] = resultados(regla_id, instantanea)
        assert r.resultado == "sin_datos" and "planning" in r.detalle


# ============================================================ puerta: el nivel

def _nivel(f, instantanea: Instantanea) -> str:
    i = f.imputaciones[0]
    indice = turnos.Indice(instantanea.turnos)
    celda = turnos.celda_de(i, f.lineas[0], f, indice, turnos.de_la_parte(f))
    return celda.nivel


def test_la_comparacion_elige_el_nivel_mas_fino_de_los_dos_lados() -> None:
    diario = [turno(1, LUNES), turno(2, LUNES + timedelta(days=1)),
              turno(3, LUNES, recurso=6)]
    con_dias = plan(turnos_=diario)
    # Persona y dia: la linea es de un dia y el planning tiene sus turnos ese dia.
    assert _nivel(trabajo(compra(1)), con_dias) == "recurso_dia"
    # Sin persona (o una que el planning no tiene esos dias): el Objeto.
    assert _nivel(trabajo(compra(2), recurso=None), con_dias) == "objeto_dia"
    assert _nivel(trabajo(compra(3), recurso=99), con_dias) == "objeto_dia"
    # Una semana entera de lunes a domingo.
    assert _nivel(trabajo(compra(4), dia=LUNES, hasta=LUNES + timedelta(days=6)),
                  con_dias) == "recurso_semana"
    # Unos dias sueltos o un mes: el periodo.
    assert _nivel(trabajo(compra(5), dia=date(2026, 10, 1), hasta=date(2026, 10, 31)),
                  con_dias) == "recurso_periodo"
    # Un dia dentro de una semana de la que el planning solo tiene la fila semanal: la semana.
    semanas = plan(turnos_=[semanal(10)])
    assert _nivel(trabajo(compra(6), dia=LUNES + timedelta(days=2)), semanas) == "recurso_semana"
    assert _nivel(trabajo(compra(7), dia=LUNES + timedelta(days=2), recurso=None),
                  semanas) == "objeto_semana"


def test_cada_nivel_compara_sus_horas() -> None:
    diario = [turno(1, LUNES), turno(2, LUNES + timedelta(days=1)),
              turno(3, LUNES, recurso=6, horas=4000)]
    # La persona: 8 h el lunes (los 4 de otra persona no cuentan).
    assert uno("G2", plan(trabajo(compra(1)), turnos_=diario), 1).resultado == "ok"
    # El Objeto: el lunes son 12 h (las dos personas).
    r = uno("G2", plan(trabajo(compra(2), recurso=None, horas=8000), turnos_=diario), 2)
    assert r.resultado == "fallo" and r.valores["nivel"] == "objeto_dia"
    assert r.valores["validadas_mil"] == 12000
    assert uno("G2", plan(trabajo(compra(3), recurso=None, horas=12000), turnos_=diario),
               3).resultado == "ok"
    # La semana de la persona: 16 h, con la tolerancia de dos dias con turnos.
    semana = trabajo(compra(4), dia=LUNES, hasta=LUNES + timedelta(days=6), horas=16500)
    assert uno("G2", plan(semana, turnos_=diario), 4).resultado == "ok"
    semana = trabajo(compra(4), dia=LUNES, hasta=LUNES + timedelta(days=6), horas=16510)
    r = uno("G2", plan(semana, turnos_=diario), 4)
    assert r.resultado == "fallo" and r.valores["nivel"] == "recurso_semana"
    assert r.valores["tolerancia_mil"] == 500
    # El periodo: el mes entero.
    mes = trabajo(compra(5), dia=date(2026, 10, 1), hasta=date(2026, 10, 31), horas=16000)
    assert uno("G2", plan(mes, turnos_=diario), 5).resultado == "ok"


def test_la_fila_semanal_se_compara_con_todo_lo_facturado_de_su_semana() -> None:
    """La exportacion pivotada se lee por semanas: varias lineas de dias de esa semana suman
    contra la fila, y una linea que solo cae en parte en la semana no la puede partir."""
    fila = semanal(10, horas=40000)
    f = compra(1)
    lineas = tuple(linea(10 + n, cantidad_mil=8000, fecha_trabajo=LUNES + timedelta(days=n))
                   for n in range(5))
    f = dataclasses.replace(f, lineas=lineas, imputaciones=tuple(
        imp(l.id + 1000, l.id, objeto=8, recurso=5, horas=8000) for l in lineas))
    [r] = de("G2", plan(f, turnos_=[fila]), 1)
    assert r.resultado == "ok" and "2026-W41" in r.detalle
    partida = trabajo(compra(2), dia=LUNES + timedelta(days=3), hasta=LUNES + timedelta(days=9))
    r = uno("G2", plan(partida, turnos_=[fila]), 2)
    assert r.resultado == "sin_datos" and "no se pueden partir" in r.detalle


# ============================================================ puerta: el ano ISO

def test_la_semana_52_de_una_factura_de_enero_es_la_del_ano_anterior() -> None:
    assert turnos.semana_impresa(52, date(2027, 1, 6)) == date(2026, 12, 21)
    assert turnos.semana_impresa(52, date(2026, 1, 6)) == date(2025, 12, 22)
    # 2026 tiene 53 semanas: la 53 facturada en enero de 2027 es la de 2026.
    assert turnos.semana_impresa(53, date(2027, 1, 6)) == date(2026, 12, 28)
    # Por adelantado: la semana 1 facturada el 30 de diciembre es la de 2027.
    assert turnos.semana_impresa(1, date(2026, 12, 30)) == date(2027, 1, 4)
    # Una semana 53 que no tiene ningun ano cercano no da dias: la linea va por el periodo.
    assert turnos.semana_impresa(53, date(2028, 1, 10)) is None


def test_una_factura_del_6_de_enero_por_la_semana_52_se_compara_con_esa_semana() -> None:
    semana_52 = [turno(n, date(2026, 12, 21) + timedelta(days=n)) for n in range(5)]
    otra_52 = [turno(10 + n, date(2027, 12, 27) + timedelta(days=n)) for n in range(2)]
    f = trabajo(compra(1, fecha_factura=date(2027, 1, 6), periodo_inicio=None,
                       periodo_fin=None), dia=None, semana=52, horas=40000)
    instantanea = plan(f, turnos_=semana_52 + otra_52,
                       fotos=(foto(desde=date(2026, 12, 1), hasta=date(2027, 12, 31)),),
                       hoy=date(2027, 1, 8))
    r = uno("G2", instantanea, 1)
    assert r.resultado == "ok" and "2026-W52" in r.detalle
    # Ni G5 se queja de la semana: la linea no trae fechas que la contradigan.
    assert [x.resultado for x in de("G5", instantanea, 1)] == ["ok"]
    # Con 32 h facturadas faltan 8: es la semana de 2026 la que se compara.
    menos = dataclasses.replace(f, imputaciones=(dataclasses.replace(f.imputaciones[0],
                                                                     horas_mil=32000),))
    r = uno("G2", dataclasses.replace(instantanea, facturas=(menos,)), 1)
    assert r.resultado == "fallo" and r.valores["desde"] == "2026-12-21"


def test_la_semana_impresa_que_no_es_la_de_sus_fechas_es_g5() -> None:
    f = trabajo(compra(1), semana=40)
    r = [x for x in de("G5", plan(f, turnos_=[turno(1)]), 1) if x.clave.startswith("semana")]
    assert [x.resultado for x in r] == ["fallo"]
    assert "2026-W41" in r[0].detalle


# ============================================================ puerta: la tolerancia

@pytest.mark.parametrize("facturadas, esperado", [
    (8250, "ok"), (8260, "fallo"), (7750, "ok"), (7740, "fallo"), (8000, "ok")])
def test_la_tolerancia_es_de_0_25_horas_por_dia(facturadas, esperado) -> None:
    instantanea = plan(trabajo(compra(1), horas=facturadas), trabajo(venta(2), horas=facturadas),
                       turnos_=[turno(1)])
    assert uno("G2", instantanea, 1).resultado == esperado
    assert uno("V1", instantanea, 2).resultado == esperado


def test_la_tolerancia_sale_de_la_politica() -> None:
    politica = Politica(planning_tolerancia_horas_dia=Decimal("0.5"))
    instantanea = plan(trabajo(compra(1), horas=8400), turnos_=[turno(1)], politica=politica)
    assert uno("G2", instantanea, 1).resultado == "ok"


def test_un_turno_sin_validar_da_sin_datos_en_g2() -> None:
    instantanea = plan(trabajo(compra(1)), turnos_=[turno(1, estado="realizado")])
    r = uno("G2", instantanea, 1)
    assert r.resultado == "sin_datos" and "sin validar" in r.detalle


# ============================================================ puerta: los cancelados

def test_un_turno_cancelado_no_cuenta() -> None:
    cancelado = turno(2, horas=8000, estado="cancelado", externo="D-cancelado")
    instantanea = plan(trabajo(compra(1)), trabajo(venta(2)), turnos_=[turno(1), cancelado])
    assert uno("G2", instantanea, 1).resultado == "ok"
    assert uno("V1", instantanea, 2).resultado == "ok"
    # Solo cancelados: para G1 no hay ningun turno del proveedor.
    solo = plan(trabajo(compra(3)), turnos_=[cancelado])
    assert uno("G1", solo, 3).resultado == "fallo"
    # Ni lo cuenta V6 como trabajo sin facturar.
    viejo = dataclasses.replace(cancelado, fecha=date(2026, 8, 3))
    assert fallos("V6", plan(turnos_=[viejo])) == []
    assert turnos.horas_referencia(cancelado) == 0


# ============================================================ G1

def test_g1_sin_turnos_del_proveedor_retiene_y_con_el_planning_obligatorio_bloquea() -> None:
    f = trabajo(compra(1))
    sin = plan(f, turnos_=[turno(1, proveedor=99, recurso=6)])
    r = uno("G1", sin, 1)
    assert r.resultado == "fallo" and r.severidad is None
    assert catalogo.regla("G1").severidad == "retencion"
    obligatorio = dataclasses.replace(sin, politica=Politica(planning_obligatorio=True))
    r = uno("G1", obligatorio, 1)
    assert r.resultado == "fallo" and r.severidad == "bloqueo"
    # Anularlo pide una segunda firma.
    assert catalogo.regla("G1").segunda_firma
    assert uno("G1", plan(f, turnos_=[turno(1)]), 1).resultado == "ok"


def test_g1_con_dias_que_el_planning_no_cubre_da_sin_datos() -> None:
    f = trabajo(compra(1))
    r = uno("G1", plan(f, fotos=(foto(desde=date(2026, 11, 1)),)), 1)
    assert r.resultado == "sin_datos" and "no cubre" in r.detalle


def test_con_el_planning_caducado_nada_es_ok() -> None:
    viejo = (lote(1, "trnsprnt", "planning", exportado=date(2026, 9, 1)),)
    instantanea = plan(trabajo(compra(1)), turnos_=[turno(1)], lotes=viejo)
    for regla_id in ("G1", "G2"):
        r = uno(regla_id, instantanea, 1)
        assert r.resultado == "sin_datos" and "frescura" in r.detalle


# ============================================================ G4 y V2: el Objeto

def test_g4_propone_el_objeto_del_planning_sin_tocar_la_linea() -> None:
    f = trabajo(compra(1), objeto_id=None)
    instantanea = plan(f, turnos_=[turno(1, objeto=9)], objetos=[objeto(8), objeto(9)])
    r = uno("G4", instantanea, 1)
    assert r.resultado == "fallo" and r.valores["propuesta"] == 9
    assert "OBJ9" in r.detalle and "cambiar_objeto" in r.detalle
    assert f.imputaciones[0].objeto_id is None
    # Con la persona en dos Objetos ese dia, no se elige: se ensenan los dos.
    dos = plan(f, turnos_=[turno(1, objeto=9), turno(2, objeto=8, inicio="16:00")],
               objetos=[objeto(8), objeto(9)])
    r = uno("G4", dos, 1)
    assert r.valores["propuesta"] is None and r.valores["candidatos"] == [8, 9]


def test_g4_un_objeto_que_no_es_el_del_planning_retiene() -> None:
    instantanea = plan(trabajo(compra(1), objeto_id=8), turnos_=[turno(1, objeto=9)],
                       objetos=[objeto(8), objeto(9)])
    r = uno("G4", instantanea, 1)
    assert r.resultado == "fallo" and r.valores["planning"] == [9]
    assert uno("G4", plan(trabajo(compra(2)), turnos_=[turno(1)]), 2).resultado == "ok"


def test_v2_no_espera_al_planning_salvo_para_proponer() -> None:
    sin_objeto = trabajo(venta(1), objeto_id=None)
    r = uno("V2", plan(sin_objeto, trabajo(venta(2)), fotos=(), objetos=[objeto(8)]), 1)
    assert r.resultado == "fallo" and r.valores == {"objeto": None}
    assert uno("V2", plan(trabajo(venta(2)), fotos=(), objetos=[objeto(8)]), 2).resultado == "ok"


def test_v2_el_objeto_es_del_cliente_y_estaba_activo() -> None:
    objetos = [objeto(8), objeto(9, cliente_id=4),
               dataclasses.replace(objeto(10), activo_hasta=date(2026, 9, 30))]
    ventas = [trabajo(venta(1)), trabajo(venta(2), objeto_id=9),
              trabajo(venta(3), objeto_id=10), trabajo(venta(4), objeto_id=None)]
    instantanea = plan(*ventas, turnos_=[turno(1)], objetos=objetos)
    assert uno("V2", instantanea, 1).resultado == "ok"
    assert "otro cliente" in uno("V2", instantanea, 2).detalle
    assert "no estaba activo" in uno("V2", instantanea, 3).detalle
    r = uno("V2", instantanea, 4)
    assert r.resultado == "fallo" and r.valores["propuesta"] == 8


# ============================================================ G5 y V3: otra fecha

def test_lo_facturado_en_un_dia_sin_turnos_con_trabajo_cerca_es_g5() -> None:
    instantanea = plan(trabajo(compra(1), dia=LUNES + timedelta(days=7)), turnos_=[turno(1)])
    r = uno("G5", instantanea, 1)
    assert r.resultado == "fallo" and r.valores["semanas"] == ["2026-W41"]
    # Ese trabajo ya facturado (conciliado con otra factura) no es otra fecha.
    ya = conciliado(1, 9999, 99, turno(1))
    otra = dataclasses.replace(instantanea, conciliaciones=(ya,), facturas=(
        *instantanea.facturas, trabajo(compra(99, numero_norm="C99"))))
    assert uno("G5", otra, 1).resultado == "ok"


# ============================================================ G6: los recargos

def test_un_recargo_de_noche_a_su_tarifa_pactada_no_da_g3() -> None:
    noche = trabajo(compra(1), tipo="nacht", tarifa_e4=442500, horas=7500)
    dia = trabajo(compra(2, numero_norm="C2"), tarifa_e4=385000, dia=LUNES + timedelta(days=1))
    tarifas = [tarifa(1, 385000, proveedor=7), tarifa(2, 442500, proveedor=7, turno="nacht")]
    planning = [turno(1, horas=7500, tipo="nacht", inicio="23:00", fin="07:00",
                      compra_e4=442500),
                turno(2, LUNES + timedelta(days=1), compra_e4=385000)]
    instantanea = plan(noche, dia, turnos_=planning, tarifas=tarifas)
    assert fallos("G3", instantanea) == []
    assert {r.resultado for r in de("G6", instantanea, 1)} == {"ok"}
    # Sin tarifa pactada, la del turno en el planning (la misma): tampoco.
    sin_pactada = dataclasses.replace(instantanea, tarifas=())
    assert fallos("G3", sin_pactada) == []
    assert [r.clave for r in de("G3", sin_pactada, 1)] == ["turno:1010"]


def test_horas_de_noche_que_el_planning_tiene_de_dia_son_g6() -> None:
    noche = trabajo(compra(1), tipo="nacht", tarifa_e4=442500)
    instantanea = plan(noche, turnos_=[turno(1)],
                       tarifas=[tarifa(2, 442500, proveedor=7, turno="nacht")])
    [r] = [x for x in de("G6", instantanea, 1) if x.clave.startswith("recargo")]
    assert r.resultado == "fallo" and r.valores["planificadas_mil"] == 0


def test_g3_contra_la_tarifa_del_turno_cuando_no_hay_pactada() -> None:
    cara = trabajo(compra(1), tarifa_e4=450000)
    instantanea = plan(cara, turnos_=[turno(1, compra_e4=400000)])
    [r] = [x for x in de("G3", instantanea, 1) if x.clave.startswith("turno")]
    assert r.resultado == "fallo" and r.valores["turno_e4"] == 400000
    # Turnos de la celda con tarifas distintas: no se adivina.
    dos = plan(cara, turnos_=[turno(1, compra_e4=400000), turno(2, recurso=5, inicio="16:00",
                                                                compra_e4=410000)])
    assert not [x for x in de("G3", dos, 1) if x.clave.startswith("turno")]


def test_v4_sin_pactada_contra_la_tarifa_de_venta_del_turno() -> None:
    barata = trabajo(venta(1), tarifa_e4=500000)
    instantanea = plan(barata, turnos_=[turno(1, venta_e4=520000)])
    [r] = de("V4", instantanea, 1)
    assert r.resultado == "fallo" and "por debajo" in r.detalle
    [r] = de("V4", plan(barata, turnos_=[turno(1)]), 1)
    assert r.resultado == "sin_datos"


# ============================================================ G7 y V9: el planning cambio

def test_una_foto_mas_nueva_que_cambia_una_semana_facturada_da_v9_y_g7() -> None:
    semana = (LUNES, LUNES + timedelta(days=6))
    antes = [turno(n + 1, LUNES + timedelta(days=n), importacion=1) for n in range(5)]
    f = trabajo(venta(1), dia=semana[0], hasta=semana[1], horas=40000)
    g = trabajo(compra(2), dia=semana[0], hasta=semana[1], horas=40000)
    conciliaciones = [conciliado(n + 1, 1010, 1, t, nivel="recurso_semana")
                      for n, t in enumerate(antes)]
    conciliaciones += [conciliado(n + 10, 1020, 2, t, nivel="recurso_semana")
                       for n, t in enumerate(antes)]
    fotos = (foto(1), foto(2))
    igual = plan(f, g, turnos_=antes, fotos=fotos, conciliaciones=conciliaciones)
    assert uno("V9", igual, 1).resultado == "ok"
    assert uno("G7", igual, 2).resultado == "ok"
    # La foto 2 cambia el viernes: 6 h en vez de 8.
    despues = antes[:4] + [dataclasses.replace(antes[4], id=6, importacion_id=2,
                                               horas_aprobadas_mil=6000,
                                               horas_realizadas_mil=6000)]
    cambiada = dataclasses.replace(igual, turnos=tuple(despues))
    r = uno("V9", cambiada, 1)
    assert r.resultado == "fallo" and "otras horas" in r.detalle
    assert r.valores["fotos"] == [1]
    assert catalogo.regla("V9").severidad == "retencion"
    assert uno("G7", cambiada, 2).resultado == "fallo"
    # Un turno cancelado en la foto nueva tambien.
    cancelada = dataclasses.replace(igual, turnos=tuple(
        antes[:4] + [dataclasses.replace(antes[4], estado="cancelado", importacion_id=2)]))
    assert "se cancelaron" in uno("V9", cancelada, 1).detalle


# ============================================================ V5, V6 y V8: sin facturar

def test_v5_turnos_del_periodo_facturado_que_ninguna_linea_cubre() -> None:
    f = trabajo(venta(1), periodo=(LUNES, LUNES + timedelta(days=6)))
    martes = turno(2, LUNES + timedelta(days=1), venta_e4=520000)
    instantanea = plan(f, turnos_=[turno(1), martes])
    r = uno("V5", instantanea, 1)
    assert r.resultado == "fallo" and r.valores["turnos"] == ["D-2"]
    assert (r.valores["valor_cent"], r.valores["estimado"]) == (41600, True)
    assert uno("V5", plan(f, turnos_=[turno(1)]), 1).resultado == "ok"


@pytest.mark.parametrize("hoy, aparece", [(date(2026, 10, 14), False), (date(2026, 10, 15), True)])
def test_el_trabajo_sin_facturar_aparece_pasado_su_periodo_y_su_gracia(hoy, aparece) -> None:
    """Sin ciclo, el mes natural y los dias de gracia de la politica (14): lo de septiembre
    aparece el 15 de octubre, no antes."""
    sin_facturar = turno(1, date(2026, 9, 10), venta_e4=520000)
    instantanea = plan(turnos_=[sin_facturar], hoy=hoy)
    v6 = fallos("V6", instantanea)
    assert bool(v6) == aparece
    if aparece:
        [r] = v6
        assert (r.tabla, r.fila_id) == ("cliente", 3)
        assert r.valores["gracia_hasta"] == "2026-10-14"
        assert (r.valores["valor_cent"], r.valores["estimado"]) == (41600, True)


def test_v6_valora_a_la_tarifa_pactada_y_sigue_el_ciclo() -> None:
    sin_facturar = turno(1, date(2026, 10, 1), venta_e4=520000)
    semanal_ = ciclo(1, frecuencia="semanal", ancla=date(2026, 1, 5), gracia=3)
    instantanea = plan(turnos_=[sin_facturar], ciclos=[semanal_],
                       tarifas=[tarifa(3, 500000, sentido="venta", cliente=3)])
    [r] = fallos("V6", instantanea)
    assert (r.valores["desde"], r.valores["hasta"]) == ("2026-09-28", "2026-10-04")
    assert (r.valores["valor_cent"], r.valores["estimado"]) == (40000, False)
    # Lo que ya cobra una venta del Objeto no esta sin facturar.
    cobrada = trabajo(venta(1), dia=date(2026, 10, 1),
                      periodo=(date(2026, 9, 28), date(2026, 10, 4)))
    assert fallos("V6", dataclasses.replace(instantanea, facturas=(cobrada,))) == []


def test_v8_un_periodo_de_un_ciclo_con_trabajo_y_sin_factura() -> None:
    trabajo_ = [turno(1, date(2026, 9, 29)), turno(2, date(2026, 10, 6))]
    semanal_ = ciclo(1, frecuencia="semanal", ancla=date(2026, 1, 5), gracia=3)
    facturada = trabajo(venta(1), dia=date(2026, 9, 29),
                        periodo=(date(2026, 9, 28), date(2026, 10, 4)))
    instantanea = plan(facturada, turnos_=trabajo_, ciclos=[semanal_],
                       fotos=(foto(desde=date(2026, 9, 28)),))
    # La semana del 5 de octubre acaba el 11, y con sus 3 dias de gracia el 14: aun no.
    assert fallos("V8", instantanea) == []
    [r] = fallos("V8", dataclasses.replace(instantanea, hoy=date(2026, 10, 15)))
    assert (r.tabla, r.fila_id, r.clave) == ("cliente", 3, "ciclo:1:2026-10-05")


# ============================================================ B5 y V7: dos veces

def test_las_mismas_horas_de_un_turno_en_dos_compras_es_b5() -> None:
    t = turno(1)
    a, b = trabajo(compra(1)), trabajo(compra(2, numero_norm="C2"))
    conciliaciones = [conciliado(1, 1010, 1, t), conciliado(2, 1020, 2, t)]
    instantanea = plan(a, b, turnos_=[t], conciliaciones=conciliaciones)
    r = fallos("B5", instantanea)
    assert {x.fila_id for x in r} == {1, 2} and r[0].grupo == "turno:D-1"
    # Un abono entre las dos lo explica.
    enlazadas = dataclasses.replace(instantanea, relaciones=(Relacion(2, 1, "sustituye", id=1),))
    assert fallos("B5", enlazadas) == []
    # En ventas, el mismo caso es V7.
    ventas = plan(trabajo(venta(3)), trabajo(venta(4, numero_norm="V4")), turnos_=[t],
                  conciliaciones=[conciliado(3, 1030, 3, t), conciliado(4, 1040, 4, t)])
    assert {x.fila_id for x in fallos("V7", ventas) if x.valores.get("caso") == "turno"} == {3, 4}


# ============================================================ P7, P8 y P10

def test_p8_y_p10_cuentan_el_trabajo_del_planning() -> None:
    po = orden(1, valor=100000)
    futuro = [turno(n, HOY + timedelta(days=n), venta_e4=500000, po=1) for n in range(1, 4)]
    instantanea = plan(turnos_=futuro, ordenes=[po])
    p8 = uno("P8", instantanea, 1, "orden_compra")
    assert p8.resultado == "fallo" and "1.200,00" in p8.detalle
    p10 = uno("P10", instantanea, 1, "orden_compra")
    assert p10.resultado == "fallo" and p10.valores["esperado_cent"] == 120000
    # Lo trabajado hasta hoy sin facturar cuenta en P10, no en P8.
    pasado = [turno(n, HOY - timedelta(days=n), venta_e4=500000, po=1) for n in range(1, 4)]
    instantanea = plan(turnos_=pasado, ordenes=[po])
    assert uno("P8", instantanea, 1, "orden_compra").resultado == "ok"
    assert uno("P10", instantanea, 1, "orden_compra").resultado == "fallo"


def test_p7_una_po_caducada_con_trabajo_despues_de_su_fin() -> None:
    po = orden(1, fin=date(2026, 10, 1), valor=100000)
    instantanea = plan(turnos_=[turno(1, date(2026, 10, 5), po=1)], ordenes=[po])
    r = uno("P7", instantanea, 1, "orden_compra")
    assert r.resultado == "fallo" and r.valores["turnos_despues"] == 1
    assert uno("P7", plan(ordenes=[po]), 1, "orden_compra").resultado == "ok"
    assert uno("P7", plan(ordenes=[po], fotos=()), 1, "orden_compra").resultado == "sin_datos"


# ============================================================ revision del paso 10

def test_unas_horas_en_la_columna_de_validadas_de_un_turno_planificado_no_estan_validadas() -> None:
    """Lo que dice si unas horas estan validadas es el estado: una fila semanal planificada con
    su total en esa columna no hace buenas las 40 h facturadas."""
    planificada = dataclasses.replace(semanal(1, estado="planificado"), horas_aprobadas_mil=40000)
    semana = (LUNES, LUNES + timedelta(days=6))
    instantanea = plan(trabajo(compra(1), dia=semana[0], hasta=semana[1], horas=40000),
                       trabajo(venta(2), dia=semana[0], hasta=semana[1], horas=40000),
                       turnos_=[planificada])
    for regla_id, factura_id in (("G2", 1), ("V1", 2)):
        r = uno(regla_id, instantanea, factura_id)
        assert r.resultado == "sin_datos" and "sin validar" in r.detalle
    assert turnos.horas_validadas(planificada) is None
    assert turnos.horas_validadas(semanal(2)) == 40000


def test_un_periodo_de_mas_de_92_dias_no_da_ningun_turno_por_no_haber_mirado() -> None:
    trimestre = (date(2026, 9, 1), date(2026, 12, 15))
    instantanea = plan(trabajo(compra(1), dia=None, periodo=trimestre),
                       turnos_=[turno(1, date(2026, 10, 5))])
    assert uno("G1", instantanea, 1).resultado == "ok"
    # V5: la venta del trimestre cobra el 5 y el 6 no lo cubre ninguna linea.
    venta_ = trabajo(venta(2), dia=LUNES, periodo=trimestre)
    turnos_ = [turno(1, LUNES), turno(2, LUNES + timedelta(days=1), venta_e4=520000)]
    r = uno("V5", plan(venta_, turnos_=turnos_), 2)
    assert r.resultado == "fallo" and r.valores["turnos"] == ["D-2"]
    # El indice da lo mismo recorriendo los dias que por los turnos de la clave.
    indice = turnos.Indice([turno(1, LUNES), semanal(2, LUNES + timedelta(days=7))])
    corto = indice.de(turnos.RECURSO, 5, LUNES, LUNES + timedelta(days=13))
    largo = indice.de(turnos.RECURSO, 5, LUNES - timedelta(days=60), LUNES + timedelta(days=60))
    assert [len(x) for x in corto] == [len(x) for x in largo] == [1, 1]


def test_una_po_caducada_y_la_que_la_sustituye_no_se_quitan_los_turnos() -> None:
    vieja = orden(1, fin=date(2026, 10, 1))
    nueva = orden(2, inicio=date(2026, 10, 2))
    futuro = [turno(n, HOY + timedelta(days=n), venta_e4=500000) for n in range(1, 4)]
    instantanea = plan(turnos_=futuro, ordenes=[vieja, nueva])
    p8 = uno("P8", instantanea, 2, "orden_compra")
    assert p8.resultado == "fallo" and "1.200,00" in p8.detalle
    assert uno("P10", instantanea, 2, "orden_compra").resultado == "fallo"
    # La caducada no tiene trabajo suyo despues de su fin: lo cubre la nueva.
    assert uno("P7", instantanea, 1, "orden_compra").resultado == "ok"
    # Sin la nueva, ese trabajo si es de la caducada, despues de su fin.
    sola = plan(turnos_=futuro, ordenes=[vieja])
    r = uno("P7", sola, 1, "orden_compra")
    assert r.resultado == "fallo" and r.valores["turnos_despues"] == 3


def test_un_turno_planificado_que_se_valida_con_lo_facturado_no_da_v9() -> None:
    planificado = turno(1, horas=8000, estado="planificado")
    instantanea = plan(trabajo(venta(1), horas=7500), turnos_=[turno(1, horas=7500)],
                       conciliaciones=[conciliado(1, 1010, 1, planificado, horas=7500)])
    assert uno("V1", instantanea, 1).resultado == "ok"
    r = uno("V9", instantanea, 1)
    assert r.resultado == "ok" and "lo facturado es lo que dice ahora" in r.detalle
    # Validado con otras horas que las facturadas, si.
    otras = dataclasses.replace(instantanea, turnos=(turno(1, horas=6000),))
    r = uno("V9", otras, 1)
    assert r.resultado == "fallo" and r.valores["facturadas"] == [["D-1", 7500]]


def test_cobrar_mas_de_lo_que_tienen_unos_turnos_sin_validar_retiene() -> None:
    for estado in ("planificado", "realizado"):
        instantanea = plan(trabajo(compra(1), horas=80000), trabajo(venta(2), horas=80000),
                           turnos_=[turno(1, estado=estado)])
        for regla_id, factura_id in (("G2", 1), ("V1", 2)):
            r = uno(regla_id, instantanea, factura_id)
            assert r.resultado == "fallo" and "sin validar" in r.detalle
            assert (r.valores["tope_mil"], r.valores["diferencia_mil"]) == (8000, 72000)
    # Dentro del tope (con la tolerancia), sin datos hasta que se validen.
    dentro = plan(trabajo(compra(1), horas=8250), turnos_=[turno(1, estado="realizado")])
    assert uno("G2", dentro, 1).resultado == "sin_datos"


def test_con_el_planning_obligatorio_g1_bloquea_aunque_no_haya_con_que_comparar() -> None:
    obligatorio = Politica(planning_obligatorio=True)
    f = trabajo(compra(1))
    sin = plan(f, fotos=(), politica=obligatorio)
    r = uno("G1", sin, 1)
    assert (r.resultado, r.severidad, r.valores["causa"]) == ("fallo", "bloqueo", "sin_planning")
    sin_cubrir = plan(f, fotos=(foto(desde=date(2026, 11, 1)),), politica=obligatorio)
    r = uno("G1", sin_cubrir, 1)
    assert (r.resultado, r.severidad, r.valores["causa"]) == ("fallo", "bloqueo", "sin_cubrir")
    viejo = (lote(1, "trnsprnt", "planning", exportado=date(2026, 9, 1)),)
    caducado = plan(f, turnos_=[turno(1)], lotes=viejo, politica=obligatorio)
    r = uno("G1", caducado, 1)
    assert (r.resultado, r.severidad, r.valores["causa"]) == ("fallo", "bloqueo", "caducado")
    assert "frescura" in r.detalle
    # Sin obligatorio, lo de siempre: sin datos.
    assert [x.resultado for x in resultados("G1", plan(f, fotos=()))] == ["sin_datos"]


def test_g4_g5_v3_y_g6_dan_sin_datos_si_no_pueden_mirar_el_planning() -> None:
    """Nunca nada: un hallazgo abierto solo se queda como estaba si su regla da sin datos."""
    noviembre = (foto(desde=date(2026, 11, 1)),)
    instantanea = plan(trabajo(compra(1), tipo="nacht"), trabajo(venta(2)),
                       turnos_=[turno(1)], fotos=noviembre)
    for regla_id, factura_id, clave in (("G4", 1, "imputacion:1010"), ("G5", 1, "imputacion:1010"),
                                        ("V3", 2, "imputacion:1020"), ("G6", 1, "recargo:1010")):
        r = [x for x in de(regla_id, instantanea, factura_id) if x.clave == clave]
        assert [x.resultado for x in r] == ["sin_datos"], regla_id
        assert "no cubre" in r[0].detalle


def test_g6_valora_las_horas_de_un_recargo_que_no_estan_en_el_planning() -> None:
    noche = trabajo(compra(1), tipo="nacht", tarifa_e4=442500)
    instantanea = plan(noche, turnos_=[turno(1)],
                       tarifas=[tarifa(2, 442500, proveedor=7, turno="nacht")])
    [r] = [x for x in de("G6", instantanea, 1) if x.clave.startswith("recargo")]
    assert r.resultado == "fallo" and r.valores["valor_cent"] == 35400


def test_p7_p8_y_p10_no_dicen_ok_con_un_planning_viejo_o_que_no_llega() -> None:
    po = orden(1, valor=50000)
    futuro = [turno(n, HOY + timedelta(days=n), venta_e4=500000, po=1) for n in range(1, 4)]
    viejo = (lote(1, "trnsprnt", "planning", exportado=date(2026, 8, 1)),)
    caducado = plan(turnos_=futuro, ordenes=[po], lotes=viejo)
    for regla_id in ("P8", "P10"):
        r = uno(regla_id, caducado, 1, "orden_compra")
        assert r.resultado == "sin_datos" and "frescura" in r.detalle
    # Una PO que acaba despues de lo que cubre el planning: pasarse se ve, caber no.
    po_larga = orden(1, valor=500000, fin=date(2027, 3, 31))
    corto = plan(turnos_=futuro[:1], ordenes=[po_larga])
    for regla_id in ("P8", "P10"):
        r = uno(regla_id, corto, 1, "orden_compra")
        assert r.resultado == "sin_datos" and "no cubre" in r.detalle
    pequena = orden(1, valor=10000, fin=date(2027, 3, 31))
    assert uno("P8", plan(turnos_=futuro, ordenes=[pequena]), 1,
               "orden_compra").resultado == "fallo"
    # P7 de una caducada: sin turnos despues de su fin y sin planning de esos dias, sin datos.
    caducada = orden(1, fin=date(2026, 8, 15))
    r = uno("P7", plan(ordenes=[caducada]), 1, "orden_compra")
    assert r.resultado == "sin_datos" and "no cubre" in r.detalle
    r = uno("P7", plan(ordenes=[caducada], lotes=viejo), 1, "orden_compra")
    assert r.resultado == "sin_datos" and "frescura" in r.detalle


def test_g1_cuenta_una_vez_el_turno_de_su_proveedor_y_de_su_persona() -> None:
    r = uno("G1", plan(trabajo(compra(1)), turnos_=[turno(1)]), 1)
    assert r.resultado == "ok" and "1 turno(s)" in r.detalle


def test_lo_que_cubre_el_planning_no_cuenta_los_huecos_de_una_fila_semanal_que_ya_no_vale() -> None:
    vieja = FotoPlanning(1, HOY, date(2026, 10, 12), date(2026, 10, 18),
                         ((date(2026, 10, 12), date(2026, 10, 14)),))
    nueva = foto(2, desde=date(2026, 10, 15), hasta=date(2026, 10, 31))
    assert turnos.tramos([vieja, nueva]) == [(date(2026, 10, 15), date(2026, 10, 31))]
    instantanea = plan(trabajo(venta(1), dia=date(2026, 10, 12)),
                       turnos_=[turno(1, date(2026, 10, 17))], fotos=(vieja, nueva))
    r = uno("V1", instantanea, 1)
    assert r.resultado == "sin_datos" and "no cubre" in r.detalle


def test_lo_esperado_de_un_objeto_no_pasa_de_lo_que_queda_de_la_factura() -> None:
    from bms_agent import trabajo as trabajo_

    f = dataclasses.replace(venta(1), lineas=(), imputaciones=(
        imp(1, None, objeto=8, importe=1000, horas=None),
        imp(2, None, objeto=9, importe=-900, horas=None)))
    vista = trabajo_.horas_objeto(plan(f), 8, {1: ("entrada", 12100)})
    assert 0 < vista["esperado"]["entrante_cent"] <= 12100


def test_las_horas_de_un_objeto_de_una_semana_sin_planning_son_sin_datos() -> None:
    from bms_agent import trabajo as trabajo_

    septiembre = date(2026, 9, 7)
    instantanea = plan(trabajo(compra(1), dia=septiembre), trabajo(venta(2), dia=septiembre),
                       turnos_=[turno(1, date(2026, 10, 5))],
                       fotos=(foto(desde=date(2026, 10, 1), hasta=date(2026, 10, 31)),))
    semanas = {s["semana"]: s for s in trabajo_.horas_objeto(instantanea, 8)["semanas"]}
    w37 = semanas["2026-W37"]
    assert w37["cobertura"] == "ninguna" and w37["cliente_mil"] == 8000
    assert (w37["planificadas_mil"], w37["validadas_mil"], w37["sin_facturar_mil"]) == (
        None, None, None)
    assert semanas["2026-W41"]["cobertura"] == "entera"
    assert semanas["2026-W41"]["validadas_mil"] == 8000
    viejo = (lote(1, "trnsprnt", "planning", exportado=date(2026, 8, 1)),)
    assert trabajo_.horas_objeto(dataclasses.replace(instantanea, lotes=viejo), 8)[
        "planning"] == "caducado"


# ------------------------------------------------------------ escenarios

def escenarios() -> list[Instantanea]:
    """Instantaneas que pasan por cada rama de las reglas del paso 10 (test_pureza_reglas)."""
    semana = (LUNES, LUNES + timedelta(days=6))
    semana_43 = (LUNES + timedelta(days=14), LUNES + timedelta(days=20))
    diario = [turno(1, tipo=None, compra_e4=400000, venta_e4=520000, servicio="beveiliging"),
              turno(2, LUNES + timedelta(days=1), tipo="nacht", compra_e4=442500),
              turno(3, LUNES + timedelta(days=2), estado="realizado"),
              turno(4, LUNES + timedelta(days=3), estado="cancelado"),
              turno(5, LUNES, recurso=6, objeto=9, proveedor=None, cliente=3, po=1),
              turno(6, date(2026, 8, 10), venta_e4=520000),
              turno(7, HOY + timedelta(days=3), po=1, venta_e4=500000),
              turno(8, date(2026, 9, 29), facturable=False),
              semanal(9, semana_43[0], objeto=9),
              turno(10, HOY + timedelta(days=5), compra_e4=400000, cliente=None),
              semanal(11, semana_43[0] + timedelta(days=7), objeto=9)]
    compras = [
        trabajo(compra(1)),
        trabajo(compra(2, numero_norm="C2"), tipo="nacht", dia=LUNES + timedelta(days=1)),
        trabajo(compra(3, numero_norm="C3"), objeto_id=None),
        trabajo(compra(4, numero_norm="C4"), objeto_id=9),
        trabajo(compra(5, numero_norm="C5"), dia=LUNES + timedelta(days=2)),
        trabajo(compra(6, numero_norm="C6"), dia=LUNES + timedelta(days=8), semana=40),
        trabajo(compra(7, numero_norm="C7", proveedor_id=None, parte=None)),
        trabajo(compra(8, numero_norm="C8"), dia=None, periodo=semana),
        trabajo(compra(9, numero_norm="C9"), dia=semana[0], hasta=semana[1], horas=99000),
        trabajo(compra(10, numero_norm="C10"), dia=LUNES + timedelta(days=16),
                hasta=LUNES + timedelta(days=24)),
        trabajo(compra(11, numero_norm="C11", periodo_inicio=None, periodo_fin=None), dia=None),
        trabajo(compra(12, numero_norm="C12"), dia=date(2027, 3, 1)),
        trabajo(compra(13, numero_norm="C13", fecha_factura=date(2026, 10, 25)), dia=None,
                semana=43, periodo=False),
        trabajo(compra(14, numero_norm="C14", proveedor_id=99)),
        trabajo(compra(15, numero_norm="C15", tipo="nota_credito")),
        trabajo(compra(16, numero_norm="C16"), tarifa_e4=500000, po=2),
        trabajo(compra(17, numero_norm="C17"), tipo="nacht", objeto_id=9,
                dia=semana_43[0] + timedelta(days=2)),
    ]
    ventas = [
        trabajo(venta(21), periodo=semana),
        trabajo(venta(22, numero_norm="V22"), objeto_id=None),
        trabajo(venta(23, numero_norm="V23"), objeto_id=10),
        trabajo(venta(24, numero_norm="V24"), objeto_id=11),
        trabajo(venta(25, numero_norm="V25", cliente_id=None, parte=None), objeto_id=None),
        trabajo(venta(26, numero_norm="V26"), tarifa_e4=500000, po=1),
        trabajo(venta(27, numero_norm="V27", periodo_inicio=None, periodo_fin=None,
                      fecha_factura=None), dia=None),
        trabajo(venta(28, numero_norm="V28", fecha_factura=date(2026, 10, 25)), dia=None,
                semana=43, objeto_id=9, periodo=(semana_43[0], semana_43[1] + timedelta(days=7))),
        trabajo(venta(29, numero_norm="V29"), dia=None, periodo=semana),
        trabajo(venta(30, numero_norm="V30"), dia=LUNES + timedelta(days=8), semana=40),
        trabajo(venta(31, numero_norm="V31"), dia=semana[0], hasta=semana[1], horas=16000),
    ]
    cambiado = dataclasses.replace(diario[0], horas_aprobadas_mil=7000)
    conciliaciones = [conciliado(1, 1010, 1, diario[0]),
                      conciliado(2, 1210, 21, diario[0]),
                      conciliado(3, 1090, 9, diario[0]),
                      conciliado(4, 1090, 9, dataclasses.replace(diario[1], horas_aprobadas_mil=1)),
                      conciliado(5, 9999, 98, diario[0]),
                      conciliado(6, 1280, 28, diario[8]),
                      conciliado(7, 1290, 29, cambiado),
                      conciliado(8, 1310, 31, diario[0]),
                      conciliado(9, 1260, 26, diario[0]),
                      conciliado(10, 1080, 8, cambiado),
                      conciliado(11, 1130, 13, diario[8]),
                      conciliado(12, 1170, 17, diario[8])]
    objetos = [objeto(8), objeto(9), objeto(10, cliente_id=4),
               dataclasses.replace(objeto(11), activo_desde=date(2026, 11, 1))]
    ciclos = [ciclo(1, frecuencia="semanal", ancla=None, desde=date(2026, 9, 7)),
              ciclo(2, cliente=None, objeto_id=9, frecuencia="mensual",
                    ancla=date(2026, 1, 1), gracia=5, hasta=date(2026, 12, 31)),
              ciclo(3, cliente=None, objeto_id=8, frecuencia="cuatrisemanal",
                    ancla=date(2026, 8, 31), gracia=1, desde=date(2026, 9, 1))]
    tarifas = [tarifa(1, 400000, proveedor=7), tarifa(2, 442500, proveedor=7, turno="nacht"),
               tarifa(3, 500000, sentido="venta", cliente=3, objeto=8)]
    pos = [orden(1, valor=50000, fin=date(2026, 10, 1)),
           orden(2, lado="proveedor", parte=7, objetos=(8,)), orden(3, cerrada=True)]
    todas = (*compras, *ventas)
    fotos = (foto(1, desde=date(2026, 8, 1)), foto(2, desde=date(2027, 1, 1),
                                                   hasta=date(2027, 1, 31)))
    return [
        plan(*todas, fotos=()),
        plan(*todas, turnos_=diario, conciliaciones=conciliaciones, objetos=objetos,
             ciclos=ciclos, tarifas=tarifas, ordenes=pos, fotos=fotos,
             relaciones=[Relacion(15, 16, "acredita", id=1)],
             lotes=(lote(1, "trnsprnt", "planning"),),
             politica=Politica(planning_obligatorio=True)),
        plan(*todas, turnos_=diario, conciliaciones=conciliaciones, objetos=objetos,
             ciclos=ciclos, ordenes=pos, fotos=fotos),
        plan(*compras[:3], *ventas[:2], turnos_=diario, objetos=objetos,
             lotes=(lote(1, "trnsprnt", "planning", exportado=date(2026, 8, 1)),),
             ciclos=ciclos[:1], conciliaciones=conciliaciones[:2]),
        plan(trabajo(compra(1)), turnos_=[semanal(9)], ordenes=pos[:1]),
        # V5 con lo que falta: un turno de noche y una fila semanal sin linea que los cubra,
        # con y sin tarifa de venta pactada.
        plan(ventas[0], ventas[7], turnos_=diario, hoy=date(2026, 11, 20), tarifas=[
            *tarifas, tarifa(4, 600000, sentido="venta", cliente=3, turno="nacht",
                             desde=date(2026, 1, 1), hasta=date(2026, 12, 31))]),
        plan(ventas[0], ventas[7], turnos_=diario, hoy=date(2026, 11, 20)),
        # Revision: el planning obligatorio sin planning, uno viejo con PO y turnos sin
        # validar cobrados de mas.
        plan(*compras[:3], fotos=(), politica=Politica(planning_obligatorio=True)),
        plan(*compras[:3], *ventas[:2], turnos_=diario, ordenes=pos, objetos=objetos,
             lotes=(lote(1, "trnsprnt", "planning", exportado=date(2026, 8, 1)),),
             politica=Politica(planning_obligatorio=True)),
        plan(trabajo(compra(1), horas=80000), trabajo(venta(2), horas=80000),
             turnos_=[turno(1, estado="realizado")], ordenes=pos,
             fotos=(foto(1, desde=date(2026, 8, 1), hasta=date(2026, 10, 20),
                         huecos=((date(2026, 8, 1), date(2026, 8, 2)),)),)),
    ]
