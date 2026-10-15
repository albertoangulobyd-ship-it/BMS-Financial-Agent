"""Ajustes del extractor.

El modelo es configurable a proposito. Medir si un modelo mas barato
mantiene la precision es una de las salidas de la fase 0, y esa es una
decision con datos, no una suposicion de diseno.

El modelo por defecto cambio a claude-opus-5-5 en la misma pasada que el
esquema v2 (spec §10): cada documento que se vuelva a leer se paga una vez,
con el modelo y el esquema nuevos a la vez, y no dos. Lo ya extraido no se
vuelve a pagar al cambiar estas versiones (politica CONSERVAR de cache.py);
volver a leerlo es `bms-agent reextraer`, con presupuesto.
"""

from __future__ import annotations

import os

# Version del prompt y del esquema. Se guardan con cada extraccion para
# poder saber, meses despues, por que una factura se leyo mal.
PROMPT_VERSION = "extract/2026-10-15.1"
SCHEMA_VERSION = "2"

DEFAULT_MODEL = "claude-opus-5-5"

# Margen amplio: una factura con muchas lineas produce un JSON largo, y en
# Opus 5.5 el razonamiento, que no se puede apagar, cuenta dentro de este
# limite.
DEFAULT_MAX_TOKENS = 16000

# El esfuerzo se fija siempre, no se deja al valor por defecto del modelo:
# Opus 5.5 piensa siempre y su esfuerzo por defecto es medium, pero un valor
# implicito puede cambiar con el modelo y moveria el coste y la precision sin
# que nada lo dijera. Se cambia con BMS_EXTRACT_EFFORT y se vuelve a medir.
DEFAULT_EFFORT = "medium"
ESFUERZOS = ("low", "medium", "high", "xhigh", "max")


def model_id() -> str:
    return os.environ.get("BMS_EXTRACT_MODEL", DEFAULT_MODEL)


def max_tokens() -> int:
    return int(os.environ.get("BMS_EXTRACT_MAX_TOKENS", DEFAULT_MAX_TOKENS))


def effort() -> str:
    """El esfuerzo de la extraccion. Un valor que la API no admite se rechaza aqui, antes de pagar."""
    valor = os.environ.get("BMS_EXTRACT_EFFORT", DEFAULT_EFFORT).strip().lower()
    if valor not in ESFUERZOS:
        raise ValueError(
            f"BMS_EXTRACT_EFFORT={valor!r} no es un esfuerzo valido ({', '.join(ESFUERZOS)})"
        )
    return valor
