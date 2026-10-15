"""compat.py: una extraccion v1 se lee con la forma v2 sin tocar la guardada.

Lo que v1 no pidio queda "no solicitado en v1", que no es lo mismo que "no
esta en el documento".
"""

from __future__ import annotations

import json

import pytest
from conftest import FIXTURES_V1

from bms_agent import compat


def _fixtures() -> list[dict]:
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(FIXTURES_V1.glob("*.json"))]


def test_una_v1_sube_con_exactamente_las_claves_nuevas_marcadas() -> None:
    for registro in _fixtures():
        leida = compat.leer_registro(registro)
        original = registro["extraction"]
        nuevas = set(leida.datos) - set(original)
        assert nuevas == set(compat.CAMPOS_V2_CABECERA), registro["source_name"]
        assert all(leida.datos[c] is None for c in nuevas)
        for antes, despues in zip(original["lines"], leida.datos["lines"]):
            assert set(despues) - set(antes) == set(compat.CAMPOS_V2_LINEA)
        assert leida.no_solicitados == (
            set(compat.CAMPOS_V2_CABECERA) | {f"lines[].{c}" for c in compat.CAMPOS_V2_LINEA})
        assert leida.estado("recipient_name") == compat.NO_SOLICITADO_V1
        assert leida.estado("supplier_name") == "presente"
        assert not leida.solicitado("lines[].work_date")


def test_un_campo_v1_vacio_es_vacio_y_no_no_solicitado() -> None:
    registro = next(r for r in _fixtures() if r["source_name"] == "02-sin-kvk-btw-verlegd.pdf")
    assert compat.leer_registro(registro).estado("kvk_number") == "vacio"


def test_leer_no_reescribe_lo_guardado() -> None:
    registro = _fixtures()[0]
    copia = json.dumps(registro, sort_keys=True)
    leida = compat.leer_registro(registro)
    leida.datos["lines"][0]["description"] = "otra"
    assert json.dumps(registro, sort_keys=True) == copia


def test_una_v2_pasa_tal_cual_y_una_version_desconocida_no() -> None:
    v2 = {"supplier_name": "X", "recipient_name": "BM Support BV", "lines": [], "references": []}
    leida = compat.leer(v2, "2")
    assert leida.datos == v2 and leida.no_solicitados == frozenset()
    assert leida.estado("references") == "vacio"
    with pytest.raises(ValueError, match="no se sabe leer"):
        compat.leer(v2, "9")
