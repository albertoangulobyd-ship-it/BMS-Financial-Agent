// Documentos con datos de verdad (paso 16, revision §8.5): el archivo de Aurora sobre la base
// de prueba. Cada interaccion de las filas de Documentos de la revision (§1b, 36 a 48) hace lo
// que dice: las migas, "Volver" y el orbe; el arbol con el raton y con el teclado; la carpeta
// de cristal y "Abrir ficha"; la hoja del abanico; la ficha de verdad; el saldo; la fila y su
// vista previa dibujada desde el registro; cerrarla con la X, Escape o un clic fuera;
// "Descargar el original" (el PDF de verdad); sin "Agregar muestra"; la pista de los 12 s,
// ahora el texto del buscador; el buscador y las pestanas. Y las doce primeras con "Ver todas",
// los vacios y un error con su reintento. Las capturas, en los tres idiomas y los dos temas.
import { readFileSync } from 'node:fs';
import type { APIRequestContext, Download, Page } from '@playwright/test';
import { capture, chooseTheme, expect, expectAccessible, expectNoLeftovers, login, settled, test, token } from './fixtures';
import { TEXTS, back, crumbs, escapeRegExp, fill, go, setLang, viewHeading } from './nav';

const t = TEXTS.nl;

interface Row {
  id: number;
  nombre: string;
  pendiente_cent: number;
  /** Contrato 2.4: la cifra de la cartera, la que dice la carpeta (revision del paso 16). */
  deuda_cent: number;
  vencido_cent: number;
  nivel: string;
  documentos?: number;
}

/** Un importe como lo escribe la app (format.ts): euro, espacio que no se parte y notacion
 *  neerlandesa. */
function euro(cents: number): string {
  const abs = Math.abs(cents);
  const units = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `€\u00a0${cents < 0 ? '−' : ''}${units},${String(abs % 100).padStart(2, '0')}`;
}

/** Las carpetas como las pide la revision: lo vencido, luego lo pendiente, luego el orden de
 *  la API. */
function expectedOrder(clients: Row[], providers: Row[]): string[] {
  return [...clients, ...providers]
    .map((row, index) => ({ row, index }))
    .sort((a, b) => b.row.vencido_cent - a.row.vencido_cent || Math.max(0, b.row.deuda_cent) - Math.max(0, a.row.deuda_cent) || a.index - b.index)
    .map((x) => x.row.nombre);
}

async function lists(request: APIRequestContext, baseUrl: string): Promise<{ clients: Row[]; providers: Row[] }> {
  const headers = { 'X-BMS-Token': token('ana') };
  const clients = ((await (await request.get(`${baseUrl}/api/v2/clientes`, { headers })).json()) as { clientes: Row[] }).clientes;
  const providers = ((await (await request.get(`${baseUrl}/api/v2/proveedores`, { headers })).json()) as { proveedores: Row[] }).proveedores;
  return { clients, providers };
}

const grid = (page: Page, label = t.documents.tabAll) => page.getByRole('list', { name: label, exact: true });
const folderNames = async (page: Page, label?: string) =>
  grid(page, label).locator(':scope > [role="listitem"]').evaluateAll((cells) => cells.map((c) => c.getAttribute('aria-label') ?? ''));
/** La carpeta de cristal (su boton: abrir o cerrar). */
const folder = (page: Page, name: string) => page.getByRole('button', { name: new RegExp(`^${escapeRegExp(name)} (openen|sluiten)`) });
const profile = (page: Page, name: string) => page.getByRole('region', { name, exact: true });
const preview = (page: Page) => page.getByRole('dialog');

/** Las carpetas pintadas del todo (su dorso se calcula por partes): para las capturas. */
async function artReady(page: Page): Promise<void> {
  await page.waitForFunction(
    () => Array.from(document.querySelectorAll('canvas.gf-art')).every((c) => c.hasAttribute('data-ready')),
    undefined,
    { timeout: 30_000 }
  );
  await settled(page);
}

async function openFolder(page: Page, name: string): Promise<void> {
  await folder(page, name).click();
  await expect(page.getByRole('heading', { level: 1, name: fill(t.documents.folderOf, { name }) })).toBeVisible();
  await expect(profile(page, name)).toBeVisible();
  await settled(page);
}

