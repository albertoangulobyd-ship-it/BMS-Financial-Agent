"""Las relaciones entre facturas: lo que se propone, lo que deciden las personas y lo que mueve.

Una relacion une un origen (el abono, la factura que corrige o la que
sustituye) con su destino (la original). Llegan de tres sitios (spec §5.D,
tabla 30):

- **la extraccion**: un documento nombra otra factura (related_invoices de
  v2, en factura_cita). Si el numero casa con una sola factura de la misma
  contraparte y el mismo sentido, se propone la relacion que el documento
  enuncia ("credits" es acredita, "replaces" sustituye...). El modelo copia
  el numero y la frase; el codigo decide si casa (decision 20);
- **Exact**: la factura relacionada de un abono de venta, igual;
- **una persona**: la enlaza a mano (anular_acreditar) y entra confirmada.

Lo propuesto no mueve nada: no baja ningun saldo, no cambia el IVA ni calla
un duplicado. Lo confirma o lo rechaza una persona con anular_acreditar
(`confirmar`, `rechazar`), con motivo, en su propia orden (la base lo exige).
Lo que mueve una relacion confirmada lo dice `reglas.relaciones.efectos`, y
lo leen las reglas, las caches de estado, la caja y las consultas: un abono
que cubre la original la deja acreditada, uno parcial le baja lo pendiente,
y una factura sustituida o corregida sale de los totales, de la caja y del
IVA (spec §11, paso 8).

**Copias.** El PDF de una venta solo se lee si no hay fuente estructurada
(§10); si estan las dos, cuenta la de Exact y el PDF se fusiona en ella como
su copia: el mismo sentido, el mismo numero normalizado y la misma
contraparte resuelta. Lo que digan distinto es una discrepancia (M3). Una
persona puede deshacer la fusion (la orden deshacer_fusion), y entonces no se
vuelve a fusionar.

`sincronizar` hace las dos cosas del sistema (copias y propuestas) al
principio de cada pasada del motor, en su transaccion, como pagos.conciliar:
una factura que llega despues que el abono que la nombra recibe su propuesta
en la pasada en que llega.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from . import campos
from .almacen import usuario_sistema
from .almacen.unidades import a_cent
from .campos import Automatico, Leido, Persona
from .dominio import (
    FUENTES_MANUALES,
    RELACIONES_QUE_ACREDITAN,
    RELACIONES_QUE_SUSTITUYEN,
    EstadoRelacion,
    Fuente,
    Permiso,
    TipoFactura,
    TipoRelacion,
)
from .permisos import exigir, orden_auditada
from .reglas import instantanea
from .reglas.relaciones import SIN_EFECTO, Efecto
from .reglas.relaciones import efectos as _efectos

PROPUESTA = EstadoRelacion.PROPUESTA.value
CONFIRMADA = EstadoRelacion.CONFIRMADA.value
RECHAZADA = EstadoRelacion.RECHAZADA.value
NOTA_CREDITO = TipoFactura.NOTA_CREDITO.value

# Lo que enuncia un documento -> el tipo de la relacion que se propone. Sin
# decirlo ("unknown"), un abono acredita y lo demas solo se relaciona.
TIPO_DE_CITA = {"credits": TipoRelacion.ACREDITA.value, "cancels": TipoRelacion.ANULA.value,
                "corrects": TipoRelacion.CORRIGE.value,
                "replaces": TipoRelacion.SUSTITUYE.value,
                "refers_to": TipoRelacion.RELACIONADA.value}


class RelacionNoValida(ValueError):
    """Lo pedido no es una relacion que tenga sentido entre esas dos facturas."""


def _filas(conn: sqlite3.Connection, sql: str, parametros: tuple = ()) -> list[tuple]:
    cursor = conn.cursor()
    cursor.row_factory = None
    return cursor.execute(sql, parametros).fetchall()


# ------------------------------------------------------------ lo que mueven

def efectos(conn: sqlite3.Connection) -> dict[int, Efecto]:
    """Lo que mueven las relaciones confirmadas, por factura (reglas.relaciones.efectos)."""
    confirmadas, _propuestas = instantanea.relaciones(conn)
    if not confirmadas:
        return {}
    totales = dict(_filas(conn, "SELECT id, total_cent FROM factura"))
    return _efectos(confirmadas, totales)


def efecto_de(movido: dict[int, Efecto], factura_id: int) -> Efecto:
    return movido.get(factura_id, SIN_EFECTO)


# ------------------------------------------------------------ la contraparte

def _partes(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """Cada factura con lo que la identifica para casar: sentido, tipo, numero y contraparte."""
    salida = {}
    for (id_, sentido, tipo, numero_norm, total, origen, proveedor_id, cliente_id, emisor_btw,
         emisor_kvk, emisor_nombre, receptor_btw, receptor_nombre, anulada,
         fusionada) in _filas(
            conn, "SELECT id, sentido, tipo, numero_norm, total_cent, origen, proveedor_id, "
                  "cliente_id, emisor_btw_doc, emisor_kvk_doc, emisor_nombre_doc, "
                  "receptor_btw_doc, receptor_nombre_doc, anulada, fusionada_en_id FROM factura"):
        entrante = sentido == "entrante"
        parte = (instantanea.clave_parte(sentido, proveedor_id, None, emisor_btw, emisor_kvk,
                                         emisor_nombre) if entrante else
                 instantanea.clave_parte(sentido, None, cliente_id, receptor_btw, None,
                                         receptor_nombre))
        salida[id_] = {"id": id_, "sentido": sentido, "tipo": tipo, "numero_norm": numero_norm,
                       "total_cent": total, "origen": origen, "parte": parte,
                       "anulada": bool(anulada), "fusionada_en_id": fusionada}
    return salida


# ------------------------------------------------------------ la pasada: copias y propuestas

@dataclass
class Sincronizacion:
    """Lo que hizo el sistema con las relaciones en una pasada."""

    copias: list[tuple[int, int]] = field(default_factory=list)       # (copia, factura)
    propuestas: list[tuple[int, int, int, str]] = field(default_factory=list)
    retiradas: list[int] = field(default_factory=list)
    evento_id: int | None = None


def _copias(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """Cada PDF tipado que es la copia de una factura que llego estructurada (Exact, TRNSPRNT).

    El mismo sentido, el mismo numero y la misma contraparte resuelta en las
    dos (lo que exige tambien el disparador de fusion). No se fusiona lo que
    una persona deshizo a mano, ni una factura en la que ya hay otras
    fusionadas.
    """
    manuales = ", ".join("?" * len(FUENTES_MANUALES))
    filas = _filas(
        conn, "SELECT c.id, min(e.id) FROM factura AS c JOIN factura AS e "
              "ON e.sentido = c.sentido AND e.numero_norm = c.numero_norm "
              "WHERE c.origen = 'extraccion' AND e.origen IN ('exact', 'trnsprnt') "
              "AND c.numero_norm IS NOT NULL AND c.anulada = 0 AND e.anulada = 0 "
              "AND c.fusionada_en_id IS NULL AND e.fusionada_en_id IS NULL "
              "AND ((c.sentido = 'saliente' AND c.cliente_id IS NOT NULL "
              "      AND c.cliente_id = e.cliente_id) "
              "  OR (c.sentido = 'entrante' AND c.proveedor_id IS NOT NULL "
              "      AND c.proveedor_id = e.proveedor_id)) "
              "AND NOT EXISTS (SELECT 1 FROM factura AS x WHERE x.fusionada_en_id = c.id) "
              "AND NOT EXISTS (SELECT 1 FROM procedencia_campo AS p WHERE p.tabla = 'factura' "
              f"  AND p.fila_id = c.id AND p.campo = 'fusionada_en_id' AND p.fuente IN ({manuales})) "
              "GROUP BY c.id ORDER BY c.id", tuple(sorted(FUENTES_MANUALES)))
    return [(c, e) for c, e in filas]


def tipo_de_cita(relacion_doc: str | None, tipo_factura: str) -> str:
    """El tipo de la relacion que se propone por lo que enuncia el documento."""
    tipo = TIPO_DE_CITA.get(relacion_doc or "")
    if tipo is None:
        return (TipoRelacion.ACREDITA.value if tipo_factura == NOTA_CREDITO
                else TipoRelacion.RELACIONADA.value)
    return tipo


def _propuestas(conn: sqlite3.Connection, facturas: dict[int, dict[str, Any]],
                copias: set[int]) -> tuple[list[tuple[int, int, str, str, str | None]], list[int]]:
    """Las relaciones que proponen las citas y las propuestas que ya no sostiene ninguna.

    Una cita propone si su numero casa con una sola factura de la misma
    contraparte y el mismo sentido (una fusionada no cuenta: es la copia de
    otra). No se vuelve a proponer lo que ya hubo entre las dos, en
    cualquier sentido y estado: lo que una persona rechazo o retiro se queda
    asi.
    """
    por_numero: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for f in facturas.values():
        if (f["parte"] is not None and f["numero_norm"] is not None
                and f["fusionada_en_id"] is None and f["id"] not in copias):
            por_numero[(f["sentido"], f["parte"], f["numero_norm"])].append(f["id"])
    ya = {frozenset((o, d)) for o, d in _filas(
        conn, "SELECT origen_id, destino_id FROM factura_relacion")}
    nuevas: list[tuple[int, int, str, str, str | None]] = []
    sostenidas: set[tuple[int, int]] = set()
    for _id, factura_id, numero_norm, relacion, texto in _filas(
            conn, "SELECT id, factura_id, numero_norm, relacion_doc, texto_doc FROM factura_cita "
                  "WHERE retirada_en IS NULL AND numero_norm IS NOT NULL ORDER BY factura_id, id"):
        origen = facturas.get(factura_id)
        if (origen is None or origen["anulada"] or origen["fusionada_en_id"] is not None
                or factura_id in copias or origen["parte"] is None):
            continue
        destinos = [i for i in por_numero.get((origen["sentido"], origen["parte"], numero_norm), ())
                    if i != factura_id]
        if len(destinos) != 1:
            continue
        destino = destinos[0]
        sostenidas.add((factura_id, destino))
        if frozenset((factura_id, destino)) in ya:
            continue
        ya.add(frozenset((factura_id, destino)))
        fuente = "extraccion" if origen["origen"] == "extraccion" else "exact"
        nuevas.append((factura_id, destino, tipo_de_cita(relacion, origen["tipo"]), fuente,
                       texto))
    sueltas = [id_ for id_, origen, destino in _filas(
        conn, "SELECT id, origen_id, destino_id FROM factura_relacion WHERE estado = 'propuesta' "
              "AND retirada_en IS NULL ORDER BY id")
               if (origen, destino) not in sostenidas]
    return nuevas, sueltas


def sincronizar(conn: sqlite3.Connection) -> Sincronizacion:
    """Fusiona las copias y propone (o retira) relaciones. Un evento, o ninguno.

    Lo llama cada pasada del motor (hallazgos.recalcular) al principio, en su
    transaccion. Escribe como el motor, con campos.py: una propuesta entra
    como propuesta (la base no deja al sistema confirmar nada).
    """
    resultado = Sincronizacion()
    if conn.execute("SELECT 1 FROM factura LIMIT 1").fetchone() is None:
        return resultado
    copias = _copias(conn)
    facturas = _partes(conn)
    nuevas, sueltas = _propuestas(conn, facturas, {c for c, _e in copias})
    if not (copias or nuevas or sueltas):
        return resultado
    calculado = Fuente.CALCULADO.value
    origen = Automatico(calculado, usuario_sistema(conn, "motor"), ref="relaciones")
    with campos.orden(conn, origen, tipo="relaciones_sincronizadas",
                      tabla="factura_relacion",
                      datos={"copias": [list(c) for c in copias],
                             "propuestas": [[o, d, t] for o, d, t, _f, _e in nuevas],
                             "retiradas": sueltas}) as o:
        for copia, factura in copias:
            o.fijar("factura", copia, {"fusionada_en_id": Leido(factura, ref=f"copia_de:{factura}")})
        for origen_id, destino_id, tipo, fuente, texto in nuevas:
            relacion = o.crear("factura_relacion", {
                "origen_id": origen_id, "destino_id": destino_id, "tipo": tipo,
                "estado": PROPUESTA, "fuente": fuente, "evidencia_doc": texto})
            resultado.propuestas.append((relacion, origen_id, destino_id, tipo))
        for relacion in sueltas:
            o.retirar("factura_relacion", relacion)
    resultado.copias = copias
    resultado.retiradas = sueltas
    resultado.evento_id = o.resultado.evento_id
    return resultado


# ------------------------------------------------------------ lo que deciden las personas

def _comprobar(facturas: dict[int, dict[str, Any]], origen_id: int, destino_id: int, tipo: str,
               importe_cent: int | None) -> None:
    """Que la relacion tenga sentido: misma contraparte y sentido, y el tipo que les toca.

    Un abono que acredita o anula es una nota de credito sobre una factura,
    por como mucho lo que vale (y en el signo de la original). La que
    sustituye o corrige es una factura. Ninguna de las dos esta fusionada en
    otra (seria su copia), y las dos son de la misma contraparte: enlazar
    facturas de dos proveedores serviria para callar un duplicado o bajar un
    saldo que no es suyo.
    """
    if origen_id == destino_id:
        raise RelacionNoValida("una factura no se relaciona consigo misma")
    for factura_id in (origen_id, destino_id):
        if factura_id not in facturas:
            raise LookupError(f"no hay factura {factura_id}")
    origen, destino = facturas[origen_id], facturas[destino_id]
    if tipo not in TipoRelacion.valores():
        raise RelacionNoValida(f"{tipo!r} no es un tipo de relacion "
                               f"({', '.join(TipoRelacion.valores())})")
    if origen["sentido"] != destino["sentido"]:
        raise RelacionNoValida("una compra y una venta no se relacionan")
    for f in (origen, destino):
        if f["fusionada_en_id"] is not None:
            raise RelacionNoValida(f"la factura {f['id']} esta fusionada en la "
                                   f"{f['fusionada_en_id']}: se relaciona esa")
    if origen["parte"] is None or origen["parte"] != destino["parte"]:
        raise RelacionNoValida("las dos facturas tienen que ser de la misma contraparte (y decir "
                               "cual es)")
    if tipo in RELACIONES_QUE_ACREDITAN:
        if origen["tipo"] != NOTA_CREDITO or destino["tipo"] == NOTA_CREDITO:
            raise RelacionNoValida(f"{tipo}: el origen es un abono y el destino una factura")
        if importe_cent is not None:
            total_destino, total_abono = destino["total_cent"], origen["total_cent"]
            if total_destino is None or total_abono is None:
                raise RelacionNoValida("sin totales en euros no se acredita un importe")
            if importe_cent == 0 or (importe_cent > 0) != (total_destino > 0):
                raise RelacionNoValida("lo acreditado va en el signo de la original y no es "
                                       "cero")
            if abs(importe_cent) > abs(total_abono):
                raise RelacionNoValida(f"el abono {origen_id} no da para acreditar tanto")
    elif importe_cent is not None:
        raise RelacionNoValida(f"una relacion {tipo} no lleva importe")
    if tipo in RELACIONES_QUE_SUSTITUYEN and origen["tipo"] == NOTA_CREDITO:
        raise RelacionNoValida(f"{tipo}: la que sustituye o corrige es una factura, no un abono")


def _viva_entre(conn: sqlite3.Connection, a: int, b: int, excepto: int | None = None) -> int | None:
    fila = conn.execute(
        "SELECT id FROM factura_relacion WHERE retirada_en IS NULL AND estado <> 'rechazada' "
        "AND ((origen_id = ? AND destino_id = ?) OR (origen_id = ? AND destino_id = ?)) "
        "AND id IS NOT ?", (a, b, b, a, excepto)).fetchone()
    return fila[0] if fila else None


def _relacion(conn: sqlite3.Connection, relacion_id: int) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM factura_relacion WHERE id = ?", (relacion_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay relacion {relacion_id}")
    return fila


def _importe(importe: Decimal | None) -> int | None:
    return None if importe is None else a_cent(importe)


def enlazar(conn: sqlite3.Connection, persona: Persona, *, origen_id: int, destino_id: int,
            tipo: str, importe: Decimal | None = None,
            datos: dict[str, Any] | None = None) -> campos.ResultadoOrden:
    """Una persona enlaza dos facturas a mano: la relacion entra confirmada, con su motivo."""
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.ANULAR_ACREDITAR.value,
               accion="enlazar dos facturas")
        _comprobar(_partes(conn), origen_id, destino_id, tipo, _importe(importe))
        viva = _viva_entre(conn, origen_id, destino_id)
        if viva is not None:
            raise RelacionNoValida(f"entre las facturas {origen_id} y {destino_id} ya esta la "
                                   f"relacion {viva}: confirmala, rechazala o retirala")
        valores: dict[str, Any] = {"origen_id": origen_id, "destino_id": destino_id,
                                   "tipo": tipo, "estado": CONFIRMADA}
        if importe is not None:
            valores["importe_cent"] = importe
        with campos.orden(conn, persona, tipo="relacion_enlazada", factura_id=origen_id,
                          datos=datos) as o:
            o.crear("factura_relacion", valores)
    return o.resultado


def confirmar(conn: sqlite3.Connection, persona: Persona, *, relacion_id: int, rev: int | None,
              tipo: str | None = None, importe: Decimal | None = None,
              datos: dict[str, Any] | None = None) -> campos.ResultadoOrden:
    """Una persona confirma una propuesta (y, si hace falta, corrige su tipo o su importe)."""
    return _decidir(conn, persona, relacion_id, rev, CONFIRMADA, tipo, importe, datos)


def rechazar(conn: sqlite3.Connection, persona: Persona, *, relacion_id: int, rev: int | None,
             datos: dict[str, Any] | None = None) -> campos.ResultadoOrden:
    """Una persona rechaza una propuesta: no se vuelve a proponer."""
    return _decidir(conn, persona, relacion_id, rev, RECHAZADA, None, None, datos)


def _decidir(conn: sqlite3.Connection, persona: Persona, relacion_id: int, rev: int | None,
             estado: str, tipo: str | None, importe: Decimal | None,
             datos: dict[str, Any] | None) -> campos.ResultadoOrden:
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.ANULAR_ACREDITAR.value,
               accion=f"{'confirmar' if estado == CONFIRMADA else 'rechazar'} una relacion")
        relacion = _relacion(conn, relacion_id)
        if rev is not None and relacion["rev"] != rev:
            raise campos.Conflicto(f"la relacion {relacion_id} esta en la rev {relacion['rev']} "
                                   f"y se vio la {rev}: vuelve a cargarla")
        if relacion["retirada_en"] is not None or relacion["estado"] != PROPUESTA:
            raise RelacionNoValida(f"la relacion {relacion_id} esta "
                                   f"{'retirada' if relacion['retirada_en'] else relacion['estado']}"
                                   ": solo se decide una propuesta")
        valores: dict[str, Any] = {"estado": estado}
        if estado == CONFIRMADA:
            nuevo_tipo = tipo or relacion["tipo"]
            importe_cent = _importe(importe) if importe is not None else relacion["importe_cent"]
            _comprobar(_partes(conn), relacion["origen_id"], relacion["destino_id"], nuevo_tipo,
                       importe_cent)
            if tipo is not None:
                valores["tipo"] = tipo
            if importe is not None:
                valores["importe_cent"] = importe
        with campos.orden(conn, persona, tipo=f"relacion_{estado}", tabla="factura_relacion",
                          fila_id=relacion_id, factura_id=relacion["origen_id"], datos=datos) as o:
            o.fijar("factura_relacion", relacion_id, valores, rev_esperada=rev)
    return o.resultado


def retirar(conn: sqlite3.Connection, persona: Persona, *, relacion_id: int, rev: int | None,
            datos: dict[str, Any] | None = None) -> campos.ResultadoOrden:
    """Una persona retira una relacion (confirmada o no): deja de mover nada. No se borra."""
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.ANULAR_ACREDITAR.value,
               accion="retirar una relacion")
        relacion = _relacion(conn, relacion_id)
        if rev is not None and relacion["rev"] != rev:
            raise campos.Conflicto(f"la relacion {relacion_id} esta en la rev {relacion['rev']} "
                                   f"y se vio la {rev}: vuelve a cargarla")
        if relacion["retirada_en"] is not None:
            raise RelacionNoValida(f"la relacion {relacion_id} ya esta retirada")
        with campos.orden(conn, persona, tipo="relacion_retirada", tabla="factura_relacion",
                          fila_id=relacion_id, factura_id=relacion["origen_id"], datos=datos) as o:
            o.retirar("factura_relacion", relacion_id)
    return o.resultado


# ------------------------------------------------------------ lectura

def de_factura(conn: sqlite3.Connection, factura_id: int) -> list[dict[str, Any]]:
    """Las relaciones de una factura (como origen o como destino), con su estado."""
    salida = []
    for r in conn.execute(
            "SELECT r.*, o.numero AS origen_numero, d.numero AS destino_numero "
            "FROM factura_relacion AS r JOIN factura AS o ON o.id = r.origen_id "
            "JOIN factura AS d ON d.id = r.destino_id "
            "WHERE r.origen_id = ? OR r.destino_id = ? ORDER BY r.id", (factura_id, factura_id)):
        salida.append({
            "id": r["id"], "rev": r["rev"], "tipo": r["tipo"], "estado": r["estado"],
            "fuente": r["fuente"], "importe_cent": r["importe_cent"],
            "origen_id": r["origen_id"], "origen_numero": r["origen_numero"],
            "destino_id": r["destino_id"], "destino_numero": r["destino_numero"],
            "evidencia_doc": r["evidencia_doc"], "retirada": r["retirada_en"] is not None,
            "papel": "origen" if r["origen_id"] == factura_id else "destino",
        })
    return salida


def propuestas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Las relaciones propuestas que esperan a una persona."""
    return [{"id": r["id"], "rev": r["rev"], "tipo": r["tipo"], "fuente": r["fuente"],
             "origen_id": r["origen_id"], "destino_id": r["destino_id"],
             "evidencia_doc": r["evidencia_doc"]}
            for r in conn.execute("SELECT * FROM factura_relacion WHERE estado = 'propuesta' "
                                  "AND retirada_en IS NULL ORDER BY id")]
