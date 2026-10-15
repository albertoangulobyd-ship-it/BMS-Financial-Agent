"""La consola y /api/v2: token personal, permisos, y que el texto de un documento sea texto.

Puerta del paso 4: un documento con `<script>` en su texto se pinta como
texto. Se prueba de tres formas: la pagina no lleva ningun dato (todo llega
en JSON), el script nunca usa nada que interprete HTML y la politica de
contenido solo deja correr el script propio; y, si hay node, el script de
verdad pinta la ficha de esa factura sobre un DOM de prueba que lanza si
alguien toca innerHTML, y no aparece ningun elemento script ni img.

Se levanta el servidor de verdad en un puerto libre, como en
test_serve_seguridad.py.
"""

from __future__ import annotations

import http.client
import json
import shutil
import subprocess
import threading

import pytest
from conftest import factura_de, persona
from test_hallazgos import _cargar, _registro

from bms_agent import consola, consola_assets, hallazgos, permisos
from bms_agent.almacen import preparar
from bms_agent.serve import CABECERA_TOKEN, crear_servidor

GUION = "<script>alert('xss')</script>"
IMAGEN = '<img src=x onerror="alert(1)">'


class AgenteFalso:
    estado = {"estado": "inactivo"}

    def lanzar(self):
        return True, "no"


@pytest.fixture
def con_guion(tmp_path):
    """Un almacen en disco con una factura cuyo texto lleva HTML que se ejecutaria."""
    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        linea = {"description": f"Montagewerk {GUION}", "quantity_raw": "10,00", "unit": "uur",
                 "unit_rate_raw": "42,50", "line_total_raw": "425,00", "location": IMAGEN,
                 "week_number": 36, "period_start": None, "period_end": None}
        _cargar(almacen, tmp_path / "out", _registro(
            "a", supplier_name=f"Van Dijk {GUION}", lines=[linea],
            subtotal_excl_vat_raw="425,00", vat_amount_raw="89,25", total_incl_vat_raw="514,25",
            document_notes=f"Llame al {IMAGEN} y {GUION}"))
        hallazgos.recalcular(almacen.conn)
        conn = almacen.conn
        ana = persona(conn, "Ana", "administracion")
        carla = persona(conn, "Carla", "consulta")
        permisos.crear_rol(conn, "nada", ["anadir_informacion"])
        nadie = persona(conn, "Nadie")
        permisos.asignar_rol(conn, nadie, "nada")
        tokens = {n: permisos.emitir_token(conn, u)
                  for n, u in (("ana", ana), ("carla", carla), ("nadie", nadie))}
        factura = factura_de(conn, "2026-4471")
    return db, tokens, factura


@pytest.fixture
def servidor(con_guion, tmp_path):
    db, tokens, factura = con_guion
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "out", 0, token="token-del-servidor",
                         agente=AgenteFalso(), ruta_db=db)
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    hilo.start()
    try:
        yield srv.server_address[1], tokens, factura, db
    finally:
        srv.shutdown()
        srv.server_close()


def _pedir(puerto, metodo, ruta, cabeceras=None, cuerpo=None):
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
    cabeceras = {"Host": f"127.0.0.1:{puerto}", **(cabeceras or {})}
    conexion.request(metodo, ruta, body=cuerpo, headers=cabeceras)
    respuesta = conexion.getresponse()
    datos = respuesta.read()
    conexion.close()
    return respuesta.status, {k.lower(): v for k, v in respuesta.getheaders()}, datos


def _leer(puerto, ruta, token):
    estado, cabeceras, datos = _pedir(puerto, "GET", ruta, {CABECERA_TOKEN: token})
    return estado, cabeceras, json.loads(datos)


def _orden(puerto, token, cuerpo, **cabeceras):
    texto = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode("utf-8")
    estado, _c, datos = _pedir(puerto, "POST", "/api/v2/acciones", {
        "Content-Type": "application/json", CABECERA_TOKEN: token, **cabeceras}, texto)
    return estado, json.loads(datos)


# ------------------------------------------------------------ la pagina y el script