async function pdfOf(download: Download): Promise<string> {
  return readFileSync((await download.path())!).subarray(0, 5).toString('latin1');
}

test('el archivo: carpetas en su orden, pestanas, buscador y la ficha de verdad', async ({ page, baseUrl, request }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const { clients, providers } = await lists(request, baseUrl);
  await go(page, 'documents');
  await expect(page.getByText(t.documents.eyebrow, { exact: true })).toBeVisible();
  // Ninguna muestra que anadir, ningun dato inventado.
  await expect(page.getByRole('button', { name: /muestra|monster|sample/i })).toHaveCount(0);

  // Una carpeta por cliente y por proveedor, en el orden de lo que pide atencion; la cuenta de
  // cada pestana.
  const tabs = page.getByRole('group', { name: t.documents.tabsLabel });
  await expect(tabs.getByRole('button', { name: `${t.documents.tabAll} ${clients.length + providers.length}` })).toHaveAttribute('aria-pressed', 'true');
  expect(await folderNames(page)).toEqual(expectedOrder(clients, providers));
  // Debajo de cada carpeta, lo pendiente en euros o "Niets openstaand"; encima, la prioridad
  // solo cuando pide algo.
  const jv = providers.find((p) => p.nombre.startsWith('J. Voorbeeld'))!;
  const jvCell = grid(page).getByRole('listitem', { name: jv.nombre, exact: true });
  await expect(jvCell).toContainText(fill(t.documents.outstanding, { amount: euro(jv.deuda_cent) }));
  for (const party of [...clients, ...providers]) {
    const cell = grid(page).getByRole('listitem', { name: party.nombre, exact: true });
    await expect(cell.locator('[data-slot="status"]')).toHaveCount(party.nivel === 'normal' ? 0 : 1);
    if (party.deuda_cent === 0) await expect(cell).toContainText(t.documents.nothingOpen);
    else await expect(cell).toContainText(fill(t.documents.outstanding, { amount: euro(party.deuda_cent) }));
  }
  await expectAccessible(page, 'documenten');
  await expectNoLeftovers(page, 'nl', 'documenten');

  // Las pestanas.
  await tabs.getByRole('button', { name: new RegExp(`^${t.documents.clients}`) }).click();
  expect(await folderNames(page, t.documents.clients)).toEqual(expectedOrder(clients, []));
  await tabs.getByRole('button', { name: new RegExp(`^${t.documents.providers}`) }).click();
  expect(await folderNames(page, t.documents.providers)).toEqual(expectedOrder([], providers));
  await tabs.getByRole('button', { name: new RegExp(`^${t.documents.tabAll}`) }).click();

  // El buscador (la pista de los 12 s del prototipo es ahora su texto): nombre o codigo, sin
  // mayusculas; nada que coincida lo dice y se limpia con un clic.
  const search = page.getByRole('searchbox', { name: t.documents.searchLabel });
  await expect(search).toHaveAttribute('placeholder', t.documents.search);
  await search.fill('PROEF');
  expect(await folderNames(page)).toEqual(['Proefwacht Security VOF']);
  await search.fill('zzzz');
  await expect(page.getByRole('heading', { name: t.documents.noMatch })).toBeVisible();
  await page.getByRole('button', { name: t.documents.clearSearch }).click();
  await expect(search).toHaveValue('');
  expect((await folderNames(page)).length).toBe(clients.length + providers.length);

  // Pasar por encima de una carpeta lee sus documentos: asoman las hojas (cerrada, no se
  // pueden pulsar).
  await folder(page, jv.nombre).hover();
  const sheets = page.getByRole('list', { name: fill(t.aurora.folder.filesOf, { name: jv.nombre }) });
  await expect(sheets.locator('[role="listitem"]')).toHaveCount(Math.min(4, jv.documentos ?? 0));

  // La carpeta de cristal abre la carpeta: migas, la ficha de solo lectura arriba (sin
  // desplazar) y sus documentos al lado.
  await openFolder(page, jv.nombre);
  expect(await crumbs(page)).toEqual([t.nav.documents.label, jv.nombre]);
  await expect(folder(page, jv.nombre)).toHaveAttribute('aria-expanded', 'true');
  const card = profile(page, jv.nombre);
  await expect(card).toBeInViewport();
  await expect(card).toContainText(t.documents.profileProvider);
  for (const label of [t.documents.exactCode, t.documents.btwId, t.documents.kvk, t.parties.paymentTerm, t.parties.outstanding, t.parties.overdueColumn, t.documents.paysProvider, t.columns.priority, t.documents.account, t.documents.phone]) {
    await expect(card.getByRole('term').filter({ hasText: new RegExp(`^${escapeRegExp(label)}$`) })).toHaveCount(1);
  }
  await expect(card).toContainText('30002');
  await expect(card).toContainText('NL999000102B01');
  // El IBAN del registro con su estado y el telefono de los maestros; solo se mira: se verifica
  // en IBAN-controles.
  await expect(card).toContainText(/NL\d\dDEMO\d{10}/);
  await expect(card.getByRole('definition').filter({ hasText: /NL\d\dDEMO/ }).locator('[data-slot="status"]').first()).toBeVisible();
  await expect(card).toContainText(t.documents.ibanReadOnly);
  await expect(card.getByRole('textbox')).toHaveCount(0);
  // Los documentos: uno por fila (un tipo solo: sin filtro).
  const docs = card.getByRole('button', { name: new RegExp(`^${escapeRegExp(fill(t.documents.previewNamed, { name: '' }))}`) });
  await expect(docs).toHaveCount(jv.documentos ?? 0);
  await expect(card.getByRole('group', { name: t.documents.typeFilter })).toHaveCount(0);
  await expectAccessible(page, 'map van een leverancier');
  await expectNoLeftovers(page, 'nl', 'map van een leverancier');

  // "Naar IBAN-controles" lleva a su pantalla; "Terug" vuelve a la carpeta, como estaba.
  await card.getByRole('button', { name: new RegExp(`^${escapeRegExp(t.documents.toIbanChecks)}`) }).click();
  await expect(viewHeading(page, 'iban-checks')).toBeVisible();
  await go(page, 'documents');

  // "Kaart openen" abre la carpeta; en la abierta, "Kaart bekijken" lleva el foco a la ficha.
  await page.getByRole('button', { name: fill(t.aurora.archive.openProfileNamed, { name: jv.nombre }) }).click();
  await expect(profile(page, jv.nombre)).toBeVisible();
  await page.getByRole('button', { name: fill(t.aurora.archive.viewProfileNamed, { name: jv.nombre }) }).click();
  await expect(page.getByRole('heading', { level: 2, name: jv.nombre })).toBeFocused();

  // Cerrar la carpeta (otra vez la carpeta de cristal) vuelve a la rejilla.
  await folder(page, jv.nombre).click();
  await expect(viewHeading(page, 'documents')).toBeVisible();
  expect(await crumbs(page)).toEqual([]);

  // Un proveedor con dos tipos: el filtro de tipo ensena solo los que hay.
  const noord = providers.find((p) => p.nombre.startsWith('Demo Beveiligingsdiensten Noord'))!;
  await openFolder(page, noord.nombre);
  const types = profile(page, noord.nombre).getByRole('group', { name: t.documents.typeFilter });
  await expect(types.getByRole('button')).toHaveText([
    `${t.documents.allTypes}3`,
    `${t.documents.types.factura_compra}2`,
    `${t.documents.types.abono_compra}1`,
  ]);
  await types.getByRole('button', { name: new RegExp(`^${escapeRegExp(t.documents.types.abono_compra)}`) }).click();
  await expect(profile(page, noord.nombre).getByRole('button', { name: /^Voorbeeld van / })).toHaveText([/DBN-CR-2026-09/]);
  await types.getByRole('button', { name: new RegExp(`^${t.documents.allTypes}`) }).click();
  await expect(profile(page, noord.nombre).getByRole('button', { name: /^Voorbeeld van / })).toHaveCount(3);

  // Otra carpeta desde la rejilla: un paso, no dos (las migas no crecen).
  const havenRow = clients.find((c) => c.nombre.startsWith('Demo Havenbedrijf'))!;
  await openFolder(page, havenRow.nombre);
  expect(await crumbs(page)).toEqual([t.nav.documents.label, havenRow.nombre]);
  // Un cliente sin documentos: la suricata y lo que pasa; sus Objects y sus PO abren su ficha.
  const haven = profile(page, havenRow.nombre);
  await expect(haven).toContainText(t.documents.empty);
  await expect(haven.getByRole('img', { name: t.aurora.meerkat })).toBeVisible();
  await expect(haven).toContainText(t.documents.paysClient);
  await haven.getByRole('button', { name: fill(t.common.openRecord, { what: `${t.records.object.label} HAVEN-NOORD` }) }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Haventerrein Demo-Noord' })).toBeVisible();
  expect(await crumbs(page)).toEqual([t.nav.documents.label, havenRow.nombre, 'HAVEN-NOORD']);
  await back(page);
  await haven.getByRole('button', { name: fill(t.common.openRecord, { what: `${t.records['purchase-order'].label} PO-DEMO-4501` }) }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'PO-DEMO-4501' })).toBeVisible();
  await back(page);
  await expectAccessible(page, 'map van een klant');
  // La ficha completa vive en su seccion (Te ontvangen › Klanten).
  await haven.getByRole('button', { name: new RegExp(`^${escapeRegExp(t.documents.fullCard)}`) }).click();
  await expect(page.getByRole('heading', { level: 1, name: havenRow.nombre })).toBeVisible();
  expect(await crumbs(page)).toEqual([t.areas.receivables.label, t.nav.clients.label, havenRow.nombre]);

  // El orbe de la cabecera lleva al inicio.
  await go(page, 'documents');
  await page.getByRole('button', { name: t.aurora.archive.home }).click();
  await expect(viewHeading(page, 'home')).toBeVisible();
});

