"""Agregacion del historico de facturas para el panel.

El informe por fichas contesta "que dice esta factura". Esto contesta "que
esta pasando": cuanto se gasta, con quien, como evoluciona, y que hay raro.

Todas las deteccion de anomalias de aqui son deterministas y cruzan el
historico completo, que es lo que una factura mirada de una en una no puede
ver: un duplicado, un periodo repetido o una tarifa que cambio.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from .checks import run_checks
from .parsing import ParseError, parse_amount, parse_iso_date

VENTANA_DUPLICADO = timedelta(days=14)

SEVERIDAD_ORDEN = {"critico": 0, "revisar": 1, "aviso": 2}


@dataclass
class Alerta:
    severidad: str  # critico | revisar | aviso
    regla: str
    titulo: str
    detalle: str
    facturas: list[str] = field(default_factory=list)


@dataclass
class Fila:
    """Una factura, aplanada para la tabla."""

    fichero: str
    proveedor: str
    numero: str
    fecha: str
    fecha_orden: str
    periodo: str
    ubicaciones: str
    semanas: str
    horas: Decimal | None
    base: Decimal | None
    iva: Decimal | None
    total: Decimal | None
    regimen: str
    iban: str
    vencimiento: str
    estado: str  # ok | revisar | critico
    motivos: list[str]


def _dec(raw: Any) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        return parse_amount(str(raw))
    except ParseError:
        return None


def _fecha(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    try:
        return parse_iso_date(str(raw))
    except ParseError:
        return None


def _horas(extraction: dict[str, Any]) -> Decimal | None:
    total = Decimal(0)
    visto = False
    for linea in extraction.get("lines") or []:
        if (linea.get("unit") or "").lower().startswith("uur"):
            cantidad = _dec(linea.get("quantity_raw"))
            if cantidad is not None:
                total += cantidad
                visto = True
    return total if visto else None


def _unicos(valores: list[Any]) -> str:
    vistos: list[str] = []
    for v in valores:
        if v in (None, "") or str(v) in vistos:
            continue
        vistos.append(str(v))
    return " · ".join(vistos) if vistos else "—"


def construir_filas(registros: list[dict[str, Any]]) -> list[Fila]:
    filas: list[Fila] = []
    for registro in registros:
        x = registro.get("extraction") or {}
        comprobaciones = run_checks(x)
        motivos = [f"{c.label}: {c.detail}" for c in comprobaciones if c.failed]

        dudosos = x.get("low_confidence_fields") or []
        if dudosos:
            motivos.append("Lectura dudosa en " + ", ".join(dudosos))
        if x.get("document_notes"):
            motivos.append("El documento lleva texto marcado para revisar")

        critico = any(c.failed for c in comprobaciones)
        estado = "critico" if critico else ("revisar" if motivos else "ok")

        inicio, fin = x.get("service_period_start"), x.get("service_period_end")
        periodo = f"{inicio or '?'} a {fin or '?'}" if (inicio or fin) else "—"

        lineas = x.get("lines") or []
        filas.append(
            Fila(
                fichero=registro.get("source_name", "—"),
                proveedor=x.get("supplier_name") or "(sin nombre)",
                numero=x.get("invoice_number") or "—",
                fecha=x.get("invoice_date") or "—",
                fecha_orden=x.get("invoice_date") or "0000-00-00",
                periodo=periodo,
                ubicaciones=_unicos([l.get("location") for l in lineas]),
                semanas=_unicos([l.get("week_number") for l in lineas]),
                horas=_horas(x),
                base=_dec(x.get("subtotal_excl_vat_raw")),
                iva=_dec(x.get("vat_amount_raw")),
                total=_dec(x.get("total_incl_vat_raw")),
                regimen=x.get("vat_regime") or "unknown",
                iban=(x.get("iban") or "—"),
                vencimiento=x.get("due_date") or "—",
                estado=estado,
                motivos=motivos,
            )
        )
    filas.sort(key=lambda f: f.fecha_orden, reverse=True)
    return filas


def por_mes(filas: list[Fila]) -> list[dict[str, Any]]:
    """Serie temporal de gasto. Incluye los meses vacios del rango."""
    acumulado: dict[str, list[Any]] = defaultdict(lambda: [0, Decimal(0)])
    for fila in filas:
        if fila.fecha_orden == "0000-00-00" or fila.total is None:
            continue
        clave = fila.fecha_orden[:7]
        acumulado[clave][0] += 1
        acumulado[clave][1] += fila.total

    if not acumulado:
        return []

    meses = sorted(acumulado)
    salida: list[dict[str, Any]] = []
    ano, mes = int(meses[0][:4]), int(meses[0][5:7])
    fin_ano, fin_mes = int(meses[-1][:4]), int(meses[-1][5:7])
    while (ano, mes) <= (fin_ano, fin_mes):
        clave = f"{ano:04d}-{mes:02d}"
        cuenta, total = acumulado.get(clave, [0, Decimal(0)])
        salida.append({"mes": clave, "facturas": cuenta, "total": total})
        mes += 1
        if mes == 13:
            ano, mes = ano + 1, 1
    return salida


def por_proveedor(filas: list[Fila]) -> list[dict[str, Any]]:
    acumulado: dict[str, dict[str, Any]] = {}
    for fila in filas:
        entrada = acumulado.setdefault(
            fila.proveedor,
            {"proveedor": fila.proveedor, "facturas": 0, "total": Decimal(0),
             "horas": Decimal(0), "primera": None, "ultima": None, "avisos": 0},
        )
        entrada["facturas"] += 1
        if fila.total is not None:
            entrada["total"] += fila.total
        if fila.horas is not None:
            entrada["horas"] += fila.horas
        if fila.estado != "ok":
            entrada["avisos"] += 1
        if fila.fecha_orden != "0000-00-00":
            if entrada["primera"] is None or fila.fecha_orden < entrada["primera"]:
                entrada["primera"] = fila.fecha_orden
            if entrada["ultima"] is None or fila.fecha_orden > entrada["ultima"]:
                entrada["ultima"] = fila.fecha_orden
    return sorted(acumulado.values(), key=lambda e: e["total"], reverse=True)


def por_regimen(filas: list[Fila]) -> list[dict[str, Any]]:
    etiquetas = {
        "standard": "IVA repercutido",
        "reverse_charged": "IVA trasladado",
        "kor_exempt": "Exenta por KOR",
        "unknown": "Sin determinar",
    }
    acumulado: dict[str, dict[str, Any]] = {}
    for fila in filas:
        entrada = acumulado.setdefault(
            fila.regimen,
            {"clave": fila.regimen, "etiqueta": etiquetas.get(fila.regimen, fila.regimen),
             "facturas": 0, "total": Decimal(0)},
        )
        entrada["facturas"] += 1
        if fila.total is not None:
            entrada["total"] += fila.total
    return sorted(acumulado.values(), key=lambda e: e["total"], reverse=True)


def detectar_duplicados(filas: list[Fila]) -> list[Alerta]:
    """Reglas B2 y B3: lo que solo se ve cruzando el historico."""
    alertas: list[Alerta] = []

    # B2: mismo proveedor y mismo numero.
    por_clave: dict[tuple[str, str], list[Fila]] = defaultdict(list)
    for fila in filas:
        if fila.numero != "—":
            por_clave[(fila.proveedor, fila.numero)].append(fila)
    for (proveedor, numero), grupo in sorted(por_clave.items()):
        if len(grupo) > 1:
            alertas.append(Alerta(
                "critico", "B2", "Numero de factura repetido",
                f"{proveedor} tiene {len(grupo)} facturas con el numero {numero}.",
                [f.fichero for f in grupo],
            ))

    # B3: mismo proveedor, mismo importe, pocos dias de diferencia, numero distinto.
    por_proveedor_: dict[str, list[Fila]] = defaultdict(list)
    for fila in filas:
        if fila.total is not None and fila.fecha_orden != "0000-00-00":
            por_proveedor_[fila.proveedor].append(fila)
    for proveedor, grupo in sorted(por_proveedor_.items()):
        grupo = sorted(grupo, key=lambda f: f.fecha_orden)
        for i, a in enumerate(grupo):
            for b in grupo[i + 1:]:
                if a.numero == b.numero or a.total != b.total:
                    continue
                fa, fb = _fecha(a.fecha_orden), _fecha(b.fecha_orden)
                if fa is None or fb is None or (fb - fa) > VENTANA_DUPLICADO:
                    break
                alertas.append(Alerta(
                    "revisar", "B3", "Posible duplicado por contenido",
                    f"{proveedor}: {a.numero} y {b.numero} suman lo mismo "
                    f"({b.total:,.2f}) con {(fb - fa).days} dias de diferencia.",
                    [a.fichero, b.fichero],
                ))
    return alertas


def detectar_periodos_repetidos(filas: list[Fila]) -> list[Alerta]:
    """Regla B4: la misma semana facturada dos veces."""
    alertas: list[Alerta] = []
    por_clave: dict[tuple[str, str], list[Fila]] = defaultdict(list)
    for fila in filas:
        if fila.periodo != "—":
            por_clave[(fila.proveedor, fila.periodo)].append(fila)
    for (proveedor, periodo), grupo in sorted(por_clave.items()):
        if len(grupo) > 1:
            alertas.append(Alerta(
                "critico", "B4", "Periodo facturado dos veces",
                f"{proveedor} ha facturado el periodo {periodo} en "
                f"{len(grupo)} facturas distintas.",
                [f.fichero for f in grupo],
            ))
    return alertas


def _tipo_de_trabajo(descripcion: Any) -> str:
    """Normaliza la descripcion de una linea a su tipo de trabajo.

    "Montagewerk, locatie Schiedam" y "Reisuren, locatie Schiedam" son la
    misma obra pero trabajos distintos, y cobrarlos a tarifas distintas es lo
    normal. Sin esta distincion, cada factura con horas de viaje dispara una
    alerta de cambio de tarifa, y una alerta que salta siempre se ignora.
    """
    texto = str(descripcion or "").strip().lower()
    return texto.split(",")[0].strip() or "(sin descripcion)"


def detectar_cambios_de_tarifa(registros: list[dict[str, Any]]) -> list[Alerta]:
    """Regla G3 en su version disponible hoy: la tarifa cambia sin el planning.

    Sin el programa de planificacion no se puede comprobar contra la tarifa
    pactada, pero si se puede ver que un proveedor cobra dos tarifas distintas
    por el mismo trabajo en la misma ubicacion, en facturas distintas.

    Solo se compara entre facturas: dos tarifas dentro de una misma factura
    son normalmente dos conceptos, no un cambio.
    """
    tarifas: dict[tuple[str, str, str], dict[Decimal, list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for registro in registros:
        x = registro.get("extraction") or {}
        proveedor = x.get("supplier_name") or "(sin nombre)"
        fecha = x.get("invoice_date") or "0000-00-00"
        fichero = registro.get("source_name", "—")
        for linea in x.get("lines") or []:
            tarifa = _dec(linea.get("unit_rate_raw"))
            ubicacion = linea.get("location")
            if tarifa is None or not ubicacion:
                continue
            clave = (proveedor, str(ubicacion), _tipo_de_trabajo(linea.get("description")))
            tarifas[clave][tarifa].append((fecha, fichero))

    alertas: list[Alerta] = []
    for (proveedor, ubicacion, trabajo), por_tarifa in sorted(tarifas.items()):
        if len(por_tarifa) < 2:
            continue
        # Solo cuenta si las tarifas distintas vienen de facturas distintas.
        ficheros_por_tarifa = {t: {f for _, f in v} for t, v in por_tarifa.items()}
        if len(set().union(*ficheros_por_tarifa.values())) < 2:
            continue
        distintas = sorted(por_tarifa)
        fechas = sorted(fecha for lista in por_tarifa.values() for fecha, _ in lista)
        alertas.append(Alerta(
            "revisar", "G3", "Tarifa distinta por el mismo trabajo",
            f"{proveedor}, {trabajo} en {ubicacion}: " +
            " y ".join(f"{t:,.2f}" for t in distintas) +
            f" entre {fechas[0]} y {fechas[-1]}.",
            sorted(set().union(*ficheros_por_tarifa.values())),
        ))
    return alertas


def detectar_ibanes(registros: list[dict[str, Any]]) -> list[Alerta]:
    """Un proveedor con mas de un IBAN en el historico. Parada dura F3."""
    ibanes: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for registro in registros:
        x = registro.get("extraction") or {}
        proveedor = x.get("supplier_name") or "(sin nombre)"
        iban = (x.get("iban") or "").replace(" ", "").upper()
        if iban:
            ibanes[proveedor][iban].append(registro.get("source_name", "—"))

    alertas: list[Alerta] = []
    for proveedor, cuentas in sorted(ibanes.items()):
        if len(cuentas) > 1:
            alertas.append(Alerta(
                "critico", "F3", "Mas de un IBAN para el mismo proveedor",
                f"{proveedor} aparece con {len(cuentas)} cuentas distintas: " +
                ", ".join(sorted(cuentas)) +
                ". Verificacion telefonica al numero ya conocido antes de pagar.",
                sorted({f for lista in cuentas.values() for f in lista}),
            ))
    return alertas


def construir_alertas(
    filas: list[Fila], registros: list[dict[str, Any]]
) -> list[Alerta]:
    alertas: list[Alerta] = []
    alertas += detectar_ibanes(registros)
    alertas += detectar_duplicados(filas)
    alertas += detectar_periodos_repetidos(filas)
    alertas += detectar_cambios_de_tarifa(registros)

    for fila in filas:
        for motivo in fila.motivos:
            severidad = "critico" if fila.estado == "critico" else "revisar"
            alertas.append(Alerta(
                severidad, "—", motivo.split(":")[0],
                f"{fila.proveedor} {fila.numero}: {motivo}", [fila.fichero],
            ))

    alertas.sort(key=lambda a: (SEVERIDAD_ORDEN.get(a.severidad, 9), a.regla, a.titulo))
    return alertas


def _num(value: Decimal | None) -> float | None:
    """Decimal a float solo en la frontera de serializacion.

    Los calculos van en Decimal. El JSON que consume el navegador necesita
    numeros, y a estas alturas ya no se opera con ellos: solo se pintan.
    """
    return None if value is None else float(value)


def construir_datos(registros: list[dict[str, Any]]) -> dict[str, Any]:
    """Todo lo que el panel necesita, listo para serializar a JSON."""
    filas = construir_filas(registros)
    alertas = construir_alertas(filas, registros)

    coste = Decimal(0)
    for registro in registros:
        uso = registro.get("usage") or {}
        from .pricing import estimate_cost

        estimado = estimate_cost(
            registro.get("model", ""),
            uso.get("input_tokens") or 0,
            uso.get("output_tokens") or 0,
        )
        if estimado is not None:
            coste += estimado

    total = sum((f.total for f in filas if f.total is not None), Decimal(0))
    horas = sum((f.horas for f in filas if f.horas is not None), Decimal(0))
    iva = sum((f.iva for f in filas if f.iva is not None), Decimal(0))

    return {
        "filas": [
            {
                "fichero": f.fichero, "proveedor": f.proveedor, "numero": f.numero,
                "fecha": f.fecha, "orden": f.fecha_orden, "periodo": f.periodo,
                "ubicaciones": f.ubicaciones, "semanas": f.semanas,
                "horas": _num(f.horas), "base": _num(f.base), "iva": _num(f.iva),
                "total": _num(f.total), "regimen": f.regimen, "iban": f.iban,
                "vencimiento": f.vencimiento, "estado": f.estado, "motivos": f.motivos,
            }
            for f in filas
        ],
        "por_mes": [
            {"mes": m["mes"], "facturas": m["facturas"], "total": _num(m["total"])}
            for m in por_mes(filas)
        ],
        "por_proveedor": [
            {
                "proveedor": p["proveedor"], "facturas": p["facturas"],
                "total": _num(p["total"]), "horas": _num(p["horas"]),
                "primera": p["primera"], "ultima": p["ultima"], "avisos": p["avisos"],
            }
            for p in por_proveedor(filas)
        ],
        "por_regimen": [
            {"clave": r["clave"], "etiqueta": r["etiqueta"],
             "facturas": r["facturas"], "total": _num(r["total"])}
            for r in por_regimen(filas)
        ],
        "alertas": [
            {"severidad": a.severidad, "regla": a.regla, "titulo": a.titulo,
             "detalle": a.detalle, "facturas": a.facturas}
            for a in alertas
        ],
        "totales": {
            "facturas": len(filas),
            "importe": _num(total),
            "iva": _num(iva),
            "horas": _num(horas),
            "proveedores": len({f.proveedor for f in filas}),
            "criticas": sum(1 for a in alertas if a.severidad == "critico"),
            "por_revisar": sum(1 for f in filas if f.estado != "ok"),
            "coste_lectura": _num(coste),
            "desde": min((f.fecha_orden for f in filas if f.fecha_orden != "0000-00-00"), default=None),
            "hasta": max((f.fecha_orden for f in filas if f.fecha_orden != "0000-00-00"), default=None),
        },
    }
