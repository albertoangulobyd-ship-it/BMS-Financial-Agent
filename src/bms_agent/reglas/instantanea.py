"""La instantanea: lo que las reglas pueden ver, leido del almacen de una vez y congelado.

Es el unico modulo de reglas/ que toca la base. Lee las facturas tipadas con
sus valores actuales (los que dejo campos.py: lo corregido por una persona
gana a lo extraido), sus lineas e imputaciones activas, el desglose de IVA y
las relaciones confirmadas, y lo deja en tuplas de dataclasses congeladas
ordenadas por id. Lo que es derivar y no decidir tambien se hace aqui, una
vez: la contraparte como clave de agrupacion (normas.py: btw-id, KvK,
nombre normalizado, nunca el IBAN), la moneda que no es el euro, el Objeto
que nombra cada linea, y que campos traen un literal que no se pudo leer.

Desde el paso 5 lee tambien los maestros (proveedores y clientes con sus
alias confirmados), el registro de cuentas con sus eventos, la historia del
telefono de verificacion de cada proveedor y las importaciones de maestros.
Desde el paso 7, los extractos y movimientos del banco, lo pagado de cada
factura (con su vencimiento efectivo y su saldo), los beneficiarios conocidos
y los dias en que cada factura con algun pago estuvo Bloqueada. Desde el paso
8, de donde viene cada factura, lo que le acreditan los abonos confirmados y
si otra la sustituye (reglas/relaciones.efectos), las relaciones propuestas y
las facturas que nombra cada documento.
Desde el paso 9, las imputaciones y las referencias de cada factura, las
ordenes de compra con su valor y su fin vigentes, las tarifas pactadas y los
Objetos del maestro.
Desde el paso 10, el planning que vale (v_turno_vigente), con lo que nombra
cada turno resuelto contra el maestro de ahora si al importarlo no se resolvio
(`Resolutor`, por coincidencia exacta, como registrar.py), las fotos aceptadas
del planning, la conciliacion de cada imputacion con sus turnos y los ciclos
de facturacion.
Desde el paso 11, los trimestres del BTW ya presentados con lo que se declaro de
cada factura (C4).
Solo lee: lo que escribe el registro de cuentas es cuentas.py, y nada de la
via de entrada de los documentos llega alli.

Leer de golpe (una consulta por tabla, sin sqlite3.Row) es lo que permite
recalcular cinco mil facturas en menos de dos segundos.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .. import compat
from ..dominio import FUENTES_MANUALES, Sentido
from ..parsing import detectar_moneda, normalizar_referencia
from ..reloj import ZONA_EMPRESA
from .base import (
    Aplicacion,
    Bloqueo,
    CambioTelefono,
    Ciclo,
    Cita,
    Conciliacion,
    Cuenta,
    EventoCuenta,
    Extracto,
    Factura,
    FotoPlanning,
    Imputacion,
    Instantanea,
    Linea,
    LineaSinCasar,
    Lote,
    Movimiento,
    Objeto,
    OrdenCompra,
    PagadoExact,
    Parte,
    PeriodoBtw,
    Politica,
    Referencia,
    Relacion,
    Tarifa,
    TramoIva,
    Turno,
)
from .ordenes import vigentes
from .pagos import saldo, tolerancia_cent
from .relaciones import SIN_EFECTO
from .relaciones import efectos as efectos_de_relaciones
from .normas import (
    normalizar_btw,
    normalizar_iban,
    normalizar_kvk,
    normalizar_nombre,
    normalizar_telefono,
)
from .tarifas import normalizar_turno

_COLUMNAS_FACTURA = (
    "f.id", "f.sentido", "f.tipo", "f.numero", "f.numero_norm", "f.proveedor_id", "f.cliente_id",
    "f.emisor_nombre_doc", "f.emisor_kvk_doc", "f.emisor_btw_doc", "f.receptor_nombre_doc",
    "f.receptor_btw_doc", "f.fecha_factura", "f.periodo_inicio", "f.periodo_fin", "f.base_cent",
    "f.iva_cent", "f.total_cent", "f.tipo_iva_pb", "f.tratamiento_iva", "f.iban_doc",
    "f.moneda_doc", "f.anulada", "f.fusionada_en_id", "e.schema_version",
    "f.documento_id", "f.emisor_direccion_doc", "f.kor_mencionada", "f.notas_doc",
    "f.origen = 'extraccion' AND d.ruta_cas IS NULL", "f.origen",
)

_COLUMNAS_LINEA = (
    "id", "factura_id", "orden", "descripcion_doc", "objeto_doc", "unidad", "cantidad_mil",
    "tarifa_e4", "importe_cent", "tipo_iva_pb", "fecha_inicio", "fecha_fin", "fecha_trabajo",
    "semana_doc",
)

# Lo que una extraccion v1 no pidio, en columnas de factura (compat.py habla
# en claves del extractor).
_CLAVE_A_COLUMNA = {
    "recipient_name": "receptor_nombre_doc",
    "recipient_vat_number": "receptor_btw_doc",
    "recipient_contact_person": "contacto_nombre_doc",
    "payment_terms_raw": "condiciones_pago_doc",
    "currency_raw": "moneda_doc",
}


def _fecha(texto: str | None) -> date | None:
    return None if texto is None else date.fromisoformat(texto)


def _filas(conn: sqlite3.Connection, sql: str, parametros: tuple = ()) -> list[tuple]:
    cursor = conn.cursor()
    cursor.row_factory = None
    return cursor.execute(sql, parametros).fetchall()


def clave_parte(sentido: str, proveedor_id: int | None, cliente_id: int | None,
                btw: str | None, kvk: str | None, nombre: str | None) -> str | None:
    """La contraparte como clave: la fila del maestro, o lo que el documento dice de ella.

    Por este orden: la fila resuelta, el btw-id, el KvK y el nombre, todos
    normalizados como en identidad.py. Nunca el IBAN: es lo que cambia quien
    se hace pasar por otro. None si el documento no dice nada: dos facturas
    sin nombre no son de la misma contraparte.
    """
    if sentido == Sentido.ENTRANTE.value and proveedor_id is not None:
        return f"proveedor:{proveedor_id}"
    if sentido == Sentido.SALIENTE.value and cliente_id is not None:
        return f"cliente:{cliente_id}"
    for prefijo, valor in (("btw", normalizar_btw(btw)), ("kvk", normalizar_kvk(kvk)),
                           ("nom", normalizar_nombre(nombre))):
        if valor:
            return f"{prefijo}:{valor}"
    return None


def moneda_extranjera(moneda_doc: str | None) -> str | None:
    """La moneda que no es el euro (X1); None si esta en euros o no se sabe."""
    if not moneda_doc or not moneda_doc.strip():
        return None
    codigo = detectar_moneda(moneda_doc) or moneda_doc.strip().upper()
    return None if codigo in ("EUR", "EURO", "EUROS") else codigo


def _no_solicitados(schema_version: str | None) -> frozenset[str]:
    if schema_version is None:
        return frozenset()
    try:
        claves = compat.no_solicitados(schema_version)
    except ValueError:
        return frozenset()
    return frozenset(_CLAVE_A_COLUMNA[c] for c in claves if c in _CLAVE_A_COLUMNA)


def _ilegibles(conn: sqlite3.Connection) -> dict[tuple[str, int], set[str]]:
    """Campos con un literal impreso y sin valor: estan en el papel, no se pudieron leer."""
    salida: dict[tuple[str, int], set[str]] = defaultdict(set)
    for tabla, fila_id, campo in _filas(
            conn, "SELECT tabla, fila_id, campo FROM procedencia_campo "
                  "WHERE valor_actual IS NULL AND valor_original_crudo IS NOT NULL "
                  "AND tabla IN ('factura', 'factura_linea')"):
        salida[(tabla, fila_id)].add(campo)
    return salida


def _sin_casar(conn: sqlite3.Connection) -> dict[int, tuple[LineaSinCasar, ...]]:
    """Las lineas sin casar de la extraccion vigente de cada factura (paso 6, M2).

    Solo cuentan las de la lectura que vale ahora: si una extraccion
    posterior vuelve a casar la linea, su apunte anterior ya no dice nada.
    """
    salida: dict[int, list[LineaSinCasar]] = defaultdict(list)
    for factura_id, linea_id, orden, retirada, excluida, campos_json in _filas(
            conn, "SELECT s.factura_id, s.linea_id, l.orden, l.retirada_en, s.excluida, "
                  "s.campos_json FROM linea_sin_casar AS s "
                  "JOIN factura AS f ON f.id = s.factura_id "
                  "AND f.extraccion_vigente_id = s.extraccion_id "
                  "JOIN factura_linea AS l ON l.id = s.linea_id ORDER BY s.factura_id, l.orden"):
        salida[factura_id].append(LineaSinCasar(
            linea_id=linea_id, orden=orden, activa=retirada is None, excluida=bool(excluida),
            campos=tuple(json.loads(campos_json))))
    return {f: tuple(v) for f, v in salida.items()}


def imputaciones(conn: sqlite3.Connection) -> dict[int, tuple[Imputacion, ...]]:
    """Las imputaciones activas de cada factura, en orden (paso 9)."""
    salida: dict[int, list[Imputacion]] = defaultdict(list)
    for (id_, factura_id, linea_id, objeto_id, recurso_id, orden_compra_id, importe, horas,
         inicio, fin, servicio, turno) in _filas(
            conn, "SELECT id, factura_id, linea_id, objeto_id, recurso_id, orden_compra_id, "
                  "importe_cent, horas_mil, fecha_inicio, fecha_fin, tipo_servicio, tipo_turno "
                  "FROM factura_imputacion WHERE retirada_en IS NULL ORDER BY factura_id, id"):
        salida[factura_id].append(Imputacion(
            id=id_, linea_id=linea_id, objeto_id=objeto_id, recurso_id=recurso_id,
            orden_compra_id=orden_compra_id, importe_cent=importe, horas_mil=horas,
            fecha_inicio=_fecha(inicio), fecha_fin=_fecha(fin), tipo_servicio=servicio,
            tipo_turno=turno))
    return {f: tuple(v) for f, v in salida.items()}


def _objeto_de_linea(de_factura: dict[int, tuple[Imputacion, ...]]) -> dict[int, int]:
    """El Objeto resuelto de cada linea con una sola imputacion activa.

    Una linea dividida en varias imputaciones no nombra un Objeto solo; ahi
    vale lo impreso.
    """
    por_linea: dict[int, list[int | None]] = defaultdict(list)
    for lista in de_factura.values():
        for i in lista:
            if i.linea_id is not None:
                por_linea[i.linea_id].append(i.objeto_id)
    return {l: o[0] for l, o in por_linea.items() if len(o) == 1 and o[0] is not None}


def referencias(conn: sqlite3.Connection) -> dict[int, tuple[Referencia, ...]]:
    """Las referencias impresas vivas de cada factura (paso 9)."""
    salida: dict[int, list[Referencia]] = defaultdict(list)
    for id_, factura_id, linea_id, valor_doc, valor_norm, clase, orden_compra_id in _filas(
            conn, "SELECT id, factura_id, linea_id, valor_doc, valor_norm, clase, "
                  "orden_compra_id FROM factura_referencia WHERE retirada_en IS NULL "
                  "ORDER BY factura_id, id"):
        salida[factura_id].append(Referencia(id_, linea_id, valor_doc, valor_norm, clase,
                                             orden_compra_id))
    return {f: tuple(v) for f, v in salida.items()}


def ordenes(conn: sqlite3.Connection) -> tuple[OrdenCompra, ...]:
    """Las ordenes de compra con su valor y su fin vigentes y los Objetos que cubren."""
    filas = _filas(conn, "SELECT id, numero, numero_norm, lado, cliente_id, proveedor_id, "
                         "fecha_emision, fecha_inicio, fecha_fin, valor_original_cent, cerrada "
                         "FROM orden_compra ORDER BY id")
    if not filas:
        return ()
    objetos_de: dict[int, set[int]] = defaultdict(set)
    for orden_id, objeto_id in _filas(conn, "SELECT orden_compra_id, objeto_id FROM "
                                            "orden_compra_objeto WHERE retirada_en IS NULL"):
        objetos_de[orden_id].add(objeto_id)
    modificaciones: dict[int, list[tuple]] = defaultdict(list)
    for id_, orden_id, fecha, valor, fin in _filas(
            conn, "SELECT id, orden_compra_id, fecha, valor_nuevo_cent, fecha_fin_nueva "
                  "FROM orden_compra_modificacion"):
        modificaciones[orden_id].append((id_, date.fromisoformat(fecha), valor, _fecha(fin)))
    salida = []
    for (id_, numero, numero_norm, lado, cliente_id, proveedor_id, emision, inicio, fin,
         original, cerrada) in filas:
        valor, fin_vigente = vigentes(original, _fecha(fin), modificaciones.get(id_, ()))
        salida.append(OrdenCompra(
            id=id_, numero=numero, numero_norm=numero_norm, lado=lado,
            parte_id=cliente_id if lado == "cliente" else proveedor_id,
            fecha_emision=_fecha(emision), fecha_inicio=_fecha(inicio), fecha_fin=fin_vigente,
            valor_cent=valor, valor_original_cent=original, fecha_fin_original=_fecha(fin),
            cerrada=bool(cerrada), objetos=frozenset(objetos_de.get(id_, ()))))
    return tuple(salida)


def tarifas(conn: sqlite3.Connection) -> tuple[Tarifa, ...]:
    """Las tarifas pactadas, con el turno ya normalizado (el de dia es None)."""
    return tuple(
        Tarifa(id=id_, sentido=sentido, proveedor_id=proveedor, recurso_id=recurso,
               cliente_id=cliente, objeto_id=objeto, orden_compra_id=orden,
               tipo_servicio=servicio or None, tipo_turno=normalizar_turno(turno),
               unidad=unidad or None, tarifa_e4=precio, vigente_desde=_fecha(desde),
               vigente_hasta=_fecha(hasta))
        for (id_, sentido, proveedor, recurso, cliente, objeto, orden, servicio, turno, unidad,
             precio, desde, hasta) in _filas(
            conn, "SELECT id, sentido, proveedor_id, recurso_id, cliente_id, objeto_id, "
                  "orden_compra_id, tipo_servicio, tipo_turno, unidad, tarifa_e4, vigente_desde, "
                  "vigente_hasta FROM tarifa_acordada WHERE tarifa_e4 IS NOT NULL ORDER BY id"))


def objetos(conn: sqlite3.Connection) -> tuple[Objeto, ...]:
    """Los Objetos del maestro: de que cliente son y si piden PO."""
    return tuple(Objeto(id_, codigo, cliente_id, None if requiere is None else bool(requiere),
                        _fecha(desde), _fecha(hasta))
                 for id_, codigo, cliente_id, requiere, desde, hasta in _filas(
                     conn, "SELECT id, codigo, cliente_id, requiere_po, activo_desde, "
                           "activo_hasta FROM objeto ORDER BY id"))


def _clave_objeto(objeto_id: int | None, objeto_doc: str | None) -> str | None:
    if objeto_id is not None:
        return f"objeto:{objeto_id}"
    texto = normalizar_nombre(objeto_doc)
    return f"doc:{texto}" if texto else None


def _recordar(funcion: Callable[..., Any]) -> Callable[..., Any]:
    """La funcion con memoria de sus argumentos, para una sola construccion.

    Un historico repite mucho lo impreso (el mismo proveedor y la misma obra
    en cientos de facturas): cada texto distinto se normaliza una vez. La
    memoria vive lo que dura `construir`, asi que nada queda entre pasadas.
    """
    memoria: dict[tuple, Any] = {}

    def recordada(*argumentos: Any) -> Any:
        try:
            return memoria[argumentos]
        except KeyError:
            valor = memoria[argumentos] = funcion(*argumentos)
            return valor
    return recordada


def construir(conn: sqlite3.Connection, *, hoy: date,
              politica: Politica | None = None) -> Instantanea:
    """La instantanea del almacen tal como esta ahora, para evaluar el catalogo."""
    ilegibles = _ilegibles(conn)
    de_factura = imputaciones(conn)
    objetos_de_linea = _objeto_de_linea(de_factura)
    referencias_de = referencias(conn)
    vacio: frozenset[str] = frozenset()
    clave_objeto, clave_de_parte = _recordar(_clave_objeto), _recordar(clave_parte)
    no_solicitados = _recordar(_no_solicitados)

    lineas: dict[int, list[Linea]] = defaultdict(list)
    for fila in _filas(conn, f"SELECT {', '.join(_COLUMNAS_LINEA)} FROM factura_linea "
                             "WHERE retirada_en IS NULL ORDER BY factura_id, orden, id"):
        (id_, factura_id, orden, descripcion, objeto_doc, unidad, cantidad, tarifa, importe,
         tipo_iva, inicio, fin, trabajo, semana_doc) = fila
        lineas[factura_id].append(Linea(
            id=id_, orden=orden, descripcion_doc=descripcion, objeto_doc=objeto_doc,
            unidad=unidad, cantidad_mil=cantidad, tarifa_e4=tarifa, importe_cent=importe,
            tipo_iva_pb=tipo_iva, fecha_inicio=_fecha(inicio), fecha_fin=_fecha(fin),
            fecha_trabajo=_fecha(trabajo),
            objeto=clave_objeto(objetos_de_linea.get(id_), objeto_doc),
            ilegibles=frozenset(ilegibles.get(("factura_linea", id_), vacio)),
            semana_doc=semana_doc))

    desglose: dict[int, list[TramoIva]] = defaultdict(list)
    for id_, factura_id, tipo_iva, base, cuota, tratamiento in _filas(
            conn, "SELECT id, factura_id, tipo_iva_pb, base_cent, cuota_cent, tratamiento "
                  "FROM factura_iva WHERE retirada_en IS NULL ORDER BY factura_id, id"):
        desglose[factura_id].append(TramoIva(id_, tipo_iva, base, cuota, tratamiento))

    facturas = []
    dudosos = _dudosos(conn)
    sin_casar = _sin_casar(conn)
    politica = politica or Politica()
    pagos = aplicaciones(conn)
    por_factura: dict[int, list[Aplicacion]] = defaultdict(list)
    for a in pagos:
        por_factura[a.factura_id].append(a)
    vence = vencimientos(conn)
    tolerancia = tolerancia_cent(politica.tolerancia_pago)
    filas_factura = _filas(conn, f"SELECT {', '.join(_COLUMNAS_FACTURA)} FROM factura AS f "
                                 "LEFT JOIN extraccion AS e ON e.id = f.extraccion_vigente_id "
                                 "LEFT JOIN documento AS d ON d.id = f.documento_id "
                                 "ORDER BY f.id")
    confirmadas, propuestas = relaciones(conn)
    movido = efectos_de_relaciones(confirmadas, {fila[0]: fila[17] for fila in filas_factura})
    for fila in filas_factura:
        (id_, sentido, tipo, numero, numero_norm, proveedor_id, cliente_id, emisor_nombre,
         emisor_kvk, emisor_btw, receptor_nombre, receptor_btw, fecha_factura, inicio, fin,
         base, iva, total, tipo_iva, tratamiento, iban, moneda_doc, anulada, fusionada_en,
         schema_version, documento_id, direccion, kor, notas, sin_original, origen) = fila
        efecto = movido.get(id_, SIN_EFECTO)
        entrante = sentido == Sentido.ENTRANTE.value
        nombre = emisor_nombre if entrante else receptor_nombre
        facturas.append(Factura(
            id=id_, sentido=sentido, tipo=tipo, numero=numero, numero_norm=numero_norm,
            parte=(clave_de_parte(sentido, proveedor_id, None, emisor_btw, emisor_kvk,
                                  emisor_nombre)
                   if entrante else
                   clave_de_parte(sentido, None, cliente_id, receptor_btw, None, receptor_nombre)),
            parte_nombre=nombre or "(sin nombre)",
            proveedor_id=proveedor_id, cliente_id=cliente_id,
            emisor_nombre_doc=emisor_nombre, emisor_kvk_doc=emisor_kvk,
            emisor_btw_doc=emisor_btw, receptor_nombre_doc=receptor_nombre,
            receptor_btw_doc=receptor_btw, fecha_factura=_fecha(fecha_factura),
            periodo_inicio=_fecha(inicio), periodo_fin=_fecha(fin), base_cent=base,
            iva_cent=iva, total_cent=total, tipo_iva_pb=tipo_iva, tratamiento_iva=tratamiento,
            iban_doc=iban, moneda=moneda_extranjera(moneda_doc), anulada=bool(anulada),
            fusionada_en_id=fusionada_en, lineas=tuple(lineas.get(id_, ())),
            desglose=tuple(desglose.get(id_, ())),
            ilegibles=frozenset(ilegibles.get(("factura", id_), vacio)),
            no_solicitados=no_solicitados(schema_version),
            documento_id=documento_id, emisor_direccion_doc=direccion,
            kor_mencionada=None if kor is None else bool(kor), notas_doc=notas,
            dudosos=dudosos.get(id_, vacio), sin_original=bool(sin_original),
            sin_casar=sin_casar.get(id_, ()), vencimiento=vence.get(id_),
            origen=origen, acreditado_cent=efecto.acreditado_cent,
            sustituida_por=efecto.sustituida_por,
            imputaciones=de_factura.get(id_, ()), referencias=referencias_de.get(id_, ()),
            **_pagado(total, por_factura.get(id_), tolerancia, efecto.acreditado_cent)))

    fotos = fotos_planning(conn)
    resolutor = Resolutor(conn) if fotos else None
    vigentes = turnos_vigentes(conn, resolutor) if resolutor is not None else ()
    return Instantanea(hoy=hoy, politica=politica, facturas=tuple(facturas),
                       relaciones=confirmadas, propuestas=propuestas, citas=citas(conn),
                       proveedores=partes(conn, "proveedor"),
                       clientes=partes(conn, "cliente"), cuentas=cuentas(conn),
                       telefonos=telefonos(conn),
                       lotes=lotes(conn, sin_resolver_del_planning(conn, resolutor)),
                       extractos=extractos(conn),
                       movimientos=movimientos(conn), aplicaciones=pagos,
                       beneficiarios=beneficiarios(conn),
                       bloqueos=bloqueos(conn, {a.factura_id for a in pagos
                                                if a.estado == "confirmada"}),
                       exact_pagado=exact_pagado(conn), ordenes=ordenes(conn),
                       tarifas=tarifas(conn), objetos=objetos(conn), turnos=vigentes,
                       fotos_planning=fotos,
                       conciliaciones=conciliaciones(conn) if fotos else (),
                       ciclos=ciclos(conn), periodos_btw=periodos_btw(conn))


_SIN_PAGOS = {"pagado_cent": 0, "fuente_pago": None, "pagada": False}


def _pagado(total: int | None, propias: list[Aplicacion] | None,
            tolerancia: int, acreditado: int = 0) -> dict[str, Any]:
    if not propias and not acreditado:
        return _SIN_PAGOS
    s = saldo(total, propias or (), tolerancia, acreditado)
    return {"pagado_cent": s.pagado_cent, "fuente_pago": s.fuente, "pagada": s.pagada}


# ------------------------------------------------------------ paso 8: relaciones y citas

def relaciones(conn: sqlite3.Connection) -> tuple[tuple[Relacion, ...], tuple[Relacion, ...]]:
    """Las relaciones vivas (ni retiradas ni rechazadas): las confirmadas y las propuestas.

    Una confirmada solo mueve algo mientras sus dos facturas cuentan: si su
    origen esta anulado (el abono emitido por error, la sustituta que se
    retiro) o una de las dos esta fusionada en otra (es la copia de otra), no
    esta entre las confirmadas. Si no, un abono anulado seguiria bajando lo
    pendiente de la original, o una sustituta anulada la seguiria sacando de
    los totales, sin que nada lo dijera. Es lo mismo que v_factura_relaciones
    (migracion 0009).
    """
    confirmadas, propuestas = [], []
    for id_, origen, destino, tipo, importe, estado, fuente, vigente in _filas(
            conn, "SELECT r.id, r.origen_id, r.destino_id, r.tipo, r.importe_cent, r.estado, "
                  "r.fuente, o.anulada = 0 AND o.fusionada_en_id IS NULL "
                  "AND d.fusionada_en_id IS NULL "
                  "FROM factura_relacion AS r JOIN factura AS o ON o.id = r.origen_id "
                  "JOIN factura AS d ON d.id = r.destino_id "
                  "WHERE r.retirada_en IS NULL AND r.estado <> 'rechazada' ORDER BY r.id"):
        relacion = Relacion(origen, destino, tipo, id_, importe, fuente)
        if estado != "confirmada":
            propuestas.append(relacion)
        elif vigente:
            confirmadas.append(relacion)
    return tuple(confirmadas), tuple(propuestas)


def citas(conn: sqlite3.Connection) -> tuple[Cita, ...]:
    """Las facturas que nombra cada documento (factura_cita), las que siguen vivas."""
    return tuple(Cita(id_, factura_id, numero_doc, numero_norm, relacion)
                 for id_, factura_id, numero_doc, numero_norm, relacion in _filas(
                     conn, "SELECT id, factura_id, numero_doc, numero_norm, relacion_doc "
                           "FROM factura_cita WHERE retirada_en IS NULL "
                           "ORDER BY factura_id, id"))


# ------------------------------------------------------------ paso 5: maestros y cuentas

# Los campos criticos de una factura (campos.criticos("factura")), escritos
# aqui para no importar campos.py desde reglas/: un test comprueba que son
# los mismos.
CRITICOS_FACTURA = ("numero", "proveedor_id", "cliente_id", "emisor_nombre_doc",
                    "fecha_factura", "periodo_inicio", "periodo_fin", "iva_cent", "total_cent",
                    "iban_doc")


def _dudosos(conn: sqlite3.Connection) -> dict[int, frozenset[str]]:
    """Por factura, sus campos criticos leidos con duda que nadie ha verificado (Q2).

    Lo mismo que cuenta revision.estado_de_campos: lo automatico marcado
    dudoso, sin una verificacion de esa misma rev del campo.
    """
    marcas = ", ".join("?" * len(CRITICOS_FACTURA))
    manuales = ", ".join("?" * len(FUENTES_MANUALES))
    salida: dict[int, set[str]] = defaultdict(set)
    for fila_id, campo in _filas(
            conn, "SELECT fila_id, campo FROM procedencia_campo WHERE tabla = 'factura' "
                  f"AND dudoso = 1 AND campo IN ({marcas}) AND fuente NOT IN ({manuales}) "
                  "AND (verificado_rev IS NULL OR verificado_rev <> rev_campo)",
            (*CRITICOS_FACTURA, *sorted(FUENTES_MANUALES))):
        salida[fila_id].add(campo)
    return {f: frozenset(c) for f, c in salida.items()}


def partes(conn: sqlite3.Connection, tabla: str) -> tuple[Parte, ...]:
    """Los proveedores o clientes del maestro, con sus nombres y alias ya normalizados."""
    alias: dict[int, set[str]] = defaultdict(set)
    for fila_id, norma in _filas(conn, "SELECT fila_id, alias_norm FROM alias WHERE tabla = ? "
                                       "AND confirmado = 1 AND activo = 1", (tabla,)):
        alias[fila_id].add(norma)
    columnas = ("id, nombre, kvk, btw_id, regimen_iva, activo, NULL, NULL"
                if tabla == "proveedor" else
                "id, nombre, kvk, btw_id, tratamiento_iva_defecto, activo, requiere_po, "
                "verlegd_elegible")
    salida = []
    for id_, nombre, kvk, btw, regimen, activo, requiere_po, elegible in _filas(
            conn, f"SELECT {columnas} FROM {tabla} ORDER BY id"):
        nombres = {n for n in (normalizar_nombre(nombre),) if n} | alias.get(id_, set())
        salida.append(Parte(id=id_, tabla=tabla, nombre=nombre, nombres=frozenset(nombres),
                            kvk=normalizar_kvk(kvk), btw=normalizar_btw(btw),
                            regimen_iva=regimen, activo=bool(activo),
                            requiere_po=None if requiere_po is None else bool(requiere_po),
                            verlegd_elegible=None if elegible is None else bool(elegible)))
    return tuple(salida)


# Cuando llego un documento: recibido_en puede ser la fecha del fichero (el
# mtime), que pone quien lo manda y puede estar en el futuro; registrado_en
# es cuando entro aqui. Vale la primera de las dos: una fecha posterior haria
# valer un telefono puesto despues de que el documento llegara (F8).
LLEGADA_DOCUMENTO = "min(coalesce({d}.recibido_en, {d}.registrado_en), {d}.registrado_en)"


def primeros_documentos(conn: sqlite3.Connection) -> dict[tuple[int, str], str]:
    """Por proveedor e IBAN impreso (normalizado), cuando llego el primer documento que lo traia.

    Es lo que motiva verificar una cuenta aunque la orden no nombre la factura
    (bancaria.referencia_de): quien verifica no elige el documento.
    """
    salida: dict[tuple[int, str], str] = {}
    for proveedor_id, iban_doc, llegada in _filas(
            conn, "SELECT f.proveedor_id, f.iban_doc, "
                  f"min({LLEGADA_DOCUMENTO.format(d='d')}) FROM factura AS f "
                  "JOIN documento AS d ON d.id = f.documento_id "
                  "WHERE f.proveedor_id IS NOT NULL AND f.iban_doc IS NOT NULL "
                  "GROUP BY f.proveedor_id, f.iban_doc"):
        iban = normalizar_iban(iban_doc)
        if iban is None or llegada is None:
            continue
        clave = (proveedor_id, iban)
        if clave not in salida or llegada < salida[clave]:
            salida[clave] = llegada
    return salida


def cuentas(conn: sqlite3.Connection) -> tuple[Cuenta, ...]:
    """El registro de cuentas con sus eventos, en orden.

    Para una decision de una persona: si tenia confirmar_iban en ese
    momento (el rol vigente entonces, aunque hoy este de baja) y cuando
    llego lo que la motivo (el documento de la factura, o el fichero de la
    importacion del maestro). De cada cuenta de proveedor, cuando llego el
    primer documento suyo con ese IBAN.
    """
    eventos: dict[int, list[EventoCuenta]] = defaultdict(list)
    for (id_, cuenta_id, tipo, importacion_id, documento_id, usuario_id, telefono, en,
         decision, llegada_doc, llegada_imp, con_permiso) in _filas(
            conn, "SELECT e.id, e.cuenta_id, e.tipo, e.importacion_id, e.documento_id, "
                  "e.usuario_id, e.telefono_usado, e.en, e.decision_facturas, "
                  f"{LLEGADA_DOCUMENTO.format(d='d')}, "
                  "coalesce(di.registrado_en, i.iniciada_en), "
                  "e.usuario_id IS NOT NULL AND EXISTS ("
                  "  SELECT 1 FROM usuario AS u JOIN usuario_rol AS ur ON ur.usuario_id = u.id "
                  "  JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id "
                  "  WHERE u.id = e.usuario_id AND u.es_sistema = 0 "
                  "  AND rp.permiso = 'confirmar_iban' AND ur.desde <= e.en "
                  "  AND (ur.hasta IS NULL OR ur.hasta > e.en)) "
                  "FROM cuenta_evento AS e "
                  "LEFT JOIN documento AS d ON d.id = e.documento_id "
                  "LEFT JOIN importacion AS i ON i.id = e.importacion_id "
                  "LEFT JOIN documento AS di ON di.id = i.documento_id "
                  "ORDER BY e.id"):
        eventos[cuenta_id].append(EventoCuenta(
            id=id_, tipo=tipo, en=en, importacion_id=importacion_id, documento_id=documento_id,
            usuario_id=usuario_id, con_permiso=bool(con_permiso),
            telefono_usado=normalizar_telefono(telefono), llegada=llegada_doc or llegada_imp,
            decision_facturas=decision, dia=_dia(en)))
    documentos = primeros_documentos(conn)
    return tuple(
        Cuenta(id=id_, titular=titular, parte_id=proveedor_id or cliente_id, iban=iban,
               primera_fuente=primera, eventos=tuple(eventos.get(id_, ())),
               primer_documento=documentos.get((proveedor_id, iban))
               if proveedor_id is not None else None)
        for id_, titular, proveedor_id, cliente_id, iban, primera in _filas(
            conn, "SELECT id, titular, proveedor_id, cliente_id, iban, primera_fuente "
                  "FROM cuenta_bancaria WHERE titular <> 'propia' ORDER BY id"))


def _dia(instante: str) -> date:
    return datetime.fromisoformat(instante).astimezone(ZoneInfo(ZONA_EMPRESA)).date()


def telefonos(conn: sqlite3.Connection) -> tuple[CambioTelefono, ...]:
    """Cada valor que tuvo el telefono de verificacion de cada proveedor, en orden.

    Un cambio_campo con el mismo valor (solo cambio la fuente) no es un
    cambio de numero. El que se puso al crear el proveedor (rev 0) es el
    alta: no abre el enfriamiento.
    """
    salida = []
    for fila_id, cambio_id, rev, anterior, nuevo, en in _filas(
            conn, "SELECT c.fila_id, c.id, c.rev, c.valor_anterior, c.valor_nuevo, e.en "
                  "FROM cambio_campo AS c JOIN evento AS e ON e.id = c.evento_id "
                  "WHERE c.tabla = 'proveedor' AND c.campo = 'telefono_verificacion' "
                  "ORDER BY c.id"):
        valor = normalizar_telefono(json.loads(nuevo) if nuevo else None)
        previo = normalizar_telefono(json.loads(anterior) if anterior else None)
        if rev > 0 and valor == previo:
            continue
        salida.append(CambioTelefono(proveedor_id=fila_id, cambio_id=cambio_id, valor=valor,
                                     en=en, dia=_dia(en), alta=rev == 0))
    return tuple(salida)


def lotes(conn: sqlite3.Connection,
          sin_resolver: dict[int, tuple[tuple[int, str, str], ...]] | None = None,
          ) -> tuple[Lote, ...]:
    """Las importaciones de maestros (no las de out/, que son una por documento), con lo que
    cada foto del planning trae sin resolver contra el maestro de ahora (Z2)."""
    filas = _filas(
        conn, "SELECT id, fuente, tipo, estado, exportado_en, iniciada_en, filas_rechazadas, "
              "rechazos_json FROM importacion WHERE fuente <> 'extracciones' ORDER BY id")
    ultimo: dict[tuple[str, str], int] = {}
    for id_, fuente, tipo, *_resto in filas:
        ultimo[(fuente, tipo)] = id_
    salida = []
    for id_, fuente, tipo, estado, exportado, iniciada, rechazadas, rechazos in filas:
        lista = tuple(
            (int(r.get("fila") or 0), str(r.get("codigo") or "fila"), str(r.get("motivo") or ""))
            for r in json.loads(rechazos or "[]") if isinstance(r, dict))
        # Nunca mas fresco que cuando se importo: una fecha de exportacion
        # futura (una errata, un fichero copiado) haria que no caducase nunca (Z1).
        salida.append(Lote(id=id_, fuente=fuente, tipo=tipo, estado=estado,
                           exportado=_dia(min(exportado or iniciada, iniciada)),
                           filas_rechazadas=rechazadas, rechazos=lista,
                           ultimo=ultimo[(fuente, tipo)] == id_,
                           sin_resolver=(sin_resolver or {}).get(id_, ())))
    return tuple(salida)


# ------------------------------------------------------------ paso 7: vencimientos, banco y pagos

def vencimientos(conn: sqlite3.Connection) -> dict[int, date | None]:
    """El vencimiento efectivo de cada factura: el impreso o, si no hay, la fecha mas el plazo.

    El plazo que la ingesta calcula de las condiciones impresas (v2) es lo que
    dice el proveedor, no lo acordado: solo vale si el maestro no tiene plazo.
    Si no, un "per omgaande" impreso haria vencer la factura el dia de su
    fecha. El que fija una persona o una importacion en la factura si manda
    sobre el maestro. Lo usan las reglas de pagos, las caches de estado y el
    flujo de caja: una sola cuenta.
    """
    plazos = {("proveedor", i): p for i, p in _filas(
        conn, "SELECT id, plazo_pago_dias FROM proveedor WHERE plazo_pago_dias IS NOT NULL")}
    plazos.update({("cliente", i): p for i, p in _filas(
        conn, "SELECT id, plazo_pago_dias FROM cliente WHERE plazo_pago_dias IS NOT NULL")})
    del_documento = {f[0] for f in _filas(
        conn, "SELECT fila_id FROM procedencia_campo WHERE tabla = 'factura' "
              "AND campo = 'plazo_pago_dias' AND fuente = 'calculado' "
              "AND fuente_ref = 'condiciones_pago_doc'")}
    salida: dict[int, date | None] = {}
    for id_, sentido, proveedor_id, cliente_id, fecha, impreso, plazo in _filas(
            conn, "SELECT id, sentido, proveedor_id, cliente_id, fecha_factura, "
                  "fecha_vencimiento, plazo_pago_dias FROM factura"):
        entrante = sentido == Sentido.ENTRANTE.value
        acordado = plazos.get(("proveedor", proveedor_id) if entrante else ("cliente", cliente_id))
        if plazo is None or (id_ in del_documento and acordado is not None):
            plazo = acordado
        if impreso is not None:
            salida[id_] = date.fromisoformat(impreso)
        elif fecha is not None and plazo is not None:
            salida[id_] = date.fromisoformat(fecha) + timedelta(days=plazo)
        else:
            salida[id_] = None
    return salida


def aplicaciones(conn: sqlite3.Connection) -> tuple[Aplicacion, ...]:
    """Lo pagado de cada factura (aplicacion_pago), en orden."""
    filas = _filas(conn, "SELECT id, factura_id, movimiento_id, importe_cent, fecha_pago, "
                         "fuente, metodo, estado FROM aplicacion_pago ORDER BY id")
    return tuple(Aplicacion(id_, factura_id, movimiento_id, importe, date.fromisoformat(fecha),
                            fuente, metodo, estado)
                 for id_, factura_id, movimiento_id, importe, fecha, fuente, metodo, estado
                 in filas)


def extractos(conn: sqlite3.Connection) -> tuple[Extracto, ...]:
    filas = _filas(conn, "SELECT id, importacion_id, cuenta_propia_iban, secuencia, "
                         "saldo_inicial_cent, saldo_final_cent, desde, hasta, con_saldos "
                         "FROM extracto_bancario ORDER BY id")
    return tuple(Extracto(id_, importacion, cuenta, secuencia, inicial, final, _fecha(desde),
                          _fecha(hasta), bool(saldos))
                 for id_, importacion, cuenta, secuencia, inicial, final, desde, hasta, saldos
                 in filas)


# Una referencia de menos de tres caracteres ("1", "12") casaria con cualquier cosa.
LARGO_MINIMO = 3
_PALABRA = re.compile(r"[A-Za-z0-9]+(?:[-./_][A-Za-z0-9]+)*")
_SIN_REFERENCIA = frozenset({"NOTPROVIDED", "NONREF", "NOTAVAILABLE"})


def referencias_de(*textos: str | None) -> frozenset[str]:
    """Lo que puede ser un numero de factura en lo que dice el banco, ya normalizado.

    Cada palabra (con sus guiones, puntos o barras: "2026-4471") y cada par de
    palabras seguidas ("2026 4471"): el banco parte a veces el numero en dos.
    Lo usan casar (pagos.py) y la referencia de cada movimiento para K4.
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


