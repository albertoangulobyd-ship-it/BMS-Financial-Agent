"""La comprobacion de aislamiento de la instalacion nativa (paso 14, `comprobar-aislamiento`).

En Docker el aislamiento lo dan las redes: un contenedor en una red interna no
tiene por donde salir. En la instalacion nativa de Windows lo dan unas reglas del
cortafuegos por programa (docs/instalacion-nativa.md), y una regla que falta, un
cortafuegos apagado o un antivirus que lo sustituye no se ven a simple vista. Esta
comprobacion no se fia de la configuracion: lo intenta. Cada papel (consola, lector,
salida, orden) corre con su propio programa y prueba a salir:

- a una lista fija de destinos de internet (1.1.1.1:443, 8.8.8.8:53 por TCP y por UDP,
  1.1.1.1:80 y api.anthropic.com:443). La consola, el lector y las ordenes no pueden
  llegar a ninguno; la salida solo al puerto 443;
- el lector, ademas, tiene que llegar al proxy de la salida, y por el solo a
  api.anthropic.com:443: otro destino, otro puerto o una IP tienen que recibir un no, y
  sin la credencial de esta pasada tambien;
- en la instalacion, el codigo (app, lib, runtime) no se puede escribir y los datos y el
  buzon si.

El resultado va a datos/aislamiento.json, con la hora y el papel. La consola pinta una
banda roja si falta o falla alguno (`problemas`), y una pasada de lectura no se hace si
la comprobacion del lector y de la salida de esa misma pasada no salio bien
(`motivo_para_no_leer`): falla cerrada.

Lo que no puede probar (y la guia lo dice): que el programa no lance otro programa sin
reglas (eso lo vigila un test del codigo), y las consultas de nombres, que en Windows
hace un servicio del sistema y no el programa.

Solo abre conexiones a esa lista fija y al proxy local, no manda nada mas que la peticion
CONNECT y una consulta DNS de example.com, y cierra cada una en seguida.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROLES = ("consola", "lector", "salida", "orden")
FICHERO = "aislamiento.json"
VERSION = 1

ESPERA = 2.0
# El proxy tarda en contestar lo que tarda en conectar con la API (salida.ESPERA_CONEXION).
ESPERA_API = 12.0
# La banda de la consola: una comprobacion vieja tambien es una comprobacion que falta.
CADUCIDAD = timedelta(days=90)
# Una pasada de lectura solo vale con la comprobacion de esa misma pasada, y de hace poco.
VIGENCIA_LECTURA = timedelta(minutes=60)
DESFASE = timedelta(minutes=5)

API = "api.anthropic.com:443"
USUARIO_PROXY = "bms"

CONECTA = "conecta"
NO_CONECTA = "no conecta"
NO_RESUELVE = "no resuelve el nombre"
CONTESTA = "contesta"
NO_CONTESTA = "no contesta"
BLOQUEADOS = (NO_CONECTA, NO_RESUELVE, NO_CONTESTA)

_DE = {"consola": "de la consola", "lector": "del lector", "salida": "de la salida",
       "orden": "de las ordenes"}


def de(rol: str) -> str:
    """"de la consola", "del lector": para decirlo en claro."""
    return _DE.get(rol, f"de {rol}")


@dataclass(frozen=True)
class Sonda:
    """Un destino de internet al que se prueba a llegar sin pasar por el proxy."""

    nombre: str
    host: str
    puerto: int
    protocolo: str = "tcp"


EXTERNOS = (
    Sonda("1.1.1.1:443 (TCP)", "1.1.1.1", 443),
    Sonda("8.8.8.8:53 (TCP)", "8.8.8.8", 53),
    Sonda("8.8.8.8:53 (UDP, DNS)", "8.8.8.8", 53, "udp-dns"),
    Sonda("1.1.1.1:80 (TCP)", "1.1.1.1", 80),
    Sonda("api.anthropic.com:443 (TCP)", "api.anthropic.com", 443),
)

# Lo que el lector pide al proxy y tiene que recibir un no: otro nombre, el de la API con
# otro puerto, una IP y un nombre que solo empieza como el de la API.
PROHIBIDOS_POR_EL_PROXY = ("example.com:443", "api.anthropic.com:80", "1.1.1.1:443",
                           "api.anthropic.com.evil.example:443")


@dataclass(frozen=True)
class Comprobacion:
    """Una prueba: lo que tiene que pasar, lo que paso y si esta bien. Una que no es
    `grave` es un aviso: se dice, pero no cuenta para el aislamiento."""

    nombre: str
    esperado: str
    obtenido: str
    bien: bool
    grave: bool = True


@dataclass(frozen=True)
class Informe:
    rol: str
    fecha: str
    comprobaciones: tuple[Comprobacion, ...]
    sesion: str | None = None
    programa: str = ""

    @property
    def correcto(self) -> bool:
        """Bien si hay pruebas y ninguna grave falla: sin pruebas no se ha comprobado nada."""
        return bool(self.comprobaciones) and all(c.bien for c in self.comprobaciones if c.grave)

    def a_dict(self) -> dict[str, Any]:
        return {"rol": self.rol, "fecha": self.fecha, "correcto": self.correcto,
                "sesion": self.sesion, "programa": self.programa,
                "comprobaciones": [asdict(c) for c in self.comprobaciones]}


@dataclass
class Observaciones:
    """Lo que se vio al probar, sin juzgarlo todavia (lo juzga `evaluar`)."""

    directas: dict[str, str] = field(default_factory=dict)
    proxy_alcanzable: bool | None = None
    con_credencial: dict[str, int | None] = field(default_factory=dict)
    sin_credencial: dict[str, int | None] = field(default_factory=dict)
    escritura: dict[str, bool] = field(default_factory=dict)


# ------------------------------------------------------------ las pruebas, una a una

Conectar = Callable[..., socket.socket]


def probar_tcp(host: str, puerto: int, espera: float = ESPERA,
               conectar: Conectar = socket.create_connection) -> str:
    """Si se abre una conexion TCP con host:puerto. Se cierra en seguida, sin mandar nada."""
    try:
        conexion = conectar((host, puerto), espera)
    except socket.gaierror:
        return NO_RESUELVE
    except OSError:
        return NO_CONECTA
    conexion.close()
    return CONECTA


def consulta_dns(nombre: str = "example.com", ident: int = 0x424D) -> bytes:
    """Una consulta DNS de tipo A, la mas pequena que contesta cualquier servidor."""
    cabecera = struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0)
    pregunta = b"".join(bytes([len(e)]) + e.encode("ascii") for e in nombre.split("."))
    return cabecera + pregunta + b"\x00" + struct.pack(">HH", 1, 1)


def probar_dns_udp(host: str, puerto: int, espera: float = ESPERA,
                   crear: Callable[..., socket.socket] = socket.socket) -> str:
    """Si un servidor DNS contesta por UDP. Un cortafuegos que bloquea no contesta nada (o el
    envio falla en el acto); no hay conexion que se pueda rechazar."""
    try:
        with crear(socket.AF_INET, socket.SOCK_DGRAM) as conexion:
            conexion.settimeout(espera)
            conexion.sendto(consulta_dns(), (host, puerto))
            datos, _origen = conexion.recvfrom(512)
    except OSError:
        return NO_CONTESTA
    return CONTESTA if datos else NO_CONTESTA


def credencial_basica(clave: str, usuario: str = USUARIO_PROXY) -> str:
    return base64.b64encode(f"{usuario}:{clave}".encode("utf-8")).decode("ascii")


def pedir_tunel(proxy: tuple[str, int], destino: str, credencial: str | None,
                espera: float = ESPERA, conectar: Conectar = socket.create_connection
                ) -> int | None:
    """El codigo con que contesta el proxy a un CONNECT, o None si no se llega a el o no
    contesta. Si dice que si (200), el tunel se cierra sin mandar nada por el."""
    peticion = f"CONNECT {destino} HTTP/1.1\r\nHost: {destino}\r\n"
    if credencial is not None:
        peticion += f"Proxy-Authorization: Basic {credencial_basica(credencial)}\r\n"
    datos = b""
    try:
        with conectar(proxy, espera) as conexion:
            conexion.settimeout(espera)
            conexion.sendall((peticion + "\r\n").encode("ascii"))
            while b"\r\n" not in datos and len(datos) < 4096:
                trozo = conexion.recv(1024)
                if not trozo:
                    break
                datos += trozo
    except OSError:
        if not datos:
            return None
    partes = datos.split(b"\r\n", 1)[0].split()
    if len(partes) >= 2 and partes[0].startswith(b"HTTP/") and partes[1].isdigit():
        return int(partes[1])
    return None


def se_puede_escribir(carpeta: Path) -> bool:
    """Si este programa puede crear un fichero en la carpeta (lo crea y lo borra)."""
    try:
        descriptor, nombre = tempfile.mkstemp(prefix=".bms-prueba-", dir=carpeta)
    except OSError:
        return False
    os.close(descriptor)
    try:
        os.unlink(nombre)
    except OSError:
        pass
    return True


# ------------------------------------------------------------ el juicio

def _codigo(codigo: int | None) -> str:
    return "no contesta" if codigo is None else f"contesta {codigo}"


def evaluar(rol: str, vistas: Observaciones, sondas: Iterable[Sonda] = EXTERNOS,
            *, escribibles: Iterable[str] = ("datos", "buzon")) -> tuple[Comprobacion, ...]:
    """Lo que se vio, juzgado segun el papel. Funcion pura: es la regla del aislamiento.

    - consola, lector y orden: ningun destino de internet, por ningun protocolo;
    - salida: nada que no sea TCP al 443 (llegar a la API es lo normal, y no llegar es un
      aviso: sin internet tampoco se puede leer);
    - lector: el proxy se alcanza, por el con la credencial la API dice que si, cualquier
      otro destino dice que no, y sin la credencial tambien no;
    - consola y orden, si se les da el proxy: sin credencial no pasan;
    - el codigo no se puede escribir; los datos y el buzon si (si no, es un aviso: no es
      una fuga, pero nada funcionaria).
    """
    if rol not in ROLES:
        raise ValueError(f"{rol!r} no es un papel ({', '.join(ROLES)})")
    salida: list[Comprobacion] = []
    for sonda in sondas:
        obtenido = vistas.directas.get(sonda.nombre)
        if obtenido is None:
            continue
        if rol == "salida" and sonda.protocolo == "tcp" and sonda.puerto == 443:
            salida.append(Comprobacion(
                f"directo a {sonda.nombre}", "conecta (la salida sale por el 443)", obtenido,
                obtenido == CONECTA, grave=False))
        else:
            salida.append(Comprobacion(
                f"directo a {sonda.nombre}", "bloqueado", obtenido, obtenido in BLOQUEADOS))
    if rol == "lector":
        # Sin proxy no se ha probado lo que mas importa del lector: falla, no se da por bueno.
        obtenido = ("sin probar (no se ha dado el proxy)" if vistas.proxy_alcanzable is None
                    else CONECTA if vistas.proxy_alcanzable else NO_CONECTA)
        salida.append(Comprobacion("llegar al proxy de la salida", "conecta", obtenido,
                                   vistas.proxy_alcanzable is True))
    for destino, codigo in vistas.con_credencial.items():
        if destino == API:
            if codigo == 200:
                salida.append(Comprobacion(f"por el proxy a {destino}", "contesta 200",
                                           _codigo(codigo), True))
            elif codigo in (None, 502):
                # El proxy lo dejaria pasar, pero la API no contesta: sin internet. No es una
                # fuga; la lectura fallara sola.
                salida.append(Comprobacion(f"por el proxy a {destino}", "contesta 200",
                                           _codigo(codigo), False, grave=False))
            else:
                salida.append(Comprobacion(f"por el proxy a {destino}", "contesta 200",
                                           _codigo(codigo), False))
        else:
            salida.append(Comprobacion(f"por el proxy a {destino}", "no pasa (403)",
                                       _codigo(codigo), codigo != 200))
    for destino, codigo in vistas.sin_credencial.items():
        salida.append(Comprobacion(f"por el proxy a {destino} sin la credencial",
                                   "no pasa (407)", _codigo(codigo), codigo != 200))
    for nombre, puede in vistas.escritura.items():
        if nombre in escribibles:
            salida.append(Comprobacion(f"escribir en {nombre}", "se puede",
                                       "se puede" if puede else "no se puede", puede,
                                       grave=False))
        else:
            salida.append(Comprobacion(f"escribir en {nombre}", "no se puede (codigo)",
                                       "se puede" if puede else "no se puede", not puede))
    return tuple(salida)


# ------------------------------------------------------------ todo junto

def observar(rol: str, *, proxy: tuple[str, int] | None = None, credencial: str | None = None,
             sondas: Iterable[Sonda] = EXTERNOS, espera: float = ESPERA,
             espera_api: float = ESPERA_API, carpetas: Mapping[str, Path] | None = None,
             conectar: Conectar = socket.create_connection,
             crear_udp: Callable[..., socket.socket] = socket.socket,
             escribir: Callable[[Path], bool] | None = None) -> Observaciones:
    """Hace las pruebas a la vez (cada una tiene su plazo corto): lo que tarda es el plazo,
    no la suma de todos."""
    sondas = tuple(sondas)
    escribir = escribir or se_puede_escribir
    vistas = Observaciones()
    with ThreadPoolExecutor(max_workers=16) as hilos:
        directas = {
            s.nombre: (hilos.submit(probar_dns_udp, s.host, s.puerto, espera, crear_udp)
                       if s.protocolo == "udp-dns"
                       else hilos.submit(probar_tcp, s.host, s.puerto, espera, conectar))
            for s in sondas}
        alcanzable = con = sin = None
        if proxy is not None and rol != "salida":
            if rol == "lector":
                alcanzable = hilos.submit(probar_tcp, proxy[0], proxy[1], espera, conectar)
                con = {d: hilos.submit(pedir_tunel, proxy, d, credencial,
                                       espera_api if d == API else espera, conectar)
                       for d in (API, *PROHIBIDOS_POR_EL_PROXY)}
            sin = {API: hilos.submit(pedir_tunel, proxy, API, None, espera, conectar)}
        vistas.directas = {nombre: f.result() for nombre, f in directas.items()}
        if alcanzable is not None:
            vistas.proxy_alcanzable = alcanzable.result() == CONECTA
        if con is not None:
            vistas.con_credencial = {d: f.result() for d, f in con.items()}
        if sin is not None:
            vistas.sin_credencial = {d: f.result() for d, f in sin.items()}
    for nombre, carpeta in (carpetas or {}).items():
        vistas.escritura[nombre] = escribir(carpeta)
    return vistas


def comprobar(rol: str, *, ahora: datetime | None = None, sesion: str | None = None,
              programa: str = "", **opciones: Any) -> Informe:
    """Prueba y juzga. `opciones` son las de `observar` (el proxy, la credencial, las sondas,
    las carpetas y, en los tests, como se conecta)."""
    sondas = tuple(opciones.pop("sondas", EXTERNOS))
    vistas = observar(rol, sondas=sondas, **opciones)
    fecha = (ahora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return Informe(rol, fecha, evaluar(rol, vistas, sondas), sesion, programa)


def formatear(informe: Informe) -> str:
    """El resultado en claro, una linea por prueba y el veredicto al final."""
    lineas = [f"Comprobacion de aislamiento {de(informe.rol)}"]
    for c in informe.comprobaciones:
        marca = "bien " if c.bien else ("MAL  " if c.grave else "aviso")
        lineas.append(f"  {marca}  {c.nombre}: {c.obtenido} (tiene que: {c.esperado})")
    if informe.correcto:
        lineas.append(f"Aislamiento {de(informe.rol)}: BIEN")
    else:
        malas = [c.nombre for c in informe.comprobaciones if c.grave and not c.bien]
        lineas.append(f"Aislamiento {de(informe.rol)}: MAL ({'; '.join(malas)})")
    return "\n".join(lineas)


# ------------------------------------------------------------ el fichero de resultados

def leer(ruta: str | Path) -> dict[str, Any]:
    """Lo apuntado, o un resultado vacio si no hay fichero o no se entiende (y entonces cada
    papel cuenta como sin comprobar)."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {"version": VERSION, "roles": {}}
    if not isinstance(datos, dict) or not isinstance(datos.get("roles"), dict):
        return {"version": VERSION, "roles": {}}
    return datos


