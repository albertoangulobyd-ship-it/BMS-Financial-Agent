// El trabajo diario sobre la base de prueba (paso 17: los paneles y la hoja de Aurora): el panel
// Inicio (E2-I) con lo que pide atencion, "Eerst", la Werklijst, las Uitzonderingen y los IBAN
// por verificar; la hoja de una factura (E6-h, en Documentos) con sus filas y las ordenes de cada
// una en su tarjeta, con su permiso (sin permiso, la tarjeta sin botones). Las pruebas van en
// orden y cambian la base (aceptar, resolver, marcar), asi que cada una mira lo que deja la
// anterior: lo que comprueban son cambios, no cifras sueltas. Se llega a todo como una persona
// (e2e/nav.ts): el orbe, la rueda, la fila del grupo y su tarjeta; una factura, escribiendo su
// numero en la caja. El idioma se cambia en Ajustes. Captura de cada sitio en neerlandes y en
// ingles (CAPTURAS_DIR).
import type { Locator, Page } from '@playwright/test';
import { capture, expect, expectAccessible, login, test, token, type Who } from './fixtures';
import {
  ENTRIES,
  TEXTS,
  answerRow,
  ask,
  detail,
  entryButton,
  fill,
  fillOrder,
  giveOrder,
  invoiceRow,
  openCard,
  openEntry,
  openGroup,
  openInvoice as openSheet,
  openMenu,
  openSheetRow,
  panel,
  panelRow,
  readCount,
  setLang,
  sheetDialog,
  signOut,
  toHome,
  unfold,
} from './nav';

const t = TEXTS.nl;

async function signIn(page: Page, baseUrl: string, who: Who = 'ana') {
  await page.goto(`${baseUrl}/app`);
  await login(page, who);
}

/** Cuantas bloqueadas dice la fila de la Werklijst ("4 geblokkeerd"). */
async function blockedNow(page: Page): Promise<number> {
  await openEntry(page, 'home');
  const state = (await panelRow(page, t.nav['work-queue'].label).locator('.doc-end small').textContent()) ?? '';
  const m = /(\d+)/.exec(state);
  return m ? Number(m[1]) : 0;
}

/** El numero de un grupo del panel Inicio (su fila en reposo). */
async function homeCount(page: Page, label: string): Promise<number> {
  await openEntry(page, 'home');
  await expect(panelRow(page, label)).toBeVisible();
  return readCount(page, label);
}

/** La factura que la base de prueba recibe dos veces (B2): la ultima quincenal de J. Voorbeeld
 *  Beveiliging. Su numero depende del dia en que se crea la base: se lee de la Werklijst, donde
 *  va con "1 van 2". */
async function twinNumber(page: Page): Promise<string> {
  await openEntry(page, 'home');
  await openGroup(page, t.nav['work-queue'].label);
  const row = panel(page).locator('button.doc').filter({ hasText: fill(t.common.twin, { n: 1, of: 2 }) }).first();
  await expect(row).toBeVisible();
  const number = /JV-\d{4}-\d{3}/.exec((await row.textContent()) ?? '')?.[0];
  if (!number) throw new Error('la Werklijst no trae la factura repetida');
  return number;
}

/** La hoja de una factura, entera: con mas de cuatro filas se abre plegada y aqui se despliega
 *  (su control, como una persona), para ver y abrir todas sus filas. */
async function openInvoice(page: Page, number: string, options: { lang?: 'nl' | 'en' | 'es'; nth?: number } = {}): Promise<Locator> {
  const sheet = await openSheet(page, number, options);
  await unfold(page);
  return sheet;
}

/** El veredicto de la hoja: la linea pequena de "Gelezen gegevens". */
const verdictLine = (page: Page, lang: 'nl' | 'en' = 'nl') => invoiceRow(page, TEXTS[lang].aurora.sheet.read).locator('small');

/** La orden primaria del formulario abierto en una tarjeta (la del "si" viene despues). */
const formButton = (card: Locator, label: string) => card.locator('.order-form').getByRole('button', { name: label, exact: true });

