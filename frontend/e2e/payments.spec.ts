// Cuentas por cobrar y por pagar con datos de verdad (paso 17: los paneles E2-C y E2-P de Aurora
// en dos niveles, y la hoja de una factura), sobre la base de prueba con el extracto de hoy que le
// anade scripts/crear_demo_e2e.py (cobros y pagos que el banco caso a medias y un ingreso que no
// es de ninguna factura). La cifra principal, cada grupo y cada tramo dicen los mismos centimos
// que la API; y cada orden se da de verdad, en su tarjeta: confirmar un cobro propuesto, decir que
// una propuesta no es (con motivo), enlazar una linea del banco a su factura, apuntar un pago ya
// hecho con motivo y justificante, el aviso cuando otra persona se adelanta (409) y quien solo
// mira, que no ve ningun boton. Las capturas, en los tres idiomas y los dos temas. Las pruebas van
// en orden: cambian la base.
import type { APIRequestContext, Locator, Page } from '@playwright/test';
import type { Lang } from '../src/i18n/langs';
import type { BankLines, Cartera, PaymentProposal } from '../src/lib/api-types';
import { partiesByOverdue } from '../src/aurora/panels/money-model';
import { capture, expect, expectAccessible, expectNoLeftovers, login, outsideTheWindow, settled, test, token, type Who } from './fixtures';
import {
  TEXTS,
  chooseTheme,
  escapeRegExp,
  euro,
  fill,
  fillOrder,
  folderProfile,
  openCard,
  openDocuments,
  openEntry,
  openFolder,
  openGroup,
  openInvoice,
  openSheetRow,
  panel,
  panelRow,
  pickDate,
  readCount,
  setLang,
  sheetDialog,
} from './nav';

test.describe.configure({ mode: 'serial' });

const t = TEXTS.nl;

async function api<T>(request: APIRequestContext, baseUrl: string, path: string, who: Who = 'ana'): Promise<T> {
  const response = await request.get(`${baseUrl}${path}`, { headers: { 'X-BMS-Token': token(who) } });
  expect(response.status(), path).toBe(200);
  return (await response.json()) as T;
}

const cartera = async (request: APIRequestContext, baseUrl: string, sentido: 'saliente' | 'entrante') =>
  (await api<{ cartera: Cartera }>(request, baseUrl, `/api/v2/cartera?sentido=${sentido}`)).cartera;
const proposals = async (request: APIRequestContext, baseUrl: string) =>
  (await api<{ propuestas: PaymentProposal[] }>(request, baseUrl, '/api/v2/pagos/propuestas')).propuestas;
const unmatched = async (request: APIRequestContext, baseUrl: string, signo: 'entrada' | 'salida') =>
  (await api<{ movimientos: BankLines }>(request, baseUrl, `/api/v2/movimientos?signo=${signo}`)).movimientos.lista;

/** La propuesta de una empresa (los numeros de factura cambian con el dia de la base). */
function proposalOf(list: PaymentProposal[], party: string, side: 'saliente' | 'entrante' = 'saliente'): PaymentProposal {
  const found = list.find((p) => p.factura.parte === party && p.factura.sentido === side);
  if (!found) throw new Error(`no hay una propuesta de ${party}`);
  return found;
}

/** La cifra principal del panel abierto. */
const balance = (page: Page) => panel(page).getByTestId('balance');
/** La fila de una propuesta en la vista "Te bevestigen" (su nombre: el numero y el importe). */
const proposalRow = (page: Page, numero: string) => panel(page).getByRole('button', { name: new RegExp(`^${escapeRegExp(numero)}( \\(.*\\))? · `) });
/** Una linea del banco en la vista "Niet gekoppeld", por lo que dice su concepto. */
const lineRow = (page: Page, concepto: string) => panel(page).locator('.doc-list button.doc').filter({ hasText: concepto });
/** La orden del formulario abierto en una tarjeta y su "si". */
const formButton = (card: Locator, label: string) => card.locator('.order-form').getByRole('button', { name: label, exact: true });
const yes = (card: Locator, label: string) => card.locator('.chat-export').getByRole('button', { name: label, exact: true });

