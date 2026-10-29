// Procesar (E7, paso 17; especificacion §5) con el lector de las pruebas: la app pide la lectura,
// ensena lo que cuenta el lector, manda el si con su tope y sigue la pasada de verdad. El lector
// es scripts/simular_lector.py sobre la misma base de prueba (sus pasos, cuando la prueba los
// pide: tomar, contar, leer, caducar, fallar), nunca la API ni un PDF. Se comprueba:
// - pedir -> contado -> si -> avance -> resultado: el cuerpo de la suricata no sale sin un si
//   aceptado por el servidor; las cinco etapas, en orden, cada una cuando la pide la lectura; el %
//   no baja nunca y no pasa del techo de la lectura ni de lo que lleva la pila; la linea de la
//   lectura bajo la escena; la centinela; nuevas, ya leidas y posibles duplicados; "Ir a la cola
//   de trabajo" (F8) y "Ver en Documentos" sin vuelo (F5); la nota de la ultima lectura (P0);
// - no leer, caducar y nada que leer: la cabeza sigue (el mismo motor, sin fundido);
// - el aislamiento mal y la lectura que falla leyendo: fundido de 0,3 s, el error, y "Volver a
//   pedir" con un motor nuevo; parar sin nada leido: fundido y la cabeza de un motor nuevo;
// - la estimacion que cambio (409) y el si que no llega al servidor;
// - el tope que se aprobo; reduce motion;
// - con el reloj virtual, a 1440 y 400 px, lo mismo que Aurora (e2e/aurora/suricata.json): las
//   transiciones de la entrada (+-40 ms), la cabeza esperando y la suricata revisando la pila (pixel
//   a pixel) y las acciones de cada etapa;
// - en cada estado, solo Procesar: ni la rueda, ni el orbe, ni otra pantalla.
// Cada prueba termina sin ninguna lectura viva. Capturas: CAPTURAS_DIR/<tema>/procesar-*.png.
import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { APIRequestContext, Locator, Page } from '@playwright/test';
import type { ReadingPassRow, ReadingStatus } from '../src/lib/api-types';
import { capture, expect, login, test, token } from './fixtures';
import {
  TEXTS,
  app,
  auroraRoot,
  centre,
  chooseTheme,
  engineState,
  entryButton,
  fill,
  landed,
  openEntry,
  openMenu,
  panelTitle,
  setLang,
  sheetDialog,
} from './nav';
import { sources } from '../src/aurora/processing/loader-sprites';
import { decodePng, differingPixels, opaqueColumns } from './png';

test.describe.configure({ mode: 'serial' });

const t = TEXTS.es;
const p = t.aurora.process;
const NBSP = ' ';
const STAGE_TITLES = [p.stageTitles.loading, p.stageTitles.reading, p.stageTitles.comparing, p.stageTitles.analyzing, p.stageTitles.organizing];

/** Lo grabado de Aurora (herramientas/reloj.cjs): ver el _nota del fichero. */
interface Suricata {
  mundo: Record<string, [number, number, number, number]>;
  entrada: Record<string, { vt: number; debug: string }[]>;
  etapas: Record<string, Record<string, string[]>>;
  recortes: Record<string, { fichero: string; vt?: number; debug: string }>;
  reducido: Record<string, string[]>;
}
const AURORA = JSON.parse(readFileSync(new URL('./aurora/suricata.json', import.meta.url), 'utf8')) as Suricata;

// ------------------------------------------------------------------ el lector de las pruebas

function readerSetup() {
  const repo = process.env.BMS_E2E_REPO,
    db = process.env.BMS_E2E_DB,
    python = process.env.BMS_E2E_PYTHON;
  if (!repo || !db || !python) throw new Error('faltan BMS_E2E_REPO, BMS_E2E_DB o BMS_E2E_PYTHON (e2e/global-setup.ts)');
  return {
    python,
    args: (more: string[]) => [join(repo, 'scripts', 'simular_lector.py'), '--db', db, ...more],
    env: { ...process.env, PYTHONPATH: join(repo, 'src'), PYTHONUTF8: '1' },
  };
}

/** Un paso del lector, y como queda la lectura. */
function reader(...args: string[]): { solicitud: number; estado: string } {
  const r = readerSetup();
  const run = spawnSync(r.python, r.args(args), { env: r.env, encoding: 'utf8' });
  expect(run.status, `simular_lector ${args.join(' ')}: ${run.stderr}`).toBe(0);
  return JSON.parse(run.stdout.trim().split('\n').pop()!) as { solicitud: number; estado: string };
}

/** El lector leyendo mientras la prueba mira la pantalla: la promesa acaba con el. */
function readerInBackground(...args: string[]): Promise<{ solicitud: number; estado: string }> {
  const r = readerSetup();
  return new Promise((resolve, reject) => {
    const child = spawn(r.python, r.args(args), { env: r.env });
    let out = '',
      err = '';
    child.stdout.on('data', (chunk: Buffer) => (out += chunk.toString()));
    child.stderr.on('data', (chunk: Buffer) => (err += chunk.toString()));
    child.on('error', reject);
    child.on('exit', (code) =>
      code === 0 ? resolve(JSON.parse(out.trim().split('\n').pop()!) as { solicitud: number; estado: string }) : reject(new Error(`simular_lector ${args.join(' ')} (${code}): ${err}`))
    );
  });
}

async function reading(request: APIRequestContext, baseUrl: string): Promise<ReadingStatus> {
  const response = await request.get(`${baseUrl}/api/v2/lectura`, { headers: { 'X-BMS-Token': token('ana') } });
  expect(response.status()).toBe(200);
  return ((await response.json()) as { lectura: ReadingStatus }).lectura;
}

async function stateOf(request: APIRequestContext, baseUrl: string): Promise<string | null> {
  return (await reading(request, baseUrl)).solicitud?.estado ?? null;
}

