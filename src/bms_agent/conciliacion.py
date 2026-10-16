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

Una conciliacion no cambia despues (la base lo exige). Si cambia la
imputacion (su Objeto, su persona, sus dias, sus horas, la parte de su
factura) o la factura sale de juego, se retira y, si hace falta, se vuelve a
conciliar. Si cambia el planning, no: lo conciliado es con lo que se facturo
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
from .dominio import Fuente, MetodoConciliacion, Sentido, TipoFactura
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

    activas: dict[int, list[tuple[int, str | None, str, int]]] = defaultdict(list)
    for fila_id, imputacion_id, huella, id_externo, horas, sentido in conn.execute(
            "SELECT c.id, c.imputacion_id, c.huella_imputacion, t.id_externo, c.horas_mil, "
            "f.sentido FROM conciliacion AS c JOIN planning_turno AS t "
            "ON t.id = c.planning_turno_id JOIN factura_imputacion AS i "
            "ON i.id = c.imputacion_id JOIN factura AS f ON f.id = i.factura_id "
            "WHERE c.retirada_en IS NULL ORDER BY c.id"):
        activas[imputacion_id].append((fila_id, huella, id_externo, horas, sentido))

    imputaciones = _imputaciones(conn)
    huellas = {i.id: huella_imputacion(f, i, l) for f, i, l in imputaciones}
    retirar = sorted(fila_id for imputacion_id, filas in activas.items()
                     for fila_id, huella, *_resto in filas
                     if huellas.get(imputacion_id) != huella)
    retiradas = set(retirar)
    asignado: dict[tuple[str, str], int] = defaultdict(int)
    con_conciliacion = set()
    for imputacion_id, filas in activas.items():
        for fila_id, _huella, id_externo, horas, sentido in filas:
            if fila_id not in retiradas:
                asignado[(sentido, id_externo)] += horas
                con_conciliacion.add(imputacion_id)

    nuevas: list[tuple[Imputacion, str, str, list[tuple[int, int]]]] = []
    if not caducado:
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
            if not contenido.turnos or contenido.parcial:
                continue
            nuevas.append((i, celda.nivel, huellas[i.id],
                           _repartir(i.horas_mil, contenido.turnos, f.sentido, asignado)))

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
            "horas_turno_mil": aprobadas if aprobadas is not None else (
                realizadas if realizadas is not None else planificadas),
            "horas_asignadas_mil": horas, "objeto": objeto, "recurso": recurso,
            "importacion_id": importacion_id})
    return list(salida.values())
