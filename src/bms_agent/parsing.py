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

__all__ = ["ParseError", "parse_amount", "parse_percentage", "parse_iso_date", "normalize_iban"]


class ParseError(ValueError):
    """El texto no representa un valor interpretable sin adivinar."""


_CURRENCY = re.compile(r"[€$£]|\b(?:eur|euro|euros|usd)\b", re.IGNORECASE)
_SPACES = re.compile(r"[\s  ]+")


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
    """Convierte un importe impreso en Decimal.

    Regla de separadores:

    - Si aparecen punto y coma, el ultimo de los dos es el decimal.
    - Si solo aparece uno, decide el numero de digitos que le siguen:
      uno o dos lo hacen decimal, exactamente tres lo hacen de millares.
    - Cualquier otra forma se rechaza en vez de adivinarse.

    Nunca devuelve un valor aproximado: si el texto es ambiguo, lanza
    ParseError y la factura se queda en la cola de revision.
    """
    if raw is None:
        raise ParseError("importe vacio")

    text = _SPACES.sub("", _CURRENCY.sub("", str(raw)))
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
