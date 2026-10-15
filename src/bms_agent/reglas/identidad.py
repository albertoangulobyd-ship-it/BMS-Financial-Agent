"""Reglas de identidad (spec §7): A0, A2, A5, A7 y A8.

Quien firma una factura y a quien va dirigida, contra el maestro y contra la
propia historia de esa contraparte. La contraparte se resuelve fuera
(identidad.py, al tipar: btw-id, KvK, alias confirmado; nunca el IBAN ni por
parecido); aqui solo se mira lo que salio:

- A0: no se sabe quien es (desconocida o ambigua). Sin maestro importado no
  se puede saber: sin_datos.
- A2: lo impreso (nombre, KvK, btw-id) no dice lo mismo que el maestro de la
  contraparte resuelta. Un alias confirmado cuenta como su nombre.
- A5: una compra sin btw-id que tampoco dice KOR bloquea; un btw-id
  neerlandes con forma rara retiene.
- A7: lo impreso cambio respecto a la factura anterior de la misma
  contraparte: btw-id o KvK retienen, nombre o direccion avisan.
- A8: no va dirigida a BM Support BV (config/empresa.yaml); una factura de
  la via de salida que no emite BM Support BV esta mal encaminada (bloquea).

Como todas las reglas de factura del paso 5, solo escriben lo que objetan:
un fallo o un sin_datos (base.solo_objeciones).
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from .base import (
    A,
    B,
    ENTRANTE,
    LEE_CADUCIDAD,
    LEE_EN_JUEGO,
    LEE_IMPORTADO,
    R,
    SALIENTE,
    Factura,
    Instantanea,
    Objetivo,
    Parte,
    Resultado,
    caducada,
    en_juego,
    fallo,
    importado,
    sin_datos,
    solo_objeciones,
)
from .normas import normalizar_btw, normalizar_kvk, normalizar_nombre

_BTW_NL = re.compile(r"NL\d{9}B\d{2}")


def _maestro(instantanea: Instantanea, sentido: str) -> tuple[Parte, ...]:
    return instantanea.proveedores if sentido == ENTRANTE else instantanea.clientes


def _impreso(factura: Factura) -> tuple[str | None, str | None, str | None]:
    """El btw-id, el KvK y el nombre de la contraparte tal como los imprime, normalizados."""
    if factura.sentido == ENTRANTE:
        return (normalizar_btw(factura.emisor_btw_doc), normalizar_kvk(factura.emisor_kvk_doc),
                normalizar_nombre(factura.emisor_nombre_doc))
    return normalizar_btw(factura.receptor_btw_doc), None, normalizar_nombre(
        factura.receptor_nombre_doc)


# --------------------------------------------------------------- A0

def _preparar_a0(instantanea: Instantanea) -> dict[str, Any]:
    indices: dict[str, Any] = {}
    for sentido, tipo in ((ENTRANTE, "proveedores"), (SALIENTE, "clientes")):
        por_btw: dict[str, int] = defaultdict(int)
        por_kvk: dict[str, int] = defaultdict(int)
        for parte in _maestro(instantanea, sentido):
            if parte.btw:
                por_btw[parte.btw] += 1
            if parte.kvk:
                por_kvk[parte.kvk] += 1
        indices[sentido] = (importado(instantanea, tipo), por_btw, por_kvk)
    return indices


def a0(factura: Factura, indices: dict[str, Any]) -> list[Resultado]:
    """A0: la contraparte no se conoce o es ambigua (retiene, no se anula)."""
    resuelta = factura.proveedor_id if factura.sentido == ENTRANTE else factura.cliente_id
    if resuelta is not None:
        return []
    hay_maestro, por_btw, por_kvk = indices[factura.sentido]
    quien = "proveedores" if factura.sentido == ENTRANTE else "clientes"
    if not hay_maestro:
        return [sin_datos("A0", factura, f"Todavía no se ha importado el maestro de {quien}: no "
                                         "se puede decir si la contraparte se conoce.")]
    btw, kvk, nombre = _impreso(factura)
    valores = {"btw": btw, "kvk": kvk, "nombre": nombre}
    objetivo = (Objetivo("factura", factura.id,
                         "proveedor_id" if factura.sentido == ENTRANTE else "cliente_id"),)
    for etiqueta, clave, indice in (("btw-id", btw, por_btw), ("KvK", kvk, por_kvk)):
        if clave and indice.get(clave, 0) > 1:
            return [fallo("A0", factura, f"Contraparte ambigua: {indice[clave]} {quien} del "
                                         f"maestro tienen el {etiqueta} {clave}.",
                          valores={**valores, "candidatos": indice[clave]}, objetivos=objetivo)]
    return [fallo("A0", factura, f"Contraparte desconocida: ningún {quien[:-2]} del maestro "
                                 "coincide exactamente (btw-id, KvK o alias confirmado).",
                  valores=valores, objetivos=objetivo)]


LEE_A0 = LEE_EN_JUEGO | LEE_IMPORTADO | frozenset({
    "factura.id", "factura.sentido", "factura.proveedor_id", "factura.cliente_id",
    "factura.emisor_btw_doc", "factura.emisor_kvk_doc", "factura.emisor_nombre_doc",
    "factura.receptor_btw_doc", "factura.receptor_nombre_doc",
    "instantanea.proveedores", "instantanea.clientes", "parte.btw", "parte.kvk",
})

# --------------------------------------------------------------- A2

def _preparar_partes(instantanea: Instantanea) -> dict[str, Any]:
    return {"proveedor": {p.id: p for p in instantanea.proveedores},
            "cliente": {c.id: c for c in instantanea.clientes},
            "caducada": bool(caducada(instantanea, "exact"))}


def a2(factura: Factura, contexto: dict[str, Any]) -> list[Resultado]:
    """A2: lo impreso no dice lo mismo que el maestro de la contraparte resuelta."""
    entrante = factura.sentido == ENTRANTE
    parte_id = factura.proveedor_id if entrante else factura.cliente_id
    if parte_id is None:
        return []
    parte = contexto["proveedor" if entrante else "cliente"].get(parte_id)
    if parte is None:
        return []
    btw, kvk, nombre = _impreso(factura)
    distintos = {}
    if btw and parte.btw and btw != parte.btw:
        distintos["btw"] = [btw, parte.btw]
    if kvk and parte.kvk and kvk != parte.kvk:
        distintos["kvk"] = [kvk, parte.kvk]
    if nombre and nombre not in parte.nombres:
        distintos["nombre"] = [nombre, sorted(parte.nombres)]
    if not distintos:
        if contexto["caducada"]:
            return [sin_datos("A2", factura, "El maestro de Exact está pasado de su límite de "
                                             "frescura: no se compara con él.")]
        return []
    columnas = ({"btw": "emisor_btw_doc", "kvk": "emisor_kvk_doc", "nombre": "emisor_nombre_doc"}
                if entrante else {"btw": "receptor_btw_doc", "nombre": "receptor_nombre_doc"})
    etiquetas = {"btw": "el btw-id", "kvk": "el KvK", "nombre": "el nombre"}
    return [fallo("A2", factura,
                  f"Lo impreso no coincide con el maestro de {parte.nombre}: "
                  + ", ".join(etiquetas[c] for c in distintos) + ".",
                  valores=distintos,
                  objetivos=tuple(Objetivo("factura", factura.id, columnas[c]) for c in distintos))]


LEE_A2 = LEE_EN_JUEGO | LEE_CADUCIDAD | frozenset({
    "factura.id", "factura.sentido", "factura.proveedor_id", "factura.cliente_id",
    "factura.emisor_btw_doc", "factura.emisor_kvk_doc", "factura.emisor_nombre_doc",
    "factura.receptor_btw_doc", "factura.receptor_nombre_doc",
    "instantanea.proveedores", "instantanea.clientes", "parte.id", "parte.btw", "parte.kvk",
    "parte.nombres",
})
SOLO_TEXTO_A2 = frozenset({"parte.nombre"})

# --------------------------------------------------------------- A5

def a5(factura: Factura, _contexto: Any) -> list[Resultado]:
    """A5: una compra sin btw-id que no dice KOR bloquea; uno neerlandes mal formado retiene."""
    if factura.sentido != ENTRANTE:
        return []
    kor = bool(factura.kor_mencionada) or factura.tratamiento_iva == "kor"
    btw = normalizar_btw(factura.emisor_btw_doc)
    if btw is None:
        if "emisor_btw_doc" in factura.ilegibles or kor:
            return []
        return [fallo("A5", factura, "La factura no lleva el btw-id del proveedor y no dice "
                                     "que aplique la KOR.", valores={"btw": None, "kor": kor},
                      objetivos=(Objetivo("factura", factura.id, "emisor_btw_doc"),))]
    if btw.startswith("NL") and not _BTW_NL.fullmatch(btw):
        return [fallo("A5", factura, f"El btw-id {btw} no tiene la forma NL + nueve cifras + B + "
                                     "dos cifras.", valores={"btw": btw}, severidad=R,
                      objetivos=(Objetivo("factura", factura.id, "emisor_btw_doc"),))]
    return []


LEE_A5 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.sentido", "factura.kor_mencionada", "factura.tratamiento_iva",
    "factura.emisor_btw_doc", "factura.ilegibles",
})

# --------------------------------------------------------------- A7

_CAMPOS_A7 = (("btw", "emisor_btw_doc", R, "el btw-id", normalizar_btw),
              ("kvk", "emisor_kvk_doc", R, "el KvK", normalizar_kvk),
              ("nombre", "emisor_nombre_doc", A, "el nombre", normalizar_nombre),
              ("direccion", "emisor_direccion_doc", A, "la dirección", normalizar_nombre))


def _preparar_a7(instantanea: Instantanea) -> dict[int, Resultado]:
    """Recorre cada contraparte por fecha y deja el resultado de A7 de cada compra que cambia.

    Lo impreso se compara primero tal cual: casi siempre es el mismo texto
    que en la factura anterior, y solo cuando difiere se normaliza para ver
    si es otra cosa o la misma escrita de otra forma.
    """
    grupos: dict[str, list[Factura]] = defaultdict(list)
    for f in instantanea.facturas:
        if f.sentido == ENTRANTE and f.parte is not None and en_juego(f):
            grupos[f.parte].append(f)
    salida: dict[int, Resultado] = {}
    for lista in grupos.values():
        lista.sort(key=lambda f: (f.fecha_factura or date.min, f.id))
        for previa, actual in zip(lista, lista[1:]):
            cambios = []
            for clave, columna, severidad, etiqueta, norma in _CAMPOS_A7:
                antes, ahora = getattr(previa, columna), getattr(actual, columna)
                if antes == ahora or not antes or not ahora:
                    continue
                antes, ahora = norma(antes), norma(ahora)
                if antes and ahora and antes != ahora:
                    cambios.append((clave, columna, severidad, etiqueta, antes, ahora))
            if cambios:
                salida[actual.id] = _resultado_a7(actual, previa.id, cambios)
    return salida


def _resultado_a7(factura: Factura, previa_id: int, cambios: list[tuple]) -> Resultado:
    severidad = R if any(c[2] == R for c in cambios) else A
    return fallo("A7", factura,
                 "Cambia respecto a su factura anterior: "
                 + ", ".join(c[3] for c in cambios) + ".",
                 valores={"anterior": previa_id, **{c[0]: [c[4], c[5]] for c in cambios}},
                 severidad=severidad,
                 objetivos=tuple(Objetivo("factura", factura.id, c[1]) for c in cambios))


def a7(factura: Factura, resultados: dict[int, Resultado]) -> list[Resultado]:
    """A7: lo que imprime un proveedor cambio respecto a su factura anterior.

    btw-id o KvK retienen (y el hallazgo no se cierra solo); nombre o
    direccion avisan. Solo se compara lo que imprimen las dos: que falte es
    Q1 o A5, no un cambio.
    """
    resultado = resultados.get(factura.id)
    return [resultado] if resultado is not None else []


LEE_A7 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.sentido", "factura.parte", "factura.fecha_factura",
    "factura.emisor_btw_doc", "factura.emisor_kvk_doc", "factura.emisor_nombre_doc",
    "factura.emisor_direccion_doc",
})

# --------------------------------------------------------------- A8

def _preparar_a8(instantanea: Instantanea) -> dict[str, Any]:
    """La identidad de la empresa, y una memoria de lo ya normalizado en esta pasada.

    Casi todas las facturas imprimen el mismo receptor (o ninguno): cada
    texto distinto se normaliza una vez y no en cada factura.
    """
    politica = instantanea.politica
    return {"nombres": politica.empresa_nombres, "btw": politica.empresa_btw, "normas": {}}


def _normas(contexto: dict[str, Any], nombre: str | None,
            btw: str | None) -> tuple[str | None, str | None]:
    hecho = contexto["normas"].get((nombre, btw))
    if hecho is None:
        hecho = contexto["normas"][(nombre, btw)] = (normalizar_nombre(nombre),
                                                      normalizar_btw(btw))
    return hecho


# Lo que llega estructurado de su sistema no es un documento con emisor y
# receptor impresos: una venta de Exact la emite BM Support BV por ser de su
# administracion. A8 mira documentos.
_DE_SU_SISTEMA = frozenset({"exact", "trnsprnt"})


def a8(factura: Factura, contexto: dict[str, Any]) -> list[Resultado]:
    """A8: va dirigida a BM Support BV; una de salida la emite BM Support BV.

    En la via de salida, que el emisor no sea BM Support BV es que el
    documento esta mal encaminado: bloquea (spec §7 y §8). La direccion la
    puso la via, no el modelo, asi que un PDF de un proveedor dejado en la
    carpeta de ventas es una venta mal encaminada, nunca una compra.
    """
    nombres, btw_empresa = contexto["nombres"], contexto["btw"]
    if factura.origen in _DE_SU_SISTEMA:
        return []
    if factura.sentido == SALIENTE:
        nombre, btw = _normas(contexto, factura.emisor_nombre_doc, factura.emisor_btw_doc)
        if nombre is None and btw is None:
            return [sin_datos("A8", factura, "La factura de salida no dice quién la emite.")]
        if (nombre is not None and nombre not in nombres) or (
                btw is not None and btw_empresa and btw != btw_empresa):
            return [fallo("A8", factura, "Llegó por la vía de salida y no la emite BM Support "
                                         "BV: está mal encaminada.",
                          valores={"emisor": nombre, "btw": btw}, severidad=B,
                          objetivos=(Objetivo("factura", factura.id, "emisor_nombre_doc"),))]
        return []
    nombre, btw = _normas(contexto, factura.receptor_nombre_doc, factura.receptor_btw_doc)
    if nombre is None and btw is None:
        if "receptor_nombre_doc" in factura.no_solicitados:
            return [sin_datos("A8", factura, "La versión del esquema no pidió a quién va "
                                             "dirigida.")]
        return [sin_datos("A8", factura, "El documento no dice a quién va dirigido.")]
    distintos = {}
    if nombre is not None and nombre not in nombres:
        distintos["nombre"] = nombre
    if btw is not None and btw_empresa and btw != btw_empresa:
        distintos["btw"] = btw
    if not distintos:
        return []
    columnas = {"nombre": "receptor_nombre_doc", "btw": "receptor_btw_doc"}
    return [fallo("A8", factura, "No va dirigida a BM Support BV: "
                                 + ", ".join(f"{c} {v}" for c, v in distintos.items()) + ".",
                  valores=distintos,
                  objetivos=tuple(Objetivo("factura", factura.id, columnas[c])
                                  for c in distintos))]


LEE_A8 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.sentido", "factura.origen", "factura.emisor_nombre_doc",
    "factura.emisor_btw_doc",
    "factura.receptor_nombre_doc", "factura.receptor_btw_doc", "factura.no_solicitados",
    "instantanea.politica", "politica.empresa_nombres", "politica.empresa_btw",
})

EVALUAR = {
    "A0": solo_objeciones(a0, _preparar_a0),
    "A2": solo_objeciones(a2, _preparar_partes),
    "A5": solo_objeciones(a5),
    "A7": solo_objeciones(a7, _preparar_a7),
    "A8": solo_objeciones(a8, _preparar_a8),
}
