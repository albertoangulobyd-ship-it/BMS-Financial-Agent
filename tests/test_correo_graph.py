"""El cliente de Graph del correo de facturas (paso 18, paso 8 del plan; solo Docker).

Contra GraphFalso (tests/graph_falso.py), que contesta con las formas de Microsoft:

- el token con la asercion firmada (que el falso comprueba de verdad), uno por ronda, y lo que
  dice `correo comprobar` en cada caso de §2.3 (roles vacios exigidos);
- solo GET a Graph y un POST, al token (lo mira el falso en cada peticion y un test sobre el
  codigo); nunca $expand ni el cuerpo;
- los enlaces de la delta: las formas de Microsoft pasan; otro host, http:, usuario en la URL,
  el puerto 8443 u otra ruta no se siguen (interno);
- Retry-After, 429, 503 y 504; el delta que caduca (410, syncStateNotFound);
- el tope de 4 MiB de cada respuesta JSON, leido por trozos, y el de cada adjunto;
- ni el token, ni la asercion, ni la consulta de un enlace, ni el buzon en los errores ni en
  el registro;
- y por una salida de verdad (salida.Proxy con la lista del correo): con la credencial pasa a
  los dos hosts de Microsoft, a api.anthropic.com le dice 403, sin credencial 407.
"""

from __future__ import annotations

import ast
import io
import logging
import socket
import socketserver
import subprocess
import sys
import threading
import traceback
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx2
import pytest
from conftest import RAIZ
from graph_falso import GraphFalso, crear_certificado, fixture, mensajes, pdf

from bms_agent import aislamiento, salida
from bms_agent.correo import MAX_PDF, ajustes, certificado, graph

SRC = RAIZ / "src" / "bms_agent"
AHORA = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
INQUILINO = "1111abcd-2222-4333-8444-55555555ef55"
APLICACION = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
BUZON = "facturen@contoso.onmicrosoft.com"
CONTROL = "bms-control@contoso.onmicrosoft.com"
DESDE = date(2026, 10, 25)
CREDENCIAL = "c" * 64


class Reloj:
    def __init__(self) -> None:
        self.instante = AHORA

    def __call__(self) -> datetime:
        return self.instante


@pytest.fixture(scope="module")
def certificado_de_prueba(tmp_path_factory) -> tuple[Path, Path]:
    return crear_certificado(tmp_path_factory.mktemp("cert") / "secretos-correo", AHORA)


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def falso(certificado_de_prueba, reloj):
    falso = GraphFalso(certificado=certificado_de_prueba[1].read_bytes(), inquilino=INQUILINO,
                       aplicacion=APLICACION, buzon=BUZON, control=CONTROL, ahora=reloj)
    yield falso
    falso.comprobar()


def _ajustes() -> ajustes.Ajustes:
    return ajustes.Ajustes(inquilino=INQUILINO, aplicacion=APLICACION, buzon=BUZON,
                           buzon_control=CONTROL, desde=DESDE)


class Dormidas(list):
    def __call__(self, segundos: float) -> None:
        self.append(segundos)


@pytest.fixture
def dormidas() -> Dormidas:
    return Dormidas()


@pytest.fixture
def cliente(falso, certificado_de_prueba, reloj, dormidas):
    with graph.ClienteGraph(_ajustes(), certificado.cargar(certificado_de_prueba[0]),
                            transporte=falso.transporte, ahora=reloj, dormir=dormidas) as uno:
        yield uno


def _error(funcion, *args) -> graph.ErrorGraph:
    with pytest.raises(graph.ErrorGraph) as error:
        resultado = funcion(*args)
        if hasattr(resultado, "__next__"):
            list(resultado)
    return error.value


# ============================================================ el token y comprobar (§2.2, §2.3)

def test_comprobar_con_todo_bien_y_un_solo_post(cliente, falso) -> None:
    assert cliente.comprobar() == graph.Alcance(True)
    assert [(p.metodo, p.host, p.tipo) for p in falso.peticiones] == [
        ("POST", "login.microsoftonline.com", "token"), ("GET", "graph.microsoft.com", "buzon"),
        ("GET", "graph.microsoft.com", "control"), ("GET", "graph.microsoft.com", "usuarios")]
    # El falso comprobo la asercion (firma, x5t#S256, aud, iss = sub, jti, plazo) y el
    # formulario; cada GET llevaba Prefer IdType="ImmutableId" y el token que dio.
    assert falso.asercion_vista and len(falso.tokens) == 1
    assert falso.peticiones[1].consulta == "$select=id"
    assert falso.peticiones[3].consulta == "$top=1&$select=id"