// Ninguna prueba deja una lectura viva (la siguiente empieza en P0). Si una se queda a medias,
// el lector la cierra para no arrastrar el fallo, pero la prueba falla.
test.afterEach(async ({ request, baseUrl }) => {
  const live = (await reading(request, baseUrl)).solicitud?.viva ?? false;
  if (live) reader('fallar', '--motivo', 'interrumpida');
  expect(live, 'al terminar no queda ninguna lectura viva').toBe(false);
});

// ------------------------------------------------------------------ la pantalla

const workspace = (page: Page) => page.locator('.processing-workspace');
/** El saludo de Procesar: el titulo y la linea de cada estado van al saludo (main.tsx:29). */
const title = (page: Page) => page.locator('.welcome-line h1');
const line = (page: Page) => page.locator('.welcome-line p');
const flow = (page: Page) => workspace(page).locator('.flow-button');
const note = (page: Page) => workspace(page).locator('.processing-demo');
const card = (page: Page) => page.locator('.processing-card');
const textButton = (page: Page, name: string) => workspace(page).getByRole('button', { name, exact: true });

/** Entra (en castellano, como en Aurora), con el tema elegido, y abre Procesar desde la rueda. */
async function enter(page: Page, baseUrl: string, options: { width?: number; theme?: 'light' } = {}): Promise<void> {
  const width = options.width ?? 1440;
  await page.setViewportSize({ width, height: width === 400 ? 860 : 900 });
  await page.goto(`${baseUrl}/app`);
  await setLang(page, 'es');
  await login(page);
  if (options.theme) await chooseTheme(page, options.theme, 'es');
  await openEntry(page, 'process', 'es');
}

/** Solo Procesar: ni la rueda, ni el orbe, ni otra pantalla (la regla del dueno). */
async function expectAlone(page: Page, what: string): Promise<void> {
  const seen = await page.evaluate(() => {
    const shown = (sel: string) =>
      Array.from(document.querySelectorAll<HTMLElement>(sel)).some((el) => el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) && el.getBoundingClientRect().width > 0);
    return {
      menu: shown('.navigation .nav-item'),
      orb: shown('button.aurora'),
      panel: shown('aside.panel'),
      conversation: shown('.conversation'),
      search: shown('.search-workspace'),
      documents: shown('.ws-layout'),
      process: shown('.processing-workspace'),
    };
  });
  expect(seen, `${what}: solo Procesar`).toEqual({ menu: false, orb: false, panel: false, conversation: false, search: false, documents: false, process: true });
}

/** Antes del si: solo la cabeza de la suricata (guard-head), sin cuerpo y sin pila. */
async function expectHeadOnly(page: Page, what: string): Promise<void> {
  await expect.poll(() => engineState(page), { message: `${what}: solo la cabeza` }).toMatch(/^Etapa 1\/5 · cabeza fuera del hoyo · frame \d · pila 0$/);
}

/** Lo que se ve en cada cuadro mientras la suricata trabaja (y el fundido de la escena). */
interface Frame {
  at: number;
  pct: number | null;
  techo: number | null;
  motor: number | null;
  title: string;
  step: string;
  debug: string;
  rows: string;
  loader: boolean;
  fading: boolean;
  complete: boolean;
  error: boolean;
}

const RECORD = `(() => {
  const frames = [];
  window.__bmsProcess = frames;
  let last = '';
  const text = (sel) => { const el = document.querySelector(sel); return el ? el.textContent || '' : ''; };
  const num = (v) => (v === null || v === undefined || v === '' ? null : Number.parseInt(v, 10));
  const tick = () => {
    if (window.__bmsProcess !== frames) return;
    const card = document.querySelector('.processing-card');
    const pct = document.querySelector('.pc-progress b');
    const loader = document.querySelector('.zur-loader');
    const f = {
      pct: pct ? num(pct.textContent) : null,
      techo: num(card && card.getAttribute('data-techo')),
      motor: num(card && card.getAttribute('data-motor')),
      title: text('.welcome-line h1'),
      step: text('.processing-loading .processing-demo'),
      debug: text('.zur-debug output'),
      rows: text('.pc-reading pre'),
      loader: !!loader,
      fading: !!loader && loader.style.opacity === '0',
      complete: !!document.querySelector('.processing-complete'),
      error: !!document.querySelector('.processing-error'),
    };
    const key = JSON.stringify(f);
    if (key !== last) { f.at = performance.now(); frames.push(f); last = key; }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})()`;

async function record(page: Page): Promise<void> {
  await page.evaluate(RECORD);
}

async function recorded(page: Page): Promise<Frame[]> {
  return (await page.evaluate(`(() => { const f = window.__bmsProcess; window.__bmsProcess = null; return f; })()`)) as Frame[];
}

/** La etapa mas alta que puede tener la suricata con este techo (reading-model.ts, ceilingOf):
 *  comparando 60, analizando 80, organizando 99, hecha 100; antes, cargando o leyendo. */
function stageAllowed(ceiling: number): number {
  return ceiling >= 99 ? 4 : ceiling >= 80 ? 3 : ceiling >= 60 ? 2 : 1;
}