def guardar(ruta: str | Path, informe: Informe, *, intentos: int = 20) -> None:
    """Apunta el resultado de un papel sin tocar los de los demas.

    Se escribe aparte y se cambia de nombre: quien lo lee a la vez (la consola) ve el de
    antes o el de ahora, nunca medio. En Windows el cambio de nombre falla mientras otro
    proceso tiene el fichero abierto; se reintenta un momento.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = leer(ruta)
    datos["version"] = VERSION
    datos["roles"][informe.rol] = informe.a_dict()
    texto = json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True)
    descriptor, temporal = tempfile.mkstemp(prefix=".aislamiento-", dir=ruta.parent)
    with os.fdopen(descriptor, "w", encoding="utf-8") as fichero:
        fichero.write(texto)
    for intento in range(intentos):
        try:
            os.replace(temporal, ruta)
            return
        except PermissionError:
            if intento + 1 == intentos:
                os.unlink(temporal)
                raise
            time.sleep(0.05)


def _fecha(texto: Any) -> datetime | None:
    if not isinstance(texto, str):
        return None
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return fecha if fecha.tzinfo is not None else None


def _malas(entrada: Mapping[str, Any]) -> list[str]:
    comprobaciones = entrada.get("comprobaciones")
    if not isinstance(comprobaciones, list):
        return []
    return [str(c.get("nombre")) for c in comprobaciones
            if isinstance(c, dict) and c.get("grave", True) and not c.get("bien")]


def _bien(entrada: Mapping[str, Any]) -> bool:
    """Bien de verdad: lo dice, tiene pruebas y ninguna grave lo contradice."""
    comprobaciones = entrada.get("comprobaciones")
    return (entrada.get("correcto") is True and isinstance(comprobaciones, list)
            and bool(comprobaciones) and not _malas(entrada))


def problemas_de(datos: Mapping[str, Any], ahora: datetime, *, roles: Iterable[str] = ROLES,
                 caducidad: timedelta = CADUCIDAD) -> list[str]:
    """Lo que la consola dice en su banda roja: cada papel sin comprobar, con una prueba que
    falla, o comprobado hace demasiado. Lista vacia: todo en verde. Funcion pura."""
    entradas = datos.get("roles") if isinstance(datos.get("roles"), dict) else {}
    salida = []
    for rol in roles:
        entrada = entradas.get(rol)
        if not isinstance(entrada, dict):
            salida.append(f"{rol}: sin comprobar")
            continue
        if not _bien(entrada):
            malas = _malas(entrada)
            salida.append(f"{rol}: FALLA ({'; '.join(malas[:3]) or 'sin detalle'})")
            continue
        fecha = _fecha(entrada.get("fecha"))
        if fecha is None or fecha > ahora + DESFASE:
            salida.append(f"{rol}: la fecha de la comprobacion no vale")
        elif ahora - fecha > caducidad:
            salida.append(f"{rol}: comprobado por ultima vez hace {(ahora - fecha).days} dias")
    return salida


def problemas(ruta: str | Path, ahora: datetime | None = None) -> list[str]:
    return problemas_de(leer(ruta), ahora or datetime.now(timezone.utc))


def motivo_para_no_leer_de(datos: Mapping[str, Any], sesion: str, ahora: datetime, *,
                           vigencia: timedelta = VIGENCIA_LECTURA) -> str | None:
    """Por que no se puede hacer una pasada de lectura, o None si se puede. Funcion pura.

    Hace falta la comprobacion del lector y la de la salida, las dos bien, las dos de esta
    pasada (`sesion`: la huella de la credencial del proxy que se arranco para ella) y de
    hace menos de `vigencia`. Una que falta cuenta como una que falla.
    """
    entradas = datos.get("roles") if isinstance(datos.get("roles"), dict) else {}
    for rol in ("salida", "lector"):
        entrada = entradas.get(rol)
        if not isinstance(entrada, dict):
            return f"falta la comprobacion de aislamiento {de(rol)}"
        if not _bien(entrada):
            return (f"la comprobacion de aislamiento {de(rol)} ha fallado: "
                    f"{'; '.join(_malas(entrada)) or 'sin detalle'}")
        if entrada.get("sesion") != sesion:
            return f"la comprobacion de aislamiento {de(rol)} no es de esta pasada"
        fecha = _fecha(entrada.get("fecha"))
        if fecha is None or fecha > ahora + DESFASE or ahora - fecha > vigencia:
            return (f"la comprobacion de aislamiento {de(rol)} es de hace mas de "
                    f"{int(vigencia.total_seconds() // 60)} minutos")
    return None


def motivo_para_no_leer(ruta: str | Path, sesion: str, ahora: datetime | None = None
                        ) -> str | None:
    return motivo_para_no_leer_de(leer(ruta), sesion, ahora or datetime.now(timezone.utc))
