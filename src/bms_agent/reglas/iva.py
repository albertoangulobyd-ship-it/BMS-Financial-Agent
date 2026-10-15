"""Reglas de IVA de esta fase: D3 (la cuota por el tipo), E3 (KOR) y E4 (IVA trasladado).

Con IVA trasladado o con KOR no hay tipo que aplicar, y eso no es un dato
que falte: es el estado correcto de la factura (D3 no aplica). Pero si en
ese regimen aparece una cuota distinta de cero, eso si es una regla
incumplida, y no la misma: E3 con la KOR, E4 con el IVA trasladado.

Pendiente de confirmar con el contador (validacion-facturas.md): todo el
grupo E toca obligaciones fiscales.
"""

from __future__ import annotations

from decimal import Decimal

from .base import (
    FALLO,
    NO_APLICA,
    OK,
    SIN_DATOS,
    Comprobacion,
    Factura,
    Objetivo,
    Politica,
    Resultado,
    euros,
    euros_texto,
    porcentaje,
    resultado_de,
)

CENTIMO = Decimal("0.01")

# Como se nombra en un texto el regimen que no repercute IVA.
ETIQUETA_REGIMEN = {"autoliquidacion": "IVA trasladado", "kor": "KOR", "exento": "exención"}

# --------------------------------------------------------------- D3


def cuota_por_tipo(base: Decimal | None, cuota: Decimal | None, tipo: Decimal | None,
                   politica: Politica) -> Comprobacion:
    """D3: base por tipo da la cuota, con dos centimos."""
    if base is None or cuota is None or tipo is None:
        return Comprobacion(SIN_DATOS, "Falta la base, el tipo o la cuota.")
    esperado = (base * tipo / Decimal(100)).quantize(CENTIMO)
    if abs(esperado - cuota) <= politica.tolerancia_factura:
        return Comprobacion(OK, f"{euros_texto(base)} al {tipo}% = {euros_texto(cuota)}.")
    return Comprobacion(
        FALLO, f"Al {tipo}% deberían ser {euros_texto(esperado)} y la factura dice "
        f"{euros_texto(cuota)}.")


def sin_iva_por_regimen(etiqueta: str) -> Comprobacion:
    return Comprobacion(NO_APLICA, f"Sin IVA repercutido por el régimen declarado ({etiqueta}).")


def d3(factura: Factura, politica: Politica) -> list[Resultado]:
    """D3 por tipo: con desglose (v2), cada tipo; sin el (v1), el tipo de la cabecera."""
    if factura.tratamiento_iva in ETIQUETA_REGIMEN:
        return [resultado_de("D3", factura,
                             sin_iva_por_regimen(ETIQUETA_REGIMEN[factura.tratamiento_iva]),
                             valores={"tratamiento_iva": factura.tratamiento_iva})]
    if not factura.desglose:
        comprobacion = cuota_por_tipo(euros(factura.base_cent), euros(factura.iva_cent),
                                      porcentaje(factura.tipo_iva_pb), politica)
        objetivos = ()
        if comprobacion.resultado == FALLO:
            objetivos = tuple(Objetivo("factura", factura.id, c)
                              for c in ("iva_cent", "base_cent", "tipo_iva_pb"))
        return [resultado_de("D3", factura, comprobacion, objetivos=objetivos, valores={
            "base_cent": factura.base_cent, "iva_cent": factura.iva_cent,
            "tipo_iva_pb": factura.tipo_iva_pb})]
    tramos = sorted(factura.desglose, key=lambda t: (t.tipo_iva_pb is None, t.tipo_iva_pb, t.id))
    comprobaciones = [(t, cuota_por_tipo(euros(t.base_cent), euros(t.cuota_cent),
                                         porcentaje(t.tipo_iva_pb), politica)) for t in tramos]
    fallos = [c for _t, c in comprobaciones if c.resultado == FALLO]
    valores = {"tramos": [[t.tipo_iva_pb, t.base_cent, t.cuota_cent] for t in tramos]}
    if fallos:
        detalle = " ".join(c.detalle for c in fallos)
        return [resultado_de("D3", factura, Comprobacion(FALLO, detalle),
                             valores=valores, objetivos=tuple(
                                 Objetivo("factura_iva", t.id, "cuota_cent")
                                 for t, c in comprobaciones if c.resultado == FALLO))]
    if any(c.resultado == SIN_DATOS for _t, c in comprobaciones):
        return [resultado_de("D3", factura, Comprobacion(
            SIN_DATOS, "Algún tipo del desglose no trae base, tipo o cuota."), valores=valores)]
    return [resultado_de("D3", factura, Comprobacion(
        OK, f"Los {len(tramos)} tipos del desglose cuadran."), valores=valores)]


