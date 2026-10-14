"""`extract` y el servidor escriben en el almacen y en out/, con el mismo texto.

Ningun test llama a la API: el cliente falso de test_extraccion_pasada
cuenta las llamadas.
"""

from __future__ import annotations

import pytest

from test_extraccion_pasada import PDF, ClienteFalso

from bms_agent.almacen import abrir, preparar, ruta_anclas_de
from bms_agent.auditoria import leer_anclas, verificar_cadena
from bms_agent.extract import extraer_pasada
from bms_agent.importadores.extracciones import importar_out
from bms_agent.legado import registros_legado


@pytest.fixture
def carpeta(tmp_path):
    pdfs = tmp_path / "facturas"
    pdfs.mkdir()
    (pdfs / "a.pdf").write_bytes(PDF)
    return [pdfs / "a.pdf"], tmp_path / "out"


def _extracciones(conn) -> list:
    return conn.execute(
        "SELECT e.via, e.contenido_json, d.ruta_cas, d.origen, d.nombre_original "
        "FROM extraccion AS e JOIN documento AS d ON d.id = e.documento_id ORDER BY e.id"
    ).fetchall()


def test_una_extraccion_nueva_va_al_almacen_con_el_texto_del_fichero(almacen, carpeta) -> None:
    rutas, out = carpeta
    r = extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5", almacen=almacen)

    assert (r.extraidas, r.almacenadas, r.sin_almacen) == (1, 1, 0)
    [fila] = _extracciones(almacen.conn)
    [fichero] = sorted(out.glob("*.json"))
    assert fila["contenido_json"].encode("utf-8") == fichero.read_bytes()
    assert (fila["via"], fila["origen"], fila["nombre_original"]) == ("api", "carpeta", "a.pdf")
    assert almacen.documentos.ruta(fila["ruta_cas"]).read_bytes() == PDF


def test_lo_reutilizado_de_out_tambien_entra_y_no_se_paga(almacen, carpeta) -> None:
    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5")    # sin almacen
    assert _extracciones(almacen.conn) == []

    cliente = ClienteFalso()
    r = extraer_pasada(cliente, rutas, out, model="claude-opus-5", almacen=almacen)
    assert cliente.llamadas == 0 and r.almacenadas == 1
    [fila] = _extracciones(almacen.conn)
    assert fila["via"] == "out_v1" and fila["ruta_cas"] is not None

    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5", almacen=almacen)
    assert len(_extracciones(almacen.conn)) == 1                       # nada repetido
    assert verificar_cadena(almacen.conn).ok


def test_si_el_almacen_falla_la_extraccion_pagada_sigue_en_out(almacen, carpeta) -> None:
    rutas, out = carpeta
    almacen.conn.close()                         # cualquier escritura fallara
    avisos = []
    r = extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5", almacen=almacen,
                       informar=lambda tipo, nombre, detalle: avisos.append((tipo, detalle)))
    assert (r.extraidas, r.sin_almacen, r.fallidas) == (1, 1, 0)
    assert len(list(out.glob("*.json"))) == 1
    assert any(tipo == "error" and "importar-out" in detalle for tipo, detalle in avisos)


def test_la_cli_extract_escribe_en_el_almacen_de_bms_db(carpeta, monkeypatch, capsys) -> None:
    import anthropic

    from bms_agent.almacen import ruta_por_defecto
    from bms_agent.cli import main

    rutas, out = carpeta
    cliente = ClienteFalso()
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: cliente)
    assert main(["extract", str(rutas[0].parent), "--out", str(out)]) == 0
    assert "Almacen: 1 documentos guardados" in capsys.readouterr().out

    conn = abrir(ruta_por_defecto())
    try:
        [fila] = _extracciones(conn)
        assert fila["via"] == "api"
        anclas, _ = leer_anclas(ruta_anclas_de(ruta_por_defecto()))
        assert verificar_cadena(conn, anclas).ok and anclas
        assert not (out / "anclas.log").exists()
    finally:
        conn.close()


def test_el_servidor_escribe_en_el_almacen(carpeta, monkeypatch, tmp_path) -> None:
    from bms_agent.serve import Agente

    rutas, out = carpeta
    db = tmp_path / "datos" / "bms.sqlite3"
    cliente = ClienteFalso()
    agente = Agente(rutas[0].parent, out, db)
    monkeypatch.setattr(agente, "_cliente", lambda: cliente)
    agente._ejecutar()

    assert agente.estado["estado"] == "terminado" and cliente.llamadas == 1
    with preparar(db) as almacen:
        [fila] = _extracciones(almacen.conn)
        [fichero] = sorted(out.glob("*.json"))
        assert fila["contenido_json"].encode("utf-8") == fichero.read_bytes()
        assert almacen.documentos.ruta(fila["ruta_cas"]).read_bytes() == PDF


def test_el_registro_que_se_guarda_es_el_mismo_texto_que_el_fichero(tmp_path) -> None:
    """Byte a byte: read_text compararia con los CRLF de Windows ya cambiados por LF."""
    from test_extraccion_pasada import _registro

    registro = _registro()
    ruta = registro.write_json(tmp_path)
    assert ruta.read_bytes() == registro.contenido().encode("utf-8")


def test_un_fichero_con_crlf_entra_una_sola_vez(almacen, carpeta) -> None:
    """Un out/ escrito en Windows (CRLF): extract e importar-out guardan los mismos bytes."""
    rutas, out = carpeta
    extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5")    # sin almacen
    [fichero] = sorted(out.glob("*.json"))
    fichero.write_bytes(fichero.read_bytes().replace(b"\n", b"\r\n"))

    r = extraer_pasada(ClienteFalso(), rutas, out, model="claude-opus-5", almacen=almacen)
    assert (r.reutilizadas, r.almacenadas) == (1, 1)
    [fila] = _extracciones(almacen.conn)
    assert fila["contenido_json"].encode("utf-8") == fichero.read_bytes()

    importado = importar_out(almacen, out, None)
    assert (importado.importadas, importado.ya_estaban) == (0, 1)
    assert len(_extracciones(almacen.conn)) == 1
    assert len(registros_legado(almacen.conn, todas=True)) == 1
