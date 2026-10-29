// Documentos de Aurora con datos de verdad (paso 17, especificacion §2.3 y D-37…D-45): el vuelo
// del orbe a la esquina y de vuelta; el companero de la esquina (un solo orbe); el antetitulo, el
// titulo y la linea de Aurora; el arbol "Verkennen" con el raton y con el teclado; la rejilla de
// carpetas de cristal con las 12 que piden atencion (las demas, en el arbol, y lo dice el pie); la
// prioridad en la carpeta y su pie (el importe o "Bij", y "Kaart openen"); la ficha debajo de la
// rejilla, con sus documentos, sus Objects y sus PO; la hoja en el <dialog> (dibujada desde el
// registro), que se cierra con la ✕, Escape o un clic fuera; "Origineel downloaden" (el PDF de
// verdad, que queda en la auditoria); un error con su reintento. Capturas en los tres idiomas y
// los dos temas, y en el movil. La hoja de una factura con mas de cuatro filas, plegada al abrirla
// tras un solo control (decision del dueno del 29-10-2026), con el raton y con el teclado.
import { readFileSync } from 'node:fs';
import type { APIRequestContext, Download, Page } from '@playwright/test';
import type { InvoiceRow } from '../src/lib/api';
import type { InvoiceDetail, PartyRow } from '../src/lib/api-types';
import { capture, expect, expectAccessible, expectNoLeftovers, login, outsideTheWindow, settled, test, token } from './fixtures';
import {
  TEXTS,
  auroraRoot,
  chooseTheme,
  crumbs,
  entryButton,
  escapeRegExp,
  euro,
  fill,
  folderCell,
  folderProfile,
  greeting,
  landed,
  openDocuments,
  openFolder,
  openInvoice,
  openMenu,
  profileRow,
  setLang,
  sheetDialog,
  sheetFold,
  treeItem,
} from './nav';

const t = TEXTS.nl;
const a = t.aurora.archive;
const JV = 'J. Voorbeeld Beveiliging (zzp)';
const HAVEN = 'Demo Havenbedrijf BV';

async function lists(request: APIRequestContext, baseUrl: string): Promise<{ clients: PartyRow[]; providers: PartyRow[] }> {
  const headers = { 'X-BMS-Token': token('ana') };
  const clients = ((await (await request.get(`${baseUrl}/api/v2/clientes`, { headers })).json()) as { clientes: PartyRow[] }).clientes;
  const providers = ((await (await request.get(`${baseUrl}/api/v2/proveedores`, { headers })).json()) as { proveedores: PartyRow[] }).proveedores;
  return { clients, providers };
}

/** Las carpetas en el orden de la atencion: lo vencido, luego lo pendiente, luego la API. */
function byAttention(clients: PartyRow[], providers: PartyRow[]): string[] {
  return [...clients, ...providers]
    .map((row, index) => ({ row, index }))
    .sort((x, y) => Math.max(0, y.row.vencido_cent) - Math.max(0, x.row.vencido_cent) || Math.max(0, y.row.deuda_cent) - Math.max(0, x.row.deuda_cent) || x.index - y.index)
    .map((x) => x.row.nombre);
}

const folderNames = (page: Page) => page.locator('.ws-grid [data-testid="folder-cell"] .gf-title').allTextContents();

/** Las carpetas pintadas del todo (su dorso se calcula por partes): para las capturas. */
async function artReady(page: Page): Promise<void> {
  await page.waitForFunction(() => Array.from(document.querySelectorAll('canvas.gf-art')).every((c) => c.hasAttribute('data-ready')), undefined, { timeout: 30_000 });
  await settled(page);
}

async function pdfOf(download: Download): Promise<string> {
  return readFileSync((await download.path())!).subarray(0, 5).toString('latin1');
}

