"""Conversion de los textos literales de la factura a tipos.

El extractor copia los importes tal como estan impresos y no los convierte.
La conversion vive aqui, en codigo con tests, por una razon concreta: una
factura neerlandesa escribe ocho mil setecientos cuarenta euros como
"8.740,00", con el punto de millares y la coma decimal. Pedirle al modelo
que normalice eso es una conversion silenciosa que no se puede auditar.
Pedirle el texto literal y convertirlo aqui si se puede probar.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = [
    "ParseError",
    "detectar_moneda",
    "es_unidad_hora",
    "normalizar_referencia",
    "normalize_iban",
    "parse_amount",
    "parse_importe",
    "parse_iso_date",
    "parse_percentage",
    "parse_plazo_pago",
]


class ParseError(ValueError):
    """El texto no representa un valor interpretable sin adivinar."""


# Los marcadores se acotan por letras, no con \b: entre "USD" y "2" no hay
# limite de palabra (letras y digitos son los dos caracteres de palabra), y
# con \b un "USD2,500.00" o un "2.500,00EUR" pasaban sin marcador.
_EURO = re.compile(r"€|(?<![a-z])(?:eur|euro|euros)(?![a-z])", re.IGNORECASE)
_SPACES = re.compile(r"[\s  ]+")

# Un "$" con las letras que lleva pegadas delante: "US$", "C$", "R$", "CAD$".
# Se mira el prefijo entero porque buscar "c$" dentro de "cad$" no lo
# encontraba y el "$" a secas lo leia como dolar estadounidense.
_DOLAR = re.compile(r"([a-z]*)\$", re.IGNORECASE)
_PREFIJOS_DOLAR = {
    "": "USD", "us": "USD", "usd": "USD",
    "c": "CAD", "ca": "CAD", "cad": "CAD",
    "a": "AUD", "au": "AUD", "aud": "AUD",
    "nz": "NZD", "nzd": "NZD",
    "hk": "HKD", "hkd": "HKD",
    "s": "SGD", "sg": "SGD", "sgd": "SGD",
    "r": "BRL", "brl": "BRL",
    "mx": "MXN", "mxn": "MXN",
}
# Moneda con "$" de prefijo desconocido. No es un codigo ISO, como "KR": no se
# sabe cual es, pero si que no es el euro, que es lo unico que decide aqui.
DOLAR_SIN_PAIS = "$"

_SIMBOLOS_MONEDA = (
    ("£", "GBP"), ("¥", "JPY"), ("₹", "INR"), ("₺", "TRY"), ("₽", "RUB"),
    ("zł", "PLN"),
)
_CODIGOS_MONEDA = re.compile(
    r"(?<![a-z])(usd|gbp|chf|pln|sek|nok|dkk|czk|huf|ron|bgn|try|jpy|cny|cad|aud"
    r"|nzd|hkd|sgd|inr|zar|rub|brl|mxn)(?![a-z])",
    re.IGNORECASE,
)
# "kr" sirve para la corona danesa, la noruega y la sueca: no se puede decir
# cual, pero si que no es el euro, que es lo unico que importa aqui.
_CORONA = re.compile(r"(?<![a-z])kr(?![a-z])\.?", re.IGNORECASE)


def detectar_moneda(raw: str | None) -> str | None:
    """Moneda que declara un importe impreso, o None si no declara ninguna.

    Devuelve el codigo ISO 4217 cuando el marcador lo determina ("$" a secas
    se lee como USD, "R$" como BRL), "$" para un dolar de prefijo desconocido,
    "KR" para la corona sin pais, "EUR" para el euro y None si el literal no
    lleva marcador. Si conviven el euro y otra moneda, gana la otra: un
    importe que dice dos monedas no puede sumarse como euros.

    Existe por la regla X1. Antes, el simbolo del dolar se quitaba igual que
    el del euro y una factura en dolares entraba en los totales como si fuera
    en euros, sin que nada lo dijera.
    """
    if raw is None:
        return None
    texto = str(raw).lower()
    if m := _DOLAR.search(texto):
        return _PREFIJOS_DOLAR.get(m.group(1), DOLAR_SIN_PAIS)
    for simbolo, codigo in _SIMBOLOS_MONEDA:
        if simbolo in texto:
            return codigo
    if m := _CODIGOS_MONEDA.search(texto):
        return m.group(1).upper()
    if _CORONA.search(texto):
        return "KR"
    if _EURO.search(texto):
        return "EUR"
    return None


def _quitar_monedas(texto: str) -> str:
    """Quita del literal cualquier marcador de moneda reconocido."""
    texto = _DOLAR.sub("", texto)
    texto = _EURO.sub("", _CODIGOS_MONEDA.sub("", _CORONA.sub("", texto)))
    for simbolo, _codigo in _SIMBOLOS_MONEDA:
        texto = re.sub(re.escape(simbolo), "", texto, flags=re.IGNORECASE)
    return texto


def _join_thousands(text: str, sep: str, raw: str) -> str:
    """Quita el separador de millares comprobando que los grupos son de tres.

    Sin esta comprobacion, "12.34,567" se leeria como 1234,567 en vez de
    rechazarse, y un importe malformado entraria en el sistema como si fuera
    bueno.
    """
    head, *groups = text.split(sep)
    if not head or len(head) > 3 or any(len(g) != 3 for g in groups):
        raise ParseError(f"agrupacion de millares invalida: {raw!r}")
    return head + "".join(groups)


def parse_amount(raw: str) -> Decimal:
    """Convierte un importe impreso EN EUROS en Decimal.

    Regla de separadores:

    - Si aparecen punto y coma, el ultimo de los dos es el decimal.
    - Si solo aparece uno, decide el numero de digitos que le siguen:
      uno o dos lo hacen decimal, exactamente tres lo hacen de millares.
    - Cualquier otra forma se rechaza en vez de adivinarse.

    Nunca devuelve un valor aproximado: si el texto es ambiguo, lanza
    ParseError y la factura se queda en la cola de revision.

    Solo se quita el marcador del euro. Un importe en otra moneda lanza
    ParseError: devolver 2500 por "$2,500.00" es sumar dolares como euros.
    Quien necesite el importe y su moneda usa parse_importe.
    """
    if raw is None:
        raise ParseError("importe vacio")

    moneda = detectar_moneda(raw)
    if moneda not in (None, "EUR"):
        raise ParseError(f"importe en {moneda}, no en euros: {raw!r}")
    return _parse_numero(_EURO.sub("", str(raw)), raw)


def parse_importe(raw: str) -> tuple[Decimal, str | None]:
    """Importe impreso y la moneda que declara, sin convertir nada.

    La moneda es la de detectar_moneda: None si el literal no lleva marcador.
    Sirve para comparar importes de cualquier moneda sin mezclarlas; para
    sumar, el codigo tiene que mirar la moneda antes.
    """
    if raw is None:
        raise ParseError("importe vacio")
    return _parse_numero(_quitar_monedas(str(raw)), raw), detectar_moneda(raw)


def _parse_numero(texto: str, raw: Any) -> Decimal:
    """El numero de un importe que ya no lleva marcador de moneda."""
    text = _SPACES.sub("", texto)
    if not text:
        raise ParseError("importe vacio")

    negative = False
    if text.startswith("-") or text.startswith("−"):
        negative, text = True, text[1:]
    elif text.endswith("-"):
        # Formato de algunos exportes contables: el signo va detras.
        negative, text = True, text[:-1]
    if text.startswith("+"):
        text = text[1:]

    if not text or not re.fullmatch(r"[0-9.,]+", text):
        raise ParseError(f"importe no interpretable: {raw!r}")

    has_dot, has_comma = "." in text, "," in text

    if has_dot and has_comma:
        decimal_sep = "." if text.rfind(".") > text.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        integer_part, _, decimal_part = text.rpartition(decimal_sep)
        text = _join_thousands(integer_part, thousands_sep, raw) + "." + decimal_part
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        tail = len(text) - text.rfind(sep) - 1
        if tail in (1, 2):
            text = text.replace(sep, ".")
        elif tail == 3:
            text = _join_thousands(text, sep, raw)
        else:
            raise ParseError(f"separador ambiguo en {raw!r}")

    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ParseError(f"importe no interpretable: {raw!r}") from exc

    return -value if negative else value


def parse_percentage(raw: str) -> Decimal:
    """Convierte un tipo impositivo impreso ("21%", "21,0 %", "9") en Decimal."""
    if raw is None:
        raise ParseError("porcentaje vacio")
    text = _SPACES.sub("", str(raw)).rstrip("%")
    if not text:
        raise ParseError("porcentaje vacio")
    value = parse_amount(text)
    if not (Decimal(0) <= value <= Decimal(100)):
        raise ParseError(f"porcentaje fuera de rango: {raw!r}")
    return value


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_NL = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")


def parse_iso_date(raw: str) -> date:
    """Convierte una fecha a date.

    Se pide al extractor que emita ISO. Se acepta ademas el formato
    neerlandes dia-mes-ano porque aparece cuando el modelo copia en vez de
    normalizar. No se acepta mes-dia-ano: "05/06/2026" no se puede resolver
    sin adivinar, y adivinar una fecha desplaza un periodo de facturacion.
    """
    if raw is None:
        raise ParseError("fecha vacia")
    text = _SPACES.sub("", str(raw))

    if m := _ISO.match(text):
        y, mo, d = (int(g) for g in m.groups())
    elif m := _NL.match(text):
        d, mo, y = (int(g) for g in m.groups())
    else:
        raise ParseError(f"fecha no interpretable: {raw!r}")

    try:
        return date(y, mo, d)
    except ValueError as exc:
        raise ParseError(f"fecha invalida: {raw!r}") from exc


def normalize_iban(raw: str) -> str:
    """Quita espacios y pasa a mayusculas. No valida: eso es la regla F1."""
    if raw is None:
        raise ParseError("IBAN vacio")
    return _SPACES.sub("", str(raw)).upper()


# Unidades que son horas, en minusculas y sin puntuacion. Neerlandes, ingles y
# las abreviaturas alemanas que aparecen en facturas de la frontera.
_UNIDADES_HORA = frozenset({
    "uur", "uren", "u", "manuur", "manuren", "werkuur", "werkuren",
    "h", "hr", "hrs", "hour", "hours", "std", "stunde", "stunden",
})


def es_unidad_hora(unidad: str | None) -> bool:
    """La unidad impresa en una linea es la hora.

    Antes se miraba solo si empezaba por "uur", y una linea en "uren", "u" o
    "hours" daba cero horas sin avisar: el panel, la proyeccion de venta y el
    simulador perdian esas horas en silencio. Se sigue aceptando todo lo que
    empieza por "uur" para no perder nada de lo que ya contaba.

    Decide la primera palabra de la unidad ("u." es "u", "uren (avond)" es
    "uren"). Una unidad desconocida no es hora: es mejor declararla aparte,
    como hace el panel, que sumarla como lo que no es.
    """
    texto = str(unidad or "").strip().lower()
    if not texto:
        return False
    if texto.startswith("uur"):
        return True
    palabra = next((p for p in re.split(r"[^a-z]+", texto) if p), "")
    return palabra in _UNIDADES_HORA


_SEPARADORES_REFERENCIA = re.compile(r"[\s\u00a0\u202f.\-/_]+")


def normalizar_referencia(raw: str | None) -> str | None:
    """Un numero de factura o una referencia, en la forma con la que se comparan.

    Mayusculas y sin espacios, puntos, guiones, barras ni guiones bajos:
    "2026-4471", "2026 4471" y "2026/4471" son el mismo numero para B2. No
    se quitan ceros a la izquierda: "2026-012" y "2026-12" pueden ser dos
    facturas distintas, y juntarlas daria un duplicado que no lo es.
    Devuelve None si no queda nada.
    """
    if raw is None:
        return None
    texto = _SEPARADORES_REFERENCIA.sub("", str(raw)).upper()
    return texto or None


# Un plazo de pago impreso: "binnen 30 dagen", "30 dgn netto", "within 14 days",
# "2 weken". Los dias laborables y los meses no se convierten: dependen del
# calendario, y un plazo adivinado mueve un vencimiento.
_PLAZO_DIAS = re.compile(
    r"(?<![\d,.])(\d{1,3})\s*(?:kalender\s*)?(?:dagen|dag|dgn|days|day|d)(?![a-z])", re.IGNORECASE)
_PLAZO_SEMANAS = re.compile(r"(?<![\d,.])(\d{1,2})\s*(?:weken|week|weeks|wk)(?![a-z])",
                            re.IGNORECASE)
# "8 of 14 dagen", "30-60 days": dos plazos que comparten la unidad.
_PLAZO_ALTERNATIVA = re.compile(
    r"(?<![\d,.])(\d{1,3})\s*(?:of|en|tot|or|to|-|\u2013)\s*\d{1,3}\s*"
    r"(?:kalender\s*)?(?:dagen|dag|dgn|days|day|d|weken|week|weeks|wk)(?![a-z])", re.IGNORECASE)
_PLAZO_LABORABLES = re.compile(r"werkdag|working\s*day|business\s*day", re.IGNORECASE)
_PLAZO_MESES = re.compile(r"(?<![a-z])(?:maand|maanden|month|months)(?![a-z])", re.IGNORECASE)
_PLAZO_NETO = re.compile(r"(?:netto|net)\s*(\d{1,3})|(\d{1,3})\s*(?:dagen|dgn|days)?\s*(?:netto|net)(?![a-z])",
                         re.IGNORECASE)
_PLAZO_INMEDIATO = re.compile(
    r"per\s*omgaande|contant|bij\s*ontvangst|direct\s*(?:te\s*)?betal|immediately|upon\s*receipt|"
    r"on\s*receipt|due\s*on\s*receipt", re.IGNORECASE)
_PLAZO_NUMERO_SUELTO = re.compile(r"^\s*(?:netto\s*|net\s*)?(\d{1,3})\s*(?:netto|net)?\s*$",
                                  re.IGNORECASE)


def parse_plazo_pago(raw: str | None) -> int:
    """Los dias de un plazo de pago impreso (payment_terms_raw, v2).

    "Betaling binnen 30 dagen" son 30; "2 weken", 14; "per omgaande" o
    "contant", 0. Si el texto da dos plazos distintos (un descuento por
    pronto pago y el neto), vale el que dice "netto"; si ninguno lo dice, no
    se elige. Los dias laborables y los meses se rechazan en vez de
    convertirse: un mes no tiene un numero fijo de dias, y un dia laborable
    depende de festivos que aqui no se saben.

    El vencimiento que se calcula con esto es "calculado" (spec §10): el
    modelo nunca lo calcula, y el impreso, si lo hay, manda.
    """
    if raw is None:
        raise ParseError("plazo vacio")
    texto = _SPACES.sub(" ", str(raw)).strip()
    if not texto:
        raise ParseError("plazo vacio")
    if _PLAZO_LABORABLES.search(texto):
        raise ParseError(f"plazo en dias laborables, no se convierte: {raw!r}")

    plazos = {int(m.group(1)) for m in _PLAZO_DIAS.finditer(texto)}
    plazos |= {int(m.group(1)) * 7 for m in _PLAZO_SEMANAS.finditer(texto)}
    # "8 of 14 dagen" lleva un plazo sin unidad propia; con el, ya no hay uno solo.
    alternativa = _PLAZO_ALTERNATIVA.search(texto) is not None
    if not plazos and (m := _PLAZO_NUMERO_SUELTO.match(texto)):
        plazos = {int(m.group(1))}
    if not plazos:
        if _PLAZO_MESES.search(texto):
            raise ParseError(f"plazo en meses, no se convierte: {raw!r}")
        if _PLAZO_INMEDIATO.search(texto):
            return 0
        raise ParseError(f"plazo no interpretable: {raw!r}")
    if len(plazos) == 1 and not alternativa:
        return plazos.pop()
    netos = {int(m.group(1) or m.group(2)) for m in _PLAZO_NETO.finditer(texto)}
    if len(netos) == 1 and netos <= plazos:
        return netos.pop()
    raise ParseError(f"el texto da varios plazos y ninguno es el neto: {raw!r}")
