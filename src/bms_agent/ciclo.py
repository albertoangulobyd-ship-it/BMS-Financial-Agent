"""El latido del ciclo automatico (paso 18, diseno §3.9 y §4.1): `bms-agent ciclo latido`.

El ciclo (docker\\ciclo.ps1, cada 5 minutos) lo llama al principio de cada vuelta, con el
espacio libre que mide desde Windows (en Docker el contenedor solo veria el disco virtual de
WSL2), y Pausar-Automatico con --pausado. Deja una fila en estado_ciclo (una CACHE: se
reescribe), que es lo que la app dice del ciclo ("el trabajo automatico no corre desde...") y
del disco. No decide nada ni lanza nada: solo apunta. `ciclo quitar` (automatico.bat -Quitar)
la borra: sin la automatizacion, la app no dice nada del ciclo, como si no hubiera corrido nunca.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .almacen import reloj_de, transaccion
from .reloj import marca

VARIANTES = ("nativa", "docker")
# Con menos de esto libre, el ciclo no trae ni lee (diseno §3.5, §4.1) y la app lo dice.
DISCO_MINIMO = 10 * 1024 ** 3
# Lo mas grande que se apunta: un numero de bytes de verdad (y que cabe en SQLite).
MAX_DISCO = 2 ** 62


@dataclass(frozen=True)
class Latido:
    visto_en: str
    variante: str | None
    pausado: bool
    pausado_desde: str | None
    disco_libre_bytes: int | None

    @property
    def disco_bajo(self) -> bool:
        return self.disco_libre_bytes is not None and self.disco_libre_bytes < DISCO_MINIMO


def latido(conn: sqlite3.Connection, *, disco_libre: int | None = None, pausado: bool = False,
           variante: str | None = None) -> Latido:
    """Apunta que el ciclo ha pasado ahora. `pausado`: lo apunta Pausar-Automatico (desde
    cuando, si no lo estaba ya); sin el, el ciclo corre y no esta en pausa. Lo que no se da (el
    disco, la variante) queda como estaba."""
    if variante is not None and variante not in VARIANTES:
        raise ValueError(f"variante: {', '.join(VARIANTES)}")
    if disco_libre is not None and (isinstance(disco_libre, bool) or not isinstance(
            disco_libre, int) or not 0 <= disco_libre <= MAX_DISCO):
        raise ValueError("disco libre: un numero de bytes")
    ahora = marca(reloj_de(conn).ahora())
    with transaccion(conn):
        antes = conn.execute("SELECT * FROM estado_ciclo WHERE id = 1").fetchone()
        if variante is None and antes is not None:
            variante = antes["variante"]
        if disco_libre is None and antes is not None:
            disco_libre = antes["disco_libre_bytes"]
        desde = None
        if pausado:
            desde = (antes["pausado_desde"] if antes is not None and antes["pausado"] == 1
                     and antes["pausado_desde"] else ahora)
        conn.execute(
            "INSERT INTO estado_ciclo (id, visto_en, variante, pausado, pausado_desde, "
            "disco_libre_bytes, actualizado_en) VALUES (1, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET visto_en = excluded.visto_en, "
            "variante = excluded.variante, pausado = excluded.pausado, "
            "pausado_desde = excluded.pausado_desde, "
            "disco_libre_bytes = excluded.disco_libre_bytes, "
            "actualizado_en = excluded.actualizado_en",
            (ahora, variante, int(pausado), desde, disco_libre, ahora))
    return Latido(ahora, variante, pausado, desde, disco_libre)


def leer(conn: sqlite3.Connection) -> Latido | None:
    """El ultimo latido, o None si el ciclo no ha pasado nunca."""
    fila = conn.execute("SELECT * FROM estado_ciclo WHERE id = 1").fetchone()
    if fila is None:
        return None
    return Latido(fila["visto_en"], fila["variante"], fila["pausado"] == 1,
                  fila["pausado_desde"], fila["disco_libre_bytes"])


def quitar(conn: sqlite3.Connection) -> bool:
    """La automatizacion se ha quitado (automatico.bat -Quitar): se borra el latido, para que la
    app no diga para siempre que el trabajo automatico no corre (es una CACHE, no evidencia).
    Devuelve si habia alguno."""
    with transaccion(conn):
        return conn.execute("DELETE FROM estado_ciclo WHERE id = 1").rowcount > 0
