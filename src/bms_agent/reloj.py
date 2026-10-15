"""Reloj inyectable.

Todo lo que escribe una marca de tiempo (eventos de auditoria, documentos,
importaciones) la pide a un reloj en vez de llamar a datetime.now. Asi un
test fija el instante y el resultado no depende de cuando se ejecute, y las
reglas de los pasos siguientes reciben `hoy` como dato en vez de mirarlo.

Las marcas se guardan en UTC con el formato que ya usa el extractor
(`2026-09-20T10:00:12+00:00`). `hoy` es la fecha en Amsterdam: es la que
cuenta para vencimientos y plazos de la empresa, no la del servidor.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

ZONA_EMPRESA = "Europe/Amsterdam"


class Reloj:
    """El reloj del sistema."""

    def ahora(self) -> datetime:
        return datetime.now(timezone.utc)

    def hoy(self) -> date:
        """La fecha de hoy en Amsterdam (en Windows necesita el paquete tzdata)."""
        return self.ahora().astimezone(ZoneInfo(ZONA_EMPRESA)).date()


class RelojFijo(Reloj):
    """Un reloj parado en un instante. Solo avanza cuando se le pide."""

    def __init__(self, instante: datetime) -> None:
        if instante.tzinfo is None:
            raise ValueError("el instante de un reloj fijo tiene que llevar zona horaria")
        self.instante = instante

    def ahora(self) -> datetime:
        return self.instante

    def avanzar(self, **delta: float) -> None:
        self.instante = self.instante + timedelta(**delta)


RELOJ_SISTEMA = Reloj()


def marca(instante: datetime) -> str:
    """Un instante como texto UTC con segundos, el formato de todo el almacen."""
    if instante.tzinfo is None:
        raise ValueError("una marca de tiempo sin zona horaria no se sabe de cuando es")
    return instante.astimezone(timezone.utc).isoformat(timespec="seconds")


def semana_iso(dia: date) -> str:
    """La semana ISO de un dia, como '2026-W38'.

    SQLite no la sabe calcular (strftime('%V') devuelve NULL), asi que se
    calcula aqui y se guarda. El ano es el de la semana ISO, que no siempre
    es el del dia: el 1 de enero de 2027 cae en la semana 2026-W53.
    """
    ano, semana, _ = dia.isocalendar()
    return f"{ano:04d}-W{semana:02d}"


def trimestre_de(dia: date) -> tuple[int, int]:
    """El trimestre natural de un dia: (2026, 3) para el 15 de septiembre de 2026."""
    return dia.year, (dia.month - 1) // 3 + 1


@lru_cache(maxsize=256)
def limite_btw(ano: int, trimestre: int) -> date:
    """El ultimo dia para declarar un trimestre: el ultimo del mes siguiente a su cierre.

    El 31 de octubre para el tercero y el 31 de enero del ano siguiente para
    el cuarto (arquitectura.md §8). Confirmarlo con el contable es del paso 11.
    """
    if trimestre not in (1, 2, 3, 4):
        raise ValueError(f"un trimestre va de 1 a 4, no {trimestre}")
    mes, ano_limite = trimestre * 3 + 1, ano
    if mes > 12:
        mes, ano_limite = mes - 12, ano + 1
    siguiente = date(ano_limite + (mes == 12), mes % 12 + 1, 1)
    return siguiente - timedelta(days=1)


def proximo_limite_btw(dia: date, hoy: date) -> date:
    """El plazo del BTW que le toca a algo fechado `dia`, visto desde hoy.

    Es el de su trimestre si aun no ha pasado; si ya paso, el primero que no
    ha pasado: lo que quede por arreglar de un trimestre ya vencido entra en
    la siguiente declaracion.
    """
    ano, trimestre = trimestre_de(dia)
    limite = limite_btw(ano, trimestre)
    while limite < hoy:
        ano, trimestre = (ano + 1, 1) if trimestre == 4 else (ano, trimestre + 1)
        limite = limite_btw(ano, trimestre)
    return limite