/** Las reglas de la suricata mientras trabaja, cuadro a cuadro. */
function checkRun(frames: Frame[], what: string): void {
  let shown = 0,
    stage = -1,
    step = 0;
  const titles: number[] = [];
  frames.forEach((f, i) => {
    if (f.pct !== null) {
      expect(f.pct, `${what}: el % no baja (cuadro ${i})`).toBeGreaterThanOrEqual(shown);
      shown = f.pct;
      if (f.techo !== null) expect(f.pct, `${what}: el % no pasa del techo de la lectura (cuadro ${i})`).toBeLessThanOrEqual(f.techo);
      if (f.motor !== null && f.techo !== null) expect(f.pct, `${what}: el % es el menor del motor y del techo (cuadro ${i})`).toBe(Math.min(f.motor, f.techo));
    }
    const pile = /· pila (\d)$/.exec(f.debug);
    if (pile && f.motor !== null) expect(f.motor, `${what}: el motor no pasa de lo que lleva la pila (cuadro ${i})`).toBeLessThanOrEqual(20 * Number(pile[1]) + 17);
    const at = /^Etapa (\d)\/5 · (?!cabeza)/.exec(f.debug);
    if (at) {
      const s = Number(at[1]) - 1;
      expect(s, `${what}: las etapas no vuelven atras (cuadro ${i})`).toBeGreaterThanOrEqual(stage);
      stage = s;
      // La etapa la pide la lectura: el techo de ese momento (o el de los cuadros que siguen, por
      // si React pinta el techo un cuadro despues que el motor) la deja.
      const ceiling = Math.max(0, ...frames.slice(i, i + 6).map((g) => g.techo ?? 0));
      expect(s, `${what}: la etapa ${s + 1} con el techo ${ceiling} (cuadro ${i})`).toBeLessThanOrEqual(stageAllowed(ceiling));
    }
    const ti = STAGE_TITLES.indexOf(f.title);
    if (ti >= 0 && titles[titles.length - 1] !== ti) titles.push(ti);
    const n = /^Paso (\d) de 5/.exec(f.step);
    if (n) {
      const k = Number(n[1]);
      expect(k, `${what}: el paso no vuelve atras (cuadro ${i})`).toBeGreaterThanOrEqual(step);
      step = k;
      // El saludo cambia con un fundido (0,3 s): va igual o un paso por detras.
      if (ti >= 0) expect(k - 1 - ti, `${what}: «${f.title}» con «${f.step}» (cuadro ${i})`).toBeGreaterThanOrEqual(0);
      if (ti >= 0) expect(k - 1 - ti, `${what}: «${f.title}» con «${f.step}» (cuadro ${i})`).toBeLessThanOrEqual(1);
    }
  });
  expect(titles, `${what}: las cinco etapas, en orden`).toEqual([0, 1, 2, 3, 4]);
  expect(frames.some((f) => / · centinela · /.test(f.debug)), `${what}: la centinela del final`).toBe(true);
}

/** El fundido de la escena (hide: opacidad 0 y fuera a los 0,3 s) antes de lo que viene. */
function checkFade(frames: Frame[], what: string, next: (f: Frame) => boolean): void {
  const fade = frames.findIndex((f) => f.fading);
  expect(fade, `${what}: la escena se funde`).toBeGreaterThanOrEqual(0);
  const after = frames.findIndex((f, i) => i > fade && next(f));
  expect(after, `${what}: lo que viene, despues del fundido`).toBeGreaterThan(fade);
  expect(frames[after]!.at - frames[fade]!.at, `${what}: el fundido dura 0,3 s`).toBeGreaterThanOrEqual(250);
}

function counts(rows: ReadingPassRow[]) {
  return {
    fresh: rows.filter((r) => r.estado === 'nueva').length,
    repeated: rows.filter((r) => r.estado === 'ya_leida' || r.estado === 'posible_duplicado').length,
    failed: rows.filter((r) => r.estado === 'fallida').length,
  };
}

async function box(locator: Locator) {
  const b = await locator.boundingBox();
  expect(b).not.toBeNull();
  return b!;
}

function expectSameBox(a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }, what: string) {
  for (const k of ['x', 'y', 'width', 'height'] as const) expect(Math.abs(a[k] - b[k]), `${what}: ${k}`).toBeLessThanOrEqual(1);
}

/** Pide la lectura (P0 -> P1) y espera a que la pantalla lo diga. */
async function requestReading(page: Page): Promise<void> {
  await expect(flow(page)).toHaveText(p.request);
  await flow(page).click();
  await expect(title(page)).toHaveText(fill(p.requested.title, { readShortcut: 'BMS Finanzas - Leer facturas' }));
}

/** P3 con lo contado: n facturas nuevas y el boton Empezar. */
async function counted(page: Page, ...args: string[]): Promise<void> {
  reader('tomar');
  reader('contar', ...args);
  await expect(flow(page)).toHaveText(p.start);
  await expect(flow(page)).toBeVisible();
}

// ------------------------------------------------------------------ los recorridos

