"""importar-out: las extracciones de out/ entran en el almacen tal cual, sin la API.

La puerta del paso 1 que vive aqui: dos pasadas dan los mismos recuentos, lo
guardado es byte a byte el fichero, un PDF que no esta deja ruta_cas NULL, y
el modulo anthropic no se puede ni importar mientras corre.
"""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest

from bms_agent.almacen import Almacen, abrir, preparar, raiz_documentos_de
from bms_agent.almacen import documentos
from bms_agent.almacen.documentos import AlmacenDocumentos
from bms_agent.almacen.unidades import sha256_bytes
from bms_agent.auditoria import leer_anclas, verificar_cadena
from bms_agent.cli import main
from bms_agent.importadores.extracciones import importar_out

TABLAS = ("documento", "extraccion", "importacion", "evento", "cambio_campo")
CON_PDF = {"01-limpia.pdf", "02-sin-kvk-btw-verlegd.pdf", "03-con-inyeccion.pdf"}


def _recuentos(conn) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLAS}


@pytest.fixture
def sin_api(monkeypatch):
    """Cualquier `import anthropic` (o de un submodulo) lanza ImportError."""
    for nombre in [m for m in sys.modules if m == "anthropic" or m.startswith("anthropic.")]:
        monkeypatch.setitem(sys.modules, nombre, None)
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(ImportError):
        import anthropic  # noqa: F401
    return True


def test_importar_dos_veces_da_los_mismos_recuentos(almacen, out_v1, pdfs_ejemplo) -> None:
    primera = importar_out(almacen, out_v1, pdfs_ejemplo)
    despues = _recuentos(almacen.conn)
    segunda = importar_out(almacen, out_v1, pdfs_ejemplo)

    assert _recuentos(almacen.conn) == despues
    assert (primera.ficheros, primera.importadas, primera.rechazadas) == (7, 7, 0)
    assert (primera.documentos_nuevos, primera.originales_guardados, primera.sin_original) == (
        7, 3, 4)
    assert (segunda.importadas, segunda.ya_estaban, segunda.documentos_nuevos) == (0, 7, 0)
    assert despues["documento"] == 7 and despues["extraccion"] == 7
    assert despues["importacion"] == 7
    assert verificar_cadena(almacen.conn).ok


def test_lo_guardado_es_byte_a_byte_el_fichero(almacen, out_v1, pdfs_ejemplo) -> None:
    importar_out(almacen, out_v1, pdfs_ejemplo)
    for fichero in sorted(out_v1.glob("*.json")):
        registro = json.loads(fichero.read_text(encoding="utf-8"))
        fila = almacen.conn.execute(
            "SELECT e.* FROM extraccion AS e JOIN documento AS d ON d.id = e.documento_id "
            "WHERE d.sha256 = ?", (registro["source_sha256"],)).fetchone()
        assert fila["contenido_json"].encode("utf-8") == fichero.read_bytes(), fichero.name
        assert fila["via"] == "out_v1"
        assert (fila["modelo"], fila["prompt_version"], fila["schema_version"]) == (
            registro["model"], registro["prompt_version"], registro["schema_version"])
        assert fila["extraido_en"] == registro["extracted_at"]
        assert json.loads(fila["uso_json"]) == registro["usage"]


def test_un_pdf_que_no_esta_deja_ruta_cas_vacia(almacen, out_v1, pdfs_ejemplo) -> None:
    importar_out(almacen, out_v1, pdfs_ejemplo)
    filas = almacen.conn.execute(
        "SELECT nombre_original, ruta_cas, bytes, origen, ruta_declarada, recibido_fuente "
        "FROM documento ORDER BY nombre_original").fetchall()
    for fila in filas:
        assert (fila["origen"], fila["ruta_declarada"]) == ("out_v1", "entrante")
        if fila["nombre_original"] in CON_PDF:
            pdf = pdfs_ejemplo / fila["nombre_original"]
            assert almacen.documentos.ruta(fila["ruta_cas"]).read_bytes() == pdf.read_bytes()
            assert (fila["bytes"], fila["recibido_fuente"]) == (pdf.stat().st_size, "mtime")
        else:
            assert (fila["ruta_cas"], fila["bytes"], fila["recibido_fuente"]) == (
                None, None, "desconocido"), fila["nombre_original"]
    assert documentos.verificar(almacen) == []


