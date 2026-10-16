"""Las reglas del paso 9 sin base: P1-P10 y las tarifas pactadas (G3, G6, V4).

Las instantanas llevan, ademas de lo de los pasos anteriores, las ordenes de
compra con su valor y su fin vigentes (`ordenes`), las tarifas pactadas
(`tarifas`), los Objetos del maestro (`objetos`) y, en cada factura, sus
imputaciones (con su PO) y sus referencias impresas. Hoy es siempre el
2026-10-14 (test_reglas.HOY): la caducidad y la prevision se prueban con esa
fecha fija. Los constructores y `escenarios()` los usa tambien
test_pureza_reglas.py.
"""

from __future__ import annotations

import dataclasses
import random
from datetime import date, timedelta

import pytest
from test_reglas import HOY, factura, linea
from test_reglas_paso8 import abono, con_efectos, venta

from bms_agent.reglas import catalogo
from bms_agent.reglas.base import (
    Imputacion,
    Instantanea,
    Objeto,
    OrdenCompra,
    Parte,
    Politica,
    Referencia,
    Relacion,
    Tarifa,
)
from bms_agent.reglas.ordenes import cargos, prevision, situacion, vigentes
from bms_agent.reglas.tarifas import (
    AMBIGUA,
    NINGUNA,
    NO_CASA,
    UNICA,
    normalizar_turno,
    pactada,
)

# ------------------------------------------------------------ constructores


def imp(id_: int, linea_id: int | None, *, po: int | None = None, importe: int | None = 34000,
        objeto: int | None = None, recurso: int | None = None, horas: int | None = 8000,
        inicio: date | None = None, fin: date | None = None, servicio: str | None = None,
        turno: str | None = None) -> Imputacion:
    return Imputacion(id_, linea_id, objeto, recurso, po, importe, horas, inicio, fin, servicio,
                      turno)


def orden(id_: int, *, numero: str | None = None, lado: str = "cliente", parte: int = 3,
          valor: int = 100000, inicio: date | None = date(2026, 9, 1),
          fin: date | None = date(2026, 12, 31), emision: date | None = None,
          cerrada: bool = False, objetos: tuple[int, ...] = ()) -> OrdenCompra:
    numero = numero or f"PO-{id_}"
    return OrdenCompra(id_, numero, numero.replace("-", ""), lado, parte, emision, inicio, fin,
                       valor, valor, fin, cerrada, frozenset(objetos))


def ref(id_: int, valor: str, *, linea_id: int | None = None, clase: str = "po",
        po: int | None = None) -> Referencia:
    return Referencia(id_, linea_id, valor, valor.replace("-", ""), clase, po)


def tarifa(id_: int, precio: int, *, sentido: str = "compra", proveedor: int | None = None,
           recurso: int | None = None, cliente: int | None = None, objeto: int | None = None,
           po: int | None = None, servicio: str | None = None, turno: str | None = None,
           unidad: str | None = None, desde: date | None = None,
           hasta: date | None = None) -> Tarifa:
    return Tarifa(id_, sentido, proveedor, recurso, cliente, objeto, po, servicio, turno, unidad,
                  precio, desde, hasta)


def cliente(id_: int = 3, requiere_po: bool | None = None) -> Parte:
    return Parte(id_, "cliente", "Havenbedrijf", frozenset({"havenbedrijf"}), None, None, None,
                 True, requiere_po)


def objeto(id_: int, cliente_id: int | None = 3, requiere_po: bool | None = None) -> Objeto:
    return Objeto(id_, f"OBJ{id_}", cliente_id, requiere_po, None, None)


def con_po(f, po: int | None, importe: int | None = None, **cambios):
    """La factura con una imputacion por linea (de id la de la linea + 1000), a esa PO."""
    imputaciones = tuple(imp(l.id + 1000, l.id, po=po,
                             importe=l.importe_cent if importe is None else importe, **cambios)
                         for l in f.lineas)
    return dataclasses.replace(f, imputaciones=imputaciones)


def compra(id_: int, **cambios):
    """Una compra al proveedor 7, resuelta."""
    valores = dict(proveedor_id=7)
    valores.update(cambios)
    return factura(id_, **valores)


def inst(*facturas, ordenes=(), tarifas=(), objetos=(), clientes=(), relaciones=(),
         politica: Politica | None = None) -> Instantanea:
    return Instantanea(hoy=HOY, politica=politica or Politica(),
                       facturas=tuple(con_efectos(facturas, relaciones)),
                       relaciones=tuple(relaciones), ordenes=tuple(ordenes),
                       tarifas=tuple(tarifas), objetos=tuple(objetos), clientes=tuple(clientes))


def resultados(regla_id: str, instantanea: Instantanea) -> list:
    return list(catalogo.regla(regla_id).evaluar(instantanea))


def de(regla_id: str, instantanea: Instantanea, fila_id: int, tabla: str = "factura") -> list:
    return [r for r in resultados(regla_id, instantanea)
            if r.fila_id == fila_id and r.tabla == tabla]


def uno(regla_id: str, instantanea: Instantanea, fila_id: int, tabla: str = "factura"):
    [resultado] = de(regla_id, instantanea, fila_id, tabla)
    return resultado


# ============================================================ lo consumido