test('het begin: wat aandacht vraagt, eerst het geblokkeerde en urgente, in NL en EN', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await openEntry(page, 'home');
  // La cifra principal: cuantas piden a una persona, cuantas bloqueadas y urgentes.
  const balance = panel(page).getByTestId('balance');
  await expect(balance).toContainText(t.aurora.home.attention);
  await expect(balance).toContainText(/\d+ geblokkeerd · \d+ urgent/);
  // Una fila por grupo: Eerst, Werklijst, Uitzonderingen, IBAN te controleren y Kasstroom.
  for (const label of [t.aurora.home.first, t.nav['work-queue'].label, t.nav.exceptions.label, t.aurora.home.iban, t.nav['cash-flow'].label]) {
    await expect(panelRow(page, label)).toBeVisible();
  }
  await expect(panelRow(page, t.nav['work-queue'].label).locator('.doc-end small')).toContainText('geblokkeerd');
  await expectAccessible(page, 'begin nl');
  await capture(page, 'daily-nl-home');

  // Eerst: cinco cosas como mucho, solo bloqueadas o urgentes, las bloqueadas arriba.
  await openGroup(page, t.aurora.home.first);
  const rows = panel(page).locator('.doc-list button.doc');
  await expect(rows).toHaveCount(5);
  await expect(rows.first().locator('.doc-end small')).toHaveText('Geblokkeerd');
  for (const row of await rows.all()) await expect(row.locator('.doc-end small')).toHaveText(/^(Geblokkeerd|Urgent)$/);
  // Cinco cosas distintas: dos facturas con el mismo numero van en una fila, que lo dice.
  const notes = await Promise.all((await rows.all()).map(async (r) => ((await r.locator('strong + small').first().textContent()) ?? '').split(' · ')[0]!));
  expect(new Set(notes).size).toBe(5);
  const twin = rows.filter({ hasText: /JV-\d{4}-\d{3}/ });
  await expect(twin).toHaveCount(1);
  await expect(twin).toContainText(fill(t.overview.nextUp.sameNumber, { n: 2 }));
  // La primera, con por que pide atencion, y su hoja a un clic.
  const card = await openCard(page, rows.first());
  await expect(card).toContainText(fill(t.aurora.card.why, { why: 'Andere valuta dan euro' }));
  await expectAccessible(page, 'eerst nl');
  await capture(page, 'daily-nl-first');

  await setLang(page, 'en');
  await openEntry(page, 'home', 'en');
  await expect(panel(page).getByTestId('balance')).toContainText(TEXTS.en.aurora.home.attention);
  await openGroup(page, TEXTS.en.aurora.home.first);
  const en = await openCard(page, panel(page).locator('.doc-list button.doc').first());
  await expect(en).toContainText(fill(TEXTS.en.aurora.card.why, { why: 'Currency other than euro' }));
  await capture(page, 'daily-en-first');
  // "Open the invoice": su hoja, con el vuelo, en la carpeta de su empresa.
  await en.getByRole('button', { name: TEXTS.en.aurora.card.openInvoice }).click();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('DGG-2026-118');
  await setLang(page, 'nl');

  // "Vervallen" en Te ontvangen: la busqueda con sus filtros (E5-p), con la vencida de prueba.
  await openEntry(page, 'receivables');
  await panelRow(page, t.aurora.money.overdue).click();
  await expect(page.locator('.active-filter-chips')).toBeVisible();
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByRole('region', { name: t.aurora.search.resultsLabel })).toContainText('VD26-306');
});

