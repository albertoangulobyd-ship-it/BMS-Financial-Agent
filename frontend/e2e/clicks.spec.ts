// Los 3 clics (revision de Aurora, §5): cada tarea de la tabla, desde el inicio, con como mucho
// los clics de su columna "Objetivo". Se cuentan los clics de verdad (escribir no es un clic; el
// boton que abre un dialogo de confirmacion cuenta como "+ dialogo", como en la tabla). La
// lectura de PDF con su coste (21) es de un paso siguiente del paso 16: va como pendiente. La
// vista previa de Documentos (22) la hizo el paso de Documentos, y los pagos (11, 12 y 13) el
// de Cuentas por cobrar y por pagar, que tambien cambio los caminos de 6 a 9 y 16: Te ontvangen
// y Te betalen abren con su resumen.
import type { Locator, Page } from '@playwright/test';
import { expect, login, test } from './fixtures';
import { TEXTS, crumbs, mainMenu, sectionButton, sectionMenu, viewHeading } from './nav';

const t = TEXTS.nl;

/** Cuenta los clics de una tarea. */
class Clicks {
  n = 0;
  constructor(private readonly page: Page) {}
  async click(target: Locator) {
    this.n += 1;
    await target.click();
  }
  /** Vuelve al inicio (no cuenta: es donde empieza cada tarea). */
  async fromHome() {
    await this.page.getByRole('button', { name: t.shell.home }).click();
    await expect(viewHeading(this.page, 'home')).toBeVisible();
    await expect(this.page.getByTestId('summary-card').first()).toBeVisible();
    this.n = 0;
  }
}

const card = (page: Page, title: string) => page.getByTestId('summary-card').filter({ has: page.getByRole('heading', { level: 2, name: title }) });
const askResults = (page: Page) => page.locator('section[aria-labelledby="ask-results"]');

/** Escribe en la caja del inicio e Intro (escribir no es un clic). */
async function ask(page: Page, text: string): Promise<void> {
  const box = page.getByRole('textbox', { name: t.ask.label });
  await box.fill(text);
  await box.press('Enter');
  await expect(askResults(page)).toBeVisible();
}

