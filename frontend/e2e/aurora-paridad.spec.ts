// Las cajas de BMS contra las de Aurora (paso 17, especificacion §6.1): la caja, la letra, el
// color y la escala de cada elemento, a 1440 × 900 y a 400 × 860, contra las medidas del prototipo
// del dueno (e2e/aurora/referencia.json, con e2e/aurora/cajas.ts): x, y y ancho ±4 px (a `y` se le
// resta el alto de las bandas del servidor); el alto ±4 px salvo en lo que depende de los datos
// (solo que no pase de su tope); letra y color exactos; escala ±0,01. Los estados: L0 y E0, E1
// (recien abierto y con Procesar en el centro), E2-C y E2-P (en reposo, con la vista de un grupo y
// con una tarjeta; la rueda no se compara: no esta, §1.1), E3, E4, E4-b, E5 (sola, con resultados y
// con filtros) y E6 (todo, una carpeta abierta y la hoja de una factura: la `y` se cuenta desde la
// marca, la pagina se desplaza al abrir); y, con menos movimiento, los que Aurora grabo asi. E7 (P0,
// P4 y P5) se compara en procesar.spec.ts, con el lector de las pruebas. Lo que Aurora no tiene en
// la pagina en un estado tampoco debe verse en BMS.
// Y el desplazamiento (§6.1): cada panel en reposo, cada vista de grupo e importar sin fichero no
// pasan de 53 px a 1440 × 900 ni de 213 px a 400 × 860; el del dialogo de cada factura de la base
// de prueba se mide y se anota (falla si pasa de 300 px una hoja de cuatro filas o menos). Y que
// nada salte al aterrizar el vuelo a Documentos y de vuelta (sus tiempos, T11 y T17, y el del orbe
// al abrir el menu, T01, se miden en aurora-tiempos.spec.ts con la herramienta de §6.2).
import type { Page } from '@playwright/test';
import type { InvoiceRow } from '../src/lib/api';
import { expect, login, settled, test, token } from './fixtures';
import { TEXTS, entryButton, landed, openEntry, openGroup, openInvoice, openMenu, panel, panelRow, setLang, sheetDialog, toHome, treeItem } from './nav';
import { expectLikeAurora, measure } from './aurora/cajas';

const es = TEXTS.es;

const SIZES = [
  { width: 1440, height: 900 },
  { width: 400, height: 860 },
] as const;

for (const size of SIZES) {
  test(`L0, E0, E1, E2-C y E6 como Aurora a ${size.width} px`, async ({ page, baseUrl }) => {
    await page.setViewportSize(size);
    await page.goto(`${baseUrl}/app`);
    // En castellano, como se midio Aurora (el ancho de «Presiona para navegar» es de su texto).
    await setLang(page, 'es');
    const w = size.width;
    // L0 contra el inicio: el saludo, el orbe, la caja y la marca (la linea del idioma es nuestra).
    await expectLikeAurora(page, `E0@${w}`, { skip: ['discreet', 'navigation', 'navSelected', 'heroOrb', 'panel'], as: 'L0' });
    await login(page);
    await expectLikeAurora(page, `E0@${w}`);
    await page.getByRole('button', { name: es.aurora.home.navigate }).click();
    await expect(page.locator('.navigation')).toBeVisible();
    await expectLikeAurora(page, `E1@${w}`);
    // Procesar en el centro: el morado y el orbe de particulas.
    await entryButton(page, 'process').focus();
    await expect(page.locator('.hero-orb')).toBeVisible();
    await expectLikeAurora(page, `E1-procesar@${w}`);
    // E2: Cuentas por cobrar, en reposo, con la vista de un grupo y con una tarjeta (la de Aurora es
    // la de una fila del panel; la nuestra, la de una fila de la vista de un grupo).
    await panelStates(page, 'receivables', `E2-cobrar{}@${w}`);

    // Documentos: todo, una carpeta abierta (la categoria de los clientes, tres como en Aurora) y la
    // hoja de un documento suyo (de la hoja, el dialogo: lo de detras ya esta en la carpeta).
    await documentStates(page, '', w);
  });
}

/** La caja de escribir del inicio (y de la conversacion). */
const askBox = (page: Page) => page.getByRole('textbox', { name: es.aurora.composer.askLabel });

/** Entra en castellano, como se midio Aurora, a `size`. */
async function enter(page: Page, baseUrl: string, size: { width: number; height: number }): Promise<void> {
  await page.setViewportSize(size);
  await page.goto(`${baseUrl}/app`);
  await setLang(page, 'es');
  await login(page);
}

/** E2 con un panel: en reposo, con la vista de su primer grupo y con la tarjeta de su primera fila.
 *  La rueda no se compara: no esta (§1.1). */