def test_sin_carpeta_de_pdf_todo_queda_sin_original_y_se_anade_despues(
    almacen, out_v1, pdfs_ejemplo
) -> None:
    sin = importar_out(almacen, out_v1, None)
    assert (sin.importadas, sin.sin_original, sin.originales_guardados) == (7, 7, 0)
    recuentos = _recuentos(almacen.conn)

    con = importar_out(almacen, out_v1, pdfs_ejemplo)
    assert (con.importadas, con.originales_guardados, con.sin_original) == (0, 3, 4)
    assert almacen.conn.execute(
        "SELECT count(*) FROM documento WHERE ruta_cas IS NOT NULL").fetchone()[0] == 3
    # Las filas son las mismas; solo hay los eventos de los tres originales anadidos.
    despues = _recuentos(almacen.conn)
    assert {t: despues[t] for t in TABLAS if t != "evento"} == {
        t: recuentos[t] for t in TABLAS if t != "evento"}
    assert despues["evento"] == recuentos["evento"] + 3
    assert importar_out(almacen, out_v1, pdfs_ejemplo).originales_guardados == 0


def test_lo_que_no_es_una_extraccion_se_rechaza_una_vez(almacen, out_v1) -> None:
    (out_v1 / "roto.json").write_text("{ esto no es json", encoding="utf-8")
    (out_v1 / "sin-hash.json").write_text(json.dumps({"model": "m"}), encoding="utf-8")
    (out_v1 / "lista.json").write_text("[1, 2]", encoding="utf-8")

    r = importar_out(almacen, out_v1, None)
    assert (r.importadas, r.rechazadas) == (7, 3)
    motivos = dict(r.rechazos)
    assert "no es JSON" in motivos["roto.json"]
    assert "source_sha256" in motivos["sin-hash.json"]
    assert "objeto" in motivos["lista.json"]
    rechazadas = almacen.conn.execute(
        "SELECT estado, filas_rechazadas, rechazos_json FROM importacion "
        "WHERE estado = 'rechazada'").fetchall()
    assert len(rechazadas) == 3 and all(f["filas_rechazadas"] == 1 for f in rechazadas)

    recuentos = _recuentos(almacen.conn)
    otra = importar_out(almacen, out_v1, None)
    assert otra.rechazadas == 3 and _recuentos(almacen.conn) == recuentos


