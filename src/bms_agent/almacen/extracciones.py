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
from typing import Any

from ..auditoria import registrar
from ..reloj import marca
from . import reloj_de, transaccion
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
    """extracted_at si es un instante ISO legible; si no, la columna queda vacia.

    El texto original sigue en contenido_json: aqui solo se decide si sirve
    para ordenar.
    """
    if not isinstance(valor, str):
        return None
    try:
        datetime.fromisoformat(valor)
    except ValueError:
        return None
    return valor


def _uso(valor: Any) -> str | None:
    if not isinstance(valor, dict):
        return None
    if not all(isinstance(k, str) and (v is None or (isinstance(v, int) and not isinstance(v, bool)))
               for k, v in valor.items()):
        return None
    return json_canonico(valor)


def leer_registro(contenido: str) -> RegistroLeido:
    """Comprueba que el texto es un registro de extraccion y saca sus columnas.

    No valida la extraccion contra el esquema: se guarda lo que se leyo, y el
    paso 2 decide como interpretarlo (compat.py). Solo exige lo que hace
    falta para atarlo a su documento y a sus versiones.
    """
    try:
        registro = json.loads(contenido)
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
) -> ExtraccionRegistrada:
    """Guarda la extraccion de un documento si no estaba ya, y lo audita."""
    if via not in VIAS:
        raise ValueError(f"via desconocida: {via!r}")
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
            datos={"documento_id": documento_id, "via": via, "modelo": registro.modelo,
                   "prompt_version": registro.prompt_version,
                   "schema_version": registro.schema_version,
                   "contenido_sha256": registro.contenido_sha256},
        )
        return ExtraccionRegistrada(extraccion_id, True)


def contenido_vigente(conn: sqlite3.Connection) -> list[str]:
    """El texto de la extraccion vigente de cada documento, por orden de documento."""
    return [
        fila["contenido_json"]
        for fila in conn.execute(
            "SELECT contenido_json FROM v_extraccion_vigente ORDER BY documento_id, id"
        )
    ]


def contenido_todas(conn: sqlite3.Connection) -> list[str]:
    """El texto de todas las extracciones, por orden de entrada."""
    return [fila["contenido_json"] for fila in conn.execute(
        "SELECT contenido_json FROM extraccion ORDER BY id"
    )]
