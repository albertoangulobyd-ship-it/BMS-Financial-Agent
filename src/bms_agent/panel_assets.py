"""CSS y JS del panel, separados del ensamblaje para poder leerlos.

Paleta de marcas validada con el script del metodo de visualizacion contra
las superficies reales del proyecto (#FFFFFF clara, #161B23 oscura), modo
all-pairs: las tres ranuras pasan las cinco comprobaciones en ambos modos.
La ranura aqua queda por debajo de 3:1 sobre fondo claro, asi que lleva
etiqueta directa y la tabla completa como alivio, que es lo que exige la
regla.
"""

from __future__ import annotations

CSS = """
:root{
  --ground:#F6F7F9; --surface:#FFFFFF; --surface-2:#EDF0F5;
  --ink:#141A23; --ink-soft:#4E5A6B; --ink-faint:#7C8798;
  --line:#DCE1E8; --line-strong:#B7C0CC;
  --accent:#1F4E8C; --accent-soft:#E7EDF7;
  --grid:#E6E9EE; --axis:#C3C7CE;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
  --seq1:#cde2fb; --seq2:#9ec5f4; --seq3:#6da7ec; --seq4:#3987e5; --seq5:#256abf;
  --good:#0ca30c; --warning:#a06a00; --serious:#ec835a; --critical:#d03b3b;
  --critical-soft:#F8E8E8; --warning-soft:#F7EEE0; --good-soft:#E3F0EB;
  --sans:'Archivo','Segoe UI',system-ui,-apple-system,sans-serif;
  --mono:'IBM Plex Mono','Cascadia Mono',Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --warning:#fab219;
  --seq1:#172335; --seq2:#1c3a5c; --seq3:#235485; --seq4:#2a6fae; --seq5:#3987e5;
  --ground:#0D1117; --surface:#161B23; --surface-2:#1E252F;
  --ink:#E3E9F1; --ink-soft:#9DA9BA; --ink-faint:#77838F;
  --line:#28313D; --line-strong:#3C4753;
  --accent:#7BA9E7; --accent-soft:#172335;
  --grid:#232C37; --axis:#3C4753;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --critical-soft:#2B1719; --warning-soft:#292014; --good-soft:#11241E;
}}
:root[data-theme="dark"]{
  --warning:#fab219;
  --seq1:#172335; --seq2:#1c3a5c; --seq3:#235485; --seq4:#2a6fae; --seq5:#3987e5;
  --ground:#0D1117; --surface:#161B23; --surface-2:#1E252F;
  --ink:#E3E9F1; --ink-soft:#9DA9BA; --ink-faint:#77838F;
  --line:#28313D; --line-strong:#3C4753;
  --accent:#7BA9E7; --accent-soft:#172335;
  --grid:#232C37; --axis:#3C4753;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --critical-soft:#2B1719; --warning-soft:#292014; --good-soft:#11241E;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1360px;margin:0 auto;padding:36px 22px 80px}
.eyebrow{font-family:var(--mono);font-size:.66rem;letter-spacing:.16em;
  text-transform:uppercase;color:var(--accent);margin:0 0 12px}
h1{font-weight:700;font-size:1.95rem;letter-spacing:-.022em;line-height:1.1;margin:0 0 8px}
.lede{color:var(--ink-soft);margin:0 0 24px;font-size:.98rem;max-width:60ch}

/* filtros: una fila, encima de todo lo que acotan */
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:14px 16px;
  background:var(--surface);border:1px solid var(--line);border-radius:6px;margin:0 0 22px;
  position:sticky;top:0;z-index:20}
.filters label{display:flex;flex-direction:column;gap:4px}
.filters span{font-family:var(--mono);font-size:.58rem;letter-spacing:.11em;
  text-transform:uppercase;color:var(--ink-faint)}
select,input[type=search]{font-family:var(--sans);font-size:.88rem;padding:7px 10px;
  min-height:34px;border:1px solid var(--line-strong);border-radius:4px;
  background:var(--surface);color:var(--ink)}
input[type=search]{min-width:200px}
select:focus-visible,input:focus-visible,button:focus-visible,th[role=button]:focus-visible{
  outline:2px solid var(--accent);outline-offset:1px}
.filters .count{margin-left:auto;font-family:var(--mono);font-size:.72rem;color:var(--ink-soft)}
.btn{font-family:var(--sans);font-size:.82rem;padding:7px 12px;min-height:34px;
  border:1px solid var(--line-strong);border-radius:4px;background:var(--surface);
  color:var(--ink-soft);cursor:pointer}
.btn:hover{background:var(--surface-2);color:var(--ink)}

/* tiles */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(154px,1fr));gap:2px;
  background:var(--line);border:1px solid var(--line);border-radius:6px;
  overflow:hidden;margin:0 0 22px}
.tile{background:var(--surface);padding:15px 17px}
.tile b{display:block;font-size:1.62rem;font-weight:600;letter-spacing:-.022em;line-height:1.15}
.tile span{font-family:var(--mono);font-size:.58rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-faint)}
.tile em{display:block;font-style:normal;font-size:.76rem;color:var(--ink-faint);margin-top:3px}
.tile.crit b{color:var(--critical)} .tile.warn b{color:var(--serious)}

/* alertas */
.alerts{background:var(--surface);border:1px solid var(--line);border-radius:6px;
  margin:0 0 22px;overflow:hidden}
#alerts-body{max-height:340px;overflow-y:auto}
.alerts-h{display:flex;align-items:baseline;gap:10px;padding:13px 17px;
  border-bottom:1px solid var(--line)}
.alerts-h h2{margin:0;font-size:1rem;font-weight:600}
.alerts-h .sub{font-family:var(--mono);font-size:.66rem;color:var(--ink-faint)}
.alert{display:flex;gap:12px;padding:12px 17px;border-bottom:1px solid var(--line)}
.alert:last-child{border-bottom:none}
.alert.critico{background:var(--critical-soft)}
.badge{font-family:var(--mono);font-size:.56rem;letter-spacing:.09em;text-transform:uppercase;
  padding:3px 7px;border-radius:2px;white-space:nowrap;height:fit-content;margin-top:2px;
  background:var(--surface-2);color:var(--ink-soft)}
.alert.critico .badge{background:var(--critical);color:#fff}
.alert-b{min-width:0}
.alert-b b{font-weight:600;font-size:.9rem}
.alert-b .rule{font-family:var(--mono);font-size:.66rem;color:var(--ink-faint);margin-left:6px}
.alert-b p{margin:3px 0 0;font-size:.87rem;color:var(--ink-soft);overflow-wrap:anywhere}
.alert-b .files{font-family:var(--mono);font-size:.68rem;color:var(--ink-faint);margin-top:4px}

/* graficos */
.charts{display:grid;grid-template-columns:1fr;gap:16px;margin:0 0 22px}
@media (min-width:900px){.charts{grid-template-columns:1.25fr 1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:18px 20px}
.card h2{margin:0 0 2px;font-size:.98rem;font-weight:600}
.hint{margin:0 0 14px;font-size:.8rem;color:var(--ink-faint)}
.chart{position:relative}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.gridline{stroke:var(--grid);stroke-width:1}
.axisline{stroke:var(--axis);stroke-width:1}
.tick{fill:var(--ink-faint);font-family:var(--mono);font-size:9.5px}
.tick.num{font-variant-numeric:tabular-nums}
.bar{fill:var(--s1)}
.bar.dim{fill:var(--line-strong)}
.barlabel{fill:var(--ink);font-size:10.5px;font-weight:600;font-variant-numeric:tabular-nums}
.catlabel{fill:var(--ink-soft);font-size:10.5px}
.hit{fill:transparent;cursor:pointer}
.bar.hot{fill:var(--accent)}
.empty{padding:26px 0;text-align:center;color:var(--ink-faint);font-size:.88rem}
.tip{position:absolute;pointer-events:none;opacity:0;transition:opacity .08s;
  background:var(--surface);border:1px solid var(--line-strong);border-radius:4px;
  padding:8px 11px;font-size:.8rem;box-shadow:0 4px 14px rgba(0,0,0,.14);z-index:10;
  white-space:nowrap}
.tip b{display:block;font-size:.95rem;font-variant-numeric:tabular-nums}
.tip span{color:var(--ink-soft);font-size:.76rem}
.tip i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:6px}

/* barra apilada de regimen */
.stack{display:flex;gap:2px;height:30px;margin:0 0 10px;border-radius:3px;overflow:hidden}
.stack div{min-width:2px}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:.82rem;color:var(--ink-soft)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;
  vertical-align:-1px;margin-right:6px}
.legend b{color:var(--ink);font-variant-numeric:tabular-nums;font-weight:600}


/* matriz proveedor x semana: rampa secuencial, un solo tono */
.matrix-wrap{overflow-x:auto}
table.matrix{border-collapse:separate;border-spacing:2px;min-width:auto;width:auto}
table.matrix th{position:static;background:none;border:none;padding:2px 4px;font-size:.58rem;
  letter-spacing:.06em;cursor:default;white-space:nowrap}
table.matrix th.prov{text-align:left;font-family:var(--sans);font-size:.78rem;
  font-weight:500;letter-spacing:0;text-transform:none;color:var(--ink);
  max-width:190px;overflow:hidden;text-overflow:ellipsis;padding-right:10px}
table.matrix td{padding:0;border:none;width:30px;height:26px;position:relative}
.cell{width:100%;height:100%;border-radius:3px;display:flex;align-items:center;
  justify-content:center;font-size:.62rem;font-weight:600;cursor:pointer;
  font-family:var(--mono)}
.cell.v0{background:var(--surface-2);box-shadow:inset 0 0 0 1px var(--line)}
.cell.v1{background:var(--seq1)} .cell.v2{background:var(--seq2)}
.cell.v3{background:var(--seq3)} .cell.v4{background:var(--seq4)}
.cell.v5{background:var(--seq5);color:#fff}
.cell.dup{box-shadow:inset 0 0 0 2px var(--critical)}
.cell.rev{box-shadow:inset 0 0 0 2px var(--warning)}
.cell:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.mkey{display:flex;align-items:center;gap:7px;margin-top:12px;font-size:.76rem;
  color:var(--ink-soft);flex-wrap:wrap}
.mkey i{display:inline-block;width:19px;height:13px;border-radius:2px}

/* tabla */
.tablecard{background:var(--surface);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.tablecard>header{display:flex;align-items:baseline;gap:10px;padding:14px 18px;
  border-bottom:1px solid var(--line);flex-wrap:wrap}
.tablecard h2{margin:0;font-size:1rem;font-weight:600}
.tw{overflow-x:auto;max-height:70vh}
table{border-collapse:collapse;width:100%;min-width:1280px;font-size:.85rem}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
th{position:sticky;top:0;background:var(--surface-2);z-index:2;
  font-family:var(--mono);font-weight:500;font-size:.6rem;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink-faint);cursor:pointer;user-select:none}
.tw th:hover{color:var(--ink)}
th .arrow{opacity:.45;margin-left:3px}
td.n{text-align:right;font-variant-numeric:tabular-nums;font-family:var(--mono);font-size:.82rem}
td.mono{font-family:var(--mono);font-size:.8rem}
/* Una linea por celda: partir el nombre en tres hace la fila de 150px y la
   tabla deja de poder escanearse. El nombre completo va en el title.
   Ojo con el nombre de la clase: .wrap es el contenedor de pagina y lleva
   padding 36/22/80. Llamar .wrap a una celda le metia ese relleno vertical
   y cada fila medía 120px. */
td.trunc{max-width:210px;overflow:hidden;text-overflow:ellipsis}
tbody tr:hover{background:var(--surface-2)}
tbody tr.critico{background:var(--critical-soft)}
tbody tr.revisar td:first-child{box-shadow:inset 3px 0 0 var(--warning)}
tbody tr.critico td:first-child{box-shadow:inset 3px 0 0 var(--critical)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px}
.dot.ok{background:var(--good)} .dot.revisar{background:var(--warning)}
.dot.critico{background:var(--critical)}
tfoot td{font-weight:600;background:var(--surface-2);border-top:1px solid var(--line-strong)}
.why{font-size:.78rem;color:var(--ink-soft);white-space:normal}
footer.page{margin-top:30px;padding-top:18px;border-top:1px solid var(--line);
  font-size:.82rem;color:var(--ink-faint)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""


JS = r"""
// Panel de facturas. Todo el texto que viene de las extracciones entra en el
// DOM con textContent: son datos de PDF de terceros, nunca HTML.

