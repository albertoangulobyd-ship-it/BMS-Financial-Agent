// El resto de la app (paso 15, B2; paso 17: en sus portadores de Aurora, especificacion §2.6) sobre
// la base de prueba: las fichas de proveedor y cliente (la ficha de su carpeta en Documentos), la
// hoja de un Object y la de una PO, la del trimestre del IVA (su tarjeta en el panel IVA) y la de
// una factura, en neerlandes, ingles y castellano; la caja de las cuatro semanas con su estimacion
// aparte; el IVA con la descarga de la hoja y sus estados (la declaracion la anota una persona; el
// programa no presenta nada); importar primero como prueba y despues de verdad (dentro de Cuentas
// por cobrar); lo que cuesta leer los PDF y pedir la lectura (Procesar); y Ajustes. En cada
// sitio: solo 127.0.0.1, ninguna violacion de la CSP ni error en la consola (fixtures), axe sin
// nada serio y ningun resto de otro idioma. Captura de cada uno como <idioma>-<sitio>.png.
import { readFileSync } from 'node:fs';
import type { Locator, Page } from '@playwright/test';
import { capture, expect, expectAccessible, expectNoLeftovers, login, settled, test, token, type Who } from './fixtures';
import {
  ENTRIES,
  TEXTS,
  crumbs,
  entryButton,
  fill,
  openCard,
  openDocuments,
  openEntry,
  openFolder,
  openGroup,
  openInvoice,
  openMenu,
  openSettingsRow,
  openSheetRow,
  panel,
  panelRow,
  pickDate,
  profileRow,
  setLang,
  sheetDialog,
  treeItem,
} from './nav';

type Lang = 'nl' | 'en' | 'es';

async function signIn(page: Page, baseUrl: string, who: Who = 'ana') {
  await page.goto(`${baseUrl}/app`);
  await login(page, who);
}

/** Lo que se mira en cada sitio, y su captura. */
async function check(page: Page, lang: Lang, screen: string) {
  await expectAccessible(page, `${lang} ${screen}`);
  await expectNoLeftovers(page, lang, `${lang} ${screen}`);
  await capture(page, `${lang}-${screen}`);
}

const PROVIDER = 'J. Voorbeeld Beveiliging (zzp)';
const CLIENT = 'Demo Havenbedrijf BV';

/** La carpeta de una empresa en Documentos (por el arbol). */
async function folder(page: Page, name: string, side: 'client' | 'provider', lang: Lang): Promise<Locator> {
  await openDocuments(page, lang);
  return openFolder(page, name, side, lang);
}

/** La hoja de una fila de la ficha (un documento, un Object, una PO), en el <dialog>. */
async function sheetOf(page: Page, title: string | RegExp): Promise<Locator> {
  await profileRow(page, title).first().click();
  const sheet = sheetDialog(page);
  await expect(sheet.getByTestId('paper')).toBeVisible();
  await settled(page);
  return sheet;
}

/** La tarjeta de un trimestre en el panel IVA. */
async function quarter(page: Page, label: string, lang: Lang): Promise<Locator> {
  await openEntry(page, 'vat', lang);
  return openCard(page, panelRow(page, label));
}

