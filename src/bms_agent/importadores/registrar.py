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
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .. import campos, cuentas, identidad
from ..almacen import Almacen, reloj_de, transaccion, usuario_sistema
from ..almacen.documentos import registrar_documento
from ..almacen.evidencia import foto
from ..almacen.unidades import json_canonico
from ..auditoria import registrar
from ..campos import Automatico, Leido
from ..dominio import Fuente, Permiso
from ..permisos import exigir, orden_auditada
from ..reloj import ZONA_EMPRESA, marca
from .base import ATOMICOS, LoteLeido, Rechazo
from .tabular import LectorTabular, Mapeo, cargar_mapeo, elegir_mapeo, lectores

# Lo que cambia como se resuelven las facturas: despues de importarlo se
# vuelven a resolver proveedor, cliente, Objeto y recurso.
RESUELVEN = frozenset({"proveedores", "clientes", "objetos", "recursos", "alias"})
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

    @property
    def origen(self) -> Automatico:
        return Automatico(Fuente.IMPORTACION.value, self.actor,
                          ref=f"importacion:{self.importacion_id}", usuario_id=self.persona,
                          en_nombre_de=self.lote.fuente if self.lote.fuente in SISTEMAS else None)

    def orden(self, fila: int, tabla: str):
        return campos.orden(self.conn, self.origen, tipo="maestro_importado", tabla=tabla,
                            datos={"importacion_id": self.importacion_id, "fila": fila})

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
             "unidad": (registro.unidad or "").strip().lower() or None,
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


ESCRITORES = {
    "proveedores": lambda ctx, r: _parte(ctx, r, "proveedor"),
    "clientes": lambda ctx, r: _parte(ctx, r, "cliente"),
    "contactos": _contacto, "objetos": _objeto, "recursos": _recurso, "alias": _alias, "tarifas": _tarifa,
    "ciclos": _ciclo,
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
               nombre: str | None, tipo_mime: str) -> ResultadoLote:
    conn = almacen.conn
    resultado = ResultadoLote(lote.fuente, lote.tipo, lote.formato,
                              filas_leidas=lote.filas_leidas)
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
    ctx = _Contexto(conn, lote, resultado.importacion_id, persona, actor, resultado)
    rechazos = list(lote.rechazos)
    if lote.tipo == "cuentas":
        propios = _cuentas(ctx)
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
    elif aceptadas and lote.tipo not in ATOMICOS:
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
               "fila": foto(conn, "importacion", resultado.importacion_id)})
    return resultado


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
                   nombre: str | None = None, tipo_mime: str = "text/csv") -> ResultadoLote:
    """Lleva un lote al almacen (ver el docstring del modulo). El unico escritor.

    `lanzado_por` es la persona, con importar_datos. `contenido` son los
    bytes del fichero, que se guardan como documento (no al simular).
    Repetir el mismo fichero devuelve la importacion que ya hubo.
    """
    conn = almacen.conn
    with orden_auditada(conn):
        exigir(conn, lanzado_por, Permiso.IMPORTAR_DATOS.value,
               accion=f"importar {lote.fuente}/{lote.tipo}")
        _exportado_no_futuro(conn, lote)
        previa = importacion_previa(conn, lote)
        if previa is not None:
            return ResultadoLote(lote.fuente, lote.tipo, lote.formato,
                                 importacion_id=int(previa["id"]), estado=previa["estado"],
                                 repetida=True, filas_leidas=lote.filas_leidas)
        if not simular:
            return _registrar(almacen, lote, lanzado_por, contenido, nombre, tipo_mime)
        try:
            with transaccion(conn):
                raise _Simulacion(_registrar(almacen, lote, lanzado_por, None, nombre,
                                             tipo_mime))
        except _Simulacion as simulacion:
            return replace(simulacion.resultado, simulada=True)


def importar_fichero(almacen: Almacen, fuente: str, tipo: str, ruta: str | Path, *,
                     lanzado_por: int, mapeo: str | Path | Mapeo | None = None,
                     exportado_en: datetime | None = None,
                     simular: bool = False) -> ResultadoImportacion:
    """La orden entera: elegir el mapeo, leer, registrar cada lote y recalcular, todo o nada.

    Un fichero de acreedores de Exact da dos lotes (proveedores y sus
    cuentas), en el orden del mapeo; cada uno es su importacion, y las
    cuentas entran o no enteras sin deshacer los proveedores. Al final se
    vuelven a resolver las facturas y se recalculan las reglas, en la misma
    transaccion. Simulando, se hace todo y se deshace.
    """
    from ..hallazgos import recalcular

    ruta = Path(ruta)
    contenido = ruta.read_bytes()
    if isinstance(mapeo, Mapeo):
        elegido = mapeo
    elif mapeo is not None:
        elegido = cargar_mapeo(mapeo)
    else:
        elegido = elegir_mapeo(fuente, tipo, contenido, ruta.name)
    if (elegido.fuente, elegido.tipo) != (fuente, tipo):
        raise ValueError(f"el mapeo {elegido.id} es de {elegido.fuente}/{elegido.tipo}, no de "
                         f"{fuente}/{tipo}")
    if not LectorTabular(elegido, elegido.registros[0].tipo).reconoce(contenido, ruta.name):
        raise ValueError(f"{ruta.name} no tiene las columnas del mapeo {elegido.id}")
    lotes = [lector.leer(contenido, ruta.name, exportado_en=exportado_en)
             for lector in lectores(elegido)]
    resultado = ResultadoImportacion(fichero=ruta.name, mapeo=elegido.id, simulada=simular)
    conn = almacen.conn

    def hacer() -> ResultadoImportacion:
        for lote in lotes:
            resultado.lotes.append(registrar_lote(
                almacen, lote, lanzado_por=lanzado_por, nombre=ruta.name,
                contenido=None if simular else contenido, tipo_mime=elegido.tipo_mime))
        nuevas = [r for r in resultado.lotes if not r.repetida]
        if nuevas and elegido.texto:
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
        if not simular:
            return hacer()
        try:
            with transaccion(conn):
                raise _Simulacion(hacer())
        except _Simulacion:
            for lote in resultado.lotes:
                lote.simulada = True
            return resultado
