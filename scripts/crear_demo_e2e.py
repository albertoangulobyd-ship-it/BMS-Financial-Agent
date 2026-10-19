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

Y deja en la carpeta, junto a la base, los ficheros que la prueba de Importeren sube desde
el navegador (paso 15): la exportacion de clientes de Exact con un cliente nuevo, con la
marca de los datos de prueba (en la base de prueba solo entra lo de la prueba), y un fichero
que no es ninguna exportacion. Van en "ficheros" del JSON.
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
    ficheros = _ficheros_de_importar(Path(args.carpeta))
    print(json.dumps({"db": str(ruta), "tokens": tokens, "cifras": resumen.cifras,
                      "ficheros": ficheros}, ensure_ascii=False))
    return 0


def _ficheros_de_importar(carpeta: Path) -> dict[str, str]:
    """Los ficheros que sube la prueba de Importeren: los clientes de Exact de la base de
    prueba mas uno nuevo (con la marca y un IBAN del banco ficticio) y uno que no es nada."""
    from bms_agent import demo

    filas = [[c.codigo, c.nombre, c.kvk or "", c.btw or "", "Normaal", "nee",
              "ja" if c.codigo == "10001" else "nee", f"{c.plazo} dagen", "Actief",
              c.iban or "", c.nombre] for c in demo.CLIENTES]
    filas.append(["10004", "Demo Nieuwbouw BV", "99000204", "NL999000204B01", "Normaal", "nee",
                  "nee", "30 dagen", "Actief", demo.iban_demo(1000401), "Demo Nieuwbouw BV"])
    clientes = carpeta / "exact-debiteuren-nieuw.csv"
    clientes.write_bytes(demo._csv(
        ["Debiteurnummer", "Naam", "KvK-nummer", "Btw-nummer", "Btw-behandeling",
         "Verleggen toegestaan", "PO verplicht", "Betalingsconditie", "Status", "IBAN",
         "Tenaamstelling"], filas))
    raro = carpeta / "notities.txt"
    raro.write_text(f"{demo.MARCA_TEXTO}: dit is geen export van Exact, de bank of TRNSPRNT.\n",
                    encoding="utf-8")
    return {"clientes": str(clientes), "raro": str(raro)}


if __name__ == "__main__":
    raise SystemExit(main())
