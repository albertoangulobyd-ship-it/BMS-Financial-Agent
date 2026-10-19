// Las pantallas del trabajo diario sobre la base de prueba: Overzicht, Werklijst, Inkomend,
// Uitgaand, la ficha de una factura, Uitzonderingen e IBAN-controles, con datos y ordenes
// de verdad. Las pruebas van en orden y cambian la base (aceptar, resolver, marcar), asi
// que cada una mira lo que deja la anterior: lo que comprueban son cambios, no cifras
// sueltas. Captura de cada pantalla en neerlandes y en ingles (CAPTURAS_DIR).
import { capture, expect, expectAccessible, login, settled, test, token, type Who } from './fixtures';
import type { Page } from '@playwright/test';

const MENU = { nl: 'Hoofdmenu', en: 'Main menu' } as const;

async function nav(page: Page, label: string, lang: 'nl' | 'en' = 'nl') {
  await page.getByRole('navigation', { name: MENU[lang] }).getByRole('button', { name: new RegExp(`^${label}`) }).click();
  await expect(page.getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
  await settled(page);
}

async function english(page: Page) {
  await page.getByRole('button', { name: 'English' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await settled(page);
}

async function dutch(page: Page) {
  await page.getByRole('button', { name: 'Nederlands' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'nl');
  await settled(page);
}

/** Abre una factura desde Inkomend o Uitgaand buscando su numero. */
async function openInvoice(page: Page, number: string, list: 'Inkomend' | 'Uitgaand' = 'Inkomend') {
  await nav(page, list);
  await page.getByRole('searchbox').fill(number);
  await page.getByRole('button', { name: `Factuur ${number} openen` }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(`${number}$`) })).toBeVisible();
}

async function signIn(page: Page, baseUrl: string, who: Who = 'ana') {
  await page.goto(`${baseUrl}/app`);
  await login(page, who);
}

async function signOut(page: Page, name: string) {
  await page.getByRole('button', { name: `Accountmenu van ${name}` }).click();
  await page.getByRole('menuitem', { name: 'Uitloggen' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
}

/** El numero de una insignia de la navegacion ("Uitzonderingen 13"). */
async function badge(page: Page, label: string): Promise<number> {
  const text = (await page.getByRole('navigation', { name: MENU.nl }).getByRole('button', { name: new RegExp(`^${label}`) }).textContent()) ?? '';
  const m = /(\d+)/.exec(text);
  return m ? Number(m[1]) : 0;
}

/** La insignia cuando ya ha llegado del panel (al entrar, aun no hay ninguna). */
async function loadedBadge(page: Page, label: string): Promise<number> {
  await expect.poll(() => badge(page, label)).toBeGreaterThan(0);
  return badge(page, label);
}

test('het overzicht: vier kaarten en wat als eerste moet, in NL en EN', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await expect(page.getByRole('heading', { level: 1, name: 'Overzicht' })).toBeVisible();
  // Vier kaarten, niet meer.
  for (const title of ['Aandacht nodig', 'Geld binnen', 'Geld uit']) {
    await expect(page.getByRole('heading', { level: 2, name: title })).toBeVisible();
  }
  await expect(page.getByRole('heading', { level: 2, name: 'Btw dit kwartaal' })).toBeVisible();
  await expect(page.getByTestId('summary-card')).toHaveCount(4);
  // Als eerste: vijf facturen, de geblokkeerde bovenaan, met een waarom in gewone woorden.
  const next = page.locator('section[aria-labelledby="next-up"]').getByRole('listitem');
  await expect(next).toHaveCount(5);
  await expect(next.first()).toContainText('Geblokkeerd');
  await expect(next.first()).toContainText('Bedragen in USD: niet in euro');
  // Vijf verschillende dingen: twee facturen met hetzelfde nummer staan in één rij.
  const numbers = await next.getByTestId('next-up-number').allTextContents();
  expect(new Set(numbers).size).toBe(5);
  await expect(next.filter({ hasText: 'JV-2026-006' })).toContainText('2 facturen met dit nummer');
  // De kaarten van het geld zeggen welke facturen ze openen.
  await expect(page.getByRole('main').getByRole('button', { name: 'Verkoopfacturen' })).toBeVisible();
  await expect(page.getByRole('main').getByRole('button', { name: 'Inkoopfacturen' })).toBeVisible();
  await expectAccessible(page, 'overzicht nl');
  await capture(page, 'daily-nl-overview');
  await english(page);
  await expect(page.getByRole('heading', { level: 2, name: 'Needs attention' })).toBeVisible();
  await expect(next.first()).toContainText('Amounts in USD: not in euros');
  await capture(page, 'daily-en-overview');
  // Een kaart opent het scherm dat haar uitlegt.
  await page.getByRole('main').getByRole('button', { name: 'Work queue', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Work queue', exact: true })).toBeVisible();
  await dutch(page);
});

test('de geblokkeerde facturen zeggen waarom, in het Nederlands en het Engels', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl);
  await nav(page, 'Werklijst');
  await page.getByRole('group', { name: 'Toon' }).getByRole('button', { name: /^Geblokkeerd/ }).click();
  const rows = page.getByRole('table').getByRole('row');
  // De kop en vier geblokkeerde facturen.
  await expect(rows).toHaveCount(5);
  await expect(page.getByRole('table')).toContainText('Bedragen in USD: niet in euro, daarom buiten alle totalen.');
  await expect(page.getByRole('table')).toContainText('Hetzelfde nummer (JV2026006) staat op 2 facturen van dezelfde wederpartij.');
  // De twee met hetzelfde nummer zijn te onderscheiden.
  await expect(page.getByRole('table')).toContainText('1 van 2');
  await expect(page.getByRole('table')).toContainText('2 van 2');
  await expect(page.getByRole('table')).toContainText('NL37 DEMO 0009 9903 01 staat niet in het rekeningregister van deze leverancier.');
  // Geen Spaans van de API.
  await expect(page.getByRole('table')).not.toContainText('Importes en USD');
  await expectAccessible(page, 'werklijst geblokkeerd nl');
  await capture(page, 'daily-nl-work-queue-blocked');

  await english(page);
  await expect(page.getByRole('table')).toContainText('Amounts in USD: not in euros, so left out of all totals.');
  await expect(page.getByRole('table')).toContainText('The same number (JV2026006) is on 2 invoices from the same party.');
  await capture(page, 'daily-en-work-queue-blocked');

  // De factuur zelf: wat het is, wat er mis is en wat te doen.
  await page.getByRole('button', { name: 'Open Invoice DGG-2026-118' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Invoice DGG-2026-118' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 3, name: 'Currency other than euro' })).toBeVisible();
  await expect(page.getByText('Amounts in USD: not in euros, so left out of all totals.')).toBeVisible();
  await expect(page.getByText('Check the currency and get a version in euros')).toBeVisible();
  await expect(page.getByText('System objections: 2')).toBeVisible();
  await expectAccessible(page, 'factuur en');
  await capture(page, 'daily-en-invoice-blocked');
  await dutch(page);
  await expect(page.getByRole('heading', { level: 1, name: 'Factuur DGG-2026-118' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 3, name: 'Andere valuta dan euro' })).toBeVisible();
  await expect(page.getByText('Wat te doen:').first()).toBeVisible();
  await capture(page, 'daily-nl-invoice-blocked');
});

test('accepteren vraagt een tweede persoon; met die handtekening gaat het en de tellingen veranderen', async ({
  page,
  baseUrl,
  watch,
}) => {
  watch.expectHttpErrors(403);
  await signIn(page, baseUrl, 'ana');
  const blockedBefore = await loadedBadge(page, 'Werklijst');
  await openInvoice(page, 'JV-2026-006');
  const card = page.getByRole('article', { name: 'Factuurnummer dubbel' });
  await card.getByRole('button', { name: 'Accepteren' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'Melding accepteren' })).toBeVisible();
  // De regel van de twee personen: zonder de handtekening van een collega kan het niet. De
  // app zegt het en laat niet versturen wat de server toch zou weigeren.
  await expect(dialog.getByTestId('action-blocked')).toContainText('Vraag een collega met dezelfde bevoegdheid om “Tweede handtekening geven”');
  await expect(dialog.getByRole('button', { name: 'Melding accepteren' })).toBeDisabled();
  await dialog.getByLabel('Reden').fill('Twee keer dezelfde factuur ontvangen; de leverancier heeft het bevestigd.');
  await expectAccessible(page, 'dialoog tweede persoon');
  await capture(page, 'daily-nl-accept-second-person');
  await dialog.getByRole('button', { name: 'Annuleren' }).click();
  // Ana zet geen tweede handtekening voor zichzelf: zij staat niet bij "Voor wie".
  await page.getByRole('article', { name: 'Factuurnummer dubbel' }).getByRole('button', { name: 'Tweede handtekening geven' }).click();
  const own = page.getByRole('dialog');
  await expect(own.getByLabel('Voor wie').locator('option', { hasText: 'Ana Demo' })).toHaveCount(0);
  await own.getByRole('button', { name: 'Annuleren' }).click();
  await signOut(page, 'Ana Demo');

  // Bram zet de tweede handtekening voor Ana.
  await login(page, 'bram');
  await openInvoice(page, 'JV-2026-006');
  await page.getByRole('article', { name: 'Factuurnummer dubbel' }).getByRole('button', { name: 'Tweede handtekening geven' }).click();
  const sign = page.getByRole('dialog');
  await sign.getByLabel('Voor wie').selectOption({ label: 'Ana Demo' });
  await sign.getByLabel('Reden').fill('Gecontroleerd met Ana: dubbel ontvangen.');
  await sign.getByRole('button', { name: 'Tweede handtekening geven' }).click();
  await expect(sign).toBeHidden();
  await signOut(page, 'Bram Demo');

  // Nu accepteert Ana: de melding is geaccepteerd en er staan minder facturen geblokkeerd.
  await login(page, 'ana');
  await openInvoice(page, 'JV-2026-006');
  await page.getByRole('article', { name: 'Factuurnummer dubbel' }).getByRole('button', { name: 'Accepteren' }).click();
  const accept = page.getByRole('dialog');
  await expect(accept).toContainText('Bram Demo heeft de tweede handtekening voor jou gegeven');
  await expect(accept.getByTestId('action-blocked')).toHaveCount(0);
  // Te kort: dat zegt de app zelf, zonder iets te versturen.
  await accept.getByLabel('Reden').fill('kort');
  await accept.getByRole('button', { name: 'Melding accepteren' }).click();
  await expect(accept.getByRole('alert')).toContainText('minstens 10 tekens');
  await accept.getByLabel('Reden').fill('Twee keer dezelfde factuur ontvangen; de leverancier heeft het bevestigd.');
  await capture(page, 'daily-nl-accept-signed');
  await accept.getByRole('button', { name: 'Melding accepteren' }).click();
  await expect(accept).toBeHidden();
  await expect(page.getByRole('article', { name: 'Factuurnummer dubbel' })).toContainText('Geaccepteerd');
  await expect(page.getByTestId('verdict')).toContainText('Door een medewerker geaccepteerd: 1');
  await expect.poll(() => badge(page, 'Werklijst')).toBeLessThan(blockedBefore);
  await capture(page, 'daily-nl-invoice-accepted');
});

test('een melding accepteren en de uitzondering oplossen: de tellingen veranderen', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'ana');
  const exceptionsBefore = await loadedBadge(page, 'Uitzonderingen');
  await openInvoice(page, 'KT-202608');
  await expect(page.getByTestId('verdict')).toContainText('Bezwaren van het systeem: 1');
  await page.getByRole('article', { name: 'Vervallen' }).getByRole('button', { name: 'Accepteren' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Reden').fill('Betalingsregeling afgesproken met de zzp-er.');
  await capture(page, 'daily-nl-accept-dialog');
  await dialog.getByRole('button', { name: 'Melding accepteren' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId('verdict')).toContainText('Door een medewerker geaccepteerd: 1');
  // Dan de uitzondering: oplossen met hoe het is afgelopen.
  await page.getByRole('button', { name: 'Oplossen' }).click();
  const resolve = page.getByRole('dialog');
  await resolve.getByLabel('Hoe is het afgelopen').selectOption('aceptado');
  await resolve.getByLabel('Wat is er gedaan').fill('Regeling vastgelegd; de melding is geaccepteerd.');
  await resolve.getByRole('button', { name: 'Uitzondering oplossen' }).click();
  await expect(resolve).toBeHidden();
  await expect(page.getByText('Er staat geen uitzondering open.')).toBeVisible();
  await expect.poll(() => badge(page, 'Uitzonderingen')).toBe(exceptionsBefore - 1);
});

test('een schone factuur markeren als gecontroleerd', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'ana');
  await openInvoice(page, 'JV-2026-004');
  await expect(page.getByTestId('verdict')).toHaveText('Geen bezwaren van het systeem');
  await expect(page.getByText('Niets heeft je aandacht nodig')).toBeVisible();
  await page.getByRole('button', { name: 'Markeren als gecontroleerd' }).click();
  const dialog = page.getByRole('dialog');
  // Una explicacion, la de la pantalla (sin repetirla en una caja gris con "Doorgaan?").
  await expect(dialog).toContainText('Dat keurt geen betaling goed en betaalt niets.');
  await expect(dialog).not.toContainText('Doorgaan?');
  await dialog.getByRole('button', { name: 'Markeren als gecontroleerd' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText(/^Gecontroleerd door Ana Demo op \d+ \w+ 20\d\d\.$/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Markeren als gecontroleerd' })).toHaveCount(0);
  await capture(page, 'daily-nl-invoice-reviewed');
  await english(page);
  await expect(page.getByTestId('verdict')).toHaveText('No system objections');
  await capture(page, 'daily-en-invoice-reviewed');
  await dutch(page);
});

test('een verouderde rev geeft de melding dat iemand anders het wijzigde', async ({ page, baseUrl, watch, request }) => {
  watch.expectHttpErrors(409);
  await signIn(page, baseUrl, 'ana');
  await openInvoice(page, 'JV-2026-005');
  await page.getByRole('button', { name: /^Velden/ }).click();
  const row = page.getByRole('row', { name: /Betaalvoorwaarden/ });
  await row.getByRole('button', { name: 'Wijzigen' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('Nu', { exact: true })).toBeVisible();

  // Intussen wijzigt Bram dezelfde factuur (via de API, met zijn eigen code).
  const facturas = await (await request.get(`${baseUrl}/api/v2/facturas`, { headers: { 'X-BMS-Token': token('bram') } })).json();
  const id = facturas.facturas.find((f: { numero: string }) => f.numero === 'JV-2026-005').id;
  const detail = await (await request.get(`${baseUrl}/api/v2/facturas/${id}`, { headers: { 'X-BMS-Token': token('bram') } })).json();
  const changed = await request.post(`${baseUrl}/api/v2/acciones`, {
    headers: { 'X-BMS-Token': token('bram'), 'Content-Type': 'application/json' },
    data: {
      accion: 'fijar_campo',
      peticion_id: `e2e-${Date.now()}`,
      datos: { tabla: 'factura', fila_id: id, campo: 'referencia_pago', valor: 'REF-BRAM', rev: detail.factura.rev, motivo: 'Kenmerk van de bank' },
    },
  });
  expect(changed.status()).toBe(200);

  // Ana slaat haar wijziging op met de oude rev: die van Bram wordt niet overschreven.
  await dialog.getByLabel('Nieuw').fill('30 dagen netto');
  await expect(dialog.getByText('30 dagen netto', { exact: true })).toBeVisible();
  await dialog.getByLabel('Reden').fill('Zo staat het op de factuur');
  await dialog.getByRole('button', { name: 'Waarde invullen of corrigeren' }).click();
  await expect(dialog.getByRole('alert')).toContainText('Iemand anders heeft dit net gewijzigd');
  await expectAccessible(page, 'conflict');
  await capture(page, 'daily-nl-conflict');
  await dialog.getByRole('button', { name: 'Opnieuw laden' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('row', { name: /Betalingskenmerk/ })).toContainText('REF-BRAM');
});

test('wie alleen mag kijken, ziet geen enkele knop voor een handeling', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'cas');
  const actions = /Accepteren|Tweede handtekening|Afsluiten|Markeren als|Opnieuw laten bekijken|Notitie toevoegen|Uitzondering openen|Zelf oppakken|Toewijzen|Wacht op anderen|Oplossen|Wijzigen|Invullen|Verifiëren|Terugzetten|Bevestigen|Afwijzen|Telefonisch|Overgenomen rekeningen bevestigen/;
  await openInvoice(page, 'DGG-2026-118');
  await expect(page.getByRole('heading', { level: 3, name: 'Andere valuta dan euro' })).toBeVisible();
  await page.getByRole('button', { name: /^Velden/ }).click();
  await page.getByRole('button', { name: /^Koppelingen/ }).click();
  await expect(page.getByRole('main').getByRole('button', { name: actions })).toHaveCount(0);
  await capture(page, 'daily-nl-invoice-read-only');
  await nav(page, 'Uitzonderingen');
  await page.getByRole('table').getByRole('row').nth(1).getByRole('button').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog').getByRole('button', { name: actions })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await nav(page, 'IBAN-controles');
  await expect(page.getByText('020-5550103')).toBeVisible();
  await expect(page.getByRole('main').getByRole('button', { name: actions })).toHaveCount(0);
  // Importeren en Facturen lezen staan niet eens in het menu.
  await expect(page.getByRole('navigation', { name: MENU.nl }).getByRole('button', { name: /^Importeren/ })).toHaveCount(0);
});

test('uitzonderingen: de lijst, het paneel en zelf oppakken', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'bram');
  await nav(page, 'Uitzonderingen');
  const table = page.getByRole('table');
  await expect(table).toContainText('Andere valuta dan euro');
  await expect(table).toContainText('Wacht op de leverancier');
  await expect(table).not.toContainText('Sin turnos');
  await expectAccessible(page, 'uitzonderingen');
  await capture(page, 'daily-nl-exceptions');
  await page.getByRole('button', { name: /^Uitzondering \d+ openen$/ }).first().click();
  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('heading', { name: 'Wat is er aan de hand' })).toBeVisible();
  // De titel zegt waar het om gaat, niet een intern nummer.
  await expect(sheet.getByRole('heading', { level: 2 }).first()).not.toHaveText(/^Uitzondering \d+$/);
  await expect(sheet.getByRole('heading', { level: 2 }).first()).not.toBeEmpty();
  await sheet.getByRole('button', { name: 'Zelf oppakken' }).click();
  await page.getByRole('dialog', { name: 'Zelf oppakken' }).getByRole('button', { name: 'Uitzondering toewijzen' }).click();
  await expect(sheet).toContainText('Bij Bram Demo');
  await expectAccessible(page, 'uitzondering paneel');
  await capture(page, 'daily-nl-exception-sheet');
  await sheet.getByRole('button', { name: 'Factuur openen' }).click();
  await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
  await nav(page, 'Uitzonderingen');
  await english(page);
  await expect(page.getByRole('heading', { level: 1, name: 'Exceptions' })).toBeVisible();
  await expect(page.getByRole('table')).toContainText('Currency other than euro');
  await capture(page, 'daily-en-exceptions');
  await dutch(page);
});

test('IBAN-controles: bellen naar het nummer uit de stamgegevens, zelf typen, en de regel van de twee personen', async ({
  page,
  baseUrl,
  watch,
}) => {
  watch.expectHttpErrors(403);
  await signIn(page, baseUrl, 'ana');
  await nav(page, 'IBAN-controles');
  const card = page.getByRole('article', { name: /Proefwacht Security VOF/ });
  await expect(card).toContainText('NL37 DEMO 0009 9903 01');
  await expect(card).toContainText('020-5550103');
  await expect(card).toContainText('Nieuw of gewijzigd IBAN');
  await expectAccessible(page, 'iban');
  await capture(page, 'daily-nl-iban-checks');

  async function fillCall() {
    await card.getByRole('button', { name: 'Telefonisch bevestigen' }).click();
    const dialog = page.getByRole('dialog');
    // Het IBAN wordt nooit uit het document overgenomen: het veld is leeg.
    await expect(dialog.getByLabel('IBAN zoals de leverancier het noemt')).toHaveValue('');
    await expect(dialog.getByLabel('Gebeld nummer')).toHaveValue('020-5550103');
    await dialog.getByLabel('IBAN zoals de leverancier het noemt').fill('NL37 DEMO 0009 9903 02');
    await expect(dialog.getByText('Anders dan het gevonden IBAN')).toBeVisible();
    await dialog.getByLabel('IBAN zoals de leverancier het noemt').fill('nl37 demo 0009 9903 01');
    await expect(dialog.getByText('Hetzelfde als het gevonden IBAN')).toBeVisible();
    await dialog.getByLabel('Gesproken met').fill('P. Proef');
    await dialog.getByLabel('Notitie').fill('Gebeld op 19-10, rekening voorgelezen en bevestigd.');
    return dialog;
  }

  // Ana zette zelf het telefoonnummer van deze leverancier in de stamgegevens: zij mag
  // niet met dat nummer verifiëren. De server weigert, en de app zegt het duidelijk.
  let dialog = await fillCall();
  await expectAccessible(page, 'iban dialoog');
  await capture(page, 'daily-nl-iban-verify');
  await dialog.getByRole('button', { name: 'IBAN telefonisch verifiëren' }).click();
  // Waarom precies: zij stelde het nummer zelf in (niet een algemene "of dit, of dat").
  await expect(dialog.getByRole('alert')).toContainText('Je hebt het telefoonnummer voor controle van deze leverancier zelf ingesteld');
  await capture(page, 'daily-nl-iban-second-person');
  await dialog.getByRole('button', { name: 'Annuleren' }).click();
  await signOut(page, 'Ana Demo');

  // Bram belt en verifieert: de melding "nieuw of gewijzigd" verdwijnt; betalen kan pas
  // als de rekening ook in Exact staat, dus "niet betaalbaar" blijft.
  await login(page, 'bram');
  await nav(page, 'IBAN-controles');
  dialog = await fillCall();
  await dialog.getByRole('button', { name: 'IBAN telefonisch verifiëren' }).click();
  await expect(dialog).toBeHidden();
  await expect(card).not.toContainText('Nieuw of gewijzigd IBAN');
  await expect(card).toContainText('IBAN niet betaalbaar');
  await expect(card).toContainText('Telefonisch geverifieerd');
  // Una tarjeta dice un solo estado: ya no "nog niet bevestigd" ni otra vez el boton de
  // bellen; lo que falta (ponerla en Exact) en palabras.
  await expect(card).not.toContainText('nog niet bevestigd');
  await expect(card.getByRole('button', { name: 'Telefonisch bevestigen' })).toHaveCount(0);
  await expect(card.getByTestId('iban-step')).toContainText('nog niet in de stamgegevens van Exact');
  await expectAccessible(page, 'iban geverifieerd');
  await capture(page, 'daily-nl-iban-verified');
  await english(page);
  await expect(page.getByRole('heading', { level: 1, name: 'IBAN checks' })).toBeVisible();
  await capture(page, 'daily-en-iban-checks');
  await dutch(page);
});

test('inkomend en uitgaand: filters, zoeken en een rij opent de factuur', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'ana');
  await nav(page, 'Inkomend');
  // Fichas, como in de Werklijst; één gekleurde pastilla per rij (de prioriteit).
  const chips = page.getByRole('group', { name: 'Welke facturen' });
  await chips.getByRole('button', { name: /^Vervallen/ }).click();
  const rows = page.getByRole('table').getByRole('row');
  await expect(rows).toHaveCount(2);
  await expect(page.getByRole('table')).toContainText('KT-202608');
  await chips.getByRole('button', { name: /^Alle/ }).click();
  for (const row of await page.getByRole('table').getByRole('row').all()) {
    expect(await row.locator('[data-slot="status"]').count()).toBeLessThanOrEqual(1);
  }
  await page.getByRole('searchbox').fill('voorbeeld');
  await expect(page.getByRole('table')).toContainText('J. Voorbeeld Beveiliging (zzp)');
  await expect(page.getByRole('table')).not.toContainText('Proefwacht');
  await page.getByRole('searchbox').fill('');
  await expectAccessible(page, 'inkomend');
  await capture(page, 'daily-nl-invoices-in');
  await nav(page, 'Uitgaand');
  await expect(page.getByRole('table')).toContainText('Gemeente Demodorp');
  await expect(page.getByRole('table')).not.toContainText('Proefwacht');
  await page.getByRole('group', { name: 'Welke facturen' }).getByRole('button', { name: /^Controle nodig/ }).click();
  await expect(page.getByRole('table')).toContainText('Controle nodig');
  await expect(page.getByRole('table')).not.toContainText('Gecontroleerd');
  await page.getByRole('group', { name: 'Welke facturen' }).getByRole('button', { name: /^Alle/ }).click();
  await capture(page, 'daily-nl-invoices-out');
  await english(page);
  await nav(page, 'Out', 'en');
  await capture(page, 'daily-en-invoices-out');
  await nav(page, 'In', 'en');
  await capture(page, 'daily-en-invoices-in');
  await nav(page, 'Work queue', 'en');
  await capture(page, 'daily-en-work-queue');
  await dutch(page);
  await nav(page, 'Werklijst');
  await capture(page, 'daily-nl-work-queue');
  // Een rij opent de factuur in een tabblad; terug naar de lijst houdt het filter.
  await page.getByRole('group', { name: 'Toon' }).getByRole('button', { name: /^Urgent/ }).click();
  await page.getByRole('table').getByRole('row').nth(1).getByRole('button').click();
  await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
  await page.getByRole('tab').first().click();
  await expect(page.getByRole('group', { name: 'Toon' }).getByRole('button', { name: /^Urgent/ })).toHaveAttribute('aria-pressed', 'true');
});

test('de details van een factuur: velden, koppelingen, geschiedenis en het origineel', async ({ page, baseUrl }) => {
  await signIn(page, baseUrl, 'ana');
  await openInvoice(page, 'DBN-CR-2026-09');
  await expect(page.getByRole('heading', { level: 1, name: 'Creditnota DBN-CR-2026-09' })).toBeVisible();
  await page.getByRole('button', { name: /^Koppelingen/ }).click();
  await expect(page.getByText('Deze factuur', { exact: true })).toBeVisible();
  await expect(page.getByText('Creditering op factuur DBN-2026-09')).toBeVisible();
  await page.getByRole('button', { name: /^Geschiedenis/ }).click();
  await expect(page.getByText('Gelezen uit de pdf', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: /^Velden/ }).click();
  await expect(page.getByRole('row', { name: /Factuurnummer/ })).toContainText('Gelezen uit het document');
  await expectAccessible(page, 'details');
  await capture(page, 'daily-nl-invoice-details');
  // De relatie bevestigen: daarna is ze bevestigd.
  await page.getByRole('button', { name: 'Bevestigen' }).click();
  const dialog = page.getByRole('dialog');
  // Lo que va a pasar, una vez y sin "Doorgaan?" (el boton ya dice la orden).
  await expect(dialog).toContainText('Na bevestigen veranderen saldi, btw en dubbele facturen.');
  await expect(dialog).not.toContainText('Doorgaan?');
  await dialog.getByLabel('Reden').fill('De creditnota noemt deze factuur.');
  await dialog.getByRole('button', { name: 'Koppeling bevestigen' }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole('button', { name: /^Origineel document/ }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Origineel downloaden' }).click();
  expect((await download).suggestedFilename()).toBe('DBN-CR-2026-09.pdf');
  await english(page);
  await expect(page.getByRole('heading', { level: 1, name: 'Credit note DBN-CR-2026-09' })).toBeVisible();
  await expect(page.getByText('Confirmed', { exact: true })).toBeVisible();
  await capture(page, 'daily-en-invoice-details');
  await dutch(page);
});