def _referencia_de_pago(texto: str | None) -> str | None:
    normal = normalizar_referencia(texto)
    return None if not normal or normal in _SIN_REFERENCIA else normal


def movimientos(conn: sqlite3.Connection) -> tuple[Movimiento, ...]:
    """Los movimientos del banco, con lo que los identifica como pago de algo (K4).

    `referencia`: la estructurada, el end-to-end o, sin ninguna, el numero (o
    la referencia de pago) de una factura que aparezca en el concepto. Nunca el
    concepto entero: los recibos de un contrato llevan el mismo texto cada mes.
    """
    conocidas: set[str] = set()
    for numero, referencia in _filas(conn, "SELECT numero_norm, referencia_pago FROM factura"):
        conocidas.update(r for r in (numero, normalizar_referencia(referencia))
                         if r and len(r) >= LARGO_MINIMO)
    salida = []
    for (id_, extracto_id, cuenta, fecha, importe, moneda, contraparte, nombre, estructurada,
         e2e, concepto) in _filas(
            conn, "SELECT id, extracto_id, cuenta_propia_iban, fecha_contable, importe_cent, "
                  "moneda, contraparte_iban, contraparte_nombre_doc, referencia_estructurada, "
                  "referencia_e2e, concepto_doc FROM movimiento_bancario ORDER BY id"):
        referencia = _referencia_de_pago(estructurada) or _referencia_de_pago(e2e)
        if referencia is None and concepto:
            en_concepto = sorted(referencias_de(concepto) & conocidas)
            referencia = en_concepto[0] if en_concepto else None
        salida.append(Movimiento(id_, extracto_id, cuenta, date.fromisoformat(fecha), importe,
                                 moneda, contraparte, nombre, referencia))
    return tuple(salida)


