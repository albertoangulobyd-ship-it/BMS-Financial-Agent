"""El catalogo en castellano (es.json, paso 16): que es castellano de verdad y de oficina.

La forma (las mismas claves, condiciones y marcadores que nl y en), los casos
y el renderizador se prueban en test_textos.py para los tres idiomas. Aqui va
lo que solo tiene sentido para el castellano:

- que no queda ningun texto en neerlandes ni en ingles (una lista de palabras
  que solo existen en esos idiomas), salvo los terminos de BMS que se dejan
  tal cual: zzp'er, BTW, Object, PO, Exact, TRNSPRNT, IBAN, KvK, KOR, PDF;
- que un texto igual al ingles solo puede ser uno de esos terminos (Total,
  Manual, PO): una frase copiada sin traducir no pasa;
- que se escribe con tildes (numero sin tilde es una errata, no un estilo);
- que el impuesto se llama siempre BTW, como en la empresa, y nunca IVA;
- que el importe, la fecha, el trimestre y el IBAN salen igual que en
  neerlandes: el formato no depende del idioma;
- que ninguna etiqueta promete lo que el sistema no hace (aprobar, pagar,
  presentar), tampoco en castellano.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from bms_agent import textos

ES = textos.catalogo("es")
EN = textos.catalogo("en")
NL = textos.catalogo("nl")


def _textos(catalogo: dict[str, Any], camino: str = "") -> Iterator[tuple[str, str]]:
    """Cada texto del catalogo con su camino (sin las condiciones ni la clave idioma)."""
    if isinstance(catalogo, dict):
        for k, v in catalogo.items():
            if k not in ("cuando", "idioma"):
                yield from _textos(v, f"{camino}.{k}" if camino else k)
    elif isinstance(catalogo, list):
        for i, v in enumerate(catalogo):
            yield from _textos(v, f"{camino}[{i}]")
    else:
        yield camino, catalogo


def _sin_marcadores(texto: str) -> str:
    """El texto sin {marcadores}: llevan claves del codigo ({pendiente_cent}), no son texto."""
    return re.sub(r"\{[^{}]*\}", "", texto)


# Palabras que solo existen en neerlandes: un texto de es.json que las lleva se quedo
# sin traducir. Sin las que tambien son castellanas ("de", "en", "van", "te"), y sin
# los terminos de BMS (zzp'er, Belastingdienst, verlegd).
_NEERLANDES = re.compile(
    r"\b(factuur|facturen|factuurregel|leverancier|leveranciers|klant|klanten|bedrag|"
    r"bedragen|btw-nummer|niet|geen|het|een|voor|wordt|worden|zijn|met|ook|nog|bij|naar|"
    r"uit|deze|dit|heeft|betaald|betaling|rekening|gegevens|stamgegevens|periode|datum|"
    r"regel|regels|controle|bevinding|uren|inkoop|verkoop|wederpartij|aangifte|kwartaal|"
    r"ontbreekt|als|dan|maar|wel|zonder|wat|staat|komt|overeen|openstaand|vervallen|"
    r"goedgekeurd|ja|nee)\b", re.IGNORECASE)

# Palabras que solo existen en ingles. Sin "no" ni "has" (tambien castellanas: "has
# rellenado"), ni "Object" (termino de BMS).
_INGLES = re.compile(
    r"\b(the|and|invoice|invoices|provider|providers|amount|amounts|paid|payment|payments|"
    r"with|without|from|for|not|is|are|was|were|been|this|that|which|there|line|lines|"
    r"rate|rates|hours|week|missing|check|checked|due|overdue|master|data|of|to|on|or|by|"
    r"at|be|it|vat|credit|note|shift|shifts|planning|booked|yes|unknown|already|still|"
    r"yet|after|before|until|should|must|can|cannot|reviewed|approved|filed)\b",
    re.IGNORECASE)

# Lo que puede ser igual que en ingles: los terminos de BMS y las pocas palabras que se
# escriben igual en los dos idiomas.
_IGUALES = {"no", "Total", "IBAN", "Exact", "TRNSPRNT", "Manual", "PO", "Object", "Objects",
            "Normal", "general"}


def test_no_queda_neerlandes_ni_ingles_en_castellano() -> None:
    for camino, valor in _textos(ES):
        texto = _sin_marcadores(valor)
        for idioma, palabras in (("nl", _NEERLANDES), ("en", _INGLES)):
            encontrado = palabras.search(texto)
            assert encontrado is None, (idioma, camino, encontrado and encontrado.group(0))


def test_las_listas_de_palabras_ven_un_texto_sin_traducir() -> None:
    assert _NEERLANDES.search("De factuur is vervallen; het btw-bedrag ontbreekt")
    assert _INGLES.search("The invoice is overdue; the VAT amount is missing")
    assert _INGLES.search("Ver factura: invoice number")
    for bien in ("La factura está vencida; falta el importe del BTW",
                 "Autónomo (zzp'er)", "Autoliquidación (BTW verlegd)",
                 "Revisa lo que has rellenado. No se paga nada.",
                 "Anota que el trimestre se presentó en el portal de Hacienda (Belastingdienst).",
                 "El Object de la línea es de otro cliente; la PO no lo cubre."):
        assert not _NEERLANDES.search(bien) and not _INGLES.search(bien), bien


def test_un_texto_igual_al_ingles_es_solo_un_termino() -> None:
    """Una frase que sale igual que en ingles se quedo sin traducir: solo pueden coincidir
    los terminos de BMS (Exact, PO, IBAN...) y palabras como Total o Manual."""
    ingles = dict(_textos(EN))
    neerlandes = dict(_textos(NL))
    for camino, valor in _textos(ES):
        if valor not in (ingles[camino], neerlandes[camino]):
            continue
        palabras = set(re.findall(r"[^\W\d_]+", _sin_marcadores(valor)))
        assert palabras <= _IGUALES, (camino, valor)


# Palabras que en castellano llevan tilde siempre: sin ella son una errata. Las que
# cambian de sentido con la tilde (esta/está, aun/aún, mas/más, solo) no estan.
_SIN_TILDE = re.compile(
    r"\b(numero|numeros|dias|telefono|declaracion|planificacion|importacion|exportacion|"
    r"codigo|direccion|facturacion|verificacion|linea|lineas|tambien|segun|despues|"
    r"automatico|automaticamente|valido|valida|modulo|calculo|ningun|algun|aqui|alli|asi|"
    r"todavia|ultimo|ultima|ultimos|ultimas|excepcion|revision|relacion|objecion|"
    r"anomalia|categoria|electronico|credito|habiles|minimo|maximo|pagina)\b")


def test_se_escribe_con_tildes() -> None:
    """Los textos de la app, a diferencia del codigo, llevan tildes: las personas leen
    castellano, no identificadores."""
    for camino, valor in _textos(ES):
        encontrado = _SIN_TILDE.search(_sin_marcadores(valor).lower())
        assert encontrado is None, (camino, encontrado and encontrado.group(0))


def test_la_comprobacion_de_tildes_ve_una_errata() -> None:
    assert _SIN_TILDE.search("el numero de dias habiles")
    assert not _SIN_TILDE.search("el número de días hábiles; esta factura aún no está")


def test_el_impuesto_es_siempre_btw() -> None:
    """La empresa dice BTW (un termino de BMS, como Object o PO): un catalogo que mezcla
    IVA y BTW hace pensar que son dos impuestos."""
    for camino, valor in _textos(ES):
        assert not re.search(r"\bIVA\b|\bVAT\b|\bbtw\b", _sin_marcadores(valor)), camino
    assert ES["categorias"]["iva"]["etiqueta"] == "BTW"


def test_ninguna_etiqueta_promete_lo_que_el_sistema_no_hace() -> None:
    for nombre, texto in ES["acciones"].items():
        etiqueta = texto["etiqueta"].lower()
        assert not re.search(r"aprob|\bpagar\b|\bpresentar\b|\bpaga\b", etiqueta), nombre
    for clave in ("marcar_pagada", "marcar_revisada", "btw_anotar_presentacion"):
        frase = ES["acciones"][clave]["confirmar"]
        assert "no" in frase.lower(), clave
    assert ES["acciones"]["marcar_pagada"]["confirmar"].endswith("El sistema no paga nada.")


def test_los_formatos_no_dependen_del_idioma() -> None:
    """Importes, fechas, trimestres e IBAN se escriben igual en los tres: formato
    neerlandes, euro delante, sin floats."""
    plantilla = "{a|dinero} {b|fecha} {c|trimestre} {d|iban} {e|pct} {f|horas} {g|tarifa}"
    valores = {"a": -123456, "b": "2026-10-16", "c": "2026-T3", "d": "NL91ABNA0417164300",
               "e": 2100, "f": 37500, "g": 425050}
    textos_ = {i: textos.renderizar(plantilla, valores, i) for i in textos.IDIOMAS}
    assert textos_["es"] == textos_["nl"] == textos_["en"] == (
        "€ -1.234,56 16-10-2026 Q3 2026 NL91 ABNA 0417 1643 00 21% 37,5 € 42,505")


def test_si_y_no_y_los_codigos_en_castellano() -> None:
    assert textos.renderizar("{a} {b}", {"a": True, "b": False}, "es") == "sí no"
    assert textos.renderizar("{x|codigo}", {"x": ["kor", "autoliquidacion"]}, "es") == (
        "la KOR (sin BTW), autoliquidación del BTW")
    pintado = textos.pintar("{x|codigo}", {"x": "otro"}, "es")
    assert pintado.texto == "otro" and pintado.faltan == ("codigo:otro",)


def test_un_detalle_entero_en_castellano() -> None:
    """Un hallazgo de verdad escrito desde sus valores, con sus formatos."""
    assert textos.detalle("K2", "fallo", {
        "total_cent": 290279, "pagado_cent": 100000, "fuente": "manual",
        "pendiente_cent": 190279}, "es").texto == (
        "Total €\u00a02.902,79, pagado €\u00a01.000,00 (anotado a mano), pendiente "
        "€\u00a01.902,79.")
    assert textos.detalle("Q1", "fallo", {"faltan": ["numero", "fecha"]}, "es").texto == (
        "Falta en el documento: número de factura, fecha de factura.")
    # Sin plantilla para un resultado, el significado de la regla, nunca el espanol de la API.
    assert textos.detalle("Q4", "sin_datos", {}, "es").texto == ES["reglas"]["Q4"]["significa"]
