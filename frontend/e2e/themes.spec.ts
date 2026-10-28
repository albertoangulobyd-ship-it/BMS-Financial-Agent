// Los temas, el castellano y el orbe de Aurora (paso 16; paso 17: la onda de Aurora tal cual):
// - el oscuro de Aurora por defecto aunque Windows este en claro; el claro y "Volg Windows"
//   se eligen en Ajustes > Thema y se guardan por persona, como el idioma; "Volg Windows"
//   cambia en vivo;
// - cada sitio (cada panel en reposo y cada vista de grupo, la busqueda, Documentos y Procesar)
//   en claro en los tres idiomas y en oscuro en castellano (los tres idiomas en oscuro ya los
//   recorre shell.spec.ts): axe sin nada serio, ningun resto de otro idioma y un orbe como mucho;
//   y las fichas (las carpetas de Documentos, las hojas de un Object, una PO y una factura, la
//   tarjeta de un trimestre y la de una excepcion) en claro;
// - el orbe (la SiriWave de Aurora): se mueve al ritmo de la pantalla, como en Aurora, tambien
//   con "menos movimiento"; se para con la ventana oculta o fuera de la vista y sigue al volver;
//   lo que cuesta al hilo principal se anota (especificacion §6.6 y §7, punto 1); sin WebGL, el
//   degradado fijo.
// Capturas en CAPTURAS_DIR/dark y CAPTURAS_DIR/light como <idioma>-<sitio>.png.
import type { Page } from '@playwright/test';
import type { InvoiceRow } from '../src/lib/api';
import type { Lang } from '../src/i18n/langs';
import { capture, expect, expectAccessible, expectNoLeftovers, login, settled, test, token, type Who } from './fixtures';
import {
  TEXTS,
  chooseTheme,
  openCard,
  openDocuments,
  openEntry,
  openFolder,
  openGroup,
  openInvoice,
  openSheetRow,
  panel,
  panelRow,
  profileRow,
  setLang,
  sheetDialog,
  signOut,
  tourAll,
} from './nav';

async function signIn(page: Page, baseUrl: string, who: Who = 'ana') {
  await page.goto(`${baseUrl}/app`);
  await login(page, who);
}

/** Un orbe como mucho a la vista: el de Aurora (la onda o las particulas de Procesar) o el
 *  companero de Documentos. */
async function atMostOneOrb(page: Page, what: string) {
  const shown = await page.locator('button.aurora canvas, .ws-companion canvas').evaluateAll((els) =>
    els.filter((el) => {
      const r = el.getBoundingClientRect();
      const visible = getComputedStyle(el).visibility !== 'hidden';
      return visible && r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
    }).length
  );
  expect(shown, `orbes en ${what}`).toBeLessThanOrEqual(1);
}

/** Cada sitio de la app, en un idioma, en el tema que este puesto. */
async function tour(page: Page, lang: Lang, theme: string) {
  await tourAll(page, lang, async (where) => {
    const what = `${lang} ${theme} ${where}`;
    await expectAccessible(page, what);
    await expectNoLeftovers(page, lang, what);
    await atMostOneOrb(page, what);
    await capture(page, `${lang}-${where.replace(/[^\p{L}\d-]+/gu, '-').toLowerCase()}`);
  });
}

test('oscuro por defecto; claro y "Volg Windows" se eligen y se guardan por persona', async ({ page, baseUrl }) => {
  const html = page.locator('html');
  // La configuracion de las pruebas emula Windows en claro: la app sale en oscuro igual.
  await page.goto(`${baseUrl}/app`);
  await expect(html).toHaveAttribute('data-theme', 'dark');
  await expect(html).toHaveClass(/(^|\s)dark(\s|$)/);
  await expect(page.getByRole('heading', { level: 1, name: TEXTS.nl.aurora.login.welcome })).toBeVisible();
  await expectAccessible(page, 'entrada en oscuro');
  await capture(page, 'nl-login');
  // El castellano en la entrada, y vuelta al neerlandes.
  await setLang(page, 'es');
  await expect(page.getByRole('heading', { level: 1, name: TEXTS.es.aurora.login.welcome })).toBeVisible();
  await expectNoLeftovers(page, 'es', 'entrada en castellano');
  await capture(page, 'es-login');
  await setLang(page, 'nl');

  await login(page, 'ana');
  await chooseTheme(page, 'light');
  await expect(html).not.toHaveClass(/(^|\s)dark(\s|$)/);
  // Ajustes > Thema, en claro, con el tema elegido marcado.
  await expect(panelRow(page, 'Licht')).toContainText(TEXTS.nl.aurora.settings.inUse);
  await expectAccessible(page, 'ajustes, tema en claro');
  await capture(page, 'nl-settings-theme');

  // Recargar borra el token (vive solo en memoria): la entrada sale con el tema de este
  // ordenador, y al entrar, con el de Ana.
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: TEXTS.nl.aurora.login.welcome })).toBeVisible();
  await expect(html).toHaveAttribute('data-theme', 'light');
  await expectAccessible(page, 'entrada en claro');
  await capture(page, 'nl-login');
  await login(page, 'ana');
  await expect(html).toHaveAttribute('data-theme', 'light');
  await expectAccessible(page, 'inicio en claro');
  await capture(page, 'nl-home');

  // "Volg Windows": sigue al sistema, tambien si cambia con la app abierta.
  await chooseTheme(page, 'system');
  await expect(panelRow(page, 'Volg Windows')).toContainText(TEXTS.nl.aurora.settings.inUse);
  await expect(html).toHaveAttribute('data-theme', 'light');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(html).toHaveAttribute('data-theme', 'dark');
  await expectAccessible(page, 'ajustes, Volg Windows en oscuro');
  await capture(page, 'nl-settings-follow-windows');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(html).toHaveAttribute('data-theme', 'light');
  await panelRow(page, 'Licht').click();

  // Otra persona en el mismo ordenador entra con el ultimo tema de este ordenador; lo que
  // elija es suyo y no cambia el de Ana.
  await signOut(page);
  await login(page, 'bram');
  await expect(html).toHaveAttribute('data-theme', 'light');
  await chooseTheme(page, 'dark');
  await signOut(page);
  await expect(html).toHaveAttribute('data-theme', 'dark');
  await login(page, 'ana');
  await expect(html).toHaveAttribute('data-theme', 'light');
});

