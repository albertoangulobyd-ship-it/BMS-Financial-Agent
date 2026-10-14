"""Almacen de documentos originales: se escribe una vez y se direcciona por hash.

Cada original vive en datos/documentos/<sha[:2]>/<sha256>.<ext>, de solo
lectura (0444). La ruta sale del hash de los bytes, asi que el mismo PDF
llegado dos veces ocupa un fichero, y un fichero con otro contenido no puede
hacerse pasar por el: `verificar()` vuelve a calcular cada hash.

Escribir nunca pisa. Si la ruta ya existe y su contenido es el que dice su
nombre, guardar no hace nada; si no lo es, se niega y avisa: un original
alterado es evidencia de algo y no se repara en silencio. La escritura va a
un temporal que se enlaza con su nombre final, asi que un corte a mitad no
deja un original a medias con nombre de bueno.

La tabla documento apunta cada original con su procedencia. Abrir un
original queda en la auditoria (evento documento_abierto), tambien cuando
falla.
"""

from __future__ import annotations

import os
import re
import sqlite3
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..auditoria import registrar
from ..reloj import marca
from . import Almacen, reloj_de, transaccion
from .evidencia import foto
from .unidades import es_sha256, sha256_bytes

MODO_SOLO_LECTURA = 0o444
EXTENSIONES = {"application/pdf": "pdf"}
_EXTENSION = re.compile(r"^[a-z0-9]{1,10}$")
_RELATIVA = re.compile(r"^([0-9a-f]{2})/([0-9a-f]{64})\.([a-z0-9]{1,10})$")
_TEMPORAL = ".entrando-"


class DocumentoCorrupto(RuntimeError):
    """Un original del almacen no coincide con su hash, o no esta."""


def extension_de(tipo_mime: str, nombre: str | None = None) -> str:
    """La extension con la que se guarda: por el tipo, o por el nombre, o 'bin'."""
    if tipo_mime in EXTENSIONES:
        return EXTENSIONES[tipo_mime]
    sufijo = Path(nombre or "").suffix.lower().lstrip(".")
    return sufijo if _EXTENSION.match(sufijo) else "bin"


class AlmacenDocumentos:
    """La carpeta de originales. No sabe nada de la base: solo bytes y hashes."""

    def __init__(self, raiz: str | Path) -> None:
        self.raiz = Path(raiz)

    @staticmethod
    def ruta_relativa(sha256: str, extension: str) -> str:
        if not es_sha256(sha256):
            raise ValueError(f"no es un sha256: {sha256!r}")
        if not _EXTENSION.match(extension):
            raise ValueError(f"extension no valida: {extension!r}")
        return f"{sha256[:2]}/{sha256}.{extension}"

    def ruta(self, relativa: str) -> Path:
        """La ruta en disco de una ruta relativa del almacen, y nada fuera de el."""
        coincide = _RELATIVA.match(relativa or "")
        if coincide is None or coincide.group(2)[:2] != coincide.group(1):
            raise ValueError(f"no es una ruta del almacen de documentos: {relativa!r}")
        return self.raiz / coincide.group(1) / f"{coincide.group(2)}.{coincide.group(3)}"

    def guardar(self, contenido: bytes, extension: str) -> str:
        """Guarda el original y devuelve su ruta relativa. Nunca sobrescribe."""
        sha256 = sha256_bytes(contenido)
        relativa = self.ruta_relativa(sha256, extension)
        destino = self.ruta(relativa)
        if destino.exists():
            self._exigir_intacto(destino, sha256)
            return relativa

        destino.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporal = tempfile.mkstemp(dir=destino.parent, prefix=_TEMPORAL)
        try:
            with os.fdopen(descriptor, "wb") as fichero:
                fichero.write(contenido)
                fichero.flush()
                os.fsync(fichero.fileno())
            os.chmod(temporal, MODO_SOLO_LECTURA)
            try:
                os.link(temporal, destino)          # falla si ya existe: no pisa
            except FileExistsError:
                self._exigir_intacto(destino, sha256)
            except OSError:
                # Un sistema de ficheros sin enlaces duros: creacion exclusiva.
                with destino.open("xb") as fichero:
                    fichero.write(contenido)
                os.chmod(destino, MODO_SOLO_LECTURA)
        finally:
            _borrar(Path(temporal))
        return relativa

    def leer(self, relativa: str, sha256: str) -> bytes:
        destino = self.ruta(relativa)
        try:
            contenido = destino.read_bytes()
        except FileNotFoundError:
            raise DocumentoCorrupto(f"falta el original {relativa}") from None
        if sha256_bytes(contenido) != sha256:
            raise DocumentoCorrupto(f"el original {relativa} no coincide con su hash")
        return contenido

    def comprobar(self, relativa: str, sha256: str) -> list[str]:
        """Lo que esta mal en un original: que falte, que no cuadre, que se pueda escribir."""
        try:
            destino = self.ruta(relativa)
        except ValueError as exc:
            return [str(exc)]
        if not destino.is_file():
            return [f"falta el original {relativa}"]
        problemas = []
        if sha256_bytes(destino.read_bytes()) != sha256:
            problemas.append(f"el original {relativa} no coincide con su hash")
        if os.name == "posix" and stat.S_IMODE(destino.stat().st_mode) & 0o222:
            problemas.append(f"el original {relativa} se puede escribir (deberia ser 0444)")
        return problemas

    def ficheros(self) -> list[str]:
        """Todas las rutas relativas que hay en la carpeta, temporales incluidos."""
        if not self.raiz.is_dir():
            return []
        return sorted(
            f"{carpeta.name}/{fichero.name}"
            for carpeta in self.raiz.iterdir() if carpeta.is_dir()
            for fichero in carpeta.iterdir() if fichero.is_file()
        )

    def _exigir_intacto(self, destino: Path, sha256: str) -> None:
        if sha256_bytes(destino.read_bytes()) != sha256:
            raise DocumentoCorrupto(
                f"{destino} ya existe y no coincide con su hash: no se sobrescribe; "
                "revisa quien lo ha tocado"
            )


