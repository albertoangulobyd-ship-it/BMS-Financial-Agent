"""Las facturas de venta de un listado de Exact: de filas sueltas a facturas enteras (spec §9).

Un listado de facturas de venta con lineas trae una fila por linea, con los
datos de la factura repetidos en cada una. Esto las junta: puro, como el
lector que las lee (tabular.py), y sin escribir nada.

- Las filas de una misma factura (su id de Exact o, si no lo trae, su
  numero) tienen que decir lo mismo de la cabecera. Si una dice otro cliente,
  otra fecha u otro total, no se elige: la factura se rechaza, y con ella el
  fichero (las facturas de venta entran todo o nada, decision 6).
- Dos filas con el mismo numero de linea de una factura se rechazan igual:
  una linea repetida duplicaria lo facturado.
- Los totales son los de la cabecera si el fichero los trae; si no, la suma
  de las lineas. Lo que no suma (cabecera contra lineas) no se arregla aqui:
  lo ven las reglas de aritmetica, como en una factura leida de un PDF.
- El tipo es el que dice el fichero (factura o abono); si no lo dice, el
  signo del total, como en la extraccion.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from .base import LoteLeido, Rechazo
from .canonico import (
    FacturaVentaCanonica,
    FilaVentaCanonica,
    IvaVentaCanonico,
    LineaVentaCanonica,
)

TIPO = "facturas_venta"
# Lo que es de la factura y no de la linea: todas sus filas lo dicen igual.
CABECERA = ("numero", "tipo", "cliente_ref", "cliente_nombre", "cliente_btw", "contacto",
            "fecha_factura", "fecha_vencimiento", "condiciones_pago", "periodo_inicio",
            "periodo_fin", "tratamiento_iva", "base", "iva", "total", "po_ref",
            "factura_relacionada", "moneda")
_LINEA = {"orden": "orden", "descripcion": "descripcion", "objeto_ref": "objeto_ref",
          "recurso_ref": "recurso_ref", "linea_desde": "fecha_inicio",
          "linea_hasta": "fecha_fin", "cantidad": "cantidad", "cantidad_crudo": "cantidad_crudo",
          "unidad": "unidad", "tarifa": "tarifa", "tarifa_crudo": "tarifa_crudo",
          "importe": "importe", "importe_crudo": "importe_crudo", "tipo_iva": "tipo_iva",
          "cuota_iva": "cuota_iva", "linea_po_ref": "po_ref"}


def clave_factura(fila: FilaVentaCanonica) -> str:
    """De que factura es una fila: su id de Exact o, sin el, su numero."""
    return (fila.id_externo or fila.numero).strip()


def _distintas(primera: FilaVentaCanonica, fila: FilaVentaCanonica) -> list[str]:
    return [c for c in CABECERA if getattr(primera, c) != getattr(fila, c)]


def _linea(fila: FilaVentaCanonica) -> LineaVentaCanonica:
    return LineaVentaCanonica(fila=fila.fila, crudo=fila.crudo,
                              **{destino: getattr(fila, origen)
                                 for origen, destino in _LINEA.items()})


def _suma(valores: list[Decimal | None]) -> Decimal | None:
    """La suma si todas estan; si falta una, no se sabe."""
    if not valores or any(v is None for v in valores):
        return None
    return sum(valores, Decimal(0))


def _iva_por_tipo(lineas: list[LineaVentaCanonica]) -> tuple[IvaVentaCanonico, ...]:
    """El desglose por tipo, sumando las lineas. Sin el tipo de cada linea no hay desglose."""
    if not lineas or any(linea.tipo_iva is None for linea in lineas):
        return ()
    por_tipo: dict[Decimal, list[LineaVentaCanonica]] = defaultdict(list)
    for linea in lineas:
        por_tipo[linea.tipo_iva].append(linea)
    return tuple(IvaVentaCanonico(tipo_iva=tipo, base=sum((x.importe for x in grupo), Decimal(0)),
                                  cuota=_suma([x.cuota_iva for x in grupo]))
                 for tipo, grupo in sorted(por_tipo.items()))


def _tipo(primera: FilaVentaCanonica, total: Decimal | None, base: Decimal) -> str:
    if primera.tipo is not None:
        return primera.tipo
    importe = total if total is not None else base
    return "nota_credito" if importe < 0 else "factura"


def _periodo(primera: FilaVentaCanonica,
             lineas: list[LineaVentaCanonica]) -> tuple[Any, Any]:
    """El periodo de la cabecera o, si no lo trae, de la primera a la ultima fecha de sus lineas."""
    if primera.periodo_inicio is not None or primera.periodo_fin is not None:
        return primera.periodo_inicio, primera.periodo_fin
    inicios = [x.fecha_inicio for x in lineas if x.fecha_inicio is not None]
    fines = [x.fecha_fin or x.fecha_inicio for x in lineas
             if (x.fecha_fin or x.fecha_inicio) is not None]
    return (min(inicios) if inicios else None), (max(fines) if fines else None)


def factura(filas: list[FilaVentaCanonica]) -> FacturaVentaCanonica:
    """Una factura de sus filas, ya comprobadas (misma cabecera, lineas sin repetir)."""
    primera = filas[0]
    lineas = sorted((_linea(f) for f in filas), key=lambda x: x.orden)
    base = primera.base if primera.base is not None else sum((x.importe for x in lineas),
                                                             Decimal(0))
    iva = primera.iva if primera.iva is not None else _suma([x.cuota_iva for x in lineas])
    total = primera.total
    if total is None and iva is not None:
        total = base + iva
    inicio, fin = _periodo(primera, lineas)
    referencias = (primera.po_ref,) if primera.po_ref else ()
    return FacturaVentaCanonica(
        fila=primera.fila, crudo=primera.crudo, id_externo=clave_factura(primera),
        numero=primera.numero, tipo=_tipo(primera, total, base),
        cliente_ref=primera.cliente_ref, cliente_nombre=primera.cliente_nombre,
        cliente_btw=primera.cliente_btw, contacto=primera.contacto,
        fecha_factura=primera.fecha_factura, fecha_vencimiento=primera.fecha_vencimiento,
        condiciones_pago=primera.condiciones_pago, periodo_inicio=inicio, periodo_fin=fin,
        tratamiento_iva=primera.tratamiento_iva, base=base,
        base_crudo=primera.base_crudo if primera.base is not None else None,
        iva=iva, iva_crudo=primera.iva_crudo if primera.iva is not None else None,
        total=total, total_crudo=primera.total_crudo if primera.total is not None else None,
        iva_por_tipo=_iva_por_tipo(lineas), referencias=referencias,
        factura_relacionada=primera.factura_relacionada, moneda=primera.moneda,
        lineas=tuple(lineas))


def _comprobar(filas: list[FilaVentaCanonica]) -> list[Rechazo]:
    """Lo que impide juntar las filas de una factura: otra cabecera, una linea repetida."""
    primera = filas[0]
    rechazos = []
    vistas: set[int] = set()
    for fila in filas:
        distintas = _distintas(primera, fila)
        if distintas:
            rechazos.append(Rechazo(
                fila.fila, f"la factura {primera.numero} dice otro {', '.join(distintas)} que en "
                           f"la fila {primera.fila}: no se elige", dict(fila.crudo)))
        if fila.orden in vistas:
            rechazos.append(Rechazo(fila.fila, f"la linea {fila.orden} de la factura "
                                               f"{primera.numero} esta repetida",
                                    dict(fila.crudo), "duplicada"))
        vistas.add(fila.orden)
    return rechazos


def facturas_de_filas(lote: LoteLeido) -> LoteLeido:
    """El lote de filas de un listado de ventas, como lote de facturas enteras."""
    grupos: dict[str, list[FilaVentaCanonica]] = defaultdict(list)
    for fila in lote.registros:
        grupos[clave_factura(fila)].append(fila)
    facturas, rechazos = [], list(lote.rechazos)
    for filas in grupos.values():
        problemas = _comprobar(filas)
        if problemas:
            rechazos.extend(problemas)
            continue
        try:
            facturas.append(factura(filas))
        except ValidationError as exc:
            motivo = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                               for e in exc.errors(include_url=False))
            rechazos.append(Rechazo(filas[0].fila, motivo, dict(filas[0].crudo)))
    filas_leidas = len(lote.registros) + len(lote.rechazos)
    aviso = f"{filas_leidas} fila(s) del fichero dan {len(facturas)} factura(s)"
    return replace(lote, tipo=TIPO, registros=tuple(facturas),
                   rechazos=tuple(sorted(rechazos, key=lambda r: r.fila)),
                   avisos=(*lote.avisos, aviso))