test('el archivo de Aurora: el vuelo, el companero, el arbol, las doce carpetas y la ficha de verdad', async ({ page, baseUrl, request }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const { clients, providers } = await lists(request, baseUrl);
  // El vuelo del orbe a la esquina (D-45).
  await openMenu(page);
  await entryButton(page, 'documents').focus();
  await settled(page);
  await entryButton(page, 'documents').click();
  await expect(page.locator('.aurora-route-flight')).toHaveCount(1);
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await landed(page);
  // Un solo orbe: el companero de la esquina (D-37); antetitulo, titulo y linea de Aurora (D-38).
  await expect(page.locator('.ws-companion canvas')).toHaveCount(1);
  await expect(page.getByText(t.documents.eyebrow.toLocaleUpperCase(), { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(a.title);
  await expect(page.getByText(a.intro, { exact: true })).toBeVisible();
  // Ni pestanas ni buscador ni muestras que anadir (D-39): las categorias van por el arbol.
  await expect(page.getByRole('group', { name: t.documents.tabsLabel })).toHaveCount(0);
  await expect(page.getByRole('searchbox')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /muestra|monster|sample/i })).toHaveCount(0);
  expect(await crumbs(page)).toEqual([t.nav.documents.label]);

  // La rejilla: las doce que piden atencion, en su orden; el pie lo dice si hay mas (D-39, D-42).
  const order = byAttention(clients, providers);
  expect(await folderNames(page)).toEqual(order.slice(0, 12));
  const footnote = page.locator('.ws-footnote');
  await expect(footnote).toContainText(t.documents.later);
  if (order.length > 12) await expect(footnote).toContainText(a.firstTwelve);
  // Cada carpeta: la prioridad solo cuando pide algo; debajo, lo pendiente o "Bij" (D-41).
  for (const party of [...clients, ...providers].filter((p) => order.slice(0, 12).includes(p.nombre))) {
    const cell = folderCell(page, party.nombre);
    await expect(cell.locator('.gf-statuses [data-slot="status"]')).toHaveCount(party.nivel === 'normal' ? 0 : 1);
    await expect(cell.locator('.ws-folder-caption > span')).toHaveText(party.deuda_cent > 0 ? euro(party.deuda_cent) : a.upToDate);
    await expect(cell.getByRole('link', { name: fill(a.openProfileNamed, { name: party.nombre }) })).toBeVisible();
  }
  // El arbol: Start, Documenten con cuantos hay, y Klanten y Leveranciers con cuantas carpetas.
  await expect(treeItem(page, t.aurora.work.home)).toBeVisible();
  await expect(treeItem(page, t.documents.clients)).toContainText(String(clients.length));
  await expect(treeItem(page, t.documents.providers)).toContainText(String(providers.length));
  await expectAccessible(page, 'documenten');
  await expectNoLeftovers(page, 'nl', 'documenten');
  await capture(page, 'nl-documents');

  // "Kaart openen": la carpeta se abre (su abanico) y su ficha sale debajo de la rejilla (D-40).
  const jv = providers.find((p) => p.nombre === JV)!;
  await folderCell(page, JV).getByRole('link', { name: fill(a.openProfileNamed, { name: JV }) }).click();
  const profile = folderProfile(page, JV);
  await expect(profile).toBeVisible();
  expect(await crumbs(page)).toEqual([t.nav.documents.label, t.documents.providers, JV]);
  // La rejilla cambia de categoria (la de antes se va con su fundido y despues entra la otra):
  // se mide la que queda.
  await settled(page);
  await expect(page.locator('.ws-grid')).toBeVisible();
  const grid = (await page.locator('.ws-grid').boundingBox())!;
  const box = (await profile.boundingBox())!;
  expect(box.y).toBeGreaterThan(grid.y);
  await expect(folderCell(page, JV).getByRole('link', { name: fill(a.viewProfileNamed, { name: JV }) })).toBeVisible();
  await expect(page.getByRole('list', { name: fill(t.aurora.folder.filesOf, { name: JV }) }).getByRole('listitem')).toHaveCount(Math.min(4, jv.documentos ?? 0));
  // La ficha de solo lectura: lo del maestro, el IBAN con su estado y el telefono.
  await expect(profile.getByRole('heading', { level: 2 })).toHaveText(JV);
  for (const label of [t.documents.exactCode, t.parties.paymentTerm, t.parties.outstanding, t.parties.overdueColumn, t.documents.paysProvider, t.documents.account, t.documents.phone]) {
    await expect(profile.getByRole('term').filter({ hasText: new RegExp(`^${escapeRegExp(label)}$`) })).toHaveCount(1);
  }
  await expect(profile).toContainText('30002');
  await expect(profile).toContainText('NL999000102B01');
  await expect(profile).toContainText(/NL\d\dDEMO\d{10}/);
  await expect(profile.getByRole('definition').filter({ hasText: /NL\d\dDEMO/ }).locator('[data-slot="status"]').first()).toBeVisible();
  await expect(profile.getByRole('textbox')).toHaveCount(0);
  // Sus documentos, uno por fila.
  await expect(profile.locator('.ws-file-table > a')).toHaveCount(jv.documentos ?? 0);
  await expectAccessible(page, 'map van een leverancier');
  await expectNoLeftovers(page, 'nl', 'map van een leverancier');
  await capture(page, 'nl-documents-provider');
  // "Kaart bekijken" lleva el foco a la ficha.
  await folderCell(page, JV).getByRole('link', { name: fill(a.viewProfileNamed, { name: JV }) }).click();
  // Cerrar la carpeta (la carpeta de cristal) vuelve a la rejilla de su categoria.
  await page.getByRole('button', { name: fill(t.aurora.folder.closeNamed, { name: JV }) }).click();
  await expect(profile).toHaveCount(0);
  expect(await crumbs(page)).toEqual([t.nav.documents.label, t.documents.providers]);

  // Un cliente sin documentos: lo dice; sus Objects y sus PO abren su hoja (sin suricata, D-44).
  const haven = await openFolder(page, HAVEN, 'client');
  await expect(haven).toContainText(t.documents.paysClient);
  await expect(page.locator('.meerkat, [class*="meerkat"]')).toHaveCount(0);
  await profileRow(page, `${t.records.object.label} HAVEN-NOORD`).click();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('HAVEN-NOORD');
  expect((await crumbs(page)).at(-1)).toBe(t.records.object.label);
  await page.keyboard.press('Escape');
  await profileRow(page, `${t.records['purchase-order'].label} PO-DEMO-4501`).click();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('PO-DEMO-4501');
  await page.keyboard.press('Escape');
  await expectAccessible(page, 'map van een klant');

  // El companero de la esquina lleva al inicio de Aurora, con el vuelo de vuelta.
  await page.getByRole('link', { name: a.home }).click();
  await expect(page.locator('.aurora-route-flight')).toHaveCount(1);
  await landed(page);
  await expect(greeting(page)).toBeVisible();
  // El nodo "Start" del arbol, tambien (sin vuelo).
  await openDocuments(page);
  await treeItem(page, t.aurora.work.home).click();
  await expect(greeting(page)).toBeVisible();
});

test('la hoja: dibujada desde el registro, se cierra de tres formas y baja el original auditado', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openDocuments(page);
  await openFolder(page, JV, 'provider');

  // La hoja del abanico (el camino mas corto) abre su hoja.
  const fan = page.getByRole('list', { name: fill(t.aurora.folder.filesOf, { name: JV }) });
  await fan.getByRole('button').last().click();
  const sheet = sheetDialog(page);
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('.ws-dialog-top')).toContainText(t.documents.types.factura_compra.toLocaleUpperCase());
  await expect(sheet.getByRole('heading', { level: 2 })).toHaveText(/^JV-2026-00\d$/);
  // Desde el registro: fecha, vencimiento, base, IVA, total, pendiente, estado y pagos; sin
  // muestras; la marca de agua es la de la base de prueba.
  for (const label of [t.documents.invoiceDate, t.documents.due, t.documents.base, t.documents.vat, t.documents.total, t.parties.outstanding, t.documents.state, t.documents.payments]) {
    await expect(sheet.getByRole('term').filter({ hasText: new RegExp(`^${escapeRegExp(label)}$`) })).toHaveCount(1);
  }
  await expect(sheet).not.toContainText(/muestra|monster|sample/i);
  await expect(sheet).toContainText(a.drawn);
  await expect(sheet.locator('.ws-watermark')).toHaveText(a.watermark);
  await expectAccessible(page, 'hoja van een factuur');
  await expectNoLeftovers(page, 'nl', 'hoja van een factuur');
  await capture(page, 'nl-documents-sheet');
  // La ✕ la cierra (la carpeta sigue abierta).
  await sheet.getByRole('button', { name: a.closePreview }).click();
  await expect(sheet).toHaveCount(0);
  await expect(folderProfile(page, JV)).toBeVisible();

  // La fila abre la hoja; Escape la cierra; un clic fuera, tambien.
  const rows = profileRow(page, /^Inkoopfactuur JV-2026-/);
  await rows.nth(1).click();
  await expect(sheet).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  await rows.nth(1).click();
  await expect(sheet).toBeVisible();
  await page.mouse.click(8, 450);
  await expect(sheet).toHaveCount(0);

  // Una pagada dice segun quien: el banco, con su fecha.
  await profileRow(page, 'Inkoopfactuur JV-2026-001').click();
  await expect(sheet.getByTestId('paid-source')).toContainText(/Betaald volgens de bank op \d\d-\d\d-2026/);
  await expect(sheet.getByTestId('payment').first()).toContainText(/Bank · (Bevestigd|Confirmed)/);
  // "Origineel downloaden": el PDF de verdad, con el token, y queda en la auditoria.
  const [download] = await Promise.all([page.waitForEvent('download'), sheet.getByRole('button', { name: t.aurora.card.downloadOriginal }).click()]);
  expect(download.suggestedFilename()).toBe('JV-2026-001.pdf');
  expect(await pdfOf(download)).toBe('%PDF-');
});