test('de fiches: leverancier, klant, object, inkooporder en factuur, in NL en EN', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  const t = TEXTS.nl;

  // Leverancier: de ficha de su carpeta, con lo del maestro; la factura repetida en su tabla.
  let profile = await folder(page, PROVIDER, 'provider', 'nl');
  expect(await crumbs(page)).toEqual([t.nav.documents.label, t.documents.providers, PROVIDER]);
  await expect(profile.getByRole('heading', { level: 2 })).toHaveText(PROVIDER);
  await expect(profile).toContainText(t.documents.phone);
  await expect(profile).toContainText('06-55500102');
  await check(page, 'nl', 'provider');
  // La factura de la melding (la repetida, "1 van 2"): su hoja dice por que.
  await profileRow(page, /JV-\d{4}-\d{3}/).filter({ hasText: fill(t.common.twin, { n: 1, of: 2 }) }).click();
  // (B2, el numero repetido, puede estar ya aceptado por daily.spec.ts en la misma base: B4, el
  // periodo dos veces, sigue.)
  await expect(sheetDialog(page).locator('.ws-file-table')).toContainText(/Factuurnummer dubbel|Periode twee keer gefactureerd/);
  await check(page, 'nl', 'invoice');
  await setLang(page, 'en');
  profile = await folder(page, PROVIDER, 'provider', 'en');
  expect(await crumbs(page, 'en')).toEqual(['Documents', 'Providers', PROVIDER]);
  await check(page, 'en', 'provider');
  await profileRow(page, /JV-\d{4}-\d{3}/).filter({ hasText: fill(TEXTS.en.common.twin, { n: 1, of: 2 }) }).click();
  await expect(sheetDialog(page).locator('.ws-file-table')).toContainText(/Invoice number used twice|Period invoiced twice/);
  await check(page, 'en', 'invoice');
  await setLang(page, 'nl');

  // Klant: su ficha, con sus Objects y sus PO en la tabla.
  profile = await folder(page, CLIENT, 'client', 'nl');
  await expect(profile).toContainText(t.documents.paysClient);
  await expect(profileRow(page, `${t.records.object.label} HAVEN-NOORD`)).toBeVisible();
  await expect(profileRow(page, `${t.records['purchase-order'].label} PO-DEMO-4501`)).toBeVisible();
  await check(page, 'nl', 'client');

  // Object: lo que entra, lo que cuesta, el margen y las horas planificadas y facturadas.
  let sheet = await sheetOf(page, `${t.records.object.label} HAVEN-NOORD`);
  await expect(sheet.getByRole('heading', { level: 2 })).toHaveText('HAVEN-NOORD');
  await expect(sheet).toContainText('Haventerrein Demo-Noord');
  for (const label of [t.objects.revenueFact, t.objects.costsFact, t.objects.marginFact, t.objects.hoursFact]) {
    await expect(sheet.getByRole('term').filter({ hasText: label })).toHaveCount(1);
  }
  await check(page, 'nl', 'object');
  await page.keyboard.press('Escape');

  // Inkooporder: waarde, verbruikt, over en de verwachting.
  sheet = await sheetOf(page, `${t.records['purchase-order'].label} PO-DEMO-4501`);
  await expect(sheet.getByRole('heading', { level: 2 })).toHaveText('PO-DEMO-4501');
  await expect(sheet.getByRole('term').filter({ hasText: t.pos.forecast })).toHaveCount(1);
  await check(page, 'nl', 'purchase-order');
  await page.keyboard.press('Escape');

  await setLang(page, 'en');
  await folder(page, CLIENT, 'client', 'en');
  await check(page, 'en', 'client');
  await sheetOf(page, `${TEXTS.en.records.object.label} HAVEN-NOORD`);
  await check(page, 'en', 'object');
  await page.keyboard.press('Escape');
  sheet = await sheetOf(page, `${TEXTS.en.records['purchase-order'].label} PO-DEMO-4501`);
  await expect(sheet.getByRole('term').filter({ hasText: 'Forecast' })).toHaveCount(1);
  await check(page, 'en', 'purchase-order');
  await page.keyboard.press('Escape');
  await setLang(page, 'nl');
});

