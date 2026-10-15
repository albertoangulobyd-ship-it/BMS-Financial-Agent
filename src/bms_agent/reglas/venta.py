"""Reglas de las facturas de venta contra lo pactado: V4 (paso 9).

V4 compara la tarifa de cada linea de venta con la tarifa de venta pactada que
le toca (tarifas.py, de lo mas concreto a lo general: recurso y Objeto,
Objeto, recurso, cliente y, de config/tarifas.yaml, la del tipo de trabajo en
cualquier Objeto). En una venta importa en los dos sentidos: por encima, el
cliente reclamara; por debajo, BM Support BV pierde dinero. Sin tarifa pactada
la referencia seria la del turno en el planning, que llega en el paso 10:
hasta entonces, sin datos (nunca ok). Una ambigua da sin datos y una
retencion de la factura, con su excepcion, como en G3.

Las demas V (horas, Objeto y periodo contra el planning, trabajo sin
facturar, ciclos) son del paso 10; V7 esta en unicidad.py.
"""

from __future__ import annotations

from .base import SALIENTE, SIN_DATOS, Instantanea, Resultado
from .planning import LEE_PACTADA_VENTA, NO_EVIDENCIA_PACTADA, comparar_con_pactadas


def v4(instantanea: Instantanea) -> list[Resultado]:
    """V4: la tarifa de cada linea de venta es la de venta pactada (ni mas ni menos)."""
    return comparar_con_pactadas(instantanea, "V4", SALIENTE, recargos=None,
                                 tambien_por_debajo=True, exceso_bloqueo_pct=None,
                                 sin_pactada=SIN_DATOS)


LEE_V4 = LEE_PACTADA_VENTA | frozenset({"factura.cliente_id"})
SOLO_TEXTO_V4 = NO_EVIDENCIA_PACTADA & LEE_V4
