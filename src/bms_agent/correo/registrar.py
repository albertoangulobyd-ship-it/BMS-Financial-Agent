"""`correo registrar` (paso 18, diseno §3.8): lo que trajo el correo, a la base. Corre en `orden`.

El componente `correo` deja en su bandeja lo que trae del buzon (correo/bandeja.py) y no abre
la base. Esto lo registra, sin red y con el usuario de sistema `correo`, y trata TODO lo de la
bandeja como no confiable: lo escribio un proceso que lee correo de desconocidos.

1. Las tres carpetas fijas (entrada/llegadas, entrada/pdf y estado) se miran con lstat y se
   abren con O_DIRECTORY | O_NOFOLLOW; lo de dentro se mira, se abre y se borra relativo a ese
   descriptor (dir_fd): cambiar una carpeta por un enlace a mitad no lleva a otra parte. Una
   carpeta que no es una carpeta de verdad no se toca (y queda `interno`).
2. Solo nombres <sha256>.json y <sha256>.pdf; los demas se ignoran, y ninguna ruta sale de otro
   texto. Como mucho POR_PASADA entradas por pasada, las mas antiguas primero.
3. Cada fichero: lstat, fichero normal, O_NOFOLLOW, tope de tamano (64 KiB una llegada, MAX_PDF un
   PDF).
4. La llegada, JSON estricto (version, claves y tipos exactos, longitudes, el nombre del fichero
   = sha256(graph_id|carpeta)). Una que llego mas de 5 minutos "en el futuro" (el reloj de este
   equipo va atrasado) no se registra todavia: se queda, y el correo dice `reloj`. Antes del
   2000, el documento entra sin fecha (recibido_fuente desconocido).
5. Cada PDF: sus bytes tienen ese sha256 y empiezan por %PDF-; entra en el almacen con
   origen 'correo' (registrar_documento). Si ya estaba, no cambia: la llegada queda igual en
   adjunto_correo. Uno de los datos de prueba da `de_prueba`; uno que no esta o no casa, `error`.
6. Un mensaje entero (mensaje_correo, sus adjunto_correo, sus documentos y su evento
   correo_mensaje_registrado) va en una transaccion. Uno malo no para los demas.
7. Acuse: tras la transaccion se borra de la bandeja la llegada y cada PDF suyo (unlink relativo
   a la carpeta: borra la entrada, nunca sigue un enlace). Lo rechazado se borra tambien. Un PDF
   suelto cuyo sha256 ya esta en la base, tambien.
8. estado.json, validado igual, a estado_correo (la cache) y, si la ronda trajo algo o el codigo
   de error cambio, una fila en ronda_correo con su evento. Con aviso_volumen de hoy, la pausa
   por volumen de la lectura automatica (una vez al dia: lectura_automatica.pausar).
9. Con la base de prueba, se niega.

Nada de aqui habla con la red ni importa el cliente de Graph, el certificado, httpx2 o
cryptography. Lo que dice (la CLI) no copia nunca texto de la bandeja: los motivos son fijos.
"""

from __future__ import annotations

import contextlib
import hashlib
import heapq
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .. import lectura_automatica
from ..almacen import (Almacen, DatosDePrueba, es_base_demo, reloj_de, transaccion,
                       usuario_sistema)
from ..almacen.documentos import DocumentoCorrupto, registrar_documento
from ..almacen.evidencia import foto
from ..auditoria import registrar as registrar_evento
from ..reloj import ZONA_EMPRESA, marca
from . import MAX_PDF, bandeja

# Lo que se mira en una pasada, como mucho (§3.5): un millon de ficheros diminutos no la cuelgan;
# lo demas, en el ciclo siguiente.
POR_PASADA = 2000
# Una llegada que dice haber llegado mas tarde que esto respecto al reloj de este equipo no se
# registra todavia (§3.8, paso 4).
FUTURO = timedelta(minutes=5)
# Antes de esto, la hora de recepcion no se sabe (§3.8, paso 4).
SIN_FECHA_ANTES = datetime(2000, 1, 1, tzinfo=timezone.utc)
# Lo mas grande que se lee de estado.json (lo escribe el correo; no tiene por que pasar de poco).
MAX_ESTADO = 64 * 1024
# Un entero de la bandeja que pasa de esto no es de verdad (y no cabe en SQLite).
MAX_ENTERO = 2 ** 53

CLAVES_LLEGADA = frozenset({"version", "carpeta", "graph_id", "internet_message_id",
                            "recibido_en", "remitente", "asunto", "en_linea", "traido_en",
                            "adjuntos"})
CLAVES_ADJUNTO = frozenset({"id", "nombre", "tipo", "bytes", "resultado", "sha256", "detalle"})
CLAVES_ESTADO = frozenset({"version", "ronda", "hoy", "ultima_consulta", "ultima_buena", "buzon",
                           "certificado", "alcance", "delta_reiniciado_en", "retenido_hasta",
                           "aviso_volumen"})
CLAVES_RONDA = frozenset({"empezada", "terminada", "resultado", "error_codigo", "mensajes",
                          "pdf_nuevos", "bytes"})
CLAVES_HOY = frozenset({"fecha", "mensajes", "pdf", "bytes"})

_INSTANTE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ZONA = ZoneInfo(ZONA_EMPRESA)
_CARPETA = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(
    os, "O_NOFOLLOW", 0)