def test_el_token_dura_la_ronda_y_se_renueva_antes_de_caducar(cliente, falso, reloj) -> None:
    falso.llega(mensajes()["sin_adjuntos"])
    for _ in range(3):
        list(cliente.delta("bandeja", None, AHORA - timedelta(days=30)))
    assert len(falso.de_tipo("token")) == 1
    reloj.instante += timedelta(minutes=56)        # el token dura 3599 s: quedan menos de 5
    list(cliente.delta("bandeja", None, AHORA - timedelta(days=30)))
    assert len(falso.de_tipo("token")) == 2 and len(falso.jti) == 2


@pytest.mark.parametrize("preparar, motivo", [
    (lambda f: setattr(f, "roles", ["Mail.Read"]), "alcance"),
    (lambda f: setattr(f, "roles", ["Mail.ReadBasic.All", "User.Read.All"]), "alcance"),
    (lambda f: setattr(f, "tid", "99999999-2222-4333-8444-555555555555"), "alcance"),
    (lambda f: setattr(f, "estado_buzon", 403), "permiso"),
    (lambda f: setattr(f, "estado_buzon", 404), "permiso"),
    (lambda f: setattr(f, "estado_control", 200), "alcance"),
    (lambda f: setattr(f, "estado_control", 404), "control_no_existe"),
    (lambda f: setattr(f, "estado_control", 400), "interno"),
    (lambda f: setattr(f, "estado_usuarios", 200), "alcance"),
    (lambda f: f.fallar("token", 401, fixture("token-invalid_client.json")), "credencial"),
    (lambda f: f.fallar("token", 400, fixture("token-reloj.json")), "reloj"),
])
def test_comprobar_dice_por_que_no(cliente, falso, preparar, motivo) -> None:
    preparar(falso)
    assert cliente.comprobar() == graph.Alcance(False, motivo)


@pytest.mark.parametrize("cuerpo, motivo", [
    ({"error": "invalid_client", "error_codes": 700024}, "credencial"),
    ({"error": "invalid_client", "error_codes": "x",
      "error_description": "AADSTS700024: Client assertion is not within its valid time range."},
     "reloj"),
    ({"error_codes": [None, "700024"]}, "credencial"),
    ("no es JSON", "credencial"), (None, "credencial"),
])
def test_un_error_del_token_con_otra_forma(cliente, falso, cuerpo, motivo) -> None:
    """Lo que dice login.microsoftonline.com tambien es dato: una forma rara no rompe nada."""
    falso.fallar("token", 400, cuerpo)
    assert cliente.comprobar() == graph.Alcance(False, motivo)


def test_con_roles_en_el_token_no_se_pide_nada_a_graph(cliente, falso) -> None:
    """Un permiso de Entra vale para todos los buzones: con roles no se sigue (falla cerrado)."""
    falso.roles = ["Mail.Read"]
    assert cliente.comprobar() == graph.Alcance(False, "alcance")
    assert [p.tipo for p in falso.peticiones] == ["token"]


def test_un_certificado_caducado_no_pide_el_token(cliente, falso, reloj) -> None:
    reloj.instante = AHORA + timedelta(days=800)
    assert cliente.comprobar() == graph.Alcance(False, "credencial")
    assert falso.peticiones == []


def test_lo_que_no_es_un_veredicto_es_un_error(cliente, falso, dormidas) -> None:
    falso.fallar("token", excepcion=httpx2.ConnectError("sin red"))
    assert _error(cliente.comprobar).codigo == "sin_conexion"
    falso.fallar("buzon", 429, fixture("error-limitado.json"), cabeceras={"Retry-After": "600"})
    assert _error(cliente.comprobar).codigo == "limitado"
    assert dormidas == []


# ============================================================ solo GET, sin $expand ni cuerpo

def _llamadas_http(arbol: ast.AST) -> list[tuple[str, str, ast.Call]]:
    """(funcion que la hace, metodo, llamada) de cada llamada sobre el cliente de httpx2."""
    salida_: list[tuple[str, str, ast.Call]] = []
    for funcion in ast.walk(arbol):
        if not isinstance(funcion, ast.FunctionDef):
            continue
        for nodo in ast.walk(funcion):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and "_http" in ast.unparse(nodo.func.value)):
                salida_.append((funcion.name, nodo.func.attr, nodo))
    return salida_


