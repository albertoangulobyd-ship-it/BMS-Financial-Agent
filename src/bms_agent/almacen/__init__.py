"""El almacen: una base SQLite y una carpeta de documentos que no se reescriben.

Hasta el paso 1, la evidencia eran ficheros sueltos en out/ que cualquiera
podia editar sin dejar rastro. Ahora cada documento, cada extraccion y cada
importacion queda en una tabla que la propia base protege: las tablas de
evidencia y de auditoria abortan UPDATE y DELETE con disparadores, y cada
evento lleva el hash del anterior.

`abrir()` fija los ajustes que no se negocian (claves foraneas, WAL, espera
si otro proceso escribe) y se niega a correr en un SQLite sin tablas STRICT.
`transaccion()` envuelve una orden entera en BEGIN IMMEDIATE: el cambio, su
evento de auditoria y lo que se recalcule entran o fallan juntos.

La conexion lleva su reloj (`conn.reloj`), y de ahi sacan la hora todos los
que escriben: un test la fija una vez y vale para todo.
"""

from __future__ import annotations

import itertools
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..reloj import RELOJ_SISTEMA, Reloj

if TYPE_CHECKING:
    from .documentos import AlmacenDocumentos

RUTA_POR_DEFECTO = Path("datos") / "bms.sqlite3"
VARIABLE_RUTA = "BMS_DB"
# STRICT llega en 3.37. Sin el, '12.50' entraria en una columna INTEGER.
VERSION_MINIMA = (3, 37, 0)
MEMORIA = ":memory:"

USUARIOS_SISTEMA = ("sistema", "extractor", "importador", "motor")

_puntos = itertools.count(1)


class Conexion(sqlite3.Connection):
    """Una conexion de sqlite3 con el reloj de quien la abrio."""

    reloj: Reloj = RELOJ_SISTEMA


def ruta_por_defecto() -> Path:
    """datos/bms.sqlite3, o lo que diga la variable BMS_DB."""
    return Path(os.environ.get(VARIABLE_RUTA) or RUTA_POR_DEFECTO)


def comprobar_version(version: tuple[int, ...] = sqlite3.sqlite_version_info) -> None:
    if tuple(version) < VERSION_MINIMA:
        minima = ".".join(map(str, VERSION_MINIMA))
        actual = ".".join(map(str, version))
        raise RuntimeError(
            f"SQLite {actual} es demasiado antiguo: hace falta {minima} o mas "
            "(tablas STRICT). Actualiza Python o el SQLite del sistema."
        )


def abrir(ruta: str | Path | None = None, *, reloj: Reloj | None = None) -> Conexion:
    """Abre (o crea) la base con los ajustes del almacen.

    La conexion va en modo autocommit de sqlite3 (isolation_level=None): las
    transacciones las abre `transaccion()` de forma explicita, y no el modulo
    sqlite3 por su cuenta antes de cada INSERT.
    """
    comprobar_version()
    destino = str(ruta if ruta is not None else ruta_por_defecto())
    if destino != MEMORIA:
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(destino, isolation_level=None, factory=Conexion, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.reloj = reloj or RELOJ_SISTEMA
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if destino != MEMORIA:
        conn.execute("PRAGMA journal_mode = WAL")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        conn.close()
        raise RuntimeError("este SQLite no aplica claves foraneas; no se puede usar")
    return conn


@contextmanager
def transaccion(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Una orden entera, todo o nada.

    BEGIN IMMEDIATE toma el cerrojo de escritura al empezar, no al primer
    INSERT: dos procesos no pueden leer el mismo ultimo evento y encadenar
    los dos detras de el. Dentro de otra transaccion abre un SAVEPOINT, asi
    que una funcion que escribe se puede llamar sola o como parte de una
    orden mayor, y si falla deshace solo lo suyo.
    """
    if conn.in_transaction:
        punto = f"punto_{next(_puntos)}"
        conn.execute(f"SAVEPOINT {punto}")
        try:
            yield conn
        except BaseException:
            conn.execute(f"ROLLBACK TO {punto}")
            conn.execute(f"RELEASE {punto}")
            raise
        conn.execute(f"RELEASE {punto}")
        return

    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def reloj_de(conn: sqlite3.Connection) -> Reloj:
    """El reloj de la conexion; el del sistema si no se abrio con abrir()."""
    return getattr(conn, "reloj", RELOJ_SISTEMA)


def usuario_sistema(conn: sqlite3.Connection, nombre: str) -> int:
    """El id de uno de los usuarios de sistema que siembra la migracion 0001."""
    if nombre not in USUARIOS_SISTEMA:
        raise ValueError(f"{nombre!r} no es un usuario de sistema")
    fila = conn.execute(
        "SELECT id FROM usuario WHERE nombre = ? AND es_sistema = 1", (nombre,)
    ).fetchone()
    if fila is None:
        raise LookupError(f"falta el usuario de sistema {nombre!r}: la base no esta migrada")
    return int(fila[0])


@dataclass
class Almacen:
    """La base y la carpeta de documentos, que siempre van juntas.

    `ruta_anclas` es donde se anclan los eventos de esta base (ver
    auditoria.anclar); None en una base en memoria, que no se ancla.
    """

    conn: Conexion
    documentos: AlmacenDocumentos
    ruta_anclas: Path | None = None

    def cerrar(self) -> None:
        self.conn.close()

    def __enter__(self) -> Almacen:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.cerrar()


def raiz_documentos_de(ruta_db: str | Path) -> Path:
    """Los originales viven al lado de la base: datos/documentos/."""
    return Path(ruta_db).parent / "documentos"


def ruta_anclas_de(ruta_db: str | Path) -> Path:
    """Las anclas de la auditoria, tambien al lado de la base: datos/anclas.log.

    Van con la base y no con la carpeta out/ de cada orden: una misma base
    se alimenta desde varias carpetas (--out), y `db verificar` tiene que
    encontrar el fichero que escribieron extract, serve e importar-out.
    """
    return Path(ruta_db).parent / "anclas.log"


def preparar(
    ruta: str | Path | None = None,
    *,
    reloj: Reloj | None = None,
    raiz_documentos: str | Path | None = None,
) -> Almacen:
    """Abre la base, aplica las migraciones pendientes y devuelve el almacen.

    Las migraciones se aplican solas porque cada una esta fijada por su hash
    y nunca se edita: aplicarlas es determinista. Una migracion aplicada que
    ha cambiado detiene todo (MigracionAlterada).
    """
    from .documentos import AlmacenDocumentos
    from .migrar import migrar

    destino = Path(ruta) if ruta is not None else ruta_por_defecto()
    if str(destino) == MEMORIA and raiz_documentos is None:
        raise ValueError("una base en memoria necesita una carpeta de documentos explicita")
    conn = abrir(destino, reloj=reloj)
    try:
        migrar(conn)
    except BaseException:
        conn.close()
        raise
    raiz = Path(raiz_documentos) if raiz_documentos is not None else raiz_documentos_de(destino)
    anclas = None if str(destino) == MEMORIA else ruta_anclas_de(destino)
    return Almacen(conn=conn, documentos=AlmacenDocumentos(raiz), ruta_anclas=anclas)