test('la vista previa: dibujada desde el registro, se cierra de tres formas y baja el original', async ({ page, baseUrl, request }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const { providers } = await lists(request, baseUrl);
  const jv = providers.find((p) => p.nombre.startsWith('J. Voorbeeld'))!;
  await go(page, 'documents');
  await openFolder(page, jv.nombre);
  const card = profile(page, jv.nombre);

  // La hoja del abanico (el camino mas corto) abre su vista previa.
  const sheets = page.getByRole('list', { name: fill(t.aurora.folder.filesOf, { name: jv.nombre }) });
  await sheets.getByRole('button').last().click();
  const sheet = preview(page);
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText(t.documents.previewEyebrow.toUpperCase().slice(0, 8), { ignoreCase: true });
  await expect(sheet.getByRole('heading', { level: 2 })).toHaveText(/^Inkoopfactuur JV-2026-00\d$/);
  // Desde el registro: los importes de la factura, su estado y sus avisos, nunca "MUESTRA".
  for (const label of [t.documents.number, t.documents.invoiceDate, t.documents.due, t.documents.base, t.documents.vat, t.documents.total, t.parties.outstanding, t.documents.state, t.documents.payments, t.documents.warnings, t.documents.file]) {
    await expect(sheet.getByRole('term').filter({ hasText: new RegExp(`^${escapeRegExp(label)}$`) })).toHaveCount(1);
  }
  await expect(sheet).not.toContainText(/muestra|monster|sample/i);
  await expect(sheet).toContainText(t.documents.previewNote);
  await expectAccessible(page, 'voorbeeld van een document');
  await expectNoLeftovers(page, 'nl', 'voorbeeld van een document');
  // La X la cierra y el foco vuelve a la hoja que la abrio.
  await sheet.getByRole('button', { name: t.aurora.archive.closePreview }).click();
  await expect(sheet).toBeHidden();
  await expect(sheets.getByRole('button').last()).toBeFocused();

  // La fila abre la vista previa; Escape la cierra.
  const rows = card.getByRole('button', { name: /^Voorbeeld van Inkoopfactuur / });
  await rows.nth(3).click();
  await expect(sheet).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
  await expect(rows.nth(3)).toBeFocused();
  // Un clic fuera de la hoja la cierra.
  await rows.nth(3).click();
  await expect(sheet).toBeVisible();
  await page.mouse.click(8, 450);
  await expect(sheet).toBeHidden();

  // Una pagada dice segun quien: el banco, con su fecha.
  const paid = card.getByRole('button', { name: 'Voorbeeld van Inkoopfactuur JV-2026-001' });
  await paid.click();
  await expect(sheet).toContainText(/Betaald volgens de bank op \d\d-\d\d-2026/);
  await expect(sheet).toContainText(/Bank · (Bevestigd|Confirmed)/);
  // "Origineel downloaden": el PDF de verdad (con el token, y queda en la auditoria).
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    sheet.getByRole('button', { name: fill(t.documents.downloadNamed, { name: 'Inkoopfactuur JV-2026-001' }) }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  expect(await pdfOf(download)).toBe('%PDF-');
  // "Factuur openen": la ficha de la factura, dentro de Documenten; "Terug" vuelve a la carpeta.
  await sheet.getByRole('button', { name: t.documents.openInvoice }).click();
  await expect(page.getByRole('heading', { level: 1, name: /^Factuur JV-2026-001/ })).toBeVisible();
  const trail = await crumbs(page);
  expect(trail.slice(0, 2)).toEqual([t.nav.documents.label, jv.nombre]);
  expect(trail[2]).toMatch(/JV-2026-001/);
  await back(page);
  await expect(profile(page, jv.nombre)).toBeVisible();
  await expect(preview(page)).toBeHidden();

  // La descarga de la fila, sin abrir la vista previa.
  const [fromRow] = await Promise.all([
    page.waitForEvent('download'),
    card.getByRole('button', { name: fill(t.documents.downloadNamed, { name: 'Inkoopfactuur JV-2026-002' }) }).click(),
  ]);
  expect(await pdfOf(fromRow)).toBe('%PDF-');
});

test('el arbol "Verkennen" con el teclado: flechas, Home, End, una letra e Intro', async ({ page, baseUrl, request }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const { clients, providers } = await lists(request, baseUrl);
  await go(page, 'documents');
  const tree = page.getByRole('tree', { name: t.aurora.archive.treeLabel });
  const item = (name: RegExp) => tree.getByRole('treeitem', { name });
  // La entrada al arbol es lo que se ve (Documenten, todas las carpetas).
  const all = item(new RegExp(`^${t.nav.documents.label}`));
  await expect(all).toHaveAttribute('aria-selected', 'true');
  await expect(all).toHaveAttribute('tabindex', '0');
  await all.focus();
  // Abajo: Klanten (con el foco a la vista); Home: Start; End: la ultima carpeta.
  await page.keyboard.press('ArrowDown');
  await expect(item(new RegExp(`^${t.documents.clients}`))).toBeFocused();
  expect(await page.evaluate(() => getComputedStyle(document.activeElement!).boxShadow)).not.toBe('none');
  await page.keyboard.press('Home');
  await expect(item(new RegExp(`^${t.areas.home.label}`))).toBeFocused();
  await page.keyboard.press('End');
  const last = expectedOrder([], providers).at(-1)!;
  await expect(item(new RegExp(`^${escapeRegExp(last)}`))).toBeFocused();
  // Una letra va a la siguiente que empieza por ella.
  await page.keyboard.press('Home');
  await page.keyboard.press('l');
  await expect(item(new RegExp(`^${t.documents.providers}`))).toBeFocused();
  // Izquierda cierra el grupo; derecha lo abre.
  await page.keyboard.press('ArrowLeft');
  await expect(item(new RegExp(`^${t.documents.providers}`))).toHaveAttribute('aria-expanded', 'false');
  await page.keyboard.press('ArrowRight');
  await expect(item(new RegExp(`^${t.documents.providers}`))).toHaveAttribute('aria-expanded', 'true');
  // Derecha sobre una carpeta con documentos la abre en el arbol y los lee (por partes).
  const proef = providers.find((p) => p.nombre.startsWith('Proefwacht'))!;
  await item(new RegExp(`^${escapeRegExp(proef.nombre)}`)).focus();
  await page.keyboard.press('ArrowRight');
  await expect(item(new RegExp(`^${escapeRegExp(proef.nombre)}`))).toHaveAttribute('aria-expanded', 'true');
  const firstDoc = item(/^Inkoopfactuur PW26/).first();
  await expect(firstDoc).toBeVisible();
  // Intro sobre un documento abre su carpeta y su vista previa.
  await page.keyboard.press('ArrowDown');
  await expect(firstDoc).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { level: 1, name: fill(t.documents.folderOf, { name: proef.nombre }) })).toBeVisible();
  await expect(preview(page)).toBeVisible();
  await expect(preview(page).getByRole('heading', { level: 2 })).toHaveText(/^Inkoopfactuur PW26/);
  await page.keyboard.press('Escape');
  await expect(preview(page)).toBeHidden();
  // Intro sobre otra carpeta la abre; sobre un grupo, vuelve a la rejilla con esa pestana.
  const client = expectedOrder(clients, [])[0]!;
  await item(new RegExp(`^${escapeRegExp(client)}`)).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { level: 1, name: fill(t.documents.folderOf, { name: client }) })).toBeVisible();
  await item(new RegExp(`^${t.documents.providers}`)).focus();
  await page.keyboard.press('Enter');
  await expect(viewHeading(page, 'documents')).toBeVisible();
  await expect(page.getByRole('group', { name: t.documents.tabsLabel }).getByRole('button', { name: new RegExp(`^${t.documents.providers}`) })).toHaveAttribute('aria-pressed', 'true');
  expect(await folderNames(page, t.documents.providers)).toEqual(expectedOrder([], providers));
  await page.getByRole('group', { name: t.documents.tabsLabel }).getByRole('button', { name: new RegExp(`^${t.documents.tabAll}`) }).click();
  // Start, desde el arbol, es el inicio.
  await item(new RegExp(`^${t.areas.home.label}`)).click();
  await expect(viewHeading(page, 'home')).toBeVisible();
});

