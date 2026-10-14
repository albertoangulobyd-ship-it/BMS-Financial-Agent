"""Lo que sale del almacen es lo que salia de out/.

La puerta del paso 1: construir_datos(registros_legado(db)) es igual que
construir_datos(load_records(out)) sobre las fixtures v1, y las dos son la
foto de referencia byte a byte.
"""

from __future__ import annotations

import json
from collections import Counter

from conftest import GOLDEN, TARIFAS_V1

from bms_agent.dashboard import construir_datos
from bms_agent.importadores.extracciones import importar_out
from bms_agent.legado import registros_legado
from bms_agent.report import load_records


def _serializar(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


def test_el_panel_desde_el_almacen_es_el_panel_desde_out(almacen, out_v1, pdfs_ejemplo) -> None:
    importar_out(almacen, out_v1, pdfs_ejemplo)
    desde_almacen = construir_datos(registros_legado(almacen.conn), tarifas_path=str(TARIFAS_V1))
    desde_out = construir_datos(load_records(out_v1), tarifas_path=str(TARIFAS_V1))
    assert desde_almacen == desde_out
    foto = (GOLDEN / "construir_datos_v1.json").read_text(encoding="utf-8")
    assert _serializar(desde_almacen) == foto


def test_los_registros_son_los_mismos_diccionarios(almacen, out_v1) -> None:
    importar_out(almacen, out_v1, None)
    clave = lambda r: r["source_sha256"]   # noqa: E731
    assert sorted(registros_legado(almacen.conn), key=clave) == sorted(
        load_records(out_v1), key=clave)


def test_con_varias_extracciones_vale_la_misma_vigente_que_en_out(almacen, out_v1) -> None:
    """La regla de load_records (la mas reciente; en empate, la ultima) es la del almacen."""
    for nombre, cuando in (("02-sin-kvk-btw-verlegd", "2026-10-02T00:00:00+00:00"),
                           ("06-fecha-nl", None)):
        registro = json.loads((out_v1 / f"{nombre}.json").read_text(encoding="utf-8"))
        registro["model"] = "claude-opus-5-5"
        registro["extraction"]["payment_reference"] = f"otra lectura de {nombre}"
        if cuando:
            registro["extracted_at"] = cuando
        (out_v1 / f"{nombre}-z.json").write_text(
            json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")

    importar_out(almacen, out_v1, None)
    vigentes = registros_legado(almacen.conn)
    assert sorted(vigentes, key=lambda r: r["source_sha256"]) == sorted(
        load_records(out_v1), key=lambda r: r["source_sha256"])
    assert len(vigentes) == 7
    referencias = {r["source_name"]: r["extraction"]["payment_reference"] for r in vigentes}
    # La 02 tiene una lectura mas reciente; la 06 empata, y gana el fichero que
    # va despues por nombre ("06-fecha-nl-z" va antes que "06-fecha-nl."): la original.
    assert referencias["02-sin-kvk-btw-verlegd.pdf"] == "otra lectura de 02-sin-kvk-btw-verlegd"
    assert referencias["06-fecha-nl.pdf"] != "otra lectura de 06-fecha-nl"
    assert Counter(json.dumps(r, sort_keys=True) for r in registros_legado(
        almacen.conn, todas=True)) == Counter(
        json.dumps(r, sort_keys=True) for r in load_records(out_v1, todas=True))
