"""Lo pagado: casar el banco con las facturas, el saldo de cada una y las ordenes de pago.

Nada de aqui paga, aprueba un pago ni prepara una transferencia (regla 2 de
arquitectura.md): se apunta lo que ya se pago, que dice el banco, Exact o una
persona. Lo pagado de una factura son sus aplicaciones (aplicacion_pago), con
su importe de verdad: un pago parcial deja la factura pendiente o vencida con
lo que queda, y K2 lo dice (decision 5). No hay plazos ni un "pago parcial"
que gestionar.

**Casar** (`conciliar`, en cada pasada del motor, antes de evaluar). Cada
movimiento del banco que aun no esta cubierto se compara con las facturas en
juego del sentido que le toca (un cargo paga una compra, un abono cobra una
venta) por tres cosas:

- la referencia: el numero de la factura o su referencia de pago aparecen en
  la referencia estructurada, el end-to-end o el concepto del movimiento;
- el importe: lo que queda del movimiento es lo que queda de la factura;
- la contraparte: la cuenta del movimiento esta en el registro de cuentas de
  ese proveedor o cliente.

Con las tres, y una sola factura que las cumpla, el pago es automatico y
queda confirmado. Con dos de tres, y una sola factura con dos, es una
propuesta que una persona confirma (o retira). Con menos, nada: el
movimiento queda sin casar y K7 lo dice pasados unos dias. Lo que una
persona retiro no se vuelve a proponer. Un traspaso entre cuentas propias o
un pago a un beneficiario conocido no se casa con nada.

**El saldo** de una factura es lo confirmado de la fuente que manda: el
banco, si hay algo del banco; si no, Exact; si no, lo marcado a mano
(reglas.pagos.saldo, que usan tambien las reglas y las caches).

**Ordenes** (servicios.py, con marcar_pagada): marcar pagada a mano (con
motivo, con o sin un movimiento del banco), confirmar una propuesta y
retirar un pago.
"""

from __future__ import annotations

import re
import sqlite3
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from . import campos, politica
from .almacen import reloj_de, usuario_sistema
from .almacen.unidades import a_cent, de_cent
from .campos import Automatico, FaltaMotivo, Persona
from .dominio import (
    EstadoAplicacion,
    Fuente,
    FuenteAplicacion,
    MetodoAplicacion,
    Permiso,
    Sentido,
)
from .parsing import normalizar_referencia
from .permisos import exigir, orden_auditada
from .reglas.instantanea import aplicaciones as leer_aplicaciones
from .reglas.pagos import en_el_movimiento, saldo, tolerancia_cent

ENTRANTE = Sentido.ENTRANTE.value
SALIENTE = Sentido.SALIENTE.value
BANCO = FuenteAplicacion.BANCO.value
RETIRADA = EstadoAplicacion.RETIRADA.value
PROPUESTA = EstadoAplicacion.PROPUESTA.value
# Una referencia de menos de tres caracteres ("1", "12") casaria con cualquier cosa.
LARGO_MINIMO = 3
_PALABRA = re.compile(r"[A-Za-z0-9]+(?:[-./_][A-Za-z0-9]+)*")


class PagoNoValido(ValueError):
    """Una orden de pago que no tiene sentido: otra moneda, un importe cero, otro sentido."""


# ------------------------------------------------------------ casar (puro)

@dataclass(frozen=True)
class MovimientoAbierto:
    """Lo que queda de un movimiento por casar, con lo que lo identifica."""

    id: int
    fecha: date
    resto_cent: int                  # con el signo del movimiento
    contraparte_iban: str | None
    referencias: frozenset[str]


@dataclass(frozen=True)
class FacturaAbierta:
    """Una factura en juego con lo que queda por casar con el banco (en su signo)."""

    id: int
    sentido: str
    numero_norm: str | None
    referencia_pago: str | None
    abierto_cent: int
    cuentas: frozenset[str]          # las de su proveedor o cliente en el registro

    @property
    def claves(self) -> frozenset[str]:
        return frozenset(c for c in (self.numero_norm, self.referencia_pago)
                         if c and len(c) >= LARGO_MINIMO)

    def esperado(self) -> int:
        """Lo que tendria que traer el movimiento que la paga, en el signo del movimiento."""
        return -self.abierto_cent if self.sentido == ENTRANTE else self.abierto_cent