def exact_pagado(conn: sqlite3.Connection) -> tuple[PagadoExact, ...]:
    """Lo que dice Exact de lo pagado de cada factura (tambien cero): la ultima importacion de
    pagos aceptada que la trae, con el dia de su foto (K8)."""
    ultimo: dict[int, PagadoExact] = {}
    for (datos,) in _filas(
            conn, "SELECT e.datos_json FROM evento AS e JOIN importacion AS i "
                  "ON i.id = e.fila_id WHERE e.tipo = 'importacion' AND e.tabla = 'importacion' "
                  "AND i.fuente = 'exact' AND i.tipo = 'pagos_exact' "
                  "AND i.estado IN ('aceptada', 'parcial') ORDER BY i.id, e.id"):
        contenido = json.loads(datos or "{}")
        if not contenido.get("exact_fecha"):
            continue
        fecha = date.fromisoformat(contenido["exact_fecha"])
        for factura_id, pagado in contenido.get("exact_pagado", ()):
            ultimo[int(factura_id)] = PagadoExact(int(factura_id), int(pagado), fecha)
    return tuple(ultimo[f] for f in sorted(ultimo))


def beneficiarios(conn: sqlite3.Connection) -> frozenset[str]:
    """Los IBAN de quien se paga sin ser proveedor (vigentes)."""
    return frozenset(f[0] for f in _filas(
        conn, "SELECT iban FROM beneficiario_conocido WHERE retirada_en IS NULL"))