const NS = 'http://www.w3.org/2000/svg';
const el = (n, a) => { const e = document.createElementNS(NS, n);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const $ = (s) => document.querySelector(s);

const eur = (v) => (v == null ? '—' : v.toLocaleString('es-ES',
  {minimumFractionDigits: 2, maximumFractionDigits: 2}));
const eurCorto = (v) => {
  if (v == null) return '—';
  if (Math.abs(v) >= 1000000) return (v / 1000000).toLocaleString('es-ES', {maximumFractionDigits: 1}) + 'M';
  if (Math.abs(v) >= 1000) return (v / 1000).toLocaleString('es-ES', {maximumFractionDigits: 1}) + 'k';
  return v.toLocaleString('es-ES', {maximumFractionDigits: 0});
};
const num = (v, d = 2) => (v == null ? '—' : v.toLocaleString('es-ES',
  {minimumFractionDigits: d, maximumFractionDigits: d}));
const MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
const mesCorto = (clave) => MESES[parseInt(clave.slice(5, 7), 10) - 1] + ' ' + clave.slice(2, 4);

const REGIMEN = {standard: 'IVA repercutido', reverse_charged: 'IVA trasladado',
  kor_exempt: 'Exenta por KOR', unknown: 'Sin determinar'};
const COLOR_REGIMEN = {standard: 'var(--s1)', reverse_charged: 'var(--s2)',
  kor_exempt: 'var(--s3)', unknown: 'var(--line-strong)'};

const estado = {desde: '', hasta: '', proveedor: '', estado: '', q: '',
  orden: 'orden', dir: -1};

// ---------- filtro ----------

function filtrar() {
  const q = estado.q.trim().toLowerCase();
  return DATOS.filas.filter((f) => {
    if (estado.desde && f.orden < estado.desde) return false;
    if (estado.hasta && f.orden > estado.hasta) return false;
    if (estado.proveedor && f.proveedor !== estado.proveedor) return false;
    if (estado.estado === 'avisos' && f.estado === 'ok') return false;
    if (estado.estado === 'critico' && f.estado !== 'critico') return false;
    if (q) {
      const heno = [f.proveedor, f.numero, f.fichero, f.ubicaciones, f.iban,
        f.periodo, f.semanas].join(' ').toLowerCase();
      if (!heno.includes(q)) return false;
    }
    return true;
  });
}

const suma = (filas, campo) => filas.reduce((a, f) => a + (f[campo] || 0), 0);
// Base imponible con respaldo al total. Comparar regimenes por el total con
// IVA premia al regimen y no al gasto, y es lo que dicen los rotulos.
const baseDe = (f) => (f.base != null ? f.base : f.total);

// ---------- tiles ----------

function pintarTiles(filas) {
  const cont = $('#tiles');
  cont.textContent = '';
  const criticas = filas.filter((f) => f.estado === 'critico').length;
  const revisar = filas.filter((f) => f.estado !== 'ok').length;
  const proveedores = new Set(filas.map((f) => f.proveedor)).size;

  const tiles = [
    {v: eur(filas.reduce((a, f) => a + (baseDe(f) || 0), 0)), k: 'Base imponible EUR',
     e: filas.length + (filas.length === 1 ? ' factura' : ' facturas')},
    {v: String(proveedores), k: 'Proveedores'},
    {v: num(suma(filas, 'horas'), 1), k: 'Horas facturadas'},
    {v: eur(suma(filas, 'iva')), k: 'IVA soportado EUR'},
    {v: String(revisar), k: 'Por revisar', c: revisar ? 'warn' : '',
     e: revisar ? 'de ' + filas.length : 'todo limpio'},
    {v: String(criticas), k: 'Criticas', c: criticas ? 'crit' : '',
     e: criticas ? 'no pagar sin revisar' : 'ninguna'},
  ];

  for (const t of tiles) {
    const d = document.createElement('div');
    d.className = 'tile ' + (t.c || '');
    const b = document.createElement('b'); b.textContent = t.v;
    const s = document.createElement('span'); s.textContent = t.k;
    d.append(b, s);
    if (t.e) { const em = document.createElement('em'); em.textContent = t.e; d.append(em); }
    cont.append(d);
  }
}

// ---------- tooltip ----------

function tip(caja, x, y, titulo, valor, color) {
  const t = caja.querySelector('.tip');
  t.textContent = '';
  const b = document.createElement('b'); b.textContent = valor;
  const s = document.createElement('span');
  if (color) { const i = document.createElement('i'); i.style.background = color; s.append(i); }
  s.append(document.createTextNode(titulo));
  t.append(b, s);
  t.style.opacity = '1';
  const w = caja.clientWidth;
  t.style.left = Math.min(Math.max(x - 60, 4), Math.max(w - 170, 4)) + 'px';
  t.style.top = Math.max(y - 58, 2) + 'px';
}
const destip = (caja) => { caja.querySelector('.tip').style.opacity = '0'; };

// ---------- gasto por mes: columnas, periodos discretos ----------

function pintarMeses(filas) {
  const caja = $('#chart-meses');
  caja.querySelectorAll('svg,.empty').forEach((n) => n.remove());

  const acc = new Map();
  for (const f of filas) {
    const v = baseDe(f);
    if (v == null || f.orden === '0000-00-00') continue;
    const k = f.orden.slice(0, 7);
    acc.set(k, (acc.get(k) || 0) + v);
  }
  if (!acc.size) { const p = document.createElement('p');
    p.className = 'empty'; p.textContent = 'Sin facturas en este filtro.';
    caja.append(p); return; }

  const claves = [...acc.keys()].sort();
  const serie = [];
  let [a, m] = [parseInt(claves[0].slice(0, 4)), parseInt(claves[0].slice(5, 7))];
  const [fa, fm] = [parseInt(claves.at(-1).slice(0, 4)), parseInt(claves.at(-1).slice(5, 7))];
  while (a < fa || (a === fa && m <= fm)) {
    const k = String(a).padStart(4, '0') + '-' + String(m).padStart(2, '0');
    serie.push({mes: k, total: acc.get(k) || 0});
    if (++m === 13) { a++; m = 1; }
  }

  const W = 720, H = 250, L = 52, R = 14, T = 18, B = 34;
  const pw = W - L - R, ph = H - T - B;
  const max = Math.max(...serie.map((d) => d.total), 1);
  const paso = Math.pow(10, Math.floor(Math.log10(max)));
  const tope = Math.ceil(max / (paso / 2)) * (paso / 2);
  const y = (v) => T + ph - (v / tope) * ph;
  const ancho = pw / serie.length;
  const bw = Math.max(Math.min(ancho - 2, 54), 3);

  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'group',
    'aria-label': 'Gasto en facturas por mes, base imponible'});

  for (let i = 0; i <= 4; i++) {
    const v = (tope / 4) * i;
    svg.append(el('line', {class: 'gridline', x1: L, x2: W - R, y1: y(v), y2: y(v)}));
    const tx = el('text', {class: 'tick num', x: L - 8, y: y(v) + 3.5, 'text-anchor': 'end'});
    tx.textContent = eurCorto(v); svg.append(tx);
  }
  svg.append(el('line', {class: 'axisline', x1: L, x2: W - R, y1: y(0), y2: y(0)}));

  const maxIdx = serie.reduce((b, d, i) => (d.total > serie[b].total ? i : b), 0);
  serie.forEach((d, i) => {
    const cx = L + i * ancho + ancho / 2;
    const h = d.total > 0 ? Math.max(y(0) - y(d.total), 2) : 0;
    let marca = null;
    if (h) {
      marca = el('rect', {class: 'bar', x: cx - bw / 2, y: y(d.total),
        width: bw, height: h, rx: 2});
      svg.append(marca);
    }

    if (serie.length <= 14 || i % Math.ceil(serie.length / 12) === 0) {
      const tx = el('text', {class: 'tick', x: cx, y: H - B + 16, 'text-anchor': 'middle'});
      tx.textContent = mesCorto(d.mes); svg.append(tx);
    }
    // Etiqueta directa solo en el maximo y el ultimo: nunca en todos.
    if (d.total > 0 && (i === maxIdx || i === serie.length - 1)) {
      const lb = el('text', {class: 'barlabel', x: cx, y: y(d.total) - 6, 'text-anchor': 'middle'});
      lb.textContent = eurCorto(d.total); svg.append(lb);
    }
    const hit = el('rect', {class: 'hit', x: L + i * ancho, y: T,
      width: ancho, height: ph, tabindex: '0', role: 'button'});
    hit.setAttribute('aria-label', mesCorto(d.mes) + ': ' + eur(d.total) + ' euros');
    const barra = h ? svg.querySelector('rect.bar:nth-of-type(' + (i + 1) + ')') : null;
    const mostrar = () => {
      tip(caja, (cx / W) * caja.clientWidth, y(d.total) / H * caja.clientHeight,
        mesCorto(d.mes), eur(d.total) + ' EUR', 'var(--s1)');
      if (marca) marca.classList.add('hot');
    };
    const ocultar = () => { destip(caja); if (marca) marca.classList.remove('hot'); };
    hit.addEventListener('pointermove', mostrar);
    hit.addEventListener('focus', mostrar);
    hit.addEventListener('pointerleave', ocultar);
    hit.addEventListener('blur', ocultar);
    svg.append(hit);
  });
  caja.prepend(svg);
}

