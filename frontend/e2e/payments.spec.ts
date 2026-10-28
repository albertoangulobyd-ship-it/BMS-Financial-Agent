// Cuentas por cobrar y por pagar con datos de verdad (paso 16, revision de Aurora §8.4): sobre
// la base de prueba, con el extracto de hoy que le anade scripts/crear_demo_e2e.py (cobros y
// pagos que el banco caso a medias y un ingreso que no es de ninguna factura). Las cifras de
// la tarjeta del inicio, de la cabecera de cada pantalla, de cada tramo y de cada lista dicen
// los mismos centimos que la API; y cada orden se da de verdad: confirmar un cobro propuesto,
// decir que una propuesta no es (con motivo), enlazar una linea del banco a su factura desde
// el banco y desde la factura, apuntar un pago ya hecho con motivo y justificante, el aviso
// cuando otra persona se adelanta (409) y quien solo mira, que no ve ningun boton. Las
// capturas, en los tres idiomas y los dos temas. Las pruebas van en orden: cambian la base.
import type { APIRequestContext, Page } from '@playwright/test';
import type { Lang } from '../src/i18n/langs';
import type { BankLines, Cartera, PaymentProposal } from '../src/lib/api-types';
import { partiesByOverdue } from '../src/screens/money-model';
import { capture, expect, expectAccessible, expectNoLeftovers, login, outsideTheWindow, settled, test, token, type Who } from './fixtures';
import { TEXTS, chooseTheme, crumbs, escapeRegExp, fill, go, readBadge, setLang, viewHeading } from './nav';

test.describe.configure({ mode: 'serial' });

const t = TEXTS.nl;

/** Un importe como lo escribe la app (format.ts): euro, espacio que no se parte y notacion
 *  neerlandesa. */
function euro(cents: number): string {
  const abs = Math.abs(cents);
  const units = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `€ ${cents < 0 ? '−' : ''}${units},${String(abs % 100).padStart(2, '0')}`;
}

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

const card = (page: Page, title: string) => page.getByTestId('summary-card').filter({ has: page.getByRole('heading', { level: 2, name: title }) });
const figure = (page: Page, label: string) => page.locator(`[data-testid="money-figure"][data-label="${label}"]`);
const bucket = (page: Page, key: string) => page.locator(`[data-testid="ageing-bucket"][data-bucket="${key}"]`);
const proposalCard = (page: Page, numero: string) => page.getByRole('article', { name: new RegExp(`^${escapeRegExp(numero)} · `) });

/** Abre una factura de la lista de su sentido, buscandola por su numero. */
async function openInvoice(page: Page, numero: string, list: 'invoices-out' | 'invoices-in' = 'invoices-out'): Promise<void> {
  await go(page, list);
  await page.getByRole('group', { name: t.invoices.filterLabel }).getByRole('button', { name: /^Alle/ }).click();
  await page.getByRole('searchbox').fill(numero);
  await page.getByRole('button', { name: `Factuur ${numero} openen` }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(`${escapeRegExp(numero)}$`) })).toBeVisible();
  await settled(page);
}

