// Los clics de cada tarea (especificacion §2.6, con la rueda de Aurora y los paneles en dos
// niveles). Cada tarea empieza en el inicio (E0) y se cuentan los clics de verdad y, aparte, los
// pasos de la rueda (un gesto de la rueda del raton): los dos suman, como en la tabla. Escribir no
// es un clic. "+ conf." (el "si" de una orden) no se cuenta. Cada tarea abre la rueda con Inicio en
// el centro, como sale la primera vez en una sesion: ponerla ahi no cuenta. Los limites son los de
// la tabla (la columna "Clics"): la prueba falla si un camino crece. Y, en cada grupo con mas de
// cinco filas, la sexta y la ultima se alcanzan escribiendo en el campo .search de su vista, sin
// ningun clic mas.
import type { Locator, Page } from '@playwright/test';
import type { InvoiceRow } from '../src/lib/api';
import type { AccountRow, ExceptionRow } from '../src/lib/api-types';
import { accountStep, buildChecks } from '../src/aurora/panels/iban-model';
import { needsPerson } from '../src/lib/why';
import { expect, login, settled, test, token } from './fixtures';
import { TEXTS, answerRow, app, ask, centre, entryButton, landed, panel, panelRow, processLanded, sheetDialog, toHome, treeItem } from './nav';

const t = TEXTS.nl;

/** Cuenta los clics y los pasos de la rueda de una tarea. */
class Clicks {
  n = 0;
  steps = 0;
  constructor(private readonly page: Page) {}
  /** Lo que cuenta la tabla: clics y pasos de la rueda. */
  get total() {
    return this.n + this.steps;
  }
  async click(target: Locator) {
    this.n += 1;
    await target.click();
  }
  /** Un paso de la rueda del raton sobre la rueda (un gesto). */
  async step(delta: number) {
    this.steps += 1;
    const box = await this.page.locator('.marquee').boundingBox();
    await this.page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    const before = await app(this.page).getAttribute('data-active');
    await this.page.mouse.wheel(0, delta);
    await expect.poll(() => app(this.page).getAttribute('data-active')).not.toBe(before);
    await this.page.waitForTimeout(260);
    await settled(this.page);
  }
  /** Al inicio (no cuenta: es donde empieza cada tarea). */
  async fromHome() {
    await toHome(this.page);
    this.n = 0;
    this.steps = 0;
  }
  /** El orbe: la rueda (1 clic), con Inicio en el centro (§1.4). Ponerla ahi no cuenta. */
  async menu() {
    await this.click(this.page.locator('button.aurora'));
    await centre(this.page, 'home');
  }
  /** Una fila del panel abierto (la vista de su grupo, o su tarjeta). */
  async row(label: string | Locator) {
    await this.click(typeof label === 'string' ? panelRow(this.page, label) : label);
    await settled(this.page);
  }
}

const firstRow = (page: Page) => panel(page).locator('.doc-list button.doc').first();
const card = (page: Page) => panel(page).locator('.detail');

