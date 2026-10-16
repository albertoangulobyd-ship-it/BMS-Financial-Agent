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
def _proxy(*, clave: str | None = CREDENCIAL, permitidos=("api.anthropic.com:443",)):
    """La salida de verdad (salida.Proxy) en 127.0.0.1, con la API de mentira: lo que pide
    api.anthropic.com va a un eco local. Nada sale de esta maquina."""
    with _servidor(_Aceptador) as eco:
        def conectar(_direccion, espera):
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
    assert set(carpetas) == {"app", "lib", "runtime/lector", "datos", "buzon"}
    bien = {"datos", "buzon"}
    vistas = aislamiento.observar("orden", sondas=(), carpetas=carpetas,
                                  escribir=lambda c: c.name in bien)
    assert all(c.bien for c in aislamiento.evaluar("orden", vistas, ()))
    # Un programa que se puede cambiar (un DLL junto a python.exe se cargaria al arrancar).
    vistas = aislamiento.observar("orden", sondas=(), carpetas=carpetas,
                                  escribir=lambda c: c.name in bien | {"lector"})
    juicio = aislamiento.evaluar("orden", vistas, ())
    assert [c.nombre for c in juicio if c.grave and not c.bien] == ["escribir en runtime/lector"]
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
    assert nativo.detectar(sys.executable) is None
    assert nativo.instalacion_actual() is None


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
    for ruta in sorted(SRC.rglob("*.py")):
        codigo = ruta.read_text(encoding="utf-8")
        nombre = str(ruta.relative_to(SRC))
        encontrados = lanzamientos(codigo)
        if encontrados and nombre not in PUEDEN_LANZAR:
            malos[nombre] = encontrados
        if _usa_ctypes(codigo) and nombre not in PUEDEN_USAR_CTYPES:
            malos.setdefault(nombre, []).append("ctypes")
    assert malos == {}
    texto = (SRC / "secretos.py").read_text(encoding="utf-8")
    assert set(re.findall(r'WinDLL\("(\w+)"', texto)) == {"crypt32", "kernel32"}
    assert set(re.findall(r"(?:crypt32|kernel32)\.(\w+)", texto)) == {
        "CryptProtectData", "CryptUnprotectData", "LocalFree"}


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
    # Lo que se baja se usa despues de comprobarlo: el zip, y cada rueda.
    assert instalar.index("Descargar-Verificado $fijado.python.url") < instalar.index(
        "Expand-Archive -LiteralPath $zip")
    assert instalar.index("Descargar-Verificado $rueda.Url") < instalar.index(
        "Expand-Archive -LiteralPath $comoZip")
    # Lo de PyPI solo dice donde esta el fichero: lo que decide es el hash fijado.
    assert "$Requisito.Hashes -contains $fichero.digests.sha256" in instalar
    assert "Comprobar-Firma (Join-Path $base $nombre) $fijado.python.firmante" in instalar


