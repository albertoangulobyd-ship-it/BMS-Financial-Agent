"""El servidor local no se deja usar desde otras webs.

Escucha en 127.0.0.1, pero el navegador de quien lo tiene abierto visita
otras paginas. Estos tests son esas paginas: un origen que empieza igual que
localhost, un DNS que rebota hacia 127.0.0.1 y un formulario que intenta
lanzar una pasada que se paga. Se levanta el servidor de verdad en un puerto
libre, con un agente falso que cuenta los lanzamientos.
"""

from __future__ import annotations

import http.client
import json
import threading

import pytest

from bms_agent.serve import (
    CABECERA_TOKEN,
    crear_servidor,
    host_permitido,
    normalizar_origen,
    origen_permitido,
    origenes_permitidos,
)

TOKEN = "token-de-prueba-0123456789"


class AgenteFalso:
    def __init__(self) -> None:
        self.lanzamientos = 0

    @property
    def estado(self) -> dict:
        return {"estado": "inactivo", "lanzamientos": self.lanzamientos}

    def lanzar(self) -> tuple[bool, str]:
        self.lanzamientos += 1
        return True, "Ejecucion lanzada."


@pytest.fixture
def servidor(tmp_path):
    agente = AgenteFalso()
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "out", 0,
                         origenes_extra=["http://localhost:5173"], token=TOKEN, agente=agente)
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    hilo.start()
    try:
        yield srv.server_address[1], agente
    finally:
        srv.shutdown()
        srv.server_close()


def _pedir(puerto, metodo, ruta, cabeceras=None, cuerpo=None):
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)
    cabeceras = {"Host": f"127.0.0.1:{puerto}", **(cabeceras or {})}
    conexion.request(metodo, ruta, body=cuerpo, headers=cabeceras)
    respuesta = conexion.getresponse()
    datos = respuesta.read()
    conexion.close()
    return respuesta.status, {k.lower(): v for k, v in respuesta.getheaders()}, datos


def _post_bueno(puerto, **extra):
    cabeceras = {"Content-Type": "application/json", CABECERA_TOKEN: TOKEN, **extra}
    return _pedir(puerto, "POST", "/api/ejecutar", cabeceras, b"{}")


# --- reglas puras ---

@pytest.mark.parametrize("origen", [
    "http://localhost.attacker.example",
    "http://127.0.0.1.nip.io",
    "http://localhost.attacker.example:8765",
    "http://127.0.0.1.nip.io:8765",
    "http://localhost:8766",
    "https://localhost:8765",
    "http://evil.example",
    "null",
    "",
    "http://localhost:8765/ruta",
    "http://user@localhost:8765",
    "http://localhost:abc",
])
def test_un_origen_que_solo_se_parece_no_pasa(origen) -> None:
    """La comprobacion por prefijo dejaba pasar los dos primeros."""
    assert not origen_permitido(origen, origenes_permitidos(8765))


@pytest.mark.parametrize("origen", [
    "http://localhost:8765", "http://127.0.0.1:8765", "http://LOCALHOST:8765",
])
def test_la_propia_pagina_si_pasa(origen) -> None:
    assert origen_permitido(origen, origenes_permitidos(8765))


def test_otro_puerto_local_solo_pasa_si_se_declara() -> None:
    assert not origen_permitido("http://localhost:5173", origenes_permitidos(8765))
    declarados = origenes_permitidos(8765, ["http://localhost:5173"])
    assert origen_permitido("http://localhost:5173", declarados)
    assert not origen_permitido("http://localhost:5174", declarados)


@pytest.mark.parametrize("origen", ["https://example.com", "http://192.168.1.10:3000", "basura"])
def test_no_se_puede_declarar_un_origen_que_no_es_local(origen) -> None:
    with pytest.raises(ValueError):
        origenes_permitidos(8765, [origen])


def test_el_puerto_por_defecto_se_normaliza() -> None:
    assert normalizar_origen("http://localhost") == "http://localhost:80"
    assert normalizar_origen("http://localhost:80/") == "http://localhost:80"


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "LocalHost:8765"])
def test_host_propio(host) -> None:
    assert host_permitido(host, 8765)


@pytest.mark.parametrize("host", [
    "evil.example:8765", "localhost.attacker.example:8765", "127.0.0.1.nip.io:8765",
    "127.0.0.1:8766", "127.0.0.1", "", None, "127.0.0.1:8765@evil.example",
    "127.0.0.1:8765/x", "[::1]:8765", "127.0.0.1:abc",
])
def test_host_ajeno(host) -> None:
    assert not host_permitido(host, 8765)


# --- el servidor de verdad ---

def test_un_origen_parecido_no_recibe_cabecera_cors(servidor) -> None:
    puerto, _ = servidor
    for origen in ("http://localhost.attacker.example", "http://127.0.0.1.nip.io"):
        estado, cabeceras, _ = _pedir(puerto, "GET", "/api/datos", {"Origin": origen})
        assert estado == 403
        assert "access-control-allow-origin" not in cabeceras


def test_el_origen_propio_y_el_declarado_si_reciben_cors(servidor) -> None:
    """Con /api/ejecucion: /api/datos pide desde la revision final un token personal (lo
    prueba test_revision_final), y aqui solo se mira la cabecera CORS."""
    puerto, _ = servidor
    for origen in (f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}",
                   "http://localhost:5173"):
        estado, cabeceras, cuerpo = _pedir(puerto, "GET", "/api/ejecucion", {"Origin": origen})
        assert estado == 200
        assert cabeceras["access-control-allow-origin"] == origen
        assert "estado" in json.loads(cuerpo)


