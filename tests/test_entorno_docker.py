"""El entorno de Docker de verdad, con sus contenedores (paso 13). Solo con BMS_PROBAR_DOCKER=1.

Arranca el entorno en un proyecto aparte (bms-agent-prueba, con su propio volumen,
una clave falsa y un buzon vacio: nada del entorno de verdad se toca) y comprueba lo
que la configuracion promete:

- la consola contesta en 127.0.0.1:8765, con la banda de DATOS DE PRUEBA;
- desde el contenedor de la consola no se llega a internet, ni al proxy;
- desde el lector no se llega a internet directamente, solo al proxy;
- el proxy deja ir a api.anthropic.com:443 y a nada mas, y apunta cada intento;
- el cliente HTTP del SDK sale por el proxy (HTTPS_PROXY).

No llama a la API: el tunel hasta api.anthropic.com se abre y se cierra sin mandar nada.
Necesita la imagen bms-agent:local ya construida (docs/entorno-local.md). En una maquina
donde Docker pide sudo: BMS_DOCKER="sudo -n docker".
"""

from __future__ import annotations

import os
import shlex
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
from conftest import RAIZ

pytestmark = pytest.mark.skipif(os.environ.get("BMS_PROBAR_DOCKER") != "1",
                                reason="solo con BMS_PROBAR_DOCKER=1 (arranca contenedores)")

PROYECTO = "bms-agent-prueba"
COMPOSE = RAIZ / "docker" / "docker-compose.yml"
DOCKER = shlex.split(os.environ.get("BMS_DOCKER", "docker"))


def _compose(extra: Path, *argumentos: str, entrada: str | None = None,
             comprobar: bool = True) -> subprocess.CompletedProcess:
    orden = [*DOCKER, "compose", "-p", PROYECTO, "-f", str(COMPOSE), "-f", str(extra),
             *argumentos]
    proceso = subprocess.run(orden, input=entrada, capture_output=True, text=True,
                             timeout=600)
    if comprobar:
        assert proceso.returncode == 0, (argumentos, proceso.stdout, proceso.stderr)
    return proceso


@pytest.fixture(scope="module")
def entorno(tmp_path_factory):
    imagen = subprocess.run([*DOCKER, "image", "inspect", "bms-agent:local"],
                            capture_output=True)
    if imagen.returncode != 0:
        pytest.skip("falta la imagen bms-agent:local (docker compose build)")
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", 8765)) == 0:
            pytest.skip("el puerto 8765 ya esta en uso (hay otra consola en marcha)")
    carpeta = tmp_path_factory.mktemp("docker")
    clave = carpeta / "clave.txt"
    clave.write_text("sk-ant-falsa-solo-para-probar-la-red\n", encoding="utf-8")
    clave.chmod(0o644)
    buzon = carpeta / "buzon"
    (buzon / "facturas").mkdir(parents=True)
    buzon.chmod(0o755)
    extra = carpeta / "prueba.yml"
    # La base de prueba se dice aqui y no con BMS_BASE: sudo no pasa el entorno.
    demo = "    environment: {BMS_DB: /datos/demo.sqlite3}\n"
    extra.write_text(
        "services:\n"
        f"  consola:\n{demo}"
        f"  lector:\n{demo}    volumes: [\"datos:/datos\", \"{buzon}:/buzon:ro\"]\n"
        f"  orden:\n{demo}    volumes: [\"datos:/datos\", \"{buzon}:/buzon:ro\"]\n"
        f"secrets:\n  anthropic_api_key:\n    file: {clave}\n", encoding="utf-8")
    _compose(extra, "run", "--rm", "-T", "orden", "demo", "crear", "--db",
             "/datos/demo.sqlite3")
    _compose(extra, "up", "-d", "consola", "salida")
    try:
        for _intento in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/consola", timeout=2) as r:
                    if r.status == 200:
                        break
            except OSError:
                time.sleep(1)
        yield extra
    finally:
        _compose(extra, "down", "-v", "--remove-orphans", comprobar=False)


