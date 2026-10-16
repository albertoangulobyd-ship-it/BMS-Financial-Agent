"""Extracciones en el almacen: el registro tal cual se escribio, nunca reescrito.

Lo que se guarda es el texto exacto del registro (el mismo que el fichero de
out/), no una version reinterpretada: es la evidencia de lo que el modelo
leyo. Las columnas (modelo, versiones, fecha, uso) se sacan de ese texto
para poder buscar por ellas, pero el texto manda.

Un documento puede tener muchas extracciones. Volver a registrar la misma
(mismo documento, modelo, versiones y contenido) no hace nada.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..auditoria import registrar
from ..reloj import marca
from . import exigir_de_su_base, reloj_de, transaccion
from .evidencia import foto
from .unidades import es_sha256, json_canonico, sha256_texto

VIAS = ("api", "lote", "out_v1")


class RegistroInvalido(ValueError):
    """El texto no es un registro de extraccion que se pueda guardar."""


@dataclass(frozen=True)
class RegistroLeido:
    """Lo que se saca de un registro para las columnas de la tabla."""

    contenido: str
    contenido_sha256: str
    source_sha256: str
    source_name: str | None
    modelo: str
    prompt_version: str
    schema_version: str
    extraido_en: str | None
    request_id: str | None
    uso_json: str | None


def _instante(valor: Any) -> str | None:
    """extracted_at como marca UTC del almacen, o None si no es un instante claro.

    Se normaliza (reloj.marca) en vez de guardar el texto: datetime() de
    SQLite, que es lo que comprueba la columna, no entiende formas que
    Python si lee ('20260920T100012Z', '+0000', semanas ISO), y dos offsets
    distintos no se ordenan bien como texto. Sin zona horaria no se sabe de
    que instante es, y queda vacio. El texto original sigue en
    contenido_json: aqui solo se decide si sirve para ordenar.
    """
    if not isinstance(valor, str):
        return None
    try:
        instante = datetime.fromisoformat(valor)
        if instante.tzinfo is None or instante.utcoffset() is None:
            return None
        return marca(instante)
    except (ValueError, OverflowError):
        return None


def _sin_constantes(nombre: str) -> None:
    """NaN e Infinity: json.loads los acepta, pero no son JSON (json_valid los rechaza)."""
    raise RegistroInvalido(f"{nombre} no es un valor JSON")


def _uso(valor: Any) -> str | None:
    """El consumo como columna: tokens enteros y, si lo hay, un texto corto (service_tier).

    service_tier dice si se pago al precio de lote; sin el, una extraccion de
    lote se contaria al doble de lo que costo.
    """
    if not isinstance(valor, dict):
        return None

    def admitido(v: Any) -> bool:
        if v is None or (isinstance(v, int) and not isinstance(v, bool)):
            return True
        return isinstance(v, str) and 0 < len(v) <= 40

    if not all(isinstance(k, str) and admitido(v) for k, v in valor.items()):
        return None
    return json_canonico(valor)


def leer_registro(contenido: str) -> RegistroLeido:
    """Comprueba que el texto es un registro de extraccion y saca sus columnas.

    No valida la extraccion contra el esquema: se guarda lo que se leyo, y el
    paso 2 decide como interpretarlo (compat.py). Solo exige lo que hace
    falta para atarlo a su documento y a sus versiones.
    """
    try:
        registro = json.loads(contenido, parse_constant=_sin_constantes)
    except json.JSONDecodeError as exc:
        raise RegistroInvalido(f"no es JSON: {exc.msg} (linea {exc.lineno})") from None
    if not isinstance(registro, dict):
        raise RegistroInvalido("no es un objeto JSON")
    if not es_sha256(registro.get("source_sha256")):
        raise RegistroInvalido("source_sha256 falta o no es un sha256 en minusculas")
    for clave in ("model", "prompt_version", "schema_version"):
        if not isinstance(registro.get(clave), str) or not registro[clave]:
            raise RegistroInvalido(f"falta {clave}")
    nombre = registro.get("source_name")
    request_id = registro.get("request_id")
    return RegistroLeido(
        contenido=contenido,
        contenido_sha256=sha256_texto(contenido),
        source_sha256=registro["source_sha256"],
        source_name=nombre if isinstance(nombre, str) and nombre else None,
        modelo=registro["model"],
        prompt_version=registro["prompt_version"],
        schema_version=registro["schema_version"],
        extraido_en=_instante(registro.get("extracted_at")),
        request_id=request_id if isinstance(request_id, str) else None,
        uso_json=_uso(registro.get("usage")),
    )


@dataclass(frozen=True)
class ExtraccionRegistrada:
    id: int
    nueva: bool


def registrar_extraccion(
    conn: sqlite3.Connection,
    registro: RegistroLeido,
    *,
    documento_id: int,
    via: str,
    actor: int,
    usuario_id: int | None = None,
    fichero: str | None = None,
) -> ExtraccionRegistrada:
    """Guarda la extraccion de un documento si no estaba ya, y lo audita.

    `fichero` es el nombre del fichero de out/ que tiene el mismo texto, si
    lo hay. Solo sirve a registros_legado: load_records ordena por nombre de
    fichero, y para dar lo mismo que el hace falta saberlo.
    """
    if via not in VIAS:
        raise ValueError(f"via desconocida: {via!r}")
    exigir_de_su_base(conn, registro.contenido,
                      f"la extraccion de {registro.source_sha256[:12]}")
    with transaccion(conn):
        documento = conn.execute(
            "SELECT sha256 FROM documento WHERE id = ?", (documento_id,)
        ).fetchone()
        if documento is None:
            raise LookupError(f"no hay documento {documento_id}")
        if documento["sha256"] != registro.source_sha256:
            raise ValueError(
                "la extraccion es de otro documento: su source_sha256 no es el del documento"
            )
        existente = conn.execute(
            "SELECT id FROM extraccion WHERE documento_id = ? AND modelo = ? "
            "AND prompt_version = ? AND schema_version = ? AND contenido_sha256 = ?",
            (documento_id, registro.modelo, registro.prompt_version,
             registro.schema_version, registro.contenido_sha256),
        ).fetchone()
        if existente is not None:
            return ExtraccionRegistrada(existente["id"], False)

        cursor = conn.execute(
            "INSERT INTO extraccion (documento_id, modelo, prompt_version, schema_version, via, "
            "extraido_en, request_id, uso_json, contenido_json, contenido_sha256, registrada_en) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (documento_id, registro.modelo, registro.prompt_version, registro.schema_version,
             via, registro.extraido_en, registro.request_id, registro.uso_json,
             registro.contenido, registro.contenido_sha256, marca(reloj_de(conn).ahora())),
        )
        extraccion_id = int(cursor.lastrowid)
        registrar(
            conn, tipo="extraccion_registrada", actor=actor, usuario_id=usuario_id,
            tabla="extraccion", fila_id=extraccion_id,
            datos={"fichero": fichero, "fila": foto(conn, "extraccion", extraccion_id)},
        )
        return ExtraccionRegistrada(extraccion_id, True)


# Una candidata de `reextraer` (paso 6) que nadie ha activado no cuenta: la
# vigente sigue siendo la de antes hasta que una persona la activa despues de
# la puerta de puntuacion.
SIN_CANDIDATAS = (
    "NOT EXISTS (SELECT 1 FROM reextraccion_resultado AS c WHERE c.extraccion_id = e.id) "
    "OR EXISTS (SELECT 1 FROM activacion AS a WHERE a.extraccion_id = e.id)"
)


def en_orden_de_out(conn: sqlite3.Connection, *, con_candidatas: bool = False) -> list[sqlite3.Row]:
    """Las extracciones (id, documento_id, contenido_json) en el orden de out/.

    Es el orden en que load_records las leeria: por el nombre del fichero
    que se apunto al registrarlas, comparado como lo compara Path (en
    Windows, sin distinguir mayusculas). Las que no tienen fichero van
    detras, por orden de entrada.

    Sin `con_candidatas`, quedan fuera las candidatas de una reextraccion que
    no se han activado: no pueden ser la vigente de nadie.
    """
    filtro = "" if con_candidatas else f" WHERE {SIN_CANDIDATAS}"
    filas = conn.execute(
        "SELECT e.id, e.documento_id, e.contenido_json, ("
        "  SELECT json_extract(v.datos_json, '$.fichero') FROM evento AS v"
        "  WHERE v.tipo = 'extraccion_registrada' AND v.tabla = 'extraccion'"
        "    AND v.fila_id = e.id ORDER BY v.id LIMIT 1) AS fichero "
        f"FROM extraccion AS e{filtro}"
    ).fetchall()

    def posicion(fila: sqlite3.Row) -> tuple:
        if isinstance(fila["fichero"], str) and fila["fichero"]:
            return (0, Path(fila["fichero"]), fila["id"])
        return (1, fila["id"])

    return sorted(filas, key=posicion)