test('las fichas en castellano: proveedor, cliente, Object, PO, trimestre del IVA, factura y excepcion', async ({ page, baseUrl, request }) => {
  // Revision del paso 16: en castellano salian IVA y BTW, abono y nota de credito, aviso y
  // hallazgo, fichero y archivo y "Esperando a el proveedor". check() mira tambien el glosario.
  const t = TEXTS.es;
  const response = await request.get(`${baseUrl}/api/v2/excepciones`, { headers: { 'X-BMS-Token': token('ana') } });
  const waiting = ((await response.json()) as { excepciones: { id: number; esperando_a: string | null; factura_id: number | null }[] }).excepciones.find(
    (e) => e.esperando_a === 'proveedor'
  )!;
  expect(waiting, 'la base de prueba lleva una excepcion esperando al proveedor').toBeTruthy();
  const invoices = (await (await request.get(`${baseUrl}/api/v2/facturas`, { headers: { 'X-BMS-Token': token('ana') } })).json()) as {
    facturas: { id: number; numero: string | null }[];
  };
  const waitingNumber = invoices.facturas.find((f) => f.id === waiting.factura_id)?.numero ?? '';
  await signIn(page, baseUrl);
  await setLang(page, 'es');

  await folder(page, PROVIDER, 'provider', 'es');
  await check(page, 'es', 'provider');
  await folder(page, CLIENT, 'client', 'es');
  await check(page, 'es', 'client');
  await sheetOf(page, `${t.records.object.label} HAVEN-NOORD`);
  await check(page, 'es', 'object');
  await page.keyboard.press('Escape');
  const po = await sheetOf(page, `${t.records['purchase-order'].label} PO-DEMO-4501`);
  // Un porcentaje, una sola forma (sin espacio, como los textos del motor: "85,95%").
  await expect(po).not.toContainText(/\d[  ]%/);
  await expect(po).toContainText(/\d%/);
  await check(page, 'es', 'purchase-order');
  await page.keyboard.press('Escape');

  const vat = await quarter(page, 'Q3 2026', 'es');
  await expect(vat.getByRole('heading', { level: 3 })).toHaveText(fill(t.vat.title, { quarter: 'Q3 2026' }));
  await check(page, 'es', 'vat-quarter');

  // Una factura de venta con lo leido abierto (IVA en las cifras de la app y del motor).
  await openInvoice(page, 'VD26-306', { lang: 'es' });
  const read = await openSheetRow(page, t.aurora.sheet.read);
  await expect(read).toContainText('IVA');
  await check(page, 'es', 'invoice');

  // La excepcion que espera al proveedor: "Esperando al proveedor", no "a el".
  await openEntry(page, 'home', 'es');
  await openGroup(page, t.nav.exceptions.label);
  // Puede no estar entre las cinco de la vista (las demas pruebas cambian la base): su factura, en
  // el campo de buscar.
  await panel(page).getByRole('textbox', { name: t.aurora.panel.searchPlaceholder }).fill(waitingNumber);
  const card = await openCard(page, panel(page).getByRole('button', { name: fill(t.exceptions.openLabel, { id: waiting.id }) }));
  await expect(card).toContainText('Esperando al proveedor');
  await check(page, 'es', 'exception');
  await setLang(page, 'nl');
});

test('kasstroom: vier weken en de schatting uit de planning apart', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  const t = TEXTS.nl;
  await openEntry(page, 'home');
  await openGroup(page, t.nav['cash-flow'].label);
  // Una fila por semana: lo que entra, lo que sale y lo que queda.
  await expect(panel(page).locator('.doc-list button.doc')).toHaveCount(4);
  await expect(panel(page).locator('.doc-list button.doc').first()).toContainText(t.cash.moneyIn);
  await expect(panel(page).getByTestId('cash-estimate')).toContainText(t.cash.estimateBadge);
  // Sin graficos en el panel.
  await expect(panel(page).locator('canvas, svg[role="img"]')).toHaveCount(0);
  await check(page, 'nl', 'cash-flow');
  // Una semana abre sus facturas en la busqueda (E5-p).
  await panel(page).locator('.doc-list button.doc').first().click();
  await expect(page.locator('.active-filter-chips button')).not.toHaveCount(0);
  await setLang(page, 'en');
  await openEntry(page, 'home', 'en');
  await openGroup(page, TEXTS.en.nav['cash-flow'].label);
  await expect(panel(page).getByTestId('cash-estimate')).toContainText('Estimate · not invoices');
  await check(page, 'en', 'cash-flow');
  await setLang(page, 'nl');
});