test('cada tarea de la tabla de los 3 clics, en los clics de su objetivo', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const c = new Clicks(page);
  await c.fromHome();

  await test.step('1 · Qué necesita atención hoy: 0', async () => {
    const attention = card(page, 'Aandacht nodig');
    await expect(attention).toBeInViewport();
    await expect(attention).toContainText('Geblokkeerd');
    await expect(page.locator('section[aria-labelledby="next-up"]')).toContainText('Geblokkeerd');
    expect(c.n).toBe(0);
  });

  await test.step('2 · Abrir la factura más urgente: 1', async () => {
    await c.click(page.locator('section[aria-labelledby="next-up"] ol').getByRole('button').first());
    await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(1);
  });

  await test.step('3 · Total por cobrar y lo vencido: 0', async () => {
    await c.fromHome();
    const receivable = card(page, 'Te ontvangen');
    await expect(receivable).toBeInViewport();
    await expect(receivable).toContainText('€');
    await expect(receivable).toContainText('Vervallen');
    expect(c.n).toBe(0);
  });

  await test.step('4 · Total por pagar y lo de esta semana: 0', async () => {
    const payable = card(page, 'Te betalen');
    await expect(payable).toBeInViewport();
    await expect(payable).toContainText('Deze week');
    expect(c.n).toBe(0);
  });

  await test.step('5 · Lista de ventas vencidas: 1', async () => {
    await c.click(page.getByRole('button', { name: t.home.overdueOut }));
    await expect(viewHeading(page, 'invoices-out')).toBeVisible();
    await expect(page.getByRole('group', { name: 'Welke facturen' }).getByRole('button', { name: /^Vervallen/ })).toHaveAttribute('aria-pressed', 'true');
    expect(c.n).toBeLessThanOrEqual(1);
    await page.getByRole('group', { name: 'Welke facturen' }).getByRole('button', { name: /^Alle/ }).click();
  });

  await test.step('6 · Una factura por cobrar (con sus pagos): 2', async () => {
    // Paso 16: "Vervallen" en la tarjeta Te ontvangen abre la lista; la fila, la factura, con
    // la seccion "Betalingen".
    await c.fromHome();
    await c.click(page.getByRole('button', { name: t.home.overdueOut }));
    await c.click(page.getByRole('table').getByRole('row').nth(1).getByRole('button'));
    await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
    await expect(page.getByText('Betaling', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: /^Betalingen/ })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
  });

  await test.step('7 · El PDF original de una factura: 3', async () => {
    // Paso 16: Te betalen abre con su resumen; la factura se busca escribiendo (no es un clic).
    await c.fromHome();
    await ask(page, 'JV-2026-004');
    await c.click(askResults(page).getByRole('button', { name: /^JV-2026-004/ }).first());
    const download = page.waitForEvent('download');
    await c.click(page.getByRole('button', { name: 'Origineel', exact: true }));
    expect((await download).suggestedFilename()).toBe('JV-2026-004.pdf');
    expect(c.n).toBeLessThanOrEqual(3);
  });

  await test.step('8 · Lo pendiente de un cliente y sus facturas: 2', async () => {
    // Paso 16: en el resumen de Te ontvangen, cada cliente con lo que debe (lo vencido arriba).
    await c.fromHome();
    await c.click(sectionButton(page, 'receivables'));
    await c.click(page.getByRole('table', { name: t.money.parties.titleIn }).getByRole('button', { name: /Gemeente Demodorp/ }).first());
    await expect(page.getByRole('heading', { level: 1, name: 'Gemeente Demodorp' })).toBeVisible();
    await expect(page.getByText('staat nog open')).toBeVisible();
    await expect(page.getByRole('button', { name: /^Openstaande facturen/ })).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByRole('main')).toContainText('VD26-306');
    expect(c.n).toBeLessThanOrEqual(2);
  });

  await test.step('9 · Ficha de un proveedor: 2', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'payables'));
    await c.click(page.getByRole('table', { name: t.money.parties.titleOut }).getByRole('button', { name: /J\. Voorbeeld Beveiliging/ }).first());
    await expect(page.getByRole('heading', { level: 1, name: 'J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
  });

  await test.step('11 · Confirmar un cobro que propuso el banco: 3 + diálogo', async () => {
    // "Te bevestigen" en la tarjeta del inicio (1) y "Bevestigen" en la propuesta (2), con su
    // dialogo, que dice que no se paga nada. Se cancela: la prueba de pagos lo hace de verdad.
    await c.fromHome();
    await c.click(card(page, 'Te ontvangen').getByRole('button', { name: t.home.showToConfirmIn }));
    await expect(viewHeading(page, 'bank-in')).toBeVisible();
    await c.click(page.getByRole('article').first().getByRole('button', { name: t.bank.confirm }));
    await expect(page.getByRole('dialog')).toContainText(t.payments.confirmIntro);
    expect(c.n).toBeLessThanOrEqual(3);
    await page.getByRole('dialog').getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('12 · Apuntar un pago ya hecho, con motivo: 3 + diálogo', async () => {
    await c.fromHome();
    await c.click(page.getByRole('button', { name: t.home.overdueOut }));
    await c.click(page.getByRole('table').getByRole('row').nth(1).getByRole('button'));
    await c.click(page.getByRole('button', { name: t.payments.record }));
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('Er wordt niets betaald');
    await expect(dialog.getByLabel(t.payments.reasonField)).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
    await dialog.getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('13 · Ver las líneas del banco sin casar: 2', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'payables'));
    await c.click(sectionMenu(page, 'payables').getByRole('button', { name: /^Bankbetalingen/ }));
    await expect(page.getByRole('table', { name: t.bank.unmatchedTitle })).toContainText('Kosten zakelijk betalen');
    expect(c.n).toBeLessThanOrEqual(2);
  });

  await test.step('10 · Buscar una factura por número o nombre: 0 + escribir', async () => {
    await c.fromHome();
    const ask = page.getByRole('textbox', { name: t.ask.label });
    await ask.fill('KT-202608');
    await ask.press('Enter');
    await expect(page.locator('section[aria-labelledby="ask-results"]').getByRole('button', { name: /^KT-202608/ })).toBeVisible();
    expect(c.n).toBe(0);
  });

  await test.step('14 · Verificar un IBAN por teléfono: 2 + diálogo', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'payables'));
    await c.click(sectionMenu(page, 'payables').getByRole('button', { name: /^IBAN-controles/ }));
    await expect(viewHeading(page, 'iban-checks')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
    // La base de prueba trae cuentas pendientes de llamar: el boton abre el dialogo de la llamada.
    const call = page.getByRole('button', { name: 'Telefonisch bevestigen' }).first();
    await expect(call).toBeVisible();
    await call.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('dialog').getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('15 · Resolver una excepción: 3 + diálogo', async () => {
    await c.fromHome();
    await c.click(page.getByRole('navigation', { name: t.home.alsoHere }).getByRole('button', { name: /^Uitzonderingen/ }));
    await c.click(page.getByRole('button', { name: /^Uitzondering \d+ openen$/ }).first());
    await page.getByRole('main').getByRole('button', { name: 'Oplossen' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
    await page.getByRole('dialog').getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('16 · Marcar una factura como revisada: 3', async () => {
    await c.fromHome();
    await ask(page, 'JV-2026-004');
    await c.click(askResults(page).getByRole('button', { name: /^JV-2026-004/ }).first());
    await expect(page.getByRole('heading', { level: 1, name: /JV-2026-004$/ })).toBeVisible();
    // En la base de prueba esta factura esta sin revisar: el boton esta en "Afronden".
    await c.click(page.getByRole('region', { name: 'Afronden' }).getByRole('button', { name: 'Markeren als gecontroleerd' }));
    await expect(page.getByRole('dialog')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
    await page.getByRole('dialog').getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('17 · Flujo de caja: 1', async () => {
    await c.fromHome();
    await c.click(page.getByRole('navigation', { name: t.home.alsoHere }).getByRole('button', { name: /^Kasstroom/ }));
    await expect(viewHeading(page, 'cash-flow')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(1);
  });

  await test.step('18 · BTW del trimestre y su hoja: 3', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'vat'));
    await c.click(page.getByRole('table').getByRole('button', { name: /Q3 2026/ }).first());
    const download = page.waitForEvent('download');
    await c.click(page.getByRole('button', { name: 'Werkblad downloaden' }));
    expect((await download).suggestedFilename()).toBe('btw-2026-T3.csv');
    expect(c.n).toBeLessThanOrEqual(3);
  });

  await test.step('19 · Margen de un Object o lo que queda de una PO: 2', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'receivables'));
    await c.click(sectionMenu(page, 'receivables').getByRole('button', { name: /^Objecten/ }));
    await expect(page.getByRole('columnheader', { name: 'Marge' })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
    await c.fromHome();
    await c.click(sectionButton(page, 'receivables'));
    await c.click(sectionMenu(page, 'receivables').getByRole('button', { name: /^Inkooporders/ }));
    await expect(page.getByRole('columnheader', { name: 'Over' })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
  });

  await test.step('20 · Importar un fichero de Exact o del banco: 1 para llegar', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'process'));
    await expect(viewHeading(page, 'import')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Eerst proberen' })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(1);
  });

  await test.step('21 · Leer PDF (Procesar): 2 para llegar', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'process'));
    await c.click(sectionMenu(page, 'process').getByRole('button', { name: /^Facturen lezen/ }));
    await expect(viewHeading(page, 'read-invoices')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
  });

  await test.step('22 · Documentos de una empresa y su vista previa: 3', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'documents'));
    // La carpeta de cristal (paso 16, el archivo de Aurora con los datos de verdad).
    await c.click(page.getByRole('button', { name: /^J\. Voorbeeld Beveiliging \(zzp\) openen/ }));
    await expect(page.getByRole('heading', { level: 1, name: 'Documenten van J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
    expect(await crumbs(page)).toEqual(['Documenten', 'J. Voorbeeld Beveiliging (zzp)']);
    await c.click(page.getByRole('region', { name: 'J. Voorbeeld Beveiliging (zzp)' }).getByRole('button', { name: /^Voorbeeld van Inkoopfactuur / }).first());
    await expect(page.getByRole('dialog')).toContainText('Inkoopfactuur JV-2026-007');
    expect(c.n).toBeLessThanOrEqual(3);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
  });

  await test.step('22 · …y bajar el original de uno: 3', async () => {
    await c.fromHome();
    await c.click(sectionButton(page, 'documents'));
    await c.click(page.getByRole('button', { name: /^J\. Voorbeeld Beveiliging \(zzp\) openen/ }));
    const download = page.waitForEvent('download');
    await c.click(page.getByRole('region', { name: 'J. Voorbeeld Beveiliging (zzp)' }).getByRole('button', { name: /downloaden$/ }).first());
    expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
    expect(c.n).toBeLessThanOrEqual(3);
  });

  await test.step('23 · Hacer una pregunta: 0 (y dice que aún no contesta)', async () => {
    await c.fromHome();
    const ask = page.getByRole('textbox', { name: t.ask.label });
    await ask.fill('Wat moeten we deze week betalen?');
    await ask.press('Enter');
    await expect(page.locator('section[aria-labelledby="ask-results"]')).toContainText('Niets gevonden');
    await expect(page.getByText(t.ask.notYet)).toBeVisible();
    expect(c.n).toBe(0);
  });

  await test.step('24 · Cambiar idioma o tema: 1–2', async () => {
    await c.fromHome();
    await c.click(page.getByRole('button', { name: 'Accountmenu van Ana Demo' }));
    await c.click(page.getByRole('menuitemradio', { name: 'English' }));
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    expect(c.n).toBeLessThanOrEqual(2);
    await page.getByRole('button', { name: 'Account menu for Ana Demo' }).click();
    await page.getByRole('menuitemradio', { name: 'Nederlands' }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'nl');
  });

  // Las seis entradas, a un clic desde cualquier sitio (lo que hace posibles los numeros de arriba).
  await expect(mainMenu(page).getByRole('button')).toHaveCount(6);
});

// Lo que llega en un paso siguiente del paso 16 (revision §8.5): al construirlo, quien lo haga
// cambia fixme por test y escribe el camino, con su objetivo.
test.fixme('21 · Leer PDF con la confirmación del coste: 2 + confirmación (Procesar de verdad, §8.5)', async () => {});
