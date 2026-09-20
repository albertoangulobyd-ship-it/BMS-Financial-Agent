"""Informe HTML de lo que ha extraido el agente.

Es el primer paso del portal, pero en local: un fichero que se abre en el
navegador, sin servidor, sin base de datos y sin internet. Sirve para ver lo
que el agente entendio antes de decidir nada sobre desplegar nada.

Seguridad: este informe muestra texto que viene de PDF de terceros. Todo lo
que sale de una extraccion se escapa antes de entrar en el HTML. Sin eso, un
proveedor podria meter etiquetas en el nombre de su empresa y ejecutarlas en
vuestro navegador cuando abrierais el informe. Es la misma inyeccion de
siempre, cambiando el destino.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .checks import CheckResult, run_checks
from .parsing import ParseError, parse_amount
from .pricing import estimate_cost

E = html.escape


@dataclass
class InvoiceView:
    source_name: str
    sha_short: str
    extraction: dict[str, Any]
    checks: list[CheckResult]
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    cost: Decimal | None

    @property
    def total(self) -> Decimal | None:
        raw = self.extraction.get("total_incl_vat_raw")
        if raw is None:
            return None
        try:
            return parse_amount(str(raw))
        except ParseError:
            return None

    @property
    def flags(self) -> list[str]:
        out: list[str] = []
        for check in self.checks:
            if check.failed:
                out.append(f"{check.label}: {check.detail}")
        low = self.extraction.get("low_confidence_fields") or []
        if low:
            out.append("Lectura dudosa en: " + ", ".join(low))
        return out

    @property
    def notes(self) -> str | None:
        return self.extraction.get("document_notes") or None


@dataclass
class ReportData:
    invoices: list[InvoiceView] = field(default_factory=list)
    generated_at: str = ""

    @property
    def total_amount(self) -> Decimal:
        return sum((v.total for v in self.invoices if v.total is not None), Decimal(0))

    @property
    def with_flags(self) -> int:
        return sum(1 for v in self.invoices if v.flags or v.notes)

    @property
    def total_cost(self) -> Decimal:
        return sum((v.cost for v in self.invoices if v.cost is not None), Decimal(0))


def build_view(record: dict[str, Any]) -> InvoiceView:
    extraction = record.get("extraction") or {}
    usage = record.get("usage") or {}
    model = record.get("model", "desconocido")
    tokens_in = usage.get("input_tokens") or 0
    tokens_out = usage.get("output_tokens") or 0
    return InvoiceView(
        source_name=record.get("source_name", "(sin nombre)"),
        sha_short=(record.get("source_sha256") or "")[:12],
        extraction=extraction,
        checks=run_checks(extraction),
        model=model,
        prompt_version=record.get("prompt_version", ""),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=estimate_cost(model, tokens_in, tokens_out),
    )


def load_records(out_dir: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(Path(out_dir).glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return records


def _sort_key(view: InvoiceView) -> tuple[int, str, str]:
    """Mas reciente primero. Sin fecha va al final, no mezclada por medio."""
    fecha = view.extraction.get("invoice_date") or ""
    return (0 if fecha else 1, fecha and _invert(fecha) or "", view.source_name)


def _invert(fecha: str) -> str:
    """Invierte una fecha ISO para poder ordenar descendente con sort ascendente."""
    return "".join(chr(ord("9") - int(c)) if c.isdigit() else c for c in fecha)


def build_report(records: list[dict[str, Any]]) -> ReportData:
    views = sorted((build_view(r) for r in records), key=_sort_key)
    return ReportData(
        invoices=views,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


def _euros(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _field(label: str, value: Any, mono: bool = False) -> str:
    shown = E(str(value)) if value not in (None, "") else '<span class="none">sin dato</span>'
    cls = " mono" if mono else ""
    return f'<div class="f"><dt>{E(label)}</dt><dd class="v{cls}">{shown}</dd></div>'


def _lines_table(lines: list[dict[str, Any]]) -> str:
    if not lines:
        return '<p class="none">La factura no tiene líneas desglosadas.</p>'
    rows = []
    for line in lines:
        rows.append(
            "<tr>"
            f"<td>{E(str(line.get('description') or '—'))}</td>"
            f"<td class='c'>{E(str(line.get('week_number') or '—'))}</td>"
            f"<td>{E(str(line.get('location') or '—'))}</td>"
            f"<td class='n'>{E(str(line.get('quantity_raw') or '—'))}</td>"
            f"<td class='n'>{E(str(line.get('unit_rate_raw') or '—'))}</td>"
            f"<td class='n'>{E(str(line.get('line_total_raw') or '—'))}</td>"
            "</tr>"
        )
    return (
        '<div class="tw"><table><thead><tr>'
        "<th>Descripción</th><th class='c'>Semana</th><th>Ubicación</th>"
        "<th class='n'>Cant.</th><th class='n'>Tarifa</th><th class='n'>Importe</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _checks_block(checks: list[CheckResult]) -> str:
    items = []
    for check in checks:
        items.append(
            f'<li class="chk {E(check.status.replace(" ", "-"))}">'
            f'<span class="pill">{E(check.status)}</span>'
            f'<span class="chk-b"><b>{E(check.label)}</b> '
            f'<span class="rule">{E(check.rule)}</span><br>'
            f'<span class="detail">{E(check.detail)}</span></span></li>'
        )
    return '<ul class="checks">' + "".join(items) + "</ul>"


def _invoice_card(view: InvoiceView) -> str:
    x = view.extraction
    regime = {
        "standard": "IVA repercutido",
        "reverse_charged": "IVA trasladado (btw verlegd)",
        "kor_exempt": "Exenta por KOR",
        "unknown": "No determinado",
    }.get(x.get("vat_regime") or "unknown", "No determinado")

    period = "—"
    if x.get("service_period_start") or x.get("service_period_end"):
        period = f"{x.get('service_period_start') or '?'} a {x.get('service_period_end') or '?'}"

    notes_block = ""
    if view.notes:
        notes_block = (
            '<div class="notes"><p class="notes-h">Texto del documento marcado para revisar</p>'
            f"<pre>{E(view.notes)}</pre>"
            '<p class="notes-f">Transcrito como contenido de la factura. El agente no '
            "ejecuta lo que ponga aquí, y los pagos se construyen con el IBAN del maestro "
            "de proveedores, no con el del documento.</p></div>"
        )

    flag_block = ""
    if view.flags:
        flag_block = (
            '<ul class="flags">'
            + "".join(f"<li>{E(f)}</li>" for f in view.flags)
            + "</ul>"
        )

    cost = f"${view.cost:.4f}" if view.cost is not None else "sin tarifa"

    return f"""