test('btw: het werkblad downloaden, klaarzetten en de ingediende aangifte vastleggen (door een tweede persoon)', async ({ page, baseUrl, browser, watch }) => {
  // De tweede persoon: wie klaarzette, krijgt een 403 (segunda_persona) als hij zelf vastlegt.
  watch.expectHttpErrors(403);
  const t = TEXTS.nl;
  const formButton = (card: Locator, label: string) => card.locator('.order-form').getByRole('button', { name: label, exact: true });
  const yes = (card: Locator, label: string) => card.locator('.chat-export').getByRole('button', { name: label, exact: true });
  // Bram zet het kwartaal terug en weer klaar.
  await signIn(page, baseUrl, 'bram');
  await openEntry(page, 'vat');
  await expect(panel(page).getByTestId('balance')).toBeVisible();
  await check(page, 'nl', 'vat');
  let card = await quarter(page, 'Q3 2026', 'nl');
  await expect(card.getByRole('heading', { level: 3 })).toHaveText('Btw Q3 2026');
  await check(page, 'nl', 'vat-quarter');
  // In het Engels: de orden de heropenen bekijken en annuleren.
  await setLang(page, 'en');
  card = await quarter(page, 'Q3 2026', 'en');
  await check(page, 'en', 'vat-quarter');
  await card.getByRole('button', { name: 'Reopen quarter', exact: true }).click();
  await check(page, 'en', 'vat-reopen');
  await card.locator('.order-form').getByRole('button', { name: 'Cancel' }).click();
  await setLang(page, 'nl');
  card = await quarter(page, 'Q3 2026', 'nl');

  // Het werkblad: fetch met de code, als bestand, en de bytes die de hash dragen.
  const [download] = await Promise.all([page.waitForEvent('download'), card.getByRole('button', { name: t.vat.downloadSheet }).click()]);
  expect(download.suggestedFilename()).toBe('btw-2026-T3.csv');
  const sheet = readFileSync((await download.path())!, 'utf8');
  expect(sheet).toContain('2026-T3');
  expect(sheet).toContain('5c;');

  await card.getByRole('button', { name: 'Kwartaal heropenen', exact: true }).click();
  await card.getByLabel(t.vat.explanation).fill('Nog een factuur bekijken');
  await formButton(card, 'Kwartaal heropenen').click();
  await check(page, 'nl', 'vat-reopen');
  await yes(card, 'Kwartaal heropenen').click();
  await expect(panel(page).locator('.success')).toBeVisible();
  await expect(card).toContainText('Open');

  const ready = 'Kwartaal klaarzetten voor controle';
  await card.getByRole('button', { name: ready, exact: true }).click();
  await card.getByLabel(t.vat.explanation).fill('Werkblad gecontroleerd met de adviseur');
  await formButton(card, ready).click();
  await check(page, 'nl', 'vat-ready');
  await yes(card, ready).click();
  await expect(card).toContainText('Klaargezet door Bram Demo.');

  // Wie klaarzette, legt de aangifte niet zelf vast: dat doet een tweede persoon.
  const file = 'Ingediende aangifte vastleggen';
  await card.getByRole('button', { name: file, exact: true }).click();
  await card.getByLabel(t.vat.reference).fill('BD-2026-Q3-0042');
  await card.getByLabel(t.vat.explanation).fill('Ingediend in het portaal');
  await formButton(card, file).click();
  await yes(card, file).click();
  await expect(card.getByRole('alert')).toContainText('Jij hebt dit kwartaal klaargezet. Een collega legt de ingediende aangifte vast.');
  await check(page, 'nl', 'vat-second-person');
  await card.locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  await setLang(page, 'en');
  card = await quarter(page, 'Q3 2026', 'en');
  await card.getByRole('button', { name: 'Record filed return', exact: true }).click();
  await card.getByLabel('Tax office reference').fill('BD-2026-Q3-0042');
  await card.getByLabel('Explanation').fill('Filed in the portal');
  await formButton(card, 'Record filed return').click();
  await yes(card, 'Record filed return').click();
  await expect(card.getByRole('alert')).toContainText('You prepared this quarter. A colleague records the filed return.');
  await check(page, 'en', 'vat-second-person');
  await card.locator('.order-form').getByRole('button', { name: 'Cancel' }).click();
  await setLang(page, 'nl');

  // Ana legt hem vast; daarna staat het kwartaal op "ingediend".
  const ana = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'nl-NL', timezoneId: 'Europe/Amsterdam' });
  const other = await ana.newPage();
  await other.goto(`${baseUrl}/app`);
  await other.locator('#token').fill(token('ana'));
  await other.locator('#login-submit').click();
  await expect(other.getByRole('heading', { level: 1, name: /^Welkom, / })).toBeVisible();
  const otherCard = await quarter(other, 'Q3 2026', 'nl');
  await otherCard.getByRole('button', { name: file, exact: true }).click();
  await expect(otherCard.getByLabel(t.vat.declared)).not.toHaveValue('');
  await otherCard.getByLabel(t.vat.reference).fill('BD-2026-Q3-0042');
  await otherCard.getByLabel(t.vat.explanation).fill('Ingediend in het portaal van de Belastingdienst');
  await capture(other, 'nl-vat-file');
  await formButton(otherCard, file).click();
  await yes(otherCard, file).click();
  await expect(otherCard).toContainText(/Aangegeven op .* door Ana Demo, referentie BD-2026-Q3-0042/);
  await capture(other, 'nl-vat-quarter-filed');
  await ana.close();

  await page.reload();
  await login(page, 'bram');
  await setLang(page, 'en');
  await openEntry(page, 'vat', 'en');
  await check(page, 'en', 'vat');
  card = await quarter(page, 'Q3 2026', 'en');
  await expect(card).toContainText(/Filed on .* by Ana Demo/);
  await check(page, 'en', 'vat-quarter-filed');
  await setLang(page, 'nl');
});