/** Las lineas de pago de la hoja abierta ("Betalingen, notities en geschiedenis"). */
async function paymentLines(page: Page): Promise<Locator> {
  const more = await openSheetRow(page, t.aurora.sheet.more);
  return more.getByTestId('payment-line');
}

test('las cifras de cobrar y pagar: la cifra principal, los grupos y los tramos, al centimo', async ({ page, baseUrl, request }) => {
  const [inn, out] = [await cartera(request, baseUrl, 'saliente'), await cartera(request, baseUrl, 'entrante')];
  const panelApi = (await api<{ panel: { dinero_entra: Cartera['totales']; dinero_sale: Cartera['totales'] } }>(request, baseUrl, '/api/v2/panel')).panel;
  // La cartera es el panel del motor, al centimo (la misma funcion).
  expect(inn.totales).toEqual(panelApi.dinero_entra);
  expect(out.totales).toEqual(panelApi.dinero_sale);
  // Los tramos suman lo pendiente; lo de esta semana, lo vencido y lo de la semana.
  for (const c of [inn, out]) expect(c.tramos.reduce((n, b) => n + b.importe_cent, 0)).toBe(c.totales.pendiente_cent);

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // Te ontvangen: la cifra principal y su nota, que no es dinero disponible sino lo pendiente.
  await openEntry(page, 'receivables');
  await expect(balance(page)).toContainText(t.aurora.money.total);
  await expect(balance(page)).toContainText(euro(inn.totales.pendiente_cent));
  await expect(balance(page)).toContainText(`${euro(inn.totales.vencido_cent)} vervallen`);
  // Los grupos: lo que el banco propone, lo que no casa y lo vencido, con sus cifras.
  const saliente = (await proposals(request, baseUrl)).filter((p) => p.factura.sentido === 'saliente');
  await expect(panelRow(page, t.aurora.money.proposals).locator('.doc-end')).toContainText(String(saliente.length));
  await expect(panelRow(page, t.aurora.money.proposals).locator('.doc-end small')).toHaveText(euro(inn.por_confirmar.importe_cent));
  await expect(panelRow(page, t.aurora.money.overdue).locator('.doc-end strong')).toHaveText(euro(inn.totales.vencido_cent));
  await expect(panelRow(page, t.aurora.money.overdue).locator('.doc-end small')).toHaveText(
    inn.totales.vencidas === 1 ? t.money.overdueInvoicesOne : fill(t.money.overdueInvoices, { n: inn.totales.vencidas })
  );
  await expectAccessible(page, 'te ontvangen');
  await expectNoLeftovers(page, 'nl', 'te ontvangen');
  await capture(page, 'nl-receivables');
  // La antiguedad: cada tramo, lo suyo.
  await openGroup(page, t.money.ageing.title);
  for (const b of inn.tramos.filter((x) => x.clave !== 'sin_fecha' || x.facturas > 0)) {
    await expect(panelRow(page, t.money.ageing.buckets[b.clave]).locator('.doc-end strong')).toHaveText(euro(b.importe_cent));
  }
  await capture(page, 'nl-receivables-ageing');
  // Un tramo con facturas abre la busqueda con sus filtros: las mismas que dice el motor.
  const bucket = inn.tramos.find((b) => b.clave !== 'sin_fecha' && b.clave !== 'al_corriente' && b.facturas > 0)!;
  await panelRow(page, t.money.ageing.buckets[bucket.clave]).click();
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  const results = page.getByRole('region', { name: t.aurora.search.resultsLabel });
  await expect(results).toContainText(bucket.facturas === 1 ? t.aurora.search.foundOne : fill(t.aurora.search.found, { n: bucket.facturas }));

  // Te betalen: la misma forma; esta semana (lo limpio y lo retenido) y lo retenido aparte.
  await openEntry(page, 'payables');
  await expect(balance(page)).toContainText(euro(out.totales.pendiente_cent));
  const week = out.esta_semana!;
  expect(week.sin_retener.importe_cent + week.retenido.importe_cent).toBe(out.totales.vencido_cent + out.totales.semana_cent);
  await expect(panelRow(page, t.aurora.money.week).locator('.doc-end strong')).toHaveText(euro(week.sin_retener.importe_cent + week.retenido.importe_cent));
  await expect(panelRow(page, t.money.week.held).locator('.doc-end strong')).toHaveText(euro(out.retenido.importe_cent));
  // Dos facturas con el mismo numero y la misma empresa llevan su "1 van 2" y "2 van 2".
  await openGroup(page, t.money.week.held);
  await expect(panel(page)).toContainText('IBAN niet betaalbaar');
  const held = out.retenido.lista ?? [];
  const repeated = held.filter((f) => held.filter((g) => g.numero === f.numero && g.parte === f.parte).length > 1);
  expect(repeated.length, 'la base de prueba retiene dos facturas con el mismo numero').toBeGreaterThanOrEqual(2);
  for (const n of [1, 2]) {
    const name = fill(t.common.openRecord, { what: `${t.records.invoice.label} ${repeated[0]!.numero} (${fill(t.common.twin, { n, of: 2 })})` });
    await expect(panel(page).getByRole('button', { name, exact: true })).toHaveCount(1);
  }
  await capture(page, 'nl-payables-held');

  // Una empresa vive en Documentos: su carpeta dice lo mismo que la cartera.
  const first = partiesByOverdue(out.partes)[0]!;
  await openDocuments(page);
  const profile = await openFolder(page, first.nombre!, 'provider');
  await expect(profile).toContainText(euro(first.pendiente_cent));
});

