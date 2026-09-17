"""Reenviar la misma factura no debe costar nada."""

from __future__ import annotations

import json

from bms_agent.cache import CachedExtraction, build_index


def _write(out_dir, name, sha256, model="claude-opus-5", prompt="p1", schema="1"):
    payload = {
        "source_sha256": sha256,
        "source_name": name,
        "model": model,
        "prompt_version": prompt,
        "schema_version": schema,
        "extraction": {},
    }
    (out_dir / f"{sha256[:12]}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_indexa_por_hash(tmp_path) -> None:
    _write(tmp_path, "a.pdf", "a" * 64)
    _write(tmp_path, "b.pdf", "b" * 64)

    index = build_index(tmp_path)

    assert set(index) == {"a" * 64, "b" * 64}


def test_una_carpeta_que_no_existe_da_indice_vacio(tmp_path) -> None:
    assert build_index(tmp_path / "no-existe") == {}


def test_un_json_roto_no_rompe_la_ejecucion(tmp_path) -> None:
    _write(tmp_path, "a.pdf", "a" * 64)
    (tmp_path / "roto.json").write_text("{esto no es json", encoding="utf-8")
    (tmp_path / "incompleto.json").write_text('{"source_name": "x"}', encoding="utf-8")

    index = build_index(tmp_path)

    assert set(index) == {"a" * 64}


def test_se_reutiliza_en_las_mismas_condiciones(tmp_path) -> None:
    _write(tmp_path, "a.pdf", "a" * 64, model="claude-opus-5", prompt="p1", schema="1")
    entry = build_index(tmp_path)["a" * 64]

    assert entry.matches("claude-opus-5", "p1", "1")


def test_cambiar_de_modelo_invalida_lo_guardado(tmp_path) -> None:
    """Si se cambia de modelo hay que volver a extraer: se esta midiendo."""
    _write(tmp_path, "a.pdf", "a" * 64, model="claude-opus-5")
    entry = build_index(tmp_path)["a" * 64]

    assert not entry.matches("claude-sonnet-5", "p1", "1")


def test_tocar_el_prompt_invalida_lo_guardado(tmp_path) -> None:
    _write(tmp_path, "a.pdf", "a" * 64, prompt="p1")
    entry = build_index(tmp_path)["a" * 64]

    assert not entry.matches("claude-opus-5", "p2", "1")


def test_cambiar_el_esquema_invalida_lo_guardado(tmp_path) -> None:
    _write(tmp_path, "a.pdf", "a" * 64, schema="1")
    entry = build_index(tmp_path)["a" * 64]

    assert not entry.matches("claude-opus-5", "p1", "2")


def test_el_mismo_pdf_con_otro_nombre_es_el_mismo_documento(tmp_path) -> None:
    """La identidad son los bytes. Un reenvio con otro nombre no vuelve a costar."""
    _write(tmp_path, "factura.pdf", "a" * 64)
    index = build_index(tmp_path)

    # Otro fichero, mismos bytes, mismo hash: acierta en cache.
    assert "a" * 64 in index


def test_un_pdf_distinto_de_la_misma_factura_no_acierta(tmp_path) -> None:
    """Un PDF regenerado tiene otros bytes: hay que leerlo para saber que dice.

    Esa duplicidad la detectan las reglas B2 a B4 despues de extraer, no aqui.
    """
    _write(tmp_path, "factura-v1.pdf", "a" * 64)
    index = build_index(tmp_path)

    assert "c" * 64 not in index