test('de geblokkeerde facturen zeggen waarom, in het Nederlands en het Engels', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await openEntry(page, 'home');
  await openGroup(page, t.nav['work-queue'].label);
  // De dringendste bovenaan: de vier geblokkeerde, en de twee met hetzelfde nummer te onderscheiden.
  const rows = panel(page).locator('.doc-list button.doc');
  for (let i = 0; i < 4; i += 1) await expect(rows.nth(i).locator('.doc-end small')).toHaveText('Geblokkeerd');
  await expect(panel(page)).toContainText(fill(t.common.twin, { n: 1, of: 2 }));
  await expect(panel(page)).toContainText(fill(t.common.twin, { n: 2, of: 2 }));
  // Geen Spaans van de API.
  await expect(panel(page)).not.toContainText('Importes en USD');
  await expectAccessible(page, 'werklijst nl');
  await capture(page, 'daily-nl-work-queue');

  // De factuur zelf: wat het is, wat er mis is en wat te doen.
  await openInvoice(page, 'DGG-2026-118');
  await expect(verdictLine(page)).toContainText('Bezwaren van het systeem: 2');
  const card = await openSheetRow(page, 'Andere valuta dan euro');
  await expect(card).toContainText('Bedragen in USD: niet in euro, daarom buiten alle totalen.');
  await expect(card).toContainText(t.invoice.whatToDo);
  await expectAccessible(page, 'factuur nl');
  await capture(page, 'daily-nl-invoice-blocked');
  // Het IBAN dat niet in het register staat, op de factuur van Proefwacht.
  await openInvoice(page, 'PW2609-01');
  await expect(sheetDialog(page).locator('.ws-file-table')).toContainText('IBAN');
  const iban = await openSheetRow(page, /IBAN/);
  await expect(iban).toContainText('NL37 DEMO 0009 9903 01 staat niet in het rekeningregister van deze leverancier.');

  await setLang(page, 'en');
  await openInvoice(page, 'DGG-2026-118', { lang: 'en' });
  await expect(verdictLine(page, 'en')).toContainText('System objections: 2');
  const en = await openSheetRow(page, 'Currency other than euro');
  await expect(en).toContainText('Amounts in USD: not in euros, so left out of all totals.');
  await expect(en).toContainText('Check the currency and get a version in euros');
  await expectAccessible(page, 'factuur en');
  await capture(page, 'daily-en-invoice-blocked');
  await openEntry(page, 'home', 'en');
  await openGroup(page, TEXTS.en.nav['work-queue'].label);
  await expect(panel(page).locator('.doc-list button.doc').first().locator('.doc-end small')).toHaveText('Blocked');
  await capture(page, 'daily-en-work-queue');
  await setLang(page, 'nl');
});

