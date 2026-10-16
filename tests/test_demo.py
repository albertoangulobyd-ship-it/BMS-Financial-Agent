"""La base de DATOS DE PRUEBA (paso 13): que ensena de todo y que nunca se mezcla.

Puertas que viven aqui:

- `demo crear` construye datos/demo.sqlite3 y cada bloque del panel (§17) y
  cada nivel de prioridad tienen algo, tambien en fechas que cambian de mes, de
  trimestre y de ano;
- estan los casos que la consola tiene que saber ensenar (duplicado, IBAN
  cambiado, abono, dolares, inyeccion, vencidas, semana sin facturar, PO cerca
  del limite, un trimestre del BTW) y todo es ficticio;
- la consola sobre la base de prueba lleva la banda de DATOS DE PRUEBA, y
  sobre la de verdad no;
- ninguna orden lleva nada de la prueba a la base de verdad: `demo crear` no
  la toca, cada fichero que fabrico la prueba se rechaza en ella por cada via
  (importar, extract, importar-out, politica cargar), y una copia de la base de
  prueba con otro nombre no se abre.
"""

from __future__ import annotations

import http.client
import json
import re
import shutil
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pytest
from conftest import FIXTURES_V1, RAIZ

from bms_agent import checks, consultas, demo, hallazgos, permisos
from bms_agent.almacen import (
    BaseDePruebaMezclada,
    DatosDePrueba,
    abrir,
    contiene_datos_de_prueba,
    es_base_demo,
    preparar,
    raiz_documentos_de,
)
from bms_agent.cli import main
from bms_agent.dominio import Prioridad
from bms_agent.reloj import RelojFijo
from bms_agent.serve import CABECERA_ENTORNO, CABECERA_TOKEN, crear_servidor

FECHA = "2026-10-14"


def _reloj(fecha: str) -> RelojFijo:
    return RelojFijo(datetime.fromisoformat(f"{fecha}T09:30:00+00:00"))


@pytest.fixture(scope="module")
def base_demo(tmp_path_factory):
    """La base de prueba de un dia fijo, compartida por los tests que solo la leen."""
    ruta = tmp_path_factory.mktemp("prueba") / "datos" / "demo.sqlite3"
    resumen = demo.crear(ruta, reloj=_reloj(FECHA))
    return ruta, resumen


def _abrir(ruta: Path, fecha: str = FECHA):
    return preparar(ruta, reloj=_reloj(fecha))


# ============================================================ de todo, en cada bloque

def _comprobar_panel(p: dict) -> None:
    entra, sale = p["dinero_entra"], p["dinero_sale"]
    assert entra["facturas"] > 0 and entra["pendiente_cent"] > 0 and entra["vencido_cent"] > 0
    assert sale["facturas"] > 0 and sale["pendiente_cent"] > 0 and sale["vencido_cent"] > 0
    caja = p["caja"]
    assert caja["ventanas"]["total"]["entrada_cent"] > 0
    assert caja["ventanas"]["total"]["salida_cent"] > 0
    assert caja["cobrado_mes_cent"] > 0 and caja["pagado_mes_cent"] > 0
    assert caja["estimado"]["importe_cent"]
    facturacion = p["facturacion"]
    assert facturacion["estado"] == "ok"
    assert facturacion["sin_facturar"]["periodos"] >= 1
    assert facturacion["sin_facturar"]["valor_cent"] > 0
    assert facturacion["periodos_sin_factura"]
    assert facturacion["diferencias_planning"]["hallazgos"] > 0
    po = p["ordenes_compra"]
    assert po["cliente"]["activas"] >= 1 and po["proveedor"]["activas"] >= 1
    assert po["cerca_del_limite"] and po["cerca_de_caducar"] and po["agotamiento_previsto"]
    btw = p["btw"]
    assert btw["ingresos_cent"] > 0 and btw["iva_repercutido_cent"] > 0
    assert btw["iva_deducible_cent"] > 0
    assert btw["proximo_plazo"] is not None
    # Una administracion al dia: ningun plazo del BTW pasado sin presentar.
    assert btw["plazos_pasados"] == []
    atencion = p["atencion"]
    assert atencion["compras_vencidas"]["facturas"] >= 1
    assert atencion["ventas_vencidas"]["facturas"] >= 1
    assert atencion["excepciones"]["abiertas"] >= 1
    assert atencion["bloqueadas"] and atencion["urgentes"] and atencion["atencion"]
    activas = {c["clave"] for c in atencion["categorias"] if c["activos"]}
    assert {"iban", "duplicados", "planning", "sin_facturar", "ordenes_compra", "vencidas",
            "lecturas_dudosas"} <= activas
    assert p["al_dia"] and p["fuentes_caducadas"] == []


