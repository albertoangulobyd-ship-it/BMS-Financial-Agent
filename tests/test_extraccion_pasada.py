"""Politica de cache y evidencia: lo ya leido no se paga dos veces ni se pisa.

Ningun test llama a la API. El cliente falso cuenta las llamadas, que es lo
que importa: cambiar de version no puede costar una pasada entera.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from bms_agent import config
from bms_agent.cache import CONSERVAR, ESTRICTA
from bms_agent.extract import ExtractionRecord, extraer_pasada, nombre_fichero
from bms_agent.report import load_records
from bms_agent.schema import InvoiceExtraction, VatRegime

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
# Cada respuesta de la API trae su propio request_id, tambien entre clientes.
_PETICIONES = itertools.count(1)


def _extraccion(numero: str = "2026-001") -> InvoiceExtraction:
    return InvoiceExtraction(
        supplier_name="Van Dijk BV", supplier_address=None, kvk_number=None,
        vat_number="NL001234567B01", invoice_number=numero, invoice_date="2026-09-15",
        service_period_start=None, service_period_end=None, lines=[],
        subtotal_excl_vat_raw="100,00", vat_rate_raw="21%", vat_amount_raw="21,00",
        total_incl_vat_raw="121,00", vat_regime=VatRegime.standard, kor_mentioned=False,
        reverse_charge_mentioned=False, iban=None, payment_reference=None, due_date=None,
        low_confidence_fields=[], document_notes=None,
    )


class ClienteFalso:
    """Hace de anthropic.Anthropic sin red. Cuenta cada llamada que se pagaria."""

    def __init__(self) -> None:
        self.llamadas = 0
        self.messages = self

    def count_tokens(self, **peticion):
        """Contar no se cobra, pero tambien se cuenta: no deberia hacer falta."""
        self.conteos = getattr(self, "conteos", 0) + 1
        return type("C", (), {"input_tokens": 4321})()

    def parse(self, **peticion):
        assert "tools" not in peticion
        self.llamadas += 1
        uso = type("U", (), {"input_tokens": 6000, "output_tokens": 700})()
        return type("R", (), {
            "stop_reason": "end_turn", "parsed_output": _extraccion(),
            "usage": uso, "_request_id": f"req_falso_{next(_PETICIONES)}",
        })()


@pytest.fixture
def carpeta(tmp_path) -> tuple[list[Path], Path]:
    pdfs = tmp_path / "facturas"
    pdfs.mkdir()
    (pdfs / "a.pdf").write_bytes(PDF)
    return [pdfs / "a.pdf"], tmp_path / "out"


def _ficheros(out: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out.glob("*.json"))}


def _cambiar_versiones(monkeypatch) -> None:
    monkeypatch.setattr(config, "PROMPT_VERSION", "extract/2099-01-01.1")
    monkeypatch.setattr(config, "SCHEMA_VERSION", "2")


def test_cambiar_solo_la_version_no_hace_ninguna_llamada(carpeta, monkeypatch) -> None:
    """La puerta del paso 0: con CONSERVAR, subir prompt, esquema o modelo cuesta 0."""
    rutas, out = carpeta
    primero = ClienteFalso()
    extraer_pasada(primero, rutas, out, model="claude-opus-5")
    assert primero.llamadas == 1
    antes = _ficheros(out)

    _cambiar_versiones(monkeypatch)
    segundo = ClienteFalso()
    r = extraer_pasada(segundo, rutas, out, model="claude-opus-5-5")

    assert segundo.llamadas == 0
    assert (r.extraidas, r.reutilizadas) == (0, 1)
    assert _ficheros(out) == antes


def test_conservar_es_la_politica_por_defecto_de_la_cli(carpeta, monkeypatch, capsys) -> None:
    """`bms-agent extract` sin opciones tampoco paga cuando solo cambia la version."""
    import anthropic

    from bms_agent.cli import main

    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model=config.model_id())
    _cambiar_versiones(monkeypatch)
    cliente = ClienteFalso()
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: cliente)

    assert main(["extract", str(rutas[0].parent), "--out", str(out)]) == 0
    assert cliente.llamadas == 0
    assert "leida con" in capsys.readouterr().out   # dice que es de otra version

    assert main(["extract", str(rutas[0].parent), "--out", str(out), "--estricta"]) == 0
    assert cliente.llamadas == 1


def test_el_servidor_local_aplica_la_misma_politica(carpeta, monkeypatch) -> None:
    from bms_agent.serve import Agente

    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model=config.model_id())
    _cambiar_versiones(monkeypatch)
    cliente = ClienteFalso()
    agente = Agente(rutas[0].parent, out)
    monkeypatch.setattr(agente, "_cliente", lambda: cliente)

    agente._ejecutar()

    assert cliente.llamadas == 0
    assert agente.estado["reutilizadas"] == 1 and agente.estado["estado"] == "terminado"


def test_la_estimacion_de_coste_sigue_la_misma_politica(carpeta, monkeypatch, capsys) -> None:
    """`coste --estimar` dice cero si `extract` no va a pagar nada."""
    import anthropic

    from bms_agent.cli import main

    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model=config.model_id())
    _cambiar_versiones(monkeypatch)
    cliente = ClienteFalso()
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: cliente)

    assert main(["coste", "--out", str(out), "--estimar", str(rutas[0].parent)]) == 0
    assert "cuesta cero" in capsys.readouterr().out
    assert getattr(cliente, "conteos", 0) == 0

    assert main(["coste", "--out", str(out), "--estimar", str(rutas[0].parent),
                 "--estricta"]) == 0
    assert cliente.conteos == 1
    assert cliente.llamadas == 0


def test_lo_gastado_cuenta_cada_extraccion_pagada(carpeta, capsys) -> None:
    """Dos lecturas del mismo PDF se pagaron dos veces, aunque el panel vea una."""
    from bms_agent.cli import main

    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5")
    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5", forzar=True)

    assert main(["coste", "--out", str(out)]) == 0
    salida = capsys.readouterr().out
    assert "documentos leidos                 2" in salida
    assert "1 de 1 documentos estan en cache" in salida


def test_estricta_vuelve_a_leer_y_deja_la_anterior_intacta(carpeta, monkeypatch) -> None:
    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5")
    antes = _ficheros(out)

    _cambiar_versiones(monkeypatch)
    cliente = ClienteFalso()
    extraer_pasada(cliente, rutas, out, model="claude-opus-5", politica=ESTRICTA)

    assert cliente.llamadas == 1
    despues = _ficheros(out)
    assert len(despues) == 2
    for nombre, contenido in antes.items():
        assert despues[nombre] == contenido   # la extraccion v1 sigue byte a byte


def test_estricta_no_paga_lo_que_coincide(carpeta) -> None:
    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5")
    cliente = ClienteFalso()
    extraer_pasada(cliente, rutas, out, model="claude-opus-5", politica=ESTRICTA)
    assert cliente.llamadas == 0


def test_force_vuelve_a_pagar_pero_no_sobrescribe(carpeta) -> None:
    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5")
    antes = _ficheros(out)

    cliente = ClienteFalso()
    extraer_pasada(cliente, rutas, out, model="claude-opus-5", forzar=True)

    assert cliente.llamadas == 1
    despues = _ficheros(out)
    assert len(despues) == 2
    assert all(despues[n] == c for n, c in antes.items())


def test_el_mismo_pdf_dos_veces_en_la_carpeta_se_paga_una_vez(carpeta) -> None:
    rutas, out = carpeta
    copia = rutas[0].parent / "a-reenviada.pdf"
    copia.write_bytes(PDF)
    cliente = ClienteFalso()
    r = extraer_pasada(cliente, [rutas[0], copia], out, model="claude-opus-5")
    assert cliente.llamadas == 1
    assert (r.extraidas, r.reutilizadas) == (1, 1)


def test_con_force_el_mismo_pdf_dos_veces_en_la_pasada_se_paga_una_vez(carpeta) -> None:
    """--force vuelve a leer lo de antes, no lo que esta misma pasada ya leyo."""
    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5")
    copia = rutas[0].parent / "a-reenviada.pdf"
    copia.write_bytes(PDF)

    cliente = ClienteFalso()
    r = extraer_pasada(cliente, [rutas[0], copia, rutas[0]], out,
                       model="claude-opus-5", forzar=True)

    assert cliente.llamadas == 1
    assert (r.extraidas, r.reutilizadas) == (1, 2)
    assert len(_ficheros(out)) == 2


def test_un_fichero_que_no_es_pdf_no_llega_a_la_api(tmp_path) -> None:
    falso = tmp_path / "x.pdf"
    falso.write_bytes(b"no soy un pdf")
    cliente = ClienteFalso()
    r = extraer_pasada(cliente, [falso], tmp_path / "out", model="claude-opus-5")
    assert cliente.llamadas == 0 and r.fallidas == 1


# --- write_json: nunca pisa ---

def _registro(model="claude-opus-5", prompt="p1", schema="1", numero="2026-001",
              cuando="2026-09-20T10:00:00+00:00") -> ExtractionRecord:
    return ExtractionRecord(
        source_sha256="a" * 64, source_name="a.pdf", model=model, prompt_version=prompt,
        schema_version=schema, extracted_at=cuando, extraction=_extraccion(numero),
    )


def test_el_nombre_lleva_el_hash_y_las_tres_versiones() -> None:
    nombre = nombre_fichero("3573674ab6f9" + "0" * 52, "claude-opus-5", "extract/2026-09-17.1", "1")
    assert nombre == "3573674ab6f9__claude-opus-5__extract-2026-09-17.1__s1.json"


def test_otra_version_va_a_otro_fichero(tmp_path) -> None:
    v1 = _registro().write_json(tmp_path)
    contenido_v1 = v1.read_bytes()
    otros = [
        _registro(model="claude-opus-5-5").write_json(tmp_path),
        _registro(prompt="p2").write_json(tmp_path),
        _registro(schema="2").write_json(tmp_path),
    ]
    assert len({v1, *otros}) == 4
    assert v1.read_bytes() == contenido_v1


def test_las_mismas_versiones_con_otro_contenido_no_pisan(tmp_path) -> None:
    primera = _registro(numero="2026-001").write_json(tmp_path)
    segunda = _registro(numero="2026-002", cuando="2026-09-21T10:00:00+00:00").write_json(tmp_path)
    assert segunda != primera
    assert segunda.name.endswith("__2.json")
    assert json.loads(primera.read_text(encoding="utf-8"))["extraction"]["invoice_number"] == "2026-001"


def test_escribir_dos_veces_lo_mismo_no_crea_otro_fichero(tmp_path) -> None:
    registro = _registro()
    assert registro.write_json(tmp_path) == registro.write_json(tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_un_fichero_antiguo_por_hash_no_se_toca(tmp_path) -> None:
    """Las extracciones guardadas con el nombre de antes (<sha12>.json) siguen ahi."""
    antiguo = tmp_path / ("a" * 12 + ".json")
    antiguo.write_text(json.dumps(_registro().to_dict()), encoding="utf-8")
    contenido = antiguo.read_bytes()
    _registro(model="claude-opus-5-5").write_json(tmp_path)
    assert antiguo.read_bytes() == contenido


# --- lectura: una extraccion vigente por documento ---

def test_el_panel_ve_una_extraccion_por_documento_y_el_gasto_las_ve_todas(tmp_path) -> None:
    """Dos extracciones del mismo PDF no son dos facturas (seria un B2 falso)."""
    _registro(cuando="2026-09-20T10:00:00+00:00", numero="vieja").write_json(tmp_path)
    _registro(model="claude-opus-5-5", cuando="2026-10-01T10:00:00+00:00",
              numero="nueva").write_json(tmp_path)

    vigentes = load_records(tmp_path)
    assert [r["extraction"]["invoice_number"] for r in vigentes] == ["nueva"]
    assert len(load_records(tmp_path, todas=True)) == 2


def test_un_registro_sin_hash_no_se_descarta(tmp_path) -> None:
    (tmp_path / "a.json").write_text(json.dumps({"source_name": "a.pdf", "extraction": {}}),
                                     encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"source_name": "b.pdf", "extraction": {}}),
                                     encoding="utf-8")
    assert len(load_records(tmp_path)) == 2
