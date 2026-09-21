"""Genera el simulador de tarifas con los datos de las extracciones."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .facturacion import Tarifas, cargar_tarifas, lineas_para_simulador
from .simulador_assets import PLANTILLA


def render_html(datos: dict[str, Any]) -> str:
    payload = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    # Dentro de un bloque script el tokenizador reacciona a "<": escaparlo
    # entero evita que un "<!--<script" incrustado en un PDF cierre el bloque.
    payload = payload.replace("<", "\\u003c")
    return PLANTILLA.replace("__DATOS__", payload)


def escribir_simulador(
    registros: list[dict[str, Any]],
    destino: str | Path,
    tarifas: Tarifas | str | None = "config/tarifas.yaml",
) -> Path:
    if not isinstance(tarifas, Tarifas):
        tarifas = cargar_tarifas(tarifas)
    datos = lineas_para_simulador(registros, tarifas)
    destino = Path(destino)
    destino.write_text(render_html(datos), encoding="utf-8")
    return destino