test('las doce primeras y "Ver todas", el archivo vacio y una carpeta que no se pudo leer', async ({ page, baseUrl, watch }) => {
  // Mas proveedores de los que tiene la base de prueba: la respuesta de verdad, con diez mas
  // sin nada pendiente (van al final).
  await page.route('**/api/v2/proveedores', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { proveedores: Row[] };
    const extra = Array.from({ length: 10 }, (_, i) => ({
      ...body.proveedores[0]!,
      id: 9001 + i,
      nombre: `Proefmap ${String(i + 1).padStart(2, '0')}`,
      exact_id: null,
      pendiente_cent: 0,
      deuda_cent: 0,
      abonos_sin_enlazar_cent: 0,
      abonos_sin_enlazar_facturas: 0,
      vencido_cent: 0,
      nivel: 'normal',
      razones: [],
      documentos: 0,
    }));
    await route.fulfill({ response, json: { ...body, proveedores: [...body.proveedores, ...extra] } });
  });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'documents');
  const total = await page
    .getByRole('group', { name: t.documents.tabsLabel })
    .getByRole('button', { name: new RegExp(`^${t.documents.tabAll}`) })
    .textContent();
  const n = Number(/(\d+)/.exec(total ?? '')![1]);
  expect(n).toBeGreaterThan(12);
  expect((await folderNames(page)).length).toBe(12);
  await page.getByRole('button', { name: fill(t.documents.showAll, { n }) }).click();
  expect((await folderNames(page)).length).toBe(n);
  expect((await folderNames(page)).slice(-10)).toEqual(Array.from({ length: 10 }, (_, i) => `Proefmap ${String(i + 1).padStart(2, '0')}`));
  await expect(page.getByRole('button', { name: fill(t.documents.showAll, { n }) })).toHaveCount(0);
  await page.unroute('**/api/v2/proveedores');

  // Una carpeta cuyos documentos no se pudieron leer: lo dice, con su reintento.
  watch.expectHttpErrors(500);
  let failing = true;
  await page.route('**/api/v2/proveedores/*/documentos', (route) =>
    failing ? route.fulfill({ status: 500, json: { error: 'fallo de prueba', codigo: 'interno' } }) : route.continue()
  );
  await go(page, 'documents');
  const proef = 'Proefwacht Security VOF';
  await openFolder(page, proef);
  const card = profile(page, proef);
  await expect(card.getByRole('alert')).toBeVisible();
  failing = false;
  await card.getByRole('button', { name: t.common.retry }).click();
  await expect(card.getByRole('button', { name: /^Voorbeeld van Inkoopfactuur PW26/ })).toHaveCount(2);
  await page.unroute('**/api/v2/proveedores/*/documentos');

  // Sin clientes ni proveedores: la suricata y lo que pasa.
  await page.route('**/api/v2/clientes', (route) => route.fulfill({ json: { clientes: [] } }));
  await page.route('**/api/v2/proveedores', (route) => route.fulfill({ json: { proveedores: [] } }));
  await go(page, 'documents');
  await expect(page.getByText(t.documents.noFolders)).toBeVisible();
  await expect(page.getByRole('img', { name: t.aurora.meerkat })).toBeVisible();
});