def test_el_consumo_es_sin_iva_con_los_abonos_confirmados_y_sin_lo_que_no_cuenta() -> None:
    """La puerta: sin IVA, los abonos confirmados restan, anuladas y sustituidas fuera."""
    po = orden(1, valor=100000)
    buena = con_po(venta(1), 1)                                   # base 340,00 (total 411,40)
    anulada = con_po(venta(2, anulada=True, numero_norm="V2"), 1)
    sustituida = con_po(venta(3, numero_norm="V3"), 1)
    sustituta = con_po(venta(4, numero_norm="V4", base_cent=20000, total_cent=24200,
                             lineas=(linea(40, importe_cent=20000),)), 1)
    fusionada = con_po(venta(5, numero_norm="V5", fusionada_en_id=1), 1)
    abonada = con_po(abono(6, -12100, sentido="saliente", cliente_id=3, parte="cliente:3"), 1)
    suelto = con_po(abono(7, -6050, sentido="saliente", cliente_id=3, parte="cliente:3"), 1)
    de_compra = con_po(compra(8, numero_norm="C8"), 1)            # otro lado: no consume
    sin_euros = dataclasses.replace(venta(9, numero_norm="V9"),       # X1: sin importe
                                    imputaciones=(imp(1090, 90, po=1, importe=None),))
    relaciones = [Relacion(4, 3, "sustituye", id=1), Relacion(6, 1, "acredita", id=2)]
    i = inst(buena, anulada, sustituida, sustituta, fusionada, abonada, suelto, de_compra,
             sin_euros, ordenes=[po], relaciones=relaciones)
    lista = cargos(i)[1]
    assert [(c.factura_id, c.importe_cent) for c in lista] == [(1, 34000), (4, 20000),
                                                               (6, -10000)]
    s = situacion(po, lista)
    assert (s.consumido_cent, s.restante_cent) == (44000, 56000)
    assert (s.consumido_pb, s.restante_pb) == (4400, 5600)
    # Lo de cada factura es la suma de sus imputaciones a esa PO, y nada de otra PO.
    partida = dataclasses.replace(buena, imputaciones=(imp(1, 10, po=1, importe=20000),
                                                       imp(2, 10, po=1, importe=14000),
                                                       imp(3, 10, po=2, importe=999)))
    assert [(c.factura_id, c.importe_cent) for c in cargos(
        inst(partida, ordenes=[po, orden(2)]))[1]] == [(1, 34000)]
    # Un abono de una factura que ya no cuenta (anulada, o sustituida) no resta: su cargo ya
    # salio de la PO, y restaria dos veces.
    de_anulada = inst(anulada, abonada, ordenes=[po], relaciones=[Relacion(6, 2, "acredita")])
    assert cargos(de_anulada) == {}
    de_sustituida = inst(sustituida, sustituta, abonada, ordenes=[po],
                         relaciones=[Relacion(4, 3, "sustituye", id=1),
                                     Relacion(6, 3, "acredita", id=2)])
    assert [c.factura_id for c in cargos(de_sustituida)[1]] == [4]


def test_el_valor_y_el_fin_vigentes_son_los_de_la_ultima_modificacion() -> None:
    fin = date(2026, 12, 31)
    assert vigentes(1000, fin, []) == (1000, fin)
    mods = [(3, date(2026, 10, 1), 1500, None), (1, date(2026, 10, 1), 1200, date(2027, 1, 31)),
            (2, date(2026, 9, 1), 900, date(2027, 6, 30))]
    # El valor: el 1500 (misma fecha que el 1200, apuntado despues). El fin: el de la mas
    # reciente que lo cambia (la 1, del 1 de octubre), no el de la apuntada despues.
    assert vigentes(1000, fin, mods) == (1500, date(2027, 1, 31))
    assert vigentes(1000, fin, list(reversed(mods))) == (1500, date(2027, 1, 31))


# ============================================================ P4 y P6: el orden

def test_p4_sigue_el_orden_por_fecha_de_factura_y_por_id() -> None:
    po = orden(1, valor=50000)
    tarde = con_po(venta(5, numero_norm="A", fecha_factura=date(2026, 9, 15)), 1, 30000)
    pronto = con_po(venta(9, numero_norm="B", fecha_factura=date(2026, 9, 10)), 1, 30000)
    mismo_dia = con_po(venta(3, numero_norm="C", fecha_factura=date(2026, 9, 15)), 1, 10000)
    despues = con_po(venta(11, numero_norm="D", fecha_factura=date(2026, 9, 20)), 1, 5000)
    sin_fecha = con_po(venta(12, numero_norm="E", fecha_factura=None), 1, 1000)
    i = inst(tarde, pronto, mismo_dia, despues, sin_fecha, ordenes=[po])
    assert [c.factura_id for c in cargos(i)[1]] == [9, 3, 5, 11, 12]
    # Antes de la 9 quedaban 500,00; antes de la 3, 200,00 (cabe); antes de la 5, 100,00.
    assert uno("P4", i, 3).resultado == "ok"
    p4 = uno("P4", i, 5)
    assert p4.resultado == "fallo" and p4.clave == "po:1"
    assert (p4.valores["antes_cent"], p4.valores["exceso_cent"]) == (10000, 20000)
    # La 9 va la primera por su fecha, pero llego despues de la 3 y la 5 (ids menores), que
    # ya dejaban 100,00: tambien se pasa (una fecha atrasada no la libra).
    p4_9 = uno("P4", i, 9)
    assert p4_9.resultado == "fallo" and "llegó después" in p4_9.detalle
    assert (p4_9.valores["antes_cent"], p4_9.valores["antes_llegada_cent"]) == (50000, 10000)
    # Antes de la 11 ya no quedaba nada: eso lo dice P6, no P4.
    assert uno("P4", i, 11).resultado == "no_aplica"
    p6 = uno("P6", i, 11)
    assert p6.resultado == "fallo" and p6.valores["antes_cent"] == -20000
    assert uno("P6", i, 5).resultado == "ok"
    # Sin fecha no se sabe que tenia antes.
    assert uno("P4", i, 12).resultado == "sin_datos"
    assert uno("P6", i, 12).resultado == "sin_datos"
    # El orden no depende del orden en que lleguen las facturas.
    revuelta = [tarde, pronto, mismo_dia, despues, sin_fecha]
    random.Random(9).shuffle(revuelta)
    assert resultados("P4", inst(*revuelta, ordenes=[po])) == resultados("P4", i)


