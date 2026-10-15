"""Reglas contra el planning y las tarifas pactadas: G3 y G6 (y V4, en venta.py).

G3 compara la tarifa de cada linea de compra con la que le toca, en el orden
del §7: la pactada (tarifa_acordada, de lo mas concreto a lo general, ver
tarifas.py), si no la del turno en el planning (paso 10: hoy no hay planning,
asi que se salta) y si no el historico: que la misma contraparte cobre dos
tarifas distintas por el mismo trabajo en el mismo Objeto, en facturas
distintas. Contra la pactada retiene si la linea cobra mas, y bloquea si la
pasa en mas del porcentaje de la politica (anularlo pide segunda firma); contra
el historico solo retiene. Cobrar menos de lo pactado no es un problema de una
compra.

Una linea de un recargo (noche, fin de semana, festivo: un turno que no es el
de dia) con su propia tarifa pactada la mira G6: un recargo se cobra a su
propia tarifa. Sin tarifa propia, sigue con el historico de G3, como antes.

Si para una linea hay dos tarifas igual de concretas con precios distintos, no
se adivina: la comparacion da sin datos y la factura queda retenida con su
excepcion ("ambigua"), para que alguien arregle el maestro.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .base import (
    B,
    ENTRANTE,
    FALLO,
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
    en_juego,
    euros_texto,
    fuera_de_juego,
    lineas_en_orden,
    tarifa,
)
from .tarifas import (
    AMBIGUA,
    LEE_TARIFA_COMPRA,
    LEE_TARIFA_VENTA,
    NINGUNA,
    Pactada,
    normalizar_turno,
    pactada,
    por_sentido,
)


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


def comparar_con_pactadas(instantanea: Instantanea, regla: str, sentido: str, *,
                          recargos: bool | None, tambien_por_debajo: bool,
                          exceso_bloqueo_pct: int | None, sin_pactada: str | None,
                          decididas: set[int] | None = None) -> list[Resultado]:
    """Las comparaciones de una regla contra la tarifa pactada, y la retencion de las ambiguas.

    `recargos`: True, solo las lineas de un recargo; False, solo las demas; None,
    todas. `sin_pactada`: el resultado (no_aplica o sin_datos) de una linea sin
    tarifa pactada, o None para no dar ninguno (G3 la deja al historico).
    `decididas` recoge las lineas que tenian tarifa pactada (unica o ambigua).
    """
    salida: list[Resultado] = []
    ambigua: dict[int, tuple[Factura, list[int], set[int]]] = {}
    for factura, i, linea, turno, p in con_pactada(instantanea, sentido):
        if recargos is not None and (turno is not None) != recargos:
            if decididas is not None and p.estado != NINGUNA:
                decididas.add(linea.id)
            continue
        if p.estado == NINGUNA:
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
    return salida


_SIN_PACTADA = {
    "G6": "El recargo no tiene tarifa pactada propia: G3 lo compara con el histórico.",
    "V4": "Sin tarifa de venta pactada para la línea: la del turno en el planning llega en el "
          "paso 10.",
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
    """G6: un recargo se cobra a su propia tarifa pactada (las compras).

    Solo las lineas de un turno que no es el de dia. Sin tarifa propia no
    aplica: la compara G3 con el historico.
    """
    return comparar_con_pactadas(instantanea, "G6", ENTRANTE, recargos=True,
                                 tambien_por_debajo=False, exceso_bloqueo_pct=None,
                                 sin_pactada=NO_APLICA)


LEE_G6 = LEE_PACTADA_COMPRA | frozenset({"factura.proveedor_id"})
SOLO_TEXTO_G6 = NO_EVIDENCIA_PACTADA & LEE_G6


def g3(instantanea: Instantanea) -> Iterator[Resultado]:
    """G3 sobre las facturas de compra en euros: contra la pactada y, si no hay, el historico.

    Contra la pactada, un resultado por imputacion de una linea que no es un
    recargo (clave pactada:<imputacion>). En el historico, el grupo es la
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
                                     sin_pactada=None, decididas=decididas)
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
    "instantanea.politica", "politica.tarifa_exceso_bloqueo_pct",
})