test('cada tarea de la tabla de los clics, con la rueda de Aurora', async ({ page, baseUrl }) => {
  test.setTimeout(400_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const c = new Clicks(page);
  await c.fromHome();

  await test.step('1 · Qué necesita atención hoy: 2', async () => {
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await expect(panel(page).getByTestId('balance')).toContainText(t.aurora.home.attention);
    await expect(panelRow(page, t.nav['work-queue'].label)).toContainText('geblokkeerd');
    expect(c.total).toBeLessThanOrEqual(2);
  });

  await test.step('2 · Abrir la factura más urgente: 4 (la hoja, 5)', async () => {
    await c.row(t.aurora.home.first);
    await c.row(firstRow(page));
    await expect(card(page)).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(4);
    await c.click(card(page).getByRole('button', { name: t.aurora.card.openInvoice }));
    await landed(page);
    await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(5);
  });

  await test.step('3 y 4 · Lo pendiente por cobrar y por pagar: 2', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await expect(panel(page).getByTestId('balance')).toContainText('€');
    expect(c.total).toBeLessThanOrEqual(2);
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'payables'));
    await expect(panelRow(page, t.aurora.money.week)).toContainText('€');
    expect(c.total).toBeLessThanOrEqual(2);
  });

  await test.step('5 y 6 · Las ventas vencidas y una de ellas con sus pagos: 3 y 4', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.row(t.aurora.money.overdue);
    await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
    const results = page.getByRole('region', { name: t.aurora.search.resultsLabel });
    await expect(results).toContainText('VD26-306');
    expect(c.total).toBeLessThanOrEqual(3);
    await c.click(results.getByRole('link').first());
    await landed(page);
    await expect(sheetDialog(page).getByTestId('paid-source')).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(4);
  });

  await test.step('6 (por la caja) y 7 · Una factura y su PDF original: 1 y 2 + escribir', async () => {
    await c.fromHome();
    await ask(page, 'JV-2026-004');
    await c.click(answerRow(page, 'JV-2026-004'));
    await landed(page);
    await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('JV-2026-004');
    expect(c.total).toBeLessThanOrEqual(1);
    const download = page.waitForEvent('download');
    await c.click(sheetDialog(page).getByRole('button', { name: t.aurora.card.downloadOriginal }));
    expect((await download).suggestedFilename()).toBe('JV-2026-004.pdf');
    expect(c.total).toBeLessThanOrEqual(2);
  });

  await test.step('8 y 9 · La ficha de un cliente y la de un proveedor: 3', async () => {
    for (const name of ['Gemeente Demodorp', 'J. Voorbeeld Beveiliging (zzp)']) {
      await c.fromHome();
      await c.menu();
      await c.click(entryButton(page, 'documents'));
      await landed(page);
      await c.click(treeItem(page, name).first());
      await expect(page.getByRole('region', { name: `Kaart van ${name}`, exact: true })).toBeVisible();
      expect(c.total).toBeLessThanOrEqual(3);
    }
  });

  await test.step('10 · Buscar una factura: 0 + escribir', async () => {
    await c.fromHome();
    await ask(page, 'KT-202608');
    await expect(answerRow(page, 'KT-202608')).toBeVisible();
    expect(c.total).toBe(0);
  });

  await test.step('11 · Confirmar un cobro que propuso el banco: 5 + conf.', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.row(t.aurora.money.proposals);
    await c.row(firstRow(page));
    await c.click(card(page).getByRole('button', { name: t.bank.confirm, exact: true }));
    await expect(card(page)).toContainText(t.payments.confirmIntro);
    expect(c.total).toBeLessThanOrEqual(5);
    await card(page).locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  });

  await test.step('12 · Anotar un pago ya hecho, con motivo: 3 + escribir (por la caja); 5 por el panel', async () => {
    await c.fromHome();
    await ask(page, 'VD26-306');
    await c.click(answerRow(page, 'VD26-306'));
    await landed(page);
    await c.click(sheetDialog(page).locator('.ws-file-table > a').filter({ hasText: t.aurora.sheet.more }));
    const more = sheetDialog(page).locator('.detail');
    await c.click(more.getByRole('button', { name: t.payments.record, exact: true }));
    await expect(more).toContainText('Er wordt niets betaald');
    await expect(more.getByLabel(t.payments.reasonField)).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(3);
    await more.locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'payables'));
    await c.row(t.aurora.money.week);
    await c.row(firstRow(page));
    await c.click(card(page).getByRole('button', { name: t.payments.record, exact: true }));
    await expect(card(page).getByLabel(t.payments.reasonField)).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(5);
    await card(page).locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  });

  await test.step('13 · Ver las líneas del banco sin casar: 3', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'payables'));
    await c.row(t.aurora.money.unmatched);
    await expect(panel(page)).toContainText('Kosten zakelijk betalen');
    expect(c.total).toBeLessThanOrEqual(3);
  });

  await test.step('14 · Verificar un IBAN por teléfono: 5 + conf.', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await c.row(t.aurora.home.iban);
    await c.row(firstRow(page));
    const call = card(page).getByRole('button', { name: t.iban.verify, exact: true });
    await expect(call).toBeVisible();
    await c.click(call);
    await expect(card(page).getByLabel(t.iban.typedIban)).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(5);
    await card(page).locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  });

  await test.step('15 · Resolver una excepción: 5 + conf.', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await c.row(t.nav.exceptions.label);
    await c.row(firstRow(page));
    await c.click(card(page).getByRole('button', { name: t.exceptions.resolve, exact: true }));
    await expect(card(page).getByLabel(t.exceptions.whatWasDone)).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(5);
    await card(page).locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  });

  await test.step('16 · Marcar una factura como revisada: 3 + escribir', async () => {
    await c.fromHome();
    await ask(page, 'JV-2026-003');
    await c.click(answerRow(page, 'JV-2026-003'));
    await landed(page);
    await c.click(sheetDialog(page).locator('.ws-file-table > a').filter({ hasText: t.invoice.reviewStep }));
    const review = sheetDialog(page).locator('.detail');
    await c.click(review.getByRole('button', { name: t.invoice.markReviewed, exact: true }));
    await expect(review).toContainText('Dat keurt geen betaling goed');
    expect(c.total).toBeLessThanOrEqual(3);
    await review.locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
  });

  await test.step('17 · Flujo de caja: 3', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await c.row(t.nav['cash-flow'].label);
    await expect(panel(page).getByTestId('cash-estimate')).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(3);
  });

  await test.step('18 · IVA del trimestre y su hoja: 4 (un paso de rueda)', async () => {
    await c.fromHome();
    await c.menu();
    await c.step(120);
    await c.click(entryButton(page, 'vat'));
    const download = page.waitForEvent('download');
    await c.click(panel(page).getByRole('button', { name: t.aurora.vat.download }));
    expect((await download).suggestedFilename()).toMatch(/^btw-\d{4}-T\d\.csv$/);
    expect(c.total).toBeLessThanOrEqual(4);
    expect(c.steps).toBeLessThanOrEqual(1);
  });

  await test.step('19 · Margen de un Object o lo que queda de una PO: 4 por el archivo', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'documents'));
    await landed(page);
    await c.click(treeItem(page, 'Demo Havenbedrijf BV').first());
    await c.click(page.locator('.ws-profile .ws-file-table > a').filter({ hasText: 'HAVEN-NOORD' }));
    await expect(sheetDialog(page).getByRole('term').filter({ hasText: t.objects.marginFact })).toHaveCount(1);
    expect(c.total).toBeLessThanOrEqual(4);
    await page.keyboard.press('Escape');
    await c.click(page.locator('.ws-profile .ws-file-table > a').filter({ hasText: 'PO-DEMO-4501' }));
    await expect(sheetDialog(page).getByRole('term').filter({ hasText: t.pos.left })).toHaveCount(1);
    await page.keyboard.press('Escape');
  });

  await test.step('20 · Importar un fichero: 3 para llegar', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.click(panel(page).getByRole('button', { name: t.aurora.money.import }));
    await expect(panel(page).locator('.dropzone')).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(3);
  });

  await test.step('21 · Leer PDF (Procesar): dos pasos de rueda y un clic para llegar', async () => {
    await c.fromHome();
    await c.menu();
    await c.step(120);
    await c.step(120);
    // Te betalen en el centro: Verwerken asoma abajo, en la ventana de cinco, y un clic la abre.
    await expect(app(page)).toHaveAttribute('data-active', 'payables');
    await c.click(entryButton(page, 'process'));
    // Procesar (E7): el espacio central con la suricata, sin vuelo; pedir la lectura es un clic mas.
    await processLanded(page);
    expect(c.total).toBeLessThanOrEqual(4);
    expect(c.steps).toBeLessThanOrEqual(2);
  });

  await test.step('22 · Los documentos de una empresa y su hoja: 4 (2 + escribir por la caja)', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'documents'));
    await landed(page);
    await c.click(treeItem(page, 'J. Voorbeeld Beveiliging (zzp)').first());
    await c.click(page.locator('.ws-profile .ws-file-table > a').first());
    await expect(sheetDialog(page).getByTestId('paper')).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(4);
    await page.keyboard.press('Escape');
    await c.fromHome();
    await ask(page, 'Voorbeeld');
    await c.click(answerRow(page, 'J. Voorbeeld Beveiliging (zzp)').first());
    await landed(page);
    await c.click(page.locator('.ws-profile .ws-file-table > a').first());
    await expect(sheetDialog(page).getByTestId('paper')).toBeVisible();
    expect(c.total).toBeLessThanOrEqual(2);
    await page.keyboard.press('Escape');
  });

  await test.step('23 · Hacer una pregunta: 0 (y dice lo que sabe hacer)', async () => {
    await c.fromHome();
    await ask(page, 'Wat moeten we deze week betalen?');
    await expect(page.locator('.conversation')).toContainText(t.aurora.chat.unknown);
    expect(c.total).toBe(0);
  });

  await test.step('24 · Cambiar el idioma: 5 (un paso de rueda)', async () => {
    await c.fromHome();
    await c.menu();
    await c.step(-120);
    await c.click(entryButton(page, 'settings'));
    await c.click(panelRow(page, t.aurora.settings.language));
    await c.click(panelRow(page, 'English'));
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    expect(c.total).toBeLessThanOrEqual(5);
    expect(c.steps).toBeLessThanOrEqual(1);
    await panelRow(page, 'Nederlands').click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'nl');
  });
});