def test_el_cliente_solo_hace_get_y_un_post_al_token() -> None:
    """Las unicas llamadas HTTP de graph.py: un GET (en _get) y un POST (en _token_nuevo), con
    el metodo escrito tal cual; ningun httpx2.get/post/... suelto, ni send, ni request."""
    arbol = ast.parse((SRC / "correo" / "graph.py").read_text(encoding="utf-8"))
    llamadas = {(f, m, ast.unparse(c.args[0]) if c.args else "")
                for f, m, c in _llamadas_http(arbol) if m != "close"}
    assert llamadas == {("_get", "stream", "'GET'"), ("_token_nuevo", "stream", "'POST'")}
    verbos = {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream",
              "send", "build_request"}
    sueltas = [ast.unparse(n) for n in ast.walk(arbol) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute) and ast.unparse(n.func.value) == "httpx2"
               and n.func.attr in verbos]
    assert sueltas == []
    assert not [n for n in ast.walk(arbol) if isinstance(n, ast.Attribute)
                and n.attr in ("send", "build_request", "request")]


def _literales(arbol: ast.AST) -> list[tuple[str, str]]:
    """(funcion, texto) de cada literal de texto que no es un docstring."""
    docstrings = {id(n.body[0].value) for n in ast.walk(arbol)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    salida_: list[tuple[str, str]] = []

    def visitar(nodo: ast.AST, funcion: str) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, ast.Constant) and isinstance(hijo.value, str) and (
                    id(hijo) not in docstrings):
                salida_.append((funcion, hijo.value))
            visitar(hijo, hijo.name if isinstance(hijo, ast.FunctionDef) else funcion)

    visitar(arbol, "")
    return salida_


@pytest.mark.parametrize("modulo", ["graph.py", "traer.py", "bandeja.py"])
def test_ni_expand_ni_el_cuerpo_en_el_codigo(modulo) -> None:
    """Ningun literal pide $expand ni el cuerpo (body, bodyPreview, uniqueBody), y /$value solo
    en la funcion que baja un adjunto de fichero."""
    ruta = SRC / "correo" / modulo
    if not ruta.exists():
        pytest.skip("aun no esta")
    literales = _literales(ast.parse(ruta.read_text(encoding="utf-8")))
    assert not [t for _f, t in literales if "expand" in t.lower() or "body" in t.lower()
                or "mime" in t.lower()]
    con_valor = {f for f, t in literales if "$value" in t}
    assert con_valor <= {"bajar"}
    if modulo == "graph.py":
        assert con_valor == {"bajar"}
        assert any("$select" in t for _f, t in literales)


def test_el_falso_ve_cada_violacion(falso, cliente) -> None:
    """El doble no se calla: un POST a Graph, un $expand o un $select con el cuerpo, sin Prefer,
    el $value de un itemAttachment, otro host: todo queda en violaciones."""
    falso.llega(mensajes()["variado"], adjuntos=fixture("adjuntos.json")["variado"])
    token = graph.ClienteGraph._bearer(cliente)._valor
    mid = mensajes()["variado"]["id"]
    with httpx2.Client(transport=falso.transporte) as http:
        cab = {"Authorization": f"Bearer {token}", "Prefer": graph.PREFER_ID}
        base = f"https://graph.microsoft.com/v1.0/users/{BUZON}/messages/{mid}"
        http.post(f"{base}/send", headers=cab)
        http.get(f"{base}/attachments?$expand=microsoft.graph.itemattachment/item", headers=cab)
        http.get(f"{base}?$select=id,body", headers=cab)
        http.get(f"{base}/attachments/AAMkADA1MCJKtzmnlcqVgqI=/$value", headers=cab)
        http.get(f"{base}/attachments", headers={"Authorization": f"Bearer {token}"})
        http.get("https://example.test/v1.0/users", headers=cab)
    vistas = "\n".join(falso.violaciones)
    for violacion in ("POST a Graph", "$expand", "el cuerpo en $select", "$value de un",
                      "sin Prefer", "otro sitio"):
        assert violacion in vistas, violacion
    falso.violaciones.clear()


# ============================================================ la delta y sus enlaces (§3.1)

