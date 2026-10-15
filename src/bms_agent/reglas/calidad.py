"""Reglas de datos: Q1 (lo obligatorio esta), X1 (en euros) y, desde el paso 5, Q2, Q3, Q4, Z1, Z2.

Faltar no es lo mismo que no poderse leer. Q1 mira si el documento trae el
campo: un literal impreso que no se pudo leer esta en el papel (eso es Q2,
lectura dudosa, del paso 5), y un campo que la version del esquema no le
pidio al modelo no dice nada del documento: deja Q1 en sin_datos, no en
fallo. Asi el historico v1 no se llena de faltas que no son.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .base import (
    B,
    FALLO,
    FRESCURA,
    LEE_EN_JUEGO,
    LEE_PERIODO,
    OK,
    R,
    SALIENTE,
    SIN_DATOS,
    Comprobacion,
    Factura,
    Instantanea,
    Lote,
    Objetivo,
    Politica,
    Resultado,
    edad,
    fallo,
    periodo_de,
    por_factura,
    resultado_de,
    solo_objeciones,
    ultimo_lote_valido,
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


# --------------------------------------------------------------- Q2, Q3, Q4 (paso 5)
#
# Como todas las reglas de factura del paso 5, solo escriben lo que objetan
# (base.solo_objeciones).

_ETIQUETA_CAMPO = {
    "numero": "el número", "proveedor_id": "el proveedor", "cliente_id": "el cliente",
    "emisor_nombre_doc": "el nombre del emisor", "fecha_factura": "la fecha",
    "periodo_inicio": "el inicio del periodo", "periodo_fin": "el fin del periodo",
    "iva_cent": "la cuota de IVA", "total_cent": "el total", "iban_doc": "el IBAN",
}


def q2(factura: Factura, _contexto: Any) -> list[Resultado]:
    """Q2: un campo critico se leyo con duda y nadie lo ha verificado (retiene)."""
    if not factura.dudosos:
        return []
    campos = sorted(factura.dudosos)
    return [fallo("Q2", factura, "Leído con duda y sin verificar: "
                  + ", ".join(_ETIQUETA_CAMPO.get(c, c) for c in campos) + ".",
                  valores={"campos": campos},
                  objetivos=tuple(Objetivo("factura", factura.id, c) for c in campos))]


LEE_Q2 = LEE_EN_JUEGO | frozenset({"factura.id", "factura.dudosos"})

# Lo que en las notas del documento suena a instrucciones para quien lo lee:
# el extractor las copia ahi como texto (nunca las sigue), y esto lo marca.
# Se dice que clase de cosa se vio, no el texto (que puede llevar un IBAN).
MARCAS_INYECCION: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("un IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?\b")),
    ("cuenta bancaria", re.compile(
        r"\biban\b|bankrekening|rekeningnummer|bank ?account|cuenta bancaria|bankgegevens",
        re.IGNORECASE)),
    ("un cambio de datos", re.compile(
        r"gewijzigd|wijziging|changed|ha cambiado|nuevo n[uú]mero|voortaan|from now on|"
        r"werk .{0,40}bij|update|actualice", re.IGNORECASE)),
    ("instrucciones al sistema", re.compile(
        r"negeer|ignore|instructie|instruction|instrucci[oó]n|administratiesysteem|systeem|"
        r"\bsystem\b|sistema|assistant|asistente", re.IGNORECASE)),
    ("llamar o confirmar", re.compile(
        r"\bbel\b|\bbellen\b|\bcall\b|llame|telefoon|phone|tel[eé]fono|bevestig|confirm|"
        r"e-?mail", re.IGNORECASE)),
)


# Una marca sola casi siempre es inocente ("vragen? e-mail ..."; el IBAN de
# siempre repetido al pie): Q3 avisa con dos clases distintas, o con una
# frase dirigida al sistema, que no tiene lectura inocente en una factura.
MARCA_FUERTE = "instrucciones al sistema"


def marcas_de_inyeccion(texto: str | None) -> list[str]:
    """Que clases de texto sospechoso hay en unas notas (vacio si ninguna)."""
    if not texto:
        return []
    return [etiqueta for etiqueta, patron in MARCAS_INYECCION if patron.search(texto)]


def sospechoso(marcas: Sequence[str]) -> bool:
    """Si las marcas de unas notas bastan para avisar (Q3)."""
    return MARCA_FUERTE in marcas or len(set(marcas)) >= 2


def q3(factura: Factura, _contexto: Any) -> list[Resultado]:
    """Q3: las notas del documento traen texto marcado: un intento de inyeccion (aviso).

    Abre una excepcion. Lo que pide ese texto no se hace nunca: el IBAN del
    documento no entra en el registro de cuentas y el de pago sale del
    maestro (F2, F3).
    """
    marcas = marcas_de_inyeccion(factura.notas_doc)
    if not sospechoso(marcas):
        return []
    return [fallo("Q3", factura, "Las notas del documento traen texto dirigido a quien lo "
                                 "procesa (" + ", ".join(marcas) + "): no se sigue, se revisa.",
                  valores={"marcas": marcas},
                  objetivos=(Objetivo("factura", factura.id, "notas_doc"),))]


LEE_Q3 = LEE_EN_JUEGO | frozenset({"factura.id", "factura.notas_doc"})


def q4(factura: Factura, _contexto: Any) -> list[Resultado]:
    """Q4: la factura se extrajo de un documento cuyo original no esta guardado (aviso)."""
    if not factura.sin_original:
        return []
    return [fallo("Q4", factura, "El original del documento no está en el almacén: solo queda "
                                 "lo que se extrajo de él.",
                  valores={"documento_id": factura.documento_id},
                  objetivos=(Objetivo("factura", factura.id, "documento_id"),))]


LEE_Q4 = LEE_EN_JUEGO | frozenset({"factura.id", "factura.sin_original", "factura.documento_id"})

EVALUAR_Q = {"Q2": solo_objeciones(q2), "Q3": solo_objeciones(q3), "Q4": solo_objeciones(q4)}


# --------------------------------------------------------------- X1, Z1 y Z2 sobre importaciones

def _de_importacion(regla: str, lote: Lote, detalle: str, valores: dict[str, Any], *,
                    grupo: str | None = None) -> Resultado:
    return Resultado(regla, "importacion", lote.id, FALLO, detalle, valores, "", grupo, None,
                     (Objetivo("importacion", lote.id),))


def x1_importaciones(instantanea: Instantanea) -> list[Resultado]:
    """X1 sobre los maestros: una fila con un importe en otra moneda (una tarifa en dolares).

    La fila no entra (no hay columna de moneda: lo que no esta en euros no se
    guarda como importe), y la ultima importacion de su fuente y tipo queda
    bloqueada hasta que una que la sustituya llegue limpia y una persona
    cierre el hallazgo, que es pegajoso.
    """
    salida = []
    for lote in instantanea.lotes:
        if not lote.ultimo:
            continue
        filas = [[f, m] for f, codigo, m in lote.rechazos if codigo == "X1"]
        if filas:
            salida.append(_de_importacion(
                "X1", lote, f"{len(filas)} fila{'s' if len(filas) != 1 else ''} con importes que "
                            "no están en euros: no entran.", {"filas": filas[:20]}))
    return salida


def x1_todo(instantanea: Instantanea) -> list[Resultado]:
    return por_factura("X1", x1)(instantanea) + x1_importaciones(instantanea)


LEE_X1_IMPORTACIONES = frozenset({"instantanea.lotes", "lote.ultimo", "lote.rechazos", "lote.id"})


def z1(instantanea: Instantanea) -> list[Resultado]:
    """Z1: una fuente pasada de su limite de frescura (aviso y aviso en la consola).

    Mientras lo esta, las reglas que dependen de ella dan sin_datos en vez de
    ok (A2, E1, F2, F3 con Exact), nunca un ok que nadie ha comprobado.
    """
    salida = []
    for fuente, campo in sorted(FRESCURA.items()):
        lote = ultimo_lote_valido(instantanea, fuente)
        if lote is None:
            continue
        limite = getattr(instantanea.politica, campo)
        dias = edad(lote, instantanea.hoy, fuente)
        if dias <= limite:
            continue
        unidad = "días laborables" if fuente == "banco" else "días"
        salida.append(_de_importacion(
            "Z1", lote, f"Lo último de {fuente} es del {lote.exportado.isoformat()}: {dias} "
                        f"{unidad}, más que el límite de {limite}. Lo que depende de esa fuente "
                        "queda sin datos.",
            {"fuente": fuente, "exportado": lote.exportado.isoformat(), "edad": dias,
             "limite": limite}, grupo=f"fuente:{fuente}"))
    return salida


LEE_Z1 = frozenset({"instantanea.lotes", "instantanea.hoy", "instantanea.politica",
                    "lote.fuente", "lote.estado", "lote.id", "lote.exportado",
                    "politica.frescura_exact_dias", "politica.frescura_trnsprnt_dias",
                    "politica.frescura_banco_dias_laborables"})


def z2(instantanea: Instantanea) -> list[Resultado]:
    """Z2: la ultima importacion de una fuente y tipo rechazo filas, o se rechazo entera.

    Una fila rechazada es una fila que no entro: un proveedor, una tarifa o
    una cuenta que el maestro tiene y aqui no. Una referencia desconocida (un
    cliente que no existe) tambien: nada se crea solo. Retiene; se cierra
    cuando llega una importacion de esa fuente y tipo sin rechazos.
    """
    salida = []
    for lote in instantanea.lotes:
        if not lote.ultimo or (lote.filas_rechazadas == 0 and lote.estado != "rechazada"):
            continue
        filas = [[f, c, m] for f, c, m in lote.rechazos]
        entera = " Se rechazó entera: no entró nada." if lote.estado == "rechazada" else ""
        salida.append(_de_importacion(
            "Z2", lote, f"{lote.fuente}/{lote.tipo}: {lote.filas_rechazadas} fila"
                        f"{'s' if lote.filas_rechazadas != 1 else ''} rechazada"
                        f"{'s' if lote.filas_rechazadas != 1 else ''}.{entera}",
            {"rechazadas": lote.filas_rechazadas, "estado": lote.estado, "filas": filas[:20]}))
    return salida


LEE_Z2 = frozenset({"instantanea.lotes", "lote.ultimo", "lote.filas_rechazadas", "lote.estado",
                    "lote.rechazos", "lote.fuente", "lote.tipo", "lote.id"})
