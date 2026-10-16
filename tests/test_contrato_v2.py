"""El contrato v2, /api/v2 del paso 12 y la consola nueva; y /api/datos, igual que siempre.

Puertas del paso 12 que viven aqui:

- /api/datos sigue siendo byte a byte la foto de referencia
  (tests/golden/construir_datos_v1.json), tambien despues de usar todo lo
  nuevo: el contrato v1 no cambia;
- el contrato v2 (`bms-agent export --v2` y GET /api/v2/exportar) es el que
  dice docs/integracion-web.md, sin un numero con decimales ni un IBAN;
- las lecturas nuevas de /api/v2 piden el token personal, admiten solo sus
  parametros y dicen la version del contrato;
- la consola pinta el panel, la busqueda, los Objetos, el BTW y la historia
  de una factura con textContent: el HTML de un documento sale como texto.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import quote

import pytest
from conftest import GOLDEN, TARIFAS_V1, factura_de, persona
from test_consola import DOM_DE_PRUEBA, GUION, IMAGEN, AgenteFalso, _pedir
from test_hallazgos import _cargar, _registro

from bms_agent import consola_assets, consultas, hallazgos, permisos, servicios
from bms_agent.almacen import preparar
from bms_agent.cli import main
from bms_agent.serve import CABECERA_CONTRATO, CABECERA_TOKEN, crear_servidor

RAIZ = Path(__file__).resolve().parent.parent
MOTIVO = "Visto con el documento delante"


def _servidor(db: Path, tmp_path: Path):
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "vacio", 0, token="token-servidor",
                         agente=AgenteFalso(), ruta_db=db)
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                            daemon=True)
    hilo.start()
    return srv


def _leer(puerto: int, ruta: str, token: str | None):
    cabeceras = {CABECERA_TOKEN: token} if token else {}
    estado, cabeceras_r, datos = _pedir(puerto, "GET", ruta, cabeceras)
    return estado, cabeceras_r, json.loads(datos) if datos else None


@pytest.fixture
def desde_out(tmp_path, out_v1, monkeypatch):
    """Un almacen en disco con las siete fixtures v1, una persona con token y, en la carpeta
    de trabajo, config/tarifas.yaml igual que la de la foto (lo que lee /api/datos)."""
    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        ana = persona(almacen.conn, "Ana", "administrador")
        token = permisos.emitir_token(almacen.conn, ana)
    trabajo = tmp_path / "trabajo"
    (trabajo / "config").mkdir(parents=True)
    shutil.copy(TARIFAS_V1, trabajo / "config" / "tarifas.yaml")
    monkeypatch.chdir(trabajo)
    srv = _servidor(db, tmp_path)
    try:
        yield srv.server_address[1], token, db
    finally:
        srv.shutdown()
        srv.server_close()


# ============================================================ puerta: /api/datos, la foto

def test_api_datos_sigue_siendo_byte_a_byte_la_foto(desde_out) -> None:
    """GET /api/datos es la foto de referencia con la serializacion del servidor (sin sangrar:
    registro del paso 0), antes y despues de leer todo lo nuevo del paso 12."""
    puerto, token, _db = desde_out
    foto = json.loads((GOLDEN / "construir_datos_v1.json").read_text(encoding="utf-8"))
    esperado = json.dumps(foto, ensure_ascii=False).encode("utf-8")
    # Revision final: con el token personal de quien lee, como /api/v2 (sin el, 401).
    con_token = {CABECERA_TOKEN: token}
    estado, cabeceras, cuerpo = _pedir(puerto, "GET", "/api/datos", con_token)
    assert estado == 200 and cuerpo == esperado
    assert CABECERA_CONTRATO.lower() not in cabeceras
    for ruta in ("/api/v2/panel", "/api/v2/buscar?numero=4471", "/api/v2/objetos",
                 "/api/v2/exportar", "/api/v2/facturas/1/historial"):
        assert _leer(puerto, ruta, token)[0] == 200, ruta
    assert _pedir(puerto, "GET", "/api/datos", con_token)[2] == esperado
    assert _pedir(puerto, "GET", "/api/datos")[0] == 401


# ============================================================ puerta: el contrato v2

def _sin_ibanes(valor, camino="") -> list[str]:
    from bms_agent.reglas.normas import normalizar_iban, parece_iban

    if isinstance(valor, str):
        return [camino] if parece_iban(valor) and normalizar_iban(valor) else []
    if isinstance(valor, dict):
        return [c for k, v in valor.items() for c in _sin_ibanes(v, f"{camino}.{k}")]
    if isinstance(valor, list):
        return [c for i, v in enumerate(valor) for c in _sin_ibanes(v, f"{camino}[{i}]")]
    return []


def test_export_v2_cumple_el_contrato_documentado(desde_out, tmp_path, capsys) -> None:
    _puerto, _token, db = desde_out
    destino = tmp_path / "datos-v2.json"
    assert main(["export", "--v2", "--db", str(db), "--file", str(destino)]) == 0
    assert "Contrato v2 (2.0): 7 facturas" in capsys.readouterr().out
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert consultas.comprobar_v2(datos) == []
    assert datos["contrato"] == consultas.CONTRATO_V2
    assert len(datos["facturas"]) == 7 and _sin_ibanes(datos) == []
    # Nada con decimales en el fichero: ni un "1.5" suelto fuera de un texto.
    assert not re.search(r":\s*-?\d+\.\d+[,\s}\]]", destino.read_text(encoding="utf-8"))
    # Sin almacen no hay contrato v2.
    assert main(["export", "--v2", "--db", str(tmp_path / "otra.sqlite3"),
                 "--file", str(tmp_path / "x.json")]) == 1


_FICHA = re.compile(r'"([^"\n]*)"\s*(:)?|[{}\[\]]')


def _claves_documentadas(seccion: str) -> dict[str, set[str]]:
    """Las claves que documenta cada esqueleto de la seccion, por su camino.

    Los esqueletos son JSON a medias (`"panel": {"contrato", "hoy", ...}`, con
    comentarios `//` y `...`): se quitan los comentarios y se recorren las
    llaves y los corchetes. Una clave seguida de `{` abre su camino
    (`panel.caja`); seguida de `[`, el de su lista (`facturas[]`). Asi una clave
    tiene que estar documentada en su sitio, no en cualquier parte: "id" en
    `facturas[]` no vale por estar en `proveedores[]`.
    """
    claves: dict[str, set[str]] = {}
    for lenguaje, bloque in re.findall(r"```(\w*)\n(.*?)```", seccion, re.S):
        if lenguaje:
            continue
        sin_comentarios = "\n".join(linea.split("//", 1)[0] for linea in bloque.splitlines())
        pila: list[str | None] = []
        pendiente = None
        for m in _FICHA.finditer(sin_comentarios):
            simbolo = m.group(0)
            if simbolo in "{[":
                pila.append(None if pendiente is None
                            else pendiente + ("[]" if simbolo == "[" else ""))
                pendiente = None
            elif simbolo in "}]":
                if pila:
                    pila.pop()
                pendiente = None
            else:
                camino = ".".join(p for p in pila if p)
                claves.setdefault(camino, set()).add(m.group(1))
                pendiente = m.group(1) if m.group(2) else None
    return claves


def test_el_contrato_v2_es_el_que_dice_la_documentacion() -> None:
    """docs/integracion-web.md describe la version y cada clave que el codigo exige, en el
    bloque de su camino (no basta con que el nombre salga en algun sitio de la seccion)."""
    texto = (RAIZ / "docs" / "integracion-web.md").read_text(encoding="utf-8")
    seccion = texto.split("## El contrato v2", 1)[1].split("\n## ", 1)[0]
    assert f'"contrato": "{consultas.CONTRATO_V2}"' in seccion
    documentadas = _claves_documentadas(seccion)
    for camino, claves in consultas.CLAVES_V2.items():
        faltan = set(claves) - documentadas.get(camino, set())
        assert not faltan, (camino, sorted(faltan))
    for filtro in consultas.FILTROS:
        assert f"`{filtro}`" in seccion, filtro
    for ruta, _parametros in __import__("bms_agent.serve", fromlist=["x"]).LECTURAS_V2:
        assert f"`GET {ruta}`" in texto, ruta


def test_el_parser_de_la_documentacion_mira_cada_camino() -> None:
    """Una clave documentada en otro bloque no cuenta para el suyo."""
    seccion = ('```\n"panel": {"hoy", "caja": {"ventanas"}},\n"facturas": [ {"id"} ]\n```\n'
               '```js\nconst x = {"nada": 1}\n```')
    assert _claves_documentadas(seccion) == {"": {"panel", "facturas"},
                                             "panel": {"hoy", "caja"},
                                             "panel.caja": {"ventanas"}, "facturas[]": {"id"}}


def test_comprobar_v2_ve_lo_que_falta_y_los_decimales() -> None:
    datos = {"contrato": consultas.CONTRATO_V2, "panel": {}, "facturas": [{"id": 1}]}
    errores = consultas.comprobar_v2(datos)
    assert any("raiz: faltan" in e for e in errores)
    assert any(e.startswith("facturas[0]: faltan") for e in errores)
    assert consultas.comprobar_v2({**datos, "x": 1.5}) and any(
        "decimales" in e for e in consultas.comprobar_v2({**datos, "x": 1.5}))
    assert any("contrato" in e for e in consultas.comprobar_v2({"contrato": "1.0"}))


# ============================================================ las lecturas nuevas de /api/v2

def test_las_lecturas_del_paso_12_por_la_api(desde_out) -> None:
    puerto, token, db = desde_out
    with preparar(db) as almacen:
        f4471 = factura_de(almacen.conn, "2026-4471")
        objeto = almacen.conn.execute("SELECT id FROM objeto LIMIT 1").fetchone()
    estado, cabeceras, contrato = _leer(puerto, "/api/v2/contrato", token)
    assert estado == 200 and cabeceras[CABECERA_CONTRATO.lower()] == consultas.CONTRATO_V2
    assert {f["nombre"] for f in contrato["filtros"]} == set(consultas.FILTROS)
    estado, _c, panel = _leer(puerto, "/api/v2/panel", token)
    assert estado == 200 and set(consultas.CLAVES_V2["panel"]) <= set(panel["panel"])
    estado, _c, r = _leer(puerto, "/api/v2/buscar?numero=4471&orden=fecha", token)
    assert estado == 200 and [f["id"] for f in r["busqueda"]["facturas"]] == [f4471]
    estado, _c, r = _leer(puerto, "/api/v2/buscar?estado_pago=pendiente&estado_pago=vencida",
                          token)
    assert estado == 200 and r["busqueda"]["filtros"]["estado_pago"] == ["pendiente", "vencida"]
    inyeccion = quote("'; DROP TABLE factura; --")
    estado, _c, r = _leer(puerto, f"/api/v2/buscar?numero={inyeccion}", token)
    assert estado == 200 and r["busqueda"]["total"] == 0
    for ruta, codigo in (("/api/v2/buscar?proveedor=1", 400),
                         ("/api/v2/buscar?vencida=quizas", 400),
                         ("/api/v2/panel?x=1", 400), (f"/api/v2/objetos/9999", 404),
                         ("/api/v2/flujo?desde=ayer", 400),
                         ("/api/v2/facturas/9999/historial", 404)):
        assert _leer(puerto, ruta, token)[0] == codigo, ruta
    estado, _c, h = _leer(puerto, f"/api/v2/facturas/{f4471}/historial", token)
    assert estado == 200 and h["historial"]["factura_id"] == f4471
    assert h["historial"]["documento"]["conservado"] is False
    estado, _c, objetos = _leer(puerto, "/api/v2/objetos", token)
    assert estado == 200 and set(objetos) >= {"objetos", "sin_objeto", "totales"}
    if objeto is not None:
        estado, _c, v = _leer(puerto, f"/api/v2/objetos/{objeto[0]}?desde=2026-09-01"
                                      "&hasta=2026-09-30", token)
        assert estado == 200 and v["objeto"]["economia"]["periodo"]["desde"] == "2026-09-01"
    estado, _c, flujo = _leer(puerto, "/api/v2/flujo?desde=2026-10-01&hasta=2026-10-31", token)
    assert estado == 200 and flujo["flujo_caja"]["ventanas"]["periodo"] == [
        "2026-10-01", "2026-10-31"]
    estado, _c, todo = _leer(puerto, "/api/v2/exportar", token)
    assert estado == 200 and consultas.comprobar_v2(todo) == []
    # Sin token no se lee nada nuevo, como el resto de /api/v2.
    for ruta in ("/api/v2/panel", "/api/v2/buscar", "/api/v2/exportar", "/api/v2/contrato",
                 f"/api/v2/facturas/{f4471}/historial"):
        assert _leer(puerto, ruta, None)[0] == 401, ruta


def test_leer_el_panel_pide_ver_facturas(desde_out) -> None:
    puerto, _token, db = desde_out
    with preparar(db) as almacen:
        permisos.crear_rol(almacen.conn, "solo_notas", ["anadir_informacion"])
        nadie = persona(almacen.conn, "Nadie")
        permisos.asignar_rol(almacen.conn, nadie, "solo_notas")
        token = permisos.emitir_token(almacen.conn, nadie)
    for ruta in ("/api/v2/panel", "/api/v2/buscar", "/api/v2/exportar"):
        assert _leer(puerto, ruta, token)[0] == 403, ruta


def test_la_cli_ensena_el_panel_la_busqueda_los_objetos_y_la_historia(desde_out,
                                                                      capsys) -> None:
    _puerto, _token, db = desde_out
    capsys.readouterr()
    assert main(["resumen", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "Entra (cobros)" in salida and "BTW 2026-T4" in salida and "Atencion:" in salida
    assert main(["buscar", "--filtro", "numero=4471", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "2026-4471" in salida and "1 factura(s)" in salida
    assert main(["buscar", "--filtro", "proveedor=1", "--db", str(db)]) == 2
    assert "filtro desconocido" in capsys.readouterr().err
    assert main(["buscar", "--filtros"]) == 0
    assert "anulada_acreditada" in capsys.readouterr().out
    assert main(["objetos", "--db", str(db)]) == 0
    assert "base total" in capsys.readouterr().out
    with preparar(db) as almacen:
        f = factura_de(almacen.conn, "2026-4471")
    assert main(["historial", str(f), "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "Factura 2026-4471" in salida and "NO guardado" in salida
    assert main(["resumen", "--json", "--db", str(db)]) == 0
    assert set(json.loads(capsys.readouterr().out)) >= set(consultas.CLAVES_V2["panel"])


# ============================================================ la consola nueva, como texto

@pytest.fixture
def con_html(tmp_path):
    """Un almacen en disco con una factura vencida de "Van Dijk <script>", un Objeto con un
    <img onerror> en el nombre al que se imputa su linea, y una correccion a mano con HTML."""
    from bms_agent import campos
    from bms_agent.almacen import usuario_sistema

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        linea = {"description": f"Montagewerk {GUION}", "quantity_raw": "10,00", "unit": "uur",
                 "unit_rate_raw": "42,50", "line_total_raw": "425,00", "location": "Obra",
                 "week_number": 36, "period_start": None, "period_end": None}
        _cargar(almacen, tmp_path / "out", _registro(
            "a", supplier_name=f"Van Dijk {GUION}", lines=[linea], due_date="2026-10-01",
            subtotal_excl_vat_raw="425,00", vat_amount_raw="89,25", total_incl_vat_raw="514,25",
            document_notes=f"Llame al {IMAGEN} y {GUION}"))
        conn = almacen.conn
        maestro = campos.Automatico("maestro", usuario_sistema(conn, "importador"))
        cliente = campos.crear(conn, "cliente", {"nombre": f"Cliente {GUION}"}, maestro)
        objeto = campos.crear(conn, "objeto", {"codigo": f"Obra {IMAGEN}",
                                               "nombre": f"Obra {IMAGEN}",
                                               "cliente_id": cliente}, maestro)
        hallazgos.recalcular(conn)
        ana = persona(conn, "Ana", "administrador")
        token = permisos.emitir_token(conn, ana)
        factura = factura_de(conn, "2026-4471")
        imputacion = conn.execute("SELECT id, rev FROM factura_imputacion WHERE factura_id = ?",
                                  (factura,)).fetchone()
        servicios.ejecutar(conn, "cambiar_objeto", {
            "imputacion_id": imputacion["id"], "objeto_id": objeto, "rev": imputacion["rev"],
            "motivo": f"Es la obra {IMAGEN}"}, usuario_id=ana)
        rev = conn.execute("SELECT rev FROM factura WHERE id = ?", (factura,)).fetchone()[0]
        servicios.ejecutar(conn, "fijar_campo", {
            "tabla": "factura", "fila_id": factura, "campo": "emisor_nombre_doc",
            "valor": f"Van Dijk {GUION} BV", "motivo": f"Como en el maestro {IMAGEN}",
            "rev": rev}, usuario_id=ana)
    return db, token, factura, objeto


DOM_PASO_12 = r"""
vm.runInThisContext(fs.readFileSync(process.argv[3], 'utf8'));
const B = window.BMSConsola;
const salida = {};
for (const [nombre, pintar, dato] of [
    ['panel', B.pintarPanel, datos.panel], ['busqueda', B.pintarBusqueda, datos.busqueda],
    ['historial', B.pintarHistorial, datos.historial], ['objetos', B.pintarObjetos, datos.objetos],
    ['objeto', B.pintarObjeto, datos.objeto], ['btw', B.pintarBtw, datos.btw],
    ['trimestre', B.pintarTrimestre, datos.trimestre], ['buscador', B.pintarBuscador, datos.filtros],
    ['ficha', B.pintarDetalle, datos.ficha]]) {
  const caja = new Elemento('div');
  pintar(caja, dato);
  salida[nombre] = caja.textContent;
}
const navegacion = new Elemento('nav');
B.pintarNavegacion(navegacion);
salida.navegacion = navegacion.textContent;
const atributos = [];
creados.forEach(e => Object.values(e.atributos).forEach(v => atributos.push(v)));
salida.etiquetas = [...new Set(creados.map(e => e.tagName))];
salida.atributos = atributos;
salida.importe = [B.importe(-123456), B.importe(5), B.importe(null)];
process.stdout.write(JSON.stringify(salida));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="sin node no se ejecuta el script")
def test_la_consola_nueva_pinta_el_html_de_los_documentos_como_texto(con_html, tmp_path) -> None:
    """Puerta del paso 4, ahora para todo lo nuevo: el panel, la busqueda, la historia de
    una factura, los Objetos, el BTW y la ficha con sus insignias de procedencia."""
    db, token, factura, objeto = con_html
    srv = _servidor(db, tmp_path)
    try:
        puerto = srv.server_address[1]
        datos = {
            "panel": _leer(puerto, "/api/v2/panel", token)[2]["panel"],
            "busqueda": _leer(puerto, "/api/v2/buscar?texto=van", token)[2]["busqueda"],
            "historial": _leer(puerto, f"/api/v2/facturas/{factura}/historial", token)[2][
                "historial"],
            "objetos": _leer(puerto, "/api/v2/objetos", token)[2],
            "objeto": _leer(puerto, f"/api/v2/objetos/{objeto}", token)[2]["objeto"],
            "btw": _leer(puerto, "/api/v2/btw", token)[2]["btw"],
            "trimestre": _leer(puerto, "/api/v2/btw/2026-T3", token)[2]["trimestre"],
            "filtros": _leer(puerto, "/api/v2/contrato", token)[2]["filtros"],
            "ficha": _leer(puerto, f"/api/v2/facturas/{factura}", token)[2]["factura"],
        }
    finally:
        srv.shutdown()
        srv.server_close()
    fichero = tmp_path / "datos.json"
    fichero.write_text(json.dumps(datos), encoding="utf-8")
    script = tmp_path / "consola.js"
    script.write_text(consola_assets.SCRIPT, encoding="utf-8")
    prueba = tmp_path / "prueba.js"
    prueba.write_text(DOM_DE_PRUEBA.split("vm.runInThisContext")[0] + DOM_PASO_12,
                      encoding="utf-8")
    proceso = subprocess.run(["node", str(prueba), str(fichero), str(script)],
                             capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    r = json.loads(proceso.stdout)
    assert "SCRIPT" not in r["etiquetas"] and "IMG" not in r["etiquetas"]
    assert not any("alert" in v for v in r["atributos"])
    # Lo del documento sale como texto, tal cual, en cada pagina que lo ensena.
    assert f"Van Dijk {GUION}" in r["panel"]          # la compra vencida
    assert f"Van Dijk {GUION}" in r["busqueda"]
    assert f"Van Dijk {GUION} BV" in r["historial"] and IMAGEN in r["historial"]
    assert f"Obra {IMAGEN}" in r["objetos"] and f"Cliente {GUION}" in r["objetos"]
    assert f"Van Dijk {GUION} BV" in r["objeto"]       # sus facturas relacionadas
    assert "Corregido a mano" in r["ficha"] and f"Como en el maestro {IMAGEN}" in r["ficha"]
    assert "Extraído del documento" in r["ficha"]
    assert "anulada_acreditada" in r["buscador"] and "Panel" in r["navegacion"]
    assert "2026-T3" in r["btw"] and "Rúbrica" in r["trimestre"]
    assert r["importe"] == ["-1.234,56", "0,05", ""]


# ============================================================ revision del paso 12

_IBAN_ENTERO = re.compile(r"\b[A-Z]{2}\d{2}[A-Z]{4}\d{10}\b|\b[A-Z]{2}\d{2}(?: [A-Z0-9]{4}){3}")


def _con_ibanes(almacen, tmp_path) -> None:
    """El maestro de Exact y la factura con inyeccion: F2 y F3 abiertos, con el IBAN entero en
    sus textos y en los motivos de la prioridad."""
    from test_cuentas import EXACT_PROVEEDORES, _fixture

    from bms_agent.importadores.registrar import importar_fichero

    conn = almacen.conn
    ana = persona(conn, "Ana", "administracion")
    importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    _cargar(almacen, tmp_path / "out", _fixture("03-con-inyeccion"))
    hallazgos.recalcular(conn)


def test_el_contrato_v2_no_lleva_ningun_iban_ni_dentro_de_un_texto(almacen, tmp_path) -> None:
    """Los mensajes de F2, F3, F5, F6 y F10 escriben el IBAN entero, y de ahi pasa a los
    motivos de facturas, proveedores y excepciones: el export los enmascara (NL..5689) y
    comprobar_v2 busca un IBAN dentro de cualquier texto, no solo un texto que sea un IBAN."""
    conn = almacen.conn
    _con_ibanes(almacen, tmp_path)
    abiertos = {r for (r,) in conn.execute("SELECT regla FROM hallazgo WHERE estado = 'abierto'")}
    assert {"F2", "F3"} <= abiertos
    motivos = [m for f in consultas.listado(conn) for m in f["motivos"]]
    assert any(_IBAN_ENTERO.search(m) for m in motivos)          # dentro de la casa, entero
    datos = consultas.exportar_v2(conn)
    texto = json.dumps(datos, ensure_ascii=False)
    assert not _IBAN_ENTERO.search(texto), _IBAN_ENTERO.search(texto)
    assert consultas.comprobar_v2(datos) == []
    assert any("NL.." in m for f in datos["facturas"] for m in f["motivos"])
    # comprobar_v2 lo ve aunque vaya en medio de una frase.
    falso = {**datos, "facturas": [{**datos["facturas"][0],
                                    "motivos": ["Bloqueada: La cuenta NL91ABNA0417164300 es "
                                                "nueva (F3)"]}]}
    assert any("lleva un IBAN (NL..4300)" in e for e in consultas.comprobar_v2(falso))


@pytest.fixture
def con_otro_origen(tmp_path):
    """Un almacen en disco con IBAN en el registro y en los avisos, y un servidor que admite
    el origen de un sitio propio (http://localhost:5173)."""
    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        _con_ibanes(almacen, tmp_path)
        ana = almacen.conn.execute("SELECT id FROM usuario WHERE nombre = 'Ana'").fetchone()[0]
        token = permisos.emitir_token(almacen.conn, ana)
        proveedor = almacen.conn.execute(
            "SELECT proveedor_id FROM cuenta_bancaria WHERE proveedor_id IS NOT NULL LIMIT 1"
        ).fetchone()
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "vacio", 0, token="token-servidor",
                         agente=AgenteFalso(), ruta_db=db,
                         origenes_extra=["http://localhost:5173"])
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                            daemon=True)
    hilo.start()
    try:
        yield srv.server_address[1], token, db, proveedor[0] if proveedor else None
    finally:
        srv.shutdown()
        srv.server_close()


