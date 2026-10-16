"""El planning de TRNSPRNT: lo que se hace con los turnos leidos antes de registrarlos (paso 10).

Puro, como los lectores: un LoteLeido de turnos canonicos entra y sale otro,
sin tocar la base. Tres cosas:

- **La clave de cada turno.** El identificador del turno en TRNSPRNT
  (`id_externo`) es lo que reconoce el mismo turno en dos fotos del planning
  (G7, V9). Si el fichero no lo trae (la exportacion semanal pivotada no lo
  tiene nunca), la clave es sintetica: el dia o la semana, el Objeto, la
  persona, las horas de inicio y fin y el turno. Se marca `clave_fragil`: si
  TRNSPRNT cambia la hora de un turno, la foto siguiente lo vera como un turno
  que desaparece y otro que aparece. Dos turnos iguales en todo eso llevan su
  ocurrencia (`#2`), como dos movimientos iguales del banco.
- **Un identificador repetido** en el mismo fichero no se adivina: el fichero
  no entra (el planning entra todo o nada, decision 6).
- **Lo que cubre la foto** (`cubre_desde`, `cubre_hasta`): del primer al
  ultimo dia que trae, o lo que diga quien lo importa (`con_cobertura`). Es lo
  que hace que una foto mas nueva sustituya a las anteriores en esos dias
  (v_turno_vigente): un turno que ya no viene en ella, dentro de lo que cubre,
  ya no esta en el planning.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date, timedelta

from ..reglas.normas import normalizar_nombre
from ..reloj import semana_iso
from .base import LoteLeido, Rechazo
from .canonico import TurnoCanonico

TIPO = "planning"
PREFIJO_SINTETICA = "sint:"


def clave_sintetica(turno: TurnoCanonico) -> str:
    """La clave de un turno sin identificador: lo que lo distingue de los demas ese dia."""
    cuando = turno.fecha.isoformat() if turno.fecha is not None else semana_iso(turno.dia)
    partes = [cuando, normalizar_nombre(turno.objeto_ref) or "",
              normalizar_nombre(turno.recurso_ref) or "",
              f"{turno.hora_inicio or ''}-{turno.hora_fin or ''}",
              normalizar_nombre(turno.tipo_turno) or ""]
    return PREFIJO_SINTETICA + "|".join(partes)


def ultimo_dia(turno: TurnoCanonico) -> date:
    """El ultimo dia que toca un turno: el suyo, o el domingo de su semana."""
    return turno.dia if turno.fecha is not None else turno.dia + timedelta(days=6)


def preparar(lote: LoteLeido) -> LoteLeido:
    """Las claves de cada turno, los identificadores repetidos y lo que cubre la foto."""
    registros: list[TurnoCanonico] = list(lote.registros)
    rechazos = list(lote.rechazos)
    estables = Counter(t.id_externo.strip() for t in registros if t.id_externo
                       and t.id_externo.strip())
    repetidos = {clave for clave, veces in estables.items() if veces > 1}
    rechazos.extend(
        Rechazo(t.fila, f"el turno {t.id_externo} esta {estables[t.id_externo.strip()]} veces en "
                        "el fichero: no se sabe cual vale", dict(t.crudo), "duplicada")
        for t in registros if t.id_externo and t.id_externo.strip() in repetidos)
    vistas: Counter[str] = Counter()
    salida = []
    for t in registros:
        if t.id_externo and t.id_externo.strip():
            salida.append(t.model_copy(update={"id_externo": t.id_externo.strip(),
                                               "clave_fragil": False}))
            continue
        clave = clave_sintetica(t)
        vistas[clave] += 1
        if vistas[clave] > 1:
            clave = f"{clave}#{vistas[clave]}"
        salida.append(t.model_copy(update={"id_externo": clave, "clave_fragil": True}))
    fragiles = sum(1 for t in salida if t.clave_fragil)
    avisos = list(lote.avisos)
    if fragiles:
        avisos.append(f"{fragiles} turno(s) sin identificador estable: llevan una clave "
                      "sintetica (dia, Objeto, persona, horas y turno) que no reconoce un turno "
                      "al que TRNSPRNT le cambie la hora")
    desde = min((t.dia for t in salida), default=None)
    hasta = max((ultimo_dia(t) for t in salida), default=None)
    return replace(lote, registros=tuple(salida), rechazos=tuple(sorted(
        rechazos, key=lambda r: r.fila)), avisos=tuple(avisos),
        cubre_desde=lote.cubre_desde or desde, cubre_hasta=lote.cubre_hasta or hasta)


def con_cobertura(lote: LoteLeido, desde: date | None, hasta: date | None) -> LoteLeido:
    """El lote con lo que dice cubrir quien lo importa (la exportacion de un periodo).

    Lo declarado manda sobre los dias que traen los turnos: una exportacion
    de octubre sin ningun turno el dia 31 tambien dice que ese dia no hay
    nada. Un turno fuera de lo declarado es un fichero que no es lo que se dice
    que es: se rechaza entero.
    """
    if desde is None and hasta is None:
        return lote
    desde, hasta = desde or lote.cubre_desde, hasta or lote.cubre_hasta
    if desde is not None and hasta is not None and desde > hasta:
        raise ValueError(f"lo que cubre el planning va del {desde} al {hasta}: al reves")
    fuera = [Rechazo(t.fila, f"el turno del {t.dia.isoformat()} cae fuera de lo que se dice que "
                             f"cubre el fichero ({desde} a {hasta})", dict(t.crudo), "fila")
             for t in lote.registros
             if (desde is not None and t.dia < desde)
             or (hasta is not None and ultimo_dia(t) > hasta)]
    return replace(lote, cubre_desde=desde, cubre_hasta=hasta,
                   rechazos=tuple(sorted((*lote.rechazos, *fuera), key=lambda r: r.fila)))