test('las cifras de cobrar y pagar: la tarjeta del inicio, la pantalla, los tramos y las listas, al centimo', async ({ page, baseUrl, request }) => {
  const [inn, out] = [await cartera(request, baseUrl, 'saliente'), await cartera(request, baseUrl, 'entrante')];
  const panel = (await api<{ panel: { dinero_entra: Cartera['totales']; dinero_sale: Cartera['totales'] } }>(request, baseUrl, '/api/v2/panel')).panel;
  // La cartera es el panel, al centimo (la misma funcion del motor).
  expect(inn.totales).toEqual(panel.dinero_entra);
  expect(out.totales).toEqual(panel.dinero_sale);

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // La tarjeta del resumen de Inicio (su fila «Overzicht» en el panel de Start, paso 17).
  await go(page, 'home');
  const receivable = card(page, t.overview.moneyIn.title);
  await expect(receivable).toContainText(euro(inn.totales.pendiente_cent));
  await expect(receivable).toContainText(euro(inn.totales.vencido_cent));
  await expect(receivable).toContainText(euro(inn.totales.proximos_30_cent));
  // El pie, cada cifra con su palabra: en singular si es 1 (la puerta del paso 16 vio "bij 1 klanten").
  const said = (n: number, many: string, one: string) => (n === 1 ? one : fill(many, { n }));
  const owing = (c: Cartera) => c.partes.filter((p) => p.id !== null).length;
  await expect(receivable).toContainText(
    fill(t.home.captionIn, { invoices: said(inn.totales.facturas, t.counts.invoices, t.counts.invoicesOne), parties: said(owing(inn), t.counts.clients, t.counts.clientsOne) })
  );
  await expect(receivable).not.toContainText(/(^|\D)1 (facturen|klanten)\b/);
  await expect(receivable.getByRole('button', { name: t.home.showToConfirmIn })).toHaveText(String(inn.por_confirmar.pagos));
  const payable = card(page, t.overview.moneyOut.title);
  await expect(payable).toContainText(euro(out.totales.pendiente_cent));
  await expect(payable).toContainText(
    fill(t.home.captionOut, { invoices: said(out.totales.facturas, t.counts.invoices, t.counts.invoicesOne), parties: said(owing(out), t.counts.providers, t.counts.providersOne) })
  );
  await expect(payable).not.toContainText(/(^|\D)1 (facturen|leveranciers)\b/);
  await expect(payable).toContainText(euro(out.totales.semana_cent));

  // La cabecera de la pantalla: las cuatro cifras y la nota de que no es dinero disponible.
  await page.getByRole('main').getByRole('button', { name: `${t.areas.receivables.label} · ${t.nav.receivables.label}` }).click();
  await expect(viewHeading(page, 'receivables')).toBeVisible();
  expect(await crumbs(page)).toEqual([t.areas.receivables.label]);
  await expect(figure(page, t.money.outstanding)).toContainText(euro(inn.totales.pendiente_cent));
  await expect(figure(page, t.money.overdue)).toContainText(euro(inn.totales.vencido_cent));
  await expect(figure(page, t.money.thisWeek)).toContainText(euro(inn.totales.semana_cent));
  await expect(figure(page, t.money.next30)).toContainText(euro(inn.totales.proximos_30_cent));
  await expect(page.getByText(t.money.note)).toBeVisible();
  // La antiguedad, a la vista al cobrar: cada tramo con lo suyo.
  for (const b of inn.tramos.filter((x) => x.clave !== 'sin_fecha' || x.facturas > 0)) {
    await expect(bucket(page, b.clave)).toContainText(euro(b.importe_cent));
  }
  // Lo que espera a alguien: las propuestas y lo que no casa, que abren el banco.
  await expect(page.getByRole('button', { name: fill(t.money.notices.confirmIn, { n: inn.por_confirmar.pagos }) })).toBeVisible();
  // Cada empresa, lo vencido primero (como la API, ordenado igual).
  const expected = partiesByOverdue(inn.partes).map((p) => p.nombre ?? '');
  const rows = page.getByRole('table', { name: t.money.parties.titleIn }).getByRole('row');
  await expect(rows).toHaveCount(expected.length + 1);
  for (const [i, name] of expected.entries()) await expect(rows.nth(i + 1)).toContainText(name);
  await expectAccessible(page, 'te ontvangen');
  await expectNoLeftovers(page, 'nl', 'te ontvangen');

  // Cada cifra y cada tramo abre la lista con su ficha, y la lista suma lo mismo.
  const checks: [() => Promise<void>, number][] = [
    [() => figure(page, t.money.outstanding).click(), inn.totales.pendiente_cent],
    [() => figure(page, t.money.overdue).click(), inn.totales.vencido_cent],
    [() => figure(page, t.money.next30).click(), inn.totales.proximos_30_cent],
    ...inn.tramos.filter((b) => b.facturas > 0).map((b) => [() => bucket(page, b.clave).click(), b.importe_cent] as [() => Promise<void>, number]),
  ];
  for (const [open, cents] of checks) {
    await go(page, 'receivables');
    await open();
    await expect(viewHeading(page, 'invoices-out')).toBeVisible();
    await expect(page.getByTestId('list-sum')).toContainText(euro(cents));
  }
  await capture(page, 'nl-receivables-bucket');

  // Te betalen: la misma forma; la antiguedad plegada, y lo limpio y lo retenido hasta el domingo.
  await go(page, 'payables');
  await expect(figure(page, t.money.outstanding)).toContainText(euro(out.totales.pendiente_cent));
  await expect(figure(page, t.money.thisWeek)).toContainText(euro(out.totales.semana_cent));
  const ageing = page.getByRole('button', { name: new RegExp(`^${escapeRegExp(t.money.ageing.title)}`) });
  await expect(ageing).toHaveAttribute('aria-expanded', 'false');
  const week = out.esta_semana!;
  await expect(page.getByTestId('week-clean')).toContainText(euro(week.sin_retener.importe_cent));
  await expect(page.getByTestId('week-held')).toContainText(euro(week.retenido.importe_cent));
  expect(week.sin_retener.importe_cent + week.retenido.importe_cent).toBe(out.totales.vencido_cent + out.totales.semana_cent);
  // Lo retenido que vence despues, con por que (el IBAN, el numero repetido...).
  for (const held of (out.retenido.lista ?? []).filter((f) => !week.facturas.some((w) => w.id === f.id))) {
    await expect(page.getByRole('main')).toContainText(held.numero ?? '');
  }
  await expect(page.getByRole('main')).toContainText('IBAN niet betaalbaar');
  // Dos facturas con el mismo numero y la misma empresa llevan su "1 van 2" y "2 van 2", como
  // en las listas (revision del paso 16: JV-2026-007 salia dos veces igual en lo retenido).
  const shown = [...week.facturas, ...(out.retenido.lista ?? []).filter((f) => !week.facturas.some((w) => w.id === f.id))];
  const repeated = shown.filter((f) => shown.filter((g) => g.numero === f.numero && g.parte === f.parte).length > 1);
  expect(repeated.length, 'la base de prueba retiene dos facturas con el mismo numero').toBeGreaterThanOrEqual(2);
  const weekRegion = page.getByRole('region', { name: new RegExp(`^${escapeRegExp(fill(t.money.week.title, { date: '' }).trim())}`) });
  for (const n of [1, 2]) {
    const name = fill(t.common.openRecord, { what: `${t.records.invoice.label} ${repeated[0]!.numero} (${fill(t.common.twin, { n, of: 2 })})` });
    await expect(weekRegion.getByRole('button', { name, exact: true })).toHaveCount(1);
  }
  await ageing.click();
  await expect(ageing).toHaveAttribute('aria-expanded', 'true');
  const overdue = out.tramos.find((b) => b.clave !== 'al_corriente' && b.facturas > 0)!;
  await bucket(page, overdue.clave).click();
  await expect(viewHeading(page, 'invoices-in')).toBeVisible();
  await expect(page.getByTestId('list-sum')).toContainText(euro(overdue.importe_cent));
  await go(page, 'payables');
  await figure(page, t.money.thisWeek).click();
  await expect(page.getByTestId('list-sum')).toContainText(euro(out.totales.semana_cent));

  // Una empresa abre su ficha (en su seccion) o su carpeta en Documentos.
  await go(page, 'payables');
  const first = partiesByOverdue(out.partes)[0]!;
  await page.getByRole('table', { name: t.money.parties.titleOut }).getByRole('button', { name: fill(t.common.openRecord, { what: first.nombre! }), exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name: first.nombre! })).toBeVisible();
  expect(await crumbs(page)).toEqual([t.areas.payables.label, first.nombre!]);
  await go(page, 'payables');
  await page.getByRole('button', { name: fill(t.money.parties.folderLabel, { name: first.nombre! }) }).click();
  await expect(page.getByRole('heading', { level: 1, name: `Documenten van ${first.nombre}` })).toBeVisible();
  expect(await crumbs(page)).toEqual([t.nav.documents.label, first.nombre!]);
});