/** Los botones de color (la accion principal) que se ven en el panel: uno como mucho. */
async function primaryActions(page: Page): Promise<string[]> {
  await page.mouse.move(0, 0);
  await settled(page);
  return panel(page)
    .locator('button.primary')
    .evaluateAll((buttons) => buttons.filter((el) => el.getBoundingClientRect().width > 0).map((el) => el.textContent?.trim() ?? ''));
}

/** Importar: dentro de Te ontvangen, su boton. */
async function openImport(page: Page, lang: Lang) {
  await openEntry(page, 'receivables', lang);
  await panel(page).getByRole('button', { name: TEXTS[lang].aurora.money.import }).click();
  await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(TEXTS[lang].nav.import.label);
  await settled(page);
}

test('importeren: eerst een proef die niets bewaart, daarna echt', async ({ page, baseUrl, request, watch }) => {
  watch.expectHttpErrors(400);
  const t = TEXTS.nl;
  const clients = async () =>
    ((await (await request.get(`${baseUrl}/api/v2/clientes`, { headers: { 'X-BMS-Token': token('ana') } })).json()) as { clientes: { nombre: string }[] }).clientes;
  const before = await clients();
  expect(before.map((c) => c.nombre)).not.toContain('Demo Nieuwbouw BV');
  const file = page.locator('aside.panel input[type="file"]');

  // Lo que manda la app a POST /api/v2/importar: la importacion de verdad, lo mismo que la proef.
  const posts: { simular: boolean; exportado?: string; fuente?: string; tipo?: string }[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && new URL(r.url()).pathname === '/api/v2/importar') posts.push(JSON.parse(r.postData() ?? '{}'));
  });
  await signIn(page, baseUrl);
  // Eerst in het Engels, zonder iets te bewaren: wat niet herkend wordt, de proef en de bevestiging.
  await setLang(page, 'en');
  await openImport(page, 'en');
  await file.setInputFiles(process.env.BMS_E2E_FILE_ODD!);
  await panel(page).getByRole('button', { name: 'Try first', exact: true }).click();
  await expect(page.getByTestId('import-error')).toContainText('This file is not recognised');
  await check(page, 'en', 'import-not-recognised');
  await file.setInputFiles(process.env.BMS_E2E_FILE_CLIENTS!);
  await panel(page).getByRole('button', { name: 'Try first', exact: true }).click();
  await expect(page.getByTestId('import-result')).toContainText('What would happen');
  expect(await primaryActions(page)).toEqual(['Import for real']);
  await check(page, 'en', 'import-preview');
  // Echt importeren vraagt een eigen bevestiging.
  await panel(page).getByRole('button', { name: 'Import for real', exact: true }).click();
  await expect(panel(page).locator('.chat-export')).toContainText('exact-debiteuren-nieuw.csv');
  await check(page, 'en', 'import-confirm');
  await panel(page).locator('.chat-export').getByRole('button', { name: 'Cancel' }).click();
  expect((await clients()).length).toBe(before.length);
  await setLang(page, 'nl');
  posts.length = 0;

  await openImport(page, 'nl');
  // Sin fichero: de cuando es cada fuente y las ultimas importaciones, una fila cada una.
  await expect(panelRow(page, t.aurora.import.sources)).toBeVisible();
  await expect(panelRow(page, t.importing.historyTitle)).toBeVisible();
  await check(page, 'nl', 'import');
  await openGroup(page, t.aurora.import.sources);
  await check(page, 'nl', 'import-sources');
  await page.keyboard.press('Escape');

  // Een bestand dat geen export is: het zegt het in gewone woorden, met de code apart.
  await file.setInputFiles(process.env.BMS_E2E_FILE_ODD!);
  await expect(page.getByTestId('import-file')).toContainText('notities.txt');
  expect(await primaryActions(page)).toEqual([t.importing.tryFirst]);
  await panel(page).getByRole('button', { name: t.importing.tryFirst, exact: true }).click();
  await expect(page.getByTestId('import-error')).toContainText('Dit bestand wordt niet herkend');
  // De technische details: alleen de status en de code, niet de Spaanse zin van de server.
  await expect(page.getByTestId('import-error').locator('small')).toHaveText('(400 fichero_no_reconocido)');
  await check(page, 'nl', 'import-not-recognised');

  // De debiteuren uit Exact met één nieuwe klant: de proef zegt wat er zou gebeuren...
  await file.setInputFiles(process.env.BMS_E2E_FILE_CLIENTS!);
  expect(await primaryActions(page)).toEqual([t.importing.tryFirst]);
  await panel(page).getByRole('button', { name: t.importing.tryFirst, exact: true }).click();
  const result = page.getByTestId('import-result');
  await expect(result).toContainText(t.importing.previewTitle);
  // Despues de la prueba, la principal es importar de verdad.
  expect(await primaryActions(page)).toEqual([t.importing.importNow]);
  await expect(result).toContainText('Herkend als: Exact · Klanten.');
  await expect(result).toContainText('1 nieuw');
  await expect(result).toContainText('1 nieuwe bankrekening');
  await check(page, 'nl', 'import-preview');
  // ... en bewaart niets.
  expect((await clients()).length).toBe(before.length);
  // Een andere exportdatum na de proef: de proef geldt niet meer, er is geen knop om echt te
  // importeren, en na een nieuwe proef gaat precies dat mee.
  const first = new Date();
  first.setDate(1);
  await pickDate(page, panel(page), t.importing.exported, first);
  await expect(result).toHaveCount(0);
  await expect(panel(page).getByRole('button', { name: t.importing.importNow, exact: true })).toHaveCount(0);
  expect(await primaryActions(page)).toEqual([t.importing.tryFirst]);
  await panel(page).getByRole('button', { name: t.importing.tryFirst, exact: true }).click();
  await expect(result).toContainText(t.importing.previewTitle);
  const preview = posts.at(-1)!;
  expect(preview.simular).toBe(true);
  await panel(page).getByRole('button', { name: t.importing.importNow, exact: true }).click();
  await expect(panel(page).locator('.chat-export')).toContainText('exact-debiteuren-nieuw.csv');
  await check(page, 'nl', 'import-confirm');
  await panel(page).locator('.chat-export').getByRole('button', { name: t.importing.confirmTitle, exact: true }).click();
  await expect(panel(page).locator('.success')).toContainText(t.importing.done);
  // Ya importado: nada en color ("Ander bestand" es secundario).
  expect(await primaryActions(page)).toEqual([]);
  expect(posts.at(-1)).toMatchObject({ simular: false, exportado: preview.exportado, fuente: 'exact', tipo: 'clientes' });
  await check(page, 'nl', 'import-done');
  expect((await clients()).map((c) => c.nombre)).toContain('Demo Nieuwbouw BV');

  // De geschiedenis zegt wie wat inlas; hetzelfde bestand nog eens verandert niets.
  await panel(page).getByRole('button', { name: t.importing.another }).click();
  await openGroup(page, t.importing.historyTitle);
  await expect(panelRow(page, 'exact-debiteuren-nieuw.csv').first()).toBeVisible();
  await check(page, 'nl', 'import-history');
  await page.keyboard.press('Escape');
  await file.setInputFiles(process.env.BMS_E2E_FILE_CLIENTS!);
  await panel(page).getByRole('button', { name: t.importing.tryFirst, exact: true }).click();
  await expect(result).toContainText(t.importing.repeated);
  // Con la prueba no entraria nada: tampoco hay principal (ni se ofrece importar).
  expect(await primaryActions(page)).toEqual([]);
  // In het Engels: de geschiedenis met de import.
  await setLang(page, 'en');
  await openImport(page, 'en');
  await check(page, 'en', 'import');
  await openGroup(page, TEXTS.en.importing.historyTitle);
  await expect(panelRow(page, 'exact-debiteuren-nieuw.csv').first()).toBeVisible();
  await check(page, 'en', 'import-history');
  await setLang(page, 'nl');

  // De nieuwe klant staat in Documenten.
  await openDocuments(page);
  const clientsNode = treeItem(page, t.documents.clients).first();
  if ((await clientsNode.getAttribute('aria-expanded')) !== 'true') await clientsNode.click();
  await expect(treeItem(page, 'Demo Nieuwbouw BV')).toBeVisible();
});

