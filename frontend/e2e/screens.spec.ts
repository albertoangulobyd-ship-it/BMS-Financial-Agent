// El resto de pantallas (paso 15, B2) sobre la base de prueba: las fichas de proveedor,
// cliente, Object, PO, trimestre del btw y factura en neerlandes y en ingles; la caja con su
// estimacion aparte; el btw con la descarga del werkblad y sus estados (la aangifte la
// anota una persona, el programa no presenta nada); importar primero como proef y despues de
// verdad; la lectura de los pdf sin ningun boton que la lance; y la configuracion. En cada
// pantalla: solo 127.0.0.1, ninguna violacion de la CSP ni error en la consola (fixtures),
// axe sin nada serio y ningun resto de otro idioma (fixtures). Captura de cada una como
// <idioma>-<pantalla>.png en CAPTURAS_DIR.
import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import type { ViewId } from '../src/screens/sections';
import { capture, expect, expectAccessible, expectNoLeftovers, login, settled, test, token, type Who } from './fixtures';
import { ENTRIES, TEXTS, crumbs, entryButton, fill, go, openEntry, openMenu, openSettingsRow, panel, panelRow, setLang as switchLang } from './nav';

type Lang = 'nl' | 'en' | 'es';

/** Las pantallas por el nombre que se ve (asi se leen las pruebas); desde el paso 16 se llega
 *  a cada una por su entrada y su vista (e2e/nav.ts). */
const VIEW: Record<string, ViewId> = {
  Leveranciers: 'providers',
  Providers: 'providers',
  Klanten: 'clients',
  Clients: 'clients',
  Objecten: 'objects',
  Objects: 'objects',
  // Las PO de la base de prueba que se miran aqui son de clientes (PO-DEMO-4501).
  Inkooporders: 'client-pos',
  'Purchase orders': 'client-pos',
  Kasstroom: 'cash-flow',
  Btw: 'vat',
  VAT: 'vat',
  Importeren: 'import',
  'Facturen lezen': 'read-invoices',
  Instellingen: 'settings',
};

async function signIn(page: Page, baseUrl: string, who: Who = 'ana') {
  await page.goto(`${baseUrl}/app`);
  await login(page, who);
}

async function setLang(page: Page, lang: Lang) {
  await switchLang(page, lang);
}

/** El idioma se cambia en Ajustes (paso 17: un panel, fuera de la pantalla): despues se vuelve
 *  a la misma pantalla por el mismo camino, ya en el idioma nuevo. */
async function setLangAnd(page: Page, lang: Lang, back: (lang: Lang) => Promise<void>) {
  await switchLang(page, lang);
  await back(lang);
}

/** Ajustes y una de sus filas (E2-A). */
async function openSettingsRowHere(page: Page, row: 'account' | 'system', lang: Lang) {
  await openSettingsRow(page, row, lang);
}

async function nav(page: Page, label: string, lang: Lang = 'nl') {
  await go(page, VIEW[label]!, lang);
}

/** Lo ultimo de las migas: la ficha donde se esta. */
async function here(page: Page): Promise<string> {
  return (await crumbs(page)).at(-1) ?? '';
}

/** Lo que se mira en cada pantalla, y su captura. */
async function check(page: Page, lang: Lang, screen: string) {
  await expectAccessible(page, `${lang} ${screen}`);
  await expectNoLeftovers(page, lang, `${lang} ${screen}`);
  await capture(page, `${lang}-${screen}`);
}

/** Vuelve arriba (la captura de una ficha empieza por lo que es). */
async function toTop(page: Page) {
  await page.evaluate(() => window.scrollTo(0, 0));
}

/** La tabla de la pantalla cabe en su caja: no hay que desplazarla de lado. */
async function tableFits(page: Page) {
  const box = page.getByRole('table').locator('xpath=..');
  return box.evaluate((el) => el.scrollWidth <= el.clientWidth + 1);
}

/** Abre una fila de una lista por su boton (el nombre accesible empieza por lo que es). */
async function openRow(page: Page, name: RegExp) {
  await page.getByRole('table').getByRole('button', { name }).first().click();
}

