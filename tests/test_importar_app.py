"""Importar desde la app (paso 15): POST /api/v2/importar y las lecturas nuevas de /api/v2.

Puertas que viven aqui:

- simular no guarda nada: la base es byte a byte la misma (su volcado entero) antes y
  despues, y la simulacion dice lo que entraria;
- importar de verdad es la misma orden que `bms-agent importar`: la persona queda en la
  importacion, el fichero repetido no entra dos veces y queda en la historia;
- el permiso importar_datos se mira antes de leer el fichero; sin token, 401; desde otro
  origen, 403; sin JSON, 415;
- el limite de tamano (del cuerpo y del fichero ya decodificado) es un 413 con su codigo;
- un fichero mal formado, uno que nadie reconoce o uno que reconocen dos clases dicen su
  codigo y no escriben nada; el nombre del fichero nunca es una ruta;
- las lecturas nuevas (importaciones, lectura, empresa, aislamiento), los roles de
  /api/v2/yo y /api/v2/personas y las `razones` de las listas de partes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

import pytest
from conftest import persona
from test_consola import AgenteFalso, _pedir

from bms_agent import consultas, importar_web, permisos
from bms_agent.almacen import preparar
from bms_agent.importadores.tabular import mapeos
from bms_agent.serve import CABECERA_TOKEN, crear_servidor

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures" / "importacion"
PROVEEDORES = FIXTURES / "exact-proveedores-v1.csv"
CLIENTES = FIXTURES / "exact-clientes-v1.csv"


def _volcado(db: Path) -> str:
    """La huella de todo lo que hay en la base (cada tabla y cada fila)."""
    with closing(sqlite3.connect(db)) as conn:
        return hashlib.sha256("\n".join(conn.iterdump()).encode("utf-8")).hexdigest()


@pytest.fixture
def base(tmp_path):
    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        conn = almacen.conn
        ana = persona(conn, "Ana", "administracion")
        carla = persona(conn, "Carla", "consulta")
        tokens = {"ana": permisos.emitir_token(conn, ana),
                  "carla": permisos.emitir_token(conn, carla)}
    return db, tokens


def _arrancar(db: Path, tmp_path: Path, **opciones):
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "out", 0, token="token-servidor",
                         agente=AgenteFalso(), ruta_db=db, **opciones)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                     daemon=True).start()
    return srv


@pytest.fixture
def servidor(base, tmp_path):
    db, tokens = base
    srv = _arrancar(db, tmp_path)
    try:
        yield srv.server_address[1], tokens, db
    finally:
        srv.shutdown()
        srv.server_close()


def _cuerpo(fichero: Path | None = None, *, contenido: bytes | None = None,
            nombre: str | None = None, **extra) -> dict:
    datos = contenido if contenido is not None else fichero.read_bytes()
    return {"fichero": nombre or (fichero.name if fichero else "fichero.csv"),
            "contenido": base64.b64encode(datos).decode("ascii"), **extra}


def _importar(puerto: int, token: str | None, cuerpo: dict | bytes, **cabeceras):
    texto = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode("utf-8")
    pedir = {"Content-Type": "application/json", **cabeceras}
    if token:
        pedir[CABECERA_TOKEN] = token
    estado, _c, datos = _pedir(puerto, "POST", "/api/v2/importar", pedir, texto)
    return estado, json.loads(datos) if datos else None


def _leer(puerto: int, ruta: str, token: str):
    estado, _c, datos = _pedir(puerto, "GET", ruta, {CABECERA_TOKEN: token})
    return estado, json.loads(datos)


# ============================================================ simular y despues importar

def test_la_simulacion_dice_lo_que_entraria_y_no_guarda_nada(servidor) -> None:
    puerto, tokens, db = servidor
    antes = _volcado(db)
    estado, cuerpo = _importar(puerto, tokens["ana"], _cuerpo(PROVEEDORES, simular=True))
    assert estado == 200, cuerpo
    r = cuerpo["importacion"]
    # Sin decir que es: lo reconoce por sus columnas, como el importador.
    assert (r["fuente"], r["tipo"], r["simulada"]) == ("exact", "proveedores", True)
    lotes = {lote["tipo"]: lote for lote in r["lotes"]}
    assert lotes["proveedores"]["nuevos"] > 0 and lotes["proveedores"]["aceptadas"] > 0
    assert lotes["proveedores"]["importacion_id"] is None
    assert lotes["cuentas"]["cuentas"]["nuevas"] > 0
    assert _volcado(db) == antes
    estado, historia = _leer(puerto, "/api/v2/importaciones", tokens["ana"])
    assert estado == 200 and historia["importaciones"] == []


def test_importar_de_verdad_guarda_queda_en_la_historia_y_no_entra_dos_veces(servidor) -> None:
    puerto, tokens, db = servidor
    estado, cuerpo = _importar(puerto, tokens["ana"],
                               _cuerpo(PROVEEDORES, simular=False, exportado="2026-10-16"))
    assert estado == 200, cuerpo
    r = cuerpo["importacion"]
    assert r["simulada"] is False and all(lote["importacion_id"] for lote in r["lotes"])
    estado, historia = _leer(puerto, "/api/v2/importaciones", tokens["ana"])
    assert {(i["fuente"], i["tipo"], i["persona"], i["fichero"])
            for i in historia["importaciones"]} >= {
        ("exact", "proveedores", "Ana", PROVEEDORES.name)}
    assert historia["importaciones"][0]["exportado_en"].startswith("2026-10-16")
    assert historia["limite_bytes"] == importar_web.MAX_FICHERO
    assert {"fuente": "banco", "tipo": "extracto"} in historia["tipos"]
    assert any(f["fuente"] == "exact" and f["tipo"] == "proveedores"
               for f in historia["fuentes"])
    _e, lista = _leer(puerto, "/api/v2/proveedores", tokens["ana"])
    assert len(lista["proveedores"]) == lotes_de(r, "proveedores")["aceptadas"]
    # El mismo fichero otra vez: no hace nada (lo mismo que la CLI).
    antes = _volcado(db)
    estado, otra = _importar(puerto, tokens["ana"], _cuerpo(PROVEEDORES, simular=False))
    assert estado == 200 and all(lote["repetida"] for lote in otra["importacion"]["lotes"])
    assert _volcado(db) == antes


def lotes_de(resultado: dict, tipo: str) -> dict:
    return next(lote for lote in resultado["lotes"] if lote["tipo"] == tipo)


def test_la_eleccion_explicita_y_un_fichero_que_no_es_de_esa_clase(servidor) -> None:
    puerto, tokens, db = servidor
    estado, cuerpo = _importar(puerto, tokens["ana"], _cuerpo(
        CLIENTES, fuente="exact", tipo="clientes", simular=True))
    assert estado == 200 and cuerpo["importacion"]["tipo"] == "clientes"
    antes = _volcado(db)
    estado, cuerpo = _importar(puerto, tokens["ana"], _cuerpo(
        PROVEEDORES, fuente="exact", tipo="clientes", simular=True))
    assert (estado, cuerpo["codigo"]) == (400, "fichero_no_valido")
    estado, cuerpo = _importar(puerto, tokens["ana"], _cuerpo(
        PROVEEDORES, fuente="exact", tipo="no_existe", simular=True))
    assert (estado, cuerpo["codigo"]) == (400, "invalido")
    assert _volcado(db) == antes


# ============================================================ las puertas

def test_sin_permiso_es_un_403_antes_de_leer_el_fichero(servidor) -> None:
    puerto, tokens, db = servidor
    # Un fichero que ni siquiera es base64: si se leyera antes del permiso seria un 400.
    estado, cuerpo = _importar(puerto, tokens["carla"], {"fichero": "x.csv", "contenido": "%%"})
    assert (estado, cuerpo["codigo"]) == (403, "sin_permiso")
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT count(*) FROM importacion").fetchone()[0] == 0
        # La denegacion queda en la auditoria, como la de cualquier orden.
        assert conn.execute("SELECT count(*) FROM evento WHERE tipo = 'permiso_denegado'"
                            ).fetchone()[0] >= 1
    estado, cuerpo = _importar(puerto, None, _cuerpo(PROVEEDORES, simular=True))
    assert (estado, cuerpo["codigo"]) == (401, "no_autenticado")
    estado, cuerpo = _importar(puerto, tokens["ana"], _cuerpo(PROVEEDORES, simular=True),
                               **{"Content-Type": "text/plain"})
    assert (estado, cuerpo["codigo"]) == (415, "tipo_no_admitido")


def test_desde_otro_origen_no_se_importa(base, tmp_path) -> None:
    db, tokens = base
    srv = _arrancar(db, tmp_path, origenes_extra=["http://localhost:5173"])
    try:
        puerto = srv.server_address[1]
        estado, cuerpo = _importar(puerto, tokens["ana"], _cuerpo(PROVEEDORES, simular=True),
                                   Origin="http://localhost:5173")
        assert (estado, cuerpo["codigo"]) == (403, "otro_origen")
        estado, cuerpo = _importar(puerto, tokens["ana"], _cuerpo(PROVEEDORES, simular=True),
                                   Origin="http://evil.example")
        assert (estado, cuerpo["codigo"]) == (403, "origen_no_permitido")
    finally:
        srv.shutdown()
        srv.server_close()


def test_el_limite_de_tamano_del_cuerpo_y_del_fichero(servidor, monkeypatch) -> None:
    puerto, tokens, db = servidor
    antes = _volcado(db)
    monkeypatch.setattr(importar_web, "MAX_FICHERO", 600)
    monkeypatch.setattr(importar_web, "MAX_CUERPO", 2000)
    grande = _cuerpo(contenido=b"x" * 3000, nombre="grande.csv", simular=True)
    estado, cuerpo = _importar(puerto, tokens["ana"], grande)
    assert (estado, cuerpo["codigo"]) == (413, "fichero_demasiado_grande")
    # El cuerpo cabe, pero el fichero ya decodificado no.
    medio = _cuerpo(contenido=b"x" * 900, nombre="medio.csv", simular=True)
    estado, cuerpo = _importar(puerto, tokens["ana"], medio)
    assert (estado, cuerpo["codigo"]) == (413, "fichero_demasiado_grande")
    assert _volcado(db) == antes


def test_lo_mal_formado_dice_su_codigo_y_no_escribe_nada(servidor) -> None:
    puerto, tokens, db = servidor
    antes = _volcado(db)
    casos = [
        ({"fichero": "x.csv", "contenido": "no es base64!"}, "invalido"),
        ({"fichero": "x.csv", "contenido": ""}, "invalido"),
        ({"fichero": "", "contenido": "eA=="}, "invalido"),
        ({**_cuerpo(PROVEEDORES), "ruta": "/etc/passwd"}, "invalido"),
        ({**_cuerpo(PROVEEDORES), "simular": "si"}, "invalido"),
        ({**_cuerpo(PROVEEDORES), "exportado": "16-10-2026"}, "invalido"),
        ({**_cuerpo(PROVEEDORES), "fuente": "exact"}, "invalido"),
        ({**_cuerpo(PROVEEDORES), "confirmar": True, "simular": True}, "invalido"),
        (_cuerpo(contenido=b"\x00\x01 nada que ver", nombre="raro.bin", simular=True),
         "fichero_no_reconocido"),
        (_cuerpo(contenido=b"<Document><nada/></Document>", nombre="banco.xml",
                 simular=True), "fichero_no_valido"),
        (_cuerpo(contenido=b"nada: 1", nombre="po.yaml", simular=True),
         "fichero_no_reconocido"),
        (_cuerpo(contenido=b"ordenes: 12", nombre="po.yaml", simular=True),
         "fichero_no_valido"),
    ]
    for cuerpo, codigo in casos:
        estado, respuesta = _importar(puerto, tokens["ana"], cuerpo)
        assert (estado, respuesta["codigo"]) == (400, codigo), (cuerpo.get("fichero"), respuesta)
    estado, respuesta = _importar(puerto, tokens["ana"], b"{no es json")
    assert (estado, respuesta["codigo"]) == (400, "invalido")
    assert _volcado(db) == antes


def _cabeceras_de(fuente: str, tipo: str) -> tuple[str, ...]:
    return next(m.cabecera for m in mapeos() if (m.fuente, m.tipo) == (fuente, tipo))


def test_un_fichero_que_reconocen_dos_clases_pide_elegir(servidor) -> None:
    puerto, tokens, db = servidor
    columnas = list(dict.fromkeys([*_cabeceras_de("exact", "proveedores"),
                                   *_cabeceras_de("exact", "clientes")]))
    contenido = (";".join(columnas) + "\n" + ";".join("x" for _ in columnas) + "\n").encode()
    assert {("exact", "proveedores"), ("exact", "clientes")} <= set(
        importar_web.detectar(contenido, "los-dos.csv"))
    antes = _volcado(db)
    estado, cuerpo = _importar(puerto, tokens["ana"], _cuerpo(
        contenido=contenido, nombre="los-dos.csv", simular=True))
    assert (estado, cuerpo["codigo"]) == (400, "tipo_ambiguo")
    assert {"fuente": "exact", "tipo": "clientes"} in cuerpo["candidatos"]
    assert _volcado(db) == antes


def test_el_nombre_del_fichero_es_solo_un_nombre() -> None:
    assert importar_web.nombre_de_fichero("../../etc/passwd") == "passwd"
    assert importar_web.nombre_de_fichero("C:\\Users\\ana\\export.csv") == "export.csv"
    assert importar_web.nombre_de_fichero("ex\x00port\n.csv") == "export.csv"
    for malo in ("", "..", "a/", "x" * 201, 12, None):
        with pytest.raises(importar_web.PeticionNoValida):
            importar_web.nombre_de_fichero(malo)


def test_detectar_el_banco_y_el_yaml_de_po() -> None:
    banco = (RAIZ / "tests" / "fixtures" / "banco" / "camt053-001.02.xml").read_bytes()
    assert importar_web.detectar(banco, "extracto.xml") == [("banco", "extracto")]
    yaml_po = (FIXTURES / "po_csv-yaml.yaml").read_bytes()
    assert importar_web.detectar(yaml_po, "po.yaml") == [("po_csv", "ordenes_compra")]
    assert importar_web.detectar(b"modificaciones: []\n", "po.yml") == [
        ("po_csv", "modificaciones_po")]
    planning = (FIXTURES / "trnsprnt-planning-v1.csv").read_bytes()
    assert importar_web.detectar(planning, "planning.csv") == [("trnsprnt", "planning")]


# ============================================================ las lecturas nuevas

def test_yo_y_las_personas_llevan_sus_roles(servidor) -> None:
    puerto, tokens, _db = servidor
    _e, yo = _leer(puerto, "/api/v2/yo", tokens["carla"])
    assert yo["roles"] == ["consulta"] and yo["permisos"] == ["ver_facturas"]
    _e, gente = _leer(puerto, "/api/v2/personas", tokens["ana"])
    assert {(p["nombre"], tuple(p["roles"])) for p in gente["personas"]} == {
        ("Ana", ("administracion",)), ("Carla", ("consulta",))}


def test_la_lectura_de_pdf_la_empresa_y_el_aislamiento(servidor) -> None:
    puerto, tokens, _db = servidor
    estado, cuerpo = _leer(puerto, "/api/v2/lectura", tokens["carla"])
    assert estado == 200
    lectura = cuerpo["lectura"]
    assert (lectura["extracciones"], lectura["coste_usd_micro"], lectura["estimacion"]) == (
        0, None, None)
    assert lectura["pasadas"] == [] and isinstance(lectura["lee_aqui"], bool)
    _e, empresa = _leer(puerto, "/api/v2/empresa", tokens["carla"])
    assert empresa["empresa"]["nombre"] == "BM Support BV"
    assert empresa["empresa"]["completa"] is False
    _e, aislamiento = _leer(puerto, "/api/v2/aislamiento", tokens["carla"])
    assert aislamiento["aislamiento"] == {"aplica": False, "entorno": "local",
                                          "correcto": None, "papeles": []}


def test_el_aislamiento_por_papeles_sin_copiar_el_texto(base, tmp_path) -> None:
    db, tokens = base
    srv = _arrancar(db, tmp_path, aislamiento=lambda: ["lector: FALLA (<b>x</b>)"])
    try:
        _e, cuerpo = _leer(srv.server_address[1], "/api/v2/aislamiento", tokens["ana"])
    finally:
        srv.shutdown()
        srv.server_close()
    a = cuerpo["aislamiento"]
    assert (a["aplica"], a["entorno"], a["correcto"]) == (True, "nativo", False)
    assert {p["papel"]: p["bien"] for p in a["papeles"]} == {
        "consola": True, "lector": False, "salida": True, "orden": True}
    assert {p["papel"]: p["estado"] for p in a["papeles"]} == {
        "consola": "correcto", "lector": "falla", "salida": "correcto", "orden": "correcto"}
    assert "<b>" not in json.dumps(a)


def test_el_estado_de_cada_papel_sale_del_principio_del_problema() -> None:
    """La pastilla de la app dice si un papel falla, no se comprobo o se comprobo hace
    demasiado; se saca de los textos que escribe aislamiento.problemas_de, sin copiarlos."""
    from datetime import datetime, timedelta, timezone

    from bms_agent import aislamiento
    from bms_agent.app_local import ESTADOS_AISLAMIENTO, estados_de_papeles

    ahora = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
    bien = {"correcto": True, "fecha": ahora.isoformat(),
            "comprobaciones": [{"nombre": "red", "bien": True}]}
    viejo = {**bien, "fecha": (ahora - aislamiento.CADUCIDAD - timedelta(days=1)).isoformat()}
    futuro = {**bien, "fecha": (ahora + timedelta(days=3)).isoformat()}
    datos = {"roles": {"consola": bien, "lector": viejo, "salida": futuro}}
    problemas = aislamiento.problemas_de(datos, ahora)
    assert estados_de_papeles(problemas) == {
        "consola": "correcto", "lector": "caducada", "salida": "caducada", "orden": "sin_comprobar"}
    malo = {"correcto": False, "fecha": ahora.isoformat(),
            "comprobaciones": [{"nombre": "<script>", "bien": False}]}
    problemas = aislamiento.problemas_de({"roles": {"consola": bien, "lector": malo, "salida": bien,
                                                    "orden": bien}}, ahora)
    assert estados_de_papeles(problemas)["lector"] == "falla"
    assert estados_de_papeles([]) == dict.fromkeys(("consola", "lector", "salida", "orden"), "correcto")
    # Un problema que no nombra un papel conocido: ninguno pasa por bien.
    assert set(estados_de_papeles(["otro: lo que sea"]).values()) == {"falla"}
    assert set(estados_de_papeles(problemas).values()) <= set(ESTADOS_AISLAMIENTO)


def test_el_coste_de_la_lectura_sale_de_las_extracciones_guardadas(tmp_path, out_v1) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        lectura = consultas.lectura_pdf(almacen.conn)
    assert lectura["extracciones"] == lectura["documentos"] == 7
    assert lectura["coste_usd_micro"] is None or lectura["coste_usd_micro"] > 0
    assert sum(p["documentos"] for p in lectura["pasadas"]) <= 7
    assert all(isinstance(v, int) for p in lectura["pasadas"] for v in (p["documentos"],))


def test_las_listas_de_partes_llevan_sus_razones(tmp_path) -> None:
    from bms_agent import demo

    ruta = tmp_path / "datos" / "demo.sqlite3"
    demo.crear(ruta)
    with preparar(ruta) as almacen:
        conn = almacen.conn
        proveedores = {p["nombre"]: [r["regla"] for r in p["razones"]]
                       for p in consultas.proveedores(conn)}
        clientes = {c["nombre"]: [r["regla"] for r in c["razones"]]
                    for c in consultas.clientes(conn)}
        objetos = {o["codigo"]: [r["regla"] for r in o["razones"]]
                   for o in consultas.objetos_resumen(conn)["objetos"]}
        ordenes = {o["numero"]: [r["regla"] for r in o["razones"]]
                   for o in consultas.ordenes_compra(conn)}
        razon = consultas.clientes(conn)[0]["razones"][0]
    # Las de sus facturas (el numero repetido de J. Voorbeeld) y las que la senalan a ella:
    # lo sin facturar de un cliente (V6, V8) no es de ninguna factura.
    assert "B2" in proveedores["J. Voorbeeld Beveiliging (zzp)"]
    assert {"V6", "V8"} <= set(clientes["Demo Havenbedrijf BV"])
    assert "B2" in objetos["HAVEN-NOORD"]
    assert "P10" in ordenes["PO-DEMO-4501"]
    assert set(razon) == {"id", "regla", "severidad", "estado", "resultado", "valores"}
    # Lo mas urgente primero: lo que bloquea antes que lo que retiene y que lo que avisa.
    orden = {"bloqueo": 0, "retencion": 1, "aviso": 2}
    for lista in (consultas.proveedores, consultas.clientes):
        with preparar(ruta) as almacen:
            for fila in lista(almacen.conn):
                severidades = [orden[r["severidad"]] for r in fila["razones"]
                               if r["estado"] == "abierto"]
                assert severidades == sorted(severidades), fila["nombre"]
