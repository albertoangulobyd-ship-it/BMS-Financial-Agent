// Los temas, el castellano y el orbe de Aurora (paso 16) sobre la base de prueba:
// - el oscuro de Aurora por defecto aunque Windows este en claro; el claro y "Volg Windows"
//   se eligen y se guardan por persona, como el idioma; "Volg Windows" cambia en vivo;
// - cada pantalla en claro en los tres idiomas y en oscuro en castellano (el neerlandes y el
//   ingles en oscuro ya los recorre shell.spec.ts): axe sin nada serio, cada pastilla a
//   4,5:1, ningun resto de otro idioma (en castellano se toleran los textos de dominio en
//   ingles: DOMAIN_FALLBACK) y un orbe como mucho;
// - el orbe quieto en reposo: ningun cuadro pedido y casi nada de CPU; se mueve solo mientras
//   carga, y nunca con la ventana oculta, fuera de pantalla o con "menos movimiento"; sin
//   WebGL, el degradado fijo.
// Capturas en CAPTURAS_DIR/dark y CAPTURAS_DIR/light como <idioma>-<pantalla>.png.
import type { Page } from '@playwright/test';
import type { Lang } from '../src/i18n/langs';
import {
  capture,
  chooseTheme,
  expect,
  expectAccessible,
  expectNoLeftovers,
  expectStatusContrast,
  login,
  settled,
  test,
  type Who,
} from './fixtures';

const NAV: ReadonlyArray<readonly [string, Record<Lang, string>]> = [
  ['overview', { nl: 'Overzicht', en: 'Overview', es: 'Resumen' }],
  ['work-queue', { nl: 'Werklijst', en: 'Work queue', es: 'Cola de trabajo' }],
  ['exceptions', { nl: 'Uitzonderingen', en: 'Exceptions', es: 'Excepciones' }],
  ['iban-checks', { nl: 'IBAN-controles', en: 'IBAN checks', es: 'Controles de IBAN' }],
  ['invoices-in', { nl: 'Inkomend', en: 'In', es: 'Recibidas' }],
  ['invoices-out', { nl: 'Uitgaand', en: 'Out', es: 'Emitidas' }],
  ['providers', { nl: 'Leveranciers', en: 'Providers', es: 'Proveedores' }],
  ['clients', { nl: 'Klanten', en: 'Clients', es: 'Clientes' }],
  ['objects', { nl: 'Objecten', en: 'Objects', es: 'Objects' }],
  ['purchase-orders', { nl: 'Inkooporders', en: 'Purchase orders', es: 'Órdenes de compra' }],
  ['cash-flow', { nl: 'Kasstroom', en: 'Cash flow', es: 'Flujo de caja' }],
  ['vat', { nl: 'Btw', en: 'VAT', es: 'IVA' }],
  ['import', { nl: 'Importeren', en: 'Import', es: 'Importar' }],
  ['read-invoices', { nl: 'Facturen lezen', en: 'Read invoices', es: 'Leer facturas' }],
  ['settings', { nl: 'Instellingen', en: 'Settings', es: 'Ajustes' }],
];
const MENU: Record<Lang, string> = { nl: 'Hoofdmenu', en: 'Main menu', es: 'Menú principal' };
const LANG_NAME: Record<Lang, string> = { nl: 'Nederlands', en: 'English', es: 'Español' };

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

async function signIn(page: Page, baseUrl: string, who: Who = 'ana') {
  await page.goto(`${baseUrl}/app`);
  await login(page, who);
}

async function setLang(page: Page, lang: Lang) {
  await page.getByRole('button', { name: LANG_NAME[lang] }).first().click();
  await expect(page.locator('html')).toHaveAttribute('lang', lang);
  await settled(page);
}

/** Lo que la pantalla tarda en cargar: ningun "Cargando..." en la pestana. */
async function loaded(page: Page) {
  await expect(page.locator('#tab-panel [role="status"] .animate-spin')).toHaveCount(0);
}