def referencias_de(*textos: str | None) -> frozenset[str]:
    """Lo que puede ser un numero de factura en lo que dice el banco, ya normalizado.

    Cada palabra (con sus guiones, puntos o barras: "2026-4471") y cada par de
    palabras seguidas ("2026 4471"): el banco parte a veces el numero en dos.
    """
    salida: set[str] = set()
    for texto in textos:
        if not texto:
            continue
        completo = normalizar_referencia(texto)
        if completo and len(completo) >= LARGO_MINIMO and len(texto) <= 40:
            salida.add(completo)
        palabras = [normalizar_referencia(p) for p in _PALABRA.findall(texto)]
        palabras = [p for p in palabras if p]
        salida.update(p for p in palabras if len(p) >= LARGO_MINIMO)
        salida.update(a + b for a, b in zip(palabras, palabras[1:]) if len(a + b) >= LARGO_MINIMO)
    return frozenset(salida)


@dataclass(frozen=True)
class Casado:
    """Lo que casa un movimiento con una factura: automatico o propuesta, con su porque."""

    movimiento_id: int
    factura_id: int
    metodo: str
    importe_cent: int                # en el signo de la factura
    regla: str


def puntos(m: MovimientoAbierto, f: FacturaAbierta, tolerancia: int) -> tuple[bool, bool, bool]:
    """(referencia, importe, contraparte): en que coinciden un movimiento y una factura."""
    referencia = bool(f.claves & m.referencias)
    importe = abs(m.resto_cent - f.esperado()) <= tolerancia
    contraparte = m.contraparte_iban is not None and m.contraparte_iban in f.cuentas
    return referencia, importe, contraparte


def _que(coincide: tuple[bool, bool, bool]) -> str:
    nombres = ("referencia", "importe", "contraparte")
    return "+".join(n for n, si in zip(nombres, coincide) if si)


def casar(m: MovimientoAbierto, facturas: Iterable[FacturaAbierta], tolerancia: int,
          vistas: frozenset[int] = frozenset()) -> Casado | None:
    """Con que factura casa un movimiento, si casa con una sola (ver el docstring del modulo).

    `vistas` son las facturas que ya tuvieron una aplicacion con este
    movimiento (tambien retirada): no se vuelven a proponer.
    """
    candidatas = []
    for f in facturas:
        if f.id in vistas or f.abierto_cent == 0:
            continue
        if (f.esperado() > 0) != (m.resto_cent > 0):
            continue
        coincide = puntos(m, f, tolerancia)
        cuantos = sum(coincide)
        if cuantos >= 2:
            candidatas.append((cuantos, f, coincide))
    if not candidatas:
        return None
    mejor = max(c[0] for c in candidatas)
    mejores = [c for c in candidatas if c[0] == mejor]
    if len(mejores) != 1:
        return None
    cuantos, f, coincide = mejores[0]
    if cuantos == 3:
        return Casado(m.id, f.id, MetodoAplicacion.AUTOMATICA.value, f.abierto_cent, _que(coincide))
    # Lo que se lleva una propuesta: el movimiento entero, sin pasar de lo que
    # queda de la factura (lo que sobre queda sin casar).
    signo = 1 if f.abierto_cent > 0 else -1
    importe = signo * min(abs(m.resto_cent), abs(f.abierto_cent))
    return Casado(m.id, f.id, MetodoAplicacion.PROPUESTA.value, importe, _que(coincide))


# ------------------------------------------------------------ casar (la base)

class _Indice:
    """Las facturas por sus claves y por el importe que esperan del banco.

    Para casar hacen falta dos de tres coincidencias, asi que una candidata
    coincide al menos en la referencia o en el importe: con el indice no se
    recorre todo el historico por cada movimiento.
    """

    def __init__(self, facturas: Iterable[FacturaAbierta]) -> None:
        self.por_clave: dict[str, set[int]] = defaultdict(set)
        self.por_importe: dict[int, set[int]] = defaultdict(set)
        for f in facturas:
            for clave in f.claves:
                self.por_clave[clave].add(f.id)
            self.por_importe[f.esperado()].add(f.id)
        self.importes = sorted(self.por_importe)

    def candidatas(self, m: MovimientoAbierto, tolerancia: int) -> list[int]:
        ids: set[int] = set()
        for referencia in m.referencias:
            ids |= self.por_clave.get(referencia, set())
        desde = bisect_left(self.importes, m.resto_cent - tolerancia)
        hasta = bisect_right(self.importes, m.resto_cent + tolerancia)
        for importe in self.importes[desde:hasta]:
            ids |= self.por_importe[importe]
        return sorted(ids)