test('pedir, contar, empezar, leer y el resultado: la suricata sigue la lectura de verdad (1440)', async ({ page, baseUrl, request }) => {
  test.setTimeout(240_000);
  await enter(page, baseUrl);

  // P0: el saludo de Aurora, «Pedir lectura» y lo que cuesta.
  await expect(title(page)).toHaveText(p.ready.title);
  await expect(line(page)).toHaveText(p.ready.line);
  await expect(flow(page)).toHaveText(p.request);
  await expect(note(page)).toContainText(/^Gastado hasta hoy: \$\s\d+,\d{2} · Cada factura, entre \$\s0,\d{3} y \$\s0,\d{3}/);
  await expect(card(page).locator('.pc-reading')).toHaveText(p.card.idle + p.card.idleNote);
  await expectHeadOnly(page, 'P0');
  await expectAlone(page, 'P0');
  await capture(page, 'procesar-p0-1440');
  const button0 = await box(flow(page));
  const note0 = await box(note(page));

  // P1: la app no lanza nada; dice que se abra el acceso directo. El boton guarda su sitio, oculto.
  await requestReading(page);
  await expect(title(page).locator('[data-proper-name]')).toHaveText('BMS Finanzas - Leer facturas');
  await expect(line(page)).toHaveText(p.requested.line);
  await expect(flow(page)).toHaveCSS('visibility', 'hidden');
  await expect(note(page)).toHaveText(new RegExp(`^Pedida por Ana Demo a las \\d{2}:\\d{2} · ${p.notRead}$`));
  await expect(card(page).locator('.pc-label')).toContainText(p.card.waiting);
  expectSameBox(await box(flow(page)), button0, 'P1: el boton');
  expect(Math.abs((await box(note(page))).y - note0.y), 'P1: la nota').toBeLessThanOrEqual(1);
  await expectHeadOnly(page, 'P1');
  await expectAlone(page, 'P1');
  await capture(page, 'procesar-p1-1440');

  // P2: el lector la toma y comprueba la conexion.
  reader('tomar');
  await expect(title(page)).toHaveText(p.checking.title);
  await expect(line(page)).toHaveText(p.checking.line);
  expectSameBox(await box(flow(page)), button0, 'P2: el boton');
  await expectHeadOnly(page, 'P2');
  await capture(page, 'procesar-p2-1440');

  // P3: lo contado, el precio del lote y el plazo.
  reader('contar', '--nuevas', '4', '--ya-leidas', '1');
  await expect(title(page)).toHaveText(`4 facturas nuevas, entre $${NBSP}0,23 y $${NBSP}0,25.`);
  await expect(line(page)).toHaveText(/^1 ya leída no se vuelve a pagar\. Tienes hasta las \d{2}:\d{2} para decidir\.$/);
  await expect(flow(page)).toHaveText(p.start);
  await expect(flow(page)).toBeVisible();
  await expect(card(page).locator('.pc-label')).toContainText(p.card.ready);
  await expect(card(page).locator('.pc-reading')).toHaveText(p.card.start + p.card.startNote);
  expectSameBox(await box(flow(page)), button0, 'P3: el boton');
  expect(Math.abs((await box(note(page))).y - note0.y), 'P3: la nota').toBeLessThanOrEqual(1);
  await expectHeadOnly(page, 'P3');
  await expectAlone(page, 'P3');
  await capture(page, 'procesar-p3-1440');

  // Empezar: el si se queda en el camino un rato. Sin el 200 del servidor, el cuerpo no sale.
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  let held = false;
  await page.route('**/api/v2/acciones', async (route) => {
    if ((route.request().postData() ?? '').includes('"aprobar_lectura"')) {
      held = true;
      await gate;
    }
    await route.fallback();
  });
  await flow(page).click();
  await expect.poll(() => held).toBe(true);
  for (let i = 0; i < 6; i += 1) {
    expect(await engineState(page), 'sin el si del servidor: solo la cabeza').toMatch(/^Etapa 1\/5 · cabeza fuera del hoyo/);
    await page.waitForTimeout(250);
  }
  expect(await stateOf(request, baseUrl)).toBe('esperando_aprobacion');
  await record(page);
  release();
  await expect.poll(() => engineState(page)).toMatch(/· (emerge-search|buscando otro documento) ·/);
  await expect(workspace(page).locator('.processing-loading')).toBeVisible();
  await expect(card(page).locator('.pc-label')).toContainText(p.card.running);
  expect(await stateOf(request, baseUrl)).toBe('aprobada');

  // La lectura de verdad, documento a documento: la suricata va detras.
  const done = readerInBackground('leer', '--pausa', '0.8', '--duplicados', '1');
  await expect(title(page)).toHaveText(STAGE_TITLES[1]!, { timeout: 60_000 });
  await expectAlone(page, 'P4');
  await capture(page, 'procesar-p4-1440');
  await done;
  await expect(workspace(page).locator('.processing-complete')).toBeVisible({ timeout: 120_000 });
  const frames = await recorded(page);
  checkRun(frames, 'P4');

  // P5: lo que encontro, de la pasada de verdad.
  const status = await reading(request, baseUrl);
  const rows = (status.ultima_pasada ?? status.pasada_en_curso)!.resultado;
  const c = counts(rows);
  expect(c).toEqual({ fresh: 3, repeated: 2, failed: 0 });
  // Bajo la escena, la linea de la lectura nombro los PDF de verdad.
  expect(frames.some((f) => rows.some((r) => f.rows.includes(r.nombre))), 'la linea de la lectura, con los PDF').toBe(true);
  await expect(title(page)).toHaveText(p.complete.title);
  await expect(line(page)).toHaveText(fill(p.complete.line, { n: rows.length }));
  await expect(workspace(page).locator('.analysis-new strong')).toHaveText(String(c.fresh));
  await expect(workspace(page).locator('.analysis-duplicate strong')).toHaveText(String(c.repeated));
  await expect(workspace(page).locator('.analysis-entry')).toHaveCount(rows.length);
  await expect(workspace(page).locator('.analysis-entry.new')).toHaveCount(c.fresh);
  await expect(workspace(page).locator('.analysis-entry.duplicate')).toHaveCount(c.repeated);
  await expect(workspace(page).locator('.analysis-entry.duplicate .analysis-entry-status')).toHaveText([p.entry.posible_duplicado, p.entry.ya_leida]);
  await expect(workspace(page).locator('.zur-loader')).toHaveCount(0);
  await expect(note(page)).toHaveText(`${p.complete.note} · ${p.queue}`);
  await expectAlone(page, 'P5');
  await capture(page, 'procesar-p5-1440');

  // F8: «Ir a la cola de trabajo», el panel de Inicio en su vista.
  await textButton(page, p.queue).click();
  await expect(app(page)).toHaveClass(/\bhas-panel\b/);
  await expect(panelTitle(page)).toHaveText(t.nav['work-queue'].label);
  await expect(workspace(page)).toHaveCount(0);
  await expect(page.locator('.navigation .nav-item').first()).not.toBeVisible();
});

