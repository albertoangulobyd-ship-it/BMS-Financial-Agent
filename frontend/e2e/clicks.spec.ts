// Los clics de cada tarea (revision de Aurora, §5; paso 17: con la rueda de Aurora). Cada tarea
// empieza en el inicio (E0) y se cuentan los clics de verdad y, aparte, los pasos de la rueda
// (escribir no es un clic; el boton que abre un dialogo de confirmacion cuenta como "+ dialogo").
// Cada tarea abre la rueda con Start en el centro, como sale la primera vez en una sesion
// (despues sale con la ultima entrada que se uso): los clics y los pasos se cuentan desde ahi.
// Mientras los paneles llevan las pantallas de hoy (paso 17, B1), cada camino pasa por
// «Druk om te navigeren», la entrada y la fila de su pantalla: los limites de abajo son los de
// ahora y la prueba falla si un camino crece. Los paneles de especificacion §2.2 (B2) los
// acortan a lo de la tabla de §2.6. La conversacion (escribir un numero o un nombre) abre una
// factura con un clic desde el inicio.
import type { Locator, Page } from '@playwright/test';
import { expect, login, settled, test } from './fixtures';
import { TEXTS, app, centre, crumbs, entryButton, landed, panel, panelRow, toHome, viewHeading } from './nav';

const t = TEXTS.nl;

/** Cuenta los clics y los pasos de la rueda de una tarea. */
class Clicks {
  n = 0;
  steps = 0;
  constructor(private readonly page: Page) {}
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
  /** «Druk om te navigeren»: la rueda (1 clic), como sale la primera vez en una sesion, con
   *  Start en el centro (§1.4; despues sale con la ultima que se uso). Ponerla ahi no cuenta. */
  async menu() {
    await this.click(this.page.getByRole('button', { name: t.aurora.home.navigate }));
    await centre(this.page, 'home');
  }
  /** Una fila del panel abierto, y su pantalla con el vuelo. */
  async row(label: string) {
    await this.click(panelRow(this.page, label));
    await landed(this.page);
  }
}

/** Escribe en la caja del inicio e Intro (escribir no es un clic) y espera la respuesta. */
async function ask(page: Page, text: string): Promise<void> {
  const box = page.getByRole('textbox', { name: t.aurora.composer.askLabel });
  await box.fill(text);
  await box.press('Enter');
  await expect(page.locator('.conversation')).toBeVisible();
  await expect(page.locator('.typing-dots')).toHaveCount(0, { timeout: 15_000 });
}

/** Una fila de la respuesta de la conversacion. */
const answerRow = (page: Page, name: RegExp) => page.locator('.conversation .chat-rows').getByRole('link', { name }).first();

