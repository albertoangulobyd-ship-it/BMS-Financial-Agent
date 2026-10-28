// El inicio, el menu y el vuelo del orbe contra Aurora (paso 17, especificacion §6.1 y §6.2). Las
// cajas, la letra, el color y la escala de cada elemento de L0, E0, E1 (recien abierto y con
// Procesar en el centro) y E2 (Cuentas por cobrar), a 1440 × 900 y a 400 × 860, contra las
// medidas del prototipo del dueno (e2e/aurora/referencia.json): x, y y ancho ±4 px (a `y` se le
// resta el alto de las bandas del servidor); el alto ±4 px salvo en el panel (que depende de los
// datos: solo que no pase de su tope); letra y color exactos; escala ±0,01. En E2 la rueda no se
// compara: no esta (§1.1). Y los tiempos: el orbe al abrir el menu (T01, 0,85 s con
// cubic-bezier(.22,.8,.2,1)) y el vuelo a Documentos (T11, 1,05 s con cubic-bezier(.4,0,.15,1)),
// por los cruces del 5, 50 y 95 % de su recorrido (como herramientas/cruces.py).
// Paso 17 B2: tambien E2 con una tarjeta, Documentos (todo, una carpeta abierta y la hoja de una
// factura): en Documentos la `y` se cuenta desde la marca (la pagina se desplaza al abrir); lo
// que va debajo de los datos (la tarjeta) y el dialogo centrado dependen de los datos en su `y`.
// Y el desplazamiento (§6.1): cada panel en reposo, cada vista de grupo e importar sin fichero no
// pasan de 53 px a 1440 × 900 ni de 213 px a 400 × 860; el del dialogo de cada factura de la base
// de prueba se mide y se anota (falla si pasa de 300 px una hoja de cuatro filas o menos).
import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import type { InvoiceRow } from '../src/lib/api';
import { expect, login, settled, test, token } from './fixtures';
import { TEXTS, entryButton, landed, openEntry, openGroup, openInvoice, openMenu, panel, panelRow, setLang, sheetDialog, treeItem } from './nav';

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  font: string;
  ls: string;
  color: string;
  scale: number;
  display?: string;
  maxH?: number;
}
type State = Record<string, Box | { display: 'none' } | number>;
const REF = JSON.parse(readFileSync(new URL('./aurora/referencia.json', import.meta.url), 'utf8')) as Record<string, State>;

const SEL: Record<string, string> = {
  brand: '.bms-brand',
  aurora: '.aurora',
  welcomeH1: '.welcome-line h1',
  welcomeP: '.welcome-line p',
  composer: '.composer',
  discreet: '.discreet',
  navigation: '.navigation',
  navSelected: '.nav-item.selected',
  heroOrb: '.hero-orb',
  panel: '.panel',
  detail: '.detail',
  companion: '.ws-companion',
  wsTitle: '.ws-title-line h1',
  wsGrid: '.ws-grid',
  wsSidebar: '.ws-sidebar',
  wsProfile: '.ws-profile',
  dialog: '.ws-dialog',
};
/** Lo que depende de los datos: solo el tope de su alto. */
const DATA_HEIGHT = new Set(['panel', 'detail', 'wsGrid', 'wsSidebar', 'wsProfile', 'dialog']);
/** Lo que depende de los datos tambien en su `y`: la tarjeta va debajo de las filas del panel y
 *  el dialogo se centra segun su alto. */
const DATA_Y = new Set(['detail', 'dialog']);