test('una lectura rapida a 400 px: las cinco etapas en orden, «Ver en Documentos» sin vuelo y la ultima lectura en P0', async ({ page, baseUrl, request }) => {
  test.setTimeout(180_000);
  await enter(page, baseUrl, { width: 400 });
  await expectAlone(page, 'P0 a 400');
  await capture(page, 'procesar-p0-400');
  await requestReading(page);
  await counted(page, '--nuevas', '2', '--ya-leidas', '0');
  await expect(title(page)).toHaveText(`2 facturas nuevas, entre $${NBSP}0,11 y $${NBSP}0,12.`);
  await expect(line(page)).toHaveText(/^Tienes hasta las \d{2}:\d{2} para decidir\.$/);
  await capture(page, 'procesar-p3-400');
  await record(page);
  await flow(page).click();
  await expect.poll(() => stateOf(request, baseUrl)).toBe('aprobada');
  // El lector lee de golpe: la app pide cada etapa en orden, aunque lleguen juntas.
  reader('leer', '--pausa', '0');
  await expect(title(page)).toHaveText(STAGE_TITLES[2]!, { timeout: 60_000 });
  await expectAlone(page, 'P4 a 400');
  await capture(page, 'procesar-p4-400');
  await expect(workspace(page).locator('.processing-complete')).toBeVisible({ timeout: 120_000 });
  checkRun(await recorded(page), 'P4 a 400');
  await expect(workspace(page).locator('.analysis-entry.new')).toHaveCount(2);
  await expectAlone(page, 'P5 a 400');
  await capture(page, 'procesar-p5-400');

  // F5: «Ver en Documentos», sin el vuelo del orbe (Procesar no tiene orbe).
  await page.evaluate(`(() => {
    window.__bmsFlight = false;
    const tick = () => { if (document.querySelector('.aurora-route-flight')) window.__bmsFlight = true; if (window.__bmsFlight !== null) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  })()`);
  await flow(page).click();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await landed(page);
  expect(await page.evaluate(`(() => { const f = window.__bmsFlight; window.__bmsFlight = null; return f; })()`), 'sin vuelo').toBe(false);
  await expect(page.locator('.ws-layout')).toBeVisible();

  // Otra visita: P0, con la ultima lectura en la nota (el resultado era de aquella visita).
  await openEntry(page, 'process', 'es');
  await expect(title(page)).toHaveText(p.ready.title);
  await expect(note(page)).toContainText(/La última lectura: hoy a las \d{2}:\d{2} · 2 nuevas, 0 repetidas\./);
});

test('no leer, caducar y nada que leer: la cabeza sigue, sin fundido ni otro motor (1440, claro)', async ({ page, baseUrl }) => {
  test.setTimeout(180_000);
  await enter(page, baseUrl, { theme: 'light' });
  const loader = await page.locator('.zur-loader').elementHandle();
  const same = async (what: string) => expect(await loader!.evaluate((el) => el.isConnected && (el as HTMLElement).style.opacity !== '0'), `${what}: el mismo motor`).toBe(true);

  // P1 -> «No leer»: cancelada, sin gastar nada.
  await requestReading(page);
  await textButton(page, p.notRead).click();
  await expect(title(page)).toHaveText(p.cancelled.title);
  await expect(line(page)).toHaveText(p.cancelled.line);
  await expect(flow(page)).toHaveText(p.request);
  await expect(flow(page)).toBeVisible();
  await same('P8 desde P1');
  await expectHeadOnly(page, 'P8');
  await expectAlone(page, 'P8');
  await capture(page, 'procesar-p8-1440');

  // P3 -> nadie dice que si en el plazo.
  await requestReading(page);
  await counted(page, '--nuevas', '2', '--ya-leidas', '0');
  reader('caducar');
  await expect(title(page)).toHaveText(p.expired.title);
  await expect(line(page)).toHaveText(p.expired.line);
  await same('P7');
  await expectHeadOnly(page, 'P7');
  await capture(page, 'procesar-p7-1440');

  // P3 -> «No leer» en la app, y otra vez el no en la ventana del lector.
  await requestReading(page);
  await counted(page, '--nuevas', '2', '--ya-leidas', '0');
  await textButton(page, p.notRead).click();
  await expect(title(page)).toHaveText(p.cancelled.title);
  await requestReading(page);
  await counted(page, '--nuevas', '2', '--ya-leidas', '0');
  reader('no');
  await expect(title(page)).toHaveText(p.cancelled.title);
  await same('P8 desde P3');

  // Nada que leer: las que hay ya estan leidas.
  await requestReading(page);
  reader('tomar');
  reader('contar', '--nuevas', '0', '--ya-leidas', '3');
  await expect(title(page)).toHaveText(p.nothing.title);
  await expect(line(page)).toHaveText(fill(p.nothing.line, { n: 3 }));
  await same('P8 nada que leer');
  await expectHeadOnly(page, 'P8 nada que leer');
  await capture(page, 'procesar-p8-nada-1440');
});

test('el aislamiento mal: fundido, el error y «Volver a pedir» con un motor nuevo (400, claro)', async ({ page, baseUrl }) => {
  test.setTimeout(120_000);
  await enter(page, baseUrl, { width: 400, theme: 'light' });
  await requestReading(page);
  reader('tomar');
  await expect(title(page)).toHaveText(p.checking.title);
  const loader = await page.locator('.zur-loader').elementHandle();
  await record(page);
  reader('fallar', '--motivo', 'aislamiento');
  await expect(workspace(page).locator('.processing-error')).toBeVisible();
  await expect(title(page)).toHaveText(p.error.title);
  await expect(workspace(page).locator('.processing-error [role=alert]')).toHaveText(p.reasons.aislamiento);
  checkFade(await recorded(page), 'P6', (f) => f.error);
  expect(await loader!.evaluate((el) => el.isConnected)).toBe(false);
  await expectAlone(page, 'P6');
  await capture(page, 'procesar-p6-400');

  // «Volver a pedir»: otra peticion y un motor nuevo, que entra con su nube de reserva.
  await record(page);
  await textButton(page, p.again).click();
  await expect(title(page)).toHaveText(fill(p.requested.title, { readShortcut: 'BMS Finanzas - Leer facturas' }));
  await expectHeadOnly(page, 'P1 de nuevo');
  const frames = await recorded(page);
  expect(frames.some((f) => /partículas cayendo/.test(f.debug)), 'el motor nuevo entra desde las particulas').toBe(true);
  await textButton(page, p.notRead).click();
  await expect(title(page)).toHaveText(p.cancelled.title);
});

