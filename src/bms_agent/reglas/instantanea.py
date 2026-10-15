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
y los dias en que cada factura con algun pago estuvo Bloqueada.
Solo lee: lo que escribe el registro de cuentas es cuentas.py, y nada de la
via de entrada de los documentos llega alli.

Leer de golpe (una consulta por tabla, sin sqlite3.Row) es lo que permite
recalcular cinco mil facturas en menos de dos segundos.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable
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
    Cuenta,
    EventoCuenta,
    Extracto,
    Factura,
    Instantanea,
    Linea,
    LineaSinCasar,
    Lote,
    Movimiento,
    Parte,
    Politica,
    Relacion,
    TramoIva,
)
from .pagos import saldo, tolerancia_cent
from .normas import (
    normalizar_btw,
    normalizar_iban,
    normalizar_kvk,
    normalizar_nombre,
    normalizar_telefono,
)

_COLUMNAS_FACTURA = (
    "f.id", "f.sentido", "f.tipo", "f.numero", "f.numero_norm", "f.proveedor_id", "f.cliente_id",
    "f.emisor_nombre_doc", "f.emisor_kvk_doc", "f.emisor_btw_doc", "f.receptor_nombre_doc",
    "f.receptor_btw_doc", "f.fecha_factura", "f.periodo_inicio", "f.periodo_fin", "f.base_cent",
    "f.iva_cent", "f.total_cent", "f.tipo_iva_pb", "f.tratamiento_iva", "f.iban_doc",
    "f.moneda_doc", "f.anulada", "f.fusionada_en_id", "e.schema_version",
    "f.documento_id", "f.emisor_direccion_doc", "f.kor_mencionada", "f.notas_doc",
    "f.origen = 'extraccion' AND d.ruta_cas IS NULL",
)

_COLUMNAS_LINEA = (
    "id", "factura_id", "orden", "descripcion_doc", "objeto_doc", "unidad", "cantidad_mil",
    "tarifa_e4", "importe_cent", "tipo_iva_pb", "fecha_inicio", "fecha_fin", "fecha_trabajo",
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


def _objeto_de_linea(conn: sqlite3.Connection) -> dict[int, int]:
    """El Objeto resuelto de cada linea con una sola imputacion activa.

    Una linea dividida en varias imputaciones no nombra un Objeto solo; ahi
    vale lo impreso.
    """
    por_linea: dict[int, list[int | None]] = defaultdict(list)
    for linea_id, objeto_id in _filas(
            conn, "SELECT linea_id, objeto_id FROM factura_imputacion "
                  "WHERE retirada_en IS NULL AND linea_id IS NOT NULL"):
        por_linea[linea_id].append(objeto_id)
    return {l: o[0] for l, o in por_linea.items() if len(o) == 1 and o[0] is not None}


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
    objetos = _objeto_de_linea(conn)
    vacio: frozenset[str] = frozenset()
    clave_objeto, clave_de_parte = _recordar(_clave_objeto), _recordar(clave_parte)
    no_solicitados = _recordar(_no_solicitados)

    lineas: dict[int, list[Linea]] = defaultdict(list)
    for fila in _filas(conn, f"SELECT {', '.join(_COLUMNAS_LINEA)} FROM factura_linea "
                             "WHERE retirada_en IS NULL ORDER BY factura_id, orden, id"):
        (id_, factura_id, orden, descripcion, objeto_doc, unidad, cantidad, tarifa, importe,
         tipo_iva, inicio, fin, trabajo) = fila
        lineas[factura_id].append(Linea(
            id=id_, orden=orden, descripcion_doc=descripcion, objeto_doc=objeto_doc,
            unidad=unidad, cantidad_mil=cantidad, tarifa_e4=tarifa, importe_cent=importe,
            tipo_iva_pb=tipo_iva, fecha_inicio=_fecha(inicio), fecha_fin=_fecha(fin),
            fecha_trabajo=_fecha(trabajo),
            objeto=clave_objeto(objetos.get(id_), objeto_doc),
            ilegibles=frozenset(ilegibles.get(("factura_linea", id_), vacio))))

    desglose: dict[int, list[TramoIva]] = defaultdict(list)
    for id_, factura_id, tipo_iva, base, cuota in _filas(
            conn, "SELECT id, factura_id, tipo_iva_pb, base_cent, cuota_cent FROM factura_iva "
                  "WHERE retirada_en IS NULL ORDER BY factura_id, id"):
        desglose[factura_id].append(TramoIva(id_, tipo_iva, base, cuota))

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
    for fila in _filas(conn, f"SELECT {', '.join(_COLUMNAS_FACTURA)} FROM factura AS f "
                             "LEFT JOIN extraccion AS e ON e.id = f.extraccion_vigente_id "
                             "LEFT JOIN documento AS d ON d.id = f.documento_id "
                             "ORDER BY f.id"):
        (id_, sentido, tipo, numero, numero_norm, proveedor_id, cliente_id, emisor_nombre,
         emisor_kvk, emisor_btw, receptor_nombre, receptor_btw, fecha_factura, inicio, fin,
         base, iva, total, tipo_iva, tratamiento, iban, moneda_doc, anulada, fusionada_en,
         schema_version, documento_id, direccion, kor, notas, sin_original) = fila
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
            **_pagado(total, por_factura.get(id_), tolerancia)))

    relaciones = tuple(Relacion(o, d, t) for o, d, t in _filas(
        conn, "SELECT origen_id, destino_id, tipo FROM factura_relacion "
              "WHERE estado = 'confirmada' AND retirada_en IS NULL ORDER BY id"))
    return Instantanea(hoy=hoy, politica=politica, facturas=tuple(facturas),
                       relaciones=relaciones, proveedores=partes(conn, "proveedor"),
                       clientes=partes(conn, "cliente"), cuentas=cuentas(conn),
                       telefonos=telefonos(conn), lotes=lotes(conn), extractos=extractos(conn),
                       movimientos=movimientos(conn), aplicaciones=pagos,
                       beneficiarios=beneficiarios(conn),
                       bloqueos=bloqueos(conn, {a.factura_id for a in pagos
                                                if a.estado == "confirmada"}))