@dataclass
class Conciliacion:
    """Lo que hizo una pasada de casar: aplicaciones automaticas y propuestas nuevas."""

    evento_id: int | None = None
    automaticas: list[tuple[int, int, int]] = field(default_factory=list)   # (aplicacion, mov, fac)
    propuestas: list[tuple[int, int, int]] = field(default_factory=list)

    def a_dict(self) -> dict[str, Any]:
        return {"evento_id": self.evento_id, "automaticas": self.automaticas,
                "propuestas": self.propuestas}


def _filas(conn: sqlite3.Connection, sql: str, parametros: tuple = ()) -> list[tuple]:
    cursor = conn.cursor()
    cursor.row_factory = None
    return cursor.execute(sql, parametros).fetchall()


def _ajenas(conn: sqlite3.Connection) -> frozenset[str]:
    """Las cuentas que no son de nadie a quien se facture: las propias y los beneficiarios."""
    propias = set(politica.empresa(conn).cuentas_propias)
    propias.update(f[0] for f in _filas(
        conn, "SELECT iban FROM beneficiario_conocido WHERE retirada_en IS NULL"))
    return frozenset(propias)


def _sentidos(conn: sqlite3.Connection) -> dict[int, str]:
    return dict(_filas(conn, "SELECT id, sentido FROM factura"))


def movimientos_abiertos(conn: sqlite3.Connection, tolerancia: int = 0) -> list[MovimientoAbierto]:
    """Los movimientos en euros que no estan cubiertos por lo aplicado (propuesto o confirmado)."""
    ajenas = _ajenas(conn)
    sentidos = _sentidos(conn)
    aplicado: dict[int, int] = defaultdict(int)
    for a in leer_aplicaciones(conn):
        if a.movimiento_id is not None and a.estado != RETIRADA:
            aplicado[a.movimiento_id] += en_el_movimiento(a, sentidos.get(a.factura_id, ENTRANTE))
    salida = []
    for id_, fecha, importe, contraparte, concepto, estructurada, e2e in _filas(
            conn, "SELECT id, fecha_contable, importe_cent, contraparte_iban, concepto_doc, "
                  "referencia_estructurada, referencia_e2e FROM movimiento_bancario "
                  "WHERE importe_cent IS NOT NULL AND importe_cent <> 0 "
                  "ORDER BY fecha_contable, id"):
        if contraparte is not None and contraparte in ajenas:
            continue
        resto = importe - aplicado.get(id_, 0)
        if abs(resto) <= tolerancia or (resto > 0) != (importe > 0):
            continue
        salida.append(MovimientoAbierto(id_, date.fromisoformat(fecha), resto, contraparte,
                                        referencias_de(estructurada, e2e, concepto)))
    return salida


def facturas_abiertas(conn: sqlite3.Connection) -> list[FacturaAbierta]:
    """Las facturas en juego, en euros, con lo que queda por cubrir con el banco."""
    cuentas: dict[tuple[str, int], set[str]] = defaultdict(set)
    for titular, proveedor_id, cliente_id, iban in _filas(
            conn, "SELECT titular, proveedor_id, cliente_id, iban FROM cuenta_bancaria "
                  "WHERE titular <> 'propia'"):
        cuentas[(titular, proveedor_id or cliente_id)].add(iban)
    del_banco: dict[int, int] = defaultdict(int)
    for a in leer_aplicaciones(conn):
        if a.fuente == BANCO and a.estado != RETIRADA:
            del_banco[a.factura_id] += a.importe_cent
    salida = []
    for id_, sentido, numero_norm, referencia, total, proveedor_id, cliente_id in _filas(
            conn, "SELECT id, sentido, numero_norm, referencia_pago, total_cent, proveedor_id, "
                  "cliente_id FROM factura WHERE anulada = 0 AND fusionada_en_id IS NULL "
                  "AND total_cent IS NOT NULL ORDER BY id"):
        titular, parte = (("proveedor", proveedor_id) if sentido == ENTRANTE
                          else ("cliente", cliente_id))
        salida.append(FacturaAbierta(
            id_, sentido, numero_norm, normalizar_referencia(referencia),
            total - del_banco.get(id_, 0), frozenset(cuentas.get((titular, parte), ()))))
    return salida


