"""Quien es quien: un proveedor, un cliente, un Objeto o un recurso, por coincidencia exacta.

Un documento dice un nombre, un KvK y un btw-id; el maestro dice los suyos.
Se busca en este orden, y solo por igualdad tras normalizar:

1. el btw-id,
2. el KvK,
3. un alias confirmado del nombre.

Nunca por IBAN: un IBAN es lo que un estafador cambia, y si sirviera para
reconocer al proveedor, la factura falsa se reconoceria a si misma. Nunca
por parecido: "Van Dijk Bouw" no es "Van Dijk Bouwtechniek" hasta que una
persona confirme el alias, porque juntar dos proveedores mezcla sus IBAN,
sus duplicados y su historia de tarifas. Lo que no se encuentra queda sin
resolver (hallazgo A0, Z2), y nada se crea solo.

Dos filas con el mismo btw-id o el mismo KvK son una ambiguedad, no una
eleccion: queda sin resolver y se dice por que.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from .campos import Automatico, Persona, crear

PARTES = ("proveedor", "cliente")
TABLAS_ALIAS = ("proveedor", "cliente", "objeto", "recurso")

_NO_ALFANUMERICO = re.compile(r"[^0-9A-Za-z]")
_SIN_PUNTUACION = re.compile(r"[^\w\s]")


def normalizar_btw(texto: Any) -> str | None:
    """'NL 0012.34567.B01' es 'NL001234567B01'."""
    limpio = _NO_ALFANUMERICO.sub("", str(texto or "")).upper()
    return limpio or None


def normalizar_kvk(texto: Any) -> str | None:
    """Solo los digitos: 'KvK 8765 4321' es '87654321'."""
    limpio = re.sub(r"\D", "", str(texto or ""))
    return limpio or None


def normalizar_nombre(texto: Any) -> str | None:
    """Sin mayusculas, sin puntuacion y con un espacio entre palabras.

    "Van Dijk B.V." y "van dijk bv" son el mismo nombre escrito de dos
    formas; "Van Dijk Bouw" es otro. Es la misma normalizacion que agrupa los
    pagos del panel (dashboard._nombre_normalizado).
    """
    sin_puntos = _SIN_PUNTUACION.sub("", str(texto or "").lower())
    limpio = " ".join(sin_puntos.split())
    return limpio or None


def parece_iban(texto: Any) -> bool:
    """La forma de un IBAN: dos letras, dos digitos y de 15 a 34 caracteres alfanumericos."""
    compacto = "".join(str(texto or "").split()).upper()
    return (15 <= len(compacto) <= 34 and compacto[:2].isalpha() and compacto[2:4].isdigit()
            and compacto.isalnum())


@dataclass(frozen=True)
class Resolucion:
    """El resultado de buscar una parte: la fila, o por que no hay una."""

    fila_id: int | None
    por: str | None = None                 # btw | kvk | alias | codigo
    candidatos: tuple[int, ...] = ()
    motivo: str | None = None

    @property
    def ambigua(self) -> bool:
        return self.fila_id is None and len(self.candidatos) > 1


def _ids(conn: sqlite3.Connection, tabla: str, columna: str, clave: str,
         normalizar: Any) -> tuple[int, ...]:
    """Las filas cuyo btw-id o KvK, normalizado igual que el del documento, es la clave.

    Los dos lados pasan por la misma funcion: un maestro escrito
    "NL/001234567/B01" o "KvK 8765-4321" es el mismo numero que el
    documento, y la coincidencia sigue siendo exacta. Se compara en Python
    porque la normalizacion es la de aqui, no una cadena de replace() en SQL
    que se quedaria corta con el primer separador nuevo.
    """
    return tuple(
        f["id"] for f in conn.execute(
            f"SELECT id, {columna} FROM {tabla} WHERE {columna} IS NOT NULL ORDER BY id")
        if normalizar(f[columna]) == clave)


def _por_alias(conn: sqlite3.Connection, tabla: str, texto: Any) -> int | None:
    norma = normalizar_nombre(texto)
    if norma is None or parece_iban(norma):
        return None
    fila = conn.execute(
        "SELECT fila_id FROM alias WHERE tabla = ? AND alias_norm = ? AND confirmado = 1 "
        "AND activo = 1", (tabla, norma)).fetchone()
    return int(fila[0]) if fila else None


def resolver_parte(
    conn: sqlite3.Connection, tabla: str, *, btw: Any = None, kvk: Any = None, nombre: Any = None,
) -> Resolucion:
    """El proveedor o el cliente de un documento: btw-id, luego KvK, luego alias confirmado."""
    if tabla not in PARTES:
        raise ValueError(f"{tabla} no es una parte (proveedor o cliente)")
    clave = normalizar_btw(btw)
    if clave:
        ids = _ids(conn, tabla, "btw_id", clave, normalizar_btw)
        if len(ids) == 1:
            return Resolucion(ids[0], "btw", ids)
        if ids:
            return Resolucion(None, None, ids, f"{len(ids)} filas de {tabla} con el btw-id {clave}")
    if tabla == "proveedor":
        numero = normalizar_kvk(kvk)
        if numero:
            ids = _ids(conn, tabla, "kvk", numero, normalizar_kvk)
            if len(ids) == 1:
                return Resolucion(ids[0], "kvk", ids)
            if ids:
                return Resolucion(None, None, ids,
                                  f"{len(ids)} filas de {tabla} con el KvK {numero}")
    fila_id = _por_alias(conn, tabla, nombre)
    if fila_id is not None:
        return Resolucion(fila_id, "alias", (fila_id,))
    return Resolucion(None, motivo=f"ningun {tabla} coincide exactamente")


def resolver_objeto(conn: sqlite3.Connection, texto: Any) -> Resolucion:
    """El Objeto de una linea: por su codigo, o por un alias confirmado. Exacto."""
    norma = normalizar_nombre(texto)
    if norma is None:
        return Resolucion(None, motivo="la linea no nombra ningun Objeto")
    ids = tuple(f["id"] for f in conn.execute("SELECT id, codigo FROM objeto ORDER BY id")
                if normalizar_nombre(f["codigo"]) == norma)
    if len(ids) == 1:
        return Resolucion(ids[0], "codigo", ids)
    if ids:
        return Resolucion(None, None, ids, f"{len(ids)} Objetos con el codigo {texto!r}")
    fila_id = _por_alias(conn, "objeto", texto)
    if fila_id is not None:
        return Resolucion(fila_id, "alias", (fila_id,))
    return Resolucion(None, motivo=f"ningun Objeto se llama {texto!r}")


def resolver_recurso(conn: sqlite3.Connection, texto: Any) -> Resolucion:
    """El recurso (persona que trabajo) de una linea, por un alias confirmado."""
    if normalizar_nombre(texto) is None:
        return Resolucion(None, motivo="la linea no nombra a nadie")
    fila_id = _por_alias(conn, "recurso", texto)
    if fila_id is not None:
        return Resolucion(fila_id, "alias", (fila_id,))
    return Resolucion(None, motivo=f"ningun recurso se llama {texto!r}")


def anadir_alias(
    conn: sqlite3.Connection, tabla: str, alias: str, fila_id: int,
    origen: Automatico | Persona, *, origen_alias: str = "manual", confirmado: bool = True,
) -> int:
    """Un nombre mas con el que se reconoce una fila. Devuelve el id del alias.

    Se niega con un IBAN (un IBAN no identifica a nadie) y con un nombre que
    ya es alias de otra fila: eso se resuelve a mano, no eligiendo una.
    Volver a anadir el mismo alias a la misma fila no hace nada.
    """
    if tabla not in TABLAS_ALIAS:
        raise ValueError(f"{tabla} no admite alias")
    norma = normalizar_nombre(alias)
    if norma is None:
        raise ValueError("un alias vacio no reconoce a nadie")
    if parece_iban(alias) or parece_iban(norma):
        raise ValueError("un IBAN nunca es un alias: no identifica a nadie")
    existente = conn.execute(
        "SELECT id, fila_id FROM alias WHERE tabla = ? AND alias_norm = ?", (tabla, norma)
    ).fetchone()
    if existente is not None:
        if existente["fila_id"] == fila_id:
            return int(existente["id"])
        raise ValueError(
            f"{alias!r} ya es alias de {tabla} {existente['fila_id']}: no se reasigna solo")
    return crear(conn, "alias", {
        "tabla": tabla, "alias": alias.strip(), "fila_id": fila_id, "origen": origen_alias,
        "confirmado": confirmado,
    }, origen, tipo="alias_alta")
