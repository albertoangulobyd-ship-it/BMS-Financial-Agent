"""El flujo de caja (lista de funciones §7): lo que se espera cobrar y pagar, y lo ya movido.

Lo esperado son las facturas en juego (sin anular, sin fusionar y sin pagar)
por lo que les queda (reglas.pagos.saldo: un pago parcial deja lo que falta,
decision 5), en euros (lo que no lo esta, X1, no entra en ninguna suma), por
su fecha esperada: el vencimiento efectivo (el impreso, o la fecha mas el
plazo acordado; instantanea.vencimientos). "Entrada" es lo que se espera
cobrar (ventas, y abonos de proveedores); "salida", lo que se espera pagar
(compras, y abonos a clientes).

Las ventanas se cuentan desde `hoy` (en Amsterdam, inyectado):

- vencido: con fecha anterior a hoy y sin pagar;
- esta semana: de hoy al domingo de la semana ISO (de lunes a domingo);
- este mes: de hoy al ultimo dia del mes;
- proximos 30 dias: de hoy a hoy + 29 (treinta dias contando hoy);
- un periodo pedido: del dia `desde` al `hasta`, los dos incluidos, tambien si
  ya paso (lo que vencio en el y sigue sin pagar).

Las ventanas que empiezan hoy no llevan lo vencido, que va aparte; el total
lo lleva todo, tambien lo que no tiene fecha (sin vencimiento ni plazo: no
se adivina). Neto es entrada menos salida en cada ventana.

Lo movido (cobrado y pagado) es el dinero que se movio de verdad (decision
5): los movimientos del banco en euros, salvo los traspasos entre cuentas
propias, con su fecha contable en la semana y el mes en curso hasta hoy, o en
el periodo pedido. Va entero, case o no con una factura; lo que no casa se
dice aparte (`sin_casar`). Lo que solo dicen Exact o una persona (la fuente
que manda en una factura sin pagos del banco) no se suma: va en sus lineas,
`segun_exact` y `a_mano`, porque el banco no lo ha visto.

El trabajo sin facturar y el planificado no se mezclan con nada de esto: van
en una linea aparte, "estimado" (decision 22), que llega con el planning
(paso 10). Hasta entonces dice que no hay datos, nunca cero.

Nada de aqui paga ni propone pagar: es una vista.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from . import politica
from .reglas import instantanea
from .reglas.pagos import CONFIRMADA, PRECEDENCIA, en_el_movimiento, saldo, tolerancia_cent
from .reloj import mes_de, semana_de

ENTRADA = "entrada"
SALIDA = "salida"
VENTANAS = ("vencido", "semana", "mes", "proximos_30", "periodo", "sin_fecha", "total")
SIN_ESTIMADO = ("El trabajo sin facturar y el planificado llegan con el planning (paso 10): "
                "todavía no hay datos.")


@dataclass(frozen=True)
class Partida:
    """Lo que queda de una factura, por cobrar (entrada) o por pagar (salida), y cuando."""

    factura_id: int
    direccion: str
    fecha: date | None
    importe_cent: int


BANCO = "banco"
EXACT = "exact"
MANUAL = "manual"
SIN_CASAR = "sin_casar"


@dataclass(frozen=True)
class Movido:
    """Dinero cobrado (entrada) o pagado (salida), cuando y segun quien.

    `origen`: banco (un movimiento, o la parte de el casada con `factura_id`),
    sin_casar (lo de un movimiento que no casa con ninguna factura; tambien es
    banco), exact o manual (lo que dicen Exact o una persona sin el banco).
    """

    factura_id: int | None
    direccion: str
    fecha: date
    importe_cent: int
    origen: str = BANCO


def direccion(sentido: str, importe_cent: int) -> str:
    """Si un importe de una factura entra o sale: una venta cobra, una compra paga; un abono,
    al reves."""
    entra = (sentido == "saliente") == (importe_cent > 0)
    return ENTRADA if entra else SALIDA


def ventanas(hoy: date, desde: date | None = None,
             hasta: date | None = None) -> dict[str, tuple[date, date] | None]:
    """Las ventanas de lo esperado, con sus dos dias incluidos."""
    _lunes, domingo = semana_de(hoy)
    _primero, ultimo = mes_de(hoy)
    return {"semana": (hoy, domingo), "mes": (hoy, ultimo),
            "proximos_30": (hoy, hoy + timedelta(days=29)),
            "periodo": (desde, hasta) if desde is not None and hasta is not None else None}


def _vacio() -> dict[str, int]:
    return {v: 0 for v in VENTANAS}


def calcular(partidas: list[Partida], movidos: list[Movido], hoy: date, *,
             desde: date | None = None, hasta: date | None = None) -> dict[str, Any]:
    """El flujo de caja de unas partidas y unos pagos, visto desde hoy. Puro."""
    if (desde is None) != (hasta is None):
        raise ValueError("un periodo lleva desde y hasta")
    if desde is not None and hasta is not None and desde > hasta:
        raise ValueError("el periodo empieza despues de terminar")
    limites = ventanas(hoy, desde, hasta)
    esperado = {ENTRADA: _vacio(), SALIDA: _vacio()}
    for p in partidas:
        cuentas = esperado[p.direccion]
        cuentas["total"] += p.importe_cent
        if p.fecha is None:
            cuentas["sin_fecha"] += p.importe_cent
            continue
        if p.fecha < hoy:
            cuentas["vencido"] += p.importe_cent
        for nombre, rango in limites.items():
            if rango is not None and rango[0] <= p.fecha <= rango[1] and (
                    nombre == "periodo" or p.fecha >= hoy):
                cuentas[nombre] += p.importe_cent
    if limites["periodo"] is None:
        for cuentas in esperado.values():
            cuentas["periodo"] = None
    neto = {v: (None if esperado[ENTRADA][v] is None
                else esperado[ENTRADA][v] - esperado[SALIDA][v]) for v in VENTANAS}
    lunes, _domingo = semana_de(hoy)
    primero, _ultimo = mes_de(hoy)
    rangos_movidos = {"semana": (lunes, hoy), "mes": (primero, hoy),
                      "periodo": limites["periodo"]}

    def suma(origenes: frozenset[str]) -> dict[str, dict[str, int | None]]:
        salida: dict[str, dict[str, int | None]] = {ENTRADA: {}, SALIDA: {}}
        for nombre, rango in rangos_movidos.items():
            for d in (ENTRADA, SALIDA):
                salida[d][nombre] = None if rango is None else sum(
                    m.importe_cent for m in movidos
                    if m.origen in origenes and m.direccion == d
                    and rango[0] <= m.fecha <= rango[1])
        return salida

    real = suma(frozenset({BANCO, SIN_CASAR}))
    aparte = {nombre: suma(frozenset({origen})) for nombre, origen in (
        ("sin_casar", SIN_CASAR), ("segun_exact", EXACT), ("a_mano", MANUAL))}
    return {
        "hoy": hoy.isoformat(),
        "ventanas": {n: (None if r is None else [r[0].isoformat(), r[1].isoformat()])
                     for n, r in limites.items()},
        "esperado": {"entrada": esperado[ENTRADA], "salida": esperado[SALIDA], "neto": neto},
        "real": {"cobrado": real[ENTRADA], "pagado": real[SALIDA],
                 **{nombre: {"cobrado": cuentas[ENTRADA], "pagado": cuentas[SALIDA]}
                    for nombre, cuentas in aparte.items()},
                 "ventanas": {n: (None if r is None else [r[0].isoformat(), r[1].isoformat()])
                              for n, r in rangos_movidos.items()}},
        "estimado": {"importe_cent": None, "nota": SIN_ESTIMADO},
    }


# ------------------------------------------------------------ del almacen

def _filas(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    cursor = conn.cursor()
    cursor.row_factory = None
    return cursor.execute(sql).fetchall()


def _del_banco(conn: sqlite3.Connection, sentidos: dict[int, str]) -> list[Movido]:
    """Los movimientos del banco en euros, salvo los traspasos entre cuentas propias: la parte
    casada (confirmada) con cada factura y lo que queda sin casar."""
    propias = frozenset(politica.empresa(conn).cuentas_propias)
    casado: dict[int, list] = defaultdict(list)
    for a in instantanea.aplicaciones(conn):
        if a.movimiento_id is not None and a.estado == CONFIRMADA:
            casado[a.movimiento_id].append(a)
    salida = []
    for id_, fecha, importe, contraparte in _filas(
            conn, "SELECT id, fecha_contable, importe_cent, contraparte_iban "
                  "FROM movimiento_bancario WHERE importe_cent IS NOT NULL AND importe_cent <> 0 "
                  "ORDER BY id"):
        if contraparte is not None and contraparte in propias:
            continue
        dia = date.fromisoformat(fecha)
        sentido_ = ENTRADA if importe > 0 else SALIDA
        resto = importe
        for a in casado.get(id_, ()):
            parte = en_el_movimiento(a, sentidos.get(a.factura_id, "entrante"))
            resto -= parte
            salida.append(Movido(a.factura_id, sentido_, dia, abs(parte), BANCO))
        if resto:
            salida.append(Movido(None, ENTRADA if resto > 0 else SALIDA, dia, abs(resto),
                                 SIN_CASAR))
    return salida


def datos(conn: sqlite3.Connection,
          tolerancia: Decimal | None = None) -> tuple[list[Partida], list[Movido]]:
    """Lo que queda de cada factura en juego y el dinero movido (ver el docstring del modulo).

    Del banco, todo lo que movio. De Exact o de una persona, solo lo de las
    facturas en que mandan (sin pagos del banco), marcado con su origen: si
    el banco ya lo trae, lo que dijo Exact o una persona no se suma otra vez.
    """
    tol = tolerancia_cent(tolerancia if tolerancia is not None
                          else politica.politica_reglas(conn).tolerancia_pago)
    vence = instantanea.vencimientos(conn)
    por_factura: dict[int, list] = defaultdict(list)
    for a in instantanea.aplicaciones(conn):
        por_factura[a.factura_id].append(a)
    sentidos = dict(_filas(conn, "SELECT id, sentido FROM factura"))
    partidas, movidos = [], _del_banco(conn, sentidos)
    for id_, sentido, total, anulada, fusionada, moneda in _filas(
            conn, "SELECT id, sentido, total_cent, anulada, fusionada_en_id, moneda_doc "
                  "FROM factura ORDER BY id"):
        if anulada or fusionada is not None or total is None or (
                instantanea.moneda_extranjera(moneda) is not None):
            continue
        s = saldo(total, por_factura.get(id_, ()), tol)
        if s.fuente in (EXACT, MANUAL):
            for a in por_factura[id_]:
                if a.estado == CONFIRMADA and a.fuente == s.fuente:
                    movidos.append(Movido(id_, direccion(sentido, a.importe_cent),
                                          a.fecha_pago, abs(a.importe_cent), s.fuente))
        if s.pagada or not s.pendiente_cent:
            continue
        partidas.append(Partida(id_, direccion(sentido, s.pendiente_cent), vence.get(id_),
                                abs(s.pendiente_cent)))
    return partidas, movidos


def flujo(conn: sqlite3.Connection, hoy: date, *, desde: date | None = None,
          hasta: date | None = None) -> dict[str, Any]:
    """El flujo de caja del almacen visto desde hoy (lo pasa quien llama: el reloj, la CLI)."""
    partidas, movidos = datos(conn)
    salida = calcular(partidas, movidos, hoy, desde=desde, hasta=hasta)
    salida["facturas"] = len(partidas)
    salida["fuentes"] = list(PRECEDENCIA)
    return salida