_SIN_PAGOS = {"pagado_cent": 0, "fuente_pago": None, "pagada": False}


def _pagado(total: int | None, propias: list[Aplicacion] | None,
            tolerancia: int) -> dict[str, Any]:
    if not propias:
        return _SIN_PAGOS
    s = saldo(total, propias, tolerancia)
    return {"pagado_cent": s.pagado_cent, "fuente_pago": s.fuente, "pagada": s.pagada}


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
    columnas = ("id, nombre, kvk, btw_id, regimen_iva, activo" if tabla == "proveedor"
                else "id, nombre, kvk, btw_id, tratamiento_iva_defecto, activo")
    salida = []
    for id_, nombre, kvk, btw, regimen, activo in _filas(
            conn, f"SELECT {columnas} FROM {tabla} ORDER BY id"):
        nombres = {n for n in (normalizar_nombre(nombre),) if n} | alias.get(id_, set())
        salida.append(Parte(id=id_, tabla=tabla, nombre=nombre, nombres=frozenset(nombres),
                            kvk=normalizar_kvk(kvk), btw=normalizar_btw(btw),
                            regimen_iva=regimen, activo=bool(activo)))
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
            decision_facturas=decision))
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


def lotes(conn: sqlite3.Connection) -> tuple[Lote, ...]:
    """Las importaciones de maestros (no las de out/, que son una por documento)."""
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
                           ultimo=ultimo[(fuente, tipo)] == id_))
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


def movimientos(conn: sqlite3.Connection) -> tuple[Movimiento, ...]:
    """Los movimientos del banco. `referencia`: la estructurada o el concepto, normalizados."""
    return tuple(Movimiento(id_, extracto_id, cuenta, date.fromisoformat(fecha), importe, moneda,
                            contraparte, nombre,
                            normalizar_referencia(estructurada) or normalizar_referencia(concepto))
                 for (id_, extracto_id, cuenta, fecha, importe, moneda, contraparte, nombre,
                      estructurada, concepto) in _filas(
                     conn, "SELECT id, extracto_id, cuenta_propia_iban, fecha_contable, "
                           "importe_cent, moneda, contraparte_iban, contraparte_nombre_doc, "
                           "referencia_estructurada, concepto_doc FROM movimiento_bancario "
                           "ORDER BY id"))


def beneficiarios(conn: sqlite3.Connection) -> frozenset[str]:
    """Los IBAN de quien se paga sin ser proveedor (vigentes)."""
    return frozenset(f[0] for f in _filas(
        conn, "SELECT iban FROM beneficiario_conocido WHERE retirada_en IS NULL"))


_PENDIENTE = frozenset({"abierto", "desaparecido"})


def bloqueos(conn: sqlite3.Connection, facturas: set[int]) -> tuple[Bloqueo, ...]:
    """Los dias en que cada una de estas facturas tuvo un hallazgo que bloquea pendiente.

    Sale de la historia de cada hallazgo (hallazgo_evento): pendiente desde
    que se abre o reabre, hasta que se anula, se cierra o se resuelve. No
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
    tramos: dict[int, list[tuple[date, date | None]]] = defaultdict(list)
    abierto: dict[int, date] = {}
    for hallazgo_id, estado, en in _filas(
            conn, "SELECT hallazgo_id, estado, en FROM hallazgo_evento ORDER BY id"):
        if hallazgo_id not in hallazgos:
            continue
        if estado in _PENDIENTE:
            abierto.setdefault(hallazgo_id, _dia(en))
        elif hallazgo_id in abierto:
            tramos[hallazgo_id].append((abierto.pop(hallazgo_id), _dia(en)))
    for hallazgo_id, desde in abierto.items():
        tramos[hallazgo_id].append((desde, None))
    salida = []
    for hallazgo_id, lista in sorted(tramos.items()):
        regla, suyas = hallazgos[hallazgo_id]
        for factura_id in sorted(suyas & facturas):
            salida.extend(Bloqueo(factura_id, regla, desde, hasta) for desde, hasta in lista)
    return tuple(salida)
