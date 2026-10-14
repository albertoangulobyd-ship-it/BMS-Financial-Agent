"""importar-out: las extracciones de out/ entran en el almacen tal cual, sin la API.

La puerta del paso 1 que vive aqui: dos pasadas dan los mismos recuentos, lo
guardado es byte a byte el fichero, un PDF que no esta deja ruta_cas NULL, y
el modulo anthropic no se puede ni importar mientras corre. Tambien
`db verificar`: la cadena, sus anclas y la evidencia tocada por detras.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys

import pytest
from conftest import RAIZ

from bms_agent.almacen import Almacen, abrir, preparar, raiz_documentos_de, ruta_anclas_de
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


# Un proceso nuevo en el que `import anthropic` (o de un submodulo) lanza
# ImportError desde antes de importar bms_agent: asi tambien se veria un
# import al cargar un modulo, y no solo uno perezoso dentro de la orden.
SIN_API = """
import sys

class SinApi:
    def find_spec(self, nombre, ruta=None, destino=None):
        if nombre == "anthropic" or nombre.startswith("anthropic."):
            raise ImportError("anthropic esta bloqueado en este test")
        return None

sys.meta_path.insert(0, SinApi())
assert "anthropic" not in sys.modules
from bms_agent.cli import main
codigo = main(sys.argv[1:])
cargados = sorted(m for m in sys.modules if m.split(".")[0] == "anthropic")
assert not cargados, f"se importo {cargados}"
sys.exit(codigo)
"""


def _sin_api(*argumentos: str) -> subprocess.CompletedProcess:
    entorno = {**os.environ, "PYTHONPATH": str(RAIZ / "src")}
    return subprocess.run(
        [sys.executable, "-c", SIN_API, *argumentos], capture_output=True, text=True,
        env=entorno, timeout=120,
    )


def _evidencia_atacable(tmp_path, out_v1):
    """Un almacen importado por la CLI, listo para que lo toque una conexion directa."""
    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no-hay"),
                 "--db", str(db)]) == 0
    return db


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


def test_el_bloqueo_de_la_api_funciona() -> None:
    """El proceso de los tests de abajo de verdad no puede importar anthropic."""
    hecho = subprocess.run(
        [sys.executable, "-c", SIN_API.replace("from bms_agent.cli import main", "import anthropic")
         .replace("codigo = main(sys.argv[1:])", "codigo = 0")],
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(RAIZ / "src")},
        timeout=120)
    assert hecho.returncode != 0 and "anthropic esta bloqueado" in hecho.stderr


def test_la_orden_de_la_cli_no_llama_a_la_api(out_v1, pdfs_ejemplo, tmp_path) -> None:
    """La puerta: con anthropic imposible de importar, importar-out va entero."""
    db = tmp_path / "datos" / "bms.sqlite3"
    argumentos = ["importar-out", "--out", str(out_v1), "--pdfs", str(pdfs_ejemplo),
                  "--db", str(db)]
    hecho = _sin_api(*argumentos)
    assert hecho.returncode == 0, hecho.stderr
    assert "sin ninguna llamada a la API" in hecho.stdout
    assert "importados          7" in hecho.stdout and "sin original        4" in hecho.stdout

    conn = abrir(db)
    recuentos = _recuentos(conn)
    conn.close()
    hecho = _sin_api(*argumentos)
    assert hecho.returncode == 0, hecho.stderr
    assert "ya estaban          7" in hecho.stdout
    verificado = _sin_api("db", "verificar", "--db", str(db))
    assert verificado.returncode == 0, verificado.stdout + verificado.stderr
    conn = abrir(db)
    try:
        assert _recuentos(conn) == recuentos
        assert conn.execute(
            "SELECT count(*) FROM documento WHERE ruta_cas IS NULL").fetchone()[0] == 4
        anclas, _ = leer_anclas(ruta_anclas_de(db))
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
    anclas = str(ruta_anclas_de(db))
    capsys.readouterr()
    assert main(["db", "verificar", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    # Dos anclas: la de db init (el evento 1) y la de importar-out.
    assert "Todo cuadra" in salida and "anclas comprobadas    2" in salida
    assert "la ultima es la cabeza" in salida
    assert "documentos            7  (3 con el original)" in salida

    with preparar(db) as almacen:
        ruta = almacen.documentos.ruta(almacen.conn.execute(
            "SELECT ruta_cas FROM documento WHERE ruta_cas IS NOT NULL").fetchone()[0])
    ruta.chmod(0o644)
    ruta.write_bytes(b"%PDF-1.4 otro")
    assert main(["db", "verificar", "--db", str(db), "--anclas", anclas]) == 1
    assert "no coincide con su hash" in capsys.readouterr().out


def test_db_verificar_encuentra_un_evento_tocado_por_detras(tmp_path, out_v1, capsys) -> None:
    db = _evidencia_atacable(tmp_path, out_v1)
    atacante = sqlite3.connect(db, isolation_level=None)
    atacante.execute("DROP TRIGGER evento_sin_update")
    atacante.execute("UPDATE evento SET datos_json = '{}' WHERE id = 4")
    atacante.close()
    capsys.readouterr()
    assert main(["db", "verificar", "--db", str(db)]) == 1
    assert "el evento 4 o sus cambio_campo se han modificado" in capsys.readouterr().out


def _verificar(db, capsys, *extra: str) -> tuple[int, str]:
    capsys.readouterr()
    codigo = main(["db", "verificar", "--db", str(db), *extra])
    return codigo, capsys.readouterr().out


def test_una_extraccion_metida_por_detras_no_cuadra(tmp_path, out_v1, capsys) -> None:
    """Con los disparadores intactos: un INSERT directo con otro IBAN, sin evento."""
    db = _evidencia_atacable(tmp_path, out_v1)
    atacante = sqlite3.connect(db, isolation_level=None)
    fila = atacante.execute("SELECT * FROM extraccion WHERE id = 1").fetchone()
    columnas = [c[1] for c in atacante.execute("PRAGMA table_info(extraccion)")][1:]
    valores = dict(zip(columnas, fila[1:]))
    registro = json.loads(valores["contenido_json"])
    registro["extracted_at"] = "2099-01-01T00:00:00+00:00"
    registro["extraction"]["iban"] = "NL91ABNA0417164300"
    valores.update(contenido_json=json.dumps(registro, indent=2, ensure_ascii=False),
                   extraido_en="2099-01-01T00:00:00+00:00")
    valores["contenido_sha256"] = sha256_bytes(valores["contenido_json"].encode("utf-8"))
    atacante.execute(
        f"INSERT INTO extraccion ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})",
        [valores[c] for c in columnas])
    atacante.close()

    codigo, salida = _verificar(db, capsys)
    assert codigo == 1
    assert "extraccion 8 no tiene su evento extraccion_registrada" in salida


def test_una_extraccion_editada_y_con_el_disparador_repuesto_no_cuadra(
    tmp_path, out_v1, capsys
) -> None:
    db = _evidencia_atacable(tmp_path, out_v1)
    atacante = sqlite3.connect(db, isolation_level=None)
    [sql] = atacante.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'extraccion_sin_update'").fetchone()
    atacante.execute("DROP TRIGGER extraccion_sin_update")
    atacante.execute("UPDATE extraccion SET contenido_json = replace(contenido_json, "
                     "'NL02 ABNA 0123 4567 89', 'NL91 ABNA 0417 1643 00') WHERE id = 1")
    assert atacante.execute("SELECT changes()").fetchone()[0] == 1
    atacante.execute(sql)
    atacante.close()

    codigo, salida = _verificar(db, capsys)
    assert codigo == 1
    assert "extraccion 1: contenido_json no da su contenido_sha256" in salida
    assert "disparador" not in salida                  # el esquema esta como estaba


def test_filas_de_evidencia_editadas_sin_disparadores_no_cuadran(tmp_path, out_v1, capsys) -> None:
    db = _evidencia_atacable(tmp_path, out_v1)
    atacante = sqlite3.connect(db, isolation_level=None)
    for disparador in ("extraccion_sin_update", "documento_sin_update", "importacion_sin_update",
                       "extraccion_sin_delete"):
        atacante.execute(f"DROP TRIGGER {disparador}")
    contenido = atacante.execute("SELECT contenido_json FROM extraccion WHERE id = 2").fetchone()[0]
    otro = contenido.replace("2026", "2025")
    atacante.execute("UPDATE extraccion SET contenido_json = ?, contenido_sha256 = ? WHERE id = 2",
                     (otro, sha256_bytes(otro.encode("utf-8"))))
    atacante.execute("UPDATE documento SET ruta_declarada = 'saliente', origen = 'manual' "
                     "WHERE id = 2")
    atacante.execute("UPDATE importacion SET estado = 'rechazada' WHERE id = 3")
    atacante.execute("DELETE FROM extraccion WHERE id = 7")
    atacante.close()

    codigo, salida = _verificar(db, capsys)
    assert codigo == 1
    assert "falta el disparador extraccion_sin_update, que crea una migracion" in salida
    assert "extraccion 2: contenido_sha256 no es lo que registro el evento" in salida
    assert "documento 2: origen, ruta_declarada no es lo que registro el evento" in salida
    assert "importacion 3: estado no es lo que registro el evento" in salida
    assert "registro extraccion 7, que ya no existe: se ha borrado" in salida


def test_un_disparador_cambiado_o_de_mas_no_cuadra(tmp_path, out_v1, capsys) -> None:
    db = _evidencia_atacable(tmp_path, out_v1)
    atacante = sqlite3.connect(db, isolation_level=None)
    atacante.execute("DROP TRIGGER extraccion_sin_delete")
    atacante.execute("CREATE TRIGGER extraccion_sin_delete BEFORE DELETE ON extraccion "
                     "WHEN 0 BEGIN SELECT RAISE(ABORT, 'no'); END")
    atacante.execute("CREATE TRIGGER espia AFTER INSERT ON extraccion BEGIN SELECT 1; END")
    atacante.close()

    codigo, salida = _verificar(db, capsys)
    assert codigo == 1
    assert "el disparador extraccion_sin_delete ha cambiado" in salida
    assert "sobra el disparador espia" in salida


def test_sin_anclas_no_se_da_por_buena_una_cadena_cortada(tmp_path, out_v1, capsys) -> None:
    db = _evidencia_atacable(tmp_path, out_v1)
    assert _verificar(db, capsys)[0] == 0
    atacante = sqlite3.connect(db, isolation_level=None)
    atacante.execute("DROP TRIGGER evento_sin_delete")
    atacante.execute("DELETE FROM evento WHERE id > 10")
    atacante.execute("CREATE TRIGGER evento_sin_delete BEFORE DELETE ON evento "
                     "BEGIN SELECT RAISE(ABORT, 'evento es de solo escritura: no se borra'); END")
    atacante.close()
    codigo, salida = _verificar(db, capsys)
    assert codigo == 1 and "la cadena ya no llega al evento anclado 22" in salida

    ruta_anclas_de(db).unlink()
    codigo, salida = _verificar(db, capsys)
    assert codigo == 1
    assert "no hay ninguna ancla de este almacen" in salida
    # La evidencia tambien lo ve: hay filas cuyo evento de alta ya no existe.
    assert "no tiene su evento" in salida

    codigo, salida = _verificar(db, capsys, "--sin-anclas")
    assert "no hay ninguna ancla" not in salida


def test_las_anclas_van_con_la_base_y_no_con_la_carpeta_out(tmp_path, out_v1, capsys) -> None:
    """Dos bases, la misma carpeta out/: cada una encuentra las suyas y no se pisan."""
    for nombre in ("db1", "db2"):
        db = tmp_path / nombre / "bms.sqlite3"
        assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no-hay"),
                     "--db", str(db)]) == 0
        codigo, salida = _verificar(db, capsys)
        assert codigo == 0, salida
        assert "anclas comprobadas    1" in salida
    assert not (out_v1 / "anclas.log").exists()

    # Y un fichero compartido a proposito tampoco confunde a la segunda.
    compartido = tmp_path / "compartido.log"
    shutil.copy(ruta_anclas_de(tmp_path / "db1" / "bms.sqlite3"), compartido)
    with compartido.open("a", encoding="utf-8") as fichero:
        fichero.write(ruta_anclas_de(tmp_path / "db2" / "bms.sqlite3").read_text(encoding="utf-8"))
    codigo, salida = _verificar(tmp_path / "db2" / "bms.sqlite3", capsys, "--anclas", str(compartido))
    assert codigo == 0, salida
    assert "1 anclas de" in salida and "son de otro almacen" in salida


def test_verificar_una_base_sin_migrar_lo_dice_sin_traza(tmp_path, capsys) -> None:
    db = tmp_path / "vacia.sqlite3"
    db.touch()
    codigo, salida = _verificar(db, capsys)
    assert codigo == 1
    assert "el almacen no esta migrado (bms-agent db migrar)" in salida


def _cambiar(out_v1, nombre: str, **campos) -> None:
    ruta = out_v1 / nombre
    registro = json.loads(ruta.read_text(encoding="utf-8"))
    registro.update(campos)
    ruta.write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("cuando, guardado", [
    ("20260920T100012+0000", "2026-09-20T10:00:12+00:00"),
    ("20260920T100012Z", "2026-09-20T10:00:12+00:00"),
    ("2026-W38-7T10:00:00+00:00", "2026-09-20T10:00:00+00:00"),
    ("2026-09-20T10:00:12+0530", "2026-09-20T04:30:12+00:00"),
    ("2026-10-02T00:00:00+02:00", "2026-10-01T22:00:00+00:00"),
    ("2026-10-02T00", None),                          # sin zona: no se sabe que instante es
    ("2026-10-14 por la tarde", None),
])
def test_un_extracted_at_que_python_lee_y_sqlite_no_se_guarda_en_utc(
    almacen, out_v1, cuando, guardado
) -> None:
    _cambiar(out_v1, "01-limpia.json", extracted_at=cuando)
    r = importar_out(almacen, out_v1, None)
    assert (r.importadas, r.rechazadas) == (7, 0)
    fila = almacen.conn.execute(
        "SELECT e.extraido_en, e.contenido_json FROM extraccion AS e JOIN documento AS d "
        "ON d.id = e.documento_id WHERE d.nombre_original = '01-limpia.pdf'").fetchone()
    assert fila["extraido_en"] == guardado
    assert json.loads(fila["contenido_json"])["extracted_at"] == cuando   # el texto, tal cual


def test_nan_o_infinity_se_rechazan_sin_tumbar_la_orden(out_v1, tmp_path, capsys) -> None:
    ruta = out_v1 / "03-con-inyeccion.json"
    ruta.write_text(ruta.read_text(encoding="utf-8").replace(
        '"input_tokens": ', '"input_tokens": NaN, "x": ', 1), encoding="utf-8")
    db = tmp_path / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "importados          6" in salida and "rechazados          1" in salida
    assert "rechazado 03-con-inyeccion.json: NaN no es un valor JSON" in salida


def test_lo_que_la_base_rechaza_es_una_importacion_rechazada(almacen, out_v1, monkeypatch) -> None:
    """Un CHECK que la lectura no previo deshace solo ese fichero, no la orden."""
    from bms_agent.almacen import extracciones

    original = extracciones.leer_registro

    def con_fecha_imposible(contenido):
        leido = original(contenido)
        if leido.source_name == "02-sin-kvk-btw-verlegd.pdf":
            import dataclasses
            return dataclasses.replace(leido, extraido_en="no es un instante")
        return leido

    monkeypatch.setattr("bms_agent.importadores.extracciones.leer_registro", con_fecha_imposible)
    r = importar_out(almacen, out_v1, None)
    assert (r.importadas, r.rechazadas, r.documentos_nuevos) == (6, 1, 6)
    assert "CHECK constraint failed" in dict(r.rechazos)["02-sin-kvk-btw-verlegd.json"]
    assert _recuentos(almacen.conn)["documento"] == 6
    assert almacen.conn.execute(
        "SELECT count(*) FROM importacion WHERE estado = 'rechazada'").fetchone()[0] == 1
    assert verificar_cadena(almacen.conn).ok
    from bms_agent.almacen.evidencia import verificar_evidencia
    assert verificar_evidencia(almacen.conn) == []


def test_importar_out_sin_carpeta_falla_sin_crear_nada(tmp_path, capsys) -> None:
    db = tmp_path / "bms.sqlite3"
    assert main(["importar-out", "--out", str(tmp_path / "no-existe"), "--db", str(db)]) == 1
    assert not db.exists()


def test_el_almacen_en_memoria_y_la_carpeta_temporal_de_los_tests(db, tmp_path) -> None:
    """Las fixtures de conftest: base migrada, reloj fijo y carpeta propia."""
    almacen = Almacen(db, AlmacenDocumentos(tmp_path / "documentos"))
    assert almacen.conn.execute("SELECT count(*) FROM migracion").fetchone()[0] >= 1
    assert db.reloj.ahora().isoformat() == "2026-10-14T09:30:00+00:00"