@pytest.mark.parametrize("fecha", [FECHA, "2027-01-02", "2026-08-01", "2026-03-31"])
def test_cada_bloque_del_panel_y_cada_nivel_tienen_algo(tmp_path, fecha) -> None:
    """Del 14 de octubre (a mitad de trimestre), del 2 de enero (semana 53 y trimestre
    nuevo), de un sabado 1 de mes y del ultimo dia de un trimestre."""
    ruta = tmp_path / "datos" / "demo.sqlite3"
    resumen = demo.crear(ruta, reloj=_reloj(fecha))
    assert resumen.creada and resumen.avisos == []
    with _abrir(ruta, fecha) as almacen:
        conn = almacen.conn
        _comprobar_panel(consultas.panel(conn))
        niveles = {f[0] for f in conn.execute("SELECT DISTINCT nivel FROM factura_estado")}
        assert niveles == set(Prioridad.valores())
        assert conn.execute("SELECT count(*) FROM factura_estado WHERE estado_pago = "
                            "'pagada'").fetchone()[0] > 0


def test_estan_los_casos_que_la_consola_tiene_que_ensenar(base_demo) -> None:
    ruta, resumen = base_demo
    assert resumen.avisos == []
    with _abrir(ruta) as almacen:
        conn = almacen.conn

        def abiertos(regla: str) -> list[sqlite3.Row]:
            return conn.execute(
                "SELECT h.*, f.numero FROM hallazgo AS h LEFT JOIN factura AS f "
                "ON f.id = h.factura_id WHERE h.regla = ? AND h.estado = 'abierto'",
                (regla,)).fetchall()

        # Una factura duplicada: las dos copias, bloqueadas.
        [b2] = abiertos("B2")
        copias = conn.execute("SELECT f.id, e.nivel FROM factura AS f JOIN factura_estado AS e "
                              "ON e.factura_id = f.id WHERE f.numero = ?",
                              (b2["numero"],)).fetchall()
        assert len(copias) == 2 and {c["nivel"] for c in copias} == {"bloqueada"}
        # Un IBAN cambiado: F2 y F3, y el IBAN del documento no entra en el registro.
        assert abiertos("F2") and abiertos("F3")
        registro = {f[0] for f in conn.execute("SELECT iban FROM cuenta_bancaria")}
        assert demo.IBAN_CAMBIADO not in registro and demo.IBAN_INYECTADO not in registro
        # El intento de inyeccion: Q3 con su excepcion, y el IBAN de su cabecera es el de siempre.
        [q3] = abiertos("Q3")
        assert conn.execute("SELECT iban_doc FROM factura WHERE id = ?",
                            (q3["factura_id"],)).fetchone()[0] in registro
        assert conn.execute("SELECT count(*) FROM excepcion_hallazgo WHERE hallazgo_id = ?",
                            (q3["id"],)).fetchone()[0] == 1
        # La factura en dolares: X1, bloqueada y fuera de los totales.
        [x1] = abiertos("X1")
        assert conn.execute("SELECT moneda_doc FROM factura WHERE id = ?",
                            (x1["factura_id"],)).fetchone()[0] == "USD"
        # Abonos: uno de compra (propuesto, R5) y uno de venta (confirmado).
        tipos = {(f["sentido"], f["tipo"]) for f in conn.execute(
            "SELECT sentido, tipo FROM factura")}
        assert {("entrante", "nota_credito"), ("saliente", "nota_credito")} <= tipos
        assert abiertos("R5")
        assert conn.execute("SELECT count(*) FROM factura_relacion WHERE estado = "
                            "'confirmada'").fetchone()[0] >= 1
        # Vencidas: una compra de hace mas de treinta dias y una venta de mas de sesenta.
        vencidas = {(f["sentido"], f["nivel"]) for f in conn.execute(
            "SELECT f.sentido, e.nivel FROM factura AS f JOIN factura_estado AS e "
            "ON e.factura_id = f.id WHERE e.estado_pago = 'vencida' AND e.dias_vencida > 30")}
        assert {("entrante", "urgente"), ("saliente", "urgente")} <= vencidas
        # La semana trabajada sin facturar: V6 de un periodo de siete dias, y su V8.
        semanas = [json.loads(h["valores_json"]) for h in abiertos("V6")]
        assert any((datetime.fromisoformat(v["hasta"]) - datetime.fromisoformat(v["desde"])
                    ).days == 6 and not v["estimado"] for v in semanas)
        assert abiertos("V8")
        # Tarifas pactadas con recargo de noche y de fin de semana.
        tarifas = {f["tipo_turno"]: f["tarifa_e4"] for f in conn.execute(
            "SELECT tipo_turno, tarifa_e4 FROM tarifa_acordada WHERE sentido = 'compra' "
            "AND proveedor_id = (SELECT id FROM proveedor WHERE exact_id = '30001')")}
        assert tarifas["nacht"] > tarifas["dag"] and tarifas["weekend"] > tarifas["nacht"]
        assert {f[0].lower() for f in conn.execute(
            "SELECT DISTINCT tipo_turno FROM planning_turno")} >= {"nacht", "weekend", "dag"}
        # PO cerca de su limite y cerca de caducar; el banco; un trimestre del BTW.
        assert abiertos("P5") and abiertos("P7")
        assert conn.execute("SELECT count(*) FROM aplicacion_pago WHERE fuente = 'banco' AND "
                            "estado = 'confirmada'").fetchone()[0] >= 10
        assert conn.execute("SELECT count(*) FROM periodo_btw WHERE estado IN "
                            "('listo_revision', 'presentado')").fetchone()[0] >= 1
        # Lo que han hecho las personas: revisiones, una correccion a mano sin verificar.
        assert conn.execute("SELECT count(*) FROM revision WHERE resultado = "
                            "'revisada'").fetchone()[0] >= 1
        assert abiertos("M1") or conn.execute(
            "SELECT count(*) FROM factura_estado WHERE sin_resolver = 1").fetchone()[0] >= 1


