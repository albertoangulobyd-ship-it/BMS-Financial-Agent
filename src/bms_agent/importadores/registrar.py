"""registrar_lote: lo unico que escribe lo que trae una importacion de maestros (spec §9).

Un lector (tabular.py) da un LoteLeido sin escribir nada; esto lo lleva al
almacen con las mismas garantias para toda fuente:

- **Repetir no hace nada.** Una importacion es unica por fuente, tipo y hash
  del fichero: el mismo fichero otra vez devuelve la que ya hubo.
- **Todo o nada donde un fichero a medias miente** (decision 6): las cuentas
  bancarias entran enteras o no entra ninguna. El resto de los maestros
  entra fila a fila, y lo rechazado queda en la importacion (Z2).
- **Procedencia.** Cada valor entra por campos.py con fuente importacion y la
  referencia importacion:N. Un valor que una persona puso a mano no se pisa:
  el de la importacion queda como valor automatico y el campo sin resolver
  (M1). Un campo que es de Exact o de TRNSPRNT solo lo escribe la
  importacion de ese sistema.
- **La foto completa.** Lo que un sistema ya no trae en su foto completa
  queda retirado: la cuenta, con un evento ausente_en_*; el proveedor o el
  cliente, inactivo (nunca borrado), y solo si la foto entro entera.
- **Nada se crea solo.** Una referencia que no se encuentra (un cliente, un
  Objeto, un proveedor) rechaza la fila; la coincidencia es exacta (numero
  de Exact, btw-id, KvK o alias confirmado), nunca por parecido.
- **Las cuentas, solo por su sitio.** Un IBAN entra como una fila de
  cuenta_bancaria y un evento visto_en_* (cuentas.py); la importacion nunca
  escribe un estado decidido (verificada, atestada): ni el modelo canonico
  tiene ese campo ni la base lo admite del importador.
- **Quien.** La ejecuta el usuario de sistema importador, la lanza una
  persona con importar_datos, y quedan los dos.
- **Simular.** Con `simular` se hace entera y se deshace: dice lo que seria
  nuevo, cambiaria o se rechazaria, sin escribir nada.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .. import campos, cuentas, identidad, ordenes_compra
from ..almacen import Almacen, reloj_de, transaccion, usuario_sistema
from ..almacen.documentos import registrar_documento
from ..almacen.evidencia import foto
from ..almacen.unidades import (
    FueraDeRango,
    PerdidaDePrecision,
    a_cent,
    a_e4,
    a_mil,
    de_cent,
    json_canonico,
    sha256_texto,
)
from ..auditoria import registrar
from ..campos import Automatico, Leido
from ..dominio import Fuente, Permiso
from ..parsing import normalizar_unidad
from ..permisos import exigir, orden_auditada
from ..reloj import ZONA_EMPRESA, marca, semana_iso
from . import planning as planning_
from .base import ATOMICOS, LoteLeido, Rechazo
from .tabular import LectorTabular, Mapeo, cargar_mapeo, elegir_mapeo, lectores

# Lo que cambia como se resuelven las facturas: despues de importarlo se
# vuelven a resolver proveedor, cliente, contacto, Objeto y recurso.
RESUELVEN = frozenset({"proveedores", "clientes", "contactos", "objetos", "recursos", "alias"})
SISTEMAS = ("exact", "trnsprnt")
_ORIGEN_DOCUMENTO = {"exact": "exact", "trnsprnt": "trnsprnt", "banco": "banco"}
_RUTA_DOCUMENTO = {"extracto": "banco", "planning": "planning"}


class RechazoFila(ValueError):
    def __init__(self, motivo: str, codigo: str = "fila") -> None:
        super().__init__(motivo)
        self.codigo = codigo


@dataclass
class ResultadoLote:
    """Lo que hizo (o haria, simulando) una importacion."""

    fuente: str
    tipo: str
    formato: str
    importacion_id: int | None = None
    estado: str | None = None
    repetida: bool = False
    simulada: bool = False
    filas_leidas: int = 0
    aceptadas: int = 0
    rechazos: list[Rechazo] = field(default_factory=list)
    nuevos: list[tuple[str, int]] = field(default_factory=list)
    cambiados: list[tuple[str, int, str]] = field(default_factory=list)
    sin_resolver: list[tuple[str, int, str]] = field(default_factory=list)
    cuentas: list[cuentas.ResultadoMaestro] = field(default_factory=list)
    retirados: list[tuple[str, int]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    evento_id: int | None = None


@dataclass
class ResultadoImportacion:
    """Lo que hizo una orden de importar un fichero: un lote por tipo, y su pasada."""

    fichero: str
    mapeo: str
    lotes: list[ResultadoLote] = field(default_factory=list)
    referencias: int = 0
    recalculo: Any = None
    simulada: bool = False


class _Simulacion(Exception):
    def __init__(self, resultado: Any) -> None:
        super().__init__("simulacion")
        self.resultado = resultado


@dataclass
class _Contexto:
    conn: sqlite3.Connection
    lote: LoteLeido
    importacion_id: int
    persona: int
    actor: int
    resultado: ResultadoLote
    confirmar: bool = False
    # Lo que dice Exact de cada factura de un fichero de pagos, tambien cero (K8).
    exact_pagado: dict[int, int] = field(default_factory=dict)

    @property
    def origen(self) -> Automatico:
        return Automatico(Fuente.IMPORTACION.value, self.actor,
                          ref=f"importacion:{self.importacion_id}", usuario_id=self.persona,
                          en_nombre_de=self.lote.fuente if self.lote.fuente in SISTEMAS else None)

    def orden(self, fila: int, tabla: str):
        return campos.orden(self.conn, self.origen, tipo="maestro_importado", tabla=tabla,
                            datos={"importacion_id": self.importacion_id, "fila": fila})

    def marca(self) -> tuple[int, int, int]:
        """Cuanto lleva anotado: para olvidar lo de una transaccion que se deshace."""
        r = self.resultado
        return len(r.nuevos), len(r.cambiados), len(r.sin_resolver)

    def olvidar_desde(self, marca: tuple[int, int, int]) -> None:
        """Olvida lo anotado desde `marca`: la transaccion que lo escribio se deshizo."""
        r = self.resultado
        del r.nuevos[marca[0]:], r.cambiados[marca[1]:], r.sin_resolver[marca[2]:]

    def anotar(self, resultado: campos.ResultadoOrden) -> None:
        self.resultado.nuevos.extend(resultado.creadas)
        creadas = set(resultado.creadas)
        for e in resultado.efectos:
            if e.accion == "cambiado" and (e.tabla, e.fila_id) not in creadas:
                self.resultado.cambiados.append((e.tabla, e.fila_id, e.campo))
            elif e.accion == "solo_automatico" and e.discrepancia:
                self.resultado.sin_resolver.append((e.tabla, e.fila_id, e.campo))


# ------------------------------------------------------------ referencias

def _unica(conn: sqlite3.Connection, sql: str, parametros: tuple) -> int | None:
    filas = conn.execute(sql, parametros).fetchall()
    return int(filas[0][0]) if len(filas) == 1 else None


def referencia_parte(conn: sqlite3.Connection, tabla: str, ref: str) -> int:
    """La fila de un proveedor o un cliente que nombra un fichero: por su numero de Exact o de
    TRNSPRNT, o por btw-id, KvK o alias confirmado. Exacta; si no, RechazoFila."""
    texto = str(ref).strip()
    for columna in ("exact_id", "trnsprnt_id"):
        fila_id = _unica(conn, f"SELECT id FROM {tabla} WHERE {columna} = ?", (texto,))
        if fila_id is not None:
            return fila_id
    r = identidad.resolver_parte(conn, tabla, btw=texto, kvk=texto if tabla == "proveedor"
                                 else None, nombre=texto)
    if r.fila_id is not None:
        return r.fila_id
    if r.ambigua:
        raise RechazoFila(f"{tabla} {texto!r} es ambiguo ({r.motivo})", "referencia")
    raise RechazoFila(f"no hay ningun {tabla} {texto!r}: no se crea solo", "referencia")


def referencia_objeto(conn: sqlite3.Connection, ref: str) -> int:
    r = identidad.resolver_objeto(conn, ref)
    if r.fila_id is None:
        raise RechazoFila(f"no hay ningun Objeto {ref!r}: no se crea solo", "referencia")
    return r.fila_id


def referencia_recurso(conn: sqlite3.Connection, ref: str) -> int:
    r = identidad.resolver_recurso(conn, ref)
    if r.fila_id is None:
        raise RechazoFila(f"no hay ningun recurso {ref!r}: no se crea solo", "referencia")
    return r.fila_id


# ------------------------------------------------------------ escritores fila a fila

def _alias_del_nombre(ctx: _Contexto, o: campos.Orden, tabla: str, fila_id: int,
                      nombre: str) -> None:
    """El nombre que da el maestro reconoce su fila (como el alias de la semilla de tarifas)."""
    try:
        _norma, existente = identidad.comprobar_alias(ctx.conn, tabla, nombre, fila_id)
    except ValueError as exc:
        ctx.resultado.cambiados.append((tabla, fila_id, f"alias no anadido: {exc}"))
        return
    if existente is None:
        o.crear("alias", {"tabla": tabla, "alias": nombre.strip(), "fila_id": fila_id,
                          "origen": "maestro", "confirmado": True})


def _parte(ctx: _Contexto, registro: Any, tabla: str) -> None:
    """Un proveedor o un cliente: por su numero del sistema, o adoptando el que ya se conoce."""
    conn, fuente = ctx.conn, ctx.lote.fuente
    columna = f"{fuente}_id" if fuente in SISTEMAS else None
    fila_id = None
    if columna and registro.id_externo:
        fila_id = _unica(conn, f"SELECT id FROM {tabla} WHERE {columna} = ?",
                         (registro.id_externo,))
    if fila_id is None:
        r = identidad.resolver_parte(conn, tabla, btw=registro.btw_id,
                                     kvk=registro.kvk if tabla == "proveedor" else None,
                                     nombre=registro.nombre)
        if r.ambigua:
            raise RechazoFila(f"coincide con varios {tabla}: {r.motivo}", "referencia")
        if r.fila_id is not None:
            otro = conn.execute(f"SELECT {columna} FROM {tabla} WHERE id = ?",
                                (r.fila_id,)).fetchone()[0] if columna else None
            if otro is None:
                fila_id = r.fila_id               # el mismo, todavia sin numero de este sistema
    excluir = {"fila", "crudo", "id_externo"}
    valores = {k: v for k, v in registro.model_dump().items() if k not in excluir}
    if columna and registro.id_externo:
        valores[columna] = registro.id_externo
    with ctx.orden(registro.fila, tabla) as o:
        if fila_id is None:
            fila_id = o.crear(tabla, valores)
        else:
            o.fijar(tabla, fila_id, valores)
        _alias_del_nombre(ctx, o, tabla, fila_id, registro.nombre)
    ctx.anotar(o.resultado)


def _contacto(ctx: _Contexto, registro: Any) -> None:
    """Un contacto, por su proveedor o cliente y su nombre (sin distinguir mayusculas)."""
    conn = ctx.conn
    parte_id = referencia_parte(conn, registro.titular, registro.parte_ref)
    columna = f"{registro.titular}_id"
    fila_id = _unica(conn, f"SELECT id FROM contacto WHERE {columna} = ? "
                           "AND lower(trim(nombre)) = lower(trim(?))", (parte_id, registro.nombre))
    valores = {"email": registro.email, "telefono": registro.telefono,
               "funcion": registro.funcion, "activo": registro.activo}
    with ctx.orden(registro.fila, "contacto") as o:
        if fila_id is None:
            o.crear("contacto", {columna: parte_id, "nombre": registro.nombre.strip(), **valores})
        else:
            o.fijar("contacto", fila_id, valores)
    ctx.anotar(o.resultado)


def _objeto(ctx: _Contexto, registro: Any) -> None:
    conn = ctx.conn
    cliente_id = (referencia_parte(conn, "cliente", registro.cliente_ref)
                  if registro.cliente_ref else None)
    fila_id = _unica(conn, "SELECT id FROM objeto WHERE codigo = ?", (registro.codigo,))
    if fila_id is None:
        r = identidad.resolver_objeto(conn, registro.codigo)
        if r.ambigua:
            raise RechazoFila(f"el codigo {registro.codigo!r} es de varios Objetos",
                              "referencia")
        fila_id = r.fila_id
    valores = {"nombre": registro.nombre, "cliente_id": cliente_id,
               "requiere_po": registro.requiere_po, "activo_desde": registro.activo_desde,
               "activo_hasta": registro.activo_hasta}
    with ctx.orden(registro.fila, "objeto") as o:
        if fila_id is None:
            o.crear("objeto", {"codigo": registro.codigo, **valores})
        else:
            o.fijar("objeto", fila_id, valores)
    ctx.anotar(o.resultado)


def _recurso(ctx: _Contexto, registro: Any) -> None:
    conn = ctx.conn
    proveedor_id = (referencia_parte(conn, "proveedor", registro.proveedor_ref)
                    if registro.proveedor_ref else None)
    fila_id = identidad.resolver_recurso(conn, registro.nombre).fila_id
    valores = {"nombre": registro.nombre, "tipo": registro.tipo, "proveedor_id": proveedor_id,
               "activo": registro.activo}
    with ctx.orden(registro.fila, "recurso") as o:
        if fila_id is None:
            fila_id = o.crear("recurso", valores)
            _alias_del_nombre(ctx, o, "recurso", fila_id, registro.nombre)
        else:
            o.fijar("recurso", fila_id, valores)
    ctx.anotar(o.resultado)


def _alias(ctx: _Contexto, registro: Any) -> None:
    conn = ctx.conn
    if registro.tabla in ("proveedor", "cliente"):
        destino = referencia_parte(conn, registro.tabla, registro.destino_ref)
    elif registro.tabla == "objeto":
        destino = referencia_objeto(conn, registro.destino_ref)
    else:
        destino = referencia_recurso(conn, registro.destino_ref)
    _norma, existente = identidad.comprobar_alias(conn, registro.tabla, registro.alias, destino)
    if existente is not None:
        return
    with ctx.orden(registro.fila, "alias") as o:
        o.crear("alias", {"tabla": registro.tabla, "alias": registro.alias.strip(),
                          "fila_id": destino, "origen": "maestro", "confirmado": True})
    ctx.anotar(o.resultado)


_EUROS = (None, "", "EUR", "EURO", "EUROS", "€")


def _tarifa(ctx: _Contexto, registro: Any) -> None:
    """Una tarifa pactada, por su clave natural: sentido, a quien, donde, trabajo y desde."""
    conn = ctx.conn
    if (registro.moneda or "").strip().upper() not in _EUROS:
        raise RechazoFila(f"la tarifa esta en {registro.moneda}: lo que no esta en euros no "
                          "entra", "X1")
    ids = {
        "proveedor_id": referencia_parte(conn, "proveedor", registro.proveedor_ref)
        if registro.proveedor_ref else None,
        "recurso_id": referencia_recurso(conn, registro.recurso_ref)
        if registro.recurso_ref else None,
        "cliente_id": referencia_parte(conn, "cliente", registro.cliente_ref)
        if registro.cliente_ref else None,
        "objeto_id": referencia_objeto(conn, registro.objeto_ref) if registro.objeto_ref
        else None,
    }
    if registro.sentido == "venta" and ids["proveedor_id"] is not None:
        raise RechazoFila("una tarifa de venta no es de un proveedor")
    if registro.sentido == "compra" and ids["cliente_id"] is not None:
        raise RechazoFila("una tarifa de compra no es de un cliente")
    clave = {**ids, "tipo_servicio": (registro.tipo_servicio or "").strip().lower() or None,
             "tipo_turno": (registro.tipo_turno or "").strip().lower() or None,
             "unidad": normalizar_unidad(registro.unidad),
             "vigente_desde": registro.vigente_desde.isoformat() if registro.vigente_desde
             else None}
    condicion = " AND ".join(f"{c} IS ?" for c in clave)
    fila_id = _unica(conn, f"SELECT id FROM tarifa_acordada WHERE sentido = ? AND fuente = "
                           f"'maestro' AND {condicion}", (registro.sentido, *clave.values()))
    tarifa = Leido(registro.tarifa, crudo=registro.tarifa_crudo)
    with ctx.orden(registro.fila, "tarifa_acordada") as o:
        if fila_id is None:
            o.crear("tarifa_acordada", {**clave, "sentido": registro.sentido,
                                        "tarifa_e4": tarifa, "fuente": "maestro",
                                        "vigente_hasta": registro.vigente_hasta})
        else:
            o.fijar("tarifa_acordada", fila_id, {"tarifa_e4": tarifa,
                                                 "vigente_hasta": registro.vigente_hasta})
    ctx.anotar(o.resultado)


def _ciclo(ctx: _Contexto, registro: Any) -> None:
    conn = ctx.conn
    cliente_id = (referencia_parte(conn, "cliente", registro.cliente_ref)
                  if registro.cliente_ref else None)
    objeto_id = referencia_objeto(conn, registro.objeto_ref) if registro.objeto_ref else None
    if cliente_id is None and objeto_id is None:
        raise RechazoFila("un ciclo de facturacion es de un cliente o de un Objeto")
    desde = registro.vigente_desde.isoformat() if registro.vigente_desde else None
    fila_id = _unica(conn, "SELECT id FROM ciclo_facturacion WHERE cliente_id IS ? AND "
                           "objeto_id IS ? AND vigente_desde IS ?", (cliente_id, objeto_id, desde))
    valores = {"frecuencia": registro.frecuencia, "ancla": registro.ancla,
               "dias_gracia": registro.dias_gracia, "vigente_hasta": registro.vigente_hasta}
    with ctx.orden(registro.fila, "ciclo_facturacion") as o:
        if fila_id is None:
            o.crear("ciclo_facturacion", {"cliente_id": cliente_id, "objeto_id": objeto_id,
                                          "vigente_desde": registro.vigente_desde, **valores})
        else:
            o.fijar("ciclo_facturacion", fila_id, valores)
    ctx.anotar(o.resultado)


# ------------------------------------------------------------ ordenes de compra (paso 9)

# La hoja de PO la teclea una persona que ademas de importar puede cambiar PO.
PIDEN_CAMBIAR_PO = frozenset({"ordenes_compra", "modificaciones_po"})


def _en_euros(moneda: str | None, que: str) -> None:
    if (moneda or "").strip().upper() not in _EUROS:
        raise RechazoFila(f"{que} esta en {moneda}: lo que no esta en euros no entra", "X1")


def _parte_de_po(conn: sqlite3.Connection, registro: Any) -> tuple[str, int]:
    """La columna de la parte (cliente_id o proveedor_id) y su fila, como la nombra la hoja."""
    tabla = "cliente" if registro.lado == "cliente" else "proveedor"
    return f"{tabla}_id", referencia_parte(conn, tabla, registro.parte_ref)


def _po_existente(conn: sqlite3.Connection, registro: Any, columna: str,
                  parte: int) -> int | None:
    from ..parsing import normalizar_referencia

    return _unica(conn, f"SELECT id FROM orden_compra WHERE lado = ? AND {columna} = ? AND "
                        "numero_norm = ?", (registro.lado, parte,
                                            normalizar_referencia(registro.numero)))


def _orden_compra(ctx: _Contexto, registro: Any) -> None:
    """Una PO de la hoja: nueva, o la misma otra vez (con sus Objetos nuevos anadidos).

    El valor y el fin originales no cambian: una fila que trae otros para una
    PO que ya esta se rechaza y pide la modificacion, que es su propia fila y
    deja rastro de quien, cuando y por que. Un Objeto que la hoja ya no trae
    no se retira (no es una foto completa).
    """
    from ..parsing import normalizar_referencia

    conn = ctx.conn
    _en_euros(registro.moneda, "la PO")
    if normalizar_referencia(registro.numero) is None:
        raise RechazoFila(f"{registro.numero!r} no es un numero de PO: solo tiene separadores")
    columna, parte = _parte_de_po(conn, registro)
    objetos = sorted({referencia_objeto(conn, ref) for ref in registro.objetos_ref})
    try:
        ordenes_compra.comprobar_objetos(conn, registro.lado, parte, objetos)
    except ordenes_compra.PONoValida as exc:
        raise RechazoFila(str(exc), "referencia") from None
    if registro.fecha_inicio and registro.fecha_fin and registro.fecha_inicio > registro.fecha_fin:
        raise RechazoFila("la PO acaba antes de empezar")
    fila_id = _po_existente(conn, registro, columna, parte)
    vivos: set[int] = set()
    if fila_id is not None:
        valor, fin = conn.execute("SELECT valor_original_cent, fecha_fin FROM orden_compra "
                                  "WHERE id = ?", (fila_id,)).fetchone()
        nuevo_fin = registro.fecha_fin.isoformat() if registro.fecha_fin else None
        if valor != a_cent(registro.valor) or fin != nuevo_fin:
            raise RechazoFila(f"la PO {registro.numero} ya esta registrada con otro valor o "
                              "otro fin originales: lo que cambia se apunta como modificacion "
                              "(su propia fila, con su motivo)")
        vivos = {f[0] for f in conn.execute(
            "SELECT objeto_id FROM orden_compra_objeto WHERE orden_compra_id = ? "
            "AND retirada_en IS NULL", (fila_id,))}
    with ctx.orden(registro.fila, "orden_compra") as o:
        valores = {"fecha_emision": registro.fecha_emision,
                   "fecha_inicio": registro.fecha_inicio, "cerrada": registro.cerrada}
        if fila_id is None:
            fila_id = o.crear("orden_compra", {
                "numero": registro.numero.strip(), "lado": registro.lado, columna: parte,
                "valor_original_cent": Leido(registro.valor, crudo=registro.valor_crudo),
                "fecha_fin": registro.fecha_fin, "fuente": "po_csv", **valores})
        else:
            o.fijar("orden_compra", fila_id, valores)
        for objeto_id in objetos:
            if objeto_id not in vivos:
                o.crear("orden_compra_objeto", {"orden_compra_id": fila_id,
                                                "objeto_id": objeto_id})
    ctx.anotar(o.resultado)


def _modificacion_po(ctx: _Contexto, registro: Any) -> None:
    """Una modificacion de la hoja, de una PO que ya esta. La misma otra vez no se apunta."""
    conn = ctx.conn
    if registro.valor_nuevo is not None:
        _en_euros(registro.moneda, "el valor nuevo")
    columna, parte = _parte_de_po(conn, registro)
    po = _po_existente(conn, registro, columna, parte)
    if po is None:
        raise RechazoFila(f"no hay ninguna PO {registro.numero} de esa parte: la PO entra antes "
                          "que sus modificaciones", "referencia")
    try:
        valor = a_cent(registro.valor_nuevo) if registro.valor_nuevo is not None else None
    except (PerdidaDePrecision, FueraDeRango) as exc:
        raise RechazoFila(f"el valor nuevo no es un importe en centimos: {exc}") from None
    fin = registro.fecha_fin_nueva.isoformat() if registro.fecha_fin_nueva else None
    if conn.execute(
            "SELECT 1 FROM orden_compra_modificacion WHERE orden_compra_id = ? AND fecha = ? "
            "AND valor_nuevo_cent IS ? AND fecha_fin_nueva IS ? AND motivo = ?",
            (po, registro.fecha.isoformat(), valor, fin, registro.motivo.strip())).fetchone():
        ctx.resultado.avisos.append(f"fila {registro.fila}: la modificacion de la PO "
                                    f"{registro.numero} ya estaba apuntada")
        return
    try:
        modificacion = ordenes_compra.apuntar_modificacion(
            conn, orden_compra_id=po, fecha=registro.fecha, valor_nuevo_cent=valor,
            fecha_fin_nueva=registro.fecha_fin_nueva, motivo=registro.motivo,
            usuario_id=ctx.persona, actor=ctx.actor, importacion_id=ctx.importacion_id,
            datos={"importacion_id": ctx.importacion_id, "fila_importada": registro.fila})
    except ordenes_compra.PONoValida as exc:
        raise RechazoFila(str(exc)) from None
    ctx.resultado.nuevos.append(("orden_compra_modificacion", modificacion))


ESCRITORES = {
    "proveedores": lambda ctx, r: _parte(ctx, r, "proveedor"),
    "clientes": lambda ctx, r: _parte(ctx, r, "cliente"),
    "contactos": _contacto, "objetos": _objeto, "recursos": _recurso, "alias": _alias,
    "tarifas": _tarifa, "ciclos": _ciclo, "ordenes_compra": _orden_compra,
    "modificaciones_po": _modificacion_po,
}


# ------------------------------------------------------------ las cuentas, todo o nada

def _cuentas(ctx: _Contexto) -> list[Rechazo]:
    """Las cuentas de un maestro: si una fila no vale, no entra ninguna."""
    lote, conn = ctx.lote, ctx.conn
    if lote.fuente not in SISTEMAS:
        return [Rechazo(0, f"las cuentas llegan del maestro de Exact o de TRNSPRNT, no de "
                           f"{lote.fuente}")]
    if not lote.completo:
        return [Rechazo(0, "un fichero de cuentas tiene que ser la foto entera del maestro: lo "
                           "que no trae cuenta como retirado")]
    rechazos: list[Rechazo] = []
    por_titular: dict[str, list[tuple[int, str, str | None]]] = defaultdict(list)
    for registro in lote.registros:
        columna = f"{lote.fuente}_id"
        parte_id = _unica(conn, f"SELECT id FROM {registro.titular} WHERE {columna} = ?",
                          (registro.parte_ref,))
        if parte_id is None:
            rechazos.append(Rechazo(registro.fila, f"no hay ningun {registro.titular} con el "
                                                   f"numero {registro.parte_ref!r} de "
                                                   f"{lote.fuente}: la cuenta no entra",
                                    dict(registro.crudo), "referencia"))
            continue
        por_titular[registro.titular].append((parte_id, registro.iban, registro.nombre_titular))
    if rechazos or lote.rechazos:
        return rechazos
    for titular, presentes in sorted(por_titular.items()):
        ctx.resultado.cuentas.append(cuentas.apuntar_maestro(
            conn, importacion_id=ctx.importacion_id, fuente=lote.fuente, titular=titular,
            presentes=presentes, usuario_id=ctx.persona))
    return []


# ------------------------------------------------------------ los extractos del banco (paso 7)

def huella_movimiento(cuenta: str, m: Any, ocurrencia: int) -> str:
    """La huella de un movimiento: lo que dice el banco de el y cuantos identicos van antes.

    La posicion entre filas identicas del mismo fichero entra en la huella:
    dos comisiones iguales del mismo dia son dos movimientos, y el mismo
    fichero (o otro que repite el mismo dia) no las mete dos veces.
    """
    return sha256_texto(json_canonico([
        cuenta, m.fecha_contable.isoformat(),
        m.fecha_valor.isoformat() if m.fecha_valor else None, str(m.importe), m.importe_crudo,
        m.moneda,
        m.contraparte_iban, m.contraparte_nombre, m.concepto, m.referencia_estructurada,
        m.referencia_e2e, m.ref_banco, m.remesa, ocurrencia]))


def _extractos(ctx: _Contexto) -> list[Rechazo]:
    """Los extractos de un fichero del banco: todos o ninguno.

    La cuenta de cada extracto tiene que ser de BM Support BV
    (config/empresa.yaml, cuentas_propias): un extracto de otra cuenta rechaza
    el fichero entero. Un extracto que ya estaba (misma cuenta, secuencia,
    fechas y saldos) no se vuelve a dar de alta, y un movimiento cuya huella
    ya esta no entra otra vez.
    """
    from .. import politica

    lote, conn = ctx.lote, ctx.conn
    if lote.fuente != "banco":
        return [Rechazo(0, f"un extracto llega del banco, no de {lote.fuente}")]
    if lote.rechazos:
        return []
    propias = set(politica.empresa(conn).cuentas_propias)
    if not propias:
        return [Rechazo(0, "config/empresa.yaml no tiene cuentas propias: no se sabe si el "
                           "extracto es de BM Support BV", None, "cuenta_ajena")]
    ajenas = [Rechazo(e.fila, f"la cuenta {e.cuenta_propia_iban} no es de BM Support BV "
                              "(config/empresa.yaml): el fichero no entra", dict(e.crudo),
                      "cuenta_ajena")
              for e in lote.registros if e.cuenta_propia_iban not in propias]
    if ajenas:
        return ajenas
    preparados = []
    vistos: dict[str, int] = defaultdict(int)
    posicion = 0
    try:
        for extracto in lote.registros:
            filas = []
            for m in extracto.movimientos:
                posicion += 1
                clave = huella_movimiento(extracto.cuenta_propia_iban, m, 0)
                vistos[clave] += 1
                importe = a_cent(m.importe) if m.moneda == "EUR" else None
                filas.append((posicion, m, importe,
                              huella_movimiento(extracto.cuenta_propia_iban, m, vistos[clave])))
            preparados.append((extracto, filas,
                               a_cent(extracto.saldo_inicial) if extracto.saldo_inicial is not None
                               else None,
                               a_cent(extracto.saldo_final) if extracto.saldo_final is not None
                               else None))
    except (PerdidaDePrecision, FueraDeRango) as exc:
        return [Rechazo(0, f"un importe no cabe en centimos: {exc}")]
    actor = ctx.actor
    for extracto, filas, inicial, final in preparados:
        existente = conn.execute(
            "SELECT id FROM extracto_bancario WHERE cuenta_propia_iban = ? AND secuencia IS ? "
            "AND desde IS ? AND hasta IS ? AND saldo_inicial_cent IS ? AND saldo_final_cent IS ? "
            "AND con_saldos = ?",
            (extracto.cuenta_propia_iban, extracto.secuencia,
             extracto.desde.isoformat() if extracto.desde else None,
             extracto.hasta.isoformat() if extracto.hasta else None, inicial, final,
             int(extracto.con_saldos))).fetchone()
        huellas = [h for *_resto, h in filas]
        ya = set()
        for inicio in range(0, len(huellas), 500):
            trozo = huellas[inicio:inicio + 500]
            ya.update(f[0] for f in conn.execute(
                f"SELECT huella FROM movimiento_bancario WHERE huella IN "
                f"({', '.join('?' * len(trozo))})", trozo))
        nuevas = [f for f in filas if f[3] not in ya]
        if existente is not None and not nuevas:
            ctx.resultado.avisos.append(
                f"el extracto {extracto.identificador or extracto.fila} de "
                f"{extracto.cuenta_propia_iban} ya estaba (extracto {existente[0]}): no entra "
                "otra vez")
            continue
        extracto_id = int(conn.execute(
            "INSERT INTO extracto_bancario (importacion_id, cuenta_propia_iban, identificador, "
            "secuencia, moneda, saldo_inicial_cent, saldo_final_cent, fecha_saldo_inicial, "
            "fecha_saldo_final, desde, hasta, con_saldos, entradas, formato) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ctx.importacion_id, extracto.cuenta_propia_iban, extracto.identificador,
             extracto.secuencia, extracto.moneda, inicial, final,
             extracto.fecha_saldo_inicial.isoformat() if extracto.fecha_saldo_inicial else None,
             extracto.fecha_saldo_final.isoformat() if extracto.fecha_saldo_final else None,
             extracto.desde.isoformat() if extracto.desde else None,
             extracto.hasta.isoformat() if extracto.hasta else None, int(extracto.con_saldos),
             len(filas), extracto.formato)).lastrowid)
        ctx.resultado.nuevos.append(("extracto_bancario", extracto_id))
        fotos = {}
        for posicion_, m, importe, huella in nuevas:
            movimiento_id = int(conn.execute(
                "INSERT INTO movimiento_bancario (importacion_id, extracto_id, cuenta_propia_iban, "
                "posicion, fecha_contable, fecha_valor, importe_cent, importe_crudo, moneda, "
                "contraparte_iban, contraparte_nombre_doc, concepto_doc, referencia_estructurada, "
                "referencia_e2e, ref_banco, remesa, huella) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ctx.importacion_id, extracto_id, extracto.cuenta_propia_iban, posicion_,
                 m.fecha_contable.isoformat(),
                 m.fecha_valor.isoformat() if m.fecha_valor else None, importe, m.importe_crudo,
                 m.moneda, m.contraparte_iban, m.contraparte_nombre, m.concepto,
                 m.referencia_estructurada, m.referencia_e2e, m.ref_banco, m.remesa,
                 huella)).lastrowid)
            fotos[str(movimiento_id)] = foto(conn, "movimiento_bancario", movimiento_id)
            ctx.resultado.nuevos.append(("movimiento_bancario", movimiento_id))
        if len(nuevas) < len(filas):
            ctx.resultado.avisos.append(
                f"{len(filas) - len(nuevas)} movimiento(s) del extracto "
                f"{extracto.identificador or extracto.fila} ya estaban: no entran otra vez")
        registrar(conn, tipo="extracto_registrado", actor=actor, usuario_id=ctx.persona,
                  tabla="extracto_bancario", fila_id=extracto_id,
                  datos={"importacion_id": ctx.importacion_id,
                         "repetidos": len(filas) - len(nuevas),
                         "fila": foto(conn, "extracto_bancario", extracto_id),
                         "movimientos": fotos})
    return []


# ------------------------------------------------------------ el planning de TRNSPRNT (paso 10)

_REF_PLANNING = (("objeto", "objeto_ref"), ("recurso", "recurso_ref"),
                 ("proveedor", "proveedor_ref"), ("cliente", "cliente_ref"))


def _mil_o_nada(valor: Decimal | None) -> int | None:
    return None if valor is None else a_mil(valor)


def _e4_o_nada(valor: Decimal | None) -> int | None:
    return None if valor is None else a_e4(valor)


def _planning(ctx: _Contexto) -> list[Rechazo]:
    """Una foto del planning: todos sus turnos o ninguno (decision 6).

    Lo que no se lee (una fecha, unas horas que no caben en milesimas, una
    tarifa en otra moneda) rechaza el fichero entero: medio planning daria por
    no trabajado o no facturado lo que si lo esta. Lo que nombra cada turno
    (Objeto, persona, proveedor, cliente) se busca en el maestro por
    coincidencia exacta (instantanea.Resolutor) y, si no esta, entra con su
    texto y sin resolver: no se crea nada, y lo dice Z2. Todos los turnos van
    en un evento, planning_registrado, con la foto de cada uno.
    """
    from ..reglas.instantanea import Resolutor

    lote, conn = ctx.lote, ctx.conn
    if lote.fuente != "trnsprnt":
        return [Rechazo(0, f"el planning llega de TRNSPRNT, no de {lote.fuente}")]
    if lote.rechazos:
        return []
    riesgos, desaparecen = _riesgos_del_planning(conn, lote)
    ctx.resultado.avisos.extend(f"confirmado: {r}" for r in riesgos)
    if desaparecen:
        ctx.resultado.avisos.append(f"{desaparecen} turno(s) del planning que valia dejan de "
                                    "valer: esta foto cubre sus dias y no los trae")
    resolutor = Resolutor(conn)
    filas = []
    for posicion, t in enumerate(lote.registros, start=1):
        if (t.moneda or "").strip().upper() not in _EUROS:
            return [Rechazo(t.fila, f"las tarifas del turno estan en {t.moneda}, no en euros: "
                                    "el fichero no entra", dict(t.crudo), "X1")]
        try:
            horas = [_mil_o_nada(getattr(t, h)) for h in ("horas_planificadas",
                                                         "horas_realizadas", "horas_aprobadas")]
            tarifas_ = (_e4_o_nada(t.tarifa_compra), _e4_o_nada(t.tarifa_venta))
        except (PerdidaDePrecision, FueraDeRango) as exc:
            return [Rechazo(t.fila, f"un valor del turno no cabe: {exc}", dict(t.crudo))]
        ids = {que: resolutor.resolver(que, getattr(t, campo)) for que, campo in _REF_PLANNING}
        filas.append((posicion, t, horas, tarifas_, ids))
    fotos: dict[str, dict[str, Any]] = {}
    sin_resolver: dict[str, int] = defaultdict(int)
    for posicion, t, horas, (compra, venta), ids in filas:
        for que, campo in _REF_PLANNING:
            if ids[que] is None and getattr(t, campo):
                sin_resolver[que] += 1
        turno_id = int(conn.execute(
            "INSERT INTO planning_turno (importacion_id, posicion, id_externo, clave_fragil, "
            "nivel, fecha, semana_iso, dias, hora_inicio, hora_fin, pausa_min, "
            "horas_planificadas_mil, horas_realizadas_mil, horas_aprobadas_mil, estado, "
            "objeto_ref_doc, recurso_ref_doc, proveedor_ref_doc, cliente_ref_doc, po_ref_doc, "
            "objeto_id, recurso_id, proveedor_id, cliente_id, tipo_servicio, tipo_turno, "
            "facturable, tarifa_compra_e4, tarifa_venta_e4, datos_origen_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?)",
            (ctx.importacion_id, posicion, t.id_externo, int(t.clave_fragil), t.nivel,
             t.dia.isoformat(), semana_iso(t.dia), t.dias, t.hora_inicio, t.hora_fin,
             t.pausa_min, *horas, t.estado, t.objeto_ref, t.recurso_ref, t.proveedor_ref,
             t.cliente_ref, t.po_ref, ids["objeto"], ids["recurso"], ids["proveedor"],
             ids["cliente"], t.tipo_servicio, t.tipo_turno,
             None if t.facturable is None else int(t.facturable), compra, venta,
             json_canonico(dict(t.crudo)))).lastrowid)
        fotos[str(turno_id)] = foto(conn, "planning_turno", turno_id)
        ctx.resultado.nuevos.append(("planning_turno", turno_id))
    for que, cuantos in sorted(sin_resolver.items()):
        ctx.resultado.avisos.append(f"{cuantos} turno(s) nombran un {que} que no esta en el "
                                    "maestro: entran sin resolver (Z2)")
    registrar(conn, tipo="planning_registrado", actor=ctx.actor, usuario_id=ctx.persona,
              tabla="importacion", fila_id=ctx.importacion_id,
              datos={"importacion_id": ctx.importacion_id, "turnos": fotos,
                     "sin_resolver": dict(sorted(sin_resolver.items())),
                     "dejan_de_valer": desaparecen, "riesgos": riesgos,
                     "confirmado": ctx.confirmar})
    return []


def _riesgos_del_planning(conn: sqlite3.Connection, lote: LoteLeido) -> tuple[list[str], int]:
    """Lo que hace que una foto del planning pida confirmacion (planning_.riesgos), y cuantos
    turnos del planning que vale ahora deja sin valer sin traerlos.

    Los que deja sin valer son los turnos (no cancelados) de v_turno_vigente
    cuyos dias cubre y de importaciones que no son mas nuevas que ella (la que
    entra es la ultima, y a igual fecha de exportacion gana), como en la vista.
    """
    if lote.cubre_desde is None or lote.cubre_hasta is None:
        return planning_.riesgos(lote, 0, 0), 0
    cuando = marca(lote.exportado_en) if lote.exportado_en else marca(reloj_de(conn).ahora())
    traidos = {t.id_externo for t in lote.registros}
    cubiertos = [id_externo for (id_externo,) in conn.execute(
        "SELECT v.id_externo FROM v_turno_vigente AS v "
        "JOIN importacion AS i ON i.id = v.importacion_id "
        "WHERE i.fuente = ? AND v.estado <> 'cancelado' "
        "AND ? <= CASE v.nivel WHEN 'semana' THEN date(v.fecha, '+6 days') ELSE v.fecha END "
        "AND ? >= v.fecha AND ? >= coalesce(i.exportado_en, i.iniciada_en)",
        (lote.fuente, lote.cubre_desde.isoformat(), lote.cubre_hasta.isoformat(), cuando))]
    desaparecen = sum(1 for id_externo in cubiertos if id_externo not in traidos)
    return planning_.riesgos(lote, len(cubiertos), desaparecen), desaparecen


def _confirmar_planning(conn: sqlite3.Connection, lote: LoteLeido, confirmar: bool) -> None:
    """Una foto del planning que borraria mucho del de ahora no se importa sin confirmarla.

    Se para antes de escribir nada (como una fecha de exportacion futura): un
    fichero rechazado queda apuntado con su hash y no se podria volver a
    importar con --confirmar.
    """
    if confirmar or lote.tipo != planning_.TIPO or lote.rechazos:
        return
    riesgos, _desaparecen = _riesgos_del_planning(conn, lote)
    if riesgos:
        raise planning_.PideConfirmacion(
            "; ".join(riesgos) + ". Si es lo que se quiere, se importa con --confirmar.")


# ------------------------------------------------------------ lo pagado segun Exact (paso 7)

def _factura_de_exact(conn: sqlite3.Connection, registro: Any) -> int:
    """La factura que nombra una fila de Exact: por el numero de Exact de su parte y su numero."""
    from ..parsing import normalizar_referencia

    tabla, columna, sentido = (("proveedor", "proveedor_id", "entrante")
                               if registro.sentido == "compra"
                               else ("cliente", "cliente_id", "saliente"))
    partes = [f[0] for f in conn.execute(f"SELECT id FROM {tabla} WHERE exact_id = ?",
                                         (registro.parte_ref.strip(),))]
    if not partes:
        raise RechazoFila(f"no hay ningun {tabla} con el numero {registro.parte_ref!r} de Exact",
                          "referencia")
    numero = normalizar_referencia(registro.numero)
    facturas = [f[0] for f in conn.execute(
        f"SELECT id FROM factura WHERE sentido = ? AND numero_norm = ? AND {columna} IN "
        f"({', '.join('?' * len(partes))}) AND fusionada_en_id IS NULL ORDER BY id",
        (sentido, numero, *partes))]
    if len(facturas) != 1:
        raise RechazoFila(f"la factura {registro.numero} de {tabla} {registro.parte_ref} "
                          + ("no esta en el almacen" if not facturas else "esta repetida")
                          + ": su pago no se aplica", "referencia")
    return facturas[0]


def _pagado_segun_exact(conn: sqlite3.Connection, registro: Any, factura_id: int) -> Decimal:
    if registro.importe_pagado is not None:
        return registro.importe_pagado
    if registro.importe_abierto is None:
        raise RechazoFila("la fila no dice ni lo pagado ni lo abierto")
    if registro.importe_factura is not None:
        return registro.importe_factura - registro.importe_abierto
    total = conn.execute("SELECT total_cent FROM factura WHERE id = ?", (factura_id,)).fetchone()[0]
    if total is None:
        raise RechazoFila("la factura no tiene total en euros: no se sabe lo pagado")
    return de_cent(total) - registro.importe_abierto


def _pagos_exact(ctx: _Contexto) -> tuple[list[Rechazo], int]:
    """Lo que Exact dice que se ha pagado de cada factura, como aplicaciones de fuente exact.

    Una fila que no se lee, o un importe en otra moneda, rechaza el fichero
    entero (decision 6: un fichero de pagos a medias da estados falsos). Una
    fila de una factura que aqui no esta no se aplica y queda como rechazo
    (Z2); las demas si: a una factura que no esta no se le puede dar ningun
    estado falso. Si Exact dice otro importe que la ultima vez, la aplicacion
    de antes se retira y se escribe otra.

    Un pago de cero no es una aplicacion, pero es lo que dice Exact: lo de
    cada factura (tambien cero) va en el evento de la importacion
    (`exact_pagado`, con el dia de la foto), y K8 lo compara con el banco.
    """
    lote, conn = ctx.lote, ctx.conn
    if lote.fuente != "exact":
        return [Rechazo(0, f"lo pagado segun Exact llega de Exact, no de {lote.fuente}")], 0
    if lote.rechazos:
        return [], 0
    otras = [Rechazo(r.fila, f"esta en {r.moneda}: lo que no esta en euros no entra",
                     dict(r.crudo), "X1")
             for r in lote.registros if (r.moneda or "").strip().upper() not in _EUROS]
    if otras:
        return otras, 0
    rechazos: list[Rechazo] = []
    aceptadas = 0
    fecha_lote = (lote.exportado_en.astimezone(ZoneInfo(ZONA_EMPRESA)).date()
                  if lote.exportado_en else reloj_de(conn).hoy())
    for registro in lote.registros:
        try:
            with transaccion(conn):
                factura_id = _factura_de_exact(conn, registro)
                pagado = _pagado_segun_exact(conn, registro, factura_id)
                ctx.exact_pagado[factura_id] = a_cent(pagado)
                actuales = conn.execute(
                    "SELECT id, importe_cent FROM aplicacion_pago WHERE factura_id = ? "
                    "AND fuente = 'exact' AND estado = 'confirmada' ORDER BY id",
                    (factura_id,)).fetchall()
                if sum(f[1] for f in actuales) != a_cent(pagado):
                    with campos.orden(conn, ctx.origen, tipo="pagos_exact_importados",
                                      tabla="aplicacion_pago", factura_id=factura_id,
                                      datos={"importacion_id": ctx.importacion_id,
                                             "fila": registro.fila}) as o:
                        for fila in actuales:
                            o.retirar("aplicacion_pago", fila[0])
                        if pagado != 0:
                            o.crear("aplicacion_pago", {
                                "factura_id": factura_id, "importacion_id": ctx.importacion_id,
                                "importe_cent": pagado,
                                "fecha_pago": registro.fecha_pago or fecha_lote,
                                "fuente": "exact", "metodo": "automatica",
                                "regla": "exact: pagado" if registro.importe_pagado is not None
                                else "exact: factura menos lo abierto"})
                    ctx.anotar(o.resultado)
        except RechazoFila as exc:
            rechazos.append(Rechazo(registro.fila, str(exc), dict(registro.crudo), exc.codigo))
        except (PerdidaDePrecision, FueraDeRango) as exc:
            rechazos.append(Rechazo(registro.fila, str(exc), dict(registro.crudo)))
        else:
            aceptadas += 1
    return rechazos, aceptadas


# ------------------------------------------------------------ las facturas de venta (paso 8)

def _plazo_de(condiciones: str | None) -> int | None:
    """Los dias del plazo que da el texto de Exact ("30 dagen"), si se leen sin adivinar."""
    from ..parsing import ParseError, parse_plazo_pago

    try:
        return parse_plazo_pago(condiciones) if condiciones else None
    except ParseError:
        return None


def _cabecera_venta(registro: Any, cliente_id: int) -> dict[str, Any]:
    """Lo que la importacion escribe de la factura: lo que dice Exact, con su literal."""
    unico = registro.iva_por_tipo[0].tipo_iva if len(registro.iva_por_tipo) == 1 else None
    return {
        "tipo": registro.tipo, "numero": registro.numero, "cliente_id": cliente_id,
        "receptor_nombre_doc": registro.cliente_nombre, "receptor_btw_doc": registro.cliente_btw,
        "contacto_nombre_doc": registro.contacto, "fecha_factura": registro.fecha_factura,
        "fecha_vencimiento": registro.fecha_vencimiento,
        "condiciones_pago_doc": registro.condiciones_pago,
        "plazo_pago_dias": _plazo_de(registro.condiciones_pago),
        "periodo_inicio": registro.periodo_inicio, "periodo_fin": registro.periodo_fin,
        "base_cent": Leido(registro.base, crudo=registro.base_crudo),
        "iva_cent": Leido(registro.iva, crudo=registro.iva_crudo),
        "total_cent": Leido(registro.total, crudo=registro.total_crudo),
        "tipo_iva_pb": unico, "tratamiento_iva": registro.tratamiento_iva,
        "moneda_doc": "EUR",
    }


def _valores_linea(linea: Any) -> dict[str, Any]:
    return {
        "descripcion_doc": linea.descripcion, "objeto_doc": linea.objeto_ref,
        "recurso_doc": linea.recurso_ref, "unidad_doc": linea.unidad,
        "fecha_inicio": linea.fecha_inicio, "fecha_fin": linea.fecha_fin,
        "cantidad_mil": Leido(linea.cantidad, crudo=linea.cantidad_crudo),
        "tarifa_e4": Leido(linea.tarifa, crudo=linea.tarifa_crudo),
        "importe_cent": Leido(linea.importe, crudo=linea.importe_crudo),
        "tipo_iva_pb": linea.tipo_iva,
    }


def _vivas(conn: sqlite3.Connection, tabla: str, factura_id: int) -> list[sqlite3.Row]:
    return conn.execute(f"SELECT * FROM {tabla} WHERE factura_id = ? AND retirada_en IS NULL "
                        "ORDER BY id", (factura_id,)).fetchall()


def _lineas_venta(o: campos.Orden, conn: sqlite3.Connection, factura_id: int,
                  registro: Any) -> dict[int, int]:
    """Las lineas por su numero de linea de Exact: la que sigue se actualiza, la nueva entra con
    su imputacion por defecto y la que ya no viene se retira (con su imputacion)."""
    actuales = {f["orden"]: f["id"] for f in _vivas(conn, "factura_linea", factura_id)}
    retiradas = {f["orden"]: f["id"] for f in conn.execute(
        "SELECT id, orden FROM factura_linea WHERE factura_id = ? AND retirada_en IS NOT NULL",
        (factura_id,))}
    ids = {}
    for linea in registro.lineas:
        valores = _valores_linea(linea)
        if linea.orden in actuales:
            ids[linea.orden] = actuales.pop(linea.orden)
            o.fijar("factura_linea", ids[linea.orden], valores)
            continue
        if linea.orden in retiradas:
            raise RechazoFila(f"la linea {linea.orden} de la factura {registro.numero} ya se "
                              "retiro: Exact no vuelve a usar un numero de linea", "fila")
        ids[linea.orden] = o.crear("factura_linea", {"factura_id": factura_id,
                                                     "orden": linea.orden, **valores})
        o.crear("factura_imputacion", {"factura_id": factura_id,
                                       "linea_id": ids[linea.orden]})
    for linea_id in actuales.values():
        o.retirar("factura_linea", linea_id)
    return ids


def _hijas_venta(o: campos.Orden, conn: sqlite3.Connection, factura_id: int, registro: Any,
                 lineas: dict[int, int]) -> None:
    """Las PO, el IVA por tipo y la factura citada, por lo que las identifica."""
    from ..parsing import normalizar_referencia

    querido = {(None, normalizar_referencia(r)): (None, r) for r in registro.referencias}
    for linea in registro.lineas:
        if linea.po_ref:
            querido[(lineas[linea.orden], normalizar_referencia(linea.po_ref))] = (
                lineas[linea.orden], linea.po_ref)
    for fila in _vivas(conn, "factura_referencia", factura_id):
        if querido.pop((fila["linea_id"], fila["valor_norm"]), None) is None:
            o.retirar("factura_referencia", fila["id"])
    for linea_id, valor in querido.values():
        o.crear("factura_referencia", {"factura_id": factura_id, "linea_id": linea_id,
                                       "etiqueta_doc": "PO", "valor_doc": valor})

    tipos = {iva.tipo_iva: iva for iva in registro.iva_por_tipo}
    for fila in _vivas(conn, "factura_iva", factura_id):
        tipo = Decimal(fila["tipo_iva_pb"]) / 100 if fila["tipo_iva_pb"] is not None else None
        iva = tipos.pop(tipo, None)
        if iva is None:
            o.retirar("factura_iva", fila["id"])
        else:
            o.fijar("factura_iva", fila["id"], {"tratamiento": registro.tratamiento_iva,
                                                "base_cent": iva.base,
                                                "cuota_cent": iva.cuota})
    for iva in tipos.values():
        o.crear("factura_iva", {"factura_id": factura_id, "tipo_iva_pb": iva.tipo_iva,
                                "tratamiento": registro.tratamiento_iva,
                                "base_cent": iva.base, "cuota_cent": iva.cuota})

    citada = registro.factura_relacionada
    relacion = "credits" if registro.tipo == "nota_credito" else "unknown"
    citas = _vivas(conn, "factura_cita", factura_id)
    for fila in citas:
        if citada and fila["numero_norm"] == normalizar_referencia(citada):
            o.fijar("factura_cita", fila["id"], {"relacion_doc": relacion})
            citada = None
        else:
            o.retirar("factura_cita", fila["id"])
    if citada:
        o.crear("factura_cita", {"factura_id": factura_id, "numero_doc": citada,
                                 "relacion_doc": relacion,
                                 "texto_doc": f"Gerelateerde factuur {citada}"})


def _comprobar_venta(conn: sqlite3.Connection, registro: Any) -> int:
    """El cliente de la factura y lo que no puede entrar. Devuelve el cliente; no escribe."""
    if (registro.moneda or "").strip().upper() not in _EUROS:
        raise RechazoFila(f"la factura {registro.numero} esta en {registro.moneda}: lo que no "
                          "esta en euros no entra", "X1")
    for importe in (registro.base, registro.iva, registro.total,
                    *(linea.importe for linea in registro.lineas)):
        if importe is not None:
            a_cent(importe)
    return referencia_parte(conn, "cliente", registro.cliente_ref)


def _facturas_venta(ctx: _Contexto) -> list[Rechazo]:
    """Las facturas de venta de un listado de Exact: todas o ninguna (decision 6).

    Primero se comprueba todo (moneda, importes, cliente) sin escribir; si
    algo no vale, no entra ninguna. Despues cada factura es una orden de
    campos.py, a nombre de Exact: la factura por su diario y numero de Exact
    (la que ya estaba se actualiza), sus lineas por su numero de linea, con
    su imputacion por defecto (el Objeto lo resuelve el codigo del centro de
    coste o el proyecto; si no se conoce, la linea queda sin Objeto como una
    leida de un PDF), sus PO, su IVA por tipo y la factura que cita (de la
    que relaciones.py propone la relacion: nunca la confirma una
    importacion). Nada de esto crea una factura en Exact ni un borrador: la
    V1 solo lee lo que Exact ya emitio.
    """
    lote, conn = ctx.lote, ctx.conn
    if lote.fuente not in SISTEMAS:
        return [Rechazo(0, f"las facturas de venta llegan de Exact o de TRNSPRNT, no de "
                           f"{lote.fuente}")]
    if lote.rechazos:
        return []
    rechazos: list[Rechazo] = []
    clientes: dict[int, int] = {}
    for registro in lote.registros:
        try:
            clientes[registro.fila] = _comprobar_venta(conn, registro)
        except RechazoFila as exc:
            rechazos.append(Rechazo(registro.fila, str(exc), dict(registro.crudo), exc.codigo))
        except (PerdidaDePrecision, FueraDeRango) as exc:
            rechazos.append(Rechazo(registro.fila, f"un importe no cabe en centimos: {exc}",
                                    dict(registro.crudo)))
    if rechazos:
        return rechazos
    # Si una factura no entra se deshacen todas: lo anotado de las anteriores
    # tampoco entro, y el evento de la importacion no lo cuenta como nuevo.
    marca = ctx.marca()
    try:
        with transaccion(conn):
            for registro in lote.registros:
                _factura_venta(ctx, registro, clientes[registro.fila])
    except RechazoFila as exc:
        ctx.olvidar_desde(marca)
        return [Rechazo(0, str(exc), None, exc.codigo)]
    except (ValueError, LookupError, TypeError, sqlite3.IntegrityError) as exc:
        ctx.olvidar_desde(marca)
        codigo = "sistema" if isinstance(exc, campos.CampoDeOtroSistema) else "fila"
        return [Rechazo(0, f"no entra ninguna factura: {exc}", None, codigo)]
    return []


def _factura_venta(ctx: _Contexto, registro: Any, cliente_id: int) -> None:
    conn, fuente = ctx.conn, ctx.lote.fuente
    fila_id = _unica(conn, "SELECT id FROM factura WHERE fuente_externa = ? AND id_externo = ?",
                     (fuente, registro.id_externo))
    cabecera = _cabecera_venta(registro, cliente_id)
    with campos.orden(conn, ctx.origen, tipo="factura_importada", tabla="factura",
                      fila_id=fila_id, factura_id=fila_id,
                      datos={"importacion_id": ctx.importacion_id, "fila": registro.fila,
                             "id_externo": registro.id_externo}) as o:
        if fila_id is None:
            fila_id = o.crear("factura", {
                "sentido": "saliente", "origen": fuente, "fuente_externa": fuente,
                "id_externo": registro.id_externo, **cabecera})
            o.tabla, o.fila_id, o.factura_id = "factura", fila_id, fila_id
        else:
            sentido = conn.execute("SELECT sentido FROM factura WHERE id = ?",
                                   (fila_id,)).fetchone()[0]
            if sentido != "saliente":
                raise RechazoFila(f"{registro.id_externo} es una factura de compra aqui", "fila")
            o.fijar("factura", fila_id, cabecera)
        lineas = _lineas_venta(o, conn, fila_id, registro)
        _hijas_venta(o, conn, fila_id, registro, lineas)
    ctx.anotar(o.resultado)


# ------------------------------------------------------------ la foto completa de un sistema

_PARTES = {"proveedores": "proveedor", "clientes": "cliente"}


def _retirar_ausentes(ctx: _Contexto, rechazos: list[Rechazo]) -> None:
    """Un proveedor o cliente que el sistema ya no trae en su foto completa queda inactivo.

    Solo los de ese sistema (con su numero) y solo si la foto entro entera:
    una fila rechazada puede ser justo la de uno que si esta, y darlo por
    retirado seria inventar. No se borra nada: activo pasa a falso, con la
    procedencia de esta importacion, y vuelve a verdadero si reaparece.
    """
    lote, conn = ctx.lote, ctx.conn
    tabla = _PARTES.get(lote.tipo)
    if tabla is None or not lote.completo or lote.fuente not in SISTEMAS:
        return
    if rechazos:
        ctx.resultado.avisos.append(
            f"con {len(rechazos)} fila(s) rechazada(s) no se retira a nadie: la foto no esta entera")
        return
    columna = f"{lote.fuente}_id"
    presentes = {r.id_externo for r in lote.registros if r.id_externo}
    for fila_id, externo in conn.execute(
            f"SELECT id, {columna} FROM {tabla} WHERE {columna} IS NOT NULL AND activo = 1 "
            "ORDER BY id").fetchall():
        if externo in presentes:
            continue
        with transaccion(conn):
            with ctx.orden(0, tabla) as o:
                o.fijar(tabla, fila_id, {"activo": False})
        ctx.anotar(o.resultado)
        ctx.resultado.retirados.append((tabla, fila_id))


# ------------------------------------------------------------ registrar_lote

def importacion_previa(conn: sqlite3.Connection, lote: LoteLeido) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, estado FROM importacion WHERE fuente = ? AND tipo = ? AND fichero_sha256 = ?",
        (lote.fuente, lote.tipo, lote.fichero_sha256)).fetchone()


def _registrar(almacen: Almacen, lote: LoteLeido, persona: int, contenido: bytes | None,
               nombre: str | None, tipo_mime: str, confirmar: bool = False) -> ResultadoLote:
    conn = almacen.conn
    resultado = ResultadoLote(lote.fuente, lote.tipo, lote.formato,
                              filas_leidas=lote.filas_leidas, avisos=list(lote.avisos))
    actor = usuario_sistema(conn, "importador")
    ahora = marca(reloj_de(conn).ahora())
    documento_id = None
    if contenido is not None:
        documento_id = registrar_documento(
            almacen, sha256=lote.fichero_sha256, contenido=contenido, nombre_original=nombre,
            tipo_mime=tipo_mime, origen=_ORIGEN_DOCUMENTO.get(lote.fuente, "manual"),
            ruta_declarada=_RUTA_DOCUMENTO.get(lote.tipo, "maestro"), recibido_en=ahora,
            recibido_fuente="ingesta", actor=actor, usuario_id=persona).id
    resultado.importacion_id = int(conn.execute(
        "INSERT INTO importacion (fuente, tipo, formato, documento_id, fichero_sha256, "
        "mapeo_sha256, exportado_en, cubre_desde, cubre_hasta, completa, filas_leidas, "
        "iniciada_en, iniciada_por, actor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (lote.fuente, lote.tipo, lote.formato, documento_id, lote.fichero_sha256,
         lote.mapeo_sha256, marca(lote.exportado_en) if lote.exportado_en else None,
         lote.cubre_desde.isoformat() if lote.cubre_desde else None,
         lote.cubre_hasta.isoformat() if lote.cubre_hasta else None, int(lote.completo),
         lote.filas_leidas, ahora, persona, actor)).lastrowid)
    ctx = _Contexto(conn, lote, resultado.importacion_id, persona, actor, resultado, confirmar)
    rechazos = list(lote.rechazos)
    if lote.tipo == "cuentas":
        propios = _cuentas(ctx)
        rechazos.extend(propios)
        aceptadas = 0 if (propios or lote.rechazos) else len(lote.registros)
    elif lote.tipo == "extracto":
        propios = _extractos(ctx)
        rechazos.extend(propios)
        aceptadas = 0 if (propios or lote.rechazos) else len(lote.registros)
    elif lote.tipo == "pagos_exact":
        propios, aceptadas = _pagos_exact(ctx)
        rechazos.extend(propios)
    elif lote.tipo == "facturas_venta":
        propios = _facturas_venta(ctx)
        rechazos.extend(propios)
        aceptadas = 0 if (propios or lote.rechazos) else len(lote.registros)
    elif lote.tipo == "planning":
        propios = _planning(ctx)
        rechazos.extend(propios)
        aceptadas = 0 if (propios or lote.rechazos) else len(lote.registros)
    elif lote.tipo in ATOMICOS or lote.tipo not in ESCRITORES:
        rechazos.append(Rechazo(0, f"el tipo {lote.tipo} todavia no se importa"))
        aceptadas = 0
    else:
        aceptadas = 0
        for registro in lote.registros:
            try:
                with transaccion(conn):
                    ESCRITORES[lote.tipo](ctx, registro)
            except RechazoFila as exc:
                rechazos.append(Rechazo(registro.fila, str(exc), dict(registro.crudo),
                                        exc.codigo))
            except (ValueError, LookupError, TypeError, sqlite3.IntegrityError) as exc:
                codigo = "sistema" if isinstance(exc, campos.CampoDeOtroSistema) else "fila"
                rechazos.append(Rechazo(registro.fila, str(exc), dict(registro.crudo), codigo))
            else:
                aceptadas += 1
        _retirar_ausentes(ctx, rechazos)
    rechazos.sort(key=lambda r: r.fila)
    resultado.rechazos, resultado.aceptadas = rechazos, aceptadas
    if not rechazos:
        resultado.estado = "aceptada"
    elif aceptadas and (lote.tipo not in ATOMICOS or lote.tipo == "pagos_exact"):
        # Lo pagado segun Exact entra salvo las filas de facturas que aqui no
        # estan (ver _pagos_exact); lo que no se lee lo rechaza entero.
        resultado.estado = "parcial"
    else:
        resultado.estado = "rechazada"
    conn.execute(
        "UPDATE importacion SET estado = ?, filas_aceptadas = ?, filas_rechazadas = ?, "
        "rechazos_json = ?, terminada_en = ? WHERE id = ?",
        (resultado.estado, aceptadas, len(rechazos),
         json_canonico([r.a_dict() for r in rechazos]) if rechazos else None,
         marca(reloj_de(conn).ahora()), resultado.importacion_id))
    resultado.evento_id = registrar(
        conn, tipo="importacion", actor=actor, usuario_id=persona,
        resultado="ok" if resultado.estado != "rechazada" else "error",
        tabla="importacion", fila_id=resultado.importacion_id,
        datos={"fichero": nombre, "mapeo": lote.mapeo_id, "estado": resultado.estado,
               "nuevos": len(resultado.nuevos), "cambiados": len(resultado.cambiados),
               "sin_resolver": len(resultado.sin_resolver),
               "fila": foto(conn, "importacion", resultado.importacion_id),
               **_lo_que_dice_exact(ctx)})
    return resultado


def _lo_que_dice_exact(ctx: _Contexto) -> dict[str, Any]:
    """Para el evento de un fichero de pagos de Exact: lo pagado de cada factura y de que dia."""
    if ctx.lote.tipo != "pagos_exact" or not ctx.exact_pagado:
        return {}
    lote = ctx.lote
    fecha = (lote.exportado_en.astimezone(ZoneInfo(ZONA_EMPRESA)).date()
             if lote.exportado_en else reloj_de(ctx.conn).hoy())
    return {"exact_pagado": sorted([f, c] for f, c in ctx.exact_pagado.items()),
            "exact_fecha": fecha.isoformat()}


def _exportado_no_futuro(conn: sqlite3.Connection, lote: LoteLeido) -> None:
    """Un fichero no se saca de su sistema despues de importarlo.

    exportado_en mide la frescura (Z1): una fecha futura (una errata en
    --exportado, la fecha de un fichero copiado) haria que la fuente no
    caducase nunca y que A2, E1, F2 y F3 siguieran dando ok contra un maestro
    de cualquier edad. Se compara por dia en la zona de la empresa.
    """
    if lote.exportado_en is None:
        return
    reloj = reloj_de(conn)
    dia = lote.exportado_en.astimezone(ZoneInfo(ZONA_EMPRESA)).date()
    if dia > reloj.hoy():
        raise ValueError(f"el fichero dice estar exportado el {dia.isoformat()}, en el futuro: "
                         "revisa la fecha (--exportado)")


def registrar_lote(almacen: Almacen, lote: LoteLeido, *, lanzado_por: int,
                   simular: bool = False, contenido: bytes | None = None,
                   nombre: str | None = None, tipo_mime: str = "text/csv",
                   confirmar: bool = False) -> ResultadoLote:
    """Lleva un lote al almacen (ver el docstring del modulo). El unico escritor.

    `lanzado_por` es la persona, con importar_datos. `contenido` son los
    bytes del fichero, que se guardan como documento (no al simular).
    Repetir el mismo fichero devuelve la importacion que ya hubo.
    `confirmar`: una foto del planning que borraria mucho del planning de
    ahora entra igual (importadores/planning.riesgos).
    """
    conn = almacen.conn
    with orden_auditada(conn):
        exigir(conn, lanzado_por, Permiso.IMPORTAR_DATOS.value,
               accion=f"importar {lote.fuente}/{lote.tipo}")
        if lote.tipo in PIDEN_CAMBIAR_PO:
            exigir(conn, lanzado_por, Permiso.CAMBIAR_PO.value,
                   accion=f"importar {lote.fuente}/{lote.tipo}")
        _exportado_no_futuro(conn, lote)
        previa = importacion_previa(conn, lote)
        if previa is not None:
            return ResultadoLote(lote.fuente, lote.tipo, lote.formato,
                                 importacion_id=int(previa["id"]), estado=previa["estado"],
                                 repetida=True, filas_leidas=lote.filas_leidas)
        _confirmar_planning(conn, lote, confirmar)
        if not simular:
            return _registrar(almacen, lote, lanzado_por, contenido, nombre, tipo_mime,
                              confirmar)
        try:
            with transaccion(conn):
                raise _Simulacion(_registrar(almacen, lote, lanzado_por, None, nombre,
                                             tipo_mime, confirmar))
        except _Simulacion as simulacion:
            return replace(simulacion.resultado, simulada=True)


def importar_fichero(almacen: Almacen, fuente: str, tipo: str, ruta: str | Path, *,
                     lanzado_por: int, mapeo: str | Path | Mapeo | None = None,
                     exportado_en: datetime | None = None, simular: bool = False,
                     cubre_desde: date | None = None, cubre_hasta: date | None = None,
                     confirmar: bool = False) -> ResultadoImportacion:
    """La orden entera: elegir el mapeo, leer, registrar cada lote y recalcular, todo o nada.

    Un fichero de acreedores de Exact da dos lotes (proveedores y sus
    cuentas), en el orden del mapeo; cada uno es su importacion, y las
    cuentas entran o no enteras sin deshacer los proveedores. Al final se
    vuelven a resolver las facturas y se recalculan las reglas, en la misma
    transaccion. Simulando, se hace todo y se deshace. Una foto del planning
    cubre los dias que trae, o los que se digan (`cubre_desde`, `cubre_hasta`:
    la exportacion de un periodo, aunque algun dia no tenga turnos). Una foto
    que borraria mucho del planning de ahora solo entra con `confirmar`.
    """
    from ..hallazgos import recalcular

    if (fuente, tipo) == ("banco", "extracto"):
        from .banco import importar_extracto

        formato = mapeo.id if isinstance(mapeo, Mapeo) else (str(mapeo) if mapeo else None)
        return importar_extracto(almacen, ruta, lanzado_por=lanzado_por, formato=formato,
                                 exportado_en=exportado_en, simular=simular)
    ruta = Path(ruta)
    contenido = ruta.read_bytes()
    elegido: Mapeo | None = None
    if fuente == "po_csv" and ruta.suffix.lower() in (".yaml", ".yml"):
        # La hoja de PO tecleada en YAML (importadores/ordenes.py): sin mapeo.
        from . import ordenes as yaml_po

        if mapeo is not None:
            raise ValueError("un YAML de PO no lleva mapeo: sus campos son los canonicos")
        lotes = yaml_po.lotes(contenido, tipo, exportado_en=exportado_en)
        mapeo_id, tipo_mime = yaml_po.FORMATO, "application/yaml"
    else:
        if isinstance(mapeo, Mapeo):
            elegido = mapeo
        elif mapeo is not None:
            elegido = cargar_mapeo(mapeo)
        else:
            elegido = elegir_mapeo(fuente, tipo, contenido, ruta.name)
        if (elegido.fuente, elegido.tipo) != (fuente, tipo):
            raise ValueError(f"el mapeo {elegido.id} es de {elegido.fuente}/{elegido.tipo}, no "
                             f"de {fuente}/{tipo}")
        if not LectorTabular(elegido, elegido.registros[0].tipo).reconoce(contenido, ruta.name):
            raise ValueError(f"{ruta.name} no tiene las columnas del mapeo {elegido.id}")
        lotes = [lector.leer(contenido, ruta.name, exportado_en=exportado_en)
                 for lector in lectores(elegido)]
        if tipo == "planning":
            from .planning import con_cobertura

            lotes = [con_cobertura(lote, cubre_desde, cubre_hasta) for lote in lotes]
        mapeo_id, tipo_mime = elegido.id, elegido.tipo_mime
    resultado = ResultadoImportacion(fichero=ruta.name, mapeo=mapeo_id, simulada=simular)
    conn = almacen.conn

    def hacer() -> ResultadoImportacion:
        for lote in lotes:
            resultado.lotes.append(registrar_lote(
                almacen, lote, lanzado_por=lanzado_por, nombre=ruta.name,
                contenido=None if simular else contenido, tipo_mime=tipo_mime,
                confirmar=confirmar))
        nuevas = [r for r in resultado.lotes if not r.repetida]
        if nuevas and elegido is not None and elegido.texto:
            # El mapeo aplicado queda en la politica con su texto (§5, tabla 2):
            # importacion.mapeo_sha256 apunta a el. Solo si cambio desde el ultimo.
            from .. import politica

            politica.registrar(conn, f"importacion/{elegido.id}.yaml", elegido.texto,
                               lanzado_por)
        if any(r.tipo in RESUELVEN for r in nuevas):
            resultado.referencias = identidad.reconciliar_referencias(conn)
        if nuevas:
            causa = max((r.evento_id for r in nuevas if r.evento_id), default=None)
            resultado.recalculo = recalcular(conn, motivo="importacion", usuario_id=lanzado_por,
                                             causa_evento_id=causa)
        return resultado

    with orden_auditada(conn):
        exigir(conn, lanzado_por, Permiso.IMPORTAR_DATOS.value,
               accion=f"importar {fuente}/{tipo}")
        if tipo in PIDEN_CAMBIAR_PO:
            exigir(conn, lanzado_por, Permiso.CAMBIAR_PO.value,
                   accion=f"importar {fuente}/{tipo}")
        if not simular:
            return hacer()
        try:
            with transaccion(conn):
                raise _Simulacion(hacer())
        except _Simulacion:
            for lote in resultado.lotes:
                lote.simulada = True
            return resultado