test('accepteren vraagt een tweede persoon; met die handtekening gaat het en de tellingen veranderen', async ({ page, baseUrl, watch }) => {
  watch.expectHttpErrors(403);
  await signIn(page, baseUrl, 'ana');
  const blockedBefore = await blockedNow(page);
  const twin = await twinNumber(page);
  const title = 'Factuurnummer dubbel';
  await openInvoice(page, twin);
  let card = await openSheetRow(page, title);
  await card.getByRole('button', { name: t.invoice.accept, exact: true }).click();
  // De regel van de twee personen: zonder de handtekening van een collega kan het niet. De app
  // zegt het en laat niet versturen wat de server toch zou weigeren.
  await expect(card.getByTestId('action-blocked')).toContainText('Vraag een collega met dezelfde bevoegdheid om “Tweede handtekening geven”');
  await expect(formButton(card, t.invoice.accept)).toBeDisabled();
  await card.getByLabel(t.action.reason).fill('Twee keer dezelfde factuur ontvangen; de leverancier heeft het bevestigd.');
  await expectAccessible(page, 'tweede persoon');
  await capture(page, 'daily-nl-accept-second-person');
  await card.locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  // Ana zet geen tweede handtekening voor zichzelf: zij staat niet bij "Voor wie".
  await card.getByRole('button', { name: t.invoice.giveSecondSignature, exact: true }).click();
  await card.getByRole('combobox', { name: t.invoice.signFor }).click();
  await expect(page.getByRole('option', { name: 'Bram Demo' })).toBeVisible();
  await expect(page.getByRole('option', { name: 'Ana Demo' })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await card.locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  await signOut(page);

  // Bram zet de tweede handtekening voor Ana.
  await login(page, 'bram');
  await openInvoice(page, twin);
  card = await openSheetRow(page, title);
  await giveOrder(page, card, t.invoice.giveSecondSignature, { [t.invoice.signFor]: 'Ana Demo', [t.action.reason]: 'Gecontroleerd met Ana: dubbel ontvangen.' });
  await expect(page.locator('.ws-toast')).toBeVisible();
  await signOut(page);

  // Nu accepteert Ana: de melding is geaccepteerd en er staan minder facturen geblokkeerd.
  await login(page, 'ana');
  await openInvoice(page, twin);
  card = await openSheetRow(page, title);
  await card.getByRole('button', { name: t.invoice.accept, exact: true }).click();
  await expect(card).toContainText('Bram Demo heeft de tweede handtekening voor jou gegeven');
  await expect(card.getByTestId('action-blocked')).toHaveCount(0);
  // Te kort: dat zegt de app zelf, zonder iets te versturen.
  await card.getByLabel(t.action.reason).fill('kort');
  await formButton(card, t.invoice.accept).click();
  await expect(card.getByRole('alert')).toContainText('minstens 10 tekens');
  await card.getByLabel(t.action.reason).fill('Twee keer dezelfde factuur ontvangen; de leverancier heeft het bevestigd.');
  await capture(page, 'daily-nl-accept-signed');
  await formButton(card, t.invoice.accept).click();
  await card.locator('.chat-export').getByRole('button', { name: t.invoice.accept, exact: true }).click();
  await expect(page.locator('.ws-toast')).toBeVisible();
  // De melding staat niet meer bij wat te doen; het veredicto lo cuenta como aceptada.
  await expect(invoiceRow(page, title)).toHaveCount(0);
  await expect(verdictLine(page)).toContainText('Door een medewerker geaccepteerd: 1');
  await capture(page, 'daily-nl-invoice-accepted');
  await expect.poll(() => blockedNow(page)).toBeLessThan(blockedBefore);
});

test('een melding accepteren en de uitzondering oplossen: de tellingen veranderen', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'ana');
  const exceptionsBefore = await homeCount(page, t.nav.exceptions.label);
  await openInvoice(page, 'KT-202608');
  await expect(verdictLine(page)).toContainText('Bezwaren van het systeem: 1');
  const card = await openSheetRow(page, 'Vervallen');
  await card.getByRole('button', { name: t.invoice.accept, exact: true }).click();
  await card.getByLabel(t.action.reason).fill('Betalingsregeling afgesproken met de zzp-er.');
  await capture(page, 'daily-nl-accept-card');
  await formButton(card, t.invoice.accept).click();
  await card.locator('.chat-export').getByRole('button', { name: t.invoice.accept, exact: true }).click();
  await expect(invoiceRow(page, 'Vervallen')).toHaveCount(0);
  await expect(verdictLine(page)).toContainText('Door een medewerker geaccepteerd: 1');
  // Dan de uitzondering: oplossen met hoe het is afgelopen.
  const exception = await openSheetRow(page, t.invoice.exceptionStep);
  await giveOrder(page, exception, t.exceptions.resolve, {
    [t.exceptions.resolution]: 'Geaccepteerd',
    [t.exceptions.whatWasDone]: 'Regeling vastgelegd; de melding is geaccepteerd.',
  });
  await expect(invoiceRow(page, t.invoice.exceptionStep)).toHaveCount(0);
  await expect.poll(() => homeCount(page, t.nav.exceptions.label)).toBe(exceptionsBefore - 1);
});

