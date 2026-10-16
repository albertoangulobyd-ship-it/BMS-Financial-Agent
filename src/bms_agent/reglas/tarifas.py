"""Las tarifas pactadas: cual vale para una imputacion, de lo mas concreto a lo general (paso 9).

El §7 (G3) fija el orden: recurso + Objeto + turno, Objeto + turno, parte +
turno, parte. Aqui son cinco niveles, y el turno es una condicion de todos
(una tarifa de noche no es la de una linea de dia):

1. recurso y Objeto: la tarifa nombra a la persona y el Objeto de la linea;
2. Objeto: nombra el Objeto y a nadie en concreto;
3. recurso: nombra a la persona y ningun Objeto (la tarifa propia de un zzp'er
   en cualquier obra; el §7 no la nombra, y sin ella una tarifa por persona del
   maestro no se usaria nunca);
4. parte: ni persona ni Objeto, solo el proveedor (o el cliente);
5. general: ni persona, ni Objeto, ni parte, pero si el tipo de trabajo (la
   tarifa de venta de config/tarifas.yaml "en cualquier obra").

Lo que una tarifa no dice vale para todo (una tarifa sin tipo de trabajo es de
cualquiera), y lo que dice tiene que coincidir. Dentro del nivel mas concreto
que tiene alguna, gana la mas concreta en lo demas (la de esa PO, la de esa
parte, la de ese tipo de trabajo, la de esa unidad, y la de vigencia mas
reciente: una tarifa nueva sustituye a la anterior sin que nadie cierre la
vieja). Si quedan varias con precios distintos, es ambigua: no se adivina, la
regla da sin_datos y abre una excepcion (spec §7). Puro: no lee la base.

El turno, la unidad y el dia de una linea salen del documento, que escribe el
proveedor. Si la linea no casa con ninguna tarifa pero si con alguna de su
parte, su recurso o su Objeto mirando solo esas tres cosas, no es que no haya
nada pactado: es que la linea dice un turno, una unidad o un dia que lo
pactado no tiene. Eso es `no_casa`, y no sigue con el historico como si nada
(G3 y G6 retienen): sin esto, imprimir "Nacht" o "stuk" bastaria para saltarse
el control de la tarifa pactada.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from ..dominio import normalizar_unidad
from .base import Tarifa

UNICA = "unica"
AMBIGUA = "ambigua"
NINGUNA = "ninguna"
NO_CASA = "no_casa"

COMPRA = "compra"
VENTA = "venta"

# El turno de siempre: una linea de dia y una sin turno impreso son lo mismo, y
# la tarifa "Dag" del maestro es la de las dos.
TURNOS_BASE = frozenset({"", "dag", "dagdienst", "dag dienst", "day", "normaal", "regulier",
                         "standaard"})


def normalizar_turno(texto: object) -> str | None:
    """El turno o recargo de una linea o una tarifa, en minusculas; None si es el de siempre."""
    turno = " ".join(str(texto or "").lower().split())
    return None if turno in TURNOS_BASE else turno


@dataclass(frozen=True)
class Pactada:
    """La tarifa pactada que vale para una imputacion: unica (con su precio), ambigua, ninguna
    o no_casa (hay pactadas para ella, pero ninguna de su turno, su unidad o su dia).

    `nivel` es el nivel en que se encontro; `tarifas`, los ids de las que quedaron (una si es
    unica, varias si es ambigua, las que casarian sin turno, unidad ni dia si no_casa).
    """

    estado: str
    tarifa_e4: int | None = None
    nivel: str | None = None
    tarifas: tuple[int, ...] = ()


SIN_PACTADA = Pactada(NINGUNA)


def _parte(t: Tarifa) -> int | None:
    return t.proveedor_id if t.sentido == COMPRA else t.cliente_id


_NIVELES: tuple[tuple[str, Callable[[Tarifa], bool]], ...] = (
    ("recurso y Objeto", lambda t: t.recurso_id is not None and t.objeto_id is not None),
    ("Objeto", lambda t: t.recurso_id is None and t.objeto_id is not None),
    ("recurso", lambda t: t.recurso_id is not None and t.objeto_id is None),
    ("parte", lambda t: t.recurso_id is None and t.objeto_id is None and _parte(t) is not None),
    ("general", lambda t: t.recurso_id is None and t.objeto_id is None and _parte(t) is None
     and t.tipo_servicio is not None),
)


def por_sentido(tarifas: Iterable[Tarifa]) -> dict[str, tuple[Tarifa, ...]]:
    """Las tarifas de compra y de venta por separado, en orden de id."""
    salida: dict[str, list[Tarifa]] = defaultdict(list)
    for t in sorted(tarifas, key=lambda t: t.id):
        salida[t.sentido].append(t)
    return {sentido: tuple(lista) for sentido, lista in salida.items()}


def _vigente(t: Tarifa, fecha: date | None) -> bool:
    if fecha is None:
        return t.vigente_desde is None and t.vigente_hasta is None
    return ((t.vigente_desde is None or t.vigente_desde <= fecha)
            and (t.vigente_hasta is None or fecha <= t.vigente_hasta))


def _concrecion(t: Tarifa) -> tuple:
    """Lo concreta que es una tarifa dentro de su nivel (mayor, mas concreta)."""
    return (t.orden_compra_id is not None, _parte(t) is not None, t.tipo_servicio is not None,
            t.unidad is not None, t.vigente_desde or date.min)


def pactada(tarifas: Sequence[Tarifa], *, parte_id: int | None, recurso_id: int | None,
            objeto_id: int | None, orden_compra_id: int | None, turno: str | None,
            servicio: str | None, unidad: str | None, fecha: date | None) -> Pactada:
    """La tarifa pactada de una imputacion entre `tarifas` (las de su sentido)."""
    unidad = normalizar_unidad(unidad)
    suyas = [
        t for t in tarifas
        if (t.recurso_id is None or t.recurso_id == recurso_id)
        and (t.objeto_id is None or t.objeto_id == objeto_id)
        and (t.orden_compra_id is None or t.orden_compra_id == orden_compra_id)
        and (_parte(t) is None or _parte(t) == parte_id)
        and (t.tipo_servicio is None or t.tipo_servicio == servicio)
    ]
    candidatas = [
        t for t in suyas
        if t.tipo_turno == turno
        and (t.unidad is None or normalizar_unidad(t.unidad) == unidad)
        and _vigente(t, fecha)
    ]
    if not candidatas:
        if suyas:
            return Pactada(NO_CASA, tarifas=tuple(sorted(t.id for t in suyas)))
        return SIN_PACTADA
    for nivel, cumple in _NIVELES:
        del_nivel = [t for t in candidatas if cumple(t)]
        if not del_nivel:
            continue
        mejor = max(_concrecion(t) for t in del_nivel)
        finales = [t for t in del_nivel if _concrecion(t) == mejor]
        ids = tuple(sorted(t.id for t in finales))
        precios = {t.tarifa_e4 for t in finales}
        if len(precios) == 1:
            return Pactada(UNICA, precios.pop(), nivel, ids)
        return Pactada(AMBIGUA, None, nivel, ids)
    return SIN_PACTADA


# Lo que lee pactada() de cada tarifa (para lo que declara una regla que la usa). La
# parte de una tarifa de compra es su proveedor; la de una de venta, su cliente.
_LEE_TARIFA = frozenset({
    "tarifa.id", "tarifa.sentido", "tarifa.recurso_id", "tarifa.objeto_id",
    "tarifa.orden_compra_id", "tarifa.tipo_servicio", "tarifa.tipo_turno", "tarifa.unidad",
    "tarifa.tarifa_e4", "tarifa.vigente_desde", "tarifa.vigente_hasta",
})
LEE_TARIFA_COMPRA = _LEE_TARIFA | {"tarifa.proveedor_id"}
LEE_TARIFA_VENTA = _LEE_TARIFA | {"tarifa.cliente_id"}