// ---------- ranking de proveedores: barras horizontales ----------

function pintarProveedores(filas) {
  const caja = $('#chart-prov');
  caja.querySelectorAll('svg,.empty').forEach((n) => n.remove());

  const acc = new Map();
  for (const f of filas) {
    const e = acc.get(f.proveedor) || {total: 0, n: 0};
    e.total += baseDe(f) || 0; e.n += 1; acc.set(f.proveedor, e);
  }
  if (!acc.size) { const p = document.createElement('p');
    p.className = 'empty'; p.textContent = 'Sin facturas en este filtro.';
    caja.append(p); return; }

  let lista = [...acc.entries()].map(([nombre, e]) => ({nombre, ...e}))
    .sort((a, b) => b.total - a.total);
  if (lista.length > 10) {
    const resto = lista.slice(10);
    lista = lista.slice(0, 10).concat([{
      nombre: 'Otros (' + resto.length + ')',
      total: resto.reduce((a, r) => a + r.total, 0),
      n: resto.reduce((a, r) => a + r.n, 0), otros: true}]);
  }

  const fila = 34, gap = 3, L = 4, R = 82, W = 560;
  const H = lista.length * (fila + gap) + 6;
  const max = Math.max(...lista.map((d) => d.total), 1);
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'group',
    'aria-label': 'Base imponible facturada por proveedor'});

  lista.forEach((d, i) => {
    const yb = i * (fila + gap);
    const bw = Math.max((d.total / max) * (W - L - R), 2);
    svg.append(el('rect', {class: 'bar' + (d.otros ? ' dim' : ''), x: L, y: yb + 16,
      width: bw, height: fila - 18, rx: 2}));
    const nm = el('text', {class: 'catlabel', x: L, y: yb + 11});
    nm.textContent = d.nombre.length > 46 ? d.nombre.slice(0, 44) + '…' : d.nombre;
    svg.append(nm);
    const vl = el('text', {class: 'barlabel', x: W - 4, y: yb + fila - 5,
      'text-anchor': 'end'});
    vl.textContent = eur(d.total); svg.append(vl);

    const hit = el('rect', {class: 'hit', x: 0, y: yb, width: W, height: fila + gap,
      tabindex: '0', role: 'button'});
    hit.setAttribute('aria-label', d.nombre + ': ' + eur(d.total) + ' euros en ' + d.n + ' facturas');
    const mostrar = () => tip(caja, (bw / W) * caja.clientWidth,
      ((yb + fila) / H) * caja.clientHeight,
      d.n + (d.n === 1 ? ' factura' : ' facturas'), eur(d.total) + ' EUR', 'var(--s1)');
    hit.addEventListener('pointermove', mostrar);
    hit.addEventListener('focus', mostrar);
    hit.addEventListener('pointerleave', () => destip(caja));
    hit.addEventListener('blur', () => destip(caja));
    svg.append(hit);
  });
  caja.prepend(svg);
}