<article class="card">
  <header class="card-h">
    <div>
      <h2>{E(str(x.get('supplier_name') or '(proveedor sin nombre)'))}</h2>
      <p class="sub">Factura <span class="mono">{E(str(x.get('invoice_number') or '—'))}</span>
         · {E(str(x.get('invoice_date') or 'sin fecha'))}</p>
    </div>
    <div class="amount">{_euros(view.total) if view.total is not None else '—'}<span>EUR</span></div>
  </header>

  {flag_block}
  {notes_block}

  <dl class="fields">
    {_field('Periodo de prestación', period)}
    {_field('Régimen de IVA', regime)}
    {_field('KvK', x.get('kvk_number'), mono=True)}
    {_field('btw-id', x.get('vat_number'), mono=True)}
    {_field('IBAN', x.get('iban'), mono=True)}
    {_field('Vencimiento', x.get('due_date'))}
  </dl>

  {_lines_table(x.get('lines') or [])}

  <dl class="fields totals">
    {_field('Base imponible', x.get('subtotal_excl_vat_raw'), mono=True)}
    {_field('Tipo', x.get('vat_rate_raw'), mono=True)}
    {_field('Cuota de IVA', x.get('vat_amount_raw'), mono=True)}
    {_field('Total', x.get('total_incl_vat_raw'), mono=True)}
  </dl>

  <p class="sec-h">Comprobaciones aplicadas</p>
  {_checks_block(view.checks)}

  <footer class="prov">
    <span>{E(view.source_name)}</span>
    <span class="mono">{E(view.sha_short)}</span>
    <span>{E(view.model)}</span>
    <span class="mono">{E(view.prompt_version)}</span>
    <span>{view.tokens_in:,} + {view.tokens_out:,} tokens</span>
    <span>{E(cost)}</span>
  </footer>
