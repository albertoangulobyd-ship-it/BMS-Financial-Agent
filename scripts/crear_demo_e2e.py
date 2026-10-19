"""Crea una base de DATOS DE PRUEBA nueva en una carpeta y escribe sus tokens en JSON.

Lo usan los tests de la app en el navegador (frontend/e2e/global-setup.ts): cada pasada
empieza con una base de prueba recien hecha en una carpeta temporal, y necesita los
tokens para entrar. `bms-agent demo crear` los escribe para una persona; aqui salen en
JSON, una sola linea, para que un programa los lea sin interpretar texto.

    python scripts/crear_demo_e2e.py --carpeta /tmp/x/datos
    {"db": "/tmp/x/datos/demo.sqlite3", "tokens": {"Ana Demo": "bms_...", ...}, "cifras": {...}}

Solo escribe en un fichero demo.sqlite3 que no exista o que ya sea de prueba (demo.crear
lo exige), y con --rehacer lo vuelve a hacer.

Ademas de las dos personas de la base de prueba (Ana, administradora, y Bram, de
administracion), anade una tercera, "Cas Consulta", con el rol consulta (solo mira): las
pruebas comprueban con ella que quien solo puede leer no ve ningun boton de una orden.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CONSULTA = "Cas Consulta"


def _persona_de_consulta(ruta: Path) -> str:
    """Una persona de solo lectura en la base de prueba recien hecha, y su token."""
    from bms_agent import permisos
    from bms_agent.almacen import preparar

    with preparar(ruta) as almacen:
        conn = almacen.conn
        usuario = permisos.crear_usuario(conn, CONSULTA)
        permisos.asignar_rol(conn, usuario, "consulta")
        return permisos.emitir_token(conn, usuario)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--carpeta", required=True, help="donde va demo.sqlite3")
    parser.add_argument("--rehacer", action="store_true", help="si ya existe, se hace de nuevo")
    args = parser.parse_args(argv)

    from bms_agent import demo
    from bms_agent.almacen import NOMBRE_DEMO

    ruta = Path(args.carpeta) / NOMBRE_DEMO
    resumen = demo.crear(ruta, rehacer=args.rehacer)
    if not resumen.creada:
        print(json.dumps({"error": f"{ruta} ya existe: --rehacer para hacerla de nuevo"}),
              file=sys.stderr)
        return 2
    tokens = {**resumen.tokens, CONSULTA: _persona_de_consulta(ruta)}
    print(json.dumps({"db": str(ruta), "tokens": tokens, "cifras": resumen.cifras},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