test('capturas del archivo en los tres idiomas y los dos temas, y en el movil', async ({ page, baseUrl }) => {
  test.setTimeout(420_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const lang of ['es', 'nl', 'en'] as const) {
    const tx = TEXTS[lang];
    await setLang(page, lang);
    for (const theme of ['dark', 'light'] as const) {
      await chooseTheme(page, theme);
      await go(page, 'documents', lang);
      await artReady(page);
      await expectAccessible(page, `${lang} ${theme} documentos`);
      await expectNoLeftovers(page, lang, `${lang} ${theme} documentos`);
      await capture(page, `${lang}-documentos`);
      const name = 'J. Voorbeeld Beveiliging (zzp)';
      await page.getByRole('button', { name: fill(tx.aurora.archive.openProfileNamed, { name }) }).click();
      await expect(page.getByRole('region', { name, exact: true })).toBeVisible();
      await artReady(page);
      await expectAccessible(page, `${lang} ${theme} carpeta de un proveedor`);
      await expectNoLeftovers(page, lang, `${lang} ${theme} carpeta de un proveedor`);
      await capture(page, `${lang}-documentos-proveedor`);
      await page.getByRole('region', { name, exact: true }).getByRole('button', { name: fill(tx.documents.previewNamed, { name: `${tx.documents.types.factura_compra} JV-2026-001` }) }).click();
      await expect(page.getByRole('dialog')).toContainText(/JV-2026-001/);
      await expect(page.getByRole('dialog').getByRole('term')).toHaveCount(12);
      await expectAccessible(page, `${lang} ${theme} vista previa`);
      await expectNoLeftovers(page, lang, `${lang} ${theme} vista previa`);
      await capture(page, `${lang}-documentos-vista-previa`);
      await page.keyboard.press('Escape');
      // Un cliente sin documentos (la suricata quieta: con menos movimiento sale ya sentada).
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const client = 'Demo Havenbedrijf BV';
      await page.getByRole('button', { name: fill(tx.aurora.archive.openProfileNamed, { name: client }) }).click();
      await expect(page.getByRole('region', { name: client, exact: true })).toContainText(tx.documents.empty);
      await artReady(page);
      await expectAccessible(page, `${lang} ${theme} carpeta de un cliente`);
      await expectNoLeftovers(page, lang, `${lang} ${theme} carpeta de un cliente`);
      await capture(page, `${lang}-documentos-cliente`);
      await page.emulateMedia({ reducedMotion: 'no-preference' });
    }
  }
  // En el movil, en castellano y oscuro: nada se sale por el lado.
  await chooseTheme(page, 'dark');
  await setLang(page, 'es');
  await page.setViewportSize({ width: 400, height: 860 });
  await go(page, 'documents', 'es');
  await artReady(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await capture(page, 'es-movil-documentos');
  await page.getByRole('button', { name: fill(TEXTS.es.aurora.archive.openProfileNamed, { name: 'J. Voorbeeld Beveiliging (zzp)' }) }).click();
  await expect(page.getByRole('region', { name: 'J. Voorbeeld Beveiliging (zzp)', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await capture(page, 'es-movil-documentos-proveedor');
  await page.getByRole('region', { name: 'J. Voorbeeld Beveiliging (zzp)', exact: true }).getByRole('button', { name: /^Vista previa de / }).first().click();
  await expect(page.getByRole('dialog').getByRole('button', { name: /^Descargar / })).toBeInViewport();
  await capture(page, 'es-movil-documentos-vista-previa');
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1440, height: 900 });
  await setLang(page, 'nl');
});
