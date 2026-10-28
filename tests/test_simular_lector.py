"""scripts/simular_lector.py: el lector de las pruebas en el navegador (paso 17).

Solo con la base de prueba; da los pasos del lector con las mismas funciones (lectura.py),
asi que la app ve lo mismo que con el lector de verdad: los estados en su orden, la pasada
por fases con sus cuentas, el tope y el parar, y un resultado con documentos de la base.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from contextlib import closing

import pytest
from conftest import RAIZ

from bms_agent import demo, lectura, servicios
from bms_agent.almacen import preparar


def _script():
    ruta = RAIZ / "scripts" / "simular_lector.py"
    spec = importlib.util.spec_from_file_location("simular_lector", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def base_de_prueba(tmp_path_factory):
    ruta = tmp_path_factory.mktemp("simular") / "datos" / "demo.sqlite3"
    demo.crear(ruta)
    return ruta


@pytest.fixture
def db(base_de_prueba, tmp_path):
    copia = tmp_path / "datos" / "demo.sqlite3"
    copia.parent.mkdir()
    with closing(sqlite3.connect(base_de_prueba)) as origen, \
            closing(sqlite3.connect(copia)) as destino:
        origen.backup(destino)
    return copia


def _correr(db, capsys, *argumentos) -> tuple[int, dict]:
    codigo = _script().main(["--db", str(db), *argumentos])
    salida = capsys.readouterr()
    texto = salida.out if codigo == 0 else salida.err
    return codigo, json.loads(texto.strip().splitlines()[-1])


def _ana(conn) -> int:
    return conn.execute("SELECT id FROM usuario WHERE nombre LIKE 'Ana%' AND es_sistema = 0"
                        ).fetchone()[0]


def test_se_niega_con_la_base_de_verdad(tmp_path, capsys) -> None:
    real = tmp_path / "datos" / "bms.sqlite3"
    with preparar(real):
        pass
    codigo, respuesta = _correr(real, capsys, "tomar")
    assert codigo == 2 and "DATOS DE PRUEBA" in respuesta["error"]


def test_el_escenario_entero_como_lo_ve_la_app(db, capsys) -> None:
    with preparar(db) as almacen:
        servicios.ejecutar(almacen.conn, "pedir_lectura", {}, usuario_id=_ana(almacen.conn))
    assert _correr(db, capsys, "tomar")[1]["estado"] == "comprobando"
    assert _correr(db, capsys, "contar", "--nuevas", "3", "--ya-leidas", "1")[1][
        "estado"] == "esperando_aprobacion"
    with preparar(db) as almacen:
        conn = almacen.conn
        vista = lectura.para_la_app(conn)["solicitud"]
        assert (vista["pdf_nuevos"], vista["pdf_ya_leidos"], vista["coste_max_usd_micro"]) == (
            3, 1, 3 * 62_000)
        servicios.ejecutar(conn, "aprobar_lectura", {
            "solicitud_id": vista["id"], "huella_estimacion": vista["huella_estimacion"]},
            usuario_id=_ana(conn))
    codigo, respuesta = _correr(db, capsys, "leer", "--pausa", "0", "--duplicados", "1")
    assert (codigo, respuesta["estado"]) == (0, "hecha")
    with preparar(db) as almacen:
        app = lectura.para_la_app(almacen.conn)
    pasada = app["pasada_en_curso"]
    assert [f["fase"] for f in pasada["fases"]] == [
        "cargando", "leyendo", "comparando", "analizando", "organizando", "hecha"]
    assert sorted(r["estado"] for r in pasada["resultado"]) == [
        "nueva", "nueva", "posible_duplicado", "ya_leida"]
    assert all(r["documento_id"] and r["factura_id"] for r in pasada["resultado"])
    assert (pasada["leidas"], pasada["ya_leidas"], pasada["coste_usd_micro"]) == (3, 1, 3 * 38_000)
    assert app["ultima_pasada"]["resultado"] == pasada["resultado"]


def test_el_si_con_la_huella_de_antes_y_el_tope(db, capsys) -> None:
    _correr(db, capsys, "tomar")
    _correr(db, capsys, "contar", "--nuevas", "2")
    with preparar(db) as almacen:
        vieja = lectura.para_la_app(almacen.conn)["solicitud"]["huella_estimacion"]
    assert _correr(db, capsys, "recontar", "--nuevas", "3")[1]["estado"] == (
        "esperando_aprobacion")
    with preparar(db) as almacen:
        conn = almacen.conn
        solicitud = lectura.viva(conn)
        with pytest.raises(lectura.EstimacionCambiada):
            lectura.aprobar(conn, _ana(conn), solicitud["id"], vieja)
        # Un tope que da para una sola.
        lectura.aprobar(conn, _ana(conn), solicitud["id"], solicitud["huella_estimacion"],
                        62_000)
    _correr(db, capsys, "leer", "--pausa", "0")
    with preparar(db) as almacen:
        pasada = lectura.para_la_app(almacen.conn)["pasada_en_curso"]
    assert (pasada["fase"], pasada["leidas"]) == ("tope", 1)


@pytest.mark.parametrize("orden, estado", [("no", "cancelada"), ("caducar", "caducada"),
                                           ("si", "aprobada")])
def test_lo_que_responde_el_lector(db, capsys, orden, estado) -> None:
    _correr(db, capsys, "tomar")
    _correr(db, capsys, "contar")
    assert _correr(db, capsys, orden)[1]["estado"] == estado


def test_los_finales_malos(db, capsys) -> None:
    _correr(db, capsys, "tomar")
    assert _correr(db, capsys, "fallar", "--motivo", "aislamiento")[1]["estado"] == "fallida"
    _correr(db, capsys, "tomar")
    _correr(db, capsys, "contar", "--nuevas", "4")
    _correr(db, capsys, "si")
    assert _correr(db, capsys, "fallar", "--leyendo", "--pausa", "0")[1]["estado"] == "fallida"
    with preparar(db) as almacen:
        pasada = lectura.para_la_app(almacen.conn)["pasada_en_curso"]
    assert pasada["fase"] == "fallida" and pasada["leidas"] == 2
    # Sin nada vivo, una orden que no toca dice por que.
    codigo, respuesta = _correr(db, capsys, "si")
    assert codigo == 2 and "ninguna lectura viva" in respuesta["error"]
