#!/usr/bin/env python3
"""Regenera la foto de referencia de construir_datos desde tests/fixtures/v1.

    python scripts/regenerar_golden.py

Escribe tests/golden/construir_datos_v1.json. Solo hay que ejecutarlo cuando
un paso de la V1 cambia a proposito lo que sale del panel, y ese cambio se
explica en docs/v1/registro.md. Si la foto cambia sin que nadie lo haya
decidido, es un fallo, no una foto vieja.

No regenera construir_datos_v1_antes_sin_afectadas.json: esa es la foto de
antes de las correcciones del paso 0 y no se vuelve a escribir nunca.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from bms_agent.dashboard import construir_datos  # noqa: E402
from bms_agent.report import load_records  # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures" / "v1"
DESTINO = RAIZ / "tests" / "golden" / "construir_datos_v1.json"


def serializar(datos: dict) -> str:
    """La misma serializacion que comparan los tests, byte a byte."""
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    registros = load_records(FIXTURES)
    datos = construir_datos(registros, tarifas_path=str(FIXTURES / "tarifas.yaml"))
    DESTINO.write_text(serializar(datos), encoding="utf-8")
    print(f"{len(registros)} registros -> {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