def test_otra_extraccion_del_mismo_pdf_se_anade_y_pasa_a_vigente(almacen, out_v1) -> None:
    from bms_agent.legado import registros_legado

    importar_out(almacen, out_v1, None)
    registro = json.loads((out_v1 / "01-limpia.json").read_text(encoding="utf-8"))
    registro.update(model="claude-opus-5-5", extracted_at="2026-10-01T08:00:00+00:00")
    registro["extraction"]["invoice_number"] = "2026-4471-B"
    (out_v1 / "01-limpia-v2.json").write_text(
        json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")

    r = importar_out(almacen, out_v1, None)
    assert (r.importadas, r.documentos_nuevos) == (1, 0)
    assert almacen.conn.execute(
        "SELECT count(*) FROM extraccion AS e JOIN documento AS d ON d.id = e.documento_id "
        "WHERE d.sha256 = ?", (registro["source_sha256"],)).fetchone()[0] == 2
    numeros = {r["extraction"]["invoice_number"] for r in registros_legado(almacen.conn)}
    assert "2026-4471-B" in numeros and "2026-4471" not in numeros
    assert len(registros_legado(almacen.conn, todas=True)) == 8


def test_la_orden_de_la_cli_no_llama_a_la_api(sin_api, out_v1, pdfs_ejemplo, tmp_path, capsys) -> None:
    """La puerta: con anthropic imposible de importar, importar-out va entero."""
    db = tmp_path / "datos" / "bms.sqlite3"
    argumentos = ["importar-out", "--out", str(out_v1), "--pdfs", str(pdfs_ejemplo),
                  "--db", str(db)]
    assert main(argumentos) == 0
    salida = capsys.readouterr().out
    assert "sin ninguna llamada a la API" in salida
    assert "importados          7" in salida and "sin original        4" in salida

    conn = abrir(db)
    recuentos = _recuentos(conn)
    conn.close()
    assert main(argumentos) == 0
    assert "ya estaban          7" in capsys.readouterr().out
    conn = abrir(db)
    try:
        assert _recuentos(conn) == recuentos
        assert conn.execute(
            "SELECT count(*) FROM documento WHERE ruta_cas IS NULL").fetchone()[0] == 4
        anclas, _ = leer_anclas(out_v1 / "anclas.log")
        assert verificar_cadena(conn, anclas).ok and len(anclas) == 1
    finally:
        conn.close()
    assert sorted(p.name for p in raiz_documentos_de(db).rglob("*.pdf")) == sorted(
        f"{sha256_bytes((pdfs_ejemplo / nombre).read_bytes())}.pdf" for nombre in CON_PDF)


def test_db_init_migrar_y_verificar(tmp_path, out_v1, pdfs_ejemplo, capsys) -> None:
    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["db", "migrar", "--db", str(db)]) == 1          # no existe todavia
    assert main(["db", "init", "--db", str(db)]) == 0
    assert "aplicada 0001_almacen.sql" in capsys.readouterr().out
    assert main(["db", "migrar", "--db", str(db)]) == 0
    assert "no hay migraciones pendientes" in capsys.readouterr().out

    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(pdfs_ejemplo),
                 "--db", str(db)]) == 0
    anclas = str(out_v1 / "anclas.log")
    capsys.readouterr()
    assert main(["db", "verificar", "--db", str(db), "--anclas", anclas]) == 0
    salida = capsys.readouterr().out
    assert "Todo cuadra" in salida and "anclas comprobadas    1" in salida
    assert "documentos            7  (3 con el original)" in salida

    with preparar(db) as almacen:
        ruta = almacen.documentos.ruta(almacen.conn.execute(
            "SELECT ruta_cas FROM documento WHERE ruta_cas IS NOT NULL").fetchone()[0])
    ruta.chmod(0o644)
    ruta.write_bytes(b"%PDF-1.4 otro")
    assert main(["db", "verificar", "--db", str(db), "--anclas", anclas]) == 1
    assert "no coincide con su hash" in capsys.readouterr().out


def test_db_verificar_encuentra_un_evento_tocado_por_detras(tmp_path, out_v1, capsys) -> None:
    db = tmp_path / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no-hay"),
                 "--db", str(db)]) == 0
    atacante = sqlite3.connect(db, isolation_level=None)
    atacante.execute("DROP TRIGGER evento_sin_update")
    atacante.execute("UPDATE evento SET datos_json = '{}' WHERE id = 4")
    atacante.close()
    capsys.readouterr()
    assert main(["db", "verificar", "--db", str(db),
                 "--anclas", str(out_v1 / "anclas.log")]) == 1
    assert "el evento 4 o sus cambio_campo se han modificado" in capsys.readouterr().out


def test_importar_out_sin_carpeta_falla_sin_crear_nada(tmp_path, capsys) -> None:
    db = tmp_path / "bms.sqlite3"
    assert main(["importar-out", "--out", str(tmp_path / "no-existe"), "--db", str(db)]) == 1
    assert not db.exists()


def test_el_almacen_en_memoria_y_la_carpeta_temporal_de_los_tests(db, tmp_path) -> None:
    """Las fixtures de conftest: base migrada, reloj fijo y carpeta propia."""
    almacen = Almacen(db, AlmacenDocumentos(tmp_path / "documentos"))
    assert almacen.conn.execute("SELECT count(*) FROM migracion").fetchone()[0] >= 1
    assert db.reloj.ahora().isoformat() == "2026-10-14T09:30:00+00:00"
