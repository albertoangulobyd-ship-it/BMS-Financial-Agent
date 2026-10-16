"""Las ordenes de compra: lo consumido de cada una y las reglas P1-P10 (spec §7, paso 9).

Lo consumido de una PO es la base (sin IVA) de las imputaciones activas que
apuntan a ella, en las facturas que cuentan (ni anuladas, ni fusionadas en
otra, ni sustituidas o corregidas por otra) del sentido que consume su lado:
una PO de cliente la consumen las ventas a ese cliente; una de proveedor, sus
compras. Un abono resta solo cuando tiene una relacion confirmada que dice a
que factura abona (§7: "minus confirmed credits"), y mientras esa factura
cuente; antes, sus lineas no mueven la PO. Lo que no esta en euros no tiene importe (X1) y no cuenta.

El orden es el del §7: por fecha de factura y, a igual fecha, por id. Lo que
queda antes de una factura es el valor vigente menos lo de las anteriores; una
factura sin fecha va al final y no se sabe que tenia antes (sin datos).

El valor y el fin vigentes son los de la ultima modificacion que los cambia
(por su fecha y, a igual fecha, la ultima apuntada): `vigentes`. Es lo mismo
que v_po_vigente y v_po_consumo (migracion 0010) en SQL, y un test lo compara.

La prevision (P9) es determinista: el ritmo es lo consumido en las ultimas
`po_semanas_ritmo` semanas (por fecha de factura, hasta hoy incluido; si la PO
empezo despues, desde su inicio), y el dia de agotamiento es hoy mas lo que
queda dividido por ese ritmo, redondeado hacia arriba en dias enteros. Sin
consumo en la ventana no hay fecha: a ese ritmo no se agota.

Lo que depende del planning (paso 10): el trabajo planificado de P8, lo
trabajado sin facturar y lo planificado de P10 y el trabajo despues del fin de
una PO ya caducada en P7. Los turnos de una PO son los que la nombran (el
PO-nummer del planning) o, si no nombran ninguna, los de un Objeto (o, en una
PO sin Objetos, de su parte) que cubre una sola PO abierta. Se valoran a la
tarifa pactada de su lado (venta en una PO de cliente, compra en una de
proveedor) o, si no hay, a la del turno en el planning. Sin ninguna foto del
planning, sin datos: nunca ok.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import NamedTuple

from ..dominio import SENTIDO_DE_LADO, ClaseReferencia, LadoOrdenCompra, TipoFactura
from . import turnos
from .base import (
    FALLO,
    NO_APLICA,
    OK,
    RELACIONADO,
    R,
    SALIENTE,
    SIN_DATOS,
    Factura,
    Imputacion,
    Instantanea,
    Linea,
    Objetivo,
    OrdenCompra,
    Referencia,
    Resultado,
    Turno,
    en_juego,
    euros,
    euros_texto,
    periodo_de,
)
from .tarifas import LEE_TARIFA_COMPRA, LEE_TARIFA_VENTA, por_sentido

CLIENTE = LadoOrdenCompra.CLIENTE.value
PROVEEDOR = LadoOrdenCompra.PROVEEDOR.value
PO = ClaseReferencia.PO.value
NOTA_CREDITO = TipoFactura.NOTA_CREDITO.value
ABONAN = frozenset({"acredita", "anula"})


def lado_de(factura: Factura) -> str:
    """El lado de PO que consume una factura: una venta, el del cliente; una compra, el del
    proveedor."""
    return CLIENTE if factura.sentido == SALIENTE else PROVEEDOR


def parte_de(factura: Factura) -> int | None:
    return factura.cliente_id if factura.sentido == SALIENTE else factura.proveedor_id


# ------------------------------------------------------------ valor y fin vigentes

def vigentes(valor_original: int, fin_original: date | None,
             modificaciones: Iterable[tuple[int, date, int | None, date | None]],
             ) -> tuple[int, date | None]:
    """El valor y el fin vigentes: los de la ultima modificacion que cambia cada uno.

    `modificaciones` son (id, fecha, valor_nuevo_cent, fecha_fin_nueva). Ultima
    es la de fecha mayor y, a igual fecha, la apuntada despues (id mayor).
    """
    valor, fin = valor_original, fin_original
    for _id, _fecha, nuevo, fin_nuevo in sorted(modificaciones, key=lambda m: (m[1], m[0])):
        if nuevo is not None:
            valor = nuevo
        if fin_nuevo is not None:
            fin = fin_nuevo
    return valor, fin


# ------------------------------------------------------------ lo consumido

class Cargo(NamedTuple):
    """Lo que una factura carga a una PO: la suma de sus imputaciones a ella, sin IVA."""

    orden_compra_id: int
    factura_id: int
    fecha: date | None
    importe_cent: int


def en_orden(cargos: Iterable[Cargo]) -> list[Cargo]:
    """En el orden del §7: por fecha de factura y por id; sin fecha, al final."""
    return sorted(cargos, key=lambda c: (c.fecha is None, c.fecha or date.min, c.factura_id))


def abonos_confirmados(relaciones: Iterable, cuentan: frozenset[int]) -> frozenset[int]:
    """Los abonos con una relacion confirmada (viva) que dice a que factura abonan, mientras
    esa factura cuente (`cuentan`: las facturas en juego). Si la original se anula o se
    sustituye, su cargo sale de la PO; si su abono siguiera restando, contaria dos veces."""
    return frozenset(r.origen_id for r in relaciones
                     if r.tipo in ABONAN and r.destino_id in cuentan)


def cuenta_para_po(factura: Factura, abonos: frozenset[int]) -> bool:
    """Si las imputaciones de una factura consumen PO: en juego, y si es un abono, confirmado."""
    return en_juego(factura) and (factura.tipo == "factura" or factura.id in abonos)


def cargos(instantanea: Instantanea) -> dict[int, list[Cargo]]:
    """Por PO, lo que le carga cada factura que cuenta, en el orden del §7."""
    if not instantanea.ordenes:
        return {}
    lados = {o.id: o.lado for o in instantanea.ordenes}
    abonos = abonos_confirmados(instantanea.relaciones,
                                frozenset(f.id for f in instantanea.facturas if en_juego(f)))
    sumas: dict[tuple[int, int], int] = defaultdict(int)
    fechas: dict[int, date | None] = {}
    for f in instantanea.facturas:
        if not f.imputaciones or not cuenta_para_po(f, abonos):
            continue
        for i in f.imputaciones:
            if i.orden_compra_id is None or i.importe_cent is None:
                continue
            lado = lados.get(i.orden_compra_id)
            if lado is None or SENTIDO_DE_LADO[lado] != f.sentido:
                continue
            sumas[(i.orden_compra_id, f.id)] += i.importe_cent
            fechas[f.id] = f.fecha_factura
    salida: dict[int, list[Cargo]] = defaultdict(list)
    for (po, factura_id), importe in sumas.items():
        salida[po].append(Cargo(po, factura_id, fechas[factura_id], importe))
    return {po: en_orden(lista) for po, lista in salida.items()}


def pb(parte: int, total: int) -> int:
    """Un porcentaje en puntos basicos, truncado hacia cero (como la division entera de SQLite)."""
    cociente = abs(parte) * 10000 // total
    return cociente if parte >= 0 else -cociente


class Situacion(NamedTuple):
    """El valor vigente de una PO, lo consumido, lo que queda y los porcentajes (en pb)."""

    valor_cent: int
    consumido_cent: int
    restante_cent: int
    consumido_pb: int
    restante_pb: int


def situacion(orden: OrdenCompra, cargos_po: Sequence[Cargo]) -> Situacion:
    consumido = sum(c.importe_cent for c in cargos_po)
    restante = orden.valor_cent - consumido
    return Situacion(orden.valor_cent, consumido, restante, pb(consumido, orden.valor_cent),
                     pb(restante, orden.valor_cent))


def antes_de_cada(orden: OrdenCompra, cargos_po: Sequence[Cargo]) -> list[tuple[Cargo, int]]:
    """Cada cargo (en orden) con lo que quedaba de la PO antes de el."""
    salida, consumido = [], 0
    for c in cargos_po:
        salida.append((c, orden.valor_cent - consumido))
        consumido += c.importe_cent
    return salida


def antes_por_llegada(orden: OrdenCompra, cargos_po: Sequence[Cargo]) -> dict[int, int]:
    """Por factura, lo que quedaba de la PO con lo que llego antes que ella (id menor).

    El orden del §7 va por la fecha impresa, que pone el proveedor: una factura
    con fecha atrasada se colaria delante de las que ya se miraron (y quiza se
    pagaron) y pasaria el limite a una de ellas. Por llegada, la que llega la
    ultima es la que pasa lo que quedaba.
    """
    salida, consumido = {}, 0
    for c in sorted(cargos_po, key=lambda c: c.factura_id):
        salida[c.factura_id] = orden.valor_cent - consumido
        consumido += c.importe_cent
    return salida


class Prevision(NamedTuple):
    """El ritmo de consumo de una PO y cuando se agotaria a ese ritmo (P9)."""

    desde: date
    dias: int
    consumido_cent: int
    agotamiento: date | None


def prevision(orden: OrdenCompra, cargos_po: Sequence[Cargo], hoy: date,
              semanas: int) -> Prevision:
    """El ritmo de las ultimas `semanas` y el dia en que se agotaria (ver el docstring)."""
    desde = hoy - timedelta(days=semanas * 7 - 1)
    inicio = orden.fecha_inicio or orden.fecha_emision
    if inicio is not None and inicio > desde:
        desde = inicio
    dias = (hoy - desde).days + 1
    en_ventana = sum(c.importe_cent for c in cargos_po
                     if c.fecha is not None and desde <= c.fecha <= hoy)
    restante = orden.valor_cent - sum(c.importe_cent for c in cargos_po)
    if restante <= 0:
        return Prevision(desde, max(dias, 0), en_ventana, hoy)
    if dias <= 0 or en_ventana <= 0:
        return Prevision(desde, max(dias, 0), en_ventana, None)
    dias_hasta = -(-restante * dias // en_ventana)
    return Prevision(desde, dias, en_ventana, hoy + timedelta(days=dias_hasta))


# ------------------------------------------------------------ ayudas de las reglas

def _por_id(instantanea: Instantanea) -> dict[int, OrdenCompra]:
    return {o.id: o for o in instantanea.ordenes}


def _po_texto(orden: OrdenCompra) -> str:
    return f"la PO {orden.numero}"


def _mayus(texto: str) -> str:
    """La primera letra en mayuscula, sin tocar las demas (capitalize las baja)."""
    return texto[:1].upper() + texto[1:]


def _pct(puntos: int) -> str:
    """Unos puntos basicos como porcentaje con coma: 8125 es 81,25 %."""
    signo = "-" if puntos < 0 else ""
    return f"{signo}{abs(puntos) // 100},{abs(puntos) % 100:02d} %"


def _lineas(factura: Factura) -> dict[int, Linea]:
    return {l.id: l for l in factura.lineas}


def dias_de_trabajo(i: Imputacion, linea: Linea | None,
                    factura: Factura) -> tuple[date | None, date | None]:
    """De que dias es el trabajo de una imputacion: los suyos, los de su linea, el periodo de
    la factura o, si no hay nada, la fecha de la factura."""
    desde = i.fecha_inicio or (linea.fecha_trabajo or linea.fecha_inicio if linea else None)
    hasta = i.fecha_fin or (linea.fecha_trabajo or linea.fecha_fin if linea else None)
    if desde is None or hasta is None:
        inicio, fin = periodo_de(factura)
        desde, hasta = desde or inicio, hasta or fin
    if desde is None and hasta is None:
        desde = hasta = factura.fecha_factura
    return desde or hasta, hasta or desde


def _de_po(factura: Factura) -> dict[int, list[Imputacion]]:
    salida: dict[int, list[Imputacion]] = defaultdict(list)
    for i in factura.imputaciones:
        if i.orden_compra_id is not None:
            salida[i.orden_compra_id].append(i)
    return salida


def _objetivo_po(orden: OrdenCompra) -> Objetivo:
    return Objetivo("orden_compra", orden.id, None, RELACIONADO)


# ------------------------------------------------------------ P1: PO valida

def p1(instantanea: Instantanea) -> list[Resultado]:
    """Cada PO a la que se imputa una factura esta abierta y cubre los dias del trabajo.

    Que la PO sea de la parte y cubra el Objeto lo mira P3 (una PO de otro).
    Un resultado por factura y PO: ok, fallo o sin datos (sin ningun dia).
    """
    ordenes = _por_id(instantanea)
    if not ordenes:
        return []
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if not f.imputaciones or not en_juego(f):
            continue
        lineas = _lineas(f)
        for po_id, imputaciones in sorted(_de_po(f).items()):
            orden = ordenes[po_id]
            clave = f"po:{po_id}"
            problemas, fuera = [], []
            sin_dias = []
            for i in imputaciones:
                desde, hasta = dias_de_trabajo(i, lineas.get(i.linea_id), f)
                if desde is None:
                    sin_dias.append(i.id)
                    continue
                if ((orden.fecha_inicio is not None and desde < orden.fecha_inicio)
                        or (orden.fecha_fin is not None and hasta > orden.fecha_fin)):
                    fuera.append([i.id, desde.isoformat(), hasta.isoformat()])
            if orden.cerrada:
                problemas.append(f"{_po_texto(orden)} está cerrada")
            if fuera:
                problemas.append(
                    f"trabajo del {fuera[0][1]} al {fuera[-1][2]} fuera de su vigencia "
                    f"({orden.fecha_inicio.isoformat() if orden.fecha_inicio else '…'} a "
                    f"{orden.fecha_fin.isoformat() if orden.fecha_fin else '…'})")
            valores = {"po": po_id, "numero": orden.numero, "cerrada": orden.cerrada,
                       "inicio": orden.fecha_inicio.isoformat() if orden.fecha_inicio else None,
                       "fin": orden.fecha_fin.isoformat() if orden.fecha_fin else None,
                       "fuera": fuera}
            if problemas:
                salida.append(Resultado("P1", "factura", f.id, FALLO,
                                        _mayus("; ".join(problemas)) + ".", valores, clave,
                                        objetivos=(_objetivo_po(orden),)))
            elif sin_dias:
                salida.append(Resultado("P1", "factura", f.id, SIN_DATOS,
                                        "No se sabe de qué días es el trabajo imputado a "
                                        f"{_po_texto(orden)}.", valores, clave))
            else:
                salida.append(Resultado("P1", "factura", f.id, OK,
                                        f"{_mayus(_po_texto(orden))} cubre el trabajo.",
                                        clave=clave))
    return salida


LEE_P1 = frozenset({
    "instantanea.ordenes", "instantanea.facturas", "factura.id", "factura.imputaciones",
    "factura.anulada", "factura.fusionada_en_id", "factura.sustituida_por", "factura.lineas",
    "factura.periodo_inicio", "factura.periodo_fin", "factura.fecha_factura",
    "linea.id", "linea.fecha_trabajo", "linea.fecha_inicio", "linea.fecha_fin",
    "imputacion.id", "imputacion.linea_id", "imputacion.orden_compra_id",
    "imputacion.fecha_inicio", "imputacion.fecha_fin",
    "orden_compra.id", "orden_compra.numero", "orden_compra.cerrada",
    "orden_compra.fecha_inicio", "orden_compra.fecha_fin",
})


# ------------------------------------------------------------ P2: falta la PO

def _requisitos(instantanea: Instantanea) -> tuple[dict[int, bool | None], dict]:
    clientes = {c.id: c.requiere_po for c in instantanea.clientes}
    objetos = {o.id: o for o in instantanea.objetos}
    return clientes, objetos


def es_po(r: Referencia) -> bool:
    """Una referencia que el codigo da por PO: caso con una registrada, o su clase lo dice
    (la etiqueta impresa o una persona)."""
    return r.orden_compra_id is not None or r.clase == PO


def p2(instantanea: Instantanea) -> list[Resultado]:
    """Una venta sin PO donde el Objeto (o, si no dice, el cliente) la pide.

    Solo en las ventas: que un cliente o un Objeto pida PO es del maestro de
    clientes y Objetos; ningun maestro dice que un proveedor la pida. Lleva
    PO la imputacion que apunta a una, o la que tiene una PO impresa en su
    linea o en la cabecera: si esa PO es buena lo dicen P1 y P3, no P2. Un
    resultado por venta en juego a la que se le pide: ok o fallo.

    Un abono no se factura contra una PO: toma la de la factura que abona
    cuando su relacion se confirma (ordenes_compra.sincronizar), y la relacion
    que le falta ya la dice R4. Pedirle la PO retendria cada abono de un
    cliente que la pide por algo que no depende de el.
    """
    clientes, objetos = _requisitos(instantanea)
    if not any(clientes.values()) and not any(o.requiere_po for o in objetos.values()):
        return []
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if f.sentido != SALIENTE or f.tipo == NOTA_CREDITO or not en_juego(f):
            continue
        del_cliente = clientes.get(f.cliente_id) if f.cliente_id is not None else None
        en_cabecera = any(r.linea_id is None and es_po(r) for r in f.referencias)
        en_linea = {r.linea_id for r in f.referencias if r.linea_id is not None and es_po(r)}
        sin_po, pedida = [], False
        for i in f.imputaciones:
            objeto = objetos.get(i.objeto_id) if i.objeto_id is not None else None
            pide = (objeto.requiere_po if objeto is not None and objeto.requiere_po is not None
                    else del_cliente)
            if pide:
                pedida = True
                if i.orden_compra_id is None and not en_cabecera and i.linea_id not in en_linea:
                    sin_po.append(i.id)
        if not f.imputaciones and del_cliente:
            pedida = True
            if not (en_cabecera or en_linea):
                sin_po.append(None)
        if not pedida:
            continue
        if sin_po:
            lineas = [i for i in sin_po if i is not None]
            salida.append(Resultado(
                "P2", "factura", f.id, FALLO,
                "Falta la PO: el cliente o el Objeto la pide y "
                + (f"{len(lineas)} imputación(es) no la llevan." if lineas
                   else "la factura no tiene líneas imputadas ni PO impresa."),
                {"imputaciones": lineas}))
        else:
            salida.append(Resultado("P2", "factura", f.id, OK, "Lleva la PO que se pide."))
    return salida


LEE_P2 = frozenset({
    "instantanea.clientes", "instantanea.objetos", "instantanea.facturas", "parte.id",
    "parte.requiere_po", "objeto.id", "objeto.requiere_po", "factura.id", "factura.sentido",
    "factura.tipo", "factura.anulada", "factura.fusionada_en_id", "factura.sustituida_por", "factura.cliente_id",
    "factura.imputaciones", "factura.referencias", "imputacion.id", "imputacion.objeto_id",
    "imputacion.orden_compra_id", "imputacion.linea_id", "referencia.linea_id",
    "referencia.clase", "referencia.orden_compra_id",
})


# ------------------------------------------------------------ P3: PO desconocida o de otro

def p3(instantanea: Instantanea) -> list[Resultado]:
    """La PO que dice una factura existe y es de su parte y de su Objeto.

    Una referencia que el codigo da por PO (su etiqueta, o una persona) y que
    no caso con ninguna PO de la parte: desconocida, o de otra parte si su
    numero es de una PO de otro. Una imputacion a una PO de otra parte (o de
    otro lado), o a una que no cubre su Objeto. Sin ninguna PO registrada de
    ese lado no se sabe si es desconocida: sin datos.

    Una imputacion sin PO donde lo impreso dice varias PO registradas (en su
    linea o, si su linea no dice ninguna, en la cabecera) tambien retiene: la
    sincronizacion no reparte adivinando, y sin esto la factura no consumiria
    de ninguna y escaparia a P1, P4 y P6 por imprimir un numero de mas. Una
    persona decide con imputar_po.
    """
    por_numero: dict[tuple[str, str], list[OrdenCompra]] = defaultdict(list)
    for o in instantanea.ordenes:
        por_numero[(o.lado, o.numero_norm)].append(o)
    lados = {o.lado for o in instantanea.ordenes}
    ordenes = _por_id(instantanea)
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if not (f.referencias or f.imputaciones) or not en_juego(f):
            continue
        lado, parte = lado_de(f), parte_de(f)
        problemas: list[str] = []
        valores: dict[str, list] = {"desconocidas": [], "de_otra_parte": [], "de_otro_objeto": []}
        sin_datos: list[str] = []
        mira = False
        casadas: dict[int | None, set[int]] = defaultdict(set)
        for r in f.referencias:
            if r.orden_compra_id is not None:
                casadas[r.linea_id].add(r.orden_compra_id)
        for r in f.referencias:
            if r.clase != PO or r.orden_compra_id is not None:
                mira = mira or r.orden_compra_id is not None
                continue
            mira = True
            otras = por_numero.get((lado, r.valor_norm or ""), [])
            if otras:
                if parte is None:
                    sin_datos.append(f"la PO {r.valor_doc} es de una parte, y la factura no "
                                     "tiene la suya resuelta")
                else:
                    valores["de_otra_parte"].append(r.valor_doc)
                    problemas.append(f"la PO {r.valor_doc} es de otra parte")
            elif lado not in lados:
                sin_datos.append(f"no hay ninguna PO de {lado} registrada para saber si "
                                 f"{r.valor_doc} existe")
            else:
                valores["desconocidas"].append(r.valor_doc)
                problemas.append(f"la PO {r.valor_doc} no está registrada")
        varias: list[int] = []
        for i in f.imputaciones:
            orden = ordenes.get(i.orden_compra_id) if i.orden_compra_id is not None else None
            if orden is None:
                if i.orden_compra_id is None and len(_impresas_para(i, casadas)) > 1:
                    varias.append(i.id)
                continue
            mira = True
            if orden.lado != lado or orden.parte_id != parte:
                valores["de_otra_parte"].append(orden.numero)
                problemas.append(f"la imputación {i.id} va a {_po_texto(orden)}, que es de "
                                 "otra parte")
            elif orden.objetos and i.objeto_id is not None and i.objeto_id not in orden.objetos:
                valores["de_otro_objeto"].append([i.id, orden.numero])
                problemas.append(f"la imputación {i.id} va a {_po_texto(orden)}, que no cubre "
                                 "su Objeto")
        if varias:
            mira = True
            numeros = sorted({ordenes[po].numero for i in f.imputaciones if i.id in varias
                              for po in _impresas_para(i, casadas) if po in ordenes})
            valores["varias"] = [[i, numeros] for i in varias]
            problemas.append(f"{len(varias)} imputación(es) sin PO y la factura imprime varias "
                             f"({', '.join(numeros)}): una persona decide con imputar_po")
        if not mira:
            continue
        if problemas:
            salida.append(Resultado("P3", "factura", f.id, FALLO,
                                    _mayus("; ".join(dict.fromkeys(problemas))) + ".",
                                    {k: sorted(v, key=str) for k, v in valores.items()}))
        elif sin_datos:
            salida.append(Resultado("P3", "factura", f.id, SIN_DATOS,
                                    _mayus("; ".join(sin_datos)) + "."))
        else:
            salida.append(Resultado("P3", "factura", f.id, OK,
                                    "Las PO que dice son de su parte y de su Objeto."))
    return salida


def _impresas_para(i: Imputacion, casadas: dict[int | None, set[int]]) -> set[int]:
    """Las PO que lo impreso dice para una imputacion: las de su linea o, si su linea no dice
    ninguna, las de la cabecera (el orden de ordenes_compra._po_de_imputacion)."""
    return casadas.get(i.linea_id) if i.linea_id in casadas else casadas.get(None, set())


LEE_P3 = frozenset({
    "instantanea.ordenes", "instantanea.facturas", "orden_compra.id", "orden_compra.lado",
    "orden_compra.numero_norm", "orden_compra.numero", "orden_compra.parte_id",
    "orden_compra.objetos", "factura.id", "factura.referencias", "factura.imputaciones",
    "factura.anulada", "factura.fusionada_en_id", "factura.sustituida_por", "factura.sentido",
    "factura.cliente_id", "factura.proveedor_id", "referencia.clase",
    "referencia.orden_compra_id", "referencia.valor_norm", "referencia.valor_doc",
    "referencia.linea_id", "imputacion.id", "imputacion.orden_compra_id",
    "imputacion.objeto_id", "imputacion.linea_id",
})


# ------------------------------------------------------------ P4 y P6: lo que queda antes

def _p4_p6(instantanea: Instantanea, regla: str) -> list[Resultado]:
    ordenes = _por_id(instantanea)
    salida: list[Resultado] = []
    for po_id, lista in sorted(cargos(instantanea).items()):
        orden = ordenes[po_id]
        por_llegada = antes_por_llegada(orden, lista)
        for cargo, antes in antes_de_cada(orden, lista):
            clave = f"po:{po_id}"
            valores = {"po": po_id, "numero": orden.numero, "valor_cent": orden.valor_cent,
                       "antes_cent": antes, "importe_cent": cargo.importe_cent}
            llegada = por_llegada[cargo.factura_id]
            if llegada < antes:
                valores["antes_llegada_cent"] = llegada
            if cargo.importe_cent <= 0:
                salida.append(Resultado(regla, "factura", cargo.factura_id, OK,
                                        f"Abona a {_po_texto(orden)}: no la consume.",
                                        clave=clave))
                continue
            if cargo.fecha is None:
                salida.append(Resultado(regla, "factura", cargo.factura_id, SIN_DATOS,
                                        "Sin fecha de factura no se sabe qué quedaba de "
                                        f"{_po_texto(orden)} antes de ella.", valores, clave))
                continue
            # Lo que quedaba es lo menos de los dos ordenes: el del §7 y el de llegada.
            quedaba = min(antes, llegada)
            texto_antes = euros_texto(euros(quedaba))
            if regla == "P6":
                if quedaba <= 0:
                    salida.append(Resultado(
                        "P6", "factura", cargo.factura_id, FALLO,
                        f"{_mayus(_po_texto(orden))} ya estaba consumida (quedaban "
                        f"{texto_antes}) y la factura le carga "
                        f"{euros_texto(euros(cargo.importe_cent))}.", valores, clave,
                        objetivos=(_objetivo_po(orden),)))
                else:
                    salida.append(Resultado("P6", "factura", cargo.factura_id, OK,
                                            f"A {_po_texto(orden)} le quedaba valor.",
                                            clave=clave))
                continue
            if quedaba <= 0:
                salida.append(Resultado("P4", "factura", cargo.factura_id, NO_APLICA,
                                        f"{_mayus(_po_texto(orden))} ya estaba consumida: "
                                        "lo dice P6.", clave=clave))
            elif cargo.importe_cent > quedaba:
                atrasada = cargo.importe_cent <= antes
                salida.append(Resultado(
                    "P4", "factura", cargo.factura_id, FALLO,
                    f"La factura carga {euros_texto(euros(cargo.importe_cent))} a "
                    f"{_po_texto(orden)} y solo quedaban {texto_antes} (se pasa en "
                    f"{euros_texto(euros(cargo.importe_cent - quedaba))})"
                    + ("; por su fecha va antes, pero llegó después de facturas que ya "
                       "contaban con ese valor." if atrasada else "."),
                    {**valores, "exceso_cent": cargo.importe_cent - quedaba}, clave,
                    objetivos=(_objetivo_po(orden),)))
            else:
                salida.append(Resultado("P4", "factura", cargo.factura_id, OK,
                                        f"Cabe en lo que quedaba de {_po_texto(orden)}.",
                                        clave=clave))
    return salida


def p4(instantanea: Instantanea) -> list[Resultado]:
    """La factura carga a una PO mas de lo que le quedaba antes de ella.

    Antes de ella en el orden del §7 (fecha de factura e id) o en el de llegada
    (id): retiene si se pasa en cualquiera de los dos. Una factura con fecha
    atrasada que llega cuando la PO ya estaba casi consumida no se libra por
    colarse delante (antes_por_llegada).
    """
    return _p4_p6(instantanea, "P4")


def p6(instantanea: Instantanea) -> list[Resultado]:
    """La PO ya estaba consumida entera antes de la factura (en el orden del §7 o en el de
    llegada, como P4), y la factura le carga mas."""
    return _p4_p6(instantanea, "P6")


LEE_CARGOS = frozenset({
    "instantanea.ordenes", "instantanea.relaciones", "instantanea.facturas", "orden_compra.id",
    "orden_compra.lado", "orden_compra.valor_cent", "orden_compra.numero", "relacion.origen_id",
    "relacion.destino_id", "relacion.tipo", "factura.id", "factura.imputaciones", "factura.anulada",
    "factura.fusionada_en_id", "factura.sustituida_por", "factura.tipo", "factura.sentido",
    "factura.fecha_factura", "imputacion.orden_compra_id", "imputacion.importe_cent",
})


# ------------------------------------------------------------ reglas de la PO entera

def _de_cada_po(instantanea: Instantanea, regla: str, funcion) -> list[Resultado]:
    """Una regla de PO: un resultado por PO; una cerrada no se mira (ya no se consume)."""
    salida: list[Resultado] = []
    consumos = cargos(instantanea)
    for orden in instantanea.ordenes:
        if orden.cerrada:
            salida.append(Resultado(regla, "orden_compra", orden.id, NO_APLICA,
                                    f"{_mayus(_po_texto(orden))} está cerrada."))
            continue
        salida.append(funcion(orden, consumos.get(orden.id, []), instantanea))
    return salida


def _p5(orden: OrdenCompra, lista: list[Cargo], instantanea: Instantanea) -> Resultado:
    s = situacion(orden, lista)
    umbral = instantanea.politica.po_aviso_consumo_pct
    valores = {"valor_cent": s.valor_cent, "consumido_cent": s.consumido_cent,
               "restante_cent": s.restante_cent, "consumido_pb": s.consumido_pb,
               "umbral_pct": umbral}
    texto = (f"{_mayus(_po_texto(orden))} lleva consumido el {_pct(s.consumido_pb)} "
             f"({euros_texto(euros(s.consumido_cent))} de {euros_texto(euros(s.valor_cent))})")
    if s.consumido_pb >= umbral * 100:
        return Resultado("P5", "orden_compra", orden.id, FALLO, texto + f", el {umbral} % o más.",
                         valores)
    return Resultado("P5", "orden_compra", orden.id, OK, texto + ".")


def p5(instantanea: Instantanea) -> list[Resultado]:
    """La PO lleva consumido el umbral de la politica (80 %) o mas."""
    return _de_cada_po(instantanea, "P5", _p5)


def _p7(orden: OrdenCompra, lista: list[Cargo], instantanea: Instantanea,
        plan: turnos.Planificacion | None = None) -> Resultado:
    hoy, limite = instantanea.hoy, instantanea.politica.po_dias_caducidad
    if orden.fecha_fin is None:
        return Resultado("P7", "orden_compra", orden.id, NO_APLICA,
                         f"{_mayus(_po_texto(orden))} no tiene fecha de fin.")
    s = situacion(orden, lista)
    if s.restante_cent <= 0:
        return Resultado("P7", "orden_compra", orden.id, OK,
                         f"{_mayus(_po_texto(orden))} está consumida: no queda valor que "
                         "caduque.")
    dias = (orden.fecha_fin - hoy).days
    # Solo lo que no cambia con hoy: los valores son la huella, y unos dias que
    # bajan cada dia reabririan cada manana un P7 aceptado. Los dias que quedan
    # los cuenta la prioridad desde el fin (estados._dias_hasta_fin).
    valores = {"fin": orden.fecha_fin.isoformat(), "restante_cent": s.restante_cent,
               "limite_dias": limite}
    if dias < 0:
        caducada = (f"{_mayus(_po_texto(orden))} caducó el {orden.fecha_fin.isoformat()} con "
                    f"{euros_texto(euros(s.restante_cent))} por consumir")
        if plan is None:
            return Resultado("P7", "orden_compra", orden.id, SIN_DATOS,
                             caducada + ": sin planning importado no se sabe si hay trabajo "
                             "después de su fin.", valores)
        if plan.caducado:
            return Resultado("P7", "orden_compra", orden.id, SIN_DATOS,
                             caducada + ": " + _primera_minuscula(plan.sin_datos(hoy, hoy) or ""),
                             valores)
        despues = sin_po_tras_fin(instantanea, orden)
        if despues:
            return Resultado("P7", "orden_compra", orden.id, FALLO,
                             caducada + f" y el planning tiene {len(despues)} turno(s) después "
                             "de su fin que ninguna otra PO cubre: una PO nueva o una "
                             "modificación.",
                             {**valores, "turnos_despues": len(despues)}, severidad=R)
        motivo = plan.sin_datos(orden.fecha_fin + timedelta(days=1), hoy)
        if motivo is not None:
            return Resultado("P7", "orden_compra", orden.id, SIN_DATOS,
                             caducada + ": " + _primera_minuscula(motivo), valores)
        return Resultado("P7", "orden_compra", orden.id, OK,
                         caducada + ", sin trabajo en el planning después de su fin.")
    if dias <= limite:
        cuando = "hoy" if dias == 0 else f"en {dias} días"
        return Resultado("P7", "orden_compra", orden.id, FALLO,
                         f"{_mayus(_po_texto(orden))} caduca el {orden.fecha_fin.isoformat()} "
                         f"({cuando}) y le quedan {euros_texto(euros(s.restante_cent))}.", valores)
    return Resultado("P7", "orden_compra", orden.id, OK,
                     f"{_mayus(_po_texto(orden))} caduca dentro de {dias} días.")


def p7(instantanea: Instantanea) -> list[Resultado]:
    """La PO caduca dentro de los dias de la politica (30) con valor por consumir."""
    plan = turnos.Planificacion(instantanea) if instantanea.fotos_planning else None
    return _de_cada_po(instantanea, "P7",
                       lambda orden, lista, inst: _p7(orden, lista, inst, plan))


def _primera_minuscula(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def _sin_ver_lo_planificado(plan: turnos.Planificacion, orden: OrdenCompra,
                            hoy: date) -> str | None:
    """Por que el planning no deja decir que lo planificado de una PO cabe (P8, P10), o None.

    Lo planificado es lo de despues de hoy hasta el fin de la PO (sin fin,
    lo que el planning tenga desde hoy): un planning pasado de su frescura o
    que no cubre esos dias no dice que no haya mas. Pasarse si se puede decir
    con lo que se ve (es lo menos que hay); que cabe, no.
    """
    if plan.caducado:
        return plan.sin_datos(hoy, hoy)
    if orden.fecha_fin is None:
        return plan.sin_datos(hoy, hoy)
    if orden.fecha_fin <= hoy:
        return None
    return plan.sin_datos(hoy + timedelta(days=1), orden.fecha_fin)


def _sin_planning(instantanea: Instantanea, regla: str, que: str) -> list[Resultado]:
    """Una regla que necesita el planning, sin ninguna foto: sin datos por PO abierta (nunca
    ok)."""
    return [Resultado(regla, "orden_compra", orden.id, NO_APLICA,
                      f"{_mayus(_po_texto(orden))} está cerrada.") if orden.cerrada
            else Resultado(regla, "orden_compra", orden.id, SIN_DATOS,
                           f"{que} de {_po_texto(orden)} sale del planning, y no se ha "
                           "importado ninguno.")
            for orden in instantanea.ordenes]


def _de_su_parte(orden: OrdenCompra, t: Turno) -> bool:
    """Un turno de la parte de la PO y de un Objeto suyo (o de cualquiera, si no tiene)."""
    parte = t.cliente_id if orden.lado == CLIENTE else t.proveedor_id
    if parte is None or parte != orden.parte_id:
        return False
    return not orden.objetos or t.objeto_id in orden.objetos


def _cubre_turno(orden: OrdenCompra, t: Turno) -> bool:
    """Una PO abierta cubre un turno que no nombra ninguna: de su parte, de un Objeto suyo y de
    unos dias dentro de su vigencia (de su inicio a su fin, abierta por donde no lo dice).

    Sin la vigencia, una PO caducada que aun tiene valor y la que la sustituye
    cubririan los mismos turnos: ninguno seria de una sola, y P8 y P10 de la
    nueva no contarian nada.
    """
    return _de_su_parte(orden, t) and turnos.solapa(
        (t.fecha, turnos.ultimo_dia(t)), (orden.fecha_inicio or date.min,
                                          orden.fecha_fin or date.max))


def sin_po_tras_fin(instantanea: Instantanea, orden: OrdenCompra) -> list[Turno]:
    """P7 de una PO caducada: sus turnos de despues de su fin. Los que la nombran, y los que no
    nombran ninguna, son de su parte y de un Objeto suyo y ninguna otra PO abierta cubre (si
    la cubre la que la sustituye, no le falta nada). En una de cliente, solo los
    facturables."""
    otras = [o for o in instantanea.ordenes if not o.cerrada and o.id != orden.id]
    salida = []
    for t in instantanea.turnos:
        if (t.estado == turnos.CANCELADO or turnos.ultimo_dia(t) <= orden.fecha_fin
                or (orden.lado == CLIENTE and t.facturable is False)):
            continue
        if t.orden_compra_id is not None:
            if t.orden_compra_id == orden.id:
                salida.append(t)
        elif _de_su_parte(orden, t) and not any(_cubre_turno(o, t) for o in otras):
            salida.append(t)
    return salida


def turnos_de_po(instantanea: Instantanea) -> dict[int, list[Turno]]:
    """Los turnos (no cancelados) de cada PO; en una de cliente, solo los facturables."""
    por_id = {o.id: o for o in instantanea.ordenes}
    abiertas = [o for o in instantanea.ordenes if not o.cerrada]
    salida: dict[int, list[Turno]] = defaultdict(list)
    for t in instantanea.turnos:
        if t.estado == turnos.CANCELADO:
            continue
        if t.orden_compra_id is not None:
            orden = por_id.get(t.orden_compra_id)
            candidatas = [orden] if orden is not None else []
        else:
            candidatas = [o for o in abiertas if _cubre_turno(o, t)]
        if len(candidatas) != 1:
            continue
        orden = candidatas[0]
        if orden.lado == CLIENTE and t.facturable is False:
            continue
        salida[orden.id].append(t)
    return salida


def _valor_turnos(orden: OrdenCompra, lista: Sequence[Turno], horas: dict[str, int],
                  tarifas_: dict[str, tuple]) -> tuple[int, int]:
    """Lo que valen unas horas de unos turnos a la tarifa del lado de la PO, y cuantos no
    tienen ninguna tarifa (no suman: el valor es lo menos que sera)."""
    valor, sin_tarifa = 0, 0
    for t in lista:
        if orden.lado == CLIENTE:
            precio, _estimado = turnos.tarifa_de_venta(t, tarifas_.get("venta", ()))
        else:
            precio, _estimado = turnos.tarifa_de_compra(t, tarifas_.get("compra", ()))
        if precio is None:
            sin_tarifa += 1
            continue
        valor += turnos.valor_cent(horas[t.id_externo], precio)
    return valor, sin_tarifa


def esperado(instantanea: Instantanea, orden: OrdenCompra, lista: Sequence[Turno],
             conciliado: dict[str, tuple[int, frozenset[int]]],
             tarifas_: dict[str, tuple]) -> tuple[int, int, int]:
    """Lo trabajado sin facturar (hasta hoy, lo que no se ha conciliado con facturas de su
    lado) y lo planificado (despues de hoy) de una PO, valorados; y cuantos turnos no tienen
    tarifa."""
    pasados: dict[str, int] = {}
    futuros: dict[str, int] = {}
    for t in lista:
        horas = turnos.horas_referencia(t)
        if t.fecha > instantanea.hoy:
            futuros[t.id_externo] = horas
        else:
            pendiente = horas - conciliado.get(t.id_externo, (0,))[0]
            if pendiente > 0:
                pasados[t.id_externo] = pendiente
    sin_facturar, sin_a = _valor_turnos(orden, [t for t in lista if t.id_externo in pasados],
                                        pasados, tarifas_)
    planificado, sin_b = _valor_turnos(orden, [t for t in lista if t.id_externo in futuros],
                                       futuros, tarifas_)
    return sin_facturar, planificado, sin_a + sin_b


def p8(instantanea: Instantanea) -> list[Resultado]:
    """El trabajo planificado (despues de hoy) por la tarifa de su lado pasa lo que queda de la
    PO. Aviso de la PO entera: lo planificado se mueve cada dia, y no es de ninguna factura."""
    if not instantanea.fotos_planning:
        return _sin_planning(instantanea, "P8", "El trabajo planificado")
    de_po = turnos_de_po(instantanea)
    tarifas_ = por_sentido(instantanea.tarifas)
    plan = turnos.Planificacion(instantanea)

    def una(orden: OrdenCompra, lista: list[Cargo], inst: Instantanea) -> Resultado:
        if plan.caducado:
            return Resultado("P8", "orden_compra", orden.id, SIN_DATOS,
                             plan.sin_datos(inst.hoy, inst.hoy) or "")
        s = situacion(orden, lista)
        _sin, planificado, sin_tarifa = esperado(inst, orden, de_po.get(orden.id, []), {},
                                                 tarifas_)
        sin = f" ({sin_tarifa} turno(s) sin tarifa no suman)" if sin_tarifa else ""
        texto = (f"Lo planificado de {_po_texto(orden)} vale "
                 f"{euros_texto(euros(planificado))}{sin} y le quedan "
                 f"{euros_texto(euros(s.restante_cent))}")
        if planificado > s.restante_cent:
            return Resultado("P8", "orden_compra", orden.id, FALLO, texto + ": no alcanza.",
                             {"restante_cent": s.restante_cent, "valor_po_cent": s.valor_cent})
        motivo = _sin_ver_lo_planificado(plan, orden, inst.hoy)
        if motivo is not None:
            return Resultado("P8", "orden_compra", orden.id, SIN_DATOS,
                             texto + "; pero " + _primera_minuscula(motivo))
        return Resultado("P8", "orden_compra", orden.id, OK, texto + ".")
    return _de_cada_po(instantanea, "P8", una)


def _p9(orden: OrdenCompra, lista: list[Cargo], instantanea: Instantanea) -> Resultado:
    politica, hoy = instantanea.politica, instantanea.hoy
    if orden.fecha_fin is None:
        return Resultado("P9", "orden_compra", orden.id, NO_APLICA,
                         f"{_mayus(_po_texto(orden))} no tiene fecha de fin.")
    s = situacion(orden, lista)
    if s.restante_cent <= 0:
        return Resultado("P9", "orden_compra", orden.id, NO_APLICA,
                         f"{_mayus(_po_texto(orden))} ya está consumida: lo dicen P5 y P6.")
    p = prevision(orden, lista, hoy, politica.po_semanas_ritmo)
    if p.agotamiento is None:
        return Resultado("P9", "orden_compra", orden.id, OK,
                         f"Sin consumo desde el {p.desde.isoformat()}: a este ritmo "
                         f"{_po_texto(orden)} no se agota.")
    tope = orden.fecha_fin - timedelta(days=politica.po_margen_prevision_dias)
    # Como en P7, nada que se mueva con hoy (la ventana, sus dias y el dia de
    # agotamiento se mueven cada dia aunque no llegue ninguna factura): eso va
    # en el texto. La evidencia es lo que queda, el fin y el margen.
    valores = {"restante_cent": s.restante_cent, "fin": orden.fecha_fin.isoformat(),
               "margen_dias": politica.po_margen_prevision_dias}
    if p.agotamiento < tope:
        return Resultado("P9", "orden_compra", orden.id, FALLO,
                         f"Al ritmo de las últimas semanas ({euros_texto(euros(p.consumido_cent))}"
                         f" en {p.dias} días) {_po_texto(orden)} se agota el "
                         f"{p.agotamiento.isoformat()}, más de "
                         f"{politica.po_margen_prevision_dias} días antes de su fin "
                         f"({orden.fecha_fin.isoformat()}).", valores)
    return Resultado("P9", "orden_compra", orden.id, OK,
                     f"A este ritmo {_po_texto(orden)} se agota el {p.agotamiento.isoformat()}.")


def p9(instantanea: Instantanea) -> list[Resultado]:
    """Al ritmo de las ultimas semanas la PO se agota antes del margen de su fin (14 dias)."""
    return _de_cada_po(instantanea, "P9", _p9)


def p10(instantanea: Instantanea) -> list[Resultado]:
    """Lo facturado mas lo trabajado sin facturar mas lo planificado pasa el valor de la PO.

    Es de la PO entera, y retiene ademas las facturas que le cargan desde el
    punto en que lo esperado pasa el valor (en el orden del §7): son sus
    objetivos, y asi su suelo urgente (§8) llega a ellas.
    """
    if not instantanea.fotos_planning:
        return _sin_planning(instantanea, "P10", "Lo trabajado sin facturar y lo planificado")
    de_po = turnos_de_po(instantanea)
    tarifas_ = por_sentido(instantanea.tarifas)
    conciliados = {lado: turnos.conciliado(instantanea, SENTIDO_DE_LADO[lado])
                   for lado in (CLIENTE, PROVEEDOR)}
    plan = turnos.Planificacion(instantanea)

    def una(orden: OrdenCompra, lista: list[Cargo], inst: Instantanea) -> Resultado:
        if plan.caducado:
            return Resultado("P10", "orden_compra", orden.id, SIN_DATOS,
                             plan.sin_datos(inst.hoy, inst.hoy) or "")
        s = situacion(orden, lista)
        sin_facturar, planificado, sin_tarifa = esperado(
            inst, orden, de_po.get(orden.id, []), conciliados[orden.lado], tarifas_)
        pendiente = sin_facturar + planificado
        total = s.consumido_cent + pendiente
        sin = f" ({sin_tarifa} turno(s) sin tarifa no suman)" if sin_tarifa else ""
        texto = (f"{_mayus(_po_texto(orden))}: facturado {euros_texto(euros(s.consumido_cent))}"
                 f", sin facturar {euros_texto(euros(sin_facturar))} y planificado "
                 f"{euros_texto(euros(planificado))}{sin}; vale "
                 f"{euros_texto(euros(s.valor_cent))}")
        if total <= s.valor_cent:
            motivo = _sin_ver_lo_planificado(plan, orden, inst.hoy)
            if motivo is not None:
                return Resultado("P10", "orden_compra", orden.id, SIN_DATOS,
                                 texto + "; pero " + _primera_minuscula(motivo))
            return Resultado("P10", "orden_compra", orden.id, OK, texto + ".")
        desde, objetivos = None, []
        for cargo, antes in antes_de_cada(orden, lista):
            if desde is None and antes - cargo.importe_cent - pendiente < 0:
                desde = cargo.factura_id
            if desde is not None:
                objetivos.append(Objetivo("factura", cargo.factura_id, None, RELACIONADO))
        return Resultado("P10", "orden_compra", orden.id, FALLO,
                         texto + f": lo esperado ({euros_texto(euros(total))}) pasa su valor.",
                         {"valor_po_cent": s.valor_cent, "esperado_cent": total},
                         objetivos=tuple(objetivos))
    return _de_cada_po(instantanea, "P10", una)


LEE_DE_PO = frozenset({"instantanea.ordenes", "orden_compra.id", "orden_compra.cerrada",
                       "orden_compra.numero"}) | LEE_CARGOS
LEE_P5 = LEE_DE_PO | {"instantanea.politica", "politica.po_aviso_consumo_pct"}
LEE_TURNOS_DE_PO = frozenset({
    "instantanea.turnos", "instantanea.ordenes", "orden_compra.id", "orden_compra.cerrada",
    "orden_compra.lado", "orden_compra.parte_id", "orden_compra.objetos", "turno.estado",
    "turno.orden_compra_id", "turno.cliente_id", "turno.proveedor_id", "turno.objeto_id",
    "turno.facturable", "orden_compra.fecha_inicio", "orden_compra.fecha_fin", "turno.fecha",
    "turno.nivel"})
LEE_P7 = LEE_DE_PO | LEE_TURNOS_DE_PO | turnos.LEE_PLANIFICACION | {
    "instantanea.politica", "instantanea.hoy", "politica.po_dias_caducidad",
    "orden_compra.fecha_fin", "instantanea.fotos_planning", "turno.nivel", "turno.fecha"}
LEE_SIN_PLANNING = frozenset({"instantanea.ordenes", "orden_compra.id", "orden_compra.cerrada",
                              "orden_compra.numero", "instantanea.fotos_planning"})
_LEE_ESPERADO = LEE_TURNOS_DE_PO | frozenset({
    "instantanea.hoy", "instantanea.tarifas", "turno.fecha", "turno.id_externo",
    "turno.horas_aprobadas_mil", "turno.horas_realizadas_mil", "turno.horas_planificadas_mil",
    "turno.tarifa_venta_e4", "turno.tarifa_compra_e4", "turno.recurso_id", "turno.tipo_turno",
    "turno.tipo_servicio", "tarifa.sentido", "tarifa.id"}) | LEE_TARIFA_COMPRA | LEE_TARIFA_VENTA
LEE_P8 = LEE_SIN_PLANNING | LEE_DE_PO | _LEE_ESPERADO | turnos.LEE_PLANIFICACION
LEE_P9 = LEE_DE_PO | {"instantanea.politica", "instantanea.hoy", "politica.po_semanas_ritmo",
                      "politica.po_margen_prevision_dias", "orden_compra.fecha_fin",
                      "orden_compra.fecha_inicio", "orden_compra.fecha_emision"}
LEE_P10 = (LEE_SIN_PLANNING | LEE_DE_PO | _LEE_ESPERADO | turnos.LEE_CONCILIADO
           | turnos.LEE_PLANIFICACION)


# El texto de un aviso de PO de la PO entera no lleva nada que dependa de una
# factura: su numero si, para ensenarlo.
SOLO_TEXTO = frozenset({"orden_compra.numero", "referencia.valor_doc"})

