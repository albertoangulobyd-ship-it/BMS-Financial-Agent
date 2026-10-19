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
- **Lo que una foto puede borrar sin que nadie lo confirme** (`riesgos`).
  Como lo que cubre una foto sustituye a todo lo anterior, una fecha mal
  escrita (2016 por 2026), un fichero vacio con un --desde/--hasta amplio o
  una exportacion filtrada a un Objeto borrarian en silencio el planning de
  meses, y con el el trabajo sin facturar de V5 y V6. Una foto sin turnos,
  con semanas enteras sin ningun turno dentro de lo que cubre, o que deja sin
  valer muchos turnos del planning de ahora que ella no trae, no se importa
  (no se escribe nada, ni la importacion) si quien la importa no lo confirma
  (--confirmar); confirmada, entra con esos avisos. Cuantos turnos de antes
  deja de valer se dice siempre.
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
# Dias seguidos sin ningun turno dentro de lo que cubre una foto a partir de los
# cuales se pide confirmarla: un servicio de seguridad trabaja cada semana, y dos
# semanas vacias son mas una fecha mal escrita que un planning.
HUECO_MAXIMO_DIAS = 14
# Turnos del planning que vale que una foto puede dejar sin valer (sin traerlos)
# sin pedir confirmacion: hasta estos, o hasta este porcentaje de los que cubre.
DESAPARECEN_MINIMO = 3
DESAPARECEN_PCT = 20


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


class PideConfirmacion(ValueError):
    """Una foto del planning que borraria mucho del de ahora, importada sin --confirmar."""

    # El codigo de su error en /api/v2 (servicios.CODIGOS_ERROR; la app lo dice en NL/EN).
    codigo = "pide_confirmacion"


def hueco_mas_largo(lote: LoteLeido) -> tuple[date, date] | None:
    """Los dias seguidos mas largos sin ningun turno dentro de lo que cubre la foto (una fila
    semanal ocupa su semana entera), o None si no tiene ninguno."""
    if lote.cubre_desde is None or lote.cubre_hasta is None:
        return None
    ocupados = sorted((t.dia, ultimo_dia(t)) for t in lote.registros)
    mas_largo, siguiente = None, lote.cubre_desde
    for desde, hasta in [*ocupados, (lote.cubre_hasta + timedelta(days=1),) * 2]:
        if desde > siguiente:
            hueco = (siguiente, desde - timedelta(days=1))
            if mas_largo is None or (hueco[1] - hueco[0]) > (mas_largo[1] - mas_largo[0]):
                mas_largo = hueco
        siguiente = max(siguiente, hasta + timedelta(days=1))
    return mas_largo


def riesgos(lote: LoteLeido, cubiertos: int, desaparecen: int) -> list[str]:
    """Lo que hace que una foto pida confirmacion antes de entrar (ver el docstring).

    `cubiertos`: los turnos (no cancelados) del planning que vale que la foto
    deja sin valer; `desaparecen`: cuantos de ellos no trae.
    """
    salida = []
    if not lote.registros:
        salida.append("la foto no trae ningun turno: dejaria sin planning todo lo que dice "
                      "cubrir")
    hueco = hueco_mas_largo(lote)
    if lote.registros and hueco is not None and (hueco[1] - hueco[0]).days + 1 > \
            HUECO_MAXIMO_DIAS:
        salida.append(f"del {hueco[0].isoformat()} al {hueco[1].isoformat()} "
                      f"({(hueco[1] - hueco[0]).days + 1} dias) no trae ningun turno, y lo que "
                      f"cubre va del {lote.cubre_desde.isoformat()} al "
                      f"{lote.cubre_hasta.isoformat()}: una fecha mal escrita o un --desde/"
                      "--hasta demasiado amplio borraria ese planning")
    if desaparecen > DESAPARECEN_MINIMO and desaparecen * 100 > cubiertos * DESAPARECEN_PCT:
        salida.append(f"deja sin valer {desaparecen} de los {cubiertos} turnos del planning de "
                      "ahora en lo que cubre, que ella no trae (una exportacion filtrada o "
                      "incompleta?)")
    return salida