/** Un orbe con WebGL como mucho por pantalla (orbRegistry). */
async function atMostOneOrb(page: Page, what: string) {
  expect(await page.locator('canvas.aurora-orb__canvas').count(), `orbes en ${what}`).toBeLessThanOrEqual(1);
}

/** Todas las areas del menu, en un idioma, en el tema que este puesto. */
async function tour(page: Page, lang: Lang, theme: string) {
  const menu = page.getByRole('navigation', { name: MENU[lang] });
  for (const [id, labels] of NAV) {
    const label = labels[lang];
    const what = `${lang} ${theme} ${id}`;
    await menu.getByRole('button', { name: new RegExp(`^${escape(label)}\\b`) }).click();
    await expect(page.getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
    await loaded(page);
    if (id === 'overview') await expect(page.getByTestId('summary-card').first()).toBeVisible();
    if (id === 'work-queue') await expect(page.getByRole('table')).toBeVisible();
    await expectAccessible(page, what);
    await expectNoLeftovers(page, lang, what);
    await atMostOneOrb(page, what);
    await capture(page, `${lang}-${id}`);
  }
}

test('oscuro por defecto; claro y "Volg Windows" se eligen y se guardan por persona', async ({ page, baseUrl }) => {
  const html = page.locator('html');
  // La configuracion de las pruebas emula Windows en claro: la app sale en oscuro igual.
  await page.goto(`${baseUrl}/app`);
  await expect(html).toHaveAttribute('data-theme', 'dark');
  await expect(html).toHaveClass(/(^|\s)dark(\s|$)/);
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  await expectAccessible(page, 'entrada en oscuro');
  await capture(page, 'nl-login');
  // El castellano en la entrada, y vuelta al neerlandes.
  await setLang(page, 'es');
  await expect(page.getByRole('heading', { level: 1, name: 'Entrar' })).toBeVisible();
  await expectNoLeftovers(page, 'es', 'entrada en castellano');
  await capture(page, 'es-login');
  await setLang(page, 'nl');

  await login(page, 'ana');
  await chooseTheme(page, 'light');
  await expect(html).not.toHaveClass(/(^|\s)dark(\s|$)/);
  // El menu de la cuenta, en claro, con el tema elegido marcado. (Sin axe con el menu
  // abierto: Radix esconde el resto con aria-hidden mientras el foco esta en el menu.)
  await page.getByRole('button', { name: 'Accountmenu van Ana Demo' }).click();
  await expect(page.getByRole('menuitemradio', { name: 'Licht' })).toHaveAttribute('aria-checked', 'true');
  await expectStatusContrast(page, 'menu de la cuenta en claro');
  await capture(page, 'nl-account-menu');
  await page.keyboard.press('Escape');

  // Recargar borra el token (vive solo en memoria): la entrada sale con el tema de este
  // ordenador, y al entrar, con el de Ana.
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  await expect(html).toHaveAttribute('data-theme', 'light');
  await expectAccessible(page, 'entrada en claro');
  await capture(page, 'nl-login');
  await login(page, 'ana');
  await expect(html).toHaveAttribute('data-theme', 'light');

  // "Volg Windows" en Instellingen: sigue al sistema, tambien si cambia con la app abierta.
  await page.getByRole('navigation', { name: 'Hoofdmenu' }).getByRole('button', { name: /^Instellingen/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Instellingen' })).toBeVisible();
  const themes = page.getByRole('group', { name: 'Thema' });
  await themes.getByRole('button', { name: 'Volg Windows' }).click();
  await expect(themes.getByRole('button', { name: 'Volg Windows' })).toHaveAttribute('aria-pressed', 'true');
  await expect(html).toHaveAttribute('data-theme', 'light');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(html).toHaveAttribute('data-theme', 'dark');
  await expectAccessible(page, 'instellingen, Volg Windows en oscuro');
  await capture(page, 'nl-settings-follow-windows');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(html).toHaveAttribute('data-theme', 'light');
  await themes.getByRole('button', { name: 'Licht' }).click();

  // Otra persona en el mismo ordenador entra con el ultimo tema de este ordenador; lo que
  // elija es suyo y no cambia el de Ana.
  await page.getByRole('button', { name: 'Accountmenu van Ana Demo' }).click();
  await page.getByRole('menuitem', { name: 'Uitloggen' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  await login(page, 'bram');
  await expect(html).toHaveAttribute('data-theme', 'light');
  await chooseTheme(page, 'dark');
  await page.getByRole('button', { name: /^Accountmenu van / }).click();
  await page.getByRole('menuitem', { name: 'Uitloggen' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  await expect(html).toHaveAttribute('data-theme', 'dark');
  await login(page, 'ana');
  await expect(html).toHaveAttribute('data-theme', 'light');
});

for (const lang of ['nl', 'en', 'es'] as const) {
  test(`cada pantalla en claro: ${lang}`, async ({ page, baseUrl }) => {
    await signIn(page, baseUrl);
    await chooseTheme(page, 'light');
    if (lang !== 'nl') await setLang(page, lang);
    await tour(page, lang, 'claro');
  });
}

test('cada pantalla en oscuro: es', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await setLang(page, 'es');
  await tour(page, 'es', 'oscuro');
});

test('las fichas en claro, y una factura en castellano en los dos temas', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await chooseTheme(page, 'light');
  const menu = page.getByRole('navigation', { name: 'Hoofdmenu' });
  const open = async (area: string, row: RegExp, heading: string | RegExp, name: string) => {
    await menu.getByRole('button', { name: new RegExp(`^${area}`) }).click();
    await expect(page.getByRole('heading', { level: 1, name: area, exact: true })).toBeVisible();
    await page.getByRole('table').getByRole('button', { name: row }).first().click();
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
    await loaded(page);
    await expectAccessible(page, `claro ${name}`);
    await expectNoLeftovers(page, 'nl', `claro ${name}`);
    await capture(page, `nl-${name}`);
  };
  await open('Leveranciers', /J\. Voorbeeld Beveiliging/, 'J. Voorbeeld Beveiliging (zzp)', 'provider');
  await open('Klanten', /Demo Havenbedrijf/, 'Demo Havenbedrijf BV', 'client');
  await open('Objecten', /HAVEN-NOORD/, 'Haventerrein Demo-Noord', 'object');
  await open('Inkooporders', /PO-DEMO-4501/, 'PO-DEMO-4501', 'purchase-order');
  await open('Btw', /Q3 2026/, 'Btw Q3 2026', 'vat-quarter');

  // Una factura bloqueada, con su veredicto, sus avisos y sus campos abiertos.
  await menu.getByRole('button', { name: /^Werklijst/ }).click();
  await page.getByRole('table').getByRole('row').filter({ hasText: 'Geblokkeerd' }).first().getByRole('button').first().click();
  await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
  await loaded(page);
  await page.getByRole('button', { name: /^Velden/ }).click();
  await expectAccessible(page, 'claro factuur');
  await capture(page, 'nl-invoice');
  await setLang(page, 'es');
  // El tipo de factura es texto de dominio: en ingles hasta que llegue es.json (DOMAIN_FALLBACK).
  await expect(page.getByRole('heading', { level: 2, name: 'Campos' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: /^(Factura|Invoice) / })).toBeVisible();
  await expectAccessible(page, 'claro factura en castellano');
  await expectNoLeftovers(page, 'es', 'claro factura');
  await capture(page, 'es-invoice');
  await chooseTheme(page, 'dark');
  await expectAccessible(page, 'oscuro factura en castellano');
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

/** El panel del Overzicht no contesta hasta que la prueba lo suelta: mientras, carga. */
async function holdPanel(page: Page) {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v2/panel', async (route) => {
    await held;
    await route.fallback();
  });
  return () => release();
}

test('el orbe: se mueve solo mientras carga y en reposo no pide cuadros ni gasta CPU', async ({ page, baseUrl }) => {
  const frames = await countFrames(page);
  const release = await holdPanel(page);
  await signIn(page, baseUrl);
  const orb = page.locator('[data-orb]');
  await expect(orb).toHaveCount(1);
  await expect(orb).toHaveAttribute('data-orb', 'webgl');
  await expect(orb).toHaveAttribute('aria-label', /^Aurora/);
  // Cargando: se mueve, y a 30 imagenes por segundo como mucho (el bucle pide cada cuadro y
  // dibuja uno de cada dos a 60 Hz: aqui solo se mira que pide).
  await expect(orb).toHaveAttribute('data-moving', 'true');
  const before = await frames();
  await page.waitForTimeout(1000);
  const moving = (await frames()) - before;
  expect(moving, 'cuadros pedidos en 1 s moviendose').toBeGreaterThan(10);

  // Oculta la ventana: se para. Vuelve: sigue.
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(orb).toHaveAttribute('data-moving', 'false');
  await page.evaluate(() => {
    delete (document as unknown as { visibilityState?: string }).visibilityState;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(orb).toHaveAttribute('data-moving', 'true');
  // Fuera de pantalla: se para. De vuelta: sigue.
  await orb.evaluate((el) => {
    el.style.transform = 'translateY(-4000px)';
  });
  await expect(orb).toHaveAttribute('data-moving', 'false');
  await orb.evaluate((el) => {
    el.style.transform = '';
  });
  await expect(orb).toHaveAttribute('data-moving', 'true');

  // Llega el panel: reposo.
  release();
  await expect(page.getByTestId('summary-card').first()).toBeVisible();
  await expect(orb).toHaveAttribute('data-moving', 'false');
  await settled(page);
  // En reposo: ningun cuadro pedido en 3 s (con margen para algo suelto de la app; el orbe
  // moviendose pediria unos 180).
  const restStart = await frames();
  await page.waitForTimeout(3000);
  const atRest = (await frames()) - restStart;
  expect(atRest, 'cuadros pedidos en 3 s en reposo').toBeLessThan(10);
  // Y el hilo principal casi sin trabajo: menos de 0,25 s de tareas en 5 s (un 5 % de un
  // nucleo; en reposo de verdad se mide cerca de 0).
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  const task = async () => {
    const { metrics } = await cdp.send('Performance.getMetrics');
    return metrics.find((m) => m.name === 'TaskDuration')?.value ?? Number.NaN;
  };
  const t0 = await task();
  await page.waitForTimeout(5000);
  const busy = (await task()) - t0;
  console.log(`orbe en reposo: ${atRest} cuadros en 3 s, ${(busy * 1000).toFixed(0)} ms de tareas en 5 s; moviendose: ${moving} cuadros en 1 s`);
  expect(busy, 'segundos de tareas del hilo principal en 5 s en reposo').toBeLessThan(0.25);
  await expect(orb).toHaveAttribute('data-moving', 'false');
  await capture(page, 'nl-overview-orb-at-rest');
});

test('el orbe con "menos movimiento": quieto tambien mientras carga', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const frames = await countFrames(page);
  const release = await holdPanel(page);
  await signIn(page, baseUrl);
  const orb = page.locator('[data-orb]');
  await expect(orb).toHaveAttribute('data-orb', 'webgl');
  await expect(page.locator('#tab-panel [role="status"]').first()).toBeVisible();
  await settled(page);
  const before = await frames();
  await page.waitForTimeout(1000);
  expect((await frames()) - before, 'cuadros pedidos en 1 s cargando con menos movimiento').toBeLessThan(10);
  await expect(orb).toHaveAttribute('data-moving', 'false');
  release();
  await expect(page.getByTestId('summary-card').first()).toBeVisible();
  await expect(orb).toHaveAttribute('data-moving', 'false');
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
  await expect(page.getByTestId('summary-card').first()).toBeVisible();
  const orb = page.locator('[data-orb]');
  await expect(orb).toHaveAttribute('data-orb', 'fallback');
  await expect(page.locator('canvas.aurora-orb__canvas')).toHaveCount(0);
  const image = await orb.locator('.aurora-orb__fallback').evaluate((el) => getComputedStyle(el).backgroundImage);
  expect(image).toContain('gradient');
  await expectAccessible(page, 'overzicht sin WebGL');
  await capture(page, 'nl-overview-no-webgl');
});
