"""El planning visto por las reglas: celdas, horas de referencia y lo que cubre (paso 10).

Una imputacion (una linea de factura, o una parte de ella) se compara con el
planning en su **celda**: el nivel mas fino que llevan los dos lados (§7, G2).
Por el lado de la factura, una linea de un dia, de una semana (sus fechas, o
el numero de semana impreso con el ano de la fecha de la factura) o de un
periodo (sus fechas, o el periodo de la cabecera); por el del planning, turnos
de un dia o filas semanales (la exportacion pivotada se lee a nivel de
semana). La celda es:

- la persona (el recurso) si la imputacion la nombra y el planning tiene sus
  turnos en esos dias; si no, el Objeto. Con persona y Objeto, solo los turnos
  de esa persona en ese Objeto;
- de un dia si la linea es de un dia y el planning de esos dias es diario;
- de una semana si la linea es de una semana entera, o si cae dentro de una
  semana de la que el planning solo tiene la fila semanal (entonces se
  compara la semana: todas las horas de la factura en esa semana contra la
  fila);
- de un periodo en lo demas (una linea de varias semanas, o de unos dias que
  no son una semana entera). Una fila semanal que cae solo en parte dentro
  del periodo no se puede partir: la celda queda sin datos.

En una compra solo cuentan los turnos de su proveedor; en una venta, los
facturables de su cliente. Un turno cancelado no cuenta nunca. Las horas
que se comparan (G2, V1) son las validadas: una celda con algun turno sin
validar da sin datos. La tolerancia es la de la politica por cada dia con
turnos de la celda (`dias`: uno por dia distinto; los de una fila semanal,
los suyos).

Lo que cubre el planning es la union de lo que cubren sus fotos aceptadas:
una celda con algun dia fuera da sin datos (el planning no dice nada de
ese dia), nunca un "no hay turnos".

Puro: lo usan las reglas (sobre la instantanea) y conciliacion.py (sobre el
planning del almacen), y asi la traza y las reglas ven las mismas celdas.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import date, timedelta
from typing import NamedTuple

from ..dominio import EstadoTurno, NivelConciliacion, NivelTurno, TipoFactura
from .base import (
    ENTRANTE,
    SIN_DATOS,
    Factura,
    FotoPlanning,
    Imputacion,
    Instantanea,
    Linea,
    Resultado,
    Tarifa,
    Turno,
    caducada,
    en_juego,
)
from .tarifas import UNICA, pactada

CANCELADO = EstadoTurno.CANCELADO.value
FACTURA = TipoFactura.FACTURA.value
VALIDADO = EstadoTurno.VALIDADO.value
SEMANAL = NivelTurno.SEMANA.value
RECURSO = "recurso"
OBJETO = "objeto"
PROVEEDOR = "proveedor"
CLIENTE = "cliente"
_NIVEL = {(RECURSO, "dia"): NivelConciliacion.RECURSO_DIA.value,
          (OBJETO, "dia"): NivelConciliacion.OBJETO_DIA.value,
          (RECURSO, "semana"): NivelConciliacion.RECURSO_SEMANA.value,
          (OBJETO, "semana"): NivelConciliacion.OBJETO_SEMANA.value,
          (RECURSO, "periodo"): NivelConciliacion.RECURSO_PERIODO.value,
          (OBJETO, "periodo"): NivelConciliacion.OBJETO_PERIODO.value}
# Un periodo de mas de esto no se compara dia a dia: es una linea que no dice
# de cuando es (un ano entero), no trabajo que se pueda poner en celdas.
DIAS_MAXIMOS = 92


# ------------------------------------------------------------ los dias de una imputacion

def semana_impresa(numero: int, fecha_factura: date) -> date | None:
    """El lunes de la semana `numero` que una factura quiere decir: la mas cercana a su fecha.

    Una factura imprime "semana 52" sin ano; el ano lo da su fecha. La del 6
    de enero de 2027 por la semana 52 es la 2026-W52 (del 21 al 27 de
    diciembre), no la 2027-W52; la del 12 de octubre por la semana 43 (que se
    factura por adelantado) es la de ese mismo ano. Se mira la semana con ese
    numero del ano ISO de la factura, del anterior y del siguiente, y vale la
    que empieza mas cerca de la fecha (a igual distancia, la anterior).
    """
    ano = fecha_factura.isocalendar()[0]
    candidatas = []
    for candidato in (ano - 1, ano, ano + 1):
        try:
            lunes = date.fromisocalendar(candidato, numero, 1)
        except ValueError:
            continue
        candidatas.append((abs((lunes - fecha_factura).days), lunes))
    return min(candidatas)[1] if candidatas else None


def dias_de(i: Imputacion, linea: Linea | None, factura: Factura) -> tuple[date, date] | None:
    """De que dias es una imputacion: los suyos, el dia de trabajo o las fechas de su linea,
    la semana impresa (con el ano de la fecha de la factura) o el periodo de la cabecera."""
    desde = i.fecha_inicio or (linea.fecha_trabajo or linea.fecha_inicio if linea else None)
    hasta = i.fecha_fin or (linea.fecha_trabajo or linea.fecha_fin if linea else None)
    if desde is not None or hasta is not None:
        desde, hasta = desde or hasta, hasta or desde
        return (desde, hasta) if desde <= hasta else (hasta, desde)
    if linea is not None and linea.semana_doc is not None and factura.fecha_factura is not None:
        lunes = semana_impresa(linea.semana_doc, factura.fecha_factura)
        if lunes is not None:
            return lunes, lunes + timedelta(days=6)
    if factura.periodo_inicio is not None and factura.periodo_fin is not None:
        return factura.periodo_inicio, factura.periodo_fin
    return None


def lunes_de(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def semana_entera(desde: date, hasta: date) -> bool:
    return desde.weekday() == 0 and hasta == desde + timedelta(days=6)


def semana_iso(dia: date) -> str:
    ano, semana, _ = dia.isocalendar()
    return f"{ano:04d}-W{semana:02d}"


def horas_de(i: Imputacion) -> int | None:
    """Las horas de una imputacion (las de su linea si es por horas, campos._horas)."""
    return i.horas_mil


# ------------------------------------------------------------ lo que cubre el planning

def tramos(fotos: Iterable[FotoPlanning]) -> list[tuple[date, date]]:
    """Lo que cubren las fotos aceptadas, unido en tramos sin huecos."""
    ordenados = sorted((f.cubre_desde, f.cubre_hasta) for f in fotos
                       if f.cubre_desde is not None and f.cubre_hasta is not None)
    salida: list[list[date]] = []
    for desde, hasta in ordenados:
        if salida and desde <= salida[-1][1] + timedelta(days=1):
            salida[-1][1] = max(salida[-1][1], hasta)
        else:
            salida.append([desde, hasta])
    return [(d, h) for d, h in salida]


def cubierto(desde: date, hasta: date, cubre: Sequence[tuple[date, date]]) -> bool:
    return any(d <= desde and hasta <= h for d, h in cubre)


# ------------------------------------------------------------ horas de un turno

def horas_referencia(t: Turno) -> int:
    """Las horas que tiene un turno: las validadas, si no las realizadas, si no las
    planificadas; cero si esta cancelado (lo mismo que v_planning_estado)."""
    if t.estado == CANCELADO:
        return 0
    for horas in (t.horas_aprobadas_mil, t.horas_realizadas_mil, t.horas_planificadas_mil):
        if horas is not None:
            return horas
    return 0


def ultimo_dia(t: Turno) -> date:
    return t.fecha + timedelta(days=6) if t.nivel == SEMANAL else t.fecha


# ------------------------------------------------------------ el indice y las celdas

Filtro = Callable[[Turno], bool]


class Indice:
    """Los turnos que cuentan (no cancelados), por persona, por Objeto y por proveedor o
    cliente, por dia o (las filas semanales) por el lunes de su semana."""

    def __init__(self, turnos: Iterable[Turno]) -> None:
        self.por_dia: dict[tuple[str, int, date], list[Turno]] = defaultdict(list)
        self.por_semana: dict[tuple[str, int, date], list[Turno]] = defaultdict(list)
        for t in turnos:
            if t.estado == CANCELADO:
                continue
            destino = self.por_semana if t.nivel == SEMANAL else self.por_dia
            for dimension, clave in ((RECURSO, t.recurso_id), (OBJETO, t.objeto_id),
                                     (PROVEEDOR, t.proveedor_id), (CLIENTE, t.cliente_id)):
                if clave is not None:
                    destino[(dimension, clave, t.fecha)].append(t)

    def de(self, dimension: str, clave: int, desde: date, hasta: date
           ) -> tuple[list[Turno], list[Turno]]:
        """Los turnos diarios de esos dias y las filas semanales de las semanas que tocan."""
        diarios: list[Turno] = []
        if (hasta - desde).days <= DIAS_MAXIMOS:
            dia = desde
            while dia <= hasta:
                diarios.extend(self.por_dia.get((dimension, clave, dia), ()))
                dia += timedelta(days=1)
        semanales: list[Turno] = []
        lunes = lunes_de(desde)
        while lunes <= hasta and (lunes - desde).days <= DIAS_MAXIMOS:
            semanales.extend(self.por_semana.get((dimension, clave, lunes), ()))
            lunes += timedelta(days=7)
        return diarios, semanales


class Celda(NamedTuple):
    """Donde se compara una imputacion: persona u Objeto, unos dias y el nivel (dia, semana o
    periodo, ya con su dimension: NivelConciliacion). `objeto_id`, el de la imputacion (con
    persona, solo sus turnos en ese Objeto)."""

    dimension: str
    clave: int
    objeto_id: int | None
    desde: date
    hasta: date
    nivel: str


class Contenido(NamedTuple):
    """Lo que tiene el planning en una celda: sus turnos, cuantos dias con turnos (para la
    tolerancia) y si una fila semanal cae solo en parte dentro (no se puede partir)."""

    turnos: tuple[Turno, ...]
    dias: int
    parcial: bool


def _filtrados(turnos: Iterable[Turno], filtro: Filtro, objeto_id: int | None,
               dimension: str) -> list[Turno]:
    return [t for t in turnos if filtro(t)
            and (dimension == OBJETO or objeto_id is None or t.objeto_id == objeto_id)]


def celda_de(i: Imputacion, linea: Linea | None, factura: Factura, indice: Indice,
             filtro: Filtro) -> Celda | None:
    """La celda de una imputacion (ver el docstring del modulo). None si no tiene dias, ni
    persona ni Objeto."""
    dias = dias_de(i, linea, factura)
    if dias is None or (dias[1] - dias[0]).days > DIAS_MAXIMOS:
        return None
    desde, hasta = dias
    dimension, clave = None, None
    if i.recurso_id is not None:
        diarios, semanales = indice.de(RECURSO, i.recurso_id, lunes_de(desde),
                                       lunes_de(hasta) + timedelta(days=6))
        if _filtrados(diarios + semanales, filtro, i.objeto_id, RECURSO):
            dimension, clave = RECURSO, i.recurso_id
    if dimension is None:
        if i.objeto_id is not None:
            dimension, clave = OBJETO, i.objeto_id
        elif i.recurso_id is not None:
            dimension, clave = RECURSO, i.recurso_id
        else:
            return None
    _diarios, semanales = indice.de(dimension, clave, desde, hasta)
    semanales = _filtrados(semanales, filtro, i.objeto_id, dimension)
    if semanales and lunes_de(desde) == lunes_de(hasta):
        desde, hasta, tamano = lunes_de(desde), lunes_de(desde) + timedelta(days=6), "semana"
    elif desde == hasta:
        tamano = "dia"
    elif semana_entera(desde, hasta):
        tamano = "semana"
    else:
        tamano = "periodo"
    return Celda(dimension, clave, i.objeto_id, desde, hasta, _NIVEL[(dimension, tamano)])


def contenido(celda: Celda, indice: Indice, filtro: Filtro) -> Contenido:
    """Los turnos de una celda que pasan el filtro (la parte de la factura)."""
    diarios, semanales = indice.de(celda.dimension, celda.clave, celda.desde, celda.hasta)
    diarios = [t for t in _filtrados(diarios, filtro, celda.objeto_id, celda.dimension)
               if celda.desde <= t.fecha <= celda.hasta]
    semanales = _filtrados(semanales, filtro, celda.objeto_id, celda.dimension)
    parcial = any(t.fecha < celda.desde or ultimo_dia(t) > celda.hasta for t in semanales)
    dias = len({t.fecha for t in diarios}) + sum(t.dias for t in semanales)
    turnos = tuple(sorted(diarios + semanales,
                          key=lambda t: (t.fecha, t.hora_inicio or "", t.id_externo, t.id)))
    return Contenido(turnos, dias, parcial)


def de_la_parte(factura: Factura) -> Filtro:
    """Los turnos que cuentan para una factura: los de su proveedor en una compra, los
    facturables de su cliente en una venta."""
    if factura.sentido == "entrante":
        proveedor = factura.proveedor_id
        return lambda t: t.proveedor_id == proveedor
    cliente = factura.cliente_id
    return lambda t: t.cliente_id == cliente and t.facturable is not False


def tolerancia_mil(politica_horas_dia: int, dias: int) -> int:
    """La tolerancia de una celda: la de la politica por cada dia con turnos (al menos uno)."""
    return politica_horas_dia * max(1, dias)


# ------------------------------------------------------------ periodos de facturacion

def periodo_mensual(dia: date) -> tuple[date, date]:
    primero = dia.replace(day=1)
    siguiente = date(primero.year + (primero.month == 12), primero.month % 12 + 1, 1)
    return primero, siguiente - timedelta(days=1)


def _inicio_de_mes(ano: int, mes: int, dia_ancla: int) -> date:
    """El dia del ancla en ese mes (el ultimo si el mes es mas corto)."""
    ano, mes = ano + (mes - 1) // 12, (mes - 1) % 12 + 1
    return date(ano, mes, min(dia_ancla, periodo_mensual(date(ano, mes, 1))[1].day))


def periodo_de_ciclo(frecuencia: str, ancla: date, dia: date) -> tuple[date, date]:
    """El periodo de un ciclo de facturacion que contiene `dia`: semanas o bloques de cuatro
    semanas contados desde el ancla, o meses que empiezan el dia del mes del ancla."""
    if frecuencia in ("semanal", "cuatrisemanal"):
        largo = 7 if frecuencia == "semanal" else 28
        inicio = ancla + timedelta(days=((dia - ancla).days // largo) * largo)
        return inicio, inicio + timedelta(days=largo - 1)
    inicio = _inicio_de_mes(dia.year, dia.month, ancla.day)
    if inicio > dia:
        inicio = _inicio_de_mes(dia.year, dia.month - 1, ancla.day)
    siguiente = _inicio_de_mes(inicio.year, inicio.month + 1, ancla.day)
    return inicio, siguiente - timedelta(days=1)


def solapa(a: tuple[date, date], b: tuple[date, date]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


# ------------------------------------------------------------ la pasada de una regla

SIN_PLANNING = ("No se ha importado ningún planning de TRNSPRNT: no hay con qué comparar "
                "(bms-agent importar trnsprnt planning).")


def sin_planning(instantanea: Instantanea, regla: str) -> list[Resultado] | None:
    """Sin ninguna foto del planning, la regla da un solo sin_datos (del planning, no de cada
    factura): nunca ok, y sin llenar la cache con un sin_datos por factura y regla."""
    if instantanea.fotos_planning:
        return None
    return [Resultado(regla, "planning", 0, SIN_DATOS, SIN_PLANNING)]


class Planificacion:
    """Lo que una regla necesita del planning en una pasada: el indice de los turnos, lo que
    cubren las fotos, si el planning esta pasado de su frescura (Z1) y la tolerancia."""

    def __init__(self, instantanea: Instantanea) -> None:
        self.cubre = tramos(instantanea.fotos_planning)
        self.caducado = bool(caducada(instantanea, "trnsprnt"))
        self.indice = Indice(instantanea.turnos)
        self.tolerancia = int(instantanea.politica.planning_tolerancia_horas_dia * 1000)
        self.hoy = instantanea.hoy

    def sin_datos(self, desde: date, hasta: date) -> str | None:
        """Por que no se puede mirar el planning de esos dias, o None si se puede."""
        if self.caducado:
            return ("El planning de TRNSPRNT está pasado de su frescura (Z1): no se compara "
                    "con él hasta que llegue uno al día.")
        if not cubierto(desde, hasta, self.cubre):
            return (f"El planning importado no cubre del {desde.isoformat()} al "
                    f"{hasta.isoformat()}: no dice nada de esos días.")
        return None


class Grupo(NamedTuple):
    """Las imputaciones con horas de una factura que caen en la misma celda, y sus horas."""

    factura: Factura
    celda: Celda
    imputaciones: tuple[Imputacion, ...]
    horas_mil: int

    @property
    def clave(self) -> str:
        """La identidad de su resultado: su primera imputacion (no depende de lo resuelto)."""
        return f"imputacion:{min(i.id for i in self.imputaciones)}"


class Suelta(NamedTuple):
    """Una imputacion con horas que no tiene celda, y por que."""

    factura: Factura
    imputacion: Imputacion
    motivo: str


def _parte(factura: Factura) -> int | None:
    return factura.proveedor_id if factura.sentido == ENTRANTE else factura.cliente_id


def agrupar(instantanea: Instantanea, sentido: str,
            indice: Indice) -> tuple[list[Grupo], list[Suelta]]:
    """Las imputaciones con horas de las facturas en juego de un sentido, por celda.

    Un abono no es trabajo: no entra. Sin la parte resuelta no se sabe que
    turnos son suyos (A0 lo dice); sin dias, ni persona ni Objeto no hay celda.
    """
    grupos: dict[tuple[int, Celda], list[Imputacion]] = defaultdict(list)
    facturas: dict[int, Factura] = {}
    sueltas: list[Suelta] = []
    for f in instantanea.facturas:
        if (f.sentido != sentido or f.tipo != FACTURA or not f.imputaciones
                or not en_juego(f)):
            continue
        lineas: dict[int, Linea] | None = None
        filtro = de_la_parte(f)
        for i in f.imputaciones:
            if i.horas_mil is None:
                continue
            if _parte(f) is None:
                sueltas.append(Suelta(f, i, "La factura no tiene su "
                                            f"{'proveedor' if sentido == ENTRANTE else 'cliente'}"
                                            " resuelto: no se sabe qué turnos son suyos."))
                continue
            if lineas is None:
                lineas = {l.id: l for l in f.lineas}
            celda = celda_de(i, lineas.get(i.linea_id) if i.linea_id is not None else None, f,
                             indice, filtro)
            if celda is None:
                sueltas.append(Suelta(f, i, "La línea no dice de qué días es, o no nombra ni "
                                            "persona ni Objeto: no se puede poner en el "
                                            "planning."))
                continue
            grupos[(f.id, celda)].append(i)
            facturas[f.id] = f
    salida = [Grupo(facturas[factura_id], celda, tuple(imputaciones),
                    sum(i.horas_mil for i in imputaciones))
              for (factura_id, celda), imputaciones in grupos.items()]
    salida.sort(key=lambda g: (g.factura.id, min(i.id for i in g.imputaciones)))
    return salida, sueltas


def conciliado(instantanea: Instantanea, sentido: str) -> dict[str, tuple[int, frozenset[int]]]:
    """Por turno (su id_externo), las horas de las facturas en juego de un sentido conciliadas
    con el, y de que facturas (la traza de conciliacion.py)."""
    del_sentido = {f.id for f in instantanea.facturas if f.sentido == sentido and en_juego(f)}
    horas: dict[str, int] = defaultdict(int)
    facturas: dict[str, set[int]] = defaultdict(set)
    for c in instantanea.conciliaciones:
        if c.factura_id in del_sentido:
            horas[c.turno.id_externo] += c.horas_mil
            facturas[c.turno.id_externo].add(c.factura_id)
    return {clave: (horas[clave], frozenset(facturas[clave])) for clave in horas}


def valor_cent(horas_mil: int, tarifa_e4: int) -> int:
    """Lo que valen unas horas a una tarifa, en centimos (truncado, como G3)."""
    return horas_mil * tarifa_e4 // 100000


def tarifa_de_venta(t: Turno, tarifas_venta: Sequence[Tarifa]) -> tuple[int | None, bool]:
    """La tarifa con que se valora un turno: la de venta pactada si hay una sola (no es una
    estimacion) o, si no, la del turno en el planning (estimada). None si ninguna."""
    if tarifas_venta:
        p = pactada(tarifas_venta, parte_id=t.cliente_id, recurso_id=t.recurso_id,
                    objeto_id=t.objeto_id, orden_compra_id=t.orden_compra_id,
                    turno=t.tipo_turno, servicio=t.tipo_servicio, unidad="hora", fecha=t.fecha)
        if p.estado == UNICA:
            return p.tarifa_e4, False
    return t.tarifa_venta_e4, True


def tarifa_de_compra(t: Turno, tarifas_compra: Sequence[Tarifa]) -> tuple[int | None, bool]:
    """Como tarifa_de_venta, para lo que se compra (las PO de un proveedor)."""
    if tarifas_compra:
        p = pactada(tarifas_compra, parte_id=t.proveedor_id, recurso_id=t.recurso_id,
                    objeto_id=t.objeto_id, orden_compra_id=t.orden_compra_id,
                    turno=t.tipo_turno, servicio=t.tipo_servicio, unidad="hora", fecha=t.fecha)
        if p.estado == UNICA:
            return p.tarifa_e4, False
    return t.tarifa_compra_e4, True


# Lo que leen agrupar, celda_de, contenido e Indice (y la Planificacion) de la
# instantanea: lo declaran las reglas que los usan.
LEE_PLANIFICACION = frozenset({
    "instantanea.fotos_planning", "instantanea.turnos", "instantanea.politica",
    "instantanea.hoy", "instantanea.lotes", "politica.planning_tolerancia_horas_dia",
    "politica.frescura_trnsprnt_dias", "foto_planning.cubre_desde", "foto_planning.cubre_hasta",
    "lote.fuente", "lote.estado", "lote.id", "lote.exportado",
    "turno.estado", "turno.nivel", "turno.recurso_id", "turno.objeto_id", "turno.proveedor_id",
    "turno.cliente_id", "turno.fecha",
})
LEE_DIAS = frozenset({
    "factura.fecha_factura", "factura.periodo_inicio", "factura.periodo_fin",
    "linea.fecha_trabajo", "linea.fecha_inicio", "linea.fecha_fin", "linea.semana_doc",
    "imputacion.fecha_inicio", "imputacion.fecha_fin",
})
LEE_CELDA = LEE_DIAS | frozenset({"imputacion.recurso_id", "imputacion.objeto_id",
                                  "factura.sentido"})
# La parte de una factura y que turnos son suyos (de_la_parte): en una compra su
# proveedor; en una venta su cliente, y si el turno es facturable.
LEE_COMPRA = frozenset({"factura.proveedor_id"})
LEE_VENTA = frozenset({"factura.cliente_id", "turno.facturable"})
LEE_GRUPOS = LEE_CELDA | frozenset({
    "instantanea.facturas", "factura.id", "factura.sentido", "factura.tipo",
    "factura.imputaciones", "factura.anulada", "factura.fusionada_en_id",
    "factura.sustituida_por", "factura.lineas", "linea.id", "imputacion.id",
    "imputacion.horas_mil", "imputacion.linea_id",
})
LEE_CONTENIDO = frozenset({"turno.hora_inicio", "turno.id_externo", "turno.id", "turno.dias"})
LEE_CONCILIADO = frozenset({"instantanea.conciliaciones", "conciliacion.factura_id",
                            "conciliacion.turno", "conciliacion.horas_mil"})
