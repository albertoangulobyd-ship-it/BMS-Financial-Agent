"""Reglas contra el planning y las tarifas pactadas: G1-G7 (y V4, en venta.py).

G3 compara la tarifa de cada linea de compra con la que le toca, en el orden
del §7: la pactada (tarifa_acordada, de lo mas concreto a lo general, ver
tarifas.py), si no la del turno en el planning (paso 10: si todos los turnos
de su celda dicen la misma) y si no el historico: que la misma contraparte cobre dos
tarifas distintas por el mismo trabajo en el mismo Objeto, en facturas
distintas. Contra la pactada retiene si la linea cobra mas, y bloquea si la
pasa en mas del porcentaje de la politica (anularlo pide segunda firma); contra
el historico solo retiene. Cobrar menos de lo pactado no es un problema de una
compra.

Una linea de un recargo (noche, fin de semana, festivo: un turno que no es el
de dia) con su propia tarifa pactada la mira G6: un recargo se cobra a su
propia tarifa. Si su parte, su recurso o su Objeto no tienen ninguna tarifa
pactada, sigue con el historico de G3, como antes.

El turno, la unidad y el dia salen del documento. Una linea que no casa con
ninguna pactada por su turno, su unidad o su dia, cuando si las hay para ella
(tarifas.NO_CASA), no vuelve al historico: da sin datos y la factura queda
retenida (clave "no_casa"), en G3 si es de dia y en G6 si es un recargo, para
que una persona confirme el recargo, la unidad o el dia. Si no, imprimir
"Nacht" o "stuk" bastaria para saltarse la tarifa pactada y su bloqueo.

Si para una linea hay dos tarifas igual de concretas con precios distintos, no
se adivina: la comparacion da sin datos y la factura queda retenida con su
excepcion ("ambigua"), para que alguien arregle el maestro.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import turnos
from .base import (
    B,
    ENTRANTE,
    FALLO,
    LEE_PERIODO,
    NO_APLICA,
    OK,
    RELACIONADO,
    SIN_DATOS,
    Factura,
    Imputacion,
    Instantanea,
    Linea,
    Objetivo,
    Resultado,
    compacto,
    en_juego,
    euros_texto,
    fuera_de_juego,
    lineas_en_orden,
    periodo_de,
    tarifa,
)
from .tarifas import (
    AMBIGUA,
    LEE_TARIFA_COMPRA,
    LEE_TARIFA_VENTA,
    NINGUNA,
    NO_CASA,
    Pactada,
    normalizar_turno,
    pactada,
    por_sentido,
)
from .turnos import Celda


def tipo_de_trabajo(descripcion: object) -> str:
    """La descripcion de una linea reducida a su tipo de trabajo.

    "Montagewerk, locatie Schiedam" y "Reisuren, locatie Schiedam" son la
    misma obra pero trabajos distintos, y cobrarlos a tarifas distintas es lo
    normal. Sin esta distincion, cada factura con horas de viaje dispararia
    un cambio de tarifa, y una alerta que salta siempre se ignora.
    """
    texto = str(descripcion or "").strip().lower()
    return texto.split(",")[0].strip() or "(sin descripcion)"


@dataclass(frozen=True)
class Observacion:
    """Una tarifa cobrada: de que grupo (contraparte, obra, trabajo), cuando y en que factura."""

    grupo: Hashable
    tarifa: Decimal
    fecha: str
    ref: Hashable


@dataclass(frozen=True)
class CambioDeTarifa:
    grupo: Hashable
    anterior: Decimal
    posteriores: tuple[Decimal, ...]
    desviadas: tuple[Hashable, ...]
    primera_fecha: str
    ultima_fecha: str


def cambios_de_tarifa(observaciones: Iterable[Observacion]) -> list[CambioDeTarifa]:
    """Los grupos donde la tarifa cambia de una factura a otra.

    Solo cuenta entre facturas: dos tarifas dentro de una misma factura son
    normalmente dos conceptos. La de referencia es la primera que se vio (por
    fecha, y a igual fecha la menor), no la mas repetida: tras una subida
    pactada, la frecuencia acabaria senalando el historico correcto en vez de
    la subida. Las desviadas son las facturas con otra tarifa.
    """
    tarifas: dict[Hashable, dict[Decimal, list[tuple[str, Hashable]]]] = defaultdict(
        lambda: defaultdict(list))
    for o in observaciones:
        tarifas[o.grupo][o.tarifa].append((o.fecha, o.ref))
    salida = []
    for grupo, por_tarifa in tarifas.items():
        if len(por_tarifa) < 2:
            continue
        refs = {t: {r for _f, r in v} for t, v in por_tarifa.items()}
        if len(set().union(*refs.values())) < 2:
            continue
        if not any(refs[t1] - refs[t2] for t1 in refs for t2 in refs if t1 != t2):
            continue
        primera_de = {t: min(f for f, _r in v) for t, v in por_tarifa.items()}
        anterior = min(por_tarifa, key=lambda t: (primera_de[t], t))
        posteriores = tuple(sorted(t for t in por_tarifa if t != anterior))
        desviadas = tuple(sorted(r for t in posteriores for r in refs[t]))
        fechas = sorted(f for lista in por_tarifa.values() for f, _r in lista)
        salida.append(CambioDeTarifa(grupo, anterior, posteriores, desviadas,
                                     fechas[0], fechas[-1]))
    return salida


SIN_OBRA = "(sin obra)"


# ------------------------------------------------------------ contra la tarifa pactada

def dia_de(i: Imputacion, linea: Linea, factura: Factura) -> date | None:
    """El dia con que se busca la tarifa vigente: el de la imputacion, el de su linea, el del
    periodo de la factura o el de la factura."""
    return (i.fecha_inicio or linea.fecha_trabajo or linea.fecha_inicio
            or factura.periodo_inicio or factura.fecha_factura)


def con_pactada(instantanea: Instantanea, sentido: str,
                ) -> Iterator[tuple[Factura, Imputacion, Linea, str | None, Pactada]]:
    """Cada imputacion de una linea con tarifa, en las facturas en juego de un sentido, con
    su turno y la tarifa pactada que le toca. Nada si no hay tarifas de ese sentido."""
    del_sentido = por_sentido(instantanea.tarifas).get(
        "compra" if sentido == ENTRANTE else "venta", ())
    if not del_sentido:
        return
    for factura in instantanea.facturas:
        if factura.sentido != sentido or not factura.imputaciones or not en_juego(factura):
            continue
        lineas = {l.id: l for l in factura.lineas}
        parte = factura.proveedor_id if sentido == ENTRANTE else factura.cliente_id
        for i in factura.imputaciones:
            linea = lineas.get(i.linea_id) if i.linea_id is not None else None
            if linea is None or linea.tarifa_e4 is None:
                continue
            turno = normalizar_turno(i.tipo_turno)
            yield factura, i, linea, turno, pactada(
                del_sentido, parte_id=parte, recurso_id=i.recurso_id, objeto_id=i.objeto_id,
                orden_compra_id=i.orden_compra_id, turno=turno, servicio=i.tipo_servicio,
                unidad=linea.unidad, fecha=dia_de(i, linea, factura))


def valor_de_la_diferencia(diferencia_e4: int, i: Imputacion, linea: Linea) -> int:
    """Lo que vale una diferencia de tarifa en la imputacion, en centimos (para la
    prioridad): la diferencia por sus horas o, si no, por la cantidad de su linea."""
    cantidad = i.horas_mil if i.horas_mil is not None else (linea.cantidad_mil or 0)
    return abs(diferencia_e4) * abs(cantidad) // 100000


def contra_pactada(regla: str, factura: Factura, i: Imputacion, linea: Linea, p: Pactada, *,
                   tambien_por_debajo: bool = False,
                   exceso_bloqueo_pct: int | None = None) -> Resultado:
    """El resultado de comparar la tarifa de una linea con la pactada de su imputacion."""
    clave = f"pactada:{i.id}"
    if p.estado == AMBIGUA:
        return Resultado(regla, "factura", factura.id, SIN_DATOS,
                         f"Hay {len(p.tarifas)} tarifas pactadas igual de concretas ({p.nivel}) "
                         "con precios distintos: no se adivina cuál vale.",
                         {"imputacion": i.id, "tarifas": list(p.tarifas), "nivel": p.nivel}, clave)
    precio, pactado = linea.tarifa_e4, p.tarifa_e4
    diferencia = precio - pactado
    texto_precio = euros_texto(tarifa(precio).quantize(Decimal("0.01")))
    texto_pactado = euros_texto(tarifa(pactado).quantize(Decimal("0.01")))
    if diferencia > 0 or (diferencia < 0 and tambien_por_debajo):
        severidad = None
        if (exceso_bloqueo_pct is not None and diferencia > 0
                and diferencia * 100 > pactado * exceso_bloqueo_pct):
            severidad = B
        donde = "por encima" if diferencia > 0 else "por debajo"
        valores = {"imputacion": i.id, "linea": linea.id, "tarifa_e4": precio,
                   "pactada_e4": pactado, "tarifas": list(p.tarifas), "nivel": p.nivel,
                   "valor_cent": valor_de_la_diferencia(diferencia, i, linea)}
        return Resultado(
            regla, "factura", factura.id, FALLO,
            f"La línea {linea.orden} cobra {texto_precio}, {donde} de la tarifa pactada "
            f"({p.nivel}) de {texto_pactado}"
            + (f", más del {exceso_bloqueo_pct} %" if severidad == B else "") + ".",
            valores, clave, severidad=severidad,
            objetivos=(Objetivo("factura_linea", linea.id, "tarifa_e4", RELACIONADO),))
    return Resultado(regla, "factura", factura.id, OK,
                     f"La línea {linea.orden} va a la tarifa pactada ({p.nivel})"
                     + (" o por debajo." if diferencia < 0 else "."), clave=clave)


def ambiguas(regla: str, factura: Factura, imputaciones: list[int],
             tarifas_: set[int]) -> Resultado:
    """La retencion de una factura con tarifas pactadas ambiguas (spec §7: sin datos y una
    excepcion). Retiene, y por eso abre su excepcion como cualquier retencion: un aviso no la
    abriria sin crea_excepcion, y esa marca haria que la abriera tambien cada aviso del
    historico de G3."""
    return Resultado(regla, "factura", factura.id, FALLO,
                     f"Las tarifas pactadas {', '.join(map(str, sorted(tarifas_)))} dicen precios "
                     f"distintos para {len(imputaciones)} línea(s) de esta factura: hay que "
                     "arreglar el maestro de tarifas.",
                     {"imputaciones": sorted(imputaciones), "tarifas": sorted(tarifas_)},
                     "ambigua")


def no_casa(regla: str, factura: Factura, i: Imputacion, linea: Linea, turno: str | None,
            p: Pactada) -> Resultado:
    """Una linea que no casa con ninguna tarifa pactada por su turno, su unidad o su dia,
    cuando si las hay para ella: sin datos (la retencion la da `sin_casar`)."""
    dia = dia_de(i, linea, factura)
    return Resultado(regla, "factura", factura.id, SIN_DATOS,
                     f"La línea {linea.orden} (turno {turno or 'de día'}, unidad "
                     f"{linea.unidad or 'sin unidad'}, del {dia.isoformat() if dia else '…'}) no "
                     f"casa con ninguna de las tarifas pactadas que tiene "
                     f"({', '.join(map(str, p.tarifas))}): no se compara con el histórico.",
                     {"imputacion": i.id, "turno": turno, "unidad": linea.unidad,
                      "dia": dia.isoformat() if dia else None, "tarifas": list(p.tarifas)},
                     f"pactada:{i.id}")


def sin_casar(regla: str, factura: Factura, imputaciones: list[int],
              tarifas_: set[int]) -> Resultado:
    """La retencion de una factura con lineas que no casan con lo pactado por su turno, su
    unidad o su dia: una persona confirma el recargo, la unidad o el dia (como una ambigua)."""
    return Resultado(regla, "factura", factura.id, FALLO,
                     f"{len(imputaciones)} línea(s) con un turno, una unidad o un día que no "
                     f"tiene ninguna de las tarifas pactadas ({', '.join(map(str, sorted(tarifas_)))}"
                     "): una persona confirma el recargo, la unidad o el día.",
                     {"imputaciones": sorted(imputaciones), "tarifas": sorted(tarifas_)},
                     NO_CASA)


def comparar_con_pactadas(instantanea: Instantanea, regla: str, sentido: str, *,
                          recargos: bool | None, tambien_por_debajo: bool,
                          exceso_bloqueo_pct: int | None, sin_pactada: str | None,
                          retiene_sin_casar: bool = False,
                          decididas: set[int] | None = None) -> list[Resultado]:
    """Las comparaciones de una regla contra la tarifa pactada, y la retencion de las ambiguas.

    `recargos`: True, solo las lineas de un recargo; False, solo las demas; None,
    todas. `sin_pactada`: el resultado (no_aplica o sin_datos) de una linea sin
    tarifa pactada, o None para no dar ninguno (G3 la deja al historico).
    `retiene_sin_casar`: una linea que no casa por su turno, su unidad o su dia
    da sin datos y retiene la factura (G3, G6); si no, es como sin pactada (V4).
    `decididas` recoge las lineas que tenian tarifa pactada (unica o ambigua) o
    que no casan con ella: ninguna vuelve al historico.
    """
    salida: list[Resultado] = []
    ambigua: dict[int, tuple[Factura, list[int], set[int]]] = {}
    no_casan: dict[int, tuple[Factura, list[int], set[int]]] = {}
    for factura, i, linea, turno, p in con_pactada(instantanea, sentido):
        if recargos is not None and (turno is not None) != recargos:
            if decididas is not None and p.estado != NINGUNA:
                decididas.add(linea.id)
            continue
        if p.estado == NO_CASA and retiene_sin_casar:
            if decididas is not None:
                decididas.add(linea.id)
            salida.append(no_casa(regla, factura, i, linea, turno, p))
            _f, ids, tarifas_ = no_casan.setdefault(factura.id, (factura, [], set()))
            ids.append(i.id)
            tarifas_.update(p.tarifas)
            continue
        if p.estado in (NINGUNA, NO_CASA):
            if sin_pactada is not None:
                salida.append(Resultado(regla, "factura", factura.id,
                                        SIN_DATOS if sin_pactada == SIN_DATOS else NO_APLICA,
                                        _SIN_PACTADA[regla], clave=f"pactada:{i.id}"))
            continue
        if decididas is not None:
            decididas.add(linea.id)
        salida.append(contra_pactada(regla, factura, i, linea, p,
                                     tambien_por_debajo=tambien_por_debajo,
                                     exceso_bloqueo_pct=exceso_bloqueo_pct))
        if p.estado == AMBIGUA:
            _f, ids, tarifas_ = ambigua.setdefault(factura.id, (factura, [], set()))
            ids.append(i.id)
            tarifas_.update(p.tarifas)
    for factura_id in sorted(ambigua):
        factura, ids, tarifas_ = ambigua[factura_id]
        salida.append(ambiguas(regla, factura, ids, tarifas_))
    for factura_id in sorted(no_casan):
        factura, ids, tarifas_ = no_casan[factura_id]
        salida.append(sin_casar(regla, factura, ids, tarifas_))
    return salida


_SIN_PACTADA = {
    "G6": "Ni el recargo ni su parte, su recurso o su Objeto tienen tarifa pactada: G3 lo "
          "compara con el histórico.",
}

_LEE_PACTADA = frozenset({
    "instantanea.tarifas", "instantanea.facturas", "factura.id", "factura.sentido",
    "factura.imputaciones", "factura.anulada", "factura.fusionada_en_id",
    "factura.sustituida_por", "factura.lineas", "factura.periodo_inicio", "factura.fecha_factura",
    "linea.id", "linea.orden", "linea.tarifa_e4", "linea.unidad", "linea.fecha_trabajo",
    "linea.fecha_inicio", "linea.cantidad_mil", "imputacion.id", "imputacion.linea_id",
    "imputacion.recurso_id", "imputacion.objeto_id", "imputacion.orden_compra_id",
    "imputacion.tipo_turno", "imputacion.tipo_servicio", "imputacion.fecha_inicio",
    "imputacion.horas_mil",
})
LEE_PACTADA_COMPRA = _LEE_PACTADA | LEE_TARIFA_COMPRA
LEE_PACTADA_VENTA = _LEE_PACTADA | LEE_TARIFA_VENTA


# Quien resolvio la contraparte, el Objeto, el recurso y la PO elige la tarifa
# pactada que vale, pero no es evidencia: lo es la tarifa elegida y su precio,
# que van en los valores del resultado. Si entrara su fuente, dar de alta el
# proveedor o sembrar los Objetos reabriria un G3 ya aceptado sin que cambie
# nada de lo comparado (como la contraparte de los duplicados, motor.py).
NO_EVIDENCIA_PACTADA = frozenset({"factura.proveedor_id", "factura.cliente_id",
                                  "imputacion.objeto_id", "imputacion.recurso_id",
                                  "imputacion.orden_compra_id"})


def g6(instantanea: Instantanea) -> list[Resultado]:
    """G6: un recargo se cobra a su propia tarifa pactada (las compras), y solo por las horas
    que el planning tiene de ese recargo.

    Solo las lineas de un turno que no es el de dia. Si su parte, su recurso o
    su Objeto tienen tarifas pactadas pero ninguna de ese turno (o de su unidad
    o su dia), no casa: sin datos y la factura retenida, para que una persona
    confirme el recargo. Sin ninguna tarifa pactada no aplica: la compara G3
    con el historico. Desde el paso 10, ademas, las horas de cada recargo
    contra las de los turnos de ese recargo en el planning
    (`recargos_contra_planning`); sin planning, esa parte da un solo sin_datos.
    """
    salida = comparar_con_pactadas(instantanea, "G6", ENTRANTE, recargos=True,
                                   tambien_por_debajo=False, exceso_bloqueo_pct=None,
                                   sin_pactada=NO_APLICA, retiene_sin_casar=True)
    vacio = turnos.sin_planning(instantanea, "G6")
    salida.extend(vacio if vacio is not None else recargos_contra_planning(instantanea))
    return salida


def g3(instantanea: Instantanea) -> Iterator[Resultado]:
    """G3 sobre las facturas de compra en euros: contra la pactada y, si no hay, el historico.

    Contra la pactada, un resultado por imputacion de una linea que no es un
    recargo (clave pactada:<imputacion>); sin pactada, contra la tarifa del turno
    en el planning si todos los turnos de su celda dicen la misma (clave
    turno:<imputacion>, paso 10). En el historico, el grupo es la
    contraparte, el Objeto (el resuelto o, si no, el nombre impreso), el tipo de
    trabajo y la unidad: una tarifa por hora y otra por pieza no se comparan.
    Cada factura tiene un resultado por grupo en el que cobra algo; el hallazgo
    es del grupo y cubre las facturas desviadas. Una linea con tarifa pactada
    (la de G3 o la propia de un recargo, de G6) no entra en el historico.
    """
    decididas: set[int] = set()
    exceso = instantanea.politica.tarifa_exceso_bloqueo_pct if instantanea.tarifas else None
    yield from comparar_con_pactadas(instantanea, "G3", ENTRANTE, recargos=False,
                                     tambien_por_debajo=False, exceso_bloqueo_pct=exceso,
                                     sin_pactada=None, retiene_sin_casar=True,
                                     decididas=decididas)
    # Paso 10: sin pactada, la tarifa del turno en el planning, antes que el historico.
    if instantanea.fotos_planning:
        yield from contra_tarifa_del_turno(instantanea, "G3", ENTRANTE, decididas,
                                           tambien_por_debajo=False)
    facturas = {f.id: f for f in instantanea.facturas}
    observaciones: list[Observacion] = []
    lineas_de: dict[tuple, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    nombres_obra: dict[tuple, str] = {}
    grupos_de: dict[int, set] = defaultdict(set)
    for factura in instantanea.facturas:
        motivo = fuera_de_juego(factura)
        if motivo is not None:
            yield Resultado("G3", "factura", factura.id, NO_APLICA, motivo)
            continue
        if factura.sentido != ENTRANTE:
            yield Resultado("G3", "factura", factura.id, NO_APLICA,
                            "G3 compara las tarifas de compra.")
            continue
        if decididas and not any(l.tarifa_e4 is not None and l.id not in decididas
                                 for l in factura.lineas):
            if any(l.id in decididas for l in factura.lineas):
                continue        # todas sus lineas con tarifa tienen la pactada
        if factura.parte is None:
            yield Resultado("G3", "factura", factura.id, SIN_DATOS,
                            "El documento no dice de quién es: no hay historico con que comparar.")
            continue
        if factura.fecha_factura is None:
            # La referencia es la tarifa que se vio primero: una factura sin
            # fecha no se puede poner en esa fila, y tomarla por la mas
            # antigua haria de su tarifa la buena y senalaria a las demas.
            yield Resultado("G3", "factura", factura.id, SIN_DATOS,
                            "Sin fecha de factura: no se sabe qué tarifa vino antes.")
            continue
        fecha = factura.fecha_factura.isoformat()
        for linea in lineas_en_orden(factura):
            precio = tarifa(linea.tarifa_e4)
            if precio is None or linea.id in decididas:
                continue
            grupo = (factura.parte, linea.objeto or SIN_OBRA,
                     tipo_de_trabajo(linea.descripcion_doc), linea.unidad or "")
            # El nombre que se ensena no puede depender de que factura llego antes.
            nombre = linea.objeto_doc or SIN_OBRA
            nombres_obra[grupo] = min(nombres_obra.get(grupo, nombre), nombre)
            observaciones.append(Observacion(grupo, precio, fecha, factura.id))
            lineas_de[grupo][factura.id].append(linea)
            grupos_de[factura.id].add(grupo)
        if not grupos_de[factura.id]:
            yield Resultado("G3", "factura", factura.id, SIN_DATOS,
                            "Ninguna línea trae tarifa.")

    cambios = {c.grupo: c for c in cambios_de_tarifa(observaciones)}
    hallazgo_de: dict[tuple, tuple] = {}
    # La identidad del grupo es su primera linea (la de id menor): cada linea
    # cae en un grupo solo, y no cambia cuando la contraparte o el Objeto se
    # resuelven contra el maestro ("doc:rijnhaven" pasa a "objeto:1"), que es
    # justo lo que no puede cerrar un hallazgo ni quitarle su anulacion.
    clave_de = {grupo: f"linea:{min(l.id for ls in por_factura.values() for l in ls)}"
                for grupo, por_factura in lineas_de.items()}

    def hallazgo(grupo: tuple, clave: str, cambio: CambioDeTarifa) -> tuple:
        """Lo que comparten todas las facturas desviadas de un grupo, calculado una vez."""
        if grupo not in hallazgo_de:
            _parte, _obra, trabajo, unidad = grupo
            desviadas = sorted(set(cambio.desviadas))
            principal = desviadas[-1]
            objetivos = (Objetivo("factura", principal),) + tuple(
                Objetivo("factura", i, None, RELACIONADO) for i in desviadas[:-1]) + tuple(
                Objetivo("factura_linea", l.id, "tarifa_e4", RELACIONADO)
                for i in desviadas for l in lineas_de[grupo][i]
                if tarifa(l.tarifa_e4) != cambio.anterior)
            detalle = (f"{facturas[principal].parte_nombre}, {trabajo} en {nombres_obra[grupo]}: "
                       f"venía a {euros_texto(cambio.anterior)} y después a "
                       + " y ".join(euros_texto(t) for t in cambio.posteriores)
                       + f", entre {cambio.primera_fecha} y {cambio.ultima_fecha}.")
            valores = {"grupo": clave, "trabajo": trabajo, "unidad": unidad,
                       "anterior_e4": int(cambio.anterior.scaleb(4)),
                       "posteriores_e4": [int(t.scaleb(4)) for t in cambio.posteriores],
                       "desviadas": desviadas}
            hallazgo_de[grupo] = (detalle, valores, objetivos)
        return hallazgo_de[grupo]

    for factura_id in sorted(grupos_de):
        for grupo in sorted(grupos_de[factura_id]):
            _parte, _obra, trabajo, _unidad = grupo
            clave = clave_de[grupo]
            cambio = cambios.get(grupo)
            if cambio is None or factura_id not in cambio.desviadas:
                yield Resultado("G3", "factura", factura_id, OK,
                                f"{trabajo} en {nombres_obra[grupo]}: la tarifa de siempre.",
                                clave=clave)
                continue
            detalle, valores, objetivos = hallazgo(grupo, clave, cambio)
            yield Resultado("G3", "factura", factura_id, FALLO, detalle, valores=valores,
                            clave=clave, grupo=clave, objetivos=objetivos)


# El nombre de la contraparte y el de la obra solo se ensenan.
SOLO_TEXTO_G3 = frozenset({"factura.parte_nombre", "linea.objeto_doc"})

LEE_G3 = LEE_PACTADA_COMPRA | frozenset({
    "instantanea.facturas", "factura.id", "factura.anulada", "factura.fusionada_en_id",
    "factura.sustituida_por",
    "factura.sentido", "factura.parte", "factura.parte_nombre", "factura.fecha_factura",
    "factura.lineas", "linea.id", "linea.orden", "linea.tarifa_e4", "linea.objeto",
    "linea.objeto_doc", "linea.descripcion_doc", "linea.unidad", "factura.proveedor_id",
    "instantanea.politica", "politica.tarifa_exceso_bloqueo_pct", "instantanea.fotos_planning",
    "turno.tarifa_compra_e4",
})


# ------------------------------------------------------------ contra el planning (paso 10)
#
# G1, G2, G4, G5, G7, la parte del planning de G6 y el escalon del planning de
# G3 (y de V4, en venta.py). Las celdas, lo que cubre el planning y lo que se
# concilio salen de turnos.py. Sin ninguna foto del planning, cada regla da un
# solo sin_datos (turnos.sin_planning); con el planning pasado de su frescura
# o sin cubrir los dias de una factura, sin_datos en esa factura: nunca ok.

def _horas(mil: int) -> str:
    """Unas horas como se leen: 8, 7,5 o 8,333."""
    texto = str(compacto(Decimal(mil).scaleb(-3)))
    return texto.replace(".", ",")


def _dias_texto(celda: Celda) -> str:
    if celda.desde == celda.hasta:
        return f"el {celda.desde.isoformat()}"
    if turnos.semana_entera(celda.desde, celda.hasta):
        return f"la semana {turnos.semana_iso(celda.desde)}"
    return f"del {celda.desde.isoformat()} al {celda.hasta.isoformat()}"


def _de_quien(celda: Celda) -> str:
    return "la persona" if celda.dimension == turnos.RECURSO else "el Objeto"


def _sin_datos(regla: str, factura: Factura, motivo: str, clave: str) -> Resultado:
    return Resultado(regla, "factura", factura.id, SIN_DATOS, motivo, clave=clave)


def comparar_horas(instantanea: Instantanea, regla: str, sentido: str) -> list[Resultado]:
    """G2 y V1: las horas facturadas de cada celda contra las validadas del planning.

    En una compra, los turnos de su proveedor; en una venta, los facturables de
    su cliente. La tolerancia es la de la politica por dia con turnos de la
    celda (0,25 h: 0,25 pasa y 0,26 no). Una fila semanal que no se puede
    partir o unos dias que el planning no cubre dan sin datos.

    Lo que dice si unas horas estan validadas es el estado del turno. Una celda
    con algun turno sin validar no tiene con que comparar del todo, pero si
    tiene un tope: las horas de cada turno (las validadas, las realizadas o las
    planificadas, turnos.horas_referencia). Cobrar mas que ese tope (con la
    tolerancia) retiene; si no, sin datos hasta que se validen. Si no, una
    factura podria cobrar cualquier cosa contra turnos sin validar sin que
    nada la parase.
    """
    vacio = turnos.sin_planning(instantanea, regla)
    if vacio is not None:
        return vacio
    plan = turnos.Planificacion(instantanea)
    grupos, sueltas = turnos.agrupar(instantanea, sentido, plan.indice)
    salida = [_sin_datos(regla, s.factura, s.motivo, f"imputacion:{s.imputacion.id}")
              for s in sueltas]
    for g in grupos:
        motivo = plan.sin_datos(g.celda.desde, g.celda.hasta)
        if motivo is not None:
            salida.append(_sin_datos(regla, g.factura, motivo, g.clave))
            continue
        c = turnos.contenido(g.celda, plan.indice, turnos.de_la_parte(g.factura))
        if c.parcial:
            salida.append(_sin_datos(
                regla, g.factura, f"El planning de {_dias_texto(g.celda)} solo tiene filas "
                                  "semanales que no caben enteras: no se pueden partir.",
                g.clave))
            continue
        tolerancia = turnos.tolerancia_mil(plan.tolerancia, c.dias)
        dias = _dias_texto(g.celda)
        tarifa_ = _tarifa_de(g)
        pendientes = [t for t in c.turnos if turnos.horas_validadas(t) is None]
        if pendientes:
            tope = sum(turnos.horas_referencia(t) for t in c.turnos)
            exceso = g.horas_mil - tope
            if exceso <= tolerancia:
                salida.append(_sin_datos(
                    regla, g.factura, f"{len(pendientes)} turno(s) de {dias} todavía sin validar "
                                      "en el planning: no hay horas validadas con qué comparar.",
                    g.clave))
                continue
            salida.append(Resultado(
                regla, "factura", g.factura.id, FALLO,
                f"{_horas(g.horas_mil)} h facturadas {dias} ({_de_quien(g.celda)}) y el planning "
                f"tiene como mucho {_horas(tope)} h, con {len(pendientes)} turno(s) todavía sin "
                f"validar: {_horas(exceso)} h de más, más que la tolerancia de "
                f"{_horas(tolerancia)} h.",
                {"nivel": g.celda.nivel, "desde": g.celda.desde.isoformat(),
                 "hasta": g.celda.hasta.isoformat(), "facturadas_mil": g.horas_mil,
                 "tope_mil": tope, "sin_validar": len(pendientes), "diferencia_mil": exceso,
                 "tolerancia_mil": tolerancia, "turnos": sorted(t.id_externo for t in c.turnos),
                 "valor_cent": turnos.valor_cent(exceso, tarifa_)}, g.clave,
                objetivos=tuple(Objetivo("factura_imputacion", i.id, "horas_mil", RELACIONADO)
                                for i in g.imputaciones)))
            continue
        validadas = sum(t.horas_aprobadas_mil for t in c.turnos)
        diferencia = g.horas_mil - validadas
        if abs(diferencia) <= tolerancia:
            salida.append(Resultado(
                regla, "factura", g.factura.id, OK,
                f"{_horas(g.horas_mil)} h facturadas {dias} y {_horas(validadas)} h validadas en "
                "el planning.", clave=g.clave))
            continue
        valores = {"nivel": g.celda.nivel, "desde": g.celda.desde.isoformat(),
                   "hasta": g.celda.hasta.isoformat(), "facturadas_mil": g.horas_mil,
                   "validadas_mil": validadas, "diferencia_mil": diferencia,
                   "tolerancia_mil": tolerancia,
                   "turnos": sorted(t.id_externo for t in c.turnos),
                   "valor_cent": turnos.valor_cent(abs(diferencia), tarifa_)}
        salida.append(Resultado(
            regla, "factura", g.factura.id, FALLO,
            f"{_horas(g.horas_mil)} h facturadas {dias} ({_de_quien(g.celda)}) y "
            f"{_horas(validadas)} h validadas en el planning: "
            f"{_horas(abs(diferencia))} h {'de más' if diferencia > 0 else 'de menos'}, más "
            f"que la tolerancia de {_horas(tolerancia)} h.", valores, g.clave,
            objetivos=tuple(Objetivo("factura_imputacion", i.id, "horas_mil", RELACIONADO)
                            for i in g.imputaciones)))
    return salida


def _tarifa_de(g: turnos.Grupo) -> int:
    """La tarifa con que se valora una diferencia de horas de una celda: la mas alta de sus
    lineas (cero si ninguna la dice)."""
    lineas = {i.linea_id for i in g.imputaciones}
    return max((l.tarifa_e4 or 0 for l in g.factura.lineas if l.id in lineas), default=0)


LEE_COMPARAR = (turnos.LEE_PLANIFICACION | turnos.LEE_GRUPOS | turnos.LEE_CONTENIDO
                | frozenset({"turno.horas_aprobadas_mil", "turno.horas_realizadas_mil",
                             "turno.horas_planificadas_mil", "linea.tarifa_e4"}))
LEE_G2 = LEE_COMPARAR | turnos.LEE_COMPRA


def g2(instantanea: Instantanea) -> list[Resultado]:
    """G2: las horas facturadas contra las validadas, en la celda mas fina de los dos lados."""
    return comparar_horas(instantanea, "G2", ENTRANTE)


def g1(instantanea: Instantanea) -> list[Resultado]:
    """G1: una compra sin ningun turno de su proveedor (ni de sus personas) en lo facturado.

    Con el planning declarado obligatorio (politica.planning_obligatorio)
    bloquea; si no, retiene. Anularlo pide segunda firma (catalogo).

    Obligatorio quiere decir que una compra no pasa sin planning con que
    compararla: sin ningun planning, con el planning pasado de su frescura
    (Z1) o sin cubrir lo facturado, bloquea igual (diciendo por que) en vez de
    dar sin datos, que no retiene nada. Si no, no importar el planning (o
    dejarlo envejecer) bastaria para saltarse el bloqueo.
    """
    obligatorio = instantanea.politica.planning_obligatorio
    if not instantanea.fotos_planning and not obligatorio:
        return turnos.sin_planning(instantanea, "G1") or []
    plan = turnos.Planificacion(instantanea) if instantanea.fotos_planning else None
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if f.sentido != ENTRANTE or f.tipo != turnos.FACTURA or not en_juego(f):
            continue
        if plan is None:
            salida.append(_sin_planning_obligatorio(f, None, None, "sin_planning",
                                                    turnos.SIN_PLANNING))
            continue
        if f.proveedor_id is None:
            salida.append(_sin_datos("G1", f, "La factura no tiene su proveedor resuelto (A0).",
                                     ""))
            continue
        desde, hasta = periodo_de(f)
        if desde is None or hasta is None:
            salida.append(_sin_datos("G1", f, "La factura no dice de qué periodo es (C2).", ""))
            continue
        motivo = plan.sin_datos(desde, hasta)
        if motivo is not None:
            salida.append(
                _sin_planning_obligatorio(f, desde, hasta,
                                          "caducado" if plan.caducado else "sin_cubrir", motivo)
                if obligatorio else _sin_datos("G1", f, motivo, ""))
            continue
        tiene = plan.indice.de(turnos.PROVEEDOR, f.proveedor_id, desde, hasta)
        recursos = {i.recurso_id for i in f.imputaciones if i.recurso_id is not None}
        for recurso in sorted(recursos):
            diarios, semanales = plan.indice.de(turnos.RECURSO, recurso, desde, hasta)
            tiene = (tiene[0] + diarios, tiene[1] + semanales)
        # Un turno de su proveedor y de una de sus personas sale por los dos lados: una vez.
        en_periodo = list({t.id: t for t in tiene[0] + tiene[1]
                           if t.nivel == turnos.SEMANAL or desde <= t.fecha <= hasta}.values())
        if en_periodo:
            salida.append(Resultado("G1", "factura", f.id, OK,
                                    f"El planning tiene {len(en_periodo)} turno(s) de su "
                                    "proveedor en lo facturado."))
            continue
        salida.append(Resultado(
            "G1", "factura", f.id, FALLO,
            f"Ningún turno de su proveedor ni de sus personas en el planning del "
            f"{desde.isoformat()} al {hasta.isoformat()}"
            + (": el planning es obligatorio." if obligatorio else "."),
            {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "obligatorio": obligatorio},
            severidad=B if obligatorio else None))
    return salida


def _sin_planning_obligatorio(f: Factura, desde: date | None, hasta: date | None, causa: str,
                              motivo: str) -> Resultado:
    """G1 con el planning obligatorio y nada con que comparar: bloquea, y dice por que."""
    return Resultado(
        "G1", "factura", f.id, FALLO,
        f"{motivo} El planning es obligatorio: la compra no pasa sin él.",
        {"desde": desde.isoformat() if desde else None,
         "hasta": hasta.isoformat() if hasta else None, "obligatorio": True, "causa": causa},
        severidad=B)


LEE_G1 = (turnos.LEE_PLANIFICACION | LEE_PERIODO | frozenset({
    "instantanea.facturas", "factura.id", "factura.sentido", "factura.tipo", "factura.anulada",
    "factura.fusionada_en_id", "factura.sustituida_por", "factura.proveedor_id",
    "factura.imputaciones", "imputacion.recurso_id", "politica.planning_obligatorio",
    "turno.id"}))


def _objetos_del_planning(plan: turnos.Planificacion, f: Factura, i: Imputacion,
                          desde: date, hasta: date) -> set[int]:
    """Los Objetos en que el planning tiene a la persona de la imputacion (o, sin persona, al
    proveedor o al cliente de la factura) esos dias."""
    filtro = turnos.de_la_parte(f)
    if i.recurso_id is not None:
        dimension, clave = turnos.RECURSO, i.recurso_id
    elif f.sentido == ENTRANTE:
        dimension, clave = turnos.PROVEEDOR, f.proveedor_id
    else:
        dimension, clave = turnos.CLIENTE, f.cliente_id
    diarios, semanales = plan.indice.de(dimension, clave, desde, hasta)
    return {t.objeto_id for t in diarios + semanales
            if t.objeto_id is not None and filtro(t)
            and (t.nivel == turnos.SEMANAL or desde <= t.fecha <= hasta)}


def objeto_propuesto(regla: str, plan: turnos.Planificacion, f: Factura, i: Imputacion,
                     linea: Linea | None, nombres: dict[int, str]) -> Resultado | None:
    """Una imputacion sin Objeto: el que propone el planning (G4 en compras, V2 en ventas).

    Solo es una propuesta: la imputacion no se toca, y una persona la
    confirma con cambiar_objeto. None si no tiene dias o el planning no dice
    nada esos dias.
    """
    dias = turnos.dias_de(i, linea, f)
    clave = f"imputacion:{i.id}"
    if dias is None:
        return None
    motivo = plan.sin_datos(*dias)
    if motivo is not None:
        return _sin_datos(regla, f, motivo, clave)
    objetos = _objetos_del_planning(plan, f, i, *dias)
    if not objetos:
        return _sin_datos(regla, f, "La línea no dice su Objeto y el planning no tiene turnos "
                                    "suyos esos días.", clave)
    texto = ", ".join(nombres.get(o, str(o)) for o in sorted(objetos))
    propuesta = next(iter(objetos)) if len(objetos) == 1 else None
    orden = linea.orden if linea is not None else i.id
    return Resultado(
        regla, "factura", f.id, FALLO,
        (f"La línea {orden} no dice su Objeto; el planning propone {texto} "
         "(una persona lo confirma con cambiar_objeto)." if propuesta is not None else
         f"La línea {orden} no dice su Objeto; el planning tiene esos días turnos en {texto}: "
         "una persona decide con cambiar_objeto."),
        {"propuesta": propuesta, "candidatos": sorted(objetos),
         "desde": dias[0].isoformat(), "hasta": dias[1].isoformat()}, clave,
        objetivos=(Objetivo("factura_imputacion", i.id, "objeto_id", RELACIONADO),))


def g4(instantanea: Instantanea) -> list[Resultado]:
    """G4: el Objeto de cada imputacion de una compra contra el planning.

    Si la persona (o el proveedor) tiene turnos esos dias y ninguno en el
    Objeto de la linea, retiene diciendo donde los tiene. Una linea sin Objeto
    recibe la propuesta del planning (sin tocarla).
    """
    vacio = turnos.sin_planning(instantanea, "G4")
    if vacio is not None:
        return vacio
    plan = turnos.Planificacion(instantanea)
    nombres = {o.id: o.codigo for o in instantanea.objetos}
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if (f.sentido != ENTRANTE or f.tipo != turnos.FACTURA or not f.imputaciones
                or not en_juego(f) or f.proveedor_id is None):
            continue
        lineas = {l.id: l for l in f.lineas}
        for i in f.imputaciones:
            if i.horas_mil is None:
                continue
            linea = lineas.get(i.linea_id) if i.linea_id is not None else None
            if i.objeto_id is None:
                propuesta = objeto_propuesto("G4", plan, f, i, linea, nombres)
                if propuesta is not None:
                    salida.append(propuesta)
                continue
            dias = turnos.dias_de(i, linea, f)
            clave = f"imputacion:{i.id}"
            # Sin datos (nunca nada): un G4 abierto se queda como estaba hasta que se pueda
            # volver a mirar, no se cierra porque el planning envejezca.
            if dias is None:
                salida.append(_sin_datos("G4", f, "La línea no dice de qué días es: no se puede "
                                                  "mirar en el planning.", clave))
                continue
            motivo = plan.sin_datos(*dias)
            if motivo is not None:
                salida.append(_sin_datos("G4", f, motivo, clave))
                continue
            objetos = _objetos_del_planning(plan, f, i, *dias)
            if not objetos or i.objeto_id in objetos:
                salida.append(Resultado("G4", "factura", f.id, OK,
                                        "El Objeto de la línea es el del planning.", clave=clave))
                continue
            texto = ", ".join(nombres.get(o, str(o)) for o in sorted(objetos))
            salida.append(Resultado(
                "G4", "factura", f.id, FALLO,
                f"La línea {linea.orden if linea else i.id} es de "
                f"{nombres.get(i.objeto_id, i.objeto_id)} y el planning tiene esos días sus "
                f"turnos en {texto}.",
                {"objeto": i.objeto_id, "planning": sorted(objetos),
                 "desde": dias[0].isoformat(), "hasta": dias[1].isoformat()}, clave,
                objetivos=(Objetivo("factura_imputacion", i.id, "objeto_id", RELACIONADO),)))
    return salida


LEE_G4 = (turnos.LEE_PLANIFICACION | turnos.LEE_CELDA | frozenset({
    "instantanea.facturas", "instantanea.objetos", "objeto.id", "objeto.codigo", "factura.id",
    "factura.sentido", "factura.tipo", "factura.imputaciones", "factura.anulada",
    "factura.fusionada_en_id", "factura.sustituida_por", "factura.lineas", "linea.id",
    "linea.orden", "imputacion.id", "imputacion.horas_mil", "imputacion.linea_id"})
          | turnos.LEE_COMPRA)
# El Objeto que propone el planning sale de lo resuelto: no es evidencia de G4 (si se
# resuelve otro Objeto, cambia la propuesta y sus valores).
SOLO_TEXTO_G4 = frozenset({"objeto.codigo", "linea.orden"})

# Cuanto se mira alrededor de una celda vacia buscando su trabajo en otra fecha (G5, V3).
VENTANA_FECHA_DIAS = 28


def fechas_contra_planning(instantanea: Instantanea, regla: str,
                           sentido: str) -> list[Resultado]:
    """G5 y V3: el periodo y la semana ISO de lo facturado contra el planning.

    Dos cosas: la semana impresa en una linea no es la de sus fechas; o una
    celda con horas facturadas no tiene ningun turno, y la misma persona u
    Objeto tiene trabajo sin conciliar cerca (cuatro semanas antes o despues):
    es el trabajo de otra fecha facturado con la que no es.
    """
    vacio = turnos.sin_planning(instantanea, regla)
    if vacio is not None:
        return vacio
    plan = turnos.Planificacion(instantanea)
    grupos, _sueltas = turnos.agrupar(instantanea, sentido, plan.indice)
    conciliado = turnos.conciliado(instantanea, sentido)
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if f.sentido != sentido or f.tipo != turnos.FACTURA or not en_juego(f):
            continue
        for l in f.lineas:
            fecha = l.fecha_trabajo or l.fecha_inicio
            if l.semana_doc is None or fecha is None:
                continue
            semana = fecha.isocalendar()[1]
            if semana != l.semana_doc:
                salida.append(Resultado(
                    regla, "factura", f.id, FALLO,
                    f"La línea {l.orden} dice semana {l.semana_doc} y sus fechas son de la "
                    f"semana {turnos.semana_iso(fecha)}.",
                    {"semana_doc": l.semana_doc, "fecha": fecha.isoformat()}, f"semana:{l.id}",
                    objetivos=(Objetivo("factura_linea", l.id, "semana_doc", RELACIONADO),)))
    for g in grupos:
        motivo = plan.sin_datos(g.celda.desde, g.celda.hasta)
        if motivo is not None:
            salida.append(_sin_datos(regla, g.factura, motivo, g.clave))
            continue
        filtro = turnos.de_la_parte(g.factura)
        c = turnos.contenido(g.celda, plan.indice, filtro)
        if c.turnos or g.horas_mil <= 0:
            salida.append(Resultado(regla, "factura", g.factura.id, OK,
                                    "Lo facturado cae en días con turnos en el planning.",
                                    clave=g.clave))
            continue
        cerca = g.celda._replace(desde=g.celda.desde - timedelta(days=VENTANA_FECHA_DIAS),
                                 hasta=g.celda.hasta + timedelta(days=VENTANA_FECHA_DIAS))
        otros = [t for t in turnos.contenido(cerca, plan.indice, filtro).turnos
                 if (t.fecha < g.celda.desde or t.fecha > g.celda.hasta)
                 and conciliado.get(t.id_externo, (0,))[0] < turnos.horas_referencia(t)]
        if not otros:
            salida.append(Resultado(regla, "factura", g.factura.id, OK,
                                    "El planning no tiene ese trabajo en otras fechas.",
                                    clave=g.clave))
            continue
        semanas = sorted({turnos.semana_iso(t.fecha) for t in otros})
        salida.append(Resultado(
            regla, "factura", g.factura.id, FALLO,
            f"{_horas(g.horas_mil)} h facturadas {_dias_texto(g.celda)}, sin turnos en el "
            f"planning esos días; {_de_quien(g.celda)} tiene trabajo sin facturar en "
            f"{', '.join(semanas)}.",
            {"desde": g.celda.desde.isoformat(), "hasta": g.celda.hasta.isoformat(),
             "facturadas_mil": g.horas_mil, "semanas": semanas,
             "turnos": sorted(t.id_externo for t in otros)}, g.clave,
            objetivos=tuple(Objetivo("factura_imputacion", i.id, None, RELACIONADO)
                            for i in g.imputaciones)))
    return salida


LEE_FECHAS = (turnos.LEE_PLANIFICACION | turnos.LEE_GRUPOS | turnos.LEE_CONTENIDO
              | turnos.LEE_CONCILIADO | frozenset({
                  "linea.orden", "turno.horas_planificadas_mil", "turno.horas_realizadas_mil",
                  "turno.horas_aprobadas_mil"}))
LEE_G5 = LEE_FECHAS | turnos.LEE_COMPRA


def g5(instantanea: Instantanea) -> list[Resultado]:
    """G5: el periodo y la semana ISO de una compra contra el planning."""
    return fechas_contra_planning(instantanea, "G5", ENTRANTE)


def cambios_tras_conciliar(instantanea: Instantanea, regla: str,
                           sentido: str) -> list[Resultado]:
    """G7 y V9: el planning que vale ahora no es el de la foto con que se concilio.

    Lo conciliado (conciliacion.py) son los turnos de la celda de cada
    imputacion tal como eran en esa foto. Si la celda de hoy (con el planning
    que vale) tiene otros turnos, otras horas, o alguno se cancelo, el planning
    cambio despues de facturar (regla 9 de arquitectura.md). Solo es un
    problema si lo facturado ya no es lo que dice el planning: de cada turno que
    cambio, las horas de hoy contra las que le cobran las facturas de ese
    sentido (lo conciliado con el, con la tolerancia de la politica por dia).
    Una factura de antes de validar que ya cobraba las horas que despues se
    validaron no necesita ni correccion ni abono.
    """
    vacio = turnos.sin_planning(instantanea, regla)
    if vacio is not None:
        return vacio
    plan = turnos.Planificacion(instantanea)
    de_imputacion: dict[int, list] = defaultdict(list)
    for c in instantanea.conciliaciones:
        de_imputacion[c.imputacion_id].append(c)
    if not de_imputacion:
        return []
    facturado = turnos.conciliado(instantanea, sentido)
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if f.sentido != sentido or not en_juego(f) or not f.imputaciones:
            continue
        lineas = {l.id: l for l in f.lineas}
        for i in f.imputaciones:
            conciliadas = de_imputacion.get(i.id)
            if not conciliadas:
                continue
            clave = f"imputacion:{i.id}"
            linea = lineas.get(i.linea_id) if i.linea_id is not None else None
            celda = turnos.celda_de(i, linea, f, plan.indice, turnos.de_la_parte(f))
            antes = {c.turno.id_externo: turnos.horas_referencia(c.turno) for c in conciliadas}
            if celda is None:
                continue
            motivo = plan.sin_datos(celda.desde, celda.hasta)
            if motivo is not None:
                salida.append(_sin_datos(regla, f, motivo, clave))
                continue
            de_hoy = turnos.contenido(celda, plan.indice, turnos.de_la_parte(f)).turnos
            ahora = {t.id_externo: turnos.horas_referencia(t) for t in de_hoy}
            if ahora == antes:
                salida.append(Resultado(regla, "factura", f.id, OK,
                                        "El planning de lo facturado no ha cambiado.",
                                        clave=clave))
                continue
            dias = {c.turno.id_externo: c.turno.dias for c in conciliadas}
            dias.update((t.id_externo, t.dias) for t in de_hoy)
            cobradas = {k: facturado.get(k, (0,))[0] for k in set(antes) | set(ahora)}
            no_cuadran = {k for k in set(antes) | set(ahora)
                          if antes.get(k) != ahora.get(k)
                          and abs(ahora.get(k, 0) - cobradas[k])
                          > turnos.tolerancia_mil(plan.tolerancia, dias[k])}
            if not no_cuadran:
                salida.append(Resultado(regla, "factura", f.id, OK,
                                        "El planning de lo facturado cambió después de "
                                        "conciliarlo, y lo facturado es lo que dice ahora.",
                                        clave=clave))
                continue
            quitados = sorted(k for k in no_cuadran if k not in ahora)
            nuevos = sorted(k for k in no_cuadran if k not in antes)
            cambiados = sorted(k for k in no_cuadran if k in antes and k in ahora)
            partes = []
            if cambiados:
                partes.append(f"{len(cambiados)} turno(s) con otras horas")
            if quitados:
                partes.append(f"{len(quitados)} que ya no están o se cancelaron")
            if nuevos:
                partes.append(f"{len(nuevos)} nuevo(s)")
            importaciones = sorted({c.turno.importacion_id for c in conciliadas})
            salida.append(Resultado(
                regla, "factura", f.id, FALLO,
                f"El planning de lo facturado en la línea {linea.orden if linea else i.id} "
                f"({_dias_texto(celda)}) cambió después de conciliarlo: {', '.join(partes)} "
                f"({_horas(sum(antes.values()))} h entonces, {_horas(sum(ahora.values()))} h "
                "ahora). Hace falta una corrección o un abono.",
                {"antes": sorted([k, v] for k, v in antes.items()),
                 "ahora": sorted([k, v] for k, v in ahora.items()),
                 "facturadas": sorted([k, cobradas[k]] for k in no_cuadran),
                 "fotos": importaciones}, clave,
                objetivos=(Objetivo("factura_imputacion", i.id, "horas_mil", RELACIONADO),)))
    return salida


LEE_CAMBIOS = (turnos.LEE_PLANIFICACION | turnos.LEE_CELDA | turnos.LEE_CONTENIDO | frozenset({
    "instantanea.facturas", "instantanea.conciliaciones", "conciliacion.imputacion_id",
    "conciliacion.turno", "factura.id", "factura.sentido", "factura.anulada",
    "factura.fusionada_en_id", "factura.sustituida_por", "factura.imputaciones",
    "factura.lineas", "linea.id", "linea.orden",
    "imputacion.id", "imputacion.linea_id", "turno.horas_planificadas_mil",
    "turno.horas_realizadas_mil", "turno.horas_aprobadas_mil", "turno.importacion_id"})
    | turnos.LEE_CONCILIADO)
LEE_G7 = LEE_CAMBIOS | turnos.LEE_COMPRA


def g7(instantanea: Instantanea) -> list[Resultado]:
    """G7: una foto mas nueva del planning cambia las horas ya conciliadas con una compra."""
    return cambios_tras_conciliar(instantanea, "G7", ENTRANTE)


def recargos_contra_planning(instantanea: Instantanea) -> list[Resultado]:
    """La parte del planning de G6: las horas de cada recargo (noche, fin de semana...) de una
    compra contra las de turnos de ese recargo en el planning, en la misma celda.

    Cobrar como noche las horas de un turno que el planning tiene de dia es
    cobrar un recargo que no toca, aunque sea a su tarifa pactada.
    """
    plan = turnos.Planificacion(instantanea)
    grupos, _sueltas = turnos.agrupar(instantanea, ENTRANTE, plan.indice)
    salida: list[Resultado] = []
    for g in grupos:
        por_turno: dict[str, list[Imputacion]] = defaultdict(list)
        for i in g.imputaciones:
            turno = normalizar_turno(i.tipo_turno)
            if turno is not None:
                por_turno[turno].append(i)
        if not por_turno:
            continue
        motivo = plan.sin_datos(g.celda.desde, g.celda.hasta)
        if motivo is not None:
            salida.extend(_sin_datos("G6", g.factura, motivo,
                                     f"recargo:{min(i.id for i in imputaciones)}")
                          for _turno, imputaciones in sorted(por_turno.items()))
            continue
        c = turnos.contenido(g.celda, plan.indice, turnos.de_la_parte(g.factura))
        tolerancia = turnos.tolerancia_mil(plan.tolerancia, c.dias)
        for turno, imputaciones in sorted(por_turno.items()):
            facturadas = sum(i.horas_mil for i in imputaciones)
            planificadas = sum(turnos.horas_referencia(t) for t in c.turnos
                               if t.tipo_turno == turno)
            clave = f"recargo:{min(i.id for i in imputaciones)}"
            lineas = {i.linea_id for i in imputaciones}
            tarifa_ = max((l.tarifa_e4 or 0 for l in g.factura.lineas if l.id in lineas),
                          default=0)
            if facturadas - planificadas <= tolerancia:
                salida.append(Resultado("G6", "factura", g.factura.id, OK,
                                        f"Las horas de {turno} son las del planning.",
                                        clave=clave))
                continue
            salida.append(Resultado(
                "G6", "factura", g.factura.id, FALLO,
                f"{_horas(facturadas)} h cobradas como {turno} {_dias_texto(g.celda)} y el "
                f"planning tiene {_horas(planificadas)} h de turnos de {turno}.",
                {"turno": turno, "facturadas_mil": facturadas,
                 "planificadas_mil": planificadas, "tolerancia_mil": tolerancia,
                 "desde": g.celda.desde.isoformat(), "hasta": g.celda.hasta.isoformat(),
                 "valor_cent": turnos.valor_cent(facturadas - planificadas, tarifa_)},
                clave,
                objetivos=tuple(Objetivo("factura_imputacion", i.id, "tipo_turno", RELACIONADO)
                                for i in imputaciones)))
    return salida


LEE_RECARGOS = (turnos.LEE_PLANIFICACION | turnos.LEE_GRUPOS | turnos.LEE_CONTENIDO
                | frozenset({"imputacion.tipo_turno", "turno.tipo_turno",
                             "turno.horas_planificadas_mil", "turno.horas_realizadas_mil",
                             "turno.horas_aprobadas_mil", "linea.tarifa_e4"})
                | turnos.LEE_COMPRA)


def contra_tarifa_del_turno(instantanea: Instantanea, regla: str, sentido: str,
                            decididas: set[int], *, tambien_por_debajo: bool) -> list[Resultado]:
    """El escalon del planning de G3 y V4: una linea sin tarifa pactada contra la tarifa de los
    turnos de su celda (la de compra en una compra, la de venta en una venta).

    Solo si todos los turnos de su celda con su mismo turno (dia, noche...)
    dicen la misma tarifa: si dicen varias, no se adivina y la linea sigue con
    lo que haya despues (el historico en G3). La linea comparada entra en
    `decididas`.
    """
    plan = turnos.Planificacion(instantanea)
    salida: list[Resultado] = []
    for f in instantanea.facturas:
        if (f.sentido != sentido or f.tipo != turnos.FACTURA or not f.imputaciones
                or not en_juego(f) or turnos._parte(f) is None):
            continue
        lineas = {l.id: l for l in f.lineas}
        filtro = turnos.de_la_parte(f)
        for i in f.imputaciones:
            linea = lineas.get(i.linea_id) if i.linea_id is not None else None
            if linea is None or linea.tarifa_e4 is None or linea.id in decididas:
                continue
            celda = turnos.celda_de(i, linea, f, plan.indice, filtro)
            if celda is None or plan.sin_datos(celda.desde, celda.hasta) is not None:
                continue
            turno = normalizar_turno(i.tipo_turno)
            precios = {(t.tarifa_compra_e4 if sentido == ENTRANTE else t.tarifa_venta_e4)
                       for t in turnos.contenido(celda, plan.indice, filtro).turnos
                       if t.tipo_turno == turno}
            precios.discard(None)
            if len(precios) != 1:
                continue
            decididas.add(linea.id)
            del_turno = precios.pop()
            diferencia = linea.tarifa_e4 - del_turno
            clave = f"turno:{i.id}"
            texto_precio = euros_texto(tarifa(linea.tarifa_e4).quantize(Decimal("0.01")))
            texto_turno = euros_texto(tarifa(del_turno).quantize(Decimal("0.01")))
            if diferencia > 0 or (diferencia < 0 and tambien_por_debajo):
                donde = "por encima" if diferencia > 0 else "por debajo"
                salida.append(Resultado(
                    regla, "factura", f.id, FALLO,
                    f"La línea {linea.orden} cobra {texto_precio}, {donde} de la tarifa del "
                    f"turno en el planning ({texto_turno}); no hay tarifa pactada.",
                    {"imputacion": i.id, "linea": linea.id, "tarifa_e4": linea.tarifa_e4,
                     "turno_e4": del_turno,
                     "valor_cent": valor_de_la_diferencia(diferencia, i, linea)}, clave,
                    objetivos=(Objetivo("factura_linea", linea.id, "tarifa_e4", RELACIONADO),)))
            else:
                salida.append(Resultado(regla, "factura", f.id, OK,
                                        f"La línea {linea.orden} va a la tarifa del turno en "
                                        "el planning.", clave=clave))
    return salida


LEE_TURNO_TARIFA = (turnos.LEE_PLANIFICACION | turnos.LEE_CELDA | turnos.LEE_CONTENIDO
                    | frozenset({"factura.tipo", "imputacion.tipo_turno", "turno.tipo_turno",
                                 "linea.cantidad_mil", "imputacion.horas_mil"}))
LEE_G6 = (LEE_PACTADA_COMPRA | LEE_RECARGOS
          | frozenset({"factura.proveedor_id", "instantanea.fotos_planning"}))
SOLO_TEXTO_G6 = NO_EVIDENCIA_PACTADA & LEE_G6