@pytest.mark.parametrize("forma", ["clave", "guid", "primera"])
def test_los_enlaces_de_microsoft_se_siguen(cliente, falso, forma) -> None:
    falso.forma = forma
    falso.max_pagina = 1
    todos = mensajes()
    for nombre in ("factura", "variado", "sin_adjuntos"):
        falso.llega(todos[nombre])
    paginas = list(cliente.delta("bandeja", None, AHORA - timedelta(days=30)))
    assert [len(p.mensajes) for p in paginas] == [1, 1, 1]
    assert [p.siguiente is None for p in paginas] == [False, False, True]
    assert paginas[-1].delta is not None
    primera, *siguientes = falso.de_tipo("delta")
    assert primera.ruta == f"/v1.0/users/{BUZON}/mailFolders/inbox/messages/delta"
    assert primera.parametros == {"changeType": ["created"],
                                  "$select": [",".join(graph.CAMPOS_MENSAJE)],
                                  "$filter": ["receivedDateTime ge 2026-10-25T10:00:00Z"]}
    assert primera.cabeceras["prefer"] == 'odata.maxpagesize=50, IdType="ImmutableId"'
    # Lo que se pidio despues es tal cual lo que dio Microsoft (la ruta sin reescribir).
    assert [p.ruta for p in siguientes] == [p.siguiente.split("?")[0].split(
        "graph.microsoft.com")[1] for p in paginas[:-1]]
    # La ronda siguiente empieza en el deltaLink: solo lo nuevo.
    falso.llega(todos["spam"])
    nuevas = list(cliente.delta("bandeja", paginas[-1].delta, AHORA))
    assert [m["id"] for p in nuevas for m in p.mensajes] == [todos["spam"]["id"]]


@pytest.mark.parametrize("malo", [
    "https://evil.example/v1.0/users/x/messages/delta?$skiptoken=a",
    "https://graph.microsoft.com.evil.example/v1.0/users/x/messages/delta?$skiptoken=a",
    "http://graph.microsoft.com/v1.0/users/x/messages/delta?$skiptoken=a",
    "https://user:pass@graph.microsoft.com/v1.0/users/x/messages/delta?$skiptoken=a",
    "https://graph.microsoft.com@evil.example/v1.0/users/x/messages/delta",
    "https://graph.microsoft.com:8443/v1.0/users/x/messages/delta?$skiptoken=a",
    "https://graph.microsoft.com/beta/users/x/messages/delta?$skiptoken=a",
    "https://graph.microsoft.com/v1.0/users/x/messages?$skiptoken=a",
    "https://graph.microsoft.com/v1.0/users/x/messages/delta/../../me/sendMail",
    "https://graph.microsoft.com/v1.0/users/x/../me/messages/delta",
    "https://graph.microsoft.com/v1.0/users/x/%2e%2e/me/messages/delta",
    "https://graph.microsoft.com/v1.0/users/x/messages/delta#otro",
    "https://graph.microsoft.com/v1.0/users/x y/messages/delta",
    "https://graph.microsoft.com/v1.0/users/x\\y/messages/delta",
    "https://graph.microsoft.com/v1.0/users/ñ/messages/delta",
    "https://graph.microsoft.com./v1.0/users/x/messages/delta",
    "HTTPS://GRAPH.MICROSOFT.COM:99999/v1.0/users/x/messages/delta",
    "",
])
def test_un_enlace_que_no_es_de_graph_no_se_sigue(cliente, falso, malo) -> None:
    assert not graph.enlace_valido(malo)
    falso.max_pagina = 1
    falso.siguiente_malo = malo
    for nombre in ("factura", "sin_adjuntos"):
        falso.llega(mensajes()[nombre])
    error = _error(cliente.delta, "bandeja", None, AHORA - timedelta(days=30))
    assert error.codigo == "interno" and "no se sigue" in error.detalle
    assert len(falso.de_tipo("delta")) == 1          # el malo no se pidio
    # Tampoco el guardado: sin pedir nada.
    antes = len(falso.peticiones)
    assert _error(cliente.delta, "bandeja", malo, AHORA).codigo == "interno"
    assert len(falso.peticiones) == antes


