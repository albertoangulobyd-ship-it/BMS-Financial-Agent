#!/usr/bin/env python3
"""Inserta el simulador de facturacion en un panel ya compilado.

NO regenera el fichero: solo anade. El bundle de React, el reestilo, el dock
de navegacion y el panel original quedan intactos, byte a byte. Tres bloques
nuevos y cuatro retoques de un literal dentro de su paquete:

1. Un <style> antes de </head>, con lo que no existia todavia. Todo lo demas
   reutiliza sus clases (.card, .tiles, .tw, .btn) para heredar su diseno.
2. La seccion, antes del <footer class="page">.
3. Un <script> al final, con los datos y la logica.
4. Cuatro literales de su paquete: la entrada del dock, el orden de las
   secciones, el glosario y la lista de lo que su traductor no toca.

Los textos de la seccion van en ingles y neerlandes, los dos idiomas de su
panel, y cambian con su interruptor EN/NL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CSS = """
<style>
/* Simulador de facturacion. Reutiliza .card, .tiles, .tile, .tw y .btn del
   panel; aqui solo va lo que no existia. */
.sim-nota{display:flex;gap:10px;margin:0 0 20px;padding:12px 16px;
  background:var(--warning-soft);border-left:3px solid var(--warning);
  font-size:12px;line-height:1.55;max-width:90ch}
.sim-nota b{display:block;font:10px var(--mono);letter-spacing:.1em;
  text-transform:uppercase;color:var(--warning);margin-bottom:5px}
.sim-split{display:grid;grid-template-columns:1fr;gap:20px}
@media (min-width:1080px){.sim-split{grid-template-columns:320px minmax(0,1fr);
  align-items:start}}
.sim-bloque{padding:16px 18px;background:var(--surface-2);border-radius:8px}
.sim-bloque + .sim-bloque{margin-top:12px}
.sim-bloque h3{margin:0 0 3px;font-size:13px;font-weight:600;letter-spacing:-.2px}
.sim-bloque p{margin:0 0 13px;font-size:11px;line-height:1.5;color:var(--ink-faint)}
.sim-margen{display:flex;align-items:baseline;gap:9px;margin-bottom:7px}
.sim-margen b{font-size:28px;font-weight:600;letter-spacing:-.8px;line-height:1;
  color:var(--accent)}
.sim-margen span{font-size:11px;color:var(--ink-faint)}
.sim-seccion input[type=range]{width:100%;accent-color:var(--accent);height:24px}
.sim-ej{margin:6px 0 0!important;font-family:var(--mono);font-size:11px;
  color:var(--ink-soft)}
.sim-fila{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;
  margin-bottom:6px}