SITIO = "http://localhost:5173"


def test_un_sitio_de_otro_origen_lee_sin_iban_y_no_da_ordenes(con_otro_origen) -> None:
    """La consola (mismo origen, o sin navegador) ve el IBAN entero (decision 23). Un sitio
    declarado con --origen lee el contrato con cada IBAN enmascarado, tambien el registro de
    cuentas, y no puede dar ordenes con el token de quien sea."""
    puerto, token, _db, proveedor = con_otro_origen
    assert proveedor is not None
    propio = {CABECERA_TOKEN: token}
    ajeno = {CABECERA_TOKEN: token, "Origin": SITIO}
    for ruta in ("/api/v2/cuentas", f"/api/v2/proveedores/{proveedor}", "/api/v2/facturas",
                 "/api/v2/buscar", "/api/v2/excepciones", "/api/v2/exportar"):
        estado, cabeceras, cuerpo = _pedir(puerto, "GET", ruta, ajeno)
        assert estado == 200 and cabeceras["access-control-allow-origin"] == SITIO, ruta
        assert not _IBAN_ENTERO.search(cuerpo.decode("utf-8")), ruta
    estado, _c, cuerpo = _pedir(puerto, "GET", "/api/v2/cuentas", propio)
    assert estado == 200 and _IBAN_ENTERO.search(cuerpo.decode("utf-8"))
    estado, _c, cuerpo = _pedir(puerto, "GET", "/api/v2/cuentas", {
        **propio, "Origin": f"http://127.0.0.1:{puerto}"})
    assert estado == 200 and _IBAN_ENTERO.search(cuerpo.decode("utf-8"))
    # Ordenes: desde el sitio, no; desde la consola, si.
    nota = json.dumps({"accion": "anadir_nota", "datos": {"fila_id": 1, "texto": "Llamado"}})
    for cabeceras, codigo in ((ajeno, 403), ({**propio, "Origin": f"http://127.0.0.1:{puerto}"},
                                             200), (propio, 200)):
        estado, _c, cuerpo = _pedir(puerto, "POST", "/api/v2/acciones", {
            **cabeceras, "Content-Type": "application/json"}, nota.encode("utf-8"))
        assert estado == codigo, (cabeceras, cuerpo)
    assert "consola" in json.loads(_pedir(puerto, "POST", "/api/v2/acciones", {
        **ajeno, "Content-Type": "application/json"}, nota.encode("utf-8"))[2])["error"]


