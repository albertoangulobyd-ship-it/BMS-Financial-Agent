"""La instalacion nativa de Windows, sin Docker (paso 14). Aqui no hay Windows: se prueba
todo lo que es Python y, de los scripts de PowerShell, lo que se puede leer.

Puertas que viven aqui:

- la clave de la API con DPAPI: se guarda cifrada, nunca se ensena y solo la descifra el
  lector (con un protector falso: aqui no hay DPAPI, y fuera de Windows se niega);
- la comprobacion de aislamiento, con sockets locales: un puerto bloqueado, un proxy que
  deja pasar lo que debe, uno que deja pasar de mas y uno que no pide la credencial;
- falla cerrada: sin la comprobacion de esta pasada, o con una que falla, ninguna orden que
  habla con la API llega a crear el cliente;
- la banda roja de la consola;
- la credencial del proxy de la salida (que en Docker no se usa);
- ningun modulo lanza procesos (el hueco de las reglas por programa);
- los scripts de windows/: ASCII, su .bat, sin Docker, sin descargas sin hash, las reglas del
  cortafuegos con su prefijo, programa, sentido y accion, el desinstalador que las quita por
  el prefijo, y PowerShell 5.1. Con pwsh (o BMS_PROBAR_PWSH=1 y Docker), ademas, cada .ps1
  pasa el analizador de PowerShell y unas funciones se ejecutan de verdad.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import logging
import ntpath
import os
import re
import shlex
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from conftest import RAIZ

from bms_agent import aislamiento, config, consola, nativo, salida, secretos
from bms_agent.cli import main
from bms_agent.serve import CABECERA_TOKEN, crear_servidor

WINDOWS = RAIZ / "windows"
SRC = RAIZ / "src" / "bms_agent"
AHORA = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
CREDENCIAL = "c" * 64
CLAVE = "sk-ant-api03-de-prueba-para-los-tests"


# ============================================================ ayudas

class ProtectorFalso:
    """Hace de DPAPI: lo cifrado solo lo descifra el mismo "usuario" y con la entropia."""

    def __init__(self, usuario: str = "ana") -> None:
        self.marca = b"FALSO:" + usuario.encode() + b":"
        self.llamadas: list[str] = []

    def proteger(self, datos: bytes, entropia: bytes) -> bytes:
        self.llamadas.append("proteger")
        assert entropia == secretos.ENTROPIA
        return self.marca + bytes(b ^ 0x5A for b in datos)

    def desproteger(self, blob: bytes, entropia: bytes) -> bytes:
        self.llamadas.append("desproteger")
        if entropia != secretos.ENTROPIA or not blob.startswith(self.marca):
            raise OSError(13, "DPAPI: no es de este usuario")
        return bytes(b ^ 0x5A for b in blob[len(self.marca):])


def _instalacion(raiz: Path, rol: str, puerto_salida: int = 3128) -> nativo.Instalacion:
    """Una instalacion de mentira en una carpeta temporal: instalacion.json y las carpetas."""
    (raiz / "runtime" / rol).mkdir(parents=True, exist_ok=True)
    (raiz / "runtime" / rol / "python.exe").write_bytes(b"")
    for carpeta in ("app", "lib", "datos", "buzon"):
        (raiz / carpeta).mkdir(exist_ok=True)
    (raiz / nativo.FICHERO_INSTALACION).write_text(json.dumps(
        {"version": 1, "puerto_consola": 8765, "puerto_salida": puerto_salida}),
        encoding="utf-8")
    instalacion = nativo.detectar(raiz / "runtime" / rol / "python.exe")
    assert instalacion is not None and instalacion.rol == rol
    return instalacion


@pytest.fixture
def como(monkeypatch, tmp_path):
    """como("lector") hace creer al codigo que corre con el programa de ese papel."""
    raiz = tmp_path / "BMS"

    def poner(rol: str | None, puerto_salida: int = 3128) -> nativo.Instalacion | None:
        instalacion = _instalacion(raiz, rol, puerto_salida) if rol else None
        monkeypatch.setattr(nativo, "instalacion_actual", lambda: instalacion)
        return instalacion

    return poner


@pytest.fixture
def protector(monkeypatch) -> ProtectorFalso:
    falso = ProtectorFalso()
    monkeypatch.setattr(secretos, "protector_del_sistema", lambda: falso)
    return falso


def _puerto_cerrado() -> int:
    """Un puerto local en el que nadie escucha: como un destino que el cortafuegos bloquea."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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
def _servidor(clase, direccion=("127.0.0.1", 0), manejador=_Eco):
    servidor = clase(direccion, manejador)
    hilo = threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.05},
                            daemon=True)
    hilo.start()
    try:
        yield servidor
    finally:
        servidor.shutdown()
        servidor.server_close()


@contextmanager
def _internet():
    """Un "destino de internet" que si contesta: un programa que llega a el no esta aislado."""
    with _servidor(_Aceptador) as servidor:
        yield servidor.server_address[1]