def test_todo_es_ficticio(base_demo) -> None:
    ruta, _resumen = base_demo
    ficticio = re.compile(r"Demo|Voorbeeld|Proef|Fictief|Test")
    with _abrir(ruta) as almacen:
        conn = almacen.conn
        for tabla in ("proveedor", "cliente"):
            for fila in conn.execute(f"SELECT nombre, kvk, btw_id FROM {tabla}"):
                assert ficticio.search(fila["nombre"]), fila["nombre"]
                assert fila["kvk"] is None or fila["kvk"].startswith("99")
                assert fila["btw_id"] is None or "99900" in fila["btw_id"]
        for (iban,) in conn.execute("SELECT iban FROM cuenta_bancaria"):
            assert iban[4:8] == "DEMO" and checks.check_iban({"iban": iban}).status == "ok"
            assert contiene_datos_de_prueba(iban)
        assert {n for (n,) in conn.execute("SELECT nombre FROM usuario WHERE es_sistema = 0")} \
            == {"Ana Demo", "Bram Demo"}
        # Cada fichero que fabrico la prueba lleva la marca: es lo que la base de verdad rechaza.
        rutas = [r for (r,) in conn.execute("SELECT ruta_cas FROM documento")]
        assert rutas and all(r is not None for r in rutas)
        for relativa in rutas:
            contenido = (raiz_documentos_de(ruta) / relativa).read_bytes()
            assert contiene_datos_de_prueba(contenido), relativa
        for (texto,) in conn.execute("SELECT contenido_json FROM extraccion"):
            assert contiene_datos_de_prueba(texto)


