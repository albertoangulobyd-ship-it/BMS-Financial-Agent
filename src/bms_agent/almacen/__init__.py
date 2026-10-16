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

Paso 13: la base de datos de prueba (`bms-agent demo crear`) se llama
siempre demo.sqlite3 y lleva una marca en la cabecera del fichero
(PRAGMA application_id). `abrir()` exige que las dos cosas vayan juntas: una
base con la marca que no se llama asi (alguien copio demo.sqlite3 encima de
la de verdad) o una que se llama asi sin la marca no se abren. Sus
originales y sus anclas van aparte (demo-documentos/, demo-anclas.log), asi
que nada de la prueba cae en la carpeta de la base de verdad.
"""

from __future__ import annotations

import itertools
import os
import re
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

# La base de prueba (paso 13, demo.py): su nombre y la marca de su cabecera
# ("BMSD"). La marca vive en el fichero: viaja con el aunque se copie.
NOMBRE_DEMO = "demo.sqlite3"
MARCA_DEMO = 0x424D5344

_puntos = itertools.count(1)


class Conexion(sqlite3.Connection):
    """Una conexion de sqlite3 con el reloj de quien la abrio."""

    reloj: Reloj = RELOJ_SISTEMA


def ruta_por_defecto() -> Path:
    """datos/bms.sqlite3, o lo que diga la variable BMS_DB."""
    return Path(os.environ.get(VARIABLE_RUTA) or RUTA_POR_DEFECTO)


class BaseDePruebaMezclada(RuntimeError):
    """Una base de prueba con otro nombre, o una con el nombre de la de prueba sin serlo."""


def marca_de_fichero(ruta: str | Path) -> int | None:
    """El application_id de la cabecera de un fichero SQLite, sin abrirlo con sqlite3; None
    si no existe o no es una base SQLite.

    Leerlo de los bytes 68 a 71 de la cabecera (el formato de fichero de SQLite)
    permite saber si una base es la de prueba antes de abrirla y sin crearla.
    """
    try:
        with open(ruta, "rb") as fichero:
            cabecera = fichero.read(100)
    except OSError:
        return None
    if len(cabecera) < 100 or not cabecera.startswith(b"SQLite format 3\x00"):
        return None
    return int.from_bytes(cabecera[68:72], "big")


def es_base_demo(conn: sqlite3.Connection) -> bool:
    """Si la conexion es a la base de datos de prueba."""
    return int(conn.execute("PRAGMA application_id").fetchone()[0]) == MARCA_DEMO


def _comprobar_nombre_y_marca(destino: Path) -> None:
    """Una base de prueba se llama demo.sqlite3, y solo ella se llama asi."""
    marca = marca_de_fichero(destino)
    es_demo = marca == MARCA_DEMO
    if destino.name == NOMBRE_DEMO and not es_demo:
        if destino.exists():
            raise BaseDePruebaMezclada(
                f"{destino} se llama como la base de prueba pero no lo es: no se abre")
        raise BaseDePruebaMezclada(
            f"{destino} es la base de prueba y no existe: se crea con bms-agent demo crear")
    if es_demo and destino.name != NOMBRE_DEMO:
        raise BaseDePruebaMezclada(
            f"{destino} lleva la marca de DATOS DE PRUEBA y no se llama {NOMBRE_DEMO}: "
            "parece una copia de la base de prueba encima de otra. No se abre; la base de "
            "prueba se crea con bms-agent demo crear")


# Lo que lleva todo fichero que fabrica `demo crear`: la palabra en los CSV (una
# columna mas), en los PDF y en el XML del banco, y el codigo de banco DEMO en
# sus IBAN (que pasan el modulo 97). Una base que no es la de prueba no admite
# nada que lo lleve: asi nada de la prueba entra en la de verdad por ninguna
# orden (importar, extract, importar-out, politica cargar).
MARCA_TEXTO = "BMS-DEMO"
_MARCAS_BYTES = tuple(MARCA_TEXTO.encode(c) for c in ("ascii", "utf-16-le", "utf-16-be"))
_IBAN_DEMO = re.compile(r"\b[A-Z]{2}\d{2} ?DEMO ?\d{4} ?\d{4} ?\d{2}\b")


class DatosDePrueba(ValueError):
    """Algo hecho por `demo crear` iba a entrar en una base que no es la de prueba."""


def contiene_datos_de_prueba(contenido: bytes | str | None) -> bool:
    """Si un fichero o un texto lleva la marca de los datos de prueba."""
    if not contenido:
        return False
    if isinstance(contenido, str):
        return MARCA_TEXTO in contenido or _IBAN_DEMO.search(contenido) is not None
    if any(marca in contenido for marca in _MARCAS_BYTES):
        return True
    for codificacion in ("utf-8", "utf-16"):
        try:
            texto = contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
        if _IBAN_DEMO.search(texto) is not None:
            return True
    return False


def exigir_sin_datos_de_prueba(conn: sqlite3.Connection, contenido: bytes | str | None,
                               que: str) -> None:
    """DatosDePrueba si lo que va a entrar es de prueba y la base no lo es."""
    if contiene_datos_de_prueba(contenido) and not es_base_demo(conn):
        raise DatosDePrueba(
            f"{que} es de los DATOS DE PRUEBA (lleva su marca o un IBAN del banco ficticio) y "
            "esta base no es la de prueba: no entra. Los datos de prueba solo viven en "
            f"{NOMBRE_DEMO}.")


class DatosDeVerdadEnLaPrueba(DatosDePrueba):
    """Lo contrario: algo sin la marca de la prueba (un fichero de verdad) iba a entrar en la
    base de prueba. Es un DatosDePrueba mas para quien lo captura."""


def exigir_de_su_base(conn: sqlite3.Connection, contenido: bytes | str | None, que: str) -> None:
    """Lo de la prueba solo en la base de prueba, y en la base de prueba solo lo de la prueba.

    La segunda mitad es por el buzon, que comparten las dos bases en el
    entorno de Docker: un extracto o un maestro de verdad importado con -Demo
    acabaria bajo la banda "todo es ficticio", fuera de la base de verdad, y
    se borraria al rehacer la prueba. Todo lo que fabrica `demo crear` lleva
    la marca, asi que a la base de prueba no le falta nada.
    """
    exigir_sin_datos_de_prueba(conn, contenido, que)
    if es_base_demo(conn) and not contiene_datos_de_prueba(contenido):
        raise DatosDeVerdadEnLaPrueba(
            f"{que} no es de los DATOS DE PRUEBA (no lleva su marca) y esta es la base de "
            "prueba: no entra. Lo de verdad va a la base de verdad (sin -Demo).")


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
        _comprobar_nombre_y_marca(Path(destino))
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


# La tabla de una entidad que no se llama como ella: un hallazgo o una
# excepcion de un movimiento del banco dicen "movimiento" (la lista de la
# migracion 0003), y la tabla es movimiento_bancario (paso 7).
TABLA_DE_ENTIDAD = {"movimiento": "movimiento_bancario"}


class EntidadNoDisponible(ValueError):
    """La entidad es de una tabla que llega en un paso posterior: todavia no se le apunta nada."""


def comprobar_entidad(conn: sqlite3.Connection, entidad: str, fila_id: int) -> None:
    """Que exista aquello a lo que apunta una orden (una excepcion, una subida de prioridad).

    Sin esto, una subida o una excepcion a mano sobre un id que no existe
    quedaba en la auditoria apuntando a nada. Un trimestre no tiene tabla:
    es ano * 10 + trimestre (20263 es el T3 de 2026). Una tabla que todavia
    no existe (orden_compra, movimiento) no admite nada hasta que llegue.
    """
    if entidad == "trimestre":
        ano, trimestre = divmod(int(fila_id), 10)
        if not (1 <= trimestre <= 4 and 1900 <= ano <= 9999):
            raise LookupError(f"{fila_id} no es un trimestre: se escribe año * 10 + trimestre "
                              "(20263 es el T3 de 2026)")
        return
    tabla = TABLA_DE_ENTIDAD.get(entidad, entidad)
    existe = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                          (tabla,)).fetchone()
    if existe is None:
        raise EntidadNoDisponible(f"{entidad} todavia no esta en el almacen (llega en un paso "
                                  "posterior): no se le apunta nada")
    if conn.execute(f"SELECT 1 FROM {tabla} WHERE id = ?", (fila_id,)).fetchone() is None:
        raise LookupError(f"no hay {entidad} {fila_id}")


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
    """Los originales viven al lado de la base: datos/documentos/ (los de la base de prueba,
    en datos/demo-documentos/: nunca en la carpeta de la de verdad)."""
    ruta = Path(ruta_db)
    return ruta.parent / ("demo-documentos" if ruta.name == NOMBRE_DEMO else "documentos")


def ruta_anclas_de(ruta_db: str | Path) -> Path:
    """Las anclas de la auditoria, tambien al lado de la base: datos/anclas.log.

    Van con la base y no con la carpeta out/ de cada orden: una misma base
    se alimenta desde varias carpetas (--out), y `db verificar` tiene que
    encontrar el fichero que escribieron extract, serve e importar-out. Las de
    la base de prueba van en demo-anclas.log.
    """
    ruta = Path(ruta_db)
    return ruta.parent / ("demo-anclas.log" if ruta.name == NOMBRE_DEMO else "anclas.log")


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
    anclas = None if str(destino) == MEMORIA else ruta_anclas_de(destino)
    try:
        hechas = migrar(conn)
        if anclas is not None and any(m.version == 1 for m in hechas):
            # La base se acaba de crear: se dice en su fichero de anclas (auditoria).
            from ..auditoria import declarar_base

            declarar_base(conn, anclas)
    except BaseException:
        conn.close()
        raise
    raiz = Path(raiz_documentos) if raiz_documentos is not None else raiz_documentos_de(destino)
    return Almacen(conn=conn, documentos=AlmacenDocumentos(raiz), ruta_anclas=anclas)