def test_p4_una_factura_con_fecha_atrasada_no_se_cuela_delante() -> None:
    """La A (1 de octubre) llega y cabe. La B llega despues con fecha del 2 de septiembre: por
    el §7 va antes y pasaria el limite a la A, ya mirada; la B se retiene igual."""
    po = orden(1, valor=100000)
    a = con_po(venta(1, numero_norm="A", fecha_factura=date(2026, 10, 1)), 1, 80000)
    assert uno("P4", inst(a, ordenes=[po]), 1).resultado == "ok"
    b = con_po(venta(2, numero_norm="B", fecha_factura=date(2026, 9, 2)), 1, 80000)
    i = inst(a, b, ordenes=[po])
    p4_b = uno("P4", i, 2)
    assert p4_b.resultado == "fallo" and p4_b.valores["exceso_cent"] == 60000
    assert uno("P4", i, 1).resultado == "fallo"                     # el orden del §7
    # Si la B ya no cabia en nada (la A lo consumio todo), es P6, en cualquier orden.
    toda = con_po(venta(1, numero_norm="A", fecha_factura=date(2026, 10, 1)), 1, 100000)
    j = inst(toda, b, ordenes=[po])
    assert uno("P6", j, 2).resultado == "fallo" and uno("P4", j, 2).resultado == "no_aplica"


def test_un_abono_no_consume_y_libera_lo_que_abona() -> None:
    po = orden(1, valor=40000)
    v1 = con_po(venta(1, fecha_factura=date(2026, 9, 1)), 1)                     # 340,00
    nota = con_po(abono(2, -12100, sentido="saliente", cliente_id=3, parte="cliente:3",
                        fecha_factura=date(2026, 9, 5)), 1)                        # -100,00
    v3 = con_po(venta(3, numero_norm="V3", fecha_factura=date(2026, 9, 10)), 1, 15000)
    sin_confirmar = inst(v1, nota, v3, ordenes=[po])
    assert uno("P4", sin_confirmar, 3).resultado == "fallo"          # quedaban 60,00
    confirmado = inst(v1, nota, v3, ordenes=[po], relaciones=[Relacion(2, 1, "acredita")])
    assert uno("P4", confirmado, 2).resultado == "ok"
    assert uno("P4", confirmado, 3).resultado == "ok"                # quedaban 160,00


# ============================================================ umbrales de la politica

def test_p5_avisa_desde_el_umbral_de_la_politica() -> None:
    po = orden(1, valor=40000)
    i = inst(con_po(venta(1), 1), ordenes=[po])                       # 340 de 400: 85 %
    assert uno("P5", i, 1, "orden_compra").resultado == "fallo"
    assert uno("P5", i, 1, "orden_compra").valores["umbral_pct"] == 80
    alto = dataclasses.replace(i, politica=Politica(po_aviso_consumo_pct=90))
    assert uno("P5", alto, 1, "orden_compra").resultado == "ok"
    justo = inst(con_po(venta(1), 1, 32000), ordenes=[po])            # 80,00 % justo
    assert uno("P5", justo, 1, "orden_compra").resultado == "fallo"
    cerrada = inst(con_po(venta(1), 1), ordenes=[orden(1, valor=40000, cerrada=True)])
    assert uno("P5", cerrada, 1, "orden_compra").resultado == "no_aplica"


# ============================================================ P7: caducidad con fecha fija

@pytest.mark.parametrize("fin, esperado, dias", [
    (date(2026, 11, 10), "fallo", 27), (date(2026, 11, 13), "fallo", 30),
    (date(2026, 11, 14), "ok", 31), (HOY, "fallo", 0),
    (date(2026, 10, 1), "sin_datos", -13),
])
def test_p7_caduca_dentro_de_los_dias_de_la_politica(fin, esperado, dias) -> None:
    i = inst(con_po(venta(1), 1, 10000), ordenes=[orden(1, fin=fin)])
    p7 = uno("P7", i, 1, "orden_compra")
    assert p7.resultado == esperado
    if esperado != "ok":
        # La huella no lleva los dias (bajan cada dia): el fin fijo, y los dias en el texto.
        assert p7.valores["fin"] == fin.isoformat() and "dias_para_caducar" not in p7.valores
    if esperado == "fallo":
        assert ("(hoy)" if dias == 0 else f"(en {dias} días)") in p7.detalle
    corta = dataclasses.replace(i, politica=Politica(po_dias_caducidad=7))
    if esperado == "fallo" and dias > 7:
        assert uno("P7", corta, 1, "orden_compra").resultado == "ok"


