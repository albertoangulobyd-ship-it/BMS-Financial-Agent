// Finance Bento de Aurora (components/ui/finance-bento-component.tsx, entrega del 28-10-2026): la
// misma estructura (markup + mount + FinanceBento), las mismas tarjetas, la cifra de puntos
// (DotNumber, 96 columnas), el medidor semicircular de 57 marcas y las barras. Cambios
// permitidos (especificacion §4.1 y §4.2):
// - C: markup() y mount() crean los nodos con createElement/createElementNS y ponen el texto
//   con textContent (sin innerHTML ni esc); el <style> en linea va a finance-bento-component.css;
//   cada style="..." pasa a el.style (CSSOM); onclick pasa a addEventListener; sin el sello
//   del autor (credit), que llevaba una direccion de fuera y la app nunca lo pinta;
// - E: euros desde centimos enteros (lib/format.ts). La cifra de puntos dice "€ 1.234,56":
//   se anade el glifo "." en la misma rejilla de 5x7 (el "€" y la "," ya estaban);
// - D e I: los textos, del diccionario; los enlaces a una carpeta llaman a onOpenParty (sin
//   direccion: la app no usa la barra de direcciones).
import * as React from 'react';
import { NBSP, formatMoney } from '@/lib/format';
import './finance-bento-component.css';

/** Los datos del resumen (finance-bento.tsx los saca de las lecturas). Importes en centimos. */
export interface FinanceBentoData {
  capturedAt: string;
  receivable: number;
  payable: number;
  documents: number;
  invoices: number;
  parties: { id: number; name: string; type: 'clientes' | 'proveedores'; balance: number; documents: number }[];
  analysis: { total: number; newCount: number; duplicateCount: number } | null;
}

/** Los textos de las tarjetas (del diccionario: los arma finance-bento.tsx). */
export interface FinanceBentoTexts {
  period: string;
  currency: string;
  currencyBadge: string;
  pending: string;
  pendingNote: string;
  receivable: string;
  payable: string;
  allocation: string;
  allocationLabel: string;
  allocationCaption: string;
  collect: string;
  pay: string;
  clientsWithBalance: (n: number) => string;
  providersWithBalance: (n: number) => string;
  documents: string;
  invoicesInArchive: (n: number) => string;
  folders: string;
  foldersNote: string;
  where: string;
  companyType: string;
  clients: string;
  providers: string;
  noFolders: string;
  lastReview: string;
  newCount: string;
  duplicateCount: string;
  reviewed: (n: number) => string;
  noCopies: string;
  explore: string;
  noReview: string;
  noReviewNote: string;
  composition: string;
  compositionLabel: (invoices: number, others: number) => string;
  invoicesLabel: string;
  othersLabel: string;
}

export interface FinanceBentoProps {
  data: FinanceBentoData;
  texts: FinanceBentoTexts;
  title?: string;
  subtitle?: string;
  className?: string;
  style?: React.CSSProperties;
  /** Un enlace a una carpeta ("Donde esta el saldo") o a Documentos (sin empresa). */
  onOpenParty?: (party: { id: number; type: 'clientes' | 'proveedores' } | null) => void;
}

type Attrs = Record<string, string | number>;

/** Un elemento HTML con su clase, sus atributos y su texto (sin HTML). */
function h(tag: string, attrs: Attrs = {}, text?: string, parent?: Element): HTMLElement {
  const e = document.createElement(tag);
  for (const k in attrs) e.setAttribute(k, String(attrs[k]));
  if (text !== undefined) e.textContent = text;
  parent?.appendChild(e);
  return e;
}

const markup = (root: HTMLElement, o: { title: string; subtitle: string; texts: FinanceBentoTexts }) => {
  const canvas = h('div', { class: 'fpb-c canvas' }, undefined, root);
  const top = h('div', { class: 'top' }, undefined, canvas);
  const title = h('h1', {}, o.title, top);
  h('span', { id: 'asof' }, o.subtitle, title);
  const ctrls = h('div', { class: 'ctrls' }, undefined, top);
  h('div', { class: 'seg', id: 'period', role: 'group', 'aria-label': o.texts.period }, undefined, ctrls);
  h('div', { class: 'seg', id: 'ccy', role: 'group', 'aria-label': o.texts.currency }, undefined, ctrls);
  const grid = h('div', { class: 'grid', id: 'grid' }, undefined, canvas);
  h('section', { class: 'card h1', id: 'nw' }, undefined, grid);
  h('section', { class: 'card h1', id: 'alloc' }, undefined, grid);
  h('section', { class: 'card h2 kpi', id: 'ret' }, undefined, grid);
  h('section', { class: 'card glass h2 kpi', id: 'cash' }, undefined, grid);
  h('section', { class: 'card glass h2 kpi', id: 'pay' }, undefined, grid);
  h('section', { class: 'card glass h2 kpi', id: 'goals' }, undefined, grid);
  h('section', { class: 'card h3', id: 'flow' }, undefined, grid);
  h('section', { class: 'card h3', id: 'crypto' }, undefined, grid);
  h('section', { class: 'card h3', id: 'stocks' }, undefined, grid);
  h('div', { class: 'tip', id: 'tip' }, undefined, root);
};