test('confirmar un cobro que propuso el banco y decir que otro no es', async ({ page, baseUrl, request }) => {
  const list = await proposals(request, baseUrl);
  const saliente = list.filter((p) => p.factura.sentido === 'saliente');
  const a = proposalOf(list, 'Stichting Voorbeeld Zorggroep');
  const [b] = list.filter((p) => p.factura.parte === 'Demo Havenbedrijf BV' && p.factura.sentido === 'saliente');
  const before = (await cartera(request, baseUrl, 'saliente')).totales.pendiente_cent;

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // La fila "Te bevestigen" dice cuantas hay.
  await openEntry(page, 'receivables');
  expect(await readCount(page, t.aurora.money.proposals)).toBe(saliente.length);
  await openGroup(page, t.aurora.money.proposals);
  const cardA = await openCard(page, proposalRow(page, a.factura.numero!));
  await expect(cardA).toContainText(a.movimiento!.concepto!);
  await expect(cardA.getByLabel(t.bank.matches)).toContainText(`${t.bank.match.referencia}: ${t.bank.yes}`);
  await expect(cardA.getByLabel(t.bank.matches)).toContainText(`${t.bank.match.contraparte}: ${t.bank.no}`);
  await expectAccessible(page, 'te bevestigen');
  await capture(page, 'nl-bank-in');

  // Bevestigen: la linea del banco al lado de la factura, y no paga nada.
  await cardA.getByRole('button', { name: t.bank.confirm, exact: true }).click();
  await expect(cardA).toContainText(t.payments.confirmIntro);
  await expect(cardA).toContainText(a.movimiento!.contraparte!);
  await formButton(cardA, t.bank.confirm).click();
  await expectAccessible(page, 'bevestigen');
  await capture(page, 'nl-bank-confirm');
  await yes(cardA, t.bank.confirm).click();
  await expect(panel(page).locator('.success')).toBeVisible();
  await expect(proposalRow(page, a.factura.numero!)).toHaveCount(0);
  await expect.poll(() => readCount(page)).toBe(saliente.length - 1);
  // Lo pendiente baja lo que se confirmo, y la factura dice pagada segun el banco, por quien.
  expect((await cartera(request, baseUrl, 'saliente')).totales.pendiente_cent).toBe(before - a.importe_cent);
  await openInvoice(page, a.factura.numero!);
  await expect(sheetDialog(page).getByTestId('paid-source')).toContainText('Betaald volgens de bank op');
  const lines = await paymentLines(page);
  await expect(lines.first()).toContainText('Bevestigd');
  await expect(lines.first()).toContainText('Ana Demo');
  await expectAccessible(page, 'factuur betaald');
  await capture(page, 'nl-invoice-paid-bank');

  // Niet deze: con motivo (sin el, no se manda); la linea pasa a "Niet gekoppeld".
  await openEntry(page, 'receivables');
  await openGroup(page, t.aurora.money.proposals);
  const cardB = await openCard(page, proposalRow(page, b!.factura.numero!));
  await cardB.getByRole('button', { name: t.payments.withdraw, exact: true }).click();
  await formButton(cardB, t.payments.withdraw).click();
  await expect(cardB.getByRole('alert')).toContainText(fill(t.action.required, { field: t.payments.withdrawReason }));
  await cardB.getByLabel(t.payments.withdrawReason).fill('Het rekeningnummer is niet van deze klant; eerst navragen');
  await formButton(cardB, t.payments.withdraw).click();
  await yes(cardB, t.payments.withdraw).click();
  await expect(proposalRow(page, b!.factura.numero!)).toHaveCount(0);
  await openEntry(page, 'receivables');
  await openGroup(page, t.aurora.money.unmatched);
  await expect(lineRow(page, b!.movimiento!.concepto!)).toHaveCount(1);
  // En la factura queda como "Ingetrokken", con su motivo.
  await openInvoice(page, b!.factura.numero!);
  await expect((await paymentLines(page)).filter({ hasText: 'Ingetrokken' })).toContainText('Het rekeningnummer is niet van deze klant');
});

