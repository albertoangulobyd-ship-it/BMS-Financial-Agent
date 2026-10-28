// Una empresa, un solo «Openstaand» (revision del paso 16; paso 17: los paneles y Documentos de
// Aurora): la cifra del panel, la del resumen general de la conversacion (el Finance Bento) y la de
// cada carpeta dicen lo de la cartera, al centimo; los grupos suman (los tramos, lo pendiente; esta
// semana, lo vencido y lo de la semana). Demo Beveiligingsdiensten Noord decia € 10.702,57 en el
// resumen de Te betalen y € 10.340,54 en su carpeta y su ficha (la vista, que restaba la nota de
// credito sin enlazar DBN-CR-2026-09): ahora todos dicen lo de la cartera, y el abono va aparte.
// Va en su propio fichero, antes que daily.spec.ts: esa prueba enlaza la nota de credito y despues
// ya no hay ninguna sin enlazar (las pruebas comparten la base, en orden alfabetico).
import type { APIRequestContext } from '@playwright/test';
import type { Cartera, PartyRow } from '../src/lib/api-types';
import { capture, expect, expectAccessible, login, test, token } from './fixtures';
import { TEXTS, ask, euro, fill, openDocuments, openEntry, openFolder, openGroup, panel, panelRow, toHome } from './nav';

const t = TEXTS.nl;

async function api<T>(request: APIRequestContext, baseUrl: string, path: string): Promise<T> {
  const response = await request.get(`${baseUrl}${path}`, { headers: { 'X-BMS-Token': token('ana') } });
  expect(response.status(), path).toBe(200);
  return (await response.json()) as T;
}

const cartera = async (request: APIRequestContext, baseUrl: string, sentido: 'saliente' | 'entrante') =>
  (await api<{ cartera: Cartera }>(request, baseUrl, `/api/v2/cartera?sentido=${sentido}`)).cartera;

test('una empresa dice un solo Openstaand: el panel, el resumen, su carpeta y su ficha, al centimo', async ({ page, baseUrl, request }) => {
  const [inn, out] = [await cartera(request, baseUrl, 'saliente'), await cartera(request, baseUrl, 'entrante')];
  const providers = (await api<{ proveedores: PartyRow[] }>(request, baseUrl, '/api/v2/proveedores')).proveedores;
  const clients = (await api<{ clientes: PartyRow[] }>(request, baseUrl, '/api/v2/clientes')).clientes;
  for (const [rows, c] of [
    [providers, out],
    [clients, inn],
  ] as const) {
    for (const r of rows) {
      expect(r.deuda_cent, r.nombre).toBe(c.partes.find((p) => p.id === r.id)?.pendiente_cent ?? 0);
      expect(r.pendiente_cent, r.nombre).toBe(r.deuda_cent + r.abonos_sin_enlazar_cent);
    }
  }
  // Los grupos suman: los tramos dan lo pendiente; esta semana, lo vencido mas lo de la semana.
  for (const c of [inn, out]) expect(c.tramos.reduce((n, b) => n + b.importe_cent, 0)).toBe(c.totales.pendiente_cent);
  const week = out.esta_semana!;
  expect(week.sin_retener.importe_cent + week.retenido.importe_cent).toBe(out.totales.vencido_cent + out.totales.semana_cent);
  const credit = out.abonos_sin_enlazar.lista[0]!;
  const party = out.partes.find((p) => p.id === credit.parte_id)!;
  const row = providers.find((r) => r.id === party.id)!;
  expect(row.abonos_sin_enlazar_cent).toBe(credit.pendiente_cent);
  expect(row.pendiente_cent).not.toBe(row.deuda_cent);
  const creditText = fill(t.parties.unlinkedCredit, { amount: euro(credit.pendiente_cent) });

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // El panel: la cifra principal de cada lado y, en la antiguedad, cada tramo.
  for (const [entry, c] of [
    ['receivables', inn],
    ['payables', out],
  ] as const) {
    await openEntry(page, entry);
    await expect(panel(page).getByTestId('balance')).toContainText(euro(c.totales.pendiente_cent));
    await openGroup(page, t.money.ageing.title);
    for (const b of c.tramos.filter((x) => x.facturas > 0)) {
      await expect(panelRow(page, t.money.ageing.buckets[b.clave]).locator('.doc-end strong')).toHaveText(euro(b.importe_cent));
    }
  }
  await openEntry(page, 'payables');
  await openGroup(page, t.aurora.money.week);
  await expect(panel(page).locator('.list-title span')).toHaveText(String(week.facturas.length));

  // El resumen general (la conversacion): lo mismo, al centimo.
  await toHome(page);
  await ask(page, 'Geef me een overzicht');
  const bento = page.getByRole('region', { name: t.aurora.bento.label });
  await expect(bento).toContainText(euro(Math.max(0, inn.totales.pendiente_cent)));
  await expect(bento).toContainText(euro(Math.max(0, out.totales.pendiente_cent)));

  // Cada carpeta de Documentos: lo de la cartera debajo de la carpeta (o "Al corriente").
  await openDocuments(page);
  for (const r of [...providers, ...clients].slice(0, 12)) {
    const cell = page.getByTestId('folder-cell').filter({ has: page.locator('.gf-title').getByText(r.nombre, { exact: true }) });
    if (!(await cell.count())) continue;
    await expect(cell.locator('.ws-folder-caption > span')).toHaveText(r.deuda_cent > 0 ? euro(r.deuda_cent) : t.aurora.archive.upToDate);
  }
  // Su carpeta y su ficha: lo de la cartera, y el abono sin enlazar aparte.
  const profile = await openFolder(page, party.nombre!, 'provider');
  await expect(profile).toContainText(euro(party.pendiente_cent));
  await expect(profile.getByTestId('unlinked-credit')).toHaveText(creditText);
  await expectAccessible(page, 'carpeta con abono aparte');
  await capture(page, 'nl-provider-credit-apart');
});