@pytest.mark.parametrize("bueno", [
    "https://graph.microsoft.com/v1.0/me/mailfolders('AQMkADNkNAAAgEMAAAA')/messages/delta"
    "?$skiptoken=GwcBoTmPuoTQWfcsAbkYM",
    "https://graph.microsoft.com/v1.0/me/mailFolders/AQMkADNkNAAAgEMAAAA/messages/delta"
    "?$deltatoken=GwcBoTmPuoGNlgXgF1nyUNMXY",
    "https://graph.microsoft.com/v1.0/users('facturen%40contoso.onmicrosoft.com')"
    "/mailfolders('AQMkADAw')/messages/delta?$skiptoken=x",
    "https://graph.microsoft.com:443/v1.0/users/0f1e2d3c-4b5a-4968-8776-655443322110"
    "/mailFolders/AAMkAD/Messages/Delta?$deltatoken=x",
    "https://Graph.Microsoft.com/V1.0/users/facturen@contoso.onmicrosoft.com/mailFolders/inbox"
    "/messages/delta?changeType=created&$filter=receivedDateTime%20ge%202026-10-25T00:00:00Z",
])
def test_las_formas_de_microsoft_valen(bueno) -> None:
    assert graph.enlace_valido(bueno)


# ============================================================ Microsoft que limita (§3.1)

def test_retry_after_se_espera_y_se_repite(cliente, falso, dormidas) -> None:
    falso.llega(mensajes()["sin_adjuntos"])
    falso.fallar("delta", 429, fixture("error-limitado.json"), cabeceras={"Retry-After": "7"})
    assert len(list(cliente.delta("bandeja", None, AHORA - timedelta(days=30)))) == 1
    assert dormidas == [7]


def test_sin_retry_after_a_los_2_y_a_los_8_segundos_y_despues_limitado(cliente, falso,
                                                                         dormidas) -> None:
    falso.fallar("delta", 429, fixture("error-limitado.json"), veces=3)
    assert _error(cliente.delta, "bandeja", None, AHORA).codigo == "limitado"
    assert dormidas == [2, 8] and len(falso.de_tipo("delta")) == 3


@pytest.mark.parametrize("estado", [429, 503, 504])
def test_un_retry_after_de_mas_de_120_s_no_se_espera(cliente, falso, dormidas, estado) -> None:
    falso.fallar("delta", estado, fixture("error-limitado.json"), cabeceras={"Retry-After": "121"})
    assert _error(cliente.delta, "bandeja", None, AHORA).codigo == "limitado"
    assert dormidas == [] and len(falso.de_tipo("delta")) == 1


def test_503_y_504_tambien_se_repiten_y_el_token_tambien(cliente, falso, dormidas) -> None:
    falso.llega(mensajes()["sin_adjuntos"])
    falso.fallar("token", 503)
    falso.fallar("delta", 504, cabeceras={"Retry-After": "0"})
    falso.fallar("delta", 503)
    assert len(list(cliente.delta("bandeja", None, AHORA - timedelta(days=30)))) == 1
    # Las esperas son de cada peticion: el token, a los 2 s; la delta, lo que dice Retry-After
    # y, sin el, la segunda espera (8 s).
    assert dormidas == [2, 0, 8]


@pytest.mark.parametrize("estado, cuerpo", [
    (410, None), (400, fixture("error-sin-estado.json")),
    (404, {"error": {"code": "resyncRequired", "message": "x"}}),
])
def test_un_delta_caducado_se_dice(cliente, falso, estado, cuerpo) -> None:
    falso.fallar("delta", estado, cuerpo, cabeceras={"Location": "https://graph.microsoft.com/"
                                                     "v1.0/users/x/messages/delta?$deltatoken="})
    with pytest.raises(graph.DeltaCaducado):
        list(cliente.delta("bandeja", None, AHORA))
    assert len(falso.de_tipo("delta")) == 1          # el Location no se sigue


@pytest.mark.parametrize("estado, codigo", [(401, "credencial"), (403, "permiso"),
                                            (404, "permiso"), (400, "interno"), (500, "limitado"),
                                            (302, "interno")])
def test_cada_respuesta_de_la_delta_su_codigo(cliente, falso, estado, codigo) -> None:
    falso.fallar("delta", estado, fixture("error-acceso.json"),
                 cabeceras={"Location": "https://evil.example/"})
    error = _error(cliente.delta, "bandeja", None, AHORA)
    assert error.codigo == codigo and str(estado) in error.detalle
    assert len(falso.de_tipo("delta")) == 1


def test_los_fallos_de_red_dicen_sin_conexion_o_salida(cliente, falso) -> None:
    falso.fallar("delta", excepcion=httpx2.ReadTimeout("lento"))
    assert _error(cliente.delta, "bandeja", None, AHORA).codigo == "sin_conexion"
    falso.fallar("delta", excepcion=httpx2.ProxyError("403 Forbidden"))
    assert _error(cliente.delta, "bandeja", None, AHORA).codigo == "salida"
    falso.fallar("delta", excepcion=httpx2.RemoteProtocolError("corte"))
    assert _error(cliente.delta, "bandeja", None, AHORA).codigo == "sin_conexion"


