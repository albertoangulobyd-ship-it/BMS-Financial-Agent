// La busqueda con filtros (revision del paso 16: §1b filas 28 a 35, que no estaban montadas).
// Se llega desde Ctrl+K y desde la caja del inicio con lo escrito; los filtros salen en
// pastillas con su X, "Filters" lleva cuantos hay, "Filters wissen" los quita, "Opnieuw
// beginnen" lo quita todo, un resultado abre su factura y "Terug" vuelve a la busqueda como
// estaba, y "Sluiten" vuelve a donde se estaba. Cada resultado es lo que dice el motor
// (GET /api/v2/buscar con los mismos filtros). En los tres idiomas, con axe y sin restos.
import type { APIRequestContext, Page } from '@playwright/test';
import type { InvoiceRow } from '../src/lib/api';
import type { PartyRow } from '../src/lib/api-types';
import type { Lang } from '../src/i18n/langs';
import { capture, expect, expectAccessible, expectNoLeftovers, login, settled, test, token } from './fixtures';
import { TEXTS, back, crumbs, fill, go, setLang, viewHeading } from './nav';

const t = TEXTS.nl;

async function engine(request: APIRequestContext, baseUrl: string, query: Record<string, string>): Promise<{ total: number; facturas: InvoiceRow[] }> {
  const params = new URLSearchParams({ limite: '50', orden: 'fecha', ...query });
  const response = await request.get(`${baseUrl}/api/v2/buscar?${params}`, { headers: { 'X-BMS-Token': token('ana') } });
  expect(response.status()).toBe(200);
  return ((await response.json()) as { busqueda: { total: number; facturas: InvoiceRow[] } }).busqueda;
}

const results = (page: Page, lang: Lang = 'nl') => page.getByRole('region', { name: TEXTS[lang].aurora.search.resultsLabel });
const resultButtons = (page: Page, lang: Lang = 'nl') => results(page, lang).getByRole('button');
const toggle = (page: Page, lang: Lang = 'nl') => page.getByRole('button', { name: new RegExp(`^${TEXTS[lang].aurora.search.filters}(?: \\d+)?$`) });
/** "Zoeken" del formulario (el de la cabecera abre Ctrl+K). */
const submit = (page: Page, lang: Lang = 'nl') =>
  page.getByRole('search', { name: TEXTS[lang].finder.title }).getByRole('button', { name: TEXTS[lang].finder.submit, exact: true }).first();

/** Lo que ensena la pantalla es lo que dice el motor: cuantas y cuales, en su orden. */
async function sameAsEngine(page: Page, found: { total: number; facturas: InvoiceRow[] }) {
  if (found.total === 0) {
    await expect(page.getByText(t.aurora.search.noMatches)).toBeVisible();
    return;
  }
  await expect(results(page)).toContainText(found.total === 1 ? t.finder.headingOne : fill(t.finder.heading, { n: found.total }));
  await expect(resultButtons(page)).toHaveCount(found.facturas.length);
  const names = await resultButtons(page).evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')));
  expect(names).toEqual(found.facturas.map((f) => fill(t.common.openRecord, { what: `${t.records.invoice.label} ${f.numero ?? f.id}` })));
}