test('en un grupo de mas de cinco filas, la sexta y la ultima se alcanzan escribiendo', async ({ page, baseUrl, request }) => {
  const headers = { 'X-BMS-Token': token('ana') };
  const get = async <T,>(path: string) => (await (await request.get(`${baseUrl}${path}`, { headers })).json()) as T;
  const invoices = (await get<{ facturas: InvoiceRow[] }>('/api/v2/facturas')).facturas;
  const exceptions = (await get<{ excepciones: ExceptionRow[] }>('/api/v2/excepciones')).excepciones;
  const accounts = (await get<{ cuentas: AccountRow[] }>('/api/v2/cuentas')).cuentas;
  // Lo que se escribe para llegar a una fila: su numero de factura (Werklijst, Uitzonderingen) o
  // su IBAN (IBAN te controleren), en el orden en que las pinta su vista.
  const queue = invoices.filter(needsPerson).map((f) => f.numero ?? '');
  const byException = exceptions.map((e) => invoices.find((f) => f.id === e.factura_id)?.numero ?? '');
  const checks = buildChecks(invoices, accounts)
    .filter((x) => accountStep(x) === 'confirm')
    .map((x) => x.iban);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  let tried = 0;
  for (const [group, keys] of [
    [t.nav['work-queue'].label, queue],
    [t.nav.exceptions.label, byException],
    [t.aurora.home.iban, checks],
  ] as const) {
    if (keys.length <= 5) continue;
    tried += 1;
    await toHome(page);
    await page.locator('button.aurora').click();
    await centre(page, 'home');
    await entryButton(page, 'home').click();
    await panelRow(page, group).click();
    // Cinco a la vista y "En nog N".
    await expect(panel(page).locator('.doc-list button.doc')).toHaveCount(5);
    await expect(panel(page).locator('.doc-list .empty')).toBeVisible();
    const search = panel(page).getByRole('textbox', { name: t.aurora.panel.searchPlaceholder });
    for (const key of [keys[5]!, keys[keys.length - 1]!].filter(Boolean)) {
      // Escribir no es un clic: la fila sale entre las que encajan.
      await search.fill(key);
      const shown = panel(page).locator('.doc-list button.doc');
      await expect(shown.first()).toBeVisible();
      expect(await shown.count()).toBeGreaterThan(0);
      await expect(panel(page).locator('.doc-list')).toContainText(group === t.aurora.home.iban ? /NL/ : key);
      await search.fill('');
    }
  }
  // La base de prueba tiene grupos de mas de cinco (la cola, las excepciones): no es una prueba vacia.
  expect(tried).toBeGreaterThan(0);
});