for (const lang of ['nl', 'en', 'es'] as const) {
  test(`cada pantalla en claro: ${lang}`, async ({ page, baseUrl }) => {
    test.setTimeout(600_000);
    await signIn(page, baseUrl);
    await chooseTheme(page, 'light');
    if (lang !== 'nl') await setLang(page, lang);
    await tour(page, lang, 'claro');
  });
}

test('cada pantalla en oscuro: es', async ({ page, baseUrl }) => {
  test.setTimeout(600_000);
  await signIn(page, baseUrl);
  await setLang(page, 'es');
  await tour(page, 'es', 'oscuro');
});

test('las fichas en claro, y una factura en castellano en los dos temas', async ({ page, baseUrl, request }) => {
  test.setTimeout(300_000);
  // Una factura bloqueada con un numero que no se repite: la que se abre al final.
  const response = await request.get(`${baseUrl}/api/v2/facturas`, { headers: { 'X-BMS-Token': token('ana') } });
  const invoices = ((await response.json()) as { facturas: InvoiceRow[] }).facturas;
  const blocked = invoices.find((f) => f.nivel === 'bloqueada' && f.numero && invoices.filter((g) => g.numero === f.numero).length === 1)!;
  expect(blocked, 'la base de prueba lleva una factura bloqueada').toBeTruthy();
  const number = blocked.numero!;
  const t = TEXTS.nl;
  await signIn(page, baseUrl);
  await chooseTheme(page, 'light');
  const check = async (name: string) => {
    await settled(page);
    await expectAccessible(page, `claro ${name}`);
    await expectNoLeftovers(page, 'nl', `claro ${name}`);
    await capture(page, `nl-${name}`);
  };
  // Las carpetas de Documentos: un proveedor (con sus documentos) y un cliente (con sus Objects y
  // sus PO); la hoja de un Object y la de una PO.
  await openDocuments(page);
  await openFolder(page, 'J. Voorbeeld Beveiliging (zzp)', 'provider');
  await expect(profileRow(page, /JV-\d{4}-\d{3}/).first()).toBeVisible();
  await check('provider');
  await openFolder(page, 'Demo Havenbedrijf BV', 'client');
  await check('client');
  for (const [row, name] of [
    [`${t.records.object.label} HAVEN-NOORD`, 'object'],
    [`${t.records['purchase-order'].label} PO-DEMO-4501`, 'purchase-order'],
  ] as const) {
    await profileRow(page, row).first().click();
    await expect(sheetDialog(page).getByTestId('paper')).toBeVisible();
    await check(name);
    await page.keyboard.press('Escape');
    await expect(sheetDialog(page)).toHaveCount(0);
  }
  // La tarjeta de un trimestre del IVA y la de una excepcion.
  await openEntry(page, 'vat');
  await openCard(page, panelRow(page, 'Q3 2026'));
  await check('vat-quarter');
  await openEntry(page, 'home');
  await openGroup(page, t.nav.exceptions.label);
  await openCard(page, panel(page).locator('.doc-list button.doc').first());
  await check('exception');

  // Una factura bloqueada, con su veredicto, sus avisos y lo leido abierto.
  await openInvoice(page, number);
  await openSheetRow(page, t.aurora.sheet.read);
  await check('invoice');
  // En castellano, en claro y en oscuro (el idioma y el tema estan en Ajustes: se vuelve a abrir).
  await setLang(page, 'es');
  await openInvoice(page, number, { lang: 'es' });
  await openSheetRow(page, TEXTS.es.aurora.sheet.read);
  await settled(page);
  await expectAccessible(page, 'claro factura en castellano');
  await expectNoLeftovers(page, 'es', 'claro factura');
  await capture(page, 'es-invoice');
  await chooseTheme(page, 'dark', 'es');
  await openInvoice(page, number, { lang: 'es' });
  await openSheetRow(page, TEXTS.es.aurora.sheet.read);
  await settled(page);
  await expectAccessible(page, 'oscuro factura en castellano');
  await expectNoLeftovers(page, 'es', 'oscuro factura');
  await capture(page, 'es-invoice');
});

