"""Migraciones ordenadas, una por paso de construccion, fijadas por su hash.

Cada fichero sql/NNNN_nombre.sql se aplica una vez, en su propia
transaccion, y se apunta en la tabla migracion con su sha256. Un fichero ya
aplicado no se edita nunca: si su hash cambia, migrar() se niega a seguir.
Sin esa regla, dos bases con la misma version podrian tener esquemas
distintos y nadie lo sabria.

El hash se calcula con los finales de linea normalizados a LF, para que un
checkout en Windows con CRLF no parezca una migracion alterada.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ..reloj import marca
from . import reloj_de, transaccion, usuario_sistema
from .unidades import sha256_bytes

DIRECTORIO_SQL = Path(__file__).resolve().parent / "sql"
_NOMBRE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


class MigracionAlterada(RuntimeError):
    """Una migracion aplicada ya no coincide con su fichero, o falta."""


@dataclass(frozen=True)
class Migracion:
    version: int
    nombre: str
    sha256: str
    sql: str = field(repr=False)


def disponibles(directorio: str | Path | None = None) -> list[Migracion]:
    """Las migraciones del directorio, en orden y sin huecos (0001, 0002...)."""
    directorio = Path(directorio) if directorio is not None else DIRECTORIO_SQL
    migraciones = []
    for ruta in sorted(directorio.glob("*.sql")):
        coincide = _NOMBRE.match(ruta.name)
        if coincide is None:
            raise ValueError(f"{ruta.name}: una migracion se llama NNNN_nombre.sql")
        crudo = ruta.read_bytes().replace(b"\r\n", b"\n")
        migraciones.append(Migracion(
            version=int(coincide.group(1)), nombre=ruta.name,
            sql=crudo.decode("utf-8"), sha256=sha256_bytes(crudo),
        ))
    versiones = [m.version for m in migraciones]
    if versiones != list(range(1, len(versiones) + 1)):
        raise ValueError(f"las migraciones tienen que ir de 1 en 1 desde 0001: {versiones}")
    return migraciones


def aplicadas(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    existe = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'migracion'"
    ).fetchone()
    if existe is None:
        return {}
    return {
        fila["version"]: fila
        for fila in conn.execute("SELECT version, nombre, sha256, aplicada_en FROM migracion")
    }


def comprobar(conn: sqlite3.Connection, directorio: str | Path | None = None) -> list[str]:
    """Lo que no cuadra entre la base y los ficheros. Vacio si todo esta bien."""
    por_version = {m.version: m for m in disponibles(directorio)}
    problemas = []
    for version, fila in sorted(aplicadas(conn).items()):
        fichero = por_version.get(version)
        if fichero is None:
            problemas.append(
                f"la migracion {fila['nombre']} esta aplicada pero su fichero ya no existe"
            )
        elif fichero.sha256 != fila["sha256"]:
            problemas.append(
                f"la migracion {fila['nombre']} se edito despues de aplicarse "
                f"(hash aplicado {fila['sha256'][:12]}, fichero {fichero.sha256[:12]})"
            )
        elif fichero.nombre != fila["nombre"]:
            problemas.append(
                f"la migracion {version} se aplico como {fila['nombre']} y ahora es {fichero.nombre}"
            )
    return problemas


def pendientes(
    conn: sqlite3.Connection, directorio: str | Path | None = None
) -> list[Migracion]:
    hechas = aplicadas(conn)
    return [m for m in disponibles(directorio) if m.version not in hechas]


def migrar(conn: sqlite3.Connection, directorio: str | Path | None = None) -> list[Migracion]:
    """Aplica lo pendiente, cada migracion en su transaccion. Devuelve lo aplicado.

    executescript() hace COMMIT de lo que haya abierto antes de empezar, asi
    que el BEGIN va dentro del propio guion: el DDL, la fila de migracion y
    su evento de auditoria entran o fallan juntos.
    """
    if conn.in_transaction:
        raise RuntimeError("migrar necesita su propia transaccion; hay una abierta")
    problemas = comprobar(conn, directorio)
    if problemas:
        raise MigracionAlterada("; ".join(problemas))

    from ..auditoria import registrar

    hechas = []
    for migracion in pendientes(conn, directorio):
        try:
            conn.executescript("BEGIN IMMEDIATE;\n" + migracion.sql)
            conn.execute(
                "INSERT INTO migracion (version, nombre, sha256, aplicada_en) VALUES (?, ?, ?, ?)",
                (migracion.version, migracion.nombre, migracion.sha256,
                 marca(reloj_de(conn).ahora())),
            )
            with transaccion(conn):
                registrar(
                    conn, tipo="migracion_aplicada", actor=usuario_sistema(conn, "sistema"),
                    tabla="migracion", fila_id=migracion.version,
                    datos={"nombre": migracion.nombre, "sha256": migracion.sha256},
                )
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        hechas.append(migracion)
    return hechas