def _borrar(ruta: Path) -> None:
    """Borra un temporal; en Windows un fichero de solo lectura hay que soltarlo antes."""
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass
    except PermissionError:
        os.chmod(ruta, 0o600)
        ruta.unlink()


@dataclass(frozen=True)
class DocumentoRegistrado:
    id: int
    nuevo: bool
    # guardado | anadido (el original llego despues) | ya_estaba | falta
    original: str


def registrar_documento(
    almacen: Almacen,
    *,
    sha256: str,
    contenido: bytes | None,
    nombre_original: str | None,
    tipo_mime: str,
    origen: str,
    ruta_declarada: str,
    recibido_en: str | None,
    recibido_fuente: str,
    actor: int,
    usuario_id: int | None = None,
    mensaje_id: str | None = None,
) -> DocumentoRegistrado:
    """Apunta un documento por su hash, con su original si se tiene.

    Un documento que ya estaba no cambia, con una excepcion: si se registro
    sin original y ahora llegan sus bytes, el original se guarda y se apunta.
    Es la unica modificacion que la tabla admite.
    """
    if not es_sha256(sha256):
        raise ValueError(f"no es un sha256: {sha256!r}")
    if contenido is not None and sha256_bytes(contenido) != sha256:
        raise ValueError("el contenido no es el del hash que se registra")

    conn = almacen.conn
    extension = extension_de(tipo_mime, nombre_original)
    with transaccion(conn):
        existente = conn.execute(
            "SELECT id, ruta_cas FROM documento WHERE sha256 = ?", (sha256,)
        ).fetchone()
        if existente is not None:
            if existente["ruta_cas"] is not None or contenido is None:
                estado = "ya_estaba" if existente["ruta_cas"] is not None else "falta"
                return DocumentoRegistrado(existente["id"], False, estado)
            relativa = almacen.documentos.guardar(contenido, extension)
            conn.execute(
                "UPDATE documento SET ruta_cas = ?, bytes = ? WHERE id = ?",
                (relativa, len(contenido), existente["id"]),
            )
            registrar(
                conn, tipo="documento_original_anadido", actor=actor, usuario_id=usuario_id,
                tabla="documento", fila_id=existente["id"],
                datos={"ruta_cas": relativa, "bytes": len(contenido),
                       "fila": foto(conn, "documento", existente["id"])},
            )
            return DocumentoRegistrado(existente["id"], False, "anadido")

        relativa = almacen.documentos.guardar(contenido, extension) if contenido is not None else None
        cursor = conn.execute(
            "INSERT INTO documento (sha256, nombre_original, tipo_mime, bytes, ruta_cas, origen, "
            "ruta_declarada, mensaje_id, recibido_en, recibido_fuente, registrado_en, "
            "registrado_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sha256, nombre_original, tipo_mime,
             len(contenido) if contenido is not None else None, relativa, origen,
             ruta_declarada, mensaje_id, recibido_en, recibido_fuente,
             marca(reloj_de(conn).ahora()), actor),
        )
        documento_id = int(cursor.lastrowid)
        registrar(
            conn, tipo="documento_registrado", actor=actor, usuario_id=usuario_id,
            tabla="documento", fila_id=documento_id,
            datos={"sha256": sha256, "origen": origen, "ruta_declarada": ruta_declarada,
                   "original": "guardado" if relativa else "falta",
                   "fila": foto(conn, "documento", documento_id)},
        )
        return DocumentoRegistrado(documento_id, True, "guardado" if relativa else "falta")