def test_p7_sin_valor_que_caduque_o_sin_fin_no_avisa() -> None:
    consumida = inst(con_po(venta(1), 1), ordenes=[orden(1, valor=34000,
                                                         fin=date(2026, 10, 20))])
    assert uno("P7", consumida, 1, "orden_compra").resultado == "ok"
    sin_fin = inst(ordenes=[orden(1, fin=None)])
    assert uno("P7", sin_fin, 1, "orden_compra").resultado == "no_aplica"


# ============================================================ P9: prevision determinista

def test_la_prevision_es_determinista_y_sale_del_ritmo_de_las_semanas() -> None:
    po = orden(1, valor=100000, inicio=date(2026, 8, 1), fin=date(2026, 12, 31))
    facturas = [con_po(venta(1, fecha_factura=date(2026, 8, 10)), 1, 5000),    # fuera
                con_po(venta(2, numero_norm="V2", fecha_factura=date(2026, 9, 1)), 1, 28000),
                con_po(venta(3, numero_norm="V3", fecha_factura=date(2026, 10, 1)), 1, 28000)]
    i = inst(*facturas, ordenes=[po])
    p = prevision(po, cargos(i)[1], HOY, 8)
    # Ventana de 56 dias (20 de agosto a hoy): 560,00, 10,00 al dia. Quedan 390,00: 39 dias.
    assert (p.desde, p.dias, p.consumido_cent) == (date(2026, 8, 20), 56, 56000)
    assert p.agotamiento == HOY + timedelta(days=39) == date(2026, 11, 22)
    p9 = uno("P9", i, 1, "orden_compra")
    assert p9.resultado == "fallo" and "se agota el 2026-11-22" in p9.detalle
    # Lo mismo en cualquier orden y cada vez.
    for semilla in range(3):
        revueltas = facturas[:]
        random.Random(semilla).shuffle(revueltas)
        assert resultados("P9", inst(*revueltas, ordenes=[po])) == resultados("P9", i)
    # El margen y las semanas son de la politica: con 90 dias de margen ya no avisa (se
    # agota 39 dias antes de su fin), y con 2 semanas el ritmo es otro.
    holgada = dataclasses.replace(i, politica=Politica(po_margen_prevision_dias=90))
    assert uno("P9", holgada, 1, "orden_compra").resultado == "ok"
    dos_semanas = prevision(po, cargos(i)[1], HOY, 2)
    assert (dos_semanas.desde, dos_semanas.consumido_cent) == (date(2026, 10, 1), 28000)
    assert dos_semanas.agotamiento == HOY + timedelta(days=20)


def test_la_prevision_empieza_en_el_inicio_de_la_po_y_sin_consumo_no_se_agota() -> None:
    reciente = orden(1, valor=100000, inicio=date(2026, 10, 5), fin=date(2027, 3, 31))
    i = inst(con_po(venta(1, fecha_factura=date(2026, 10, 10)), 1, 10000), ordenes=[reciente])
    p = prevision(reciente, cargos(i)[1], HOY, 8)
    assert (p.desde, p.dias) == (date(2026, 10, 5), 10)
    assert p.agotamiento == HOY + timedelta(days=90)                   # 900,00 a 10,00/dia
    quieta = inst(ordenes=[orden(1)])
    assert prevision(orden(1), [], HOY, 8).agotamiento is None
    assert uno("P9", quieta, 1, "orden_compra").resultado == "ok"


# ============================================================ P1, P2, P3

def test_p1_mira_que_la_po_este_abierta_y_cubra_los_dias_del_trabajo() -> None:
    po = orden(1, inicio=date(2026, 9, 1), fin=date(2026, 9, 30))
    dentro = con_po(venta(1), 1)                                      # periodo 7-13 sep
    fuera = con_po(venta(2, numero_norm="V2", periodo_inicio=date(2026, 8, 25),
                         periodo_fin=date(2026, 9, 5)), 1)
    por_linea = con_po(venta(3, numero_norm="V3", lineas=(linea(
        30, fecha_trabajo=date(2026, 10, 2)),)), 1)
    sin_dias = con_po(venta(4, numero_norm="V4", periodo_inicio=None, periodo_fin=None,
                            fecha_factura=None), 1)
    i = inst(dentro, fuera, por_linea, sin_dias, ordenes=[po])
    assert uno("P1", i, 1).resultado == "ok"
    fuera_p1 = uno("P1", i, 2)
    assert fuera_p1.resultado == "fallo" and "fuera de su vigencia" in fuera_p1.detalle
    assert uno("P1", i, 3).resultado == "fallo"
    assert uno("P1", i, 4).resultado == "sin_datos"
    cerrada = inst(dentro, ordenes=[orden(1, cerrada=True)])
    assert "cerrada" in uno("P1", cerrada, 1).detalle
    assert resultados("P1", inst(dentro)) == []


def test_p2_pide_la_po_donde_el_objeto_o_el_cliente_la_piden() -> None:
    sin = con_po(venta(1), None, objeto=None)
    impresa = dataclasses.replace(venta(2, numero_norm="V2", referencias=(ref(1, "PO-9"),)),
                                  imputaciones=(imp(1, 20),))
    no_la_pide = con_po(venta(3, numero_norm="V3"), None, objeto=8)
    i = inst(sin, impresa, no_la_pide, clientes=[cliente(3, True)],
             objetos=[objeto(8, requiere_po=False)])
    assert uno("P2", i, 1).resultado == "fallo"
    assert uno("P2", i, 2).resultado == "ok"            # la lleva impresa: si vale, P1 y P3
    assert de("P2", i, 3) == []                          # el Objeto dice que no
    por_objeto = inst(con_po(venta(1), None, objeto=8), clientes=[cliente(3, False)],
                      objetos=[objeto(8, requiere_po=True)])
    assert uno("P2", por_objeto, 1).resultado == "fallo"
    assert resultados("P2", inst(sin, clientes=[cliente(3, None)])) == []
    assert de("P2", inst(con_po(compra(4), None), clientes=[cliente(3, True)]), 4) == []
    # Un abono no se factura contra una PO: la toma de la que abona al confirmarse (R4).
    nota = con_po(abono(5, -12100, sentido="saliente", cliente_id=3, parte="cliente:3"), None)
    assert de("P2", inst(nota, clientes=[cliente(3, True)]), 5) == []