def test_la_pagina_no_lleva_datos_y_solo_corre_su_script(servidor) -> None:
    puerto, _tokens, _f, _db = servidor
    estado, cabeceras, cuerpo = _pedir(puerto, "GET", "/consola")
    assert estado == 200 and cabeceras["content-type"].startswith("text/html")
    politica = cabeceras["content-security-policy"]
    assert "script-src 'self'" in politica and "unsafe-inline" not in politica
    assert "frame-ancestors 'none'" in politica and cabeceras["x-frame-options"] == "DENY"
    texto = cuerpo.decode("utf-8")
    assert "Van Dijk" not in texto and "alert" not in texto
    # Ningun script en linea: solo el propio, por su ruta.
    assert texto.count("<script") == 1 and '<script src="/consola.js" defer></script>' in texto
    estado, cabeceras, script = _pedir(puerto, "GET", "/consola.js")
    assert estado == 200 and cabeceras["content-type"].startswith("text/javascript")
    assert cabeceras["x-content-type-options"] == "nosniff"
    assert script.decode("utf-8") == consola_assets.SCRIPT


@pytest.mark.parametrize("prohibido", ["innerHTML", "outerHTML", "insertAdjacentHTML",
                                       "document.write", "eval(", "Function(", "srcdoc",
                                       ".href", "javascript:"])
def test_el_script_no_usa_nada_que_interprete_html(prohibido) -> None:
    assert prohibido not in consola_assets.SCRIPT


def test_la_consola_no_guarda_el_token_en_el_navegador() -> None:
    for prohibido in ("localStorage", "sessionStorage", "document.cookie", "location.search"):
        assert prohibido not in consola_assets.SCRIPT


def test_los_datos_llegan_como_json_con_el_html_tal_cual(servidor) -> None:
    puerto, tokens, factura, _db = servidor
    estado, cabeceras, datos = _leer(puerto, f"/api/v2/facturas/{factura}", tokens["ana"])
    assert estado == 200
    assert cabeceras["content-type"].startswith("application/json")
    assert cabeceras["x-content-type-options"] == "nosniff"
    ficha = datos["factura"]
    assert ficha["contraparte"] == f"Van Dijk {GUION}"
    assert GUION in ficha["notas_doc"] and IMAGEN in ficha["notas_doc"]