// ---------- regimen de IVA: barra apilada de parte sobre el todo ----------

function pintarRegimen(filas) {
  const stack = $('#stack'), leg = $('#legend');
  stack.textContent = ''; leg.textContent = '';
  const acc = new Map();
  for (const f of filas) {
    const e = acc.get(f.regimen) || {total: 0, n: 0};
    e.total += baseDe(f) || 0; e.n += 1; acc.set(f.regimen, e);
  }
  const total = [...acc.values()].reduce((a, e) => a + e.total, 0);
  if (!total) { const p = document.createElement('p');
    p.className = 'empty'; p.textContent = 'Sin facturas en este filtro.';
    stack.append(p); return; }

  const orden = ['standard', 'reverse_charged', 'kor_exempt', 'unknown'];
  for (const k of orden) {
    const e = acc.get(k); if (!e || !e.total) continue;
    const pct = (e.total / total) * 100;
    const seg = document.createElement('div');
    seg.style.width = pct + '%'; seg.style.background = COLOR_REGIMEN[k];
    seg.title = REGIMEN[k] + ': ' + eur(e.total) + ' EUR';
    stack.append(seg);

    const li = document.createElement('div');
    const i = document.createElement('i'); i.style.background = COLOR_REGIMEN[k];
    const b = document.createElement('b'); b.textContent = eur(e.total);
    li.append(i, document.createTextNode(REGIMEN[k] + ' · '), b,
      document.createTextNode(' EUR · ' + e.n + (e.n === 1 ? ' factura' : ' facturas')));
    leg.append(li);
  }
}