def test_p3_ve_la_po_desconocida_la_de_otro_y_la_que_no_cubre_el_objeto() -> None:
    propia, ajena = orden(1, numero="PO-1"), orden(2, numero="PO-2", parte=4)
    con_objeto = orden(3, numero="PO-3", objetos=(8,))
    desconocida = venta(1, referencias=(ref(1, "PO-77"),))
    de_otro = venta(2, numero_norm="V2", referencias=(ref(2, "PO-2"),))
    buena = venta(3, numero_norm="V3", referencias=(ref(3, "PO-1", po=1),))
    imputada_ajena = con_po(venta(4, numero_norm="V4"), 2)
    otro_objeto = con_po(venta(5, numero_norm="V5"), 3, objeto=9)
    sin_parte = venta(6, numero_norm="V6", cliente_id=None, parte=None,
                      referencias=(ref(6, "PO-2"),))
    no_po = venta(7, numero_norm="V7", referencias=(ref(7, "X-1", clase="proyecto"),))
    i = inst(desconocida, de_otro, buena, imputada_ajena, otro_objeto, sin_parte, no_po,
             ordenes=[propia, ajena, con_objeto])
    assert uno("P3", i, 1).valores["desconocidas"] == ["PO-77"]
    assert uno("P3", i, 2).valores["de_otra_parte"] == ["PO-2"]
    assert uno("P3", i, 3).resultado == "ok"
    assert uno("P3", i, 4).valores["de_otra_parte"] == ["PO-2"]
    assert uno("P3", i, 5).valores["de_otro_objeto"] == [[1050, "PO-3"]]
    assert uno("P3", i, 6).resultado == "sin_datos"
    assert de("P3", i, 7) == []
    # Sin ninguna PO de ese lado no se sabe si es desconocida: sin datos, nunca ok.
    solo_compras = inst(desconocida, ordenes=[orden(5, lado="proveedor", parte=7)])
    assert uno("P3", solo_compras, 1).resultado == "sin_datos"


def test_p3_retiene_una_compra_que_imprime_dos_po_y_no_consume_ninguna() -> None:
    """Dos PO de su proveedor en la cabecera: la sincronizacion no reparte y la imputacion queda
    sin PO; sin P3 no consumiria de ninguna y P1, P4 y P6 no dirian nada."""
    pos = [orden(1, lado="proveedor", parte=7, valor=10000),
           orden(2, lado="proveedor", parte=7, valor=10000)]
    dos = compra(1, referencias=(ref(1, "PO-1", po=1), ref(2, "PO-2", po=2)))
    i = inst(con_po(dos, None, 500000), ordenes=pos)
    p3 = uno("P3", i, 1)
    assert p3.resultado == "fallo" and "imputar_po" in p3.detalle
    assert p3.valores["varias"] == [[1010, ["PO-1", "PO-2"]]]
    # La de su linea manda sobre la cabecera, como en la sincronizacion.
    en_linea = compra(1, referencias=(ref(1, "PO-1", po=1), ref(2, "PO-2", po=2),
                                      ref(3, "PO-1", po=1, linea_id=10)))
    assert uno("P3", inst(con_po(en_linea, 1, 5000), ordenes=pos), 1).resultado == "ok"
    # Imputada a una (lo decidio una persona): ya no retiene por eso.
    assert uno("P3", inst(con_po(dos, 2, 5000), ordenes=pos), 1).resultado == "ok"


def test_p8_y_p10_esperan_al_planning() -> None:
    i = inst(ordenes=[orden(1), orden(2, cerrada=True)])
    for regla in ("P8", "P10"):
        assert uno(regla, i, 1, "orden_compra").resultado == "sin_datos"
        assert "paso 10" in uno(regla, i, 1, "orden_compra").detalle
        assert uno(regla, i, 2, "orden_compra").resultado == "no_aplica"


def test_sin_ordenes_de_compra_las_reglas_p_no_dicen_nada() -> None:
    i = inst(con_po(venta(1), None), con_po(compra(2), None))
    for regla in ("P1", "P4", "P5", "P6", "P7", "P8", "P9", "P10"):
        assert resultados(regla, i) == [], regla


# ============================================================ la tarifa pactada que vale

def _p(tarifas, **cambios):
    datos = dict(parte_id=7, recurso_id=5, objeto_id=8, orden_compra_id=None, turno=None,
                 servicio="montage", unidad="hora", fecha=date(2026, 9, 10))
    datos.update(cambios)
    return pactada(tarifas, **datos)