# ============================================================ los topes (§3.1, §3.3)

def test_una_pagina_de_mas_de_4_mib_se_corta_leyendo_por_trozos(cliente, falso) -> None:
    falso.llega(mensajes()["factura"])
    falso.extra_en_mensajes = {"relleno": "x" * (6 * 1024 * 1024)}
    error = _error(cliente.delta, "bandeja", None, AHORA - timedelta(days=30))
    assert isinstance(error, graph.RespuestaGrande) and error.codigo == "interno"
    assert falso.total_json > 6 * 1024 * 1024
    assert falso.servido_json <= graph.MAX_JSON + 64 * 1024


def test_un_content_length_de_mas_de_4_mib_no_se_lee(cliente, falso) -> None:
    falso.fallar("delta", 200, {"value": [], "relleno": "x" * (graph.MAX_JSON + 10)})
    assert isinstance(_error(cliente.delta, "bandeja", None, AHORA), graph.RespuestaGrande)


def test_una_lista_de_adjuntos_con_su_contenido_pasa_del_tope(cliente, falso) -> None:
    """Si Graph trajera contentBytes a pesar del $select, el tope de 4 MiB lo para."""
    mensaje = mensajes()["factura"]
    lista = fixture("adjuntos.json")["factura"]
    falso.llega(mensaje, adjuntos=lista, contenidos={lista[0]["id"]: pdf("x", 5 * 1024 * 1024)})
    assert len(cliente.adjuntos(mensaje["id"])) == 1
    falso.contenido_en_la_lista = True
    assert isinstance(_error(cliente.adjuntos, mensaje["id"]), graph.RespuestaGrande)
    assert falso.servido_json <= graph.MAX_JSON + 64 * 1024


def test_un_adjunto_se_baja_por_trozos_con_su_tope(cliente, falso) -> None:
    mensaje = mensajes()["factura"]
    lista = fixture("adjuntos.json")["factura"]
    contenido = pdf("factuur 0412", 200_000)
    falso.llega(mensaje, adjuntos=lista, contenidos={lista[0]["id"]: contenido})
    fichero = io.BytesIO()
    bajado = cliente.bajar(mensaje["id"], lista[0]["id"], fichero)
    assert fichero.getvalue() == contenido
    import hashlib

    assert bajado == graph.Bajado(len(contenido), len(contenido),
                                  hashlib.sha256(contenido).hexdigest(), True, False)
    [peticion] = falso.de_tipo("valor")
    assert peticion.ruta.endswith(f"/attachments/{lista[0]['id']}/$value")
    assert peticion.cabeceras["accept"] == "*/*"


def test_un_adjunto_que_pasa_de_20_mib_al_bajarlo_se_corta(cliente, falso) -> None:
    mensaje = mensajes()["factura"]
    lista = fixture("adjuntos.json")["factura"]

    def sin_fin():
        yield b"%PDF-1.7\n"
        while True:
            yield b"0" * (64 * 1024)

    falso.llega(mensaje, adjuntos=lista, contenidos={lista[0]["id"]: sin_fin})
    fichero = io.BytesIO()
    bajado = cliente.bajar(mensaje["id"], lista[0]["id"], fichero)
    assert bajado.cortado and bajado.escritos == len(fichero.getvalue()) <= MAX_PDF
    assert falso.servidos[f"{mensaje['id']}/{lista[0]['id']}"] <= MAX_PDF + 64 * 1024


def test_un_adjunto_que_no_es_pdf_lo_dice(cliente, falso) -> None:
    mensaje = mensajes()["factura"]
    lista = fixture("adjuntos.json")["factura"]
    falso.llega(mensaje, adjuntos=lista, contenidos={lista[0]["id"]: b"<html>no</html>"})
    bajado = cliente.bajar(mensaje["id"], lista[0]["id"], io.BytesIO())
    assert not bajado.es_pdf and not bajado.cortado


def test_un_id_raro_no_va_en_una_ruta(cliente, falso) -> None:
    for malo in ("../../sendMail", "AAMk?x=1", "AAMk/../x", "", "a" * 513, "AAMk#x", "AAMk x"):
        assert _error(cliente.adjuntos, malo).codigo == "interno"
    assert falso.peticiones == []