test('cada tarea de la tabla de los clics, con la rueda de Aurora', async ({ page, baseUrl }) => {
  test.setTimeout(300_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const c = new Clicks(page);
  await c.fromHome();

  await test.step('1 · Qué necesita atención hoy: 2', async () => {
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await expect(panelRow(page, t.nav['work-queue'].label)).toContainText(t.badges.blocked);
    expect(c.n).toBeLessThanOrEqual(2);
  });

  await test.step('2 · Abrir la factura más urgente: 4', async () => {
    await c.row(t.aurora.panel.overview);
    await c.click(page.locator('section[aria-labelledby="next-up"] ol').getByRole('button').first());
    await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(4);
  });

  await test.step('3 y 4 · Lo pendiente por cobrar y por pagar: 3', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.row(t.aurora.panel.overview);
    await expect(viewHeading(page, 'receivables')).toBeVisible();
    await expect(page.locator('[data-testid="money-figure"]').first()).toContainText('€');
    expect(c.n).toBeLessThanOrEqual(3);
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'payables'));
    await c.row(t.aurora.panel.overview);
    await expect(page.locator(`[data-testid="money-figure"][data-label="${t.money.thisWeek}"]`)).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
  });

  await test.step('5 y 6 · Las ventas vencidas y una de ellas: 4 y 5', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await c.row(t.aurora.panel.overview);
    await c.click(page.getByRole('button', { name: t.home.overdueOut }));
    await expect(viewHeading(page, 'invoices-out')).toBeVisible();
    await expect(page.getByRole('group', { name: 'Welke facturen' }).getByRole('button', { name: /^Vervallen/ })).toHaveAttribute('aria-pressed', 'true');
    expect(c.n).toBeLessThanOrEqual(4);
    await c.click(page.getByRole('table').getByRole('row').nth(1).getByRole('button'));
    await expect(page.getByRole('heading', { level: 2, name: /^Betalingen/ })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(5);
  });

  await test.step('7 · El PDF original de una factura: 2 (escribiendo su número)', async () => {
    await c.fromHome();
    await ask(page, 'JV-2026-004');
    await c.click(answerRow(page, /JV-2026-004/));
    await landed(page);
    const download = page.waitForEvent('download');
    await c.click(page.getByRole('button', { name: 'Origineel', exact: true }));
    expect((await download).suggestedFilename()).toBe('JV-2026-004.pdf');
    expect(c.n).toBeLessThanOrEqual(2);
  });

  await test.step('8 · Lo pendiente de un cliente y sus facturas: 4', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.row(t.aurora.panel.overview);
    await c.click(page.getByRole('table', { name: t.money.parties.titleIn }).getByRole('button', { name: /Gemeente Demodorp/ }).first());
    await expect(page.getByRole('heading', { level: 1, name: 'Gemeente Demodorp' })).toBeVisible();
    await expect(page.getByRole('main')).toContainText('VD26-306');
    expect(c.n).toBeLessThanOrEqual(4);
  });

  await test.step('9 · Ficha de un proveedor: 4', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'payables'));
    await c.row(t.nav.providers.label);
    await c.click(page.getByRole('table').getByRole('button', { name: /J\. Voorbeeld Beveiliging/ }).first());
    await expect(page.getByRole('heading', { level: 1, name: 'J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(4);
  });

  await test.step('10 · Buscar una factura por número o nombre: 0 + escribir', async () => {
    await c.fromHome();
    await ask(page, 'KT-202608');
    await expect(answerRow(page, /KT-202608/)).toBeVisible();
    expect(c.n).toBe(0);
  });

  await test.step('11 · Confirmar un cobro que propuso el banco: 4 + diálogo', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.row(t.nav['bank-in'].label);
    await c.click(page.getByRole('article').first().getByRole('button', { name: t.bank.confirm }));
    await expect(page.getByRole('dialog')).toContainText(t.payments.confirmIntro);
    expect(c.n).toBeLessThanOrEqual(4);
    await page.getByRole('dialog').getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('12 · Apuntar un pago ya hecho, con motivo: 2 + diálogo (escribiendo su número)', async () => {
    await c.fromHome();
    await ask(page, 'VD26-306');
    await c.click(answerRow(page, /VD26-306/));
    await landed(page);
    await c.click(page.getByRole('button', { name: t.payments.record }));
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('Er wordt niets betaald');
    await expect(dialog.getByLabel(t.payments.reasonField)).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
    await dialog.getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('13 · Ver las líneas del banco sin casar: 3', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'payables'));
    await c.row(t.nav['bank-out'].label);
    await expect(page.getByRole('table', { name: t.bank.unmatchedTitle })).toContainText('Kosten zakelijk betalen');
    expect(c.n).toBeLessThanOrEqual(3);
  });

  await test.step('14 · Verificar un IBAN por teléfono: 3 + diálogo', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await c.row(t.nav['iban-checks'].label);
    await expect(viewHeading(page, 'iban-checks')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
    const call = page.getByRole('button', { name: 'Telefonisch bevestigen' }).first();
    await expect(call).toBeVisible();
    await call.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('dialog').getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('15 · Resolver una excepción: 4 + diálogo', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await c.row(t.nav.exceptions.label);
    await c.click(page.getByRole('button', { name: /^Uitzondering \d+ openen$/ }).first());
    await page.getByRole('main').getByRole('button', { name: 'Oplossen' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(4);
    await page.getByRole('dialog').getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('16 · Marcar una factura como revisada: 2 (escribiendo su número)', async () => {
    await c.fromHome();
    await ask(page, 'JV-2026-004');
    await c.click(answerRow(page, /JV-2026-004/));
    await landed(page);
    await expect(page.getByRole('heading', { level: 1, name: /JV-2026-004$/ })).toBeVisible();
    await c.click(page.getByRole('region', { name: 'Afronden' }).getByRole('button', { name: 'Markeren als gecontroleerd' }));
    await expect(page.getByRole('dialog')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
    await page.getByRole('dialog').getByRole('button', { name: 'Annuleren' }).click();
  });

  await test.step('17 · Flujo de caja: 3', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'home'));
    await c.row(t.nav['cash-flow'].label);
    await expect(viewHeading(page, 'cash-flow')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
  });

  await test.step('18 · IVA del trimestre y su hoja: 5 y un paso de rueda', async () => {
    await c.fromHome();
    await c.menu();
    await c.step(120);
    await c.click(entryButton(page, 'vat'));
    await c.row(t.aurora.panel.overview);
    await c.click(page.getByRole('table').getByRole('button', { name: /Q3 2026/ }).first());
    const download = page.waitForEvent('download');
    await c.click(page.getByRole('button', { name: 'Werkblad downloaden' }));
    expect((await download).suggestedFilename()).toBe('btw-2026-T3.csv');
    expect(c.n).toBeLessThanOrEqual(5);
    expect(c.steps).toBeLessThanOrEqual(1);
  });

  await test.step('19 · Margen de un Object o lo que queda de una PO: 3', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.row(t.nav.objects.label);
    await expect(page.getByRole('columnheader', { name: 'Marge' })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.row(t.nav['client-pos'].label);
    await expect(page.getByRole('columnheader', { name: 'Over' })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
  });

  await test.step('20 · Importar un fichero de Exact o del banco: 3 para llegar', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'receivables'));
    await c.row(t.nav.import.label);
    await expect(viewHeading(page, 'import')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Eerst proberen' })).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(3);
  });

  await test.step('21 · Leer PDF (Procesar): 2 para llegar y dos pasos de rueda', async () => {
    await c.fromHome();
    await c.menu();
    await c.step(120);
    await c.step(120);
    // Te betalen en el centro: Verwerken asoma abajo, en la ventana de cinco, y un clic la abre.
    await expect(app(page)).toHaveAttribute('data-active', 'payables');
    await c.click(entryButton(page, 'process'));
    await landed(page);
    await expect(viewHeading(page, 'read-invoices')).toBeVisible();
    expect(c.n).toBeLessThanOrEqual(2);
    expect(c.steps).toBeLessThanOrEqual(2);
  });

  await test.step('22 · Documentos de una empresa y su vista previa: 4', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'documents'));
    await landed(page);
    await c.click(page.getByRole('button', { name: /^J\. Voorbeeld Beveiliging \(zzp\) openen/ }));
    await expect(page.getByRole('heading', { level: 1, name: 'Documenten van J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
    expect(await crumbs(page)).toEqual(['Documenten', 'J. Voorbeeld Beveiliging (zzp)']);
    await c.click(page.getByRole('region', { name: 'J. Voorbeeld Beveiliging (zzp)' }).getByRole('button', { name: /^Voorbeeld van Inkoopfactuur / }).first());
    await expect(page.getByRole('dialog')).toContainText('Inkoopfactuur JV-2026-007');
    expect(c.n).toBeLessThanOrEqual(4);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
  });

  await test.step('22 · …y bajar el original de uno: 4', async () => {
    await c.fromHome();
    await c.menu();
    await c.click(entryButton(page, 'documents'));
    await landed(page);
    await c.click(page.getByRole('button', { name: /^J\. Voorbeeld Beveiliging \(zzp\) openen/ }));
    const download = page.waitForEvent('download');
    await c.click(page.getByRole('region', { name: 'J. Voorbeeld Beveiliging (zzp)' }).getByRole('button', { name: /downloaden$/ }).first());
    expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
    expect(c.n).toBeLessThanOrEqual(4);
  });

  await test.step('23 · Hacer una pregunta: 0 (y dice lo que sabe hacer)', async () => {
    await c.fromHome();
    await ask(page, 'Wat moeten we deze week betalen?');
    await expect(page.locator('.conversation')).toContainText(t.aurora.chat.unknown);
    expect(c.n).toBe(0);
  });

  await test.step('24 · Cambiar el idioma: 4 y un paso de rueda (Ajustes)', async () => {
    await c.fromHome();
    await c.menu();
    await c.step(-120);
    await c.click(entryButton(page, 'settings'));
    await c.click(panelRow(page, t.aurora.settings.language));
    await c.click(panelRow(page, 'English'));
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    expect(c.n).toBeLessThanOrEqual(4);
    expect(c.steps).toBeLessThanOrEqual(1);
    await panelRow(page, 'Nederlands').click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'nl');
    await expect(panel(page)).toBeVisible();
  });
});

// Lo que llega en un paso siguiente (revision §8.5, Procesar de verdad): al construirlo, quien lo
// haga cambia fixme por test y escribe el camino, con su objetivo.
test.fixme('21 · Leer PDF con la confirmación del coste: 2 + confirmación (Procesar de verdad, §8.5)', async () => {});