test('de fiches: leverancier, klant, object, inkooporder en factuur, in NL en EN', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);

  // Leverancier: de geblokkeerde met het dubbele factuurnummer.
  await nav(page, 'Leveranciers');
  await expect(page.getByRole('columnheader', { name: 'Waarom' })).toBeVisible();
  await check(page, 'nl', 'providers');
  await openRow(page, /J\. Voorbeeld Beveiliging/);
  await expect(page.getByRole('heading', { level: 1, name: 'J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
  expect(await here(page)).toContain('J. Voorbeeld');
  await expect(page.getByRole('heading', { level: 3, name: 'Factuurnummer dubbel' }).first()).toBeVisible();
  await check(page, 'nl', 'provider');
  await page.getByRole('button', { name: /^Bankrekeningen/ }).click();
  await expect(page.getByText('Telefoon voor controle: 06-55500102')).toBeVisible();
  await page.getByRole('button', { name: /^Alle facturen/ }).click();
  await check(page, 'nl', 'provider-details');
  const provider = async (lang: Lang) => {
    await go(page, 'providers', lang);
    await openRow(page, /J\. Voorbeeld Beveiliging/);
    await expect(page.getByRole('heading', { level: 1, name: 'J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
  };
  // De factuur van de melding, in het Nederlands (de kruimels gaan door).
  await toTop(page);
  await page.getByRole('button', { name: 'Factuur JV-2026-006 openen' }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: /JV-2026-006$/ })).toBeVisible();
  await check(page, 'nl', 'invoice');
  await setLangAnd(page, 'en', provider);
  await expect(page.getByRole('heading', { level: 3, name: 'Invoice number used twice' }).first()).toBeVisible();
  await check(page, 'en', 'provider');
  await page.getByRole('button', { name: /^All invoices/ }).click();
  await page.getByRole('button', { name: /^All invoices/ }).scrollIntoViewIfNeeded();
  await check(page, 'en', 'provider-details');
  await toTop(page);
  // Een melding opent haar factuur, binnen Te betalen (de kruimels gaan door).
  await page.getByRole('button', { name: 'Open invoice JV-2026-006' }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: /JV-2026-006$/ })).toBeVisible();
  expect(await crumbs(page, 'en')).toEqual(['Payables', 'Providers', 'J. Voorbeeld Beveiliging (zzp)', 'JV-2026-006']);
  await check(page, 'en', 'invoice');
  await setLang(page, 'nl');

  // Klant: wat nog gefactureerd moet worden (V6) staat bovenaan.
  await nav(page, 'Klanten');
  await check(page, 'nl', 'clients');
  await openRow(page, /Demo Havenbedrijf/);
  await expect(page.getByRole('heading', { level: 1, name: 'Demo Havenbedrijf BV' })).toBeVisible();
  await expect(page.getByText('Nog te factureren', { exact: true })).toBeVisible();
  await check(page, 'nl', 'client');
  await setLangAnd(page, 'en', async (lang) => {
    await go(page, 'clients', lang);
    await openRow(page, /Demo Havenbedrijf/);
  });
  await expect(page.getByText('Not yet invoiced', { exact: true })).toBeVisible();
  await check(page, 'en', 'client');
  await setLang(page, 'nl');

  // Object: opbrengst en marge per periode, uren gepland tegenover gefactureerd.
  await nav(page, 'Objecten');
  await check(page, 'nl', 'objects');
  await openRow(page, /HAVEN-NOORD/);
  await expect(page.getByRole('heading', { level: 1, name: 'Haventerrein Demo-Noord' })).toBeVisible();
  expect(await here(page)).toContain('HAVEN-NOORD');
  await check(page, 'nl', 'object');
  await page.getByRole('button', { name: 'Dit jaar' }).click();
  await expect(page.getByRole('button', { name: 'Dit jaar' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: /^Uren per week/ }).click();
  await expect(page.getByRole('columnheader', { name: 'Nog niet gefactureerd' })).toBeVisible();
  await check(page, 'nl', 'object-details');
  await setLangAnd(page, 'en', async (lang) => {
    await go(page, 'objects', lang);
    await openRow(page, /HAVEN-NOORD/);
    await expect(page.getByRole('heading', { level: 1, name: 'Haventerrein Demo-Noord' })).toBeVisible();
  });
  await check(page, 'en', 'object');
  await page.getByRole('button', { name: /^Hours per week/ }).click();
  await expect(page.getByRole('columnheader', { name: 'Not yet invoiced' })).toBeVisible();
  await check(page, 'en', 'object-details');
  await setLang(page, 'nl');

  // Inkooporder: waarde, verbruikt, over en de verwachting.
  await nav(page, 'Inkooporders');
  await check(page, 'nl', 'purchase-orders');
  await openRow(page, /PO-DEMO-4501/);
  await expect(page.getByRole('heading', { level: 1, name: 'PO-DEMO-4501' })).toBeVisible();
  await expect(page.getByText('Verwachting', { exact: true })).toBeVisible();
  await check(page, 'nl', 'purchase-order');
  await setLangAnd(page, 'en', async (lang) => {
    await go(page, 'client-pos', lang);
    await openRow(page, /PO-DEMO-4501/);
  });
  await expect(page.getByText('Forecast', { exact: true })).toBeVisible();
  await check(page, 'en', 'purchase-order');
  await nav(page, 'Providers', 'en');
  await check(page, 'en', 'providers');
  await nav(page, 'Clients', 'en');
  await check(page, 'en', 'clients');
  await nav(page, 'Objects', 'en');
  await check(page, 'en', 'objects');
  await nav(page, 'Purchase orders', 'en');
  await check(page, 'en', 'purchase-orders');
});

test('las fichas en castellano: proveedor, cliente, Object, PO, trimestre del IVA, factura y excepcion', async ({
  page,
  baseUrl,
  request,
}) => {
  // Revision del paso 16: las fichas solo se miraban en NL y EN, y en castellano salian IVA y
  // BTW, abono y nota de credito, aviso y hallazgo, fichero y archivo y "Esperando a el
  // proveedor" con la prueba en verde. check() mira ahora tambien el glosario (fixtures.ts).
  const t = TEXTS.es;
  const response = await request.get(`${baseUrl}/api/v2/excepciones`, { headers: { 'X-BMS-Token': token('ana') } });
  const waiting = ((await response.json()) as { excepciones: { id: number; esperando_a: string | null }[] }).excepciones.find(
    (e) => e.esperando_a === 'proveedor'
  )!;
  expect(waiting, 'la base de prueba lleva una excepcion esperando al proveedor').toBeTruthy();
  await signIn(page, baseUrl);
  await setLang(page, 'es');

  await go(page, 'providers', 'es');
  await check(page, 'es', 'providers');
  await openRow(page, /J\. Voorbeeld Beveiliging/);
  await expect(page.getByRole('heading', { level: 1, name: 'J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
  await check(page, 'es', 'provider');

  await go(page, 'clients', 'es');
  await check(page, 'es', 'clients');
  await openRow(page, /Demo Havenbedrijf/);
  await expect(page.getByRole('heading', { level: 1, name: 'Demo Havenbedrijf BV' })).toBeVisible();
  await check(page, 'es', 'client');

  await go(page, 'objects', 'es');
  await check(page, 'es', 'objects');
  await openRow(page, /HAVEN-NOORD/);
  await expect(page.getByRole('heading', { level: 1, name: 'Haventerrein Demo-Noord' })).toBeVisible();
  await check(page, 'es', 'object');

  await go(page, 'client-pos', 'es');
  await check(page, 'es', 'purchase-orders');
  await openRow(page, /PO-DEMO-4501/);
  await expect(page.getByRole('heading', { level: 1, name: 'PO-DEMO-4501' })).toBeVisible();
  // Un porcentaje, una sola forma (sin espacio, como los textos del motor: "85,95%").
  await expect(page.getByRole('main')).not.toContainText(/\d[\u00a0 ]%/);
  await expect(page.getByRole('main')).toContainText(/\d%/);
  await check(page, 'es', 'purchase-order');

  await go(page, 'vat', 'es');
  await check(page, 'es', 'vat');
  await openRow(page, /Q3 2026/);
  await expect(page.getByRole('heading', { level: 1, name: fill(t.vat.title, { quarter: 'Q3 2026' }) })).toBeVisible();
  await check(page, 'es', 'vat-quarter');

  // Una factura de venta con sus campos abiertos (IVA en las cifras de la app y del motor).
  await go(page, 'invoices-out', 'es');
  await page.getByRole('table').getByRole('button').first().click();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(`^${t.sections.fields}`) }).click();
  await expect(page.getByRole('main')).toContainText('IVA');
  await check(page, 'es', 'invoice');

  // La excepcion que espera al proveedor: "Esperando al proveedor", no "a el".
  await go(page, 'exceptions', 'es');
  await page.getByRole('button', { name: fill(t.exceptions.openLabel, { id: waiting.id }) }).click();
  await expect(page.getByText('Esperando al proveedor').first()).toBeVisible();
  await check(page, 'es', 'exception');
});

test('kasstroom: één tabel en de schatting uit de planning apart', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await nav(page, 'Kasstroom');
  const table = page.getByRole('table');
  for (const period of ['Al vervallen', 'Deze week', 'Rest van deze maand', 'Komende 30 dagen', 'Alles wat openstaat']) {
    await expect(table.getByText(period, { exact: true })).toBeVisible();
  }
  await expect(page.getByText('Schatting · geen facturen')).toBeVisible();
  // Sin graficos en la pantalla (el lienzo del orbe de la esquina es del marco, no de ella).
  await expect(page.locator('#contenido canvas, #contenido svg[role="img"]')).toHaveCount(0);
  await check(page, 'nl', 'cash-flow');
  await setLangAnd(page, 'en', (lang) => go(page, 'cash-flow', lang));
  await expect(page.getByText('Estimate · not invoices')).toBeVisible();
  await check(page, 'en', 'cash-flow');
});

test('btw: het werkblad downloaden, klaarzetten en de ingediende aangifte vastleggen (door een tweede persoon)', async ({
  page,
  baseUrl,
  browser,
  watch,
}) => {
  // De tweede persoon: wie klaarzette, krijgt een 403 (segunda_persona) als hij zelf vastlegt.
  watch.expectHttpErrors(403);
  // Bram zet het kwartaal terug en weer klaar.
  await signIn(page, baseUrl, 'bram');
  await nav(page, 'Btw');
  await expect(page.getByText('De aangifte doe je zelf in het portaal van de Belastingdienst')).toBeVisible();
  await check(page, 'nl', 'vat');
  await openRow(page, /Q3 2026/);
  await expect(page.getByRole('heading', { level: 1, name: 'Btw Q3 2026' })).toBeVisible();
  expect(await here(page)).toBe('Btw Q3 2026');
  await check(page, 'nl', 'vat-quarter');
  const quarter = async (lang: Lang) => {
    await go(page, 'vat', lang);
    await openRow(page, /Q3 2026/);
    await expect(page.getByRole('heading', { level: 1, name: fill(TEXTS[lang].vat.title, { quarter: 'Q3 2026' }) })).toBeVisible();
  };
  // Dezelfde stappen in het Engels: elk dialoogvenster bekijken en annuleren.
  await setLangAnd(page, 'en', quarter);
  await check(page, 'en', 'vat-quarter');
  await page.getByRole('button', { name: 'Reopen quarter' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await check(page, 'en', 'vat-reopen-dialog');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  await setLangAnd(page, 'nl', quarter);

  // Het werkblad: fetch met de code, als bestand, en de bytes die de hash dragen.
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Werkblad downloaden' }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('btw-2026-T3.csv');
  const sheet = readFileSync((await download.path())!, 'utf8');
  expect(sheet).toContain('2026-T3');
  expect(sheet).toContain('5c;');

  await page.getByRole('button', { name: 'Kwartaal heropenen' }).click();
  const reopen = page.getByRole('dialog');
  await expect(reopen).toBeVisible();
  await check(page, 'nl', 'vat-reopen-dialog');
  await reopen.getByLabel('Toelichting').fill('Nog een factuur bekijken');
  await reopen.getByRole('button', { name: 'Kwartaal heropenen' }).click();
  await expect(reopen).toBeHidden();
  await expect(page.getByText('Open', { exact: true }).first()).toBeVisible();

  await setLangAnd(page, 'en', quarter);
  await page.getByRole('button', { name: 'Mark quarter ready for review' }).click();
  await page.getByRole('dialog').getByLabel('Explanation').fill('Worksheet checked with the adviser');
  await check(page, 'en', 'vat-ready-dialog');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  await setLangAnd(page, 'nl', quarter);
  const ready = page.getByRole('button', { name: 'Kwartaal klaarzetten voor controle' });
  await ready.click();
  await page.getByRole('dialog').getByLabel('Toelichting').fill('Werkblad gecontroleerd met de adviseur');
  await check(page, 'nl', 'vat-ready-dialog');
  await page.getByRole('dialog').getByRole('button', { name: 'Kwartaal klaarzetten voor controle' }).click();
  await expect(page.getByText('Klaargezet door Bram Demo.')).toBeVisible();

  // Wie klaarzette, legt de aangifte niet zelf vast: dat doet een tweede persoon.
  await page.getByRole('button', { name: 'Ingediende aangifte vastleggen' }).click();
  const file = page.getByRole('dialog');
  await file.getByLabel('Referentie van de Belastingdienst').fill('BD-2026-Q3-0042');
  await file.getByLabel('Toelichting').fill('Ingediend in het portaal');
  await file.getByRole('button', { name: 'Ingediende aangifte vastleggen' }).click();
  await expect(file.getByRole('alert')).toContainText('Jij hebt dit kwartaal klaargezet. Een collega legt de ingediende aangifte vast.');
  await check(page, 'nl', 'vat-second-person');
  await file.getByRole('button', { name: 'Annuleren' }).click();
  await setLangAnd(page, 'en', quarter);
  await page.getByRole('button', { name: 'Record filed return' }).click();
  await file.getByLabel('Tax office reference').fill('BD-2026-Q3-0042');
  await file.getByLabel('Explanation').fill('Filed in the portal');
  await file.getByRole('button', { name: 'Record filed return' }).click();
  await expect(file.getByRole('alert')).toContainText('You prepared this quarter. A colleague records the filed return.');
  await check(page, 'en', 'vat-second-person');
  await file.getByRole('button', { name: 'Cancel' }).click();
  await setLang(page, 'nl');

  // Ana legt hem vast; daarna staat het kwartaal op "ingediend".
  const ana = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'nl-NL', timezoneId: 'Europe/Amsterdam' });
  const other = await ana.newPage();
  await other.goto(`${baseUrl}/app`);
  await other.locator('#token').fill(token('ana'));
  await other.locator('#login-submit').click();
  await expect(other.getByRole('heading', { level: 1, name: /^Welkom, / })).toBeVisible();
  const otherQuarter = async (lang: Lang) => {
    await go(other, 'vat', lang);
    await openRow(other, /Q3 2026/);
    await expect(other.getByRole('heading', { level: 1, name: fill(TEXTS[lang].vat.title, { quarter: 'Q3 2026' }) })).toBeVisible();
  };
  await switchLang(other, 'en');
  await otherQuarter('en');
  await other.getByRole('button', { name: 'Record filed return' }).click();
  await other.getByRole('dialog').getByLabel('Tax office reference').fill('BD-2026-Q3-0042');
  await capture(other, 'en-vat-file-dialog');
  await other.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  await switchLang(other, 'nl');
  await otherQuarter('nl');
  await other.getByRole('button', { name: 'Ingediende aangifte vastleggen' }).click();
  const dialog = other.getByRole('dialog');
  await expect(dialog.getByLabel('Aangegeven bedrag')).not.toHaveValue('');
  await dialog.getByLabel('Referentie van de Belastingdienst').fill('BD-2026-Q3-0042');
  await dialog.getByLabel('Toelichting').fill('Ingediend in het portaal van de Belastingdienst');
  await capture(other, 'nl-vat-file-dialog');
  await dialog.getByRole('button', { name: 'Ingediende aangifte vastleggen' }).click();
  await expect(other.getByText(/Aangegeven op .* door Ana Demo, referentie BD-2026-Q3-0042/)).toBeVisible();
  await capture(other, 'nl-vat-quarter-filed');
  await ana.close();

  await page.reload();
  await login(page, 'bram');
  await setLang(page, 'en');
  await nav(page, 'VAT', 'en');
  await check(page, 'en', 'vat');
  await openRow(page, /Q3 2026/);
  await expect(page.getByText(/Filed on .* by Ana Demo/)).toBeVisible();
  await check(page, 'en', 'vat-quarter-filed');
});

/**
 * Los botones de color (la accion principal) que se ven en la tarjeta de importar: tiene que
 * haber uno como mucho. Se mira el color de fondo de cada boton contra el de --primary.
 * (Antes de esta comprobacion, despues de probar salian dos: la prueba y la de verdad.)
 */
async function primaryActions(page: Page): Promise<string[]> {
  // Sin el raton encima (hover:bg-primary/90) y sin un cambio de color a medias.
  await page.mouse.move(0, 0);
  await settled(page);
  return page.locator('section[aria-labelledby="import-form"] button').evaluateAll((buttons) => {
    const hex = getComputedStyle(document.documentElement).getPropertyValue('--primary').trim();
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    const primary = `rgb(${r}, ${g}, ${b})`;
    return buttons
      .filter((el) => el.getBoundingClientRect().width > 0 && getComputedStyle(el).backgroundColor === primary)
      .map((el) => el.textContent?.trim() ?? '');
  });
}

test('importeren: eerst een proef die niets bewaart, daarna echt', async ({ page, baseUrl, request, watch }) => {
  watch.expectHttpErrors(400);
  const clients = async () =>
    ((await (await request.get(`${baseUrl}/api/v2/clientes`, { headers: { 'X-BMS-Token': token('ana') } })).json()) as {
      clientes: { nombre: string }[];
    }).clientes;
  const before = await clients();
  expect(before.map((c) => c.nombre)).not.toContain('Demo Nieuwbouw BV');

  // Lo que manda la app a POST /api/v2/importar: la importacion de verdad, lo mismo que la proef.
  const posts: { simular: boolean; exportado?: string; fuente?: string; tipo?: string }[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && new URL(r.url()).pathname === '/api/v2/importar') posts.push(JSON.parse(r.postData() ?? '{}'));
  });
  await signIn(page, baseUrl);
  // Eerst in het Engels, zonder iets te bewaren: wat niet herkend wordt, de proef en de
  // bevestiging (het idioma se cambia en Ajustes y al volver la pantalla empieza de nuevo).
  await setLang(page, 'en');
  await go(page, 'import', 'en');
  await page.locator('input[type="file"]').setInputFiles(process.env.BMS_E2E_FILE_ODD!);
  await page.getByRole('button', { name: 'Try first' }).click();
  await expect(page.getByTestId('import-error')).toContainText('This file is not recognised');
  await check(page, 'en', 'import-not-recognised');
  await page.locator('input[type="file"]').setInputFiles(process.env.BMS_E2E_FILE_CLIENTS!);
  await page.getByRole('button', { name: 'Try first' }).click();
  await expect(page.getByTestId('import-result')).toContainText('What would happen');
  expect(await primaryActions(page)).toEqual(['Import for real']);
  await check(page, 'en', 'import-preview');
  // Echt importeren vraagt een eigen bevestiging.
  await page.getByRole('button', { name: 'Import for real' }).click();
  await expect(page.getByRole('dialog')).toContainText('exact-debiteuren-nieuw.csv');
  await check(page, 'en', 'import-confirm');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  expect((await clients()).length).toBe(before.length);
  await setLang(page, 'nl');
  posts.length = 0;

  await nav(page, 'Importeren');
  await expect(page.getByRole('heading', { level: 2, name: 'Hoe vers zijn de gegevens' })).toBeVisible();
  await check(page, 'nl', 'import');
  // Una sola accion principal en cada momento: antes de probar, la prueba.
  expect(await primaryActions(page)).toEqual(['Eerst proberen']);

  // Een bestand dat geen export is: het zegt het in gewone woorden.
  await page.locator('input[type="file"]').setInputFiles(process.env.BMS_E2E_FILE_ODD!);
  await expect(page.getByTestId('import-file')).toContainText('notities.txt');
  await page.getByRole('button', { name: 'Eerst proberen' }).click();
  await expect(page.getByTestId('import-error')).toContainText('Dit bestand wordt niet herkend');
  // De technische details: alleen de status en de code, niet de Spaanse zin van de server.
  await page.getByTestId('import-error').getByText('Technische details').click();
  await expect(page.getByTestId('import-error').locator('details p')).toHaveText('400 fichero_no_reconocido');
  await check(page, 'nl', 'import-not-recognised');
  await page.getByTestId('import-error').getByText('Technische details').click();

  // De debiteuren uit Exact met één nieuwe klant: de proef zegt wat er zou gebeuren...
  await page.locator('input[type="file"]').setInputFiles(process.env.BMS_E2E_FILE_CLIENTS!);
  expect(await primaryActions(page)).toEqual(['Eerst proberen']);
  await page.getByRole('button', { name: 'Eerst proberen' }).click();
  const result = page.getByTestId('import-result');
  await expect(result).toContainText('Wat er zou gebeuren');
  // Despues de la prueba, la principal es importar de verdad; la prueba pasa a secundaria.
  expect(await primaryActions(page)).toEqual(['Nu echt importeren']);
  await expect(result).toContainText('Herkend als: Exact · Klanten.');
  await expect(result).toContainText('1 nieuw');
  await expect(result).toContainText('1 nieuwe bankrekening');
  await check(page, 'nl', 'import-preview');
  // ... en bewaart niets.
  expect((await clients()).length).toBe(before.length);
  // Een andere exportdatum na de proef: de proef geldt niet meer, er is geen knop om echt te
  // importeren, en na een nieuwe proef gaat precies dat mee.
  const exportedField = page.locator('#import-exported');
  const previewedDay = await exportedField.inputValue();
  await exportedField.fill('01-01-2020');
  await expect(result).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Nu echt importeren' })).toHaveCount(0);
  expect(await primaryActions(page)).toEqual(['Eerst proberen']);
  await exportedField.fill(previewedDay);
  await page.getByRole('button', { name: 'Eerst proberen' }).click();
  await expect(result).toContainText('Wat er zou gebeuren');
  const preview = posts.at(-1)!;
  expect(preview.simular).toBe(true);
  await page.getByRole('button', { name: 'Nu echt importeren' }).click();
  await expect(page.getByRole('dialog')).toContainText('exact-debiteuren-nieuw.csv');
  await check(page, 'nl', 'import-confirm');
  await page.getByRole('dialog').getByRole('button', { name: 'Nu echt importeren' }).click();
  await expect(result).toContainText('Ingelezen. De lijsten en controles zijn bijgewerkt.');
  // Ya importado: nada en color (lo dice el texto; "Ander bestand" es secundario).
  expect(await primaryActions(page)).toEqual([]);
  expect(posts.at(-1)).toMatchObject({ simular: false, exportado: preview.exportado, fuente: 'exact', tipo: 'clientes' });
  await check(page, 'nl', 'import-done');
  expect((await clients()).map((c) => c.nombre)).toContain('Demo Nieuwbouw BV');

  // De geschiedenis zegt wie wat inlas; hetzelfde bestand nog eens verandert niets.
  await page.getByRole('button', { name: /^Laatste imports/ }).click();
  const historyRow = page.getByRole('cell', { name: 'exact-debiteuren-nieuw.csv' }).first();
  await expect(historyRow).toBeVisible();
  await historyRow.scrollIntoViewIfNeeded();
  await check(page, 'nl', 'import-history');
  await page.getByRole('button', { name: 'Ander bestand' }).click();
  await page.locator('input[type="file"]').setInputFiles(process.env.BMS_E2E_FILE_CLIENTS!);
  await page.getByRole('button', { name: 'Eerst proberen' }).click();
  await expect(result).toContainText('Dit bestand is al eerder ingelezen');
  // Con la prueba no entraria nada: tampoco hay principal (ni se ofrece importar).
  expect(await primaryActions(page)).toEqual([]);
  // In het Engels: het scherm en de geschiedenis met de import.
  await setLangAnd(page, 'en', (lang) => go(page, 'import', lang));
  await check(page, 'en', 'import');
  await page.getByRole('button', { name: /^Recent imports/ }).click();
  await expect(page.getByRole('cell', { name: 'exact-debiteuren-nieuw.csv' }).first()).toBeVisible();
  await check(page, 'en', 'import-history');

  // De nieuwe klant staat in de lijst.
  await nav(page, 'Clients', 'en');
  await expect(page.getByRole('table')).toContainText('Demo Nieuwbouw BV');
});