test('een schone factuur markeren als gecontroleerd', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'ana');
  await openInvoice(page, 'JV-2026-004');
  await expect(verdictLine(page)).toHaveText('Geen bezwaren van het systeem');
  const card = await openSheetRow(page, t.invoice.reviewStep);
  await expect(card).toContainText(t.invoice.reviewReady);
  await card.getByRole('button', { name: t.invoice.markReviewed, exact: true }).click();
  // Una explicacion, la de la tarjeta (sin "Doorgaan?").
  await expect(card).toContainText('Dat keurt geen betaling goed en betaalt niets.');
  await expect(card).not.toContainText('Doorgaan?');
  await formButton(card, t.invoice.markReviewed).click();
  await card.locator('.chat-export').getByRole('button', { name: t.invoice.markReviewed, exact: true }).click();
  // Ya revisada: la fila se va, y la historia dice quien.
  await expect(invoiceRow(page, t.invoice.reviewStep)).toHaveCount(0);
  const more = await openSheetRow(page, t.aurora.sheet.more);
  await expect(more).toContainText(`${t.history.reviewed} · Ana Demo`);
  await capture(page, 'daily-nl-invoice-reviewed');
  await setLang(page, 'en');
  await openInvoice(page, 'JV-2026-004', { lang: 'en' });
  await expect(verdictLine(page, 'en')).toHaveText('No system objections');
  await capture(page, 'daily-en-invoice-reviewed');
  await setLang(page, 'nl');
});

test('een verouderde rev geeft de melding dat iemand anders het wijzigde', async ({ page, baseUrl, watch, request }) => {
  watch.expectHttpErrors(409);
  await signIn(page, baseUrl, 'ana');
  await openInvoice(page, 'JV-2026-005');
  const card = await openSheetRow(page, t.aurora.sheet.read);
  // El campo, elegido en la tarjeta de "Gelezen gegevens"; su orden "Wijzigen".
  await fillOrder(page, card, { [t.aurora.sheet.field]: 'Betaalvoorwaarden (op document)' });
  const edit = fill(t.fields.editThis, { field: 'Betaalvoorwaarden (op document)' });
  await card.getByRole('button', { name: edit, exact: true }).click();

  // Intussen wijzigt Bram dezelfde factuur (via de API, met zijn eigen code).
  const facturas = await (await request.get(`${baseUrl}/api/v2/facturas`, { headers: { 'X-BMS-Token': token('bram') } })).json();
  const id = facturas.facturas.find((f: { numero: string }) => f.numero === 'JV-2026-005').id;
  const invoice = await (await request.get(`${baseUrl}/api/v2/facturas/${id}`, { headers: { 'X-BMS-Token': token('bram') } })).json();
  const changed = await request.post(`${baseUrl}/api/v2/acciones`, {
    headers: { 'X-BMS-Token': token('bram'), 'Content-Type': 'application/json' },
    data: {
      accion: 'fijar_campo',
      peticion_id: `e2e-${Date.now()}`,
      datos: { tabla: 'factura', fila_id: id, campo: 'referencia_pago', valor: 'REF-BRAM', rev: invoice.factura.rev, motivo: 'Kenmerk van de bank' },
    },
  });
  expect(changed.status()).toBe(200);

  // Ana slaat haar wijziging op met de oude rev: die van Bram wordt niet overschreven.
  await card.getByLabel(t.fields.newValue).fill('30 dagen netto');
  await expect(card).toContainText('30 dagen netto');
  await card.getByLabel(t.action.reason).fill('Zo staat het op de factuur');
  await formButton(card, edit).click();
  await card.locator('.chat-export').getByRole('button', { name: edit, exact: true }).click();
  // Lo dice en la tarjeta y vuelve a leer: lo de Bram se ve.
  await expect(card.getByRole('alert')).toContainText(t.aurora.order.stale);
  await expectAccessible(page, 'conflict');
  await capture(page, 'daily-nl-conflict');
  await expect(card.getByTestId('field-line').filter({ hasText: /^Betalingskenmerk/ })).toContainText('REF-BRAM');
});