def _ejemplo(ruta: str) -> str:
    return (ruta.replace("/N/", "/1/").replace("/N", "/1")
            .replace("AAAA-TN", "2026-T3"))


def test_cada_lectura_de_v2_rechaza_un_parametro_que_no_admite(desde_out) -> None:
    """Todas las lecturas de LECTURAS_V2, no solo las del paso 12: un parametro desconocido es
    un 400 (antes, /api/v2/facturas?cosa=1 daba todas y /api/v2/btw?x=1 un 200)."""
    from bms_agent.serve import LECTURAS_V2

    puerto, token, _db = desde_out
    for ruta, _parametros in LECTURAS_V2:
        estado, _c, cuerpo = _leer(puerto, f"{_ejemplo(ruta)}?cosa=1", token)
        assert estado == 400, (ruta, estado, cuerpo)
        assert "cosa" in cuerpo["error"], ruta
    for ruta in ("/api/v2/facturas?nivel=normal&nivel=urgente", "/api/v2/flujo?desde=2026-10-01"
                 "&desde=2026-10-02&hasta=2026-10-31"):
        assert _leer(puerto, ruta, token)[0] == 400, ruta


def test_el_nivel_de_la_lista_de_facturas(desde_out) -> None:
    """`nivel=` vacio es como no ponerlo (todas, como antes de guardar los vacios); un nivel
    que no existe es un 400, no una lista vacia."""
    puerto, token, _db = desde_out
    todas = _leer(puerto, "/api/v2/facturas", token)[2]["facturas"]
    assert len(todas) == 7
    assert _leer(puerto, "/api/v2/facturas?nivel=", token)[2]["facturas"] == todas
    estado, _c, flujo = _leer(puerto, "/api/v2/flujo?desde=&hasta=", token)
    assert estado == 200 and flujo["flujo_caja"]["hoy"]
    estado, _c, cuerpo = _leer(puerto, "/api/v2/facturas?nivel=xyz", token)
    assert estado == 400 and "xyz" in cuerpo["error"]
    nivel = todas[0]["nivel"]
    assert {f["id"] for f in _leer(puerto, f"/api/v2/facturas?nivel={nivel}", token)[2][
        "facturas"]} == {f["id"] for f in todas if f["nivel"] == nivel}


