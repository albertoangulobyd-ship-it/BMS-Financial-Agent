// El resumen general (Finance Bento), con lo de work/test-finance-summary.cjs del dueno: el
// montaje, los saldos, los nombres como texto (nunca HTML), los datos vacios (sin NaN ni
// Infinity), el medidor y la limpieza; ademas, la cifra de puntos en euros y la pregunta en los
// tres idiomas. Sin navegador: un DOM de juguete con lo que usan markup() y mount().
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MESSAGES } from '@/i18n';
import { formatMoney } from '@/lib/format';
import { mountFinanceBento, type FinanceBentoData } from './finance-bento-component';
import { bentoTexts, summaryRequested, summaryText } from './finance-bento';

class FakeNode {
  tag: string;
  attrs = new Map<string, string>();
  children: FakeNode[] = [];
  parent: FakeNode | null = null;
  style: Record<string, string> = {};
  listeners = new Map<string, ((e: unknown) => void)[]>();
  private text = '';
  classList = {
    add: (c: string) => this.attrs.set('class', [this.attrs.get('class') ?? '', c].join(' ').trim()),
  };
  constructor(tag: string) {
    this.tag = tag;
  }
  setAttribute(k: string, v: string) {
    this.attrs.set(k, String(v));
  }
  getAttribute(k: string) {
    return this.attrs.get(k) ?? null;
  }
  appendChild(c: FakeNode) {
    c.parent = this;
    this.children.push(c);
    return c;
  }
  append(...items: (FakeNode | string)[]) {
    for (const i of items) {
      if (typeof i === 'string') {
        const t = new FakeNode('#text');
        t.textContent = i;
        this.appendChild(t);
      } else this.appendChild(i);
    }
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
  }
  replaceChildren() {
    this.children = [];
    this.text = '';
  }
  addEventListener(type: string, fn: (e: unknown) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  set textContent(v: string) {
    this.children = [];
    this.text = v;
  }
  get textContent(): string {
    return this.text + this.children.map((c) => c.textContent).join('');
  }
  get innerHTML(): string {
    throw new Error('innerHTML no se usa');
  }
  all(): FakeNode[] {
    return this.children.flatMap((c) => [c, ...c.all()]);
  }
  private matches(sel: string): boolean {
    if (sel.startsWith('#')) return this.attrs.get('id') === sel.slice(1);
    if (sel.startsWith('.')) return (this.attrs.get('class') ?? '').split(/\s+/).includes(sel.slice(1));
    return this.tag === sel;
  }
  querySelector(sel: string): FakeNode | null {
    return this.all().find((n) => n.matches(sel)) ?? null;
  }
  querySelectorAll(sel: string): FakeNode[] {
    return this.all().filter((n) => n.matches(sel));
  }
}

const texts = (lang: 'es' | 'nl' | 'en') => bentoTexts(MESSAGES[lang]);

const data = (over: Partial<FinanceBentoData> = {}): FinanceBentoData => ({
  capturedAt: '2026-10-28T10:00:00Z',
  receivable: 100000,
  payable: 30000,
  documents: 2,
  invoices: 1,
  parties: [
    { id: 1, name: 'Cliente <A>', type: 'clientes', balance: 100000, documents: 1 },
    { id: 2, name: 'Proveedor B', type: 'proveedores', balance: 30000, documents: 1 },
  ],
  analysis: null,
  ...over,
});

let frames: (() => void)[] = [];
beforeEach(() => {
  frames = [];
  vi.stubGlobal('document', {
    createElement: (tag: string) => new FakeNode(tag),
    createElementNS: (_ns: string, tag: string) => new FakeNode(tag),
  });
  vi.stubGlobal('window', { matchMedia: () => ({ matches: true }) });
  vi.stubGlobal('requestAnimationFrame', (cb: (t: number) => void) => {
    frames.push(() => cb(1000));
    return frames.length;
  });
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
});
afterEach(() => vi.unstubAllGlobals());

const run = () => {
  while (frames.length) frames.shift()!();
};

describe('Finance Bento', () => {
  it('monta las nueve tarjetas con los saldos pendientes, el medidor y los nombres como texto', () => {
    const root = new FakeNode('div');
    const dispose = mountFinanceBento(root as unknown as HTMLElement, { data: data(), texts: texts('es'), title: 'T', subtitle: 'S' });
    run();
    for (const id of ['nw', 'alloc', 'ret', 'cash', 'pay', 'goals', 'flow', 'crypto', 'stocks']) expect(root.querySelector('#' + id), id).not.toBeNull();
    expect(root.querySelector('#period')).toBeNull();
    expect(root.querySelector('#nw')!.textContent).toContain(MESSAGES.es.aurora.bento.pending);
    expect(root.querySelector('#nw')!.textContent).toContain(formatMoney(100000));
    // El nombre va tal cual, como texto (no se interpreta).
    expect(root.querySelector('.company-bars')!.textContent).toContain('Cliente <A>');
    // 100000 / 130000 = 77 %.
    expect(root.querySelector('.alg')!.textContent).toContain('77%');
    expect(root.querySelector('#crypto')!.textContent).toContain(MESSAGES.es.aurora.bento.noReview);
    // La cifra de puntos: "€ 1.300,00" con su aria-label.
    expect(root.querySelector('.nwn')!.getAttribute('aria-label')).toBe(formatMoney(130000));
    const lit = root.querySelector('.dots')!.children.filter((c) => c.getAttribute('opacity') === '1');
    expect(lit.length).toBeGreaterThan(40);
    dispose();
    expect(root.children).toEqual([]);
  });

  it('sin datos: ni NaN ni Infinity, y "Sin expedientes"', () => {
    const root = new FakeNode('div');
    const dispose = mountFinanceBento(root as unknown as HTMLElement, {
      data: data({ receivable: 0, payable: 0, documents: 0, invoices: 0, parties: [] }),
      texts: texts('es'),
      title: 'T',
      subtitle: 'S',
    });
    run();
    const all = root.all();
    for (const n of all) {
      expect(n.textContent).not.toMatch(/NaN|Infinity/);
      for (const v of [...n.attrs.values(), ...Object.values(n.style)]) expect(String(v)).not.toMatch(/NaN|Infinity/);
    }
    expect(root.querySelector('.company-bars')!.textContent).toContain(MESSAGES.es.aurora.bento.noFolders);
    dispose();
  });

  it('las pestanas cambian de grupo y un enlace abre la carpeta de su empresa', () => {
    const root = new FakeNode('div');
    const opened: unknown[] = [];
    mountFinanceBento(root as unknown as HTMLElement, { data: data(), texts: texts('es'), title: 'T', subtitle: 'S', onOpenParty: (p) => opened.push(p) });
    const tabs = root.querySelector('.company-tabs')!;
    const providers = tabs.children.find((b) => b.getAttribute('data-group') === 'proveedores')!;
    providers.listeners.get('click')![0]!({});
    expect(root.querySelector('.company-bars')!.textContent).toContain('Proveedor B');
    const link = root.querySelector('.company-bars')!.children[0]!;
    link.listeners.get('click')![0]!({ preventDefault: () => undefined });
    expect(opened).toEqual([{ id: 2, type: 'proveedores' }]);
  });

  it('la pregunta del resumen, en castellano, neerlandes e ingles', () => {
    for (const q of ['Dame un resumen general', '¿Cómo vamos?', 'Geef me een overzicht', 'Hoe staan we ervoor?', 'Give me an overview', 'summary please']) {
      expect(summaryRequested(q), q).toBe(true);
    }
    for (const q of ['IVA', 'FAC-2026-01', '¿Qué es un Object?']) expect(summaryRequested(q), q).toBe(false);
  });

  it('el texto dice que son saldos pendientes y que la diferencia no es efectivo', () => {
    const text = summaryText(MESSAGES.es, { data: data(), asOf: '2026-10-27' });
    expect(text).toContain(formatMoney(100000));
    expect(text).toContain(formatMoney(70000));
    expect(text).toContain('no representa efectivo disponible');
    expect(text).toContain('27-10-2026');
  });
});