class _DNS(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        datos, conexion = self.request
        conexion.sendto(datos[:2] + b"\x81\x80" + datos[4:], self.client_address)


@contextmanager
def _dns_que_contesta():
    with _servidor(socketserver.ThreadingUDPServer, manejador=_DNS) as servidor:
        yield servidor.server_address[1]


def _sondas(*, abierto: int | None = None, dns: int | None = None) -> tuple:
    """La lista fija, pero local: todo cerrado salvo lo que se diga. Ningun nombre: nada
    pregunta al DNS de verdad."""
    cerrado = _puerto_cerrado()
    return (
        aislamiento.Sonda("1.1.1.1:443 (TCP)", "127.0.0.1", abierto or cerrado),
        aislamiento.Sonda("8.8.8.8:53 (TCP)", "127.0.0.1", cerrado),
        aislamiento.Sonda("8.8.8.8:53 (UDP, DNS)", "127.0.0.1", dns or cerrado, "udp-dns"),
    )


@contextmanager
def _proxy(*, clave: str | None = CREDENCIAL, permitidos=("api.anthropic.com:443",),
           retraso: float = 0.0):
    """La salida de verdad (salida.Proxy) en 127.0.0.1, con la API de mentira: lo que pide
    api.anthropic.com va a un eco local. Nada sale de esta maquina. `retraso`: lo que tarda
    en conectar con el destino (una conexion lenta)."""
    with _servidor(_Aceptador) as eco:
        def conectar(_direccion, espera):
            if retraso:
                import time

                time.sleep(retraso)
            return socket.create_connection(eco.server_address, espera)

        proxy = salida.Proxy(("127.0.0.1", 0), salida.lista_blanca(permitidos),
                             resolver=lambda host, puerto: ["127.0.0.1"], conectar=conectar,
                             solo_publicas=False, inactividad=2, clave=clave)
        with _servidor(lambda *_a: proxy) as servidor:
            yield servidor.server_address


def _malas(informe) -> list[str]:
    return [c.nombre for c in informe.comprobaciones if c.grave and not c.bien]


# ============================================================ la clave de la API (DPAPI)

def test_la_clave_se_guarda_cifrada_y_se_lee_sin_ensenarla(tmp_path, protector) -> None:
    ruta = secretos.guardar_clave(f"  {CLAVE}\r\n", tmp_path / "secretos" / secretos.FICHERO)
    contenido = ruta.read_bytes()
    assert contenido.startswith(secretos.CABECERA)
    assert CLAVE.encode() not in contenido and b"sk-ant-" not in contenido
    assert secretos.leer_clave(ruta) == CLAVE
    assert protector.llamadas == ["proteger", "desproteger"]
    # No queda ningun temporal al lado.
    assert [p.name for p in ruta.parent.iterdir()] == [secretos.FICHERO]


@pytest.mark.parametrize("mala", ["", "no-es-una-clave", "sk-ant- con espacio", "sk-ant-a\nb"])
def test_una_clave_mala_no_se_guarda_ni_se_ensena(tmp_path, protector, mala) -> None:
    ruta = tmp_path / secretos.FICHERO
    with pytest.raises(config.ClaveNoValida) as error:
        secretos.guardar_clave(mala, ruta)
    if mala.strip():
        assert mala.strip() not in str(error.value)
    assert not ruta.exists() and protector.llamadas == []


def test_otro_usuario_u_otro_ordenador_no_la_descifra(tmp_path, monkeypatch) -> None:
    ruta = secretos.guardar_clave(CLAVE, tmp_path / secretos.FICHERO, ProtectorFalso("ana"))
    with pytest.raises(config.ClaveNoValida) as error:
        secretos.leer_clave(ruta, ProtectorFalso("bram"))
    assert "otro usuario" in str(error.value) and CLAVE not in str(error.value)


@pytest.mark.parametrize("contenido", [None, b"", b"sk-ant-en-claro", secretos.CABECERA])
def test_lo_que_no_es_una_clave_guardada_se_rechaza(tmp_path, protector, contenido) -> None:
    ruta = tmp_path / secretos.FICHERO
    if contenido is not None:
        ruta.write_bytes(contenido)
    with pytest.raises(config.ClaveNoValida) as error:
        secretos.leer_clave(ruta)
    assert "clave.bat" in str(error.value) and "sk-ant-en-claro" not in str(error.value)


@pytest.mark.skipif(sys.platform == "win32", reason="en Windows si hay DPAPI")
def test_fuera_de_windows_no_hay_dpapi_y_se_dice() -> None:
    with pytest.raises(secretos.SinDPAPI) as error:
        secretos.DPAPI()
    assert "Windows" in str(error.value)
    # SinDPAPI es un ClaveNoValida: la CLI lo dice en una linea, sin traza.
    assert issubclass(secretos.SinDPAPI, config.ClaveNoValida)


def test_solo_el_lector_descifra_la_clave(tmp_path, protector) -> None:
    for rol in aislamiento.ROLES:
        instalacion = _instalacion(tmp_path / "BMS", rol)
        secretos.guardar_clave(CLAVE, instalacion.fichero_clave)
        if rol == "lector":
            assert nativo.clave_del_lector(instalacion) == CLAVE
        else:
            with pytest.raises(config.ClaveNoValida, match="solo la descifra el lector"):
                nativo.clave_del_lector(instalacion)


def test_en_la_instalacion_la_clave_nunca_esta_en_claro(tmp_path, monkeypatch, como,
                                                       protector) -> None:
    """La del SDK (ANTHROPIC_API_KEY) no se usa, y un fichero de texto tampoco: solo DPAPI."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-de-una-variable")
    lector = como("lector")
    with pytest.raises(config.ClaveNoValida, match="no hay ninguna clave"):
        config.clave_api()
    secretos.guardar_clave(CLAVE, lector.fichero_clave)
    assert config.clave_api() == CLAVE
    fichero = tmp_path / "clave.txt"
    fichero.write_text(CLAVE, encoding="utf-8")
    monkeypatch.setenv(config.VARIABLE_FICHERO_CLAVE, str(fichero))
    with pytest.raises(config.ClaveNoValida, match="va cifrada"):
        config.clave_api()
    monkeypatch.delenv(config.VARIABLE_FICHERO_CLAVE)
    como("consola")
    with pytest.raises(config.ClaveNoValida, match="solo la descifra el lector"):
        config.clave_api()
    # Fuera de la instalacion, como antes: el SDK la busca.
    como(None)
    assert config.clave_api() is None


def test_la_cli_guarda_comprueba_y_borra_sin_ensenar_la_clave(tmp_path, monkeypatch, protector,
                                                             capsys) -> None:
    ruta = tmp_path / "secretos" / secretos.FICHERO
    preguntas = []
    monkeypatch.setattr("getpass.getpass", lambda texto: preguntas.append(texto) or CLAVE)
    assert main(["clave", "guardar", "--fichero", str(ruta)]) == 0
    assert main(["clave", "comprobar", "--fichero", str(ruta)]) == 0
    assert main(["clave", "borrar", "--fichero", str(ruta)]) == 0
    assert main(["clave", "comprobar", "--fichero", str(ruta)]) == 2
    salida_ = capsys.readouterr()
    assert CLAVE not in salida_.out + salida_.err and "sk-ant-api" not in salida_.out
    assert len(preguntas) == 1 and "no se ve" in preguntas[0]
    assert not ruta.exists()


def test_en_la_instalacion_clave_comprobar_mira_el_fichero_pedido(tmp_path, como, protector,
                                                                 capsys) -> None:
    """Revision del paso 14: con --fichero, comprobar miraba la de la instalacion."""
    lector = como("lector")
    otra = tmp_path / "otra" / secretos.FICHERO
    secretos.guardar_clave(CLAVE, otra)
    assert not lector.fichero_clave.exists()
    assert main(["clave", "comprobar", "--fichero", str(otra)]) == 0
    secretos.guardar_clave(CLAVE, lector.fichero_clave)
    assert main(["clave", "comprobar", "--fichero", str(tmp_path / "no-hay.dpapi")]) == 2
    assert main(["clave", "comprobar"]) == 0
    # La regla del lector sigue: otro programa no la descifra, venga de donde venga.
    como("consola")
    assert main(["clave", "comprobar", "--fichero", str(otra)]) == 2
    assert "solo la descifra el lector" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="en Windows si hay DPAPI")
def test_la_cli_fuera_de_windows_no_pide_la_clave(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("getpass.getpass", lambda texto: pytest.fail("no se pide"))
    assert main(["clave", "guardar", "--fichero", str(tmp_path / "c.dpapi")]) == 2
    assert "Windows" in capsys.readouterr().err


# ============================================================ la comprobacion de aislamiento

def _sin_dns(direccion, espera):
    if direccion[0].endswith(".invalid"):
        raise socket.gaierror("no existe")
    return socket.create_connection(direccion, espera)


def test_una_consola_aislada_sale_bien_y_lo_apunta(tmp_path) -> None:
    sondas = (*_sondas(), aislamiento.Sonda("api.anthropic.com:443 (TCP)", "api.invalid", 443))
    informe = aislamiento.comprobar("consola", sondas=sondas, espera=1, ahora=AHORA,
                                    conectar=_sin_dns)
    assert informe.correcto and len(informe.comprobaciones) == 4
    # Un nombre que no resuelve tampoco es una salida.
    assert dict((c.nombre, c.obtenido) for c in informe.comprobaciones)[
        "directo a api.anthropic.com:443 (TCP)"] == aislamiento.NO_RESUELVE
    # Sin pruebas no se ha comprobado nada.
    assert not aislamiento.Informe("consola", AHORA.isoformat(), ()).correcto
    ruta = tmp_path / aislamiento.FICHERO
    aislamiento.guardar(ruta, informe)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["roles"]["consola"]["correcto"] is True
    assert datos["roles"]["consola"]["fecha"] == AHORA.isoformat(timespec="seconds")
    assert "Aislamiento de la consola: BIEN" in aislamiento.formatear(informe)


@pytest.mark.parametrize("rol", ["consola", "lector", "orden"])
def test_un_papel_que_llega_a_internet_falla(rol) -> None:
    with _internet() as puerto:
        informe = aislamiento.comprobar(rol, sondas=_sondas(abierto=puerto), espera=1)
    assert not informe.correcto
    assert "directo a 1.1.1.1:443 (TCP)" in _malas(informe)
    assert "MAL" in aislamiento.formatear(informe)


def test_un_dns_que_contesta_por_udp_es_una_salida() -> None:
    with _dns_que_contesta() as puerto:
        assert aislamiento.probar_dns_udp("127.0.0.1", puerto, 1) == aislamiento.CONTESTA
        informe = aislamiento.comprobar("consola", sondas=_sondas(dns=puerto), espera=1)
    assert _malas(informe) == ["directo a 8.8.8.8:53 (UDP, DNS)"]
    assert aislamiento.probar_dns_udp("127.0.0.1", _puerto_cerrado(), 0.3) == \
        aislamiento.NO_CONTESTA


def test_el_lector_solo_llega_al_proxy_y_por_el_solo_a_la_api() -> None:
    with _proxy() as proxy:
        informe = aislamiento.comprobar("lector", sondas=_sondas(), proxy=proxy,
                                        credencial=CREDENCIAL, espera=1, espera_api=3)
    obtenido = {c.nombre: c.obtenido for c in informe.comprobaciones}
    assert informe.correcto, aislamiento.formatear(informe)
    assert obtenido["llegar al proxy de la salida"] == aislamiento.CONECTA
    assert obtenido["por el proxy a api.anthropic.com:443"] == "contesta 200"
    for destino in aislamiento.PROHIBIDOS_POR_EL_PROXY:
        assert obtenido[f"por el proxy a {destino}"] == "contesta 403", destino
    assert obtenido["por el proxy a api.anthropic.com:443 sin la credencial"] == "contesta 407"


def test_un_proxy_que_deja_pasar_otro_destino_falla_cerrado() -> None:
    with _proxy(permitidos=("api.anthropic.com:443", "example.com:443")) as proxy:
        informe = aislamiento.comprobar("lector", sondas=_sondas(), proxy=proxy,
                                        credencial=CREDENCIAL, espera=1, espera_api=3)
    assert _malas(informe) == ["por el proxy a example.com:443"]


def test_un_proxy_que_no_pide_la_credencial_falla_cerrado() -> None:
    with _proxy(clave=None) as proxy:
        informe = aislamiento.comprobar("lector", sondas=_sondas(), proxy=proxy,
                                        credencial=CREDENCIAL, espera=1, espera_api=3)
    assert _malas(informe) == ["por el proxy a api.anthropic.com:443 sin la credencial"]


def test_un_proxy_lento_que_deja_pasar_de_mas_no_se_da_por_bueno() -> None:
    """Revision del paso 14: una salida mal puesta conecta con el destino antes de contestar.
    Con una conexion lenta, su 200 llegaba despues del plazo corto y "no contesta" contaba
    como un no. Ahora todas las pruebas por el proxy tienen el plazo de la API, y solo un no
    explicito es un no."""
    with _proxy(permitidos=("api.anthropic.com:443", "example.com:443"), retraso=1.0) as proxy:
        informe = aislamiento.comprobar("lector", sondas=_sondas(), proxy=proxy,
                                        credencial=CREDENCIAL, espera=0.3, espera_api=4)
    assert _malas(informe) == ["por el proxy a example.com:443"]
    assert "Aislamiento del lector: MAL" in aislamiento.formatear(informe)
    with _proxy(clave=None, retraso=1.0) as proxy:
        lector = aislamiento.comprobar("lector", sondas=_sondas(), proxy=proxy,
                                       credencial=CREDENCIAL, espera=0.3, espera_api=4)
        consola_ = aislamiento.comprobar("consola", sondas=_sondas(), proxy=proxy, espera=0.3,
                                         espera_api=4)
    malo = "por el proxy a api.anthropic.com:443 sin la credencial"
    assert _malas(lector) == [malo] and _malas(consola_) == [malo]


@pytest.mark.parametrize("codigo, bien", [(403, True), (400, True), (405, True), (407, True),
                                          (None, False), (200, False), (502, False),
                                          (503, False)])
def test_por_el_proxy_solo_un_no_explicito_es_un_no(codigo, bien) -> None:
    """Pura: un destino prohibido tiene que recibir un 4xx; no contestar no se ha podido
    comprobar (y es grave), y un 502 o un 503 dicen que el destino estaba permitido."""
    vistas = aislamiento.Observaciones(proxy_alcanzable=True, con_credencial={
        aislamiento.API: 200, "example.com:443": codigo})
    juicio = {c.nombre: c for c in aislamiento.evaluar("lector", vistas, ())}
    prohibido = juicio["por el proxy a example.com:443"]
    assert (prohibido.bien, prohibido.grave) == (bien, True)
    if codigo is None:
        assert prohibido.obtenido == "no contesta: no se ha podido comprobar"
    # Sin la credencial, solo el 407: un 403 diria que la credencial no se ha mirado.
    sin = aislamiento.evaluar("consola", aislamiento.Observaciones(
        sin_credencial={aislamiento.API: codigo}), ())
    assert [(c.bien, c.grave) for c in sin] == [(codigo == 407, True)]


def test_un_lector_sin_proxy_no_se_da_por_bueno() -> None:
    sin_proxy = aislamiento.comprobar("lector", sondas=_sondas(), espera=1)
    assert _malas(sin_proxy) == ["llegar al proxy de la salida"]
    apagado = aislamiento.comprobar("lector", sondas=_sondas(), espera=1,
                                    proxy=("127.0.0.1", _puerto_cerrado()), credencial=CREDENCIAL)
    assert _malas(apagado) == ["llegar al proxy de la salida"] and not apagado.correcto


def test_la_consola_no_pasa_por_el_proxy_sin_la_credencial() -> None:
    with _proxy() as proxy:
        bien = aislamiento.comprobar("consola", sondas=_sondas(), proxy=proxy, espera=1)
    with _proxy(clave=None) as proxy:
        mal = aislamiento.comprobar("consola", sondas=_sondas(), proxy=proxy, espera=1)
    assert bien.correcto
    assert _malas(mal) == ["por el proxy a api.anthropic.com:443 sin la credencial"]


def _vistas(**directas) -> aislamiento.Observaciones:
    return aislamiento.Observaciones(directas=directas)


def test_la_salida_solo_puede_salir_por_el_443() -> None:
    """Pura (evaluar): aqui no se puede escuchar en el 443."""
    sondas = aislamiento.EXTERNOS
    bloqueado = {s.nombre: aislamiento.NO_CONECTA for s in sondas}
    con_443 = dict(bloqueado, **{"1.1.1.1:443 (TCP)": aislamiento.CONECTA,
                                 "api.anthropic.com:443 (TCP)": aislamiento.CONECTA})
    juicio = aislamiento.evaluar("salida", aislamiento.Observaciones(directas=con_443), sondas)
    assert all(c.bien for c in juicio)
    # Sin internet no es una fuga, es un aviso: la lectura fallara sola.
    sin_red = aislamiento.evaluar("salida", aislamiento.Observaciones(directas=bloqueado), sondas)
    assert all(c.bien or not c.grave for c in sin_red)
    assert [c.nombre for c in sin_red if not c.grave] == [
        "directo a 1.1.1.1:443 (TCP)", "directo a api.anthropic.com:443 (TCP)"]
    for otro in ("8.8.8.8:53 (TCP)", "8.8.8.8:53 (UDP, DNS)", "1.1.1.1:80 (TCP)"):
        fuga = dict(con_443, **{otro: aislamiento.CONECTA if "TCP" in otro
                                else aislamiento.CONTESTA})
        juicio = aislamiento.evaluar("salida", aislamiento.Observaciones(directas=fuga), sondas)
        assert [c.nombre for c in juicio if c.grave and not c.bien] == [f"directo a {otro}"]


@pytest.mark.parametrize("codigo, bien, grave", [(200, True, True), (502, False, False),
                                                 (None, False, False), (403, False, True),
                                                 (407, False, True)])
def test_lo_que_contesta_la_api_por_el_proxy(codigo, bien, grave) -> None:
    vistas = aislamiento.Observaciones(proxy_alcanzable=True,
                                       con_credencial={aislamiento.API: codigo})
    [_proxy, api] = aislamiento.evaluar("lector", vistas, ())
    assert (api.bien, api.grave) == (bien, grave)


def test_el_codigo_no_se_puede_escribir_y_los_datos_si(tmp_path) -> None:
    instalacion = _instalacion(tmp_path / "BMS", "lector")
    carpetas = instalacion.carpetas_a_probar()
    # La raiz (instalacion.json) y windows (los scripts) tambien: revision del paso 14.
    assert set(carpetas) == {"app", "lib", "windows", "raiz", "runtime/lector", "datos",
                             "buzon"}
    assert carpetas["raiz"] == instalacion.raiz
    bien = {"datos", "buzon"}
    vistas = aislamiento.observar("orden", sondas=(), carpetas=carpetas,
                                  escribir=lambda c: c.name in bien)
    assert all(c.bien for c in aislamiento.evaluar("orden", vistas, ()))
    # Un programa que se puede cambiar (un DLL junto a python.exe se cargaria al arrancar).
    vistas = aislamiento.observar("orden", sondas=(), carpetas=carpetas,
                                  escribir=lambda c: c.name in bien | {"lector"})
    juicio = aislamiento.evaluar("orden", vistas, ())
    assert [c.nombre for c in juicio if c.grave and not c.bien] == ["escribir en runtime/lector"]
    # Una raiz o unos scripts que se pueden cambiar: se podria borrar instalacion.json, o
    # cambiar lo que arranca la salida.
    for carpeta, nombre in (("BMS", "raiz"), ("windows", "windows")):
        vistas = aislamiento.observar("orden", sondas=(), carpetas=carpetas,
                                      escribir=lambda c, x=carpeta: c.name in bien | {x})
        juicio = aislamiento.evaluar("orden", vistas, ())
        assert [c.nombre for c in juicio if c.grave and not c.bien] == [f"escribir en {nombre}"]
    # Unos datos que no se pueden escribir no son una fuga: un aviso.
    vistas = aislamiento.observar("orden", sondas=(), carpetas=carpetas, escribir=lambda c: False)
    juicio = aislamiento.evaluar("orden", vistas, ())
    assert all(c.bien or not c.grave for c in juicio)
    assert aislamiento.se_puede_escribir(tmp_path) is True
    assert aislamiento.se_puede_escribir(tmp_path / "no-existe") is False
    assert list(tmp_path.iterdir()) == [tmp_path / "BMS"]


def test_un_papel_que_no_existe_no_se_juzga() -> None:
    with pytest.raises(ValueError):
        aislamiento.evaluar("navegador", aislamiento.Observaciones())


def test_la_lista_fija_de_destinos_es_la_documentada() -> None:
    assert [(s.host, s.puerto, s.protocolo) for s in aislamiento.EXTERNOS] == [
        ("1.1.1.1", 443, "tcp"), ("8.8.8.8", 53, "tcp"), ("8.8.8.8", 53, "udp-dns"),
        ("1.1.1.1", 80, "tcp"), ("api.anthropic.com", 443, "tcp")]
    assert aislamiento.API == "api.anthropic.com:443"
    assert set(aislamiento.ROLES) == {"consola", "lector", "salida", "orden"}


# ============================================================ el fichero de resultados

def _entrada(rol: str, *, correcto: bool = True, fecha: datetime = AHORA,
             sesion: str | None = None) -> dict:
    return {"rol": rol, "fecha": fecha.isoformat(), "correcto": correcto, "sesion": sesion,
            "comprobaciones": [{"nombre": "directo a 1.1.1.1:443 (TCP)", "bien": correcto,
                                "grave": True, "esperado": "bloqueado", "obtenido": "x"}]}


def _datos(**entradas) -> dict:
    return {"version": 1, "roles": entradas}


def test_guardar_junta_los_papeles_y_aguanta_un_fichero_roto(tmp_path) -> None:
    ruta = tmp_path / aislamiento.FICHERO
    ruta.write_text("esto no es json", encoding="utf-8")
    assert aislamiento.leer(ruta) == {"version": 1, "roles": {}}
    for rol in ("consola", "orden"):
        aislamiento.guardar(ruta, aislamiento.Informe(rol, AHORA.isoformat(), ()))
    assert set(aislamiento.leer(ruta)["roles"]) == {"consola", "orden"}
    # Un papel sin pruebas apuntado no cuenta como bien.
    assert aislamiento.problemas_de(aislamiento.leer(ruta), AHORA)[0] == "consola: FALLA (sin detalle)"
    assert sorted(p.name for p in tmp_path.iterdir()) == [aislamiento.FICHERO]


def test_la_banda_dice_lo_que_falta_lo_que_falla_y_lo_viejo() -> None:
    todo = {r: _entrada(r) for r in aislamiento.ROLES}
    assert aislamiento.problemas_de(_datos(**todo), AHORA) == []
    assert aislamiento.problemas_de({}, AHORA) == [f"{r}: sin comprobar" for r in aislamiento.ROLES]
    falla = dict(todo, lector=_entrada("lector", correcto=False))
    assert aislamiento.problemas_de(_datos(**falla), AHORA) == [
        "lector: FALLA (directo a 1.1.1.1:443 (TCP))"]
    # Lo que dice "correcto" no basta si una prueba grave lo contradice.
    mentira = dict(todo, orden=dict(_entrada("orden", correcto=False), correcto=True))
    assert aislamiento.problemas_de(_datos(**mentira), AHORA)[0].startswith("orden: FALLA")
    vieja = dict(todo, salida=_entrada("salida", fecha=AHORA - timedelta(days=91)))
    assert aislamiento.problemas_de(_datos(**vieja), AHORA) == [
        "salida: comprobado por ultima vez hace 91 dias"]
    futura = dict(todo, consola=_entrada("consola", fecha=AHORA + timedelta(days=2)))
    assert aislamiento.problemas_de(_datos(**futura), AHORA) == [
        "consola: la fecha de la comprobacion no vale"]


def test_una_lectura_solo_con_la_comprobacion_de_esta_pasada() -> None:
    sesion = nativo.huella_sesion(CREDENCIAL)
    bien = {"salida": _entrada("salida", sesion=sesion), "lector": _entrada("lector", sesion=sesion)}
    motivo = aislamiento.motivo_para_no_leer_de
    assert motivo(_datos(**bien), sesion, AHORA) is None
    assert "falta la comprobacion de aislamiento de la salida" in motivo(
        _datos(lector=bien["lector"]), sesion, AHORA)
    assert "del lector ha fallado" in motivo(
        _datos(**dict(bien, lector=_entrada("lector", correcto=False, sesion=sesion))),
        sesion, AHORA)
    assert "no es de esta pasada" in motivo(_datos(**bien), nativo.huella_sesion("otra" * 8),
                                            AHORA)
    assert "hace mas de 60 minutos" in motivo(_datos(**bien), sesion,
                                              AHORA + timedelta(minutes=61))
    assert motivo(_datos(**bien), sesion, AHORA + timedelta(minutes=59)) is None


# ============================================================ falla cerrada: la puerta de la API

def _comprobacion_buena(instalacion: nativo.Instalacion, credencial: str = CREDENCIAL) -> None:
    sesion = nativo.huella_sesion(credencial)
    ahora = datetime.now(timezone.utc)
    for rol in ("salida", "lector"):
        aislamiento.guardar(instalacion.resultado_aislamiento, aislamiento.Informe(
            rol, ahora.isoformat(timespec="seconds"),
            (aislamiento.Comprobacion("x", "bloqueado", "no conecta", True),), sesion))


def _proxy_url(credencial: str = CREDENCIAL, puerto: int = 3128) -> str:
    return f"http://bms:{credencial}@127.0.0.1:{puerto}"


def test_la_puerta_solo_deja_al_lector_de_una_pasada_comprobada(tmp_path) -> None:
    lector = _instalacion(tmp_path / "BMS", "lector")
    entorno = {"HTTPS_PROXY": _proxy_url()}
    for rol in ("consola", "orden", "salida"):
        with pytest.raises(nativo.LecturaNoAislada, match="lo hace el lector"):
            nativo.exigir_lectura(_instalacion(tmp_path / "BMS", rol), entorno)
    with pytest.raises(nativo.LecturaNoAislada, match="falta la comprobacion"):
        nativo.exigir_lectura(lector, entorno)
    _comprobacion_buena(lector)
    nativo.exigir_lectura(lector, entorno)
    for malo, que in ((None, "falta HTTPS_PROXY"), ("http://127.0.0.1:3128", "credencial"),
                      (_proxy_url(puerto=3129), "puerto"),
                      (f"http://bms:{CREDENCIAL}@10.0.0.5:3128", "proxy de la salida"),
                      (f"https://bms:{CREDENCIAL}@127.0.0.1:3128", "proxy de la salida"),
                      (f"http://otro:{CREDENCIAL}@127.0.0.1:3128", "credencial"),
                      (_proxy_url("otra-credencial-de-otra-pasada"), "no es de esta pasada")):
        with pytest.raises(nativo.LecturaNoAislada, match=que) as error:
            nativo.exigir_lectura(lector, {} if malo is None else {"HTTPS_PROXY": malo})
        assert CREDENCIAL not in str(error.value)


def test_sin_la_comprobacion_ninguna_orden_que_paga_crea_el_cliente(tmp_path, monkeypatch, como,
                                                                    pdfs_ejemplo, capsys,
                                                                    protector) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: pytest.fail("no se crea"))
    lector = como("lector")
    secretos.guardar_clave(CLAVE, lector.fichero_clave)
    monkeypatch.setenv("HTTPS_PROXY", _proxy_url())
    for orden in (["coste", "--estimar", str(pdfs_ejemplo), "--out", str(tmp_path / "out")],
                  ["extract", str(pdfs_ejemplo), "--out", str(tmp_path / "out")]):
        assert main(orden) == 2, orden
        assert "no se lee nada ni se paga nada" in capsys.readouterr().err
    # Una comprobacion que falla tampoco vale.
    aislamiento.guardar(lector.resultado_aislamiento, aislamiento.Informe(
        "lector", datetime.now(timezone.utc).isoformat(),
        (aislamiento.Comprobacion("directo a 1.1.1.1:443 (TCP)", "bloqueado", "conecta", False),),
        nativo.huella_sesion(CREDENCIAL)))
    assert main(["coste", "--estimar", str(pdfs_ejemplo)]) == 2
    # Y otro papel no habla con la API aunque todo este bien.
    como("consola")
    assert main(["coste", "--estimar", str(pdfs_ejemplo)]) == 2
    assert "lo hace el lector" in capsys.readouterr().err


def test_la_pasada_entera_comprobada_llega_a_la_api_con_la_clave_cifrada(
        tmp_path, monkeypatch, como, pdfs_ejemplo, capsys, protector) -> None:
    """Como leer-facturas: la salida con su credencial, la comprobacion de la salida y del
    lector (con los destinos de internet de mentira, locales), y solo entonces la API."""
    import anthropic

    class Llego(Exception):
        pass

    def cliente(*_a, api_key=None, **_k):
        raise Llego(api_key)

    monkeypatch.setattr(anthropic, "Anthropic", cliente)
    monkeypatch.setattr(aislamiento, "EXTERNOS", _sondas())
    # Aqui todo se puede escribir (no hay ACL de Windows): el codigo hace como si no.
    monkeypatch.setattr(aislamiento, "se_puede_escribir", lambda c: c.name in ("datos", "buzon"))
    out = str(tmp_path / "out")
    with _proxy() as (_host, puerto):
        como("salida", puerto)
        monkeypatch.setenv(salida.VARIABLE_CLAVE, CREDENCIAL)
        assert main(["comprobar-aislamiento", "--rol", "salida", "--espera", "1"]) == 0
        monkeypatch.delenv(salida.VARIABLE_CLAVE)
        lector = como("lector", puerto)
        secretos.guardar_clave(CLAVE, lector.fichero_clave)
        monkeypatch.setenv("HTTPS_PROXY", _proxy_url(puerto=puerto))
        assert main(["comprobar-aislamiento", "--rol", "lector", "--espera", "1"]) == 0
    assert "Aislamiento del lector: BIEN" in capsys.readouterr().out
    with pytest.raises(Llego) as llegada:
        main(["coste", "--estimar", str(pdfs_ejemplo), "--out", out])
    assert llegada.value.args == (CLAVE,)
    # La credencial de otra pasada ya no vale, aunque la comprobacion sea de hace un momento.
    monkeypatch.setenv("HTTPS_PROXY", _proxy_url("otra" * 16, puerto))
    assert main(["coste", "--estimar", str(pdfs_ejemplo), "--out", out]) == 2
    guardado = lector.resultado_aislamiento.read_text(encoding="utf-8")
    assert CREDENCIAL not in guardado and nativo.huella_sesion(CREDENCIAL) in guardado


def test_cada_papel_se_comprueba_con_su_propio_programa(como, capsys) -> None:
    como("consola")
    assert main(["comprobar-aislamiento", "--rol", "lector"]) == 2
    assert "el cortafuegos distingue los programas por su ruta" in capsys.readouterr().err


def test_el_lector_sin_el_proxy_de_la_pasada_no_se_comprueba(como, monkeypatch, capsys) -> None:
    como("lector")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    assert main(["comprobar-aislamiento", "--rol", "lector"]) == 2
    assert "falta HTTPS_PROXY" in capsys.readouterr().err


def test_un_instalacion_json_roto_no_se_toma_por_ninguno(tmp_path, capsys) -> None:
    raiz = tmp_path / "BMS"
    _instalacion(raiz, "orden")
    (raiz / nativo.FICHERO_INSTALACION).write_text("{roto", encoding="utf-8")
    with pytest.raises(nativo.InstalacionNoValida):
        nativo.detectar(raiz / "runtime" / "orden" / "python.exe")
    (raiz / nativo.FICHERO_INSTALACION).write_text('{"version": 7}', encoding="utf-8")
    with pytest.raises(nativo.InstalacionNoValida):
        nativo.detectar(raiz / "runtime" / "orden" / "python.exe")
    # Fuera de runtime\<papel> no hay instalacion: el desarrollo, Docker y los tests.
    assert nativo.detectar(raiz / "otra" / "python.exe") is None
    # Sin instalacion.json y sin el ._pth de la instalacion, tampoco.
    (raiz / nativo.FICHERO_INSTALACION).unlink()
    assert nativo.detectar(raiz / "runtime" / "orden" / "python.exe") is None
    assert nativo.detectar(sys.executable) is None
    assert nativo.instalacion_actual() is None


def test_un_interprete_de_la_instalacion_sin_instalacion_json_no_apaga_las_puertas(
        tmp_path, monkeypatch, pdfs_ejemplo, capsys) -> None:
    """Revision del paso 14: sin instalacion.json, detectar decia "no hay instalacion" tambien
    para runtime\\lector\\python.exe, y la puerta de la API, la clave solo cifrada y la consola
    sin lectura se apagaban. Con el ._pth de la instalacion al lado, es un error."""
    raiz = tmp_path / "BMS"
    lector = raiz / "runtime" / "lector"
    lector.mkdir(parents=True)
    (lector / "python.exe").write_bytes(b"")
    (lector / nativo.FICHERO_PTH).write_text(nativo.contenido_pth(), encoding="ascii")
    with pytest.raises(nativo.InstalacionNoValida, match="falta .*instalacion.json"):
        nativo.detectar(lector / "python.exe")
    assert nativo.FICHERO_PTH == "python313._pth" and nativo.RUTAS_PTH[0] == "Lib"
    # Paso 14b: el ._pth de otra version (el de una instalacion de antes de cambiar de Python)
    # tampoco apaga las puertas.
    (lector / nativo.FICHERO_PTH).unlink()
    assert nativo.detectar(lector / "python.exe") is None
    (lector / "python311._pth").write_text("python311.zip\r\n.\r\n", encoding="ascii")
    with pytest.raises(nativo.InstalacionNoValida, match="falta .*instalacion.json"):
        nativo.detectar(lector / "python.exe")
    # La CLI de ese programa no sigue: ni paga, ni abre la consola como si fuera la de siempre.
    monkeypatch.setattr(sys, "executable", str(lector / "python.exe"))
    for orden in (["coste", "--estimar", str(pdfs_ejemplo)], ["serve", "--puerto", "0"]):
        assert main(orden) == 2, orden
        assert "falta" in capsys.readouterr().err


# ============================================================ la consola

def _pedir(puerto: int, ruta: str) -> tuple[int, str]:
    import http.client

    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)
    conexion.request("GET", ruta, headers={"Host": f"127.0.0.1:{puerto}"})
    respuesta = conexion.getresponse()
    return respuesta.status, respuesta.read().decode("utf-8")


@contextmanager
def _consola(tmp_path, aislamiento_=None, ruta_db=None):
    servidor = crear_servidor(tmp_path / "pdf", tmp_path / "out", 0,
                              ruta_db=ruta_db or tmp_path / "datos" / "bms.sqlite3",
                              lectura=False, aislamiento=aislamiento_)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield servidor.server_address[1]
    finally:
        servidor.shutdown()
        servidor.server_close()


def test_la_consola_pinta_la_banda_roja_si_el_aislamiento_falla_o_falta(tmp_path) -> None:
    problemas = ["lector: sin comprobar", "<script>alert(1)</script>"]
    with _consola(tmp_path, lambda: problemas) as puerto:
        estado, pagina = _pedir(puerto, "/consola")
        _e, local = _pedir(puerto, "/")
        _e, estilo = _pedir(puerto, "/consola.css")
    assert estado == 200
    assert re.search(r'<body>\s*<div id="aislamiento" class="aislamiento-falla" role="alert">'
                     r'AISLAMIENTO SIN COMPROBAR O CON FALLOS: lector: sin comprobar', pagina)
    assert "<title>SIN AISLAMIENTO" in pagina and "comprobar.bat" in pagina
    # El texto viene de un fichero que se puede escribir: va escapado.
    assert "<script>alert(1)</script>" not in pagina and "&lt;script&gt;" in pagina
    assert "AISLAMIENTO SIN COMPROBAR" in local and "<script>alert" not in local
    assert ".aislamiento-falla{" in estilo


def test_sin_problemas_o_fuera_de_la_instalacion_no_hay_banda(tmp_path) -> None:
    for problemas in (lambda: [], None):
        with _consola(tmp_path, problemas) as puerto:
            _e, pagina = _pedir(puerto, "/consola")
        assert 'id="aislamiento"' not in pagina and "SIN AISLAMIENTO" not in pagina


def test_con_datos_de_prueba_la_banda_de_prueba_va_primero() -> None:
    _tipo, datos = consola.fichero("/consola", demo=True, aislamiento=["orden: sin comprobar"])
    texto = datos.decode("utf-8")
    assert re.search(r'<body>\s*<div id="datos-de-prueba"[^>]*>DATOS DE PRUEBA[^<]*</div>\s*'
                     r'<div id="aislamiento"', texto)
    assert "<title>DATOS DE PRUEBA · SIN AISLAMIENTO" in texto


def test_la_consola_de_la_instalacion_no_lee_pdf_y_lleva_la_banda(tmp_path, como,
                                                                  monkeypatch) -> None:
    from bms_agent import serve

    llamadas = {}
    monkeypatch.setattr(serve, "servir", lambda **k: llamadas.update(k))
    consola_ = como("consola")
    assert main(["serve", "--puerto", "0"]) == 0
    assert llamadas["lectura"] is False and llamadas["contenedor"] is False
    assert llamadas["aislamiento"]() == [f"{r}: sin comprobar" for r in aislamiento.ROLES]
    for rol in aislamiento.ROLES:
        aislamiento.guardar(consola_.resultado_aislamiento, aislamiento.Informe(
            rol, datetime.now(timezone.utc).isoformat(),
            (aislamiento.Comprobacion("x", "bloqueado", "no conecta", True),)))
    assert llamadas["aislamiento"]() == []
    # Con otro programa, la consola no se abre.
    como("lector")
    assert main(["serve", "--puerto", "0"]) == 2
    # Fuera de la instalacion, como siempre.
    como(None)
    llamadas.clear()
    assert main(["serve", "--puerto", "0"]) == 0
    assert llamadas["lectura"] is None and llamadas["aislamiento"] is None


# ============================================================ la credencial de la salida

def _basic(texto: str) -> bytes:
    return base64.b64encode(texto.encode()).decode().encode()


@pytest.mark.parametrize("cabecera, vale", [
    (b"CONNECT a:443 HTTP/1.1\r\nProxy-Authorization: Basic " + _basic(f"bms:{CREDENCIAL}"), True),
    (b"CONNECT a:443 HTTP/1.1\r\nproxy-authorization:   basic " + _basic(f"bms:{CREDENCIAL}"),
     True),
    (b"CONNECT a:443 HTTP/1.1\r\nHost: a\r\n", False),
    (b"CONNECT a:443 HTTP/1.1\r\nProxy-Authorization: Basic " + _basic("bms:otra"), False),
    (b"CONNECT a:443 HTTP/1.1\r\nProxy-Authorization: Basic " + _basic(f"ana:{CREDENCIAL}"),
     False),
    (b"CONNECT a:443 HTTP/1.1\r\nProxy-Authorization: Bearer " + CREDENCIAL.encode(), False),
    (b"CONNECT a:443 HTTP/1.1\r\nProxy-Authorization: Basic no-es-base64!", False),
    # En la primera linea no cuenta.
    (b"Proxy-Authorization: Basic " + _basic(f"bms:{CREDENCIAL}"), False),
])
def test_credencial_valida_es_pura(cabecera, vale) -> None:
    assert salida.credencial_valida(cabecera, CREDENCIAL) is vale


def test_sin_la_credencial_el_proxy_contesta_407_y_lo_apunta_sin_ella(caplog) -> None:
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    with _proxy() as proxy:
        assert aislamiento.pedir_tunel(proxy, aislamiento.API, None, 2) == 407
        assert aislamiento.pedir_tunel(proxy, aislamiento.API, "otra" * 8, 2) == 407
        assert aislamiento.pedir_tunel(proxy, aislamiento.API, CREDENCIAL, 2) == 200
        with socket.create_connection(proxy, 2) as conexion:
            conexion.sendall(b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n")
            respuesta = conexion.recv(4096)
    assert b'Proxy-Authenticate: Basic realm="bms"' in respuesta
    registro = "\n".join(r.getMessage() for r in caplog.records)
    assert "codigo=407" in registro and "sin la credencial de esta pasada" in registro
    assert CREDENCIAL not in registro and _basic(f"bms:{CREDENCIAL}").decode() not in registro


def test_el_cliente_http_del_sdk_manda_la_credencial_de_https_proxy(monkeypatch, caplog) -> None:
    """El lector no hace nada especial: el cliente del SDK lee HTTPS_PROXY y manda la
    credencial que lleva dentro. Con otra, el proxy no le deja pasar."""
    import httpx2

    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    for variable in ("https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY", "no_proxy",
                     "NO_PROXY"):
        monkeypatch.delenv(variable, raising=False)
    with _proxy() as (host, puerto):
        for credencial, pasa in ((CREDENCIAL, True), ("otra" * 8, False)):
            caplog.clear()
            monkeypatch.setenv("HTTPS_PROXY", f"http://bms:{credencial}@{host}:{puerto}")
            with httpx2.Client(timeout=3) as cliente, pytest.raises(Exception) as error:
                cliente.get("https://api.anthropic.com/v1/models")
            registro = "\n".join(r.getMessage() for r in caplog.records)
            assert ("decision=permitida" in registro) is pasa, (credencial, registro)
            if not pasa:
                assert "407" in str(error.value) or "codigo=407" in registro


def test_el_sdk_de_la_api_manda_la_credencial_de_https_proxy(monkeypatch, caplog) -> None:
    """Revision del paso 14: lo mismo, pero con el cliente que usa el lector de verdad
    (anthropic.Anthropic), que monta sus propios proxies y su propio transporte. Con la
    credencial pasa (y el TLS falla contra el eco local); con otra, 407."""
    import anthropic

    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    for variable in ("https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY", "no_proxy",
                     "NO_PROXY", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(variable, raising=False)
    with _proxy() as (host, puerto):
        for credencial, pasa in ((CREDENCIAL, True), ("otra" * 8, False)):
            caplog.clear()
            monkeypatch.setenv("HTTPS_PROXY", f"http://bms:{credencial}@{host}:{puerto}")
            cliente = anthropic.Anthropic(api_key="sk-ant-x", max_retries=0, timeout=3)
            with pytest.raises(anthropic.APIConnectionError):
                cliente.models.list()
            registro = "\n".join(r.getMessage() for r in caplog.records)
            assert ("decision=permitida" in registro) is pasa, (credencial, registro)
            assert ("codigo=407" in registro) is not pasa, (credencial, registro)
            assert "api.anthropic.com:443" in registro
            cliente.close()


def test_la_salida_se_para_sola_al_cumplir_su_vida(monkeypatch) -> None:
    """Revision del paso 14: si se cierra la ventana de leer-facturas con la X, PowerShell
    muere sin parar la salida. Con --max-segundos se para sola."""
    import time

    monkeypatch.setenv(salida.VARIABLE_CLAVE, CREDENCIAL)
    resultado = {}
    hilo = threading.Thread(target=lambda: resultado.setdefault("codigo", main(
        ["salida", "--escuchar", "127.0.0.1:0", "--clave-del-entorno", "--max-segundos",
         "0.5"])), daemon=True)
    inicio = time.monotonic()
    hilo.start()
    hilo.join(10)
    assert not hilo.is_alive() and resultado == {"codigo": 0}
    assert time.monotonic() - inicio < 5
    with pytest.raises(ValueError):
        salida.servir("127.0.0.1:0", vida=0)
    assert main(["salida", "--escuchar", "127.0.0.1:0", "--max-segundos", "-1"]) == 2


def test_la_salida_con_credencial_la_exige_en_el_entorno(monkeypatch, capsys) -> None:
    monkeypatch.delenv(salida.VARIABLE_CLAVE, raising=False)
    assert main(["salida", "--escuchar", "127.0.0.1:0", "--clave-del-entorno"]) == 2
    monkeypatch.setenv(salida.VARIABLE_CLAVE, "corta")
    assert main(["salida", "--escuchar", "127.0.0.1:0", "--clave-del-entorno"]) == 2
    assert "falta la credencial de la pasada" in capsys.readouterr().err
    with pytest.raises(ValueError):
        salida.Proxy(("127.0.0.1", 0), salida.lista_blanca(["api.anthropic.com:443"]),
                     clave="corta")


# ============================================================ nadie lanza procesos

# Lo que lanza un proceso. Un modulo que lo necesitara iria en PUEDEN_LANZAR, con su porque.
MODULOS_PROHIBIDOS = {"subprocess", "multiprocessing", "pty", "webbrowser", "_winapi",
                      "_posixsubprocess", "pexpect", "sh", "plumbum"}
LLAMADAS_PROHIBIDAS = re.compile(
    r"^(system|popen|startfile|fork|forkpty|posix_spawnp?|exec[lv]p?e?|spawn[lv]p?e?|"
    r"create_subprocess_(exec|shell)|ProcessPoolExecutor)$")
NOMBRES_DE_WINDOWS = re.compile(r"ShellExecute|CreateProcess|WinExec|CreateRemoteThread|"
                                r"NtCreate(User)?Process|RtlCreateUserProcess", re.IGNORECASE)
PUEDEN_LANZAR: dict[str, str] = {}
# Solo secretos.py usa ctypes, y solo para crypt32 (DPAPI) y LocalFree.
PUEDEN_USAR_CTYPES = {"secretos.py"}


def lanzamientos(codigo: str) -> list[str]:
    """Lo que en un modulo podria lanzar otro proceso (por el AST)."""
    encontrados = []
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            encontrados += [a.name for a in nodo.names
                            if a.name.split(".")[0] in MODULOS_PROHIBIDOS]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            raiz = nodo.module.split(".")[0]
            if raiz in MODULOS_PROHIBIDOS:
                encontrados.append(nodo.module)
            encontrados += [f"{nodo.module}.{a.name}" for a in nodo.names
                            if LLAMADAS_PROHIBIDAS.match(a.name)]
        elif isinstance(nodo, ast.Attribute) and LLAMADAS_PROHIBIDAS.match(nodo.attr):
            encontrados.append(ast.unparse(nodo))
        elif isinstance(nodo, ast.Name) and LLAMADAS_PROHIBIDAS.match(nodo.id):
            encontrados.append(nodo.id)
        elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if nodo.value.split(".")[0] in MODULOS_PROHIBIDOS or \
                    NOMBRES_DE_WINDOWS.search(nodo.value):
                encontrados.append(repr(nodo.value))
        if isinstance(nodo, ast.Attribute) and NOMBRES_DE_WINDOWS.search(nodo.attr):
            encontrados.append(ast.unparse(nodo))
    return encontrados


def _usa_ctypes(codigo: str) -> bool:
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import) and any(a.name.split(".")[0] == "ctypes"
                                                for a in nodo.names):
            return True
        if isinstance(nodo, ast.ImportFrom) and (nodo.module or "").split(".")[0] == "ctypes":
            return True
    return False


def test_ningun_modulo_lanza_procesos() -> None:
    """El hueco de las reglas por programa: un proceso que arrancara otro programa (uno sin
    reglas) saldria a internet. Ningun modulo de bms_agent lanza nada: ni subprocess, ni
    os.system u os.popen, ni os.exec* u os.spawn*, ni os.startfile, ni multiprocessing, ni
    ShellExecute o CreateProcess por ctypes, ni el navegador."""
    malos = {}
    # Los nombres de los sucesos de auditoria que nativo prohibe no son llamadas.
    sucesos = {repr(s) for s in nativo.SUCESOS_DE_PROCESO}
    for ruta in sorted(SRC.rglob("*.py")):
        codigo = ruta.read_text(encoding="utf-8")
        nombre = str(ruta.relative_to(SRC))
        encontrados = lanzamientos(codigo)
        if nombre == "nativo.py":
            encontrados = [e for e in encontrados if e not in sucesos]
        if encontrados and nombre not in PUEDEN_LANZAR:
            malos[nombre] = encontrados
        if _usa_ctypes(codigo) and nombre not in PUEDEN_USAR_CTYPES:
            malos.setdefault(nombre, []).append("ctypes")
    assert malos == {}
    texto = (SRC / "secretos.py").read_text(encoding="utf-8")
    assert set(re.findall(r'WinDLL\("(\w+)"', texto)) == {"crypt32", "kernel32"}
    assert set(re.findall(r"(?:crypt32|kernel32)\.(\w+)", texto)) == {
        "CryptProtectData", "CryptUnprotectData", "LocalFree"}


GANCHO = r'''
import os, platform, subprocess, sys
sys.path.insert(0, sys.argv[1])
from bms_agent import nativo
if sys.argv[2] == "si":
    nativo.prohibir_procesos()
    for intento in (lambda: subprocess.run(["true"]), lambda: os.system("true")):
        try:
            intento()
        except PermissionError as exc:
            assert "no arranca otros programas" in str(exc)
        else:
            raise SystemExit("ha lanzado un proceso")
# Lo que hace platform en Windows (y por el, el SDK de la API) si WMI no contesta, y con
# Python 3.11 siempre: `ver`.
sys.platform = "win32"
print(platform._syscmd_ver("s", "r", "v"))
'''


@pytest.mark.skipif(sys.platform == "win32", reason="el `ver` de mentira es un script de sh")
@pytest.mark.parametrize("gancho", [False, True])
def test_en_la_instalacion_ni_las_dependencias_arrancan_programas(tmp_path, gancho) -> None:
    """Revision del paso 14: el SDK llama a platform.system(), que en Windows ejecuta `ver`
    con cmd.exe, un programa sin reglas. Con el gancho de nativo (que main pone en la
    instalacion), platform no arranca nada y sigue con lo que sabe. Se prueba en otro proceso:
    un gancho de auditoria no se quita."""
    marca = tmp_path / "ver-ha-corrido"
    carpeta = tmp_path / "bin"
    carpeta.mkdir()
    ver = carpeta / "ver"
    ver.write_text(f"#!/bin/sh\ntouch '{marca}'\necho 'Microsoft Windows [Version 10.0.1.2]'\n",
                   encoding="ascii")
    ver.chmod(0o755)
    entorno = dict(os.environ, PATH=f"{carpeta}{os.pathsep}{os.environ.get('PATH', '')}")
    proceso = subprocess.run([sys.executable, "-c", GANCHO, str(SRC.parent),
                              "si" if gancho else "no"], capture_output=True, text=True,
                             env=entorno, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    assert marca.exists() is not gancho
    if gancho:
        assert proceso.stdout.strip() == "('s', 'r', 'v')"
    # En este proceso (los tests) no hay instalacion: el gancho no se pone.
    nativo.prohibir_procesos_si_nativa()
    assert nativo._prohibidos is False


def test_el_gancho_conoce_cada_forma_de_lanzar_de_python() -> None:
    assert {"subprocess.Popen", "os.system", "os.startfile", "os.exec", "os.spawn",
            "os.posix_spawn", "_winapi.CreateProcess"} <= nativo.SUCESOS_DE_PROCESO
    with pytest.raises(PermissionError):
        nativo._sin_procesos("subprocess.Popen", ("cmd.exe", "ver", None, None))
    assert nativo._sin_procesos("open", ("x", "r", 0)) is None


@pytest.mark.parametrize("codigo", [
    "import subprocess", "from subprocess import run", "import multiprocessing.pool",
    "import os\nos.system('x')", "import os\nos.popen('x')", "os.execv('a', [])",
    "os.spawnl(0, 'a')", "os.startfile('a')", "from os import system", "from os import execvp",
    "import webbrowser", "__import__('subprocess')", "importlib.import_module('subprocess')",
    "asyncio.create_subprocess_exec('x')", "from concurrent.futures import ProcessPoolExecutor",
    "ctypes.windll.shell32.ShellExecuteW(None)", "k.CreateProcessW", "getattr(k, 'WinExec')",
    "os.posix_spawn('a', [], {})", "os.fork()",
])
def test_el_vigilante_ve_cada_forma_de_lanzar(codigo) -> None:
    assert lanzamientos(codigo), codigo


def test_el_vigilante_no_ve_lo_que_no_lanza() -> None:
    assert lanzamientos("import os\nos.replace('a', 'b')\nos.environ.get('X')\n"
                        "from concurrent.futures import ThreadPoolExecutor\n"
                        "import socket, ctypes\nctypes.WinDLL('crypt32').CryptProtectData") == []


# ============================================================ los scripts de windows/

SCRIPTS = ("instalar", "desinstalar", "iniciar", "parar", "leer-facturas", "importar", "copia",
           "restaurar", "comprobar", "persona", "empresa", "orden", "ver-salida", "clave")


def _ps1(nombre: str) -> str:
    return (WINDOWS / f"{nombre}.ps1").read_text(encoding="utf-8")


def _codigo(texto: str) -> str:
    """El script sin sus comentarios ni lo que va entre comillas: lo que de verdad se ejecuta."""
    sin_cadenas = re.sub(r'"(?:[^"`]|`.)*"|\'[^\']*\'', '""', texto)
    return "\n".join(linea.split("#", 1)[0] for linea in sin_cadenas.splitlines())


@pytest.mark.parametrize("nombre", SCRIPTS)
def test_cada_script_tiene_su_bat_y_habla_claro(nombre) -> None:
    ps1 = _ps1(nombre)
    bat = (WINDOWS / f"{nombre}.bat").read_text(encoding="utf-8")
    assert f'-File "%~dp0{nombre}.ps1" %*' in bat and "-ExecutionPolicy Bypass" in bat
    assert bat.startswith("@echo off") and "powershell -NoProfile" in bat
    assert '. "$PSScriptRoot\\comun.ps1"' in ps1
    # Windows PowerShell lee un .ps1 sin BOM como ANSI: nada fuera del ASCII.
    assert ps1.isascii() and bat.isascii()
    # Ninguna clave dentro (decir que empieza por sk- si se puede).
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{6,}", ps1)
    assert "Escribir" in ps1 or "Fallar" in ps1
    assert "paso 14" in ps1.splitlines()[0] + ps1.splitlines()[1]


def test_ningun_script_usa_docker_ni_ejecuta_texto_ni_baja_sin_hash() -> None:
    todos = {p.name: p.read_text(encoding="utf-8") for p in WINDOWS.glob("*.ps1")}
    assert set(todos) == {f"{n}.ps1" for n in SCRIPTS} | {"comun.ps1"}
    for nombre, texto in todos.items():
        codigo = _codigo(texto)
        assert not re.search(r"\bdocker\b", codigo, re.IGNORECASE), nombre
        assert not re.search(r"Invoke-Expression|\biex\b|DownloadString|DownloadFile|"
                             r"Start-BitsTransfer|\bcurl\b|\bwget\b|Net\.WebClient|"
                             r"FromBase64String|-EncodedCommand|Set-ExecutionPolicy|"
                             r"SkipCertificateCheck|ServerCertificateValidationCallback",
                             codigo, re.IGNORECASE), nombre
        # Una descarga solo en el instalador, y solo en Descargar-Verificado.
        descargas = [m.start() for m in re.finditer(r"Invoke-WebRequest[^\n]*-OutFile", texto)]
        if nombre != "instalar.ps1":
            assert descargas == [], nombre
    instalar = todos["instalar.ps1"]
    funcion = instalar[instalar.index("function Descargar-Verificado"):]
    funcion = funcion[:funcion.index("\n}\n")]
    assert len(re.findall(r"Invoke-WebRequest", instalar)) == 1
    assert "Invoke-WebRequest" in funcion and "-OutFile $Destino" in funcion
    assert funcion.index("-OutFile") < funcion.index("Get-FileHash -Algorithm SHA256")
    assert "if ($real -ne $Sha256.ToLower())" in funcion and "Remove-Item" in funcion
    # Lo que se baja se usa despues de comprobarlo: el paquete del Python, y cada rueda.
    assert instalar.index("Descargar-Verificado $fijado.python.url") < instalar.index(
        "Abrir-Python $paquete $base") < instalar.index("Comprobar-Firma (Join-Path $base")
    assert instalar.index("Descargar-Verificado $rueda.Url") < instalar.index(
        "Expand-Archive -LiteralPath $comoZip")
    # Lo de PyPI solo dice donde esta el fichero: lo que decide es el hash fijado.
    assert "$Requisito.Hashes -contains $fichero.digests.sha256" in instalar
    assert "Comprobar-Firma (Join-Path $base $nombre) $fijado.python.firmante" in instalar
    assert 'foreach ($nombre in @("python.exe", $DllPython)) {' in instalar


def test_el_instalador_no_sigue_sin_los_hashes_fijados() -> None:
    instalar = _ps1("instalar")
    assert "$fijado.python.sha256 -notmatch '^[0-9a-f]{64}$'" in instalar
    assert '$sinHash = @($requisitos | Where-Object { $_.Hashes.Count -eq 0 }' in instalar
    # Paso 14b: el Python solo se baja de nuget.org.
    assert ("$fijado.python.url -notmatch '^https://api\\.nuget\\.org/v3-flatcontainer/python/'"
            in instalar)
    assert "python.org/ftp" not in instalar


def test_el_python_fijado_es_el_paquete_de_nuget_entero() -> None:
    """Paso 14b: fijado.json lleva el paquete "python" de nuget.org (de la Python Software
    Foundation), con el sha256 calculado de lo bajado y el SHA-512 que publica nuget.org de
    esa version (los dos cruzados por scripts/fijar_windows.py), y la version menor que
    espera el codigo (el nombre de la DLL y del ._pth)."""
    fijado = json.loads((WINDOWS / "fijado.json").read_text(encoding="utf-8"))["python"]
    version = fijado["version"]
    assert re.fullmatch(r"3\.13\.\d+", version)
    assert tuple(map(int, version.split(".")[:2])) == nativo.VERSION_PYTHON == (3, 13)
    assert fijado["origen"] == "nuget.org: python, Python Software Foundation"
    assert fijado["fichero"] == f"python.{version}.nupkg"
    assert fijado["url"] == (f"https://api.nuget.org/v3-flatcontainer/python/{version}/"
                             f"python.{version}.nupkg")
    assert re.fullmatch(r"[0-9a-f]{64}", fijado["sha256"])
    assert len(base64.b64decode(fijado["sha512"], validate=True)) == 64
    assert fijado["catalogo"].startswith("https://api.nuget.org/v3/catalog0/data/")
    assert fijado["catalogo"].endswith(f"/python.{version}.json")
    assert fijado["firmante"] == "Python Software Foundation"
    # Lo que se midio al fijarlo (paso 14b): el paquete 3.13.16, y su SHA-512 es el de nuget.org.
    assert (version, fijado["sha256"], fijado["sha512"]) == (
        "3.13.16", "95fad176338f1d6a799e45946488063f4aa61764e6cff2f132ddeffbf7a04c34",
        "TGEhuRTpWtRifDR4r/GEhmg/cGMqtwB4kOCkt1QhXnCmdDE3Dict3iLJI1xrsNSRbXGyCwLEhe6qa5Rd2s376w==")
    assert nativo.DLL_PYTHON == "python313.dll" and nativo.FICHERO_PTH == "python313._pth"


def test_las_dependencias_de_windows_son_las_de_docker_con_su_hash() -> None:
    sys.path.insert(0, str(RAIZ / "scripts"))
    try:
        import fijar_windows
    finally:
        sys.path.pop(0)
    windows = {r.nombre.lower().replace("_", "-"): r for r in fijar_windows.leer_requisitos(
        (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8"))}
    docker = {r.nombre.lower().replace("_", "-"): r for r in fijar_windows.leer_requisitos(
        (RAIZ / "docker" / "requirements.txt").read_text(encoding="utf-8"))}
    assert set(windows) == set(docker) | {"tzdata"}
    for nombre, requisito in docker.items():
        assert windows[nombre].version == requisito.version, nombre
    # Una rueda py3-none-any es el mismo fichero en cada plataforma: su hash es el de Docker.
    binarias = {"jiter", "pydantic-core", "pyyaml"}
    for nombre in set(docker) - binarias:
        assert windows[nombre].hashes and set(windows[nombre].hashes) <= set(docker[nombre].hashes)
    # Paso 14b: ninguna sin hash, cada una con el de una sola rueda (la cp313-win_amd64 en las
    # binarias, que no es ninguna de las de Linux de Docker).
    assert all(len(r.hashes) == 1 for r in windows.values()), windows
    for nombre in binarias:
        assert not set(windows[nombre].hashes) & set(docker[nombre].hashes), nombre


def test_cada_linea_de_requisitos_lleva_su_hash() -> None:
    """Paso 14b: nada PENDIENTE. Cada dependencia lleva su --hash=sha256 en las lineas que la
    siguen, como lo lee pip con --require-hashes, y el sha256 de cada rueda es el que publica
    PyPI para esa version (lo saca y lo comprueba fijar_windows.py)."""
    texto = (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8")
    assert "PENDIENTE" not in texto.upper()
    lineas = [l for l in texto.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    nombres = [l for l in lineas if not l[:1].isspace()]
    assert len(nombres) == 17
    for i, linea in enumerate(lineas):
        if linea[:1].isspace():
            assert re.fullmatch(r"    --hash=sha256:[0-9a-f]{64}( \\)?", linea), linea
        else:
            assert re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9.]+ \\", linea), linea
            assert lineas[i + 1].startswith("    --hash=sha256:"), linea
    assert {"jiter==0.17.0": "a3cebb1fe4a1abb00465f3f8a17e09112603e8b7c59e5c3adbcd9f7815a64acd",
            "pydantic_core==2.50.1":
                "7816e98acc08119dc0f340ab167048ecc54126316330c1f0caf7c6756c88e28f",
            "PyYAML==6.0.3": "79005a0d97d5ddabfeeea4cf676af11e647e41d81c9a7722a193022accdb6b7c",
            "tzdata==2025.2": "1a403fada01ff9221ca8044d701868fa132215d84beb92242d9acd2147f667a8",
            }.items() <= {l.split()[0]: lineas[i + 1].split(":")[1].split()[0]
                          for i, l in enumerate(lineas) if not l[:1].isspace()}.items()


# Las reglas que tiene que haber, por papel: (sentido, accion, protocolo, puertos).
REGLAS = {
    "consola": {("Outbound", "Block", "", ()), ("Inbound", "Block", "", ())},
    "lector": {("Outbound", "Block", "", ()), ("Inbound", "Block", "", ())},
    "orden": {("Outbound", "Block", "", ()), ("Inbound", "Block", "", ())},
    "salida": {("Inbound", "Block", "", ()), ("Outbound", "Allow", "TCP", ("443",)),
               ("Outbound", "Block", "TCP", ("1-442", "444-65535")),
               ("Outbound", "Block", "UDP", ()), ("Outbound", "Block", "ICMPv4", ()),
               ("Outbound", "Block", "ICMPv6", ())},
}


def _tabla_de_reglas() -> list[dict]:
    comun = _ps1("comun")
    filas = re.findall(r'@\{ Rol = "(\w+)"; Que = "([^"]+)"; Direccion = "(\w+)"; '
                       r'Accion = "(\w+)"; Protocolo = "(\w*)"; Puertos = @\(([^)]*)\) \}', comun)
    return [{"rol": r, "que": q, "direccion": d, "accion": a, "protocolo": p,
             "puertos": tuple(re.findall(r'"([^"]+)"', ps))} for r, q, d, a, p, ps in filas]


def test_las_reglas_del_cortafuegos_son_por_programa_con_su_prefijo() -> None:
    tabla = _tabla_de_reglas()
    assert len(tabla) == sum(len(v) for v in REGLAS.values())
    por_rol = {}
    for fila in tabla:
        por_rol.setdefault(fila["rol"], set()).add(
            (fila["direccion"], fila["accion"], fila["protocolo"], fila["puertos"]))
    assert por_rol == REGLAS
    # Un bloqueo gana siempre a un permiso en Windows: los puertos bloqueados de la salida no
    # pisan el 443, y entre los dos cubren todos.
    puertos = set()
    for desde, _guion, hasta in (p.partition("-") for p in ("1-442", "444-65535")):
        puertos |= set(range(int(desde), int(hasta or desde) + 1))
    assert 443 not in puertos and puertos | {443} == set(range(1, 65536))
    comun = _ps1("comun")
    assert '$Prefijo = "BMS Finanzas - "' in comun
    assert 'Nombre    = $Prefijo + $fila.Rol + " - " + $fila.Que' in comun
    assert 'Programa  = (Join-Path $Raiz ("runtime\\" + $fila.Rol + "\\python.exe"))' in comun
    assert len({f["rol"] + f["que"] for f in tabla}) == len(tabla)
    # Una sola forma de crearlas: con su nombre, grupo, sentido, accion, programa y perfil.
    instalar = _ps1("instalar")
    assert instalar.count("New-NetFirewallRule") == 1
    crear = instalar[instalar.index("function Crear-Reglas"):]
    crear = crear[:crear.index("\n}\n")]
    for campo in ("DisplayName = $regla.Nombre", "Direction   = $regla.Direccion",
                  "Action      = $regla.Accion", "Program     = $regla.Programa",
                  'Profile     = "Any"', "Group       = $Grupo"):
        assert campo in crear, campo
    assert crear.index("Quitar-Reglas") < crear.index("New-NetFirewallRule")
    assert sum(t.count("New-NetFirewallRule") for t in map(_ps1, SCRIPTS)) == 1


def test_el_desinstalador_quita_las_reglas_por_el_prefijo_y_deja_los_datos() -> None:
    comun = _ps1("comun")
    quitar = comun[comun.index("function Quitar-Reglas"):]
    quitar = quitar[:quitar.index("\n}\n")]
    assert 'Get-NetFirewallRule -DisplayName ($Prefijo + "*")' in quitar
    assert "Remove-NetFirewallRule" in quitar
    desinstalar = _ps1("desinstalar")
    assert "Quitar-Reglas" in desinstalar and "-Verb RunAs" in desinstalar
    # Los datos solo se borran si se escribe SI, en mayusculas.
    assert '$borrarDatos = ($borrar -ceq "SI")' in desinstalar
    assert desinstalar.index("if ($BorrarDatos)") < desinstalar.index('@("datos", "buzon")')
    assert desinstalar.count('"datos"') == 1
    for carpeta in ("runtime", "lib", "app", "windows"):
        assert f'"{carpeta}"' in desinstalar
    assert '($Prefijo + "*.lnk")' in desinstalar
    assert sum("Remove-NetFirewallRule" in _ps1(n) for n in SCRIPTS) == 0


def _de_la_instalacion() -> set[str]:
    instalar = _ps1("instalar")
    lista = re.search(r"\$DeLaInstalacion = @\(([^)]*)\)", instalar).group(1)
    return set(re.findall(r'"([^"]+)"', lista))


def test_se_puede_volver_a_instalar_donde_se_desinstalo_o_fallo() -> None:
    """Revision del paso 14: Validar-Raiz rechazaba toda carpeta sin instalacion.json que no
    estuviera vacia, y eso es justo lo que dejan desinstalar (con tus datos) y un intento que
    no acaba. Ahora acepta una carpeta con solo lo que deja bms-agent."""
    nuestros = _de_la_instalacion()
    instalar = _ps1("instalar")
    validar = _funcion(instalar, "Validar-Raiz")
    assert "$DeLaInstalacion -notcontains $_.Name" in validar
    assert "instalacion.json" in nuestros
    # Lo que crea el instalador en la raiz: todo es de la lista.
    creados = set(re.findall(r'Join-Path \$Raiz \(?"([a-z.]+)[\\"]', instalar))
    carpetas = re.search(r'foreach \(\$carpeta in @\(("datos"[^)]*)\)\)', instalar).group(1)
    creados |= {c.split("\\")[0] for c in re.findall(r'"([^"]+)"', carpetas)}
    assert {"descargas", "runtime", "lib", "app", "windows", "instalacion.json",
            "instalacion.log"} <= creados
    assert creados <= nuestros, creados - nuestros
    # Lo que deja desinstalar: lo que habia menos lo que borra.
    desinstalar = _ps1("desinstalar")
    borrados = set()
    for lista in re.findall(r"foreach \(\$\w+ in @\(([^)]*)\)\) \{\s*Remove-Item", desinstalar):
        borrados |= set(re.findall(r'"([^"]+)"', lista))
    assert {"runtime", "lib", "app", "windows", "descargas", "instalacion.json",
            "instalacion.log", "datos", "buzon"} <= borrados
    sin_borrar_datos = creados - (borrados - {"datos", "buzon"})
    assert sin_borrar_datos == {"datos", "buzon"} and sin_borrar_datos <= nuestros
    # Una carpeta con algo mas sigue sin valer, y un enlace tampoco.
    assert "ya existe y no es una instalacion de bms-agent" in validar
    assert validar.count("ReparsePoint") == 2


def test_sin_los_hashes_fijados_no_se_crea_la_carpeta() -> None:
    instalar = _ps1("instalar")
    elevado = instalar.index("if (-not $Elevado) {")
    for llamada in ("$null = Leer-Fijado", "$null = @(Leer-Requisitos)"):
        assert instalar.index(llamada) < elevado, llamada
    assert instalar.index("function Leer-Fijado") < instalar.index("$null = Leer-Fijado")
    assert instalar.index("New-Item -ItemType Directory -Force -Path $Raiz") > elevado


def test_la_raiz_se_cierra_antes_de_bajar_copiar_o_ejecutar_nada() -> None:
    """Revision del paso 14: bajo C:\\ la raiz nueva heredaba "modificar" para cada usuario
    hasta el ultimo paso, y el instalador comprobaba, copiaba y ejecutaba como administrador
    lo de una carpeta que cualquiera podia cambiar."""
    instalar = _ps1("instalar")
    principal = instalar[instalar.rindex("$bien = $false"):]
    orden = [principal.index(t) for t in ("try {", "New-Item -ItemType Directory -Force -Path $Raiz",
                                          "Cerrar-Raiz $Raiz $Usuario", "Start-Transcript",
                                          "Instalar $Raiz $Usuario")]
    # Todo dentro del try: un fallo al cerrar tambien se dice y espera a que lo leas.
    assert orden == sorted(orden)
    cerrar = _funcion(instalar, "Cerrar-Raiz")
    for trozo in ('Icacls @($Raiz, "/setowner", $administradores, "/T", "/C", "/Q")',
                  '$Raiz, "/inheritance:r", "/grant:r"', '("*" + $Sid + ":(OI)(CI)RX")',
                  '"/remove:g"', "ReparsePoint", '"/reset", "/T"',
                  '@("datos", "buzon") -notcontains $hijo.Name'):
        assert trozo in cerrar, trozo
    assert "(OI)(CI)M" not in cerrar
    # Lo que se baja va dentro de la raiz ya cerrada; nada en %TEMP%.
    assert '$descargas = Join-Path $Raiz "descargas"' in instalar
    for nombre in (*SCRIPTS, "comun"):
        assert "$env:TEMP" not in _codigo(_ps1(nombre)), nombre


def test_el_desinstalador_se_eleva_en_su_sitio_y_sale_de_la_carpeta() -> None:
    """Revision del paso 14: la parte de administrador corria desde una copia en %TEMP%, que
    tu usuario puede cambiar; y la ventana, con su carpeta actual en windows\\, no dejaba
    borrarla."""
    desinstalar = _ps1("desinstalar")
    assert '"-File", $PSCommandPath' in desinstalar and "TEMP" not in _codigo(desinstalar)
    assert "Copy-Item" not in desinstalar
    assert desinstalar.index("Set-Location -LiteralPath $env:SystemRoot") < desinstalar.index(
        "if (-not $Elevado) {")
    bat = (WINDOWS / "desinstalar.bat").read_text(encoding="utf-8")
    orden = [linea for linea in bat.splitlines() if "powershell" in linea]
    assert len(orden) == 1 and orden[0].startswith('cd /d "%SystemRoot%" & powershell')


def _lista_ps(texto: str, variable: str) -> tuple[str, ...]:
    """Los elementos de `$Variable = @("a", "b")` (o de `$Variable = "a"`) en un script."""
    encontrado = re.search(rf"(?m)^\${variable} = (@\(([^)]*)\)|\"([^\"]*)\")$", texto)
    assert encontrado, variable
    if encontrado.group(3) is not None:
        return (encontrado.group(3),)
    return tuple(re.findall(r'"([^"]*)"', encontrado.group(2)))


def test_comun_dice_lo_mismo_que_nativo_del_python_de_cada_papel() -> None:
    """Paso 14b: los nombres y las listas del Python de NuGet estan en nativo.py (lo que usan
    el codigo y los tests) y en comun.ps1 (lo que usa el instalador): tienen que ser iguales."""
    comun = _ps1("comun")
    assert _lista_ps(comun, "DllPython") == (nativo.DLL_PYTHON,)
    assert _lista_ps(comun, "FicheroPth") == (nativo.FICHERO_PTH,)
    assert _lista_ps(comun, "RutasPth") == nativo.RUTAS_PTH
    assert _lista_ps(comun, "CarpetaDelPaquete") == (nativo.CARPETA_DEL_PAQUETE,)
    assert _lista_ps(comun, "FueraDelRuntime") == nativo.FUERA_DEL_RUNTIME
    assert _lista_ps(comun, "NecesariosDelRuntime") == nativo.NECESARIOS_DEL_RUNTIME


def test_el_pth_es_el_de_la_estructura_del_paquete_de_nuget() -> None:
    """Paso 14b: en el paquete de NuGet la biblioteca va en Lib (en .py) y los modulos
    compilados en DLLs; en la carpeta del programa no hay nada que importar. El ._pth va junto
    a la DLL (python313._pth), deja site sin importar (ninguna linea "import site": sin
    site-packages ni la carpeta del usuario) y solo lleva rutas dentro de la instalacion."""
    assert nativo.RUTAS_PTH == ("Lib", "DLLs", r"..\..\lib", r"..\..\app\src")
    assert nativo.contenido_pth() == "Lib\r\nDLLs\r\n..\\..\\lib\r\n..\\..\\app\\src\r\n"
    assert nativo.FICHERO_PTH == nativo.DLL_PYTHON.replace(".dll", "._pth")
    assert not any(r.startswith("import") or "site" in r.lower() for r in nativo.RUTAS_PTH)
    assert "." not in nativo.RUTAS_PTH and not any(":" in r or r.startswith("\\")
                                                    for r in nativo.RUTAS_PTH)
    # Cada ruta es de la carpeta del Python de un papel (runtime\<papel>) o de la raiz.
    for ruta in nativo.RUTAS_PTH:
        destino = ntpath.normpath(ntpath.join(r"C:\BMS\runtime\lector", ruta))
        assert destino.startswith("C:\\BMS\\"), ruta
    # Lo que pide el ._pth es lo que el instalador saca del paquete.
    assert {"Lib/os.py", "DLLs/_socket.pyd"} <= set(nativo.NECESARIOS_DEL_RUNTIME)


def test_el_instalador_hace_un_python_por_papel_con_su_pth() -> None:
    instalar = _ps1("instalar")
    pth = _funcion(instalar, "Escribir-Pth")
    assert "Join-Path $Carpeta $FicheroPth" in pth and "$RutasPth -join" in pth
    assert "[System.Text.Encoding]::ASCII" in pth and '"`r`n"' in pth
    assert '$Roles = @("consola", "lector", "salida", "orden")' in _ps1("comun")
    assert tuple(aislamiento.ROLES) == ("consola", "lector", "salida", "orden")
    bucle = instalar[instalar.index("foreach ($rol in $Roles) {\n        $destino"):]
    bucle = bucle[:bucle.index("\n    }\n")]
    assert 'Join-Path $Raiz ("runtime\\" + $rol)' in bucle and "Escribir-Pth $destino" in bucle
    # Paso 14b: cada papel con un solo programa, python.exe (pythonw.exe o un lanzador serian
    # programas sin reglas): lo comprueba despues de copiar.
    assert bucle.index("Copy-Item") < bucle.index("Escribir-Pth $destino") < bucle.index(
        "Comprobar-Runtime $destino")
    # El instalacion.json que lee nativo.detectar.
    assert re.search(r"version\s+= 1\b", instalar) and "puerto_consola = 8765" in instalar
    assert "puerto_salida  = 3128" in instalar and '"instalacion.json"' in instalar
    assert nativo.PUERTO_CONSOLA == 8765 and nativo.PUERTO_SALIDA == 3128



# Lo que trae el paquete "python" de nuget.org, en pequeno: la misma forma (lo de NuGet fuera
# de tools/, y en tools/ el interprete con lo que no va en cada papel), visto en el paquete de
# verdad (python.3.13.16.nupkg) al hacer el paso 14b.
ENTRADAS_DEL_PAQUETE = (
    "_rels/.rels", "python.nuspec", "build/native/python.props", "images/python.png",
    "[Content_Types].xml", "package/services/metadata/core-properties/nuget.psmdcp",
    ".signature.p7s",
    "tools/python.exe", "tools/pythonw.exe", "tools/python3.dll", "tools/python313.dll",
    "tools/vcruntime140.dll", "tools/vcruntime140_1.dll", "tools/LICENSE.txt",
    "tools/DLLs/_socket.pyd", "tools/DLLs/_sqlite3.pyd", "tools/DLLs/_ssl.pyd",
    "tools/DLLs/libssl-3.dll", "tools/DLLs/python.cat",
    "tools/Lib/os.py", "tools/Lib/json/__init__.py", "tools/Lib/ctypes/macholib/fetch_macholib.bat",
    "tools/Lib/site-packages/README.txt", "tools/Lib/site-packages/pip/__init__.py",
    "tools/Lib/site-packages/pip/_vendor/distlib/t64.exe",
    "tools/Lib/site-packages/pip/_vendor/distlib/w64.exe",
    "tools/Lib/ensurepip/__init__.py", "tools/Lib/ensurepip/_bundled/pip-26.2.1-py3-none-any.whl",
    "tools/Lib/venv/__init__.py", "tools/Lib/venv/scripts/nt/venvlauncher.exe",
    "tools/Lib/venv/scripts/nt/venvwlauncher.exe",
    "tools/include/Python.h", "tools/libs/python313.lib",
)
EN_CADA_PAPEL = {
    "python.exe", "python3.dll", "python313.dll", "vcruntime140.dll", "vcruntime140_1.dll",
    "LICENSE.txt", "DLLs/_socket.pyd", "DLLs/_sqlite3.pyd", "DLLs/_ssl.pyd", "DLLs/libssl-3.dll",
    "DLLs/python.cat", "Lib/os.py", "Lib/json/__init__.py", "Lib/ctypes/macholib/fetch_macholib.bat",
}


def _nupkg(ruta: Path, entradas=ENTRADAS_DEL_PAQUETE, version: str = "3.13.16") -> bytes:
    """Un paquete de NuGet de mentira con esas entradas (el nuspec, como el de verdad)."""
    import zipfile

    with zipfile.ZipFile(ruta, "w") as paquete:
        for nombre in entradas:
            if nombre == "python.nuspec":
                contenido = ("\ufeff<?xml version=\"1.0\"?><package><metadata><id>python</id>"
                             f"<version>{version}</version><authors>Python Software Foundation"
                             "</authors></metadata></package>").encode("utf-8")
            else:
                contenido = f"contenido de {nombre}".encode("utf-8")
            paquete.writestr(nombre, contenido)
    return ruta.read_bytes()


def test_de_cada_paquete_solo_sale_el_interprete_con_un_programa() -> None:
    """Paso 14b: de lo que trae el paquete de NuGet, en cada papel va tools/ menos pythonw.exe,
    pip (con sus lanzadores .exe), ensurepip, venv (con venvlauncher.exe) y lo de compilar
    (include, libs). Queda un solo programa: python.exe."""
    destinos = {nativo.destino_en_runtime(e) for e in ENTRADAS_DEL_PAQUETE} - {None}
    assert destinos == EN_CADA_PAPEL
    assert [d for d in destinos if d.lower().endswith(".exe")] == ["python.exe"]
    assert set(nativo.NECESARIOS_DEL_RUNTIME) <= destinos
    # Sin distinguir mayusculas, como Windows: Lib/Site-Packages es la misma carpeta.
    for entrada in ("tools/PythonW.exe", "tools/Lib/Site-Packages/x.py", "tools/LIBS/x.lib",
                    "TOOLS/Lib/VENV/scripts/nt/venvlauncher.exe", "tools/", "tools/Lib/",
                    "tools", "otra/python.exe", "python.exe"):
        assert nativo.destino_en_runtime(entrada) is None, entrada
    assert nativo.destino_en_runtime("TOOLS/Lib/os.py") == "Lib/os.py"


@pytest.mark.parametrize("entrada", [
    "tools/../python.exe", "../tools/python.exe", "/tools/python.exe", "tools/Lib/../../x.py",
    "tools\\Lib\\os.py", "C:/tools/python.exe", "tools/Lib//os.py", "tools/./python.exe",
])
def test_una_ruta_que_se_sale_de_la_carpeta_para_la_instalacion(entrada) -> None:
    with pytest.raises(nativo.PaqueteNoValido, match="no vale"):
        nativo.destino_en_runtime(entrada)


def test_el_instalador_abre_el_paquete_de_nuget_sin_salirse_y_con_un_solo_programa() -> None:
    """Paso 14b: el paquete se abre con .NET entrada a entrada (Expand-Archive de Windows
    PowerShell 5.1 solo abre .zip, y lo abre todo),
    solo lo que dice Destino-En-Runtime, nada fuera de la carpeta, y despues se exige un solo
    programa y lo necesario; la firma se mira en python.exe y en python313.dll."""
    instalar = _ps1("instalar")
    abrir = _funcion(instalar, "Abrir-Python")
    assert "[System.IO.Compression.ZipFile]::OpenRead($Paquete)" in abrir
    assert "Destino-En-Runtime $entrada.FullName" in abrir
    assert "if ($null -eq $relativa) { continue }" in abrir
    assert "$ruta.StartsWith($carpeta + [System.IO.Path]::DirectorySeparatorChar" in abrir
    assert abrir.index("StartsWith($carpeta") < abrir.index("ExtractToFile($entrada, $ruta, $true)")
    assert "$zip.Dispose()" in abrir and abrir.rstrip().endswith("Comprobar-Runtime $carpeta")
    destino = _funcion(instalar, "Destino-En-Runtime")
    for pieza in ('$Entrada.Contains("\\")', '$Entrada.Contains(":")', '$partes[$i] -eq ".."',
                  "$CarpetaDelPaquete", "foreach ($fuera in $FueraDelRuntime)",
                  "ToLowerInvariant()", "Fallar"):
        assert pieza in destino, pieza
    runtime = _funcion(instalar, "Comprobar-Runtime")
    assert '@(".exe", ".com", ".scr") -contains $_.Extension.ToLowerInvariant()' in runtime
    assert '$programas.Count -ne 1 -or $programas[0].FullName -ne (Join-Path $Carpeta "python.exe")' \
        in runtime
    assert "foreach ($necesario in $NecesariosDelRuntime)" in runtime
    firma = _funcion(instalar, "Comprobar-Firma")
    assert '$firma.Status -ne "Valid" -or $nombre -cne $Firmante' in firma
    assert "X509NameType]::SimpleName" in firma
    # Lo de antes (el embebible) ya no esta.
    assert "Expand-Archive -LiteralPath $zip" not in instalar and "python311" not in instalar
    assert "Expand-Archive" not in _codigo(abrir)


def test_el_instalador_compila_la_biblioteca_y_prueba_que_el_pth_vale() -> None:
    """Paso 14b: la biblioteca del paquete viene en .py: se compila una vez al instalar (luego
    runtime\\ es de solo lectura para tu usuario), y la prueba de arranque exige el modo aislado
    sin site (que el ._pth se aplica) y la version fijada."""
    instalar = _ps1("instalar")
    paso = instalar[instalar.index('Escribir "5/7'):instalar.index('Escribir "6/7')]
    assert '$bibliotecas = @($Roles | ForEach-Object { Join-Path $Raiz ("runtime\\" + $_ + "\\Lib") })' \
        in paso
    assert "-m compileall -q --invalidation-mode checked-hash @bibliotecas" in paso
    assert "sys.flags.isolated == 1 and sys.flags.no_site == 1 and 'site' not in sys.modules" in paso
    assert "$fijado.python.version" in paso and "sys.version_info[:3]" in paso
    assert paso.index("compileall") < paso.index("sys.flags.isolated") < paso.index("$LASTEXITCODE")


def test_las_reglas_apuntan_al_unico_programa_de_cada_papel() -> None:
    """Paso 14b: las reglas son de runtime\\<papel>\\python.exe, que es el unico programa que
    queda en cada papel."""
    for fila in _tabla_de_reglas():
        assert fila["rol"] in aislamiento.ROLES
    comun = _ps1("comun")
    assert 'Programa  = (Join-Path $Raiz ("runtime\\" + $fila.Rol + "\\python.exe"))' in comun
    assert [d for d in EN_CADA_PAPEL if d.endswith(".exe")] == ["python.exe"]


def test_el_instalador_deja_el_codigo_de_solo_lectura() -> None:
    instalar = _ps1("instalar")
    permisos = instalar[instalar.index("function Poner-Permisos"):]
    permisos = permisos[:permisos.index("\n}\n")]
    assert '"/setowner", $administradores' in permisos
    assert '$Raiz, "/inheritance:r", "/grant:r"' in permisos
    assert '($usuario + ":(OI)(CI)RX")' in permisos
    assert '($usuario + ":(OI)(CI)M")' in permisos
    assert permisos.count("(OI)(CI)M") == 1
    assert 'foreach ($hijo in @("datos", "buzon"))' in permisos
    assert 'foreach ($hijo in @("app", "lib", "runtime", "windows"))' in permisos
    assert set(nativo.ESCRIBIBLES) == {"datos", "buzon"}
    # La parte de administrador sabe para quien instala (el SID de tu usuario, no el suyo).
    assert '"-Usuario", $sid, "-Elevado"' in instalar and "-Verb RunAs" in instalar
    assert "$sid = Sid-Actual" in instalar
    assert "Poner-Permisos $Raiz $Sid" in instalar and "Instalar $Raiz $Usuario" in instalar
    # Y los accesos del escritorio y la clave, con tu usuario: fuera de la parte elevada.
    elevada = instalar.index("function Fallar([string]$Texto) { throw $Texto }")
    assert instalar.index("    Crear-Accesos $Raiz") < elevada
    assert instalar.index('& (Join-Path $Raiz "windows\\clave.ps1")') < elevada


def test_leer_facturas_comprueba_antes_de_pagar_y_para_la_salida() -> None:
    texto = _ps1("leer-facturas")
    orden = [texto.index(t) for t in (
        "if ($Demo)", "$salida = Arrancar-Salida $credencial", 'Comprobar-Rol "salida"',
        'Comprobar-Rol "lector"', "if ($codigoSalida -ne 0 -or $codigoLector -ne 0)",
        '"coste", "--estimar"', "Read-Host", "-not (Es-Si $respuesta)", '"extract"',
        "} finally {", "Parar-Salida $salida")]
    assert orden == sorted(orden)
    # Sin forma de saltarse la comprobacion: ningun parametro mas que -Demo.
    assert re.search(r"(?m)^param\(\[switch\]\$Demo\)$", texto)
    assert not re.search(r"Sin|Saltar|Forzar|Bypass|Omitir", _codigo(texto).replace(
        "SilentlyContinue", ""))
    # La credencial va por el entorno y se olvida; el lector sale por el proxy de la pasada.
    assert '$env:HTTPS_PROXY = "http://bms:" + $credencial + "@127.0.0.1:"' in texto
    finalmente = texto[texto.index("} finally {"):]
    assert "Remove-Item Env:\\HTTPS_PROXY" in finalmente
    assert "Remove-Item Env:\\BMS_PROXY_CLAVE" in finalmente
    # Fallar (que sale) va despues del finally: la salida se para siempre.
    assert texto.index("if ($motivo) { Fallar $motivo }") > texto.index("Parar-Salida $salida")
    comun = _ps1("comun")
    arrancar = comun[comun.index("function Arrancar-Salida"):]
    arrancar = arrancar[:arrancar.index("\n}\n")]
    for trozo in ('("127.0.0.1:" + $Inst.PuertoSalida)', '"--permitir", $Api',
                  '"--clave-del-entorno"', "$env:BMS_PROXY_CLAVE = $Credencial",
                  "Remove-Item Env:\\BMS_PROXY_CLAVE"):
        assert trozo in arrancar, trozo
    assert '$Api = "api.anthropic.com:443"' in comun


def test_iniciar_comprueba_y_abre_la_consola_solo_en_127_0_0_1() -> None:
    texto = _ps1("iniciar")
    assert '"demo", "crear", "--rehacer", "--db", $env:BMS_DB' in texto
    assert texto.index('"recalcular", "--diaria"') < texto.index('Arrancar-En-Segundo-Plano "consola"')
    assert texto.index('Comprobar-Rol "consola"') < texto.index('Arrancar-En-Segundo-Plano "consola"')
    assert 'Comprobar-Rol "orden"' in texto
    assert '"http://127.0.0.1:" + $Inst.PuertoConsola + "/consola"' in texto
    assert "--contenedor" not in texto and "0.0.0.0" not in texto and "--interfaz" not in texto
    assert '@("serve", "--puerto"' in texto
    assert 'Parar-Rol "consola"' in _ps1("parar") and 'Parar-Rol "salida"' in _ps1("parar")
    comun = _ps1("comun")
    procesos = comun[comun.index("function Procesos-De"):]
    assert "$_.Path -eq $programa" in procesos[:procesos.index("\n}\n")]


def test_comprobar_prueba_cada_papel_con_su_programa() -> None:
    texto = _ps1("comprobar")
    for rol in aislamiento.ROLES:
        assert f'$resultados["{rol}"] = Comprobar-Rol "{rol}"' in texto
    assert texto.index("Arrancar-Salida") < texto.index('Comprobar-Rol "lector"') < \
        texto.index("Parar-Salida $salida")
    assert 'Comprobar-Rol "consola" @("--proxy", $proxy)' in texto
    assert "Get-NetFirewallProfile" in texto and "Reglas-Del-Cortafuegos" in texto
    assert "exit 0" in texto and "Fallar" in texto
    comun = _ps1("comun")
    assert 'function Comprobar-Rol' in comun and '@("comprobar-aislamiento", "--rol", $Rol)' in comun
    orden = comun[comun.index("function Orden-De"):]
    assert "& $programa @OpcionesPython -m bms_agent.cli @Argumentos" in orden[:orden.index("\n}\n")]


def _funcion(texto: str, nombre: str) -> str:
    cuerpo = texto[texto.index(f"function {nombre}"):]
    return cuerpo[:cuerpo.index("\n}\n")]


def test_cada_python_corre_sin_bufer() -> None:
    """Revision del paso 14: con la salida por una tuberia (Out-Host) o a un fichero, Python
    guardaba lo que decia hasta acabar: una lectura de pago dejaba la ventana parada. Con el
    ._pth no se mira PYTHONUNBUFFERED; -u si vale."""
    comun = _ps1("comun")
    assert '$OpcionesPython = @("-u", "-X", "utf8")' in comun
    for nombre in ("Orden-De", "Orden-Directa", "Arrancar-En-Segundo-Plano"):
        assert "OpcionesPython" in _funcion(comun, nombre), nombre
    assert '"-X", "utf8", "-m"' not in comun
    for nombre in (*SCRIPTS, "comun"):
        assert not re.search(r"python\.exe[\"']?\s+-X", _ps1(nombre)), nombre


def test_el_cortafuegos_se_compara_como_texto() -> None:
    """Revision del paso 14: Get-NetFirewallProfile da Enabled como GpoBoolean (no un
    booleano), y `-ne $true` daba siempre "apagado"."""
    for nombre in (*SCRIPTS, "comun"):
        assert not re.search(r"Enabled\s+-(eq|ne)\s+\$(true|false)", _ps1(nombre),
                             re.IGNORECASE), nombre
    assert '@("True", "1") -notcontains ("" + $perfil.Enabled)' in _ps1("comprobar")
    assert '@("True", "1") -notcontains ("" + $_.Enabled)' in _ps1("instalar")


def test_comprobar_solo_sale_en_verde_con_el_cortafuegos_y_la_clave() -> None:
    """Revision del paso 14: una clave que no se puede usar, o un cortafuegos que no se puede
    leer, salian como "Todo en verde"."""
    texto = _ps1("comprobar")
    assert "$todoBien = $cortafuegosBien -and $claveBien" in texto
    clave = texto[texto.index('"3. La clave de la API"'):texto.index('"4. Otros programas')]
    assert clave.index("if ($codigo -ne 0) {") < clave.index("$claveBien = $false")
    cortafuegos = texto[texto.index('"1. El cortafuegos'):texto.index('"2. Cada papel')]
    captura = cortafuegos[cortafuegos.index("} catch {"):]
    assert "$cortafuegosBien = $false" in captura and "MAL" in captura
    # Lo que escucha en 127.0.0.1 (el cortafuegos no lo filtra) se ensena, como aviso.
    escucha = texto[texto.index('"4. Otros programas'):texto.index('"Resumen"')]
    assert "Get-NetTCPConnection -State Listen" in escucha and '"127.0.0.1", "::1"' in escucha
    assert "$todoBien" not in escucha
    assert texto.index("$todoBien = ") < texto.index("if ($todoBien)")


def test_la_salida_se_apaga_sola_si_nadie_la_para() -> None:
    """Revision del paso 14: cerrar la ventana con la X no llega al finally."""
    comun = _ps1("comun")
    arrancar = _funcion(comun, "Arrancar-Salida")
    assert "function Arrancar-Salida([string]$Credencial, [int]$Segundos)" in arrancar
    assert '"--max-segundos", ([string]$Segundos)' in arrancar
    assert "if ($Segundos -le 0)" in arrancar
    assert "$VidaSalidaLectura = 3 * 60 * 60" in comun
    assert "$VidaSalidaComprobacion = 10 * 60" in comun
    assert "Arrancar-Salida $credencial $VidaSalidaLectura" in _ps1("leer-facturas")
    assert "Arrancar-Salida $credencial $VidaSalidaComprobacion" in _ps1("comprobar")
    # Al abrir la consola, una salida que se quedo encendida se para (si no se esta leyendo).
    assert 'if ((Procesos-De "lector").Count -eq 0) { Parar-Rol "salida" }' in _ps1("iniciar")


def test_windows_prepara_la_cadena_de_la_api_antes_de_comprobar_el_lector() -> None:
    """Revision del paso 14: el lector valida el certificado con Windows dentro de su proceso,
    sin red; si Windows aun no tiene la cadena de la API, la baja PowerShell (que si tiene
    red) con una peticion HEAD, sin guardar nada."""
    comun = _ps1("comun")
    preparar = _funcion(comun, "Preparar-Certificados")
    assert re.search(r"Invoke-WebRequest -UseBasicParsing -Method Head [^\n]*"
                     r'-Uri \("https://" \+ \$ApiNombre \+ "/"\)', preparar)
    assert "-OutFile" not in preparar and '$ApiNombre = "api.anthropic.com"' in comun
    assert "$_.Exception.Response" in preparar
    for nombre in ("comprobar", "leer-facturas"):
        texto = _ps1(nombre)
        assert texto.index("Preparar-Certificados") < texto.index('Comprobar-Rol "lector"'), nombre


def _importables() -> set[tuple[str, str]]:
    """Lo que se puede importar: cada (fuente, tipo) de config/importacion."""
    tipos = set()
    for mapeo in (RAIZ / "config" / "importacion").glob("*.yaml"):
        datos = yaml.safe_load(mapeo.read_text(encoding="utf-8"))
        tipos.add((datos["fuente"], datos["tipo"]))
    return tipos


def test_importar_conoce_cada_carpeta_del_buzon_como_docker() -> None:
    comun = _ps1("comun")
    nativas = re.findall(r'"([a-z\\]+)"\s*=\s*@\("([a-z_]+)", "([a-z_]+)"\)', comun)
    docker = re.findall(r'"([a-z\\]+)"\s*=\s*@\("([a-z_]+)", "([a-z_]+)"\)',
                        (RAIZ / "docker" / "importar.ps1").read_text(encoding="utf-8"))
    assert nativas == docker and len(nativas) == len(_importables())
    from bms_agent.cli import SALIDA_PARCIAL, SALIDA_RECHAZADA

    texto = _ps1("importar")
    assert f"$rechazada = {SALIDA_RECHAZADA}" in texto and f"$parcial = {SALIDA_PARCIAL}" in texto
    mover = texto.index("Move-Item")
    assert texto.index("if ($codigo -eq 0 -or $codigo -eq $parcial)") < mover
    assert mover < texto.index("elseif ($codigo -eq $rechazada)")
    assert '"recalcular", "--diaria"' in texto and 'Orden-De "orden"' in texto


def test_el_token_y_la_clave_nunca_van_en_la_linea_de_la_orden() -> None:
    comun = _ps1("comun")
    assert "-AsSecureString" in comun and "ZeroFreeBSTR" in comun
    for nombre in SCRIPTS:
        texto = _ps1(nombre)
        assert "--token" not in texto, nombre
        assert "ANTHROPIC_API_KEY" not in texto, nombre
    clave = _ps1("clave")
    assert 'Orden-Directa "orden" @("clave", "guardar")' in clave
    assert 'Orden-De "lector" @("clave", "comprobar")' in clave


def test_los_scripts_son_de_windows_powershell_5_1() -> None:
    """Nada que solo entienda PowerShell 7: el que trae Windows es el 5.1."""
    for nombre in (*SCRIPTS, "comun"):
        codigo = _codigo(_ps1(nombre))
        assert not re.search(r"&&|\|\||\?\?|\?\.|\s\?\s[^:\n]+\s:\s", codigo), nombre
        assert not re.search(r"-Parallel|-AsPlainText|-AsHashtable|-AsByteStream|utf8NoBOM|"
                             r"\$PSStyle|-SkipCertificateCheck|Start-Process[^\n]*-Environment|"
                             r"GetRelativePath|\bclean\s*\{", codigo, re.IGNORECASE), nombre
        # Join-Path con tres partes es de PowerShell 7.
        simple = r'(?:\$[\w.:]+|"[^"]*")'
        lineas = "\n".join(l for l in _ps1(nombre).splitlines() if not l.lstrip().startswith("#"))
        assert not re.search(rf"Join-Path[ \t]+{simple}[ \t]+{simple}[ \t]+{simple}", lineas), \
            nombre
    instalar = _ps1("instalar")
    assert "[Net.SecurityProtocolType]::Tls12" in instalar
    assert '$ProgressPreference = "SilentlyContinue"' in _ps1("comun")


def test_gitattributes_y_gitignore_cubren_la_carpeta_windows() -> None:
    atributos = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert "*.ps1 text eol=crlf" in atributos and "*.bat text eol=crlf" in atributos
    ignorado = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/windows/paquetes/" in ignorado


def test_la_variante_de_docker_no_cambia() -> None:
    """La salida de Docker no pide credencial (alli la red ya separa al lector) y sus
    scripts siguen sin saber nada de la instalacion nativa."""
    compose = yaml.safe_load((RAIZ / "docker" / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "--clave-del-entorno" not in compose["services"]["salida"]["command"]
    assert "BMS_PROXY_CLAVE" not in json.dumps(compose)
    for script in (RAIZ / "docker").glob("*.ps1"):
        assert "comprobar-aislamiento" not in script.read_text(encoding="utf-8")


def _apartado(guia: str, titulo: str) -> str:
    """Un apartado de la guia, con los espacios y los saltos de linea juntados en uno."""
    texto = guia[guia.index(titulo):]
    siguiente = re.search(r"\n## \d+\.", texto[len(titulo):])
    return " ".join((texto[:len(titulo) + siguiente.start()] if siguiente else texto).split())


def test_la_guia_dice_de_donde_viene_python_y_por_que() -> None:
    """Paso 14b: la guia del dueno dice que el Python es el 3.13 de nuget.org (de la Python
    Software Foundation) y por que (las correcciones de seguridad que la 3.11 ya no tiene en
    Windows), y su tabla de "si algo no va" ya no le manda pedir los hashes que faltan: no
    falta ninguno."""
    guia = (RAIZ / "docs" / "instalacion-nativa.md").read_text(encoding="utf-8")
    instalar = _apartado(guia, "## 3. Instalar")
    assert "nuget.org" in instalar and "3.13" in instalar
    assert "Python Software Foundation" in instalar and "correcciones de seguridad" in instalar
    assert "un solo `python.exe`" in instalar
    problemas = _apartado(guia, "## 14. Si algo no va")
    assert "sha256 fijado" not in problemas and "Faltan los sha256" not in problemas
    assert not re.search(r"(?i)pide[^|\n]*(versi[oó]n|hash)", problemas)
    assert "no es lo fijado" in problemas and "api.nuget.org" in problemas
    mantener = _apartado(guia, "## 17. Para quien mantiene el programa")
    for pieza in ("Por qué Python 3.13 de nuget.org", "SHA-512", "--comprobar", "--rehacer",
                  "python313._pth", "un solo programa, `python.exe`"):
        assert pieza in mantener, pieza
    assert "python311" not in guia and "embed-amd64" not in guia


# ============================================================ fijar_windows.py

def _fijar():
    sys.path.insert(0, str(RAIZ / "scripts"))
    try:
        import fijar_windows
    finally:
        sys.path.pop(0)
    return fijar_windows


@pytest.mark.parametrize("fichero, vale", [
    ("pyyaml-6.0.3-cp313-cp313-win_amd64.whl", True),
    ("pydantic_core-2.50.1-cp313-cp313-win_amd64.whl", True),
    ("tzdata-2025.2-py2.py3-none-any.whl", True),
    ("anthropic-1.13.0-py3-none-any.whl", True),
    ("x-1.0-cp39-abi3-win_amd64.whl", True),
    ("x-1.0-cp313-abi3-win_amd64.whl", True),
    ("x-1.0-py313-none-any.whl", True),
    ("PyYAML-6.0.3-cp311-cp311-win_amd64.whl", False),
    ("pyyaml-6.0.3-cp313-cp313-win32.whl", False),
    ("pyyaml-6.0.3-cp313-cp313-win_arm64.whl", False),
    ("pyyaml-6.0.3-cp314-cp314-win_amd64.whl", False),
    ("pydantic_core-2.50.1-cp313-cp313t-win_amd64.whl", False),
    ("pyyaml-6.0.3-cp313-cp313-manylinux_2_17_x86_64.whl", False),
    ("x-1.0-cp314-abi3-win_amd64.whl", False),
    ("x-1.0-py2-none-any.whl", False),
    ("PyYAML-6.0.3.tar.gz", False),
])
def test_fijar_elige_la_rueda_de_windows(fichero, vale) -> None:
    assert _fijar().vale_para_windows(fichero, 13) is vale


def test_fijar_saca_el_hash_de_pypi_y_rehace_las_lineas() -> None:
    fijar = _fijar()
    meta = {"urls": [
        {"filename": "jiter-0.17.0-cp313-cp313-win32.whl", "digests": {"sha256": "1" * 64}},
        {"filename": "jiter-0.17.0-cp313-cp313-win_amd64.whl", "digests": {"sha256": "2" * 64}},
        {"filename": "jiter-0.17.0-cp311-cp311-win_amd64.whl", "digests": {"sha256": "4" * 64}},
        {"filename": "jiter-0.17.0.tar.gz", "digests": {"sha256": "3" * 64}}]}
    assert fijar.elegir_rueda(meta, "jiter", 13) == ("jiter-0.17.0-cp313-cp313-win_amd64.whl",
                                                     "2" * 64)
    assert fijar.elegir_rueda(meta, "jiter", 11)[1] == "4" * 64
    with pytest.raises(ValueError, match="ninguna rueda"):
        fijar.elegir_rueda({"urls": meta["urls"][::3]}, "jiter", 13)
    retirada = {"urls": [dict(meta["urls"][1], yanked=True)]}
    with pytest.raises(ValueError, match="ninguna rueda"):
        fijar.elegir_rueda(retirada, "jiter", 13)
    dos = {"urls": [meta["urls"][1], {"filename": "jiter-0.17.0-cp39-abi3-win_amd64.whl",
                                      "digests": {"sha256": "5" * 64}}]}
    with pytest.raises(ValueError, match="valen varias"):
        fijar.elegir_rueda(dos, "jiter", 13)
    # Rehacer las lineas: la vieja (con sus hashes o con un PENDIENTE) fuera; lo demas, igual.
    texto = ("# cabecera\njiter==0.17.0  # PENDIENTE: lo que sea\nPyYAML==6.0.3 \\\n"
             f"    --hash=sha256:{'a' * 64} \\\n    --hash=sha256:{'b' * 64}\nh11==0.16.0 \\\n"
             f"    --hash=sha256:{'c' * 64}\n")
    nuevo = fijar.escribir_requisitos(texto, {"jiter": ["d" * 64], "PyYAML": ["e" * 64]})
    assert nuevo == ("# cabecera\njiter==0.17.0 \\\n"
                     f"    --hash=sha256:{'d' * 64}\nPyYAML==6.0.3 \\\n    --hash=sha256:{'e' * 64}\n"
                     f"h11==0.16.0 \\\n    --hash=sha256:{'c' * 64}\n")
    assert [(r.nombre, r.hashes) for r in fijar.leer_requisitos(nuevo)] == [
        ("jiter", ["d" * 64]), ("PyYAML", ["e" * 64]), ("h11", ["c" * 64])]
    with pytest.raises(ValueError, match="sin un sha256"):
        fijar.escribir_requisitos(texto, {"jiter": []})


def test_fijar_cruza_el_paquete_con_el_sha512_de_nuget() -> None:
    """Paso 14b: el sha256 de lo bajado solo dice que es lo que nuget.org sirve hoy; se cruza
    con el SHA-512 que nuget.org publica de esa version en su catalogo (packageHash, en
    base64), con el id, la version, el autor y el tamano. Si algo no cuadra, se para."""
    fijar = _fijar()
    contenido = b"un paquete de nuget"
    sha512 = base64.b64encode(hashlib.sha512(contenido).digest()).decode()
    catalogo = {"id": "python", "version": "3.13.16", "authors": "Python Software Foundation",
                "packageHash": sha512, "packageHashAlgorithm": "SHA512",
                "packageSize": len(contenido)}
    assert fijar.sha512_nuget(contenido) == sha512
    assert fijar.cruzar_con_el_catalogo(contenido, catalogo, "3.13.16") == []
    malos = {
        "packageHash": base64.b64encode(hashlib.sha512(b"otro").digest()).decode(),
        "packageHashAlgorithm": "SHA256", "packageSize": 7, "version": "3.13.15",
        "id": "pythonx86", "authors": "Alguien",
    }
    for clave, valor in malos.items():
        assert fijar.cruzar_con_el_catalogo(contenido, dict(catalogo, **{clave: valor}),
                                            "3.13.16"), clave
    # La entrada del catalogo se encuentra por el indice de registro, con las paginas dentro
    # o aparte (como lo sirve nuget.org para el paquete python).
    hoja = {"catalogEntry": {"@id": "https://api.nuget.org/v3/catalog0/data/x/python.3.13.16.json",
                             "version": "3.13.16"}}
    otra = {"catalogEntry": {"@id": "...", "version": "3.13.15"}}
    indice = {"items": [{"@id": "p1", "items": [otra]}, {"@id": "p2"}]}
    assert fijar.entrada_del_registro(indice, {"p2": {"items": [hoja]}}, "3.13.16") == hoja
    with pytest.raises(ValueError, match="no tiene la version"):
        fijar.entrada_del_registro(indice, {"p2": {"items": []}}, "3.13.16")
    assert fijar.url_del_paquete("3.13.16") == (
        "https://api.nuget.org/v3-flatcontainer/python/3.13.16/python.3.13.16.nupkg")


def test_fijar_revisa_lo_que_el_instalador_abrira(tmp_path) -> None:
    """Paso 14b: el paquete tiene que ser un zip con el nuspec de python de la Python Software
    Foundation y, con lo que se saca para cada papel, un solo programa (python.exe), la DLL de
    esa version y lo necesario. Uno con otro programa, sin la DLL o con una ruta que se sale,
    no vale."""
    fijar = _fijar()
    assert fijar.revisar_paquete(_nupkg(tmp_path / "bueno.nupkg"), "3.13.16") == []
    assert fijar.revisar_paquete(_nupkg(tmp_path / "v.nupkg"), "3.13.17") == [
        "el nuspec no dice version = 3.13.17"]
    otro = _nupkg(tmp_path / "otro.nupkg", ENTRADAS_DEL_PAQUETE + ("tools/Scripts/pip.exe",))
    assert any("solo python.exe" in m for m in fijar.revisar_paquete(otro, "3.13.16"))
    sin_dll = _nupkg(tmp_path / "sin.nupkg",
                     tuple(e for e in ENTRADAS_DEL_PAQUETE if e != "tools/python313.dll"))
    assert "al paquete le falta tools/python313.dll" in fijar.revisar_paquete(sin_dll, "3.13.16")
    fuera = _nupkg(tmp_path / "fuera.nupkg", ENTRADAS_DEL_PAQUETE + ("tools/../evil.py",))
    assert any("no vale" in m for m in fijar.revisar_paquete(fuera, "3.13.16"))
    assert fijar.revisar_paquete(b"no es un zip", "3.13.16")[0].startswith("no es un paquete")


def test_fijar_comprobar_dice_que_falta_y_que_no_cuadra(tmp_path) -> None:
    fijar = _fijar()
    texto = (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8")
    docker = fijar.leer_requisitos((RAIZ / "docker" / "requirements.txt").read_text("utf-8"))
    fijado = json.loads((WINDOWS / "fijado.json").read_text(encoding="utf-8"))
    requisitos = fijar.leer_requisitos(texto)
    assert fijar.problemas(requisitos, docker, fijado) == []
    # Sin un hash, otra version que Docker, una de mas o de menos.
    sin = fijar.leer_requisitos(texto.replace(
        "jiter==0.17.0 \\\n    --hash=sha256:", "jiter==0.17.0\n    # --hash=sha256:"))
    assert "jiter: sin sha256" in fijar.problemas(sin, docker, fijado)
    otra = fijar.leer_requisitos(texto.replace("idna==3.20", "idna==3.21"))
    assert "idna: 3.21 en Windows y 3.20 en Docker" in fijar.problemas(otra, docker, fijado)
    assert any("no en requirements-windows" in m
               for m in fijar.problemas(requisitos[1:], docker, fijado))
    de_mas = requisitos + [fijar.Requisito("otra", "1.0", ["f" * 64])]
    assert any("otra: esta en requirements-windows" in m
               for m in fijar.problemas(de_mas, docker, fijado))
    # El Python: cada campo que falta o no es de nuget.org.
    for clave, valor in {"sha256": "", "sha512": "corto", "url": "https://www.python.org/x.zip",
                         "origen": "python.org", "fichero": "python-3.13.16-embed-amd64.zip",
                         "catalogo": "", "firmante": "Otro", "version": "3.14.1"}.items():
        roto = {"python": dict(fijado["python"], **{clave: valor})}
        assert fijar.problemas(requisitos, docker, roto), clave
    assert fijar.problemas(requisitos, docker, {"python": {"version": "x"}}) == [
        "python: 'x' no es una version de Python 3 (3.X.Y)"]
    # Con los ficheros ya bajados: los que no son los fijados se dicen.
    paquetes = tmp_path / "paquetes"
    paquetes.mkdir()
    (paquetes / fijado["python"]["fichero"]).write_bytes(b"otro paquete")
    malos = fijar.problemas_de_los_paquetes(paquetes, requisitos, fijado)
    assert "python.3.13.16.nupkg: su sha256 no es el fijado" in malos
    assert "python.3.13.16.nupkg: su SHA-512 no es el de nuget.org" in malos
    assert "anthropic: no hay ninguna rueda con su sha256 en " + str(paquetes) in malos


def test_fijar_comprobar_sale_con_0_con_lo_que_hay_en_el_repositorio(capsys) -> None:
    """La puerta del paso 14b: windows/fijado.json y windows/requirements-windows.txt estan
    completos. Por main y como lo corre quien mantiene el programa (sin red)."""
    assert _fijar().main(["--comprobar"]) == 0
    assert capsys.readouterr().out.strip() == "Todo fijado."
    proceso = subprocess.run([sys.executable, str(RAIZ / "scripts" / "fijar_windows.py"),
                              "--comprobar"], capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    assert proceso.stdout.strip() == "Todo fijado."


def _paquetes_bajados() -> Path | None:
    """La carpeta con lo bajado de verdad (el paquete de nuget.org y las ruedas), si la hay:
    BMS_PAQUETES_WINDOWS o windows/paquetes (la que usa el instalador sin internet)."""
    for carpeta in (os.environ.get("BMS_PAQUETES_WINDOWS"), WINDOWS / "paquetes"):
        if carpeta and Path(carpeta).is_dir():
            return Path(carpeta)
    return None


def test_lo_bajado_de_verdad_es_lo_fijado() -> None:
    """Con el paquete de nuget.org y las ruedas bajados (no van en git): su sha256 y su SHA-512
    son los fijados, y el paquete de verdad es uno que el instalador sabe abrir, con un solo
    programa por papel."""
    carpeta = _paquetes_bajados()
    if carpeta is None:
        pytest.skip("sin lo bajado (BMS_PAQUETES_WINDOWS o windows/paquetes)")
    fijar = _fijar()
    fijado = json.loads((WINDOWS / "fijado.json").read_text(encoding="utf-8"))
    requisitos = fijar.leer_requisitos(
        (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8"))
    assert fijar.problemas_de_los_paquetes(carpeta, requisitos, fijado) == []
    import zipfile

    with zipfile.ZipFile(carpeta / fijado["python"]["fichero"]) as paquete:
        destinos = {d for d in map(nativo.destino_en_runtime, paquete.namelist()) if d}
    assert [d for d in destinos if d.lower().endswith(".exe")] == ["python.exe"]
    assert {nativo.DLL_PYTHON, "Lib/os.py", "DLLs/_socket.pyd"} <= destinos
    assert not any(d.lower().startswith(("lib/site-packages/", "lib/venv/", "include/"))
                   for d in destinos)


# ============================================================ con PowerShell de verdad

def _pwsh(carpeta: Path) -> tuple[list[str], str] | None:
    """La orden de pwsh y donde ve la carpeta: el de esta maquina, o el de la imagen de
    Microsoft por Docker con BMS_PROBAR_PWSH=1 (sin red)."""
    if shutil.which("pwsh"):
        return ["pwsh"], str(carpeta)
    if os.environ.get("BMS_PROBAR_PWSH") != "1":
        return None
    docker = shlex.split(os.environ.get("BMS_DOCKER", "docker"))
    imagen = os.environ.get("BMS_IMAGEN_PWSH", "mcr.microsoft.com/powershell:lts-debian-12")
    return [*docker, "run", "--rm", "--network", "none", "-v", f"{carpeta}:/w", imagen,
            "pwsh"], "/w"


PRUEBA_PWSH = r"""
$ErrorActionPreference = "Stop"
$todo = [ordered]@{}
$errores = @{}
foreach ($f in Get-ChildItem (Join-Path $Base "windows") -Filter *.ps1) {
    $t = $null; $e = $null
    [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$t, [ref]$e) | Out-Null
    $errores[$f.Name] = @($e | ForEach-Object { $_.Message })
}
$todo["errores"] = $errores
. (Join-Path $Base "windows/comun.ps1")
function Fallar([string]$Texto) { throw $Texto }
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Base "windows/instalar.ps1"), [ref]$null, [ref]$null)
foreach ($f in $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    if ($f.Name -in @("Leer-Requisitos", "Escribir-Pth", "Descargar-Verificado", "Destino-En-Runtime", "Comprobar-Runtime", "Abrir-Python")) {
        . ([scriptblock]::Create($f.Extent.Text.Replace('$PSScriptRoot', '$Scripts')))
    }
}
$Scripts = Join-Path $Base "windows"
try { Leer-Requisitos | Out-Null; $todo["pendientes"] = "" } catch { $todo["pendientes"] = $_.Exception.Message }
$Scripts = Join-Path $Base "incompleto"
try { Leer-Requisitos | Out-Null; $todo["incompleto"] = "" } catch { $todo["incompleto"] = $_.Exception.Message }
$Scripts = Join-Path $Base "windows"
$todo["requisitos"] = @(Leer-Requisitos | ForEach-Object { [ordered]@{ nombre = $_.Nombre; version = $_.Version; hashes = @($_.Hashes) } })
Escribir-Pth (Join-Path $Base "pth")
$todo["pth"] = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes((Join-Path $Base "pth/python313._pth")))
$Scripts = Join-Path $Base "completo"
$destino = Join-Path $Base "bajado.bin"
Descargar-Verificado "https://nunca.invalid/x" $BuenHash $destino
$todo["bueno"] = (Test-Path $destino)
$destino2 = Join-Path $Base "bajado2.bin"
Copy-Item (Join-Path $Base "completo/paquetes/bajado.bin") (Join-Path $Base "completo/paquetes/bajado2.bin")
try { Descargar-Verificado "https://nunca.invalid/x" ("0" * 64) $destino2; $todo["malo"] = "siguio" } catch { $todo["malo"] = $_.Exception.Message }
$todo["malo_borrado"] = -not (Test-Path $destino2)
try { Descargar-Verificado "http://inseguro.invalid/x" ("0" * 64) (Join-Path $Base "nada.bin"); $todo["http"] = "siguio" } catch { $todo["http"] = $_.Exception.Message }
# El paquete de NuGet: lo que sale para cada papel, y lo que no se abre.
function Ficheros-De([string]$Carpeta) {
    $raiz = [System.IO.Path]::GetFullPath($Carpeta)
    return @(Get-ChildItem -Recurse -File -Force -LiteralPath $raiz | ForEach-Object { $_.FullName.Substring($raiz.Length + 1).Replace("\", "/") } | Sort-Object)
}
# Una lista y no un diccionario: los de PowerShell no distinguen mayusculas.
$destinos = @()
foreach ($entrada in (Get-Content -LiteralPath (Join-Path $Base "nupkg/entradas.txt"))) {
    try { $d = Destino-En-Runtime $entrada } catch { $d = "FALLA: " + $_.Exception.Message }
    $destinos += [ordered]@{ entrada = $entrada; destino = $d }
}
$todo["destinos"] = $destinos
foreach ($nombre in @("bueno", "otro", "fuera", "sin_dll", "real")) {
    $paquete = Join-Path $Base ("nupkg/" + $nombre + ".nupkg")
    if (-not (Test-Path -LiteralPath $paquete)) { continue }
    $carpeta = Join-Path $Base ("abierto/" + $nombre)
    try { Abrir-Python $paquete $carpeta; $todo["abierto_" + $nombre] = @(Ficheros-De $carpeta) } catch { $todo["abierto_" + $nombre] = "FALLA: " + $_.Exception.Message }
    $todo["fuera_de_" + $nombre] = (Test-Path -LiteralPath (Join-Path $Base "abierto/evil.py"))
}
$todo["reglas"] = @(Reglas-Del-Cortafuegos $Base | ForEach-Object { [ordered]@{ nombre = $_.Nombre; programa = $_.Programa; direccion = $_.Direccion; accion = $_.Accion; protocolo = $_.Protocolo; puertos = @($_.Puertos) } })
$todo["comillas"] = Linea-De-Argumentos @("-m", "C:\Mis datos\BMS", 'di "hola"', "")
$todo["si"] = @(@("si", "S", " si ", ("s" + [char]0x00ED), "no", "") | ForEach-Object { Es-Si $_ })
$todo["credencial"] = Nueva-Credencial
$todo["buzon"] = @((Carpetas-Del-Buzon).Keys)
$todo | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $Base "resultado.json") -Encoding ascii
"""

# Lo que Destino-En-Runtime tiene que decir igual que nativo.destino_en_runtime.
ENTRADAS_A_COMPARAR = ENTRADAS_DEL_PAQUETE + (
    "tools/PythonW.exe", "tools/Lib/Site-Packages/x.py", "TOOLS/Lib/os.py", "tools/", "tools",
    "tools/../python.exe", "/tools/python.exe", "tools/Lib//os.py", "tools/./python.exe",
    "C:/tools/python.exe", "tools\\Lib\\os.py")


def _destino_o_falla(entrada: str) -> str | None:
    try:
        return nativo.destino_en_runtime(entrada)
    except nativo.PaqueteNoValido:
        return "FALLA"


@pytest.fixture(scope="module")
def con_pwsh(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("pwsh")
    orden = _pwsh(carpeta)
    if orden is None:
        pytest.skip("sin pwsh (o BMS_PROBAR_PWSH=1 con Docker y la imagen de PowerShell)")
    comando, base = orden
    shutil.copytree(WINDOWS, carpeta / "windows", ignore=shutil.ignore_patterns("paquetes"))
    completo = carpeta / "completo"
    (completo / "paquetes").mkdir(parents=True)
    texto = (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8")
    fijar = _fijar()
    # Uno al que le faltan los hashes de jiter: el instalador no sigue.
    (carpeta / "incompleto").mkdir()
    (carpeta / "incompleto" / "requirements-windows.txt").write_text(
        re.sub(r"(?m)^(jiter==\S+) \\\n    --hash=sha256:[0-9a-f]{64}\n", r"\1\n", texto),
        encoding="utf-8")
    contenido = b"un fichero bajado"
    (completo / "paquetes" / "bajado.bin").write_bytes(contenido)
    (carpeta / "pth").mkdir()
    nupkg = carpeta / "nupkg"
    nupkg.mkdir()
    (nupkg / "entradas.txt").write_text("\n".join(ENTRADAS_A_COMPARAR) + "\n", encoding="ascii")
    _nupkg(nupkg / "bueno.nupkg")
    _nupkg(nupkg / "otro.nupkg", ENTRADAS_DEL_PAQUETE + ("tools/Scripts/pip.exe",))
    _nupkg(nupkg / "fuera.nupkg", ENTRADAS_DEL_PAQUETE + ("tools/../../evil.py",))
    _nupkg(nupkg / "sin_dll.nupkg",
           tuple(e for e in ENTRADAS_DEL_PAQUETE if e != "tools/python313.dll"))
    real = None
    bajados = _paquetes_bajados()
    if bajados is not None:
        fichero = json.loads((WINDOWS / "fijado.json").read_text(encoding="utf-8"))["python"]["fichero"]
        if (bajados / fichero).is_file():
            real = bajados / fichero
            shutil.copyfile(real, nupkg / "real.nupkg")
    guion = (f'$Base = "{base}"\n$BuenHash = "{hashlib.sha256(contenido).hexdigest()}"\n'
             + PRUEBA_PWSH)
    (carpeta / "prueba.ps1").write_text(guion, encoding="ascii")
    proceso = subprocess.run([*comando, "-NoProfile", "-File", f"{base}/prueba.ps1"],
                             capture_output=True, text=True, timeout=600)
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    return (json.loads((carpeta / "resultado.json").read_text(encoding="ascii")), fijar, texto,
            real)


def test_pwsh_cada_script_pasa_el_analizador(con_pwsh) -> None:
    resultado = con_pwsh[0]
    assert set(resultado["errores"]) == {f"{n}.ps1" for n in SCRIPTS} | {"comun.ps1"}
    assert {n: e for n, e in resultado["errores"].items() if e} == {}


def test_pwsh_el_instalador_lee_los_hashes_como_pip_y_no_sigue_sin_ellos(con_pwsh) -> None:
    resultado, fijar, texto, _real = con_pwsh
    # Paso 14b: con lo del repositorio sigue (nada pendiente); sin los de jiter, no.
    assert resultado["pendientes"] == ""
    assert resultado["incompleto"].startswith("Faltan los sha256 de jiter en ")
    assert [(r["nombre"], r["version"], r["hashes"]) for r in resultado["requisitos"]] == [
        (r.nombre, r.version, r.hashes) for r in fijar.leer_requisitos(texto)]


def test_pwsh_el_pth_y_las_descargas_comprobadas(con_pwsh) -> None:
    resultado = con_pwsh[0]
    assert base64.b64decode(resultado["pth"]) == nativo.contenido_pth().encode("ascii")
    assert resultado["bueno"] is True
    assert "no es lo fijado" in resultado["malo"] and resultado["malo_borrado"] is True
    assert "Solo se descarga por https" in resultado["http"]


def test_pwsh_el_paquete_de_nuget_se_abre_como_dice_nativo(con_pwsh) -> None:
    """Paso 14b: Destino-En-Runtime dice lo mismo que nativo.destino_en_runtime, entrada a
    entrada; Abrir-Python deja en la carpeta exactamente eso, para con otro programa, sin la
    DLL o con una ruta que se sale (sin dejar nada fuera)."""
    resultado = con_pwsh[0]
    de_powershell = [(f["entrada"], "FALLA" if str(f["destino"]).startswith("FALLA")
                      else f["destino"]) for f in resultado["destinos"]]
    assert de_powershell == [(e, _destino_o_falla(e)) for e in ENTRADAS_A_COMPARAR]
    assert set(resultado["abierto_bueno"]) == EN_CADA_PAPEL
    assert "un solo programa, python.exe" in resultado["abierto_otro"]
    assert "Scripts/pip.exe" in resultado["abierto_otro"].replace("\\", "/")
    assert "no vale" in resultado["abierto_fuera"] and resultado["fuera_de_fuera"] is False
    assert "le falta python313.dll" in resultado["abierto_sin_dll"]


def test_pwsh_el_paquete_de_verdad_deja_un_solo_programa(con_pwsh) -> None:
    """Con el paquete de nuget.org bajado (BMS_PAQUETES_WINDOWS o windows/paquetes): lo que
    abre el instalador es lo que dice nativo, con un solo programa y lo necesario."""
    resultado, _f, _t, real = con_pwsh
    if real is None:
        pytest.skip("sin el paquete de nuget.org bajado (BMS_PAQUETES_WINDOWS o windows/paquetes)")
    import zipfile

    with zipfile.ZipFile(real) as paquete:
        esperado = {d for d in map(nativo.destino_en_runtime, paquete.namelist()) if d}
    abierto = resultado["abierto_real"]
    assert isinstance(abierto, list), abierto
    assert set(abierto) == esperado
    assert [f for f in abierto if f.lower().endswith(".exe")] == ["python.exe"]
    assert set(nativo.NECESARIOS_DEL_RUNTIME) <= set(abierto)


def test_pwsh_las_reglas_y_lo_demas_de_comun(con_pwsh) -> None:
    resultado = con_pwsh[0]
    reglas = resultado["reglas"]
    assert all(r["nombre"].startswith("BMS Finanzas - ") for r in reglas)
    por_rol = {}
    for regla in reglas:
        rol = regla["nombre"].split(" - ")[1]
        assert regla["programa"].replace("/", "\\").endswith(f"runtime\\{rol}\\python.exe")
        por_rol.setdefault(rol, set()).add((regla["direccion"], regla["accion"],
                                            regla["protocolo"], tuple(regla["puertos"] or ())))
    assert por_rol == REGLAS
    assert resultado["comillas"] == '-m "C:\\Mis datos\\BMS" "di \\"hola\\"" ""'
    assert resultado["si"] == [True, True, True, True, False, False]
    assert re.fullmatch(r"[0-9a-f]{64}", resultado["credencial"])
    assert len(resultado["buzon"]) == len(_importables())