def test_un_filtro_enorme_es_un_400_y_no_un_500(desde_out) -> None:
    puerto, token, _db = desde_out
    estado, _c, cuerpo = _leer(puerto, "/api/v2/buscar?proveedor_id=99999999999999999999", token)
    assert estado == 400 and "demasiado grande" in cuerpo["error"]


def test_la_vista_del_objeto_pide_los_dos_extremos_del_periodo(desde_out) -> None:
    from bms_agent import campos
    from bms_agent.almacen import usuario_sistema

    puerto, token, db = desde_out
    with preparar(db) as almacen:
        maestro = campos.Automatico("maestro", usuario_sistema(almacen.conn, "importador"))
        objeto = campos.crear(almacen.conn, "objeto", {"codigo": "Rijnhaven",
                                                       "nombre": "Rijnhaven"}, maestro)
    for consulta in ("hasta=2026-09-30", "desde=2026-11-01"):
        estado, _c, cuerpo = _leer(puerto, f"/api/v2/objetos/{objeto}?{consulta}", token)
        assert estado == 400 and "desde y hasta" in cuerpo["error"], consulta
    estado, _c, v = _leer(puerto, f"/api/v2/objetos/{objeto}?desde=2026-09-01"
                                  "&hasta=2026-09-30", token)
    assert estado == 200 and v["objeto"]["economia"]["periodo"]["hasta"] == "2026-09-30"