/** Las medidas de la app, como capture.cjs mide Aurora (menos las bandas en `y`). */
async function measure(page: Page): Promise<Record<string, Box | { display: 'none' }>> {
  await page.mouse.move(1, 1);
  await settled(page);
  return page.evaluate((sel) => {
    const bands = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bms-bandas')) || 0;
    const out: Record<string, unknown> = {};
    for (const [name, s] of Object.entries(sel)) {
      const el = document.querySelector(s);
      if (!el) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none') {
        out[name] = { display: 'none' };
        continue;
      }
      const r = el.getBoundingClientRect();
      const m = /matrix\(([-\d.e]+),\s*([-\d.e]+)/.exec(cs.transform);
      const scale = m ? Math.hypot(Number(m[1]), Number(m[2])) : 1;
      const hidden = r.width === 0 && r.height === 0;
      out[name] = {
        x: Math.round(r.x),
        y: Math.round(r.y - (hidden ? 0 : bands)),
        w: Math.round(r.width),
        h: Math.round(r.height),
        font: `${cs.fontWeight} ${cs.fontSize}/${cs.lineHeight} ${cs.fontFamily.split(',')[0]!.replace(/"/g, '')}`,
        ls: cs.letterSpacing,
        color: cs.color,
        scale,
        maxH: parseFloat(cs.maxHeight) || undefined,
      };
    }
    return out as Record<string, Box | { display: 'none' }>;
  }, SEL);
}

/** Cada elemento contra Aurora, con las tolerancias de §6.1. Con `anchor`, la `y` de cada uno se
 *  cuenta desde la de ese elemento (en Documentos, la marca: la pagina se desplaza). */
function compare(state: string, ours: Record<string, Box | { display: 'none' }>, skip: string[] = [], anchor?: string): string[] {
  const ref = REF[state];
  expect(ref, state).toBeDefined();
  const out: string[] = [];
  const origin = (m: Record<string, unknown>) => (anchor ? ((m[anchor] as Box | undefined)?.y ?? 0) : 0);
  const [refY, ourY] = [origin(ref!), origin(ours)];
  for (const name of Object.keys(SEL)) {
    if (skip.includes(name)) continue;
    const a = ref![name] as Box | { display: 'none' } | undefined;
    if (!a) continue;
    const b = ours[name];
    if ('display' in a && a.display === 'none') {
      // Que no se vea: con display:none o sin montar (el <dialog> cerrado).
      if (b && !('display' in b) && b.w > 0) out.push(`${name}: en Aurora no se ve`);
      continue;
    }
    const want = a as Box;
    if (!b || 'display' in b) {
      out.push(`${name}: no esta`);
      continue;
    }
    const near = (k: 'x' | 'y' | 'w' | 'h') => Math.abs(k === 'y' ? b.y - ourY - (want.y - refY) : b[k] - want[k]) <= 4;
    for (const k of ['x', 'y', 'w'] as const) {
      if (k === 'y' && (DATA_Y.has(name) || name === anchor)) continue;
      if (!near(k)) out.push(`${name}.${k}: ${b[k]} (Aurora ${want[k]})`);
    }
    if (DATA_HEIGHT.has(name)) {
      if (b.maxH !== undefined && b.h > b.maxH + 1) out.push(`${name}.h: ${b.h} pasa de su tope ${b.maxH}`);
    } else if (!near('h')) out.push(`${name}.h: ${b.h} (Aurora ${want.h})`);
    if (b.font !== want.font) out.push(`${name}.font: ${b.font} (Aurora ${want.font})`);
    if (b.ls !== want.ls) out.push(`${name}.ls: ${b.ls} (Aurora ${want.ls})`);
    if (b.color !== want.color) out.push(`${name}.color: ${b.color} (Aurora ${want.color})`);
    if (Math.abs(b.scale - want.scale) > 0.01) out.push(`${name}.scale: ${b.scale} (Aurora ${want.scale})`);
  }
  return out;
}