_FICHERO = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0) | getattr(
    os, "O_NONBLOCK", 0)


class NoSeRegistra(RuntimeError):
    """`correo registrar` no corre: la base de prueba, o un sistema sin dir_fd (Windows)."""


class _Rechazo(ValueError):
    """Lo de la bandeja que no vale. El motivo es un texto fijo: nunca lleva lo que venia."""


class _CarpetaNoValida(_Rechazo):
    """Una de las tres carpetas no es una carpeta de verdad (un enlace, un fichero...)."""


@dataclass
class Resultado:
    """Lo que hizo una pasada, para la CLI y las pruebas."""

    mensajes: int = 0                 # llegadas registradas (mensaje_correo nuevos)
    documentos_nuevos: int = 0        # documentos nuevos en el almacen
    repetidos: int = 0                # llegadas que ya estaban en la base (se borran)
    esperan_reloj: int = 0            # llegadas "del futuro": se quedan
    fallidos: int = 0                 # mensajes que no entraron por algo de la base: se quedan
    pdf_borrados: int = 0             # PDF quitados de la bandeja (acuse o rechazados)
    quedan: bool = False              # habia mas de POR_PASADA: lo demas, la proxima vez
    rechazados: list[str] = field(default_factory=list)   # motivos fijos, uno por fichero
    carpetas_malas: list[str] = field(default_factory=list)
    estado_copiado: bool = False
    error_codigo: str | None = None   # el error del correo que queda en estado_correo
    ronda_registrada: bool = False
    pausa_volumen: bool = False


# ------------------------------------------------------------------ las carpetas y los ficheros

def _cerrar(descriptor: int | None) -> None:
    if descriptor is not None:
        with contextlib.suppress(OSError):
            os.close(descriptor)