def test_la_tarifa_pactada_va_de_lo_mas_concreto_a_lo_general() -> None:
    general = tarifa(1, 300000, sentido="venta", servicio="montage")
    parte = tarifa(2, 310000, proveedor=7)
    recurso = tarifa(3, 320000, recurso=5)
    de_objeto = tarifa(4, 330000, objeto=8)
    las_dos = tarifa(5, 340000, recurso=5, objeto=8)
    todas = [general, parte, recurso, de_objeto, las_dos]
    assert dataclasses.astuple(_p(todas)) == (UNICA, 340000, "recurso y Objeto", (5,))
    assert _p(todas[:4]).nivel == "Objeto"
    assert _p(todas[:3]).nivel == "recurso"
    assert _p(todas[:2]).nivel == "parte"
    assert _p(todas[:1]).nivel == "general"
    # Lo que la tarifa dice tiene que coincidir: otro recurso u otro proveedor no vale.
    assert _p([tarifa(6, 1, recurso=6), tarifa(7, 1, proveedor=9)]).estado == NINGUNA
    # El turno es condicion: la de noche no es la de una linea de dia, ni al reves.
    # (Una linea de dia con solo la de noche pactada no casa: no es que no haya nada.)
    noche = tarifa(8, 500000, proveedor=7, turno="nacht")
    assert dataclasses.astuple(_p([noche])) == (NO_CASA, None, None, (8,))
    assert _p([noche, parte], turno="nacht").tarifa_e4 == 500000
    assert normalizar_turno("Dag") is None and normalizar_turno(" Nacht ") == "nacht"


def test_dentro_del_nivel_gana_la_mas_concreta_y_si_no_es_ambigua() -> None:
    vieja = tarifa(1, 300000, proveedor=7, desde=date(2026, 1, 1))
    nueva = tarifa(2, 320000, proveedor=7, desde=date(2026, 7, 1))
    assert _p([vieja, nueva]).tarifa_e4 == 320000
    assert _p([vieja, nueva], fecha=date(2026, 3, 1)).tarifa_e4 == 300000
    de_la_po = tarifa(3, 280000, proveedor=7, po=4)
    assert _p([vieja, de_la_po], orden_compra_id=4).tarifa_e4 == 280000
    assert _p([vieja, de_la_po]).tarifa_e4 == 300000
    caducada = tarifa(4, 1, proveedor=7, hasta=date(2026, 8, 31))
    assert _p([caducada]).estado == NO_CASA
    # Dos igual de concretas con precios distintos: ambigua (no se adivina)...
    otra = tarifa(5, 310000, proveedor=7, desde=date(2026, 1, 1))
    assert dataclasses.astuple(_p([vieja, otra])) == (AMBIGUA, None, "parte", (1, 5))
    # ...y con el mismo precio no lo es.
    assert _p([vieja, dataclasses.replace(otra, tarifa_e4=300000)]).estado == UNICA


# ============================================================ G3, G6 y V4

def test_g3_compara_con_la_pactada_retiene_por_encima_y_bloquea_pasado_el_exceso() -> None:
    caro = compra(1)                                                   # 42,50 la hora
    i = inst(con_po(caro, None), tarifas=[tarifa(1, 400000, proveedor=7)])
    g3 = uno("G3", i, 1)
    assert (g3.resultado, g3.severidad, g3.clave) == ("fallo", None, "pactada:1010")
    # Lo que vale la diferencia: 2,50 la hora por 8 horas.
    assert g3.valores["pactada_e4"] == 400000 and g3.valores["valor_cent"] == 2000
    bloquea = inst(con_po(caro, None), tarifas=[tarifa(1, 380000, proveedor=7)])
    assert uno("G3", bloquea, 1).severidad == "bloqueo"                # 11,8 % > 10 %
    holgada = dataclasses.replace(bloquea, politica=Politica(tarifa_exceso_bloqueo_pct=15))
    assert uno("G3", holgada, 1).severidad is None
    barato = inst(con_po(caro, None), tarifas=[tarifa(1, 450000, proveedor=7)])
    assert uno("G3", barato, 1).resultado == "ok"                      # por debajo no retiene


def test_g3_ambigua_da_sin_datos_y_retiene_con_su_excepcion() -> None:
    i = inst(con_po(compra(1), None), tarifas=[tarifa(1, 400000, proveedor=7),
                                               tarifa(2, 410000, proveedor=7)])
    por_clave = {r.clave: r for r in de("G3", i, 1)}
    assert por_clave["pactada:1010"].resultado == "sin_datos"
    ambigua = por_clave["ambigua"]
    assert ambigua.resultado == "fallo" and ambigua.severidad is None  # la de G3: retiene
    assert ambigua.valores == {"imputaciones": [1010], "tarifas": [1, 2]}
    assert catalogo.regla("G3").severidad == "retencion"


def test_g3_sigue_con_el_historico_donde_no_hay_pactada() -> None:
    historico = [con_po(compra(30 + n, numero_norm=f"T{n}", fecha_factura=date(2026, 3 + n, 5),
                               lineas=(linea(300 + n, tarifa_e4=425000 + n * 10000),)), None)
                 for n in range(3)]
    sin_pactadas = inst(*historico)
    con_otra = inst(*historico, tarifas=[tarifa(1, 1, proveedor=99)])
    assert resultados("G3", sin_pactadas) == resultados("G3", con_otra)
    assert any(r.resultado == "fallo" for r in resultados("G3", sin_pactadas))
    # Con pactada, sus lineas salen del historico.
    pactadas = inst(*historico, tarifas=[tarifa(1, 445000, proveedor=7)])
    assert all(r.clave.startswith("pactada:") for r in resultados("G3", pactadas))