test('facturen lezen: wat het kost en hoe je het start, zonder knop die het start', async ({ page, baseUrl, request }) => {
  await signIn(page, baseUrl);
  await nav(page, 'Facturen lezen');
  // Como se empieza: con el nombre de verdad del acceso directo y del .bat (revision del paso
  // 16: solo el castellano los nombraba, y la oficina en neerlandes es la que mas los necesita).
  // En el disco se llaman asi, en castellano: van marcados como nombre propio, no son restos.
  await expect(page.getByText(/met de snelkoppeling «BMS Finanzas - Leer facturas» op het bureaublad/)).toBeVisible();
  await expect(page.locator('[data-proper-name]').filter({ hasText: 'BMS Finanzas - Leer facturas' })).toHaveCount(1);
  await expect(page.locator('[data-proper-name]').filter({ hasText: 'leer-facturas.bat' })).toHaveCount(1);
  await expect(page.getByText('Deze app heeft bewust geen internet')).toBeVisible();
  // Cuantos se han leido depende del dia en que se crea la base de prueba (16 el 19-10-2026, 17
  // el 27-10-2026): lo que diga la API, tal cual.
  const reading = (await (await request.get(`${baseUrl}/api/v2/lectura`, { headers: { 'X-BMS-Token': token('ana') } })).json()) as {
    lectura: { documentos: number };
  };
  expect(reading.lectura.documentos).toBeGreaterThan(1);
  await expect(page.getByText(new RegExp(`\\b${reading.lectura.documentos} documenten`))).toBeVisible();
  // Geen knop die het lezen start: in het scherm staan alleen de plooibare uitleg en tabellen.
  // Se llega desde Verwerken en la rueda (paso 17), y las migas dicen donde se esta.
  await expect(page.getByRole('main').getByRole('button', { name: /lezen|lees|start|read/i })).toHaveCount(0);
  expect(await crumbs(page)).toEqual(['Facturen lezen']);
  await check(page, 'nl', 'read-invoices');
  await setLangAnd(page, 'en', (lang) => go(page, 'read-invoices', lang));
  await expect(page.getByText('This app has no internet on purpose')).toBeVisible();
  await check(page, 'en', 'read-invoices');
});