def conciliar(conn: sqlite3.Connection, *, tolerancia: Decimal | None = None) -> Conciliacion:
    """Casa los movimientos sin cubrir con las facturas y escribe lo casado. Un evento, o ninguno.

    Lo llama cada pasada del motor (hallazgos.recalcular) antes de evaluar,
    en su transaccion: un movimiento importado antes que su factura se casa
    cuando la factura llega. Escribe como el motor, con campos.py.
    """
    resultado = Conciliacion()
    if conn.execute("SELECT 1 FROM movimiento_bancario LIMIT 1").fetchone() is None:
        return resultado
    tol = tolerancia_cent(tolerancia if tolerancia is not None
                          else politica.politica_reglas(conn).tolerancia_pago)
    movimientos = movimientos_abiertos(conn, tol)
    if not movimientos:
        return resultado
    facturas = facturas_abiertas(conn)
    por_id = {f.id: f for f in facturas}
    indice = _Indice(facturas)
    vistas: dict[int, set[int]] = defaultdict(set)
    for a in leer_aplicaciones(conn):
        if a.movimiento_id is not None:
            vistas[a.movimiento_id].add(a.factura_id)
    casados: list[tuple[Casado, MovimientoAbierto]] = []
    for m in movimientos:
        casado = casar(m, (por_id[i] for i in indice.candidatas(m, tol)), tol,
                       frozenset(vistas[m.id]))
        if casado is None:
            continue
        casados.append((casado, m))
        f = por_id[casado.factura_id]
        por_id[f.id] = FacturaAbierta(f.id, f.sentido, f.numero_norm, f.referencia_pago,
                                      f.abierto_cent - casado.importe_cent, f.cuentas)
    if not casados:
        return resultado
    origen = Automatico(Fuente.CALCULADO.value, usuario_sistema(conn, "motor"), ref="conciliacion")
    with campos.orden(conn, origen, tipo="pagos_conciliados", tabla="aplicacion_pago",
                      datos={"casados": [[c.movimiento_id, c.factura_id, c.metodo, c.regla]
                                         for c, _m in casados]}) as o:
        creadas = []
        for casado, m in casados:
            creadas.append((casado, o.crear("aplicacion_pago", {
                "factura_id": casado.factura_id, "movimiento_id": casado.movimiento_id,
                "importe_cent": de_cent(casado.importe_cent), "fecha_pago": m.fecha,
                "fuente": BANCO, "metodo": casado.metodo, "regla": casado.regla})))
    resultado.evento_id = o.resultado.evento_id
    for casado, aplicacion_id in creadas:
        destino = (resultado.automaticas if casado.metodo == MetodoAplicacion.AUTOMATICA.value
                   else resultado.propuestas)
        destino.append((aplicacion_id, casado.movimiento_id, casado.factura_id))
    return resultado


# ------------------------------------------------------------ saldos

def saldos(conn: sqlite3.Connection, tolerancia: Decimal | None = None) -> dict[int, Any]:
    """El saldo de cada factura (reglas.pagos.Saldo), con la tolerancia de la politica."""
    tol = tolerancia_cent(tolerancia if tolerancia is not None
                          else politica.politica_reglas(conn).tolerancia_pago)
    por_factura: dict[int, list] = defaultdict(list)
    for a in leer_aplicaciones(conn):
        por_factura[a.factura_id].append(a)
    return {id_: saldo(total, por_factura.get(id_, ()), tol)
            for id_, total in _filas(conn, "SELECT id, total_cent FROM factura ORDER BY id")}


# ------------------------------------------------------------ ordenes de personas

def _factura(conn: sqlite3.Connection, factura_id: int) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM factura WHERE id = ?", (factura_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay factura {factura_id}")
    return fila


def _aplicacion(conn: sqlite3.Connection, aplicacion_id: int) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM aplicacion_pago WHERE id = ?", (aplicacion_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay aplicacion de pago {aplicacion_id}")
    return fila


def _comprobar_rev(fila: sqlite3.Row, rev: int | None, que: str) -> None:
    if rev is not None and fila["rev"] != rev:
        raise campos.Conflicto(f"{que} esta en la rev {fila['rev']} y se vio la {rev}: vuelve a "
                               "cargarla")