test('confirmar un cobro que propuso el banco y decir que otro no es', async ({ page, baseUrl, request }) => {
  const list = await proposals(request, baseUrl);
  const a = proposalOf(list, 'Stichting Voorbeeld Zorggroep');
  const [b] = list.filter((p) => p.factura.parte === 'Demo Havenbedrijf BV' && p.factura.sentido === 'saliente');
  const before = (await cartera(request, baseUrl, 'saliente')).totales.pendiente_cent;

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // La fila del banco en el panel de Te ontvangen dice cuantos hay por confirmar.
  await expect.poll(() => readBadge(page, 'bank-in')).toBe(list.filter((p) => p.factura.sentido === 'saliente').length);
  // Desde el resumen de Inicio: "Te bevestigen" en la tarjeta abre el banco de cobrar.
  await go(page, 'home');
  await card(page, t.overview.moneyIn.title).getByRole('button', { name: t.home.showToConfirmIn }).click();
  await expect(viewHeading(page, 'bank-in')).toBeVisible();
  const cardA = proposalCard(page, a.factura.numero!);
  await expect(cardA).toContainText(a.movimiento!.concepto!);
  await expect(cardA.getByRole('list', { name: t.bank.matches })).toContainText(`${t.bank.match.referencia}: ${t.bank.yes}`);
  await expect(cardA.getByRole('list', { name: t.bank.matches })).toContainText(`${t.bank.match.contraparte}: ${t.bank.no}`);
  await expectAccessible(page, 'bankontvangsten');
  await capture(page, 'nl-bank-in');

  // Bevestigen: el dialogo ensena la linea del banco al lado de la factura, y no paga nada.
  await cardA.getByRole('button', { name: t.bank.confirm }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText(t.payments.confirmIntro);
  await expect(dialog).toContainText(a.movimiento!.contraparte!);
  await expectAccessible(page, 'bevestigen');
  await capture(page, 'nl-bank-confirm');
  await dialog.getByRole('button', { name: 'Betaling bevestigen' }).click();
  await expect(dialog).toBeHidden();
  await expect(cardA).toHaveCount(0);
  // Y la fila del banco en el panel cuenta uno menos.
  await expect.poll(() => readBadge(page, 'bank-in')).toBe(list.filter((p) => p.factura.sentido === 'saliente').length - 1);
  // Lo pendiente baja lo que se confirmo, y la factura dice pagada segun el banco, por quien.
  expect((await cartera(request, baseUrl, 'saliente')).totales.pendiente_cent).toBe(before - a.importe_cent);
  await openInvoice(page, a.factura.numero!);
  await expect(page.getByTestId('paid-source')).toContainText('Betaald volgens de bank op');
  const payment = page.getByTestId('payment').first();
  await expect(payment).toContainText('Bevestigd');
  await expect(payment).toContainText('door Ana Demo');
  await expect(payment).toContainText(a.movimiento!.concepto!);
  await expectAccessible(page, 'factuur betaald');
  await capture(page, 'nl-invoice-paid-bank');

  // Niet deze: con motivo (sin el, no se manda); la linea pasa a "Zonder factuur".
  await go(page, 'bank-in');
  const cardB = proposalCard(page, b!.factura.numero!);
  await cardB.getByRole('button', { name: t.bank.notThis }).click();
  await dialog.getByRole('button', { name: 'Betaling intrekken' }).click();
  await expect(dialog.getByRole('alert')).toContainText(fill(t.action.required, { field: t.payments.withdrawReason }));
  await dialog.getByLabel(t.payments.withdrawReason).fill('Het rekeningnummer is niet van deze klant; eerst navragen');
  await dialog.getByRole('button', { name: 'Betaling intrekken' }).click();
  await expect(dialog).toBeHidden();
  await expect(cardB).toHaveCount(0);
  const table = page.getByRole('table', { name: t.bank.unmatchedTitle });
  await expect(table).toContainText(b!.movimiento!.concepto!);
  // En la factura queda como "Ingetrokken", con su motivo.
  await openInvoice(page, b!.factura.numero!);
  await expect(page.getByTestId('payment').filter({ hasText: 'Ingetrokken' })).toContainText('Het rekeningnummer is niet van deze klant');
});

test('enlazar una linea del banco a su factura: desde el banco y desde la factura', async ({ page, baseUrl, request }) => {
  const lines = await unmatched(request, baseUrl, 'entrada');
  const withdrawn = lines.find((l) => l.contraparte === 'Demo Havenbedrijf BV')!;
  const loose = lines.find((l) => l.contraparte === 'Fictief Evenementen BV')!;
  const open = (await api<{ facturas: { id: number; numero: string; contraparte: string; pendiente_cent: number; estado_pago: string; sentido: string }[] }>(request, baseUrl, '/api/v2/facturas')).facturas;
  const waiting = new Set((await proposals(request, baseUrl)).map((p) => p.factura.id));
  // La factura de la linea retirada (su concepto la nombra) y la del ingreso suelto (su importe).
  const target = open.find((f) => withdrawn.concepto!.includes(f.numero))!;
  const other = open.find((f) => f.sentido === 'saliente' && f.estado_pago === 'pendiente' && f.pendiente_cent === loose.importe_cent && !waiting.has(f.id))!;

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // Desde el banco: "Aan een factuur koppelen" en la linea, elegir la factura y un motivo.
  await go(page, 'bank-in');
  const row = page.getByRole('table', { name: t.bank.unmatchedTitle }).getByRole('row').filter({ hasText: withdrawn.concepto! });
  await row.getByRole('button', { name: t.bank.link }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText(t.payments.recordIntro);
  // Ninguna factura viene elegida (revision del paso 16: se elegia la primera de la lista, que
  // no tenia nada que ver con la linea); sin elegir, no se manda nada.
  const choice = dialog.getByLabel(t.payments.invoiceField);
  await expect(choice).toHaveValue('');
  await expect(choice.locator('option').first()).toHaveText(t.payments.chooseInvoice);
  // La que nombra el concepto de la linea va marcada, entre las primeras (sin elegirla).
  const mark = t.payments.likelyMark.split(' · ').at(-1)!;
  await expect(choice.locator(`option[value="${target.id}"]`)).toHaveText(new RegExp(`^${escapeRegExp(target.numero)}.* · ${escapeRegExp(mark)}$`));
  await expect(choice.locator('option').nth(1)).toHaveText(new RegExp(`${escapeRegExp(mark)}$`));
  const sent: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/api/v2/acciones')) sent.push(r.url());
  });
  await dialog.getByLabel(t.payments.reasonField).fill('Toch deze factuur: de klant betaalde vanaf een nieuwe rekening');
  await dialog.getByRole('button', { name: 'Betaling vastleggen' }).click();
  await expect(dialog.getByRole('alert')).toContainText(fill(t.action.required, { field: t.payments.invoiceField }));
  expect(sent).toEqual([]);
  await choice.selectOption(String(target.id));
  // Lo que faltaba ya esta elegido: el aviso no se queda al lado.
  await expect(dialog.getByRole('alert')).toHaveCount(0);
  await capture(page, 'nl-bank-link');
  await dialog.getByRole('button', { name: 'Betaling vastleggen' }).click();
  await expect(dialog).toBeHidden();
  expect(sent).toHaveLength(1);
  await expect(row).toHaveCount(0);
  await openInvoice(page, target.numero);
  await expect(page.getByTestId('paid-source')).toContainText('Betaald volgens de bank op');

  // Desde la factura: "Betaling vastleggen" con la linea del banco; el importe, lo que queda.
  await openInvoice(page, other.numero);
  await page.getByRole('button', { name: t.payments.record }).click();
  await expect(dialog.getByLabel(t.payments.amount)).toHaveValue(`${Math.floor(other.pendiente_cent / 100)},${String(other.pendiente_cent % 100).padStart(2, '0')}`);
  await dialog.getByLabel(t.payments.bankLineField).selectOption(String(loose.id));
  await dialog.getByLabel(t.payments.reasonField).fill('Betaald via een evenementenbureau, bevestigd per mail');
  await dialog.getByRole('button', { name: 'Betaling vastleggen' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId('paid-source')).toContainText('Betaald volgens de bank op');
  const payment = page.getByTestId('payment').first();
  await expect(payment).toContainText('Fictief Evenementen BV');
  await expect(payment).toContainText('Betaald via een evenementenbureau');
  await expect(payment).toContainText('door Ana Demo');
  // Ya no sale entre lo que no casa.
  await go(page, 'bank-in');
  await expect(page.getByRole('table', { name: t.bank.unmatchedTitle })).toHaveCount(0);
  await expect(page.getByText(t.bank.noUnmatched)).toBeVisible();
});

test('apuntar un pago ya hecho, con motivo y justificante, y retirar una propuesta de pago', async ({ page, baseUrl, request }) => {
  const list = await proposals(request, baseUrl);
  const oost = proposalOf(list, 'Demo Brandwacht Oost BV', 'entrante');

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // En Te betalen, la propuesta de un pago al proveedor: no es (Niet deze).
  await go(page, 'bank-out');
  await expectAccessible(page, 'bankbetalingen');
  await capture(page, 'nl-bank-out');
  const cardP = proposalCard(page, oost.factura.numero!);
  await cardP.getByRole('button', { name: t.bank.notThis }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(t.payments.withdrawReason).fill('Dit was een voorschot, niet de factuur');
  await dialog.getByRole('button', { name: 'Betaling intrekken' }).click();
  await expect(cardP).toHaveCount(0);

  // A mano: el motivo es obligatorio, la fecha no puede ser futura, el importe no pasa de lo
  // que queda; con un justificante de su carpeta. "Er wordt niets betaald".
  await openInvoice(page, oost.factura.numero!, 'invoices-in');
  await page.getByRole('button', { name: t.payments.record }).click();
  await expect(dialog).toContainText('Er wordt niets betaald');
  await dialog.getByLabel(t.payments.amount).fill('99999,00');
  await dialog.getByLabel(t.payments.reasonField).fill('Contant betaald aan de brandwacht, kwitantie in de map');
  await dialog.getByRole('button', { name: 'Betaling vastleggen' }).click();
  await expect(dialog.getByRole('alert')).toContainText('Dat is meer dan wat nog openstaat');
  await dialog.getByLabel(t.payments.amount).fill('');
  await dialog.getByLabel(t.payments.payDate).fill('01-01-2099');
  await dialog.getByRole('button', { name: 'Betaling vastleggen' }).click();
  await expect(dialog.getByRole('alert')).toContainText(t.payments.future);
  const evidence = dialog.getByLabel(t.payments.evidenceField);
  await expect(evidence.locator('option')).not.toHaveCount(1);
  const docValue = await evidence.locator('option').nth(1).getAttribute('value');
  await evidence.selectOption(docValue!);
  await expectAccessible(page, 'betaling vastleggen');
  // Con la fecha futura todavia escrita: el aviso y el campo que lo causa, juntos.
  await capture(page, 'nl-record-payment');
  await dialog.getByLabel(t.payments.payDate).fill('');
  await dialog.getByRole('button', { name: 'Betaling vastleggen' }).click();
  await expect(dialog).toBeHidden();
  // Pagada con su fuente: a mano, por quien, y que el banco aun no lo trae.
  await expect(page.getByTestId('paid-source')).toContainText('Met de hand als betaald vastgelegd door Ana Demo');
  await expect(page.getByTestId('paid-source')).toContainText('de bank laat het nog niet zien');
  const manual = page.getByTestId('payment').filter({ hasText: 'Handmatig' });
  await expect(manual).toContainText('Contant betaald aan de brandwacht');
  const download = page.waitForEvent('download');
  await manual.getByRole('button', { name: t.payments.evidence }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await expectAccessible(page, 'met de hand betaald');
  await capture(page, 'nl-invoice-paid-manual');
  // Y la propuesta retirada sigue ahi, como "Ingetrokken".
  await expect(page.getByTestId('payment').filter({ hasText: 'Ingetrokken' })).toContainText('Dit was een voorschot');
  // En la lista, "Betaald" tambien dice de donde sale (decision 5): aqui, a mano y aun sin el
  // banco; lo que trajo el banco, "volgens de bank".
  await go(page, 'invoices-in');
  await page.getByRole('group', { name: t.invoices.filterLabel }).getByRole('button', { name: /^Betaald/ }).click();
  const paidRow = page.getByRole('table').getByRole('row').filter({ hasText: oost.factura.numero! });
  await expect(paidRow.getByTestId('payment-state')).toHaveText('Betaald');
  await expect(paidRow.getByTestId('paid-source-short')).toHaveText(t.payments.listManual);
  await capture(page, 'nl-invoices-paid-source');
  await go(page, 'invoices-out');
  await page.getByRole('group', { name: t.invoices.filterLabel }).getByRole('button', { name: /^Betaald/ }).click();
  await expect(page.getByTestId('paid-source-short').filter({ hasText: t.payments.listBank }).first()).toBeVisible();
});

test('si otra persona confirma antes, el dialogo lo dice y vuelve a leer (409)', async ({ page, baseUrl, request, watch }) => {
  watch.expectHttpErrors(409);
  const list = await proposals(request, baseUrl);
  const [e] = list.filter((p) => p.factura.parte === 'Demo Havenbedrijf BV' && p.factura.sentido === 'saliente');

  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'bank-in');
  const cardE = proposalCard(page, e!.factura.numero!);
  await cardE.getByRole('button', { name: t.bank.confirm }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // Intussen bevestigt Bram dezelfde betaling (via de API, met zijn eigen code).
  const done = await request.post(`${baseUrl}/api/v2/acciones`, {
    headers: { 'X-BMS-Token': token('bram'), 'Content-Type': 'application/json' },
    data: { accion: 'confirmar_pago', peticion_id: `e2e-${Date.now()}`, datos: { aplicacion_id: e!.id, rev: e!.rev } },
  });
  expect(done.status()).toBe(200);
  await dialog.getByRole('button', { name: 'Betaling bevestigen' }).click();
  await expect(dialog.getByRole('alert')).toContainText('Iemand anders heeft dit net gewijzigd');
  await capture(page, 'nl-bank-conflict');
  await dialog.getByRole('button', { name: t.common.reload }).click();
  await expect(dialog).toBeHidden();
  await expect(cardE).toHaveCount(0);
  // Lo que confirmo Bram cuenta, con su nombre.
  await openInvoice(page, e!.factura.numero!);
  await expect(page.getByTestId('payment').first()).toContainText('door Bram Demo');
});

test('quien solo mira ve los cobros, los pagos y el banco, y ningun boton de una orden', async ({ page, baseUrl, request }) => {
  const list = await proposals(request, baseUrl);
  const waiting = list.find((p) => p.factura.sentido === 'saliente')!;
  await page.goto(`${baseUrl}/app`);
  await login(page, 'cas');
  await go(page, 'receivables');
  await expect(figure(page, t.money.outstanding)).toBeVisible();
  await go(page, 'bank-in');
  const cardW = proposalCard(page, waiting.factura.numero!);
  await expect(cardW).toBeVisible();
  await expect(cardW.getByRole('button', { name: t.bank.confirm })).toHaveCount(0);
  await expect(cardW.getByRole('button', { name: t.bank.notThis })).toHaveCount(0);
  await expect(page.getByRole('button', { name: t.bank.link })).toHaveCount(0);
  await openInvoice(page, waiting.factura.numero!);
  await expect(page.getByTestId('payment').first()).toContainText('Voorgesteld');
  await expect(page.getByRole('button', { name: t.payments.record })).toHaveCount(0);
  await expect(page.getByRole('button', { name: t.bank.confirm })).toHaveCount(0);
  await expect(page.getByRole('button', { name: t.payments.withdraw })).toHaveCount(0);
  await capture(page, 'nl-invoice-read-only-payments');
});

test('despues de las ordenes, todo sigue cuadrando: el inicio, las pantallas y la API', async ({ page, baseUrl, request }) => {
  const [inn, out] = [await cartera(request, baseUrl, 'saliente'), await cartera(request, baseUrl, 'entrante')];
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'home');
  await expect(card(page, t.overview.moneyIn.title)).toContainText(euro(inn.totales.pendiente_cent));
  await expect(card(page, t.overview.moneyOut.title)).toContainText(euro(out.totales.pendiente_cent));
  await go(page, 'receivables');
  await expect(figure(page, t.money.outstanding)).toContainText(euro(inn.totales.pendiente_cent));
  await figure(page, t.money.outstanding).click();
  await expect(page.getByTestId('list-sum')).toContainText(euro(inn.totales.pendiente_cent));
  await go(page, 'payables');
  await expect(figure(page, t.money.outstanding)).toContainText(euro(out.totales.pendiente_cent));
  await figure(page, t.money.outstanding).click();
  await expect(page.getByTestId('list-sum')).toContainText(euro(out.totales.pendiente_cent));
});

test('capturas de cobrar, pagar y el banco en los tres idiomas y los dos temas', async ({ page, baseUrl }) => {
  test.setTimeout(600_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const theme of ['dark', 'light'] as const) {
    if (theme === 'light') await chooseTheme(page, 'light');
    for (const lang of ['nl', 'en', 'es'] as Lang[]) {
      await setLang(page, lang);
      for (const view of ['receivables', 'payables', 'bank-in', 'bank-out', 'invoices-out'] as const) {
        await go(page, view, lang);
        await expectAccessible(page, `${lang} ${theme} ${view}`);
        await expectNoLeftovers(page, lang, `${lang} ${view}`);
        await capture(page, `${lang}-money-${view}`);
      }
      // Una factura con sus pagos y el dialogo de apuntar uno.
      await go(page, 'invoices-out', lang);
      await page.getByRole('group', { name: TEXTS[lang].invoices.filterLabel }).getByRole('button', { name: new RegExp(`^${escapeRegExp(TEXTS[lang].money.outstanding)}`) }).click();
      await page.getByRole('table').getByRole('row').nth(1).getByRole('button').first().click();
      await expect(page.getByRole('heading', { level: 2, name: new RegExp(`^${escapeRegExp(TEXTS[lang].payments.title)}`) })).toBeVisible();
      await expectNoLeftovers(page, lang, `${lang} factuur`);
      await capture(page, `${lang}-money-invoice`);
      await page.getByRole('button', { name: TEXTS[lang].payments.record }).click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await expectAccessible(page, `${lang} ${theme} vastleggen`);
      await expectNoLeftovers(page, lang, `${lang} vastleggen`);
      await capture(page, `${lang}-money-record`);
      await page.getByRole('dialog').getByRole('button', { name: TEXTS[lang].common.cancel }).click();
    }
    await setLang(page, 'nl');
  }
  // En el movil: las cifras una debajo de otra, sin nada fuera de la ventana.
  await page.setViewportSize({ width: 400, height: 860 });
  for (const view of ['receivables', 'payables', 'bank-in'] as const) {
    await go(page, view);
    expect(await outsideTheWindow(page), view).toEqual([]);
    await capture(page, `nl-money-${view}-mobile`);
  }
});