def test_g6_un_recargo_a_su_propia_tarifa_y_sin_ella_lo_mira_g3() -> None:
    noche = con_po(compra(1), None, turno="Nacht")
    tarifas = [tarifa(1, 400000, proveedor=7), tarifa(2, 425000, proveedor=7, turno="nacht")]
    i = inst(noche, tarifas=tarifas)
    assert uno("G6", i, 1).resultado == "ok"                    # la de noche, a su tarifa
    assert de("G3", i, 1) == []                                  # y G3 no la mira
    cara = inst(noche, tarifas=[*tarifas[:1], dataclasses.replace(tarifas[1], tarifa_e4=410000)])
    assert uno("G6", cara, 1).resultado == "fallo"
    # Sin tarifa propia pero con la de dia de su proveedor: no casa, y no vuelve al
    # historico (alli una primera factura siempre es "la de siempre"): retiene.
    sin_propia = inst(noche, tarifas=tarifas[:1])
    por_clave = {r.clave: r for r in de("G6", sin_propia, 1)}
    assert por_clave["pactada:1010"].resultado == "sin_datos"
    assert (por_clave["no_casa"].resultado, por_clave["no_casa"].valores) == (
        "fallo", {"imputaciones": [1010], "tarifas": [1]})
    assert de("G3", sin_propia, 1) == []
    # Sin ninguna tarifa pactada de su proveedor, si: no aplica y la mira G3 con el historico.
    sin_ninguna = inst(noche, tarifas=[tarifa(1, 400000, proveedor=99)])
    assert uno("G6", sin_ninguna, 1).resultado == "no_aplica"
    assert de("G3", sin_ninguna, 1)


@pytest.mark.parametrize("cambio", [
    {"turno": "Nacht"}, {"turno": "x"}, {"unidad": "stuk"}, {"fecha": date(2027, 2, 1)},
])
def test_un_turno_una_unidad_o_un_dia_que_no_casan_no_se_saltan_la_pactada(cambio) -> None:
    """El turno, la unidad y el dia los imprime el proveedor: una linea a 60,00 contra una
    pactada de 40,00 (un 50 % por encima) bloquea; con otro turno, otra unidad o fuera de la
    vigencia no puede quedar en ok por volver al historico (una primera factura)."""
    pactada_ = tarifa(1, 400000, proveedor=7, unidad="hora", desde=date(2026, 1, 1),
                      hasta=date(2026, 12, 31))
    lineas = (linea(10, tarifa_e4=600000, importe_cent=48000,
                    unidad=cambio.get("unidad", "hora"),
                    fecha_trabajo=cambio.get("fecha", date(2026, 9, 10))),)
    f = con_po(compra(1, lineas=lineas), None, turno=cambio.get("turno"))
    base = con_po(compra(1, lineas=(dataclasses.replace(lineas[0], unidad="hora",
                                                        fecha_trabajo=date(2026, 9, 10)),)),
                  None)
    assert uno("G3", inst(base, tarifas=[pactada_]), 1).severidad == "bloqueo"
    i = inst(f, tarifas=[pactada_])
    todos = de("G3", i, 1) + de("G6", i, 1)
    assert not any(r.resultado == "ok" for r in todos)
    [retiene] = [r for r in todos if r.clave == "no_casa"]
    assert retiene.resultado == "fallo" and retiene.regla == ("G6" if "turno" in cambio
                                                               else "G3")


def test_una_tarifa_por_dia_casa_con_una_linea_por_dia() -> None:
    """La hoja de tarifas dice "dag" (dia) y la linea imprime "dag": son lo mismo."""
    por_dia = tarifa(1, 4000000, proveedor=7, unidad="dia")
    assert _p([por_dia], unidad="dag").estado == UNICA
    assert _p([por_dia], unidad="Dagen").estado == UNICA
    assert _p([tarifa(2, 1, proveedor=7, unidad="stuk")], unidad="stuks").estado == UNICA
    f = con_po(compra(1, lineas=(linea(10, unidad="dia", tarifa_e4=4500000,
                                       cantidad_mil=1000, importe_cent=45000),)), None)
    assert uno("G3", inst(f, tarifas=[por_dia]), 1).resultado == "fallo"


def test_v4_la_venta_a_la_tarifa_pactada_ni_por_encima_ni_por_debajo() -> None:
    tarifas = [tarifa(1, 425000, sentido="venta", cliente=3)]
    igual = inst(con_po(venta(1), None), tarifas=tarifas)
    assert uno("V4", igual, 1).resultado == "ok"
    for precio in (400000, 450000):
        otra = inst(con_po(venta(1), None), tarifas=[dataclasses.replace(tarifas[0],
                                                                         tarifa_e4=precio)])
        assert uno("V4", otra, 1).resultado == "fallo"
    sin = inst(con_po(venta(1), None), tarifas=[tarifa(2, 1, sentido="venta", cliente=99)])
    assert uno("V4", sin, 1).resultado == "sin_datos"            # el planning, paso 10
    assert resultados("V4", inst(con_po(venta(1), None))) == []  # sin tarifas de venta


# ------------------------------------------------------------ escenarios (pureza)

