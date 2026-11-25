"""El entorno de Docker de verdad, con sus contenedores (paso 13). Solo con BMS_PROBAR_DOCKER=1.

Arranca el entorno en un proyecto aparte (bms-agent-prueba, con su propio volumen,
una clave falsa y un buzon vacio: nada del entorno de verdad se toca) y comprueba lo
que la configuracion promete:

- la consola contesta en 127.0.0.1:8765, con la banda de DATOS DE PRUEBA;
- desde el contenedor de la consola no se llega a internet, ni al proxy;
- desde el lector no se llega a internet directamente, solo al proxy;
- el proxy deja ir a api.anthropic.com:443 y a nada mas, y apunta cada intento;
- el cliente HTTP del SDK sale por el proxy (HTTPS_PROXY);
- el registro de la salida sigue despues de `docker compose down` (su volumen);
- paso 18: el correo solo llega a su proxy, que solo deja ir a los dos hosts de Microsoft; el
  lector no llega a Microsoft ni al proxy del correo; la salida del correo no llega a la
  consola; y el correo (uid 10001) escribe en sus dos volumenes.

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
    # Paso 18: los dos secretos del correo, de mentira (no se pide nada a Microsoft).
    ajustes = carpeta / "correo_ajustes.json"
    ajustes.write_text("{}\n", encoding="utf-8")
    certificado = carpeta / "correo_certificado.pem"
    certificado.write_text("de prueba\n", encoding="utf-8")
    for fichero in (ajustes, certificado):
        fichero.chmod(0o644)
    extra = carpeta / "prueba.yml"
    # La base de prueba se dice aqui y no con BMS_BASE: sudo no pasa el entorno.
    demo = "    environment: {BMS_DB: /datos/demo.sqlite3}\n"
    extra.write_text(
        "services:\n"
        f"  consola:\n{demo}"
        f"  lector:\n{demo}    volumes: [\"datos:/datos\", \"{buzon}:/buzon:ro\"]\n"
        f"  orden:\n{demo}    volumes: [\"datos:/datos\", \"{buzon}:/buzon:ro\"]\n"
        f"secrets:\n  anthropic_api_key:\n    file: {clave}\n"
        f"  correo_ajustes:\n    file: {ajustes}\n"
        f"  correo_certificado:\n    file: {certificado}\n", encoding="utf-8")
    _compose(extra, "run", "--rm", "-T", "orden", "demo", "crear", "--db",
             "/datos/demo.sqlite3")
    _compose(extra, "up", "-d", "consola", "salida", "salida_correo")
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
    if servicio in ("consola", "salida_correo"):
        proceso = _compose(entorno, "exec", "-T", servicio, "python", "-", entrada=codigo)
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
                                           ("proxy", 3128), ("proxy-correo", 3128),
                                           ("graph.microsoft.com", 443)])
    assert resultado == {"1.1.1.1:443": "no", "api.anthropic.com:443": "no",
                         "consola:8765": "no", "entrada:8765": "no", "proxy:3128": "conecta",
                         "proxy-correo:3128": "no", "graph.microsoft.com:443": "no"}


def test_el_correo_solo_llega_a_su_proxy(entorno) -> None:
    """Paso 18: la red del correo tiene un solo vecino, su salida; ni la de la API ni la
    consola."""
    resultado = _desde(entorno, "correo", [("1.1.1.1", 443), ("graph.microsoft.com", 443),
                                           ("proxy", 3128), ("salida", 3128),
                                           ("consola", 8765), ("entrada", 8765),
                                           ("proxy-correo", 3128)])
    assert resultado == {"1.1.1.1:443": "no", "graph.microsoft.com:443": "no",
                         "proxy:3128": "no", "salida:3128": "no", "consola:8765": "no",
                         "entrada:8765": "no", "proxy-correo:3128": "conecta"}


def test_la_salida_del_correo_no_llega_a_la_consola(entorno) -> None:
    """S7: la salida del correo sale por su propia red: no ve la entrada a la consola (que la
    salida de la API escucha en red_exterior), ni la consola, ni la salida de la API."""
    resultado = _desde(entorno, "salida_correo", [("entrada", 8765), ("salida", 8765),
                                                  ("consola", 8765), ("proxy", 3128)])
    assert resultado == {"entrada:8765": "no", "salida:8765": "no", "consola:8765": "no",
                         "proxy:3128": "no"}


_POR_EL_PROXY_DEL_CORREO = r"""
import socket
def pedir(texto):
    s = socket.create_connection(("proxy-correo", 3128), timeout=15)
    s.sendall(texto.encode())
    linea = s.recv(200).split(b"\r\n")[0].decode()
    s.close()
    return linea.split(" ")[1]
