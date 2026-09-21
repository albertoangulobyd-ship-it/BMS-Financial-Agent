"""Ensamblado del panel: un fichero HTML autocontenido.

Los datos van incrustados como JSON en la propia pagina. Es un fichero local
que se abre desde el disco: no hay servidor, no hay base de datos y no sale
nada a internet. Cuando esto se despliegue de verdad, los datos ya no viajan
en el bundle (ver portal-consulta.md): vienen de una API de solo lectura
sobre un modelo de lectura sin IBAN. Aqui, en local y sobre datos propios,
incrustarlos es lo correcto y lo mas simple.

Ningun dato de una extraccion se interpola en el HTML: todo entra por el
JSON y llega al DOM con textContent. El texto de un PDF de un tercero nunca
se concatena en markup.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .dashboard import construir_datos
from .panel_assets import CSS, JS

E = html.escape


def _cabecera(datos: dict[str, Any], generado: str) -> str:
    t = datos["totales"]
    rango = "sin facturas todavia"
    if t["desde"] and t["hasta"]:
        rango = (
            f"del {t['desde']} al {t['hasta']}"
            if t["desde"] != t["hasta"]
            else f"del {t['desde']}"
        )
    coste = t["coste_lectura"] or 0
    return (
        f"{t['facturas']} facturas {rango} · "
        f"{t['proveedores']} proveedores · "
        f"lectura ${coste:.4f} · generado el {generado}"
    )


def render_html(datos: dict[str, Any], generado: str) -> str:
    payload = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    # Dentro de un bloque script, el tokenizador de HTML reacciona a "<!--",
    # "<script" y "</script". Escapar solo "</" dejaba pasar un "<!--<script"
    # incrustado en un PDF, que abre un comentario y se come el resto del
    # bloque: el panel quedaba en blanco. Escapar todo "<" lo cierra entero, y
    # dentro de un literal JS \u003c es exactamente el mismo caracter.
    payload = payload.replace("<", "\\u003c")

    return (
        "<!doctype html>\n"
        '<html lang="es"><head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Panel de facturas · BMS Support</title>\n"
        "<style>" + CSS + "</style>\n"
        "</head><body>\n"
        '<div class="wrap">\n'
        '  <p class="eyebrow">BMS Support · Panel de administracion</p>\n'
        "  <h1>Que esta pasando</h1>\n"
        '  <p class="lede">Todas las facturas leidas por el agente, con lo que se '
        "puede comprobar cruzando el historico completo. " + _cabecera(datos, generado) + "</p>\n"
        "\n"
        '  <div class="filters">\n'
        '    <label><span>Periodo</span><select id="f-periodo">\n'
        '      <option value="">Todo el historico</option>\n'
        '      <option value="30">Ultimos 30 dias</option>\n'
        '      <option value="90">Ultimos 90 dias</option>\n'
        '      <option value="180">Ultimos 6 meses</option>\n'
        '      <option value="365">Ultimo ano</option>\n'
        "    </select></label>\n"
        '    <label><span>Proveedor</span><select id="f-proveedor">\n'
        '      <option value="">Todos</option>\n'
        "    </select></label>\n"
        '    <label><span>Estado</span><select id="f-estado">\n'
        '      <option value="">Todas</option>\n'
        '      <option value="avisos">Solo con avisos</option>\n'
        '      <option value="critico">Solo criticas</option>\n'
        "    </select></label>\n"
        '    <label><span>Buscar</span>'
        '<input type="search" id="f-q" placeholder="proveedor, numero, obra, IBAN"></label>\n'
        '    <button class="btn" id="f-csv" type="button">Exportar CSV</button>\n'
        '    <button class="btn" id="f-reset" type="button">Limpiar</button>\n'
        '    <span class="count" id="count"></span>\n'
        "  </div>\n"
        "\n"
        '  <div class="tiles" id="tiles"></div>\n'
        "\n"
        '  <section class="alerts" id="alerts" hidden>\n'
        '    <div class="alerts-h"><h2>Revisar</h2>'
        '<span class="sub" id="alerts-count"></span></div>\n'
        '    <div id="alerts-body"></div>\n'
        "  </section>\n"
        "\n"
        '  <div class="charts">\n'
        '    <div class="card">\n'
        "      <h2>Gasto por mes</h2>\n"
        '      <p class="hint">Base imponible, no total con IVA: un proveedor con el '
        "IVA trasladado no lleva cuota y otro al 21% si, asi que el total premiaria al "
        "regimen y no al gasto. Los meses sin facturas salen vacios.</p>\n"
        '      <div class="chart" id="chart-meses"><div class="tip"></div></div>\n'
        "    </div>\n"
        '    <div class="card">\n'
        "      <h2>Por proveedor</h2>\n"
        '      <p class="hint">Base imponible acumulada en el periodo filtrado.</p>\n'
        '      <div class="chart" id="chart-prov"><div class="tip"></div></div>\n'
        "    </div>\n"
        "  </div>\n"
        "\n"
        '  <div class="card" style="margin:0 0 22px">\n'
        "    <h2>Reparto por regimen de IVA</h2>\n"
        '    <p class="hint">Importante para la declaracion trimestral: el IVA '
        "trasladado y la KOR no llevan cuota deducible.</p>\n"
        '    <div class="stack" id="stack"></div>\n'
        '    <div class="legend" id="legend"></div>\n'
        "  </div>\n"
        "\n"
        '  <div class="card" style="margin:0 0 22px">\n'
        "    <h2>Semanas facturadas por proveedor</h2>\n"
        '    <p class="hint">Cada columna es una semana ISO. Una celda vacia es una '
        "semana sin factura de ese proveedor; dos o mas facturas en la misma celda "
        "salen marcadas. Sin el planning no se sabe si el hueco es que no trabajo o "
        "que no ha facturado, pero si a quien llamar. Pulsa una celda para filtrar.</p>\n"
        '    <div class="chart" id="matrix"><div class="tip"></div></div>\n'
        "  </div>\n"
        "\n"
        '  <section class="tablecard">\n'
        "    <header><h2>Todas las facturas</h2>\n"
        '      <p class="hint" style="margin:0">Pulsa una cabecera para ordenar. '
        "El punto de la izquierda marca el estado.</p>\n"
        "    </header>\n"
        '    <div class="tw"><table>\n'
        '      <thead id="thead"></thead><tbody id="tbody"></tbody><tfoot id="tfoot"></tfoot>\n'
        "    </table></div>\n"
        "  </section>\n"
        "\n"
        '  <footer class="page">Fichero local generado desde las extracciones. '
        "No se ha enviado nada a ninguna parte. Los importes son los que dicen las "
        "facturas, sin contrastar todavia con el planning ni con Exact.</footer>\n"
        "</div>\n"
        "<script>\nconst DATOS = " + payload + ";\n" + JS + "\n</script>\n"
        "</body></html>\n"
    )


def escribir_panel(
    registros: list[dict[str, Any]], destino: str | Path, generado: str | None = None
) -> Path:
    datos = construir_datos(registros)
    marca = generado or datetime.now().strftime("%d/%m/%Y %H:%M")
    destino = Path(destino)
    destino.write_text(render_html(datos, marca), encoding="utf-8")
    return destino