test('instellingen: wie je bent, het bedrijf, de afscherming en de personen (alleen voor de beheerder)', async ({
  page,
  baseUrl,
}) => {
  // Ajustes es el panel E2-A (paso 17): Jouw account, Systeem (Bedrijf, Afscherming, Personen y
  // Back-ups), con la tarjeta .detail de Aurora.
  await signIn(page, baseUrl);
  const s = TEXTS.nl.aurora.settings;
  await openSettingsRowHere(page, 'account', 'nl');
  await expect(panelRow(page, s.account)).toContainText(TEXTS.nl.account.roleAdmin);
  const card = panel(page).locator('.detail');
  await expect(card).toContainText(`${TEXTS.nl.settings.role}: `);
  await expect(card).toContainText(/Wat je mag doen: \d+/);
  await expect(card.getByText('Facturen bekijken', { exact: true })).toBeVisible();
  await check(page, 'nl', 'settings');
  await openSettingsRowHere(page, 'system', 'nl');
  await panelRow(page, s.systemRows.company).click();
  await expect(card).toContainText('NL999900001B01');
  await check(page, 'nl', 'settings-company');
  await panelRow(page, s.systemRows.isolation).click();
  await expect(card).toContainText(TEXTS.nl.settings.isolationTitle);
  await panelRow(page, s.systemRows.people).click();
  await expect(panelRow(page, 'Cas Consulta')).toBeVisible();
  await check(page, 'nl', 'settings-people');
  await setLang(page, 'en');
  await openSettingsRowHere(page, 'account', 'en');
  await expect(panel(page).locator('.detail')).toContainText(`${TEXTS.en.settings.role}: `);
  await expect(panelRow(page, TEXTS.en.aurora.settings.account)).toContainText(TEXTS.en.account.roleAdmin);
  await check(page, 'en', 'settings');
});

