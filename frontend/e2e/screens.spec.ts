// El resto de pantallas (paso 15, B2) sobre la base de prueba: las fichas de proveedor,
// cliente, Object, PO, trimestre del btw y factura en neerlandes y en ingles; la caja con su
// estimacion aparte; el btw con la descarga del werkblad y sus estados (la aangifte la
// anota una persona, el programa no presenta nada); importar primero como proef y despues de
// verdad; la lectura de los pdf sin ningun boton que la lance; y la configuracion. En cada
// pantalla: solo 127.0.0.1, ninguna violacion de la CSP ni error en la consola (fixtures),
// axe sin nada serio y ninguna palabra en castellano. Captura de cada una como
// <idioma>-<pantalla>.png en CAPTURAS_DIR.
import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { capture, expect, expectAccessible, expectNoSpanish, login, settled, test, token, type Who } from './fixtures';

type Lang = 'nl' | 'en';
const MENU = { nl: 'Hoofdmenu', en: 'Main menu' } as const;

async function signIn(page: Page, baseUrl: string, who: Who = 'ana') {
  await page.goto(`${baseUrl}/app`);
  await login(page, who);
}

async function setLang(page: Page, lang: Lang) {
  await page.getByRole('button', { name: lang === 'nl' ? 'Nederlands' : 'English' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('lang', lang);
  // Los textos de la navegacion entran con un fundido: axe mide el contraste al final.
  await settled(page);
}

async function nav(page: Page, label: string, lang: Lang = 'nl') {
  await page.getByRole('navigation', { name: MENU[lang] }).getByRole('button', { name: new RegExp(`^${label}`) }).click();
  await expect(page.getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
  // Ir a una pestana ya abierta la vuelve a pintar con un fundido (150 ms).
  await settled(page);
}

/** Lo que se mira en cada pantalla, y su captura. */
async function check(page: Page, lang: Lang, screen: string) {
  await expectAccessible(page, `${lang} ${screen}`);
  await expectNoSpanish(page, `${lang} ${screen}`);
  await capture(page, `${lang}-${screen}`);
}

/** Vuelve arriba en la pestana (la captura de una ficha empieza por lo que es). */
async function toTop(page: Page) {
  await page.locator('#tab-panel').evaluate((el) => el.scrollTo(0, 0));
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
  await expect(page.getByRole('tab', { selected: true })).toContainText('J. Voorbeeld');
  await expect(page.getByRole('heading', { level: 3, name: 'Factuurnummer dubbel' }).first()).toBeVisible();
  await check(page, 'nl', 'provider');
  await page.getByRole('button', { name: /^Bankrekeningen/ }).click();
  await expect(page.getByText('Telefoon voor controle: 06-55500102')).toBeVisible();
  await page.getByRole('button', { name: /^Alle facturen/ }).click();
  await check(page, 'nl', 'provider-details');
  await setLang(page, 'en');
  await expect(page.getByRole('heading', { level: 3, name: 'Invoice number used twice' }).first()).toBeVisible();
  await page.getByRole('button', { name: /^All invoices/ }).scrollIntoViewIfNeeded();
  await check(page, 'en', 'provider-details');
  await toTop(page);
  await check(page, 'en', 'provider');
  // Een melding opent haar factuur in een eigen tabblad.
  await page.getByRole('button', { name: 'Open invoice JV-2026-006' }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: /JV-2026-006$/ })).toBeVisible();
  await check(page, 'en', 'invoice');
  await setLang(page, 'nl');
  await check(page, 'nl', 'invoice');

  // Klant: wat nog gefactureerd moet worden (V6) staat bovenaan.
  await nav(page, 'Klanten');
  await check(page, 'nl', 'clients');
  await openRow(page, /Demo Havenbedrijf/);
  await expect(page.getByRole('heading', { level: 1, name: 'Demo Havenbedrijf BV' })).toBeVisible();
  await expect(page.getByText('Nog te factureren', { exact: true })).toBeVisible();
  await check(page, 'nl', 'client');
  await setLang(page, 'en');
  await expect(page.getByText('Not yet invoiced', { exact: true })).toBeVisible();
  await check(page, 'en', 'client');
  await setLang(page, 'nl');

  // Object: opbrengst en marge per periode, uren gepland tegenover gefactureerd.
  await nav(page, 'Objecten');
  await check(page, 'nl', 'objects');
  await openRow(page, /HAVEN-NOORD/);
  await expect(page.getByRole('heading', { level: 1, name: 'Haventerrein Demo-Noord' })).toBeVisible();
  await expect(page.getByRole('tab', { selected: true })).toContainText('HAVEN-NOORD');
  await check(page, 'nl', 'object');
  await page.getByRole('button', { name: 'Dit jaar' }).click();
  await expect(page.getByRole('button', { name: 'Dit jaar' })).toHaveAttribute('aria-pressed', 'true');
  await setLang(page, 'en');
  await check(page, 'en', 'object');
  await page.getByRole('button', { name: /^Hours per week/ }).click();
  await expect(page.getByRole('columnheader', { name: 'Not yet invoiced' })).toBeVisible();
  await check(page, 'en', 'object-details');
  await setLang(page, 'nl');
  await expect(page.getByRole('columnheader', { name: 'Nog niet gefactureerd' })).toBeVisible();
  await check(page, 'nl', 'object-details');

  // Inkooporder: waarde, verbruikt, over en de verwachting.
  await nav(page, 'Inkooporders');
  await check(page, 'nl', 'purchase-orders');
  await openRow(page, /PO-DEMO-4501/);
  await expect(page.getByRole('heading', { level: 1, name: 'PO-DEMO-4501' })).toBeVisible();
  await expect(page.getByText('Verwachting', { exact: true })).toBeVisible();
  await check(page, 'nl', 'purchase-order');
  await setLang(page, 'en');
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

test('kasstroom: één tabel en de schatting uit de planning apart', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await nav(page, 'Kasstroom');
  const table = page.getByRole('table');
  for (const period of ['Al vervallen', 'Deze week', 'Rest van deze maand', 'Komende 30 dagen', 'Alles wat openstaat']) {
    await expect(table.getByText(period, { exact: true })).toBeVisible();
  }
  await expect(page.getByText('Schatting · geen facturen')).toBeVisible();
  await expect(page.locator('canvas, svg[role="img"]')).toHaveCount(0);
  await check(page, 'nl', 'cash-flow');
  await setLang(page, 'en');
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
  await expect(page.getByRole('tab', { selected: true })).toContainText('Btw Q3 2026');
  await check(page, 'nl', 'vat-quarter');
  // Dezelfde stappen in het Engels: elk dialoogvenster bekijken en annuleren.
  await setLang(page, 'en');
  await check(page, 'en', 'vat-quarter');
  await page.getByRole('button', { name: 'Reopen quarter' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await check(page, 'en', 'vat-reopen-dialog');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  await setLang(page, 'nl');

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

  await setLang(page, 'en');
  await page.getByRole('button', { name: 'Mark quarter ready for review' }).click();
  await page.getByRole('dialog').getByLabel('Explanation').fill('Worksheet checked with the adviser');
  await check(page, 'en', 'vat-ready-dialog');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  await setLang(page, 'nl');
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
  await setLang(page, 'en');
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
  await nav(other, 'Btw');
  await openRow(other, /Q3 2026/);
  await setLang(other, 'en');
  await other.getByRole('button', { name: 'Record filed return' }).click();
  await other.getByRole('dialog').getByLabel('Tax office reference').fill('BD-2026-Q3-0042');
  await capture(other, 'en-vat-file-dialog');
  await other.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  await setLang(other, 'nl');
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
  await setLang(page, 'en');
  await expect(page.getByTestId('import-error')).toContainText('This file is not recognised');
  await check(page, 'en', 'import-not-recognised');
  await setLang(page, 'nl');

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
  await setLang(page, 'en');
  await expect(result).toContainText('What would happen');
  expect(await primaryActions(page)).toEqual(['Import for real']);
  await check(page, 'en', 'import-preview');

  // Echt importeren vraagt een eigen bevestiging.
  await page.getByRole('button', { name: 'Import for real' }).click();
  await expect(page.getByRole('dialog')).toContainText('exact-debiteuren-nieuw.csv');
  await check(page, 'en', 'import-confirm');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  await setLang(page, 'nl');
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
  await setLang(page, 'en');
  await expect(result).toContainText('Imported. Lists and checks are up to date.');
  await check(page, 'en', 'import-done');

  // De geschiedenis zegt wie wat inlas; hetzelfde bestand nog eens verandert niets.
  await page.getByRole('button', { name: /^Recent imports/ }).click();
  const historyRow = page.getByRole('cell', { name: 'exact-debiteuren-nieuw.csv' }).first();
  await expect(historyRow).toBeVisible();
  await historyRow.scrollIntoViewIfNeeded();
  await check(page, 'en', 'import-history');
  await setLang(page, 'nl');
  await historyRow.scrollIntoViewIfNeeded();
  await check(page, 'nl', 'import-history');
  await page.getByRole('button', { name: 'Ander bestand' }).click();
  await page.locator('input[type="file"]').setInputFiles(process.env.BMS_E2E_FILE_CLIENTS!);
  await page.getByRole('button', { name: 'Eerst proberen' }).click();
  await expect(result).toContainText('Dit bestand is al eerder ingelezen');
  // Con la prueba no entraria nada: tampoco hay principal (ni se ofrece importar).
  expect(await primaryActions(page)).toEqual([]);
  await setLang(page, 'en');
  await check(page, 'en', 'import');

  // De nieuwe klant staat in de lijst.
  await nav(page, 'Clients', 'en');
  await expect(page.getByRole('table')).toContainText('Demo Nieuwbouw BV');
});

test('facturen lezen: wat het kost en hoe je het start, zonder knop die het start', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await nav(page, 'Facturen lezen');
  // Hoe je het start, zonder de (Spaanse) naam van de snelkoppeling of het .bat-bestand.
  await expect(page.getByText('met de snelkoppeling op het bureaublad voor het lezen van facturen')).toBeVisible();
  await expect(page.getByText(/Finanzas|\.bat\b/)).toHaveCount(0);
  await expect(page.getByText('Deze app heeft bewust geen internet')).toBeVisible();
  await expect(page.getByText(/16 documenten/)).toBeVisible();
  // Geen knop die het lezen start: in de hoofdinhoud staan alleen de plooibare uitleg en tabellen.
  await expect(page.getByRole('main').getByRole('button', { name: /lezen|lees|start|read/i })).toHaveCount(0);
  await check(page, 'nl', 'read-invoices');
  await setLang(page, 'en');
  await expect(page.getByText('This app has no internet on purpose')).toBeVisible();
  await check(page, 'en', 'read-invoices');
});

test('instellingen: wie je bent, het bedrijf, de afscherming en de personen (alleen voor de beheerder)', async ({
  page,
  baseUrl,
}) => {
  await signIn(page, baseUrl);
  await nav(page, 'Instellingen');
  await expect(page.getByText('Rol: Beheerder.')).toBeVisible();
  await page.getByRole('button', { name: /^Wat je mag doen/ }).click();
  await expect(page.getByText('Facturen bekijken', { exact: true })).toBeVisible();
  await expect(page.getByText('NL999900001B01')).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Afscherming' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Personen' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Cas Consulta' })).toBeVisible();
  await check(page, 'nl', 'settings');
  await setLang(page, 'en');
  await expect(page.getByText('Role: Administrator.')).toBeVisible();
  await check(page, 'en', 'settings');
});

test('wie alleen mag kijken: geen importeren, geen btw-knoppen, geen personenlijst', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'cas');
  const menu = page.getByRole('navigation', { name: MENU.nl });
  await expect(menu.getByRole('button', { name: /^Importeren/ })).toHaveCount(0);
  await expect(menu.getByRole('button', { name: /^Facturen lezen/ })).toHaveCount(0);
  await nav(page, 'Btw');
  await openRow(page, /Q4 2026/);
  await expect(page.getByRole('heading', { level: 1, name: 'Btw Q4 2026' })).toBeVisible();
  await expect(page.getByRole('button', { name: /klaarzetten|heropenen|vastleggen/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Werkblad downloaden' })).toBeVisible();
  await check(page, 'nl', 'vat-quarter-read-only');
  await setLang(page, 'en');
  await expect(page.getByRole('button', { name: /ready|reopen|record/i })).toHaveCount(0);
  await check(page, 'en', 'vat-quarter-read-only');
  await setLang(page, 'nl');
  await nav(page, 'Instellingen');
  await expect(page.getByText('Rol: Alleen lezen.')).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Personen' })).toHaveCount(0);
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