test('wie alleen mag kijken, ziet geen enkele knop voor een handeling', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'cas');
  const actions =
    /Accepteren|Tweede handtekening|Afsluiten|Markeren als|Opnieuw laten bekijken|Notitie toevoegen|Uitzondering openen|Zelf oppakken|Toewijzen|Wacht op anderen|Oplossen|Wijzigen|Invullen|Verifiëren|Terugzetten|Bevestigen|Afwijzen|Telefonisch|Overgenomen rekeningen bevestigen|Betaling vastleggen|Intrekken/;
  await openInvoice(page, 'DGG-2026-118');
  // Cada fila se ve igual; su tarjeta, sin ninguna orden.
  const titles = await sheetDialog(page).locator('.ws-file-table > a strong').allTextContents();
  expect(titles.length).toBeGreaterThan(2);
  for (const title of titles) {
    const card = await openSheetRow(page, title);
    await expect(card.getByRole('button', { name: actions })).toHaveCount(0);
  }
  await capture(page, 'daily-nl-invoice-read-only');
  await openEntry(page, 'home');
  await openGroup(page, t.nav.exceptions.label);
  const exception = await openCard(page, panel(page).locator('.doc-list button.doc').first());
  await expect(exception.getByRole('button', { name: actions })).toHaveCount(0);
  await openEntry(page, 'home');
  await openGroup(page, t.aurora.home.iban);
  const iban = await openCard(page, panelRow(page, 'Proefwacht Security VOF'));
  await expect(iban).toContainText('020-5550103');
  await expect(iban.getByRole('button', { name: actions })).toHaveCount(0);
  // Verwerken (Facturen lezen) staat niet eens in de rueda: zeven ingangen, en in het paneel
  // van Te ontvangen geen Importeren.
  await openMenu(page);
  await expect(page.locator('.navigation .nav-item')).toHaveCount(ENTRIES.length - 1);
  await expect(entryButton(page, 'process')).toHaveCount(0);
});

test('uitzonderingen: de lijst, de uitzondering zelf en zelf oppakken', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'bram');
  await openEntry(page, 'home');
  await openGroup(page, t.nav.exceptions.label);
  await expect(panel(page)).toContainText('Andere valuta dan euro');
  await expect(panel(page)).toContainText('Wacht op de leverancier');
  await expect(panel(page)).not.toContainText('Sin turnos');
  await expectAccessible(page, 'uitzonderingen');
  await capture(page, 'daily-nl-exceptions');
  const card = await openCard(page, panel(page).getByRole('button', { name: /^Uitzondering \d+ openen$/ }).first());
  // De titel zegt waar het om gaat, niet een intern nummer.
  await expect(card.getByRole('heading', { level: 3 })).not.toHaveText(/^Uitzondering \d+$/);
  await expect(card.getByRole('heading', { level: 3 })).not.toBeEmpty();
  await giveOrder(page, card, t.exceptions.takeIt);
  await expect(detail(page)).toContainText('Bij Bram Demo');
  await expectAccessible(page, 'uitzondering');
  await capture(page, 'daily-nl-exception');
  // "Factuur openen": su hoja, con el vuelo.
  await detail(page).getByRole('button', { name: t.exceptions.openInvoice }).click();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toBeVisible();
  await setLang(page, 'en');
  await openEntry(page, 'home', 'en');
  await openGroup(page, TEXTS.en.nav.exceptions.label);
  await expect(panel(page)).toContainText('Currency other than euro');
  await capture(page, 'daily-en-exceptions');
  await setLang(page, 'nl');
});