def test_el_instalador_no_sigue_sin_los_hashes_fijados() -> None:
    instalar = _ps1("instalar")
    assert "$fijado.python.sha256 -notmatch '^[0-9a-f]{64}$'" in instalar
    assert '$sinHash = @($requisitos | Where-Object { $_.Hashes.Count -eq 0 }' in instalar
    fijado = json.loads((WINDOWS / "fijado.json").read_text(encoding="utf-8"))["python"]
    assert fijado["url"] == ("https://www.python.org/ftp/python/" + fijado["version"]
                             + "/" + fijado["fichero"])
    assert re.fullmatch(r"python-3\.11\.\d+-embed-amd64\.zip", fijado["fichero"])
    # La misma version menor que el desarrollo (y que la imagen de Docker).
    assert fijado["version"].rsplit(".", 1)[0] == f"{sys.version_info[0]}.{sys.version_info[1]}"
    assert fijado["sha256"] == "" or re.fullmatch(r"[0-9a-f]{64}", fijado["sha256"])
    assert fijado["firmante"] == "Python Software Foundation"


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
    # Lo que no se pudo fijar sin internet queda dicho como PENDIENTE (y el instalador no
    # sigue con ello): solo las ruedas de Windows y tzdata.
    pendientes = {n for n, r in windows.items() if not r.hashes}
    assert pendientes <= binarias | {"tzdata"}
    texto = (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8")
    for nombre in pendientes:
        assert re.search(rf"(?im)^{re.escape(windows[nombre].nombre)}==\S+\s+# PENDIENTE", texto)
    for nombre in binarias & set(windows):
        assert not set(windows[nombre].hashes) & set(docker[nombre].hashes), nombre


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


def test_el_instalador_hace_un_python_por_papel_con_su_pth() -> None:
    instalar = _ps1("instalar")
    pth = instalar[instalar.index("function Escribir-Pth"):]
    pth = pth[:pth.index("\n}\n")]
    lineas = re.search(r"\$lineas = @\(([^)]*)\)", pth).group(1)
    assert tuple(re.findall(r'"([^"]+)"', lineas)) == nativo.RUTAS_PTH
    assert "python311._pth" in pth and "[System.Text.Encoding]::ASCII" in pth
    assert '"`r`n"' in pth
    assert nativo.contenido_pth() == "python311.zip\r\n.\r\n..\\..\\lib\r\n..\\..\\app\\src\r\n"
    assert '$Roles = @("consola", "lector", "salida", "orden")' in _ps1("comun")
    assert tuple(aislamiento.ROLES) == ("consola", "lector", "salida", "orden")
    bucle = instalar[instalar.index("foreach ($rol in $Roles) {\n        $destino"):]
    bucle = bucle[:bucle.index("\n    }\n")]
    assert 'Join-Path $Raiz ("runtime\\" + $rol)' in bucle and "Escribir-Pth $destino" in bucle
    # pythonw.exe seria otro programa sin reglas.
    assert '"pythonw.exe"' in bucle and "Remove-Item" in bucle
    # El instalacion.json que lee nativo.detectar.
    assert re.search(r"version\s+= 1\b", instalar) and "puerto_consola = 8765" in instalar
    assert "puerto_salida  = 3128" in instalar and '"instalacion.json"' in instalar
    assert nativo.PUERTO_CONSOLA == 8765 and nativo.PUERTO_SALIDA == 3128


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
    assert "& $programa -X utf8 -m bms_agent.cli @Argumentos" in orden[:orden.index("\n}\n")]


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


# ============================================================ fijar_windows.py

def _fijar():
    sys.path.insert(0, str(RAIZ / "scripts"))
    try:
        import fijar_windows
    finally:
        sys.path.pop(0)
    return fijar_windows


@pytest.mark.parametrize("fichero, vale", [
    ("PyYAML-6.0.3-cp311-cp311-win_amd64.whl", True),
    ("pydantic_core-2.50.1-cp311-cp311-win_amd64.whl", True),
    ("tzdata-2025.2-py2.py3-none-any.whl", True),
    ("anthropic-1.13.0-py3-none-any.whl", True),
    ("x-1.0-cp39-abi3-win_amd64.whl", True),
    ("PyYAML-6.0.3-cp311-cp311-win32.whl", False),
    ("PyYAML-6.0.3-cp311-cp311-win_arm64.whl", False),
    ("PyYAML-6.0.3-cp312-cp312-win_amd64.whl", False),
    ("PyYAML-6.0.3-cp311-cp311-manylinux_2_17_x86_64.whl", False),
    ("x-1.0-cp312-abi3-win_amd64.whl", False),
    ("PyYAML-6.0.3.tar.gz", False),
])
def test_fijar_elige_la_rueda_de_windows(fichero, vale) -> None:
    assert _fijar().vale_para_windows(fichero) is vale


def test_fijar_rellena_solo_lo_pendiente_con_el_hash_de_pypi() -> None:
    fijar = _fijar()
    meta = {"urls": [
        {"filename": "jiter-0.17.0-cp311-cp311-win32.whl", "digests": {"sha256": "1" * 64}},
        {"filename": "jiter-0.17.0-cp311-cp311-win_amd64.whl", "digests": {"sha256": "2" * 64}},
        {"filename": "jiter-0.17.0.tar.gz", "digests": {"sha256": "3" * 64}}]}
    assert fijar.elegir_rueda(meta, "jiter") == ("jiter-0.17.0-cp311-cp311-win_amd64.whl", "2" * 64)
    with pytest.raises(ValueError, match="ninguna rueda"):
        fijar.elegir_rueda({"urls": meta["urls"][::2]}, "jiter")
    texto = (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8")
    pendientes = [r.nombre for r in fijar.leer_requisitos(texto) if not r.hashes]
    nuevo = fijar.escribir_requisitos(texto, {n: "a" * 64 for n in pendientes})
    requisitos = fijar.leer_requisitos(nuevo)
    assert all(r.hashes for r in requisitos)
    antes = {r.nombre: r.hashes for r in fijar.leer_requisitos(texto) if r.hashes}
    assert {r.nombre: r.hashes for r in requisitos if r.nombre in antes} == antes
    assert fijar.pendientes(requisitos, {"python": {"sha256": "b" * 64}}) == []
    assert fijar.pendientes(requisitos, {"python": {"sha256": ""}}) == ["python-embebible"]


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
    if ($f.Name -in @("Leer-Requisitos", "Escribir-Pth", "Descargar-Verificado")) {
        . ([scriptblock]::Create($f.Extent.Text.Replace('$PSScriptRoot', '$Scripts')))
    }
}
$Scripts = Join-Path $Base "windows"
try { Leer-Requisitos | Out-Null; $todo["pendientes"] = "" } catch { $todo["pendientes"] = $_.Exception.Message }
$Scripts = Join-Path $Base "completo"
$todo["requisitos"] = @(Leer-Requisitos | ForEach-Object { [ordered]@{ nombre = $_.Nombre; version = $_.Version; hashes = @($_.Hashes) } })
Escribir-Pth (Join-Path $Base "pth")
$todo["pth"] = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes((Join-Path $Base "pth/python311._pth")))
$Scripts = Join-Path $Base "completo"
$destino = Join-Path $Base "bajado.bin"
Descargar-Verificado "https://nunca.invalid/x" $BuenHash $destino
$todo["bueno"] = (Test-Path $destino)
$destino2 = Join-Path $Base "bajado2.bin"
Copy-Item (Join-Path $Base "completo/paquetes/bajado.bin") (Join-Path $Base "completo/paquetes/bajado2.bin")
try { Descargar-Verificado "https://nunca.invalid/x" ("0" * 64) $destino2; $todo["malo"] = "siguio" } catch { $todo["malo"] = $_.Exception.Message }
$todo["malo_borrado"] = -not (Test-Path $destino2)
try { Descargar-Verificado "http://inseguro.invalid/x" ("0" * 64) (Join-Path $Base "nada.bin"); $todo["http"] = "siguio" } catch { $todo["http"] = $_.Exception.Message }
$todo["reglas"] = @(Reglas-Del-Cortafuegos $Base | ForEach-Object { [ordered]@{ nombre = $_.Nombre; programa = $_.Programa; direccion = $_.Direccion; accion = $_.Accion; protocolo = $_.Protocolo; puertos = @($_.Puertos) } })
$todo["comillas"] = Linea-De-Argumentos @("-m", "C:\Mis datos\BMS", 'di "hola"', "")
$todo["si"] = @(@("si", "S", " si ", ("s" + [char]0x00ED), "no", "") | ForEach-Object { Es-Si $_ })
$todo["credencial"] = Nueva-Credencial
$todo["buzon"] = @((Carpetas-Del-Buzon).Keys)
$todo | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $Base "resultado.json") -Encoding ascii
"""


@pytest.fixture(scope="module")
def con_pwsh(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("pwsh")
    orden = _pwsh(carpeta)
    if orden is None:
        pytest.skip("sin pwsh (o BMS_PROBAR_PWSH=1 con Docker y la imagen de PowerShell)")
    comando, base = orden
    shutil.copytree(WINDOWS, carpeta / "windows")
    completo = carpeta / "completo"
    (completo / "paquetes").mkdir(parents=True)
    texto = (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8")
    fijar = _fijar()
    falta = [r.nombre for r in fijar.leer_requisitos(texto) if not r.hashes]
    (completo / "requirements-windows.txt").write_text(
        fijar.escribir_requisitos(texto, {n: "d" * 64 for n in falta}), encoding="utf-8")
    contenido = b"un fichero bajado"
    (completo / "paquetes" / "bajado.bin").write_bytes(contenido)
    (carpeta / "pth").mkdir()
    guion = (f'$Base = "{base}"\n$BuenHash = "{hashlib.sha256(contenido).hexdigest()}"\n'
             + PRUEBA_PWSH)
    (carpeta / "prueba.ps1").write_text(guion, encoding="ascii")
    proceso = subprocess.run([*comando, "-NoProfile", "-File", f"{base}/prueba.ps1"],
                             capture_output=True, text=True, timeout=300)
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    return json.loads((carpeta / "resultado.json").read_text(encoding="ascii")), fijar, texto


def test_pwsh_cada_script_pasa_el_analizador(con_pwsh) -> None:
    resultado, _f, _t = con_pwsh
    assert set(resultado["errores"]) == {f"{n}.ps1" for n in SCRIPTS} | {"comun.ps1"}
    assert {n: e for n, e in resultado["errores"].items() if e} == {}


def test_pwsh_el_instalador_lee_los_hashes_como_pip_y_no_sigue_sin_ellos(con_pwsh) -> None:
    resultado, fijar, texto = con_pwsh
    pendientes = [r.nombre for r in fijar.leer_requisitos(texto) if not r.hashes]
    if pendientes:
        assert resultado["pendientes"].startswith("Faltan los sha256 de " + ", ".join(pendientes))
    else:
        assert resultado["pendientes"] == ""
    completo = fijar.leer_requisitos(fijar.escribir_requisitos(
        texto, {n: "d" * 64 for n in pendientes}))
    assert [(r["nombre"], r["version"], r["hashes"]) for r in resultado["requisitos"]] == [
        (r.nombre, r.version, r.hashes) for r in completo]


def test_pwsh_el_pth_y_las_descargas_comprobadas(con_pwsh) -> None:
    resultado, _f, _t = con_pwsh
    assert base64.b64decode(resultado["pth"]) == nativo.contenido_pth().encode("ascii")
    assert resultado["bueno"] is True
    assert "no es lo fijado" in resultado["malo"] and resultado["malo_borrado"] is True
    assert "Solo se descarga por https" in resultado["http"]


def test_pwsh_las_reglas_y_lo_demas_de_comun(con_pwsh) -> None:
    resultado, _f, _t = con_pwsh
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