test('facturen verwerken: wat het kost en hoe je de lezer start; de app vraagt het alleen aan, in NL en EN', async ({ page, baseUrl, request }) => {
  // Verwerken (E7) es Procesar de Aurora (paso 17 B3): la vuelta entera, con el lector de las
  // pruebas, esta en procesar.spec.ts. Aqui, en neerlandes y en ingles: lo que cuesta (sin red),
  // que «Lezen aanvragen» solo pide la lectura (la app no lee ni lanza nada: lo dice, con el
  // nombre de verdad del acceso directo del escritorio) y «Niet lezen» la retira.
  await signIn(page, baseUrl);
  const title = page.locator('.welcome-line h1');
  const line = page.locator('.welcome-line p');
  const flow = page.locator('.processing-workspace .flow-button');
  const note = page.locator('.processing-workspace .processing-demo');
  const live = async () =>
    ((await (await request.get(`${baseUrl}/api/v2/lectura`, { headers: { 'X-BMS-Token': token('ana') } })).json()) as { lectura: { solicitud: { viva: boolean } | null } })
      .lectura.solicitud?.viva ?? false;
  for (const lang of ['nl', 'en'] as const) {
    const p = TEXTS[lang].aurora.process;
    await setLang(page, lang);
    await openEntry(page, 'process', lang);
    // Sin lectura viva: P0, o como acabo la ultima sin leer (P7, P8); el mismo boton y la misma nota.
    await expect(flow).toHaveText(p.request);
    expect([p.ready.title, p.cancelled.title, p.expired.title, p.nothing.title]).toContain(await title.textContent());
    await expect(note).toContainText(lang === 'nl' ? /^Uitgegeven tot nu toe: \$\s\d+,\d{2} · Per factuur tussen \$\s0,\d{3} en \$\s0,\d{3}/ : /^Spent so far: \$\s\d+,\d{2} · Each invoice, between \$\s0,\d{3} and \$\s0,\d{3}/);
    await check(page, lang, 'process-ready');
    // Aanvragen: de app start niets; ze zegt welke snelkoppeling je opent (in het Spaans, zoals
    // op de schijf: een eigennaam, geen rest).
    await flow.click();
    await expect(title).toHaveText(fill(p.requested.title, { readShortcut: 'BMS Finanzas - Leer facturas' }));
    await expect(title.locator('[data-proper-name]')).toHaveText('BMS Finanzas - Leer facturas');
    await expect(line).toHaveText(p.requested.line);
    await expect(flow).toHaveCSS('visibility', 'hidden');
    expect(await live()).toBe(true);
    await check(page, lang, 'process-requested');
    await page.locator('.processing-workspace').getByRole('button', { name: p.notRead, exact: true }).click();
    await expect(title).toHaveText(p.cancelled.title);
    await expect.poll(live).toBe(false);
  }
  await setLang(page, 'nl');
});