test('IBAN-controles: bellen naar het nummer uit de stamgegevens, zelf typen, en de regel van de twee personen', async ({ page, baseUrl, watch }) => {
  watch.expectHttpErrors(403);
  await signIn(page, baseUrl, 'ana');
  const open = async () => {
    await openEntry(page, 'home');
    await openGroup(page, t.aurora.home.iban);
    return openCard(page, panelRow(page, 'Proefwacht Security VOF'));
  };
  let card = await open();
  await expect(card).toContainText('NL37 DEMO 0009 9903 01');
  await expect(card).toContainText('020-5550103');
  await expect(card).toContainText('Nieuw of gewijzigd IBAN');
  await expectAccessible(page, 'iban');
  await capture(page, 'daily-nl-iban-checks');

  async function fillCall(c: Locator) {
    await c.getByRole('button', { name: t.iban.verify, exact: true }).click();
    // Het IBAN wordt nooit uit het document overgenomen: het veld is leeg.
    await expect(c.getByLabel(t.iban.typedIban)).toHaveValue('');
    await expect(c.getByLabel(t.iban.phoneCalled)).toHaveValue('020-5550103');
    await c.getByLabel(t.iban.typedIban).fill('NL37 DEMO 0009 9903 02');
    await expect(c.getByText(t.status.ibanTyped.difiere)).toBeVisible();
    await c.getByLabel(t.iban.typedIban).fill('nl37 demo 0009 9903 01');
    await expect(c.getByText(t.status.ibanTyped.coincide)).toBeVisible();
    await c.getByLabel(t.iban.spokeTo).fill('P. Proef');
    await c.getByLabel(t.action.note).fill('Gebeld op 19-10, rekening voorgelezen en bevestigd.');
    await formButton(c, t.iban.verify).click();
    await c.locator('.chat-export').getByRole('button', { name: t.iban.verify, exact: true }).click();
  }

  // Ana zette zelf het telefoonnummer van deze leverancier in de stamgegevens: zij mag niet met
  // dat nummer verifiëren. De server weigert, en de app zegt het duidelijk (waarom precies).
  await fillCall(card);
  await expect(card.getByRole('alert')).toContainText('Je hebt het telefoonnummer voor controle van deze leverancier zelf ingesteld');
  await capture(page, 'daily-nl-iban-second-person');
  await card.locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  await signOut(page);

  // Bram belt en verifieert: de melding "nieuw of gewijzigd" verdwijnt; betalen kan pas als de
  // rekening ook in Exact staat, dus "niet betaalbaar" blijft.
  await login(page, 'bram');
  card = await open();
  await fillCall(card);
  await expect(card).not.toContainText('Nieuw of gewijzigd IBAN');
  await expect(card).toContainText('IBAN niet betaalbaar');
  await expect(card).toContainText('Telefonisch geverifieerd');
  // Una tarjeta dice un solo estado: ni "nog niet bevestigd" ni otra vez el boton de bellen; lo
  // que falta (ponerla en Exact) en palabras.
  await expect(card).not.toContainText('nog niet bevestigd');
  await expect(card.getByRole('button', { name: t.iban.verify })).toHaveCount(0);
  await expect(card.getByTestId('iban-step')).toContainText('nog niet in de stamgegevens van Exact');
  await expectAccessible(page, 'iban geverifieerd');
  await capture(page, 'daily-nl-iban-verified');
  await setLang(page, 'en');
  await openEntry(page, 'home', 'en');
  await openGroup(page, TEXTS.en.aurora.home.iban);
  await capture(page, 'daily-en-iban-checks');
  await setLang(page, 'nl');
});

test('de facturen van een kant: vervallen, een tramo, zoeken, en een resultaat opent de factuur', async ({ page, baseUrl, request }) => {
  await signIn(page, baseUrl, 'ana');
  // Te ontvangen › Vervallen: la busqueda con sus filtros puestos, lo que dice el motor.
  await openEntry(page, 'receivables');
  await panelRow(page, t.aurora.money.overdue).click();
  await expect(page.locator('.active-filter-chips button')).not.toHaveCount(0);
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  const results = page.getByRole('region', { name: t.aurora.search.resultsLabel });
  const overdue = await (
    await request.get(`${baseUrl}/api/v2/buscar?sentido=saliente&vencida=si&orden=vencimiento&limite=50`, { headers: { 'X-BMS-Token': token('ana') } })
  ).json();
  for (const f of overdue.busqueda.facturas as { numero: string }[]) await expect(results).toContainText(f.numero);
  await expect(results).not.toContainText('Proefwacht');
  await expectAccessible(page, 'verkoop vervallen');
  await capture(page, 'daily-nl-invoices-out-overdue');
  // Te betalen › Hoe lang het al openstaat › un tramo atrasado: las de compra de ese tramo.
  await openEntry(page, 'payables');
  await openGroup(page, t.money.ageing.title);
  await panel(page).locator('button.doc').filter({ hasText: t.money.ageing.buckets['61_90'] }).click();
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await expect(results).toContainText('KT-202608');
  await capture(page, 'daily-nl-invoices-in-bucket');
  // Lo escrito busca por nombre: solo los de J. Voorbeeld.
  const box = page.getByRole('textbox', { name: t.aurora.composer.searchLabel });
  await page.getByRole('button', { name: new RegExp(`^${t.aurora.search.clearFilters}`) }).click();
  await expect(page.locator('.active-filter-chips')).toHaveCount(0);
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await box.fill('voorbeeld');
  await box.press('Enter');
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await expect(results).toContainText('J. Voorbeeld Beveiliging (zzp)');
  await expect(results).not.toContainText('Proefwacht');
  // Un resultado abre su hoja.
  const first = results.getByRole('link').first();
  const number = ((await first.locator('.result-info strong').textContent()) ?? '').trim();
  await first.click();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText(number);
});