test('enlazar una linea del banco a su factura: desde el banco y desde la factura', async ({ page, baseUrl, request }) => {
  const lines = await unmatched(request, baseUrl, 'entrada');
  const withdrawn = lines.find((l) => l.contraparte === 'Demo Havenbedrijf BV')!;
  const loose = lines.find((l) => l.contraparte === 'Fictief Evenementen BV')!;
  const open = (
    await api<{ facturas: { id: number; numero: string; contraparte: string; pendiente_cent: number; estado_pago: string; sentido: string }[] }>(request, baseUrl, '/api/v2/facturas')
  ).facturas;
  const waiting = new Set((await proposals(request, baseUrl)).map((p) => p.factura.id));
  // La factura de la linea retirada (su concepto la nombra) y la del ingreso suelto (su importe).
  const target = open.find((f) => withdrawn.concepto!.includes(f.numero))!;
  const other = open.find((f) => f.sentido === 'saliente' && f.estado_pago === 'pendiente' && f.pendiente_cent === loose.importe_cent && !waiting.has(f.id))!;

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // Desde el banco: "Aan een factuur koppelen" en la tarjeta de la linea, la factura y un motivo.
  await openEntry(page, 'receivables');
  await openGroup(page, t.aurora.money.unmatched);
  const card = await openCard(page, lineRow(page, withdrawn.concepto!));
  await card.getByRole('button', { name: t.bank.link, exact: true }).click();
  await expect(card).toContainText(t.payments.recordIntro);
  // Ninguna factura viene elegida; sin elegir, no se manda nada.
  const choice = card.getByRole('combobox', { name: t.payments.invoiceField });
  await expect(choice).toContainText(t.payments.chooseInvoice);
  // La que nombra el concepto de la linea va marcada, la primera (sin elegirla).
  const mark = t.payments.likelyMark.split(' · ').at(-1)!;
  await choice.click();
  await expect(page.getByRole('option').nth(1)).toContainText(target.numero);
  await expect(page.getByRole('option').nth(1)).toContainText(mark);
  await page.keyboard.press('Escape');
  const sent: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/api/v2/acciones')) sent.push(r.url());
  });
  await card.getByLabel(t.payments.reasonField).fill('Toch deze factuur: de klant betaalde vanaf een nieuwe rekening');
  await formButton(card, t.bank.link).click();
  await expect(card.getByRole('alert')).toContainText(fill(t.action.required, { field: t.payments.invoiceField }));
  expect(sent).toEqual([]);
  await fillOrder(page, card, { [t.payments.invoiceField]: target.numero });
  // Lo que faltaba ya esta elegido: el aviso no se queda al lado.
  await expect(card.getByRole('alert')).toHaveCount(0);
  await capture(page, 'nl-bank-link');
  await formButton(card, t.bank.link).click();
  await yes(card, t.bank.link).click();
  await expect(lineRow(page, withdrawn.concepto!)).toHaveCount(0);
  expect(sent).toHaveLength(1);
  await openInvoice(page, target.numero);
  await expect(sheetDialog(page).getByTestId('paid-source')).toContainText('Betaald volgens de bank op');

  // Desde la factura: "Betaling vastleggen" con la linea del banco; el importe, lo que queda.
  await openInvoice(page, other.numero);
  const more = await openSheetRow(page, t.aurora.sheet.more);
  await more.getByRole('button', { name: t.payments.record, exact: true }).click();
  await expect(more.getByLabel(t.payments.amount)).toHaveValue(`${Math.floor(other.pendiente_cent / 100)},${String(other.pendiente_cent % 100).padStart(2, '0')}`);
  await fillOrder(page, more, { [t.payments.bankLineField]: 'Fictief Evenementen BV', [t.payments.reasonField]: 'Betaald via een evenementenbureau, bevestigd per mail' });
  await formButton(more, t.payments.record).click();
  await yes(more, t.payments.record).click();
  await expect(sheetDialog(page).getByTestId('paid-source')).toContainText('Betaald volgens de bank op');
  const line = (await paymentLines(page)).first();
  await expect(line).toContainText('Betaald via een evenementenbureau');
  await expect(line).toContainText('Ana Demo');
  // Ya no hay nada sin casar del lado de cobrar: la fila no sale.
  await openEntry(page, 'receivables');
  await expect(panelRow(page, t.aurora.money.unmatched)).toHaveCount(0);
});