// ---------- alertas ----------

function pintarAlertas(filas) {
  const visibles = new Set(filas.map((f) => f.fichero));
  const lista = DATOS.alertas.filter((a) => a.facturas.some((f) => visibles.has(f)));
  const caja = $('#alerts'), cuerpo = $('#alerts-body');
  cuerpo.textContent = '';
  if (!lista.length) { caja.hidden = true; return; }
  caja.hidden = false;
  $('#alerts-count').textContent = lista.length + (lista.length === 1 ? ' aviso' : ' avisos') +
    ' · ' + lista.filter((a) => a.severidad === 'critico').length + ' criticos';

  for (const a of lista.slice(0, 40)) {
    const d = document.createElement('div');
    d.className = 'alert ' + a.severidad;
    const badge = document.createElement('span');
    badge.className = 'badge'; badge.textContent = a.severidad;
    const b = document.createElement('div'); b.className = 'alert-b';
    const t = document.createElement('b'); t.textContent = a.titulo;
    b.append(t);
    if (a.regla && a.regla !== '—') {
      const r = document.createElement('span'); r.className = 'rule';
      r.textContent = 'regla ' + a.regla; b.append(r);
    }
    const p = document.createElement('p'); p.textContent = a.detalle; b.append(p);
    const f = document.createElement('div'); f.className = 'files';
    // Listar treinta ficheros no ayuda a nadie y ahoga el aviso.
    const muestra = a.facturas.slice(0, 5).join(' · ');
    f.textContent = a.facturas.length > 5
      ? muestra + ' · y ' + (a.facturas.length - 5) + ' mas'
      : muestra;
    b.append(f);
    d.append(badge, b); cuerpo.append(d);
  }
  if (lista.length > 40) {
    const mas = document.createElement('div'); mas.className = 'alert';
    const b = document.createElement('div'); b.className = 'alert-b';
    const p = document.createElement('p');
    p.textContent = 'Y ' + (lista.length - 40) + ' avisos mas. Filtra para verlos.';
    b.append(p); mas.append(b); cuerpo.append(mas);
  }
}