def test_iban_demo_pasa_el_modulo_97_y_se_reconoce() -> None:
    vistos = {demo.iban_demo(n) for n in range(1, 200)}
    assert len(vistos) == 199
    for iban in vistos:
        assert checks.check_iban({"iban": iban}).status == "ok"
        assert contiene_datos_de_prueba(iban) and contiene_datos_de_prueba(iban.encode("utf-16"))
    assert not contiene_datos_de_prueba("NL91ABNA0417164300")
    assert not contiene_datos_de_prueba("Demo Beveiliging")


def test_la_base_de_prueba_lleva_su_marca_su_nombre_y_su_carpeta(base_demo, capsys) -> None:
    ruta, _resumen = base_demo
    assert demo.es_demo(ruta)
    with _abrir(ruta) as almacen:
        assert es_base_demo(almacen.conn)
        assert almacen.documentos.raiz == ruta.parent / "demo-documentos"
        assert almacen.ruta_anclas == ruta.parent / "demo-anclas.log"
    assert not (ruta.parent / "documentos").exists() and not (ruta.parent / "anclas.log").exists()
    assert main(["db", "verificar", "--db", str(ruta)]) == 0
    salida = capsys.readouterr()
    assert "Todo cuadra." in salida.out
    # Toda orden sobre la base de prueba lo dice antes de nada.
    assert "DATOS DE PRUEBA" in salida.err


def test_crear_dos_veces_no_toca_lo_que_hay_y_rehacer_empieza_de_cero(tmp_path) -> None:
    ruta = tmp_path / "demo.sqlite3"
    primera = demo.crear(ruta, reloj=_reloj(FECHA))
    antes = ruta.stat().st_mtime_ns
    segunda = demo.crear(ruta, reloj=_reloj(FECHA))
    assert not segunda.creada and ruta.stat().st_mtime_ns == antes
    tercera = demo.crear(ruta, reloj=_reloj(FECHA), rehacer=True)
    assert tercera.creada and tercera.tokens["Ana Demo"] != primera.tokens["Ana Demo"]


# ============================================================ la banda de la consola

def _pedir(puerto: int, ruta: str, cabeceras: dict | None = None):
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
    conexion.request("GET", ruta, headers={"Host": f"127.0.0.1:{puerto}", **(cabeceras or {})})
    respuesta = conexion.getresponse()
    datos = respuesta.read()
    conexion.close()
    return respuesta.status, {k.lower(): v for k, v in respuesta.getheaders()}, datos


class _SinPasadas:
    estado = {"estado": "inactivo"}

    def lanzar(self):
        raise AssertionError("ningun test lanza una pasada")


def _servidor(ruta_db: Path):
    srv = crear_servidor(ruta_db.parent / "facturas", ruta_db.parent / "out", 0,
                         token="t", agente=_SinPasadas(), ruta_db=ruta_db)
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                            daemon=True)
    hilo.start()
    return srv


def test_la_consola_de_la_base_de_prueba_lleva_la_banda(base_demo) -> None:
    ruta, resumen = base_demo
    srv = _servidor(ruta)
    try:
        puerto = srv.server_address[1]
        estado, cabeceras, pagina = _pedir(puerto, "/consola")
        texto = pagina.decode("utf-8")
        assert estado == 200 and cabeceras[CABECERA_ENTORNO.lower()] == "demo"
        # La banda va justo detras de <body>, la pone el servidor (no el script) y el titulo
        # de la pestana lo dice tambien.
        assert re.search(r"<body>\s*<div id=\"datos-de-prueba\"[^>]*>DATOS DE PRUEBA", texto)
        assert "<title>DATOS DE PRUEBA" in texto
        _e, _c, css = _pedir(puerto, "/consola.css")
        assert b".datos-de-prueba{position:sticky" in css
        _e, cabeceras_local, local = _pedir(puerto, "/")
        assert "DATOS DE PRUEBA" in local.decode("utf-8")
        estado, cabeceras, datos = _pedir(puerto, "/api/v2/panel",
                                          {CABECERA_TOKEN: resumen.tokens["Ana Demo"]})
        assert estado == 200 and cabeceras[CABECERA_ENTORNO.lower()] == "demo"
        panel = json.loads(datos)["panel"]
        assert panel["dinero_entra"]["facturas"] > 0 and panel["atencion"]["bloqueadas"] > 0
    finally:
        srv.shutdown()
        srv.server_close()