# ============================================================ nada sale

def _todo_el_texto(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) + repr(exc)


def test_ni_el_token_ni_la_asercion_ni_la_consulta_salen(cliente, falso, caplog,
                                                          dormidas) -> None:
    caplog.set_level(logging.DEBUG)
    falso.max_pagina = 1
    for nombre in ("factura", "sin_adjuntos"):
        falso.llega(mensajes()[nombre])
    paginas = list(cliente.delta("bandeja", None, AHORA - timedelta(days=30)))
    errores: list[graph.ErrorGraph] = []
    for preparar in (
            lambda: falso.fallar("delta", 401, fixture("error-token-graph.json")),
            lambda: falso.fallar("delta", 429, fixture("error-limitado.json"), veces=3),
            lambda: falso.fallar("delta", excepcion=httpx2.ConnectError("sin red")),
            lambda: falso.fallar("delta", excepcion=httpx2.ProxyError("403 Forbidden")),
            lambda: falso.fallar("delta", 500, {"error": {"code": "x" * 100, "message": BUZON}}),
            lambda: setattr(falso, "siguiente_malo", "https://evil.example/" + BUZON),
    ):
        preparar()
        falso.llega(mensajes()["spam"])
        with pytest.raises(graph.ErrorGraph) as error:
            list(cliente.delta("bandeja", paginas[-1].delta, AHORA))
        errores.append(error.value)
        falso.siguiente_malo = None
    falso.fallar("token", 401, fixture("token-invalid_client.json"))
    falso.fallar("token", excepcion=httpx2.ConnectError("sin red"))
    for _ in range(2):
        cliente._token = None
        with pytest.raises(graph.ErrorGraph) as error:
            cliente.adjuntos(mensajes()["factura"]["id"])
        errores.append(error.value)
    assert [e.codigo for e in errores] == ["credencial", "limitado", "sin_conexion", "salida",
                                          "limitado", "interno", "credencial", "sin_conexion"]
    secretos = [*falso.tokens, falso.asercion_vista, *falso._enlaces, BUZON, INQUILINO,
                APLICACION, "evil.example"]
    assert all(secretos)
    textos = [_todo_el_texto(e) for e in errores] + [caplog.text, repr(cliente)]
    for texto in textos:
        assert not [s for s in secretos if s in texto], texto
    for error in errores:
        assert error.__cause__ is None and error.__context__ is None
    assert not [r for r in caplog.records if r.name.startswith(("httpx2", "httpcore2"))]


def test_el_token_no_se_copia_ni_se_ensena(cliente) -> None:
    import copy
    import pickle

    token = cliente._bearer()
    assert repr(token) == "<token de Graph>" and token._valor not in repr(cliente.__dict__)
    for copiar in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError):
            copiar(token)


# ============================================================ por una salida de verdad

class _Aceptador(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Eco(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        try:
            while datos := self.request.recv(4096):
                self.request.sendall(datos)
        except OSError:
            pass


@contextmanager
def _servidor(crear):
    servidor = crear()
    hilo = threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.05},
                            daemon=True)
    hilo.start()
    try:
        yield servidor
    finally:
        servidor.shutdown()
        servidor.server_close()


@contextmanager
def _salida_del_correo():
    """La salida de verdad (salida.Proxy) con la lista del correo y la credencial de una
    pasada; lo que pasa va a un eco local: nada sale de esta maquina."""
    with _servidor(lambda: _Aceptador(("127.0.0.1", 0), _Eco)) as eco:
        proxy = salida.Proxy(("127.0.0.1", 0), salida.lista_blanca(salida.DESTINOS_CORREO),
                             resolver=lambda host, puerto: ["127.0.0.1"],
                             conectar=lambda _d, espera: socket.create_connection(
                                 eco.server_address, espera),
                             solo_publicas=False, inactividad=2, clave=CREDENCIAL)
        with _servidor(lambda: proxy) as servidor:
            yield servidor.server_address


class _Repartir(httpx2.BaseTransport):
    """El token al falso; lo demas, por la salida."""

    def __init__(self, falso: GraphFalso, por_la_salida: httpx2.BaseTransport,
                 token_tambien: bool = False) -> None:
        self.falso, self.salida, self.token_tambien = falso, por_la_salida, token_tambien

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.host == graph.LOGIN and not self.token_tambien:
            return self.falso.transporte.handle_request(request)
        return self.salida.handle_request(request)


