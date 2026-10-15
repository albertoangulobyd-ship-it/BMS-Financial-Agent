#!/usr/bin/env python3
"""Escribe los disparadores de guarda de una o varias tablas controladas.

    python scripts/generar_guardas.py factura factura_linea

La migracion 0002 los lleva generados asi, columna a columna. Una migracion
posterior que anade una columna a una tabla controlada (o una tabla
controlada nueva) tiene que borrar y volver a crear sus guardas: este
script las escribe con el esquema que dejan todas las migraciones de hoy
mas el SQL que se le pase con --antes (el ALTER TABLE de la migracion
nueva), para pegarlas al final de esa migracion. test_campos.py comprueba
que cada columna de cada tabla controlada esta en sus guardas.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from bms_agent.almacen.migrar import disponibles  # noqa: E402

ULTIMO = "(SELECT max(id) FROM evento)"


def columnas(conn: sqlite3.Connection, tabla: str) -> list[str]:
    return [f[1] for f in conn.execute(f"PRAGMA table_info({tabla})") if f[1] not in ("id", "rev")]


def guardas(tabla: str, nombres: list[str]) -> str:
    """Los tres disparadores de una tabla controlada: alta, cambio y borrado."""
    base = (f"SELECT 1 FROM cambio_campo WHERE evento_id = {ULTIMO}\n"
            f"        AND tabla = '{tabla}' AND fila_id = NEW.id")
    alta = ["    NEW.rev IS NOT 0", f"    OR NOT EXISTS ({base} AND rev = 0)"]
    for c in nombres:
        alta.append(
            f"    OR (NEW.{c} IS NOT NULL AND NOT EXISTS ({base} AND rev = 0\n"
            f"        AND campo = '{c}' AND json_extract(valor_nuevo, '$') IS NEW.{c}))")
    cambio = ["    NEW.id IS NOT OLD.id", "    OR NEW.rev IS NOT OLD.rev + 1",
              f"    OR NOT EXISTS ({base} AND rev = NEW.rev)"]
    for c in nombres:
        cambio.append(
            f"    OR (NEW.{c} IS NOT OLD.{c} AND NOT EXISTS ({base} AND rev = NEW.rev\n"
            f"        AND campo = '{c}' AND json_extract(valor_anterior, '$') IS OLD.{c}\n"
            f"        AND json_extract(valor_nuevo, '$') IS NEW.{c}))")
    return (
        f"\nCREATE TRIGGER {tabla}_guarda_insert BEFORE INSERT ON {tabla}\nWHEN\n"
        + "\n".join(alta)
        + f"\nBEGIN SELECT RAISE(ABORT, '{tabla} es una tabla controlada: solo la escribe campos.py, "
          "con un cambio_campo por campo en el evento en curso'); END;\n"
        f"\nCREATE TRIGGER {tabla}_guarda_update BEFORE UPDATE ON {tabla}\nWHEN\n"
        + "\n".join(cambio)
        + f"\nBEGIN SELECT RAISE(ABORT, '{tabla} es una tabla controlada: solo la escribe campos.py, "
          "con rev + 1 y un cambio_campo por campo en el evento en curso'); END;\n"
        f"\nCREATE TRIGGER {tabla}_sin_delete BEFORE DELETE ON {tabla}\n"
        f"BEGIN SELECT RAISE(ABORT, '{tabla} no se borra: una fila se retira o se desactiva'); END;\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tablas", nargs="+")
    parser.add_argument("--antes", help="fichero SQL que se aplica antes de leer las columnas")
    args = parser.parse_args()
    conn = sqlite3.connect(":memory:")
    for migracion in disponibles():
        conn.executescript(migracion.sql)
    if args.antes:
        conn.executescript(Path(args.antes).read_text(encoding="utf-8"))
    for tabla in args.tablas:
        print(guardas(tabla, columnas(conn, tabla)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