test('el arbol "Verkennen" con el teclado: flechas, Home, End, una letra e Intro', async ({ page, baseUrl, request }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const { clients, providers } = await lists(request, baseUrl);
  await openDocuments(page);
  const tree = page.getByRole('tree', { name: a.treeLabel });
  const item = (name: RegExp) => tree.getByRole('treeitem', { name });
  // La entrada al arbol es lo que se ve (Documenten, todas las carpetas).
  const all = item(new RegExp(`^${t.nav.documents.label}`));
  await expect(all).toHaveAttribute('aria-selected', 'true');
  await expect(all).toHaveAttribute('tabindex', '0');
  await all.focus();
  // Abajo: Klanten (con el foco a la vista); Home: Start; End: la ultima.
  await page.keyboard.press('ArrowDown');
  await expect(item(new RegExp(`^${t.documents.clients}`))).toBeFocused();
  expect(await page.evaluate(() => getComputedStyle(document.activeElement!).boxShadow)).not.toBe('none');
  await page.keyboard.press('Home');
  await expect(item(new RegExp(`^${t.aurora.work.home}`))).toBeFocused();
  await page.keyboard.press('End');
  await expect(tree.getByRole('treeitem').last()).toBeFocused();
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
  // Intro sobre un documento abre su carpeta y su hoja.
  await page.keyboard.press('ArrowDown');
  await expect(firstDoc).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(folderProfile(page, proef.nombre)).toBeVisible();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText(/^PW26/);
  await page.keyboard.press('Escape');
  await expect(sheetDialog(page)).toHaveCount(0);
  // Intro sobre otra carpeta la abre; sobre un grupo, vuelve a la rejilla de ese grupo.
  const client = byAttention(clients, [])[0]!;
  await item(new RegExp(`^${escapeRegExp(client)}`)).focus();
  await page.keyboard.press('Enter');
  await expect(folderProfile(page, client)).toBeVisible();
  await item(new RegExp(`^${t.documents.providers}`)).focus();
  await page.keyboard.press('Enter');
  expect(await crumbs(page)).toEqual([t.nav.documents.label, t.documents.providers]);
  await expect.poll(() => folderNames(page)).toEqual(byAttention([], providers).slice(0, 12));
  // Start, desde el arbol, es el inicio de Aurora.
  await item(new RegExp(`^${t.aurora.work.home}`)).click();
  await expect(greeting(page)).toBeVisible();
});