for (const size of [
  { width: 1440, height: 900 },
  { width: 400, height: 860 },
] as const) {
  test(`L0, E0, E1 y E2 como Aurora a ${size.width} px`, async ({ page, baseUrl }) => {
    await page.setViewportSize(size);
    await page.goto(`${baseUrl}/app`);
    // En castellano, como se midio Aurora (el ancho de «Presiona para navegar» es de su texto).
    await setLang(page, 'es');
    const w = size.width;
    // L0 contra el inicio: el saludo, el orbe, la caja y la marca (la linea del idioma es nuestra).
    expect(compare(`E0@${w}`, await measure(page), ['discreet', 'navigation', 'navSelected', 'heroOrb', 'panel']), 'L0').toEqual([]);
    await login(page);
    expect(compare(`E0@${w}`, await measure(page)), 'E0').toEqual([]);
    await page.getByRole('button', { name: TEXTS.es.aurora.home.navigate }).click();
    await expect(page.locator('.navigation')).toBeVisible();
    expect(compare(`E1@${w}`, await measure(page)), 'E1').toEqual([]);
    // Procesar en el centro: el morado y el orbe de particulas.
    await entryButton(page, 'process').focus();
    await expect(page.locator('.hero-orb')).toBeVisible();
    expect(compare(`E1-procesar@${w}`, await measure(page)), 'E1 con Procesar').toEqual([]);
    // E2: Cuentas por cobrar. La rueda no esta (§1.1): en lugar de su caja, que no se ve.
    await entryButton(page, 'receivables').focus();
    await settled(page);
    await entryButton(page, 'receivables').click();
    await expect(page.locator('aside.panel')).toBeVisible();
    const e2 = await measure(page);
    expect(e2.navigation, 'E2: la rueda').toEqual({ display: 'none' });
    expect(compare(`E2-cobrar@${w}`, e2, ['navigation', 'navSelected']), 'E2').toEqual([]);
    // E2 con una tarjeta (la de Aurora es la de una fila del panel; la nuestra, la de una fila de
    // la vista de un grupo): la tarjeta en su sitio, con su letra y su color.
    await panel(page).locator('.doc-list button.doc').first().click();
    await settled(page);
    await panel(page).locator('.doc-list button.doc').first().click();
    await expect(panel(page).locator('.detail')).toBeVisible();
    expect(compare(`E2-cobrar-tarjeta@${w}`, await measure(page), ['navigation', 'navSelected']), 'E2 con tarjeta').toEqual([]);

    // Documentos: todo, una carpeta abierta (la categoria de los clientes, tres como en Aurora) y la
    // hoja de un documento suyo.
    await page.locator('button.aurora').click();
    await openEntry(page, 'documents', 'es');
    await landed(page);
    expect(compare(`E6@${w}`, await measure(page), [], 'brand'), 'E6').toEqual([]);
    await treeItem(page, TEXTS.es.documents.clients).first().click();
    await treeItem(page, 'Demo Havenbedrijf BV').first().click();
    await expect(page.locator('.ws-profile')).toBeVisible();
    expect(compare(`E6-carpeta@${w}`, await measure(page), [], 'brand'), 'E6 con una carpeta').toEqual([]);
    await page.locator('.ws-profile .ws-file-table > a').first().click();
    await expect(sheetDialog(page)).toBeVisible();
    // De la hoja, el dialogo (lo de detras ya esta en E6 con una carpeta).
    const sheet = await measure(page);
    expect(compare(`E6-h@${w}`, sheet, ['companion', 'wsTitle', 'wsGrid', 'wsSidebar', 'wsProfile'], 'brand'), 'E6-h').toEqual([]);
  });
}

/** Lo que se desplaza el panel (o el dialogo) dentro de si. */
const overflow = (page: Page, selector: string) => page.locator(selector).evaluate((el) => el.scrollHeight - el.clientHeight);