test('instellingen: wie je bent, het bedrijf, de afscherming en de personen (alleen voor de beheerder)', async ({ page, baseUrl }) => {
  // Ajustes es el panel E2-A: Jouw account, Systeem (Bedrijf, Afscherming, Personen y Back-ups),
  // con la tarjeta .detail de Aurora.
  await signIn(page, baseUrl);
  const s = TEXTS.nl.aurora.settings;
  await openSettingsRow(page, 'account', 'nl');
  await expect(panelRow(page, s.account)).toContainText(TEXTS.nl.account.roleAdmin);
  const card = panel(page).locator('.detail');
  await expect(card).toContainText(`${TEXTS.nl.settings.role}: `);
  await expect(card).toContainText(/Wat je mag doen: \d+/);
  await expect(card.getByText('Facturen bekijken', { exact: true })).toBeVisible();
  await check(page, 'nl', 'settings');
  await openSettingsRow(page, 'system', 'nl');
  await panelRow(page, s.systemRows.company).click();
  await expect(card).toContainText('NL999900001B01');
  await check(page, 'nl', 'settings-company');
  await panelRow(page, s.systemRows.isolation).click();
  await expect(card).toContainText(TEXTS.nl.settings.isolationTitle);
  await panelRow(page, s.systemRows.people).click();
  await expect(panelRow(page, 'Cas Consulta')).toBeVisible();
  await check(page, 'nl', 'settings-people');
  await setLang(page, 'en');
  await openSettingsRow(page, 'account', 'en');
  await expect(panel(page).locator('.detail')).toContainText(`${TEXTS.en.settings.role}: `);
  await expect(panelRow(page, TEXTS.en.aurora.settings.account)).toContainText(TEXTS.en.account.roleAdmin);
  await check(page, 'en', 'settings');
  await setLang(page, 'nl');
});