def marcar_pagada(conn: sqlite3.Connection, persona: Persona, *, factura_id: int,
                  importe: Decimal | None = None, fecha_pago: date | None = None,
                  movimiento_id: int | None = None, rev: int | None = None,
                  datos: dict[str, Any] | None = None) -> campos.ResultadoOrden:
    """Una persona apunta que una factura se pago fuera de lo que el sistema ve. Pide motivo.

    Sin movimiento, es un pago manual (fuente manual): vale hasta que llegue
    el banco o Exact, y K3 avisa si pasados unos dias el banco no lo trae.
    Con un movimiento del banco, lo enlaza a mano (fuente banco): lo que el
    sistema no pudo casar. El importe, en el signo de la factura, es por
    defecto lo que queda; un importe menor deja la factura con su saldo (K2).
    """
    motivo = (persona.motivo or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.MARCAR_PAGADA.value, accion="marcar pagada")
        if not motivo:
            raise FaltaMotivo("marcar una factura pagada a mano pide un motivo")
        factura = _factura(conn, factura_id)
        _comprobar_rev(factura, rev, f"la factura {factura_id}")
        if factura["anulada"] or factura["fusionada_en_id"] is not None:
            raise PagoNoValido(f"la factura {factura_id} esta anulada o fusionada: no se paga")
        if factura["total_cent"] is None:
            raise PagoNoValido(f"la factura {factura_id} no tiene un total en euros (X1): no se "
                               "apunta ningun pago")
        s = saldos(conn)[factura_id]
        hoy = reloj_de(conn).hoy()
        fuente = FuenteAplicacion.MANUAL.value
        if movimiento_id is not None:
            movimiento = conn.execute("SELECT * FROM movimiento_bancario WHERE id = ?",
                                      (movimiento_id,)).fetchone()
            if movimiento is None:
                raise LookupError(f"no hay movimiento {movimiento_id}")
            if movimiento["importe_cent"] is None:
                raise PagoNoValido(f"el movimiento {movimiento_id} no esta en euros (X1)")
            # Un cargo paga una compra y un abono cobra una venta (al reves con un abono).
            entra_dinero = (factura["sentido"] == SALIENTE) == (factura["total_cent"] > 0)
            if (movimiento["importe_cent"] > 0) != entra_dinero:
                raise PagoNoValido("un cargo paga una compra y un abono cobra una venta: el "
                                   "movimiento va en el otro sentido")
            fuente = BANCO
            fecha_pago = fecha_pago or date.fromisoformat(movimiento["fecha_contable"])
            if importe is None:
                resto = next((m.resto_cent for m in movimientos_abiertos(conn)
                              if m.id == movimiento_id), 0)
                pendiente = s.pendiente_cent or 0
                importe_cent = (1 if pendiente >= 0 else -1) * min(abs(resto), abs(pendiente))
                importe = de_cent(importe_cent)
        if importe is None:
            importe = de_cent(s.pendiente_cent or 0)
        if a_cent(importe) == 0:
            raise PagoNoValido("no queda nada por pagar: un pago de cero no se apunta")
        fecha = fecha_pago or hoy
        if fecha > hoy:
            raise PagoNoValido(f"un pago del {fecha.isoformat()} todavia no se ha hecho: aqui se "
                               "apunta lo que ya se pago")
        with campos.orden(conn, persona, tipo="pago_marcado", tabla="aplicacion_pago",
                          factura_id=factura_id, datos=datos) as o:
            o.crear("aplicacion_pago", {
                "factura_id": factura_id, "movimiento_id": movimiento_id, "importe_cent": importe,
                "fecha_pago": fecha, "fuente": fuente,
                "metodo": MetodoAplicacion.MANUAL.value, "motivo": motivo,
                "confirmada_por": persona.usuario_id,
                "confirmada_en": datetime.fromisoformat(o.ahora)})
    return o.resultado


def confirmar_pago(conn: sqlite3.Connection, persona: Persona, *, aplicacion_id: int,
                   rev: int | None = None,
                   datos: dict[str, Any] | None = None) -> campos.ResultadoOrden:
    """Una persona confirma un pago que el sistema propuso (con dos de las tres coincidencias)."""
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.MARCAR_PAGADA.value, accion="confirmar un pago")
        aplicacion = _aplicacion(conn, aplicacion_id)
        _comprobar_rev(aplicacion, rev, f"el pago {aplicacion_id}")
        if aplicacion["estado"] != PROPUESTA:
            raise PagoNoValido(f"el pago {aplicacion_id} esta {aplicacion['estado']}: solo se "
                               "confirma una propuesta")
        with campos.orden(conn, persona, tipo="pago_confirmado", tabla="aplicacion_pago",
                          fila_id=aplicacion_id, factura_id=aplicacion["factura_id"],
                          datos=datos) as o:
            o.fijar("aplicacion_pago", aplicacion_id, {
                "confirmada_por": persona.usuario_id,
                "confirmada_en": datetime.fromisoformat(o.ahora)}, rev_esperada=rev)
    return o.resultado


