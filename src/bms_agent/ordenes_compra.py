"""Las ordenes de compra en el almacen (spec §6 ordenes_compra.py, §7 P1-P10; paso 9).

Que referencia impresa es una PO lo decide el codigo, nunca el modelo: el
modelo copia la etiqueta y el valor; aqui se casa el valor normalizado con
las PO registradas de la parte de la factura (`sincronizar`). Una referencia
que casa apunta a su PO (factura_referencia.orden_compra_id) aunque la
etiqueta dijera otra cosa; una que una persona dijo que no es una PO (clase
puesta a mano) no casa nunca.

La imputacion de una linea a una PO sale de sus referencias, por orden:

1. la PO de las referencias impresas en su linea, si es una sola;
2. si no, la de las referencias de la cabecera, si es una sola;
3. un abono sin PO propia toma la de la factura que abona (con su relacion
   confirmada), si toda ella va a una sola PO: un abono de una factura de una
   PO devuelve valor a esa PO.

Varias PO distintas en el mismo sitio no se reparten adivinando: la
imputacion queda sin PO hasta que una persona la decida (`imputar`). Lo que
una persona imputa a mano gana siempre (M1): el calculo queda como valor
automatico, y la sincronizacion solo escribe cuando cambia.

Lo consumido de una PO (`cargos`) es la misma cuenta que reglas/ordenes.cargos
y que la vista v_po_consumo: la base sin IVA de las imputaciones que cuentan,
con los abonos confirmados restando. Un test compara las tres.

Escribir una PO, sus Objetos o su cierre va por campos.py como cualquier
tabla controlada; una modificacion (valor o fin nuevos) es evidencia de solo
escritura y la escribe solo `apuntar_modificacion`, con la foto de la fila en
su evento, como una nota.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from . import campos
from .almacen import reloj_de, usuario_sistema
from .almacen.unidades import a_cent
from .auditoria import registrar
from .campos import Automatico, Leido, Persona
from .dominio import (
    FUENTES_MANUALES,
    ClaseReferencia,
    Fuente,
    LadoOrdenCompra,
    Sentido,
    TipoFactura,
)
from .reglas.instantanea import ordenes as leer_ordenes
# Las mismas cuentas que las reglas, para quien lee una PO (consultas.py).
from .reglas.ordenes import Cargo, antes_de_cada, en_orden, prevision, situacion  # noqa: F401
from .reloj import marca

CLIENTE = LadoOrdenCompra.CLIENTE.value
PROVEEDOR = LadoOrdenCompra.PROVEEDOR.value
_PO = ClaseReferencia.PO.value
_NOTA_CREDITO = TipoFactura.NOTA_CREDITO.value


class PONoValida(ValueError):
    """Lo pedido no deja la PO en un estado que tenga sentido (otra parte, valor cero...)."""


def lado_de_sentido(sentido: str) -> str:
    """El lado de PO que consume una factura de ese sentido."""
    return CLIENTE if sentido == Sentido.SALIENTE.value else PROVEEDOR


# ------------------------------------------------------------ sincronizar

@dataclass
class Sincronizacion:
    """Lo que la pasada del motor casa antes de evaluar: (fila, PO o None)."""

    referencias: list[tuple[int, int | None]] = field(default_factory=list)
    imputaciones: list[tuple[int, int | None]] = field(default_factory=list)
    evento_id: int | None = None


def _ordenes_por_clave(conn: sqlite3.Connection) -> dict[tuple[str, int, str], int]:
    return {(lado, parte, numero): id_ for id_, lado, parte, numero in conn.execute(
        "SELECT id, lado, coalesce(cliente_id, proveedor_id), numero_norm FROM orden_compra")}


def _referencias_deseadas(conn: sqlite3.Connection, por_clave: dict[tuple[str, int, str], int],
                          ) -> tuple[dict[int, int | None], dict[int, int | None],
                                     dict[int, list[tuple[int | None, int | None]]]]:
    """La PO de cada referencia viva: la actual, la que le toca y, por factura, (linea, PO)."""
    actuales: dict[int, int | None] = {}
    deseadas: dict[int, int | None] = {}
    por_factura: dict[int, list[tuple[int | None, int | None]]] = defaultdict(list)
    for (id_, factura_id, linea_id, valor_norm, actual, sentido, cliente_id, proveedor_id,
         clase, fuente_clase) in conn.execute(
            "SELECT r.id, r.factura_id, r.linea_id, r.valor_norm, r.orden_compra_id, f.sentido, "
            "f.cliente_id, f.proveedor_id, r.clase, p.fuente "
            "FROM factura_referencia AS r JOIN factura AS f ON f.id = r.factura_id "
            "LEFT JOIN procedencia_campo AS p ON p.tabla = 'factura_referencia' "
            "AND p.fila_id = r.id AND p.campo = 'clase' "
            "WHERE r.retirada_en IS NULL ORDER BY r.id"):
        parte = cliente_id if sentido == Sentido.SALIENTE.value else proveedor_id
        po = None
        no_es_po = fuente_clase in FUENTES_MANUALES and clase != _PO
        if parte is not None and valor_norm and not no_es_po:
            po = por_clave.get((lado_de_sentido(sentido), parte, valor_norm))
        actuales[id_], deseadas[id_] = actual, po
        por_factura[factura_id].append((linea_id, po))
    return actuales, deseadas, por_factura


def _una(pos: set[int]) -> int | None:
    return next(iter(pos)) if len(pos) == 1 else None


def _po_de_imputacion(linea_id: int | None,
                      referencias: list[tuple[int | None, int | None]]) -> int | None:
    """La PO que dicen las referencias: las de su linea y, si no dicen nada, las de cabecera."""
    de_linea = {po for linea, po in referencias if linea is not None and linea == linea_id
                and po is not None}
    if de_linea:
        return _una(de_linea)
    return _una({po for linea, po in referencias if linea is None and po is not None})


def _abonados(conn: sqlite3.Connection) -> dict[int, set[int]]:
    """Por abono, las facturas que abona con una relacion confirmada (acredita o anula)."""
    salida: dict[int, set[int]] = defaultdict(set)
    for origen, destino in conn.execute(
            "SELECT origen_id, destino_id FROM factura_relacion WHERE estado = 'confirmada' "
            "AND retirada_en IS NULL AND tipo IN ('acredita', 'anula')"):
        salida[origen].add(destino)
    return salida


def sincronizar(conn: sqlite3.Connection) -> Sincronizacion:
    """Casa referencias e imputaciones con las PO registradas. Un evento, o ninguno.

    La llama cada pasada del motor (hallazgos.recalcular), despues de
    relaciones.sincronizar, en su transaccion: lo que casa es lo que las reglas
    ven en esa misma pasada. Escribe como el motor, con campos.py y fuente
    calculado; un valor que una persona puso no se pisa. Sin ninguna PO
    registrada no hace nada (ni lee las facturas).
    """
    resultado = Sincronizacion()
    if conn.execute("SELECT 1 FROM orden_compra LIMIT 1").fetchone() is None:
        return resultado
    por_clave = _ordenes_por_clave(conn)
    actuales, deseadas, refs_de = _referencias_deseadas(conn, por_clave)
    cambian_refs = sorted((r, po) for r, po in deseadas.items() if actuales[r] != po)

    filas = conn.execute(
        "SELECT i.id, i.factura_id, i.linea_id, i.orden_compra_id, f.tipo, p.fuente, "
        "json_extract(p.valor_automatico, '$') FROM factura_imputacion AS i "
        "JOIN factura AS f ON f.id = i.factura_id "
        "LEFT JOIN procedencia_campo AS p ON p.tabla = 'factura_imputacion' "
        "AND p.fila_id = i.id AND p.campo = 'orden_compra_id' "
        "WHERE i.retirada_en IS NULL ORDER BY i.id").fetchall()
    deseada: dict[int, int | None] = {}
    efectiva: dict[int, set[int | None]] = defaultdict(set)
    for id_, factura_id, linea_id, actual, _tipo, fuente, _automatico in filas:
        po = _po_de_imputacion(linea_id, refs_de.get(factura_id, []))
        deseada[id_] = po
        efectiva[factura_id].add(actual if fuente in FUENTES_MANUALES else po)
    abonados = _abonados(conn)
    for id_, factura_id, _linea, _actual, tipo, _fuente, _auto in filas:
        if tipo != _NOTA_CREDITO or factura_id not in abonados or any(
                po is not None for _l, po in refs_de.get(factura_id, ())):
            continue
        de_las_abonadas: set[int | None] = set()
        for destino in abonados[factura_id]:
            de_las_abonadas |= efectiva.get(destino, {None})
        if len(de_las_abonadas) == 1 and None not in de_las_abonadas:
            deseada[id_] = next(iter(de_las_abonadas))
    cambian_imps = []
    for id_, _factura, _linea, actual, _tipo, fuente, automatico in filas:
        po = deseada[id_]
        if fuente in FUENTES_MANUALES:
            if automatico != po:
                cambian_imps.append((id_, po))
        elif actual != po:
            cambian_imps.append((id_, po))

    if not (cambian_refs or cambian_imps):
        return resultado
    origen = Automatico(Fuente.CALCULADO.value, usuario_sistema(conn, "motor"),
                        ref="ordenes_compra")
    with campos.orden(conn, origen, tipo="ordenes_sincronizadas", tabla="factura_imputacion",
                      datos={"referencias": [list(c) for c in cambian_refs],
                             "imputaciones": [list(c) for c in cambian_imps]}) as o:
        for referencia, po in cambian_refs:
            o.fijar("factura_referencia", referencia, {"orden_compra_id": Leido(po)})
        for imputacion, po in cambian_imps:
            o.fijar("factura_imputacion", imputacion, {"orden_compra_id": Leido(po)})
    resultado.referencias, resultado.imputaciones = cambian_refs, cambian_imps
    resultado.evento_id = o.resultado.evento_id
    return resultado


# ------------------------------------------------------------ lo consumido

def cargos(conn: sqlite3.Connection, orden_compra_id: int | None = None, *,
           objeto_id: int | None = None) -> dict[int, list[Cargo]]:
    """Por PO, lo que le carga cada factura que cuenta, en el orden del §7 (como v_po_consumo).

    Con `objeto_id`, solo lo de las imputaciones de ese Objeto (lo que el
    Objeto consume de cada PO, para su vista).
    """
    condiciones, parametros = [], []
    if orden_compra_id is not None:
        condiciones.append("AND po.id = ?")
        parametros.append(orden_compra_id)
    if objeto_id is not None:
        condiciones.append("AND i.objeto_id = ?")
        parametros.append(objeto_id)
    filtro = " ".join(condiciones)
    salida: dict[int, list[Cargo]] = defaultdict(list)
    for po, factura_id, fecha, importe in conn.execute(
            "WITH abonos AS ("
            "  SELECT DISTINCT r.origen_id AS factura_id FROM factura_relacion AS r "
            "  JOIN factura AS o ON o.id = r.origen_id JOIN factura AS d ON d.id = r.destino_id "
            "  WHERE r.estado = 'confirmada' AND r.retirada_en IS NULL "
            "    AND r.tipo IN ('acredita', 'anula') AND o.anulada = 0 "
            "    AND o.fusionada_en_id IS NULL AND d.fusionada_en_id IS NULL) "
            "SELECT i.orden_compra_id, f.id, f.fecha_factura, sum(i.importe_cent) "
            "FROM v_imputacion_vigente AS i JOIN factura AS f ON f.id = i.factura_id "
            "JOIN orden_compra AS po ON po.id = i.orden_compra_id "
            "WHERE i.importe_cent IS NOT NULL "
            "  AND f.sentido = CASE po.lado WHEN 'cliente' THEN 'saliente' ELSE 'entrante' END "
            f"  AND (f.tipo = 'factura' OR f.id IN (SELECT factura_id FROM abonos)) {filtro} "
            "GROUP BY i.orden_compra_id, f.id", tuple(parametros)):
        salida[po].append(Cargo(po, factura_id, date.fromisoformat(fecha) if fecha else None,
                                importe))
    return {po: en_orden(lista) for po, lista in salida.items()}


def ordenes(conn: sqlite3.Connection) -> dict[int, Any]:
    """Las PO con su valor y su fin vigentes, por id (reglas.base.OrdenCompra)."""
    return {o.id: o for o in leer_ordenes(conn)}


# ------------------------------------------------------------ ordenes de una persona

def _parte_de(conn: sqlite3.Connection, lado: str, parte_id: int) -> None:
    tabla = "cliente" if lado == CLIENTE else "proveedor"
    if conn.execute(f"SELECT 1 FROM {tabla} WHERE id = ?", (parte_id,)).fetchone() is None:
        raise LookupError(f"no hay {tabla} {parte_id}")


def comprobar_objetos(conn: sqlite3.Connection, lado: str, parte_id: int,
                      objetos: list[int]) -> None:
    """Los Objetos existen y, en una PO de cliente, no son de otro cliente."""
    for objeto_id in objetos:
        fila = conn.execute("SELECT cliente_id, codigo FROM objeto WHERE id = ?",
                            (objeto_id,)).fetchone()
        if fila is None:
            raise LookupError(f"no hay Objeto {objeto_id}")
        if lado == CLIENTE and fila[0] is not None and fila[0] != parte_id:
            raise PONoValida(f"el Objeto {fila[1]} es de otro cliente: una PO del cliente "
                             f"{parte_id} no lo cubre")


def registrar_po(conn: sqlite3.Connection, persona: Persona, *, numero: str, lado: str,
                 parte_id: int, valor: Decimal | str | int, fecha_emision: date | None = None,
                 fecha_inicio: date | None = None, fecha_fin: date | None = None,
                 objetos: list[int] | None = None, documento_id: int | None = None,
                 datos: Mapping[str, Any] | None = None) -> tuple[int, int | None]:
    """Una PO nueva tecleada por una persona (cambiar_po), con sus Objetos. (id, evento)."""
    numero = (numero or "").strip()
    if not numero:
        raise PONoValida("una PO necesita su numero")
    if lado not in (CLIENTE, PROVEEDOR):
        raise PONoValida(f"una PO es de cliente o de proveedor, no de {lado!r}")
    _parte_de(conn, lado, parte_id)
    objetos = sorted(set(objetos or ()))
    comprobar_objetos(conn, lado, parte_id, objetos)
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise PONoValida("la PO acaba antes de empezar")
    columna = "cliente_id" if lado == CLIENTE else "proveedor_id"
    from .parsing import normalizar_referencia

    if conn.execute(f"SELECT 1 FROM orden_compra WHERE lado = ? AND {columna} = ? AND "
                    "numero_norm = ?", (lado, parte_id, normalizar_referencia(numero))
                    ).fetchone() is not None:
        raise PONoValida(f"ya hay una PO {numero} de esa parte: un valor o un fin nuevos se "
                         "apuntan como modificacion")
    with campos.orden(conn, persona, tipo="po_registrada", tabla="orden_compra",
                      datos=datos) as o:
        po = o.crear("orden_compra", {
            "numero": numero, "lado": lado, columna: parte_id, "valor_original_cent": valor,
            "fecha_emision": fecha_emision, "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin, "documento_id": documento_id})
        for objeto_id in objetos:
            o.crear("orden_compra_objeto", {"orden_compra_id": po, "objeto_id": objeto_id})
    return po, o.resultado.evento_id


def _po(conn: sqlite3.Connection, orden_compra_id: int) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM orden_compra WHERE id = ?", (orden_compra_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay orden de compra {orden_compra_id}")
    return fila


def apuntar_modificacion(conn: sqlite3.Connection, *, orden_compra_id: int, fecha: date,
                         valor_nuevo_cent: int | None, fecha_fin_nueva: date | None,
                         motivo: str, usuario_id: int, actor: int,
                         importacion_id: int | None = None, documento_id: int | None = None,
                         peticion_id: str | None = None,
                         datos: Mapping[str, Any] | None = None) -> int:
    """Apunta una modificacion de una PO. El unico escritor de orden_compra_modificacion.

    La fila entra despues de su evento (la base lo exige), con la foto en el
    evento: es evidencia, y db verificar la compara con la fila. La base
    comprueba ademas que la firme una persona con cambiar_po en ese momento.
    """
    po = _po(conn, orden_compra_id)
    motivo = (motivo or "").strip()
    if not motivo:
        raise PONoValida("una modificacion de una PO pide su motivo")
    if valor_nuevo_cent is None and fecha_fin_nueva is None:
        raise PONoValida("una modificacion cambia el valor, el fin o los dos")
    if valor_nuevo_cent is not None and valor_nuevo_cent <= 0:
        raise PONoValida("el valor nuevo de una PO es mayor que cero")
    if (fecha_fin_nueva is not None and po["fecha_inicio"]
            and fecha_fin_nueva.isoformat() < po["fecha_inicio"]):
        raise PONoValida("el fin nuevo es anterior al inicio de la PO")
    fila = {"orden_compra_id": orden_compra_id, "fecha": fecha.isoformat(),
            "valor_nuevo_cent": valor_nuevo_cent,
            "fecha_fin_nueva": fecha_fin_nueva.isoformat() if fecha_fin_nueva else None,
            "motivo": motivo, "documento_id": documento_id, "importacion_id": importacion_id,
            "usuario_id": usuario_id, "en": marca(reloj_de(conn).ahora())}
    evento = registrar(conn, tipo="po_modificada", actor=actor, usuario_id=usuario_id,
                       tabla="orden_compra", fila_id=orden_compra_id, motivo=motivo,
                       peticion_id=peticion_id, datos={**(datos or {}), "fila": fila})
    return int(conn.execute(
        "INSERT INTO orden_compra_modificacion (orden_compra_id, fecha, valor_nuevo_cent, "
        "fecha_fin_nueva, motivo, documento_id, importacion_id, usuario_id, en, evento_id) "
        "VALUES (:orden_compra_id, :fecha, :valor_nuevo_cent, :fecha_fin_nueva, :motivo, "
        ":documento_id, :importacion_id, :usuario_id, :en, :evento_id)",
        {**fila, "evento_id": evento}).lastrowid)


def modificar_po(conn: sqlite3.Connection, persona: Persona, orden_compra_id: int, *,
                 fecha: date | None, valor: Decimal | str | int | None,
                 fecha_fin: date | None, documento_id: int | None = None,
                 datos: Mapping[str, Any] | None = None) -> int:
    """Una persona apunta un valor o un fin nuevos (desde `fecha`; por defecto, hoy)."""
    valor_cent = None
    if valor is not None:
        valor_cent = a_cent(Decimal(str(valor)) if not isinstance(valor, Decimal) else valor)
    return apuntar_modificacion(
        conn, orden_compra_id=orden_compra_id, fecha=fecha or reloj_de(conn).hoy(),
        valor_nuevo_cent=valor_cent, fecha_fin_nueva=fecha_fin, motivo=persona.motivo or "",
        usuario_id=persona.usuario_id, actor=persona.usuario_id, documento_id=documento_id,
        peticion_id=persona.peticion_id, datos=datos)


def cerrar_po(conn: sqlite3.Connection, persona: Persona, orden_compra_id: int, *,
              cerrada: bool, rev: int | None = None,
              datos: Mapping[str, Any] | None = None) -> int | None:
    """Cerrar una PO (ya no se consume: P1 retiene lo que se le impute) o reabrirla."""
    _po(conn, orden_compra_id)
    resultado = campos.fijar(conn, "orden_compra", orden_compra_id, {"cerrada": cerrada},
                             persona, tipo="po_cerrada" if cerrada else "po_reabierta",
                             rev_esperada=rev, datos=datos)
    return resultado.evento_id


def cambiar_objetos(conn: sqlite3.Connection, persona: Persona, orden_compra_id: int, *,
                    anadir: list[int] = (), retirar: list[int] = (),
                    datos: Mapping[str, Any] | None = None) -> int | None:
    """Anadir o retirar Objetos cubiertos por una PO (se retiran, no se borran)."""
    po = _po(conn, orden_compra_id)
    lado = po["lado"]
    parte = po["cliente_id"] if lado == CLIENTE else po["proveedor_id"]
    comprobar_objetos(conn, lado, parte, list(anadir))
    vivos = {objeto: id_ for id_, objeto in conn.execute(
        "SELECT id, objeto_id FROM orden_compra_objeto WHERE orden_compra_id = ? "
        "AND retirada_en IS NULL", (orden_compra_id,))}
    for objeto_id in retirar:
        if objeto_id not in vivos:
            raise PONoValida(f"la PO no cubre el Objeto {objeto_id}: no hay nada que retirar")
    with campos.orden(conn, persona, tipo="po_objetos", tabla="orden_compra",
                      fila_id=orden_compra_id, datos=datos) as o:
        for objeto_id in sorted(set(anadir) - set(vivos)):
            o.crear("orden_compra_objeto", {"orden_compra_id": orden_compra_id,
                                            "objeto_id": objeto_id})
        for objeto_id in sorted(set(retirar)):
            o.retirar("orden_compra_objeto", vivos[objeto_id])
    return o.resultado.evento_id


def imputar(conn: sqlite3.Connection, persona: Persona, imputacion_id: int,
            orden_compra_id: int | None, *, rev: int | None = None,
            datos: Mapping[str, Any] | None = None) -> tuple[int | None, int]:
    """Una persona imputa una linea a una PO (o a ninguna). (evento, factura).

    Una PO del otro lado (una de cliente en una compra) o de otra parte no se
    acepta: consumiria una PO que no es suya. Con la parte de la factura sin
    resolver se acepta, y P3 la mira cuando se resuelva.
    """
    fila = conn.execute(
        "SELECT i.factura_id, i.retirada_en, f.sentido, f.cliente_id, f.proveedor_id "
        "FROM factura_imputacion AS i JOIN factura AS f ON f.id = i.factura_id "
        "WHERE i.id = ?", (imputacion_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay imputacion {imputacion_id}")
    if fila["retirada_en"] is not None:
        raise PONoValida(f"la imputacion {imputacion_id} esta retirada")
    if orden_compra_id is not None:
        po = _po(conn, orden_compra_id)
        lado = lado_de_sentido(fila["sentido"])
        parte = fila["cliente_id"] if lado == CLIENTE else fila["proveedor_id"]
        po_parte = po["cliente_id"] if po["lado"] == CLIENTE else po["proveedor_id"]
        if po["lado"] != lado:
            raise PONoValida(f"la PO {po['numero']} es de {po['lado']}: no la consume una "
                             f"factura {fila['sentido']}")
        if parte is not None and po_parte != parte:
            raise PONoValida(f"la PO {po['numero']} es de otra parte")
    resultado = campos.fijar(conn, "factura_imputacion", imputacion_id,
                             {"orden_compra_id": orden_compra_id}, persona,
                             tipo="po_imputada", rev_esperada=rev, datos=datos)
    return resultado.evento_id, int(fila["factura_id"])