def test_la_consola_de_la_base_de_verdad_no_lleva_banda(tmp_path) -> None:
    ruta = tmp_path / "datos" / "bms.sqlite3"
    preparar(ruta).cerrar()
    srv = _servidor(ruta)
    try:
        puerto = srv.server_address[1]
        for camino in ("/consola", "/"):
            _estado, cabeceras, pagina = _pedir(puerto, camino)
            assert "DATOS DE PRUEBA" not in pagina.decode("utf-8")
            assert CABECERA_ENTORNO.lower() not in cabeceras
    finally:
        srv.shutdown()
        srv.server_close()


# ============================================================ nunca en la base de verdad

def _base_de_verdad(tmp_path: Path) -> tuple[Path, str]:
    """Una base de verdad en disco con las siete facturas v1 y una persona con su token."""
    from bms_agent.importadores.extracciones import importar_out
    from bms_agent.ingesta import tipar_pendientes

    ruta = tmp_path / "datos" / "bms.sqlite3"
    out = tmp_path / "out-v1"
    out.mkdir()
    for fichero in sorted(FIXTURES_V1.glob("*.json")):
        shutil.copy2(fichero, out / fichero.name)
    with preparar(ruta) as almacen:
        importar_out(almacen, out, None)
        tipar_pendientes(almacen.conn)
        conn = almacen.conn
        # La primera pasada del motor apunta la politica por defecto: asi lo que cambie despues
        # es solo lo que hayan hecho las ordenes del test.
        hallazgos.recalcular(conn)
        permisos.asegurar_roles_base(conn)
        ana = permisos.crear_usuario(conn, "Ana")
        permisos.asignar_rol(conn, ana, "administrador")
        token = permisos.emitir_token(conn, ana)
    return ruta, token


_TABLAS = ("documento", "extraccion", "factura", "factura_linea", "proveedor", "cliente",
           "objeto", "cuenta_bancaria", "politica_version", "planning_turno",
           "movimiento_bancario", "orden_compra", "tarifa_acordada")