// ---------- tabla ----------

const COLUMNAS = [
  {k: 'fecha', t: 'Fecha', orden: 'orden'},
  {k: 'proveedor', t: 'Proveedor', wrap: true},
  {k: 'numero', t: 'Numero', mono: true},
  {k: 'periodo', t: 'Periodo', mono: true},
  {k: 'semanas', t: 'Sem.', mono: true},
  {k: 'ubicaciones', t: 'Ubicacion', wrap: true},
  {k: 'horas', t: 'Horas', n: true, d: 1},
  {k: 'base', t: 'Base', n: true},
  {k: 'iva', t: 'IVA', n: true},
  {k: 'total', t: 'Total', n: true},
  {k: 'regimen', t: 'Regimen'},
  {k: 'iban', t: 'IBAN', mono: true},
  {k: 'vencimiento', t: 'Vence', mono: true},
];

function pintarTabla(filas) {
  const orden = estado.orden, dir = estado.dir;
  const ordenadas = [...filas].sort((a, b) => {
    const x = a[orden], y = b[orden];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    if (typeof x === 'number' && typeof y === 'number') return (x - y) * dir;
    return String(x).localeCompare(String(y), 'es') * dir;
  });

  const thead = $('#thead'); thead.textContent = '';
  const tr = document.createElement('tr');
  const th0 = document.createElement('th'); th0.textContent = ''; tr.append(th0);
  for (const c of COLUMNAS) {
    const th = document.createElement('th');
    th.textContent = c.t;
    th.tabIndex = 0; th.setAttribute('role', 'button');
    const clave = c.orden || c.k;
    th.setAttribute('aria-sort', orden === clave ? (dir === 1 ? 'ascending' : 'descending') : 'none');
    if (orden === clave) {
      const a = document.createElement('span'); a.className = 'arrow';
      a.textContent = dir === 1 ? '▲' : '▼'; th.append(a);
    }
    const activar = () => {
      if (estado.orden === clave) estado.dir *= -1;
      else { estado.orden = clave; estado.dir = c.n || clave === 'orden' ? -1 : 1; }
      render();
    };
    th.addEventListener('click', activar);
    th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activar(); } });
    tr.append(th);
  }
  thead.append(tr);

  const tbody = $('#tbody'); tbody.textContent = '';
  for (const f of ordenadas) {
    const tr = document.createElement('tr');
    tr.className = f.estado;
    const td0 = document.createElement('td');
    const dot = document.createElement('span');
    dot.className = 'dot ' + f.estado;
    dot.title = f.estado === 'ok' ? 'Sin avisos' : f.motivos.join(' · ');
    td0.append(dot); tr.append(td0);

    for (const c of COLUMNAS) {
      const td = document.createElement('td');
      if (c.n) td.className = 'n';
      else if (c.mono) td.className = 'mono';
      else if (c.wrap) td.className = 'trunc';
      let v = f[c.k];
      if (c.k === 'regimen') v = REGIMEN[v] || v;
      td.textContent = c.n ? num(v, c.d || 2) : (v == null || v === '' ? '—' : String(v));
      if (c.wrap && v) td.title = String(v);
      tr.append(td);
    }
    tbody.append(tr);

    if (f.motivos.length) {
      const trm = document.createElement('tr');
      trm.className = f.estado;
      const td = document.createElement('td');
      td.colSpan = COLUMNAS.length + 1;
      td.className = 'why';
      td.textContent = '↳ ' + f.motivos.join(' · ');
      trm.append(td); tbody.append(trm);
    }
  }

  // El pie se rellena por CLAVE de columna. Construirlo con una lista
  // posicional lo dejaba desplazado una celda en cuanto cambiaba COLUMNAS.
  const tfoot = $('#tfoot'); tfoot.textContent = '';
  const trf = document.createElement('tr');
  const pie = {
    fecha: ordenadas.length + (ordenadas.length === 1 ? ' factura' : ' facturas'),
    horas: num(suma(ordenadas, 'horas'), 1),
    base: eur(suma(ordenadas, 'base')),
    iva: eur(suma(ordenadas, 'iva')),
    total: eur(suma(ordenadas, 'total')),
  };
  trf.append(document.createElement('td'));
  for (const c of COLUMNAS) {
    const td = document.createElement('td');
    if (c.n) td.className = 'n';
    td.textContent = pie[c.k] || '';
    trf.append(td);
  }
  tfoot.append(trf);
}