def _abrir_carpeta(nombre: str, dir_fd: int | None = None) -> int | None:
    """El descriptor de una carpeta de verdad (lstat, sin seguir enlaces), o None si no esta.
    _CarpetaNoValida si es otra cosa."""
    try:
        antes = os.lstat(nombre, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(antes.st_mode) or getattr(antes, "st_file_attributes", 0) & 0x400:
        raise _CarpetaNoValida("no es una carpeta de verdad")
    try:
        descriptor = os.open(nombre, _CARPETA, dir_fd=dir_fd)
    except OSError:
        raise _CarpetaNoValida("no se puede abrir como carpeta") from None
    despues = os.fstat(descriptor)
    if (despues.st_dev, despues.st_ino) != (antes.st_dev, antes.st_ino):
        _cerrar(descriptor)
        raise _CarpetaNoValida("ha cambiado mientras se abria")
    return descriptor


def _leer(dir_fd: int, nombre: str, maximo: int) -> bytes:
    """Los bytes de un fichero normal de una carpeta, sin seguir enlaces y sin pasar de
    `maximo`. FileNotFoundError si no esta; _Rechazo si no vale."""
    try:
        antes = os.lstat(nombre, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError:
        raise _Rechazo("no se puede mirar") from None
    if not stat.S_ISREG(antes.st_mode):
        raise _Rechazo("no es un fichero normal")
    if antes.st_size > maximo:
        raise _Rechazo("demasiado grande")
    try:
        descriptor = os.open(nombre, _FICHERO, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError:
        raise _Rechazo("no se puede abrir sin seguir enlaces") from None
    try:
        despues = os.fstat(descriptor)
        if (not stat.S_ISREG(despues.st_mode)
                or (despues.st_dev, despues.st_ino) != (antes.st_dev, antes.st_ino)):
            raise _Rechazo("ha cambiado mientras se abria")
        trozos, leidos = [], 0
        while leidos <= maximo:
            trozo = os.read(descriptor, min(1024 * 1024, maximo + 1 - leidos))
            if not trozo:
                break
            trozos.append(trozo)
            leidos += len(trozo)
    except OSError:
        raise _Rechazo("no se puede leer") from None
    finally:
        _cerrar(descriptor)
    if leidos > maximo:
        raise _Rechazo("demasiado grande")
    return b"".join(trozos)


def _borrar(dir_fd: int, nombre: str) -> bool:
    """Quita una entrada de la carpeta (un fichero, o un enlace sin seguirlo)."""
    try:
        os.unlink(nombre, dir_fd=dir_fd)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


@dataclass(frozen=True)
class _Entrada:
    nombre: str
    normal: bool       # un fichero normal (lo demas se rechaza y se quita)


def _mas_antiguas(dir_fd: int, patron: re.Pattern[str], cuantas: int) -> tuple[list[_Entrada],
                                                                                bool]:
    """Las `cuantas` entradas mas antiguas cuyo nombre es el del patron (lo demas se ignora), y si
    habia mas."""
    if cuantas <= 0:
        return [], False
    candidatas: list[tuple[int, str, bool]] = []
    total = 0
    with os.scandir(dir_fd) as entradas:
        for entrada in entradas:
            if not patron.fullmatch(entrada.name):
                continue
            try:
                datos = entrada.stat(follow_symlinks=False)
            except OSError:
                continue
            total += 1
            candidatas.append((datos.st_mtime_ns, entrada.name, stat.S_ISREG(datos.st_mode)))
            if len(candidatas) > 4 * cuantas:
                candidatas = heapq.nsmallest(cuantas, candidatas)
    elegidas = heapq.nsmallest(cuantas, candidatas)
    return [_Entrada(nombre, normal) for _m, nombre, normal in elegidas], total > cuantas


# ------------------------------------------------------------------ JSON estricto

def _json(datos: bytes) -> Any:
    def pares(lista: list[tuple[str, Any]]) -> dict[str, Any]:
        objeto: dict[str, Any] = {}
        for clave, valor in lista:
            if clave in objeto:
                raise ValueError("clave repetida")
            objeto[clave] = valor
        return objeto

    def constante(_nombre: str) -> Any:
        raise ValueError("NaN o Infinity")

    try:
        return json.loads(datos.decode("utf-8"), object_pairs_hook=pares,
                          parse_constant=constante)
    except (ValueError, RecursionError):
        raise _Rechazo("no es JSON valido") from None


def _objeto(valor: Any, claves: frozenset[str], que: str) -> dict[str, Any]:
    if not isinstance(valor, dict) or set(valor) != claves:
        raise _Rechazo(f"{que}: no tiene las claves exactas")
    return valor


def _entero(valor: Any, que: str) -> int:
    if type(valor) is not int or not 0 <= valor <= MAX_ENTERO:
        raise _Rechazo(f"{que}: no es un entero valido")
    return valor


def _texto(valor: Any, maximo: int, que: str) -> str | None:
    """Un texto de terceros: None, o una cadena de hasta `maximo`, saneada otra vez (sin
    controles ni caracteres de direccion o de anchura cero)."""
    if valor is None:
        return None
    if not isinstance(valor, str) or len(valor) > maximo:
        raise _Rechazo(f"{que}: no es un texto valido")
    return bandeja.sanear(valor, maximo)


def _instante(valor: Any, que: str, *, nulo: bool = False) -> datetime | None:
    """Un instante como lo escribe la bandeja (AAAA-MM-DDTHH:MM:SSZ), en UTC."""
    if valor is None and nulo:
        return None
    if not isinstance(valor, str) or not _INSTANTE.fullmatch(valor):
        raise _Rechazo(f"{que}: no es un instante en UTC")
    try:
        return datetime.fromisoformat(valor[:-1] + "+00:00")
    except ValueError:
        raise _Rechazo(f"{que}: no es un instante en UTC") from None


def _ascii_visible(valor: Any, maximo: int) -> bool:
    return (isinstance(valor, str) and 0 < len(valor) <= maximo
            and all(0x21 <= ord(c) <= 0x7E for c in valor))


@dataclass(frozen=True)
class _Adjunto:
    id: str
    nombre: str | None
    tipo: str | None
    bytes: int | None
    resultado: str
    sha256: str | None


@dataclass(frozen=True)
class _Llegada:
    carpeta: str
    graph_id: str
    internet_message_id: str | None
    recibido_en: datetime
    remitente: str | None
    asunto: str | None
    en_linea: int
    traido_en: datetime
    adjuntos: tuple[_Adjunto, ...]


def validar_llegada(nombre: str, datos: bytes) -> _Llegada:
    """Una llegada de la bandeja, entera o _Rechazo (§3.8, paso 4)."""
    llegada = _objeto(_json(datos), CLAVES_LLEGADA, "la llegada")
    if type(llegada["version"]) is not int or llegada["version"] != bandeja.VERSION:
        raise _Rechazo("la llegada: version desconocida")
    carpeta = llegada["carpeta"]
    if carpeta not in bandeja.CARPETAS:
        raise _Rechazo("la llegada: carpeta desconocida")
    graph_id = llegada["graph_id"]
    if not isinstance(graph_id, str) or not bandeja.GRAPH_ID.fullmatch(graph_id):
        raise _Rechazo("la llegada: graph_id no valido")
    if nombre != bandeja.nombre_llegada(bandeja.clave(graph_id, carpeta)):
        raise _Rechazo("la llegada: el nombre del fichero no es el de su mensaje")
    message_id = llegada["internet_message_id"]
    if message_id is not None and not _ascii_visible(message_id, bandeja.MAX_MESSAGE_ID):
        raise _Rechazo("la llegada: internet_message_id no valido")
    lista = llegada["adjuntos"]
    if not isinstance(lista, list) or len(lista) > bandeja.MAX_ADJUNTOS:
        raise _Rechazo("la llegada: adjuntos no validos")
    adjuntos: list[_Adjunto] = []
    vistos: set[str] = set()
    for valor in lista:
        adjunto = _objeto(valor, CLAVES_ADJUNTO, "un adjunto")
        identificador = adjunto["id"]
        if not (isinstance(identificador, str) and 0 < len(identificador)
                <= bandeja.MAX_ADJUNTO_ID and identificador.isascii()
                and identificador.isprintable()) or identificador in vistos:
            raise _Rechazo("un adjunto: id no valido o repetido")
        vistos.add(identificador)
        resultado = adjunto["resultado"]
        if resultado not in bandeja.RESULTADOS:
            raise _Rechazo("un adjunto: resultado desconocido")
        sha = adjunto["sha256"]
        if resultado == "pdf":
            if not isinstance(sha, str) or not bandeja.HEX64.fullmatch(sha):
                raise _Rechazo("un adjunto: un PDF sin su sha256")
        elif sha is not None:
            raise _Rechazo("un adjunto: un sha256 en lo que no es un PDF")
        tamano = adjunto["bytes"]
        if tamano is not None:
            _entero(tamano, "un adjunto")
        _texto(adjunto["detalle"], bandeja.MAX_DETALLE, "un adjunto")
        adjuntos.append(_Adjunto(identificador, _texto(adjunto["nombre"], bandeja.MAX_NOMBRE,
                                                       "un adjunto"),
                                 _texto(adjunto["tipo"], bandeja.MAX_TIPO, "un adjunto"),
                                 tamano, resultado, sha))
    recibido = _instante(llegada["recibido_en"], "la llegada")
    traido = _instante(llegada["traido_en"], "la llegada")
    assert recibido is not None and traido is not None
    return _Llegada(carpeta, graph_id, message_id, recibido,
                    _texto(llegada["remitente"], bandeja.MAX_REMITENTE, "la llegada"),
                    _texto(llegada["asunto"], bandeja.MAX_ASUNTO, "la llegada"),
                    _entero(llegada["en_linea"], "la llegada"), traido, tuple(adjuntos))


@dataclass(frozen=True)
class _Estado:
    empezada: datetime
    terminada: datetime
    error_codigo: str | None
    mensajes: int
    pdf_nuevos: int
    hoy_fecha: str
    hoy: dict[str, int]
    ultima_consulta: datetime | None
    ultima_buena: datetime | None
    buzon: str | None
    caduca_en: datetime | None
    alcance_comprobado_en: datetime | None
    alcance_bien: bool | None
    delta_reiniciado_en: datetime | None
    retenido_hasta: datetime | None
    aviso_volumen: bool


def validar_estado(datos: bytes) -> _Estado:
    """estado.json (§3.7), entero o _Rechazo."""
    estado = _objeto(_json(datos), CLAVES_ESTADO, "estado.json")
    if type(estado["version"]) is not int or estado["version"] != bandeja.VERSION:
        raise _Rechazo("estado.json: version desconocida")
    ronda = _objeto(estado["ronda"], CLAVES_RONDA, "estado.json: ronda")
    codigo = ronda["error_codigo"]
    if codigo is not None and codigo not in bandeja.CODIGOS:
        raise _Rechazo("estado.json: codigo de error desconocido")
    if ronda["resultado"] not in ("bien", "fallo") or (ronda["resultado"] == "fallo") != (
            codigo is not None):
        raise _Rechazo("estado.json: resultado de la ronda no valido")
    for clave in ("mensajes", "pdf_nuevos", "bytes"):
        _entero(ronda[clave], "estado.json: ronda")
    hoy = _objeto(estado["hoy"], CLAVES_HOY, "estado.json: hoy")
    if not isinstance(hoy["fecha"], str) or not _FECHA.fullmatch(hoy["fecha"]):
        raise _Rechazo("estado.json: la fecha de hoy no vale")
    for clave in ("mensajes", "pdf", "bytes"):
        _entero(hoy[clave], "estado.json: hoy")
    certificado = _objeto(estado["certificado"], frozenset({"caduca_en"}),
                          "estado.json: certificado")
    alcance = _objeto(estado["alcance"], frozenset({"comprobado_en", "bien", "motivo_codigo"}),
                      "estado.json: alcance")
    comprobado = _instante(alcance["comprobado_en"], "estado.json: alcance", nulo=True)
    bien = alcance["bien"]
    if (bien is not None and not isinstance(bien, bool)) or (comprobado is None) != (
            bien is None):
        raise _Rechazo("estado.json: alcance no valido")
    if alcance["motivo_codigo"] is not None and alcance["motivo_codigo"] not in bandeja.CODIGOS:
        raise _Rechazo("estado.json: alcance no valido")
    buzon = estado["buzon"]
    if buzon is not None and not (isinstance(buzon, str) and 3 <= len(buzon) <= 320
                                  and bandeja.sanear(buzon, 320) == buzon):
        raise _Rechazo("estado.json: buzon no valido")
    if not isinstance(estado["aviso_volumen"], bool):
        raise _Rechazo("estado.json: aviso_volumen no valido")
    empezada = _instante(ronda["empezada"], "estado.json: ronda")
    terminada = _instante(ronda["terminada"], "estado.json: ronda")
    assert empezada is not None and terminada is not None
    return _Estado(
        empezada=empezada, terminada=terminada, error_codigo=codigo,
        mensajes=ronda["mensajes"], pdf_nuevos=ronda["pdf_nuevos"], hoy_fecha=hoy["fecha"],
        hoy={"fecha": hoy["fecha"], "mensajes": hoy["mensajes"], "pdf": hoy["pdf"],
             "bytes": hoy["bytes"]},
        ultima_consulta=_instante(estado["ultima_consulta"], "estado.json", nulo=True),
        ultima_buena=_instante(estado["ultima_buena"], "estado.json", nulo=True),
        buzon=buzon,
        caduca_en=_instante(certificado["caduca_en"], "estado.json: certificado", nulo=True),
        alcance_comprobado_en=comprobado, alcance_bien=bien,
        delta_reiniciado_en=_instante(estado["delta_reiniciado_en"], "estado.json", nulo=True),
        retenido_hasta=_instante(estado["retenido_hasta"], "estado.json", nulo=True),
        aviso_volumen=estado["aviso_volumen"])


# ------------------------------------------------------------------ una pasada

def _marca(instante: datetime | None) -> str | None:
    return None if instante is None else marca(instante)


class _Pasada:
    def __init__(self, almacen: Almacen, entrada: str, estado: str) -> None:
        self.almacen = almacen
        self.conn = almacen.conn
        self.ahora = reloj_de(self.conn).ahora()
        self.correo = usuario_sistema(self.conn, "correo")
        self.rutas = {"entrada": entrada, "estado": estado}
        self.resultado = Resultado()
        self.anulacion: str | None = None   # el error que deja esta pasada (reloj, interno)
        # Lo que se vio de cada PDF en esta pasada: los de prueba, por su sha256.
        self.de_prueba: set[str] = set()

    # -------------------------------------------------------------- carpetas

    def _carpeta(self, nombre: str, dir_fd: int | None, que: str) -> int | None:
        try:
            return _abrir_carpeta(nombre, dir_fd)
        except _CarpetaNoValida:
            self.resultado.carpetas_malas.append(que)
            self.anulacion = "interno"
            return None

    def hacer(self) -> Resultado:
        entrada = llegadas = pdf = estado = None
        try:
            entrada = self._carpeta(self.rutas["entrada"], None, "entrada")
            if entrada is not None:
                llegadas = self._carpeta(bandeja.ENTRADA_LLEGADAS, entrada, "entrada/llegadas")
                pdf = self._carpeta(bandeja.ENTRADA_PDF, entrada, "entrada/pdf")
            estado = self._carpeta(self.rutas["estado"], None, "estado")
            leido = self._leer_estado(estado) if estado is not None else None
            restan = POR_PASADA
            if llegadas is not None and pdf is not None:
                restan = self._llegadas(llegadas, pdf)
            if pdf is not None:
                self._pdf_sueltos(pdf, restan)
            self._apuntar_estado(leido)
        finally:
            for descriptor in (pdf, llegadas, entrada, estado):
                _cerrar(descriptor)
        return self.resultado

    # -------------------------------------------------------------- estado.json

    def _leer_estado(self, estado: int) -> _Estado | None:
        try:
            datos = _leer(estado, bandeja.ESTADO, MAX_ESTADO)
        except FileNotFoundError:
            return None       # el correo aun no ha hecho ninguna ronda
        except _Rechazo as rechazo:
            self.resultado.rechazados.append(f"estado.json: {rechazo}")
            self.anulacion = "interno"
            return None
        try:
            return validar_estado(datos)
        except _Rechazo as rechazo:
            self.resultado.rechazados.append(str(rechazo))
            self.anulacion = "interno"
            return None

    # -------------------------------------------------------------- las llegadas

    def _llegadas(self, llegadas: int, pdf: int) -> int:
        """Las llegadas mas antiguas, una a una. Devuelve cuantas entradas quedan por mirar."""
        elegidas, mas = _mas_antiguas(llegadas, bandeja.NOMBRE_LLEGADA, POR_PASADA)
        self.resultado.quedan = mas
        for entrada in elegidas:
            self._llegada(llegadas, pdf, entrada)
        return POR_PASADA - len(elegidas)

    def _rechazar(self, carpeta: int, nombre: str, motivo: str) -> None:
        self.resultado.rechazados.append(f"{nombre[:12]}...: {motivo}")
        _borrar(carpeta, nombre)

    def _llegada(self, llegadas: int, pdf: int, entrada: _Entrada) -> None:
        if not entrada.normal:
            self._rechazar(llegadas, entrada.nombre, "no es un fichero normal")
            return
        try:
            llegada = validar_llegada(entrada.nombre,
                                      _leer(llegadas, entrada.nombre, bandeja.MAX_LLEGADA))
        except FileNotFoundError:
            return
        except _Rechazo as rechazo:
            self._rechazar(llegadas, entrada.nombre, str(rechazo))
            return
        if llegada.recibido_en > self.ahora + FUTURO:
            # El reloj de este equipo va atrasado: no se registra todavia (el documento no se
            # puede corregir despues). Se queda y se vuelve a mirar en el ciclo siguiente.
            self.resultado.esperan_reloj += 1
            self.anulacion = self.anulacion or "reloj"
            return
        ya = self.conn.execute("SELECT id FROM mensaje_correo WHERE graph_id = ? AND carpeta = ?",
                               (llegada.graph_id, llegada.carpeta)).fetchone()
        if ya is not None:
            # La delta volvio a empezar y la trajo otra vez: ya esta, no se apunta dos veces.
            self.resultado.repetidos += 1
            _borrar(llegadas, entrada.nombre)
            self._acuse(pdf, llegada)
            return
        try:
            self._registrar(pdf, llegada)
        except (sqlite3.IntegrityError, DocumentoCorrupto):
            # Algo de la base o del almacen, no de la bandeja: la llegada se queda para la
            # proxima vez (y lo dice la CLI).
            self.resultado.fallidos += 1
            return
        _borrar(llegadas, entrada.nombre)
        self._acuse(pdf, llegada)

    def _pdf(self, pdf: int, adjunto: _Adjunto) -> tuple[str, bytes | None]:
        """El PDF de un adjunto de la bandeja: ('ok', bytes), ('falta', None) o
        ('rechazado', None)."""
        assert adjunto.sha256 is not None
        try:
            datos = _leer(pdf, bandeja.nombre_pdf(adjunto.sha256), MAX_PDF)
        except FileNotFoundError:
            return "falta", None
        except _Rechazo:
            return "rechazado", None
        if hashlib.sha256(datos).hexdigest() != adjunto.sha256 or not datos.startswith(b"%PDF-"):
            return "rechazado", None
        return "ok", datos

    def _registrar(self, pdf: int, llegada: _Llegada) -> None:
        """Un mensaje entero en una transaccion (§3.8, paso 6)."""
        conn = self.conn
        sin_fecha = llegada.recibido_en < SIN_FECHA_ANTES
        filas: list[tuple[_Adjunto, str, str | None, int | None, int | None]] = []
        nuevos = 0
        with transaccion(conn):
            for adjunto in llegada.adjuntos:
                if adjunto.resultado != "pdf":
                    filas.append((adjunto, adjunto.resultado, None, adjunto.bytes, None))
                    continue
                sha = adjunto.sha256
                assert sha is not None
                existente = conn.execute("SELECT id, ruta_cas, bytes FROM documento "
                                         "WHERE sha256 = ?", (sha,)).fetchone()
                if existente is not None and existente["ruta_cas"] is not None:
                    # Ya estaba (otro correo, o buzon\facturas): el fichero ya no hace falta.
                    filas.append((adjunto, "documento", sha, existente["bytes"],
                                  existente["id"]))
                    continue
                if sha in self.de_prueba:
                    filas.append((adjunto, "de_prueba", sha, adjunto.bytes, None))
                    continue
                como, datos = self._pdf(pdf, adjunto)
                if datos is None:
                    if existente is not None:
                        filas.append((adjunto, "documento", sha, existente["bytes"],
                                      existente["id"]))
                    else:
                        filas.append((adjunto, "error", None, adjunto.bytes, None))
                    continue
                try:
                    hecho = registrar_documento(
                        self.almacen, sha256=sha, contenido=datos,
                        nombre_original=adjunto.nombre, tipo_mime="application/pdf",
                        origen="correo", ruta_declarada="entrante",
                        recibido_en=None if sin_fecha else marca(llegada.recibido_en),
                        recibido_fuente="desconocido" if sin_fecha else "correo",
                        actor=self.correo, mensaje_id=llegada.internet_message_id)
                except DatosDePrueba:
                    self.de_prueba.add(sha)
                    filas.append((adjunto, "de_prueba", sha, len(datos), None))
                    continue
                nuevos += hecho.nuevo
                filas.append((adjunto, "documento", sha, len(datos), hecho.id))
            mensaje_id = int(conn.execute(
                "INSERT INTO mensaje_correo (graph_id, carpeta, internet_message_id_doc, "
                "recibido_en, remitente_doc, asunto_doc, adjuntos, en_linea, traido_en, "
                "registrado_en, registrado_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (llegada.graph_id, llegada.carpeta, llegada.internet_message_id,
                 marca(llegada.recibido_en), llegada.remitente, llegada.asunto,
                 len(llegada.adjuntos), llegada.en_linea, marca(llegada.traido_en),
                 marca(self.ahora), self.correo)).lastrowid)
            fotos: dict[str, dict[str, Any]] = {}
            for adjunto, resultado, sha, tamano, documento_id in filas:
                adjunto_id = int(conn.execute(
                    "INSERT INTO adjunto_correo (mensaje_id, graph_adjunto_id, nombre_doc, "
                    "tipo_declarado_doc, bytes, sha256, resultado, documento_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (mensaje_id, adjunto.id, adjunto.nombre, adjunto.tipo, tamano, sha,
                     resultado, documento_id)).lastrowid)
                fotos[str(adjunto_id)] = foto(conn, "adjunto_correo", adjunto_id)
            registrar_evento(
                conn, tipo="correo_mensaje_registrado", actor=self.correo,
                tabla="mensaje_correo", fila_id=mensaje_id,
                datos={"fila": foto(conn, "mensaje_correo", mensaje_id), "adjuntos": fotos,
                       "documentos_nuevos": nuevos})
        self.resultado.mensajes += 1
        self.resultado.documentos_nuevos += nuevos

    def _acuse(self, pdf: int, llegada: _Llegada) -> None:
        """Tras registrar una llegada, sus PDF fuera de la bandeja: los que ya estan en la base,
        los de prueba y los que no casan con su nombre (§3.8, paso 7)."""
        for adjunto in llegada.adjuntos:
            if adjunto.sha256 is None:
                continue
            nombre = bandeja.nombre_pdf(adjunto.sha256)
            en_la_base = self.conn.execute(
                "SELECT 1 FROM documento WHERE sha256 = ? AND ruta_cas IS NOT NULL",
                (adjunto.sha256,)).fetchone() is not None
            if en_la_base or adjunto.sha256 in self.de_prueba:
                self.resultado.pdf_borrados += _borrar(pdf, nombre)
                continue
            como, _datos = self._pdf(pdf, adjunto)
            if como == "rechazado":
                self.resultado.rechazados.append(f"{nombre[:12]}...: el PDF no es el de su "
                                                 "nombre o no empieza por %PDF-")
                self.resultado.pdf_borrados += _borrar(pdf, nombre)

    def _pdf_sueltos(self, pdf: int, restan: int) -> None:
        """Los PDF de la bandeja cuyo sha256 ya esta en la base (con su original) no hacen falta:
        fuera. Los demas esperan a su llegada (un mensaje con otro adjunto pendiente); los que
        nunca la tengan los quita el correo a los 45 dias. Lo que tiene nombre de PDF y no es un
        fichero normal, fuera."""
        elegidas, mas = _mas_antiguas(pdf, bandeja.NOMBRE_PDF, restan)
        self.resultado.quedan = self.resultado.quedan or mas
        for entrada in elegidas:
            if not entrada.normal:
                self._rechazar(pdf, entrada.nombre, "no es un fichero normal")
                self.resultado.pdf_borrados += 1
                continue
            sha = entrada.nombre[:-4]
            if self.conn.execute("SELECT 1 FROM documento WHERE sha256 = ? AND ruta_cas IS NOT "
                                 "NULL", (sha,)).fetchone() is not None:
                self.resultado.pdf_borrados += _borrar(pdf, entrada.nombre)

    # -------------------------------------------------------------- estado_correo y ronda_correo

    def _apuntar_estado(self, leido: _Estado | None) -> None:
        conn = self.conn
        with transaccion(conn):
            anterior = conn.execute("SELECT * FROM estado_correo WHERE id = 1").fetchone()
            if leido is not None:
                self._ronda(leido)
            if leido is None and anterior is None and self.anulacion is None:
                return      # el correo no ha hecho nada todavia: sigue sin configurar
            codigo, desde = self._error(anterior, leido)
            if self.anulacion is not None and codigo != (anterior["error_codigo"]
                                                         if anterior is not None else None):
                self._fila_de_fallo(self.anulacion)
            self.resultado.error_codigo = codigo
            if leido is not None:
                valores = {
                    "buzon": leido.buzon, "ultima_consulta": _marca(leido.ultima_consulta),
                    "ultima_buena": _marca(leido.ultima_buena),
                    "alcance_comprobado_en": _marca(leido.alcance_comprobado_en),
                    "alcance_bien": None if leido.alcance_bien is None
                    else int(leido.alcance_bien),
                    "credencial_caduca_en": _marca(leido.caduca_en),
                    "delta_reiniciado_en": _marca(leido.delta_reiniciado_en),
                    "retenido_hasta": _marca(leido.retenido_hasta),
                    "hoy_json": json.dumps(leido.hoy, sort_keys=True),
                    "aviso_volumen": int(leido.aviso_volumen)}
                self.resultado.estado_copiado = True
            elif anterior is not None:
                valores = {k: anterior[k] for k in (
                    "buzon", "ultima_consulta", "ultima_buena", "alcance_comprobado_en",
                    "alcance_bien", "credencial_caduca_en", "delta_reiniciado_en",
                    "retenido_hasta", "hoy_json", "aviso_volumen")}
            else:
                valores = {"hoy_json": "{}", "aviso_volumen": 0}
            _escribir_estado(conn, valores, codigo, desde, self.ahora)
        if leido is not None and leido.aviso_volumen and leido.hoy_fecha == self.ahora.astimezone(
                _ZONA).date().isoformat():
            # Mas de 200 correos hoy: la automatica para hasta que una persona lo mire (una vez
            # al dia; si ya la quito una persona, hoy no vuelve).
            self.resultado.pausa_volumen = lectura_automatica.pausar(
                conn, "volumen", ahora=self.ahora) is not None

    def _ronda(self, leido: _Estado) -> None:
        """La ronda de estado.json en ronda_correo si trajo algo o su codigo de error no es el de
        la ronda anterior, una vez (una ronda es su `empezada`). La anterior es la ultima que se
        apunto: las que no se apuntan tienen su mismo codigo. Los `registrar --fallo` (y lo que
        ve una pasada: reloj, interno) no cuentan: no son rondas del correo."""
        empezada = marca(leido.empezada)
        if self.conn.execute("SELECT 1 FROM ronda_correo WHERE empezada_en = ? AND terminada_en "
                             "IS NOT NULL", (empezada,)).fetchone() is not None:
            return
        ultima = self.conn.execute("SELECT error_codigo FROM ronda_correo WHERE terminada_en IS "
                                   "NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        codigo_antes = ultima["error_codigo"] if ultima is not None else None
        if not (leido.mensajes or leido.pdf_nuevos or leido.error_codigo != codigo_antes):
            return
        fila_id = int(self.conn.execute(
            "INSERT INTO ronda_correo (empezada_en, terminada_en, resultado, error_codigo, "
            "mensajes, documentos_nuevos, registrada_en) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (marca(leido.empezada), marca(leido.terminada),
             "bien" if leido.error_codigo is None else "fallo", leido.error_codigo,
             leido.mensajes, leido.pdf_nuevos, marca(self.ahora))).lastrowid)
        registrar_evento(self.conn, tipo="correo_ronda_registrada", actor=self.correo,
                         tabla="ronda_correo", fila_id=fila_id,
                         datos={"fila": foto(self.conn, "ronda_correo", fila_id)})
        self.resultado.ronda_registrada = True

    def _fila_de_fallo(self, codigo: str) -> None:
        _fila_de_fallo(self.conn, codigo, self.ahora, self.correo)
        self.resultado.ronda_registrada = True

    def _error(self, anterior: sqlite3.Row | None, leido: _Estado | None
               ) -> tuple[str | None, str | None]:
        """(codigo, desde): el de esta pasada (reloj, interno) si lo hay; si no, el mas reciente
        entre la ronda de estado.json y el ultimo `registrar --fallo` (la salida o el
        aislamiento que no dejaron traer nada despues de esa ronda). Sin estado.json (aun no hay
        ninguno, o no se pudo leer), el que ya estaba: estado_correo ya lleva cada --fallo."""
        if self.anulacion is not None:
            return _desde(anterior, self.anulacion, self.ahora)
        if leido is None:
            if anterior is None:
                return None, None
            return anterior["error_codigo"], anterior["error_desde"]
        codigo, desde = leido.error_codigo, leido.empezada
        fallo = self.conn.execute(
            "SELECT error_codigo, empezada_en FROM ronda_correo WHERE terminada_en IS NULL "
            "ORDER BY id DESC LIMIT 1").fetchone()
        if fallo is not None:
            cuando = datetime.fromisoformat(fallo["empezada_en"])
            if cuando > leido.empezada:
                codigo, desde = fallo["error_codigo"], cuando
        return _desde(anterior, codigo, desde)


def _desde(anterior: sqlite3.Row | None, codigo: str | None, desde: datetime | None
           ) -> tuple[str | None, str | None]:
    """El mismo error que ya estaba sigue siendo de cuando empezo."""
    if codigo is None:
        return None, None
    if anterior is not None and anterior["error_codigo"] == codigo and anterior["error_desde"]:
        return codigo, anterior["error_desde"]
    assert desde is not None
    return codigo, marca(desde)


def _escribir_estado(conn: sqlite3.Connection, valores: dict[str, Any], codigo: str | None,
                     desde: str | None, ahora: datetime) -> None:
    columnas = {**valores, "error_codigo": codigo, "error_desde": desde,
                "actualizado_en": marca(ahora)}
    nombres = ", ".join(columnas)
    marcas = ", ".join("?" * len(columnas))
    cambios = ", ".join(f"{c} = excluded.{c}" for c in columnas)
    conn.execute(f"INSERT INTO estado_correo (id, {nombres}) VALUES (1, {marcas}) "
                 f"ON CONFLICT (id) DO UPDATE SET {cambios}", tuple(columnas.values()))


def _fila_de_fallo(conn: sqlite3.Connection, codigo: str, ahora: datetime, correo: int) -> None:
    """Un fallo que no es una ronda entera (registrar --fallo, o lo que ve esta pasada)."""
    fila_id = int(conn.execute(
        "INSERT INTO ronda_correo (empezada_en, terminada_en, resultado, error_codigo, mensajes, "
        "documentos_nuevos, registrada_en) VALUES (?, NULL, 'fallo', ?, 0, 0, ?)",
        (marca(ahora), codigo, marca(ahora))).lastrowid)
    registrar_evento(conn, tipo="correo_ronda_registrada", actor=correo, tabla="ronda_correo",
                     fila_id=fila_id, datos={"fila": foto(conn, "ronda_correo", fila_id)})


# ------------------------------------------------------------------ lo que llama la CLI

def _exigir(almacen: Almacen) -> None:
    if es_base_demo(almacen.conn):
        raise NoSeRegistra("el correo se registra solo en la base de verdad, nunca en la de "
                           "prueba")
    if os.open not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd or not hasattr(
            os, "O_NOFOLLOW"):
        raise NoSeRegistra("el correo es solo de la variante Docker (Linux): aqui no se pueden "
                           "abrir los ficheros de la bandeja relativos a su carpeta")


def registrar(almacen: Almacen, *, entrada: str | os.PathLike[str],
              estado: str | os.PathLike[str]) -> Resultado:
    """Una pasada de `correo registrar` (§3.8) sobre la bandeja `entrada` (/correo/entrada) y el
    estado del correo `estado` (/correo/estado)."""
    _exigir(almacen)
    return _Pasada(almacen, os.fspath(entrada), os.fspath(estado)).hacer()


def apuntar_fallo(almacen: Almacen, codigo: str) -> bool:
    """`correo registrar --fallo CODIGO` (§4.1): el ciclo no pudo traer nada (la salida, el
    aislamiento, el disco). Queda en estado_correo y, si el codigo cambia, en ronda_correo (una
    fila sin `terminada_en`: no es una ronda entera). True si cambio."""
    if codigo not in bandeja.CODIGOS:
        raise ValueError("codigo de error del correo desconocido")
    _exigir(almacen)
    conn = almacen.conn
    ahora = reloj_de(conn).ahora()
    with transaccion(conn):
        anterior = conn.execute("SELECT * FROM estado_correo WHERE id = 1").fetchone()
        cambia = anterior is None or anterior["error_codigo"] != codigo
        if cambia:
            _fila_de_fallo(conn, codigo, ahora, usuario_sistema(conn, "correo"))
        valores = ({k: anterior[k] for k in (
            "buzon", "ultima_consulta", "ultima_buena", "alcance_comprobado_en", "alcance_bien",
            "credencial_caduca_en", "delta_reiniciado_en", "retenido_hasta", "hoy_json",
            "aviso_volumen")} if anterior is not None else {"hoy_json": "{}", "aviso_volumen": 0})
        _codigo, desde = _desde(anterior, codigo, ahora)
        _escribir_estado(conn, valores, codigo, desde, ahora)
    return cambia
