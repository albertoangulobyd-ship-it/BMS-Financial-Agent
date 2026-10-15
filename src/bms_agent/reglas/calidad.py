"""Reglas de datos: Q1 (lo obligatorio esta) y X1 (la factura esta en euros).

Faltar no es lo mismo que no poderse leer. Q1 mira si el documento trae el
campo: un literal impreso que no se pudo leer esta en el papel (eso es Q2,
lectura dudosa, del paso 5), y un campo que la version del esquema no le
pidio al modelo no dice nada del documento: deja Q1 en sin_datos, no en
fallo. Asi el historico v1 no se llena de faltas que no son.
"""

from __future__ import annotations

from collections.abc import Sequence

from .base import (
    B,
    FALLO,
    LEE_PERIODO,
    OK,
    R,
    SALIENTE,
    SIN_DATOS,
    Comprobacion,
    Factura,
    Objetivo,
    Politica,
    Resultado,
    periodo_de,
    resultado_de,
)

# --------------------------------------------------------------- Q1


def campos_que_faltan(presentes: Sequence[tuple[str, bool]]) -> Comprobacion:
    """Los campos que no estan, en el orden en que se piden."""
    faltan = [etiqueta for etiqueta, esta in presentes if not esta]
    if not faltan:
        return Comprobacion(OK, "Están todos.")
    return Comprobacion(FALLO, "Falta " + ", ".join(faltan) + ".")


_REGIMEN_CONOCIDO = frozenset({"estandar", "autoliquidacion", "kor", "exento", "tipo_cero"})

# (clave, etiqueta, bloquea, columnas que se marcan en la consola)
_OBLIGATORIOS_Q1: tuple[tuple[str, str, bool, tuple[str, ...]], ...] = (
    ("numero", "número", True, ("numero",)),
    ("contraparte", "contraparte", True, ()),
    ("fecha", "fecha de factura", False, ("fecha_factura",)),
    ("periodo", "periodo de prestación", False, ("periodo_inicio", "periodo_fin")),
    ("base", "base imponible", False, ("base_cent",)),
    ("iva", "IVA o régimen", False, ("iva_cent", "tratamiento_iva")),
    ("total", "total", True, ("total_cent",)),
)


def _impreso(factura: Factura, columna: str, valor: object) -> bool:
    """El documento trae el campo: con valor, o con un literal que no se pudo leer."""
    return (valor is not None and valor != "") or columna in factura.ilegibles


def _contraparte(factura: Factura) -> tuple[bool | None, tuple[str, ...]]:
    """Si el documento dice quien es la otra parte; None si no se le pregunto."""
    if factura.sentido == SALIENTE:
        columnas = ("receptor_nombre_doc", "receptor_btw_doc")
        esta = factura.cliente_id is not None or any(
            _impreso(factura, c, getattr(factura, c)) for c in columnas)
        if not esta and all(c in factura.no_solicitados for c in columnas):
            return None, columnas
        return esta, columnas[:1]
    columnas = ("emisor_nombre_doc", "emisor_btw_doc", "emisor_kvk_doc")
    esta = factura.proveedor_id is not None or any(
        _impreso(factura, c, getattr(factura, c)) for c in columnas)
    return esta, columnas[:1]


def _presencia_q1(factura: Factura) -> dict[str, bool | None]:
    inicio, fin = periodo_de(factura)
    contraparte, _ = _contraparte(factura)
    return {
        "numero": _impreso(factura, "numero", factura.numero),
        "contraparte": contraparte,
        "fecha": _impreso(factura, "fecha_factura", factura.fecha_factura),
        "periodo": (_impreso(factura, "periodo_inicio", inicio)
                    and _impreso(factura, "periodo_fin", fin)),
        "base": _impreso(factura, "base_cent", factura.base_cent),
        "iva": (_impreso(factura, "iva_cent", factura.iva_cent)
                or factura.tratamiento_iva in _REGIMEN_CONOCIDO),
        "total": _impreso(factura, "total_cent", factura.total_cent),
    }


