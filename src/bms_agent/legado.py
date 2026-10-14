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

from .almacen.extracciones import en_orden_de_out
from .report import vigentes


def registros_legado(conn: sqlite3.Connection, todas: bool = False) -> list[dict[str, Any]]:
    """Un registro por documento, el de su extraccion vigente, como load_records.

    No usa la vista v_extraccion_vigente: esa es la regla del almacen
    (extraido_en en UTC), y load_records compara el texto de extracted_at
    tal cual. Las dos coinciden con lo que escribe el extractor; para que
    esta coincida tambien con un out/ raro (una fecha que no es ISO, otro
    offset), aqui se aplica la misma funcion que en load_records, sobre las
    extracciones en el orden de out/. El orden importa: construir_datos
    lista las facturas de B2 en el orden en que le llegan.

    `todas=True` devuelve cada extraccion guardada, como
    load_records(..., todas=True): es lo que cuenta lo gastado.
    """
    leidos = [json.loads(fila["contenido_json"]) for fila in en_orden_de_out(conn)]
    return leidos if todas else vigentes(leidos)
