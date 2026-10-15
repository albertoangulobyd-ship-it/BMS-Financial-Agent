"""Reglas de datos de pago. En esta fase, F1: el IBAN impreso pasa el digito de control.

El pago se construye siempre con el IBAN del maestro, nunca con el del
documento (regla 1 de arquitectura.md): estas reglas no eligen el numero,
solo detectan la discrepancia. Ninguna se puede anular y todas son
pegajosas: un IBAN raro que deja de verse no es un problema resuelto.
F2 a F10 llegan con el registro de cuentas (paso 5) y el banco (paso 7).
"""

from __future__ import annotations

from .base import (
    FALLO,
    OK,
    SIN_DATOS,
    Comprobacion,
    Factura,
    Objetivo,
    Politica,
    Resultado,
    resultado_de,
)


def validar_iban(iban: str | None) -> bool:
    """Digito de control modulo 97 (ISO 13616).

    Aritmetica pura, sin sistemas externos. Un IBAN que no pasa esta
    comprobacion esta mal transcrito o es inventado, y en los dos casos el
    pago no puede salir.
    """
    texto = "".join(str(iban or "").split()).upper()
    if not (15 <= len(texto) <= 34) or not texto[:2].isalpha() or not texto[2:4].isdigit():
        return False
    if not texto.isalnum():
        return False
    movido = texto[4:] + texto[:4]
    digitos = "".join(str(int(c, 36)) if c.isalpha() else c for c in movido)
    return int(digitos) % 97 == 1


def iban(texto: str | None) -> Comprobacion:
    """F1: el IBAN impreso es sintacticamente valido."""
    if not texto:
        return Comprobacion(SIN_DATOS, "La factura no lleva IBAN.")
    limpio = "".join(str(texto).split()).upper()
    if validar_iban(limpio):
        return Comprobacion(OK, f"{limpio} pasa el digito de control.")
    return Comprobacion(FALLO, f"{limpio} no pasa el digito de control modulo 97.")


def f1(factura: Factura, _politica: Politica) -> list[Resultado]:
    comprobacion = iban(factura.iban_doc)
    objetivos = ((Objetivo("factura", factura.id, "iban_doc"),)
                 if comprobacion.resultado == FALLO else ())
    limpio = "".join(str(factura.iban_doc or "").split()).upper() or None
    return [resultado_de("F1", factura, comprobacion, valores={"iban": limpio},
                         objetivos=objetivos)]


LEE_F1 = frozenset({"factura.iban_doc"})
