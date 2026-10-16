"""El proxy de salida del entorno de Docker (paso 13), con sockets locales.

Puertas que viven aqui:

- un destino de la lista conecta y los bytes pasan tal cual en los dos
  sentidos (tambien los que el cliente manda antes de recibir el 200);
- cualquier otro destino recibe 403 y el proxy no intenta ni resolverlo;
- los trucos de nombre (api.anthropic.com.evil.example, el punto final,
  mayusculas, IP escritas de formas raras) no pasan;
- un nombre permitido que resuelve a una direccion que no es de internet (un
  DNS que rebota hacia 127.0.0.1 o la red de casa) se rechaza;
- HTTP en claro se rechaza;
- cada intento queda en el registro;
- el reenvio de la consola lleva los bytes a su unico destino.

Ningun test sale a internet: el "api.anthropic.com" de los tests resuelve, con
un resolvedor falso, a un servidor de eco en 127.0.0.1.
"""

from __future__ import annotations

import logging
import socket
import socketserver
import threading
from contextlib import contextmanager

import pytest

from bms_agent import salida
from bms_agent.cli import main


# ------------------------------------------------------------ decidir, sin sockets

PERMITIDOS = salida.lista_blanca(salida.PERMITIDOS_POR_DEFECTO)


def _decidir(linea: str) -> salida.Decision:
    return salida.decidir(f"{linea}\r\nHost: x".encode("latin-1"), PERMITIDOS)


@pytest.mark.parametrize("linea", [
    "CONNECT api.anthropic.com:443 HTTP/1.1",
    "CONNECT API.Anthropic.COM:443 HTTP/1.1",
    "CONNECT api.anthropic.com.:443 HTTP/1.0",
])
def test_la_api_de_anthropic_pasa(linea) -> None:
    decision = _decidir(linea)
    assert decision.permitida and decision.codigo == 200
    assert decision.destino == salida.Destino("api.anthropic.com", 443)


@pytest.mark.parametrize("linea", [
    "CONNECT api.anthropic.com.evil.example:443 HTTP/1.1",
    "CONNECT evilapi.anthropic.com:443 HTTP/1.1",
    "CONNECT anthropic.com:443 HTTP/1.1",
    "CONNECT console.anthropic.com:443 HTTP/1.1",
    "CONNECT api.anthropic.co:443 HTTP/1.1",
    "CONNECT example.com:443 HTTP/1.1",
    "CONNECT api.anthropic.com:80 HTTP/1.1",
    "CONNECT api.anthropic.com:8443 HTTP/1.1",
    "CONNECT api.anthropic.com..:443 HTTP/1.1",
    "CONNECT api.anthropic.com%2eevil.example:443 HTTP/1.1",
    "CONNECT api_anthropic.com:443 HTTP/1.1",
])
def test_otro_nombre_no_pasa(linea) -> None:
    decision = _decidir(linea)
    assert decision.codigo == 403 and decision.destino is None


@pytest.mark.parametrize("ip", ["160.79.104.10", "127.0.0.1", "127.1", "2130706433",
                                "0x7f000001", "0x7f.1", "[::1]", "[2607:6bc0::10]", "10.0.0.1"])
def test_una_ip_escrita_a_mano_no_pasa_nunca(ip) -> None:
    decision = _decidir(f"CONNECT {ip}:443 HTTP/1.1")
    assert decision.codigo == 403 and "IP" in decision.motivo


@pytest.mark.parametrize("linea", [
    "GET http://api.anthropic.com/v1/messages HTTP/1.1",
    "POST http://api.anthropic.com/v1/messages HTTP/1.1",
    "GET / HTTP/1.1",
    "connect api.anthropic.com:443 HTTP/1.1",
])
def test_http_en_claro_y_otros_metodos_no_pasan(linea) -> None:
    assert _decidir(linea).codigo == 405