async function panelStates(page: Page, entry: 'receivables' | 'payables', state: string): Promise<void> {
  const skip = ['navigation', 'navSelected'];
  await openMenu(page, 'es');
  await entryButton(page, entry).focus();
  await settled(page);
  await entryButton(page, entry).click();
  await expect(page.locator('aside.panel')).toBeVisible();
  expect((await measure(page)).navigation, `${state}: la rueda`).toEqual({ display: 'none' });
  await expectLikeAurora(page, state.replace('{}', ''), { skip });
  await panel(page).locator('.doc-list button.doc').first().click();
  await settled(page);
  // La vista de un grupo es el mismo panel de Aurora (§2.2).
  await expectLikeAurora(page, state.replace('{}', ''), { skip, as: `${state.replace('{}', '').split('@')[0]}-grupo` });
  await panel(page).locator('.doc-list button.doc').first().click();
  await expect(panel(page).locator('.detail')).toBeVisible();
  await expectLikeAurora(page, state.replace('{}', '-tarjeta'), { skip });
}

/** Escribe como una persona en la caja del inicio (E3) y espera a que la caja este quieta. */
async function typeAsk(page: Page, text: string): Promise<void> {
  await askBox(page).pressSequentially(text, { delay: 20 });
  await settled(page);
}

/** Envia lo escrito y espera la respuesta entera (E4). */
async function send(page: Page): Promise<void> {
  await askBox(page).press('Enter');
  await expect(page.locator('.conversation')).toBeVisible();
  await expect(page.locator('.typing-dots')).toHaveCount(0, { timeout: 15_000 });
}