@pytest.mark.skipif(shutil.which("node") is None, reason="sin node no se ejecuta el script")
def test_el_script_pinta_el_html_de_un_documento_como_texto(servidor, tmp_path) -> None:
    puerto, tokens, factura, _db = servidor
    _e, _c, ficha = _leer(puerto, f"/api/v2/facturas/{factura}", tokens["ana"])
    _e, _c, lista = _leer(puerto, "/api/v2/facturas", tokens["ana"])
    datos = tmp_path / "datos.json"
    datos.write_text(json.dumps({"ficha": ficha["factura"], "lista": lista["facturas"]}),
                     encoding="utf-8")
    script = tmp_path / "consola.js"
    script.write_text(consola_assets.SCRIPT, encoding="utf-8")
    prueba = tmp_path / "prueba.js"
    prueba.write_text(DOM_DE_PRUEBA, encoding="utf-8")
    proceso = subprocess.run(["node", str(prueba), str(datos), str(script)],
                             capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    resultado = json.loads(proceso.stdout)
    assert "SCRIPT" not in resultado["etiquetas"] and "IMG" not in resultado["etiquetas"]
    assert GUION in resultado["ficha"] and IMAGEN in resultado["ficha"]
    assert f"Van Dijk {GUION}" in resultado["lista"]
    # Los atributos que pone el script no vienen nunca de un documento.
    assert not any("alert" in v for v in resultado["atributos"])


DOM_DE_PRUEBA = r"""
const fs = require('fs');
const vm = require('vm');
const datos = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const creados = [];
class Texto { constructor(t) { this.nodeType = 3; this.textContent = String(t); } }
class Elemento {
  constructor(etiqueta) {
    this.nodeType = 1; this.tagName = String(etiqueta).toUpperCase(); this.children = [];
    this.atributos = {}; this.className = ''; this.value = ''; creados.push(this);
  }
  appendChild(n) { this.children.push(n); return n; }
  removeChild(n) { this.children = this.children.filter(x => x !== n); return n; }
  get firstChild() { return this.children[0] || null; }
  setAttribute(k, v) {
    if (/^on/i.test(k)) { throw new Error('atributo de evento ' + k); }
    this.atributos[k] = String(v);
  }
  addEventListener() {}
  get textContent() { return this.children.map(c => c.textContent).join(''); }
  set textContent(v) { this.children = [new Texto(v)]; }
  set innerHTML(v) { throw new Error('innerHTML'); }
  get innerHTML() { throw new Error('innerHTML'); }
  set outerHTML(v) { throw new Error('outerHTML'); }
  insertAdjacentHTML() { throw new Error('insertAdjacentHTML'); }
}
global.window = {crypto: {randomUUID: () => 'peticion'}};
global.document = {
  createElement: e => new Elemento(e), createTextNode: t => new Texto(t),
  addEventListener() {}, getElementById() { return new Elemento('div'); },
  write() { throw new Error('document.write'); },
};
global.fetch = () => { throw new Error('la prueba no habla con nadie'); };
vm.runInThisContext(fs.readFileSync(process.argv[3], 'utf8'));
const ficha = new Elemento('div');
window.BMSConsola.pintarDetalle(ficha, datos.ficha);
const lista = new Elemento('div');
window.BMSConsola.pintarListado(lista, datos.lista);
const atributos = [];
creados.forEach(e => Object.values(e.atributos).forEach(v => atributos.push(v)));
process.stdout.write(JSON.stringify({
  etiquetas: [...new Set(creados.map(e => e.tagName))], ficha: ficha.textContent,
  lista: lista.textContent, atributos: atributos,
}));
"""


# ------------------------------------------------------------ las lecturas

def test_leer_pide_un_token_personal_con_ver_facturas(servidor) -> None:
    puerto, tokens, factura, db = servidor
    for ruta in ("/api/v2/facturas", f"/api/v2/facturas/{factura}", "/api/v2/yo",
                 "/api/v2/excepciones"):
        assert _pedir(puerto, "GET", ruta)[0] == 401
        assert _pedir(puerto, "GET", ruta, {CABECERA_TOKEN: "token-del-servidor"})[0] == 401
        assert _leer(puerto, ruta, tokens["nadie"])[0] == 403
        assert _leer(puerto, ruta, tokens["carla"])[0] == 200
    estado, _c, yo = _leer(puerto, "/api/v2/yo", tokens["carla"])
    assert (yo["nombre"], yo["permisos"]) == ("Carla", ["ver_facturas"])
    with preparar(db) as almacen:
        motivos = [f[0] for f in almacen.conn.execute(
            "SELECT motivo FROM evento WHERE tipo = 'permiso_denegado'")]
    # Solo el token que llega y no vale queda en la auditoria: sin token no se escribe nada.
    assert motivos.count("token personal no valido") == 4
    assert sum("ver_facturas" in m for m in motivos) == 4


def test_el_registro_de_cuentas_y_las_fuentes_por_la_api(servidor) -> None:
    """Paso 5: lo que ensena la consola del registro de cuentas y de la frescura (Z1)."""
    puerto, tokens, _f, _db = servidor
    for ruta, clave in (("/api/v2/cuentas", "cuentas"), ("/api/v2/fuentes", "fuentes")):
        assert _pedir(puerto, "GET", ruta)[0] == 401
        assert _leer(puerto, ruta, tokens["nadie"])[0] == 403
        estado, cabeceras, datos = _leer(puerto, ruta, tokens["carla"])
        assert estado == 200 and cabeceras["content-type"].startswith("application/json")
        assert datos == {clave: []}           # sin ningun maestro importado todavia
    assert "pintarFuentes" in consola_assets.SCRIPT


def test_otra_web_no_llena_la_auditoria_con_lecturas_sin_token(servidor) -> None:
    """Un <img src> de otra web llega sin Origin y sin token: 401, y nada escrito."""
    puerto, _tokens, _f, db = servidor

    def eventos() -> int:
        with preparar(db) as almacen:
            return almacen.conn.execute("SELECT count(*) FROM evento").fetchone()[0]

    antes = eventos()
    for _ in range(20):
        assert _pedir(puerto, "GET", "/api/v2/yo")[0] == 401
        assert _pedir(puerto, "GET", "/api/v2/yo", {"Sec-Fetch-Site": "cross-site"})[0] == 401
    assert eventos() == antes


def test_la_lista_va_por_prioridad_con_sus_insignias(servidor) -> None:
    puerto, tokens, factura, _db = servidor
    _e, _c, datos = _leer(puerto, "/api/v2/facturas", tokens["carla"])
    [fila] = datos["facturas"]
    assert fila["id"] == factura
    for clave in ("nivel", "puntos", "motivos", "estado_revision", "calidad", "etiqueta",
                  "editada", "sin_resolver"):
        assert clave in fila
    estado, _c, nada = _leer(puerto, "/api/v2/no-existe", tokens["carla"])
    assert estado == 404
    assert _leer(puerto, "/api/v2/facturas/999", tokens["carla"])[0] == 404


def test_otra_web_no_lee_ni_con_el_token(servidor) -> None:
    puerto, tokens, _f, _db = servidor
    estado, cabeceras, _ = _pedir(puerto, "GET", "/api/v2/facturas", {
        CABECERA_TOKEN: tokens["ana"], "Origin": "http://localhost.attacker.example"})
    assert estado == 403 and "access-control-allow-origin" not in cabeceras
    estado, _c, _ = _pedir(puerto, "GET", "/api/v2/facturas", {
        CABECERA_TOKEN: tokens["ana"], "Host": "attacker.example"})
    assert estado == 421


# ------------------------------------------------------------ las ordenes

def test_una_orden_por_post_con_el_token_personal(servidor) -> None:
    puerto, tokens, factura, db = servidor
    cuerpo = {"accion": "anadir_nota", "peticion_id": "p-1",
              "datos": {"fila_id": factura, "texto": f"Nota con {GUION}"}}
    estado, respuesta = _orden(puerto, tokens["ana"], cuerpo)
    assert estado == 200 and respuesta["ok"]
    assert respuesta["diferencia"]["accion"] == "anadir_nota"
    estado, respuesta = _orden(puerto, tokens["ana"], cuerpo)
    assert estado == 200 and respuesta["diferencia"]["repetida"]
    with preparar(db) as almacen:
        conn = almacen.conn
        nota = conn.execute("SELECT * FROM nota").fetchone()
        assert (nota["usuario_id"], nota["texto"]) == (
            permisos.usuario_por_nombre(conn, "Ana"), f"Nota con {GUION}")
        assert conn.execute("SELECT count(*) FROM nota").fetchone()[0] == 1


@pytest.mark.parametrize("cabeceras, cuerpo, codigo", [
    ({"Origin": "http://evil.example"}, None, 403),
    ({"Content-Type": "application/x-www-form-urlencoded"}, b"accion=anadir_nota", 415),
    ({"Content-Type": "text/plain"}, None, 415),
    ({}, b'{"accion": "anadir_nota", "datos": {"fila_id": 1, "texto": "x"}, "x": 1.5}', 400),
    ({}, b"[1]", 400),
    ({CABECERA_TOKEN: ""}, None, 401),
    ({CABECERA_TOKEN: "token-del-servidor"}, None, 401),
])
def test_una_orden_que_no_llega_como_debe_se_rechaza(servidor, cabeceras, cuerpo, codigo) -> None:
    puerto, tokens, factura, db = servidor
    texto = cuerpo or json.dumps({"accion": "anadir_nota",
                                  "datos": {"fila_id": factura, "texto": "x"}}).encode("utf-8")
    base = {"Content-Type": "application/json", CABECERA_TOKEN: tokens["ana"]}
    estado, _c, _d = _pedir(puerto, "POST", "/api/v2/acciones", {**base, **cabeceras}, texto)
    assert estado == codigo
    with preparar(db) as almacen:
        assert almacen.conn.execute("SELECT count(*) FROM nota").fetchone()[0] == 0


@pytest.mark.parametrize("cuerpo, codigo, tipo", [
    ({"accion": "pagar_factura", "datos": {}}, 400, "AccionDesconocida"),
    ({"accion": "anadir_nota", "datos": {"texto": "x"}}, 400, "DatosNoValidos"),
    ({"accion": "anadir_nota", "datos": {"fila_id": 999, "texto": "x"}}, 404, "LookupError"),
    ({"accion": "fijar_campo", "datos": {"tabla": "factura", "fila_id": None, "campo":
                                         "plazo_pago_dias", "valor": "30", "rev": 99}},
     400, "DatosNoValidos"),
])
def test_los_errores_de_una_orden_tienen_su_codigo(servidor, cuerpo, codigo, tipo) -> None:
    puerto, tokens, _f, _db = servidor
    estado, respuesta = _orden(puerto, tokens["ana"], cuerpo)
    assert (estado, respuesta["tipo"]) == (codigo, tipo)


def test_permiso_conflicto_y_segunda_firma_por_la_api(servidor) -> None:
    puerto, tokens, factura, _db = servidor
    nota = {"accion": "anadir_nota", "datos": {"fila_id": factura, "texto": "x"}}
    estado, respuesta = _orden(puerto, tokens["carla"], nota)
    assert (estado, respuesta["tipo"]) == (403, "PermisoDenegado")
    viejo = {"accion": "fijar_campo", "datos": {
        "tabla": "factura", "fila_id": factura, "campo": "plazo_pago_dias", "valor": "30",
        "rev": 7}}
    estado, respuesta = _orden(puerto, tokens["ana"], viejo)
    assert (estado, respuesta["tipo"]) == (409, "Conflicto")
    # La segunda firma no viaja con la orden de otro (es una orden suya: firmar_anulacion).
    estado, respuesta = _orden(puerto, tokens["ana"], {**nota, "segunda_firma_token": "x"})
    assert estado == 400 and "segunda_firma_token" in respuesta["error"]


def test_la_ficha_tiene_lo_que_la_consola_ensena(servidor) -> None:
    puerto, tokens, factura, _db = servidor
    _e, _c, datos = _leer(puerto, f"/api/v2/facturas/{factura}", tokens["ana"])
    ficha = datos["factura"]
    total = next(c for c in ficha["campos"] if c["campo"] == "total_cent")
    assert (total["texto"], total["original_crudo"], total["fuente"], total["entrada"]) == (
        "514,25", "514,25", "extraccion", "514.25")
    assert ficha["lineas"] and ficha["lineas"][0]["imputaciones"]
    assert len(ficha["huella_contenido"]) == 64 and ficha["etiqueta"]
    for clave in ("hallazgos", "excepcion", "revisiones", "notas", "historia", "estado",
                  "pide_revision"):
        assert clave in ficha
    assert consola.fichero("/no") is None


def test_ni_la_consola_ni_la_cli_piden_el_token_de_otra_persona(capsys) -> None:
    from bms_agent.cli import main

    assert "segunda_firma_token" not in consola_assets.SCRIPT
    assert "firmar_anulacion" in consola_assets.SCRIPT
    with pytest.raises(SystemExit):
        main(["accion", "anular_hallazgo", "--hallazgo-id", "1", "--huella", "x",
              "--segunda-firma-token", "token-de-otra"])
    assert "segunda-firma-token" in capsys.readouterr().err


# ------------------------------------------------------------ ordenes de compra (paso 9)

def _con_po(db) -> tuple[int, int]:
    """Un cliente y un Objeto del maestro con HTML en el nombre (lo que llegaria de una hoja)."""
    from bms_agent import campos
    from bms_agent.almacen import usuario_sistema

    with preparar(db) as almacen:
        conn = almacen.conn
        maestro = campos.Automatico("maestro", usuario_sistema(conn, "importador"))
        cliente = campos.crear(conn, "cliente", {"nombre": f"Cliente {GUION}"}, maestro)
        objeto = campos.crear(conn, "objeto", {"codigo": f"Obra {IMAGEN}",
                                               "nombre": f"Obra {IMAGEN}",
                                               "cliente_id": cliente}, maestro)
    return cliente, objeto


def test_las_ordenes_de_compra_y_los_objetos_por_la_api(servidor) -> None:
    puerto, tokens, _factura, db = servidor
    cliente, objeto = _con_po(db)
    registrar = {"accion": "registrar_po", "peticion_id": "po-1", "datos": {
        "numero": f"PO {GUION}", "lado": "cliente", "parte_id": cliente, "valor": "1000",
        "fecha_fin": "2026-11-10", "objetos": [objeto]}}
    estado, respuesta = _orden(puerto, tokens["carla"], registrar)
    assert (estado, respuesta["tipo"]) == (403, "PermisoDenegado")
    estado, respuesta = _orden(puerto, tokens["ana"], registrar)
    assert estado == 200 and respuesta["ok"]
    po = respuesta["diferencia"]["detalle"]["orden_compra_id"]
    _e, _c, lista = _leer(puerto, "/api/v2/ordenes", tokens["carla"])
    assert [o["numero"] for o in lista["ordenes"]] == [f"PO {GUION}"]
    estado, _c, ficha = _leer(puerto, f"/api/v2/ordenes/{po}", tokens["carla"])
    assert estado == 200 and ficha["orden"]["parte"]["nombre"] == f"Cliente {GUION}"
    assert ficha["orden"]["planificado"]["estado"] == "sin_datos"
    estado, _c, vista = _leer(puerto, f"/api/v2/objetos/{objeto}", tokens["carla"])
    assert estado == 200 and [o["id"] for o in vista["objeto"]["ordenes_compra"]] == [po]
    assert _leer(puerto, "/api/v2/ordenes/999", tokens["carla"])[0] == 404
    assert _leer(puerto, "/api/v2/objetos/999", tokens["carla"])[0] == 404
    if shutil.which("node") is None:
        return
    # El script pinta la PO y el Objeto como texto, como la ficha de una factura.
    datos = db.parent / "po.json"
    datos.write_text(json.dumps({"lista": lista["ordenes"], "orden": ficha["orden"],
                                 "objeto": vista["objeto"]}), encoding="utf-8")
    script = db.parent / "consola.js"
    script.write_text(consola_assets.SCRIPT, encoding="utf-8")
    prueba = db.parent / "prueba_po.js"
    prueba.write_text(DOM_DE_PRUEBA.split("vm.runInThisContext")[0] + DOM_ORDENES,
                      encoding="utf-8")
    proceso = subprocess.run(["node", str(prueba), str(datos), str(script)],
                             capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    resultado = json.loads(proceso.stdout)
    assert "SCRIPT" not in resultado["etiquetas"] and "IMG" not in resultado["etiquetas"]
    assert f"PO {GUION}" in resultado["lista"] and f"Cliente {GUION}" in resultado["orden"]
    assert f"Obra {IMAGEN}" in resultado["objeto"]
    assert not any("alert" in v for v in resultado["atributos"])


DOM_ORDENES = r"""
vm.runInThisContext(fs.readFileSync(process.argv[3], 'utf8'));
const lista = new Elemento('div');
window.BMSConsola.pintarOrdenes(lista, datos.lista);
const orden = new Elemento('div');
window.BMSConsola.pintarOrden(orden, datos.orden);
const objeto = new Elemento('div');
window.BMSConsola.pintarObjeto(objeto, datos.objeto);
const atributos = [];
creados.forEach(e => Object.values(e.atributos).forEach(v => atributos.push(v)));
process.stdout.write(JSON.stringify({
  etiquetas: [...new Set(creados.map(e => e.tagName))], lista: lista.textContent,
  orden: orden.textContent, objeto: objeto.textContent, atributos: atributos,
}));
"""