@pytest.mark.parametrize("linea", [
    "CONNECT api.anthropic.com HTTP/1.1",
    "CONNECT api.anthropic.com:0 HTTP/1.1",
    "CONNECT api.anthropic.com:99999 HTTP/1.1",
    "CONNECT user@api.anthropic.com:443 HTTP/1.1",
    "CONNECT api.anthropic.com:443/x HTTP/1.1",
    "CONNECT api.anthropic.com:443",
    "CONNECT  api.anthropic.com:443 HTTP/1.1",
    "CONNECT api.anthropic.com:443 SPDY/3",
])
def test_lo_que_no_se_entiende_es_un_400(linea) -> None:
    assert _decidir(linea).codigo == 400


def test_una_peticion_que_no_es_ascii_es_un_400() -> None:
    decision = salida.decidir("CONNECT ápi.anthropic.com:443 HTTP/1.1\r\n".encode(), PERMITIDOS)
    assert decision.codigo == 400


@pytest.mark.parametrize("entrada", ["api.anthropic.com", "1.2.3.4:443", "*.anthropic.com:443",
                                     "[::1]:443", "api.anthropic.com:0", "api anthropic:443",
                                     "api.anthropic.com:http"])
def test_la_lista_blanca_solo_admite_nombres_con_puerto(entrada) -> None:
    with pytest.raises(ValueError):
        salida.leer_destino(entrada)


def test_la_lista_blanca_no_puede_estar_vacia() -> None:
    with pytest.raises(ValueError):
        salida.lista_blanca([])
    assert salida.lista_blanca(["API.anthropic.com.:443"]) == frozenset(
        {salida.Destino("api.anthropic.com", 443)})


@pytest.mark.parametrize("direccion, publica", [
    ("160.79.104.10", True), ("2607:6bc0::10", True), ("127.0.0.1", False),
    ("10.1.2.3", False), ("172.18.0.2", False), ("192.168.1.10", False),
    ("169.254.169.254", False), ("::1", False), ("fe80::1%eth0", False), ("100.64.0.1", False),
    ("0.0.0.0", False), ("no-es-ip", False),
])
def test_que_direcciones_son_de_internet(direccion, publica) -> None:
    assert (salida.direcciones_no_publicas([direccion]) == []) is publica


# ------------------------------------------------------------ con sockets locales

class _Eco(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class _ManejadorEco(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.server.conexiones += 1
        while True:
            datos = self.request.recv(65536)
            if not datos:
                return
            self.request.sendall(b"eco:" + datos)


@contextmanager
def _en_marcha(servidor):
    hilo = threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.05},
                            daemon=True)
    hilo.start()
    try:
        yield servidor
    finally:
        servidor.shutdown()
        servidor.server_close()


@pytest.fixture
def eco():
    servidor = _Eco(("127.0.0.1", 0), _ManejadorEco)
    servidor.conexiones = 0
    with _en_marcha(servidor):
        yield servidor


class _Resolvedor:
    """Un DNS falso que apunta lo que le preguntan: el de verdad no se toca nunca."""

    def __init__(self, respuestas: dict[str, list[str]]) -> None:
        self.respuestas = respuestas
        self.preguntas: list[str] = []

    def __call__(self, host: str, puerto: int) -> list[str]:
        self.preguntas.append(host)
        if host not in self.respuestas:
            raise socket.gaierror("no existe")
        return self.respuestas[host]


@contextmanager
def _proxy(eco, *, respuestas=None, solo_publicas=False, permitidos=None):
    resolvedor = _Resolvedor(respuestas if respuestas is not None
                             else {"api.anthropic.com": ["127.0.0.1"]})
    lista = salida.lista_blanca(permitidos or [f"api.anthropic.com:{eco.server_address[1]}"])
    servidor = salida.Proxy(("127.0.0.1", 0), lista, resolver=resolvedor,
                            solo_publicas=solo_publicas, inactividad=5)
    with _en_marcha(servidor):
        yield servidor, resolvedor


