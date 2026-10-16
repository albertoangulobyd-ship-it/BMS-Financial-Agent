"""Reglas de fechas. Desde el paso 11, C4: lo que cae en un trimestre del BTW ya presentado.

Una factura que llega tarde y cae en un trimestre que ya se presento no es un
error, pero el contable tiene que verla (validacion-facturas.md §3.C): su IVA
no esta en lo que se presento. Lo mismo una que ya estaba y cambio despues
(otra base, otro tratamiento, anulada, sustituida, otra fecha que la saca del
trimestre): lo presentado ya no es lo que dicen los datos.

C4 compara cada trimestre presentado con lo que se declaro de cada factura en
el momento de presentarlo (periodo_btw_declarada: la huella de su IVA,
reglas/iva.huella_iva). Una factura cuenta en el trimestre de su fecha de
factura (factuurstelsel, config/btw.yaml), no en el de su periodo de
servicio: una factura de octubre por trabajo de septiembre se declara en el
cuarto trimestre, y marcarla por su periodo marcaria casi todas las de las
primeras semanas tras cada presentacion.
"""

from __future__ import annotations

from .base import (
    FALLO,
    Factura,
    Instantanea,
    Objetivo,
    PeriodoBtw,
    Resultado,
    en_juego,
)
from .iva import LEE_HUELLA_IVA, huella_de_factura

_NOMBRE_MOTIVO = {
    "tarde": "llegó después de presentar el trimestre: su IVA no está en lo presentado",
    "cambio": "cambió después de presentar el trimestre: lo presentado ya no es lo que dice",
    "fuera": "se presentó en el trimestre y ya no cuenta en él (anulada, sustituida, en otra "
             "moneda o con otra fecha)",
}


def _trimestre(factura: Factura) -> tuple[int, int] | None:
    """El trimestre en que cuenta una factura, o None si no cuenta en ninguno."""
    if (not en_juego(factura) or factura.moneda is not None
            or factura.fecha_factura is None):
        return None
    return factura.fecha_factura.year, (factura.fecha_factura.month - 1) // 3 + 1


def c4(instantanea: Instantanea) -> list[Resultado]:
    """C4: una factura que no es en un trimestre presentado lo que se declaro de ella.

    Un resultado por factura y trimestre (clave "2026-T3"), solo cuando
    objeta: llego tarde (no se declaro), cambio (su huella ya no es la
    declarada) o ya no cuenta alli (se declaro y ahora esta anulada,
    sustituida, en otra moneda o con una fecha de otro trimestre). Sin ningun
    trimestre presentado no dice nada.
    """
    if not instantanea.periodos_btw:
        return []
    presentados: dict[tuple[int, int], PeriodoBtw] = {
        (p.ano, p.trimestre): p for p in instantanea.periodos_btw}
    declaradas = {clave: dict(p.declaradas) for clave, p in presentados.items()}
    salida: list[Resultado] = []
    for factura in instantanea.facturas:
        trimestre = _trimestre(factura)
        ahora = None
        for clave, periodo in sorted(presentados.items()):
            antes = declaradas[clave].get(factura.id)
            if clave == trimestre:
                ahora = ahora or huella_de_factura(factura)
                motivo = ("tarde" if antes is None else "cambio" if antes != ahora else None)
            else:
                motivo = "fuera" if antes is not None else None
            if motivo is None:
                continue
            etiqueta = f"{periodo.ano}-T{periodo.trimestre}"
            salida.append(Resultado(
                "C4", "factura", factura.id, FALLO,
                f"La factura {_NOMBRE_MOTIVO[motivo]} {etiqueta} (presentado el "
                f"{periodo.presentado_en.isoformat()}). Va a la lista del trimestre para el "
                "contable.",
                {"trimestre": etiqueta, "motivo": motivo, "declarada": antes,
                 "ahora": ahora if clave == trimestre else None},
                etiqueta, None, None, (Objetivo("factura", factura.id, "fecha_factura"),)))
    return salida


# El dia de la presentacion solo va en el texto: no es evidencia de la factura.
SOLO_TEXTO_C4 = frozenset({"periodo_btw.presentado_en"})
LEE_C4 = LEE_HUELLA_IVA | frozenset({
    "instantanea.facturas", "instantanea.periodos_btw", "periodo_btw.ano",
    "periodo_btw.trimestre", "periodo_btw.declaradas",
    "factura.id", "factura.anulada", "factura.fusionada_en_id", "factura.sustituida_por",
    "factura.moneda", "factura.fecha_factura",
})
