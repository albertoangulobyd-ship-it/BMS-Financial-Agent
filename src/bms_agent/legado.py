"""Los registros de siempre, sacados del almacen.

checks.py, dashboard.py, facturacion.py y report.py trabajan sobre los
diccionarios que escribe el extractor (los de out/*.json). Este adaptador se
los da sacados del almacen, de dos maneras:

- `registros_legado()`: la extraccion vigente de cada documento, tal cual se
  guardo. Es la prueba de que la migracion de out/ al almacen no perdio ni
  cambio nada (paso 1).
- `registros_resueltos()`: el mismo diccionario, pero con los valores
  actuales de la factura tipada (paso 2). Donde un campo sigue siendo el que
  leyo la extraccion vigente, va su literal impreso tal cual ("8.740,00",
  "13-09-2026"), sacado de la propia extraccion; donde una persona lo
  corrigio, va el valor corregido escrito de forma que parsing.py lo lee
  exacto. Asi las reglas y el panel de hoy corren sin cambiar una linea
  sobre los datos corregidos, y sin correcciones dan byte a byte lo mismo
  que sobre out/.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import campos, ingesta
from .almacen.extracciones import en_orden_de_out
from .almacen.unidades import de_cent, de_e4, de_mil, de_pb
from .parsing import parse_amount
from .report import vigentes


def registros_legado(conn: sqlite3.Connection, todas: bool = False) -> list[dict[str, Any]]:
    """Un registro por documento, el de su extraccion vigente, como load_records.

    No usa la vista v_extraccion_vigente: esa es la regla del almacen
    (extraido_en en UTC), y load_records compara el texto de extracted_at
    tal cual. Las dos coinciden con lo que escribe el extractor; para que
    esta coincida tambien con un out/ raro (una fecha que no es ISO, otro
    offset), aqui se aplica la misma funcion que en load_records, sobre las
    extracciones en el orden de out/. El orden importa: construir_datos
    lista las facturas de B2 en el orden en que le llegan.

    `todas=True` devuelve cada extraccion guardada, como
    load_records(..., todas=True): es lo que cuenta lo gastado.

    Solo lo que llego por la via de compras (paso 8): el panel de siempre
    trata cada registro como una factura de proveedor, y una venta leida de su
    PDF contaria como gasto, entraria en la proyeccion como coste y en B2, B3,
    B4, F3 y G3 de los proveedores (huecos.md, §2, acoplamiento 1). Las ventas
    viven en el almacen tipado, no en este contrato.
    """
    salientes = {f[0] for f in conn.execute(
        "SELECT id FROM documento WHERE ruta_declarada = 'saliente'")}
    leidos = [json.loads(fila["contenido_json"]) for fila in en_orden_de_out(conn)
              if fila["documento_id"] not in salientes]
    return leidos if todas else vigentes(leidos)


# ------------------------------------------------------------ resueltos

def literal_decimal(valor: Decimal) -> str:
    """Un Decimal escrito de forma que parse_amount lo lea exacto, sin ambiguedad.

    parse_amount lee "42.125" como cuarenta y dos mil ciento veinticinco
    (tres cifras tras el punto son millares). Con dos decimales o menos va
    "42.50"; con mas, se escriben los dos separadores ("0,042.125"), que
    parse_amount siempre lee bien. Se comprueba la vuelta: si no diera el
    mismo numero, mejor fallar que mostrar otro.
    """
    if valor == valor.quantize(Decimal("0.01")):
        texto = f"{valor:.2f}"
    else:
        entero, _, decimales = f"{abs(valor):f}".partition(".")
        con_grupos = f"{int(entero):,}"
        if "," not in con_grupos:
            con_grupos = "0," + entero.rjust(3, "0")
        texto = ("-" if valor < 0 else "") + con_grupos + "." + decimales
    if parse_amount(texto) != valor:
        raise AssertionError(f"{valor} se escribiria como {texto!r}, que no se lee igual")
    return texto


def _escribir(lector: str, valor: Any) -> Any:
    """El valor de una columna escrito como lo escribiria el extractor."""
    if valor is None:
        return None
    if lector == ingesta.IMPORTE:
        return literal_decimal(de_cent(valor))
    if lector == ingesta.CANTIDAD:
        return literal_decimal(de_mil(valor))
    if lector == ingesta.TARIFA:
        return literal_decimal(de_e4(valor))
    if lector == ingesta.PORCENTAJE:
        tipo = de_pb(valor).normalize()
        return f"{tipo:f}%"
    if lector == ingesta.BOOLEANO:
        return bool(valor)
    if lector == ingesta.REGIMEN_IVA:
        return ingesta.REGIMEN_INVERSO.get(valor, "unknown")
    return valor


CABECERA = "cabecera"


def _ruta_de_ref(ref: str | None, extraccion_id: int) -> str | int | None:
    """De que parte de la extraccion vigente viene un valor.

    CABECERA, el indice de la linea, o None si no viene de esa extraccion
    (una persona, un calculo, otra extraccion).
    """
    if not ref:
        return None
    if ref == f"extraccion:{extraccion_id}":
        return CABECERA
    prefijo = f"extraccion:{extraccion_id}:lines["
    if ref.startswith(prefijo) and ref.endswith("]"):
        indice = ref[len(prefijo):-1]
        return int(indice) if indice.isdigit() else None
    return None


def _valor(
    clave: str, columna: str, lector: str, fila: dict[str, Any],
    procedencias: dict[str, dict[str, Any]], literales: dict[str, Any], extraccion_id: int,
    parte: str | int | None,
) -> Any:
    """El literal de la extraccion vigente si el valor sigue siendo el suyo; si no, el actual."""
    p = procedencias.get(columna)
    if p is None:
        return literales.get(clave) if fila[columna] is None else _escribir(lector, fila[columna])
    if (p["fuente"] == "extraccion" and parte is not None
            and _ruta_de_ref(p["fuente_ref"], extraccion_id) == parte):
        return literales.get(clave)
    return _escribir(lector, fila[columna])


def _cabecera(conn: sqlite3.Connection, factura: dict[str, Any], datos: dict[str, Any],
              extraccion_id: int) -> dict[str, Any]:
    procedencias = campos.procedencia(conn, "factura", factura["id"])
    salida = dict(datos)
    for clave, columna, lector in ingesta.CABECERA:
        if clave in IMPRESO:
            continue
        if clave in datos or procedencias.get(columna) is not None:
            salida[clave] = _valor(clave, columna, lector, factura, procedencias, datos,
                                   extraccion_id, CABECERA)
    return salida


# Lo que sale siempre como lo imprimio el documento de la extraccion vigente,
# sea cual sea el valor tipado: el IBAN. detectar_ibanes (F3) compara lo que
# dicen los documentos, y un valor puesto por alguien no es un documento.
IMPRESO = frozenset({"iban"})


def _lineas(conn: sqlite3.Connection, factura_id: int, datos: dict[str, Any],
            extraccion_id: int) -> list[dict[str, Any]]:
    originales = [l for l in (datos.get("lines") or []) if isinstance(l, dict)]
    claves_v1 = [c for c, _col, _l in ingesta.LINEA if c not in compat_lineas_v2()]
    salida = []
    for fila in conn.execute(
        "SELECT * FROM factura_linea WHERE factura_id = ? AND retirada_en IS NULL ORDER BY orden",
        (factura_id,),
    ).fetchall():
        fila = dict(fila)
        procedencias = campos.procedencia(conn, "factura_linea", fila["id"])
        indice = next((r for r in (
            _ruta_de_ref(p["fuente_ref"], extraccion_id) for p in procedencias.values()
            if p["fuente"] == "extraccion") if isinstance(r, int)), None)
        literales = originales[indice] if indice is not None and indice < len(originales) else {}
        linea = dict(literales) if literales else {c: None for c in claves_v1}
        for clave, columna, lector in ingesta.LINEA:
            if clave in linea or procedencias.get(columna) is not None:
                linea[clave] = _valor(clave, columna, lector, fila, procedencias, literales,
                                      extraccion_id, indice)
        salida.append(linea)
    return salida


def compat_lineas_v2() -> frozenset[str]:
    from .compat import CAMPOS_V2_LINEA

    return frozenset(CAMPOS_V2_LINEA)


def _sigue_dudoso(conn: sqlite3.Connection, factura_id: int, ruta: str) -> bool:
    """Un nombre de low_confidence_fields sigue en la lista mientras su campo siga dudoso.

    Si una persona lo verifico o lo corrigio, ya no es una lectura dudosa.
    Un nombre que no es de ningun campo tipado se queda como vino.
    """
    columnas = {c: col for c, col, _l in ingesta.CABECERA}
    if ruta in columnas:
        p = campos.procedencia(conn, "factura", factura_id).get(columnas[ruta])
        return p is None or campos.estado_campo(p).dudoso or p["dudoso"] == 0
    return True


def _resuelto(conn: sqlite3.Connection, factura: dict[str, Any]) -> dict[str, Any]:
    extraccion = conn.execute(
        "SELECT id, contenido_json FROM extraccion WHERE id = ?",
        (factura["extraccion_vigente_id"],)).fetchone()
    registro = json.loads(extraccion["contenido_json"])
    datos = registro.get("extraction") or {}
    resuelto = _cabecera(conn, factura, datos, extraccion["id"])
    if "lines" in datos or conn.execute(
            "SELECT 1 FROM factura_linea WHERE factura_id = ?", (factura["id"],)).fetchone():
        resuelto["lines"] = _lineas(conn, factura["id"], datos, extraccion["id"])
    if isinstance(datos.get("low_confidence_fields"), list):
        resuelto["low_confidence_fields"] = [
            r for r in datos["low_confidence_fields"]
            if not isinstance(r, str) or _sigue_dudoso(conn, factura["id"], r)]
    return {**registro, "extraction": resuelto}


def registros_resueltos(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Los registros de siempre, con los valores actuales de cada factura tipada.

    Mismo orden que registros_legado (el de out/), un registro por
    documento. Un documento que todavia no tiene factura tipada sale tal
    como se extrajo, para que nada desaparezca del panel (`sin_tipar()` dice
    cuantos hay). Una factura fusionada en otra tambien sale: las reglas de
    hoy no saben de fusiones, y quitarla del registro quitaria sus avisos
    (F3, B2, E...) de todos los lectores. Sacarla de los totales y no de los
    avisos es del motor de reglas (paso 3).
    """
    por_documento = {
        f["documento_id"]: dict(f) for f in conn.execute(
            "SELECT * FROM factura WHERE origen = 'extraccion'")
    }
    sha_a_documento = {
        f["sha256"]: f["id"] for f in conn.execute("SELECT id, sha256 FROM documento")}
    salida = []
    for registro in registros_legado(conn):
        documento_id = sha_a_documento.get(registro.get("source_sha256"))
        factura = por_documento.get(documento_id)
        salida.append(registro if factura is None else _resuelto(conn, factura))
    return salida


