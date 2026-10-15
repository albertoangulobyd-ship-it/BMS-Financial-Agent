"""La instantanea: lo que las reglas pueden ver, leido del almacen de una vez y congelado.

Es el unico modulo de reglas/ que toca la base. Lee las facturas tipadas con
sus valores actuales (los que dejo campos.py: lo corregido por una persona
gana a lo extraido), sus lineas e imputaciones activas, el desglose de IVA y
las relaciones confirmadas, y lo deja en tuplas de dataclasses congeladas
ordenadas por id. Lo que es derivar y no decidir tambien se hace aqui, una
vez: la contraparte como clave de agrupacion (identidad.py: btw-id, KvK,
nombre normalizado, nunca el IBAN), la moneda que no es el euro, el Objeto
que nombra cada linea, y que campos traen un literal que no se pudo leer.

Leer de golpe (una consulta por tabla, sin sqlite3.Row) es lo que permite
recalcular cinco mil facturas en menos de dos segundos.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date

from .. import compat
from ..dominio import Sentido
from ..identidad import normalizar_btw, normalizar_kvk, normalizar_nombre
from ..parsing import detectar_moneda
from .base import Factura, Instantanea, Linea, Politica, Relacion, TramoIva

_COLUMNAS_FACTURA = (
    "f.id", "f.sentido", "f.tipo", "f.numero", "f.numero_norm", "f.proveedor_id", "f.cliente_id",
    "f.emisor_nombre_doc", "f.emisor_kvk_doc", "f.emisor_btw_doc", "f.receptor_nombre_doc",
    "f.receptor_btw_doc", "f.fecha_factura", "f.periodo_inicio", "f.periodo_fin", "f.base_cent",
    "f.iva_cent", "f.total_cent", "f.tipo_iva_pb", "f.tratamiento_iva", "f.iban_doc",
    "f.moneda_doc", "f.anulada", "f.fusionada_en_id", "e.schema_version",
)

_COLUMNAS_LINEA = (
    "id", "factura_id", "orden", "descripcion_doc", "objeto_doc", "unidad", "cantidad_mil",
    "tarifa_e4", "importe_cent", "tipo_iva_pb", "fecha_inicio", "fecha_fin", "fecha_trabajo",
)

# Lo que una extraccion v1 no pidio, en columnas de factura (compat.py habla
# en claves del extractor).
_CLAVE_A_COLUMNA = {
    "recipient_name": "receptor_nombre_doc",
    "recipient_vat_number": "receptor_btw_doc",
    "recipient_contact_person": "contacto_nombre_doc",
    "payment_terms_raw": "condiciones_pago_doc",
    "currency_raw": "moneda_doc",
}


def _fecha(texto: str | None) -> date | None:
    return None if texto is None else date.fromisoformat(texto)


def _filas(conn: sqlite3.Connection, sql: str, parametros: tuple = ()) -> list[tuple]:
    cursor = conn.cursor()
    cursor.row_factory = None
    return cursor.execute(sql, parametros).fetchall()


def clave_parte(sentido: str, proveedor_id: int | None, cliente_id: int | None,
                btw: str | None, kvk: str | None, nombre: str | None) -> str | None:
    """La contraparte como clave: la fila del maestro, o lo que el documento dice de ella.

    Por este orden: la fila resuelta, el btw-id, el KvK y el nombre, todos
    normalizados como en identidad.py. Nunca el IBAN: es lo que cambia quien
    se hace pasar por otro. None si el documento no dice nada: dos facturas
    sin nombre no son de la misma contraparte.
    """
    if sentido == Sentido.ENTRANTE.value and proveedor_id is not None:
        return f"proveedor:{proveedor_id}"
    if sentido == Sentido.SALIENTE.value and cliente_id is not None:
        return f"cliente:{cliente_id}"
    for prefijo, valor in (("btw", normalizar_btw(btw)), ("kvk", normalizar_kvk(kvk)),
                           ("nom", normalizar_nombre(nombre))):
        if valor:
            return f"{prefijo}:{valor}"
    return None


def _moneda(moneda_doc: str | None) -> str | None:
    """La moneda que no es el euro (X1); None si esta en euros o no se sabe."""
    if not moneda_doc or not moneda_doc.strip():
        return None
    codigo = detectar_moneda(moneda_doc) or moneda_doc.strip().upper()
    return None if codigo in ("EUR", "EURO", "EUROS") else codigo


def _no_solicitados(schema_version: str | None) -> frozenset[str]:
    if schema_version is None:
        return frozenset()
    try:
        claves = compat.no_solicitados(schema_version)
    except ValueError:
        return frozenset()
    return frozenset(_CLAVE_A_COLUMNA[c] for c in claves if c in _CLAVE_A_COLUMNA)


def _ilegibles(conn: sqlite3.Connection) -> dict[tuple[str, int], set[str]]:
    """Campos con un literal impreso y sin valor: estan en el papel, no se pudieron leer."""
    salida: dict[tuple[str, int], set[str]] = defaultdict(set)
    for tabla, fila_id, campo in _filas(
            conn, "SELECT tabla, fila_id, campo FROM procedencia_campo "
                  "WHERE valor_actual IS NULL AND valor_original_crudo IS NOT NULL "
                  "AND tabla IN ('factura', 'factura_linea')"):
        salida[(tabla, fila_id)].add(campo)
    return salida


def _objeto_de_linea(conn: sqlite3.Connection) -> dict[int, int]:
    """El Objeto resuelto de cada linea con una sola imputacion activa.

    Una linea dividida en varias imputaciones no nombra un Objeto solo; ahi
    vale lo impreso.
    """
    por_linea: dict[int, list[int | None]] = defaultdict(list)
    for linea_id, objeto_id in _filas(
            conn, "SELECT linea_id, objeto_id FROM factura_imputacion "
                  "WHERE retirada_en IS NULL AND linea_id IS NOT NULL"):
        por_linea[linea_id].append(objeto_id)
    return {l: o[0] for l, o in por_linea.items() if len(o) == 1 and o[0] is not None}


def _clave_objeto(objeto_id: int | None, objeto_doc: str | None) -> str | None:
    if objeto_id is not None:
        return f"objeto:{objeto_id}"
    texto = normalizar_nombre(objeto_doc)
    return f"doc:{texto}" if texto else None


def construir(conn: sqlite3.Connection, *, hoy: date,
              politica: Politica | None = None) -> Instantanea:
    """La instantanea del almacen tal como esta ahora, para evaluar el catalogo."""
    ilegibles = _ilegibles(conn)
    objetos = _objeto_de_linea(conn)
    vacio: frozenset[str] = frozenset()

    lineas: dict[int, list[Linea]] = defaultdict(list)
    for fila in _filas(conn, f"SELECT {', '.join(_COLUMNAS_LINEA)} FROM factura_linea "
                             "WHERE retirada_en IS NULL ORDER BY factura_id, orden, id"):
        (id_, factura_id, orden, descripcion, objeto_doc, unidad, cantidad, tarifa, importe,
         tipo_iva, inicio, fin, trabajo) = fila
        lineas[factura_id].append(Linea(
            id=id_, orden=orden, descripcion_doc=descripcion, objeto_doc=objeto_doc,
            unidad=unidad, cantidad_mil=cantidad, tarifa_e4=tarifa, importe_cent=importe,
            tipo_iva_pb=tipo_iva, fecha_inicio=_fecha(inicio), fecha_fin=_fecha(fin),
            fecha_trabajo=_fecha(trabajo),
            objeto=_clave_objeto(objetos.get(id_), objeto_doc),
            ilegibles=frozenset(ilegibles.get(("factura_linea", id_), vacio))))

    desglose: dict[int, list[TramoIva]] = defaultdict(list)
    for id_, factura_id, tipo_iva, base, cuota in _filas(
            conn, "SELECT id, factura_id, tipo_iva_pb, base_cent, cuota_cent FROM factura_iva "
                  "WHERE retirada_en IS NULL ORDER BY factura_id, id"):
        desglose[factura_id].append(TramoIva(id_, tipo_iva, base, cuota))

    facturas = []
    for fila in _filas(conn, f"SELECT {', '.join(_COLUMNAS_FACTURA)} FROM factura AS f "
                             "LEFT JOIN extraccion AS e ON e.id = f.extraccion_vigente_id "
                             "ORDER BY f.id"):
        (id_, sentido, tipo, numero, numero_norm, proveedor_id, cliente_id, emisor_nombre,
         emisor_kvk, emisor_btw, receptor_nombre, receptor_btw, fecha_factura, inicio, fin,
         base, iva, total, tipo_iva, tratamiento, iban, moneda_doc, anulada, fusionada_en,
         schema_version) = fila
        entrante = sentido == Sentido.ENTRANTE.value
        nombre = emisor_nombre if entrante else receptor_nombre
        facturas.append(Factura(
            id=id_, sentido=sentido, tipo=tipo, numero=numero, numero_norm=numero_norm,
            parte=(clave_parte(sentido, proveedor_id, None, emisor_btw, emisor_kvk, emisor_nombre)
                   if entrante else
                   clave_parte(sentido, None, cliente_id, receptor_btw, None, receptor_nombre)),
            parte_nombre=nombre or "(sin nombre)",
            proveedor_id=proveedor_id, cliente_id=cliente_id,
            emisor_nombre_doc=emisor_nombre, emisor_kvk_doc=emisor_kvk,
            emisor_btw_doc=emisor_btw, receptor_nombre_doc=receptor_nombre,
            receptor_btw_doc=receptor_btw, fecha_factura=_fecha(fecha_factura),
            periodo_inicio=_fecha(inicio), periodo_fin=_fecha(fin), base_cent=base,
            iva_cent=iva, total_cent=total, tipo_iva_pb=tipo_iva, tratamiento_iva=tratamiento,
            iban_doc=iban, moneda=_moneda(moneda_doc), anulada=bool(anulada),
            fusionada_en_id=fusionada_en, lineas=tuple(lineas.get(id_, ())),
            desglose=tuple(desglose.get(id_, ())),
            ilegibles=frozenset(ilegibles.get(("factura", id_), vacio)),
            no_solicitados=_no_solicitados(schema_version)))

    relaciones = tuple(Relacion(o, d, t) for o, d, t in _filas(
        conn, "SELECT origen_id, destino_id, tipo FROM factura_relacion "
              "WHERE estado = 'confirmada' AND retirada_en IS NULL ORDER BY id"))
    return Instantanea(hoy=hoy, politica=politica or Politica(), facturas=tuple(facturas),
                       relaciones=relaciones)