for destino in ["login.microsoftonline.com:443", "graph.microsoft.com:443",
                "api.anthropic.com:443", "example.com:443", "graph.microsoft.com:80",
                "graph.microsoft.com.evil.example:443"]:
    print(destino, pedir(f"CONNECT {destino} HTTP/1.1\r\nHost: {destino}\r\n\r\n"))
"""


def test_el_proxy_del_correo_solo_deja_ir_a_microsoft(entorno) -> None:
    proceso = _compose(entorno, "run", "--rm", "-T", "--entrypoint", "python", "correo", "-",
                       entrada=_POR_EL_PROXY_DEL_CORREO)
    resultado = dict(l.split(" ", 1) for l in proceso.stdout.strip().splitlines())
    assert resultado == {"login.microsoftonline.com:443": "200", "graph.microsoft.com:443": "200",
                         "api.anthropic.com:443": "403", "example.com:443": "403",
                         "graph.microsoft.com:80": "403",
                         "graph.microsoft.com.evil.example:443": "403"}
    registro = _compose(entorno, "logs", "salida_correo").stdout
    assert "CONNECT api.anthropic.com:443" in registro and "decision=rechazada" in registro


_ESCRIBIR = r"""
import os
print("uid", os.getuid())
for carpeta in ("/correo/estado", "/correo/entrada"):
    try:
        with open(os.path.join(carpeta, "prueba-escritura"), "w") as f:
            f.write("x")
        os.remove(os.path.join(carpeta, "prueba-escritura"))
        print(carpeta, "escribe")
    except OSError:
        print(carpeta, "no")
"""


def test_el_correo_escribe_en_sus_volumenes_y_orden_solo_en_la_bandeja(entorno) -> None:
    """V1: la imagen da a bms los dos puntos de montaje del correo; el correo (uid 10001)
    escribe en los dos; las ordenes, en la bandeja (el acuse) y no en el estado."""
    correo = _compose(entorno, "run", "--rm", "-T", "--entrypoint", "python", "correo", "-",
                      entrada=_ESCRIBIR).stdout
    assert dict(l.split(" ", 1) for l in correo.strip().splitlines()) == {
        "uid": "10001", "/correo/estado": "escribe", "/correo/entrada": "escribe"}
    orden = _compose(entorno, "run", "--rm", "-T", "--entrypoint", "python", "orden", "-",
                     entrada=_ESCRIBIR).stdout
    assert dict(l.split(" ", 1) for l in orden.strip().splitlines()) == {
        "uid": "10001", "/correo/estado": "no", "/correo/entrada": "escribe"}


_POR_EL_PROXY = r"""
import socket
def pedir(texto):
    s = socket.create_connection(("proxy", 3128), timeout=15)
    s.sendall(texto.encode())
    linea = s.recv(200).split(b"\r\n")[0].decode()
    s.close()
    return linea.split(" ")[1]
for destino in ["api.anthropic.com:443", "example.com:443", "api.anthropic.com.evil.example:443",
                "160.79.104.10:443", "api.anthropic.com:80", "graph.microsoft.com:443",
                "login.microsoftonline.com:443"]:
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
                         "api.anthropic.com:80": "403", "graph.microsoft.com:443": "403",
                         "login.microsoftonline.com:443": "403", "GET": "405",
                         "sdk": "ProxyError"}
    registro = _compose(entorno, "logs", "salida").stdout
    for destino in ("api.anthropic.com:443", "example.com:443",
                    "api.anthropic.com.evil.example:443"):
        assert f"CONNECT {destino}" in registro
    assert "decision=permitida codigo=200" in registro
    assert registro.count("decision=rechazada") >= 6


def test_el_registro_de_la_salida_sobrevive_a_parar_y_arrancar(entorno) -> None:
    """iniciar, parar y restaurar hacen `docker compose down`, que se lleva el registro de
    Docker: el de la salida vive en su volumen y sigue ahi (va el ultimo: para el entorno)."""
    _compose(entorno, "down")
    _compose(entorno, "up", "-d", "consola", "salida", "salida_correo")
    proceso = _compose(entorno, "run", "--rm", "-T", "orden", "salida-registro", "--rechazados")
    assert "example.com:443" in proceso.stdout
    assert "api.anthropic.com.evil.example:443" in proceso.stdout
