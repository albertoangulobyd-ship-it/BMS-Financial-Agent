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
restauracion escribe un evento `restauracion` en la base restaurada con las
anclas que deja sin cumplir, y solo esas dejan de ser un problema. El
fichero de anclas no se reescribe nunca, ni al restaurar.

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
    conn: sqlite3.Connection, anclas: Iterable[Ancla] = ()
) -> ResultadoCadena:
    """Recorre la cadena entera y dice donde no cuadra.

    No para en el primer fallo: cada evento se compara con su propio hash y
    con el anterior, asi el informe senala la fila tocada y no solo "a
    partir de aqui". No se fia de los disparadores: puede que ya no existan.

    Un ancla que la cadena ya no cumple solo se perdona si la nombra un
    evento de restauracion de la propia cadena (que tambien pasa por su
    hash): restaurar es el unico corte que se admite, y queda dicho.
    """
    resultado = ResultadoCadena()
    propia = identidad(conn)
    cambios = _cambios_por_evento(conn)
    hashes: dict[int, str] = {}
    descartadas: set[tuple[int, str]] = set()
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
            descartadas.update(_anclas_descartadas(fila["datos_json"]))
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
    return resultado


def _anclas_descartadas(datos_json: str | None) -> set[tuple[int, str]]:
    import json

    try:
        datos = json.loads(datos_json or "{}")
        return {(int(i), str(h)) for i, h in datos.get("anclas_descartadas") or []}
    except (ValueError, TypeError):
        return set()


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


def leer_anclas(ruta: str | Path) -> tuple[list[Ancla], list[str]]:
    """Las anclas de un fichero, y las lineas que no se entienden (tambien son un aviso)."""
    ruta = Path(ruta)
    if not ruta.exists():
        return [], []
    anclas, malas = [], []
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        partes = [parte.strip() for parte in linea.split("\t")]
        try:
            if len(partes) == 3:                       # linea anterior a la identidad
                _cuando, evento_id, hash_ = partes
                almacen = None
            else:
                _cuando, evento_id, hash_, almacen = partes
            anclas.append(Ancla(int(evento_id), hash_, almacen or None))
        except ValueError:
            malas.append(f"linea {numero} de {ruta.name} no es un ancla: {linea[:60]!r}")
    return anclas, malas


def anclar(conn: sqlite3.Connection, ruta: str | Path) -> Ancla | None:
    """Apunta la cabeza de la cadena al final del fichero, si ha cambiado.

    El fichero solo crece. Si la ultima ancla de esta base ya es la cabeza,
    no se repite. Cada linea dice de que base es (`identidad()`).
    """
    actual = cabeza(conn)
    if actual is None:
        return None
    ruta = Path(ruta)
    anclas, _malas = leer_anclas(ruta)
    propias = [a for a in anclas if a.almacen in (None, actual.almacen)]
    if propias and propias[-1] == actual:
        return actual
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8", newline="") as fichero:
        fichero.write(
            f"{marca(reloj_de(conn).ahora())}\t{actual.id}\t{actual.hash}\t{actual.almacen}\n"
        )
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