</article>
"""


def render_html(data: ReportData) -> str:
    cards = "".join(_invoice_card(v) for v in data.invoices)
    flagged = data.with_flags
    flag_cls = "warn" if flagged else "ok"
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informe de extracción · BMS Support</title>
<style>
:root{{
  --ground:#F6F7F9; --surface:#FFFFFF; --surface-2:#EDF0F5;
  --ink:#141A23; --ink-soft:#4E5A6B; --ink-faint:#7C8798;
  --line:#DCE1E8; --line-strong:#B7C0CC;
  --accent:#1F4E8C; --accent-soft:#E7EDF7;
  --ok:#1E6B52; --ok-soft:#E3F0EB;
  --warn:#9C5A14; --warn-soft:#F7EEE0;
  --danger:#A02128; --danger-soft:#F8E8E8;
  --sans:'Archivo','Segoe UI',system-ui,sans-serif;
  --serif:'Source Serif 4',Georgia,serif;
  --mono:'IBM Plex Mono','Cascadia Mono',Consolas,monospace;
}}
@media (prefers-color-scheme:dark){{:root{{
  --ground:#0F1319; --surface:#161B23; --surface-2:#1E252F;
  --ink:#E3E9F1; --ink-soft:#9DA9BA; --ink-faint:#77838F;
  --line:#28313D; --line-strong:#3C4753;
  --accent:#7BA9E7; --accent-soft:#172335;
  --ok:#5CB795; --ok-soft:#11241E;
  --warn:#D6A05F; --warn-soft:#292014;
  --danger:#E97C84; --danger-soft:#2B1719;
}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--serif);
  font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1000px;margin:0 auto;padding:48px 20px 80px}}
.eyebrow{{font-family:var(--mono);font-size:.66rem;letter-spacing:.16em;text-transform:uppercase;
  color:var(--accent);margin:0 0 14px}}
h1{{font-family:var(--sans);font-weight:700;font-size:2.1rem;letter-spacing:-.02em;
  line-height:1.1;margin:0 0 10px}}
.lede{{color:var(--ink-soft);margin:0 0 28px}}
.strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:2px;
  margin:0 0 40px;background:var(--line);border:1px solid var(--line);border-radius:5px;overflow:hidden}}
.stat{{background:var(--surface);padding:16px 18px}}
.stat b{{display:block;font-family:var(--sans);font-size:1.5rem;font-weight:600;
  letter-spacing:-.02em;line-height:1.2;font-variant-numeric:tabular-nums}}
.stat span{{font-family:var(--mono);font-size:.63rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-faint)}}
.stat.warn b{{color:var(--warn)}} .stat.ok b{{color:var(--ok)}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:6px;
  padding:24px 26px;margin:0 0 20px}}
.card-h{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;
  flex-wrap:wrap;padding-bottom:16px;border-bottom:1px solid var(--line);margin-bottom:18px}}
.card-h h2{{font-family:var(--sans);font-weight:600;font-size:1.22rem;letter-spacing:-.012em;
  margin:0 0 5px;line-height:1.25}}
.sub{{margin:0;font-size:.92rem;color:var(--ink-soft)}}
.amount{{font-family:var(--sans);font-weight:600;font-size:1.5rem;letter-spacing:-.02em;
  white-space:nowrap;font-variant-numeric:tabular-nums}}
.amount span{{font-family:var(--mono);font-size:.6rem;letter-spacing:.1em;
  color:var(--ink-faint);margin-left:6px}}
.fields{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:14px 22px;margin:0 0 22px}}
.f{{min-width:0}}
.f dt{{font-family:var(--mono);font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink-faint);margin-bottom:3px}}
.f dd{{margin:0;font-size:.97rem;overflow-wrap:anywhere}}
.v.mono{{font-family:var(--mono);font-size:.87rem}}
.none{{color:var(--ink-faint);font-style:italic}}
.totals{{padding:16px 18px;background:var(--surface-2);border-radius:4px}}
.tw{{overflow-x:auto;margin:0 0 22px;border:1px solid var(--line);border-radius:4px}}
table{{border-collapse:collapse;width:100%;min-width:560px;font-size:.9rem}}
th,td{{text-align:left;padding:9px 13px;border-bottom:1px solid var(--line)}}
th{{font-family:var(--mono);font-weight:500;font-size:.62rem;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink-faint);background:var(--surface-2);white-space:nowrap}}
td.n,th.n{{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}}
td.c,th.c{{text-align:center;font-family:var(--mono)}}
tbody tr:last-child td{{border-bottom:none}}
.sec-h{{font-family:var(--mono);font-size:.62rem;letter-spacing:.11em;text-transform:uppercase;
  color:var(--ink-faint);margin:0 0 10px}}
.checks{{list-style:none;margin:0 0 20px;padding:0;display:flex;flex-direction:column;gap:6px}}
.chk{{display:flex;gap:12px;align-items:flex-start;padding:10px 13px;
  background:var(--surface-2);border-radius:4px}}
.chk.ok{{background:var(--ok-soft)}} .chk.fallo{{background:var(--danger-soft)}}
.pill{{font-family:var(--mono);font-size:.58rem;letter-spacing:.09em;text-transform:uppercase;
  padding:3px 7px;border-radius:2px;white-space:nowrap;margin-top:2px;
  background:var(--surface);color:var(--ink-soft)}}
.chk.ok .pill{{color:var(--ok)}} .chk.fallo .pill{{color:var(--danger)}}
.chk-b{{font-size:.93rem;min-width:0}}
.chk-b b{{font-family:var(--sans);font-weight:600}}
.rule{{font-family:var(--mono);font-size:.68rem;color:var(--ink-faint)}}
.detail{{color:var(--ink-soft);font-size:.9rem}}
.flags{{list-style:none;margin:0 0 18px;padding:12px 16px;background:var(--warn-soft);
  border-left:3px solid var(--warn);border-radius:0 4px 4px 0;font-size:.94rem}}
.flags li + li{{margin-top:6px}}
.notes{{margin:0 0 20px;padding:16px 18px;background:var(--danger-soft);
  border-left:3px solid var(--danger);border-radius:0 4px 4px 0}}
.notes-h{{font-family:var(--mono);font-size:.62rem;letter-spacing:.11em;text-transform:uppercase;
  color:var(--danger);margin:0 0 10px}}
.notes pre{{margin:0 0 10px;font-family:var(--mono);font-size:.82rem;line-height:1.55;
  white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink)}}
.notes-f{{margin:0;font-size:.88rem;color:var(--ink-soft);line-height:1.5}}
.prov{{display:flex;flex-wrap:wrap;gap:6px 16px;padding-top:14px;
  border-top:1px solid var(--line);font-family:var(--mono);font-size:.66rem;
  color:var(--ink-faint);letter-spacing:.03em}}
.mono{{font-family:var(--mono)}}
footer.page{{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);
  font-size:.86rem;color:var(--ink-faint)}}
</style></head><body>
<div class="wrap">
  <p class="eyebrow">BMS Support · Fase 0</p>
  <h1>Informe de extracción</h1>
  <p class="lede">Lo que el agente ha leído de cada factura, con las comprobaciones
     que se pueden hacer sin consultar el planning ni Exact.</p>

  <div class="strip">
    <div class="stat"><b>{len(data.invoices)}</b><span>Facturas</span></div>
    <div class="stat"><b>{_euros(data.total_amount)}</b><span>Importe total EUR</span></div>
    <div class="stat {flag_cls}"><b>{flagged}</b><span>Con avisos</span></div>
    <div class="stat"><b>${data.total_cost:.4f}</b><span>Coste de lectura</span></div>
  </div>

  {cards}

  <footer class="page">
    Generado el {E(data.generated_at)} desde los ficheros de extracción.
    Fichero local: no se ha enviado nada a ninguna parte.
  </footer>
</div></body></html>
"""