// ---------- matriz proveedor x semana ----------

// Semanas ISO entre dos, ambas incluidas. Se recorre por lunes.
function rangoSemanas(primera, ultima) {
  const lunes = (k) => {
    const [a, w] = [parseInt(k.slice(0, 4), 10), parseInt(k.slice(6), 10)];
    const cuatro = new Date(Date.UTC(a, 0, 4));
    const d = (cuatro.getUTCDay() + 6) % 7;
    return new Date(Date.UTC(a, 0, 4 - d + (w - 1) * 7));
  };
  const clave = (d) => {
    const j = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
    j.setUTCDate(j.getUTCDate() + 3 - ((j.getUTCDay() + 6) % 7));
    const ene4 = new Date(Date.UTC(j.getUTCFullYear(), 0, 4));
    const n = 1 + Math.round(((j - ene4) / 86400000 - 3 + ((ene4.getUTCDay() + 6) % 7)) / 7);
    return j.getUTCFullYear() + '-W' + String(n).padStart(2, '0');
  };
  const out = []; const d = lunes(primera); const fin = lunes(ultima);
  while (d <= fin && out.length < 400) { out.push(clave(d)); d.setUTCDate(d.getUTCDate() + 7); }
  return out;
}

function pintarMatriz(filas) {
  const caja = document.querySelector('#matrix');
  // Borrar solo lo pintado: caja.textContent = '' se llevaba por delante el
  // nodo .tip y el tooltip de la rejilla dejaba de funcionar tras el primer
  // filtrado.
  caja.querySelectorAll('.matrix-wrap,.mkey,.empty').forEach((n) => n.remove());

  // La rejilla se recalcula sobre las filas filtradas. Consumir el agregado
  // del servidor la dejaba mostrando el historico completo mientras las
  // demas piezas obedecian al filtro, y el panel se contradecia.
  const celdas = new Map();
  const totales = new Map();
  const conSemana = new Set();
  for (const f of filas) {
    const suyas = f.semanas_iso || [];
    if (!suyas.length) continue;
    const v = baseDe(f) || 0;
    totales.set(f.proveedor, (totales.get(f.proveedor) || 0) + v);
    const trozo = v / suyas.length;
    for (const s of suyas) {
      conSemana.add(s);
      const k = f.proveedor + '\u0000' + s;
      const c = celdas.get(k) || {importe: 0, n: 0, estado: 'ok'};
      c.importe += trozo; c.n += 1;
      if (f.estado === 'critico') c.estado = 'critico';
      else if (f.estado === 'revisar' && c.estado === 'ok') c.estado = 'revisar';
      celdas.set(k, c);
    }
  }

  if (!conSemana.size) {
    const p = document.createElement('p');
    p.className = 'empty'; p.textContent = 'Sin semanas que mostrar con este filtro.';
    caja.append(p); return;
  }

  const todas = [...conSemana].sort();
  const semanas = rangoSemanas(todas[0], todas[todas.length - 1]).slice(-18);
  const prov = [...totales.entries()].sort((a, b) => b[1] - a[1])
    .map(([proveedor, total]) => ({proveedor, total}));
  const max = Math.max(...[...celdas.values()].map((c) => c.importe), 1);
  const nivel = (v) => (v <= 0 ? 0 : Math.min(5, Math.ceil((v / max) * 5)));

  const wrap = document.createElement('div'); wrap.className = 'matrix-wrap';
  const tabla = document.createElement('table'); tabla.className = 'matrix';
  const thead = document.createElement('thead');
  const trh = document.createElement('tr');
  const th0 = document.createElement('th'); th0.className = 'prov'; trh.append(th0);
  for (const s of semanas) {
    const th = document.createElement('th');
    th.textContent = s.slice(6); th.title = s; trh.append(th);
  }
  thead.append(trh); tabla.append(thead);

  const tbody = document.createElement('tbody');
  for (const p of prov) {
    const tr = document.createElement('tr');
    const th = document.createElement('th');
    th.className = 'prov'; th.textContent = p.proveedor; th.title = p.proveedor;
    tr.append(th);
    for (const s of semanas) {
      const td = document.createElement('td');
      const c = celdas.get(p.proveedor + '\u0000' + s);
      const d = document.createElement('div');
      d.className = 'cell v' + (c ? nivel(c.importe) : 0);
      d.tabIndex = 0; d.setAttribute('role', 'button');
      if (c && c.n > 1) { d.classList.add('dup'); d.textContent = String(c.n); }
      else if (c && c.estado !== 'ok') d.classList.add('rev');
      const etiqueta = c
        ? p.proveedor + ', semana ' + s.slice(6) + ': ' + eur(c.importe) +
          ' euros en ' + c.n + (c.n === 1 ? ' factura' : ' facturas')
        : p.proveedor + ', semana ' + s.slice(6) + ': sin factura';
      d.setAttribute('aria-label', etiqueta);
      const mostrar = (ev) => {
        const r = caja.getBoundingClientRect(), t = d.getBoundingClientRect();
        tip(caja, t.left - r.left + 15, t.top - r.top,
          c ? s + ' · ' + c.n + (c.n === 1 ? ' factura' : ' facturas') : s + ' · sin factura',
          c ? eur(c.importe) + ' EUR' : '—', c ? 'var(--seq4)' : 'var(--line-strong)');
      };
      d.addEventListener('pointerenter', mostrar);
      d.addEventListener('focus', mostrar);
      d.addEventListener('pointerleave', () => destip(caja));
      d.addEventListener('blur', () => destip(caja));
      d.addEventListener('click', () => {
        document.querySelector('#f-q').value = p.proveedor;
        estado.q = p.proveedor; render();
      });
      td.append(d); tr.append(td);
    }
    tbody.append(tr);
  }
  tabla.append(tbody);
  wrap.append(tabla); caja.append(wrap);

  const key = document.createElement('div'); key.className = 'mkey';
  const vacio = document.createElement('i'); vacio.className = 'cell v0';
  key.append(vacio, document.createTextNode('sin factura'));
  for (let i = 1; i <= 5; i++) {
    const b = document.createElement('i'); b.style.background = 'var(--seq' + i + ')';
    key.append(b);
  }
  key.append(document.createTextNode('menos a mas importe'));
  const dup = document.createElement('i');
  dup.style.boxShadow = 'inset 0 0 0 2px var(--critical)';
  dup.style.background = 'var(--surface-2)';
  key.append(dup, document.createTextNode('dos o mas facturas esa semana'));
  const rev = document.createElement('i');
  rev.style.boxShadow = 'inset 0 0 0 2px var(--warning)';
  rev.style.background = 'var(--surface-2)';
  key.append(rev, document.createTextNode('con avisos'));
  caja.append(key);
}