test('el 409 de una estimacion que cambio, el si que no llega, y parar sin nada leido (1440)', async ({ page, baseUrl, request, watch }) => {
  test.setTimeout(150_000);
  watch.expectHttpErrors(409, 503);
  await enter(page, baseUrl);
  await requestReading(page);
  await counted(page, '--nuevas', '3', '--ya-leidas', '0');
  await expect(title(page)).toHaveText(`3 facturas nuevas, entre $${NBSP}0,17 y $${NBSP}0,19.`);

  // El servidor no contesta: el si no ha llegado y se puede probar otra vez.
  await page.route('**/api/v2/acciones', (route) =>
    (route.request().postData() ?? '').includes('"aprobar_lectura"') ? route.fulfill({ status: 503, json: { error: 'sin servicio (prueba)' } }) : route.fallback()
  );
  await flow(page).click();
  await expect(line(page)).toHaveText(p.waiting.sendFailed);
  await expect(line(page)).toHaveAttribute('role', 'alert');
  await expectHeadOnly(page, 'sin respuesta');
  await page.unroute('**/api/v2/acciones');
  expect(await stateOf(request, baseUrl)).toBe('esperando_aprobacion');

  // El lector vuelve a contar mientras la pantalla ensena lo de antes: el si con la huella vieja
  // es un 409 «conflicto», y la pantalla ensena lo nuevo.
  let frozen: string | null = JSON.stringify({ lectura: await reading(request, baseUrl) });
  await page.route('**/api/v2/lectura', (route) => (frozen ? route.fulfill({ status: 200, contentType: 'application/json', body: frozen }) : route.fallback()));
  reader('recontar', '--nuevas', '5', '--ya-leidas', '0');
  const refused = page.waitForResponse((r) => r.url().endsWith('/api/v2/acciones') && (r.request().postData() ?? '').includes('"aprobar_lectura"'));
  await flow(page).click();
  expect((await refused).status()).toBe(409);
  frozen = null;
  await expect(title(page)).toHaveText(`Ha cambiado: 5 facturas nuevas, entre $${NBSP}0,29 y $${NBSP}0,31.`);
  await expect(line(page)).toHaveText(/^Míralo otra vez antes de empezar\. Tienes hasta las \d{2}:\d{2}\.$/);
  await expectHeadOnly(page, 'P3 cambiada');
  await capture(page, 'procesar-p3-cambio-1440');
  await page.unroute('**/api/v2/lectura');

  // El si de lo nuevo: sale el cuerpo. «Parar la lectura» antes de leer nada: fundido y la cabeza
  // de un motor nuevo.
  await flow(page).click();
  await expect.poll(() => engineState(page)).toMatch(/· (emerge-search|buscando otro documento) ·/);
  const loader = await page.locator('.zur-loader').elementHandle();
  await record(page);
  await textButton(page, p.stop).click();
  await expect(title(page)).toHaveText(p.cancelled.title);
  await expect(flow(page)).toHaveText(p.request);
  checkFade(await recorded(page), 'parar', (f) => f.loader && !f.fading);
  expect(await loader!.evaluate((el) => el.isConnected)).toBe(false);
  await expectHeadOnly(page, 'P8 tras parar');
  expect(await stateOf(request, baseUrl)).toBe('cancelada');
});

test('la lectura que falla leyendo: fundido, lo ya leido en el error y, en otra visita, la nota (1440)', async ({ page, baseUrl, request }) => {
  test.setTimeout(150_000);
  await enter(page, baseUrl);
  await requestReading(page);
  await counted(page, '--nuevas', '4', '--ya-leidas', '0');
  await flow(page).click();
  await expect.poll(() => stateOf(request, baseUrl)).toBe('aprobada');
  await record(page);
  await readerInBackground('fallar', '--motivo', 'lectura', '--leyendo', '--pausa', '0.6');
  await expect(workspace(page).locator('.processing-error')).toBeVisible({ timeout: 30_000 });
  await expect(title(page)).toHaveText(p.error.titleSome);
  await expect(workspace(page).locator('.processing-error [role=alert]')).toHaveText(`${p.reasons.lectura} ${fill(p.error.some, { n: 2 })}`);
  checkFade(await recorded(page), 'P6 leyendo', (f) => f.error);
  await expect(textButton(page, p.again)).toBeVisible();
  await expectAlone(page, 'P6 leyendo');
  await capture(page, 'procesar-p6-parcial-1440');

  // Alt+<-: al inicio. El error era de esa visita; en la siguiente, P0 con la nota.
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(app(page)).not.toHaveClass(/\bprocess-mode\b/);
  await openEntry(page, 'process', 'es');
  await expect(title(page)).toHaveText(p.ready.title);
  await expect(note(page)).toContainText(/La última lectura no terminó \(hoy a las \d{2}:\d{2}\): La lectura ha fallado\./);
});

test('el tope aprobado: el lector para en el, la nota lo dice y cada factura lleva a su hoja (1440)', async ({ page, baseUrl, request }) => {
  test.setTimeout(150_000);
  await enter(page, baseUrl);
  await requestReading(page);
  // Cada factura cuesta mas de lo contado: en la segunda ya no cabe.
  await counted(page, '--nuevas', '3', '--ya-leidas', '0', '--alto', '10000', '--bajo', '8000');
  await expect(title(page)).toHaveText(`3 facturas nuevas, entre $${NBSP}0,02 y $${NBSP}0,03.`);
  await flow(page).click();
  await expect.poll(() => stateOf(request, baseUrl)).toBe('aprobada');
  reader('leer', '--pausa', '0.2');
  await expect(workspace(page).locator('.processing-complete')).toBeVisible({ timeout: 120_000 });
  const status = await reading(request, baseUrl);
  expect(status.ultima_pasada?.fase).toBe('tope');
  await expect(line(page)).toHaveText(p.complete.lineOne);
  await expect(note(page)).toContainText(fill(p.complete.cap, { cap: `$${NBSP}0,03`, done: 1, total: 3 }));
  await capture(page, 'procesar-p5-tope-1440');

  // Una factura del resultado: su hoja, en Documentos.
  const entry = workspace(page).locator('.analysis-entry').first();
  const number = (await entry.locator('strong').textContent()) ?? '';
  await entry.click();
  await expect(sheetDialog(page)).toBeVisible();
  await expect(sheetDialog(page)).toContainText(number);
});