.sim-fila label{font-size:12px;min-width:0;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.sim-fila label i{display:block;font-style:normal;font:10px var(--mono);
  color:var(--ink-faint)}
.sim-seccion input[type=text],.sim-seccion input[type=number]{
  font-family:var(--mono);font-size:12px;padding:6px 9px;min-height:32px;width:100%;
  border:1px solid var(--line-strong);border-radius:6px;
  background:var(--surface);color:var(--ink)}
.sim-seccion input[type=number]{width:82px;text-align:right}
.sim-seccion input::placeholder{color:var(--ink-faint);font-style:italic}
.sim-seccion input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.sim-chk{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px;
  cursor:pointer}
.sim-chk input{width:16px;height:16px;accent-color:var(--accent);flex:none}
.sim-chk i{margin-left:auto;font-style:normal;font:10px var(--mono);
  color:var(--ink-faint)}
.sim-seccion .tiles{margin-bottom:14px}
.sim-avisos{margin:0 0 14px;padding:0;list-style:none}
.sim-avisos li{padding:10px 14px;margin-bottom:2px;font-size:12px;line-height:1.5;
  background:var(--surface-2);box-shadow:inset 3px 0 var(--critical);border-radius:4px}
.sim-avisos li.leve{box-shadow:inset 3px 0 var(--warning)}
.sim-avisos b{font-weight:600}
.sim-cli{padding:11px 0;border-bottom:1px solid var(--line)}
.sim-cli:last-child{border-bottom:none}
.sim-cli-h{display:flex;justify-content:space-between;align-items:baseline;gap:12px;
  margin-bottom:6px;flex-wrap:wrap}
.sim-cli-h b{font-size:13px;font-weight:600}
.sim-cli-h span{font:11px var(--mono);color:var(--ink-soft);
  font-variant-numeric:tabular-nums}
.sim-cli-h span strong{color:var(--good,#1baf7a);font-weight:600}
.sim-barra{display:flex;height:20px;border-radius:4px;overflow:hidden;gap:2px;
  background:var(--surface-2)}
.sim-barra i{display:block}
.sim-barra .c{background:var(--s1,#2a78d6)}
.sim-barra .m{background:var(--s3,#1baf7a)}
.sim-ley{display:flex;gap:16px;margin-top:11px;font-size:11px;color:var(--ink-soft);
  flex-wrap:wrap}
.sim-ley i{display:inline-block;width:10px;height:10px;border-radius:2px;
  vertical-align:-1px;margin-right:6px}
.sim-seccion .tw{max-height:430px}
/* Su tabla de facturas lleva min-width:1280px y se desplaza en horizontal.
   Aqui no vale: las dos ultimas columnas, venta y margen, son justo lo que se
   viene a mirar. Reparto fijo, y lo que se recorta es el texto, nunca la cifra. */
.sim-seccion table{width:100%;min-width:0;table-layout:fixed}
.sim-seccion td.sim-corta{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sim-seccion th.n,.sim-seccion td.n,.sim-seccion td.mono{white-space:nowrap}
.sim-seccion th:nth-child(1){width:19%}
.sim-seccion th:nth-child(2){width:11%}
.sim-seccion th:nth-child(3){width:7%}
.sim-seccion th:nth-child(4){width:14%}
.sim-seccion th:nth-child(5){width:8%}
.sim-seccion th:nth-child(6){width:9%}
.sim-seccion th:nth-child(7){width:11%}
.sim-seccion th:nth-child(8){width:11%}
.sim-seccion th:nth-child(9){width:10%}
.sim-pill{font:9px var(--mono);letter-spacing:.05em;padding:2px 6px;border-radius:3px;
  background:var(--surface-2);color:var(--ink-soft);white-space:nowrap}
.sim-pill.margen{background:var(--warning-soft);color:var(--warning)}
</style>
"""

MARKUP = """
  <section class="card sim-seccion view-hidden" id="sim-seccion" style="margin:0 0 22px">
    <h2 data-t="titulo"></h2>
    <p class="hint" data-t="lede"></p>

    <div class="sim-nota">
      <div>
        <b data-t="notaTitulo"></b>
        <span data-t="notaCuerpo"></span>
      </div>
    </div>

    <div class="sim-split">
      <div>
        <div class="sim-bloque">
          <h3 data-t="margenTitulo"></h3>
          <p data-t="margenAyuda"></p>
          <div class="sim-margen">
            <b id="sim-margen-val">35%</b><span data-t="margenSobre"></span>
          </div>
          <input type="range" id="sim-margen" min="0" max="120" step="1" value="35">
          <p class="sim-ej" id="sim-ej"></p>
        </div>

        <div class="sim-bloque">
          <h3 data-t="obrasTitulo"></h3>
          <p data-t="obrasAyuda"></p>
          <div id="sim-clientes-in"></div>
        </div>

        <div class="sim-bloque">
          <h3 data-t="tarifasTitulo"></h3>
          <p data-t="tarifasAyuda"></p>
          <div id="sim-tarifas-in"></div>
          <button class="btn" type="button" id="sim-limpiar" data-t="vaciar"
                  style="margin-top:10px"></button>
        </div>

        <div class="sim-bloque">
          <h3 data-t="nofactTitulo"></h3>
          <p data-t="nofactAyuda"></p>
          <div id="sim-nofact"></div>
        </div>
      </div>

      <div>
        <div class="tiles" id="sim-tiles"></div>
        <ul class="sim-avisos" id="sim-avisos"></ul>

        <div class="sim-bloque" style="margin-bottom:14px">
          <h3 data-t="clientesTitulo"></h3>
          <p data-t="clientesAyuda"></p>
          <div id="sim-clientes"></div>
          <div class="sim-ley">
            <span><i class="c" style="background:var(--s1,#2a78d6)"></i><span data-t="leyCoste"></span></span>
            <span><i class="m" style="background:var(--s3,#1baf7a)"></i><span data-t="leyMargen"></span></span>
          </div>
        </div>

        <div class="sim-bloque">
          <h3 data-t="propuestasTitulo"></h3>
          <p data-t="propuestasAyuda"></p>
          <div class="tw"><table>
            <thead><tr>
              <th data-t="thCliente"></th><th data-t="thObra"></th>
              <th data-t="thSemana"></th><th data-t="thTrabajo"></th>
              <th class="n" data-t="thHoras"></th><th class="n" data-t="thTarifa"></th>
              <th></th>
              <th class="n" data-t="thVenta"></th><th class="n" data-t="thMargen"></th>
            </tr></thead>
            <tbody id="sim-tbody"></tbody>
          </table></div>
        </div>
      </div>
    </div>
  </section>
"""

JS = r"""
<script>
// Simulador de facturacion. Aislado en su propio ambito: el panel original
// ya define $, eur y estado en el global, y no se tocan.
(function () {
  const SIM = __SIM__;

  // Los dos idiomas del panel. Su traductor no entra aqui (la seccion esta en
  // su lista de exclusiones), asi que estos textos son los definitivos: si hay
  // que corregir el neerlandes, se corrige aqui.
  const T = {
    en: {
      titulo: 'Client billing',
      lede: 'The hours your contractors bill you, grouped by client, site and ISO week, priced with whatever model you choose. Move the margin or type an agreed rate and every figure recalculates.',
      notaTitulo: 'This issues no invoices',
      notaCuerpo: 'A projection calculated from what your suppliers have billed you, not from the hours recorded in the planning. If a contractor billed too much, the projection inherits the error.',
      margenTitulo: 'Default margin',
      margenAyuda: 'Applied whenever no rate has been agreed for that site and trade.',
      margenSobre: 'on cost',
      ejemplo: (v) => 'An hour that costs you 40,00 is billed at ' + v + '.',
      obrasTitulo: 'Which client each site belongs to',
      obrasAyuda: 'Purchase invoices name the site, not the client. Without this there is nobody to bill.',
      obraPlaceholder: 'client name',
      tarifasTitulo: 'Agreed rates',
      tarifasAyuda: 'Sale price per hour. Left empty, the margin applies. One row per combination that appears in the invoices.',
      tarifaPlaceholder: 'margin',
      vaciar: 'Clear and use the margin only',
      nofactTitulo: 'What is not rebilled',
      nofactAyuda: 'Paid to the contractor but never charged to the client. Travel hours are the typical case.',
      clientesTitulo: 'Per client',
      clientesAyuda: 'Contractor cost with your margin on top, over the billable total.',
      leyCoste: 'Contractor cost',
      leyMargen: 'Your margin',
      propuestasTitulo: 'Invoice proposals',
      propuestasAyuda: 'One per client, site, week and trade. This is what would be issued if the pricing model were this one.',
      thCliente: 'Client', thObra: 'Site', thSemana: 'Week', thTrabajo: 'Trade',
      thHoras: 'Hours', thTarifa: 'Rate/h', thVenta: 'Sale', thMargen: 'Margin',
      tHoras: 'Billable hours', tCoste: 'Cost EUR', tVenta: 'Sale EUR',
      tMargen: 'Margin EUR', tPct: 'Margin on sale',
      nLineas: (n) => n + (n === 1 ? ' line' : ' lines'),
      eCoste: 'what it costs you', eVenta: 'what would be invoiced',
      ePerdida: 'you are losing money', eAjustado: 'thin margin',
      sinClienteTitulo: 'Sites with no client:',
      sinClienteTexto: '. Those hours cannot be billed to anyone until you say who each site belongs to.',
      negativoTitulo: 'Negative margin:',
      negativoTexto: 'at these prices the sale does not cover what the contractors cost you.',
      descartado: (h, e) => h + ' h costing you ' + e + ' EUR that are not rebilled.',
      nada: 'Nothing to bill with these settings.',
      yMas: (n) => 'And ' + n + ' more lines.',
      pillPactada: 'agreed', pillMargen: 'margin',
      tipCoste: 'cost ', tipY: ' and ', tipVenta: ' · sale ',
      sinCliente: (obra) => '— ' + obra + ', no client —',
    },
    nl: {
      titulo: 'Facturatie aan opdrachtgevers',
      lede: 'De uren die de zzp’ers jullie factureren, gegroepeerd per opdrachtgever, werf en ISO-week, geprijsd met het model dat jullie kiezen. Verschuif de marge of vul een afgesproken tarief in en alles rekent opnieuw.',
      notaTitulo: 'Dit verstuurt geen facturen',
      notaCuerpo: 'Een projectie berekend uit wat de leveranciers jullie hebben gefactureerd, niet uit de uren in de planning. Heeft een zzp’er te veel gefactureerd, dan neemt de projectie die fout over.',
      margenTitulo: 'Standaardmarge',
      margenAyuda: 'Wordt toegepast zodra er voor die werf en dat werk geen tarief is afgesproken.',
      margenSobre: 'op de kostprijs',
      ejemplo: (v) => 'Een uur dat jullie 40,00 kost, wordt gefactureerd voor ' + v + '.',
      obrasTitulo: 'Bij welke opdrachtgever elke werf hoort',
      obrasAyuda: 'Inkoopfacturen noemen de werf, niet de opdrachtgever. Zonder dit is er niemand om te factureren.',
      obraPlaceholder: 'naam opdrachtgever',
      tarifasTitulo: 'Afgesproken tarieven',
      tarifasAyuda: 'Verkoopprijs per uur. Leeg gelaten geldt de marge. Eén regel per combinatie die in de facturen voorkomt.',
      tarifaPlaceholder: 'marge',
      vaciar: 'Leegmaken en alleen de marge gebruiken',
      nofactTitulo: 'Wat niet wordt doorbelast',
      nofactAyuda: 'Wordt aan de zzp’er betaald maar niet aan de opdrachtgever doorberekend. Reisuren zijn het typische geval.',
      clientesTitulo: 'Per opdrachtgever',
      clientesAyuda: 'Kostprijs van de zzp’ers met jullie marge erbovenop, over het declarabele totaal.',
      leyCoste: 'Kostprijs zzp’ers',
      leyMargen: 'Jullie marge',
      propuestasTitulo: 'Factuurvoorstellen',
      propuestasAyuda: 'Eén per opdrachtgever, werf, week en werk. Dit is wat verstuurd zou worden als het prijsmodel dit was.',
      thCliente: 'Opdrachtgever', thObra: 'Werf', thSemana: 'Week', thTrabajo: 'Werk',
      thHoras: 'Uren', thTarifa: 'Tarief/u', thVenta: 'Omzet', thMargen: 'Marge',
      tHoras: 'Declarabele uren', tCoste: 'Kostprijs EUR', tVenta: 'Omzet EUR',
      tMargen: 'Marge EUR', tPct: 'Marge op omzet',
      nLineas: (n) => n + (n === 1 ? ' regel' : ' regels'),
      eCoste: 'wat het jullie kost', eVenta: 'wat gefactureerd zou worden',
      ePerdida: 'jullie verliezen geld', eAjustado: 'krappe marge',
      sinClienteTitulo: 'Werven zonder opdrachtgever:',
      sinClienteTexto: '. Die uren kunnen aan niemand worden gefactureerd zolang niet bekend is bij wie elke werf hoort.',
      negativoTitulo: 'Negatieve marge:',
      negativoTexto: 'tegen deze prijzen dekt de omzet niet wat de zzp’ers jullie kosten.',
      descartado: (h, e) => h + ' uur die jullie ' + e + ' EUR kosten en niet worden doorbelast.',
      nada: 'Niets te factureren met deze instellingen.',
      yMas: (n) => 'En nog ' + n + ' regels.',
      pillPactada: 'afgesproken', pillMargen: 'marge',
      tipCoste: 'kostprijs ', tipY: ' en ', tipVenta: ' · tarief ',
      sinCliente: (obra) => '— ' + obra + ', geen opdrachtgever —',
    },
  };
  const t = () => T[document.documentElement.lang === 'nl' ? 'nl' : 'en'];

  const $ = (s) => document.querySelector(s);
  // nl-NL, como el resto del panel: millares con punto, decimales con coma.
  const eur = (v) => v.toLocaleString('nl-NL', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const eur0 = (v) => v.toLocaleString('nl-NL', {maximumFractionDigits: 0});
  const hh = (v) => v.toLocaleString('nl-NL', {minimumFractionDigits: 1, maximumFractionDigits: 1});
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  const st = {
    margen: SIM.sugerido.margen,
    clientes: {...SIM.sugerido.obras},
    tarifas: {...SIM.sugerido.tarifas},
    noFact: new Set(SIM.sugerido.no_facturable),
  };

  function calcular() {
    const grupos = new Map(), descartadas = new Map(), sinCliente = new Set();
    for (const l of SIM.lineas) {
      if (st.noFact.has(l.trabajo)) {
        const d = descartadas.get(l.trabajo) || {horas: 0, coste: 0};
        d.horas += l.horas; d.coste += l.horas * l.coste_hora;
        descartadas.set(l.trabajo, d); continue;
      }
      let cliente = (st.clientes[l.obra] || '').trim();
      const huerfana = !cliente;
      if (huerfana) { sinCliente.add(l.obra); cliente = t().sinCliente(l.obra); }

      const pactada = st.tarifas[l.obra + '|' + l.trabajo];
      const usaPactada = pactada != null && pactada > 0;
      const ventaHora = usaPactada ? pactada : l.coste_hora * (1 + st.margen);

      const k = [cliente, l.obra, l.semana, l.trabajo].join('\u0000');
      const g = grupos.get(k) || {
        cliente, obra: l.obra, semana: l.semana, trabajo: l.trabajo,
        horas: 0, coste: 0, venta: 0, ventaHora,
        pactada: usaPactada, costes: new Set(), huerfana,
      };
      g.horas += l.horas;
      g.coste += l.horas * l.coste_hora;
      g.venta += l.horas * ventaHora;
      g.costes.add(l.coste_hora);
      grupos.set(k, g);
    }

    const filas = [...grupos.values()].sort((a, b) =>
      b.semana.localeCompare(a.semana) || a.cliente.localeCompare(b.cliente) ||
      a.obra.localeCompare(b.obra) || a.trabajo.localeCompare(b.trabajo));

    const clientes = new Map();
    let horas = 0, coste = 0, venta = 0;
    for (const f of filas) {
      horas += f.horas; coste += f.coste; venta += f.venta;
      const c = clientes.get(f.cliente) || {cliente: f.cliente, horas: 0, coste: 0, venta: 0};
      c.horas += f.horas; c.coste += f.coste; c.venta += f.venta;
      clientes.set(f.cliente, c);
    }
    return {
      filas, horas, coste, venta, margen: venta - coste,
      clientes: [...clientes.values()].sort((a, b) => b.venta - a.venta),
      descartadas: [...descartadas.entries()].map(([trabajo, d]) => ({trabajo, ...d})),
      sinCliente: [...sinCliente].sort(),
    };
  }

  function pintarTiles(r) {
    const L = t();
    const pct = r.venta ? (r.margen / r.venta) * 100 : 0;
    const clase = r.margen < 0 ? 'crit' : pct < 15 ? 'warn' : '';
    const datos = [
      {v: hh(r.horas), k: L.tHoras, e: L.nLineas(r.filas.length)},
      {v: eur0(r.coste), k: L.tCoste, e: L.eCoste},
      {v: eur0(r.venta), k: L.tVenta, e: L.eVenta},
      {v: eur0(r.margen), k: L.tMargen, c: clase, e: ''},
      {v: pct.toFixed(1) + '%', k: L.tPct, c: clase,
       e: r.margen < 0 ? L.ePerdida : pct < 15 ? L.eAjustado : ''},
    ];
    const cont = $('#sim-tiles'); cont.textContent = '';
    for (const d of datos) {
      const el = document.createElement('div'); el.className = 'tile ' + (d.c || '');
      const b = document.createElement('b'); b.textContent = d.v;
      const s = document.createElement('span'); s.textContent = d.k;
      el.append(b, s);
      if (d.e) { const em = document.createElement('em'); em.textContent = d.e; el.append(em); }
      cont.append(el);
    }
  }

  function pintarAvisos(r) {
    const L = t();
    const ul = $('#sim-avisos'); ul.textContent = '';
    const add = (titulo, texto, leve) => {
      const li = document.createElement('li');
      if (leve) li.className = 'leve';
      const b = document.createElement('b'); b.textContent = titulo + ' ';
      li.append(b, document.createTextNode(texto)); ul.append(li);
    };
    if (r.sinCliente.length) {
      add(L.sinClienteTitulo, r.sinCliente.join(', ') + L.sinClienteTexto);
    }
    if (r.margen < 0) add(L.negativoTitulo, L.negativoTexto);
    for (const d of r.descartadas) {
      add(cap(d.trabajo) + ':', L.descartado(hh(d.horas), eur(d.coste)), true);
    }
  }

  function pintarClientes(r) {
    const L = t();
    const cont = $('#sim-clientes'); cont.textContent = '';
    if (!r.clientes.length) {
      const p = document.createElement('p');
      p.textContent = L.nada; cont.append(p); return;
    }
    const max = Math.max(...r.clientes.map((c) => c.venta), 1);
    for (const c of r.clientes) {
      const margen = c.venta - c.coste;
      const pct = c.venta ? (margen / c.venta) * 100 : 0;
      const div = document.createElement('div'); div.className = 'sim-cli';
      const h = document.createElement('div'); h.className = 'sim-cli-h';
      const b = document.createElement('b'); b.textContent = c.cliente;
      const sp = document.createElement('span');
      sp.append(document.createTextNode(hh(c.horas) + ' h · ' + eur(c.venta) + ' EUR · '));
      const fuerte = document.createElement('strong');
      fuerte.textContent = pct.toFixed(1) + '%';
      if (margen < 0) fuerte.style.color = 'var(--critical)';
      sp.append(fuerte); h.append(b, sp);

      const barra = document.createElement('div'); barra.className = 'sim-barra';
      const ancho = (c.venta / max) * 100;
      const parte = c.venta > 0 ? Math.max(Math.min(c.coste / c.venta, 1), 0) : 1;
      const ic = document.createElement('i'); ic.className = 'c';
      ic.style.width = (ancho * parte) + '%';
      ic.title = L.leyCoste + ' ' + eur(c.coste) + ' EUR';
      const im = document.createElement('i'); im.className = 'm';
      im.style.width = (ancho * (1 - parte)) + '%';
      im.title = L.leyMargen + ' ' + eur(margen) + ' EUR';
      barra.append(ic, im);
      div.append(h, barra); cont.append(div);
    }
  }

  function pintarTabla(r) {
    const L = t();
    const tb = $('#sim-tbody'); tb.textContent = '';
    for (const f of r.filas.slice(0, 300)) {
      const tr = document.createElement('tr');
      const costes = [...f.costes].sort((a, b) => a - b);
      tr.title = L.tipCoste + costes.map(eur).join(L.tipY) + '/h'
        + L.tipVenta + eur(f.ventaHora) + '/h';
      for (const [v, c] of [[f.cliente, 'sim-corta'], [f.obra, 'sim-corta'],
                            [f.semana, 'mono'], [cap(f.trabajo), 'sim-corta'],
                            [hh(f.horas), 'n'], [eur(f.ventaHora), 'n']]) {
        const td = document.createElement('td'); td.className = c;
        td.textContent = v; tr.append(td);
      }
      const tdO = document.createElement('td');
      const pill = document.createElement('span');
      pill.className = 'sim-pill' + (f.pactada ? '' : ' margen');
      pill.textContent = f.pactada ? L.pillPactada : L.pillMargen;
      tdO.append(pill); tr.append(tdO);
      for (const v of [eur(f.venta), eur(f.venta - f.coste)]) {
        const td = document.createElement('td'); td.className = 'n';
        td.textContent = v; tr.append(td);
      }
      tb.append(tr);
    }
    if (r.filas.length > 300) {
      const tr = document.createElement('tr'), td = document.createElement('td');
      td.colSpan = 9; td.textContent = L.yMas(r.filas.length - 300);
      tr.append(td); tb.append(tr);
    }
  }

  function pintarTextos() {
    const L = t();
    for (const el of document.querySelectorAll('#sim-seccion [data-t]')) {
      if (L[el.dataset.t]) el.textContent = L[el.dataset.t];
    }
    for (const inp of document.querySelectorAll('#sim-clientes-in input')) {
      inp.placeholder = L.obraPlaceholder;
    }
    for (const inp of document.querySelectorAll('#sim-tarifas-in input')) {
      inp.placeholder = L.tarifaPlaceholder;
    }
  }

  function render() {
    const r = calcular();
    pintarTiles(r); pintarAvisos(r); pintarClientes(r); pintarTabla(r);
    $('#sim-margen-val').textContent = Math.round(st.margen * 100) + '%';
    $('#sim-ej').textContent = t().ejemplo(eur(40 * (1 + st.margen)));
  }

  function construir() {
    const cl = $('#sim-clientes-in');
    for (const obra of SIM.obras) {
      const row = document.createElement('div'); row.className = 'sim-fila';
      row.style.gridTemplateColumns = '92px minmax(0,1fr)';
      const lab = document.createElement('label');
      lab.setAttribute('for', 'sim-cl-' + obra); lab.textContent = obra;
      const inp = document.createElement('input');
      inp.type = 'text'; inp.id = 'sim-cl-' + obra;
      inp.value = st.clientes[obra] || '';
      inp.addEventListener('input', () => { st.clientes[obra] = inp.value; render(); });
      row.append(lab, inp); cl.append(row);
    }

    const tf = $('#sim-tarifas-in');
    for (const c of SIM.combinaciones) {
      const clave = c.obra + '|' + c.trabajo;
      const row = document.createElement('div'); row.className = 'sim-fila';
      const lab = document.createElement('label');
      lab.setAttribute('for', 'sim-tf-' + clave); lab.textContent = cap(c.trabajo);
      const i = document.createElement('i'); i.textContent = c.obra; lab.append(i);
      const inp = document.createElement('input');
      inp.type = 'number'; inp.id = 'sim-tf-' + clave; inp.min = '0'; inp.step = '0.50';
      if (st.tarifas[clave] != null) inp.value = st.tarifas[clave];
      inp.addEventListener('input', () => {
        const v = parseFloat(inp.value);
        st.tarifas[clave] = Number.isFinite(v) && v > 0 ? v : null;
        render();
      });
      row.append(lab, inp); tf.append(row);
    }

    const horasPor = new Map();
    for (const l of SIM.lineas) horasPor.set(l.trabajo, (horasPor.get(l.trabajo) || 0) + l.horas);
    const nf = $('#sim-nofact');
    for (const trabajo of SIM.trabajos) {
      const lab = document.createElement('label'); lab.className = 'sim-chk';
      const inp = document.createElement('input');
      inp.type = 'checkbox'; inp.id = 'sim-nf-' + trabajo;
      inp.checked = st.noFact.has(trabajo);
      inp.addEventListener('change', () => {
        if (inp.checked) st.noFact.add(trabajo); else st.noFact.delete(trabajo);
        render();
      });
      const texto = document.createElement('span'); texto.textContent = cap(trabajo);
      const n = document.createElement('i');
      n.textContent = hh(horasPor.get(trabajo) || 0) + ' h';
      lab.append(inp, texto, n); nf.append(lab);
    }

    const rango = $('#sim-margen');
    rango.value = Math.round(st.margen * 100);
    rango.addEventListener('input', (e) => {
      st.margen = parseInt(e.target.value, 10) / 100; render();
    });
    $('#sim-limpiar').addEventListener('click', () => {
      for (const c of SIM.combinaciones) {
        const clave = c.obra + '|' + c.trabajo;
        st.tarifas[clave] = null;
        const inp = document.getElementById('sim-tf-' + clave);
        if (inp) inp.value = '';
      }
      render();
    });

    // Su interruptor EN/NL avisa por este evento; la seccion se repinta entera.
    window.addEventListener('bms:language', () => { pintarTextos(); render(); });
  }

  // La entrada del dock esta puesta en su paquete y, al pulsarla, su propio
  // manejador pulsa este boton. Sigue oculto, como los otros tres: es el
  // puente entre el dock y las secciones del panel.
  function registrarPestana() {
    const nav = document.querySelector('.top-nav');
    const mia = document.querySelector('#sim-seccion');
    if (!nav || !mia) return;

    const otras = [
      document.querySelector('#matrix') && document.querySelector('#matrix').parentElement,
      document.querySelector('#alerts'),
      document.querySelector('.charts'),
      document.querySelector('#stack') && document.querySelector('#stack').parentElement,
      document.querySelector('.tablecard'),
    ].filter(Boolean);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.dataset.section = 'facturacion';
    btn.setAttribute('aria-selected', 'false');
    btn.textContent = 'Facturación a clientes';
    nav.append(btn);

    btn.addEventListener('click', () => {
      nav.querySelectorAll('button').forEach((b) =>
        b.setAttribute('aria-selected', String(b === btn)));
      otras.forEach((e) => e.classList.add('view-hidden'));
      mia.classList.remove('view-hidden');
    });
    // Los tres botones originales conservan su onclick; esto solo se suma.
    nav.querySelectorAll('button').forEach((b) => {
      if (b !== btn) b.addEventListener('click', () => mia.classList.add('view-hidden'));
    });
  }

  function arrancar() { construir(); pintarTextos(); render(); registrarPestana(); }

  // Su aplicacion monta el dock al terminar de cargar, y construir a la vez se
  // lo retrasa casi un segundo. Se espera a que este puesto; si no llegara, a
  // los cinco segundos se construye igual, para no quedarnos sin seccion.
  function cuandoTerminenEllos() {
    if (document.querySelector('.panel-dock a')) { arrancar(); return; }
    let hecho = false;
    const ya = () => {
      if (hecho) return;
      hecho = true; obs.disconnect(); clearTimeout(reloj); arrancar();
    };
    const obs = new MutationObserver(() => {
      if (document.querySelector('.panel-dock a')) ya();
    });
    obs.observe(document.body, {childList: true, subtree: true});
    const reloj = setTimeout(ya, 5000);
  }

  if (document.readyState === 'complete') cuandoTerminenEllos();
  else window.addEventListener('load', cuandoTerminenEllos);
})();
</script>
"""

ICONO = (
    'x.jsxs("svg",{xmlns:"http://www.w3.org/2000/svg",width:24,height:24,'
    'viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,'
    'strokeLinecap:"round",strokeLinejoin:"round",className:"h-full w-full",'
    'children:['
    'x.jsx("path",{d:"M4 10h12"},"a"),'
    'x.jsx("path",{d:"M4 14h9"},"b"),'
    'x.jsx("path",{d:"M19 6a7.7 7.7 0 0 0-5.2-2A7.9 7.9 0 0 0 6 12c0 4.4 3.5 8 '
    '7.8 8 2 0 3.8-.8 5.2-2"},"c")'
    ']})'
)

# Cuatro retoques dentro de su paquete. Ninguno toca logica: los cuatro son
# literales de datos. Sin el primero la seccion existe pero no hay como llegar
# a ella, porque su barra de pestanas esta oculta y quien navega es el dock.
_EDICIONES: list[tuple[str, str, str]] = [
    (
        "la entrada en el dock",
        '{title:"Reviewed invoices",href:"#cleared",icon:x.jsx(ME,{className:"h-full w-full"})}]',
        '{title:"Reviewed invoices",href:"#cleared",icon:x.jsx(ME,{className:"h-full w-full"})},'
        '{title:"Facturación a clientes",href:"#facturacion",icon:__ICONO__}]',
    ),
    (
        "el orden de las secciones, para que la transicion deslice hacia el lado correcto",
        'Dy=["agent","overview","analysis","invoices","cleared"]',
        'Dy=["agent","overview","analysis","invoices","cleared","facturacion"]',
    ),
    (
        "el titulo de la entrada, en su glosario",
        'const wl={"Reviewed invoices":',
        'const wl={"Facturación a clientes":["Client billing","Facturatie"],'
        '"Reviewed invoices":',
    ),
    (
        "la seccion, fuera del traductor: recorre cada nodo de texto en cada cambio",
        "s='#cleared-invoices-root,",
        "s='#sim-seccion,#cleared-invoices-root,",
    ),
]
EDICIONES = [(m, b, p.replace("__ICONO__", ICONO)) for m, b, p in _EDICIONES]


def parchear(origen: Path, destino: Path, datos_sim: dict) -> None:
    # Bytes, no read_text: read_text traduce \r\n a \n y eso ya seria tocar su
    # fichero. Lo suyo se copia tal cual.
    html = origen.read_bytes().decode("utf-8")

    if "sim-seccion" in html:
        raise SystemExit("El fichero ya lleva el simulador.")

    # 1. Estilos, justo antes de cerrar la cabecera.
    assert html.count("</head>") == 1
    html = html.replace("</head>", CSS + "</head>", 1)

    # 2. La seccion, antes del pie.
    ancla = '<footer class="page">'
    assert html.count(ancla) == 1, "no se encontro el pie de pagina"
    html = html.replace(ancla, MARKUP + "\n  " + ancla, 1)

    # 3. Datos y logica, al final del todo, para que corra despues de su
    #    script de pestanas y del bundle de React.
    payload = json.dumps(datos_sim, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")
    script = JS.replace("__SIM__", payload)

    assert "</body>" in html
    html = html.replace("</body>", script + "\n</body>", 1)

    # 4. Los cuatro retoques en su paquete.
    for motivo, buscar, poner in EDICIONES:
        if html.count(buscar) != 1:
            raise SystemExit(
                f"no se pudo aplicar «{motivo}»: el ancla aparece "
                f"{html.count(buscar)} veces, se esperaba una"
            )
        html = html.replace(buscar, poner, 1)

    destino.write_bytes(html.encode("utf-8"))


def main() -> None:
    import argparse
    import glob

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("origen", help="el panel tal como lo exporta vuestra compilacion")
    p.add_argument("destino", help="donde escribir la copia con el simulador")
    p.add_argument("--extracciones", default="out",
                   help="carpeta con los JSON de las extracciones (por defecto: out)")
    p.add_argument("--tarifas", default="config/tarifas.yaml",
                   help="tabla de tarifas; si no existe, se arranca en blanco")
    args = p.parse_args()

    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz / "src"))
    from bms_agent.facturacion import cargar_tarifas, lineas_para_simulador

    ficheros = sorted(glob.glob(f"{args.extracciones}/*.json"))
    if not ficheros:
        raise SystemExit(f"no hay extracciones en {args.extracciones}/")
    registros = [json.loads(Path(f).read_text(encoding="utf-8")) for f in ficheros]

    origen, destino = Path(args.origen), Path(args.destino)
    parchear(origen, destino, lineas_para_simulador(registros, cargar_tarifas(args.tarifas)))
    print(
        f"{destino}  ({destino.stat().st_size:,} bytes, "
        f"{destino.stat().st_size - origen.stat().st_size:+,} respecto al original)"
    )


if __name__ == "__main__":
    main()
