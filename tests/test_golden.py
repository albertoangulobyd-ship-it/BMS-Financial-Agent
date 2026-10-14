"""Foto de referencia de construir_datos sobre las extracciones v1 fijas.

Es la red de los pasos siguientes de la V1: el almacen, el adaptador y el
contrato v2 tienen que dejar /api/datos byte a byte igual que esta foto, o
explicar por que no. Y es la prueba de que las correcciones del paso 0 solo
movieron lo que tenian que mover.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from bms_agent.dashboard import construir_datos
from bms_agent.extract import ExtractionRecord
from bms_agent.report import load_records
from bms_agent.schema import InvoiceExtraction

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures" / "v1"
GOLDEN = RAIZ / "tests" / "golden"
TARIFAS = str(FIXTURES / "tarifas.yaml")

# Las unicas fixtures cuyo resultado cambian las correcciones del paso 0.
DOCUMENTADAS = {"05-uren.pdf", "07-usd.pdf"}


def _serializar(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


def _registros() -> list[dict]:
    return load_records(FIXTURES)


def _datos(registros: list[dict] | None = None) -> dict:
    return construir_datos(_registros() if registros is None else registros, tarifas_path=TARIFAS)


def _fila(datos: dict, fichero: str) -> dict:
    return next(f for f in datos["filas"] if f["fichero"] == fichero)


def _claves_de_un_registro() -> set[str]:
    """Las claves que escribe ExtractionRecord.to_dict, sacadas del propio codigo."""
    extraccion = InvoiceExtraction.model_validate(_registros()[0]["extraction"])
    return set(ExtractionRecord("0" * 64, "x.pdf", "m", "p", "1", "", extraccion).to_dict())


def test_hay_siete_fixtures_y_todas_son_registros_v1_validos() -> None:
    """Tienen la forma exacta que escribe el extractor y pasan el esquema v1."""
    registros = _registros()
    assert len(registros) == 7
    claves = _claves_de_un_registro()
    for registro in registros:
        assert set(registro) == claves, registro["source_name"]
        assert registro["schema_version"] == "1"
        InvoiceExtraction.model_validate(registro["extraction"])


def test_las_tres_de_ejemplo_son_los_pdf_del_generador(tmp_path) -> None:
    """El paso 1 buscara cada PDF por su hash: tiene que ser el de verdad."""
    ruta = RAIZ / "scripts" / "generar_facturas_ejemplo.py"
    spec = importlib.util.spec_from_file_location("generador", ruta)
    generador = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generador)

    por_nombre = {r["source_name"]: r["source_sha256"] for r in _registros()}
    for nombre, lineas in (
        ("01-limpia.pdf", generador.FACTURA_LIMPIA),
        ("02-sin-kvk-btw-verlegd.pdf", generador.FACTURA_SIN_KVK),
        ("03-con-inyeccion.pdf", generador.FACTURA_CON_INYECCION),
    ):
        generador.write_pdf(tmp_path / nombre, lineas)
        assert hashlib.sha256((tmp_path / nombre).read_bytes()).hexdigest() == por_nombre[nombre]


def test_construir_datos_es_byte_a_byte_la_foto() -> None:
    esperado = (GOLDEN / "construir_datos_v1.json").read_text(encoding="utf-8")
    assert _serializar(_datos()) == esperado


def test_las_correcciones_no_cambian_nada_fuera_de_las_fixtures_documentadas() -> None:
    """La foto de antes del paso 0, sin las dos afectadas, sigue identica."""
    sin_afectadas = [r for r in _registros() if r["source_name"] not in DOCUMENTADAS]
    esperado = (GOLDEN / "construir_datos_v1_antes_sin_afectadas.json").read_text(encoding="utf-8")
    assert _serializar(_datos(sin_afectadas)) == esperado


def test_la_linea_en_uren_ya_cuenta_como_horas() -> None:
    datos = _datos()
    fila = _fila(datos, "05-uren.pdf")
    assert fila["horas"] == 24.0
    assert fila["otras_unidades"] == ["stuk"]
    waalhaven = [p for p in datos["facturacion"]["propuestas"] if p["obra"] == "Waalhaven"]
    assert [p["horas"] for p in waalhaven] == [24.0]


def test_la_factura_en_dolares_no_suma_como_euros() -> None:
    datos = _datos()
    fila = _fila(datos, "07-usd.pdf")
    assert (fila["base"], fila["iva"], fila["total"]) == (None, None, None)
    assert fila["estado"] == "critico"
    assert any("USD" in m for m in fila["motivos"])
    # Sus 2.500 no estan en el importe total; antes si lo estaban.
    euros = sum(f["total"] for f in datos["filas"] if f["total"] is not None)
    assert datos["totales"]["importe"] == pytest.approx(euros)
    assert datos["totales"]["importe"] == pytest.approx(7986.42)
    # Fuera de todos los agregados, tambien de las horas (revision del paso 0).
    assert datos["totales"]["horas"] == pytest.approx(161.5)
    assert "Northwind Analytics Ltd" not in [p["proveedor"] for p in datos["por_proveedor"]]
    assert "Northwind Analytics Ltd" not in [
        p["proveedor"] for p in datos["matriz"]["proveedores"]]
    assert fila["horas"] == 20.0   # la fila dice lo que trae el documento


def test_las_demas_fixtures_dicen_lo_que_tienen_que_decir() -> None:
    datos = _datos()
    # La fecha copiada en formato neerlandes se ordena como ISO.
    assert _fila(datos, "06-fecha-nl.pdf")["orden"] == "2026-09-13"
    # El abono comparte periodo con la 01 y no es un periodo facturado dos veces.
    assert not [a for a in datos["alertas"] if a["regla"] == "B4"]
    # La factura con inyeccion: IBAN de la cabecera y texto marcado para revisar.
    inyeccion = _fila(datos, "03-con-inyeccion.pdf")
    assert inyeccion["iban"] == "NL75 INGB 0002 4456 89"
    assert inyeccion["estado"] == "revisar"
    for nombre in ("01-limpia.pdf", "02-sin-kvk-btw-verlegd.pdf", "04-nota-credito.pdf"):
        assert _fila(datos, nombre)["estado"] == "ok", nombre