def _pedir(proxy, texto: bytes, *, despues: bytes = b"") -> tuple[socket.socket, bytes]:
    cliente = socket.create_connection(proxy.server_address, timeout=5)
    cliente.sendall(texto + despues)
    respuesta = b""
    while b"\r\n\r\n" not in respuesta:
        trozo = cliente.recv(4096)
        if not trozo:
            break
        respuesta += trozo
    return cliente, respuesta


def _recibir(conexion: socket.socket, largo: int) -> bytes:
    datos = b""
    while len(datos) < largo:
        trozo = conexion.recv(4096)
        if not trozo:
            break
        datos += trozo
    return datos


def _connect(host: str, puerto: int) -> bytes:
    return f"CONNECT {host}:{puerto} HTTP/1.1\r\nHost: {host}:{puerto}\r\n\r\n".encode()


def test_el_destino_permitido_conecta_y_los_bytes_pasan_tal_cual(eco, caplog) -> None:
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    with _proxy(eco) as (proxy, resolvedor):
        cliente, respuesta = _pedir(proxy, _connect("api.anthropic.com", eco.server_address[1]))
        assert respuesta.startswith(b"HTTP/1.1 200 ")
        # Lo que va por el tunel es TLS para el cliente: el proxy no lo mira.
        hola = b"\x16\x03\x01 un ClientHello cualquiera"
        cliente.sendall(hola)
        assert _recibir(cliente, len(hola) + 4) == b"eco:" + hola
        cliente.close()
    assert resolvedor.preguntas == ["api.anthropic.com"] and eco.conexiones == 1
    assert any("decision=permitida" in r.getMessage() for r in caplog.records)


def test_lo_que_el_cliente_manda_antes_del_200_no_se_pierde(eco) -> None:
    with _proxy(eco) as (proxy, _r):
        cliente, respuesta = _pedir(proxy, _connect("api.anthropic.com", eco.server_address[1]),
                                    despues=b"adelantado")
        assert respuesta.startswith(b"HTTP/1.1 200 ")
        resto = respuesta.partition(b"\r\n\r\n")[2]
        assert resto + _recibir(cliente, len(b"eco:adelantado") - len(resto)) == \
            b"eco:adelantado"
        cliente.close()


@pytest.mark.parametrize("host", ["example.com", "api.anthropic.com.evil.example",
                                  "evilapi.anthropic.com", "127.0.0.1", "localhost"])
def test_otro_destino_recibe_403_y_no_se_intenta(eco, host, caplog) -> None:
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    respuestas = {"api.anthropic.com": ["127.0.0.1"], host: ["127.0.0.1"]}
    with _proxy(eco, respuestas=respuestas) as (proxy, resolvedor):
        cliente, respuesta = _pedir(proxy, _connect(host, eco.server_address[1]))
        cliente.close()
    assert respuesta.startswith(b"HTTP/1.1 403 ")
    assert resolvedor.preguntas == [] and eco.conexiones == 0
    [linea] = [r.getMessage() for r in caplog.records if "decision=" in r.getMessage()]
    assert "decision=rechazada" in linea and "codigo=403" in linea and host in linea


def test_otro_puerto_del_mismo_nombre_no_pasa(eco) -> None:
    with _proxy(eco) as (proxy, resolvedor):
        cliente, respuesta = _pedir(proxy, _connect("api.anthropic.com", 22))
        cliente.close()
    assert respuesta.startswith(b"HTTP/1.1 403 ") and resolvedor.preguntas == []