test('reduce motion: sin particulas ni paseos, las etapas como en Aurora y el resultado (1440)', async ({ page, baseUrl, request }) => {
  test.setTimeout(150_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await enter(page, baseUrl);
  await record(page);
  await requestReading(page);
  await counted(page, '--nuevas', '2', '--ya-leidas', '0');
  await flow(page).click();
  await expect.poll(() => stateOf(request, baseUrl)).toBe('aprobada');
  reader('leer', '--pausa', '0.3');
  await expect(workspace(page).locator('.processing-complete')).toBeVisible({ timeout: 120_000 });
  const frames = await recorded(page);
  const seen = frames.map((f) => f.debug).filter((d, i, all) => d && d !== all[i - 1]);
  expect(seen.filter((d) => /partículas|montículo|Entrada|emerge|buscando|moving|regresando|soltando/.test(d)), 'sin movimiento').toEqual([]);
  expect(seen, 'lo mismo que Aurora con reduce motion').toEqual(AURORA.reducido['1440']);
  await capture(page, 'procesar-p5-reduce-1440');
});

// ------------------------------------------------------------------ con el reloj de Aurora

/** El lienzo de la escena (zur-world), en pixeles de la pantalla. */
async function worldBox(page: Page) {
  const b = await box(page.locator('.zur-world'));
  return { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height) };
}

/** Un recorte de la escena, junto a las capturas (CAPTURAS_DIR/dark), para mirarlo al lado del de
 *  Aurora (e2e/aurora/suricata/). */
function keepFrame(name: string, png: Buffer): void {
  const dir = join(process.env.CAPTURAS_DIR || join('test-results', 'capturas'), 'dark');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, `${name}.png`), png);
}

/** Un clic de verdad en el centro, sin las esperas de Playwright (que cuentan cuadros: con el
 *  reloj parado no pasan). */
async function clickAt(page: Page, locator: Locator): Promise<void> {
  const b = await box(locator);
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
}

