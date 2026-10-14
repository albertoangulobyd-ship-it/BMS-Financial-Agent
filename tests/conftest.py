"""Fixtures comunes de los tests de la V1.

- Ningun test escribe en el almacen de verdad: BMS_DB apunta siempre a una
  carpeta temporal, tambien en los tests que no piden almacen y ejecutan
  `extract` o el servidor, que ahora escriben en el.
- `reloj` es un reloj parado; `db` una base en memoria con todas las
  migraciones aplicadas y ese reloj; `almacen` la base mas una carpeta de
  documentos temporal. Los pasos siguientes construyen encima de estas.
- `pdfs_ejemplo` escribe los tres PDF del generador, cuyos hashes son los de
  las fixtures v1 01, 02 y 03.
"""

from __future__ import annotations

import importlib.util
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bms_agent.almacen import Almacen, abrir
from bms_agent.almacen.documentos import AlmacenDocumentos
from bms_agent.almacen.migrar import migrar
from bms_agent.reloj import RelojFijo

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES_V1 = RAIZ / "tests" / "fixtures" / "v1"
TARIFAS_V1 = FIXTURES_V1 / "tarifas.yaml"
GOLDEN = RAIZ / "tests" / "golden"
INSTANTE_FIJO = datetime(2026, 10, 14, 9, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _almacen_aislado(tmp_path_factory, monkeypatch) -> Path:
    ruta = tmp_path_factory.mktemp("almacen") / "bms.sqlite3"
    monkeypatch.setenv("BMS_DB", str(ruta))
    return ruta


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo(INSTANTE_FIJO)


@pytest.fixture
def db(reloj):
    conn = abrir(":memory:", reloj=reloj)
    migrar(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def almacen(db, tmp_path) -> Almacen:
    return Almacen(db, AlmacenDocumentos(tmp_path / "documentos"))


def _generador():
    ruta = RAIZ / "scripts" / "generar_facturas_ejemplo.py"
    spec = importlib.util.spec_from_file_location("generador_ejemplo", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def pdfs_ejemplo(tmp_path) -> Path:
    """Los tres PDF de ejemplo, en una carpeta propia del test."""
    generador = _generador()
    carpeta = tmp_path / "facturas"
    carpeta.mkdir()
    for nombre, lineas in (
        ("01-limpia.pdf", generador.FACTURA_LIMPIA),
        ("02-sin-kvk-btw-verlegd.pdf", generador.FACTURA_SIN_KVK),
        ("03-con-inyeccion.pdf", generador.FACTURA_CON_INYECCION),
    ):
        generador.write_pdf(carpeta / nombre, lineas)
    return carpeta


@pytest.fixture
def out_v1(tmp_path) -> Path:
    """Una copia de las siete extracciones v1, como si fueran el out/ de alguien."""
    destino = tmp_path / "out"
    destino.mkdir()
    for fichero in sorted(FIXTURES_V1.glob("*.json")):
        shutil.copy2(fichero, destino / fichero.name)
    return destino