function mount(root: HTMLElement, data: FinanceBentoData, texts: FinanceBentoTexts, onOpenParty?: FinanceBentoProps['onOpenParty']) {
  let alive = true;
  const frames = new Set<number>();
  const RAF = (cb: (t: number) => void) => {
    if (!alive) return 0;
    const id = requestAnimationFrame((t) => {
      frames.delete(id);
      if (alive) cb(t);
    });
    frames.add(id);
    return id;
  };
  const $id = (id: string) => root.querySelector<HTMLElement>('#' + id)!;

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ease = (t: number) => 1 - Math.pow(1 - t, 3);
  const NS = 'http://www.w3.org/2000/svg';
  const el = (t: string, a: Attrs = {}, p?: Element) => {
    const e = document.createElementNS(NS, t);
    for (const k in a) e.setAttribute(k, String(a[k]));
    p && p.appendChild(e);
    return e;
  };

  const money = (v: number) => formatMoney(Math.round(v));
  const F: Record<string, string[]> = {
    '0': ['01110', '10001', '10011', '10101', '11001', '10001', '01110'],
    '1': ['00100', '01100', '00100', '00100', '00100', '00100', '01110'],
    '2': ['01110', '10001', '00001', '00010', '00100', '01000', '11111'],
    '3': ['11111', '00010', '00100', '00010', '00001', '10001', '01110'],
    '4': ['00010', '00110', '01010', '10010', '11111', '00010', '00010'],
    '5': ['11111', '10000', '11110', '00001', '00001', '10001', '01110'],
    '6': ['00110', '01000', '10000', '11110', '10001', '10001', '01110'],
    '7': ['11111', '00001', '00010', '00100', '01000', '01000', '01000'],
    '8': ['01110', '10001', '10001', '01110', '10001', '10001', '01110'],
    '9': ['01110', '10001', '10001', '01111', '00001', '00010', '01100'],
    $: ['00100', '01111', '10100', '01110', '00101', '11110', '00100'],
    '€': ['00111', '01000', '11110', '01000', '11110', '01000', '00111'],
    ',': ['0', '0', '0', '0', '0', '1', '1'],
    // E: el punto de los miles, en la misma rejilla.
    '.': ['0', '0', '0', '0', '0', '0', '1'],
    ' ': ['00', '00', '00', '00', '00', '00', '00'],
  };
  function DotNumber(host: Element, pitch: number) {
    const cols = 96,
      svg = el('svg', { class: 'dots', 'aria-hidden': 'true' }, host),
      cells: [number, number, SVGElement][] = [];
    for (let c = 0; c < cols; c++)
      for (let r = 0; r < 7; r++) {
        const ci = el('circle', { cx: c * pitch + pitch / 2, cy: r * pitch + pitch / 2, r: pitch * 0.36, fill: '#fff', opacity: 0 }, svg);
        ci.style.transitionDelay = c * 7 + 'ms';
        cells.push([c, r, ci]);
      }
    const set = (t: string) => {
      const on = new Set<number>();
      let x = 0;
      for (const raw of t) {
        const ch = raw === NBSP ? ' ' : raw;
        const g = F[ch] || F[' ']!;
        const w = g[0]!.length;
        for (let r = 0; r < 7; r++) for (let k = 0; k < w; k++) if (g[r]![k] === '1') on.add((x + k) * 8 + r);
        x += w + 1;
      }
      const used = Math.max(1, x - 1);
      for (const [c, r, ci] of cells) {
        const v = on.has(c * 8 + r);
        ci.setAttribute('opacity', String(v ? 1 : c < used ? 0.08 : 0));
        ci.style.transform = v ? 'none' : 'scale(.55)';
      }
      svg.setAttribute('width', String(used * pitch));
      svg.setAttribute('height', String(7 * pitch));
      svg.setAttribute('viewBox', `0 0 ${used * pitch} ${7 * pitch}`);
    };
    let raf = 0,
      cur = 0;
    return {
      count(to: number, dur = 900) {
        cancelAnimationFrame(raf);
        const from = cur,
          t0 = performance.now();
        let last = '';
        const f = (now: number) => {
          const t = reduce ? 1 : Math.min(1, (now - t0) / dur);
          cur = from + (to - from) * ease(t);
          const s = money(cur);
          if (s !== last) {
            set(s);
            last = s;
          }
          if (t < 1) raf = RAF(f);
        };
        raf = RAF(f);
      },
    };
  }

  const d = data;
  // card(id, titulo, cuerpo): el cuerpo lo arma una funcion con nodos (antes, HTML).
  const card = (id: string, title: string, body: (host: HTMLElement) => void) => {
    const node = $id(id);
    node.setAttribute('aria-label', title);
    const inner = h('div', { class: 'in-c' }, undefined, node);
    h('div', { class: 'cap' }, title, inner);
    body(inner);
    h('div', { class: 'rim' }, undefined, node);
    return node;
  };
  // Un enlace sin direccion: se abre con el clic o con Intro.
  const link = (parent: Element, attrs: Attrs, open: () => void) => {
    const a = h('a', { ...attrs, role: 'link', tabindex: 0 }, undefined, parent);
    a.addEventListener('click', (e) => {
      e.preventDefault();
      open();
    });
    a.addEventListener('keydown', (e) => {
      if ((e as KeyboardEvent).key === 'Enter') {
        e.preventDefault();
        open();
      }
    });
    return a;
  };
  $id('period').remove();
  const badge = h('span', { class: 'mono muted' }, texts.currencyBadge, $id('ccy'));
  badge.style.padding = '6px 10px';
  const total = d.receivable + d.payable,
    share = total ? d.receivable / total : 0;
  const nw = card('nw', texts.pending, (c) => {
    const n = h('div', { class: 'nwn', role: 'img', 'aria-label': money(total) }, undefined, c);
    n.style.marginTop = '24px';
    h('p', { class: 'muted' }, texts.pendingNote, c);
    h('div', { class: 'balance-chart' }, undefined, c);
  });
  DotNumber(nw.querySelector('.nwn')!, 6).count(total);
  const chart = nw.querySelector('.balance-chart')!;
  (
    [
      [texts.receivable, d.receivable, '#efedf1'],
      [texts.payable, d.payable, '#77717f'],
    ] as const
  ).forEach(([name, value, color]) => {
    const row = h('div', { class: 'balance-row' }, undefined, chart);
    const label = h('span', {}, name, row);
    h('b', {}, money(value), label);
    const bar = h('i', {}, undefined, h('div', {}, undefined, row));
    bar.style.width = (total ? (value / total) * 100 : 0) + '%';
    bar.style.background = color;
  });
  const al = card('alloc', texts.allocation, (c) => {
    el('svg', { class: 'alg', viewBox: '-150 -150 300 168', role: 'img', 'aria-label': texts.allocationLabel }, c);
    h('div', { class: 'allocation-labels' }, undefined, c);
  });
  const svg = al.querySelector('.alg')!;
  for (let i = 0; i <= 56; i++) {
    const a = Math.PI + (i / 56) * Math.PI;
    el(
      'line',
      {
        x1: 136 * Math.cos(a),
        y1: 136 * Math.sin(a),
        x2: (i % 7 === 0 ? 112 : 118) * Math.cos(a),
        y2: (i % 7 === 0 ? 112 : 118) * Math.sin(a),
        stroke: i / 56 < share ? '#efedf1' : '#504b56',
        'stroke-width': 3.2,
        'stroke-linecap': 'round',
      },
      svg
    );
  }
  el('text', { y: -22, 'text-anchor': 'middle', 'font-size': 48, 'font-weight': 200, fill: 'white' }, svg).textContent = `${Math.round(share * 100)}%`;
  el('text', { y: 2, 'text-anchor': 'middle', 'font-size': 12, fill: '#999' }, svg).textContent = texts.allocationCaption;
  const labels = al.querySelector('.allocation-labels')!;
  h('b', {}, money(d.receivable), h('span', {}, texts.collect + ' ', labels));
  h('b', {}, money(d.payable), h('span', {}, texts.pay + ' ', labels));
  const metric = (value: string, note: string) => (c: HTMLElement) => {
    h('strong', { class: 'big metric' }, value, c);
    h('span', { class: 'muted' }, note, c);
  };
  card('ret', texts.receivable, metric(money(d.receivable), texts.clientsWithBalance(d.parties.filter((p) => p.type === 'clientes' && p.balance > 0).length)));
  card('cash', texts.payable, metric(money(d.payable), texts.providersWithBalance(d.parties.filter((p) => p.type === 'proveedores' && p.balance > 0).length)));
  card('pay', texts.documents, metric(String(d.documents), texts.invoicesInArchive(d.invoices)));
  card('goals', texts.folders, metric(String(d.parties.length), texts.foldersNote));
  const flow = card('flow', texts.where, (c) => {
    h('div', { class: 'seg company-tabs', role: 'group', 'aria-label': texts.companyType }, undefined, c);
    h('div', { class: 'company-bars' }, undefined, c);
  });
  let group: 'clientes' | 'proveedores' = 'clientes';
  function companies() {
    const tabs = flow.querySelector('.company-tabs')!;
    tabs.replaceChildren();
    (['clientes', 'proveedores'] as const).forEach((t) => {
      const b = h('button', { type: 'button', 'aria-pressed': String(group === t), 'data-group': t }, t === 'clientes' ? texts.clients : texts.providers, tabs);
      b.addEventListener('click', () => {
        group = t;
        companies();
      });
    });
    const rows = d.parties.filter((p) => p.type === group).sort((a, b) => b.balance - a.balance),
      max = Math.max(1, ...rows.map((p) => p.balance));
    const bars = flow.querySelector('.company-bars')!;
    bars.replaceChildren();
    if (rows.length)
      rows.forEach((p) => {
        const a = link(bars, {}, () => onOpenParty?.({ id: p.id, type: p.type }));
        const line = h('span', {}, p.name, a);
        h('b', {}, money(p.balance), line);
        h('i', {}, undefined, h('div', {}, undefined, a)).style.width = (p.balance / max) * 100 + '%';
      });
    else h('p', { class: 'muted' }, texts.noFolders, bars);
  }
  companies();
  card('crypto', texts.lastReview, (c) => {
    if (d.analysis) {
      const values = h('div', { class: 'review-values' }, undefined, c);
      const fresh = h('span', {}, undefined, values);
      h('strong', {}, String(d.analysis.newCount), fresh);
      fresh.append(texts.newCount);
      const repeated = h('span', {}, undefined, values);
      h('strong', {}, String(d.analysis.duplicateCount), repeated);
      repeated.append(texts.duplicateCount);
      const p = h('p', { class: 'muted' }, texts.reviewed(d.analysis.total), c);
      p.append(document.createElement('br'), texts.noCopies);
      link(c, {}, () => onOpenParty?.(null)).textContent = texts.explore;
    } else {
      h('p', { class: 'empty-review' }, texts.noReview, c);
      h('p', { class: 'muted' }, texts.noReviewNote, c);
    }
  });
  const others = Math.max(0, d.documents - d.invoices);
  const st = card('stocks', texts.composition, (c) => {
    h('strong', { class: 'big metric' }, String(d.documents), c);
    h('div', { class: 'capsule-chart', role: 'img', 'aria-label': texts.compositionLabel(d.invoices, others) }, undefined, c);
  });
  const counts = [
      [texts.invoicesLabel, d.invoices],
      [texts.othersLabel, others],
    ] as const,
    max = Math.max(1, ...counts.map((x) => x[1]));
  const capsules = st.querySelector('.capsule-chart')!;
  counts.forEach(([label, value]) => {
    const box = h('div', {}, undefined, capsules);
    h('b', {}, String(value), box);
    h('i', {}, undefined, h('div', { class: 'capsule' }, undefined, box)).style.height = (value / max) * 100 + '%';
    h('span', {}, label, box);
  });
  $id('grid').classList.add('in');
  root.querySelectorAll<HTMLElement>('.card').forEach((c, i) => (c.style.transitionDelay = (reduce ? 0 : i * 45) + 'ms'));

  return () => {
    alive = false;
    frames.forEach((f) => cancelAnimationFrame(f));
  };
}

/** markup y mount juntos (lo que hace el efecto de FinanceBento); devuelve la limpieza. */
export function mountFinanceBento(
  root: HTMLElement,
  o: { data: FinanceBentoData; texts: FinanceBentoTexts; title: string; subtitle: string; onOpenParty?: FinanceBentoProps['onOpenParty'] }
): () => void {
  markup(root, { title: o.title, subtitle: o.subtitle, texts: o.texts });
  const stop = mount(root, o.data, o.texts, o.onOpenParty);
  return () => {
    stop();
    root.replaceChildren();
  };
}

export function FinanceBento({ data, texts, title = 'Overview', subtitle = '', className = '', style, onOpenParty }: FinanceBentoProps) {
  const ref = React.useRef<HTMLDivElement>(null);
  const open = React.useRef(onOpenParty);
  open.current = onOpenParty;
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    return mountFinanceBento(el, { data, texts, title, subtitle, onOpenParty: (party) => open.current?.(party) });
  }, [data, title, subtitle, texts]);
  return <div ref={ref} className={`fpb ${className}`} style={style} />;
}
