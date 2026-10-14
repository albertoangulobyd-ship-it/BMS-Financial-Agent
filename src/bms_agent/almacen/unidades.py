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


# Lo que cabe en una columna INTEGER de SQLite.
ENTERO_MAXIMO = 2**63 - 1
ENTERO_MINIMO = -(2**63)
_DIGITOS_MAXIMOS = len(str(ENTERO_MAXIMO))


class PerdidaDePrecision(ValueError):
    """El valor no cabe exacto en la escala de la columna."""


class FueraDeRango(ValueError):
    """El valor escalado no cabe en un entero de 64 bits (el INTEGER de SQLite)."""


def _a_entero(valor: Decimal | int, decimales: int, columna: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, Decimal)):
        raise TypeError(
            f"{columna}: se espera Decimal o int, no {type(valor).__name__}; "
            "un float ya viene redondeado y un texto hay que leerlo antes"
        )
    numero = Decimal(valor)
    if not numero.is_finite():
        raise ValueError(f"{columna}: {valor} no es un numero finito")
    entero = _escalar_exacto(numero, decimales)
    if entero is None:
        raise PerdidaDePrecision(f"{valor} no cabe en {columna} sin redondear")
    if not ENTERO_MINIMO <= entero <= ENTERO_MAXIMO:
        raise FueraDeRango(f"{valor} no cabe en {columna}: pasa de un entero de 64 bits")
    return entero


def _escalar_exacto(numero: Decimal, decimales: int) -> int | None:
    """numero * 10**decimales como int, o None si tiene decimales de mas.

    Con aritmetica de enteros sobre los digitos, no con Decimal: cualquier
    operacion de Decimal redondea primero a la precision del contexto, y
    entonces la comprobacion de exactitud compara dos numeros ya redondeados.
    """
    signo, digitos, exponente = numero.as_tuple()
    coeficiente = int("".join(map(str, digitos)) or "0")
    exponente += decimales
    if coeficiente == 0:
        return 0
    if exponente >= 0:
        if len(digitos) + exponente > _DIGITOS_MAXIMOS:
            return ENTERO_MAXIMO + 1                    # fuera de rango, sin calcular 10**n
        entero = coeficiente * 10**exponente
    else:
        if -exponente > len(digitos):
            return None                                 # menor que una unidad de la escala
        entero, resto = divmod(coeficiente, 10**-exponente)
        if resto:
            return None
    return -entero if signo else entero


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
