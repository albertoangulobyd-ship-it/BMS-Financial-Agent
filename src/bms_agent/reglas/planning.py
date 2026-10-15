"""Reglas contra el planning. En esta fase solo G3 en su version de historico.

Sin el programa de planificacion ni las tarifas pactadas (pasos 9 y 10) no
se puede comprobar una tarifa contra la de su asignacion, pero si se puede
ver que la misma contraparte cobra dos tarifas distintas por el mismo
trabajo en el mismo Objeto, en facturas distintas. Es la ultima fuente del
orden que fija el §7 (pactada, luego la del turno, luego el historico) y la
unica disponible hoy. Retiene; el bloqueo por exceso es de la tarifa pactada.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal

from .base import (
    ENTRANTE,
    FALLO,
    NO_APLICA,
    OK,
    RELACIONADO,
    SIN_DATOS,
    Instantanea,
    Objetivo,
    Resultado,
    euros_texto,
    fuera_de_juego,
    lineas_en_orden,
    tarifa,
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


def g3(instantanea: Instantanea) -> Iterator[Resultado]:
    """G3 de historico, sobre las facturas de compra en euros.

    El grupo es la contraparte, el Objeto (el resuelto o, si no, el nombre
    impreso), el tipo de trabajo y la unidad: una tarifa por hora y otra por
    pieza no se comparan. Cada factura tiene un resultado por grupo en el que
    cobra algo; el hallazgo es del grupo y cubre las facturas desviadas.
    """
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
        if factura.parte is None:
            yield Resultado("G3", "factura", factura.id, SIN_DATOS,
                            "El documento no dice de quién es: no hay historico con que comparar.")
            continue
        fecha = factura.fecha_factura.isoformat() if factura.fecha_factura else "0000-00-00"
        for linea in lineas_en_orden(factura):
            precio = tarifa(linea.tarifa_e4)
            if precio is None:
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

    def hallazgo(grupo: tuple, clave: str, cambio: CambioDeTarifa) -> tuple:
        """Lo que comparten todas las facturas desviadas de un grupo, calculado una vez."""
        if grupo not in hallazgo_de:
            parte, obra, trabajo, unidad = grupo
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
            valores = {"grupo": clave, "anterior_e4": int(cambio.anterior.scaleb(4)),
                       "posteriores_e4": [int(t.scaleb(4)) for t in cambio.posteriores],
                       "desviadas": desviadas}
            hallazgo_de[grupo] = (detalle, valores, objetivos)
        return hallazgo_de[grupo]

    for factura_id in sorted(grupos_de):
        for grupo in sorted(grupos_de[factura_id]):
            parte, obra, trabajo, unidad = grupo
            clave = f"{parte}|{obra}|{trabajo}|{unidad}"
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

LEE_G3 = frozenset({
    "instantanea.facturas", "factura.id", "factura.anulada", "factura.fusionada_en_id",
    "factura.sentido", "factura.parte", "factura.parte_nombre", "factura.fecha_factura",
    "factura.lineas", "linea.id", "linea.orden", "linea.tarifa_e4", "linea.objeto",
    "linea.objeto_doc", "linea.descripcion_doc", "linea.unidad",
})
