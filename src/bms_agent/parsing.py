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
    "normalize_iban",
    "parse_amount",
    "parse_importe",
    "parse_iso_date",
    "parse_percentage",
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
