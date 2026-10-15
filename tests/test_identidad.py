"""identidad.py: coincidencia exacta, por btw-id, KvK y alias confirmado. Nunca por IBAN.

Un proveedor reconocido por parecido mezcla historias; uno reconocido por
IBAN deja que una factura falsa se reconozca a si misma.
"""

from __future__ import annotations

import inspect
import sqlite3

import pytest

from bms_agent import campos
from bms_agent.almacen import usuario_sistema
from bms_agent.campos import Automatico
from bms_agent.identidad import (
    anadir_alias,
    normalizar_btw,
    normalizar_kvk,
    normalizar_nombre,
    parece_iban,
    resolver_objeto,
    resolver_parte,
)


@pytest.fixture
def maestro(db):
    importador = usuario_sistema(db, "importador")
    origen = Automatico("maestro", importador)
    ids = {
        "van_dijk": campos.crear(db, "proveedor", {
            "nombre": "Bouwtechniek Van Dijk BV", "kvk": "87654321", "btw_id": "NL001234567B01"},
            origen),
        "de_vries": campos.crear(db, "proveedor", {
            "nombre": "J. de Vries", "btw_id": "NL002345678B01"}, origen),
        "sin_btw": campos.crear(db, "proveedor", {"nombre": "Koster", "kvk": "76543210"}, origen),
    }
    return db, origen, ids


def test_normalizar() -> None:
    assert normalizar_btw(" nl 0012.34567-b01 ") == "NL001234567B01"
    assert normalizar_kvk("KvK 8765 4321") == "87654321"
    assert normalizar_nombre("Van Dijk B.V.") == normalizar_nombre("  van dijk  bv ") == "van dijk bv"
    assert normalizar_btw("") is None and normalizar_kvk(None) is None
    assert parece_iban("NL91 ABNA 0417 1643 00") and not parece_iban("Van Dijk BV")


def test_primero_el_btw_luego_el_kvk(maestro) -> None:
    db, _origen, ids = maestro
    assert resolver_parte(db, "proveedor", btw="NL 0012.34567.B01").fila_id == ids["van_dijk"]
    r = resolver_parte(db, "proveedor", btw=None, kvk="7654 3210", nombre="cualquiera")
    assert (r.fila_id, r.por) == (ids["sin_btw"], "kvk")
    # El btw-id manda: un KvK de otro no lo cambia.
    r = resolver_parte(db, "proveedor", btw="NL002345678B01", kvk="87654321")
    assert (r.fila_id, r.por) == (ids["de_vries"], "btw")


def test_el_nombre_solo_por_alias_confirmado_y_exacto(maestro) -> None:
    db, origen, ids = maestro
    assert resolver_parte(db, "proveedor", nombre="Bouwtechniek Van Dijk BV").fila_id is None
    anadir_alias(db, "proveedor", "Van Dijk Bouw B.V.", ids["van_dijk"], origen, origen_alias="maestro")
    assert resolver_parte(db, "proveedor", nombre="van dijk bouw bv").fila_id == ids["van_dijk"]
    assert resolver_parte(db, "proveedor", nombre="Van Dijk Bouw").fila_id is None     # no por parecido
    anadir_alias(db, "proveedor", "Koster Elektro", ids["sin_btw"], origen, confirmado=False)
    assert resolver_parte(db, "proveedor", nombre="Koster Elektro").fila_id is None    # sin confirmar


def test_nunca_por_iban(maestro) -> None:
    db, origen, ids = maestro
    with pytest.raises(ValueError, match="IBAN"):
        anadir_alias(db, "proveedor", "NL91 ABNA 0417 1643 00", ids["van_dijk"], origen)
    # Ni saltandose identidad: la base rechaza un alias con forma de IBAN.
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        campos.crear(db, "alias", {"tabla": "proveedor", "alias": "NL91ABNA0417164300",
                                   "fila_id": ids["van_dijk"], "origen": "manual"}, origen)
    assert resolver_parte(db, "proveedor", nombre="NL91ABNA0417164300").fila_id is None
    # Y no hay manera de pedirlo: la busqueda no tiene un parametro de IBAN.
    assert "iban" not in inspect.signature(resolver_parte).parameters


def test_dos_filas_con_el_mismo_btw_son_una_ambiguedad(maestro) -> None:
    db, origen, ids = maestro
    otro = campos.crear(db, "proveedor", {"nombre": "Copia", "btw_id": "NL001234567B01"}, origen)
    r = resolver_parte(db, "proveedor", btw="NL001234567B01")
    assert r.fila_id is None and r.ambigua and set(r.candidatos) == {ids["van_dijk"], otro}


def test_un_alias_no_se_reasigna_solo(maestro) -> None:
    db, origen, ids = maestro
    anadir_alias(db, "proveedor", "Vandijk", ids["van_dijk"], origen)
    assert anadir_alias(db, "proveedor", "VANDIJK", ids["van_dijk"], origen) > 0     # el mismo, nada
    with pytest.raises(ValueError, match="ya es alias"):
        anadir_alias(db, "proveedor", "vandijk", ids["de_vries"], origen)
    with pytest.raises(sqlite3.IntegrityError, match="no existe"):
        campos.crear(db, "alias", {"tabla": "objeto", "alias": "Nadie", "fila_id": 999,
                                   "origen": "manual"}, origen)


def test_el_objeto_por_codigo_o_alias(db) -> None:
    origen = Automatico("maestro", usuario_sistema(db, "importador"))
    rijnhaven = campos.crear(db, "objeto", {"codigo": "Rijnhaven", "nombre": "Rijnhaven"}, origen)
    assert resolver_objeto(db, "RIJNHAVEN").fila_id == rijnhaven
    assert resolver_objeto(db, "Rijnhaven Oost").fila_id is None
    anadir_alias(db, "objeto", "Rijnhaven Oost", rijnhaven, origen)
    assert resolver_objeto(db, "rijnhaven oost").fila_id == rijnhaven
    assert resolver_objeto(db, None).fila_id is None


@pytest.mark.parametrize("kvk, btw", [
    ("8765-4321", "NL/001234567/B01"),
    ("KvK 87654321", "nl 001234567 b01"),
    ("8765.4321", "NL_001234567_B01"),
])
def test_el_maestro_se_normaliza_como_el_documento(db, kvk, btw) -> None:
    """Un maestro escrito con otros separadores sigue siendo el mismo numero, y exacto."""
    origen = Automatico("maestro", usuario_sistema(db, "importador"))
    proveedor = campos.crear(db, "proveedor", {"nombre": "Van Dijk", "kvk": kvk, "btw_id": btw},
                             origen)
    assert resolver_parte(db, "proveedor", kvk="87654321").fila_id == proveedor
    assert resolver_parte(db, "proveedor", btw="NL001234567B01").fila_id == proveedor
    assert resolver_parte(db, "proveedor", kvk="87654322").fila_id is None
