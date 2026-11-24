"""El cliente de Microsoft Graph del correo de facturas (paso 18, diseno §2.2, §2.3, §3.1).

Solo lee. Lo unico que sabe hacer es:

- pedir el token del inquilino (client credentials con la asercion firmada por el certificado,
  sin msal): el unico POST, a login.microsoftonline.com;
- GET a graph.microsoft.com: la delta de una carpeta (la bandeja de entrada o "Correo no
  deseado"), la lista de adjuntos de un mensaje (sin su contenido) y el contenido de un
  adjunto de fichero; y, para `correo comprobar`, tres GET que dicen que solo puede leer ese
  buzon.

Nada de enviar, contestar, mover, marcar o borrar: el rol de Exchange es Application Mail.Read
y aqui no hay ningun otro metodo (lo comprueba un test sobre este fichero). Nunca se pide el
cuerpo de un mensaje (ni body, ni bodyPreview, ni uniqueBody, ni el MIME) y nunca se expande un
adjunto que es un correo (itemAttachment): lo que no se trae no puede inyectar nada.

Lo que llega es dato no confiable:

- cada respuesta JSON se lee por trozos con un tope (4 MiB) y cada adjunto con el suyo
  (correo.MAX_PDF), nunca entera en memoria;
- cada @odata.nextLink / @odata.deltaLink se comprueba antes de seguirlo (https, exactamente
  graph.microsoft.com, puerto 443, sin usuario, /v1.0/.../messages/delta, o .../attachments el
  de una lista de adjuntos) sin depender de la forma de su ruta, que Graph reescribe;
- los ids que van en una ruta solo pueden ser de base64 (los de Graph).

Lo que nunca sale de aqui: el token, la asercion, la cabecera Authorization, la consulta de un
enlace ($skiptoken, $deltatoken) ni la direccion del buzon. Los errores dicen que se pedia
("la lista de adjuntos"), el codigo HTTP y el codigo de error de Graph o el AADSTS, nada mas;
no se encadenan con los de httpx2 (que llevan la peticion entera): se lanzan fuera del except.
Los registros de httpx2 y httpcore2 (que apuntan cada URL con su consulta) se callan.

Microsoft limita: 429, 503 y 504 se reintentan como dice Graph (Retry-After hasta 120 s; sin
la cabecera, a los 2 s y a los 8 s); si no, `limitado`. Una peticion cada vez.

Sale por HTTPS_PROXY (en Docker, la salida del correo, cuya lista es solo
login.microsoftonline.com:443 y graph.microsoft.com:443: salida.DESTINOS_CORREO). En las pruebas
se le da un transporte falso (tests/graph_falso.py); en produccion, ninguno.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import IO, TYPE_CHECKING, Any, TypeVar
from urllib.parse import quote, unquote, urlsplit

import httpx2

from ..reloj import RELOJ_SISTEMA
from . import MAX_PDF, bandeja
from . import certificado as _certificado

if TYPE_CHECKING:
    from .ajustes import Ajustes

LOGIN = "login.microsoftonline.com"
GRAPH = "graph.microsoft.com"
_TOKEN = "https://login.microsoftonline.com/{inquilino}/oauth2/v2.0/token"
_USUARIOS = "https://graph.microsoft.com/v1.0/users"
AMBITO = "https://graph.microsoft.com/.default"
TIPO_ASERCION = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
# Lo que puede valer `aud` en un token de Graph (v1: la URL; o el id de la aplicacion Graph).
AUDIENCIAS = frozenset({"https://graph.microsoft.com", "https://graph.microsoft.com/",
                        "00000003-0000-0000-c000-000000000000"})

MAX_JSON = 4 * 1024 * 1024
MAX_TOKEN = 64 * 1024
MAX_ERROR = 64 * 1024
POR_PAGINA = 50
# Paginas de la lista de adjuntos de un mensaje que se siguen (si Graph la pagina: Learn no lo
# dice). Entre todas, como mucho MAX_JSON; lo que no cabe no se apunta, como lo que pasa de 50.
PAGINAS_ADJUNTOS = 10
# Graph limita (429/503/504): se espera lo que dice Retry-After si es esto o menos; sin la
# cabecera, estas esperas, una tras cada fallo. Despues, `limitado`.
ESPERA_MAXIMA = 120
REINTENTOS = (2, 8)
# El token dura 60-90 minutos; uno que caduca en menos de esto se renueva antes de usarlo.
MARGEN_TOKEN = timedelta(minutes=5)
PLAZOS = httpx2.Timeout(connect=15.0, read=60.0, write=30.0, pool=15.0)

CARPETAS_GRAPH = {"bandeja": "inbox", "no_deseado": "junkemail"}
CAMPOS_MENSAJE = ("id", "internetMessageId", "receivedDateTime", "hasAttachments", "subject",
                  "from")
CAMPOS_ADJUNTO = ("id", "name", "contentType", "size", "isInline")
PREFER_ID = 'IdType="ImmutableId"'
PREFER_DELTA = f"odata.maxpagesize={POR_PAGINA}, {PREFER_ID}"
# Lo que dice Graph de un delta que ya no vale (ademas del 410).
DELTA_CADUCADO = frozenset({"syncstatenotfound", "resyncrequired"})
# Los AADSTS de un reloj mal puesto: la asercion no esta en su plazo.
AADSTS_RELOJ = frozenset({700024})

_CODIGO_GRAPH = re.compile(r"[A-Za-z0-9_.]{1,64}")
_TOKEN_VALIDO = re.compile(r"[A-Za-z0-9._~+/=-]{1,16384}")
# Un numero de una cabecera o de una respuesta (Retry-After, Content-Length, expires_in): solo
# cifras ASCII (str.isdigit tambien da por cifras '²' o las arabes, que int() no lee o lee de
# otra forma).
_CIFRAS = re.compile(r"[0-9]+")

# httpx2 apunta cada peticion con su URL entera (la consulta lleva el $deltatoken) y httpcore2
# las cabeceras de la respuesta: en este proceso no se apunta nada de eso.
for _nombre in ("httpx2", "httpcore2"):
    logging.getLogger(_nombre).setLevel(logging.WARNING)

T = TypeVar("T")


class ErrorGraph(Exception):
    """Lo que no ha ido bien hablando con Microsoft, con su codigo de la lista cerrada del
    correo (bandeja.CODIGOS). El detalle no lleva ni el token, ni la asercion, ni una URL, ni
    la direccion del buzon."""

    def __init__(self, codigo: str, detalle: str, estado: int | None = None) -> None:
        if codigo not in bandeja.CODIGOS:
            raise ValueError("codigo de error del correo desconocido")
        super().__init__(f"{codigo}: {detalle}")
        self.codigo = codigo
        self.detalle = detalle
        self.estado = estado

    @property
    def para_la_ronda(self) -> bool:
        """Si no es cosa de una peticion sino de todas (sin red, la salida, la credencial, el
        reloj, Microsoft que pide esperar, un 403): la ronda para, y no cuenta contra el mensaje
        que se estaba trayendo. Un 403 es del buzon, no del mensaje (§3.7: `permiso`, "403 en el
        propio buzon"): el rol que no deja leer adjuntos (Application Mail.ReadBasic) o los
        permisos de Exchange que aun no han llegado; la ronda siguiente vuelve a comprobar. Un
        500 de un adjunto, un 404 (un mensaje que ya no esta) o una respuesta rara son de esa
        peticion."""
        return self.codigo in ("sin_conexion", "salida", "credencial", "reloj") or (
            self.codigo == "limitado" and self.estado in (None, 429, 503, 504)) or (
            self.codigo == "permiso" and self.estado == 403)


class RespuestaGrande(ErrorGraph):
    """Una respuesta JSON que pasa de su tope: fallo de ese mensaje, o de la ronda si es una
    pagina de la delta."""

    def __init__(self, que: str) -> None:
        super().__init__("interno", f"{que}: la respuesta de Graph pasa de "
                                    f"{MAX_JSON // (1024 * 1024)} MiB")


class DeltaCaducado(Exception):
    """El enlace de la delta ya no vale (410, syncStateNotFound, resyncRequired): hay que
    empezar otra vez con el filtro de fecha."""


@dataclass(frozen=True)
class Pagina:
    """Una pagina de la delta: los mensajes tal cual (no confiables) y el enlace que sigue
    (`siguiente`, otra pagina de esta ronda) o el de la ronda siguiente (`delta`)."""

    mensajes: list[Any]
    siguiente: str | None
    delta: str | None


@dataclass(frozen=True)
class Alcance:
    """Lo que dijo `correo comprobar` (§2.3): bien, o el codigo de por que no."""

    bien: bool
    motivo_codigo: str | None = None


@dataclass(frozen=True)
class Bajado:
    """Lo que se bajo de un adjunto: cuanto se recibio, cuanto se escribio y su sha256, si
    empieza por %PDF- y si se corto por pasar del tope."""

    recibidos: int
    escritos: int
    sha256: str
    es_pdf: bool
    cortado: bool


class _Token:
    """El token de una ronda: solo en memoria, sin repr que lo ensene ni copia."""

    __slots__ = ("_valor", "caduca", "carga")

    def __init__(self, valor: str, caduca: datetime, carga: dict | None) -> None:
        self._valor = valor
        self.caduca = caduca
        self.carga = carga

    def __repr__(self) -> str:
        return "<token de Graph>"

    def __reduce_ex__(self, _protocolo: object) -> object:
        raise TypeError("el token de Graph no se copia ni se guarda")


# ------------------------------------------------------------------ lo que llega

def enlace_valido(texto: object) -> bool:
    """Si un @odata.nextLink o @odata.deltaLink (o el enlace guardado) se puede seguir: https,
    host exactamente graph.microsoft.com, puerto 443 o ninguno, sin usuario ni contrasena, la
    ruta empieza por /v1.0/ y acaba en /messages/delta (sin mirar mayusculas: Graph reescribe la
    ruta, `.../users('x%40y')/mailfolders('AQMk...')/messages/delta`), sin tramos `.` o `..`, y
    nada que no sea ASCII visible."""
    return _enlace_de_graph(texto, "/messages/delta")


def enlace_de_adjuntos_valido(texto: object) -> bool:
    """Lo mismo para el @odata.nextLink de una lista de adjuntos: la ruta acaba en
    /attachments (nunca un $value ni otra cosa)."""
    return _enlace_de_graph(texto, "/attachments")


def _enlace_de_graph(texto: object, final: str) -> bool:
    if not isinstance(texto, str) or not 0 < len(texto) <= 8192:
        return False
    if any(not 0x21 <= ord(c) <= 0x7E for c in texto) or "\\" in texto or "#" in texto:
        return False
    try:
        partes = urlsplit(texto)
        puerto = partes.port
    except ValueError:
        return False
    if partes.scheme != "https" or "@" in partes.netloc or partes.hostname != GRAPH:
        return False
    if puerto not in (None, 443):
        return False
    ruta = partes.path.lower()
    if not ruta.startswith("/v1.0/") or not ruta.endswith(final):
        return False
    return not any(unquote(tramo) in ("", ".", "..") for tramo in ruta.split("/")[1:])


def id_valido(texto: object) -> bool:
    """Un id de Graph (mensaje o adjunto) que puede ir en una ruta."""
    return isinstance(texto, str) and bandeja.GRAPH_ID.fullmatch(texto) is not None


def _en_ruta(identificador: str) -> str:
    if not id_valido(identificador):
        raise ErrorGraph("interno", "un id de Graph con caracteres que no son de un id")
    return quote(identificador, safe="=-_")


def _json(cuerpo: bytes) -> Any:
    try:
        return json.loads(cuerpo.decode("utf-8"), parse_constant=_sin_constantes)
    except (ValueError, RecursionError):
        return None


def _sin_constantes(_nombre: str) -> object:
    raise ValueError("NaN o Infinity")


def _codigo_de_graph(cuerpo: bytes) -> str | None:
    """El codigo de error de una respuesta de Graph ({"error": {"code": ...}}), si es un
    codigo; nunca el mensaje (puede llevar la direccion del buzon)."""
    datos = _json(cuerpo)
    error = datos.get("error") if isinstance(datos, dict) else None
    codigo = error.get("code") if isinstance(error, dict) else None
    if isinstance(codigo, str) and _CODIGO_GRAPH.fullmatch(codigo):
        return codigo
    return None


def _aadsts(cuerpo: bytes) -> list[int]:
    """Los AADSTS de un error del token (error_codes, o los AADSTSnnnn de su descripcion)."""
    datos = _json(cuerpo)
    if not isinstance(datos, dict):
        return []
    lista = datos.get("error_codes")
    codigos = [c for c in lista if type(c) is int] if isinstance(lista, list) else []
    descripcion = datos.get("error_description")
    if isinstance(descripcion, str):
        codigos += [int(n) for n in re.findall(r"AADSTS([0-9]{1,9})", descripcion[:2000])]
    return codigos


def carga_del_token(valor: str) -> dict | None:
    """Lo que dice el token (la carga util del JWT, sin comprobar su firma: viene por TLS de
    Microsoft); None si no es un JWT que se pueda leer."""
    partes = valor.split(".")
    if len(partes) != 3:
        return None
    try:
        datos = base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4))
    except (binascii.Error, ValueError):
        return None
    carga = _json(datos)
    return carga if isinstance(carga, dict) else None


def _entero(texto: object, cifras: int) -> int | None:
    """Un numero de cifras ASCII; None si no lo es. Uno de mas de `cifras` cifras es "mucho":
    sale como 10**cifras (sin pasarlo entero a int, que con miles de cifras falla)."""
    if not isinstance(texto, str) or not _CIFRAS.fullmatch(texto):
        return None
    texto = texto.lstrip("0") or "0"
    return int(texto) if len(texto) <= cifras else 10 ** cifras


def _largo(respuesta: httpx2.Response) -> int | None:
    """El Content-Length, si dice un numero."""
    return _entero(respuesta.headers.get("content-length", "").strip(), 15)


def _leer(respuesta: httpx2.Response, tope: int, que: str, *, cortar: bool = False) -> bytes:
    """El cuerpo, por trozos, sin pasar de `tope`: si pasa, RespuestaGrande (o, con `cortar`,
    lo que cabe: para los errores, que solo se miran por su codigo)."""
    largo = _largo(respuesta)
    if not cortar and largo is not None and largo > tope:
        raise RespuestaGrande(que)
    datos = bytearray()
    for trozo in respuesta.iter_bytes():
        datos += trozo
        if len(datos) > tope:
            if cortar:
                return bytes(datos[:tope])
            raise RespuestaGrande(que)
    return bytes(datos)


def _guardar(respuesta: httpx2.Response, fichero: IO[bytes], tope: int) -> Bajado:
    """El contenido de un adjunto, por trozos, a `fichero`, sin pasar de `tope`."""
    resumen = hashlib.sha256()
    recibidos = escritos = 0
    cabeza = b""
    largo = _largo(respuesta)
    if largo is not None and largo > tope:
        return Bajado(0, 0, resumen.hexdigest(), False, True)
    for trozo in respuesta.iter_bytes():
        recibidos += len(trozo)
        if escritos + len(trozo) > tope:
            return Bajado(recibidos, escritos, resumen.hexdigest(), cabeza == b"%PDF-", True)
        fichero.write(trozo)
        resumen.update(trozo)
        escritos += len(trozo)
        if len(cabeza) < 5:
            cabeza = (cabeza + trozo)[:5]
    return Bajado(recibidos, escritos, resumen.hexdigest(), cabeza == b"%PDF-", False)


def _espera(cabecera: str | None, hechos: int) -> int | None:
    """Cuanto esperar antes de repetir una peticion limitada, o None si no se repite."""
    if hechos >= len(REINTENTOS):
        return None
    segundos = _entero((cabecera or "").strip(), 6)
    if segundos is None:
        return REINTENTOS[hechos]
    return segundos if segundos <= ESPERA_MAXIMA else None


def _por_estado(estado: int, codigo_graph: str | None, que: str) -> ErrorGraph:
    """El error de una respuesta de Graph que no es la esperada."""
    detalle = f"{que}: Graph contesta {estado}" + (f" ({codigo_graph})" if codigo_graph else "")
    if estado == 401:
        return ErrorGraph("credencial", detalle, estado)
    if estado in (403, 404):
        return ErrorGraph("permiso", detalle, estado)
    if estado >= 500:
        return ErrorGraph("limitado", detalle, estado)
    return ErrorGraph("interno", detalle, estado)


# ------------------------------------------------------------------ el cliente

class ClienteGraph:
    """Un cliente para una ronda (o una comprobacion) del correo. Uno a la vez: una peticion
    cada vez (Outlook admite 4 a la vez por buzon)."""

    def __init__(self, ajustes: Ajustes, credencial: _certificado.Credencial, *,
                 transporte: httpx2.BaseTransport | None = None,
                 ahora: Callable[[], datetime] = RELOJ_SISTEMA.ahora,
                 dormir: Callable[[float], None] = time.sleep) -> None:
        self._ajustes = ajustes
        self._credencial = credencial
        self._ahora = ahora
        self._dormir = dormir
        self._token: _Token | None = None
        self._buzon = f"{_USUARIOS}/{quote(ajustes.buzon, safe='@+')}"
        # Sin redirecciones (una respuesta 3xx es un error) y sin HTTP/2. El proxy sale de
        # HTTPS_PROXY (solo sin transporte: en las pruebas, ninguno).
        self._http = httpx2.Client(transport=transporte, timeout=PLAZOS, follow_redirects=False,
                                   headers={"User-Agent": "bms-agent-correo",
                                            "Accept-Encoding": "identity"})

    def __enter__(self) -> ClienteGraph:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.cerrar()

    def __repr__(self) -> str:
        return "<cliente de Graph del correo>"

    def cerrar(self) -> None:
        self._token = None
        self._http.close()

    # -------------------------------------------------------------- las peticiones

    def _con_reintentos(self, abrir: Callable[[], Any], leer: Callable[[httpx2.Response], T],
                        que: str) -> tuple[int, T]:
        """Hace la peticion (`abrir` da la respuesta por trozos) y lee su cuerpo con `leer`,
        repitiendola si Microsoft limita (429, 503, 504). Los errores de httpx2 se resumen en
        el codigo del correo, sin encadenarlos (llevan la peticion entera)."""
        hechos = 0
        while True:
            problema = espera = None
            try:
                with abrir() as respuesta:
                    estado = respuesta.status_code
                    if estado not in (429, 503, 504):
                        return estado, leer(respuesta)
                    espera = _espera(respuesta.headers.get("retry-after"), hechos)
                    if espera is None:
                        problema = ("limitado", f"{que}: Microsoft pide esperar ({estado})",
                                    estado)
            except httpx2.ProxyError:
                problema = ("salida", f"{que}: la salida del correo no deja pasar")
            except httpx2.TimeoutException:
                problema = ("sin_conexion", f"{que}: Microsoft no contesta a tiempo")
            except httpx2.TransportError as exc:
                problema = ("sin_conexion", f"{que}: sin conexion ({type(exc).__name__})")
            except (httpx2.HTTPError, httpx2.InvalidURL, httpx2.StreamError) as exc:
                problema = ("interno", f"{que}: {type(exc).__name__}")
            if problema is not None:
                raise ErrorGraph(*problema)
            assert espera is not None
            self._dormir(espera)
            hechos += 1

    def _token_nuevo(self) -> _Token:
        """Pide el token del inquilino con la asercion firmada (§2.2). El unico POST."""
        caducado = False
        try:
            asercion = self._credencial.asercion(self._ajustes.inquilino,
                                                 self._ajustes.aplicacion, ahora=self._ahora())
        except _certificado.CertificadoNoValido:
            caducado = True
        if caducado:
            raise ErrorGraph("credencial", "el certificado ha caducado o aun no vale (mira la "
                                           "hora del equipo): hace falta renovarlo")
        url = _TOKEN.format(inquilino=self._ajustes.inquilino)
        datos = {"client_id": self._ajustes.aplicacion, "scope": AMBITO,
                 "grant_type": "client_credentials", "client_assertion_type": TIPO_ASERCION,
                 "client_assertion": asercion}
        momento = self._ahora()
        estado, cuerpo = self._con_reintentos(
            lambda: self._http.stream("POST", url, data=datos,
                                      headers={"Accept": "application/json"}),
            lambda r: _leer(r, MAX_TOKEN if r.status_code == 200 else MAX_ERROR, "el token",
                            cortar=r.status_code != 200),
            "el token")
        del datos, asercion
        if estado in (400, 401):
            if AADSTS_RELOJ & set(_aadsts(cuerpo)):
                raise ErrorGraph("reloj", "Microsoft no acepta la hora de la asercion: mira la "
                                          "hora del equipo (AADSTS700024)")
            codigos = _aadsts(cuerpo)
            raise ErrorGraph("credencial", "Microsoft no acepta la credencial del correo"
                             + (f" (AADSTS{codigos[0]})" if codigos else f" ({estado})"))
        if estado != 200:
            raise _por_estado(estado, None, "el token")
        respuesta = _json(cuerpo)
        valor = respuesta.get("access_token") if isinstance(respuesta, dict) else None
        tipo = respuesta.get("token_type") if isinstance(respuesta, dict) else None
        vida = respuesta.get("expires_in") if isinstance(respuesta, dict) else None
        if isinstance(vida, str):
            vida = _entero(vida, 6)
        if (not isinstance(valor, str) or not _TOKEN_VALIDO.fullmatch(valor)
                or not isinstance(tipo, str) or tipo.lower() != "bearer"
                or type(vida) is not int or not 60 <= vida <= 86400):
            raise ErrorGraph("interno", "el token de Microsoft no tiene la forma esperada")
        return _Token(valor, momento + timedelta(seconds=vida), carga_del_token(valor))

    def _bearer(self, *, nuevo: bool = False) -> _Token:
        if nuevo or self._token is None or self._token.caduca - self._ahora() < MARGEN_TOKEN:
            self._token = None
            self._token = self._token_nuevo()
        return self._token

    def _get(self, url: str, leer: Callable[[httpx2.Response], T], que: str, *,
             prefer: str = PREFER_ID, aceptar: str = "application/json") -> tuple[int, T]:
        """Un GET a Graph con el token. El unico sitio que pide algo a Graph."""
        cabeceras = {"Authorization": "Bearer " + self._bearer()._valor, "Prefer": prefer,
                     "Accept": aceptar}
        return self._con_reintentos(lambda: self._http.stream("GET", url, headers=cabeceras),
                                    leer, que)

    def _get_json(self, url: str, que: str, *, prefer: str = PREFER_ID,
                  tope: int = MAX_JSON) -> tuple[int, bytes]:
        return self._get(url, lambda r: _leer(r, tope if r.status_code == 200 else MAX_ERROR,
                                              que, cortar=r.status_code != 200),
                         que, prefer=prefer)

    # -------------------------------------------------------------- comprobar (§2.3)

    def comprobar(self) -> Alcance:
        """Las cinco pruebas de §2.3: un token nuevo, que el token no trae permisos de Entra
        (`roles` ausente o vacio) y es de este inquilino y esta aplicacion para Graph, 200 en el
        buzon de las facturas, 403 en el de control y 403 en la lista de usuarios. Lo que no es
        un veredicto (sin conexion, Microsoft que limita, la salida) es ErrorGraph."""
        try:
            token = self._bearer(nuevo=True)
        except ErrorGraph as exc:
            if exc.codigo not in ("credencial", "reloj"):
                raise
            veredicto = exc.codigo
        else:
            veredicto = self._mirar_token(token)
        if veredicto is not None:
            return Alcance(False, veredicto)
        estado = self._estado(f"{self._buzon}/mailFolders/inbox?$select=id", "el buzon")
        if estado != 200:
            return Alcance(False, {401: "credencial", 403: "permiso", 404: "permiso"}.get(
                estado, "interno"))
        control = (f"{_USUARIOS}/{quote(self._ajustes.buzon_control, safe='@+')}"
                   "/mailFolders/inbox?$select=id")
        estado = self._estado(control, "el buzon de control")
        if estado != 403:
            return Alcance(False, {200: "alcance", 401: "credencial",
                                   404: "control_no_existe"}.get(estado, "interno"))
        estado = self._estado(f"{_USUARIOS}?$top=1&$select=id", "la lista de usuarios")
        if estado != 403:
            return Alcance(False, {200: "alcance", 401: "credencial"}.get(estado, "interno"))
        return Alcance(True)

    def _mirar_token(self, token: _Token) -> str | None:
        """Por que el token no vale para un buzon y solo lectura, o None si vale."""
        carga = token.carga
        if carga is None:
            return "interno"
        def minusculas(valor: object) -> object:
            return valor.lower() if isinstance(valor, str) else valor

        if (minusculas(carga.get("tid")) != self._ajustes.inquilino
                or minusculas(carga.get("appid", carga.get("azp"))) != self._ajustes.aplicacion
                or carga.get("aud") not in AUDIENCIAS):
            return "alcance"
        # Sin roles: ningun permiso de Entra, que valdria para todos los buzones.
        if carga.get("roles", []) not in ([], None):
            return "alcance"
        return None

    def _estado(self, url: str, que: str) -> int:
        return self._get_json(url, que)[0]

    # -------------------------------------------------------------- leer (§3.1)

    def primera(self, carpeta: str, desde: datetime) -> str:
        """La primera peticion de la delta de una carpeta, con el filtro de fecha (despues,
        los parametros van dentro del enlace)."""
        filtro = quote(f"receivedDateTime ge {bandeja.instante(desde)}", safe=":")
        return (f"{self._buzon}/mailFolders/{CARPETAS_GRAPH[carpeta]}/messages/delta"
                f"?changeType=created&$select={','.join(CAMPOS_MENSAJE)}&$filter={filtro}")

    def delta(self, carpeta: str, enlace: str | None, desde: datetime) -> Iterator[Pagina]:
        """Las paginas de la delta de una carpeta, desde `enlace` (el guardado) o, sin el, desde
        la primera peticion. Quien la recorre para cuando quiere; cada pagina trae el enlace con
        el que se sigue. DeltaCaducado si el enlace ya no vale."""
        que = "la delta de " + ("la bandeja" if carpeta == "bandeja" else "no deseado")
        url = self.primera(carpeta, desde) if enlace is None else enlace
        while True:
            if not enlace_valido(url):
                raise ErrorGraph("interno", f"{que}: un enlace que no es de Graph o no es de una "
                                            "delta; no se sigue")
            estado, cuerpo = self._get_json(url, que, prefer=PREFER_DELTA)
            if estado == 410:
                raise DeltaCaducado()
            if estado != 200:
                codigo = _codigo_de_graph(cuerpo)
                if codigo is not None and codigo.lower() in DELTA_CADUCADO:
                    raise DeltaCaducado()
                raise _por_estado(estado, codigo, que)
            pagina = _pagina(cuerpo, que)
            yield pagina
            if pagina.siguiente is None:
                return
            url = pagina.siguiente

    def adjuntos(self, mensaje_id: str) -> list[Any]:
        """La lista de adjuntos de un mensaje, sin su contenido ($select: id, nombre, tipo,
        tamano, en linea; @odata.type viene siempre). Tal cual: no confiable. Si Graph la
        pagina, se sigue su @odata.nextLink (comprobado, como los de la delta) hasta
        PAGINAS_ADJUNTOS paginas y, entre todas, MAX_JSON."""
        que = "la lista de adjuntos"
        url = (f"{self._buzon}/messages/{_en_ruta(mensaje_id)}/attachments"
               f"?$select={','.join(CAMPOS_ADJUNTO)}")
        lista: list[Any] = []
        leido = 0
        for _ in range(PAGINAS_ADJUNTOS):
            estado, cuerpo = self._get_json(url, que, tope=MAX_JSON - leido)
            if estado != 200:
                raise _por_estado(estado, _codigo_de_graph(cuerpo), que)
            leido += len(cuerpo)
            datos = _json(cuerpo)
            if not isinstance(datos, dict) or not isinstance(datos.get("value"), list):
                raise ErrorGraph("interno", f"{que}: no tiene la forma de Graph")
            lista += datos["value"]
            siguiente = datos.get("@odata.nextLink")
            if siguiente is None:
                break
            if not enlace_de_adjuntos_valido(siguiente):
                raise ErrorGraph("interno", f"{que}: un enlace que no es de Graph o no es de una "
                                            "lista de adjuntos; no se sigue")
            url = siguiente
        return lista

    def bajar(self, mensaje_id: str, adjunto_id: str, fichero: IO[bytes],
              tope: int = MAX_PDF) -> Bajado:
        """El contenido de un adjunto de fichero (fileAttachment), por trozos a `fichero`, sin
        pasar de `tope`. Nunca el de un itemAttachment ni el de un referenceAttachment."""
        que = "un adjunto"
        url = (f"{self._buzon}/messages/{_en_ruta(mensaje_id)}/attachments/"
               f"{_en_ruta(adjunto_id)}/$value")

        def leer(respuesta: httpx2.Response) -> Bajado | bytes:
            if respuesta.status_code != 200:
                return _leer(respuesta, MAX_ERROR, que, cortar=True)
            return _guardar(respuesta, fichero, tope)

        estado, resultado = self._get(url, leer, que, aceptar="*/*")
        if estado != 200 or not isinstance(resultado, Bajado):
            raise _por_estado(estado, _codigo_de_graph(resultado)
                              if isinstance(resultado, bytes) else None, que)
        return resultado


def _pagina(cuerpo: bytes, que: str) -> Pagina:
    datos = _json(cuerpo)
    if not isinstance(datos, dict) or not isinstance(datos.get("value"), list):
        raise ErrorGraph("interno", f"{que}: la pagina no tiene la forma de Graph")
    siguiente = datos.get("@odata.nextLink")
    delta = datos.get("@odata.deltaLink")
    if (siguiente is None) == (delta is None):
        raise ErrorGraph("interno", f"{que}: la pagina no dice como seguir")
    for enlace in (siguiente, delta):
        if enlace is not None and not enlace_valido(enlace):
            raise ErrorGraph("interno", f"{que}: un enlace que no es de Graph o no es de una "
                                        "delta; no se sigue")
    return Pagina(datos["value"], siguiente, delta)