def test_un_host_ajeno_se_rechaza(servidor) -> None:
    """DNS rebinding: la peticion llega a 127.0.0.1 con el nombre del atacante."""
    puerto, agente = servidor
    for host in (f"attacker.example:{puerto}", f"localhost.attacker.example:{puerto}"):
        estado, cabeceras, _ = _pedir(puerto, "GET", "/api/datos", {"Host": host})
        assert estado in (403, 421)
        assert "access-control-allow-origin" not in cabeceras
        estado, _, _ = _post_bueno(puerto, Host=host)
        assert estado in (403, 421)
    assert agente.lanzamientos == 0


def test_un_formulario_de_otra_web_no_lanza_una_pasada(servidor) -> None:
    """Lo unico que puede mandar un <form>: urlencoded, sin cabeceras propias."""
    puerto, agente = servidor
    formulario = {"Content-Type": "application/x-www-form-urlencoded"}
    estado, cabeceras, _ = _pedir(puerto, "POST", "/api/ejecutar",
                                  {**formulario, "Origin": "http://evil.example"}, b"a=1")
    assert estado == 403
    assert "access-control-allow-origin" not in cabeceras
    # Sin Origin (algunos navegadores lo omiten) tampoco: falta el token.
    estado, _, _ = _pedir(puerto, "POST", "/api/ejecutar", formulario, b"a=1")
    assert estado == 403
    # Ni siquiera desde la propia pagina sin el token.
    estado, _, _ = _pedir(puerto, "POST", "/api/ejecutar",
                          {**formulario, "Origin": f"http://127.0.0.1:{puerto}"}, b"a=1")
    assert estado == 403
    assert agente.lanzamientos == 0


def test_un_token_equivocado_no_sirve(servidor) -> None:
    puerto, agente = servidor
    estado, _, _ = _pedir(puerto, "POST", "/api/ejecutar",
                          {"Content-Type": "application/json", CABECERA_TOKEN: "otro"}, b"{}")
    assert estado == 403
    assert agente.lanzamientos == 0


def test_con_token_pero_sin_json_se_rechaza(servidor) -> None:
    puerto, agente = servidor
    for tipo, cuerpo in (("text/plain", b"{}"), ("application/json", b"[1, 2]"),
                         ("application/json", b"no es json")):
        estado, _, _ = _pedir(puerto, "POST", "/api/ejecutar",
                              {"Content-Type": tipo, CABECERA_TOKEN: TOKEN}, cuerpo)
        assert estado in (400, 415), (tipo, cuerpo)
    assert agente.lanzamientos == 0


def test_un_cuerpo_enorme_no_se_lee(servidor) -> None:
    puerto, agente = servidor
    estado, _, _ = _pedir(puerto, "POST", "/api/ejecutar",
                          {"Content-Type": "application/json", CABECERA_TOKEN: TOKEN},
                          b"{" + b" " * 10_000 + b"}")
    assert estado == 413
    assert agente.lanzamientos == 0


def test_con_token_y_json_si_se_lanza(servidor) -> None:
    puerto, agente = servidor
    estado, cabeceras, cuerpo = _post_bueno(puerto, Origin=f"http://localhost:{puerto}")
    assert estado == 202
    assert json.loads(cuerpo)["lanzada"] is True
    assert cabeceras["access-control-allow-origin"] == f"http://localhost:{puerto}"
    assert agente.lanzamientos == 1


def test_la_peticion_previa_admite_el_token_solo_para_origenes_propios(servidor) -> None:
    puerto, _ = servidor
    origen = "http://localhost:5173"
    estado, cabeceras, _ = _pedir(puerto, "OPTIONS", "/api/ejecutar", {
        "Origin": origen, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": f"content-type, {CABECERA_TOKEN.lower()}",
    })
    assert estado == 204
    assert cabeceras["access-control-allow-origin"] == origen
    assert CABECERA_TOKEN in cabeceras["access-control-allow-headers"]

    estado, cabeceras, _ = _pedir(puerto, "OPTIONS", "/api/ejecutar",
                                  {"Origin": "http://localhost.attacker.example"})
    assert estado == 403
    assert "access-control-allow-origin" not in cabeceras


def test_la_pagina_local_lleva_el_token_y_no_se_deja_enmarcar(servidor) -> None:
    puerto, _ = servidor
    estado, cabeceras, cuerpo = _pedir(puerto, "GET", "/")
    assert estado == 200
    assert cabeceras["content-type"].startswith("text/html")
    assert f'<meta name="bms-token" content="{TOKEN}">' in cuerpo.decode("utf-8")
    assert cabeceras["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in cabeceras["content-security-policy"]
    assert cabeceras["cache-control"] == "no-store"


def test_cada_servidor_tiene_su_propio_token(tmp_path) -> None:
    tokens = set()
    for _ in range(2):
        srv = crear_servidor(tmp_path, tmp_path, 0, agente=AgenteFalso())
        tokens.add(srv.RequestHandlerClass.token)
        srv.server_close()
    assert len(tokens) == 2 and all(len(t) >= 32 for t in tokens)


def test_solo_escucha_en_127_0_0_1(tmp_path) -> None:
    srv = crear_servidor(tmp_path, tmp_path, 0, agente=AgenteFalso())
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()