LEE_D3 = frozenset({
    "factura.tratamiento_iva", "factura.base_cent", "factura.iva_cent", "factura.tipo_iva_pb",
    "factura.desglose", "tramo_iva.id", "tramo_iva.tipo_iva_pb", "tramo_iva.base_cent",
    "tramo_iva.cuota_cent", "politica.tolerancia_factura",
})

# --------------------------------------------------------------- E3 y E4


def iva_indebido(etiqueta: str, cuota: Decimal) -> Comprobacion:
    """E3/E4: con un regimen que no repercute IVA, la cuota tiene que ser cero."""
    if cuota != 0:
        return Comprobacion(
            FALLO, f"Con {etiqueta} no debería repercutirse IVA y la factura cobra "
            f"{euros_texto(cuota)}.")
    return Comprobacion(OK, f"Con {etiqueta}, sin IVA repercutido.")


def _cuota_cobrada(factura: Factura) -> int | None:
    """La cuota impresa; si no la imprime, lo que el total pasa de la base."""
    if factura.iva_cent is not None:
        return factura.iva_cent
    if factura.base_cent is not None and factura.total_cent is not None:
        return factura.total_cent - factura.base_cent
    return None


def _cuota_en_regimen(regla_id: str, factura: Factura, **opciones) -> Resultado:
    cobrada = _cuota_cobrada(factura)
    etiqueta = ETIQUETA_REGIMEN[factura.tratamiento_iva]
    valores = {"tratamiento_iva": factura.tratamiento_iva, "iva_cent": factura.iva_cent,
               "base_cent": factura.base_cent, "total_cent": factura.total_cent}
    if cobrada is None:
        return resultado_de(regla_id, factura, Comprobacion(
            SIN_DATOS, "No se ve la cuota ni se puede deducir del total."),
            valores=valores, **opciones)
    comprobacion = iva_indebido(etiqueta, euros(cobrada))
    objetivos = ((Objetivo("factura", factura.id, "iva_cent"),)
                 if comprobacion.resultado == FALLO else ())
    return resultado_de(regla_id, factura, comprobacion, valores=valores, objetivos=objetivos,
                        **opciones)


def e3(factura: Factura, _politica: Politica) -> list[Resultado]:
    """E3: con KOR, la factura no repercute IVA."""
    if factura.tratamiento_iva != "kor":
        return [resultado_de("E3", factura, Comprobacion(NO_APLICA, "La factura no declara KOR."))]
    return [_cuota_en_regimen("E3", factura)]


def e4(factura: Factura, _politica: Politica) -> list[Resultado]:
    """E4: con IVA trasladado, sin cuota y con el btw-id del receptor.

    Son dos condiciones y van como dos resultados (clave "cuota" y
    "btw_receptor"): una factura v1 no pidio el btw-id del receptor, y eso no
    puede tapar que la cuota si se comprobo. Que el btw-id sea el de BM
    Support BV es A8 (paso 5, con config/empresa.yaml).
    """
    if factura.tratamiento_iva != "autoliquidacion":
        return [resultado_de("E4", factura, Comprobacion(
            NO_APLICA, "La factura no declara IVA trasladado."))]
    cuota = _cuota_en_regimen("E4", factura, clave="cuota")
    valores = {"receptor_btw_doc": factura.receptor_btw_doc}
    if factura.receptor_btw_doc or "receptor_btw_doc" in factura.ilegibles:
        btw = resultado_de("E4", factura, Comprobacion(
            OK, "Lleva el btw-id del receptor."), clave="btw_receptor", valores=valores)
    elif "receptor_btw_doc" in factura.no_solicitados:
        btw = resultado_de("E4", factura, Comprobacion(
            SIN_DATOS, "La versión del esquema no pidió el btw-id del receptor."),
            clave="btw_receptor", valores=valores)
    else:
        btw = resultado_de("E4", factura, Comprobacion(
            FALLO, "Con IVA trasladado la factura tiene que llevar el btw-id del receptor, y "
            "no lo lleva."), clave="btw_receptor", valores=valores,
            objetivos=(Objetivo("factura", factura.id, "receptor_btw_doc"),))
    return [cuota, btw]


LEE_E3 = frozenset({
    "factura.tratamiento_iva", "factura.iva_cent", "factura.base_cent", "factura.total_cent",
})
LEE_E4 = LEE_E3 | frozenset({
    "factura.receptor_btw_doc", "factura.ilegibles", "factura.no_solicitados",
})
