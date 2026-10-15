"""Reglas de pagos (spec §7, K1-K8) y lo puro de lo pagado: el saldo de una factura.

Lo pagado de una factura son sus aplicaciones confirmadas de la fuente que
manda: el banco si hay alguna del banco; si no, Exact; si no, lo marcado a
mano (decision 5 y §9). Una factura esta pagada cuando eso deja su saldo
dentro de la tolerancia (por defecto, al centimo); un pago parcial la deja
pendiente o vencida con lo que queda, y K2 lo dice. Lo usan las reglas, las
caches de estado (estados.py) y el flujo de caja: una sola cuenta.

Las reglas:

- K1 vencida (una compra desde el dia siguiente a su vencimiento, una venta
  pasados N dias): aviso con excepcion. Sin un extracto que cubra desde la
  fecha de la factura (o un Exact de pagos al dia), no se sabe si se pago: sin
  datos.
- K2 lo confirmado no es el saldo (parcial o de mas): retiene una compra,
  avisa de una venta. Ni se anula ni se cierra sola.
- K3 marcada pagada a mano y, pasados N dias, sin rastro en el banco: aviso.
- K4 pago doble: dos cargos del banco a la misma cuenta, por el mismo importe y
  con la misma referencia en menos de N dias, o una factura pagada de mas con
  dos o mas cargos. Bloquea.
- K5 pagada mientras estaba Bloqueada (un hallazgo que bloquea, pendiente y
  sin anular, ese dia). Retiene.
- K6 la cadena de extractos de una cuenta se rompe: el saldo de apertura no
  es el de cierre del anterior, o falta un numero de secuencia. Bloquea el
  extracto y cada factura pagada con un movimiento de ese extracto o de los
  siguientes de la cuenta. Los CSV del banco (sin saldos) no se miran.
- K7 un movimiento del banco sin casar pasados N dias: aviso.
- K8 el banco y Exact no dicen lo mismo de lo pagado de una factura: retiene.

K2, K4, K5 y K6 son pegajosas y no se anulan (decision 12 para K2, K4 y K6).
Los traspasos entre cuentas propias y los pagos a beneficiarios conocidos
(Belastingdienst, nominas, alquiler) no son pagos de facturas: K4 y K7 no los
miran.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import Any, NamedTuple

from .base import (
    ENTRANTE,
    FALLO,
    LEE_EN_JUEGO,
    RELACIONADO,
    VALIDOS,
    Aplicacion,
    Extracto,
    Factura,
    Instantanea,
    Movimiento,
    Objetivo,
    Resultado,
    caducada,
    edad,
    euros,
    euros_texto,
    fallo,
    sin_datos,
    solo_objeciones,
)

CONFIRMADA = "confirmada"
PROPUESTA = "propuesta"
BANCO = "banco"
EXACT = "exact"
MANUAL = "manual"
# Que fuente manda en el saldo, de mas a menos (dominio.PRECEDENCIA_PAGO).
PRECEDENCIA = (BANCO, EXACT, MANUAL)


# ------------------------------------------------------------ el saldo

class Saldo(NamedTuple):
    """Lo pagado de una factura segun la fuente que manda, y lo que queda."""

    total_cent: int | None
    pagado_cent: int
    fuente: str | None
    pagos: int
    pendiente_cent: int | None
    pagada: bool


def tolerancia_cent(tolerancia: Any) -> int:
    """La tolerancia de la politica (un Decimal en euros) en centimos, sin floats."""
    return int(tolerancia.scaleb(2).to_integral_value())


def saldo(total_cent: int | None, aplicaciones: Iterable[Any], tolerancia: int) -> Saldo:
    """El saldo de una factura con sus aplicaciones (cualquier cosa con estado, fuente e
    importe_cent). Pagada solo si hay algo confirmado y deja el saldo en la tolerancia."""
    confirmadas = [a for a in aplicaciones if a.estado == CONFIRMADA]
    for fuente in PRECEDENCIA:
        propias = [a for a in confirmadas if a.fuente == fuente]
        if propias:
            pagado = sum(a.importe_cent for a in propias)
            pendiente = None if total_cent is None else total_cent - pagado
            return Saldo(total_cent, pagado, fuente, len(propias), pendiente,
                         pendiente is not None and abs(pendiente) <= tolerancia)
    return Saldo(total_cent, 0, None, 0, total_cent, False)


def en_el_movimiento(aplicacion: Any, sentido: str) -> int:
    """Lo que una aplicacion se lleva del movimiento, en el signo del movimiento.

    En una compra se paga: el cargo es negativo y baja el saldo. En una venta
    se cobra: el abono es positivo.
    """
    return -aplicacion.importe_cent if sentido == ENTRANTE else aplicacion.importe_cent


# ------------------------------------------------------------ el contexto de una pasada

class Contexto(NamedTuple):
    """Lo que las reglas K necesitan, calculado una vez por pasada."""

    hoy: date
    por_factura: dict[int, list[Aplicacion]]
    por_movimiento: dict[int, list[Aplicacion]]
    movimientos: dict[int, Movimiento]
    extractos: dict[int, Extracto]
    sentido: dict[int, str]
    banco_desde: date | None
    banco_hasta: date | None
    banco_caducado: bool
    exact_al_dia: bool
    tolerancia: int
    ajenos: frozenset[str]           # cuentas propias y beneficiarios conocidos
    rotos: dict[str, tuple[Extracto, ...]]   # por cuenta, los extractos desde la rotura (K6)
    bloqueos: dict[int, list[Any]]


def _exact_al_dia(instantanea: Instantanea) -> bool:
    """Si hay un Exact de pagos aceptado y dentro de su frescura."""
    pagos = [l for l in instantanea.lotes if l.fuente == EXACT and l.tipo == "pagos_exact"
             and l.estado in VALIDOS]
    if not pagos:
        return False
    ultimo = max(pagos, key=lambda l: l.id)
    return edad(ultimo, instantanea.hoy, EXACT) <= instantanea.politica.frescura_exact_dias


def roturas(extractos: Iterable[Extracto]) -> dict[str, list[tuple[Extracto, str]]]:
    """Por cuenta, cada extracto con saldos que rompe la cadena y por que.

    Se ordenan por fechas y numero. Rompe la cadena un extracto cuyo saldo de
    apertura no es el de cierre del anterior, o cuyo numero no sigue al del
    anterior (salvo que vuelva a 1 con el ano, si los saldos siguen).
    """
    por_cuenta: dict[str, list[Extracto]] = defaultdict(list)
    for e in extractos:
        if e.con_saldos:
            por_cuenta[e.cuenta].append(e)
    salida: dict[str, list[tuple[Extracto, str]]] = {}
    for cuenta, lista in sorted(por_cuenta.items()):
        lista.sort(key=lambda e: (e.desde or date.min, e.hasta or date.min, e.secuencia or 0, e.id))
        rotas = []
        for anterior, actual in zip(lista, lista[1:]):
            motivos = []
            if anterior.saldo_final_cent != actual.saldo_inicial_cent:
                motivos.append(f"abre con {_texto(actual.saldo_inicial_cent)} y el anterior "
                               f"cerro con {_texto(anterior.saldo_final_cent)}")
            if anterior.secuencia is not None and actual.secuencia is not None and (
                    actual.secuencia != anterior.secuencia + 1):
                nuevo_ano = (actual.secuencia == 1 and actual.desde is not None
                             and anterior.hasta is not None
                             and actual.desde.year != anterior.hasta.year)
                if not nuevo_ano:
                    motivos.append(f"lleva el numero {actual.secuencia} y el anterior el "
                                   f"{anterior.secuencia}")
            if motivos:
                rotas.append((actual, "; ".join(motivos)))
        if rotas:
            salida[cuenta] = rotas
    return salida


def preparar(instantanea: Instantanea) -> Contexto:
    por_factura: dict[int, list[Aplicacion]] = defaultdict(list)
    por_movimiento: dict[int, list[Aplicacion]] = defaultdict(list)
    for a in instantanea.aplicaciones:
        por_factura[a.factura_id].append(a)
        if a.movimiento_id is not None:
            por_movimiento[a.movimiento_id].append(a)
    extractos = {e.id: e for e in instantanea.extractos}
    desdes = [e.desde for e in instantanea.extractos if e.desde is not None]
    hastas = [e.hasta for e in instantanea.extractos if e.hasta is not None]
    rotos: dict[str, tuple[Extracto, ...]] = {}
    for cuenta, rotas in roturas(instantanea.extractos).items():
        primera = rotas[0][0]
        clave = (primera.desde or date.min, primera.hasta or date.min, primera.secuencia or 0,
                 primera.id)
        rotos[cuenta] = tuple(e for e in instantanea.extractos if e.cuenta == cuenta and (
            e.desde or date.min, e.hasta or date.min, e.secuencia or 0, e.id) >= clave)
    bloqueos: dict[int, list[Any]] = defaultdict(list)
    for b in instantanea.bloqueos:
        bloqueos[b.factura_id].append(b)
    return Contexto(
        hoy=instantanea.hoy, por_factura=por_factura, por_movimiento=por_movimiento,
        movimientos={m.id: m for m in instantanea.movimientos}, extractos=extractos,
        sentido={f.id: f.sentido for f in instantanea.facturas},
        banco_desde=min(desdes) if desdes else None, banco_hasta=max(hastas) if hastas else None,
        banco_caducado=bool(caducada(instantanea, BANCO)), exact_al_dia=_exact_al_dia(instantanea),
        tolerancia=tolerancia_cent(instantanea.politica.tolerancia_pago),
        ajenos=frozenset(instantanea.politica.empresa_ibans) | instantanea.beneficiarios,
        rotos=rotos, bloqueos=bloqueos)


LEE_CONTEXTO = frozenset({
    "instantanea.aplicaciones", "instantanea.extractos", "instantanea.movimientos",
    "instantanea.facturas", "instantanea.hoy", "instantanea.politica", "instantanea.lotes",
    "instantanea.beneficiarios", "instantanea.bloqueos",
    "aplicacion.factura_id", "aplicacion.movimiento_id",
    "extracto.id", "extracto.cuenta", "extracto.con_saldos", "extracto.desde", "extracto.hasta",
    "extracto.secuencia", "extracto.saldo_inicial_cent", "extracto.saldo_final_cent",
    "movimiento.id", "factura.id", "factura.sentido", "bloqueo.factura_id",
    "lote.fuente", "lote.tipo", "lote.estado", "lote.id", "lote.exportado",
    "politica.tolerancia_pago", "politica.empresa_ibans", "politica.frescura_exact_dias",
    "politica.frescura_banco_dias_laborables",
})


def _confirmadas(aplicaciones: Sequence[Aplicacion]) -> list[Aplicacion]:
    return [a for a in aplicaciones if a.estado == CONFIRMADA]


def _texto(cent: int | None) -> str:
    return "?" if cent is None else euros_texto(euros(cent))


# ------------------------------------------------------------ K1

def _se_puede_saber(factura: Factura, c: Contexto) -> bool:
    """Si alguna fuente de pagos dice si esta factura se pago: un Exact de pagos al dia, o
    extractos al dia que empiezan antes de la fecha de la factura."""
    if c.exact_al_dia:
        return True
    desde = factura.fecha_factura or factura.vencimiento
    return (c.banco_desde is not None and not c.banco_caducado and desde is not None
            and c.banco_desde <= desde)


def k1(factura: Factura, contexto: tuple[Contexto, int]) -> list[Resultado]:
    """K1: vencida y sin pagar (aviso con excepcion)."""
    c, dias_venta = contexto
    if factura.pagada or factura.total_cent is None or factura.vencimiento is None:
        return []
    limite = 0 if factura.sentido == ENTRANTE else dias_venta
    if (c.hoy - factura.vencimiento).days <= limite:
        return []
    pendiente = factura.total_cent - factura.pagado_cent
    if not _se_puede_saber(factura, c):
        return [sin_datos("K1", factura, "Vencida, pero ningún extracto ni Exact al día cubre "
                                         "desde su fecha: no se sabe si se pagó.")]
    quien = "pagar" if factura.sentido == ENTRANTE else "cobrar"
    return [fallo("K1", factura, f"Vencida el {factura.vencimiento.isoformat()} y sin {quien}: "
                                 f"quedan {_texto(pendiente)}.",
                  valores={"vencimiento": factura.vencimiento.isoformat(),
                           "pendiente_cent": pendiente, "limite_dias": limite})]


# ------------------------------------------------------------ K2, K3, K5, K8

def k2(factura: Factura, c: Contexto) -> list[Resultado]:
    """K2: lo confirmado no deja el saldo a cero (pago parcial o de mas)."""
    s = saldo(factura.total_cent, c.por_factura.get(factura.id, ()), c.tolerancia)
    if s.fuente is None:
        return []
    if s.total_cent is None:
        return [sin_datos("K2", factura, "Tiene pagos, pero no un total en euros con que "
                                         "compararlos.")]
    if s.pagada:
        return []
    que = "parcial" if (s.pendiente_cent > 0) == (s.total_cent > 0) else "de más"
    return [fallo("K2", factura, f"Pago {que}: total {_texto(s.total_cent)}, pagado "
                                 f"{_texto(s.pagado_cent)} ({s.fuente}), quedan "
                                 f"{_texto(s.pendiente_cent)}.",
                  valores={"total_cent": s.total_cent, "pagado_cent": s.pagado_cent,
                           "pendiente_cent": s.pendiente_cent, "fuente": s.fuente})]


def k3(factura: Factura, contexto: tuple[Contexto, int]) -> list[Resultado]:
    """K3: marcada pagada a mano y, pasados N dias, sin rastro en el banco."""
    c, dias = contexto
    confirmadas = _confirmadas(c.por_factura.get(factura.id, ()))
    manuales = [a for a in confirmadas if a.fuente == MANUAL]
    if not manuales or any(a.fuente == BANCO for a in confirmadas):
        return []
    ultima = max(a.fecha_pago for a in manuales)
    plazo = ultima + timedelta(days=dias)
    if c.hoy <= plazo:
        return []
    if c.banco_hasta is None or c.banco_hasta < plazo or c.banco_caducado:
        return [sin_datos("K3", factura, "Marcada pagada a mano, pero ningún extracto al día "
                                         "cubre los días siguientes al pago.")]
    return [fallo("K3", factura, f"Marcada pagada a mano el {ultima.isoformat()} y el banco no "
                                 "trae ese pago.",
                  valores={"aplicaciones": sorted(a.id for a in manuales),
                           "fecha_pago": ultima.isoformat()})]


def k5(factura: Factura, c: Contexto) -> list[Resultado]:
    """K5: pagada mientras estaba Bloqueada. Un resultado por pago."""
    bloqueos = c.bloqueos.get(factura.id)
    if not bloqueos:
        return []
    salida = []
    for a in _confirmadas(c.por_factura.get(factura.id, ())):
        reglas = sorted({b.regla for b in bloqueos if b.desde <= a.fecha_pago
                         and (b.hasta is None or a.fecha_pago <= b.hasta)})
        if reglas:
            salida.append(fallo(
                "K5", factura, f"Pagada el {a.fecha_pago.isoformat()} mientras estaba Bloqueada "
                               f"({', '.join(reglas)}).",
                valores={"aplicacion": a.id, "fecha_pago": a.fecha_pago.isoformat(),
                         "reglas": reglas}, clave=f"aplicacion:{a.id}"))
    return salida


def k8(factura: Factura, c: Contexto) -> list[Resultado]:
    """K8: el banco y Exact no dicen lo mismo de lo pagado."""
    confirmadas = _confirmadas(c.por_factura.get(factura.id, ()))
    banco = [a.importe_cent for a in confirmadas if a.fuente == BANCO]
    exact = [a.importe_cent for a in confirmadas if a.fuente == EXACT]
    if not banco or not exact or abs(sum(banco) - sum(exact)) <= c.tolerancia:
        return []
    return [fallo("K8", factura, f"El banco dice {_texto(sum(banco))} pagados y Exact "
                                 f"{_texto(sum(exact))}.",
                  valores={"banco_cent": sum(banco), "exact_cent": sum(exact)})]


# ------------------------------------------------------------ K4

def _doble_de_factura(factura: Factura, c: Contexto) -> list[Resultado]:
    """K4 de una factura: pagada de mas con dos o mas cargos del banco."""
    del_banco = [a for a in _confirmadas(c.por_factura.get(factura.id, ())) if a.fuente == BANCO]
    movimientos = sorted({a.movimiento_id for a in del_banco})
    if len(movimientos) < 2 or factura.total_cent is None:
        return []
    pagado = sum(a.importe_cent for a in del_banco)
    if abs(pagado) <= abs(factura.total_cent) + c.tolerancia:
        return []
    return [fallo("K4", factura, f"Pagada dos veces: {len(movimientos)} movimientos del banco "
                                 f"suman {_texto(pagado)} para un total de "
                                 f"{_texto(factura.total_cent)}.",
                  valores={"movimientos": movimientos, "pagado_cent": pagado,
                           "total_cent": factura.total_cent},
                  objetivos=tuple(Objetivo("movimiento", m, None, RELACIONADO)
                                  for m in movimientos))]


def k4(instantanea: Instantanea) -> list[Resultado]:
    """K4: pago doble, entre movimientos y por factura (bloquea)."""
    c = preparar(instantanea)
    ventana = instantanea.politica.ventana_doble_pago_dias
    grupos: dict[tuple[str, int, str], list[Movimiento]] = defaultdict(list)
    for m in instantanea.movimientos:
        if (m.importe_cent is None or m.importe_cent >= 0 or not m.contraparte_iban
                or not m.referencia or m.contraparte_iban in c.ajenos):
            continue
        grupos[(m.contraparte_iban, m.importe_cent, m.referencia)].append(m)
    salida: list[Resultado] = []
    for (iban, importe, referencia), lista in sorted(grupos.items()):
        lista.sort(key=lambda m: (m.fecha, m.id))
        juntos: list[list[Movimiento]] = []
        for m in lista:
            if juntos and (m.fecha - juntos[-1][-1].fecha).days < ventana:
                juntos[-1].append(m)
            else:
                juntos.append([m])
        for grupo in juntos:
            if len(grupo) < 2:
                continue
            ids = [m.id for m in grupo]
            facturas = sorted({a.factura_id for m in grupo for a in c.por_movimiento.get(m.id, ())
                               if a.estado != "retirada"})
            objetivos = tuple(Objetivo("factura", f, None, RELACIONADO) for f in facturas)
            detalle = (f"{len(grupo)} cargos de {_texto(-importe)} a {iban} con la referencia "
                       f"«{referencia}» entre el {grupo[0].fecha.isoformat()} y el "
                       f"{grupo[-1].fecha.isoformat()}: pago doble.")
            valores = {"movimientos": ids, "importe_cent": importe, "iban": iban,
                       "referencia": referencia, "facturas": facturas}
            for m in grupo:
                salida.append(Resultado("K4", "movimiento", m.id, FALLO, detalle, valores, "",
                                        f"pago_doble:{ids[0]}", None,
                                        (Objetivo("movimiento", m.id), *objetivos)))
    for factura in instantanea.facturas:
        if not (factura.anulada or factura.fusionada_en_id is not None):
            salida.extend(_doble_de_factura(factura, c))
    return salida


LEE_K4 = LEE_CONTEXTO | LEE_EN_JUEGO | frozenset({
    "politica.ventana_doble_pago_dias", "movimiento.importe_cent", "movimiento.contraparte_iban",
    "movimiento.referencia", "movimiento.fecha", "aplicacion.estado", "aplicacion.fuente",
    "aplicacion.importe_cent", "factura.total_cent",
})


# ------------------------------------------------------------ K6

def k6(instantanea: Instantanea) -> list[Resultado]:
    """K6: la cadena de extractos de una cuenta se rompe (bloquea lo que va detras)."""
    c = preparar(instantanea)
    salida: list[Resultado] = []
    rotas = roturas(instantanea.extractos)
    for cuenta, lista in sorted(rotas.items()):
        for extracto, motivo in lista:
            salida.append(Resultado(
                "K6", "importacion", extracto.importacion_id, FALLO,
                f"La cadena de extractos de {cuenta} se rompe: {motivo}. Lo pagado desde aquí "
                "no se da por bueno hasta que llegue lo que falta.",
                {"cuenta": cuenta, "extracto": extracto.id, "motivo": motivo},
                f"extracto:{extracto.id}", None, None,
                (Objetivo("importacion", extracto.importacion_id),)))
    if not c.rotos:
        return salida
    despues = {e.id for lista in c.rotos.values() for e in lista}
    for factura in instantanea.facturas:
        if factura.anulada or factura.fusionada_en_id is not None:
            continue
        afectados = sorted({c.movimientos[a.movimiento_id].extracto_id
                            for a in _confirmadas(c.por_factura.get(factura.id, ()))
                            if a.fuente == BANCO and a.movimiento_id in c.movimientos
                            and c.movimientos[a.movimiento_id].extracto_id in despues})
        if afectados:
            salida.append(fallo(
                "K6", factura, "Pagada con movimientos de extractos que van detrás de una rotura "
                               "de la cadena: el pago no se da por bueno hasta que llegue lo que "
                               "falta.", valores={"extractos": afectados}))
    return salida


LEE_K6 = LEE_CONTEXTO | LEE_EN_JUEGO | frozenset({
    "extracto.importacion_id", "aplicacion.estado", "aplicacion.fuente",
    "movimiento.extracto_id",
})


# ------------------------------------------------------------ K7

def k7(instantanea: Instantanea) -> list[Resultado]:
    """K7: un movimiento del banco sin casar pasados N dias (aviso)."""
    c = preparar(instantanea)
    dias = instantanea.politica.dias_movimiento_sin_casar
    salida = []
    for m in instantanea.movimientos:
        if (m.importe_cent is None or m.importe_cent == 0
                or (m.contraparte_iban is not None and m.contraparte_iban in c.ajenos)
                or (instantanea.hoy - m.fecha).days <= dias):
            continue
        casado = sum(en_el_movimiento(a, c.sentido.get(a.factura_id, ENTRANTE))
                     for a in _confirmadas(c.por_movimiento.get(m.id, ())))
        resto = m.importe_cent - casado
        if abs(resto) <= c.tolerancia:
            continue
        quien = m.contraparte_nombre or m.contraparte_iban or "sin contraparte"
        salida.append(Resultado(
            "K7", "movimiento", m.id, FALLO,
            f"{_texto(m.importe_cent)} del {m.fecha.isoformat()} ({quien}) sin casar con ninguna "
            f"factura: quedan {_texto(resto)}.",
            {"fecha": m.fecha.isoformat(), "importe_cent": m.importe_cent,
             "sin_casar_cent": resto}, "", None, None, (Objetivo("movimiento", m.id),)))
    return salida


LEE_K7 = LEE_CONTEXTO | frozenset({
    "politica.dias_movimiento_sin_casar", "movimiento.importe_cent",
    "movimiento.contraparte_iban", "movimiento.contraparte_nombre", "movimiento.fecha",
    "aplicacion.estado", "aplicacion.importe_cent",
})


# ------------------------------------------------------------ las de factura

def _con_dias(campo: str):
    """El contexto de una regla de factura que usa un plazo de la politica (K1, K3)."""
    def preparar_con_dias(instantanea: Instantanea) -> tuple[Contexto, int]:
        return preparar(instantanea), getattr(instantanea.politica, campo)
    return preparar_con_dias


LEE_SALDO = frozenset({"aplicacion.estado", "aplicacion.fuente", "aplicacion.importe_cent"})
LEE_K1 = LEE_CONTEXTO | LEE_EN_JUEGO | frozenset({
    "factura.pagada", "factura.total_cent", "factura.vencimiento", "factura.pagado_cent",
    "factura.fecha_factura", "politica.dias_vencida_venta"})
LEE_K2 = LEE_CONTEXTO | LEE_EN_JUEGO | LEE_SALDO | frozenset({"factura.total_cent"})
LEE_K3 = LEE_CONTEXTO | LEE_EN_JUEGO | frozenset({
    "aplicacion.estado", "aplicacion.fuente", "aplicacion.fecha_pago", "aplicacion.id",
    "politica.dias_pago_sin_extracto"})
LEE_K5 = LEE_CONTEXTO | LEE_EN_JUEGO | frozenset({
    "aplicacion.estado", "aplicacion.fecha_pago", "aplicacion.id", "bloqueo.regla",
    "bloqueo.desde", "bloqueo.hasta"})
LEE_K8 = LEE_CONTEXTO | LEE_EN_JUEGO | LEE_SALDO

EVALUAR = {"K1": solo_objeciones(k1, _con_dias("dias_vencida_venta")),
           "K2": solo_objeciones(k2, preparar),
           "K3": solo_objeciones(k3, _con_dias("dias_pago_sin_extracto")),
           "K5": solo_objeciones(k5, preparar),
           "K8": solo_objeciones(k8, preparar)}