test('apuntar un pago ya hecho, con motivo y justificante, y retirar una propuesta de pago', async ({ page, baseUrl, request }) => {
  const list = await proposals(request, baseUrl);
  const oost = proposalOf(list, 'Demo Brandwacht Oost BV', 'entrante');

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // En Te betalen, la propuesta de un pago al proveedor: no es.
  await openEntry(page, 'payables');
  await openGroup(page, t.aurora.money.proposals);
  await expectAccessible(page, 'te bevestigen (betalingen)');
  await capture(page, 'nl-bank-out');
  const cardP = await openCard(page, proposalRow(page, oost.factura.numero!));
  await cardP.getByRole('button', { name: t.payments.withdraw, exact: true }).click();
  await cardP.getByLabel(t.payments.withdrawReason).fill('Dit was een voorschot, niet de factuur');
  await formButton(cardP, t.payments.withdraw).click();
  await yes(cardP, t.payments.withdraw).click();
  await expect(proposalRow(page, oost.factura.numero!)).toHaveCount(0);

  // A mano: el motivo es obligatorio, la fecha no puede ser futura, el importe no pasa de lo que
  // queda; con un justificante de su carpeta. "Er wordt niets betaald".
  await openInvoice(page, oost.factura.numero!);
  const more = await openSheetRow(page, t.aurora.sheet.more);
  await more.getByRole('button', { name: t.payments.record, exact: true }).click();
  await expect(more).toContainText('Er wordt niets betaald');
  await more.getByLabel(t.payments.amount).fill('99999,00');
  await more.getByLabel(t.payments.reasonField).fill('Contant betaald aan de brandwacht, kwitantie in de map');
  await formButton(more, t.payments.record).click();
  await expect(more.getByRole('alert')).toContainText('Dat is meer dan wat nog openstaat');
  await more.getByLabel(t.payments.amount).fill('');
  const later = new Date();
  later.setMonth(later.getMonth() + 2, 15);
  await pickDate(page, more, t.payments.payDate, later);
  await formButton(more, t.payments.record).click();
  await expect(more.getByRole('alert')).toContainText(t.payments.future);
  const evidence = more.getByRole('combobox', { name: new RegExp(`^${escapeRegExp(t.payments.evidenceField)}`) });
  await evidence.click();
  await expect(page.getByRole('option')).not.toHaveCount(1);
  await page.getByRole('option').nth(1).click();
  await expectAccessible(page, 'betaling vastleggen');
  // Con la fecha futura todavia escrita: el aviso y el campo que lo causa, juntos.
  await capture(page, 'nl-record-payment');
  await pickDate(page, more, t.payments.payDate, null);
  await formButton(more, t.payments.record).click();
  await yes(more, t.payments.record).click();
  // Pagada con su fuente: a mano, y que el banco aun no lo trae; en la linea, quien y por que.
  const paid = sheetDialog(page).getByTestId('paid-source');
  await expect(paid).toContainText('Met de hand als betaald genoteerd op');
  await expect(paid).toContainText('de bank laat het nog niet zien');
  const manual = (await paymentLines(page)).filter({ hasText: 'Handmatig' });
  await expect(manual).toContainText('Contant betaald aan de brandwacht');
  await expect(manual).toContainText('Ana Demo');
  // El justificante, con la descarga auditada.
  const download = page.waitForEvent('download');
  await sheetDialog(page).locator('.detail').getByRole('button', { name: new RegExp(`^${escapeRegExp(t.payments.evidence)}`) }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await expectAccessible(page, 'met de hand betaald');
  await capture(page, 'nl-invoice-paid-manual');
  // Y la propuesta retirada sigue ahi, como "Ingetrokken".
  await expect((await paymentLines(page)).filter({ hasText: 'Ingetrokken' })).toContainText('Dit was een voorschot');
});

test('si otra persona confirma antes, la tarjeta lo dice y vuelve a leer (409)', async ({ page, baseUrl, request, watch }) => {
  watch.expectHttpErrors(409);
  const list = await proposals(request, baseUrl);
  const [e] = list.filter((p) => p.factura.parte === 'Demo Havenbedrijf BV' && p.factura.sentido === 'saliente');

  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openEntry(page, 'receivables');
  await openGroup(page, t.aurora.money.proposals);
  const card = await openCard(page, proposalRow(page, e!.factura.numero!));
  await card.getByRole('button', { name: t.bank.confirm, exact: true }).click();
  await formButton(card, t.bank.confirm).click();
  // Intussen bevestigt Bram dezelfde betaling (via de API, met zijn eigen code).
  const done = await request.post(`${baseUrl}/api/v2/acciones`, {
    headers: { 'X-BMS-Token': token('bram'), 'Content-Type': 'application/json' },
    data: { accion: 'confirmar_pago', peticion_id: `e2e-${Date.now()}`, datos: { aplicacion_id: e!.id, rev: e!.rev } },
  });
  expect(done.status()).toBe(200);
  await yes(card, t.bank.confirm).click();
  await expect(panel(page).getByRole('alert')).toContainText(t.aurora.order.stale);
  await capture(page, 'nl-bank-conflict');
  // Vuelto a leer: la propuesta ya no esta.
  await expect(proposalRow(page, e!.factura.numero!)).toHaveCount(0);
  // Lo que confirmo Bram cuenta, con su nombre.
  await openInvoice(page, e!.factura.numero!);
  await expect((await paymentLines(page)).first()).toContainText('Bram Demo');
});

test('quien solo mira ve los cobros, los pagos y el banco, y ningun boton de una orden', async ({ page, baseUrl, request }) => {
  const list = await proposals(request, baseUrl);
  const waiting = list.find((p) => p.factura.sentido === 'saliente')!;
  await page.goto(`${baseUrl}/app`);
  await login(page, 'cas');
  await openEntry(page, 'receivables');
  await expect(balance(page)).toBeVisible();
  // Sin permiso para importar, tampoco el boton de importar.
  await expect(panel(page).getByRole('button', { name: t.aurora.money.import })).toHaveCount(0);
  await openGroup(page, t.aurora.money.proposals);
  const card = await openCard(page, proposalRow(page, waiting.factura.numero!));
  await expect(card.getByRole('button', { name: t.bank.confirm })).toHaveCount(0);
  await expect(card.getByRole('button', { name: t.payments.withdraw })).toHaveCount(0);
  await openInvoice(page, waiting.factura.numero!);
  await expect(sheetDialog(page).getByTestId('payment').first()).toContainText('Voorgesteld');
  const proposal = await openSheetRow(page, t.aurora.sheet.payment);
  await expect(proposal.getByRole('button', { name: t.bank.confirm })).toHaveCount(0);
  await expect(proposal.getByRole('button', { name: t.payments.withdraw })).toHaveCount(0);
  const more = await openSheetRow(page, t.aurora.sheet.more);
  await expect(more.getByRole('button', { name: t.payments.record })).toHaveCount(0);
  await capture(page, 'nl-invoice-read-only-payments');
});

test('despues de las ordenes, todo sigue cuadrando: los paneles, los tramos y la API', async ({ page, baseUrl, request }) => {
  const [inn, out] = [await cartera(request, baseUrl, 'saliente'), await cartera(request, baseUrl, 'entrante')];
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const [entry, c] of [
    ['receivables', inn],
    ['payables', out],
  ] as const) {
    await openEntry(page, entry);
    await expect(balance(page)).toContainText(euro(c.totales.pendiente_cent));
    await openGroup(page, t.money.ageing.title);
    for (const b of c.tramos.filter((x) => x.clave !== 'sin_fecha' || x.facturas > 0)) {
      await expect(panelRow(page, t.money.ageing.buckets[b.clave]).locator('.doc-end strong')).toHaveText(euro(b.importe_cent));
    }
    expect(c.tramos.reduce((n, b) => n + b.importe_cent, 0)).toBe(c.totales.pendiente_cent);
  }
});