test('la busqueda con filtros: lo escrito, cada filtro en su pastilla, limpiar, empezar de nuevo, abrir y cerrar', async ({ page, baseUrl, request }) => {
  const providers = ((await (await request.get(`${baseUrl}/api/v2/proveedores`, { headers: { 'X-BMS-Token': token('ana') } })).json()) as { proveedores: PartyRow[] })
    .proveedores;
  const jv = providers.find((p) => p.nombre.startsWith('J. Voorbeeld'))!;

  await page.goto(`${baseUrl}/app`);
  await login(page);
  // Desde Te betalen, con Ctrl+K: lo escrito pasa a la busqueda con filtros.
  await go(page, 'payables');
  await page.keyboard.press('Control+k');
  const palette = page.getByRole('dialog', { name: t.palette.title });
  await palette.getByRole('combobox').fill('JV');
  await palette.getByRole('button', { name: t.finder.withFilters }).click();
  await expect(page.getByRole('heading', { level: 1, name: t.finder.title })).toBeVisible();
  expect((await crumbs(page)).at(-1)).toBe(t.records.search.fallbackTitle);
  await expect(page.getByLabel(t.finder.query)).toHaveValue('JV');
  await sameAsEngine(page, await engine(request, baseUrl, { texto: 'JV' }));
  await expectAccessible(page, 'zoeken');
  await expectNoLeftovers(page, 'nl', 'zoeken');
  await capture(page, 'nl-search');

  // Filters: el contador, el panel, y cada filtro como una pastilla que se quita con su X.
  await toggle(page).click();
  await expect(toggle(page)).toHaveAttribute('aria-expanded', 'true');
  await page.getByLabel(t.finder.party).selectOption(`proveedor:${jv.id}`);
  await expect(toggle(page)).toContainText('1');
  await sameAsEngine(page, await engine(request, baseUrl, { texto: 'JV', proveedor_id: String(jv.id) }));
  await page.getByLabel(t.finder.kind).selectOption('factura');
  await page.getByLabel(t.finder.dateFrom).fill('01-01-2026');
  await page.getByLabel(t.finder.dateTo).fill('31-12-2026');
  await page.getByLabel(`${t.finder.amountFrom} (€)`).fill('100');
  await submit(page).click();
  await expect(toggle(page)).toContainText('5');
  const filtered = { texto: 'JV', proveedor_id: String(jv.id), tipo: 'factura', fecha_desde: '2026-01-01', fecha_hasta: '2026-12-31', importe_min: '100,00' };
  await sameAsEngine(page, await engine(request, baseUrl, filtered));
  for (const chip of [jv.nombre, 'Vanaf 01-01-2026', 'Tot en met 31-12-2026', 'Vanaf € 100,00']) {
    await expect(page.getByRole('button', { name: fill(t.aurora.search.removeFilter, { name: chip }) })).toBeVisible();
  }
  await expectAccessible(page, 'zoeken met filters');
  await capture(page, 'nl-search-filters');
  await page.getByRole('button', { name: fill(t.aurora.search.removeFilter, { name: 'Tot en met 31-12-2026' }) }).click();
  await expect(toggle(page)).toContainText('4');
  const { fecha_hasta: _dropped, ...withoutTo } = filtered;
  await sameAsEngine(page, await engine(request, baseUrl, withoutTo));
  // Lo que no se entiende se dice, y no se busca.
  await page.getByLabel(`${t.finder.amountTo} (€)`).fill('veel');
  await submit(page).click();
  await expect(page.getByRole('search', { name: t.finder.title }).getByRole('alert')).toContainText(fill(t.finder.badAmount, { field: t.finder.amountTo }));
  await page.getByLabel(`${t.finder.amountTo} (€)`).fill('');
  // El pago: vervallen.
  await page.getByLabel(t.finder.payment).selectOption('vencida');
  await sameAsEngine(page, await engine(request, baseUrl, { ...withoutTo, vencida: 'si' }));
  // Filters wissen: sin pastillas, sin contador; lo escrito se queda.
  await page.getByRole('button', { name: new RegExp(`^${t.aurora.search.clearFilters}`) }).click();
  await expect(page.getByRole('button', { name: new RegExp(`^${t.aurora.search.removeFilter.split('{')[0]}`) })).toHaveCount(0);
  await expect(page.getByLabel(t.finder.query)).toHaveValue('JV');
  await sameAsEngine(page, await engine(request, baseUrl, { texto: 'JV' }));

  // Un resultado abre su factura; Terug vuelve a la busqueda tal como estaba.
  await page.getByLabel(t.finder.kind).selectOption('factura');
  const first = resultButtons(page).first();
  const name = (await first.getAttribute('aria-label'))!;
  await first.click();
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(`${name.split(' ').slice(1, 2)[0]}$`) })).toBeVisible();
  await back(page);
  await expect(page.getByLabel(t.finder.kind)).toHaveValue('factura');
  await expect(page.getByLabel(t.finder.query)).toHaveValue('JV');

  // Sin nada que encaje: "Niets gevonden" y "Opnieuw beginnen", que lo quita todo.
  await page.getByLabel(t.finder.query).fill('zzzz-geen-factuur');
  await submit(page).click();
  await expect(page.getByText(t.aurora.search.noMatches)).toBeVisible();
  await capture(page, 'nl-search-empty');
  await page.getByRole('button', { name: t.aurora.search.startOver }).click();
  await expect(page.getByLabel(t.finder.query)).toHaveValue('');
  await expect(page.getByText(t.finder.start)).toBeVisible();

  // Sluiten: vuelve a donde se estaba (Te betalen).
  await page.getByRole('button', { name: t.finder.close, exact: true }).click();
  await expect(viewHeading(page, 'payables')).toBeVisible();
});

test('desde la caja del inicio, con lo escrito; y en ingles y en castellano', async ({ page, baseUrl, request }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const box = page.getByRole('textbox', { name: t.ask.label });
  await box.fill('VD26');
  await box.press('Enter');
  await page.getByRole('button', { name: t.finder.withFilters }).click();
  await expect(page.getByRole('heading', { level: 1, name: t.finder.title })).toBeVisible();
  await expect(page.getByLabel(t.finder.query)).toHaveValue('VD26');
  await sameAsEngine(page, await engine(request, baseUrl, { texto: 'VD26' }));
  for (const lang of ['en', 'es'] as Lang[]) {
    const tx = TEXTS[lang];
    await setLang(page, lang);
    await expect(page.getByRole('heading', { level: 1, name: tx.finder.title })).toBeVisible();
    await toggle(page, lang).click();
    await page.getByLabel(tx.finder.payment).selectOption('pendiente');
    await expect(results(page, lang)).toBeVisible();
    await settled(page);
    await expectAccessible(page, `${lang} zoeken`);
    await expectNoLeftovers(page, lang, `${lang} zoeken`);
    await capture(page, `${lang}-search-filters`);
    await page.getByRole('button', { name: new RegExp(`^${tx.aurora.search.clearFilters}`) }).click();
    await toggle(page, lang).click();
  }
  await setLang(page, 'nl');
});