_PROBAR = """
import socket
def probar(destino, puerto):
    try:
        socket.create_connection((destino, puerto), timeout=4).close()
        return "conecta"
    except OSError:
        return "no"
for destino, puerto in {destinos}:
    print(f"{{destino}}:{{puerto}}", probar(destino, puerto))
"""


def _desde(entorno: Path, servicio: str, destinos: list[tuple[str, int]]) -> dict[str, str]:
    codigo = _PROBAR.format(destinos=destinos)
    if servicio == "consola":
        proceso = _compose(entorno, "exec", "-T", "consola", "python", "-", entrada=codigo)
    else:
        proceso = _compose(entorno, "run", "--rm", "-T", "--entrypoint", "python", servicio, "-",
                           entrada=codigo)
    return dict(linea.split(" ", 1) for linea in proceso.stdout.strip().splitlines())


def test_la_consola_contesta_en_127_0_0_1_con_la_banda(entorno) -> None:
    with urllib.request.urlopen("http://127.0.0.1:8765/consola", timeout=5) as respuesta:
        pagina = respuesta.read().decode("utf-8")
        assert respuesta.headers["X-BMS-Entorno"] == "demo"
    assert 'id="datos-de-prueba"' in pagina
    puerto = _compose(entorno, "port", "salida", "8765").stdout.strip()
    assert puerto == "127.0.0.1:8765"


def test_la_consola_no_llega_a_internet_ni_al_proxy(entorno) -> None:
    resultado = _desde(entorno, "consola", [("1.1.1.1", 443), ("8.8.8.8", 53),
                                            ("api.anthropic.com", 443), ("proxy", 3128),
                                            ("salida", 3128), ("consola", 8765)])
    assert resultado == {"1.1.1.1:443": "no", "8.8.8.8:53": "no", "api.anthropic.com:443": "no",
                         "proxy:3128": "no", "salida:3128": "no", "consola:8765": "conecta"}


def test_el_lector_solo_llega_al_proxy(entorno) -> None:
    resultado = _desde(entorno, "lector", [("1.1.1.1", 443), ("api.anthropic.com", 443),
                                           ("consola", 8765), ("entrada", 8765),
                                           ("proxy", 3128)])
    assert resultado == {"1.1.1.1:443": "no", "api.anthropic.com:443": "no",
                         "consola:8765": "no", "entrada:8765": "no", "proxy:3128": "conecta"}


_POR_EL_PROXY = r"""
import socket
def pedir(texto):
    s = socket.create_connection(("proxy", 3128), timeout=15)
    s.sendall(texto.encode())
    linea = s.recv(200).split(b"\r\n")[0].decode()
    s.close()
    return linea.split(" ")[1]
for destino in ["api.anthropic.com:443", "example.com:443", "api.anthropic.com.evil.example:443",
                "160.79.104.10:443", "api.anthropic.com:80"]:
    print(destino, pedir(f"CONNECT {destino} HTTP/1.1\r\nHost: {destino}\r\n\r\n"))
print("GET", pedir("GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n\r\n"))
import httpx2
try:
    httpx2.get("https://example.com/", timeout=15)
    print("sdk contesta")
except Exception as exc:
    print("sdk", type(exc).__name__)
"""


def test_el_proxy_solo_deja_ir_a_la_api_y_lo_apunta(entorno) -> None:
    proceso = _compose(entorno, "run", "--rm", "-T", "--entrypoint", "python", "lector", "-",
                       entrada=_POR_EL_PROXY)
    resultado = dict(l.split(" ", 1) for l in proceso.stdout.strip().splitlines())
    assert resultado == {"api.anthropic.com:443": "200", "example.com:443": "403",
                         "api.anthropic.com.evil.example:443": "403", "160.79.104.10:443": "403",
                         "api.anthropic.com:80": "403", "GET": "405", "sdk": "ProxyError"}
    registro = _compose(entorno, "logs", "salida").stdout
    for destino in ("api.anthropic.com:443", "example.com:443",
                    "api.anthropic.com.evil.example:443"):
        assert f"CONNECT {destino}" in registro
    assert "decision=permitida codigo=200" in registro
    assert registro.count("decision=rechazada") >= 6