test('capturas de cobrar, pagar y el banco en los tres idiomas y los dos temas', async ({ page, baseUrl }) => {
  test.setTimeout(600_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const theme of ['dark', 'light'] as const) {
    if (theme === 'light') await chooseTheme(page, 'light');
    for (const lang of ['nl', 'en', 'es'] as Lang[]) {
      const tx = TEXTS[lang];
      await setLang(page, lang);
      for (const entry of ['receivables', 'payables'] as const) {
        await openEntry(page, entry, lang);
        await expectAccessible(page, `${lang} ${theme} ${entry}`);
        await expectNoLeftovers(page, lang, `${lang} ${entry}`);
        await capture(page, `${lang}-money-${entry}`);
        await openGroup(page, tx.aurora.money.proposals);
        await expectAccessible(page, `${lang} ${theme} ${entry} propuestas`);
        await expectNoLeftovers(page, lang, `${lang} ${entry} propuestas`);
        await capture(page, `${lang}-money-${entry}-proposals`);
      }
      // Una factura pendiente con su tarjeta y el formulario de apuntar un pago.
      await openEntry(page, 'payables', lang);
      await openGroup(page, tx.aurora.money.week);
      const card = await openCard(page, panel(page).locator('.doc-list button.doc').first());
      await card.getByRole('button', { name: tx.payments.record, exact: true }).click();
      await expectAccessible(page, `${lang} ${theme} vastleggen`);
      await expectNoLeftovers(page, lang, `${lang} vastleggen`);
      await capture(page, `${lang}-money-record`);
      await card.locator('.order-form').getByRole('button', { name: tx.common.cancel }).click();
    }
    await setLang(page, 'nl');
  }
  await chooseTheme(page, 'dark');
  // En el movil: el panel entero, sin nada fuera de la ventana.
  await page.setViewportSize({ width: 400, height: 860 });
  for (const entry of ['receivables', 'payables'] as const) {
    await openEntry(page, entry);
    await settled(page);
    expect(await outsideTheWindow(page), entry).toEqual([]);
    await capture(page, `nl-money-${entry}-mobile`);
  }
  await openGroup(page, t.aurora.money.proposals);
  expect(await outsideTheWindow(page), 'te bevestigen').toEqual([]);
  // La hoja de una factura, tambien.
  await openInvoice(page, 'KT-202609');
  expect(await outsideTheWindow(page), 'hoja').toEqual([]);
  await capture(page, 'nl-money-invoice-mobile');
  await expect(folderProfile(page, 'K. Testpersoon Brandwacht (zzp)')).toBeVisible();
});
