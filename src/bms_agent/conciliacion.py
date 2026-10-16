"""La conciliacion: la traza de cada linea de factura a los turnos del planning (paso 10).

Arquitectura.md §5: para explicar "por que la semana 36 son 47,5 horas" hay
que poder ir de la linea de factura a los turnos concretos, y eso solo se
puede si se guarda cuando se factura. `sincronizar` lo hace en cada pasada
del motor, antes de evaluar, para cada imputacion con horas de una factura
en juego que todavia no tiene su conciliacion:

1. su celda en el planning que vale (reglas/turnos.py: persona o Objeto, y
   dia, semana o periodo, lo mas fino que llevan los dos lados), con los
   turnos de su proveedor (compra) o los facturables de su cliente (venta);
2. sus horas se reparten entre los turnos de la celda por orden (fecha,
   hora de inicio, identificador): a cada turno, lo que le queda por conciliar
   en ese sentido (sus horas menos lo que ya tienen otras facturas), y lo que
   sobra va al ultimo, para que se vea que se cobro de mas (B5, V7);
3. cada turno de la celda queda en una fila de conciliacion, tambien con cero
   horas: lo que se guarda es la celda entera tal como era.

Las celdas mezclan niveles: una linea sin persona se reparte entre los turnos
del Objeto, y una de una persona solo en los suyos. Si la del Objeto se lleva
el turno de una persona, la de esa persona amontona sus horas en el y B5 ve
las mismas horas cobradas dos veces (y el turno de otra persona queda sin
facturar). Por eso en cada pasada se reparten antes las de persona, y una
conciliacion de Objeto cede: si una imputacion nueva de una persona no cabe
en sus turnos porque una de Objeto los ocupa, la de Objeto se retira y se
vuelve a repartir despues, con lo que queda.

Una conciliacion no cambia despues (la base lo exige). Si cambia la
imputacion (su Objeto, su persona, sus dias, sus horas, la parte de su
factura) o la factura sale de juego, se retira y, si hace falta, se vuelve a
conciliar. Una conciliacion manual (la hizo una persona) no la retira el
motor porque su huella no sea la de ahora: solo si su imputacion ya no esta
en juego; si no, el motor desharia el trabajo de una persona en la pasada
siguiente. Si cambia el planning, no: lo conciliado es con lo que se facturo
(regla 9), y la diferencia con el planning de ahora la dicen G7 y V9. Con el
planning pasado de su frescura no se concilia nada nuevo: se esperaria a uno
al dia.

Lo escribe el motor (fuente planning) por campos.py, en un solo evento por
pasada, y solo si algo cambia. La lectura para la ficha de una factura es
`traza`.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, NamedTuple

from . import campos
from .almacen import reloj_de, usuario_sistema
from .almacen.unidades import json_canonico, sha256_texto
from .campos import Automatico
from .dominio import Fuente, MetodoConciliacion, NivelConciliacion, Sentido, TipoFactura
from .reglas import turnos
from .reglas.base import Imputacion, Politica
from .reglas.instantanea import Resolutor, fotos_planning, turnos_vigentes

AUTOMATICA = MetodoConciliacion.AUTOMATICA.value
_FACTURA = TipoFactura.FACTURA.value


class _Factura(NamedTuple):
    """Lo que la celda necesita de una factura (turnos.celda_de lee estos atributos)."""

    id: int
    sentido: str
    tipo: str
    proveedor_id: int | None
    cliente_id: int | None
    fecha_factura: date | None
    periodo_inicio: date | None
    periodo_fin: date | None


class _Linea(NamedTuple):
    id: int
    fecha_trabajo: date | None
    fecha_inicio: date | None
    fecha_fin: date | None
    semana_doc: int | None


@dataclass
class Sincronizacion:
    """Lo que la pasada concilio (imputaciones) y retiro (filas de conciliacion)."""

    conciliadas: list[int] = field(default_factory=list)
    retiradas: list[int] = field(default_factory=list)
    evento_id: int | None = None


def _fecha(texto: str | None) -> date | None:
    return None if texto is None else date.fromisoformat(texto)


def huella_imputacion(f: _Factura, i: Imputacion, linea: _Linea | None) -> str:
    """Lo que tenia la imputacion al conciliarla: si cambia, la conciliacion se rehace."""
    dias = turnos.dias_de(i, linea, f)
    parte = f.proveedor_id if f.sentido == Sentido.ENTRANTE.value else f.cliente_id
    return sha256_texto(json_canonico([
        f.sentido, parte, i.objeto_id, i.recurso_id,
        [d.isoformat() for d in dias] if dias else None, i.horas_mil, i.tipo_turno]))


def _imputaciones(conn: sqlite3.Connection
                  ) -> list[tuple[_Factura, Imputacion, _Linea | None]]:
    """Las imputaciones con horas de las facturas en juego (v_imputacion_vigente), en el orden
    en que se concilian: por fecha de factura, factura e imputacion."""
    salida = []
    for (id_, factura_id, linea_id, objeto_id, recurso_id, horas, inicio, fin, turno, sentido,
         tipo, proveedor_id, cliente_id, fecha, p_inicio, p_fin, l_trabajo, l_inicio, l_fin,
         semana) in conn.execute(
            "SELECT i.id, i.factura_id, i.linea_id, i.objeto_id, i.recurso_id, i.horas_mil, "
            "i.fecha_inicio, i.fecha_fin, i.tipo_turno, f.sentido, f.tipo, f.proveedor_id, "
            "f.cliente_id, f.fecha_factura, f.periodo_inicio, f.periodo_fin, l.fecha_trabajo, "
            "l.fecha_inicio, l.fecha_fin, l.semana_doc FROM v_imputacion_vigente AS i "
            "JOIN factura AS f ON f.id = i.factura_id "
            "LEFT JOIN factura_linea AS l ON l.id = i.linea_id "
            "WHERE i.horas_mil IS NOT NULL "
            "ORDER BY f.fecha_factura IS NULL, f.fecha_factura, f.id, i.id"):
        factura = _Factura(factura_id, sentido, tipo, proveedor_id, cliente_id, _fecha(fecha),
                           _fecha(p_inicio), _fecha(p_fin))
        imputacion = Imputacion(id_, linea_id, objeto_id, recurso_id, None, None, horas,
                                _fecha(inicio), _fecha(fin), None, turno)
        linea = (_Linea(linea_id, _fecha(l_trabajo), _fecha(l_inicio), _fecha(l_fin), semana)
                 if linea_id is not None else None)
        salida.append((factura, imputacion, linea))
    return salida


def _caducado(conn: sqlite3.Connection, hoy: date, politica: Politica) -> bool:
    """Si lo ultimo de TRNSPRNT es mas viejo que su limite de frescura (como Z1)."""
    fotos = fotos_planning(conn)
    if not fotos:
        return True
    ultima = max(fotos, key=lambda f: f.importacion_id)
    return (hoy - ultima.exportado).days > politica.frescura_trnsprnt_dias


def sincronizar(conn: sqlite3.Connection, *, hoy: date | None = None,
                politica: Politica | None = None) -> Sincronizacion:
    """Concilia lo que falta y retira lo que ya no vale (ver el docstring del modulo).

    La llama cada pasada del motor (hallazgos.recalcular), despues de casar
    las PO, en su transaccion. Sin ningun planning importado no hace nada.
    """
    resultado = Sincronizacion()
    fotos = fotos_planning(conn)
    if not fotos:
        return resultado
    hoy = hoy or reloj_de(conn).hoy()
    politica = politica or Politica()
    vigentes = turnos_vigentes(conn, Resolutor(conn))
    indice = turnos.Indice(vigentes)
    cubre = turnos.tramos(fotos)
    caducado = _caducado(conn, hoy, politica)

    activas: dict[int, list[_Activa]] = defaultdict(list)
    for fila in conn.execute(
            "SELECT c.id, c.huella_imputacion, t.id_externo, c.horas_mil, f.sentido, c.metodo, "
            "c.regla, c.imputacion_id FROM conciliacion AS c JOIN planning_turno AS t "
            "ON t.id = c.planning_turno_id JOIN factura_imputacion AS i "
            "ON i.id = c.imputacion_id JOIN factura AS f ON f.id = i.factura_id "
            "WHERE c.retirada_en IS NULL ORDER BY c.id"):
        activas[fila[-1]].append(_Activa(*fila[:-1]))

    imputaciones = _imputaciones(conn)
    huellas = {i.id: huella_imputacion(f, i, l) for f, i, l in imputaciones}
    retiradas = {a.fila_id for imputacion_id, filas in activas.items() for a in filas
                 if (huellas.get(imputacion_id) != a.huella if a.metodo == AUTOMATICA
                     else imputacion_id not in huellas)}
    asignado: dict[tuple[str, str], int] = defaultdict(int)
    con_conciliacion = set()
    for imputacion_id, filas in activas.items():
        for a in filas:
            if a.fila_id not in retiradas:
                asignado[(a.sentido, a.id_externo)] += a.horas
                con_conciliacion.add(imputacion_id)

    nuevas: list[tuple[Imputacion, str, str, list[tuple[int, int]]]] = []
    if not caducado:
        orden = {i.id: n for n, (_f, i, _l) in enumerate(imputaciones)}
        candidatas = _candidatas(imputaciones, con_conciliacion, indice, cubre)
        ceden = _ceden(candidatas, activas, retiradas, asignado)
        for imputacion_id in ceden:
            for a in activas[imputacion_id]:
                retiradas.add(a.fila_id)
                asignado[(a.sentido, a.id_externo)] -= a.horas
            con_conciliacion.discard(imputacion_id)
        if ceden:
            candidatas = _candidatas(imputaciones, con_conciliacion, indice, cubre)
        # Las de una persona primero: una de Objeto se reparte con lo que dejan.
        for c in sorted(candidatas, key=lambda c: (c.celda.dimension != turnos.RECURSO,
                                                   orden[c.imputacion.id])):
            nuevas.append((c.imputacion, c.celda.nivel, huellas[c.imputacion.id],
                           _repartir(c.imputacion.horas_mil, c.contenido.turnos, c.sentido,
                                     asignado)))
    retirar = sorted(retiradas)

    if not (retirar or nuevas):
        return resultado
    ultima = max(f.importacion_id for f in fotos)
    origen = Automatico(Fuente.PLANNING.value, usuario_sistema(conn, "motor"),
                        ref=f"importacion:{ultima}")
    with campos.orden(conn, origen, tipo="conciliacion_sincronizada", tabla="conciliacion",
                      datos={"retiradas": retirar,
                             "conciliadas": [i.id for i, *_r in nuevas]}) as o:
        for fila_id in retirar:
            o.retirar("conciliacion", fila_id)
        for i, nivel, huella, reparto in nuevas:
            for turno_id, horas in reparto:
                o.crear("conciliacion", {
                    "imputacion_id": i.id, "planning_turno_id": turno_id,
                    "horas_mil": Decimal(horas).scaleb(-3), "metodo": AUTOMATICA,
                    "regla": nivel, "huella_imputacion": huella})
    resultado.retiradas = retirar
    resultado.conciliadas = [i.id for i, *_r in nuevas]
    resultado.evento_id = o.resultado.evento_id
    return resultado


class _Activa(NamedTuple):
    """Una fila de conciliacion viva."""

    fila_id: int
    huella: str | None
    id_externo: str
    horas: int
    sentido: str
    metodo: str
    nivel: str


class _Candidata(NamedTuple):
    """Una imputacion que se puede conciliar: su sentido, su celda y los turnos de esta."""

    imputacion: Imputacion
    sentido: str
    celda: turnos.Celda
    contenido: turnos.Contenido


def _candidatas(imputaciones: list[tuple[_Factura, Imputacion, _Linea | None]],
                con_conciliacion: set[int], indice: turnos.Indice,
                cubre: list[tuple[date, date]]) -> list[_Candidata]:
    """Las imputaciones sin conciliacion que se pueden conciliar: de una factura (no un abono)
    con su parte resuelta, dentro de lo que cubre el planning, con turnos en su celda y sin
    una fila semanal partida."""
    salida = []
    for f, i, linea in imputaciones:
        if i.id in con_conciliacion or f.tipo != _FACTURA:
            continue
        parte = f.proveedor_id if f.sentido == Sentido.ENTRANTE.value else f.cliente_id
        if parte is None:
            continue
        filtro = turnos.de_la_parte(f)
        celda = turnos.celda_de(i, linea, f, indice, filtro)
        if celda is None or not turnos.cubierto(celda.desde, celda.hasta, cubre):
            continue
        contenido = turnos.contenido(celda, indice, filtro)
        if contenido.turnos and not contenido.parcial:
            salida.append(_Candidata(i, f.sentido, celda, contenido))
    return salida


_DE_OBJETO = frozenset({NivelConciliacion.OBJETO_DIA.value, NivelConciliacion.OBJETO_SEMANA.value,
                        NivelConciliacion.OBJETO_PERIODO.value})


def _ceden(candidatas: list[_Candidata], activas: dict[int, list[_Activa]],
           retiradas: set[int], asignado: dict[tuple[str, str], int]) -> list[int]:
    """Las imputaciones con una conciliacion automatica de Objeto que tienen que ceder sus
    turnos a una imputacion nueva de una persona: las que ocupan alguno de sus turnos cuando
    las horas de la persona no caben en lo que les queda (ver el docstring del modulo)."""
    ocupan: dict[tuple[str, str], set[int]] = defaultdict(set)
    for imputacion_id, filas in activas.items():
        for a in filas:
            if (a.metodo == AUTOMATICA and a.nivel in _DE_OBJETO and a.horas > 0
                    and a.fila_id not in retiradas):
                ocupan[(a.sentido, a.id_externo)].add(imputacion_id)
    salida: set[int] = set()
    for c in candidatas:
        if not ocupan or c.celda.dimension != turnos.RECURSO:
            continue
        claves = [(c.sentido, t.id_externo) for t in c.contenido.turnos]
        de_objeto = set().union(*(ocupan.get(k, set()) for k in claves))
        queda = sum(max(turnos.horas_referencia(t) - asignado[k], 0)
                    for t, k in zip(c.contenido.turnos, claves))
        if de_objeto and max(c.imputacion.horas_mil, 0) > queda:
            salida.update(de_objeto)
    return sorted(salida)


def _repartir(horas_mil: int, lista: tuple, sentido: str,
              asignado: dict[tuple[str, str], int]) -> list[tuple[int, int]]:
    """Las horas de una imputacion repartidas entre los turnos de su celda, en su orden.

    A cada turno, como mucho lo que le queda en ese sentido; lo que sobra, al
    ultimo (cobrar mas horas de las que hay tiene que verse en la traza). Unas
    horas negativas (una linea de correccion) no se reparten: cada turno queda
    con cero. Actualiza `asignado`.
    """
    salida = []
    queda = max(horas_mil, 0)
    for n, t in enumerate(lista):
        cabe = max(turnos.horas_referencia(t) - asignado[(sentido, t.id_externo)], 0)
        horas = min(queda, cabe) if n < len(lista) - 1 else queda
        queda -= horas
        asignado[(sentido, t.id_externo)] += horas
        salida.append((t.id, horas))
    return salida


# ------------------------------------------------------------ lectura

def traza(conn: sqlite3.Connection, factura_id: int) -> list[dict[str, Any]]:
    """La traza de una factura: por imputacion, los turnos con que se concilio, como eran en
    su foto, con las horas que se les asignaron (arquitectura.md §5)."""
    salida: dict[int, dict[str, Any]] = {}
    for (imputacion_id, nivel, horas, id_externo, fecha, inicio, fin, estado, aprobadas,
         realizadas, planificadas, objeto, recurso, importacion_id, fragil) in conn.execute(
            "SELECT c.imputacion_id, c.regla, c.horas_mil, t.id_externo, t.fecha, "
            "t.hora_inicio, t.hora_fin, t.estado, t.horas_aprobadas_mil, "
            "t.horas_realizadas_mil, t.horas_planificadas_mil, t.objeto_ref_doc, "
            "t.recurso_ref_doc, t.importacion_id, t.clave_fragil "
            "FROM conciliacion AS c JOIN factura_imputacion AS i ON i.id = c.imputacion_id "
            "JOIN planning_turno AS t ON t.id = c.planning_turno_id "
            "WHERE i.factura_id = ? AND c.retirada_en IS NULL ORDER BY c.imputacion_id, c.id",
            (factura_id,)):
        entrada = salida.setdefault(imputacion_id, {"imputacion_id": imputacion_id,
                                                    "nivel": nivel, "horas_mil": 0,
                                                    "turnos": []})
        entrada["horas_mil"] += horas
        entrada["turnos"].append({
            "id_externo": id_externo, "clave_fragil": bool(fragil), "fecha": fecha,
            "hora_inicio": inicio, "hora_fin": fin, "estado": estado,
            "horas_turno_mil": next((h for h in (
                aprobadas if estado == "validado" else None, realizadas, planificadas, aprobadas)
                if h is not None), None),
            "horas_asignadas_mil": horas, "objeto": objeto, "recurso": recurso,
            "importacion_id": importacion_id})
    return list(salida.values())