def _foto(ruta: Path) -> dict:
    """Lo que la prueba podria haber dejado: cuantas filas hay de lo que traen sus ficheros, y
    si alguna fila de cualquier tabla lleva su marca. Una importacion rechazada (importar-out
    apunta cada fichero que no admite, con su motivo) no trae nada."""
    conn = sqlite3.connect(ruta)
    try:
        cuentas = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in _TABLAS}
        cuentas["importacion"] = conn.execute(
            "SELECT count(*) FROM importacion WHERE estado <> 'rechazada'").fetchone()[0]
        marcadas = []
        for (tabla,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            for fila in conn.execute(f'SELECT * FROM "{tabla}"'):
                if any(isinstance(v, str) and contiene_datos_de_prueba(v) for v in fila):
                    marcadas.append(tabla)
                    break
        documentos = sorted(p.name for p in raiz_documentos_de(ruta).rglob("*") if p.is_file())
    finally:
        conn.close()
    return {"cuentas": cuentas, "marcadas": marcadas, "documentos": documentos}


def test_crear_no_toca_la_base_de_verdad(tmp_path, monkeypatch, capsys) -> None:
    real, _token = _base_de_verdad(tmp_path)
    monkeypatch.setenv("BMS_DB", str(real))
    antes = _foto(real)
    with sqlite3.connect(real) as conn:
        volcado = "\n".join(conn.iterdump())
    assert main(["demo", "crear"]) == 0
    salida = capsys.readouterr().out
    assert "DATOS DE PRUEBA" in salida and "Ana Demo" in salida
    # Al lado de la de verdad, con su carpeta y sus anclas; la de verdad, igual que estaba.
    assert demo.es_demo(real.parent / "demo.sqlite3")
    assert (real.parent / "demo-documentos").is_dir() and (real.parent / "demo-anclas.log").exists()
    assert _foto(real) == antes and antes["marcadas"] == []
    with sqlite3.connect(real) as conn:
        assert "\n".join(conn.iterdump()) == volcado


@pytest.mark.parametrize("nombre", ["bms.sqlite3", "demo.db", "prueba.sqlite3",
                                    "demo.sqlite3.bak"])
def test_crear_solo_escribe_en_un_fichero_llamado_demo_sqlite3(tmp_path, nombre) -> None:
    with pytest.raises(DatosDePrueba):
        demo.crear(tmp_path / nombre)
    assert not (tmp_path / nombre).exists()
    assert main(["demo", "crear", "--db", str(tmp_path / nombre)]) == 2


def test_crear_no_sobrescribe_una_base_que_no_es_de_prueba(tmp_path) -> None:
    """Una base de verdad a la que alguien le cambio el nombre a demo.sqlite3 no se toca, ni
    con --rehacer, y no se abre."""
    real, _token = _base_de_verdad(tmp_path)
    impostora = real.parent / "demo.sqlite3"
    shutil.copy(real, impostora)
    contenido = impostora.read_bytes()
    for rehacer in (False, True):
        with pytest.raises(DatosDePrueba):
            demo.crear(impostora, rehacer=rehacer)
    assert impostora.read_bytes() == contenido
    with pytest.raises(BaseDePruebaMezclada):
        abrir(impostora)
    assert main(["demo", "crear", "--db", str(impostora), "--rehacer"]) == 2


def test_una_copia_de_la_base_de_prueba_con_otro_nombre_no_se_abre(base_demo, tmp_path,
                                                                     capsys) -> None:
    """Copiar demo.sqlite3 encima de la base de verdad no la convierte en la de verdad: la
    marca viaja con el fichero y ninguna orden la abre."""
    ruta, _resumen = base_demo
    copia = tmp_path / "datos" / "bms.sqlite3"
    copia.parent.mkdir(parents=True)
    shutil.copy(ruta, copia)
    with pytest.raises(BaseDePruebaMezclada):
        preparar(copia)
    for orden in (["facturas"], ["resumen"], ["db", "verificar"], ["recalcular"]):
        assert main([*orden, "--db", str(copia)]) == 2, orden
    assert "DATOS DE PRUEBA" in capsys.readouterr().err
    with pytest.raises(BaseDePruebaMezclada):
        abrir(tmp_path / "otra" / "demo.sqlite3")
    assert not (tmp_path / "otra" / "demo.sqlite3").exists()


class _ClienteQueNoSeLlama:
    def __getattr__(self, nombre):
        raise AssertionError("un PDF de prueba no se manda a la API")


def test_ninguna_orden_lleva_lo_de_la_prueba_a_la_base_de_verdad(base_demo, tmp_path,
                                                                  monkeypatch, capsys) -> None:
    """Cada fichero que fabrico `demo crear` (los CSV de Exact, del maestro, de las PO y de
    TRNSPRNT, los extractos del banco, los PDF, las extracciones y la politica), por cada
    orden que mete datos, se queda fuera de la base de verdad."""
    ruta, _resumen = base_demo
    real, token = _base_de_verdad(tmp_path)
    antes = _foto(real)
    buzon = tmp_path / "buzon"
    buzon.mkdir()
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    try:
        importaciones = conn.execute(
            "SELECT i.fuente, i.tipo, d.ruta_cas, d.nombre_original FROM importacion AS i "
            "JOIN documento AS d ON d.id = i.documento_id ORDER BY i.id").fetchall()
        pdfs = conn.execute("SELECT ruta_cas, nombre_original FROM documento WHERE tipo_mime = "
                            "'application/pdf'").fetchall()
        extracciones = conn.execute(
            "SELECT e.contenido_json, d.sha256 FROM extraccion AS e JOIN documento AS d "
            "ON d.id = e.documento_id").fetchall()
        empresa = conn.execute("SELECT contenido FROM politica_version WHERE fichero = "
                               "'empresa.yaml' ORDER BY id DESC LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    raiz = raiz_documentos_de(ruta)

    # importar: cada fichero de cada fuente, tambien simulando.
    fuentes = {(f["fuente"], f["tipo"]) for f in importaciones}
    assert {("exact", "proveedores"), ("exact", "clientes"), ("exact", "facturas_venta"),
            ("maestro_csv", "tarifas"), ("po_csv", "ordenes_compra"), ("trnsprnt", "planning"),
            ("banco", "extracto")} <= fuentes
    for fila in importaciones:
        fichero = buzon / fila["nombre_original"]
        shutil.copy(raiz / fila["ruta_cas"], fichero)
        for extra in ([], ["--simular"]):
            codigo = main(["importar", fila["fuente"], fila["tipo"], str(fichero), "--db",
                           str(real), "--token", token, *extra])
            assert codigo == 1, (fila["fuente"], fila["tipo"], extra)
            assert "DATOS DE PRUEBA" in capsys.readouterr().err

    # extract: los PDF de la prueba no se mandan a la API ni entran.
    facturas = tmp_path / "facturas"
    facturas.mkdir()
    for fila in pdfs:
        shutil.copy(raiz / fila["ruta_cas"], facturas / f"{fila['ruta_cas'][-20:]}.pdf")
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: _ClienteQueNoSeLlama())
    main(["extract", str(facturas), "--db", str(real), "--out", str(tmp_path / "out")])
    assert "DATOS DE PRUEBA" in capsys.readouterr().out
    assert not list((tmp_path / "out").glob("*.json"))

    # importar-out: las extracciones de la prueba, como si estuvieran en out/.
    out = tmp_path / "out-prueba"
    out.mkdir()
    for fila in extracciones:
        (out / f"{fila['sha256'][:12]}.json").write_text(fila["contenido_json"],
                                                        encoding="utf-8")
    main(["importar-out", "--out", str(out), "--db", str(real)])
    capsys.readouterr()

    # politica cargar: la empresa de la prueba, con sus cuentas DEMO.
    fichero = tmp_path / "empresa.yaml"
    fichero.write_text(empresa, encoding="utf-8")
    assert main(["politica", "cargar", str(fichero), "--db", str(real), "--token", token]) != 0
    capsys.readouterr()

    despues = _foto(real)
    assert despues["cuentas"] == antes["cuentas"], (antes["cuentas"], despues["cuentas"])
    assert despues == antes and antes["marcadas"] == []


def test_ningun_codigo_junta_dos_bases() -> None:
    """Para copiar de una base a otra haria falta abrir las dos a la vez: ningun modulo hace un
    ATTACH, y ninguna orden tiene mas opcion de base que su --db."""
    for fichero in (RAIZ / "src" / "bms_agent").rglob("*.py"):
        texto = fichero.read_text(encoding="utf-8")
        assert not re.search(r"\bATTACH\b", texto, re.IGNORECASE), fichero.name
    cli = (RAIZ / "src" / "bms_agent" / "cli.py").read_text(encoding="utf-8")
    opciones = set(re.findall(r'add_argument\(\s*"(--[a-z-]*(?:db|base|sqlite)[a-z-]*)"', cli))
    assert opciones == {"--db"}


def test_el_extractor_no_paga_un_pdf_de_prueba_sin_base(tmp_path, base_demo) -> None:
    """Sin almacen (solo out/), un PDF de la prueba tampoco va a la API: lo de out/ podria
    acabar en la base de verdad con importar-out."""
    from bms_agent.extract import extraer_pasada

    ruta, _resumen = base_demo
    with sqlite3.connect(ruta) as conn:
        [relativa] = conn.execute("SELECT ruta_cas FROM documento WHERE tipo_mime = "
                                  "'application/pdf' LIMIT 1").fetchone()
    pdf = tmp_path / "prueba.pdf"
    shutil.copy(raiz_documentos_de(ruta) / relativa, pdf)
    resultado = extraer_pasada(_ClienteQueNoSeLlama(), [pdf], tmp_path / "out")
    assert resultado.extraidas == 0 and resultado.fallidas == 1
    assert "DATOS DE PRUEBA" in resultado.errores[0]


@pytest.fixture
def demo_propia(base_demo, tmp_path):
    """Una copia de la base de prueba que el test puede tocar (con sus originales)."""
    ruta, resumen = base_demo
    copia = tmp_path / "datos" / "demo.sqlite3"
    copia.parent.mkdir()
    origen = sqlite3.connect(ruta)
    destino = sqlite3.connect(copia)
    try:
        origen.backup(destino)
    finally:
        destino.close()
        origen.close()
    shutil.copytree(raiz_documentos_de(ruta), raiz_documentos_de(copia))
    return copia, resumen


class _ClienteQueCuenta:
    def __init__(self) -> None:
        self.llamadas = 0

    def __getattr__(self, nombre):
        self.llamadas += 1
        raise AssertionError("no se tenia que llamar a la API")


def test_un_pdf_de_prueba_no_se_paga_tampoco_en_la_base_de_prueba(demo_propia,
                                                                  tmp_path) -> None:
    """-Demo con un PDF de `demo crear` en el buzon: su extraccion ya esta en la base de
    prueba, y uno de prueba no va nunca a la API (tampoco si en la base no esta)."""
    from bms_agent.extract import extraer_pasada

    ruta, _resumen = demo_propia
    with sqlite3.connect(ruta) as conn:
        filas = conn.execute("SELECT ruta_cas FROM documento WHERE tipo_mime = "
                             "'application/pdf' ORDER BY id LIMIT 2").fetchall()
    pdfs = []
    for numero, (relativa,) in enumerate(filas):
        pdfs.append(tmp_path / f"prueba-{numero}.pdf")
        shutil.copy(raiz_documentos_de(ruta) / relativa, pdfs[-1])
    # Uno que la base no conoce: el mismo PDF con un byte de mas al final.
    otro = tmp_path / "prueba-otra.pdf"
    otro.write_bytes(pdfs[0].read_bytes() + b"\n")
    cliente = _ClienteQueCuenta()
    with preparar(ruta, reloj=_reloj(FECHA)) as almacen:
        r = extraer_pasada(cliente, [*pdfs, otro], tmp_path / "out", almacen=almacen)
    assert cliente.llamadas == 0
    assert (r.reutilizadas, r.extraidas, r.fallidas) == (2, 0, 1)
    assert "no se manda nunca a la API" in r.errores[0]


def test_la_base_de_prueba_no_admite_nada_de_verdad(demo_propia, tmp_path, pdfs_ejemplo,
                                                     capsys) -> None:
    """El buzon es el mismo para las dos bases: con -Demo, un PDF o un fichero de verdad no se
    paga, no entra en la base de prueba y no sale del buzon como si hubiera entrado."""
    from bms_agent.extract import extraer_pasada

    ruta, resumen = demo_propia
    antes = _foto(ruta)
    cliente = _ClienteQueCuenta()
    with preparar(ruta, reloj=_reloj(FECHA)) as almacen:
        r = extraer_pasada(cliente, sorted(pdfs_ejemplo.glob("*.pdf")), tmp_path / "out",
                           almacen=almacen)
    assert cliente.llamadas == 0 and r.extraidas == 0 and r.fallidas == 3
    assert all("no es de los DATOS DE PRUEBA" in e for e in r.errores)
    token = resumen.tokens["Ana Demo"]
    for fuente, tipo, fichero in (
            ("exact", "proveedores", "exact-proveedores-v1.csv"),
            ("banco", "extracto", "banco-extracto-ing-v1.csv")):
        codigo = main(["importar", fuente, tipo,
                       str(RAIZ / "tests" / "fixtures" / "importacion" / fichero),
                       "--db", str(ruta), "--token", token])
        assert codigo == 1, (fuente, tipo)
        assert "no es de los DATOS DE PRUEBA" in capsys.readouterr().err
    assert _foto(ruta) == antes