# Bloqueada es lo que dice prioridad.py: un hallazgo que bloquea y esta
# abierto. Uno desaparecido (pegajoso, que espera a una persona) pone la
# factura en Atencion, no en Bloqueada: K5 no lo cuenta.
_PENDIENTE = frozenset({"abierto"})


def tramos_bloqueados(historia: Iterable[tuple[int, str, date]]
                      ) -> dict[int, list[tuple[date, date | None]]]:
    """De la historia de unos hallazgos que bloquean (hallazgo, estado, dia), en orden, los
    dias en que cada uno tuvo la factura Bloqueada: abierto, y hasta el dia en que dejo de
    estarlo (incluido); None si sigue."""
    tramos: dict[int, list[tuple[date, date | None]]] = defaultdict(list)
    abierto: dict[int, date] = {}
    for hallazgo_id, estado, dia in historia:
        if estado in _PENDIENTE:
            abierto.setdefault(hallazgo_id, dia)
        elif hallazgo_id in abierto:
            tramos[hallazgo_id].append((abierto.pop(hallazgo_id), dia))
    for hallazgo_id, desde in abierto.items():
        tramos[hallazgo_id].append((desde, None))
    return tramos


def bloqueos(conn: sqlite3.Connection, facturas: set[int]) -> tuple[Bloqueo, ...]:
    """Los dias en que cada una de estas facturas tuvo un hallazgo que bloquea pendiente.

    Sale de la historia de cada hallazgo (hallazgo_evento): pendiente desde
    que se abre o reabre, hasta que se anula, desaparece, se cierra o se
    resuelve (lo mismo que llama Bloqueada la prioridad). No
    cuentan los de los pagos (K) ni F7: los provoca el propio pago, y K5
    diria que se pago bloqueada por el hallazgo que abrio ese mismo pago.
    """
    if not facturas:
        return ()
    hallazgos: dict[int, tuple[str, set[int]]] = {}
    for hallazgo_id, regla, factura_id in _filas(
            conn, "SELECT id, regla, factura_id FROM hallazgo WHERE severidad = 'bloqueo' "
                  "AND regla NOT LIKE 'K%' AND regla <> 'F7'"):
        hallazgos[hallazgo_id] = (regla, {factura_id} if factura_id is not None else set())
    if not hallazgos:
        return ()
    for hallazgo_id, fila_id in _filas(
            conn, "SELECT hallazgo_id, fila_id FROM hallazgo_objetivo WHERE tabla = 'factura'"):
        if hallazgo_id in hallazgos:
            hallazgos[hallazgo_id][1].add(fila_id)
    tramos = tramos_bloqueados(
        (hallazgo_id, estado, _dia(en)) for hallazgo_id, estado, en in _filas(
            conn, "SELECT hallazgo_id, estado, en FROM hallazgo_evento ORDER BY id")
        if hallazgo_id in hallazgos)
    salida = []
    for hallazgo_id, lista in sorted(tramos.items()):
        regla, suyas = hallazgos[hallazgo_id]
        for factura_id in sorted(suyas & facturas):
            salida.extend(Bloqueo(factura_id, regla, desde, hasta) for desde, hasta in lista)
    return tuple(salida)


