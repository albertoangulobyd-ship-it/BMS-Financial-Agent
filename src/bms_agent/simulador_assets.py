"""Plantilla del simulador de tarifas.

Fichero HTML autocontenido: los datos van incrustados y el recalculo ocurre
en el navegador, para que mover el margen o escribir una tarifa se vea al
instante sin volver a generar nada.

El placeholder __DATOS__ se sustituye por el JSON de lineas al escribirla.
"""

from __future__ import annotations

PLANTILLA = r"""\
<title>Simulador de Tarifas</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
:root{
  --ground:#F6F7F9; --surface:#FFFFFF; --surface-2:#EDF0F5;
  --ink:#141A23; --ink-soft:#4E5A6B; --ink-faint:#7C8798;
  --line:#DCE1E8; --line-strong:#B7C0CC;
  --accent:#1F4E8C; --accent-soft:#E7EDF7;
  --coste:#2a78d6; --margen:#1baf7a;
  --warning:#a06a00; --warning-soft:#F7EEE0;
  --critical:#d03b3b; --critical-soft:#F8E8E8;
  --sans:'Archivo','Segoe UI',system-ui,-apple-system,sans-serif;
  --serif:'Source Serif 4',Georgia,serif;
  --mono:'IBM Plex Mono','Cascadia Mono',Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0D1117; --surface:#161B23; --surface-2:#1E252F;
  --ink:#E3E9F1; --ink-soft:#9DA9BA; --ink-faint:#77838F;
  --line:#28313D; --line-strong:#3C4753;
  --accent:#7BA9E7; --accent-soft:#172335;
  --coste:#3987e5; --margen:#199e70;
  --warning:#fab219; --warning-soft:#292014;
  --critical:#e66767; --critical-soft:#2B1719;
}}
:root[data-theme="dark"]{
  --ground:#0D1117; --surface:#161B23; --surface-2:#1E252F;
  --ink:#E3E9F1; --ink-soft:#9DA9BA; --ink-faint:#77838F;
  --line:#28313D; --line-strong:#3C4753;
  --accent:#7BA9E7; --accent-soft:#172335;
  --coste:#3987e5; --margen:#199e70;
  --warning:#fab219; --warning-soft:#292014;
  --critical:#e66767; --critical-soft:#2B1719;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:var(--sans);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.page{max-width:1280px;margin:0 auto;padding-inline:18px;padding-block:32px 72px}

.eyebrow{font-family:var(--mono);font-size:.64rem;letter-spacing:.16em;
  text-transform:uppercase;color:var(--accent);margin:0 0 10px}
h1{font-weight:700;font-size:1.9rem;letter-spacing:-.022em;line-height:1.1;
  margin:0 0 10px;text-wrap:balance}
.lede{font-family:var(--serif);font-size:1.02rem;line-height:1.6;color:var(--ink-soft);
  margin:0 0 6px;max-width:62ch}
.disclaimer{display:flex;gap:10px;align-items:flex-start;margin:16px 0 26px;
  padding:13px 16px;background:var(--warning-soft);border-left:3px solid var(--warning);
  max-width:62ch;font-size:.9rem;line-height:1.55}
.disclaimer b{display:block;font-size:.72rem;font-family:var(--mono);
  letter-spacing:.1em;text-transform:uppercase;color:var(--warning);margin-bottom:5px}

.split{display:grid;grid-template-columns:1fr;gap:18px}
@media (min-width:1000px){.split{grid-template-columns:352px minmax(0,1fr);align-items:start}
  .controls{position:sticky;top:env(safe-area-inset-top,0px)}}

.panel{background:var(--surface);border:1px solid var(--line);border-radius:7px;
  padding:18px 20px}
.panel + .panel{margin-top:14px}
.panel h2{margin:0 0 3px;font-size:.98rem;font-weight:600;letter-spacing:-.01em}
.panel .hint{margin:0 0 15px;font-size:.81rem;color:var(--ink-faint);line-height:1.45}

/* margen */
.margen-row{display:flex;align-items:baseline;gap:10px;margin-bottom:9px}
.margen-val{font-family:var(--sans);font-size:2rem;font-weight:600;letter-spacing:-.02em;
  line-height:1;color:var(--accent)}
.margen-row span{font-size:.82rem;color:var(--ink-faint)}
input[type=range]{width:100%;accent-color:var(--accent);height:26px}
.margen-ej{font-family:var(--mono);font-size:.76rem;color:var(--ink-soft);margin:4px 0 0}

/* filas editables */
.rows{display:flex;flex-direction:column;gap:7px}
.row{display:grid;grid-template-columns:1fr auto;gap:9px;align-items:center}
.row label{font-size:.85rem;min-width:0;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.row label .sub{display:block;font-family:var(--mono);font-size:.68rem;
  color:var(--ink-faint);text-transform:none;letter-spacing:0}
input[type=text],input[type=number]{font-family:var(--mono);font-size:.84rem;
  padding:6px 9px;min-height:34px;width:100%;
  border:1px solid var(--line-strong);border-radius:4px;
  background:var(--surface);color:var(--ink)}
input[type=number]{width:96px;text-align:right}
input::placeholder{color:var(--ink-faint);font-style:italic}
input:focus-visible,button:focus-visible,select:focus-visible{
  outline:2px solid var(--accent);outline-offset:1px}
.chk{display:flex;align-items:center;gap:9px;padding:5px 0;font-size:.86rem;cursor:pointer}
.chk input{width:17px;height:17px;accent-color:var(--accent);flex:none}
.chk .n{font-family:var(--mono);font-size:.7rem;color:var(--ink-faint);margin-left:auto}
.btn{font-family:var(--sans);font-size:.82rem;padding:7px 13px;min-height:34px;
  border:1px solid var(--line-strong);border-radius:4px;background:var(--surface);
  color:var(--ink-soft);cursor:pointer}
.btn:hover{background:var(--surface-2);color:var(--ink)}

/* tiles */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(138px,1fr));gap:2px;
  background:var(--line);border:1px solid var(--line);border-radius:7px;
  overflow:hidden;margin-bottom:16px}
.tile{background:var(--surface);padding:14px 16px}
.tile b{display:block;font-size:1.5rem;font-weight:600;letter-spacing:-.022em;line-height:1.15}
.tile span{font-family:var(--mono);font-size:.58rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-faint)}
.tile em{display:block;font-style:normal;font-size:.75rem;color:var(--ink-faint);margin-top:3px}
.tile.venta b{color:var(--accent)} .tile.margen b{color:var(--margen)}
.tile.flaco b{color:var(--warning)} .tile.perdida b{color:var(--critical)}

/* barras por cliente */
.cliente{padding:13px 0;border-bottom:1px solid var(--line)}
.cliente:last-child{border-bottom:none;padding-bottom:0}
.cliente-h{display:flex;justify-content:space-between;align-items:baseline;gap:12px;
  margin-bottom:7px;flex-wrap:wrap}
.cliente-h b{font-size:.93rem;font-weight:600}
.cliente-h .cifras{font-family:var(--mono);font-size:.8rem;color:var(--ink-soft);
  font-variant-numeric:tabular-nums}
.cliente-h .cifras strong{color:var(--margen);font-weight:600}
.barra{display:flex;height:22px;border-radius:3px;overflow:hidden;gap:2px;
  background:var(--surface-2)}
.barra i{display:block}
.barra .c{background:var(--coste)} .barra .m{background:var(--margen)}
.leyenda{display:flex;gap:16px;margin-top:12px;font-size:.8rem;color:var(--ink-soft);
  flex-wrap:wrap}
.leyenda i{display:inline-block;width:11px;height:11px;border-radius:2px;
  vertical-align:-1px;margin-right:6px}

/* tabla */
.tw{overflow-x:auto;margin-top:2px}
table{border-collapse:collapse;width:100%;min-width:640px;font-size:.85rem}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-family:var(--mono);font-weight:500;font-size:.6rem;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink-faint);background:var(--surface-2);
  position:sticky;top:0}
td.n{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
td.sub{font-family:var(--mono);font-size:.74rem;color:var(--ink-faint)}
tbody tr:hover{background:var(--surface-2)}
.pill{font-family:var(--mono);font-size:.6rem;letter-spacing:.06em;padding:2px 6px;
  border-radius:2px;background:var(--surface-2);color:var(--ink-soft)}
.pill.margen{background:var(--warning-soft);color:var(--warning)}
.scroll{max-height:460px;overflow-y:auto}

.avisos{margin:0 0 16px;padding:0;list-style:none;display:flex;flex-direction:column;gap:2px}
.avisos li{padding:11px 15px;background:var(--critical-soft);border-left:3px solid var(--critical);
  font-size:.87rem;line-height:1.5}
.avisos li.leve{background:var(--warning-soft);border-left-color:var(--warning)}
.avisos b{font-weight:600}
footer{margin-top:28px;padding-top:16px;border-top:1px solid var(--line);
  font-family:var(--serif);font-size:.87rem;color:var(--ink-faint);max-width:62ch;line-height:1.55}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<div class="page">
  <p class="eyebrow">BMS Support · Fase 0</p>
  <h1>¿A cuánto habría que facturar?</h1>
  <p class="lede">Las horas que los autónomos os facturan, agrupadas por cliente, obra y semana ISO, con el precio de venta que tú decidas. Mueve el margen o pon una tarifa pactada y todo se recalcula.</p>

  <div class="disclaimer">
    <div>
      <b>Esto no emite facturas</b>
      Es una proyección calculada desde lo que <em>los proveedores os han facturado</em>, no desde las horas registradas en el planning. Si un autónomo facturó de más, la proyección hereda el error. Las cifras de abajo son de las 134 facturas sintéticas de prueba, no de vuestra contabilidad real.
    </div>
  </div>

  <div class="split">
    <div class="controls">
      <section class="panel">
        <h2>Margen por defecto</h2>
        <p class="hint">Se aplica cuando no hay tarifa pactada para esa obra y trabajo.</p>
        <div class="margen-row">
          <span class="margen-val" id="margen-val">35%</span>
          <span>sobre el coste</span>
        </div>
        <input type="range" id="margen" min="0" max="120" step="1" value="35"
               aria-label="Margen por defecto en porcentaje">
        <p class="margen-ej" id="margen-ej"></p>
      </section>

      <section class="panel">
        <h2>De quién es cada obra</h2>
        <p class="hint">Las facturas de compra dicen la obra, no el cliente. Sin esto no hay a quién facturar.</p>
        <div class="rows" id="clientes"></div>
      </section>

      <section class="panel">
        <h2>Tarifas pactadas</h2>
        <p class="hint">Precio de venta por hora. En blanco, se usa el margen. Una fila por cada combinación que existe en las facturas.</p>
        <div class="rows" id="tarifas"></div>
        <p class="hint" style="margin:14px 0 0">
          <button class="btn" type="button" id="limpiar-tarifas">Vaciar todas y usar solo margen</button>
        </p>
      </section>

      <section class="panel">
        <h2>Lo que no se refactura</h2>
        <p class="hint">Se paga al autónomo pero no se cobra al cliente. Las horas de viaje son el caso típico.</p>
        <div id="nofact"></div>
      </section>
    </div>

    <div>
      <div class="tiles" id="tiles"></div>
      <ul class="avisos" id="avisos"></ul>

      <section class="panel">
        <h2>Por cliente</h2>
        <p class="hint">Coste de los autónomos y margen encima, sobre el total facturable.</p>
        <div id="clientes-barras"></div>
        <div class="leyenda">
          <span><i style="background:var(--coste)"></i>Coste de los autónomos</span>
          <span><i style="background:var(--margen)"></i>Vuestro margen</span>
        </div>
      </section>

      <section class="panel" style="margin-top:14px;padding-bottom:6px">
        <h2>Propuestas de factura</h2>
        <p class="hint">Una por cliente, obra y semana ISO. Es lo que se emitiría si el modelo de precios fuera este.</p>
        <div class="tw scroll"><table>
          <thead><tr>
            <th>Cliente</th><th>Obra</th><th>Sem.</th><th>Trabajo</th>
            <th class="n">Horas</th><th class="n">Venta/h</th>
            <th></th><th class="n">Venta</th><th class="n">Margen</th>
          </tr></thead>
          <tbody id="tbody"></tbody>
        </table></div>
      </section>

      <footer>
        Cuando el programa de planificación esté conectado, las horas dejarán de salir de las facturas de los autónomos y saldrán de los turnos registrados. Las cifras se moverán, y esa diferencia es exactamente lo que conviene mirar: es la medida de cuánto se está facturando de más o de menos.
      </footer>
    </div>
  </div>
</div>

<script>
const D = __DATOS__;

const eur = (v) => v.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const eur0 = (v) => v.toLocaleString('es-ES', {maximumFractionDigits: 0});
const h1 = (v) => v.toLocaleString('es-ES', {minimumFractionDigits: 1, maximumFractionDigits: 1});
const $ = (s) => document.querySelector(s);
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

const estado = {
  margen: D.sugerido.margen,
  clientes: {...D.sugerido.obras},
  tarifas: {...D.sugerido.tarifas},
  noFacturable: new Set(D.sugerido.no_facturable),
};

// ---------- cálculo ----------

function calcular() {
  const grupos = new Map();
  const descartadas = new Map();
  const sinCliente = new Set();

  for (const l of D.lineas) {
    if (estado.noFacturable.has(l.trabajo)) {
      const d = descartadas.get(l.trabajo) || {horas: 0, coste: 0};
      d.horas += l.horas; d.coste += l.horas * l.coste_hora;
      descartadas.set(l.trabajo, d);
      continue;
    }
    let cliente = (estado.clientes[l.obra] || '').trim();
    if (!cliente) { sinCliente.add(l.obra); cliente = '— ' + l.obra + ' sin cliente —'; }

    const pactada = estado.tarifas[l.obra + '|' + l.trabajo];
    const venta = (pactada != null && pactada > 0)
      ? pactada : l.coste_hora * (1 + estado.margen);
    const origen = (pactada != null && pactada > 0) ? 'pactada' : 'margen';

    const k = cliente + '\u0000' + l.obra + '\u0000' + l.semana + '\u0000' + l.trabajo;
    const g = grupos.get(k) || {
      cliente, obra: l.obra, semana: l.semana, trabajo: l.trabajo,
      horas: 0, coste: 0, venta: 0, ventaHora: venta, origen,
      costesHora: new Set(), huerfana: !estado.clientes[l.obra],
    };
    g.horas += l.horas;
    g.coste += l.horas * l.coste_hora;
    g.venta += l.horas * venta;
    g.costesHora.add(l.coste_hora);
    grupos.set(k, g);
  }

  const filas = [...grupos.values()].sort((a, b) =>
    b.semana.localeCompare(a.semana) || a.cliente.localeCompare(b.cliente, 'es') ||
    a.obra.localeCompare(b.obra, 'es') || a.trabajo.localeCompare(b.trabajo, 'es'));

  const clientes = new Map();
  let horas = 0, coste = 0, venta = 0;
  for (const f of filas) {
    horas += f.horas; coste += f.coste; venta += f.venta;
    const c = clientes.get(f.cliente) || {cliente: f.cliente, coste: 0, venta: 0, horas: 0, huerfana: f.huerfana};
    c.coste += f.coste; c.venta += f.venta; c.horas += f.horas;
    clientes.set(f.cliente, c);
  }

  return {
    filas, horas, coste, venta, margen: venta - coste,
    clientes: [...clientes.values()].sort((a, b) => b.venta - a.venta),
    descartadas: [...descartadas.entries()].map(([trabajo, d]) => ({trabajo, ...d})),
    sinCliente: [...sinCliente].sort(),
  };
}

// ---------- pintar ----------

function tiles(r) {
  const pct = r.venta ? (r.margen / r.venta) * 100 : 0;
  const clase = r.margen < 0 ? 'perdida' : pct < 15 ? 'flaco' : 'margen';
  const datos = [
    {v: h1(r.horas), k: 'Horas facturables', c: '', e: r.filas.length + ' líneas'},
    {v: eur0(r.coste), k: 'Coste EUR', c: '', e: 'lo que os cuesta'},
    {v: eur0(r.venta), k: 'Venta EUR', c: 'venta', e: 'lo que se facturaría'},
    {v: eur0(r.margen), k: 'Margen EUR', c: clase, e: ''},
    {v: pct.toFixed(1) + '%', k: 'Margen sobre venta', c: clase,
     e: r.margen < 0 ? 'estáis perdiendo dinero' : pct < 15 ? 'margen ajustado' : ''},
  ];
  const cont = $('#tiles'); cont.textContent = '';
  for (const t of datos) {
    const d = document.createElement('div'); d.className = 'tile ' + t.c;
    const b = document.createElement('b'); b.textContent = t.v;
    const s = document.createElement('span'); s.textContent = t.k;
    d.append(b, s);
    if (t.e) { const em = document.createElement('em'); em.textContent = t.e; d.append(em); }
    cont.append(d);
  }
}

function avisos(r) {
  const ul = $('#avisos'); ul.textContent = '';
  const add = (texto, titulo, leve) => {
    const li = document.createElement('li');
    if (leve) li.className = 'leve';
    const b = document.createElement('b'); b.textContent = titulo + ' ';
    li.append(b, document.createTextNode(texto)); ul.append(li);
  };
  if (r.sinCliente.length) {
    add(r.sinCliente.join(', ') + '. Esas horas no se pueden facturar a nadie hasta '
      + 'que digas de quién es cada obra.', 'Obras sin cliente:', false);
  }
  if (r.margen < 0) {
    add('Con estos precios la venta no cubre lo que os cuestan los autónomos.',
      'Margen negativo:', false);
  }
  for (const d of r.descartadas) {
    add(h1(d.horas) + ' h que os cuestan ' + eur(d.coste) + ' EUR y no se refacturan.',
      cap(d.trabajo) + ':', true);
  }
}

function barrasCliente(r) {
  const cont = $('#clientes-barras'); cont.textContent = '';
  if (!r.clientes.length) {
    const p = document.createElement('p'); p.className = 'hint';
    p.textContent = 'Nada que facturar con estos ajustes.'; cont.append(p); return;
  }
  const max = Math.max(...r.clientes.map((c) => c.venta), 1);
  for (const c of r.clientes) {
    const margen = c.venta - c.coste;
    const pct = c.venta ? (margen / c.venta) * 100 : 0;
    const div = document.createElement('div'); div.className = 'cliente';
    const h = document.createElement('div'); h.className = 'cliente-h';
    const b = document.createElement('b'); b.textContent = c.cliente;
    const cif = document.createElement('span'); cif.className = 'cifras';
    cif.append(document.createTextNode(h1(c.horas) + ' h · ' + eur(c.venta) + ' EUR · '));
    const st = document.createElement('strong');
    st.textContent = pct.toFixed(1) + '% margen';
    if (margen < 0) st.style.color = 'var(--critical)';
    cif.append(st);
    h.append(b, cif);

    const barra = document.createElement('div'); barra.className = 'barra';
    const ancho = (c.venta / max) * 100;
    const partCoste = c.venta > 0 ? Math.max(Math.min(c.coste / c.venta, 1), 0) : 1;
    const ic = document.createElement('i'); ic.className = 'c';
    ic.style.width = (ancho * partCoste) + '%';
    ic.title = 'Coste ' + eur(c.coste) + ' EUR';
    const im = document.createElement('i'); im.className = 'm';
    im.style.width = (ancho * (1 - partCoste)) + '%';
    im.title = 'Margen ' + eur(margen) + ' EUR';
    barra.append(ic, im);

    div.append(h, barra); cont.append(div);
  }
}

function tabla(r) {
  const tb = $('#tbody'); tb.textContent = '';
  for (const f of r.filas.slice(0, 300)) {
    const tr = document.createElement('tr');
    const margen = f.venta - f.coste;
    // El coste por hora va en el title de la fila: quitarlo de la tabla es lo
    // que deja sitio a la columna de margen, que es el dato del simulador.
    const costeHora = f.costesHora.size > 1
      ? 'varios costes: ' + [...f.costesHora].sort((a, b) => a - b).map(eur).join(' y ')
      : 'coste ' + eur([...f.costesHora][0]) + '/h';
    tr.title = costeHora + ' · venta ' + eur(f.ventaHora) + '/h · tarifa ' + f.origen;
    const celdas = [
      [f.cliente, ''], [f.obra, ''], [f.semana, 'sub'], [cap(f.trabajo), ''],
      [h1(f.horas), 'n'], [eur(f.ventaHora), 'n'],
    ];
    for (const [v, c] of celdas) {
      const td = document.createElement('td'); if (c) td.className = c;
      td.textContent = v; tr.append(td);
    }
    const tdOrigen = document.createElement('td');
    const pill = document.createElement('span');
    pill.className = 'pill' + (f.origen === 'margen' ? ' margen' : '');
    pill.textContent = f.origen;
    tdOrigen.append(pill); tr.append(tdOrigen);

    for (const v of [eur(f.venta), eur(margen)]) {
      const td = document.createElement('td'); td.className = 'n';
      td.textContent = v; tr.append(td);
    }
    tb.append(tr);
  }
  if (r.filas.length > 300) {
    const tr = document.createElement('tr');
    const td = document.createElement('td'); td.colSpan = 9; td.className = 'sub';
    td.textContent = 'Y ' + (r.filas.length - 300) + ' líneas más.';
    tr.append(td); tb.append(tr);
  }
}

function render() {
  const r = calcular();
  tiles(r); avisos(r); barrasCliente(r); tabla(r);
  $('#margen-val').textContent = Math.round(estado.margen * 100) + '%';
  $('#margen-ej').textContent =
    'Una hora que os cuesta 40,00 se factura a ' + eur(40 * (1 + estado.margen)) + '.';
}

// ---------- controles ----------

function construirControles() {
  const cl = $('#clientes');
  for (const obra of D.obras) {
    const row = document.createElement('div'); row.className = 'row';
    const lab = document.createElement('label');
    lab.setAttribute('for', 'cl-' + obra);
    lab.textContent = obra;
    const inp = document.createElement('input');
    inp.type = 'text'; inp.id = 'cl-' + obra;
    inp.placeholder = 'nombre del cliente';
    inp.value = estado.clientes[obra] || '';
    inp.addEventListener('input', () => {
      estado.clientes[obra] = inp.value; render();
    });
    row.append(lab, inp);
    row.style.gridTemplateColumns = '96px minmax(0,1fr)';
    cl.append(row);
  }

  const tf = $('#tarifas');
  for (const c of D.combinaciones) {
    const clave = c.obra + '|' + c.trabajo;
    const row = document.createElement('div'); row.className = 'row';
    const lab = document.createElement('label');
    lab.setAttribute('for', 'tf-' + clave);
    lab.textContent = cap(c.trabajo);
    const sub = document.createElement('span'); sub.className = 'sub';
    sub.textContent = c.obra; lab.append(sub);
    const inp = document.createElement('input');
    inp.type = 'number'; inp.id = 'tf-' + clave; inp.min = '0'; inp.step = '0.50';
    inp.placeholder = 'margen';
    if (estado.tarifas[clave] != null) inp.value = estado.tarifas[clave];
    inp.addEventListener('input', () => {
      const v = parseFloat(inp.value);
      estado.tarifas[clave] = Number.isFinite(v) && v > 0 ? v : null;
      render();
    });
    row.append(lab, inp); tf.append(row);
  }

  const horasPor = new Map();
  for (const l of D.lineas) horasPor.set(l.trabajo, (horasPor.get(l.trabajo) || 0) + l.horas);
  const nf = $('#nofact');
  for (const trabajo of D.trabajos) {
    const lab = document.createElement('label'); lab.className = 'chk';
    const inp = document.createElement('input');
    inp.type = 'checkbox'; inp.id = 'nf-' + trabajo;
    inp.checked = estado.noFacturable.has(trabajo);
    inp.addEventListener('change', () => {
      if (inp.checked) estado.noFacturable.add(trabajo);
      else estado.noFacturable.delete(trabajo);
      render();
    });
    const txt = document.createElement('span'); txt.textContent = cap(trabajo);
    const n = document.createElement('span'); n.className = 'n';
    n.textContent = h1(horasPor.get(trabajo) || 0) + ' h';
    lab.append(inp, txt, n); nf.append(lab);
  }

  $('#margen').addEventListener('input', (e) => {
    estado.margen = parseInt(e.target.value, 10) / 100; render();
  });
  $('#limpiar-tarifas').addEventListener('click', () => {
    for (const c of D.combinaciones) {
      const clave = c.obra + '|' + c.trabajo;
      estado.tarifas[clave] = null;
      const inp = document.getElementById('tf-' + clave);
      if (inp) inp.value = '';
    }
    render();
  });

  $('#margen').value = Math.round(estado.margen * 100);
}

construirControles();
render();
</script>

"""