def sin_tipar(conn: sqlite3.Connection) -> int:
    """Documentos de facturas con extraccion y sin factura tipada (falta `bms-agent ingestar`)."""
    return conn.execute(
        "SELECT count(DISTINCT d.id) FROM documento AS d "
        "JOIN extraccion AS e ON e.documento_id = d.id "
        "WHERE d.ruta_declarada IN ('entrante', 'saliente') AND NOT EXISTS ("
        "  SELECT 1 FROM factura AS f WHERE f.documento_id = d.id AND f.origen = 'extraccion')"
    ).fetchone()[0]


# ------------------------------------------------------------ quien lee

@dataclass(frozen=True)
class Lectura:
    """Los registros que leen el panel, el informe y la exportacion, y de donde salen."""

    registros: list[dict[str, Any]]
    desde: str                 # almacen | out | out_pedido
    ruta_db: Path
    out_dir: Path
    sin_tipar: int = 0

    def explicacion(self) -> str:
        if self.desde == "out_pedido":
            return (f"Se lee {self.out_dir}/ tal cual, sin correcciones, porque se pidio con "
                    "--out (sin --out se lee el almacen)")
        if self.desde == "out":
            return (f"No hay almacen en {self.ruta_db}: se lee {self.out_dir}/ tal cual, sin "
                    "correcciones (crealo con `bms-agent importar-out`)")
        texto = f"Leyendo del almacen {self.ruta_db}, con los valores corregidos"
        if self.sin_tipar:
            texto += (f"; {self.sin_tipar} documentos sin tipar salen como se extrajeron "
                      "(`bms-agent ingestar` los tipa)")
        return texto


def leer_registros(out_dir: str | Path, ruta_db: str | Path, *,
                   out_pedido: bool = False) -> Lectura:
    """Del almacen si existe; de out/ si no hay almacen o si se pidio esa carpeta, y lo dice.

    Con almacen, son los registros resueltos: los valores corregidos a mano
    llegan al panel, al informe y a la exportacion. out/ queda como respaldo
    para quien todavia no ha creado el almacen, y una carpeta pedida
    expresamente (`--out muestras/`) se lee tal cual: quien la nombra quiere
    ver esa carpeta, no el almacen.
    """
    from .almacen import preparar
    from .report import load_records

    ruta_db, out_dir = Path(ruta_db), Path(out_dir)
    if out_pedido:
        return Lectura(load_records(out_dir), "out_pedido", ruta_db, out_dir)
    if not ruta_db.exists():
        return Lectura(load_records(out_dir), "out", ruta_db, out_dir)
    with preparar(ruta_db) as almacen:
        return Lectura(registros_resueltos(almacen.conn), "almacen", ruta_db, out_dir,
                       sin_tipar(almacen.conn))
