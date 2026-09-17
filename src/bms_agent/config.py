"""Ajustes del extractor.

El modelo es configurable a proposito. Medir si un modelo mas barato
mantiene la precision es una de las salidas de la fase 0, y esa es una
decision con datos, no una suposicion de diseno.
"""

from __future__ import annotations

import os

# Version del prompt y del esquema. Se guardan con cada extraccion para
# poder saber, meses despues, por que una factura se leyo mal.
PROMPT_VERSION = "extract/2026-09-17.1"
SCHEMA_VERSION = "1"

DEFAULT_MODEL = "claude-opus-5"

# Margen amplio: una factura con muchas lineas produce un JSON largo.
DEFAULT_MAX_TOKENS = 16000


def model_id() -> str:
    return os.environ.get("BMS_EXTRACT_MODEL", DEFAULT_MODEL)


def max_tokens() -> int:
    return int(os.environ.get("BMS_EXTRACT_MAX_TOKENS", DEFAULT_MAX_TOKENS))
