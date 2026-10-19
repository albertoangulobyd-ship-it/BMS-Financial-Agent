"""La app local (/app, paso 15): lo que sirve el servidor, con que cabeceras, y que lo
construido es lo de las fuentes.

Se levanta el servidor de verdad en un puerto libre, como en test_serve_seguridad.py y
test_consola.py. Lo que se mira:

- /app y /app/ dan la pagina con una politica de contenido estricta y un nonce nuevo en
  cada respuesta (el mismo en la CSP y en la pagina), sin ningun script ni estilo en
  linea; los ficheros, por una lista blanca de nombres exactos con su tipo y cache
  inmutable; cualquier otra ruta, 404, nunca un fichero de fuera.
- Las mismas comprobaciones de Host y Origin que todo lo demas.
- Las bandas (datos de prueba y aislamiento) las pone el servidor, en neerlandes e
  ingles, escapadas.
- web/fuente.json: la huella de las fuentes del frontend es la de lo construido (si no,
  alguien cambio el frontend sin volver a construir), y lo construido es lo que apunta.
- En frontend/src no hay nada que interprete HTML ni guarde el token en el navegador.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import sqlite3
import threading
import tomllib
from contextlib import closing, contextmanager
from pathlib import Path

import pytest

from bms_agent import app_local
from bms_agent.almacen import MARCA_DEMO
from bms_agent.serve import CABECERA_ENTORNO, crear_servidor

RAIZ = Path(__file__).resolve().parent.parent
FRONTEND = RAIZ / "frontend"
WEB = RAIZ / "src" / "bms_agent" / "web"


class _SinPasadas:
    estado = {"estado": "inactivo"}

    def lanzar(self):
        raise AssertionError("ningun test lanza una pasada")


@contextmanager
def _servidor(tmp_path: Path, *, ruta_db: Path | None = None, aislamiento=None,
              carpeta_web: Path | None = None):
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "out", 0, token="t",
                         agente=_SinPasadas(), ruta_db=ruta_db or tmp_path / "datos" / "bms.sqlite3",
                         aislamiento=aislamiento, carpeta_web=carpeta_web)
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    hilo.start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


def _pedir(puerto: int, ruta: str, cabeceras: dict | None = None):
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
    conexion.request("GET", ruta, headers={"Host": f"127.0.0.1:{puerto}", **(cabeceras or {})})
    respuesta = conexion.getresponse()
    datos = respuesta.read()
    conexion.close()
    return respuesta.status, {k.lower(): v for k, v in respuesta.getheaders()}, datos


def _base_demo_vacia(tmp_path: Path) -> Path:
    """Un fichero con la marca de la base de prueba: para la banda basta con la marca."""
    ruta = tmp_path / "datos" / "demo.sqlite3"
    ruta.parent.mkdir(parents=True)
    with closing(sqlite3.connect(ruta)) as conn:
        conn.execute(f"PRAGMA application_id = {MARCA_DEMO}")
        conn.commit()
    return ruta


def _nonce_de(pagina: str) -> str:
    encontrado = re.search(r'<meta name="bms-nonce" content="([A-Za-z0-9_-]+)">', pagina)
    assert encontrado, "la pagina no lleva el nonce"
    return encontrado.group(1)


# ------------------------------------------------------------ la pagina

def test_app_da_la_pagina_con_una_csp_estricta_y_un_nonce_por_respuesta(tmp_path) -> None:
    with _servidor(tmp_path) as puerto:
        respuestas = [_pedir(puerto, ruta) for ruta in ("/app", "/app/", "/app?x=1")]
    nonces = set()
    for estado, cabeceras, cuerpo in respuestas:
        assert estado == 200 and cabeceras["content-type"] == "text/html; charset=utf-8"
        pagina = cuerpo.decode("utf-8")
        nonce = _nonce_de(pagina)
        nonces.add(nonce)
        assert cabeceras["content-security-policy"] == (
            "default-src 'none'; script-src 'self'; "
            f"style-src 'self' 'nonce-{nonce}'; font-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; "
            "require-trusted-types-for 'script'; trusted-types 'none'")
        assert "unsafe-inline" not in cabeceras["content-security-policy"]
        assert "unsafe-eval" not in cabeceras["content-security-policy"]
        assert cabeceras["x-frame-options"] == "DENY"
        assert cabeceras["x-content-type-options"] == "nosniff"
        assert cabeceras["referrer-policy"] == "no-referrer"
        assert cabeceras["cache-control"] == "no-store"
        # Ni un script ni un estilo en linea: solo los propios, por su ruta.
        scripts = re.findall(r"<script\b[^>]*>", pagina)
        assert len(scripts) == 1 and re.fullmatch(
            r'<script type="module" crossorigin src="/app/assets/[A-Za-z0-9._-]+\.js">', scripts[0])
        assert "<style" not in pagina and " style=" not in pagina
        assert not re.search(r"\son[a-z]+=", pagina)
        # Ninguna direccion de fuera.
        assert not re.search(r"(src|href)=\"(https?:)?//", pagina)
        # Las marcas se han cambiado; sin datos de prueba ni aislamiento, no hay banda.
        assert "<!--bms:" not in pagina and "bms-banda" not in pagina
        assert CABECERA_ENTORNO.lower() not in cabeceras
    assert len(nonces) == 3


def test_cada_fichero_de_la_pagina_se_sirve_con_su_tipo_y_cache_inmutable(tmp_path) -> None:
    with _servidor(tmp_path) as puerto:
        _e, _c, cuerpo = _pedir(puerto, "/app")
        referidos = re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', cuerpo.decode("utf-8"))
        assert len(referidos) >= 3  # el script, el estilo y el icono
        tipos = set()
        for ruta in referidos:
            estado, cabeceras, datos = _pedir(puerto, ruta)
            assert estado == 200 and datos
            assert cabeceras["cache-control"] == "public, max-age=31536000, immutable"
            assert cabeceras["x-content-type-options"] == "nosniff"
            tipos.add(cabeceras["content-type"])
            assert datos == (WEB / ruta.removeprefix("/app/")).read_bytes()
        assert {"text/javascript; charset=utf-8", "text/css; charset=utf-8",
                "image/svg+xml"} <= tipos
        # Las fuentes que pide el estilo: woff2, del propio servidor.
        css = next(_pedir(puerto, r)[2] for r in referidos if r.endswith(".css")).decode()
        fuentes = re.findall(r"url\(([^)]+)\)", css)
        assert fuentes and all(re.fullmatch(r"/app/assets/[A-Za-z0-9._-]+\.woff2", f) for f in fuentes)
        for fuente in fuentes:
            estado, cabeceras, _d = _pedir(puerto, fuente)
            assert estado == 200 and cabeceras["content-type"] == "font/woff2"


@pytest.mark.parametrize("ruta", [
    "/app/assets/", "/app/assets/../index.html", "/app/assets/..%2findex.html",
    "/app/assets/%2e%2e/fuente.json", "/app/assets/index.html", "/app/index.html",
    "/app/fuente.json", "/app/assets/nada.js", "/app/assets/x.js.map", "/app/../consola",
    "/app/assets//etc/passwd", "/app/assets/C:%5Cwindows%5Cwin.ini", "/appx", "/app/x",
])
def test_lo_que_no_esta_en_la_lista_blanca_es_un_404(tmp_path, ruta) -> None:
    with _servidor(tmp_path) as puerto:
        estado, cabeceras, datos = _pedir(puerto, ruta)
    if ruta == "/app/../consola":
        # http.client no normaliza: llega tal cual y no es ninguna ruta.
        assert estado == 404
        return
    assert estado == 404, ruta
    assert cabeceras["content-type"].startswith("application/json")
    assert json.loads(datos) == {"error": "no existe"}


def test_la_lista_blanca_son_los_ficheros_que_hay_y_nada_mas(tmp_path) -> None:
    web = tmp_path / "web"
    (web / "assets" / "sub").mkdir(parents=True)
    (web / "index.html").write_text(
        "<!doctype html><html><head><!--bms:nonce--><title>x</title></head>"
        "<body>\n<!--bms:bandas-->\n</body></html>", encoding="utf-8")
    for nombre in ("a-1.js", "b-2.css", "c-3.woff2", "d-4.svg", "e.txt", "f.js.map", ".oculto.js",
                   "g.html"):
        (web / "assets" / nombre).write_bytes(nombre.encode())
    (web / "assets" / "sub" / "h.js").write_bytes(b"h")
    fuera = tmp_path / "secreto.js"
    fuera.write_bytes(b"secreto")
    try:
        (web / "assets" / "enlace.js").symlink_to(fuera)
    except OSError:
        pass
    app = app_local.cargar(web)
    assert sorted(app.ficheros) == ["/app/assets/a-1.js", "/app/assets/b-2.css",
                                    "/app/assets/c-3.woff2", "/app/assets/d-4.svg"]
    assert {f.tipo for f in app.ficheros.values()} == {
        "text/javascript; charset=utf-8", "text/css; charset=utf-8", "font/woff2",
        "image/svg+xml"}
    with _servidor(tmp_path, carpeta_web=web) as puerto:
        assert _pedir(puerto, "/app/assets/a-1.js")[2] == b"a-1.js"
        for ruta in ("/app/assets/e.txt", "/app/assets/enlace.js", "/app/assets/sub/h.js",
                     "/app/assets/.oculto.js", "/app/assets/g.html"):
            assert _pedir(puerto, ruta)[0] == 404, ruta


def test_la_lista_blanca_de_lo_construido_cubre_todo_assets() -> None:
    app = app_local.cargar()
    construidos = sorted(f"/app/assets/{f.name}" for f in (WEB / "assets").iterdir())
    assert sorted(app.ficheros) == construidos
    assert app.indice == (WEB / "index.html").read_bytes()


def test_host_y_origin_se_comprueban_tambien_en_app(tmp_path) -> None:
    with _servidor(tmp_path) as puerto:
        for ruta in ("/app", "/app/assets/" + next((WEB / "assets").glob("*.js")).name):
            estado, cabeceras, _d = _pedir(puerto, ruta, {"Host": "evil.example"})
            assert estado == 421
            estado, cabeceras, _d = _pedir(puerto, ruta, {"Origin": "http://localhost.evil.example"})
            assert estado == 403 and "access-control-allow-origin" not in cabeceras


def test_sin_construir_app_lo_dice_y_la_consola_sigue(tmp_path) -> None:
    vacia = tmp_path / "web-vacia"
    vacia.mkdir()
    with _servidor(tmp_path, carpeta_web=vacia) as puerto:
        estado, cabeceras, datos = _pedir(puerto, "/app")
        assert estado == 503 and cabeceras["content-type"].startswith("text/plain")
        assert "/consola" in datos.decode("utf-8")
        assert _pedir(puerto, "/consola")[0] == 200


def test_un_index_sin_las_marcas_no_se_sirve_sin_bandas(tmp_path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><body>sin marcas</body></html>", encoding="utf-8")
    with _servidor(tmp_path, carpeta_web=web, ruta_db=_base_demo_vacia(tmp_path)) as puerto:
        estado, _c, datos = _pedir(puerto, "/app")
    assert estado == 503 and b"sin marcas" not in datos


# ------------------------------------------------------------ las bandas

def test_con_la_base_de_prueba_la_app_lleva_la_banda_en_neerlandes_e_ingles(tmp_path) -> None:
    with _servidor(tmp_path, ruta_db=_base_demo_vacia(tmp_path)) as puerto:
        estado, cabeceras, cuerpo = _pedir(puerto, "/app")
        _e, cabeceras_js, _d = _pedir(puerto, "/app/assets/" + next((WEB / "assets").glob("*.js")).name)
    pagina = cuerpo.decode("utf-8")
    assert estado == 200 and cabeceras[CABECERA_ENTORNO.lower()] == "demo"
    assert cabeceras_js[CABECERA_ENTORNO.lower()] == "demo"
    # La pone el servidor, justo al abrir el body: se ve aunque el script no cargue.
    assert re.search(r'<body>\s*<p id="datos-de-prueba" class="bms-banda bms-banda-prueba" '
                     r'role="alert">TESTGEGEVENS · TEST DATA', pagina)
    assert "testdatabase, alles is verzonnen" in pagina and "test database, everything is made up" in pagina
    assert "<title>TESTGEGEVENS · " in pagina
    assert "DATOS DE PRUEBA" not in pagina  # nada en castellano


def test_la_banda_del_aislamiento_dice_que_papel_falla_y_escapa_lo_demas(tmp_path) -> None:
    problemas = ["lector: sin comprobar", "salida: FALLA (llega a internet)",
                 "<script>alert(1)</script>: FALLA", 'x" onmouseover="alert(1)']
    with _servidor(tmp_path, aislamiento=lambda: problemas,
                   ruta_db=_base_demo_vacia(tmp_path)) as puerto:
        _e, _c, cuerpo = _pedir(puerto, "/app")
    pagina = cuerpo.decode("utf-8")
    assert re.search(r'<body>\s*<p id="datos-de-prueba"[^>]*>[^<]*</p>\s*<p id="aislamiento" '
                     r'class="bms-banda bms-banda-aislamiento" role="alert">ISOLATIE', pagina)
    banda = re.search(r'<p id="aislamiento"[^>]*>([^<]*)</p>', pagina).group(1)
    assert "(pdf-lezer, uitgang)" in banda and "(PDF reader, exit proxy)" in banda
    assert "comprobar.bat" in banda
    # Lo que viene del fichero no se copia: ni el script ni las palabras en castellano.
    assert "alert(" not in pagina and "sin comprobar" not in pagina and "FALLA" not in pagina
    assert "<title>TESTGEGEVENS · ISOLATIE · " in pagina


def test_texto_de_la_banda_del_aislamiento_sin_papeles_conocidos() -> None:
    texto = app_local.texto_aislamiento(["algo raro"])
    assert texto.startswith("ISOLATIE NIET GECONTROLEERD OF MISLUKT: draai comprobar.bat")
    assert "ISOLATION NOT CHECKED OR FAILED: run comprobar.bat" in texto


# ------------------------------------------------------------ lo construido es lo de las fuentes

def _normalizado(ruta: Path) -> bytes:
    return ruta.read_bytes().replace(b"\r\n", b"\n")


def _entradas() -> dict[str, str]:
    """Lo mismo que frontend/scripts/fuente.mjs: los ficheros de build-inputs.json."""
    config = json.loads((FRONTEND / "build-inputs.json").read_text(encoding="utf-8"))
    ficheros: list[Path] = []

    def recorrer(ruta: Path) -> None:
        if ruta.is_symlink():
            return
        if ruta.is_dir():
            for hijo in ruta.iterdir():
                if not hijo.name.startswith("."):
                    recorrer(hijo)
        elif ruta.is_file() and not any(str(ruta).endswith(s) for s in config["exclude"]):
            ficheros.append(ruta)

    for entrada in config["include"]:
        recorrer(RAIZ.joinpath(*entrada.split("/")))
    salida = {}
    for ruta in sorted(f.relative_to(RAIZ).as_posix() for f in ficheros):
        assert ruta.isascii(), ruta
        salida[ruta] = hashlib.sha256(_normalizado(RAIZ / ruta)).hexdigest()
    return salida


def _total(entradas: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{r}\0{h}\n" for r, h in entradas.items()).encode()).hexdigest()


def test_lo_construido_es_de_estas_fuentes() -> None:
    """Si falla: alguien cambio el frontend y no volvio a construir. cd frontend; npm ci;
    npm run build (escribe src/bms_agent/web y su fuente.json)."""
    fuente = json.loads((WEB / "fuente.json").read_text(encoding="utf-8"))
    entradas = _entradas()
    cambiadas = sorted(set(entradas.items()) ^ set(fuente["entradas"].items()))
    assert not cambiadas, f"cambiado sin construir: {sorted({r for r, _ in cambiadas})}"
    assert fuente["sha256"] == _total(entradas)


def test_lo_construido_es_lo_que_apunta_fuente_json() -> None:
    fuente = json.loads((WEB / "fuente.json").read_text(encoding="utf-8"))
    hay = {f.relative_to(WEB).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
           for f in WEB.rglob("*") if f.is_file() and f.name != "fuente.json"}
    assert hay == fuente["salida"]
    # Los catalogos de textos que importe la app, cuando esten, entran en la huella.
    textos = RAIZ / "src" / "bms_agent" / "textos"
    for catalogo in ("nl.json", "en.json"):
        if (textos / catalogo).exists() and "domain/placeholder" not in json.dumps(fuente["entradas"]):
            assert f"src/bms_agent/textos/{catalogo}" in fuente["entradas"]


def test_la_huella_cubre_las_fuentes_y_los_crlf_no_la_cambian(tmp_path) -> None:
    entradas = _entradas()
    for necesaria in ("frontend/index.html", "frontend/package.json", "frontend/package-lock.json",
                      "frontend/vite.config.ts", "frontend/src/main.tsx", "frontend/src/index.css",
                      "frontend/build-inputs.json", "frontend/scripts/fuente.mjs"):
        assert necesaria in entradas
    assert not any(r.endswith(".test.ts") for r in entradas)
    assert not any("/node_modules/" in r for r in entradas)
    fichero = tmp_path / "a.txt"
    fichero.write_bytes(b"uno\r\ndos\n")
    otro = tmp_path / "b.txt"
    otro.write_bytes(b"uno\ndos\n")
    assert _normalizado(fichero) == _normalizado(otro)


def test_el_paquete_lleva_la_app_y_los_textos() -> None:
    datos = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    paquete = datos["tool"]["setuptools"]["package-data"]["bms_agent"]
    assert {"web/*.html", "web/*.json", "web/assets/*", "web/licenses/*",
            "textos/*.json"} <= set(paquete)
    # Las fuentes van con su licencia (SIL OFL 1.1 pide que cada copia la lleve).
    assert {f.name for f in (WEB / "licenses").iterdir()} == {"ibm-plex-sans-OFL.txt",
                                                              "ibm-plex-mono-OFL.txt"}
    atributos = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert "src/bms_agent/web/** -text" in atributos


# ------------------------------------------------------------ el frontend no interpreta HTML

PROHIBIDO = ("dangerouslySetInnerHTML", "innerHTML", "outerHTML", "insertAdjacentHTML",
             "document.write", "eval(", "new Function", "Function(", "srcdoc", "javascript:",
             "sessionStorage", "document.cookie", "location.search", "location.hash",
             "window.open(")


def _fuentes_del_frontend() -> list[Path]:
    """Lo que va a la app (los .test.ts no: prueban, por ejemplo, que una ruta de fuera se
    rechaza, y para eso la escriben)."""
    return [f for f in (FRONTEND / "src").rglob("*") if f.suffix in (".ts", ".tsx")
            and not f.name.endswith((".test.ts", ".test.tsx"))]


def _sin_comentarios(texto: str) -> str:
    """El codigo sin sus comentarios (los comentarios explican, a veces nombrando lo
    prohibido: "nunca innerHTML")."""
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", linea) for linea in texto.splitlines())


@pytest.mark.parametrize("prohibido", PROHIBIDO)
def test_el_frontend_no_usa_nada_que_interprete_html_ni_guarde_el_token(prohibido) -> None:
    for fichero in _fuentes_del_frontend():
        texto = _sin_comentarios(fichero.read_text(encoding="utf-8"))
        assert prohibido not in texto, f"{prohibido} en {fichero.relative_to(RAIZ)}"


def test_el_navegador_solo_guarda_comodidades_desde_un_sitio() -> None:
    """localStorage solo en lib/storage.ts (preferencias, nunca el token ni datos)."""
    for fichero in _fuentes_del_frontend():
        texto = _sin_comentarios(fichero.read_text(encoding="utf-8"))
        if "localStorage" in texto:
            assert fichero == FRONTEND / "src" / "lib" / "storage.ts", fichero
    codigo = _sin_comentarios((FRONTEND / "src" / "lib" / "storage.ts").read_text(encoding="utf-8"))
    assert not re.search(r"token|api\.|fetch\(", codigo, re.IGNORECASE)


def test_el_frontend_no_lleva_ninguna_direccion_de_fuera() -> None:
    for fichero in [*_fuentes_del_frontend(), FRONTEND / "index.html", FRONTEND / "src" / "index.css"]:
        texto = fichero.read_text(encoding="utf-8")
        assert not re.search(r"https?://(?!127\.0\.0\.1|localhost)", texto), fichero


# ------------------------------------------------------------ los lanzadores abren /app

@pytest.mark.parametrize("carpeta", ["windows", "docker"])
def test_los_lanzadores_abren_la_app_en_una_ventana_de_edge(carpeta) -> None:
    comun = (RAIZ / carpeta / "comun.ps1").read_text(encoding="utf-8")
    funcion = comun[comun.index("function Abrir-App"):]
    funcion = funcion[:funcion.index("\n}") + 2]
    # Edge con --app (una ventana sin pestanas ni barra de direcciones), buscado donde se
    # instala; si no esta, el navegador de siempre; si tampoco, se dice la direccion.
    assert 'Join-Path $base "Microsoft\\Edge\\Application\\msedge.exe"' in funcion
    assert 'Start-Process -FilePath $edge -ArgumentList @("--app=" + $Direccion)' in funcion
    assert funcion.count("Start-Process $Direccion") == 2
    assert "Abre esa direccion en el navegador." in funcion
    # Nada que no entienda Windows PowerShell 5.1, y solo ASCII.
    assert funcion.isascii() and "??" not in funcion and "&&" not in funcion
    iniciar = (RAIZ / carpeta / "iniciar.ps1").read_text(encoding="utf-8")
    assert "Abrir-App" in iniciar and "/app" in iniciar
    assert "Start-Process" not in iniciar
