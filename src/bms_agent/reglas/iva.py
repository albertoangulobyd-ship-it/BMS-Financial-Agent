"""Reglas de IVA: D3 (la cuota por el tipo), E3 (KOR), E4 (IVA trasladado), desde el
paso 5 E1 (contra el regimen del maestro) y E2 (contra la factura anterior), y desde el
paso 11 E0 (falta la informacion del IVA), E5 (umbral de la KOR) y E7 (tipo o
tratamiento raro), con las lineas de IVA de una factura (`lineas_iva`) y su huella
(`huella_iva`), que comparten la declaracion del BTW (btw.py) y C4 (fechas.py).

Con IVA trasladado o con KOR no hay tipo que aplicar, y eso no es un dato
que falte: es el estado correcto de la factura (D3 no aplica). Pero si en
ese regimen aparece una cuota distinta de cero, eso si es una regla
incumplida, y no la misma: E3 con la KOR, E4 con el IVA trasladado.

Pendiente de confirmar con el contador (validacion-facturas.md): todo el
grupo E toca obligaciones fiscales.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any, NamedTuple

from .base import (
    ENTRANTE,
    FALLO,
    LEE_CADUCIDAD,
    LEE_EN_JUEGO,
    NO_APLICA,
    OK,
    RELACIONADO,
    SALIENTE,
    SIN_DATOS,
    Comprobacion,
    Factura,
    Instantanea,
    Objetivo,
    Politica,
    Resultado,
    caducada,
    en_juego,
    euros,
    euros_texto,
    fallo,
    porcentaje,
    resultado_de,
    sin_datos,
    solo_objeciones,
)
from .normas import normalizar_btw

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


# --------------------------------------------------------------- E1 y E2 (paso 5)
#
# Como las demas reglas de factura del paso 5, solo escriben lo que objetan
# (base.solo_objeciones). Un regimen que la factura no dice ("desconocido" o
# nada) no se compara: eso lo ve Q1 (falta el IVA o el regimen).

_SIN_REGIMEN = (None, "desconocido")
_NOMBRE_REGIMEN = {"estandar": "IVA normal", "autoliquidacion": "IVA trasladado", "kor": "KOR",
                   "exento": "exención", "tipo_cero": "tipo cero"}


def _preparar_e1(instantanea: Instantanea) -> dict[str, Any]:
    return {"regimen": {p.id: p.regimen_iva for p in instantanea.proveedores},
            "caducada": bool(caducada(instantanea, "exact"))}


def e1(factura: Factura, contexto: dict[str, Any]) -> list[Resultado]:
    """E1: el regimen de la factura no es el que el maestro tiene registrado del proveedor."""
    if factura.sentido != ENTRANTE or factura.proveedor_id is None:
        return []
    registrado = contexto["regimen"].get(factura.proveedor_id)
    if registrado in _SIN_REGIMEN or factura.tratamiento_iva in _SIN_REGIMEN:
        return []
    if registrado == factura.tratamiento_iva:
        if contexto["caducada"]:
            return [sin_datos("E1", factura, "El maestro de Exact está pasado de su límite de "
                                             "frescura: no se compara con él.")]
        return []
    return [fallo("E1", factura,
                  f"La factura viene con {_NOMBRE_REGIMEN.get(factura.tratamiento_iva)} y el "
                  f"maestro tiene al proveedor en {_NOMBRE_REGIMEN.get(registrado)}.",
                  valores={"maestro": registrado, "factura": factura.tratamiento_iva},
                  objetivos=(Objetivo("factura", factura.id, "tratamiento_iva"),))]


LEE_E1 = LEE_EN_JUEGO | LEE_CADUCIDAD | frozenset({
    "factura.id", "factura.sentido", "factura.proveedor_id", "factura.tratamiento_iva",
    "instantanea.proveedores", "parte.id", "parte.regimen_iva",
})


def _preparar_e2(instantanea: Instantanea) -> dict[int, tuple[int, str]]:
    """Para cada compra con regimen, la anterior de su contraparte (por fecha) y el suyo."""
    grupos: dict[str, list[Factura]] = defaultdict(list)
    for f in instantanea.facturas:
        if (f.sentido == ENTRANTE and f.parte is not None and en_juego(f)
                and f.tratamiento_iva not in _SIN_REGIMEN):
            grupos[f.parte].append(f)
    anterior: dict[int, tuple[int, str]] = {}
    for lista in grupos.values():
        lista.sort(key=lambda f: (f.fecha_factura or date.min, f.id))
        for previa, actual in zip(lista, lista[1:]):
            anterior[actual.id] = (previa.id, previa.tratamiento_iva)
    return anterior


def e2(factura: Factura, anterior: dict[int, tuple[int, str]]) -> list[Resultado]:
    """E2: el regimen cambia respecto a la factura anterior del mismo proveedor.

    Casi siempre es un cambio legitimo que hay que llevar al maestro; verlo en
    la factura y no en la declaracion es la diferencia entre un ajuste y una
    correccion (validacion-facturas.md §3.E). El hallazgo no se cierra solo.
    """
    previa = anterior.get(factura.id)
    if previa is None or previa[1] == factura.tratamiento_iva:
        return []
    return [fallo("E2", factura,
                  f"Pasa de {_NOMBRE_REGIMEN.get(previa[1])} a "
                  f"{_NOMBRE_REGIMEN.get(factura.tratamiento_iva)} respecto a su factura anterior.",
                  valores={"anterior": previa[0], "antes": previa[1],
                           "ahora": factura.tratamiento_iva},
                  objetivos=(Objetivo("factura", factura.id, "tratamiento_iva"),))]


LEE_E2 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.sentido", "factura.parte", "factura.fecha_factura",
    "factura.tratamiento_iva",
})

EVALUAR_E = {"E1": solo_objeciones(e1, _preparar_e1), "E2": solo_objeciones(e2, _preparar_e2)}


# --------------------------------------------------------------- lineas de IVA (paso 11)
#
# Lo que una factura declara de IVA, linea a linea: su desglose por tipo (v2,
# Exact) o, si no lo tiene, la cabecera (v1, que solo pidio un tipo). Es lo
# mismo que v_btw_linea (migracion 0014) en SQL; btw.py prepara la declaracion
# con la vista y C4 compara con lo declarado con esto, y un test comprueba que
# dicen lo mismo de cada factura.

class LineaIva(NamedTuple):
    """Una linea de IVA: el tratamiento (el de la fila del desglose o el de la factura),
    el tipo en puntos basicos, la base y la cuota impresa."""

    tratamiento: str | None
    tipo_iva_pb: int | None
    base_cent: int | None
    cuota_cent: int | None


def lineas_iva(factura: Factura) -> tuple[LineaIva, ...]:
    """Las lineas de IVA de una factura, en el orden de su desglose."""
    if factura.desglose:
        return tuple(LineaIva(t.tratamiento or factura.tratamiento_iva, t.tipo_iva_pb,
                              t.base_cent, t.cuota_cent)
                     for t in sorted(factura.desglose, key=lambda t: t.id))
    return (LineaIva(factura.tratamiento_iva, factura.tipo_iva_pb, factura.base_cent,
                     factura.iva_cent),)


LEE_LINEAS_IVA = frozenset({
    "factura.desglose", "factura.tratamiento_iva", "factura.tipo_iva_pb", "factura.base_cent",
    "factura.iva_cent", "tramo_iva.id", "tramo_iva.tratamiento", "tramo_iva.tipo_iva_pb",
    "tramo_iva.base_cent", "tramo_iva.cuota_cent",
})

# Los prefijos del btw-id de los paises de la Union Europea (Grecia es EL; XI,
# Irlanda del Norte, para bienes). Que la contraparte sea de uno de ellos decide
# si el IVA trasladado va a 4b o 3b en vez de a 2a o 1e (config/btw.yaml).
PAISES_UE = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE",
    "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK", "XI",
})
NACIONAL, UE, FUERA_UE = "nacional", "ue", "fuera_ue"


def pais_iva(btw: str | None) -> str:
    """De donde es una contraparte para el IVA, por el prefijo de su btw-id.

    NL, o ningun btw-id, es nacional (el subcontratista de siempre, por
    confirmar con el asesor); un pais de la UE, ue; otras dos letras, fuera_ue.
    """
    texto = normalizar_btw(btw) or ""
    prefijo = texto[:2]
    if len(prefijo) < 2 or not prefijo.isalpha() or prefijo == "NL":
        return NACIONAL
    return UE if prefijo in PAISES_UE else FUERA_UE


def btw_de_contraparte(factura: Factura) -> str | None:
    """El btw-id impreso de la contraparte: el del emisor en una compra, el del receptor
    en una venta."""
    return factura.emisor_btw_doc if factura.sentido == ENTRANTE else factura.receptor_btw_doc


LEE_PAIS = frozenset({"factura.sentido", "factura.emisor_btw_doc", "factura.receptor_btw_doc"})


def huella_iva(sentido: str, pais: str, lineas: Iterable[LineaIva]) -> str:
    """Lo que la declaracion dice de una factura, como sha256: sus lineas de IVA, sin orden,
    y de donde es la contraparte si alguna linea es de IVA trasladado (decide la rubrica).

    No lleva la fecha ni la rubrica: cambiar el dia dentro del trimestre o el
    mapeo de config/btw.yaml no cambia lo declarado de la factura.
    """
    filas = sorted(([l.tratamiento, l.tipo_iva_pb, l.base_cent, l.cuota_cent] for l in lineas),
                   key=lambda f: json.dumps(f))
    trasladado = any(f[0] == "autoliquidacion" for f in filas)
    texto = json.dumps({"sentido": sentido, "pais": pais if trasladado else None,
                        "lineas": filas}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def huella_de_factura(factura: Factura) -> str:
    return huella_iva(factura.sentido, pais_iva(btw_de_contraparte(factura)),
                      lineas_iva(factura))


LEE_HUELLA_IVA = LEE_LINEAS_IVA | LEE_PAIS

# --------------------------------------------------------------- E0, E5 y E7 (paso 11)
#
# Como las de factura del paso 5, solo escriben lo que objetan. Una factura que
# no esta en euros (X1) no tiene importes que mirar: no dicen nada de ella.

_SIN_TRATAMIENTO = (None, "desconocido")


def e0(factura: Factura, _contexto: Any) -> list[Resultado]:
    """E0: falta la informacion del IVA: el tratamiento no se sabe o, con IVA normal, falta
    el tipo o la cuota (de la cabecera o de una fila del desglose).

    Un literal que esta en el papel y no se pudo leer no falta (eso es Q2). Sin
    desglose, el tipo puede venir de las lineas. Con desglose solo mira las
    filas con IVA normal: una fila de IVA trasladado no lleva cuota.
    """
    if factura.moneda is not None:
        return []
    if factura.tratamiento_iva in _SIN_TRATAMIENTO:
        return [fallo("E0", factura, "No se sabe cómo trata el IVA la factura: el régimen no "
                                     "consta.",
                      valores={"tratamiento_iva": factura.tratamiento_iva},
                      objetivos=(Objetivo("factura", factura.id, "tratamiento_iva"),))]
    if factura.tratamiento_iva != "estandar":
        return []
    if factura.desglose:
        incompletos = [t for t in factura.desglose
                       if (t.tratamiento or factura.tratamiento_iva) == "estandar"
                       and (t.tipo_iva_pb is None or t.base_cent is None
                            or t.cuota_cent is None)]
        if not incompletos:
            return []
        return [fallo("E0", factura, f"Con IVA normal, {len(incompletos)} tipo(s) del desglose "
                                     "no traen el tipo, la base o la cuota.",
                      valores={"tramos": sorted(([t.tipo_iva_pb, t.base_cent, t.cuota_cent]
                                                 for t in incompletos), key=json.dumps)},
                      objetivos=tuple(Objetivo("factura_iva", t.id, "cuota_cent")
                                      for t in incompletos))]
    faltan = []
    tipo_en_lineas = factura.lineas and all(l.tipo_iva_pb is not None for l in factura.lineas)
    if (factura.tipo_iva_pb is None and "tipo_iva_pb" not in factura.ilegibles
            and not tipo_en_lineas):
        faltan.append("tipo_iva_pb")
    if factura.iva_cent is None and "iva_cent" not in factura.ilegibles:
        faltan.append("iva_cent")
    if not faltan:
        return []
    nombres = {"tipo_iva_pb": "el tipo", "iva_cent": "la cuota"}
    return [fallo("E0", factura, "Con IVA normal falta " + " y ".join(
        nombres[c] for c in faltan) + " de IVA.",
                  valores={"faltan": faltan},
                  objetivos=tuple(Objetivo("factura", factura.id, c) for c in faltan))]


LEE_E0 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.moneda", "factura.tratamiento_iva", "factura.desglose",
    "factura.tipo_iva_pb", "factura.iva_cent", "factura.ilegibles", "factura.lineas",
    "linea.tipo_iva_pb", "tramo_iva.id", "tramo_iva.tratamiento", "tramo_iva.tipo_iva_pb",
    "tramo_iva.base_cent", "tramo_iva.cuota_cent",
})


def _preparar_e7(instantanea: Instantanea) -> dict[str, Any]:
    return {"elegible": {c.id: c.verlegd_elegible for c in instantanea.clientes},
            "habituales": frozenset(instantanea.politica.iva_tipos_habituales_pb)}


def _tipos(factura: Factura) -> set[int]:
    """Los tipos que aplica la factura: los del desglose o el de la cabecera, y los de sus
    lineas."""
    tipos = {t.tipo_iva_pb for t in factura.desglose if t.tipo_iva_pb is not None}
    if not factura.desglose and factura.tipo_iva_pb is not None:
        tipos.add(factura.tipo_iva_pb)
    tipos.update(l.tipo_iva_pb for l in factura.lineas if l.tipo_iva_pb is not None)
    return tipos


def e7(factura: Factura, contexto: dict[str, Any]) -> list[Resultado]:
    """E7: un tipo de IVA que no es de la lista de la politica (0, 9 y 21), o una venta sin
    IVA (trasladado al cliente, tipo cero o una linea al 0 %) a un cliente que el maestro no
    tiene marcado como que se le puede facturar asi.

    Dos resultados, cada uno con su clave: el tipo raro de cualquier factura y el
    tratamiento de una venta. Sin el cliente resuelto, el segundo da sin datos.
    """
    if factura.moneda is not None:
        return []
    salida: list[Resultado] = []
    tipos = _tipos(factura)
    raros = sorted(t for t in tipos if t not in contexto["habituales"])
    if raros:
        salida.append(fallo(
            "E7", factura, "Tipo de IVA poco habitual: "
            + ", ".join(f"{porcentaje(t)}%" for t in raros) + ".",
            clave="tipo", valores={"tipos": raros},
            objetivos=(Objetivo("factura", factura.id, "tipo_iva_pb"),)))
    if factura.sentido == SALIENTE and (
            factura.tratamiento_iva in ("autoliquidacion", "tipo_cero")
            or (factura.tratamiento_iva == "estandar" and 0 in tipos)):
        que = ("IVA trasladado" if factura.tratamiento_iva == "autoliquidacion"
               else "IVA al 0 %")
        if factura.cliente_id is None:
            salida.append(sin_datos("E7", factura, f"Venta con {que} a un cliente que no se "
                                                   "conoce: no se sabe si se le puede facturar "
                                                   "así.", clave="tratamiento",
                                    valores={"tratamiento_iva": factura.tratamiento_iva}))
        elif not contexto["elegible"].get(factura.cliente_id):
            salida.append(fallo(
                "E7", factura, f"Venta con {que} a un cliente que el maestro no tiene marcado "
                               "para facturarle así (verlegd_elegible).",
                clave="tratamiento", valores={"tratamiento_iva": factura.tratamiento_iva,
                                              "cliente_id": factura.cliente_id},
                objetivos=(Objetivo("factura", factura.id, "tratamiento_iva"),)))
    return salida


LEE_E7 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.moneda", "factura.sentido", "factura.tratamiento_iva",
    "factura.cliente_id", "factura.desglose", "factura.tipo_iva_pb", "factura.lineas",
    "linea.tipo_iva_pb", "tramo_iva.tipo_iva_pb", "instantanea.clientes", "parte.id",
    "parte.verlegd_elegible", "instantanea.politica", "politica.iva_tipos_habituales_pb",
})


def e5(instantanea: Instantanea) -> list[Resultado]:
    """E5: lo que un proveedor con KOR le ha facturado a BMS este ano se acerca al umbral.

    Un indicio, no una verificacion (validacion-facturas.md §1): el umbral es
    de todo lo que factura el proveedor, y aqui solo se ve lo suyo. Cuenta la
    base de sus facturas del ano natural de hoy (abonos en negativo, ni
    anuladas ni sustituidas), si sigue facturando con KOR (su ultima factura
    del ano), y avisa desde el porcentaje de la politica. El hallazgo es del
    proveedor (y del ano), con la factura desde la que esta por encima del aviso
    como relacionada (un abono que lo baja de nuevo lo quita); su evidencia es si
    ya pasa el umbral, no la suma, que sube con cada factura.
    """
    politica = instantanea.politica
    ano = instantanea.hoy.year
    del_ano: dict[int, list[Factura]] = defaultdict(list)
    for f in instantanea.facturas:
        if (f.sentido == ENTRANTE and f.proveedor_id is not None and en_juego(f)
                and f.moneda is None and f.base_cent is not None
                and f.fecha_factura is not None and f.fecha_factura.year == ano):
            del_ano[f.proveedor_id].append(f)
    aviso = politica.kor_umbral_cent * politica.kor_aviso_pct // 100
    salida = []
    for proveedor_id in sorted(del_ano):
        lista = sorted(del_ano[proveedor_id], key=lambda f: (f.fecha_factura, f.id))
        if lista[-1].tratamiento_iva != "kor":
            continue
        acumulado, cruza = 0, None
        for f in lista:
            acumulado += f.base_cent
            if acumulado < aviso:
                cruza = None
            elif cruza is None:
                cruza = f
        if cruza is None:
            continue
        pasado = acumulado >= politica.kor_umbral_cent
        salida.append(Resultado(
            "E5", "proveedor", proveedor_id, FALLO,
            f"Con KOR, le ha facturado {euros_texto(euros(acumulado))} en {ano}: "
            + ("pasa" if pasado else "se acerca a")
            + f" el umbral de {euros_texto(euros(politica.kor_umbral_cent))}. Es probable que "
              "tenga que empezar a repercutir IVA: confírmalo con el proveedor.",
            {"ano": ano, "umbral_cent": politica.kor_umbral_cent,
             "aviso_pct": politica.kor_aviso_pct, "pasado": pasado},
            str(ano), None, None, (Objetivo("factura", cruza.id, None, RELACIONADO),)))
    return salida


LEE_E5 = LEE_EN_JUEGO | frozenset({
    "instantanea.hoy", "instantanea.politica", "politica.kor_umbral_cent",
    "politica.kor_aviso_pct", "factura.id", "factura.sentido", "factura.proveedor_id",
    "factura.moneda", "factura.base_cent", "factura.fecha_factura", "factura.tratamiento_iva",
})

EVALUAR_E.update({"E0": solo_objeciones(e0), "E7": solo_objeciones(e7, _preparar_e7)})