for (const size of [
  { width: 1440, height: 900, limit: 53 },
  { width: 400, height: 860, limit: 213 },
] as const) {
  test(`los paneles casi no se desplazan a ${size.width} px: en reposo, en cada vista de grupo e importar (§6.1)`, async ({ page, baseUrl }) => {
    test.setTimeout(300_000);
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto(`${baseUrl}/app`);
    await login(page);
    const t = TEXTS.nl;
    const groups: Record<'settings' | 'home' | 'receivables' | 'payables' | 'vat', string[]> = {
      settings: [t.aurora.settings.language, t.aurora.settings.theme, t.aurora.settings.system],
      home: [t.aurora.home.first, t.nav['work-queue'].label, t.nav.exceptions.label, t.aurora.home.iban, t.nav['cash-flow'].label],
      receivables: [t.aurora.money.proposals, t.aurora.money.unmatched, t.money.ageing.title],
      payables: [t.aurora.money.proposals, t.aurora.money.unmatched, t.aurora.money.week, t.money.week.held, t.money.ageing.title],
      vat: [t.aurora.vat.older],
    };
    const seen: string[] = [];
    const over: string[] = [];
    const check = async (what: string) => {
      await settled(page);
      const px = await overflow(page, 'aside.panel');
      seen.push(`${what} ${px}`);
      if (px > size.limit) over.push(`${what}: ${px} px`);
    };
    for (const [entry, labels] of Object.entries(groups) as [keyof typeof groups, string[]][]) {
      await openEntry(page, entry);
      await check(entry);
      for (const label of labels) {
        if (!(await panelRow(page, label).count())) continue;
        // Las vistas de Ajustes se quedan con el titulo del panel; las demas llevan el del grupo.
        if (entry === 'settings') await panelRow(page, label).click();
        else await openGroup(page, label);
        await check(`${entry} > ${label}`);
        await page.keyboard.press('Escape');
      }
    }
    // Importar sin fichero, dentro de Te ontvangen.
    await openEntry(page, 'receivables');
    await panel(page).getByRole('button', { name: t.aurora.money.import }).click();
    await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(t.nav.import.label);
    await check('importeren');
    console.log(`desplazamiento de los paneles a ${size.width} px: ${seen.join(' · ')}`);
    expect(over, `paneles que se desplazan mas de ${size.limit} px`).toEqual([]);
  });
}

test('el dialogo de cada factura: cuanto se desplaza a 1440 × 900 (§6.1)', async ({ page, baseUrl, request }) => {
  test.setTimeout(600_000);
  const response = await request.get(`${baseUrl}/api/v2/facturas`, { headers: { 'X-BMS-Token': token('ana') } });
  const invoices = ((await response.json()) as { facturas: InvoiceRow[] }).facturas.filter((f) => f.numero);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const seen: { number: string; rows: number; px: number }[] = [];
  const nth = new Map<string, number>();
  for (const f of invoices) {
    const number = f.numero!;
    const n = nth.get(number) ?? 0;
    nth.set(number, n + 1);
    const sheet = await openInvoice(page, number, { nth: n });
    seen.push({ number, rows: await sheet.locator('.ws-file-table > a').count(), px: await overflow(page, 'dialog.ws-dialog[open]') });
  }
  seen.sort((a, b) => b.px - a.px);
  // Para el registro: la peor y el reparto.
  console.log(`dialogo de factura a 1440 px: ${seen.map((s) => `${s.number} (${s.rows} filas) ${s.px}`).join(' · ')}`);
  expect(seen.length).toBe(invoices.length);
  // Con cuatro filas o menos (lo de una factura sin mucho que mirar), dentro del limite de Aurora.
  expect(seen.filter((s) => s.rows <= 4 && s.px > 300).map((s) => `${s.number}: ${s.px} px`)).toEqual([]);
});

/** Una curva medida en cada cuadro: [t en ms, valor]. */
type Series = [number, number][];

/** Los instantes en que el cambio pasa por el 5, 50 y 95 % (con el hueco entre las muestras). */
function crossings(s: Series): Record<'p5' | 'p50' | 'p95', { t: number; gap: number }> | null {
  const v0 = s[0]![1];
  const v1 = s[s.length - 1]![1];
  const d = v1 - v0;
  if (Math.abs(d) < 1e-6) return null;
  const at = (level: number) => {
    const target = v0 + d * level;
    for (let i = 1; i < s.length; i += 1) {
      const [ta, va] = s[i - 1]!;
      const [tb, vb] = s[i]!;
      if ((va - target) * (vb - target) <= 0 && va !== vb) return { t: ta + ((target - va) / (vb - va)) * (tb - ta), gap: tb - ta };
    }
    return null;
  };
  const p5 = at(0.05);
  const p50 = at(0.5);
  const p95 = at(0.95);
  return p5 && p50 && p95 ? { p5, p50, p95 } : null;
}