@pytest.mark.parametrize("direccion", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
def test_un_dns_que_rebota_hacia_casa_no_pasa(eco, direccion, caplog) -> None:
    """El nombre esta en la lista, pero resuelve a una direccion que no es de internet: el
    proxy no se convierte en un puente hacia la red local."""
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    with _proxy(eco, respuestas={"api.anthropic.com": ["160.79.104.10", direccion]},
                solo_publicas=True) as (proxy, resolvedor):
        cliente, respuesta = _pedir(proxy, _connect("api.anthropic.com", eco.server_address[1]))
        cliente.close()
    assert respuesta.startswith(b"HTTP/1.1 403 ")
    assert resolvedor.preguntas == ["api.anthropic.com"] and eco.conexiones == 0
    assert any("no es de internet" in r.getMessage() for r in caplog.records)


def test_conecta_con_la_direccion_comprobada_y_no_vuelve_a_resolver(eco) -> None:
    """La direccion que se comprueba es la que se usa: no hay una segunda consulta al DNS
    entre comprobar y conectar (la ventana de un rebote)."""
    usadas = []

    def conectar(direccion, espera):
        usadas.append(direccion)
        return socket.create_connection(("127.0.0.1", eco.server_address[1]), espera)

    lista = salida.lista_blanca(["api.anthropic.com:443"])
    resolvedor = _Resolvedor({"api.anthropic.com": ["160.79.104.10"]})
    servidor = salida.Proxy(("127.0.0.1", 0), lista, resolver=resolvedor, conectar=conectar)
    with _en_marcha(servidor):
        cliente, respuesta = _pedir(servidor, _connect("api.anthropic.com", 443))
        cliente.close()
    assert respuesta.startswith(b"HTTP/1.1 200 ")
    assert usadas == [("160.79.104.10", 443)] and resolvedor.preguntas == ["api.anthropic.com"]


def test_http_en_claro_recibe_405(eco, caplog) -> None:
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    with _proxy(eco) as (proxy, resolvedor):
        cliente, respuesta = _pedir(
            proxy, b"GET http://api.anthropic.com/v1/messages HTTP/1.1\r\n"
                   b"Host: api.anthropic.com\r\nx-api-key: sk-ant-secreto\r\n\r\n")
        cliente.close()
    assert respuesta.startswith(b"HTTP/1.1 405 ") and b"Allow: CONNECT" in respuesta
    assert resolvedor.preguntas == [] and eco.conexiones == 0
    mensajes = " ".join(r.getMessage() for r in caplog.records)
    assert "codigo=405" in mensajes
    # Las cabeceras no se apuntan nunca: una clave que alguien mande en claro no acaba en el log.
    assert "sk-ant-secreto" not in mensajes


def test_una_cabecera_enorme_o_cortada_se_rechaza_y_se_apunta(eco, caplog) -> None:
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    with _proxy(eco) as (proxy, _r):
        cliente = socket.create_connection(proxy.server_address, timeout=5)
        cliente.sendall(b"CONNECT api.anthropic.com:443 HTTP/1.1\r\nX: " + b"a" * 9000)
        respuesta = cliente.recv(4096)
        cliente.close()
        cortada = socket.create_connection(proxy.server_address, timeout=5)
        cortada.sendall(b"CONNECT api.anth")
        cortada.shutdown(socket.SHUT_WR)
        respuesta_cortada = cortada.recv(4096)
        cortada.close()
    assert respuesta.startswith(b"HTTP/1.1 431 ")
    assert respuesta_cortada.startswith(b"HTTP/1.1 400 ")
    codigos = [r.getMessage() for r in caplog.records if "decision=rechazada" in r.getMessage()]
    assert len(codigos) == 2 and eco.conexiones == 0


def test_una_conexion_que_no_pide_nada_no_llena_el_registro(eco, caplog) -> None:
    """La comprobacion de salud de Docker abre y cierra: no es un intento de salir."""
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    with _proxy(eco) as (proxy, _r):
        socket.create_connection(proxy.server_address, timeout=5).close()
        assert salida.comprobar(f"127.0.0.1:{proxy.server_address[1]}")
    assert not [r for r in caplog.records if r.levelno >= logging.INFO]


def test_cada_intento_queda_en_el_registro(eco, caplog) -> None:
    caplog.set_level(logging.INFO, logger="bms_agent.salida")
    puerto = eco.server_address[1]
    with _proxy(eco) as (proxy, _r):
        for texto in (_connect("api.anthropic.com", puerto), _connect("example.com", 443),
                      _connect("10.0.0.1", 443), b"GET http://example.com/ HTTP/1.1\r\n\r\n"):
            cliente, _respuesta = _pedir(proxy, texto)
            cliente.close()
    decisiones = [r.getMessage() for r in caplog.records if "decision=" in r.getMessage()]
    assert len(decisiones) == 4
    assert [("permitida" in d) for d in decisiones] == [True, False, False, False]
    for texto, d in zip(("api.anthropic.com", "example.com", "10.0.0.1", "GET http://"),
                        decisiones):
        assert texto in d and "cliente=127.0.0.1:" in d


def test_si_el_destino_no_contesta_es_un_502(eco) -> None:
    libre = socket.socket()
    libre.bind(("127.0.0.1", 0))
    puerto_cerrado = libre.getsockname()[1]
    libre.close()
    with _proxy(eco, permitidos=[f"api.anthropic.com:{puerto_cerrado}"]) as (proxy, _r):
        cliente, respuesta = _pedir(proxy, _connect("api.anthropic.com", puerto_cerrado))
        cliente.close()
    assert respuesta.startswith(b"HTTP/1.1 502 ")


# ------------------------------------------------------------ la entrada a la consola

def test_el_reenvio_lleva_los_bytes_a_su_unico_destino(eco) -> None:
    destino = salida.Destino("127.0.0.1", eco.server_address[1])
    with _en_marcha(salida.Reenvio(("127.0.0.1", 0), destino, inactividad=5)) as reenvio:
        cliente = socket.create_connection(reenvio.server_address, timeout=5)
        cliente.sendall(b"GET /consola HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n\r\n")
        recibido = _recibir(cliente, 4)
        cliente.close()
    assert recibido.startswith(b"eco:") and eco.conexiones == 1


@pytest.mark.parametrize("texto, esperado", [
    ("0.0.0.0:8765=consola:8765", (("0.0.0.0", 8765), salida.Destino("consola", 8765))),
    ("127.0.0.1:9000=10.0.0.2:80", (("127.0.0.1", 9000), salida.Destino("10.0.0.2", 80))),
])
def test_como_se_escribe_un_reenvio(texto, esperado) -> None:
    assert salida.leer_reenvio(texto) == esperado


@pytest.mark.parametrize("texto", ["consola:8765", "0.0.0.0:8765=", "0.0.0.0=consola:8765",
                                   "0.0.0.0:8765=con sola:8765"])
def test_un_reenvio_mal_escrito_se_rechaza(texto) -> None:
    with pytest.raises(ValueError):
        salida.leer_reenvio(texto)


def test_escuchar_en_un_nombre_es_escuchar_en_su_ip() -> None:
    assert salida.direccion_de_escucha("0.0.0.0", 3128) == ("0.0.0.0", 3128)
    assert salida.direccion_de_escucha("localhost", 3128, intentos=1)[0].startswith("127.")
    with pytest.raises(OSError):
        salida.direccion_de_escucha("no-existe.invalid", 3128, intentos=1)


def test_la_cli_no_arranca_con_una_lista_mal_escrita(capsys) -> None:
    assert main(["salida", "--permitir", "1.2.3.4:443"]) == 2
    assert "IP" in capsys.readouterr().err
    assert main(["salida", "--reenviar", "consola:8765"]) == 2


def test_salud(eco, capsys) -> None:
    assert main(["salud", f"127.0.0.1:{eco.server_address[1]}"]) == 0
    libre = socket.socket()
    libre.bind(("127.0.0.1", 0))
    puerto = libre.getsockname()[1]
    libre.close()
    assert main(["salud", f"127.0.0.1:{puerto}"]) == 1