def escenarios() -> list[Instantanea]:
    """Instantaneas que pasan por cada rama de las reglas del paso 9 (test_pureza_reglas)."""
    pos = [orden(1, valor=50000, inicio=date(2026, 9, 1), fin=date(2026, 11, 10),
                 emision=date(2026, 8, 20), objetos=(8,)),
           orden(2, numero="PO-2", parte=4), orden(3, cerrada=True),
           orden(4, lado="proveedor", parte=7, fin=None, inicio=None),
           orden(5, fin=date(2026, 10, 1)), orden(6, valor=1000)]
    ventas = [
        dataclasses.replace(venta(1, fecha_factura=date(2026, 9, 10)),
                            imputaciones=(imp(1, 10, po=1, objeto=8,
                                              inicio=date(2026, 9, 2), fin=date(2026, 9, 3)),),
                            referencias=(ref(1, "PO-1", po=1), ref(2, "PO-77"),
                                         ref(3, "PO-2"), ref(4, "X", clase="otra"))),
        con_po(venta(2, numero_norm="V2", fecha_factura=date(2026, 9, 20)), 1, 30000,
               objeto=9),
        con_po(venta(3, numero_norm="V3", fecha_factura=None, periodo_inicio=None,
                     periodo_fin=None), 1),
        con_po(venta(4, numero_norm="V4", lineas=(linea(40, fecha_trabajo=date(2026, 9, 9)),)),
               2),
        con_po(venta(5, numero_norm="V5"), 3),
        con_po(venta(6, numero_norm="V6", fecha_factura=date(2026, 10, 1)), 6, objeto=8),
        dataclasses.replace(venta(7, numero_norm="V7", cliente_id=None, parte=None),
                            referencias=(ref(7, "PO-2"),)),
        con_po(abono(8, -12100, sentido="saliente", cliente_id=3, parte="cliente:3"), 1),
        venta(9, numero_norm="V9"),
        con_po(venta(10, numero_norm="V10", anulada=True), 1),
        dataclasses.replace(venta(11, numero_norm="V11", referencias=(ref(11, "PO-9"),
                                                                      ref(12, "PO-8",
                                                                          linea_id=110))),
                            imputaciones=(imp(1100, 110, objeto=8),)),
    ]
    compras = [con_po(compra(20, lineas=(linea(200), linea(201, orden=2, tarifa_e4=None))), 4,
                      recurso=5, objeto=8, servicio="montage"),
               con_po(compra(21, numero_norm="C21"), None, turno="nacht"),
               con_po(compra(22, numero_norm="C22"), None),
               con_po(compra(23, numero_norm="C23", parte=None), None),
               con_po(compra(24, numero_norm="C24", fecha_factura=None), None)]
    tarifas = [tarifa(1, 400000, proveedor=7, recurso=5, objeto=8, po=4, servicio="montage",
                      unidad="hora", desde=date(2026, 1, 1), hasta=date(2026, 12, 31)),
               tarifa(2, 380000, proveedor=7, turno="nacht"),
               tarifa(3, 450000, sentido="venta", cliente=3),
               tarifa(4, 460000, sentido="venta", cliente=3, objeto=8),
               tarifa(5, 470000, sentido="venta", cliente=3, objeto=8)]
    historico = [con_po(compra(30 + n, numero_norm=f"T{n}", fecha_factura=date(2026, 3 + n, 5),
                               proveedor_id=None, parte="btw:NL005555555B01",
                               lineas=(linea(300 + n, tarifa_e4=425000 + n * 10000),)), None)
                 for n in range(3)]
    sin_horas = [con_po(compra(25, numero_norm="C25", periodo_inicio=None, periodo_fin=None),
                        None, turno="nacht", horas=None),
                 con_po(venta(26, numero_norm="V26"), None, horas=None),
                 con_po(compra(28, numero_norm="C28"), None, horas=None)]
    emitida = orden(7, inicio=None, emision=date(2026, 9, 1))
    return [
        inst(*sin_horas, con_po(venta(27, numero_norm="V27"), 7), ordenes=[emitida],
             tarifas=[tarifa(1, 400000, proveedor=7),
                      tarifa(2, 370000, proveedor=7, turno="nacht"),
                      tarifa(3, 450000, sentido="venta", cliente=3)]),
        inst(*ventas, *compras, ordenes=pos, tarifas=tarifas,
             clientes=[cliente(3, True), cliente(4, False)],
             objetos=[objeto(8, requiere_po=False), objeto(9)],
             relaciones=[Relacion(8, 1, "acredita", id=1)]),
        inst(*historico, *compras[2:], tarifas=tarifas[1:2]),
        inst(con_po(venta(1), None), ordenes=[orden(1)], clientes=[cliente(3, True)]),
        inst(con_po(venta(1), None), objetos=[objeto(8, requiere_po=True)],
             clientes=[cliente(3, None)]),
        inst(con_po(venta(1), 1, 120000, inicio=date(2026, 8, 1)),
             ordenes=[orden(1, valor=100000)]),
        # Revision: dos PO impresas sin imputar, lineas que no casan por turno o unidad, y
        # una factura con fecha atrasada que llega la ultima.
        inst(con_po(compra(40, referencias=(ref(40, "PO-1", po=1), ref(41, "PO-2", po=2))),
                    None, turno="x"),
             con_po(compra(41, numero_norm="C41", lineas=(linea(410, unidad="stuk"),)), None),
             con_po(compra(42, numero_norm="C42", fecha_factura=date(2026, 9, 1)), 1, 90000),
             con_po(compra(39, numero_norm="C39", fecha_factura=date(2026, 10, 1)), 1, 90000),
             ordenes=[orden(1, lado="proveedor", parte=7), orden(2, lado="proveedor", parte=7)],
             tarifas=[tarifa(1, 400000, proveedor=7, unidad="dag")]),
    ]
