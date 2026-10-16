"""Reglas de aritmetica: D1 (desglose presente), D2, D2b, D4 e I1 (las imputaciones de
cada linea suman la linea; revision final).

Son baratas y atrapan mas errores de los que parece, sobre todo en
facturas hechas a mano. Las tolerancias son las de la politica (un centimo
por linea y dos por factura). Los identificadores son los del codigo: D2 es
la suma de las lineas contra la base y D2b la cantidad por la tarifa de cada
linea (el catalogo antiguo los llamaba al reves).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from .base import (
    FALLO,
    NO_APLICA,
    OK,
    RELACIONADO,
    SIN_DATOS,
    Comprobacion,
    Factura,
    Objetivo,
    Politica,
    Resultado,
    cantidad,
    euros,
    euros_texto,
    lineas_en_orden,
    resultado_de,
    tarifa,
)

CENTIMO = Decimal("0.01")

# --------------------------------------------------------------- D2


def suma_lineas(base: Decimal | None, importes: Sequence[Decimal | None],
                politica: Politica) -> Comprobacion:
    """D2: la suma de las lineas cuadra con la base, con un centimo por linea y dos mas."""
    if base is None:
        return Comprobacion(SIN_DATOS, "No hay base imponible legible.")
    if not importes:
        return Comprobacion(SIN_DATOS, "La factura no tiene líneas.")
    if any(importe is None for importe in importes):
        return Comprobacion(SIN_DATOS, "Alguna línea no tiene importe legible.")
    total = sum(importes, Decimal(0))
    tolerancia = politica.tolerancia_linea * len(importes) + politica.tolerancia_factura
    if abs(total - base) <= tolerancia:
        return Comprobacion(OK, f"{euros_texto(total)} = base imponible.")
    return Comprobacion(
        FALLO, f"Las líneas suman {euros_texto(total)} y la base dice {euros_texto(base)}.")


def d2(factura: Factura, politica: Politica) -> list[Resultado]:
    lineas = lineas_en_orden(factura)
    comprobacion = suma_lineas(euros(factura.base_cent), [euros(l.importe_cent) for l in lineas],
                               politica)
    objetivos = ()
    if comprobacion.resultado == FALLO:
        objetivos = (Objetivo("factura", factura.id, "base_cent"),) + tuple(
            Objetivo("factura_linea", l.id, "importe_cent", RELACIONADO) for l in lineas)
    return [resultado_de("D2", factura, comprobacion, objetivos=objetivos, valores={
        "base_cent": factura.base_cent, "lineas_cent": [l.importe_cent for l in lineas]})]


LEE_D2 = frozenset({
    "factura.base_cent", "factura.lineas", "linea.id", "linea.orden", "linea.importe_cent",
    "politica.tolerancia_linea", "politica.tolerancia_factura",
})

# --------------------------------------------------------------- D2b


def aritmetica_lineas(
    lineas: Sequence[tuple[Any, Decimal | None, Decimal | None, Decimal | None]],
    politica: Politica,
) -> tuple[Comprobacion, list[Any]]:
    """D2b: cantidad por tarifa da el importe de cada linea, con un centimo.

    Cada linea es (etiqueta, cantidad, tarifa, importe). Una linea sin los
    tres valores no se evalua; si no se evalua ninguna, es sin_datos.
    Devuelve tambien las etiquetas de las lineas que fallan.
    """
    if not lineas:
        return Comprobacion(SIN_DATOS, "La factura no tiene lineas."), []
    fallos: list[str] = []
    fallidas: list[Any] = []
    evaluadas = 0
    for etiqueta, unidades, precio, importe in lineas:
        if unidades is None or precio is None or importe is None:
            continue
        evaluadas += 1
        esperado = (unidades * precio).quantize(CENTIMO)
        if abs(esperado - importe) > politica.tolerancia_linea:
            fallidas.append(etiqueta)
            fallos.append(
                f"linea {etiqueta}: {unidades} x {euros_texto(precio)} deberia dar "
                f"{euros_texto(esperado)} y pone {euros_texto(importe)}")
    if not evaluadas:
        return Comprobacion(
            SIN_DATOS, "Ninguna linea trae cantidad, tarifa e importe a la vez."), []
    if fallos:
        return Comprobacion(FALLO, "; ".join(fallos)), fallidas
    return Comprobacion(OK, f"Las {evaluadas} lineas con datos completos cuadran."), []


def d2b(factura: Factura, politica: Politica) -> list[Resultado]:
    lineas = lineas_en_orden(factura)
    comprobacion, fallidas = aritmetica_lineas(
        [(l.orden, cantidad(l.cantidad_mil), tarifa(l.tarifa_e4), euros(l.importe_cent))
         for l in lineas], politica)
    por_orden = {l.orden: l for l in lineas}
    objetivos = tuple(Objetivo("factura_linea", por_orden[o].id, "importe_cent")
                      for o in fallidas)
    return [resultado_de("D2b", factura, comprobacion, objetivos=objetivos, valores={
        "lineas": [[l.orden, l.cantidad_mil, l.tarifa_e4, l.importe_cent] for l in lineas],
      })]


LEE_D2B = frozenset({
    "factura.lineas", "linea.id", "linea.orden", "linea.cantidad_mil", "linea.tarifa_e4",
    "linea.importe_cent", "politica.tolerancia_linea",
})

# --------------------------------------------------------------- D4


def total(base: Decimal | None, cuota: Decimal | None, importe_total: Decimal | None,
          politica: Politica) -> Comprobacion:
    """D4: base mas cuota da el total, con dos centimos."""
    if base is None or cuota is None or importe_total is None:
        return Comprobacion(SIN_DATOS, "Falta la base, la cuota o el total.")
    esperado = base + cuota
    if abs(esperado - importe_total) <= politica.tolerancia_factura:
        return Comprobacion(
            OK, f"{euros_texto(base)} + {euros_texto(cuota)} = {euros_texto(importe_total)}.")
    return Comprobacion(
        FALLO, f"Base y cuota suman {euros_texto(esperado)} y el total dice "
        f"{euros_texto(importe_total)}.")


def d4(factura: Factura, politica: Politica) -> list[Resultado]:
    comprobacion = total(euros(factura.base_cent), euros(factura.iva_cent),
                         euros(factura.total_cent), politica)
    objetivos = ()
    if comprobacion.resultado == FALLO:
        objetivos = tuple(Objetivo("factura", factura.id, c)
                          for c in ("total_cent", "base_cent", "iva_cent"))
    return [resultado_de("D4", factura, comprobacion, objetivos=objetivos, valores={
        "base_cent": factura.base_cent, "iva_cent": factura.iva_cent,
        "total_cent": factura.total_cent})]


LEE_D4 = frozenset({
    "factura.base_cent", "factura.iva_cent", "factura.total_cent",
    "politica.tolerancia_factura",
})

# --------------------------------------------------------------- I1


def i1(factura: Factura, politica: Politica) -> list[Resultado]:
    """I1: las imputaciones activas de cada linea suman el importe de la linea.

    Dividir una linea entre Objetos ya lo exige (servicios._dividir_linea),
    pero una correccion posterior del importe de la linea deja las partes como
    estaban: los costes del Objeto quedarian contando la linea de antes, y lo
    que falta caeria sin aviso en "sin imputar". Una imputacion sin dividir
    sigue a su linea (campos, calculo de copia) y no da nada aqui. Un centimo
    de tolerancia por linea, como D2b.
    """
    de_linea: dict[int, list[Any]] = {}
    for imputacion in factura.imputaciones:
        if imputacion.linea_id is not None:
            de_linea.setdefault(imputacion.linea_id, []).append(imputacion)
    lineas = [l for l in lineas_en_orden(factura) if l.id in de_linea]
    if not lineas:
        return [resultado_de("I1", factura, Comprobacion(
            NO_APLICA, "Ninguna línea tiene imputaciones."))]
    fallos, objetivos, evaluadas = [], [], 0
    valores: dict[str, Any] = {}
    for l in lineas:
        partes = [i.importe_cent for i in sorted(de_linea[l.id], key=lambda i: i.id)]
        valores[str(l.id)] = [l.importe_cent, partes]
        if l.importe_cent is None or any(p is None for p in partes):
            continue
        evaluadas += 1
        suma = sum(partes)
        if abs(euros(suma) - euros(l.importe_cent)) > politica.tolerancia_linea:
            fallos.append(f"la línea {l.orden} es de {euros_texto(euros(l.importe_cent))} y sus "
                          f"{len(partes)} imputaciones suman {euros_texto(euros(suma))}")
            objetivos.append(Objetivo("factura_linea", l.id, "importe_cent"))
            objetivos.extend(Objetivo("factura_imputacion", i.id, "importe_cent", RELACIONADO)
                             for i in sorted(de_linea[l.id], key=lambda i: i.id))
    if fallos:
        return [resultado_de("I1", factura, Comprobacion(
            FALLO, "Las imputaciones no cubren la línea: " + "; ".join(fallos)
                   + ". Vuelve a dividirla."), valores={"lineas": valores},
                             objetivos=tuple(objetivos))]
    if not evaluadas:
        return [resultado_de("I1", factura, Comprobacion(
            SIN_DATOS, "Las líneas imputadas no tienen importe."), valores={"lineas": valores})]
    return [resultado_de("I1", factura, Comprobacion(
        OK, f"Las imputaciones de las {evaluadas} líneas suman su importe."),
                         valores={"lineas": valores})]


LEE_I1 = frozenset({
    "factura.imputaciones", "factura.lineas", "imputacion.linea_id", "imputacion.id",
    "imputacion.importe_cent", "linea.id", "linea.orden", "linea.importe_cent",
    "politica.tolerancia_linea",
})

# --------------------------------------------------------------- D1

_SIN_CUOTA = frozenset({"autoliquidacion", "kor", "exento"})


def _hay(valor: object, columna: str, ilegibles: frozenset[str]) -> bool:
    return valor is not None or columna in ilegibles


def d1(factura: Factura, _politica: Politica) -> list[Resultado]:
    """D1: el desglose esta en el documento (validacion-facturas.md, grupo D).

    Lineas con cantidad, tarifa e importe; base, total y, cuando se repercute
    IVA, el tipo y la cuota. Un literal que no se pudo leer cuenta como
    presente: esta en el papel, y leerlo mal es otra cosa (Q2). Con IVA
    trasladado, KOR o exencion no se pide tipo; la cuota solo si se
    repercute.
    """
    faltan: list[str] = []
    objetivos: list[Objetivo] = []
    lineas = lineas_en_orden(factura)
    if not lineas:
        faltan.append("líneas")
    for linea in lineas:
        for columna, nombre in (("cantidad_mil", "cantidad"), ("tarifa_e4", "tarifa"),
                                ("importe_cent", "importe")):
            if not _hay(getattr(linea, columna), columna, linea.ilegibles):
                faltan.append(f"{nombre} de la línea {linea.orden}")
                objetivos.append(Objetivo("factura_linea", linea.id, columna))
    for columna, nombre in (("base_cent", "base imponible"), ("total_cent", "total")):
        if not _hay(getattr(factura, columna), columna, factura.ilegibles):
            faltan.append(nombre)
            objetivos.append(Objetivo("factura", factura.id, columna))
    if factura.tratamiento_iva not in _SIN_CUOTA:
        if not _hay(factura.iva_cent, "iva_cent", factura.ilegibles):
            faltan.append("importe de IVA")
            objetivos.append(Objetivo("factura", factura.id, "iva_cent"))
        con_tipo = (_hay(factura.tipo_iva_pb, "tipo_iva_pb", factura.ilegibles)
                    or bool(factura.desglose)
                    or (bool(lineas) and all(_hay(l.tipo_iva_pb, "tipo_iva_pb", l.ilegibles)
                                             for l in lineas)))
        if not con_tipo and factura.iva_cent != 0:
            faltan.append("tipo de IVA")
            objetivos.append(Objetivo("factura", factura.id, "tipo_iva_pb"))
    if faltan:
        comprobacion = Comprobacion(FALLO, "Falta en el desglose: " + ", ".join(faltan) + ".")
    else:
        comprobacion = Comprobacion(OK, "El desglose está completo.")
    return [resultado_de("D1", factura, comprobacion, valores={"faltan": faltan},
                         objetivos=tuple(objetivos))]


LEE_D1 = frozenset({
    "factura.lineas", "factura.base_cent", "factura.total_cent", "factura.iva_cent",
    "factura.tipo_iva_pb", "factura.tratamiento_iva", "factura.desglose", "factura.ilegibles",
    "linea.id", "linea.orden", "linea.cantidad_mil", "linea.tarifa_e4", "linea.importe_cent",
    "linea.tipo_iva_pb", "linea.ilegibles",
})
