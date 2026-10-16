"""La unica salida a internet del entorno local: un proxy CONNECT con lista blanca.

En el entorno de Docker (docker/, docs/entorno-local.md) la consola y la
base no tienen red. El lector de PDF necesita hablar con la API de
Anthropic y con nada mas. Ese "nada mas" no se confia a que el codigo se
porte bien (arquitectura.md §6: una regla de salida es mas fiable que
confiar en que el codigo no llame a donde no debe): el contenedor del lector
esta en una red interna sin ruta a ningun sitio, y su unico camino es este
proxy, que corre en el unico contenedor con un pie en cada red.

Lo que hace, y por que:

- Solo CONNECT, y solo a un host:puerto de la lista (por defecto
  api.anthropic.com:443). Un GET en claro (http://...) se rechaza: lo que
  sale va cifrado de punta a punta y el proxy no lo lee.
- No intercepta TLS. Empalma los bytes y ya; no tiene certificados ni ve la
  clave de la API, que viaja dentro del tunel.
- El nombre se compara entero, despues de normalizarlo (minusculas, sin el
  punto final): "api.anthropic.com.evil.example" o "evilapi.anthropic.com"
  no son "api.anthropic.com". Una IP escrita a mano (tambien las formas
  raras, como 2130706433 o 0x7f.1) no esta nunca en la lista.
- El proxy resuelve el nombre el mismo y se conecta a la direccion que ha
  comprobado, no a otra: si el nombre resuelve a una direccion que no es
  publica (127.0.0.1, 10.x, 169.254.x...), se rechaza. Asi un DNS envenenado
  no convierte el proxy en un puente hacia la red de la casa.
- Cada intento queda en el registro (quien, a donde, que se decidio, cuanto
  paso por el tunel). Las cabeceras no se apuntan nunca.

Ademas lleva la entrada a la consola (`Reenvio`): Docker no publica un
puerto de un contenedor que solo esta en una red interna, asi que el puerto
de la consola (127.0.0.1:8765 en el ordenador del dueno) lo publica este
contenedor y lo reenvia tal cual a la consola. Es un reenvio fijo, a un solo
destino: no es un proxy y no decide nada.

Paso 14, la instalacion nativa de Windows (docs/instalacion-nativa.md): el mismo proxy,
en 127.0.0.1 y solo mientras dura una pasada de lectura. Alli no hay redes separadas: el
cortafuegos de Windows no filtra 127.0.0.1, y cualquier programa del ordenador (tambien
la consola) llegaria al proxy. Por eso, con una credencial (`clave`, que leer-facturas
saca al azar para cada pasada y solo dan a la salida y al lector), el proxy contesta 407
a quien no la trae (Proxy-Authorization: Basic). En Docker no se usa: alli la red ya
deja al lector solo. Alli tambien tiene una vida maxima (`vida`, --max-segundos): el script
que la arranca la para al acabar, pero si se cierra su ventana con la X, PowerShell muere
sin llegar a pararla, y la salida se apaga sola al cumplir su plazo.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import ipaddress
import logging
import os
import re
import selectors
import socket
import socketserver
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

PUERTO_PROXY = 3128
PERMITIDOS_POR_DEFECTO = ("api.anthropic.com:443",)
MAX_CABECERA = 8192
ESPERA_CABECERA = 10.0
ESPERA_CONEXION = 10.0
# Una peticion sin streaming a la API puede tardar minutos en dar el primer
# byte: el tunel no se corta por estar callado menos de esto.
INACTIVIDAD = 900.0
MAX_TUNELES = 32
# Conexiones que aun no han mandado su cabecera. Cada una ocupa un hilo hasta
# ESPERA_CABECERA: sin tope, mil conexiones que no dicen nada serian mil hilos.
MAX_ESPERANDO = 64

# Paso 14: la credencial de una pasada en la instalacion nativa. La variable lleva la
# credencial (la salida la lee al arrancar); el usuario es siempre este.
VARIABLE_CLAVE = "BMS_PROXY_CLAVE"
USUARIO_PROXY = "bms"
CLAVE_MINIMA = 16

registro = logging.getLogger("bms_agent.salida")

# El registro en un fichero del volumen de la salida: el de Docker se va con el
# contenedor (docker compose down en iniciar, parar y restaurar), y lo que ha
# salido a internet se mira una vez al mes. 10 ficheros de 5 MB.
REGISTRO_BYTES = 5 * 1024 * 1024
REGISTRO_COPIAS = 10
FORMATO_REGISTRO = "%(asctime)s %(message)s"

_ETIQUETA = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


@dataclass(frozen=True)
class Destino:
    host: str
    puerto: int

    def __str__(self) -> str:
        return f"{self.host}:{self.puerto}"


@dataclass(frozen=True)
class Decision:
    """Lo que se contesta a una peticion: el codigo, el porque y, si pasa, a donde va."""

    codigo: int
    motivo: str
    pedido: str
    destino: Destino | None = None

    @property
    def permitida(self) -> bool:
        return self.codigo == 200


def normalizar_host(texto: str) -> str | None:
    """Un nombre de host en minusculas y sin el punto final, o None si no es un nombre.

    Solo letras, cifras y guiones por etiqueta (lo que admite un nombre de
    DNS): un nombre con '@', '%', '/', espacios o una etiqueta vacia no se
    compara con nada, se rechaza.
    """
    host = texto.strip().lower()
    if host.endswith("."):
        host = host[:-1]
    if not host or len(host) > 253:
        return None
    if not all(_ETIQUETA.match(etiqueta) for etiqueta in host.split(".")):
        return None
    return host


def es_literal_ip(host: str) -> bool:
    """Si el texto es una direccion IP escrita a mano, en cualquiera de sus formas.

    inet_aton acepta las formas que acepta un navegador ("127.1",
    "2130706433", "0x7f000001"): todas son IP y ninguna un nombre.
    """
    limpio = host.strip().strip("[]")
    try:
        ipaddress.ip_address(limpio)
        return True
    except ValueError:
        pass
    try:
        socket.inet_aton(limpio)
        return True
    except OSError:
        return False


def leer_destino(texto: str) -> Destino:
    """Una entrada de la lista blanca, "host:puerto". ValueError si no lo es.

    El puerto es obligatorio y la entrada es un nombre: una IP o un comodin no
    se admiten en la lista, porque lo que se quiere permitir es un servicio y
    no una maquina que manana puede ser de otro.
    """
    host_texto, separador, puerto_texto = texto.strip().rpartition(":")
    if not separador or not puerto_texto.isdigit():
        raise ValueError(f"{texto!r}: se escribe host:puerto (api.anthropic.com:443)")
    puerto = int(puerto_texto)
    if not 1 <= puerto <= 65535:
        raise ValueError(f"{texto!r}: el puerto va de 1 a 65535")
    if "*" in host_texto or es_literal_ip(host_texto):
        raise ValueError(f"{texto!r}: la lista lleva nombres, no IP ni comodines")
    host = normalizar_host(host_texto)
    if host is None:
        raise ValueError(f"{texto!r}: no es un nombre de host")
    return Destino(host, puerto)


def lista_blanca(entradas: Iterable[str]) -> frozenset[Destino]:
    permitidos = frozenset(leer_destino(e) for e in entradas)
    if not permitidos:
        raise ValueError("la lista blanca esta vacia: el proxy no dejaria salir nada")
    return permitidos


def decidir(cabecera: bytes, permitidos: frozenset[Destino]) -> Decision:
    """Lo que se hace con una peticion, solo por su primera linea. Funcion pura.

    400 si no se entiende, 405 si no es CONNECT (HTTP en claro u otro
    metodo), 403 si el destino no esta en la lista y 200 si esta.
    """
    primera = cabecera.split(b"\r\n", 1)[0]
    try:
        linea = primera.decode("ascii")
    except UnicodeDecodeError:
        return Decision(400, "la peticion no es texto ASCII", repr(primera[:80]))
    partes = linea.split(" ")
    pedido = linea[:200]
    if len(partes) != 3 or not partes[2].startswith("HTTP/1."):
        return Decision(400, "la primera linea no es una peticion HTTP", pedido)
    metodo, objetivo, _version = partes
    if metodo != "CONNECT":
        return Decision(405, "solo se admite CONNECT: nada sale en claro", pedido)
    if "@" in objetivo or "/" in objetivo:
        return Decision(400, "el destino de un CONNECT es host:puerto", pedido)
    host_texto, separador, puerto_texto = objetivo.rpartition(":")
    if not separador or not puerto_texto.isdigit() or not 1 <= int(puerto_texto) <= 65535:
        return Decision(400, "el destino de un CONNECT es host:puerto", pedido)
    if host_texto.startswith("[") or es_literal_ip(host_texto):
        return Decision(403, "una IP no: solo nombres de la lista", pedido)
    host = normalizar_host(host_texto)
    if host is None:
        return Decision(403, "no es un nombre de host valido", pedido)
    destino = Destino(host, int(puerto_texto))
    if destino not in permitidos:
        return Decision(403, "no esta en la lista blanca", pedido)
    return Decision(200, "en la lista blanca", pedido, destino)


def credencial_valida(cabecera: bytes, clave: str, usuario: str = USUARIO_PROXY) -> bool:
    """Si la peticion trae Proxy-Authorization: Basic con usuario:clave. Funcion pura.

    Se compara en tiempo constante, y la cabecera no se apunta nunca (lleva la credencial).
    """
    for linea in cabecera.split(b"\r\n")[1:]:
        nombre, separador, valor = linea.partition(b":")
        if not separador or nombre.strip().lower() != b"proxy-authorization":
            continue
        esquema, _espacio, credencial = valor.strip().partition(b" ")
        if esquema.lower() != b"basic":
            return False
        try:
            texto = base64.b64decode(credencial.strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
        return hmac.compare_digest(texto, f"{usuario}:{clave}".encode("utf-8"))
    return False


def clave_del_entorno() -> str | None:
    """La credencial de la pasada (instalacion nativa), de BMS_PROXY_CLAVE; None si no hay."""
    return os.environ.get(VARIABLE_CLAVE) or None


def direcciones_no_publicas(direcciones: Iterable[str]) -> list[str]:
    """Las direcciones de la lista que no son de internet (privadas, locales, reservadas)."""
    malas = []
    for texto in direcciones:
        try:
            ip = ipaddress.ip_address(texto.split("%", 1)[0])
        except ValueError:
            malas.append(texto)
            continue
        if not ip.is_global:
            malas.append(texto)
    return malas


Resolver = Callable[[str, int], list[str]]


def resolver_dns(host: str, puerto: int) -> list[str]:
    """Las direcciones de un nombre, sin repetir y en el orden del sistema."""
    vistas: list[str] = []
    for *_resto, direccion in socket.getaddrinfo(host, puerto, type=socket.SOCK_STREAM):
        if direccion[0] not in vistas:
            vistas.append(direccion[0])
    return vistas


def _leer_cabecera(conexion: socket.socket, espera: float = ESPERA_CABECERA
                   ) -> tuple[bytes, bytes, str | None]:
    """La cabecera de la peticion, lo que vino detras (el principio del TLS, si el cliente no
    espero al 200) y, si no se pudo leer entera, por que: "vacia" (se cerro sin pedir
    nada), "incompleta" (se corto o tardo demasiado) o "larga" (mas de MAX_CABECERA).

    `espera` es para la cabecera entera, no para cada trozo: con un timeout por
    recv, un cliente que manda un byte cada pocos segundos tendria el hilo
    ocupado sin fin. Antes de cada recv el timeout es lo que queda del plazo.
    """
    datos = bytearray()
    limite = time.monotonic() + espera
    while b"\r\n\r\n" not in datos:
        if len(datos) > MAX_CABECERA:
            return bytes(datos[:200]), b"", "larga"
        queda = limite - time.monotonic()
        if queda <= 0:
            return bytes(datos[:200]), b"", "incompleta" if datos else "vacia"
        try:
            conexion.settimeout(queda)
            trozo = conexion.recv(4096)
        except OSError:
            trozo = b""
        if not trozo:
            return bytes(datos[:200]), b"", "incompleta" if datos else "vacia"
        datos += trozo
    cabecera, _sep, resto = bytes(datos).partition(b"\r\n\r\n")
    if len(cabecera) > MAX_CABECERA:
        return cabecera[:200], b"", "larga"
    return cabecera, resto, None


def _contestar(conexion: socket.socket, codigo: int, motivo: str) -> None:
    textos = {200: "Connection Established", 400: "Bad Request", 403: "Forbidden",
              405: "Method Not Allowed", 407: "Proxy Authentication Required",
              431: "Request Header Fields Too Large",
              502: "Bad Gateway", 503: "Service Unavailable"}
    cuerpo = b"" if codigo == 200 else (motivo + "\n").encode("utf-8")
    cabecera = f"HTTP/1.1 {codigo} {textos.get(codigo, 'Error')}\r\n"
    if codigo == 405:
        cabecera += "Allow: CONNECT\r\n"
    if codigo == 407:
        cabecera += 'Proxy-Authenticate: Basic realm="bms"\r\n'
    if codigo != 200:
        cabecera += ("Content-Type: text/plain; charset=utf-8\r\n"
                     f"Content-Length: {len(cuerpo)}\r\nConnection: close\r\n")
    try:
        conexion.sendall(cabecera.encode("ascii") + b"\r\n" + cuerpo)
    except OSError:
        pass


def empalmar(a: socket.socket, b: socket.socket, inactividad: float = INACTIVIDAD
             ) -> tuple[int, int]:
    """Copia bytes en los dos sentidos hasta que los dos lados terminan. Devuelve
    (de a hacia b, de b hacia a).

    Cuando un lado cierra su escritura se cierra la escritura del otro y se
    sigue leyendo en el otro sentido: una respuesta que llega despues de que el
    cliente haya terminado de enviar no se pierde.
    """
    hacia = {a: b, b: a}
    contados = {a: 0, b: 0}
    selector = selectors.DefaultSelector()
    selector.register(a, selectors.EVENT_READ)
    selector.register(b, selectors.EVENT_READ)
    abiertos = 2
    try:
        while abiertos:
            eventos = selector.select(timeout=inactividad)
            if not eventos:
                break
            for clave, _mascara in eventos:
                origen = clave.fileobj
                try:
                    datos = origen.recv(65536)
                except OSError:
                    datos = b""
                if not datos:
                    selector.unregister(origen)
                    abiertos -= 1
                    try:
                        hacia[origen].shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    continue
                try:
                    hacia[origen].sendall(datos)
                except OSError:
                    return contados[a], contados[b]
                contados[origen] += len(datos)
    finally:
        selector.close()
    return contados[a], contados[b]


class _Servidor(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, direccion: tuple[str, int], manejador: type, *,
                 max_tuneles: int = MAX_TUNELES) -> None:
        super().__init__(direccion, manejador)
        self.plazas = threading.BoundedSemaphore(max_tuneles)


class _ManejadorProxy(socketserver.BaseRequestHandler):
    server: Proxy

    def handle(self) -> None:
        conexion: socket.socket = self.request
        cliente = f"{self.client_address[0]}:{self.client_address[1]}"
        if not self.server.esperando.acquire(blocking=False):
            self.server.apuntar(cliente, "", "rechazada", 503,
                                "demasiadas conexiones esperando su cabecera")
            return
        try:
            cabecera, resto, problema = _leer_cabecera(conexion, self.server.espera_cabecera)
        finally:
            self.server.esperando.release()
        if problema == "vacia":
            # Una conexion que no pide nada (la comprobacion de salud de Docker) no
            # es un intento de salir: no llena el registro.
            registro.debug("salida cliente=%s sin peticion", cliente)
            return
        if problema is not None:
            pedido = cabecera.split(b"\r\n", 1)[0].decode("ascii", "replace")[:200]
            codigo = 431 if problema == "larga" else 400
            motivo = ("cabecera demasiado larga" if problema == "larga"
                      else "peticion incompleta o demasiado lenta")
            self.server.apuntar(cliente, pedido, "rechazada", codigo, motivo)
            _contestar(conexion, codigo, motivo)
            return
        if self.server.clave is not None and not credencial_valida(cabecera, self.server.clave):
            pedido = cabecera.split(b"\r\n", 1)[0].decode("ascii", "replace")[:200]
            motivo = "sin la credencial de esta pasada"
            self.server.apuntar(cliente, pedido, "rechazada", 407, motivo)
            _contestar(conexion, 407, motivo)
            return
        decision = decidir(cabecera, self.server.permitidos)
        if not decision.permitida:
            self.server.apuntar(cliente, decision.pedido, "rechazada", decision.codigo,
                                decision.motivo)
            _contestar(conexion, decision.codigo, decision.motivo)
            return
        if not self.server.plazas.acquire(blocking=False):
            self.server.apuntar(cliente, decision.pedido, "rechazada", 503,
                                "demasiados tuneles abiertos")
            _contestar(conexion, 503, "demasiados tuneles abiertos")
            return
        try:
            self._tunel(conexion, cliente, decision, resto)
        finally:
            self.server.plazas.release()

    def _tunel(self, conexion: socket.socket, cliente: str, decision: Decision,
               resto: bytes) -> None:
        destino = decision.destino
        assert destino is not None
        try:
            direcciones = self.server.resolver(destino.host, destino.puerto)
        except OSError as exc:
            self.server.apuntar(cliente, decision.pedido, "fallida", 502,
                                f"no se resuelve el nombre: {exc}")
            _contestar(conexion, 502, "no se resuelve el nombre")
            return
        malas = direcciones_no_publicas(direcciones) if self.server.solo_publicas else []
        if not direcciones or malas:
            motivo = ("resuelve a una direccion que no es de internet: " + ", ".join(malas)
                      if malas else "el nombre no tiene direcciones")
            self.server.apuntar(cliente, decision.pedido, "rechazada", 403, motivo)
            _contestar(conexion, 403, "el destino no resuelve a una direccion de internet")
            return
        remoto = None
        for direccion in direcciones:
            try:
                remoto = self.server.conectar((direccion, destino.puerto), ESPERA_CONEXION)
                break
            except OSError:
                continue
        if remoto is None:
            self.server.apuntar(cliente, decision.pedido, "fallida", 502,
                                "no se pudo conectar con el destino")
            _contestar(conexion, 502, "no se pudo conectar con el destino")
            return
        inicio = time.monotonic()
        self.server.apuntar(cliente, decision.pedido, "permitida", 200,
                            f"{decision.motivo}; conecta con {remoto.getpeername()[0]}")
        enviados = recibidos = 0
        try:
            conexion.settimeout(None)
            remoto.settimeout(None)
            _contestar(conexion, 200, "")
            if resto:
                remoto.sendall(resto)
            enviados, recibidos = empalmar(conexion, remoto, self.server.inactividad)
            enviados += len(resto)
        except OSError:
            pass
        finally:
            remoto.close()
            registro.info("salida cliente=%s pide=%r cierra enviados=%d recibidos=%d "
                          "segundos=%.1f", cliente, decision.pedido, enviados, recibidos,
                          time.monotonic() - inicio)


class Proxy(_Servidor):
    """El proxy de salida. `resolver` y `conectar` se inyectan en los tests (sockets locales),
    y `solo_publicas=False` solo lo usan ellos: en real, un destino tiene que resolver a una
    direccion de internet. Con `clave` (instalacion nativa) solo pasa quien la trae."""

    def __init__(self, direccion: tuple[str, int], permitidos: frozenset[Destino], *,
                 resolver: Resolver = resolver_dns,
                 conectar: Callable[..., socket.socket] = socket.create_connection,
                 solo_publicas: bool = True, inactividad: float = INACTIVIDAD,
                 espera_cabecera: float = ESPERA_CABECERA, max_tuneles: int = MAX_TUNELES,
                 max_esperando: int = MAX_ESPERANDO, clave: str | None = None) -> None:
        if clave is not None and len(clave) < CLAVE_MINIMA:
            raise ValueError(f"la credencial del proxy es demasiado corta (minimo {CLAVE_MINIMA})")
        super().__init__(direccion, _ManejadorProxy, max_tuneles=max_tuneles)
        self.clave = clave
        self.esperando = threading.BoundedSemaphore(max_esperando)
        self.espera_cabecera = espera_cabecera
        self.permitidos = permitidos
        self.resolver = resolver
        self.conectar = conectar
        self.solo_publicas = solo_publicas
        self.inactividad = inactividad

    def apuntar(self, cliente: str, pedido: str, decision: str, codigo: int,
                motivo: str) -> None:
        registro.info("salida cliente=%s pide=%r decision=%s codigo=%d motivo=%r",
                      cliente, pedido, decision, codigo, motivo)


class _ManejadorReenvio(socketserver.BaseRequestHandler):
    server: Reenvio

    def handle(self) -> None:
        conexion: socket.socket = self.request
        cliente = f"{self.client_address[0]}:{self.client_address[1]}"
        if not self.server.plazas.acquire(blocking=False):
            return
        try:
            try:
                remoto = socket.create_connection(
                    (self.server.destino.host, self.server.destino.puerto), ESPERA_CONEXION)
            except OSError as exc:
                registro.info("entrada cliente=%s hacia=%s no conecta: %s", cliente,
                              self.server.destino, exc)
                return
            remoto.settimeout(None)
            conexion.settimeout(None)
            try:
                enviados, recibidos = empalmar(conexion, remoto, self.server.inactividad)
            finally:
                remoto.close()
            registro.debug("entrada cliente=%s hacia=%s enviados=%d recibidos=%d", cliente,
                           self.server.destino, enviados, recibidos)
        finally:
            self.server.plazas.release()


class Reenvio(_Servidor):
    """La entrada a la consola: lo que llega a este puerto va tal cual a un unico destino."""

    def __init__(self, direccion: tuple[str, int], destino: Destino, *,
                 inactividad: float = INACTIVIDAD) -> None:
        super().__init__(direccion, _ManejadorReenvio)
        self.destino = destino
        self.inactividad = inactividad


def registrar_en_fichero(ruta: str | Path, *, max_bytes: int = REGISTRO_BYTES,
                        copias: int = REGISTRO_COPIAS) -> logging.Handler:
    """Apunta el registro de la salida tambien en `ruta`, anadiendo al final: lo de antes de
    parar y arrancar sigue ahi. Al llegar a max_bytes pasa a ruta.1 (y asi hasta `copias`)."""
    from logging.handlers import RotatingFileHandler

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    manejador = RotatingFileHandler(ruta, maxBytes=max_bytes, backupCount=copias,
                                    encoding="utf-8")
    manejador.setFormatter(logging.Formatter(FORMATO_REGISTRO))
    manejador.setLevel(logging.INFO)
    registro.addHandler(manejador)
    if registro.getEffectiveLevel() > logging.INFO:
        registro.setLevel(logging.INFO)
    return manejador


def leer_registro(ruta: str | Path, *, solo_rechazados: bool = False) -> list[str]:
    """Las lineas del registro de la salida, de la mas vieja a la mas nueva (ruta.N ... ruta.1,
    ruta). `solo_rechazados`: solo lo que no se dejo salir, que es lo que hay que mirar."""
    ruta = Path(ruta)
    rotados = sorted((p for p in ruta.parent.glob(f"{ruta.name}.*")
                      if p.suffix[1:].isdigit()), key=lambda p: -int(p.suffix[1:]))
    lineas: list[str] = []
    for fichero in [*rotados, ruta]:
        if fichero.is_file():
            lineas.extend(fichero.read_text(encoding="utf-8", errors="replace").splitlines())
    if solo_rechazados:
        lineas = [linea for linea in lineas if "decision=rechazada" in linea]
    return lineas


def leer_escucha(texto: str) -> tuple[str, int]:
    """Donde escucha un servidor, "host:puerto" (el host puede ser 0.0.0.0, una IP o un
    nombre, que se resuelve al arrancar)."""
    host, separador, puerto = texto.strip().rpartition(":")
    if not separador or not host or not puerto.isdigit() or not 0 <= int(puerto) <= 65535:
        raise ValueError(f"{texto!r}: se escribe host:puerto (0.0.0.0:3128)")
    return host, int(puerto)


def leer_reenvio(texto: str) -> tuple[tuple[str, int], Destino]:
    """Un reenvio "escucha=destino", por ejemplo 0.0.0.0:8765=consola:8765."""
    escucha, separador, destino = texto.partition("=")
    if not separador:
        raise ValueError(f"{texto!r}: se escribe ESCUCHA=DESTINO (0.0.0.0:8765=consola:8765)")
    host, puerto = leer_escucha(destino)
    if normalizar_host(host) is None and not es_literal_ip(host):
        raise ValueError(f"{texto!r}: el destino no es un host")
    return leer_escucha(escucha), Destino(host, puerto)


def direccion_de_escucha(host: str, puerto: int, *, intentos: int = 30,
                         pausa: float = 1.0) -> tuple[str, int]:
    """La IP en la que escuchar. Un nombre se resuelve (con reintentos: en Docker el DNS de
    la red puede tardar un momento): asi el proxy escucha solo en la red del lector, con el
    alias que esa red le da, y no en la de la consola."""
    if host in ("0.0.0.0", "") or es_literal_ip(host):
        return host or "0.0.0.0", puerto
    for intento in range(intentos):
        try:
            for familia, *_resto, direccion in socket.getaddrinfo(host, puerto,
                                                                  type=socket.SOCK_STREAM):
                if familia == socket.AF_INET:
                    return direccion[0], puerto
        except OSError:
            pass
        if intento + 1 < intentos:
            time.sleep(pausa)
    raise OSError(f"no se resuelve {host}: no se sabe en que red escuchar")


def comprobar(texto: str, espera: float = 3.0) -> bool:
    """La comprobacion de salud de un contenedor: que algo acepta conexiones en host:puerto."""
    host, puerto = leer_escucha(texto)
    try:
        with socket.create_connection((host, puerto), espera):
            return True
    except OSError:
        return False


def servir(escucha: str, permitidos: Iterable[str] = PERMITIDOS_POR_DEFECTO,
           reenvios: Iterable[str] = (), clave: str | None = None,
           vida: float | None = None) -> None:
    """Arranca el proxy y los reenvios y se queda atendiendo hasta que lo paran o, con
    `vida`, hasta que pasan esos segundos: entonces cierra y vuelve, con los tuneles que
    hubiera abiertos."""
    if vida is not None and vida <= 0:
        raise ValueError("la vida de la salida tiene que ser de mas de 0 segundos")
    limite = None if vida is None else time.monotonic() + vida
    lista = lista_blanca(permitidos)
    proxy = Proxy(direccion_de_escucha(*leer_escucha(escucha)), lista, clave=clave)
    servidores: list[_Servidor] = [proxy]
    for texto in reenvios:
        (host, puerto), destino = leer_reenvio(texto)
        servidores.append(Reenvio(direccion_de_escucha(host, puerto), destino))
    registro.info("salida escucha=%s:%d permitidos=%s credencial=%s vida=%s",
                  *proxy.server_address[:2], ",".join(sorted(map(str, lista))),
                  "si" if clave else "no", "sin limite" if vida is None else f"{vida:g}s")
    for servidor in servidores[1:]:
        registro.info("entrada escucha=%s:%d hacia=%s", *servidor.server_address[:2],
                      servidor.destino)
    hilos = [threading.Thread(target=s.serve_forever, daemon=True) for s in servidores]
    for hilo in hilos:
        hilo.start()
    try:
        while all(h.is_alive() for h in hilos):
            if limite is not None:
                queda = limite - time.monotonic()
                if queda <= 0:
                    registro.info("salida se para: ha cumplido su vida de %gs", vida)
                    break
                time.sleep(min(1.0, queda))
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for servidor in servidores:
            servidor.shutdown()
            servidor.server_close()