# ------------------------------------------------------------ paso 10: el planning

class Resolutor:
    """Lo que nombra el planning (Objeto, persona, proveedor, cliente, PO), en el maestro de
    ahora y por coincidencia exacta: lo que registrar.py resuelve al importar y, para un
    turno que entonces no se resolvio, lo que se resuelve en cada pasada sin tocar la fila.

    El orden es el de registrar.py: el numero de TRNSPRNT (o de Exact) de la
    fila; el codigo de un Objeto; el btw-id o el KvK de una parte; y un alias
    confirmado. Dos filas que casan son una ambiguedad: no se elige ninguna.
    Se lee el maestro una vez por pasada.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._alias: dict[tuple[str, str], int] = {
            (tabla, norma): fila for tabla, norma, fila in _filas(
                conn, "SELECT tabla, alias_norm, fila_id FROM alias WHERE confirmado = 1 "
                      "AND activo = 1")}
        self._objetos = _filas(conn, "SELECT id, codigo, trnsprnt_id, cliente_id FROM objeto")
        self._recursos = _filas(conn, "SELECT id, trnsprnt_id, proveedor_id FROM recurso")
        self._partes = {
            tabla: _filas(conn, f"SELECT id, exact_id, trnsprnt_id, btw_id, kvk FROM {tabla}")
            for tabla in ("proveedor", "cliente")}
        self._ordenes = _filas(conn, "SELECT id, numero_norm, cliente_id FROM orden_compra "
                                     "WHERE lado = 'cliente'")
        self.cliente_de_objeto = {f[0]: f[3] for f in self._objetos}
        self.proveedor_de_recurso = {f[0]: f[2] for f in self._recursos}
        self._memoria: dict[tuple, int | None] = {}

    @staticmethod
    def _una(ids: Iterable[int]) -> int | None:
        unicos = set(ids)
        return next(iter(unicos)) if len(unicos) == 1 else None

    def _por_alias(self, tabla: str, texto: str) -> int | None:
        norma = normalizar_nombre(texto)
        return self._alias.get((tabla, norma)) if norma else None

    def resolver(self, que: str, texto: str | None, cliente_id: int | None = None) -> int | None:
        if texto is None or not str(texto).strip():
            return None
        clave = (que, str(texto).strip(), cliente_id)
        if clave not in self._memoria:
            self._memoria[clave] = self._resolver(que, str(texto).strip(), cliente_id)
        return self._memoria[clave]

    def _resolver(self, que: str, texto: str, cliente_id: int | None) -> int | None:
        if que == "objeto":
            for columna in (2, 1):
                encontrados = [f[0] for f in self._objetos if f[columna] is not None and (
                    f[columna] == texto if columna == 2
                    else normalizar_nombre(f[columna]) == normalizar_nombre(texto))]
                if encontrados:
                    return self._una(encontrados)
            return self._por_alias("objeto", texto)
        if que == "recurso":
            encontrados = [f[0] for f in self._recursos if f[1] == texto]
            return self._una(encontrados) if encontrados else self._por_alias("recurso", texto)
        if que in ("proveedor", "cliente"):
            filas = self._partes[que]
            for columna, normalizar in ((1, None), (2, None), (3, normalizar_btw),
                                        (4, normalizar_kvk if que == "proveedor" else None)):
                if columna == 4 and normalizar is None:
                    continue
                if normalizar is None:
                    encontrados = [f[0] for f in filas if f[columna] == texto]
                else:
                    buscado = normalizar(texto)
                    encontrados = [f[0] for f in filas if buscado and f[columna] is not None
                                   and normalizar(f[columna]) == buscado]
                if encontrados:
                    return self._una(encontrados)
            return self._por_alias(que, texto)
        if que == "orden_compra":
            numero = normalizar_referencia(texto)
            encontrados = [f[0] for f in self._ordenes if f[1] == numero
                           and (cliente_id is None or f[2] == cliente_id)]
            return self._una(encontrados)
        raise ValueError(que)


_COLUMNAS_TURNO = (
    "t.id", "t.importacion_id", "t.id_externo", "t.clave_fragil", "t.nivel", "t.fecha", "t.dias",
    "t.hora_inicio", "t.hora_fin", "t.horas_planificadas_mil", "t.horas_realizadas_mil",
    "t.horas_aprobadas_mil", "t.estado", "t.objeto_id", "t.recurso_id", "t.proveedor_id",
    "t.cliente_id", "t.tipo_servicio", "t.tipo_turno", "t.facturable", "t.tarifa_compra_e4",
    "t.tarifa_venta_e4", "t.objeto_ref_doc", "t.recurso_ref_doc", "t.proveedor_ref_doc",
    "t.cliente_ref_doc", "t.po_ref_doc",
)


def _turno(fila: tuple, resolutor: Resolutor | None) -> Turno:
    """Un turno con lo que no se resolvio al importarlo resuelto ahora, el proveedor de su
    persona si no trae el suyo y el cliente de su Objeto si no trae el suyo."""
    (id_, importacion_id, id_externo, fragil, nivel, fecha, dias, inicio, fin, planificadas,
     realizadas, aprobadas, estado, objeto_id, recurso_id, proveedor_id, cliente_id, servicio,
     turno, facturable, compra, venta, objeto_ref, recurso_ref, proveedor_ref, cliente_ref,
     po_ref) = fila
    orden_compra_id = None
    if resolutor is not None:
        objeto_id = objeto_id or resolutor.resolver("objeto", objeto_ref)
        recurso_id = recurso_id or resolutor.resolver("recurso", recurso_ref)
        proveedor_id = (proveedor_id or resolutor.resolver("proveedor", proveedor_ref)
                        or resolutor.proveedor_de_recurso.get(recurso_id))
        cliente_id = (cliente_id or resolutor.resolver("cliente", cliente_ref)
                      or resolutor.cliente_de_objeto.get(objeto_id))
        orden_compra_id = resolutor.resolver("orden_compra", po_ref, cliente_id)
    return Turno(id=id_, importacion_id=importacion_id, id_externo=id_externo,
                 clave_fragil=bool(fragil), nivel=nivel, fecha=date.fromisoformat(fecha),
                 dias=dias, hora_inicio=inicio, hora_fin=fin, horas_planificadas_mil=planificadas,
                 horas_realizadas_mil=realizadas, horas_aprobadas_mil=aprobadas, estado=estado,
                 objeto_id=objeto_id, recurso_id=recurso_id, proveedor_id=proveedor_id,
                 cliente_id=cliente_id, tipo_servicio=servicio or None,
                 tipo_turno=normalizar_turno(turno),
                 facturable=None if facturable is None else bool(facturable),
                 tarifa_compra_e4=compra, tarifa_venta_e4=venta,
                 orden_compra_id=orden_compra_id)


def turnos_vigentes(conn: sqlite3.Connection,
                    resolutor: Resolutor | None = None) -> tuple[Turno, ...]:
    """El planning que vale (v_turno_vigente): de cada dia, la foto aceptada mas nueva."""
    return tuple(_turno(fila, resolutor) for fila in _filas(
        conn, f"SELECT {', '.join(_COLUMNAS_TURNO)} FROM v_turno_vigente AS t "
              "ORDER BY t.fecha, t.id"))


def fotos_planning(conn: sqlite3.Connection) -> tuple[FotoPlanning, ...]:
    """Las importaciones aceptadas del planning: de que dia son (lo que se exporto, nunca
    despues de cuando se importo), que dias cubren y sus huecos (huecos_planning)."""
    huecos = huecos_planning(conn)
    return tuple(
        FotoPlanning(id_, _dia(min(exportado or iniciada, iniciada)), _fecha(desde),
                     _fecha(hasta), huecos.get(id_, ()))
        for id_, exportado, iniciada, desde, hasta in _filas(
            conn, "SELECT id, exportado_en, iniciada_en, cubre_desde, cubre_hasta "
                  "FROM importacion WHERE fuente = 'trnsprnt' AND tipo = 'planning' "
                  "AND estado IN ('aceptada', 'parcial') ORDER BY id"))


# Una importacion n es mas nueva que i como en v_turno_vigente: por cuando se
# exporto (o, sin eso, cuando se importo) y, a igual hora, la que entro despues.
_MAS_NUEVA = (
    "n.fuente = i.fuente AND n.tipo = 'planning' AND n.estado IN ('aceptada', 'parcial') "
    "AND n.id <> i.id AND (coalesce(n.exportado_en, n.iniciada_en) > "
    "coalesce(i.exportado_en, i.iniciada_en) OR (coalesce(n.exportado_en, n.iniciada_en) = "
    "coalesce(i.exportado_en, i.iniciada_en) AND n.id > i.id))")


def huecos_planning(conn: sqlite3.Connection) -> dict[int, tuple[tuple[date, date], ...]]:
    """Por foto, los dias de sus semanas con una fila semanal que ya no vale que ninguna foto
    mas nueva cubre.

    v_turno_vigente quita una fila semanal entera en cuanto una foto mas nueva
    cubre algun dia de su semana (no se puede partir). Los demas dias de esa
    semana siguen dentro de lo que cubre la foto vieja, pero ya no tienen
    turnos: son un hueco, y lo que caiga en el da sin datos (turnos.tramos).
    """
    semanas: dict[int, set[date]] = defaultdict(set)
    for importacion_id, lunes in _filas(
            conn, "SELECT DISTINCT t.importacion_id, t.fecha FROM planning_turno AS t "
                  "JOIN importacion AS i ON i.id = t.importacion_id "
                  "WHERE t.nivel = 'semana' AND i.fuente = 'trnsprnt' AND i.tipo = 'planning' "
                  "AND i.estado IN ('aceptada', 'parcial') "
                  "AND t.id NOT IN (SELECT id FROM v_turno_vigente)"):
        semanas[importacion_id].add(date.fromisoformat(lunes))
    salida: dict[int, tuple[tuple[date, date], ...]] = {}
    for importacion_id, lunes_ in sorted(semanas.items()):
        nuevas = [(date.fromisoformat(d), date.fromisoformat(h)) for d, h in _filas(
            conn, f"SELECT n.cubre_desde, n.cubre_hasta FROM importacion AS n, importacion AS i "
                  f"WHERE i.id = ? AND {_MAS_NUEVA} AND n.cubre_desde IS NOT NULL "
                  "AND n.cubre_hasta IS NOT NULL", (importacion_id,))]
        dias = sorted(lunes + timedelta(days=n) for lunes in lunes_ for n in range(7)
                      if not any(d <= lunes + timedelta(days=n) <= h for d, h in nuevas))
        tramos_: list[list[date]] = []
        for dia in dias:
            if tramos_ and dia == tramos_[-1][1] + timedelta(days=1):
                tramos_[-1][1] = dia
            else:
                tramos_.append([dia, dia])
        if tramos_:
            salida[importacion_id] = tuple((d, h) for d, h in tramos_)
    return salida


def sin_resolver_del_planning(conn: sqlite3.Connection, resolutor: Resolutor | None,
                              ) -> dict[int, tuple[tuple[int, str, str], ...]]:
    """Por importacion del planning, lo que sus turnos nombran y el maestro de hoy no tiene:
    (posicion, que es, como lo nombra el fichero). Solo de la ultima foto (es la de Z2)."""
    if resolutor is None:
        return {}
    ultima = _filas(conn, "SELECT max(id) FROM importacion WHERE fuente = 'trnsprnt' "
                          "AND tipo = 'planning' AND estado IN ('aceptada', 'parcial')")[0][0]
    if ultima is None:
        return {}
    salida: list[tuple[int, str, str]] = []
    for posicion, objeto_id, objeto, recurso_id, recurso, proveedor_id, proveedor, cliente_id, \
            cliente in _filas(
            conn, "SELECT posicion, objeto_id, objeto_ref_doc, recurso_id, recurso_ref_doc, "
                  "proveedor_id, proveedor_ref_doc, cliente_id, cliente_ref_doc "
                  "FROM planning_turno WHERE importacion_id = ? ORDER BY posicion", (ultima,)):
        for que, fila_id, texto in (("objeto", objeto_id, objeto), ("recurso", recurso_id, recurso),
                                    ("proveedor", proveedor_id, proveedor),
                                    ("cliente", cliente_id, cliente)):
            if fila_id is None and texto and resolutor.resolver(que, texto) is None:
                salida.append((posicion, que, texto))
    return {ultima: tuple(salida)} if salida else {}


def conciliaciones(conn: sqlite3.Connection) -> tuple[Conciliacion, ...]:
    """La conciliacion viva de cada imputacion: cada turno de su celda, tal como era en la foto
    con que se concilio, y las horas que se le asignaron."""
    columnas = ", ".join(_COLUMNAS_TURNO)
    return tuple(
        Conciliacion(id=fila[0], imputacion_id=fila[1], factura_id=fila[2], horas_mil=fila[3],
                     nivel=fila[4], turno=_turno(fila[5:], None))
        for fila in _filas(
            conn, f"SELECT c.id, c.imputacion_id, i.factura_id, c.horas_mil, c.regla, {columnas} "
                  "FROM conciliacion AS c JOIN factura_imputacion AS i ON i.id = c.imputacion_id "
                  "JOIN planning_turno AS t ON t.id = c.planning_turno_id "
                  "WHERE c.retirada_en IS NULL ORDER BY c.imputacion_id, c.id"))


def ciclos(conn: sqlite3.Connection) -> tuple[Ciclo, ...]:
    """Los ciclos de facturacion de los clientes y los Objetos."""
    return tuple(Ciclo(id_, cliente_id, objeto_id, frecuencia, _fecha(ancla), dias_gracia,
                       _fecha(desde), _fecha(hasta))
                 for id_, cliente_id, objeto_id, frecuencia, ancla, dias_gracia, desde, hasta
                 in _filas(conn, "SELECT id, cliente_id, objeto_id, frecuencia, ancla, "
                                 "dias_gracia, vigente_desde, vigente_hasta "
                                 "FROM ciclo_facturacion ORDER BY id"))


# ------------------------------------------------------------ paso 11: el BTW

def periodos_btw(conn: sqlite3.Connection) -> tuple[PeriodoBtw, ...]:
    """Los trimestres presentados, con la huella de IVA declarada de cada factura (C4)."""
    declaradas: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for periodo_id, factura_id, huella in _filas(
            conn, "SELECT periodo_id, factura_id, huella FROM periodo_btw_declarada "
                  "ORDER BY periodo_id, factura_id"):
        declaradas[periodo_id].append((factura_id, huella))
    return tuple(PeriodoBtw(ano, trimestre, _fecha(presentado_en),
                            tuple(declaradas.get(id_, ())))
                 for id_, ano, trimestre, presentado_en in _filas(
                     conn, "SELECT id, ano, trimestre, presentado_en FROM periodo_btw "
                           "WHERE estado = 'presentado' ORDER BY ano, trimestre"))
