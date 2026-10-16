"""Registro de auditoria: eventos encadenados por hash.

Cada evento guarda el hash del anterior y el suyo, calculado sobre el JSON
canonico de la fila entera y de los cambio_campo que cuelgan de el. Los
disparadores de la base abortan UPDATE y DELETE, pero los disparadores se
pueden borrar con una conexion directa al fichero. La cadena es lo que queda
entonces: editar una fila cambia su hash, que ya no coincide con el guardado
ni con el hash_anterior del siguiente. `verificar_cadena()` lo encuentra.

Lo que la cadena sola no detecta es que alguien reescriba el final entero
(o lo corte) y recalcule los hashes. Para eso estan las anclas: `anclar()`
apunta el ultimo id y su hash fuera de la base (anclas.log, al lado de la
base; despues, tambien en el informe diario), y la verificacion comprueba
que la cadena sigue conteniendo cada evento anclado tal cual.

El unico corte legitimo es restaurar una copia (copia.restaurar): la base
vuelve a lo que era y lo de despues se va. Ese corte no se esconde: la
restauracion apunta en el fichero de anclas cada ancla que deja sin cumplir
(una linea `restauracion`, con la carpeta y el hash de lo sustituido), y
escribe ademas un evento `restauracion` en la base restaurada. Solo perdona
lo que dice el fichero, nunca lo que diga la base: quien puede escribir la
base puede escribir en ella un evento de restauracion falso. El fichero de
anclas no se reescribe nunca, ni al restaurar.

Por lo mismo, que base es esta lo dice el fichero: al crear una base
(almacen.preparar, `db init`) se apunta una linea `nueva_base` con su
identidad y el nombre de su fichero. Unas anclas de otra identidad en el
fichero de una base que no consta como creada alli son una cadena reescrita
desde su primer evento, no "otra base que comparte el fichero", y anclar()
no apunta encima de ellas.

Un evento solo se escribe dentro de una transaccion: se confirma o se
deshace con el cambio que describe, nunca por separado.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .almacen import reloj_de, transaccion
from .almacen.unidades import json_canonico, sha256_texto
from .reloj import marca

HASH_INICIAL = "0" * 64
RESULTADOS = ("ok", "denegado", "error")
# El evento que deja una restauracion (copia.restaurar): lleva las anclas que corta.
TIPO_RESTAURACION = "restauracion"
# Lo que el fichero de anclas dice ademas de las anclas: que base se creo en este sitio, y
# que ancla corto una restauracion (y donde quedo lo sustituido).
LINEA_BASE = "nueva_base"
LINEA_CORTE = "restauracion"
SIN_VALOR = "-"

_COLUMNAS_EVENTO = (
    "id", "en", "usuario_id", "actor", "tipo", "resultado", "tabla", "fila_id",
    "factura_id", "motivo", "datos_json", "peticion_id", "hash_anterior",
)
_COLUMNAS_CAMBIO = (
    "tabla", "fila_id", "factura_id", "campo", "rev", "valor_anterior", "valor_nuevo",
    "fuente_anterior", "fuente_nueva", "motivo",
)


@dataclass(frozen=True)
class Cambio:
    """Un campo que cambia dentro de una orden. Los valores van en JSON canonico."""

    tabla: str
    fila_id: int
    campo: str
    rev: int
    valor_anterior: Any
    valor_nuevo: Any
    fuente_nueva: str
    fuente_anterior: str | None = None
    motivo: str | None = None
    factura_id: int | None = None

    def fila(self) -> dict[str, Any]:
        return {
            "tabla": self.tabla, "fila_id": self.fila_id, "factura_id": self.factura_id,
            "campo": self.campo, "rev": self.rev,
            "valor_anterior": json_canonico(self.valor_anterior),
            "valor_nuevo": json_canonico(self.valor_nuevo),
            "fuente_anterior": self.fuente_anterior, "fuente_nueva": self.fuente_nueva,
            "motivo": self.motivo,
        }


def calcular_hash(evento: Mapping[str, Any], cambios: Sequence[Mapping[str, Any]]) -> str:
    """El hash de un evento: sus columnas (menos el propio hash) y sus cambios, en orden."""
    contenido = {columna: evento[columna] for columna in _COLUMNAS_EVENTO}
    contenido["cambios"] = [{c: cambio[c] for c in _COLUMNAS_CAMBIO} for cambio in cambios]
    return sha256_texto(json_canonico(contenido))


def registrar(
    conn: sqlite3.Connection,
    *,
    tipo: str,
    actor: int,
    usuario_id: int | None = None,
    resultado: str = "ok",
    tabla: str | None = None,
    fila_id: int | None = None,
    factura_id: int | None = None,
    motivo: str | None = None,
    datos: Mapping[str, Any] | None = None,
    peticion_id: str | None = None,
    cambios: Iterable[Cambio] = (),
) -> int:
    """Escribe un evento al final de la cadena, con sus cambios. Devuelve su id.

    El id se fija aqui (el ultimo mas uno) porque entra en el hash. Es seguro
    porque la transaccion es BEGIN IMMEDIATE: nadie mas escribe hasta el
    COMMIT. Si aun asi otro evento se colara, el disparador
    evento_encadenado lo rechaza.

    El evento y sus cambio_campo van en su propio SAVEPOINT: el hash del
    evento ya cubre sus cambios, asi que si uno no entra (una correccion sin
    motivo) tampoco puede quedar el evento, aunque quien llama capture el
    error y confirme el resto de la orden.
    """
    if not conn.in_transaction:
        raise RuntimeError(
            "un evento se escribe dentro de la transaccion de la orden que describe"
        )
    if resultado not in RESULTADOS:
        raise ValueError(f"resultado desconocido: {resultado!r}")

    ultimo = conn.execute("SELECT id, hash FROM evento ORDER BY id DESC LIMIT 1").fetchone()
    filas_cambio = [c.fila() for c in cambios]
    evento = {
        "id": (ultimo["id"] if ultimo else 0) + 1,
        "en": marca(reloj_de(conn).ahora()),
        "usuario_id": usuario_id,
        "actor": actor,
        "tipo": tipo,
        "resultado": resultado,
        "tabla": tabla,
        "fila_id": fila_id,
        "factura_id": factura_id,
        "motivo": motivo,
        "datos_json": json_canonico(dict(datos)) if datos is not None else None,
        "peticion_id": peticion_id,
        "hash_anterior": ultimo["hash"] if ultimo else HASH_INICIAL,
    }
    evento["hash"] = calcular_hash(evento, filas_cambio)

    columnas = (*_COLUMNAS_EVENTO, "hash")
    with transaccion(conn):
        conn.execute(
            f"INSERT INTO evento ({', '.join(columnas)}) "
            f"VALUES ({', '.join('?' * len(columnas))})",
            tuple(evento[c] for c in columnas),
        )
        for fila in filas_cambio:
            conn.execute(
                f"INSERT INTO cambio_campo (evento_id, {', '.join(_COLUMNAS_CAMBIO)}) "
                f"VALUES (?, {', '.join('?' * len(_COLUMNAS_CAMBIO))})",
                (evento["id"], *(fila[c] for c in _COLUMNAS_CAMBIO)),
            )
    return evento["id"]


@dataclass(frozen=True)
class Ancla:
    """Un evento de la cadena apuntado fuera de la base.

    `almacen` es la identidad de la base que lo escribio (ver
    `identidad()`); None en una linea antigua, que se comprueba siempre.
    """

    id: int
    hash: str
    almacen: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Corte:
    """Un ancla que una restauracion dejo sin cumplir, apuntada en el fichero de anclas.

    `antes` es la carpeta con lo que la restauracion sustituyo (relativa a la
    de la base) y `antes_sha256` el hash de la base guardada alli: None si no
    habia nada que guardar (una instalacion nueva).
    """

    id: int
    hash: str
    almacen: str | None
    antes: str | None
    antes_sha256: str | None


@dataclass
class FicheroAnclas:
    """Lo que dice un fichero de anclas: las anclas, las lineas que no se entienden, las bases
    que se crearon en su sitio (identidad -> nombres de fichero) y los cortes apuntados."""

    anclas: list[Ancla] = field(default_factory=list)
    malas: list[str] = field(default_factory=list)
    bases: dict[str, set[str]] = field(default_factory=dict)
    cortes: list[Corte] = field(default_factory=list)

    def declarada(self, almacen: str | None, nombre: str | None) -> bool:
        """Si la base de esa identidad consta como creada con ese nombre de fichero."""
        return almacen is not None and nombre in self.bases.get(almacen, set())


class AnclasDeOtraBase(Exception):
    """El fichero de anclas es de otra base y esta no consta como creada alli: no se ancla."""


@dataclass
class ResultadoCadena:
    eventos: int = 0
    cabeza: Ancla | None = None
    anclas: int = 0
    # Anclas de otra base que comparte el fichero: no se comprueban.
    anclas_ajenas: int = 0
    # Anclas de lo que una restauracion sustituyo: las nombra su evento.
    anclas_descartadas: int = 0
    restauraciones: list[int] = field(default_factory=list)
    ultima_ancla: int | None = None
    problemas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problemas


def _cambios_por_evento(conn: sqlite3.Connection) -> dict[int, list[sqlite3.Row]]:
    por_evento: dict[int, list[sqlite3.Row]] = {}
    for fila in conn.execute("SELECT * FROM cambio_campo ORDER BY evento_id, id"):
        por_evento.setdefault(fila["evento_id"], []).append(fila)
    return por_evento


def verificar_cadena(
    conn: sqlite3.Connection, anclas: Iterable[Ancla] = (), *,
    fichero: FicheroAnclas | None = None,
    perdonadas: Iterable[tuple[int, str]] = (),
) -> ResultadoCadena:
    """Recorre la cadena entera y dice donde no cuadra.

    No para en el primer fallo: cada evento se compara con su propio hash y
    con el anterior, asi el informe senala la fila tocada y no solo "a
    partir de aqui". No se fia de los disparadores: puede que ya no existan.

    Un ancla que la cadena ya no cumple solo se perdona si esta en
    `perdonadas`: las que un corte del fichero de anclas nombra (quien llama
    comprueba que lo sustituido sigue donde el corte dice). Un evento de
    restauracion de la base no perdona nada: lo puede escribir quien escribe
    la base. Con `fichero`, unas anclas de otra identidad son un problema si
    ninguna es de esta base y esta no consta en el como creada con su nombre:
    si no, bastaria reescribir el primer evento para que ninguna ancla se
    comprobara. Es la misma condicion con la que `anclar` no apunta: una base
    con anclas suyas (tambien una de antes de que existiera `nueva_base`) ya
    se comprueba con ellas, y quien reescribe la cadena no consigue la primera.
    """
    resultado = ResultadoCadena()
    propia = identidad(conn)
    cambios = _cambios_por_evento(conn)
    hashes: dict[int, str] = {}
    descartadas = set(perdonadas)
    esperado_id, anterior = 1, HASH_INICIAL

    for fila in conn.execute("SELECT * FROM evento ORDER BY id"):
        resultado.eventos += 1
        evento_id = fila["id"]
        if evento_id != esperado_id:
            faltan = (f"el evento {esperado_id}" if evento_id == esperado_id + 1
                      else f"los eventos {esperado_id} a {evento_id - 1}")
            resultado.problemas.append(f"falta {faltan}: se ha borrado algo de la cadena")
        if fila["hash_anterior"] != anterior:
            resultado.problemas.append(
                f"el evento {evento_id} no cuelga del anterior (hash_anterior no coincide)"
            )
        if calcular_hash(fila, cambios.pop(evento_id, [])) != fila["hash"]:
            resultado.problemas.append(
                f"el evento {evento_id} o sus cambio_campo se han modificado (el hash no coincide)"
            )
        hashes[evento_id] = fila["hash"]
        if fila["tipo"] == TIPO_RESTAURACION:
            resultado.restauraciones.append(evento_id)
        esperado_id, anterior = evento_id + 1, fila["hash"]
        resultado.cabeza = Ancla(evento_id, fila["hash"])

    for evento_id in sorted(cambios):
        resultado.problemas.append(f"hay cambio_campo del evento {evento_id}, que no existe")

    for ancla in anclas:
        if ancla.almacen is not None and ancla.almacen != propia:
            resultado.anclas_ajenas += 1
            continue
        guardado = hashes.get(ancla.id)
        if guardado != ancla.hash and (ancla.id, ancla.hash) in descartadas:
            resultado.anclas_descartadas += 1
            continue
        resultado.anclas += 1
        resultado.ultima_ancla = max(resultado.ultima_ancla or 0, ancla.id)
        if guardado is None:
            resultado.problemas.append(
                f"la cadena ya no llega al evento anclado {ancla.id}: se ha cortado"
            )
        elif guardado != ancla.hash:
            resultado.problemas.append(
                f"el evento anclado {ancla.id} ya no es el que se anclo: se ha reescrito"
            )
    if (fichero is not None and resultado.anclas_ajenas and not resultado.anclas
            and not resultado.anclas_descartadas
            and not fichero.declarada(propia, nombre_de_base(conn))):
        resultado.problemas.append(
            f"{resultado.anclas_ajenas} anclas del fichero son de otra base, y esta no consta en "
            "el como creada aqui: la cadena se ha reescrito desde su primer evento (o la base es "
            "de otro sitio y su fichero de anclas no esta)")
    return resultado


def anclas_sin_cumplir(conn: sqlite3.Connection, anclas: Iterable[Ancla]) -> list[Ancla]:
    """Las anclas de esta base que su cadena ya no cumple (el evento no esta, u otro hash), en
    el orden del fichero y sin repetir. Es lo que corta una restauracion."""
    propia = identidad(conn)
    hashes = {f["id"]: f["hash"] for f in conn.execute("SELECT id, hash FROM evento")}
    salida: list[Ancla] = []
    for ancla in anclas:
        if ancla.almacen is not None and ancla.almacen != propia:
            continue
        if hashes.get(ancla.id) != ancla.hash and ancla not in salida:
            salida.append(ancla)
    return salida


def cabeza(conn: sqlite3.Connection) -> Ancla | None:
    fila = conn.execute("SELECT id, hash FROM evento ORDER BY id DESC LIMIT 1").fetchone()
    return Ancla(fila["id"], fila["hash"], identidad(conn)) if fila else None


def identidad(conn: sqlite3.Connection) -> str | None:
    """Que base es esta: el hash de su primer evento.

    El primer evento es la migracion 0001, que lleva un identificador al
    azar (migrar.py): dos bases creadas en el mismo segundo no se confunden.
    Asi un fichero de anclas compartido por dos bases (otra --db, o una base
    vuelta a crear) no da por reescrita una base que nadie ha tocado.
    """
    fila = conn.execute("SELECT hash FROM evento WHERE id = 1").fetchone()
    return fila["hash"] if fila else None


def _o_nada(valor: str) -> str | None:
    return None if valor in ("", SIN_VALOR) else valor


def leer_fichero(ruta: str | Path) -> FicheroAnclas:
    """Todo lo que dice un fichero de anclas (ver FicheroAnclas)."""
    ruta = Path(ruta)
    salida = FicheroAnclas()
    if not ruta.exists():
        return salida
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        partes = [parte.strip() for parte in linea.split("\t")]
        try:
            if len(partes) == 4 and partes[1] == LINEA_BASE:
                _cuando, _tipo, almacen, nombre = partes
                salida.bases.setdefault(almacen, set()).add(nombre)
            elif len(partes) == 7 and partes[1] == LINEA_CORTE:
                _cuando, _tipo, evento_id, hash_, almacen, antes, sha = partes
                salida.cortes.append(Corte(int(evento_id), hash_, _o_nada(almacen),
                                           _o_nada(antes), _o_nada(sha)))
            elif len(partes) == 3:                       # linea anterior a la identidad
                _cuando, evento_id, hash_ = partes
                salida.anclas.append(Ancla(int(evento_id), hash_, None))
            else:
                _cuando, evento_id, hash_, almacen = partes
                salida.anclas.append(Ancla(int(evento_id), hash_, almacen or None))
        except ValueError:
            salida.malas.append(f"linea {numero} de {ruta.name} no es un ancla: {linea[:60]!r}")
    return salida


def leer_anclas(ruta: str | Path) -> tuple[list[Ancla], list[str]]:
    """Las anclas de un fichero, y las lineas que no se entienden (tambien son un aviso)."""
    fichero = leer_fichero(ruta)
    return fichero.anclas, fichero.malas


def nombre_de_base(conn: sqlite3.Connection) -> str | None:
    """El nombre del fichero de la base (bms.sqlite3), o None si esta en memoria."""
    fila = conn.execute("PRAGMA database_list").fetchone()
    return Path(fila[2]).name if fila and fila[2] else None


def _apuntar(ruta: Path, lineas: Iterable[str]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8", newline="") as fichero:
        fichero.write("".join(f"{linea}\n" for linea in lineas))


def declarar_base(conn: sqlite3.Connection, ruta: str | Path) -> bool:
    """Apunta en el fichero de anclas que esta base se creo aqui (su identidad y su nombre).

    Lo llama quien crea la base (almacen.preparar, `db init`) justo despues de
    la primera migracion. No se repite. Devuelve si se apunto.
    """
    almacen, nombre = identidad(conn), nombre_de_base(conn)
    if almacen is None or nombre is None:
        return False
    ruta = Path(ruta)
    if leer_fichero(ruta).declarada(almacen, nombre):
        return False
    _apuntar(ruta, [f"{marca(reloj_de(conn).ahora())}\t{LINEA_BASE}\t{almacen}\t{nombre}"])
    return True


def apuntar_cortes(conn: sqlite3.Connection, ruta: str | Path, cortadas: Iterable[Ancla], *,
                   antes: str | None, antes_sha256: str | None) -> None:
    """Apunta en el fichero de anclas las que una restauracion deja sin cumplir, con donde
    quedo lo sustituido (copia.restaurar). Es lo unico que las perdona."""
    cuando = marca(reloj_de(conn).ahora())
    _apuntar(Path(ruta), [
        f"{cuando}\t{LINEA_CORTE}\t{a.id}\t{a.hash}\t{a.almacen or SIN_VALOR}\t"
        f"{antes or SIN_VALOR}\t{antes_sha256 or SIN_VALOR}" for a in cortadas])


def anclar(conn: sqlite3.Connection, ruta: str | Path) -> Ancla | None:
    """Apunta la cabeza de la cadena al final del fichero, si ha cambiado.

    El fichero solo crece. Si la ultima ancla de esta base ya es la cabeza,
    no se repite. Cada linea dice de que base es (`identidad()`).

    No apunta (AnclasDeOtraBase) si el fichero ya tiene anclas de otra base,
    ninguna de esta y esta no consta como creada alli: es lo que deja quien
    reescribe la cadena entera, primer evento incluido, y anclarla daria por
    buena la cadena falsa en la siguiente orden.
    """
    actual = cabeza(conn)
    if actual is None:
        return None
    ruta = Path(ruta)
    fichero = leer_fichero(ruta)
    propias = [a for a in fichero.anclas if a.almacen in (None, actual.almacen)]
    if propias and propias[-1] == actual:
        return actual
    ajenas = [a for a in fichero.anclas if a.almacen not in (None, actual.almacen)]
    if ajenas and not propias and not fichero.declarada(actual.almacen, nombre_de_base(conn)):
        raise AnclasDeOtraBase(
            f"{ruta} tiene {len(ajenas)} anclas de otra base y ninguna de esta, que no consta "
            "como creada alli: no se ancla. Puede que alguien haya reescrito la cadena desde el "
            "principio; bms-agent db verificar lo dice")
    _apuntar(ruta, [f"{marca(reloj_de(conn).ahora())}\t{actual.id}\t{actual.hash}\t"
                    f"{actual.almacen}"])
    return actual


def historial(conn: sqlite3.Connection, tabla: str, fila_id: int) -> list[dict[str, Any]]:
    """Lo que ha pasado con una fila: sus eventos, en orden, cada uno con sus cambios."""
    eventos: dict[int, dict[str, Any]] = {}
    for fila in conn.execute(
        "SELECT * FROM evento WHERE tabla = ? AND fila_id = ? "
        "UNION SELECT e.* FROM evento AS e JOIN cambio_campo AS c ON c.evento_id = e.id "
        "WHERE c.tabla = ? AND c.fila_id = ? ORDER BY id",
        (tabla, fila_id, tabla, fila_id),
    ):
        eventos[fila["id"]] = {**dict(fila), "cambios": []}
    if eventos:
        marcas = ", ".join("?" * len(eventos))
        for cambio in conn.execute(
            f"SELECT * FROM cambio_campo WHERE evento_id IN ({marcas}) "
            "AND tabla = ? AND fila_id = ? ORDER BY id",
            (*eventos, tabla, fila_id),
        ):
            eventos[cambio["evento_id"]]["cambios"].append(dict(cambio))
    return list(eventos.values())