def test_por_la_salida_del_correo(falso, certificado_de_prueba, reloj, dormidas,
                                  caplog) -> None:
    assert salida.DESTINOS_CORREO == ("login.microsoftonline.com:443", "graph.microsoft.com:443")
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    credencial = certificado.cargar(certificado_de_prueba[0])
    with _salida_del_correo() as (host, puerto):
        for clave, token_tambien, codigo, pasa in (
                (CREDENCIAL, False, "sin_conexion", "graph.microsoft.com:443"),
                (CREDENCIAL, True, "sin_conexion", "login.microsoftonline.com:443"),
                (None, False, "salida", None), ("otra" * 8, True, "salida", None)):
            caplog.clear()
            usuario = "" if clave is None else f"bms:{clave}@"
            por_la_salida = httpx2.HTTPTransport(proxy=f"http://{usuario}{host}:{puerto}")
            with graph.ClienteGraph(_ajustes(), credencial, ahora=reloj, dormir=dormidas,
                                    transporte=_Repartir(falso, por_la_salida,
                                                         token_tambien)) as cliente:
                error = _error(cliente.comprobar)
            registro = "\n".join(r.getMessage() for r in caplog.records)
            # Pasa la salida (y el TLS falla contra el eco local); sin la credencial, 407.
            assert error.codigo == codigo, (clave, registro)
            if pasa:
                assert f"CONNECT {pasa}" in registro and "decision=permitida" in registro
            else:
                assert "codigo=407" in registro and "decision=permitida" not in registro
            assert not [t for t in falso.tokens if t in registro + _todo_el_texto(error)]
        # A la API de Anthropic, ni con la credencial: 403.
        assert aislamiento.pedir_tunel((host, puerto), "api.anthropic.com:443", CREDENCIAL,
                                       2) == 403
        assert aislamiento.pedir_tunel((host, puerto), "graph.microsoft.com:80", CREDENCIAL,
                                       2) == 403
        assert aislamiento.pedir_tunel((host, puerto), "graph.microsoft.com:443", None, 2) == 407


# ============================================================ sin procesos (§7.2)

SIN_PROCESOS = r'''
import subprocess, sys
from datetime import date, datetime, timezone
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2])
from bms_agent import nativo
nativo.prohibir_procesos()
# Desde aqui nada arranca otro programa: ni importar cryptography y httpx2, ni firmar, ni hablar
# con Graph.
from bms_agent.correo import ajustes, certificado, graph
from graph_falso import GraphFalso, mensajes
ahora = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
pem, cer = certificado.rutas(sys.argv[3])
falso = GraphFalso(certificado=open(cer, "rb").read(), inquilino=sys.argv[4],
                   aplicacion=sys.argv[5], buzon=sys.argv[6], control=sys.argv[7],
                   ahora=lambda: ahora)
falso.llega(mensajes()["factura"])
datos = ajustes.Ajustes(inquilino=sys.argv[4], aplicacion=sys.argv[5], buzon=sys.argv[6],
                        buzon_control=sys.argv[7], desde=date(2026, 10, 25))
with graph.ClienteGraph(datos, certificado.cargar(pem), transporte=falso.transporte,
                        ahora=lambda: ahora) as cliente:
    alcance = cliente.comprobar()
    paginas = list(cliente.delta("bandeja", None, datetime(2026, 10, 25, tzinfo=timezone.utc)))
falso.comprobar()
try:
    subprocess.run(["true"])
except PermissionError as exc:
    assert "no arranca otros programas" in str(exc)
else:
    raise SystemExit("ha lanzado un proceso")
print(alcance.bien, sum(len(p.mensajes) for p in paginas))
'''


def test_firma_y_habla_con_graph_con_los_procesos_prohibidos(certificado_de_prueba) -> None:
    """Como en la instalacion (nativo.prohibir_procesos): importar cryptography y httpx2, firmar
    la asercion y hablar con GraphFalso no arrancan ningun programa (en otro proceso, con los
    avisos como errores)."""
    proceso = subprocess.run(
        [sys.executable, "-W", "error", "-c", SIN_PROCESOS, str(SRC.parent),
         str(RAIZ / "tests"), str(certificado_de_prueba[0].parent), INQUILINO, APLICACION,
         BUZON, CONTROL], capture_output=True, text=True, timeout=120)
    assert proceso.returncode == 0, proceso.stderr
    assert proceso.stdout.split() == ["True", "1"]