test('wie alleen mag kijken: geen importeren, geen btw-knoppen, geen personenlijst', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'cas');
  // Verwerken (Facturen lezen) no sale en la rueda: siete entradas; Importeren tampoco en el panel.
  await openMenu(page);
  await expect(page.locator('.navigation .nav-item')).toHaveCount(ENTRIES.length - 1);
  await expect(entryButton(page, 'process')).toHaveCount(0);
  await openEntry(page, 'receivables');
  await expect(panelRow(page, TEXTS.nl.nav.import.label)).toHaveCount(0);
  const quarter = async (lang: Lang) => {
    await go(page, 'vat', lang);
    await openRow(page, /Q4 2026/);
    await expect(page.getByRole('heading', { level: 1, name: fill(TEXTS[lang].vat.title, { quarter: 'Q4 2026' }) })).toBeVisible();
  };
  await quarter('nl');
  await expect(page.getByRole('button', { name: /klaarzetten|heropenen|vastleggen/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Werkblad downloaden' })).toBeVisible();
  await check(page, 'nl', 'vat-quarter-read-only');
  await setLangAnd(page, 'en', quarter);
  await expect(page.getByRole('button', { name: /ready|reopen|record/i })).toHaveCount(0);
  await check(page, 'en', 'vat-quarter-read-only');
  await setLang(page, 'nl');
  const s = TEXTS.nl.aurora.settings;
  await openSettingsRowHere(page, 'account', 'nl');
  await expect(panelRow(page, s.account)).toContainText(TEXTS.nl.account.roleReadOnly);
  await openSettingsRowHere(page, 'system', 'nl');
  await expect(panelRow(page, s.systemRows.company)).toBeVisible();
  await expect(panelRow(page, s.systemRows.people)).toHaveCount(0);
});

test('op 1024 px blijven de nieuwe schermen bruikbaar', async ({ page, baseUrl }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await signIn(page, baseUrl);
  await nav(page, 'Leveranciers');
  await openRow(page, /J\. Voorbeeld Beveiliging/);
  await expect(page.getByRole('heading', { level: 1, name: 'J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
  // Geen horizontale schuifbalk op de pagina.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await capture(page, 'nl-provider-1024');
  await nav(page, 'Objecten');
  // Waarom cabe sin desplazar la tabla (la columna de kosten se deja a esta anchura).
  expect(await tableFits(page)).toBe(true);
  await capture(page, 'nl-objects-1024');
  await nav(page, 'Inkooporders');
  expect(await tableFits(page)).toBe(true);
  await capture(page, 'nl-purchase-orders-1024');
  await nav(page, 'Btw');
  await openRow(page, /Q4 2026/);
  await capture(page, 'nl-vat-quarter-1024');
  await nav(page, 'Importeren');
  await capture(page, 'nl-import-1024');
  await nav(page, 'Kasstroom');
  await capture(page, 'nl-cash-flow-1024');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