// ---------- exportar ----------

function exportarCSV() {
  const filas = filtrar();
  const cab = ['Fichero', 'Fecha', 'Proveedor', 'Numero', 'Periodo', 'Semanas',
    'Ubicacion', 'Horas', 'Base', 'IVA', 'Total', 'Regimen', 'IBAN', 'Vence',
    'Estado', 'Motivos'];
  // Excel y LibreOffice ejecutan una celda que empieza por =, +, - o @. El
  // texto de estas celdas sale de PDF de terceros, asi que se neutraliza con
  // un apostrofe antes de entrecomillar.
  const esc = (v) => {
    let s = String(v == null ? '' : v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  };
  // Coma decimal: con punto, Excel en espanol trata la columna como texto.
  const dec = (v, d) => (v == null ? '' : num(v, d));
  const lineas = [cab.map(esc).join(';')];
  for (const f of filas) {
    lineas.push([f.fichero, f.fecha, f.proveedor, f.numero, f.periodo, f.semanas,
      f.ubicaciones, dec(f.horas, 1), dec(f.base, 2), dec(f.iva, 2), dec(f.total, 2),
      REGIMEN[f.regimen] || f.regimen,
      f.iban, f.vencimiento, f.estado, f.motivos.join(' | ')].map(esc).join(';'));
  }
  // Punto y coma y BOM: es lo que abre Excel en espanol sin pelearse.
  const blob = new Blob(['\ufeff' + lineas.join('\r\n')],
    {type: 'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'facturas.csv';
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---------- orquestacion ----------

function render() {
  const filas = filtrar();
  $('#count').textContent = 'Mostrando ' + filas.length + ' de ' + DATOS.filas.length;
  pintarTiles(filas);
  pintarAlertas(filas);
  pintarMeses(filas);
  pintarProveedores(filas);
  pintarRegimen(filas);
  pintarMatriz(filas);
  pintarTabla(filas);
}

function iniciar() {
  const sel = $('#f-proveedor');
  for (const p of [...new Set(DATOS.filas.map((f) => f.proveedor))].sort((a, b) => a.localeCompare(b, 'es'))) {
    const o = document.createElement('option'); o.value = p; o.textContent = p; sel.append(o);
  }
  const periodos = $('#f-periodo');
  periodos.addEventListener('change', () => {
    const v = periodos.value;
    if (!v) { estado.desde = ''; estado.hasta = ''; }
    else {
      const hasta = DATOS.totales.hasta || '9999-12-31';
      const d = new Date(hasta + 'T00:00:00Z');
      d.setUTCDate(d.getUTCDate() - parseInt(v, 10));
      estado.desde = d.toISOString().slice(0, 10); estado.hasta = '';
    }
    render();
  });
  sel.addEventListener('change', () => { estado.proveedor = sel.value; render(); });
  $('#f-estado').addEventListener('change', (e) => { estado.estado = e.target.value; render(); });
  let t; $('#f-q').addEventListener('input', (e) => {
    clearTimeout(t); t = setTimeout(() => { estado.q = e.target.value; render(); }, 120); });
  $('#f-csv').addEventListener('click', exportarCSV);
  $('#f-reset').addEventListener('click', () => {
    Object.assign(estado, {desde: '', hasta: '', proveedor: '', estado: '', q: ''});
    periodos.value = ''; sel.value = ''; $('#f-estado').value = ''; $('#f-q').value = '';
    render();
  });
  render();
}

document.addEventListener('DOMContentLoaded', iniciar);

"""
