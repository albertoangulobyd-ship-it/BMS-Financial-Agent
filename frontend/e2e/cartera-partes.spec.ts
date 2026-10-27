// Una empresa, un solo «Openstaand» (revision del paso 16): Demo Beveiligingsdiensten Noord decia
// € 10.702,57 en el resumen de Te betalen (la cartera) y € 10.340,54 en Leveranciers, su carpeta y
// su ficha (la vista, que resta la nota de credito sin enlazar DBN-CR-2026-09). Va en su propio
// fichero, antes que daily.spec.ts: esa prueba enlaza la nota de credito y despues ya no hay
// ninguna sin enlazar (las pruebas comparten la base, en orden alfabetico).
import type { APIRequestContext } from '@playwright/test';
import type { Cartera, PartyRow } from '../src/lib/api-types';
import { capture, expect, expectAccessible, login, test, token } from './fixtures';
import { TEXTS, escapeRegExp, fill, go } from './nav';

const t = TEXTS.nl;

/** Un importe como lo escribe la app (format.ts). */
function euro(cents: number): string {
  const abs = Math.abs(cents);
  const units = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `€\u00a0${cents < 0 ? '−' : ''}${units},${String(abs % 100).padStart(2, '0')}`;
}

async function api<T>(request: APIRequestContext, baseUrl: string, path: string): Promise<T> {
  const response = await request.get(`${baseUrl}${path}`, { headers: { 'X-BMS-Token': token('ana') } });
  expect(response.status(), path).toBe(200);
  return (await response.json()) as T;
}

const cartera = async (request: APIRequestContext, baseUrl: string, sentido: 'saliente' | 'entrante') =>
  (await api<{ cartera: Cartera }>(request, baseUrl, `/api/v2/cartera?sentido=${sentido}`)).cartera;

test('una empresa dice un solo Openstaand: el resumen, su lista, su carpeta y su ficha, al centimo', async ({ page, baseUrl, request }) => {
  // Revision del paso 16: Beveiligingsdiensten Noord decia € 10.702,57 en el resumen (la
  // cartera) y € 10.340,54 en Leveranciers, su carpeta y su ficha (la vista, que resta el abono
  // sin enlazar DBN-CR-2026-09). Ahora todos dicen lo de la cartera, y el abono va aparte.
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
  const credit = out.abonos_sin_enlazar.lista[0]!;
  const party = out.partes.find((p) => p.id === credit.parte_id)!;
  const row = providers.find((r) => r.id === party.id)!;
  expect(row.abonos_sin_enlazar_cent).toBe(credit.pendiente_cent);
  expect(row.pendiente_cent).not.toBe(row.deuda_cent);
  const creditText = fill(t.parties.unlinkedCredit, { amount: euro(credit.pendiente_cent) });

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // Te betalen › Overzicht › Per leverancier.
  await go(page, 'payables');
  const perParty = page.getByRole('table', { name: t.money.parties.titleOut }).getByRole('row').filter({ has: page.getByText(party.nombre!, { exact: true }) });
  await expect(perParty).toContainText(euro(party.pendiente_cent));
  // Te betalen › Leveranciers y Te ontvangen › Klanten: cada fila, lo de la cartera.
  for (const [view, rows] of [
    ['providers', providers],
    ['clients', clients],
  ] as const) {
    await go(page, view);
    const table = page.getByRole('table');
    for (const r of rows) {
      const line = table.getByRole('row').filter({ has: page.getByText(r.nombre, { exact: true }) });
      // Sin nada en euros y con facturas en otra moneda, la columna dice «—» y cuantas (paso 15).
      const onlyOther = r.deuda_cent === 0 && (r.sin_importe ?? 0) > 0;
      await expect(line, r.nombre).toContainText(onlyOther ? `—${fill(r.sin_importe === 1 ? t.parties.notInEuroOne : t.parties.notInEuro, { n: r.sin_importe! })}` : euro(r.deuda_cent));
    }
  }
  await go(page, 'providers');
  const listed = page.getByRole('table').getByRole('row').filter({ has: page.getByText(party.nombre!, { exact: true }) });
  await expect(listed.getByTestId('unlinked-credit')).toHaveText(creditText);
  await capture(page, 'nl-providers-credit-apart');
  // Su ficha.
  await listed.getByRole('button').first().click();
  await expect(page.getByRole('heading', { level: 1, name: party.nombre! })).toBeVisible();
  await expect(page.getByRole('main')).toContainText(fill(t.parties.openAmount, { amount: euro(party.pendiente_cent) }));
  await expect(page.getByTestId('unlinked-credit')).toHaveText(creditText);
  // Su carpeta en Documentos (la rejilla y la ficha de la carpeta).
  await go(page, 'documents');
  const cell = page.getByRole('list', { name: TEXTS.nl.documents.tabAll, exact: true }).getByRole('listitem', { name: party.nombre!, exact: true });
  await expect(cell).toContainText(fill(t.documents.outstanding, { amount: euro(party.pendiente_cent) }));
  await cell.getByRole('button', { name: new RegExp(`^${escapeRegExp(party.nombre!)} (openen|sluiten)`) }).click();
  const folderProfile = page.getByRole('region', { name: party.nombre!, exact: true });
  await expect(folderProfile).toContainText(euro(party.pendiente_cent));
  await expect(folderProfile.getByTestId('unlinked-credit')).toHaveText(creditText);
  await expectAccessible(page, 'carpeta con abono aparte');
});