/** E5: la busqueda sola, con los resultados de lo escrito y con los filtros abiertos. */
async function searchStates(page: Page, suffix: string, w: number): Promise<void> {
  await openEntry(page, 'search', 'es');
  await expectLikeAurora(page, `E5${suffix}@${w}`);
  const box = page.getByRole('textbox', { name: es.aurora.composer.searchLabel });
  await box.pressSequentially('Demo', { delay: 20 });
  await box.press('Enter');
  await expect(page.locator('.search-results')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await expectLikeAurora(page, `E5-resultados${suffix}@${w}`);
  await page.getByRole('button', { name: new RegExp(`^${es.aurora.search.filters}( \\d+)?$`) }).click();
  await expect(page.locator('.search-filters')).toBeVisible();
  await expectLikeAurora(page, `E5-filtros${suffix}@${w}`);
}

/** E6: todo, una carpeta abierta (la de un cliente, como en Aurora) y la hoja de un documento suyo. */
async function documentStates(page: Page, suffix: string, w: number): Promise<void> {
  await openEntry(page, 'documents', 'es');
  await landed(page);
  await expectLikeAurora(page, `E6${suffix}@${w}`, { anchor: 'brand' });
  await treeItem(page, es.documents.clients).first().click();
  await treeItem(page, 'Demo Havenbedrijf BV').first().click();
  await expect(page.locator('.ws-profile')).toBeVisible();
  await expectLikeAurora(page, `E6-carpeta${suffix}@${w}`, { anchor: 'brand' });
  await page.locator('.ws-profile .ws-file-table > a').first().click();
  await expect(sheetDialog(page)).toBeVisible();
  await expectLikeAurora(page, `E6-h${suffix}@${w}`, { skip: ['companion', 'wsTitle', 'wsGrid', 'wsSidebar', 'wsProfile'], anchor: 'brand' });
}

for (const size of SIZES) {
  const w = size.width;
  test(`E2-P, E3, E4 y E4-b como Aurora a ${w} px`, async ({ page, baseUrl }) => {
    test.setTimeout(180_000);
    await enter(page, baseUrl, size);
    // E2-P: Cuentas por pagar, como el panel de Aurora.
    await panelStates(page, 'payables', `E2-pagar{}@${w}`);
    // E3: escribiendo desde el inicio (el orbe pequeno junto a la caja; ni saludo ni rueda).
    await toHome(page);
    await typeAsk(page, '¿Cuánto tengo por cobrar?');
    await expectLikeAurora(page, `E3@${w}`);
    // E4: la respuesta, en la conversacion de Aurora.
    await send(page);
    await expectLikeAurora(page, `E4@${w}`);
    // E4-b: el resumen general (Finance Bento), en una conversacion nueva como la de Aurora.
    await page.goto(`${baseUrl}/app`);
    await login(page);
    await expect(askBox(page)).toBeVisible();
    await typeAsk(page, 'Dame un resumen general');
    await send(page);
    await expect(page.locator('.finance-bento')).toBeVisible();
    await expectLikeAurora(page, `E4-b@${w}`);
  });

  test(`E5: la busqueda sola, con resultados y con filtros, como Aurora a ${w} px`, async ({ page, baseUrl }) => {
    test.setTimeout(120_000);
    await enter(page, baseUrl, size);
    await searchStates(page, '', w);
  });

  test(`con menos movimiento, los estados que Aurora grabo asi a ${w} px`, async ({ page, baseUrl }) => {
    test.setTimeout(300_000);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await enter(page, baseUrl, size);
    await expectLikeAurora(page, `E0-reduce@${w}`);
    await page.getByRole('button', { name: es.aurora.home.navigate }).click();
    await expect(page.locator('.navigation')).toBeVisible();
    await expectLikeAurora(page, `E1-reduce@${w}`);
    await entryButton(page, 'process').focus();
    await expect(page.locator('.hero-orb')).toBeVisible();
    await expectLikeAurora(page, `E1-procesar-reduce@${w}`);
    if (w === 1440) {
      // Aurora grabo con menos movimiento Cuentas por cobrar, la conversacion y la busqueda a 1440.
      await panelStates(page, 'receivables', `E2-cobrar{}-reduce@${w}`);
      await toHome(page);
      await typeAsk(page, '¿Cuánto tengo por cobrar?');
      await expectLikeAurora(page, `E3-reduce@${w}`);
      await send(page);
      await expectLikeAurora(page, `E4-reduce@${w}`);
      await page.goto(`${baseUrl}/app`);
      await login(page);
      await expect(askBox(page)).toBeVisible();
      await searchStates(page, '-reduce', w);
    }
    await documentStates(page, '-reduce', w);
    // Procesar en P0 (la cabeza esperando): P4 y P5, con el lector, en procesar.spec.ts.
    await openEntry(page, 'process', 'es');
    await expect(page.locator('.processing-workspace .flow-button')).toHaveText(es.aurora.process.request);
    await expectLikeAurora(page, `E7-P0-reduce@${w}`);
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

/** Un vuelo del orbe: en cada cuadro de verdad, la `y` de lo que no debe moverse (`still`), desde
 *  el clic hasta despues de aterrizar. */
async function flight(page: Page, click: () => Promise<void>, still: string[]): Promise<Record<string, number[]>> {
  await page.evaluate((sels) => {
    const w = window as unknown as { __bmsStill: (number | null)[][] | null };
    const rows: (number | null)[][] = [];
    w.__bmsStill = rows;
    const tick = () => {
      rows.push(sels.map((sel) => document.querySelector(sel)?.getBoundingClientRect().y ?? null));
      if (w.__bmsStill === rows) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, still);
  await click();
  await expect(page.locator('.aurora-route-flight')).toHaveCount(1);
  await landed(page);
  await page.waitForTimeout(400);
  const rows = (await page.evaluate(() => {
    const w = window as unknown as { __bmsStill: (number | null)[][] | null };
    const out = w.__bmsStill ?? [];
    w.__bmsStill = null;
    return out;
  })) as (number | null)[][];
  return Object.fromEntries(still.map((sel, i) => [sel, rows.map((r) => r[i]).filter((y): y is number => y !== null)]));
}

/** Lo que no debe moverse no se mueve: desde que aparece hasta despues de aterrizar, la misma `y`
 *  (con las bandas del servidor encima: la de datos de prueba esta en esta base). */
function expectStill(what: string, ys: Record<string, number[]>): void {
  for (const [sel, values] of Object.entries(ys)) {
    expect(values.length, `${what}: ${sel} a la vista`).toBeGreaterThan(10);
    expect(Math.max(...values) - Math.min(...values), `${what}: ${sel} no salta (${[...new Set(values.map(Math.round))].join(' → ')})`).toBeLessThanOrEqual(0.5);
  }
}

for (const width of [1440, 400] as const) {
  test(`el vuelo a Documentos y de vuelta a ${width} px: nada salta al aterrizar`, async ({ page, baseUrl }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width, height: width === 400 ? 860 : 900 });
    await page.goto(`${baseUrl}/app`);
    await login(page);
    await expect(page.locator('#datos-de-prueba')).toBeVisible();
    // A Documentos: las migas y el companero, quietos desde que aparecen.
    await openMenu(page);
    await entryButton(page, 'documents').focus();
    await settled(page);
    expectStill(`a Documentos, ${width} px`, await flight(page, () => entryButton(page, 'documents').click(), ['.ws-breadcrumbs', '.ws-companion']));
    // De vuelta: el orbe del inicio y la marca, quietos.
    await settled(page);
    expectStill(`de vuelta, ${width} px`, await flight(page, () => page.locator('a.ws-home').click(), ['button.aurora', '.app > .bms-brand']));
  });
}