def abrir(
    almacen: Almacen,
    documento_id: int,
    *,
    actor: int,
    usuario_id: int | None = None,
    motivo: str | None = None,
) -> bytes:
    """Los bytes de un original, comprobados. Cada apertura queda auditada.

    Si el original falta o no cuadra, el intento tambien queda (resultado
    error) y despues se lanza DocumentoCorrupto: el evento se confirma antes
    de lanzar, para que el fallo no se lleve su propio rastro.

    Por eso se niega a correr dentro de una transaccion abierta: ahi su
    evento seria solo un SAVEPOINT, y el ROLLBACK de quien llama al recibir
    DocumentoCorrupto borraria el registro de la apertura fallida. Quien
    abre un original lo hace fuera de su orden, antes o despues.
    """
    conn = almacen.conn
    if conn.in_transaction:
        raise RuntimeError(
            "abrir un original se audita en su propia transaccion; hay una abierta"
        )
    fila = conn.execute(
        "SELECT sha256, ruta_cas FROM documento WHERE id = ?", (documento_id,)
    ).fetchone()
    if fila is None:
        raise LookupError(f"no hay documento {documento_id}")

    error: DocumentoCorrupto | None = None
    contenido = b""
    if fila["ruta_cas"] is None:
        error = DocumentoCorrupto(f"el documento {documento_id} no tiene el original guardado")
    else:
        try:
            contenido = almacen.documentos.leer(fila["ruta_cas"], fila["sha256"])
        except DocumentoCorrupto as exc:
            error = exc

    with transaccion(conn):
        registrar(
            conn, tipo="documento_abierto", actor=actor, usuario_id=usuario_id,
            resultado="error" if error else "ok", tabla="documento", fila_id=documento_id,
            motivo=motivo, datos={"error": str(error)} if error else None,
        )
    if error is not None:
        raise error
    return contenido


@dataclass(frozen=True)
class Problema:
    gravedad: str        # error | aviso
    detalle: str
    documento_id: int | None = None


def verificar(almacen: Almacen) -> list[Problema]:
    """Vuelve a calcular el hash de cada original apuntado, y busca lo que sobra.

    Un fichero en la carpeta que ninguna fila apunta es un aviso, no un
    error: es lo que deja una transaccion que se deshizo despues de guardar
    el original (el original se guarda antes del INSERT, a proposito, para
    que nunca haya una fila que apunte a un fichero que no existe).
    """
    problemas = []
    apuntados = set()
    filas = almacen.conn.execute(
        "SELECT id, sha256, ruta_cas FROM documento WHERE ruta_cas IS NOT NULL ORDER BY id"
    )
    for fila in filas:
        apuntados.add(fila["ruta_cas"])
        for detalle in almacen.documentos.comprobar(fila["ruta_cas"], fila["sha256"]):
            problemas.append(Problema("error", detalle, fila["id"]))
    for relativa in almacen.documentos.ficheros():
        if relativa not in apuntados:
            problemas.append(Problema(
                "aviso", f"{relativa} esta en la carpeta y ningun documento lo apunta"
            ))
    return problemas


def instante_de_fichero(ruta: str | Path) -> str:
    """La fecha de modificacion de un fichero, como marca UTC (recibido_fuente 'mtime').

    No dice cuando llego el documento, solo cuando se escribio el fichero
    que se tiene; por eso queda marcada con su fuente y no como recepcion.
    """
    return marca(datetime.fromtimestamp(Path(ruta).stat().st_mtime, tz=timezone.utc))


def documento_por_sha(conn: sqlite3.Connection, sha256: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM documento WHERE sha256 = ?", (sha256,)).fetchone()
