"""La bandeja del correo de facturas (paso 18, diseno §3.2, §3.7): sus nombres y sus formatos.

Lo que escribe el componente `correo` (correo/traer.py) y lo que lee `orden` al registrarlo
(paso 10) es esto, en un solo sitio, para que los dos digan lo mismo y para que quien lee la
bandeja no tenga que importar el cliente de Graph ni el certificado:

    entrada/pdf/<sha256>.pdf                         un PDF bajado (empieza por %PDF-)
    entrada/llegadas/<sha256(graph_id|carpeta)>.json la llegada de un mensaje y sus adjuntos
    entrada/.parcial-<aleatorio>                     lo que se esta escribiendo (se renombra)
    estado/estado.json                               la ultima ronda, lo de hoy, el alcance
    estado/delta-bandeja.json, delta-no-deseado.json donde sigue cada carpeta
    estado/intentos.json, pendientes.json, vistos.json, traer.cerrojo

Los nombres los genera el codigo (hexadecimal): nada de lo que llega del buzon toca el sistema
de ficheros. Todo lo que viene del buzon (el asunto, el remitente, el nombre de un adjunto) es
texto de terceros, no confiable: se guarda saneado y recortado, nunca como instrucciones.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1

CARPETAS = ("bandeja", "no_deseado")
# Lo que el correo dice de cada adjunto (§3.7, cerrado). `registrar` lo pasa a adjunto_correo
# (pdf -> documento, o de_prueba).
RESULTADOS = ("pdf", "no_es_pdf", "demasiado_grande", "xml", "reenvio", "no_pdf", "enlace",
              "no_deseado", "error")
# Los codigos de error del correo (§3.7, cerrados): los mismos en estado.json, en
# `correo registrar --fallo` y en la API. `ocupado` no es un error: la ronda se salta.
CODIGOS = ("sin_configurar", "credencial", "reloj", "permiso", "alcance", "control_no_existe",
           "sin_conexion", "limitado", "aislamiento", "salida", "disco", "interno")

ENTRADA_PDF = "pdf"
ENTRADA_LLEGADAS = "llegadas"
PARCIAL = ".parcial-"
ESTADO = "estado.json"
DELTA = {"bandeja": "delta-bandeja.json", "no_deseado": "delta-no-deseado.json"}
INTENTOS = "intentos.json"
PENDIENTES = "pendientes.json"
VISTOS = "vistos.json"
CERROJO = "traer.cerrojo"

# Los limites de una llegada (§3.8, paso 4): lo que `registrar` acepta.
MAX_LLEGADA = 64 * 1024
MAX_ADJUNTOS = 50
MAX_GRAPH_ID = 512
MAX_ADJUNTO_ID = 512
MAX_MESSAGE_ID = 998
MAX_REMITENTE = 320
MAX_ASUNTO = 200
MAX_NOMBRE = 255
MAX_TIPO = 255
MAX_DETALLE = 200

GRAPH_ID = re.compile(r"[A-Za-z0-9+/=_-]{1,512}")
HEX64 = re.compile(r"[0-9a-f]{64}")
NOMBRE_LLEGADA = re.compile(r"[0-9a-f]{64}\.json")
NOMBRE_PDF = re.compile(r"[0-9a-f]{64}\.pdf")
# Lo que dice que no se sabe la hora de recepcion (antes de 2000: §3.8, paso 4).
SIN_FECHA = "1970-01-01T00:00:00Z"

# Lo que se quita de un texto de terceros: controles (tambien el tabulador y los saltos),
# formato (los de direccion bidi, los de anchura cero), sustitutos sueltos, uso privado y los
# separadores de linea y de parrafo.
_FUERA = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}


def clave(graph_id: str, carpeta: str) -> str:
    """La clave de una llegada: sha256 de "graph_id|carpeta" (§3.4). El mismo mensaje pasado
    de "no deseado" a la bandeja es otra llegada."""
    if carpeta not in CARPETAS:
        raise ValueError("carpeta del correo desconocida")
    return hashlib.sha256(f"{graph_id}|{carpeta}".encode("utf-8")).hexdigest()


def nombre_llegada(clave_llegada: str) -> str:
    if not HEX64.fullmatch(clave_llegada):
        raise ValueError("la clave de una llegada es un sha256 en hexadecimal")
    return f"{clave_llegada}.json"


def nombre_pdf(sha256: str) -> str:
    if not HEX64.fullmatch(sha256):
        raise ValueError("el nombre de un PDF es su sha256 en hexadecimal")
    return f"{sha256}.pdf"


def sanear(texto: object, maximo: int) -> str | None:
    """Un texto de terceros para guardarlo y ensenarlo: sin controles, sin caracteres de
    direccion ni de anchura cero, con los blancos juntos y recortado a `maximo`. None si no es
    texto o queda vacio."""
    if not isinstance(texto, str):
        return None
    limpio = "".join(" " if c in "\t\r\n" else c for c in texto
                     if c in "\t\r\n" or unicodedata.category(c) not in _FUERA)
    limpio = " ".join(limpio.split())
    return limpio[:maximo] or None


def instante(momento: datetime) -> str:
    """Un instante en UTC como lo escribe la bandeja: AAAA-MM-DDTHH:MM:SSZ (el ano con cuatro
    cifras tambien antes del 1000, que strftime("%Y") no rellena)."""
    if momento.tzinfo is None:
        raise ValueError("un instante sin zona horaria no se sabe de cuando es")
    utc = momento.astimezone(timezone.utc)
    return (f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T{utc.hour:02d}:{utc.minute:02d}:"
            f"{utc.second:02d}Z")


def leer_instante(texto: object) -> datetime | None:
    """Un instante ISO-8601 con zona (el receivedDateTime de Graph, o los de la bandeja), en
    UTC; None si no lo es."""
    if not isinstance(texto, str) or not 10 <= len(texto) <= 40 or not texto.isascii():
        return None
    try:
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00").replace("z", "+00:00"))
        if momento.tzinfo is None:
            return None
        # Pasarlo a UTC desborda en los extremos (0001-01-01T00:00:00+01:00 seria el ano 0).
        return momento.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def como_json(datos: object) -> bytes:
    return (json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=False) + "\n").encode(
        "utf-8")


def escribir_de_una_vez(carpeta_parcial: Path, destino: Path, contenido: bytes) -> None:
    """Escribe `destino` entero o nada: aparte (en `carpeta_parcial`, en el mismo disco, con
    un nombre al azar que empieza por .parcial-), lo lleva al disco y le cambia el nombre."""
    descriptor, temporal = tempfile.mkstemp(prefix=PARCIAL, dir=carpeta_parcial)
    try:
        with os.fdopen(descriptor, "wb") as fichero:
            fichero.write(contenido)
            fichero.flush()
            os.fsync(fichero.fileno())
        os.replace(temporal, destino)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporal)
        raise


def carpeta_propia(ruta: Path) -> Path:
    """Una carpeta de la bandeja o del estado: la crea si no esta y exige que sea una carpeta de
    verdad, no un enlace a otra parte."""
    with contextlib.suppress(FileExistsError):
        ruta.mkdir(mode=0o700)
    if ruta.is_symlink() or not ruta.is_dir():
        raise NotADirectoryError(f"{ruta.name}: no es una carpeta de verdad")
    return ruta
