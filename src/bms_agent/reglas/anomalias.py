"""Reglas de anomalias (spec §7): U1, un importe raro para esa contraparte.

El metodo es el de la especificacion, exacto: contra las bases anteriores de
la misma contraparte en facturas que no estan anuladas (ni fusionadas en
otra):

- con 6 o mas, falla si |x - mediana| / (1,4826 · MAD) > 3,5; con MAD 0,
  si |x - mediana| / mediana > 0,5 (con mediana 0, si x no es 0);
- con 3 a 5, si x > 2 · mediana o x < 0,5 · mediana;
- con menos de 3, sin_datos.

La aritmetica es exacta, sin floats: en enteros (la mediana doblada y la
MAD por cuatro lo son siempre) y en fracciones solo para ensenar el
resultado. La mediana de las desviaciones se busca sobre la lista ordenada
sin construirla (la k-esima de dos listas ordenadas), para que un proveedor
con miles de facturas no vuelva la regla cuadratica.

Los abonos no entran ni se miden: su base es negativa y no dice nada del
importe habitual. Como las demas reglas de factura del paso 5, solo escribe
lo que objeta; el aviso abre ademas una excepcion (spec §7).
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

from .base import (
    FALLO,
    LEE_EN_JUEGO,
    Factura,
    Instantanea,
    Objetivo,
    Resultado,
    euros_texto,
    fallo,
    sin_datos,
    solo_objeciones,
)

MINIMO = 3
ROBUSTO = 6
UMBRAL = Fraction(35, 10)
ESCALA_MAD = Fraction(14826, 10000)
# 3,5 · 1,4826: la distancia maxima en MAD, como fraccion (51891/10000).
LIMITE = UMBRAL * ESCALA_MAD


def mediana(ordenados: Sequence[int]) -> Fraction:
    return Fraction(_doble_mediana(ordenados), 2)


def _doble_mediana(ordenados: Sequence[int]) -> int:
    """Dos veces la mediana: siempre un entero, aunque la mediana acabe en ,5."""
    n = len(ordenados)
    mitad = n // 2
    if n % 2:
        return 2 * ordenados[mitad]
    return ordenados[mitad - 1] + ordenados[mitad]


def mad(ordenados: Sequence[int]) -> Fraction:
    """La mediana de |x - mediana| de una lista ordenada, en O(log n) comparaciones."""
    return Fraction(_cuadruple_mad(ordenados, _doble_mediana(ordenados)), 4)


def _cuadruple_mad(ordenados: Sequence[int], doble_centro: int) -> int:
    """Cuatro veces la MAD, en enteros y en O(log n).

    Con el centro doblado (un entero), las desviaciones dobladas |2x - 2c|
    son enteras; su mediana es entera o acaba en ,5, asi que el doble de esa
    mediana (cuatro veces la MAD) es siempre un entero. Las desviaciones son
    dos listas ya ordenadas sin construirlas: las de los valores <= c (de
    dentro hacia fuera, izquierda) y las de los > c (derecha); su k-esima se
    busca a la vez en las dos. Todo en enteros y sin llamadas por paso: con
    fracciones, un proveedor con miles de facturas costaba casi medio
    segundo por pasada.
    """
    o, c2 = ordenados, doble_centro
    n = len(o)
    corte = bisect_right(o, c2 // 2)         # cuantos son <= c (floor: los valores son enteros)
    largo_d = n - corte

    def kesima(k: int) -> tuple[int, int, int]:
        """La k-esima desviacion (desde 0) y cuantas de cada lado van hasta ella."""
        bajo, alto = max(0, k + 1 - largo_d), min(k + 1, corte)
        while bajo < alto:
            i = (bajo + alto) // 2
            j = k + 1 - i
            # izquierda[i] < derecha[j - 1]: la k-esima lleva mas de la izquierda.
            if j > 0 and c2 - 2 * o[corte - 1 - i] < 2 * o[corte + j - 1] - c2:
                bajo = i + 1
            else:
                alto = i
        i, j = bajo, k + 1 - bajo
        if i == 0:
            return 2 * o[corte + j - 1] - c2, i, j
        if j == 0:
            return c2 - 2 * o[corte - i], i, j
        return max(c2 - 2 * o[corte - i], 2 * o[corte + j - 1] - c2), i, j

    mitad = n // 2
    if n % 2:
        return 2 * kesima(mitad)[0]
    valor, i, j = kesima(mitad - 1)
    # La siguiente es la menor de las dos que vienen despues.
    siguientes = ([c2 - 2 * o[corte - 1 - i]] if i < corte else []) + (
        [2 * o[corte + j] - c2] if j < largo_d else [])
    return valor + min(siguientes)


def _inusual_enteros(x: int, ordenados: Sequence[int]) -> tuple[str, int, int | None]:
    """Como `inusual`, en enteros: (resultado, 2 x mediana, 4 x MAD).

    Cada comparacion de la especificacion se multiplica hasta quedar en
    enteros: |x - c| > L · MAD (L = 3,5 · 1,4826 = p/q) es, con D = |2x - 2c|
    y M = 4 · MAD, D/2 > (p/q) · M/4, o sea 2 · q · D > p · M.
    """
    n = len(ordenados)
    if n < MINIMO:
        return "sin_datos", 0, None
    c2 = _doble_mediana(ordenados)
    if n < ROBUSTO:
        raro = x > c2 or 4 * x < c2                  # x > 2c o x < c/2
        return (FALLO if raro else "ok"), c2, None
    m4 = _cuadruple_mad(ordenados, c2)
    d2 = abs(2 * x - c2)
    if m4 > 0:
        raro = 2 * LIMITE.denominator * d2 > LIMITE.numerator * m4
    elif c2 != 0:
        raro = 2 * d2 > abs(c2)                      # |x - c| / |c| > 1/2
    else:
        raro = x != 0
    return (FALLO if raro else "ok"), c2, m4


def _normal_por_conteo(x: int, o: Sequence[int]) -> bool:
    """Si x no es raro, decidido sin calcular la MAD (con 6 o mas anteriores y MAD > 0).

    x es raro si MAD < D / L, o sea si la mediana de las desviaciones
    dobladas e = |2x_i - 2c| es menor que T = q·D/p. Contar cuantas e son
    menores que T son dos busquedas en la lista ordenada (los x_i con
    (2c - T)/2 < x_i < (2c + T)/2); con n impar eso decide, y con n par
    decide salvo si cuentan justo la mitad. Devuelve True solo cuando el
    conteo asegura que no es raro; si no (raro, dudoso, o MAD 0, que tiene
    su propia regla), el calculo exacto de `_inusual_enteros` decide.
    """
    n = len(o)
    mitad = n // 2
    c2 = _doble_mediana(o)
    if c2 % 2 == 0:                          # MAD 0: mas de la mitad son la mediana
        centro = c2 // 2
        if bisect_right(o, centro) - bisect_left(o, centro) >= mitad + 1:
            return False
    p, q = LIMITE.numerator, LIMITE.denominator
    d = q * abs(2 * x - c2)
    alto = bisect_left(o, -((-(p * c2 + d)) // (2 * p)))     # x_i < (p·2c + qD) / 2p
    bajo = bisect_right(o, (p * c2 - d) // (2 * p))          # x_i > (p·2c - qD) / 2p
    cerca = max(0, alto - bajo)
    if n % 2:
        return cerca < mitad + 1
    return cerca <= mitad - 1


def inusual(x: int, ordenados: Sequence[int]) -> tuple[str, Fraction, Fraction | None]:
    """Si una base es rara frente a las anteriores: (resultado, mediana, MAD)."""
    resultado, c2, m4 = _inusual_enteros(x, ordenados)
    return resultado, Fraction(c2, 2), (None if m4 is None else Fraction(m4, 4))


def _texto(valor: Fraction | None) -> str | None:
    if valor is None:
        return None
    if valor.denominator == 1:
        return str(valor.numerator)
    return f"{valor.numerator}/{valor.denominator}"


def _euros(cent: Fraction) -> str:
    return euros_texto((Decimal(cent.numerator) / Decimal(cent.denominator) / 100).quantize(
        Decimal("0.01")))


def _preparar_u1(instantanea: Instantanea) -> dict[int, Resultado]:
    """Recorre cada contraparte por fecha y deja el resultado de U1 de cada factura que lo tiene."""
    grupos: dict[tuple[str, str], list[Factura]] = defaultdict(list)
    for f in instantanea.facturas:
        if (f.parte is not None and f.tipo != "nota_credito" and f.base_cent is not None
                and not f.anulada and f.fusionada_en_id is None):
            grupos[(f.sentido, f.parte)].append(f)
    salida: dict[int, Resultado] = {}
    for lista in grupos.values():
        lista.sort(key=lambda f: (f.fecha_factura or date.min, f.id))
        anteriores: list[int] = []
        for f in lista:
            n = len(anteriores)
            if n >= ROBUSTO and _normal_por_conteo(f.base_cent, anteriores):
                insort(anteriores, f.base_cent)
                continue
            resultado, c2, m4 = _inusual_enteros(f.base_cent, anteriores)
            if resultado == "sin_datos":
                salida[f.id] = sin_datos(
                    "U1", f, f"Solo hay {n} factura{'s' if n != 1 else ''} anterior"
                             f"{'es' if n != 1 else ''} de esta contraparte: hacen falta 3 para "
                             "decir si el importe es raro.", valores={"anteriores": n})
            elif resultado == FALLO:
                centro = Fraction(c2, 2)
                desviacion = None if m4 is None else Fraction(m4, 4)
                salida[f.id] = fallo(
                    "U1", f, f"Base {_euros(Fraction(f.base_cent))} frente a una mediana de "
                             f"{_euros(centro)} en sus {n} facturas anteriores.",
                    valores={"base_cent": f.base_cent, "mediana_cent": _texto(centro),
                             "mad_cent": _texto(desviacion), "anteriores": n},
                    objetivos=(Objetivo("factura", f.id, "base_cent"),))
            insort(anteriores, f.base_cent)
    return salida


def u1(factura: Factura, resultados: dict[int, Resultado]) -> list[Resultado]:
    """U1: importe raro para la contraparte (aviso que abre una excepcion; se anula)."""
    resultado = resultados.get(factura.id)
    return [resultado] if resultado is not None else []


LEE_U1 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.parte", "factura.tipo", "factura.base_cent", "factura.sentido",
    "factura.fecha_factura",
})

EVALUAR_U1 = solo_objeciones(u1, _preparar_u1)
