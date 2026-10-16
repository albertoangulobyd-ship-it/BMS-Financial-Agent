"""Reglas de las facturas de venta contra lo pactado y contra el planning (pasos 9 y 10).

V4 compara la tarifa de cada linea de venta con la tarifa de venta pactada que
le toca (tarifas.py, de lo mas concreto a lo general: recurso y Objeto,
Objeto, recurso, cliente y, de config/tarifas.yaml, la del tipo de trabajo en
cualquier Objeto). En una venta importa en los dos sentidos: por encima, el
cliente reclamara; por debajo, BM Support BV pierde dinero. Sin tarifa pactada
la referencia es la del turno en el planning (paso 10, si todos los turnos de
la celda dicen la misma); sin ninguna de las dos, sin datos (nunca ok). Una
ambigua da sin datos y una retencion de la factura, con su excepcion, como en
G3.

Las del planning (paso 10), con las celdas de turnos.py:

- V1: las horas facturadas de cada celda contra las validadas facturables
  del planning (como G2);
- V2: el Objeto de cada linea existe, es del cliente facturado y estaba
  activo esos dias; una linea sin Objeto recibe la propuesta del planning;
- V3: el periodo y la semana de lo facturado contra el planning (como G5);
- V5: dentro del periodo y el Objeto que una factura cobra, turnos validados
  facturables que ninguna linea de venta cubre;
- V6: trabajo sin facturar, fuera de cualquier periodo facturado, una vez
  pasado el fin de su periodo de facturacion mas sus dias de gracia;
  valorado a la tarifa de venta pactada o, si no, marcado estimado;
- V8: un periodo de un ciclo de facturacion con trabajo y sin factura;
- V9: el planning cambio despues de facturar (regla 9; como G7, pero
  retiene).

V6 y V8 son del cliente (no de una factura, que no existe): su hallazgo va en
el cliente, con el Objeto y el periodo en su clave. V7 (facturar dos veces)
esta en unicidad.py.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from . import turnos
from .base import (
    FALLO,
    OK,
    RELACIONADO,
    SALIENTE,
    SIN_DATOS,
    Ciclo,
    Instantanea,
    Objetivo,
    Resultado,
    en_juego,
    periodo_de,
)
from .planning import (
    LEE_CAMBIOS,
    LEE_COMPARAR,
    LEE_FECHAS,
    LEE_PACTADA_VENTA,
    LEE_TURNO_TARIFA,
    NO_EVIDENCIA_PACTADA,
    _horas,
    cambios_tras_conciliar,
    comparar_con_pactadas,
    comparar_horas,
    contra_tarifa_del_turno,
    fechas_contra_planning,
    objeto_propuesto,
)
from .tarifas import LEE_TARIFA_VENTA, por_sentido


def v4(instantanea: Instantanea) -> list[Resultado]:
    """V4: la tarifa de cada linea de venta es la de venta pactada (ni mas ni menos) o, sin
    pactada, la del turno en el planning."""
    decididas: set[int] = set()
    salida = comparar_con_pactadas(instantanea, "V4", SALIENTE, recargos=None,
                                   tambien_por_debajo=True, exceso_bloqueo_pct=None,
                                   sin_pactada=None, decididas=decididas)
    hay_tarifas = bool(por_sentido(instantanea.tarifas).get("venta"))
    if instantanea.fotos_planning:
        salida.extend(contra_tarifa_del_turno(instantanea, "V4", SALIENTE, decididas,
                                              tambien_por_debajo=True))
    elif not hay_tarifas:
        return salida
    for f in instantanea.facturas:
        if f.sentido != SALIENTE or not f.imputaciones or not en_juego(f):
            continue
        lineas = {l.id: l for l in f.lineas}
        for i in f.imputaciones:
            linea = lineas.get(i.linea_id) if i.linea_id is not None else None
            if linea is None or linea.tarifa_e4 is None or linea.id in decididas:
                continue
            salida.append(Resultado("V4", "factura", f.id, SIN_DATOS,
                                    "Sin tarifa de venta pactada para la línea ni tarifa del "
                                    "turno en el planning.", clave=f"pactada:{i.id}"))
    return salida


LEE_V4 = (LEE_PACTADA_VENTA | LEE_TURNO_TARIFA | turnos.LEE_VENTA
          | frozenset({"instantanea.fotos_planning", "turno.tarifa_venta_e4"}))
SOLO_TEXTO_V4 = NO_EVIDENCIA_PACTADA & LEE_V4


def v1(instantanea: Instantanea) -> list[Resultado]:
    """V1: las horas facturadas contra las validadas facturables del planning (como G2)."""
    return comparar_horas(instantanea, "V1", SALIENTE)


def v3(instantanea: Instantanea) -> list[Resultado]:
    """V3: el periodo y la semana de lo facturado contra el planning (como G5)."""
    return fechas_contra_planning(instantanea, "V3", SALIENTE)


def v9(instantanea: Instantanea) -> list[Resultado]:
    """V9: el planning cambio despues de facturar lo que se concilio (como G7, pero retiene)."""
    return cambios_tras_conciliar(instantanea, "V9", SALIENTE)


LEE_V1 = LEE_COMPARAR | turnos.LEE_VENTA
LEE_V3 = LEE_FECHAS | turnos.LEE_VENTA
LEE_V9 = LEE_CAMBIOS | turnos.LEE_VENTA


def v2(instantanea: Instantanea) -> list[Resultado]:
    """V2: el Objeto de cada linea de venta existe, es del cliente facturado y estaba activo.

    Una linea sin Objeto retiene, y el planning propone el suyo si lo sabe
    (solo una propuesta: la confirma una persona con cambiar_objeto). Lo demas
    no depende del planning: sin ninguno, V2 mira igual, sin proponer nada.
    """
    plan = turnos.Planificacion(instantanea) if instantanea.fotos_planning else None
    objetos = {o.id: o for o in instantanea.objetos}
    nombres = {o.id: o.codigo for o in instantanea.objetos}
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if (f.sentido != SALIENTE or f.tipo != turnos.FACTURA or not f.imputaciones
                or not en_juego(f)):
            continue
        lineas = {l.id: l for l in f.lineas}
        for i in f.imputaciones:
            linea = lineas.get(i.linea_id) if i.linea_id is not None else None
            orden = linea.orden if linea is not None else i.id
            clave = f"imputacion:{i.id}"
            objetivo = (Objetivo("factura_imputacion", i.id, "objeto_id", RELACIONADO),)
            if i.objeto_id is None:
                propuesta = (objeto_propuesto("V2", plan, f, i, linea, nombres)
                             if plan is not None and f.cliente_id is not None else None)
                if propuesta is not None and propuesta.resultado == FALLO:
                    salida.append(propuesta)
                else:
                    salida.append(Resultado("V2", "factura", f.id, FALLO,
                                            f"La línea {orden} no dice de qué Objeto es.",
                                            {"objeto": None}, clave, objetivos=objetivo))
                continue
            o = objetos.get(i.objeto_id)
            dias = turnos.dias_de(i, linea, f)
            if o is not None and f.cliente_id is not None and o.cliente_id is not None \
                    and o.cliente_id != f.cliente_id:
                salida.append(Resultado(
                    "V2", "factura", f.id, FALLO,
                    f"El Objeto {o.codigo} de la línea {orden} es de otro cliente.",
                    {"objeto": o.id, "cliente_objeto": o.cliente_id}, clave,
                    objetivos=objetivo))
            elif o is not None and dias is not None and (
                    (o.activo_desde is not None and dias[0] < o.activo_desde)
                    or (o.activo_hasta is not None and dias[1] > o.activo_hasta)):
                salida.append(Resultado(
                    "V2", "factura", f.id, FALLO,
                    f"El Objeto {o.codigo} no estaba activo del {dias[0].isoformat()} al "
                    f"{dias[1].isoformat()} (lo está del "
                    f"{o.activo_desde.isoformat() if o.activo_desde else '…'} al "
                    f"{o.activo_hasta.isoformat() if o.activo_hasta else '…'}).",
                    {"objeto": o.id, "desde": dias[0].isoformat(), "hasta": dias[1].isoformat(),
                     "activo_desde": o.activo_desde.isoformat() if o.activo_desde else None,
                     "activo_hasta": o.activo_hasta.isoformat() if o.activo_hasta else None},
                    clave, objetivos=objetivo))
            else:
                salida.append(Resultado("V2", "factura", f.id, OK,
                                        f"La línea {orden} es de un Objeto del cliente.",
                                        clave=clave))
    return salida


LEE_V2 = (turnos.LEE_PLANIFICACION | turnos.LEE_CELDA | frozenset({
    "instantanea.facturas", "instantanea.objetos", "objeto.id", "objeto.codigo",
    "objeto.cliente_id", "objeto.activo_desde", "objeto.activo_hasta", "factura.id",
    "factura.sentido", "factura.tipo", "factura.imputaciones", "factura.anulada",
    "factura.fusionada_en_id", "factura.sustituida_por", "factura.lineas", "linea.id",
    "linea.orden", "imputacion.id", "imputacion.linea_id"}) | turnos.LEE_VENTA)
# Los dias de una linea solo sirven para mirar si el Objeto estaba activo y para
# buscar su propuesta en el planning: los dias que salen van en los valores (desde,
# hasta), y lo que no depende de ellos (una linea sin Objeto) no cambia si una
# persona corrige la fecha de la factura (como NO_EVIDENCIA_PACTADA).
SOLO_TEXTO_V2 = frozenset({"objeto.codigo", "linea.orden"}) | (turnos.LEE_DIAS & LEE_V2)


# ------------------------------------------------------------ lo trabajado y no facturado

def cubiertos(instantanea: Instantanea) -> tuple[dict[int, list[tuple[date, date]]],
                                                  dict[int, list[tuple[date, date]]],
                                                  dict[int, list[tuple[date, date]]]]:
    """Lo que cubren las ventas en juego: por Objeto, los dias de sus lineas; por Objeto y por
    cliente, los periodos de sus facturas (el de la cabecera, o el de sus lineas)."""
    lineas_por_objeto: dict[int, list[tuple[date, date]]] = defaultdict(list)
    periodos_por_objeto: dict[int, list[tuple[date, date]]] = defaultdict(list)
    periodos_por_cliente: dict[int, list[tuple[date, date]]] = defaultdict(list)
    for f in instantanea.facturas:
        if f.sentido != SALIENTE or f.tipo != turnos.FACTURA or not en_juego(f):
            continue
        desde, hasta = periodo_de(f)
        periodo = (desde, hasta) if desde is not None and hasta is not None else None
        if periodo is not None and f.cliente_id is not None:
            periodos_por_cliente[f.cliente_id].append(periodo)
        lineas = {l.id: l for l in f.lineas}
        for i in f.imputaciones:
            if i.objeto_id is None:
                continue
            dias = turnos.dias_de(i, lineas.get(i.linea_id) if i.linea_id is not None else None,
                                  f)
            if dias is not None:
                lineas_por_objeto[i.objeto_id].append(dias)
            if periodo is not None:
                periodos_por_objeto[i.objeto_id].append(periodo)
    return lineas_por_objeto, periodos_por_objeto, periodos_por_cliente


def toca(t: turnos.Turno, rangos: list[tuple[date, date]]) -> bool:
    return any(turnos.solapa((t.fecha, turnos.ultimo_dia(t)), r) for r in rangos)


def facturado(t: turnos.Turno, coberturas: tuple[dict, dict, dict]) -> bool:
    """Si alguna venta en juego cubre un turno: una linea de su Objeto o el periodo de una
    factura de su Objeto esos dias; sin Objeto, el periodo de una factura de su cliente."""
    lineas_por_objeto, periodos_por_objeto, periodos_por_cliente = coberturas
    if t.objeto_id is not None:
        rangos = lineas_por_objeto.get(t.objeto_id, []) + periodos_por_objeto.get(
            t.objeto_id, [])
    else:
        rangos = periodos_por_cliente.get(t.cliente_id, [])
    return toca(t, rangos)


def validado_facturable(t: turnos.Turno, hoy: date) -> bool:
    return (t.estado == turnos.VALIDADO and t.facturable is not False
            and t.horas_aprobadas_mil is not None and t.cliente_id is not None
            and t.fecha <= hoy)


def _valorar(lista: list, tarifas_venta) -> tuple[int | None, bool]:
    """Lo que valen unos turnos a su tarifa de venta: la suma de los que la tienen, y si es una
    estimacion (alguno sin tarifa pactada, o sin ninguna)."""
    valor, estimado, alguno = 0, False, False
    for t in lista:
        precio, aproximado = turnos.tarifa_de_venta(t, tarifas_venta)
        estimado = estimado or aproximado or precio is None
        if precio is not None:
            valor += turnos.valor_cent(t.horas_aprobadas_mil, precio)
            alguno = True
    return (valor if alguno else None), estimado


def v5(instantanea: Instantanea) -> list[Resultado]:
    """V5: horas validadas facturables que faltan dentro del Objeto y el periodo que una
    factura de venta cobra (ninguna linea de venta cubre esos turnos)."""
    vacio = turnos.sin_planning(instantanea, "V5")
    if vacio is not None:
        return vacio
    plan = turnos.Planificacion(instantanea)
    tarifas_venta = por_sentido(instantanea.tarifas).get("venta", ())
    lineas_por_objeto, _periodos, _clientes = cubiertos(instantanea)
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if (f.sentido != SALIENTE or f.tipo != turnos.FACTURA or not en_juego(f)
                or f.cliente_id is None or not f.imputaciones):
            continue
        desde, hasta = periodo_de(f)
        if desde is None or hasta is None:
            continue
        filtro = turnos.de_la_parte(f)
        for objeto_id in sorted({i.objeto_id for i in f.imputaciones if i.objeto_id is not None}):
            clave = f"objeto:{objeto_id}"
            motivo = plan.sin_datos(desde, hasta)
            if motivo is not None:
                salida.append(Resultado("V5", "factura", f.id, SIN_DATOS, motivo, clave=clave))
                continue
            diarios, semanales = plan.indice.de(turnos.OBJETO, objeto_id, desde, hasta)
            faltan = [t for t in diarios + semanales
                      if filtro(t) and validado_facturable(t, instantanea.hoy)
                      and turnos.solapa((t.fecha, turnos.ultimo_dia(t)), (desde, hasta))
                      and not toca(t, lineas_por_objeto.get(objeto_id, []))]
            horas = sum(t.horas_aprobadas_mil for t in faltan)
            dias = len({t.fecha for t in faltan if t.nivel != turnos.SEMANAL}) + sum(
                t.dias for t in faltan if t.nivel == turnos.SEMANAL)
            if horas <= turnos.tolerancia_mil(plan.tolerancia, dias):
                salida.append(Resultado("V5", "factura", f.id, OK,
                                        "Ningún turno validado del periodo facturado queda "
                                        "fuera de sus líneas.", clave=clave))
                continue
            valor, estimado = _valorar(faltan, tarifas_venta)
            salida.append(Resultado(
                "V5", "factura", f.id, FALLO,
                f"Del {desde.isoformat()} al {hasta.isoformat()} el planning tiene "
                f"{_horas(horas)} h validadas facturables de este Objeto que ninguna línea "
                "cubre.",
                {"objeto": objeto_id, "desde": desde.isoformat(), "hasta": hasta.isoformat(),
                 "horas_mil": horas, "valor_cent": valor, "estimado": estimado,
                 "turnos": sorted(t.id_externo for t in faltan)}, clave))
    return salida


def _ciclo_de(ciclos: list[Ciclo], objeto_id: int | None, cliente_id: int | None,
              dia: date) -> Ciclo | None:
    """El ciclo de facturacion que vale para un dia: el del Objeto y, si no, el del cliente."""
    def vigente(c: Ciclo) -> bool:
        return ((c.vigente_desde is None or c.vigente_desde <= dia)
                and (c.vigente_hasta is None or dia <= c.vigente_hasta))

    del_objeto = [c for c in ciclos if c.objeto_id is not None and c.objeto_id == objeto_id
                  and vigente(c)]
    if del_objeto:
        return min(del_objeto, key=lambda c: c.id)
    del_cliente = [c for c in ciclos if c.objeto_id is None and c.cliente_id == cliente_id
                   and vigente(c)]
    return min(del_cliente, key=lambda c: c.id) if del_cliente else None


# Un ciclo sin ancla cuenta desde un lunes (las semanas y los bloques de cuatro
# semanas empiezan en lunes; los meses, el dia 1).
ANCLA_POR_DEFECTO = date(2024, 1, 1)


def periodo_y_gracia(ciclo: Ciclo | None, dia: date, gracia_politica: int
                     ) -> tuple[date, date, int]:
    """El periodo de facturacion de un dia y sus dias de gracia: los del ciclo o, sin ciclo, el
    mes natural con los dias de la politica."""
    if ciclo is None:
        inicio, fin = turnos.periodo_mensual(dia)
        return inicio, fin, gracia_politica
    ancla = ciclo.ancla or ciclo.vigente_desde or ANCLA_POR_DEFECTO
    inicio, fin = turnos.periodo_de_ciclo(ciclo.frecuencia, ancla, dia)
    return inicio, fin, ciclo.dias_gracia


def v6(instantanea: Instantanea) -> list[Resultado]:
    """V6: trabajo validado facturable que ninguna venta cubre, pasado su periodo y su gracia.

    Fuera de cualquier periodo que ya cobra una factura del Objeto o del
    cliente (lo que falta dentro de uno lo dice V5). Se agrupa por cliente,
    Objeto y periodo de facturacion (el de su ciclo, o el mes natural), y solo
    aparece cuando hoy ya ha pasado el fin del periodo mas sus dias de gracia.
    Se valora a la tarifa de venta pactada; si alguno no la tiene (o no tiene
    ninguna), el valor va marcado como estimado. Las semanas desde que paso la
    gracia las cuenta la prioridad desde la fecha fija `gracia_hasta`.
    """
    vacio = turnos.sin_planning(instantanea, "V6")
    if vacio is not None:
        return vacio
    plan = turnos.Planificacion(instantanea)
    hoy = instantanea.hoy
    tarifas_venta = por_sentido(instantanea.tarifas).get("venta", ())
    coberturas = cubiertos(instantanea)
    ciclos = list(instantanea.ciclos)
    gracia_politica = instantanea.politica.planning_dias_gracia
    grupos: dict[tuple[int, int | None, date, date, date], list] = defaultdict(list)
    for t in instantanea.turnos:
        if not validado_facturable(t, hoy) or facturado(t, coberturas):
            continue
        inicio, fin, gracia = periodo_y_gracia(_ciclo_de(ciclos, t.objeto_id, t.cliente_id,
                                                         t.fecha), t.fecha, gracia_politica)
        hasta = fin + timedelta(days=gracia)
        if hoy <= hasta:
            continue
        grupos[(t.cliente_id, t.objeto_id, inicio, fin, hasta)].append(t)
    salida: list[Resultado] = []
    for clave_grupo in sorted(grupos, key=lambda c: (c[0], c[1] or 0, c[2])):
        cliente_id, objeto_id, inicio, fin, hasta = clave_grupo
        lista = grupos[clave_grupo]
        clave = f"objeto:{objeto_id if objeto_id is not None else '-'}:{inicio.isoformat()}"
        if plan.caducado:
            salida.append(Resultado("V6", "cliente", cliente_id, SIN_DATOS,
                                    plan.sin_datos(inicio, fin) or "", clave=clave))
            continue
        horas = sum(t.horas_aprobadas_mil for t in lista)
        valor, estimado = _valorar(lista, tarifas_venta)
        cuanto = ("sin tarifa con que valorarlo" if valor is None else
                  f"{valor // 100},{valor % 100:02d} €" + (" (estimado)" if estimado else ""))
        salida.append(Resultado(
            "V6", "cliente", cliente_id, FALLO,
            f"{_horas(horas)} h validadas facturables del {inicio.isoformat()} al "
            f"{fin.isoformat()} sin facturar, pasados {hasta.isoformat()} el periodo y su "
            f"gracia: {cuanto}.",
            {"objeto": objeto_id, "desde": inicio.isoformat(), "hasta": fin.isoformat(),
             "gracia_hasta": hasta.isoformat(), "horas_mil": horas, "valor_cent": valor,
             "estimado": estimado, "turnos": sorted(t.id_externo for t in lista)}, clave))
    return salida


LEE_CUBIERTOS = turnos.LEE_DIAS | frozenset({
    "instantanea.facturas", "factura.sentido", "factura.tipo", "factura.anulada",
    "factura.fusionada_en_id", "factura.sustituida_por", "factura.cliente_id",
    "factura.lineas", "factura.imputaciones", "linea.id", "imputacion.linea_id",
    "imputacion.objeto_id"})
_LEE_VALORAR = frozenset({
    "instantanea.tarifas", "turno.tarifa_venta_e4", "turno.horas_aprobadas_mil",
    "turno.recurso_id", "turno.objeto_id", "turno.tipo_turno", "turno.tipo_servicio",
    "turno.id_externo", "turno.cliente_id", "turno.fecha", "turno.estado", "turno.facturable",
    "turno.nivel", "turno.orden_compra_id", "tarifa.sentido", "tarifa.id",
}) | LEE_TARIFA_VENTA
LEE_V5 = (turnos.LEE_PLANIFICACION | LEE_CUBIERTOS | _LEE_VALORAR | turnos.LEE_VENTA
          | frozenset({"factura.id", "turno.dias"}))
LEE_V6 = (turnos.LEE_PLANIFICACION | LEE_CUBIERTOS | _LEE_VALORAR | frozenset({
    "instantanea.ciclos", "ciclo.id", "ciclo.cliente_id", "ciclo.objeto_id",
    "ciclo.frecuencia", "ciclo.ancla", "ciclo.dias_gracia", "ciclo.vigente_desde",
    "ciclo.vigente_hasta", "politica.planning_dias_gracia"}))


def v8(instantanea: Instantanea) -> list[Resultado]:
    """V8: un periodo de un ciclo de facturacion con trabajo en el planning y sin factura.

    De cada ciclo, los periodos que ya pasaron con su gracia, dentro de lo que
    cubre el planning y de la vigencia del ciclo; si el planning tiene turnos
    facturables (no cancelados) de su cliente u Objeto y ninguna venta en juego
    de ese cliente (y de ese Objeto, si el ciclo es de un Objeto) toca el
    periodo, falta su factura.
    """
    vacio = turnos.sin_planning(instantanea, "V8")
    if vacio is not None:
        return vacio
    if not instantanea.ciclos:
        return []
    plan = turnos.Planificacion(instantanea)
    hoy = instantanea.hoy
    _lineas, periodos_por_objeto, periodos_por_cliente = cubiertos(instantanea)
    cliente_de_objeto = {o.id: o.cliente_id for o in instantanea.objetos}
    salida: list[Resultado] = []
    for ciclo in sorted(instantanea.ciclos, key=lambda c: c.id):
        cliente_id = ciclo.cliente_id or cliente_de_objeto.get(ciclo.objeto_id)
        if cliente_id is None or not plan.cubre:
            continue
        ancla = ciclo.ancla or ciclo.vigente_desde or ANCLA_POR_DEFECTO
        desde = max(d for d in (ciclo.vigente_desde, plan.cubre[0][0]) if d is not None)
        dia = turnos.periodo_de_ciclo(ciclo.frecuencia, ancla, desde)[0]
        while True:
            inicio, fin = turnos.periodo_de_ciclo(ciclo.frecuencia, ancla, dia)
            dia = fin + timedelta(days=1)
            if fin + timedelta(days=ciclo.dias_gracia) >= hoy or (
                    ciclo.vigente_hasta is not None and inicio > ciclo.vigente_hasta):
                break
            if plan.sin_datos(inicio, fin) is not None:
                continue
            dimension, clave_id = ((turnos.OBJETO, ciclo.objeto_id) if ciclo.objeto_id
                                   else (turnos.CLIENTE, cliente_id))
            diarios, semanales = plan.indice.de(dimension, clave_id, inicio, fin)
            trabajo = [t for t in diarios + semanales if t.facturable is not False
                       and t.cliente_id == cliente_id
                       and turnos.solapa((t.fecha, turnos.ultimo_dia(t)), (inicio, fin))]
            if not trabajo:
                continue
            facturados = (periodos_por_objeto.get(ciclo.objeto_id, []) if ciclo.objeto_id
                          else periodos_por_cliente.get(cliente_id, []))
            if any(turnos.solapa(p, (inicio, fin)) for p in facturados):
                continue
            salida.append(Resultado(
                "V8", "cliente", cliente_id, FALLO,
                f"El ciclo {ciclo.frecuencia} pide una factura del {inicio.isoformat()} al "
                f"{fin.isoformat()} y no hay ninguna, con {len(trabajo)} turno(s) en el "
                "planning.",
                {"ciclo": ciclo.id, "desde": inicio.isoformat(), "hasta": fin.isoformat(),
                 "dias_gracia": ciclo.dias_gracia, "turnos": len(trabajo)},
                f"ciclo:{ciclo.id}:{inicio.isoformat()}"))
    return salida


LEE_V8 = (turnos.LEE_PLANIFICACION | LEE_CUBIERTOS | frozenset({
    "instantanea.ciclos", "instantanea.objetos", "objeto.id", "objeto.cliente_id", "ciclo.id",
    "ciclo.cliente_id", "ciclo.objeto_id", "ciclo.frecuencia", "ciclo.ancla",
    "ciclo.dias_gracia", "ciclo.vigente_desde", "ciclo.vigente_hasta", "turno.facturable",
    "turno.nivel", "turno.fecha"}))