for (const width of [1440, 400] as const) {
  test(`con el reloj virtual, a ${width} px, la suricata hace lo de Aurora: la entrada, la cabeza y cada etapa`, async ({ page, baseUrl, request }) => {
    test.setTimeout(600_000);
    const w = String(width);
    await page.setViewportSize({ width, height: width === 400 ? 860 : 900 });
    await page.clock.install();
    await page.goto(`${baseUrl}/app`);
    await setLang(page, 'es');
    await login(page);
    await openMenu(page, 'es');
    await centre(page, 'process');
    const entry = await box(entryButton(page, 'process'));
    // Desde aqui el tiempo solo pasa cuando la prueba lo dice (como en herramientas/reloj.cjs).
    const now = (await page.evaluate(() => Date.now())) as number;
    await page.clock.pauseAt(now + 50);
    await page.clock.runFor(50);
    let vt = 0;
    const run = async (ms: number) => {
      await page.clock.runFor(ms);
      vt += ms;
    };
    const until = async (what: string, ok: () => Promise<boolean>) => {
      for (let i = 0; i < 300; i += 1) {
        if (await ok()) return;
        await run(100);
      }
      throw new Error(`no llega: ${what}`);
    };

    // La entrada: cada 40 ms, las transiciones de la linea del motor.
    await page.mouse.click(entry.x + entry.width / 2, entry.y + entry.height / 2);
    await page.waitForTimeout(400); // los PNG se decodifican de verdad
    const samples = [{ vt, debug: await engineState(page) }];
    while (vt < 3200) {
      await run(40);
      samples.push({ vt, debug: await engineState(page) });
    }
    const transitions = samples.filter((s, i) => i === 0 || s.debug !== samples[i - 1]!.debug);
    const reference = AURORA.entrada[w]!;
    expect(transitions.map((s) => s.debug), 'las transiciones de la entrada').toEqual(reference.map((s) => s.debug));
    transitions.forEach((s, i) => expect(Math.abs(s.vt - reference[i]!.vt), `«${s.debug}» a los ${s.vt} ms (Aurora: ${reference[i]!.vt})`).toBeLessThanOrEqual(40));

    // La cabeza esperando, a los 3,4 s: pixel a pixel.
    while (vt < 3400) await run(200);
    const world = await worldBox(page);
    const raw = await box(page.locator('.zur-world'));
    const main = (await box(page.locator('main'))).y;
    const [ax, ay, aw, ah] = AURORA.mundo[w]!;
    expect([world.x, Math.round(raw.y - main), world.width, world.height], `el lienzo de la escena, donde el de Aurora (y ${raw.y}, main ${main})`).toEqual([ax, ay, aw, ah]);
    const head = AURORA.recortes[`cabeza@${w}`]!;
    expect(await engineState(page)).toBe(head.debug);
    const headPng = await page.screenshot({ clip: world, animations: 'allow', caret: 'initial' });
    keepFrame(`procesar-cabeza-${w}`, headPng);
    const headShot = decodePng(headPng);
    const headRef = decodePng(readFileSync(new URL(`./aurora/${head.fichero}`, import.meta.url)));
    expect(differingPixels(headShot, headRef), 'la cabeza, como en Aurora').toBe(0);

    // Pedir, contar y Empezar, con el reloj parado entre paso y paso.
    await clickAt(page, flow(page));
    await until('P1', async () => (await title(page).textContent())?.startsWith('Abre') ?? false);
    reader('tomar');
    reader('contar', '--nuevas', '5', '--ya-leidas', '0');
    await until('Empezar', async () => (await flow(page).textContent()) === p.start && (await flow(page).evaluate((el) => getComputedStyle(el).visibility)) === 'visible');
    await clickAt(page, flow(page));
    await expect.poll(() => stateOf(request, baseUrl)).toBe('aprobada');
    reader('leer', '--pausa', '0', '--duplicados', '1');

    // El trabajo: cada 80 ms, las acciones de cada etapa, y la suricata revisando la pila de 1.
    const pile = AURORA.recortes[`pila1@${w}`]!;
    let pileShot: Buffer | null = null;
    const work: string[] = [];
    // Hasta que la escena se funde y se va (la centinela, 1,2 s, y el fundido, 0,3 s): entonces la
    // linea del motor ya no esta.
    let gone = false;
    for (let i = 0; i < 2000 && !gone; i += 1) {
      await run(80);
      const debug = await engineState(page);
      work.push(debug);
      if (!pileShot && debug === pile.debug) {
        // El rebote de la hoja: sube la escala y, en el cuadro siguiente, baja con una transicion
        // CSS de 120 ms de tiempo de verdad, que el reloj parado deja a medias. Aqui, la hoja
        // posada (lo que deja el motor al acabar el rebote), como en el cuadro de Aurora.
        await page.locator('.zur-pile').evaluate((el: HTMLElement) => {
          el.style.transition = 'none';
          el.style.transform = 'translateY(0)';
        });
        pileShot = await page.screenshot({ clip: world, animations: 'allow', caret: 'initial' });
      }
      gone = !debug && (await page.locator('.zur-loader').count()) === 0;
    }
    expect(gone, 'la escena se va al final').toBe(true);
    const stages: Record<string, string[]> = {};
    for (const d of work) {
      const m = /^Etapa (\d)\/5 · ([^·]+) · /.exec(d);
      if (!m) continue;
      const seq = (stages[m[1]!] ??= []);
      const action = m[2]!.trim();
      if (seq[seq.length - 1] !== action) seq.push(action);
    }
    // «vigilando» dura lo que tarda la siguiente etapa en llegar: en Aurora, 0,7 s (auto); aqui,
    // la lectura ya la pidio y dura un cuadro. Y en la etapa 1 la primera busqueda sale de donde
    // estaba el orbe, que cae dentro de la franja donde el motor elige al azar el hoyo
    // (randomLeft, Math.random): si cae a menos de 7 px, el paseo dura menos que un paso de 80 ms
    // y no se ve en la muestra (en la grabacion de Aurora duro varios). El resto, igual.
    const busy = (seq: string[] = [], stage: string) =>
      seq.filter((a, i) => a !== 'vigilando' && !(stage === '1' && i === 1 && seq[0] === 'emerge-search' && a === 'buscando otro documento'));
    for (const s of ['1', '2', '3', '4', '5']) expect(busy(stages[s], s), `las acciones de la etapa ${s}`).toEqual(busy(AURORA.etapas[w]![s], s));
    expect(stages['5']?.at(-1), 'al final, la centinela').toBe('centinela');

    // La suricata entera revisando la pila de 1 papel. La hoja de la pila cae con un desvio al
    // azar de -1, 0 o 1 veces la escala (deposited: Math.random): se compara la suricata (a la
    // izquierda de la pila) pixel a pixel; y la pila tambien: fuera de la franja por donde puede
    // caer la hoja, tal cual, y dentro, con la hoja movida lo que pueden separarse los dos
    // desvios al azar (el de Aurora y el de aqui).
    expect(pileShot, `«${pile.debug}»`).not.toBeNull();
    keepFrame(`procesar-pila1-${w}`, pileShot!);
    const pileRef = decodePng(readFileSync(new URL(`./aurora/${pile.fichero}`, import.meta.url)));
    const shot = decodePng(pileShot!);
    // Los sitios de loader-engine.ts con el ancho del lienzo: la pila (pileX), la suricata junto a
    // ella (centerAtPile) y el hoyo, que queda donde la suricata saco la hoja (randomLeft, al azar):
    // la suricata se compara entre el hoyo mas a la derecha posible y la pila.
    const scale = width === 400 ? 2 : 3;
    const pileX = Math.min(550, aw - 70);
    const nearPile = Math.min(aw - 39 * scale - 10, pileX - 60);
    const leftMost = 33 * scale + 10;
    const holeRight = Math.round(leftMost + Math.max(1, Math.min(aw * 0.34, nearPile - 80) - leftMost)) + 41 * scale;
    const pileLeft = pileX - 35 - scale;
    expect(differingPixels(shot, pileRef, { from: holeRight + 1, to: pileLeft }), 'la suricata junto a la pila, como en Aurora').toBe(0);
    // La hoja (Paper.png a escala 1, como la pinta el motor) en pileX - 35 mas su desvio.
    const sheet = opaqueColumns(decodePng(Buffer.from(sources.Paper.split(',')[1]!, 'base64')));
    const band = { from: pileX - 35 + sheet.from - scale, to: pileX - 35 + sheet.to + 1 + scale };
    expect(differingPixels(shot, pileRef, { from: pileLeft, to: band.from }), 'la pila, a la izquierda de la hoja').toBe(0);
    expect(differingPixels(shot, pileRef, { from: band.to }), 'la pila, a la derecha de la hoja').toBe(0);
    const shifts = [-2, -1, 0, 1, 2].map((k) => k * scale);
    const best = Math.min(...shifts.map((shift) => differingPixels(shot, pileRef, { ...band, shift })));
    expect(best, 'la hoja de la pila, con los desvios al azar').toBe(0);
    // El resultado lo pinta motion con WAAPI, que no sigue al reloj virtual (en la grabacion de
    // Aurora tampoco): lo miran las pruebas en tiempo real. Aqui, que la lectura acabo con las 5.
    const status = await reading(request, baseUrl);
    expect(status.solicitud?.estado).toBe('hecha');
    expect((status.ultima_pasada ?? status.pasada_en_curso)?.resultado).toHaveLength(5);
  });
}