def q1(factura: Factura, _politica: Politica) -> list[Resultado]:
    """Q1: los campos obligatorios para el sentido de la factura estan en el documento.

    Bloquea si falta el numero, el total o la contraparte (sin ellos no se
    puede ni buscar un duplicado ni pagar); retiene por lo demas. La
    contraparte es la que imprime el documento: que el maestro la conozca es
    A0 (paso 5).

    Lo que la version del esquema no pidio (la contraparte de una venta v1)
    va en un resultado aparte, con su propia clave, como el btw-id del
    receptor en E4: un sin_datos sobre la clave de los campos que si se
    pidieron haria creer al motor que no pudo mirarlos, y una fecha que
    falta y se corrige no cerraria nunca su hallazgo.
    """
    presencia = _presencia_q1(factura)
    conocidos = [(etiqueta, bool(presencia[clave]))
                 for clave, etiqueta, _b, _c in _OBLIGATORIOS_Q1 if presencia[clave] is not None]
    desconocidos = [clave for clave, *_ in _OBLIGATORIOS_Q1 if presencia[clave] is None]
    faltan = [clave for clave, *_ in _OBLIGATORIOS_Q1 if presencia[clave] is False]
    valores = {"faltan": faltan, "no_solicitados": desconocidos}
    sin_pedir = [resultado_de(
        "Q1", factura, Comprobacion(
            SIN_DATOS, f"La versión del esquema no pidió {etiqueta}: no se puede decir si el "
            "documento lo trae."), valores={"no_solicitado": clave}, clave=clave)
        for clave, etiqueta, _b, _c in _OBLIGATORIOS_Q1 if clave in desconocidos]
    comprobacion = campos_que_faltan(conocidos)
    if comprobacion.resultado != FALLO:
        return [resultado_de("Q1", factura, comprobacion, valores=valores), *sin_pedir]
    bloquea = any(b for clave, _e, b, _c in _OBLIGATORIOS_Q1 if clave in faltan)
    _, columnas_parte = _contraparte(factura)
    objetivos = tuple(
        Objetivo("factura", factura.id, columna)
        for clave, _e, _b, columnas in _OBLIGATORIOS_Q1 if clave in faltan
        for columna in (columnas or columnas_parte))
    return [resultado_de("Q1", factura, comprobacion, valores=valores,
                         severidad=B if bloquea else R, objetivos=objetivos), *sin_pedir]


LEE_Q1 = LEE_PERIODO | frozenset({
    "factura.sentido", "factura.numero", "factura.proveedor_id", "factura.cliente_id",
    "factura.emisor_nombre_doc", "factura.emisor_btw_doc", "factura.emisor_kvk_doc",
    "factura.receptor_nombre_doc", "factura.receptor_btw_doc", "factura.fecha_factura",
    "factura.base_cent", "factura.iva_cent", "factura.total_cent", "factura.tratamiento_iva",
    "factura.ilegibles", "factura.no_solicitados",
})

# --------------------------------------------------------------- X1


def moneda(hay_importes: bool, otras: Sequence[str], alguno_en_euros: bool) -> Comprobacion:
    """X1: la factura entera esta en euros.

    La moneda se decide para la factura, no importe a importe: un modelo
    copia el "$" en unos campos y lo pierde en otros, y el importe que lo
    perdio no es por eso un importe en euros. Solo se da por buena cuando
    algun importe se lee como euro; si no se lee ninguno, no se sabe en que
    moneda esta, y eso es sin_datos, no un ok que nadie ha comprobado.
    """
    if not hay_importes:
        return Comprobacion(SIN_DATOS, "La factura no trae importes.")
    if otras:
        return Comprobacion(
            FALLO, f"Importes en {', '.join(otras)}: no está en euros y queda fuera de "
            "todos los totales.")
    if not alguno_en_euros:
        return Comprobacion(
            SIN_DATOS, "Ningún importe es legible: no se puede decir en qué moneda está.")
    return Comprobacion(OK, "Importes en euros.")


_IMPORTES_CABECERA = ("base_cent", "iva_cent", "total_cent")
_IMPORTES_LINEA = ("tarifa_e4", "importe_cent")


def x1(factura: Factura, _politica: Politica) -> list[Resultado]:
    """X1 sobre el almacen: la moneda la decidio la ingesta (moneda_doc) para la factura entera.

    Una factura que no esta en euros guarda sus importes vacios con su
    literal, asi que aqui se ve como "otra moneda" y no como "sin importes".
    """
    otras = [factura.moneda] if factura.moneda not in (None, "EUR") else []
    valores = [factura.base_cent, factura.iva_cent, factura.total_cent]
    valores += [getattr(l, c) for l in factura.lineas for c in _IMPORTES_LINEA]
    legibles = any(v is not None for v in valores)
    ilegibles = (any(c in factura.ilegibles for c in _IMPORTES_CABECERA)
                 or any(c in l.ilegibles for l in factura.lineas for c in _IMPORTES_LINEA))
    comprobacion = moneda(legibles or ilegibles or bool(otras), otras, legibles)
    objetivos = (Objetivo("factura", factura.id, "moneda_doc"),) if otras else ()
    return [resultado_de("X1", factura, comprobacion, valores={"moneda": factura.moneda},
                         objetivos=objetivos)]


LEE_X1 = frozenset({
    "factura.moneda", "factura.base_cent", "factura.iva_cent", "factura.total_cent",
    "factura.lineas", "factura.ilegibles", "linea.tarifa_e4", "linea.importe_cent",
    "linea.ilegibles",
})
