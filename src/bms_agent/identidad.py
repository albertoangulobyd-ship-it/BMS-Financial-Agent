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

import sqlite3
from dataclasses import dataclass
from typing import Any

from .campos import Automatico, Persona, crear
from .reglas.normas import (  # noqa: F401 (se reexportan: identidad es su sitio de siempre)
    normalizar_btw,
    normalizar_iban,
    normalizar_kvk,
    normalizar_nombre,
    normalizar_telefono,
    parece_iban,
)

PARTES = ("proveedor", "cliente")
TABLAS_ALIAS = ("proveedor", "cliente", "objeto", "recurso")


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


def comprobar_alias(conn: sqlite3.Connection, tabla: str, alias: str,
                    fila_id: int) -> tuple[str, int | None]:
    """Que un alias se pueda dar a una fila. Devuelve su forma normalizada y, si ya lo
    tiene esa misma fila, su id.

    Se niega con un IBAN (un IBAN no identifica a nadie) y con un nombre que
    ya es alias de otra fila: eso se resuelve a mano, no eligiendo una. Lo
    usan anadir_alias y el importador de maestros, que lo da dentro de su
    propia orden.
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
    if existente is None:
        return norma, None
    if existente["fila_id"] == fila_id:
        return norma, int(existente["id"])
    raise ValueError(
        f"{alias!r} ya es alias de {tabla} {existente['fila_id']}: no se reasigna solo")


def anadir_alias(
    conn: sqlite3.Connection, tabla: str, alias: str, fila_id: int,
    origen: Automatico | Persona, *, origen_alias: str = "manual", confirmado: bool = True,
    datos: dict[str, Any] | None = None,
) -> int:
    """Un nombre mas con el que se reconoce una fila. Devuelve el id del alias.

    Volver a anadir el mismo alias a la misma fila no hace nada.
    """
    _norma, existente = comprobar_alias(conn, tabla, alias, fila_id)
    if existente is not None:
        return existente
    return crear(conn, "alias", {
        "tabla": tabla, "alias": alias.strip(), "fila_id": fila_id, "origen": origen_alias,
        "confirmado": confirmado,
    }, origen, tipo="alias_alta", datos=datos)


def reconciliar_referencias(conn: sqlite3.Connection, *, actor: int | None = None) -> int:
    """Vuelve a resolver proveedor, cliente, contacto, Objeto y recurso con los maestros de ahora.

    Lo llama quien cambia un maestro (la semilla de tarifas, el importador de
    maestros, una correccion a mano): una factura tipada antes de que
    existiera su proveedor o su Objeto se resuelve ahora. Un valor puesto a
    mano no se pisa. Devuelve cuantos campos cambiaron.

    Vive aqui y no en ingesta.py (que lo reexporta) porque el importador de
    maestros escribe el registro de cuentas, y nada que escriba ese registro
    puede importar la via de entrada de los documentos.
    """
    from .almacen import usuario_sistema
    from .campos import orden
    from .dominio import Fuente

    origen = Automatico(Fuente.CALCULADO.value, actor or usuario_sistema(conn, "motor"),
                        ref="maestros")
    with orden(conn, origen, tipo="referencias_recalculadas") as o:
        for fila in conn.execute(
            "SELECT id FROM factura WHERE fusionada_en_id IS NULL ORDER BY id"
        ).fetchall():
            o.recalcular("factura", fila["id"], ("proveedor_id", "cliente_id", "contacto_id"))
        for fila in conn.execute(
            "SELECT id FROM factura_imputacion WHERE retirada_en IS NULL ORDER BY id"
        ).fetchall():
            o.recalcular("factura_imputacion", fila["id"], ("objeto_id", "recurso_id"))
    return sum(1 for e in o.resultado.efectos if e.accion in ("cambiado", "alta"))