test('de details van een factuur: velden, koppelingen, geschiedenis en het origineel', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'ana');
  await openInvoice(page, 'DBN-CR-2026-09');
  // Lo que es, arriba: el tipo y el estado.
  await expect(sheetDialog(page).locator('.ws-dialog-top')).toContainText(t.documents.types.abono_compra.toLocaleUpperCase());
  // La koppeling propuesta: "Deze factuur crediteert DBN-2026-09".
  const relation = await openSheetRow(page, t.aurora.sheet.relation);
  await expect(relation).toContainText(t.relations.thisInvoice);
  await expect(relation).toContainText('DBN-2026-09');
  await expectAccessible(page, 'koppeling');
  await capture(page, 'daily-nl-invoice-relation');
  // Bevestigen: el "si" dice lo que cambia (y sin "Doorgaan?").
  await relation.getByRole('button', { name: t.relations.confirm, exact: true }).click();
  await relation.getByLabel(t.action.reason).fill('De creditnota noemt deze factuur.');
  await formButton(relation, t.relations.confirm).click();
  await expect(relation.locator('.chat-export')).toContainText('Na bevestigen veranderen saldi, btw en dubbele facturen.');
  await expect(relation).not.toContainText('Doorgaan?');
  await relation.locator('.chat-export').getByRole('button', { name: t.relations.confirm, exact: true }).click();
  await expect(invoiceRow(page, t.aurora.sheet.relation)).toHaveCount(0);
  // De velden: lo leido y de donde viene.
  const read = await openSheetRow(page, t.aurora.sheet.read);
  await expect(read.getByTestId('field-line').filter({ hasText: /^Factuurnummer/ })).toContainText('Gelezen uit het document');
  // De geschiedenis.
  const more = await openSheetRow(page, t.aurora.sheet.more);
  await expect(more).toContainText(t.history.read);
  await expectAccessible(page, 'details');
  await capture(page, 'daily-nl-invoice-details');
  // Het origineel: de echte pdf, met de code (y queda en la auditoria).
  const download = page.waitForEvent('download');
  await sheetDialog(page).getByRole('button', { name: t.aurora.card.downloadOriginal }).click();
  expect((await download).suggestedFilename()).toBe('DBN-CR-2026-09.pdf');
  // En ingles: el tipo y lo leido.
  await setLang(page, 'en');
  await openInvoice(page, 'DBN-CR-2026-09', { lang: 'en' });
  await expect(sheetDialog(page).locator('.ws-dialog-top')).toContainText(TEXTS.en.documents.types.abono_compra.toLocaleUpperCase());
  await capture(page, 'daily-en-invoice-details');
  await setLang(page, 'nl');
});

test('de conversatie vindt een factuur en opent haar hoja met één klik', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'ana');
  await toHome(page);
  await ask(page, 'KT-202608');
  await expect(answerRow(page, 'KT-202608')).toBeVisible();
  await answerRow(page, 'KT-202608').click();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('KT-202608');
});
