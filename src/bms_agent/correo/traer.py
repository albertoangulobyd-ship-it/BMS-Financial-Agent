"""Una ronda del correo de facturas: `correo traer` y `correo comprobar` (paso 18, diseno §3.2).

Lo hace el componente `correo` (en Docker, su contenedor: sin la base, sin la clave de la API,
y su unica salida es la del correo, a login.microsoftonline.com y graph.microsoft.com). No abre
la base, no importa el SDK de la API, no lee variables de entorno propias (las rutas llegan por
argumentos) y no pide nunca el cuerpo de un mensaje. Lo que trae lo deja en su bandeja, con
nombres que genera el (correo/bandeja.py), y `orden` lo registra despues (`correo registrar`,
que lo valida todo como no confiable y borra lo registrado).

Una ronda, en orden (§3.2):

1. el cerrojo `estado/traer.cerrojo`, del sistema (flock: se suelta solo si el proceso muere);
   si esta tomado, `ocupado` y nada mas (no es un error);
2. los ajustes y el certificado; si no hay, `sin_configurar` (o `credencial`);
3. la bandeja: si lo que aun no se ha registrado pasa de 2 GiB, `disco`;
4. los topes del dia (los PDF y los MiB de los ajustes): si ya se llego, no se pide nada a
   Graph y queda `retenido_hasta` (las 00:00 de manana en Amsterdam): la ronda va bien;
5. el token, y 6. `correo comprobar` si toca (la ultima tiene mas de 24 horas, no fue bien, la
   ronda anterior acabo en credencial, permiso, alcance o control_no_existe, o se pide);
7. los adjuntos pendientes (los que no se pudieron bajar en otra ronda), por su id, como mucho
   cada 30 minutos y durante 24 horas; despues, `error`;
8. la delta de la bandeja, pagina a pagina y mensaje a mensaje, cada uno con su propio limite
   de errores (intentos.json: al tercero, su llegada con cada adjunto `error`); tras cada
   pagina completa se guarda el enlace con el que se sigue;
9. la delta de "Correo no deseado": solo lo que dice el mensaje y sus adjuntos, sin bajar nada;
10. la limpieza (lo de la bandeja de mas de 45 dias, los intentos de mas de 7);
11. estado.json.

Los topes (§3.5): 100 mensajes y 300 MiB por ronda, 20 adjuntos tratados por mensaje (50
apuntados), cada PDF como mucho correo.MAX_PDF, y los del dia. Lo que no cabe en un tope se
queda para despues sin perderse: la delta no avanza mas alla de lo que se termino, y los PDF
de un mensaje a medias esperan en pendientes.json.

Lo que no se ha escrito nunca en ningun sitio: el token, la asercion, la consulta de un enlace,
el asunto, el remitente o la direccion del buzon (salvo el buzon en estado.json y en la llegada
el remitente y el asunto, que son para la base, saneados).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from datetime import time as hora
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..reloj import RELOJ_SISTEMA, ZONA_EMPRESA
from . import MAX_PDF, bandeja, graph
from . import ajustes as _ajustes
from . import certificado as _certificado

try:
    import fcntl
except ImportError:  # Windows: el correo es solo de la variante Docker
    fcntl = None  # type: ignore[assignment]

MIB = 1024 * 1024
MENSAJES_RONDA = 100
# Paginas de la delta por ronda (las dos carpetas): una delta que se repite (lo ya visto no
# cuenta como mensaje) o que no acaba nunca no tiene la ronda pidiendo paginas sin fin.
PAGINAS_RONDA = 40
BYTES_RONDA = 300 * MIB
ADJUNTOS_TRATADOS = 20
MAX_BANDEJA = 2 * 1024 * MIB
AVISO_VOLUMEN = 200
MAX_INTENTOS = 3
PENDIENTE_DURA = timedelta(hours=24)
PENDIENTE_CADA = timedelta(minutes=30)
MAX_PENDIENTES = 500
VIEJO_EN_LA_BANDEJA = timedelta(days=45)
VIEJO_EN_EL_ESTADO = timedelta(days=7)
MAX_VISTOS = 20000
MARGEN_DELTA = timedelta(days=3)
VIGENCIA_ALCANCE = timedelta(hours=24)
REPETIR_ALCANCE = frozenset({"credencial", "permiso", "alcance", "control_no_existe"})
# Lo mas grande que se lee de un fichero del estado (lo escribe solo el correo).
MAX_ESTADO = 64 * MIB

_ZONA = ZoneInfo(ZONA_EMPRESA)
_PDF = ("application/pdf", "application/x-pdf", "application/octet-stream")
_XML = ("application/xml", "text/xml")
_REENVIO = ("message/rfc822", "application/vnd.ms-outlook")
# Lo que dice cada adjunto que aun no tiene su resultado (solo en pendientes.json).
_BAJAR, _PENDIENTE = "_bajar", "_pendiente"


@dataclass
class Resultado:
    """Lo que paso en una ronda (o una comprobacion), para la CLI."""

    ocupado: bool = False
    codigo: str | None = None
    detalle: str | None = None
    mensajes: int = 0
    pdf_nuevos: int = 0
    bytes: int = 0
    retenido_hasta: datetime | None = None
    fallidos: int = 0
    pendientes: int = 0
    alcance: graph.Alcance | None = None


class _Fin(Exception):
    """La ronda termina aqui con este codigo (de la lista cerrada)."""

    def __init__(self, codigo: str, detalle: str) -> None:
        super().__init__(f"{codigo}: {detalle}")
        self.codigo, self.detalle = codigo, detalle


# ------------------------------------------------------------------ el dia de la empresa

def manana(ahora: datetime) -> datetime:
    """Las 00:00 del dia siguiente en Amsterdam, en UTC."""
    dia = ahora.astimezone(_ZONA).date() + timedelta(days=1)
    return datetime.combine(dia, hora(0), tzinfo=_ZONA).astimezone(timezone.utc)


def _inicio_del_dia(dia: date) -> datetime:
    return datetime.combine(dia, hora(0), tzinfo=_ZONA).astimezone(timezone.utc)


# ------------------------------------------------------------------ el cerrojo

@contextlib.contextmanager
def cerrojo(carpeta: Path) -> Iterator[bool]:
    """El cerrojo de la ronda (§3.2, paso 1): flock exclusivo sobre estado/traer.cerrojo, sin
    esperar. Un fichero que se quedo en disco sin nadie que lo tenga no bloquea: el sistema
    suelta el cerrojo cuando muere el proceso. Da True si se ha tomado."""
    if fcntl is None:
        raise OSError("el correo solo corre en la variante Docker (Linux)")
    descriptor = os.open(carpeta / bandeja.CERROJO,
                         os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
                         0o600)
    try:
        tomado = True
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            tomado = False
        yield tomado
    finally:
        os.close(descriptor)


# ------------------------------------------------------------------ los ficheros del estado

def _leer_json(ruta: Path) -> Any:
    """Un JSON nuestro del estado; None si no esta, no se puede leer o no es JSON (se empieza
    de cero: lo que se pierde es como mucho trabajo repetido)."""
    try:
        with open(ruta, "rb") as fichero:
            contenido = fichero.read(MAX_ESTADO + 1)
        if len(contenido) > MAX_ESTADO:
            return None
        return json.loads(contenido.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None


def _guardar_json(ruta: Path, datos: Any) -> None:
    bandeja.escribir_de_una_vez(ruta.parent, ruta, bandeja.como_json(datos))


def _texto(momento: datetime | None) -> str | None:
    return None if momento is None else bandeja.instante(momento)


def _mapa(datos: Any, clave: str) -> dict[str, Any]:
    if isinstance(datos, dict) and isinstance(datos.get(clave), dict):
        return {k: v for k, v in datos[clave].items()
                if isinstance(k, str) and bandeja.HEX64.fullmatch(k) and isinstance(v, dict)}
    return {}


# ------------------------------------------------------------------ cada adjunto (§3.3)

def _por_nombre_y_tipo(nombre: str | None, tipo: str | None) -> str:
    """Lo que es un adjunto de fichero por su nombre y su tipo declarado (los dos los pone el
    remitente: solo deciden si se baja; despues manda el %PDF-). El nombre gana al tipo."""
    nombre = (nombre or "").lower()
    tipo = (tipo or "").lower().split(";", 1)[0].strip()
    if nombre.endswith(".pdf"):
        return _BAJAR
    if nombre.endswith(".xml"):
        return "xml"
    if nombre.endswith((".eml", ".msg")):
        return "reenvio"
    if tipo in _PDF:
        return _BAJAR
    if tipo in _XML:
        return "xml"
    if tipo in _REENVIO:
        return "reenvio"
    return "no_pdf"


def clasificar(carpeta: str, lista: list[Any]) -> tuple[list[dict], int]:
    """Las entradas de la llegada de los adjuntos de un mensaje y los que van en linea (§3.3).
    Un adjunto sin un id que se pueda guardar es un mensaje raro (ValueError)."""
    entradas: list[dict] = []
    en_linea = tratados = 0
    for adjunto in lista:
        identificador = adjunto.get("id") if isinstance(adjunto, dict) else None
        if not (isinstance(identificador, str) and 0 < len(identificador)
                <= bandeja.MAX_ADJUNTO_ID and identificador.isascii()
                and identificador.isprintable()):
            raise ValueError("un adjunto sin id")
        tipo_graph = str(adjunto.get("@odata.type") or "").lstrip("#").lower()
        if tipo_graph == "microsoft.graph.fileattachment" and adjunto.get("isInline") is True:
            en_linea += 1
            continue
        if len(entradas) >= bandeja.MAX_ADJUNTOS:
            continue
        tamano = adjunto.get("size")
        entrada = {"id": identificador, "nombre": bandeja.sanear(adjunto.get("name"),
                                                                 bandeja.MAX_NOMBRE),
                   "tipo": bandeja.sanear(adjunto.get("contentType"), bandeja.MAX_TIPO),
                   "bytes": tamano if type(tamano) is int and tamano >= 0 else None,
                   "resultado": "no_pdf", "sha256": None, "detalle": None}
        tratados += 1
        if tratados > ADJUNTOS_TRATADOS:
            entrada["detalle"] = (f"demasiados adjuntos en el mensaje (se tratan "
                                  f"{ADJUNTOS_TRATADOS})")
        elif carpeta == "no_deseado":
            entrada["resultado"] = "no_deseado"
        elif tipo_graph == "microsoft.graph.itemattachment":
            entrada["resultado"] = "reenvio"
            entrada["detalle"] = "un correo adjunto: reenvia el PDF como adjunto normal"
        elif tipo_graph == "microsoft.graph.referenceattachment":
            entrada["resultado"] = "enlace"
            entrada["detalle"] = "un enlace (OneDrive o SharePoint): no se sigue"
        elif tipo_graph != "microsoft.graph.fileattachment":
            entrada["detalle"] = "un tipo de adjunto que no se conoce"
        else:
            entrada["resultado"] = _por_nombre_y_tipo(entrada["nombre"], entrada["tipo"])
            if entrada["resultado"] == _BAJAR and (entrada["bytes"] or 0) > MAX_PDF:
                entrada["resultado"] = "demasiado_grande"
                entrada["detalle"] = f"pasa de {MAX_PDF // MIB} MiB: no se baja"
        entradas.append(entrada)
    return entradas, en_linea


def _message_id(valor: object) -> str | None:
    if (isinstance(valor, str) and 0 < len(valor) <= bandeja.MAX_MESSAGE_ID
            and all(0x21 <= ord(c) <= 0x7E for c in valor)):
        return valor
    return None


def _remitente(mensaje: dict) -> str | None:
    de = mensaje.get("from")
    correo = de.get("emailAddress") if isinstance(de, dict) else None
    return bandeja.sanear(correo.get("address") if isinstance(correo, dict) else None,
                          bandeja.MAX_REMITENTE)


def serializar(llegada: dict) -> bytes:
    """La llegada en JSON, sin pasar de 64 KiB: si un mensaje con 50 adjuntos de nombres
    largos no cabe, se acortan los textos y, si aun no, se apuntan menos adjuntos."""
    datos = bandeja.como_json(llegada)
    if len(datos) <= bandeja.MAX_LLEGADA:
        return datos
    corta = dict(llegada, asunto=(llegada["asunto"] or "")[:80] or None,
                 adjuntos=[dict(a, nombre=(a["nombre"] or "")[:80] or None,
                                tipo=(a["tipo"] or "")[:80] or None,
                                detalle=(a["detalle"] or "")[:80] or None)
                           for a in llegada["adjuntos"]])
    while len(datos := bandeja.como_json(corta)) > bandeja.MAX_LLEGADA and corta["adjuntos"]:
        corta["adjuntos"] = corta["adjuntos"][:-1]
    return datos


# ------------------------------------------------------------------ una ronda

@dataclass
class _Rutas:
    ajustes: Path
    certificado: Path
    estado: Path
    entrada: Path | None


@dataclass
class _Hoy:
    fecha: str
    mensajes: int = 0
    pdf: int = 0
    bytes: int = 0


@dataclass
class _Ronda:
    rutas: _Rutas
    transporte: Any
    ahora: Callable[[], datetime]
    dormir: Callable[[float], None]
    forzar_comprobar: bool = False
    empezada: datetime = field(init=False)
    resultado: Resultado = field(default_factory=Resultado)

    def __post_init__(self) -> None:
        self.empezada = self.ahora()
        self.previo = _leer_json(self.rutas.estado / bandeja.ESTADO)
        if not isinstance(self.previo, dict):
            self.previo = {}
        fecha = self.empezada.astimezone(_ZONA).date().isoformat()
        hoy = self.previo.get("hoy")
        self.hoy = _Hoy(fecha)
        if isinstance(hoy, dict) and hoy.get("fecha") == fecha:
            for nombre in ("mensajes", "pdf", "bytes"):
                if type(hoy.get(nombre)) is int and hoy[nombre] >= 0:
                    setattr(self.hoy, nombre, hoy[nombre])
        alcance = self.previo.get("alcance")
        self.alcance = alcance if isinstance(alcance, dict) else None
        self.consultada = False
        self.caduca_en: datetime | None = None
        self.buzon: str | None = None
        self.delta_reiniciado_en = bandeja.leer_instante(self.previo.get("delta_reiniciado_en"))
        self.parar = False
        self.paginas = 0
        self.cliente: graph.ClienteGraph | None = None
        self.ajustes: _ajustes.Ajustes | None = None
        self.vistos: dict[str, Any] = {}
        self.intentos: dict[str, Any] = {}
        self.pendientes: dict[str, Any] = {}

    # -------------------------------------------------------------- el principio y el final

    def _cargar(self) -> _certificado.Credencial:
        """Los ajustes y el certificado (§3.2, paso 2)."""
        problema = None
        try:
            self.ajustes = _ajustes.leer(self.rutas.ajustes)
        except _ajustes.SinAjustes:
            problema = ("sin_configurar", "aun no hay ajustes del correo (correo-configurar)")
        except _ajustes.AjustesNoValidos as exc:
            problema = ("sin_configurar", f"los ajustes del correo no valen: {exc}")
        if problema is not None:
            raise _Fin(*problema)
        assert self.ajustes is not None
        self.buzon = self.ajustes.buzon
        try:
            credencial = _certificado.cargar(self.rutas.certificado)
        except _certificado.SinCertificado:
            problema = ("sin_configurar", "aun no hay certificado del correo (correo-configurar)")
        except _certificado.CertificadoNoValido as exc:
            problema = ("credencial", str(exc))
        if problema is not None:
            raise _Fin(*problema)
        self.caduca_en = credencial.datos.caduca_en
        return credencial

    def _cliente(self, credencial: _certificado.Credencial) -> graph.ClienteGraph:
        assert self.ajustes is not None
        self.cliente = graph.ClienteGraph(self.ajustes, credencial, transporte=self.transporte,
                                          ahora=self.ahora, dormir=self.dormir)
        return self.cliente

    def _toca_comprobar(self) -> bool:
        if self.forzar_comprobar or self.alcance is None or self.alcance.get("bien") is not True:
            return True
        comprobado = bandeja.leer_instante(self.alcance.get("comprobado_en"))
        ronda = self.previo.get("ronda")
        anterior = ronda.get("error_codigo") if isinstance(ronda, dict) else None
        return (comprobado is None or self.empezada - comprobado > VIGENCIA_ALCANCE
                or comprobado > self.empezada + timedelta(minutes=5)
                or anterior in REPETIR_ALCANCE)

    def _comprobar(self) -> None:
        """`correo comprobar` (§2.3). Lo que no es un veredicto (sin red...) es un error de la
        ronda y no cambia el alcance guardado; un veredicto se guarda, sea el que sea."""
        assert self.cliente is not None
        self.consultada = True
        veredicto = self.cliente.comprobar()
        self.resultado.alcance = veredicto
        self.alcance = {"comprobado_en": bandeja.instante(self.ahora()), "bien": veredicto.bien,
                        "motivo_codigo": veredicto.motivo_codigo}
        if not veredicto.bien:
            assert veredicto.motivo_codigo is not None
            raise _Fin(veredicto.motivo_codigo, "la comprobacion de que solo puede leer ese buzon "
                                                "no ha salido bien: no se trae nada")

    def _escribir_estado(self) -> None:
        """estado.json (§3.7), entero o nada."""
        terminada = self.ahora()
        codigo = self.resultado.codigo
        anteriores = {k: self.previo.get(k) for k in ("ultima_consulta", "ultima_buena")}
        ultima_consulta = (bandeja.instante(self.empezada) if self.consultada
                           else anteriores["ultima_consulta"])
        ultima_buena = (bandeja.instante(self.empezada) if self.consultada and codigo is None
                        else anteriores["ultima_buena"])
        alcance = self.alcance or {}
        datos = {
            "version": bandeja.VERSION,
            "ronda": {"empezada": bandeja.instante(self.empezada),
                      "terminada": bandeja.instante(terminada),
                      "resultado": "bien" if codigo is None else "fallo",
                      "error_codigo": codigo, "mensajes": self.resultado.mensajes,
                      "pdf_nuevos": self.resultado.pdf_nuevos, "bytes": self.resultado.bytes},
            "hoy": {"fecha": self.hoy.fecha, "mensajes": self.hoy.mensajes, "pdf": self.hoy.pdf,
                    "bytes": self.hoy.bytes},
            "ultima_consulta": ultima_consulta if isinstance(ultima_consulta, str) else None,
            "ultima_buena": ultima_buena if isinstance(ultima_buena, str) else None,
            "buzon": self.buzon,
            "certificado": {"caduca_en": _texto(self.caduca_en)},
            "alcance": {"comprobado_en": alcance.get("comprobado_en"),
                        "bien": alcance.get("bien"),
                        "motivo_codigo": alcance.get("motivo_codigo")},
            "delta_reiniciado_en": _texto(self.delta_reiniciado_en),
            "retenido_hasta": _texto(self.resultado.retenido_hasta),
            "aviso_volumen": self.hoy.mensajes > AVISO_VOLUMEN,
        }
        _guardar_json(self.rutas.estado / bandeja.ESTADO, datos)

    # -------------------------------------------------------------- correo comprobar

    def comprobar(self) -> Resultado:
        try:
            credencial = self._cargar()
            with self._cliente(credencial):
                self._comprobar()
        except _Fin as fin:
            self.resultado.codigo, self.resultado.detalle = fin.codigo, fin.detalle
        except graph.ErrorGraph as exc:
            self.resultado.codigo, self.resultado.detalle = exc.codigo, exc.detalle
        # Lo retenido por la ultima ronda sigue retenido: comprobar no baja nada.
        retenido = bandeja.leer_instante(self.previo.get("retenido_hasta"))
        if retenido is not None and retenido > self.empezada:
            self.resultado.retenido_hasta = retenido
        self._escribir_estado()
        return self.resultado

    # -------------------------------------------------------------- correo traer

    def traer(self) -> Resultado:
        assert self.rutas.entrada is not None
        estado = self.rutas.estado
        self.intentos = _mapa(_leer_json(estado / bandeja.INTENTOS), "mensajes")
        self.pendientes = _mapa(_leer_json(estado / bandeja.PENDIENTES), "mensajes")
        vistos = _leer_json(estado / bandeja.VISTOS)
        claves = vistos.get("claves") if isinstance(vistos, dict) else None
        self.vistos = ({k: v for k, v in claves.items()
                        if isinstance(k, str) and bandeja.HEX64.fullmatch(k)
                        and isinstance(v, str)} if isinstance(claves, dict) else {})
        try:
            self.llegadas = bandeja.carpeta_propia(self.rutas.entrada / bandeja.ENTRADA_LLEGADAS)
            self.pdf = bandeja.carpeta_propia(self.rutas.entrada / bandeja.ENTRADA_PDF)
            self._sin_parciales()
            self._ronda()
        except _Fin as fin:
            self.resultado.codigo, self.resultado.detalle = fin.codigo, fin.detalle
        except graph.ErrorGraph as exc:
            self.resultado.codigo, self.resultado.detalle = exc.codigo, exc.detalle
        except OSError as exc:
            self.resultado.codigo = "disco" if exc.errno in (28, 122) else "interno"
            self.resultado.detalle = (f"no se puede escribir en la bandeja o el estado: "
                                      f"{exc.strerror or type(exc).__name__}")
        except Exception as exc:
            # Un fallo nuestro fuera de un mensaje: la ronda dice `interno` (sin el texto de la
            # excepcion, que podria llevar algo de lo que llego) y lo traido queda.
            self.resultado.codigo = "interno"
            self.resultado.detalle = f"fallo del programa en la ronda ({type(exc).__name__})"
        finally:
            if self.cliente is not None:
                self.cliente.cerrar()
        self._limpiar()
        self.resultado.pendientes = sum(
            1 for p in self.pendientes.values() for a in p.get("adjuntos", [])
            if isinstance(a, dict) and a.get("resultado") == _PENDIENTE)
        if self._tope_del_dia() is not None:
            self.resultado.retenido_hasta = manana(self.empezada)
        self._escribir_estado()
        return self.resultado

    def _ronda(self) -> None:
        credencial = self._cargar()
        if self._tamano_de_la_bandeja() > MAX_BANDEJA:
            raise _Fin("disco", f"la bandeja pasa de {MAX_BANDEJA // (1024 * MIB)} GiB: lo que "
                               "trae el correo no se esta registrando")
        if self._tope_del_dia() is not None:
            return     # retenido hasta manana: no se pide nada a Graph
        self._cliente(credencial)
        self.consultada = True
        if self._toca_comprobar():
            self._comprobar()
        self._los_pendientes()
        for carpeta in bandeja.CARPETAS:
            if self.parar:
                break
            self._delta(carpeta)

    # -------------------------------------------------------------- los topes

    def _tope_del_dia(self) -> str | None:
        if self.ajustes is None:
            return None
        limites = self.ajustes.limites
        if self.hoy.pdf >= limites.pdf_dia:
            return f"hoy ya se han bajado {self.hoy.pdf} PDF"
        if self.hoy.bytes >= limites.mib_dia * MIB:
            return f"hoy ya se han bajado {self.hoy.bytes // MIB} MiB"
        return None

    def _sin_sitio(self) -> datetime | None:
        """Si ya no cabe otra descarga: cuando volver a probar (la ronda siguiente, o manana
        si es el tope del dia), y la ronda para tras este mensaje."""
        if self._tope_del_dia() is not None:
            self.parar = True
            self.resultado.retenido_hasta = manana(self.empezada)
            return self.resultado.retenido_hasta
        if self.resultado.bytes >= BYTES_RONDA:
            self.parar = True
            return self.empezada
        return None

    def _tamano_de_la_bandeja(self) -> int:
        total = 0
        for carpeta in (self.rutas.entrada, self.llegadas, self.pdf):
            assert carpeta is not None
            with os.scandir(carpeta) as entradas:
                for uno in entradas:
                    if uno.is_file(follow_symlinks=False):
                        total += uno.stat(follow_symlinks=False).st_size
        return total

    # -------------------------------------------------------------- escribir en la bandeja

    def _sin_parciales(self) -> None:
        """Lo que se estaba escribiendo cuando murio la ronda anterior (con el cerrojo en la
        mano no se esta escribiendo nada)."""
        for carpeta in (self.rutas.entrada, self.rutas.estado):
            assert carpeta is not None
            with os.scandir(carpeta) as entradas:
                for uno in entradas:
                    if uno.name.startswith(bandeja.PARCIAL) and uno.is_file(
                            follow_symlinks=False):
                        with contextlib.suppress(OSError):
                            os.unlink(uno.path)

    def _escribir_llegada(self, clave: str, llegada: dict) -> None:
        destino = self.llegadas / bandeja.nombre_llegada(clave)
        if not os.path.lexists(destino):
            assert self.rutas.entrada is not None
            bandeja.escribir_de_una_vez(self.rutas.entrada, destino, serializar(llegada))
            self.resultado.mensajes += 1
            self.hoy.mensajes += 1
        self.vistos[clave] = bandeja.instante(self.ahora())

    def _bajar(self, graph_id: str, entrada: dict) -> graph.ErrorGraph | None:
        """Baja un candidato a PDF (§3.3) por trozos a .parcial-<aleatorio> y, si empieza por
        %PDF-, lo deja en pdf/<sha256>.pdf. Devuelve el error de Graph si no se pudo bajar (la
        entrada queda pendiente)."""
        assert self.cliente is not None and self.rutas.entrada is not None
        descriptor, parcial = tempfile.mkstemp(prefix=bandeja.PARCIAL, dir=self.rutas.entrada)
        error = None
        bajado = None
        try:
            with os.fdopen(descriptor, "wb") as fichero:
                try:
                    bajado = self.cliente.bajar(graph_id, entrada["id"], fichero)
                except graph.ErrorGraph as exc:
                    error = exc
                else:
                    fichero.flush()
                    os.fsync(fichero.fileno())
            if bajado is None:
                entrada["resultado"] = _PENDIENTE
                return error
            self.resultado.bytes += bajado.recibidos
            self.hoy.bytes += bajado.recibidos
            if bajado.cortado:
                entrada.update(resultado="demasiado_grande", bytes=bajado.recibidos,
                               detalle=f"pasa de {MAX_PDF // MIB} MiB al bajarlo")
            elif not bajado.es_pdf:
                entrada.update(resultado="no_es_pdf", bytes=bajado.escritos,
                               detalle="no empieza por %PDF-")
            else:
                destino = self.pdf / bandeja.nombre_pdf(bajado.sha256)
                if not os.path.lexists(destino):
                    os.replace(parcial, destino)
                entrada.update(resultado="pdf", bytes=bajado.escritos, sha256=bajado.sha256,
                               detalle=None)
                self.resultado.pdf_nuevos += 1
                self.hoy.pdf += 1
            return None
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(parcial)

    def _bajar_lo_que_quepa(self, graph_id: str, entradas: list[dict]) -> tuple[
            datetime | None, graph.ErrorGraph | None]:
        """Baja los candidatos de un mensaje mientras quepan. Devuelve cuando volver a probar
        los que se quedan pendientes (None si no queda ninguno) y, si Graph fallo para toda la
        ronda (sin red...), ese error: la ronda para despues de apuntar el mensaje."""
        proximo: datetime | None = None
        de_la_ronda = None
        for entrada in entradas:
            if entrada["resultado"] not in (_BAJAR, _PENDIENTE):
                continue
            if de_la_ronda is not None:
                entrada["resultado"] = _PENDIENTE
                continue
            sitio = self._sin_sitio()
            if sitio is not None:
                entrada["resultado"] = _PENDIENTE
                proximo = sitio if proximo is None else max(proximo, sitio)
                continue
            error = self._bajar(graph_id, entrada)
            if error is not None:
                espera = self.ahora() + PENDIENTE_CADA
                proximo = espera if proximo is None else max(proximo, espera)
                if error.para_la_ronda:
                    de_la_ronda = error
        return proximo, de_la_ronda

    def _apuntar(self, clave: str, llegada: dict, entradas: list[dict],
                 proximo: datetime | None, desde: str | None = None) -> None:
        """La llegada, si todo tiene ya su resultado; si no, a pendientes (o, con pendientes
        lleno, lo que falta como `error`)."""
        quedan = [e for e in entradas if e["resultado"] == _PENDIENTE]
        if quedan and len(self.pendientes) >= MAX_PENDIENTES and clave not in self.pendientes:
            for entrada in quedan:
                entrada.update(resultado="error", detalle="no se ha podido traer")
            quedan = []
        if quedan:
            self.pendientes[clave] = {
                "llegada": llegada, "adjuntos": entradas,
                "desde": desde or bandeja.instante(self.ahora()),
                "proximo": bandeja.instante(proximo or self.ahora() + PENDIENTE_CADA)}
        else:
            self._escribir_llegada(clave, dict(llegada, adjuntos=entradas))
            if self.pendientes.pop(clave, None) is None:
                return
        self._guardar_pendientes()

    def _guardar_pendientes(self) -> None:
        _guardar_json(self.rutas.estado / bandeja.PENDIENTES,
                      {"version": bandeja.VERSION, "mensajes": self.pendientes})

    # -------------------------------------------------------------- 7. los pendientes

    def _los_pendientes(self) -> None:
        orden = sorted(self.pendientes, key=lambda k: str(self.pendientes[k].get("desde")))
        for clave in orden:
            if self.parar:
                return
            pendiente = self.pendientes[clave]
            llegada, entradas = pendiente.get("llegada"), pendiente.get("adjuntos")
            desde = bandeja.leer_instante(pendiente.get("desde"))
            proximo = bandeja.leer_instante(pendiente.get("proximo"))
            if (not isinstance(llegada, dict) or not isinstance(entradas, list) or desde is None
                    or proximo is None or not graph.id_valido(llegada.get("graph_id"))):
                del self.pendientes[clave]       # no es nuestro: fuera
                continue
            ahora = self.ahora()
            if ahora - desde >= PENDIENTE_DURA:
                for entrada in entradas:
                    if entrada.get("resultado") == _PENDIENTE:
                        entrada.update(resultado="error",
                                       detalle="no se ha podido traer en 24 horas")
                self._apuntar(clave, llegada, entradas, None, pendiente["desde"])
                continue
            if ahora < proximo:
                continue
            nuevo, de_la_ronda = self._bajar_lo_que_quepa(llegada["graph_id"], entradas)
            self._apuntar(clave, llegada, entradas, nuevo, pendiente["desde"])
            if de_la_ronda is not None:
                raise _Fin(de_la_ronda.codigo, de_la_ronda.detalle)
        self._guardar_pendientes()

    # -------------------------------------------------------------- 8 y 9. la delta

    def _desde(self, al_dia_en: datetime | None) -> datetime:
        """Desde cuando se pide la primera vez (o al empezar otra vez): `desde` de los ajustes
        o, si ya se estuvo al dia, tres dias antes de eso (lo repetido lo descarta registrar)."""
        assert self.ajustes is not None
        inicio = _inicio_del_dia(self.ajustes.desde)
        if al_dia_en is None:
            return inicio
        return max(inicio, al_dia_en - MARGEN_DELTA)

    def _delta(self, carpeta: str) -> None:
        assert self.cliente is not None
        ruta = self.rutas.estado / bandeja.DELTA[carpeta]
        guardado = _leer_json(ruta)
        enlace = guardado.get("enlace") if isinstance(guardado, dict) else None
        al_dia_en = bandeja.leer_instante(guardado.get("al_dia_en")) if isinstance(
            guardado, dict) else None
        if enlace is not None and not graph.enlace_valido(enlace):
            enlace = None
            self.delta_reiniciado_en = self.ahora()
        empezado_de_nuevo = False
        while True:
            try:
                for pagina in self.cliente.delta(carpeta, enlace, self._desde(al_dia_en)):
                    completa = self._pagina(carpeta, pagina)
                    if not completa:
                        return
                    if pagina.siguiente is not None:
                        _guardar_json(ruta, {"version": bandeja.VERSION,
                                             "enlace": pagina.siguiente,
                                             "al_dia_en": _texto(al_dia_en)})
                    else:
                        _guardar_json(ruta, {"version": bandeja.VERSION, "enlace": pagina.delta,
                                             "al_dia_en": bandeja.instante(self.empezada)})
                    self._guardar_vistos()
                    self.paginas += 1
                    if (self.resultado.mensajes >= MENSAJES_RONDA
                            or self.paginas >= PAGINAS_RONDA):
                        self.parar = True
                    if self.parar:
                        return
                return
            except graph.DeltaCaducado:
                if empezado_de_nuevo:
                    raise _Fin("interno", "la delta caduca tambien al empezarla de nuevo") from None
            empezado_de_nuevo = True
            enlace = None
            self.delta_reiniciado_en = self.ahora()
            with contextlib.suppress(FileNotFoundError):
                os.unlink(ruta)

    def _pagina(self, carpeta: str, pagina: graph.Pagina) -> bool:
        """Cada mensaje de una pagina, cada uno con su propio limite de errores. Completa si
        cada mensaje quedo apuntado (o pendiente, o es de los que no se apuntan)."""
        completa = True
        for mensaje in pagina.mensajes:
            if self.parar:
                return False
            if not self._mensaje(carpeta, mensaje):
                completa = False
        return completa and not self.parar

    def _mensaje(self, carpeta: str, mensaje: Any) -> bool:
        """Un mensaje (§3.2, paso 8). False si fallo (cuenta su intento y la pagina se repite)."""
        if not isinstance(mensaje, dict) or "@removed" in mensaje:
            return True
        graph_id = mensaje.get("id")
        if not graph.id_valido(graph_id):
            return True      # sin un id que se pueda guardar no hay llegada posible
        clave = bandeja.clave(graph_id, carpeta)
        if clave in self.vistos or clave in self.pendientes:
            return True
        if os.path.lexists(self.llegadas / bandeja.nombre_llegada(clave)):
            self.vistos[clave] = bandeja.instante(self.ahora())    # escrita, sin registrar
            return True
        antes = self.intentos.get(clave)
        hechos = antes.get("n") if isinstance(antes, dict) else 0
        hechos = hechos if type(hechos) is int and hechos >= 0 else 0
        if hechos >= MAX_INTENTOS:
            self._llegada_de_error(carpeta, mensaje, clave)
            self._intento(clave, None)
            return True
        self._intento(clave, {"n": hechos + 1, "en": (antes or {}).get("en")
                              or bandeja.instante(self.ahora())})
        try:
            self._traer_mensaje(carpeta, mensaje, clave)
        except graph.ErrorGraph as exc:
            if exc.para_la_ronda:
                self._intento(clave, antes)
                raise _Fin(exc.codigo, exc.detalle) from None
            self.resultado.fallidos += 1
            return False
        except _Fin:
            self._intento(clave, None)
            raise
        except OSError:
            # La bandeja o el estado (el disco): de la ronda, no del mensaje.
            self._intento(clave, antes)
            raise
        except Exception:
            # Un mensaje raro (o un fallo nuestro con el): su intento queda contado y la ronda
            # sigue con el siguiente.
            self.resultado.fallidos += 1
            return False
        self._intento(clave, None)
        return True

    def _intento(self, clave: str, valor: dict | None) -> None:
        if valor is None:
            if self.intentos.pop(clave, None) is None:
                return
        else:
            self.intentos[clave] = valor
        _guardar_json(self.rutas.estado / bandeja.INTENTOS,
                      {"version": bandeja.VERSION, "mensajes": self.intentos})

    def _cabecera(self, carpeta: str, mensaje: dict, *, tolerante: bool = False) -> dict:
        """Lo que se apunta del mensaje (§3.6): nunca su cuerpo, ni destinatarios, ni
        cabeceras; el asunto y el remitente, saneados."""
        recibido = bandeja.leer_instante(mensaje.get("receivedDateTime"))
        if recibido is None and not tolerante:
            raise ValueError("receivedDateTime")
        return {"version": bandeja.VERSION, "carpeta": carpeta, "graph_id": mensaje["id"],
                "internet_message_id": _message_id(mensaje.get("internetMessageId")),
                "recibido_en": bandeja.SIN_FECHA if recibido is None
                else bandeja.instante(recibido),
                "remitente": _remitente(mensaje),
                "asunto": bandeja.sanear(mensaje.get("subject"), bandeja.MAX_ASUNTO),
                "en_linea": 0, "traido_en": bandeja.instante(self.ahora()), "adjuntos": []}

    def _traer_mensaje(self, carpeta: str, mensaje: dict, clave: str) -> None:
        assert self.cliente is not None
        llegada = self._cabecera(carpeta, mensaje)
        lista = (self.cliente.adjuntos(mensaje["id"])
                 if mensaje.get("hasAttachments") is not False else [])
        entradas, llegada["en_linea"] = clasificar(carpeta, lista)
        proximo, de_la_ronda = self._bajar_lo_que_quepa(mensaje["id"], entradas)
        self._apuntar(clave, llegada, entradas, proximo)
        if de_la_ronda is not None:
            raise _Fin(de_la_ronda.codigo, de_la_ronda.detalle)

    def _llegada_de_error(self, carpeta: str, mensaje: dict, clave: str) -> None:
        """Un mensaje que ha fallado tres rondas: su llegada, con cada adjunto que se pueda
        listar como `error`, y la ronda sigue (§3.2, paso 8)."""
        assert self.cliente is not None
        llegada = self._cabecera(carpeta, mensaje, tolerante=True)
        entradas: list[dict] = []
        if mensaje.get("hasAttachments") is not False:
            try:
                lista = self.cliente.adjuntos(mensaje["id"])
                entradas, llegada["en_linea"] = clasificar(carpeta, [
                    a for a in lista if isinstance(a, dict) and isinstance(a.get("id"), str)
                    and 0 < len(a["id"]) <= bandeja.MAX_ADJUNTO_ID and a["id"].isascii()
                    and a["id"].isprintable()])
            except graph.ErrorGraph as exc:
                if exc.para_la_ronda:
                    raise _Fin(exc.codigo, exc.detalle) from None
            except Exception:
                entradas = []
        for entrada in entradas:
            entrada.update(resultado="error", sha256=None,
                           detalle="no se ha podido procesar el mensaje")
        self._escribir_llegada(clave, dict(llegada, adjuntos=entradas))

    def _guardar_vistos(self) -> None:
        _guardar_json(self.rutas.estado / bandeja.VISTOS,
                      {"version": bandeja.VERSION, "claves": self.vistos})

    # -------------------------------------------------------------- 10. la limpieza

    def _limpiar(self) -> None:
        """Lo de la bandeja de mas de 45 dias (lo que registrar no se llevo), los intentos de
        mas de 7 dias y los vistos de mas de 7 dias (como mucho MAX_VISTOS)."""
        ahora = self.ahora()
        limite = (ahora - VIEJO_EN_LA_BANDEJA).timestamp()
        for carpeta in (getattr(self, "llegadas", None), getattr(self, "pdf", None)):
            if carpeta is None:
                continue
            with contextlib.suppress(OSError), os.scandir(carpeta) as entradas:
                for uno in entradas:
                    with contextlib.suppress(OSError):
                        if (uno.is_file(follow_symlinks=False)
                                and uno.stat(follow_symlinks=False).st_mtime < limite):
                            os.unlink(uno.path)
        if not hasattr(self, "llegadas"):
            return

        def reciente(texto: Any) -> bool:
            momento = bandeja.leer_instante(texto)
            return momento is not None and ahora - momento <= VIEJO_EN_EL_ESTADO

        with contextlib.suppress(OSError):
            viejos = [k for k, v in self.intentos.items() if not reciente(v.get("en"))]
            for clave in viejos:
                del self.intentos[clave]
            if viejos:
                _guardar_json(self.rutas.estado / bandeja.INTENTOS,
                              {"version": bandeja.VERSION, "mensajes": self.intentos})
            vistos = sorted(((v, k) for k, v in self.vistos.items() if reciente(v)),
                            reverse=True)[:MAX_VISTOS]
            self.vistos = {k: v for v, k in sorted(vistos)}
            self._guardar_vistos()


# ------------------------------------------------------------------ lo que llama la CLI

def traer(*, ajustes: str | Path, certificado: str | Path, estado: str | Path,
          entrada: str | Path, comprobar: bool = False, transporte: Any = None,
          ahora: Callable[[], datetime] = RELOJ_SISTEMA.ahora,
          dormir: Callable[[float], None] = time.sleep) -> Resultado:
    """Una ronda (`correo traer`). `transporte` es para las pruebas (GraphFalso); en
    produccion, ninguno (sale por HTTPS_PROXY)."""
    rutas = _Rutas(Path(ajustes), Path(certificado),
                   bandeja.carpeta_propia(Path(estado)), bandeja.carpeta_propia(Path(entrada)))
    with cerrojo(rutas.estado) as tomado:
        if not tomado:
            return Resultado(ocupado=True)
        return _Ronda(rutas, transporte, ahora, dormir, forzar_comprobar=comprobar).traer()


def comprobar(*, ajustes: str | Path, certificado: str | Path, estado: str | Path,
              transporte: Any = None, ahora: Callable[[], datetime] = RELOJ_SISTEMA.ahora,
              dormir: Callable[[float], None] = time.sleep) -> Resultado:
    """`correo comprobar` (§2.3): solo la comprobacion, con su resultado en estado.json."""
    rutas = _Rutas(Path(ajustes), Path(certificado), bandeja.carpeta_propia(Path(estado)), None)
    with cerrojo(rutas.estado) as tomado:
        if not tomado:
            return Resultado(ocupado=True)
        return _Ronda(rutas, transporte, ahora, dormir, forzar_comprobar=True).comprobar()
