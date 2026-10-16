"""Lo trabajado y lo planificado segun el planning, para las vistas (paso 10).

Dos vistas lo usan, y ninguna decide nada (lo deciden las reglas):

- **el estimado del flujo de caja** (decision 22: una linea aparte, marcada
  "estimado", que no se mezcla con lo facturado):
  - por cobrar: lo trabajado hasta hoy (turnos realizados o validados,
    facturables) que no se ha facturado, y lo planificado despues de hoy. De
    un turno conciliado con alguna venta, lo que le falta por conciliar; de
    uno sin conciliar, nada si una venta lo cubre (su linea o su periodo: lo
    que no cuadre lo dicen V1 y V5) y todo si no;
  - por pagar: lo trabajado hasta hoy por un proveedor que ninguna compra ha
    conciliado todavia, y lo planificado despues de hoy;
  valorado a la tarifa pactada de su lado o, si no hay una sola, a la del
  turno en el planning (y entonces es una estimacion aun mas gruesa:
  `aproximado`). Un turno sin ninguna tarifa no suma: se cuenta aparte.
- **las horas de la vista de un Objeto** (§5), por semana ISO: planificadas,
  validadas y facturables segun el planning; facturadas por los proveedores
  (compras) y al cliente (ventas); sin facturar (validadas facturables menos
  facturadas al cliente, en las semanas que ya empezaron); las dos
  diferencias (proveedor y cliente contra lo validado), y lo esperado por
  cobrar y por pagar del Objeto (lo que queda de sus facturas abiertas, en la
  parte imputada al Objeto, mas lo trabajado sin facturar valorado, aparte).

Las horas de una linea de varias semanas se reparten por sus dias (lo que
sobra del redondeo, a la ultima); una linea sin dias va a "sin_semana". De una
semana que ninguna foto del planning cubre, el planning no dice nada: sus
horas del planning y lo sin facturar son sin datos (None), nunca cero; de una
que cubre solo en parte, las horas del planning son las de esos dias y lo sin
facturar, sin datos. Con el planning pasado de su frescura (Z1) el bloque lo
dice ("planning": "caducado"). El corte por mes del §5 (v_objeto_periodo) va
con el paso 12, con los ingresos, costes y margen.
Puro sobre la instantanea (reglas/instantanea.py), con las mismas celdas,
coberturas y tarifas que las reglas.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from .reglas import turnos
from .reglas.base import ENTRANTE, SALIENTE, Instantanea, Turno, caducada, en_juego
from .reglas.tarifas import por_sentido
from .reglas.venta import cubiertos, facturado

SIN_SEMANA = "sin_semana"
_TRABAJADO = (turnos.VALIDADO, "realizado")


@dataclass(frozen=True)
class Estimado:
    """El trabajo sin facturar y el planificado, valorados (centimos, sin IVA)."""

    entrada_sin_facturar_cent: int
    entrada_planificada_cent: int
    salida_sin_facturar_cent: int
    salida_planificada_cent: int
    sin_tarifa: int
    aproximado: bool

    @property
    def neto_cent(self) -> int:
        return (self.entrada_sin_facturar_cent + self.entrada_planificada_cent
                - self.salida_sin_facturar_cent - self.salida_planificada_cent)


class _Valorador:
    """Valora horas de un turno a la tarifa de su lado, contando lo que no tiene tarifa."""

    def __init__(self, instantanea: Instantanea) -> None:
        tarifas = por_sentido(instantanea.tarifas)
        self.venta = tarifas.get("venta", ())
        self.compra = tarifas.get("compra", ())
        self.sin_tarifa: set[tuple[str, str]] = set()
        self.aproximado = False

    def __call__(self, t: Turno, horas_mil: int, lado: str) -> int:
        if horas_mil <= 0:
            return 0
        if lado == SALIENTE:
            precio, estimado = turnos.tarifa_de_venta(t, self.venta)
        else:
            precio, estimado = turnos.tarifa_de_compra(t, self.compra)
        if precio is None:
            self.sin_tarifa.add((lado, t.id_externo))
            return 0
        self.aproximado = self.aproximado or estimado
        return turnos.valor_cent(horas_mil, precio)


def _trabajado(t: Turno, hoy: date) -> bool:
    return t.estado in _TRABAJADO and t.fecha <= hoy


def _por_cobrar(t: Turno, horas: int, vendido: dict[str, tuple[int, frozenset[int]]],
                coberturas: tuple[dict, dict, dict]) -> int:
    """Las horas de un turno trabajado que faltan por facturar al cliente."""
    if t.id_externo in vendido:
        return horas - vendido[t.id_externo][0]
    return 0 if facturado(t, coberturas) else horas


def estimado(instantanea: Instantanea) -> Estimado | None:
    """El estimado del flujo de caja (ver el docstring del modulo); None sin planning."""
    if not instantanea.fotos_planning:
        return None
    hoy = instantanea.hoy
    valorar = _Valorador(instantanea)
    coberturas = cubiertos(instantanea)
    comprado = turnos.conciliado(instantanea, ENTRANTE)
    vendido = turnos.conciliado(instantanea, SALIENTE)
    cuentas = defaultdict(int)
    for t in instantanea.turnos:
        if t.estado == turnos.CANCELADO:
            continue
        horas = turnos.horas_referencia(t)
        if t.cliente_id is not None and t.facturable is not False:
            if t.fecha > hoy:
                cuentas["entrada_planificada_cent"] += valorar(t, horas, SALIENTE)
            elif _trabajado(t, hoy):
                cuentas["entrada_sin_facturar_cent"] += valorar(
                    t, _por_cobrar(t, horas, vendido, coberturas), SALIENTE)
        if t.proveedor_id is not None:
            if t.fecha > hoy:
                cuentas["salida_planificada_cent"] += valorar(t, horas, ENTRANTE)
            elif _trabajado(t, hoy):
                pendiente = horas - comprado.get(t.id_externo, (0,))[0]
                cuentas["salida_sin_facturar_cent"] += valorar(t, pendiente, ENTRANTE)
    return Estimado(cuentas["entrada_sin_facturar_cent"], cuentas["entrada_planificada_cent"],
                    cuentas["salida_sin_facturar_cent"], cuentas["salida_planificada_cent"],
                    len(valorar.sin_tarifa), valorar.aproximado)


def estimado_como_dict(e: Estimado | None, nota_sin_datos: str) -> dict[str, Any]:
    """La linea "estimado" del flujo de caja: sin planning, sin datos (nunca cero)."""
    if e is None:
        return {"importe_cent": None, "nota": nota_sin_datos}
    return {"importe_cent": e.neto_cent, **asdict(e),
            "nota": "Estimado a partir del planning: no son facturas, y no se suma a lo "
                    "esperado." + (" Algún turno sin tarifa pactada va a la tarifa del "
                                   "planning." if e.aproximado else "")
                    + (f" {e.sin_tarifa} turno(s) sin ninguna tarifa no suman."
                       if e.sin_tarifa else "")}


# ------------------------------------------------------------ las horas de un Objeto

def semana_de(dia: date) -> str:
    return turnos.semana_iso(dia)


def repartir(desde: date, hasta: date, horas_mil: int) -> dict[str, int]:
    """Unas horas de unos dias repartidas por semana ISO, por sus dias (el resto, a la ultima)."""
    dias: dict[str, int] = defaultdict(int)
    dia = desde
    while dia <= hasta:
        dias[semana_de(dia)] += 1
        dia += timedelta(days=1)
    total = sum(dias.values())
    salida, repartido = {}, 0
    semanas = sorted(dias)
    for n, semana in enumerate(semanas):
        parte = (horas_mil - repartido if n == len(semanas) - 1
                 else horas_mil * dias[semana] // total)
        salida[semana] = parte
        repartido += parte
    return salida


_COLUMNAS = ("planificadas_mil", "validadas_mil", "facturables_mil", "proveedor_mil",
             "cliente_mil")
ENTERA, PARCIAL, NINGUNA = "entera", "parcial", "ninguna"


def _cobertura(semana: str, cubre: list[tuple[date, date]]) -> str:
    """Cuanto de una semana ISO cubre el planning: entera, en parte o nada."""
    ano, numero = semana.split("-W")
    lunes = date.fromisocalendar(int(ano), int(numero), 1)
    domingo = lunes + timedelta(days=6)
    if turnos.cubierto(lunes, domingo, cubre):
        return ENTERA
    if any(turnos.solapa((lunes, domingo), tramo) for tramo in cubre):
        return PARCIAL
    return NINGUNA


def _facturadas(instantanea: Instantanea, objeto_id: int,
                semanas: dict[str, dict[str, int]]) -> None:
    """Las horas imputadas al Objeto en las facturas en juego, por semana y por lado."""
    for f in instantanea.facturas:
        if not f.imputaciones or not en_juego(f):
            continue
        columna = "proveedor_mil" if f.sentido == ENTRANTE else "cliente_mil"
        lineas = {l.id: l for l in f.lineas}
        for i in f.imputaciones:
            if i.objeto_id != objeto_id or i.horas_mil is None:
                continue
            dias = turnos.dias_de(i, lineas.get(i.linea_id) if i.linea_id is not None else None,
                                  f)
            reparto = (repartir(dias[0], dias[1], i.horas_mil) if dias is not None
                       and (dias[1] - dias[0]).days <= turnos.DIAS_MAXIMOS
                       else {SIN_SEMANA: i.horas_mil})
            for semana, horas in reparto.items():
                semanas[semana][columna] += horas


def importes_por_semana(instantanea: Instantanea, objeto_id: int) -> dict[str, dict[str, int]]:
    """Lo facturado al cliente (ingresos) y por los proveedores (costes) del Objeto, sin IVA,
    por semana ISO de trabajo (paso 12).

    Las mismas imputaciones que v_objeto_periodo (las de facturas en juego con
    base conocida; una en otra moneda la tiene vacia, X1) y los mismos dias que
    las horas de la vista del Objeto (turnos.dias_de): una linea de varias
    semanas se reparte por sus dias, con el resto del redondeo en la ultima, asi
    que la suma de las semanas es lo de siempre del Objeto. Una imputacion sin
    dias va a "sin_semana".
    """
    salida: dict[str, dict[str, int]] = defaultdict(lambda: {"ingresos_cent": 0,
                                                            "costes_cent": 0})
    for f in instantanea.facturas:
        if not f.imputaciones or not en_juego(f) or f.base_cent is None:
            continue
        columna = "costes_cent" if f.sentido == ENTRANTE else "ingresos_cent"
        lineas = {l.id: l for l in f.lineas}
        for i in f.imputaciones:
            if i.objeto_id != objeto_id or not i.importe_cent:
                continue
            dias = turnos.dias_de(i, lineas.get(i.linea_id) if i.linea_id is not None else None,
                                  f)
            reparto = (repartir(dias[0], dias[1], i.importe_cent) if dias is not None
                       and (dias[1] - dias[0]).days <= turnos.DIAS_MAXIMOS
                       else {SIN_SEMANA: i.importe_cent})
            for semana, importe in reparto.items():
                salida[semana][columna] += importe
    return dict(salida)


def _parte_del_objeto(instantanea: Instantanea, objeto_id: int) -> dict[int, tuple[int, int]]:
    """Por factura con algo imputado al Objeto: lo imputado a el y lo imputado en total, en
    valor absoluto.

    Con signos mezclados (un descuento o una correccion en otra linea) la suma
    con signo puede dar al Objeto mas del 100 % de la factura (+10,00 suyo y
    -9,00 de otro Objeto: diez veces lo que queda); en valor absoluto su
    parte nunca pasa de la factura entera.
    """
    salida = {}
    for f in instantanea.facturas:
        if not f.imputaciones:
            continue
        propio = sum(abs(i.importe_cent or 0) for i in f.imputaciones
                     if i.objeto_id == objeto_id)
        total = sum(abs(i.importe_cent or 0) for i in f.imputaciones)
        if propio and total:
            salida[f.id] = (propio, total)
    return salida


def horas_objeto(instantanea: Instantanea, objeto_id: int,
                 pendientes: dict[int, tuple[str, int]] | None = None) -> dict[str, Any]:
    """Las horas de un Objeto por semana ISO y lo esperado de el (ver el docstring del modulo).

    `pendientes`: por factura, si entra o sale y lo que queda por cobrar o pagar
    (flujo_caja.datos). Sin planning, las horas del planning y lo sin facturar
    son sin datos (None, nunca cero); las facturadas se cuentan igual.
    """
    hay_planning = bool(instantanea.fotos_planning)
    cubre = turnos.tramos(instantanea.fotos_planning)
    hoy = instantanea.hoy
    semanas: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(_COLUMNAS, 0))
    valorar = _Valorador(instantanea)
    comprado = turnos.conciliado(instantanea, ENTRANTE)
    vendido = turnos.conciliado(instantanea, SALIENTE)
    coberturas = cubiertos(instantanea)
    sin_facturar_venta = sin_facturar_compra = 0
    for t in instantanea.turnos:
        if t.objeto_id != objeto_id or t.estado == turnos.CANCELADO:
            continue
        fila = semanas[semana_de(t.fecha)]
        fila["planificadas_mil"] += (t.horas_planificadas_mil
                                     if t.horas_planificadas_mil is not None
                                     else turnos.horas_referencia(t))
        if t.estado == turnos.VALIDADO and t.horas_aprobadas_mil is not None:
            fila["validadas_mil"] += t.horas_aprobadas_mil
            if t.facturable is not False:
                fila["facturables_mil"] += t.horas_aprobadas_mil
        if not _trabajado(t, hoy):
            continue
        horas = turnos.horas_referencia(t)
        if t.cliente_id is not None and t.facturable is not False:
            sin_facturar_venta += valorar(t, _por_cobrar(t, horas, vendido, coberturas),
                                          SALIENTE)
        if t.proveedor_id is not None:
            sin_facturar_compra += valorar(t, horas - comprado.get(t.id_externo, (0,))[0],
                                           ENTRANTE)
    _facturadas(instantanea, objeto_id, semanas)

    actual = semana_de(hoy)
    filas = []
    for semana in sorted(semanas, key=lambda s: (s == SIN_SEMANA, s)):
        fila = semanas[semana]
        cobertura = (_cobertura(semana, cubre) if hay_planning and semana != SIN_SEMANA
                     else None)
        con_planning = cobertura in (ENTERA, PARCIAL)
        empezada = semana != SIN_SEMANA and semana <= actual
        filas.append({
            "semana": semana,
            "cobertura": cobertura,
            **{c: (fila[c] if con_planning or c in ("proveedor_mil", "cliente_mil") else None)
               for c in _COLUMNAS},
            "sin_facturar_mil": (max(fila["facturables_mil"] - fila["cliente_mil"], 0)
                                 if cobertura == ENTERA and empezada else None),
            "diferencia_proveedor_mil": (fila["proveedor_mil"] - fila["validadas_mil"]
                                         if con_planning and fila["validadas_mil"] else None),
            "diferencia_cliente_mil": (fila["cliente_mil"] - fila["facturables_mil"]
                                       if con_planning and fila["facturables_mil"] else None),
        })
    total: dict[str, Any] = {"cobertura": None}
    for clave in (*_COLUMNAS, "sin_facturar_mil"):
        valores = [f[clave] for f in filas if f[clave] is not None]
        total[clave] = sum(valores) if valores or clave in ("proveedor_mil", "cliente_mil") \
            else None
    if not hay_planning:
        total["sin_facturar_mil"] = None

    # Lo esperado es dinero: entra lo que se cobra (ventas, abonos de proveedores) y sale
    # lo que se paga, como en el flujo de caja.
    abierto = {"entrada": 0, "salida": 0}
    for factura_id, (propio, total_imputado) in _parte_del_objeto(instantanea,
                                                                  objeto_id).items():
        direccion, importe = (pendientes or {}).get(factura_id, (None, 0))
        if direccion in abierto:
            abierto[direccion] += importe * propio // total_imputado
    return {
        "planning": (("caducado" if caducada(instantanea, "trnsprnt") else "ok") if hay_planning
                     else "sin_datos"),
        "semanas": filas,
        "total": total,
        "esperado": {
            "entrante_cent": abierto["entrada"],
            "saliente_cent": abierto["salida"],
            "entrante_estimado_cent": sin_facturar_venta if hay_planning else None,
            "saliente_estimado_cent": sin_facturar_compra if hay_planning else None,
            "aproximado": valorar.aproximado,
            "sin_tarifa": len(valorar.sin_tarifa),
        },
    }
