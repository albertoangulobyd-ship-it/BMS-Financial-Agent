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
