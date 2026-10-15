#!/usr/bin/env python3
"""Escribe el JSON esperado de cada mapeo de config/importacion con su fichero de ejemplo.

    python scripts/regenerar_contratos.py [mapeo ... | config-tarifas]

Es el test de contrato de cada formato (tests/test_importadores.py): lo que
sale de leer tests/fixtures/importacion/<mapeo>.csv con ese mapeo tiene que
ser, byte a byte, tests/fixtures/importacion/<mapeo>.esperado.json. Se
regenera solo cuando un mapeo cambia a proposito, y el cambio se mira entero
en el diff antes de darlo por bueno.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from bms_agent.importadores.tabular import contrato, mapeos  # noqa: E402
from bms_agent.importadores.tarifas import contrato_semilla  # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures" / "importacion"
# La semilla de una vez (config/tarifas.yaml), con la copia fija de los tests.
SEMILLA = RAIZ / "tests" / "fixtures" / "v1" / "tarifas.yaml"


def main() -> int:
    pedidos = set(sys.argv[1:])
    for mapeo in mapeos(RAIZ / "config" / "importacion"):
        if pedidos and mapeo.id not in pedidos:
            continue
        contenido = (FIXTURES / f"{mapeo.id}.csv").read_bytes()
        texto = json.dumps(contrato(mapeo, contenido), ensure_ascii=False, indent=2) + "\n"
        (FIXTURES / f"{mapeo.id}.esperado.json").write_text(texto, encoding="utf-8")
        print(f"{mapeo.id}: escrito")
    if not pedidos or "config-tarifas" in pedidos:
        semilla = contrato_semilla(SEMILLA.read_text(encoding="utf-8"))
        (FIXTURES / "config-tarifas.esperado.json").write_text(
            json.dumps(semilla, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("config-tarifas: escrito")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