/** Cuenta las veces que la pagina pide un cuadro (requestAnimationFrame en el mundo de la
 *  pagina; las esperas de Playwright van en otro). */
async function countFrames(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __frames: number };
    w.__frames = 0;
    const original = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = (callback: FrameRequestCallback) => {
      w.__frames += 1;
      return original(callback);
    };
  });
  return () => page.evaluate(() => (window as unknown as { __frames: number }).__frames);
}

/** Los cuadros que pide la pagina en `ms`. */
async function framesIn(frames: () => Promise<number>, page: Page, ms: number): Promise<number> {
  const before = await frames();
  await page.waitForTimeout(ms);
  return (await frames()) - before;
}

/** La ventana oculta (o visible otra vez), como cuando se minimiza. */
async function hideWindow(page: Page, hidden: boolean) {
  await page.evaluate((hidden) => {
    if (hidden) {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    } else {
      delete (document as unknown as { visibilityState?: string }).visibilityState;
      delete (document as unknown as { hidden?: boolean }).hidden;
    }
    document.dispatchEvent(new Event('visibilitychange'));
  }, hidden);
}

test('el orbe: se mueve al ritmo de la pantalla y se para con la ventana oculta o fuera de la vista', async ({ page, baseUrl }) => {
  const frames = await countFrames(page);
  await signIn(page, baseUrl);
  await settled(page);
  const orb = page.locator('.aurora .hero-wave canvas');
  await expect(orb).toHaveCount(1);
  await expect(orb).not.toHaveClass(/siri-wave-fallback/);
  // En reposo se mueve, como en Aurora (§7, punto 1): pide cada cuadro.
  const moving = await framesIn(frames, page, 1000);
  expect(moving, 'cuadros pedidos en 1 s en el inicio').toBeGreaterThan(20);
  // Oculta la ventana: se para. Vuelve: sigue.
  await hideWindow(page, true);
  await page.waitForTimeout(200);
  expect(await framesIn(frames, page, 1000), 'cuadros con la ventana oculta').toBeLessThan(5);
  await hideWindow(page, false);
  await expect.poll(() => framesIn(frames, page, 500)).toBeGreaterThan(10);
  // Fuera de la vista: se para. De vuelta: sigue.
  await page.locator('.aurora').evaluate((el) => {
    (el as HTMLElement).style.translate = '0 -4000px';
  });
  await page.waitForTimeout(300);
  expect(await framesIn(frames, page, 1000), 'cuadros con el orbe fuera de la vista').toBeLessThan(5);
  await page.locator('.aurora').evaluate((el) => {
    (el as HTMLElement).style.translate = '';
  });
  await expect.poll(() => framesIn(frames, page, 500)).toBeGreaterThan(10);
  // Lo que cuesta, para el registro (sin limite: §7, punto 1).
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  const task = async () => {
    const { metrics } = await cdp.send('Performance.getMetrics');
    return metrics.find((m) => m.name === 'TaskDuration')?.value ?? Number.NaN;
  };
  const t0 = await task();
  await page.waitForTimeout(5000);
  const busy = (await task()) - t0;
  console.log(`orbe en el inicio: ${moving} cuadros en 1 s, ${(busy * 1000).toFixed(0)} ms de tareas del hilo principal en 5 s`);
  await capture(page, 'nl-home-orb');
});

test('el orbe con "menos movimiento": sigue moviendose, como en Aurora', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const frames = await countFrames(page);
  await signIn(page, baseUrl);
  await settled(page);
  expect(await framesIn(frames, page, 1000), 'cuadros pedidos en 1 s con menos movimiento').toBeGreaterThan(20);
});

test('sin WebGL, el orbe es el degradado fijo y la pantalla sigue igual', async ({ page, baseUrl }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...rest: unknown[]) {
      if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') return null;
      return (original as (this: HTMLCanvasElement, ...args: unknown[]) => unknown).call(this, type, ...rest);
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await signIn(page, baseUrl);
  const orb = page.locator('.aurora .hero-wave canvas');
  await expect(orb).toHaveClass(/siri-wave-fallback/);
  const image = await orb.evaluate((el) => getComputedStyle(el).backgroundImage);
  expect(image).toContain('gradient');
  await expect(page.getByRole('button', { name: TEXTS.nl.aurora.home.navigate })).toBeVisible();
  await expectAccessible(page, 'inicio sin WebGL');
  await capture(page, 'nl-home-no-webgl');
});
