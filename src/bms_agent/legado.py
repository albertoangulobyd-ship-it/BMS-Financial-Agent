"""Los registros de siempre, sacados del almacen.

checks.py, dashboard.py, facturacion.py y report.py trabajan sobre los
diccionarios que escribe el extractor (los de out/*.json). Mientras no lean
del almacen tipado (paso 2), este adaptador les da exactamente eso, sacado
de la tabla extraccion: la vigente de cada documento, tal cual se guardo.

Que construir_datos(registros_legado(db)) sea igual que
construir_datos(load_records(out)) es la prueba de que la migracion de out/
al almacen no ha perdido ni cambiado nada.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .almacen.extracciones import contenido_todas, contenido_vigente


def registros_legado(conn: sqlite3.Connection, todas: bool = False) -> list[dict[str, Any]]:
    """Un registro por documento, el de su extraccion vigente.

    `todas=True` devuelve cada extraccion guardada, como
    load_records(..., todas=True): es lo que cuenta lo gastado.
    """
    textos = contenido_todas(conn) if todas else contenido_vigente(conn)
    return [json.loads(texto) for texto in textos]