test('las doce primeras, todas en el arbol; una carpeta que no se pudo leer; el archivo vacio', async ({ page, baseUrl, watch }) => {
  // Mas proveedores de los que tiene la base de prueba: la respuesta de verdad, con diez mas sin
  // nada pendiente (van al final).
  await page.route('**/api/v2/proveedores', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { proveedores: PartyRow[] };
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
  await openDocuments(page);
  expect((await folderNames(page)).length).toBe(12);
  await expect(page.locator('.ws-footnote')).toContainText(a.firstTwelve);
  // Las demas, en el arbol: una de las de mas abre su carpeta (y sale en la rejilla). Son de
  // mentira: el servidor no las conoce (404 en su ficha y sus documentos).
  watch.expectHttpErrors(404);
  await openFolder(page, 'Proefmap 10', 'provider');
  expect(await folderNames(page)).toContain('Proefmap 10');
  await page.unroute('**/api/v2/proveedores');

  // Una carpeta cuyos documentos no se pudieron leer: lo dice, con su reintento.
  watch.expectHttpErrors(500);
  let failing = true;
  await page.route('**/api/v2/proveedores/*/documentos', (route) =>
    failing ? route.fulfill({ status: 500, json: { error: 'fallo de prueba', codigo: 'interno' } }) : route.continue()
  );
  await openDocuments(page);
  const proef = 'Proefwacht Security VOF';
  const profile = await openFolder(page, proef, 'provider');
  await expect(profile.getByRole('alert')).toBeVisible();
  failing = false;
  await profile.getByRole('button', { name: t.common.retry }).click();
  await expect(profileRow(page, /^Inkoopfactuur PW26/)).toHaveCount(2);
  await page.unroute('**/api/v2/proveedores/*/documentos');

  // Sin clientes ni proveedores: lo vacio de Aurora (ws-empty), sin suricata.
  await page.route('**/api/v2/clientes', (route) => route.fulfill({ json: { clientes: [] } }));
  await page.route('**/api/v2/proveedores', (route) => route.fulfill({ json: { proveedores: [] } }));
  await openDocuments(page);
  await expect(page.locator('.ws-empty')).toContainText(t.documents.noFolders);
  await expect(page.locator('.meerkat, [class*="meerkat"]')).toHaveCount(0);
});

/** Lo que dice el control plegado de una factura de la API: cuantas filas quedan detras y cuantas
 *  de ellas son un aviso (un hallazgo abierto o desaparecido, o la excepcion abierta). Las filas
 *  van de la mas urgente a la menos (especificacion §2.3): hallazgos, pagos y enlaces propuestos,
 *  la excepcion, la revision y las dos de siempre. */
function foldExpected(f: InvoiceDetail, lang: 'nl' | 'es' | 'en'): { rows: number; label: string } {
  const s = TEXTS[lang].aurora.sheet;
  const findings = f.hallazgos.filter((h) => h.estado === 'abierto' || h.estado === 'desaparecido').length;
  const before = findings + (f.pagos ?? []).filter((p) => p.estado === 'propuesta').length + f.relaciones.filter((r) => !r.retirada && r.estado === 'propuesta').length;
  const exception = f.excepcion && f.excepcion.estado !== 'resuelta' ? 1 : 0;
  const review = !f.anulada && f.estado?.estado_revision !== 'revisada' ? 1 : 0;
  const rows = before + exception + review + 2;
  const hidden = rows - 3;
  const attention = Math.max(0, findings - 3) + (exception && before >= 3 ? 1 : 0);
  const more = hidden === 1 ? s.foldMoreOne : fill(s.foldMore, { n: hidden });
  const label = attention === 0 ? more : `${more} · ${attention === 1 ? s.foldAttentionOne : fill(s.foldAttention, { n: attention })}`;
  return { rows, label };
}

test('la hoja de una factura con mas de cuatro filas: plegada al abrirla, un solo control, con el raton y con el teclado', async ({ page, baseUrl, request }) => {
  test.setTimeout(300_000);
  const headers = { 'X-BMS-Token': token('ana') };
  const list = ((await (await request.get(`${baseUrl}/api/v2/facturas`, { headers })).json()) as { facturas: InvoiceRow[] }).facturas;
  const id = list.find((f) => f.numero === 'DBO-2026-0417')!.id;
  const dbo = ((await (await request.get(`${baseUrl}/api/v2/facturas/${id}`, { headers })).json()) as { factura: InvoiceDetail }).factura;
  const expected = foldExpected(dbo, 'nl');
  expect(expected.rows).toBe(8);
  await page.goto(`${baseUrl}/app`);
  await login(page);

  // Plegada: tres filas, la cuenta de todas en la cabecera y el control en la cuarta linea; el
  // papel con sus totales, entero encima.
  let sheet = await openInvoice(page, 'DBO-2026-0417');
  const rows = sheet.locator('.ws-file-table > a');
  const fold = sheetFold(page);
  await expect(rows).toHaveCount(3);
  await expect(sheet.locator('.ws-file-table > .ws-table-head').first().locator('span').last()).toHaveText('8');
  await expect(fold).toHaveAttribute('aria-expanded', 'false');
  await expect(fold).toHaveText(expected.label);
  const controls = await fold.getAttribute('aria-controls');
  expect(await sheet.locator('.ws-file-table').getAttribute('id')).toBe(controls);
  for (const label of [t.documents.base, t.documents.vat, t.documents.total, t.parties.outstanding]) {
    await expect(sheet.getByRole('term').filter({ hasText: new RegExp(`^${escapeRegExp(label)}$`) })).toBeVisible();
  }
  await expectAccessible(page, 'hoja plegada');
  await expectNoLeftovers(page, 'nl', 'hoja plegada');
  await capture(page, 'nl-hoja-plegada');

  // Con el raton: se despliega (las ocho, el foco en la primera que estaba plegada) y se pliega.
  await fold.click();
  await expect(fold).toHaveAttribute('aria-expanded', 'true');
  await expect(fold).toHaveText(t.aurora.sheet.foldLess);
  await expect(rows).toHaveCount(8);
  await expect(rows.nth(3)).toBeFocused();
  await expectAccessible(page, 'hoja desplegada');
  await capture(page, 'nl-hoja-desplegada');
  // La tarjeta de una fila que se pliega se cierra con ella.
  await rows.last().click();
  await expect(sheet.locator('.detail')).toBeVisible();
  await fold.click();
  await expect(fold).toHaveAttribute('aria-expanded', 'false');
  await expect(rows).toHaveCount(3);
  await expect(sheet.locator('.detail')).toHaveCount(0);
  await expect(fold).toHaveText(expected.label);

  // Con el teclado: Intro despliega; Tab recorre las cinco que estaban plegadas y llega al
  // control; Espacio pliega y el foco se queda en el.
  await fold.focus();
  await page.keyboard.press('Enter');
  await expect(fold).toHaveAttribute('aria-expanded', 'true');
  await expect(rows.nth(3)).toBeFocused();
  for (let i = 4; i < 8; i += 1) {
    await page.keyboard.press('Tab');
    await expect(rows.nth(i)).toBeFocused();
  }
  await page.keyboard.press('Tab');
  await expect(fold).toBeFocused();
  await page.keyboard.press(' ');
  await expect(fold).toHaveAttribute('aria-expanded', 'false');
  await expect(rows).toHaveCount(3);
  await expect(fold).toBeFocused();

  // Desplegar es de esa vez: cerrada y vuelta a abrir, otra vez plegada.
  await fold.click();
  await expect(fold).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Escape');
  await expect(sheetDialog(page)).toHaveCount(0);
  sheet = await openInvoice(page, 'DBO-2026-0417');
  await expect(sheetFold(page)).toHaveAttribute('aria-expanded', 'false');
  await expect(sheet.locator('.ws-file-table > a')).toHaveCount(3);

  // Con cuatro filas o menos, como antes: todas y ningun control.
  for (const [number, n] of [['JV-2026-006', 4], ['JV-2026-003', 3]] as const) {
    sheet = await openInvoice(page, number);
    await expect(sheet.locator('.ws-file-table > a')).toHaveCount(n);
    await expect(sheet.getByTestId('sheet-fold')).toHaveCount(0);
  }

  // En castellano, en el movil y con «menos movimiento»: lo mismo, sin animacion al plegar.
  await setLang(page, 'es');
  await page.setViewportSize({ width: 400, height: 860 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  sheet = await openInvoice(page, 'DBO-2026-0417', { lang: 'es' });
  await expect(sheetFold(page)).toHaveText(foldExpected(dbo, 'es').label);
  await capture(page, 'es-movil-hoja-plegada');
  await sheetFold(page).click();
  await expect(sheet.locator('.ws-file-table > a')).toHaveCount(8);
  expect(await sheet.evaluate((d) => d.getAnimations({ subtree: true }).filter((a) => a.playState === 'running').length)).toBe(0);
  await expect(sheetFold(page)).toHaveText(TEXTS.es.aurora.sheet.foldLess);
  await expectAccessible(page, 'hoja desplegada en el movil');
  await capture(page, 'es-movil-hoja-desplegada');
  await sheetFold(page).click();
  await expect(sheet.locator('.ws-file-table > a')).toHaveCount(3);
  await page.emulateMedia({ reducedMotion: null });
  await page.setViewportSize({ width: 1440, height: 900 });
  await setLang(page, 'nl');
});

test('capturas del archivo en los tres idiomas y los dos temas, y en el movil', async ({ page, baseUrl }) => {
  test.setTimeout(600_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const lang of ['es', 'nl', 'en'] as const) {
    const tx = TEXTS[lang];
    await setLang(page, lang);
    for (const theme of ['dark', 'light'] as const) {
      await chooseTheme(page, theme);
      await openDocuments(page, lang);
      await artReady(page);
      await expectAccessible(page, `${lang} ${theme} documentos`);
      await expectNoLeftovers(page, lang, `${lang} ${theme} documentos`);
      await capture(page, `${lang}-documentos`);
      await folderCell(page, JV).getByRole('link', { name: fill(tx.aurora.archive.openProfileNamed, { name: JV }) }).click();
      await expect(folderProfile(page, JV, lang)).toBeVisible();
      await artReady(page);
      await expectAccessible(page, `${lang} ${theme} carpeta de un proveedor`);
      await expectNoLeftovers(page, lang, `${lang} ${theme} carpeta de un proveedor`);
      await capture(page, `${lang}-documentos-proveedor`);
      await profileRow(page, `${tx.documents.types.factura_compra} JV-2026-001`).click();
      await expect(sheetDialog(page)).toContainText(/JV-2026-001/);
      await expectAccessible(page, `${lang} ${theme} hoja`);
      await expectNoLeftovers(page, lang, `${lang} ${theme} hoja`);
      await capture(page, `${lang}-documentos-hoja`);
      await page.keyboard.press('Escape');
      // Un cliente sin documentos, con sus Objects y sus PO.
      await openFolder(page, HAVEN, 'client', lang);
      await expect(folderProfile(page, HAVEN, lang)).toContainText(`${tx.records.object.label} HAVEN-NOORD`);
      await artReady(page);
      await expectAccessible(page, `${lang} ${theme} carpeta de un cliente`);
      await expectNoLeftovers(page, lang, `${lang} ${theme} carpeta de un cliente`);
      await capture(page, `${lang}-documentos-cliente`);
    }
  }
  // En el movil, en castellano y oscuro: nada se sale por el lado.
  await chooseTheme(page, 'dark', 'en');
  await setLang(page, 'es');
  await page.setViewportSize({ width: 400, height: 860 });
  await openDocuments(page, 'es');
  await artReady(page);
  expect(await outsideTheWindow(page)).toEqual([]);
  await capture(page, 'es-movil-documentos');
  await openFolder(page, JV, 'provider', 'es');
  expect(await outsideTheWindow(page)).toEqual([]);
  await capture(page, 'es-movil-documentos-proveedor');
  await profileRow(page, `${TEXTS.es.documents.types.factura_compra} JV-2026-001`).click();
  await expect(sheetDialog(page).getByRole('button', { name: TEXTS.es.aurora.card.downloadOriginal })).toBeVisible();
  await capture(page, 'es-movil-documentos-hoja');
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1440, height: 900 });
  await setLang(page, 'nl');
});
