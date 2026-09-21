"""Proyeccion de facturacion a clientes desde las facturas de compra.

Lo que hay hoy son facturas de COMPRA: lo que los autonomos cobran a BMS.
Facturar a clientes es la direccion contraria, y es la mitad del negocio que
todavia no tiene pantalla.

QUE ES ESTO Y QUE NO ES

Es una PROYECCION, no una factura emitida. Se calcula a partir de lo que los
proveedores han facturado, no de las horas registradas en el programa de
planificacion. Tres consecuencias que hay que tener presentes:

1. Si un autonomo factura de mas o de menos, la proyeccion hereda ese error.
   El cruce contra el planning es lo que lo corrige, y llega en la fase 2.
2. Las horas que se pagan no son necesariamente las que se facturan. Las
   horas de viaje son el caso tipico: se pagan y no se refacturan. Por eso
   hay una lista de conceptos no facturables.
3. Una obra no es un cliente. Las facturas de compra dicen "Rijnhaven", no
   de quien es Rijnhaven. Ese mapeo es configuracion, y sin el la proyeccion
   agrupa por obra y lo dice.

Nada de aqui emite nada ni escribe en ningun sistema.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .parsing import ParseError, parse_amount

MARGEN_POR_DEFECTO = Decimal("0.35")


@dataclass
class Tarifas:
    """Configuracion de precios de venta. Editable, versionable."""

    margen_por_defecto: Decimal = MARGEN_POR_DEFECTO
    obras: dict[str, str] = field(default_factory=dict)          # obra -> cliente
    tarifas: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    no_facturable: set[str] = field(default_factory=set)

    @property
    def configurada(self) -> bool:
        return bool(self.obras or self.tarifas)

    def cliente_de(self, obra: str) -> str | None:
        return self.obras.get(obra.strip().lower())

    def tarifa_de(self, obra: str, trabajo: str) -> Decimal | None:
        clave = (obra.strip().lower(), trabajo.strip().lower())
        if clave in self.tarifas:
            return self.tarifas[clave]
        # Una tarifa sin obra vale para ese trabajo en cualquier obra.
        return self.tarifas.get(("", trabajo.strip().lower()))

    def es_facturable(self, trabajo: str) -> bool:
        return trabajo.strip().lower() not in self.no_facturable


def cargar_tarifas(ruta: str | Path | None) -> Tarifas:
    """Lee la tabla de tarifas. Sin fichero, devuelve la configuracion vacia."""
    if ruta is None:
        return Tarifas()
    ruta = Path(ruta)
    if not ruta.is_file():
        return Tarifas()

    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}

    margen = datos.get("margen_por_defecto")
    try:
        margen_dec = Decimal(str(margen)) if margen is not None else MARGEN_POR_DEFECTO
    except Exception:
        margen_dec = MARGEN_POR_DEFECTO

    obras: dict[str, str] = {}
    for nombre, cfg in (datos.get("obras") or {}).items():
        cliente = cfg.get("cliente") if isinstance(cfg, dict) else cfg
        if cliente:
            obras[str(nombre).strip().lower()] = str(cliente)

    tarifas: dict[tuple[str, str], Decimal] = {}
    for entrada in datos.get("tarifas") or []:
        if not isinstance(entrada, dict):
            continue
        try:
            valor = parse_amount(str(entrada.get("tarifa")))
        except ParseError:
            continue
        obra = str(entrada.get("obra") or "").strip().lower()
        trabajo = str(entrada.get("trabajo") or "").strip().lower()
        if trabajo:
            tarifas[(obra, trabajo)] = valor

    no_facturable = {
        str(t).strip().lower() for t in (datos.get("no_facturable") or [])
    }

    return Tarifas(
        margen_por_defecto=margen_dec, obras=obras,
        tarifas=tarifas, no_facturable=no_facturable,
    )


def _tipo_de_trabajo(descripcion: Any) -> str:
    texto = str(descripcion or "").strip().lower()
    return texto.split(",")[0].strip() or "(sin descripcion)"


def _dec(raw: Any) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        return parse_amount(str(raw))
    except ParseError:
        return None


def _num(v: Decimal | None) -> float | None:
    return None if v is None else float(v)


def proyectar(
    registros: list[dict[str, Any]], tarifas: Tarifas
) -> dict[str, Any]:
    """Agrupa las horas compradas por cliente, obra y semana, y les pone precio."""
    grupos: dict[tuple[str, str, str], dict[str, Any]] = {}
    sin_mapear: set[str] = set()
    descartadas: dict[str, Decimal] = defaultdict(Decimal)

    for registro in registros:
        x = registro.get("extraction") or {}
        fichero = registro.get("source_name", "—")
        proveedor = x.get("supplier_name") or "(sin nombre)"

        for linea in x.get("lines") or []:
            unidad = (linea.get("unit") or "").lower()
            if not unidad.startswith("uur"):
                continue  # solo horas: dias y piezas no se proyectan asi

            horas = _dec(linea.get("quantity_raw"))
            coste_hora = _dec(linea.get("unit_rate_raw"))
            obra = str(linea.get("location") or "").strip()
            if horas is None or coste_hora is None or not obra:
                continue

            trabajo = _tipo_de_trabajo(linea.get("description"))
            if not tarifas.es_facturable(trabajo):
                descartadas[trabajo] += horas
                continue

            cliente = tarifas.cliente_de(obra)
            if cliente is None:
                sin_mapear.add(obra)
                cliente = f"(obra sin cliente: {obra})"

            semana = linea.get("week_number")
            clave_semana = f"W{int(semana):02d}" if isinstance(semana, int) else "—"

            tarifa_venta = tarifas.tarifa_de(obra, trabajo)
            if tarifa_venta is not None:
                origen = "tabla"
            else:
                tarifa_venta = (coste_hora * (Decimal(1) + tarifas.margen_por_defecto))
                tarifa_venta = tarifa_venta.quantize(Decimal("0.01"))
                origen = "margen"

            grupo = grupos.setdefault((cliente, obra, clave_semana), {
                "cliente": cliente, "obra": obra, "semana": clave_semana,
                "lineas": {}, "facturas_origen": set(), "proveedores": set(),
            })
            grupo["facturas_origen"].add(fichero)
            grupo["proveedores"].add(proveedor)

            entrada = grupo["lineas"].setdefault(trabajo, {
                "trabajo": trabajo, "horas": Decimal(0),
                "coste": Decimal(0), "venta": Decimal(0),
                "tarifa_venta": tarifa_venta, "origen_tarifa": origen,
                "tarifas_coste": set(),
            })
            entrada["horas"] += horas
            entrada["coste"] += (horas * coste_hora).quantize(Decimal("0.01"))
            entrada["venta"] += (horas * tarifa_venta).quantize(Decimal("0.01"))
            entrada["tarifas_coste"].add(coste_hora)

    propuestas = []
    for (cliente, obra, semana), grupo in sorted(grupos.items()):
        lineas = []
        horas = coste = venta = Decimal(0)
        avisos: list[str] = []

        for entrada in sorted(grupo["lineas"].values(), key=lambda e: e["trabajo"]):
            horas += entrada["horas"]
            coste += entrada["coste"]
            venta += entrada["venta"]
            if len(entrada["tarifas_coste"]) > 1:
                avisos.append(
                    f"{entrada['trabajo']}: el coste de la hora varia entre "
                    + " y ".join(f"{t:.2f}" for t in sorted(entrada["tarifas_coste"]))
                )
            lineas.append({
                "trabajo": entrada["trabajo"],
                "horas": _num(entrada["horas"]),
                "coste": _num(entrada["coste"]),
                "venta": _num(entrada["venta"]),
                "tarifa_venta": _num(entrada["tarifa_venta"]),
                "origen_tarifa": entrada["origen_tarifa"],
            })

        if cliente.startswith("(obra sin cliente"):
            avisos.append("La obra no tiene cliente asignado en la tabla de tarifas")

        margen = venta - coste
        propuestas.append({
            "cliente": cliente, "obra": obra, "semana": semana,
            "lineas": lineas,
            "horas": _num(horas), "coste": _num(coste), "venta": _num(venta),
            "margen": _num(margen),
            "margen_pct": float(margen / venta * 100) if venta else None,
            "facturas_origen": sorted(grupo["facturas_origen"]),
            "proveedores": sorted(grupo["proveedores"]),
            "avisos": avisos,
        })

    propuestas.sort(key=lambda p: (p["semana"], p["cliente"], p["obra"]), reverse=True)

    total_coste = sum((Decimal(str(p["coste"])) for p in propuestas), Decimal(0))
    total_venta = sum((Decimal(str(p["venta"])) for p in propuestas), Decimal(0))
    total_horas = sum((Decimal(str(p["horas"])) for p in propuestas), Decimal(0))

    return {
        "configurada": tarifas.configurada,
        "margen_por_defecto": float(tarifas.margen_por_defecto),
        "propuestas": propuestas,
        "sin_mapear": sorted(sin_mapear),
        "no_facturable": [
            {"trabajo": t, "horas": _num(h)} for t, h in sorted(descartadas.items())
        ],
        "totales": {
            "propuestas": len(propuestas),
            "clientes": len({p["cliente"] for p in propuestas}),
            "horas": _num(total_horas),
            "coste": _num(total_coste),
            "venta": _num(total_venta),
            "margen": _num(total_venta - total_coste),
            "margen_pct": float((total_venta - total_coste) / total_venta * 100)
            if total_venta else None,
        },
    }


def lineas_para_simulador(
    registros: list[dict[str, Any]], tarifas: Tarifas | None = None
) -> dict[str, Any]:
    """Lineas de compra en crudo, para simular precios en el navegador.

    El simulador recalcula en vivo cuando se toca una tarifa, asi que necesita
    las lineas sin agrupar. La agrupacion y el precio los hace el cliente.
    """
    tarifas = tarifas or Tarifas()
    lineas: list[dict[str, Any]] = []
    obras: set[str] = set()
    trabajos: set[str] = set()

    for registro in registros:
        x = registro.get("extraction") or {}
        proveedor = x.get("supplier_name") or "(sin nombre)"
        fecha = x.get("invoice_date") or ""
        for linea in x.get("lines") or []:
            if not (linea.get("unit") or "").lower().startswith("uur"):
                continue
            horas = _dec(linea.get("quantity_raw"))
            coste = _dec(linea.get("unit_rate_raw"))
            obra = str(linea.get("location") or "").strip()
            if horas is None or coste is None or not obra:
                continue
            trabajo = _tipo_de_trabajo(linea.get("description"))
            semana = linea.get("week_number")
            obras.add(obra)
            trabajos.add(trabajo)
            lineas.append({
                "proveedor": proveedor,
                "fichero": registro.get("source_name", "—"),
                "obra": obra,
                "trabajo": trabajo,
                "semana": f"W{int(semana):02d}" if isinstance(semana, int) else "—",
                "fecha": fecha,
                "horas": _num(horas),
                "coste_hora": _num(coste),
            })

    combinaciones = sorted({(l["obra"], l["trabajo"]) for l in lineas})
    return {
        "lineas": lineas,
        "obras": sorted(obras),
        "trabajos": sorted(trabajos),
        "combinaciones": [{"obra": o, "trabajo": t} for o, t in combinaciones],
        "sugerido": {
            "margen": float(tarifas.margen_por_defecto),
            "obras": {o: tarifas.cliente_de(o) or "" for o in sorted(obras)},
            "tarifas": {
                f"{o}|{t}": _num(tarifas.tarifa_de(o, t))
                for o, t in combinaciones
            },
            "no_facturable": sorted(tarifas.no_facturable),
        },
    }
