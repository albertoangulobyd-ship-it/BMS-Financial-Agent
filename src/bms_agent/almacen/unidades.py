"""El unico conversor entre Decimal y los enteros del almacen.

El almacen guarda dinero y cantidades como enteros para que SUM, ORDER BY y
los filtros de SQL sean exactos: un importe en TEXT compara como cadena
('100.00' < '20.00') y un REAL suma con error de coma flotante. Cada sufijo
de columna dice la escala:

    _cent   centimos de euro, con signo (los abonos son negativos)
    _mil    milesimas (horas, cantidades)
    _e4     diezmilesimas de euro (tarifas por unidad)
    _pb     puntos basicos (tipos de IVA: 21 % son 2100)

Convertir nunca redondea en silencio: si el valor no cabe exacto en la
escala, se lanza PerdidaDePrecision y quien llama deja el campo vacio con su
hallazgo (Q2). Un float no se acepta en ningun sitio: ya llega redondeado.

Aqui vive tambien el JSON canonico, que es lo que se hashea en la cadena de
auditoria: claves ordenadas, sin espacios y sin floats, para que el mismo
contenido de siempre el mismo hash.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

ESCALA_CENT = 2
ESCALA_MIL = 3
ESCALA_E4 = 4
ESCALA_PB = 2   # sobre el porcentaje: 21 -> 2100


class PerdidaDePrecision(ValueError):
    """El valor no cabe exacto en la escala de la columna."""


def _a_entero(valor: Decimal | int, decimales: int, columna: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, Decimal)):
        raise TypeError(
            f"{columna}: se espera Decimal o int, no {type(valor).__name__}; "
            "un float ya viene redondeado y un texto hay que leerlo antes"
        )
    numero = Decimal(valor)
    if not numero.is_finite():
        raise ValueError(f"{columna}: {valor} no es un numero finito")
    with localcontext() as contexto:
        contexto.prec = 100
        escalado = numero.scaleb(decimales)
        entero = escalado.to_integral_value()
    if entero != escalado:
        raise PerdidaDePrecision(f"{valor} no cabe en {columna} sin redondear")
    return int(entero)


def _de_entero(valor: int, decimales: int) -> Decimal:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"se espera un entero del almacen, no {type(valor).__name__}")
    with localcontext() as contexto:
        contexto.prec = 100
        return Decimal(valor).scaleb(-decimales)


def a_cent(euros: Decimal | int) -> int:
    return _a_entero(euros, ESCALA_CENT, "_cent")


def a_mil(cantidad: Decimal | int) -> int:
    return _a_entero(cantidad, ESCALA_MIL, "_mil")


def a_e4(tarifa: Decimal | int) -> int:
    return _a_entero(tarifa, ESCALA_E4, "_e4")


def a_pb(porcentaje: Decimal | int) -> int:
    """Un tipo en porcentaje (21, 9, 5.5) en puntos basicos (2100, 900, 550)."""
    return _a_entero(porcentaje, ESCALA_PB, "_pb")


def de_cent(valor: int) -> Decimal:
    return _de_entero(valor, ESCALA_CENT)


def de_mil(valor: int) -> Decimal:
    return _de_entero(valor, ESCALA_MIL)


def de_e4(valor: int) -> Decimal:
    return _de_entero(valor, ESCALA_E4)


def de_pb(valor: int) -> Decimal:
    return _de_entero(valor, ESCALA_PB)


def _sin_floats(valor: Any, ruta: str) -> None:
    """Recorre el valor y rechaza lo que no tiene una forma JSON unica."""
    if valor is None or isinstance(valor, (bool, int, str)):
        return
    if isinstance(valor, float):
        raise TypeError(f"{ruta}: un float no entra en el JSON canonico; usa un entero escalado")
    if isinstance(valor, (list, tuple)):
        for i, elemento in enumerate(valor):
            _sin_floats(elemento, f"{ruta}[{i}]")
        return
    if isinstance(valor, dict):
        for clave, elemento in valor.items():
            if not isinstance(clave, str):
                raise TypeError(f"{ruta}: las claves del JSON canonico son texto, no {clave!r}")
            _sin_floats(elemento, f"{ruta}.{clave}")
        return
    raise TypeError(f"{ruta}: {type(valor).__name__} no entra en el JSON canonico")


def json_canonico(valor: Any) -> str:
    """El JSON de siempre para el mismo contenido: claves ordenadas, sin espacios."""
    _sin_floats(valor, "$")
    return json.dumps(
        valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def sha256_texto(texto: str) -> str:
    return sha256_bytes(texto.encode("utf-8"))


def sha256_fichero(ruta: str | Path) -> str:
    """Hash de un fichero leido a trozos, para no cargar un PDF grande entero."""
    resumen = hashlib.sha256()
    with Path(ruta).open("rb") as fichero:
        for trozo in iter(lambda: fichero.read(1 << 20), b""):
            resumen.update(trozo)
    return resumen.hexdigest()


def es_sha256(texto: Any) -> bool:
    """Un sha256 en hexadecimal minuscula, como lo escribe hexdigest()."""
    return (
        isinstance(texto, str) and len(texto) == 64
        and all(c in "0123456789abcdef" for c in texto)
    )