def retirar_pago(conn: sqlite3.Connection, persona: Persona, *, aplicacion_id: int,
                 rev: int | None = None,
                 datos: dict[str, Any] | None = None) -> campos.ResultadoOrden:
    """Una persona retira un pago (una propuesta que no es, un enlace o una marca equivocados).

    Lo de Exact no se retira aqui: se corrige en Exact y lo trae la siguiente
    importacion. Un pago retirado no se borra, y el sistema no vuelve a
    proponer ese movimiento para esa factura.
    """
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.MARCAR_PAGADA.value, accion="retirar un pago")
        aplicacion = _aplicacion(conn, aplicacion_id)
        _comprobar_rev(aplicacion, rev, f"el pago {aplicacion_id}")
        if aplicacion["fuente"] == FuenteAplicacion.EXACT.value:
            raise PagoNoValido("lo que dice Exact se corrige en Exact: la siguiente importacion "
                               "lo trae")
        if aplicacion["estado"] == RETIRADA:
            raise PagoNoValido(f"el pago {aplicacion_id} ya esta retirado")
        with campos.orden(conn, persona, tipo="pago_retirado", tabla="aplicacion_pago",
                          fila_id=aplicacion_id, factura_id=aplicacion["factura_id"],
                          datos=datos) as o:
            o.retirar("aplicacion_pago", aplicacion_id)
    return o.resultado


# ------------------------------------------------------------ consultas

def de_factura(conn: sqlite3.Connection, factura_id: int) -> dict[str, Any]:
    """Lo pagado de una factura: su saldo y cada aplicacion, con su movimiento."""
    s = saldos(conn).get(factura_id)
    filas = conn.execute(
        "SELECT a.*, m.fecha_contable, m.importe_cent AS importe_movimiento, m.contraparte_iban, "
        "m.contraparte_nombre_doc, m.concepto_doc FROM aplicacion_pago AS a "
        "LEFT JOIN movimiento_bancario AS m ON m.id = a.movimiento_id "
        "WHERE a.factura_id = ? ORDER BY a.id", (factura_id,)).fetchall()
    return {
        "saldo": None if s is None else s._asdict(),
        "aplicaciones": [{k: f[k] for k in f.keys()} for f in filas],
    }


def movimientos(conn: sqlite3.Connection, *, sin_casar: bool = False,
                limite: int = 200) -> list[dict[str, Any]]:
    """Los movimientos del banco, los mas recientes primero, con lo que tienen casado."""
    abiertos = {m.id: m.resto_cent for m in movimientos_abiertos(conn)} if sin_casar else None
    salida = []
    for fila in conn.execute(
            "SELECT m.*, (SELECT count(*) FROM aplicacion_pago AS a WHERE a.movimiento_id = m.id "
            "AND a.estado = 'confirmada') AS confirmadas, "
            "(SELECT count(*) FROM aplicacion_pago AS a WHERE a.movimiento_id = m.id "
            "AND a.estado = 'propuesta') AS propuestas "
            "FROM movimiento_bancario AS m ORDER BY m.fecha_contable DESC, m.id DESC"):
        if abiertos is not None and fila["id"] not in abiertos:
            continue
        salida.append({k: fila[k] for k in fila.keys()})
        if len(salida) >= limite:
            break
    return salida


def propuestas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Los pagos que el sistema propuso y nadie ha confirmado ni retirado."""
    return [{k: f[k] for k in f.keys()} for f in conn.execute(
        "SELECT a.id, a.rev, a.factura_id, f.numero, a.movimiento_id, a.importe_cent, "
        "a.fecha_pago, a.regla, m.contraparte_nombre_doc, m.concepto_doc "
        "FROM aplicacion_pago AS a JOIN factura AS f ON f.id = a.factura_id "
        "LEFT JOIN movimiento_bancario AS m ON m.id = a.movimiento_id "
        "WHERE a.estado = 'propuesta' ORDER BY a.id")]