/** Muestrea la x de un elemento en cada cuadro mientras pasa `action`. */
async function sample(page: Page, selector: string, action: () => Promise<void>, ms: number): Promise<Series> {
  await page.evaluate((sel) => {
    const rows: [number, number][] = [];
    (window as unknown as { __bmsCurve: [number, number][] | null }).__bmsCurve = rows;
    const tick = () => {
      const el = document.querySelector(sel);
      if (el) {
        const r = el.getBoundingClientRect();
        rows.push([performance.now(), r.x + r.width / 2]);
      }
      if ((window as unknown as { __bmsCurve: unknown }).__bmsCurve === rows) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, selector);
  await action();
  await page.waitForTimeout(ms);
  return page.evaluate(() => {
    const w = window as unknown as { __bmsCurve: [number, number][] | null };
    const rows = w.__bmsCurve ?? [];
    w.__bmsCurve = null;
    return rows;
  });
}

/** Los dos intervalos contra los de la curva del codigo (§6.2), con hasta tres intentos. */
async function expectTiming(what: string, theory: { to50: number; to95: number }, run: () => Promise<Series>): Promise<void> {
  const notes: string[] = [];
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const s = await run();
    const c = crossings(s);
    if (!c) {
      notes.push(`intento ${attempt}: sin cruces (${s.length} muestras)`);
      continue;
    }
    // Un cuadro atascado (mas de 100 ms) mientras se mueve: la medida no vale y se repite.
    const moving = s.filter(([t]) => t >= c.p5.t - 120 && t <= c.p95.t + 120);
    const stalled = moving.some(([t], i) => i > 0 && t - moving[i - 1]![0] > 100);
    if (stalled) {
      notes.push(`intento ${attempt}: un cuadro atascado`);
      continue;
    }
    const to50 = c.p50.t - c.p5.t;
    const to95 = c.p95.t - c.p5.t;
    const ok50 = Math.abs(to50 - theory.to50) <= Math.max(theory.to50 * 0.1, c.p5.gap, c.p50.gap);
    const ok95 = Math.abs(to95 - theory.to95) <= Math.max(theory.to95 * 0.1, c.p5.gap, c.p95.gap);
    if (ok50 && ok95) {
      // Para el registro: lo medido en esta maquina.
      console.log(`${what}: 5→50 ${to50.toFixed(0)} ms (teorico ${theory.to50}), 5→95 ${to95.toFixed(0)} ms (teorico ${theory.to95}), intento ${attempt}`);
      return;
    }
    notes.push(`intento ${attempt}: 5→50 ${to50.toFixed(0)} ms (teorico ${theory.to50}), 5→95 ${to95.toFixed(0)} ms (teorico ${theory.to95})`);
  }
  expect(notes, `${what}: los tiempos de Aurora`).toEqual([]);
}

test('los tiempos del orbe: abrir el menu (T01) y el vuelo a Documentos y de vuelta (T11, T17)', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // T01: el orbe va a la izquierda en 0,85 s con (.22,.8,.2,1): 0,125 y 0,502 de la duracion.
  await expectTiming('T01', { to50: 106, to95: 427 }, async () => {
    if (await page.locator('.navigation').count()) {
      await page.locator('button.aurora').click();
      await settled(page);
    }
    return sample(page, '.aurora', () => page.getByRole('button', { name: TEXTS.nl.aurora.home.navigate }).click(), 1300);
  });
  // T11: el vuelo a Documentos, 1,05 s con (.4,0,.15,1): 0,200 y 0,580 de la duracion.
  await expectTiming('T11', { to50: 210, to95: 609 }, async () => {
    await openMenu(page);
    await entryButton(page, 'documents').focus();
    await settled(page);
    const s = await sample(page, '.aurora-route-flight', () => entryButton(page, 'documents').click(), 1600);
    await landed(page);
    await page.locator('a.ws-home').click();
    await landed(page);
    return s;
  });
  // T17: el vuelo de vuelta, igual.
  await expectTiming('T17', { to50: 210, to95: 609 }, async () => {
    await openMenu(page);
    await entryButton(page, 'documents').focus();
    await settled(page);
    await entryButton(page, 'documents').click();
    await landed(page);
    await settled(page);
    const s = await sample(page, '.aurora-route-flight', () => page.locator('a.ws-home').click(), 1600);
    await landed(page);
    return s;
  });
});