test('wie alleen mag kijken: geen importeren, geen btw-knoppen, geen personenlijst', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'cas');
  // Verwerken no sale en la rueda: siete entradas; Importeren tampoco en el panel.
  await openMenu(page);
  await expect(page.locator('.navigation .nav-item')).toHaveCount(ENTRIES.length - 1);
  await expect(entryButton(page, 'process')).toHaveCount(0);
  await openEntry(page, 'receivables');
  await expect(panel(page).getByRole('button', { name: TEXTS.nl.aurora.money.import })).toHaveCount(0);
  let card = await quarter(page, 'Q4 2026', 'nl');
  await expect(card.getByRole('button', { name: /klaarzetten|heropenen|vastleggen/ })).toHaveCount(0);
  await expect(card.getByRole('button', { name: TEXTS.nl.vat.downloadSheet })).toBeVisible();
  await check(page, 'nl', 'vat-quarter-read-only');
  await setLang(page, 'en');
  card = await quarter(page, 'Q4 2026', 'en');
  await expect(card.getByRole('button', { name: /ready|reopen|record/i })).toHaveCount(0);
  await check(page, 'en', 'vat-quarter-read-only');
  await setLang(page, 'nl');
  const s = TEXTS.nl.aurora.settings;
  await openSettingsRow(page, 'account', 'nl');
  await expect(panelRow(page, s.account)).toContainText(TEXTS.nl.account.roleReadOnly);
  await openSettingsRow(page, 'system', 'nl');
  await expect(panelRow(page, s.systemRows.company)).toBeVisible();
  await expect(panelRow(page, s.systemRows.people)).toHaveCount(0);
});

test('op 1024 px blijven de fiches, de panelen en importeren bruikbaar', async ({ page, baseUrl }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await signIn(page, baseUrl);
  const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  await folder(page, PROVIDER, 'provider', 'nl');
  // Geen horizontale schuifbalk op de pagina.
  expect(await fits()).toBe(true);
  await capture(page, 'nl-provider-1024');
  await folder(page, CLIENT, 'client', 'nl');
  await sheetOf(page, `${TEXTS.nl.records.object.label} HAVEN-NOORD`);
  expect(await fits()).toBe(true);
  await capture(page, 'nl-object-1024');
  await page.keyboard.press('Escape');
  await quarter(page, 'Q4 2026', 'nl');
  await capture(page, 'nl-vat-quarter-1024');
  await openImport(page, 'nl');
  await capture(page, 'nl-import-1024');
  await openEntry(page, 'home');
  await openGroup(page, TEXTS.nl.nav['cash-flow'].label);
  await capture(page, 'nl-cash-flow-1024');
  expect(await fits()).toBe(true);
});
