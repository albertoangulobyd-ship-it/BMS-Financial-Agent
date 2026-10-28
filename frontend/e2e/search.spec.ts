// La busqueda de Aurora (E5, paso 17; la de filtros del paso 16 se fue con su pantalla): se
// llega por la entrada «Zoeken» de la rueda y por «Zoeken met filters» de una respuesta de la
// conversacion, con lo escrito. La caja busca en /api/v2/buscar tras la espera de Aurora (1,5 s
// pensando); el filtro de empresa sale en su pastilla con su X, «Filters wissen» los quita y
// «Opnieuw beginnen» lo quita todo; un resultado abre su factura (con el vuelo del orbe). Cada
// resultado es lo que dice el motor con los mismos filtros. En los tres idiomas, con axe y sin
// restos de otro idioma. Mientras se busca, la rueda no esta (la regla del dueno).
import type { APIRequestContext, Page } from '@playwright/test';
import type { InvoiceRow } from '../src/lib/api';
import type { PartyRow } from '../src/lib/api-types';
import type { Lang } from '../src/i18n/langs';
import { capture, expect, expectAccessible, expectNoLeftovers, login, settled, test, token } from './fixtures';
import { TEXTS, auroraRoot, crumbs, entryLabel, fill, landed, openEntry, openMenu, setLang, wheel } from './nav';

const t = TEXTS.nl;

/** El motor, con lo que manda la busqueda (searchQuery: 50 como mucho, por fecha). */
async function engine(request: APIRequestContext, baseUrl: string, query: Record<string, string>): Promise<{ total: number; facturas: InvoiceRow[] }> {
  const params = new URLSearchParams({ limite: '50', orden: 'fecha', ...query });
  const response = await request.get(`${baseUrl}/api/v2/buscar?${params}`, { headers: { 'X-BMS-Token': token('ana') } });
  expect(response.status()).toBe(200);
  return ((await response.json()) as { busqueda: { total: number; facturas: InvoiceRow[] } }).busqueda;
}

const box = (page: Page, lang: Lang = 'nl') => page.getByRole('textbox', { name: TEXTS[lang].aurora.composer.searchLabel });
const results = (page: Page, lang: Lang = 'nl') => page.getByRole('region', { name: TEXTS[lang].aurora.search.resultsLabel });
const links = (page: Page, lang: Lang = 'nl') => results(page, lang).getByRole('link');
const toggle = (page: Page, lang: Lang = 'nl') => page.getByRole('button', { name: new RegExp(`^${TEXTS[lang].aurora.search.filters}( \\d+)?$`) });

/** Busca lo escrito y espera a que pase la espera de Aurora. Mientras piensa (tambien por un
 *  filtro que se acaba de cambiar), Intro no busca, como en Aurora: se espera antes. */
async function search(page: Page, text: string, lang: Lang = 'nl') {
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await box(page, lang).fill(text);
  await box(page, lang).press('Enter');
  await expect(page.getByRole('status').filter({ hasText: TEXTS[lang].aurora.search.thinking })).toBeVisible();
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
}

/** Lo que ensena la busqueda es lo que dice el motor: cuantas y cuales, en su orden. */
async function sameAsEngine(page: Page, found: { total: number; facturas: InvoiceRow[] }, lang: Lang = 'nl') {
  const s = TEXTS[lang].aurora.search;
  if (found.total === 0) {
    await expect(page.getByText(s.noMatches)).toBeVisible();
    return;
  }
  await expect(results(page, lang)).toContainText(found.total === 1 ? s.foundOne : fill(s.found, { n: found.total }));
  await expect(links(page, lang)).toHaveCount(found.facturas.length);
  const numbers = await links(page, lang).locator('.result-info strong').allTextContents();
  expect(numbers).toEqual(found.facturas.map((f) => f.numero ?? fill(TEXTS[lang].records.invoice.fallbackTitle, { id: f.id })));
}

test('la busqueda (E5): lo escrito, el filtro de empresa en su pastilla, limpiar, empezar de nuevo y abrir', async ({ page, baseUrl, request }) => {
  const providers = ((await (await request.get(`${baseUrl}/api/v2/proveedores`, { headers: { 'X-BMS-Token': token('ana') } })).json()) as { proveedores: PartyRow[] })
    .proveedores;
  const jv = providers.find((p) => p.nombre.startsWith('J. Voorbeeld'))!;

  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openEntry(page, 'search');
  // El saludo cambia y la rueda se va; la caja es la de buscar, con el foco.
  await expect(page.getByRole('heading', { level: 1, name: t.aurora.home.searchTitle })).toBeVisible();
  await expect(wheel(page)).toHaveCount(0);
  await expect(box(page)).toBeFocused();
  await search(page, 'JV');
  await sameAsEngine(page, await engine(request, baseUrl, { texto: 'JV' }));
  await expectAccessible(page, 'zoeken');
  await expectNoLeftovers(page, 'nl', 'zoeken');
  await capture(page, 'nl-search');

  // Filters: el de la empresa, en su pastilla con su X; el contador lo cuenta.
  await toggle(page).click();
  await expect(toggle(page)).toHaveAttribute('aria-expanded', 'true');
  await page.getByRole('combobox', { name: t.aurora.search.partyChoose }).click();
  await page.getByRole('combobox', { name: t.aurora.search.partySearchLabel }).fill('Voorbeeld');
  await page.getByRole('option', { name: new RegExp(jv.nombre.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).first().click();
  await expect(toggle(page)).toContainText('1');
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await sameAsEngine(page, await engine(request, baseUrl, { texto: 'JV', proveedor_id: String(jv.id) }));
  const chip = page.locator('.active-filter-chips button').filter({ hasText: jv.nombre });
  await expect(chip).toBeVisible();
  await settled(page);
  await expectAccessible(page, 'zoeken met filters');
  await capture(page, 'nl-search-filters');
  // La X de la pastilla lo quita; «Filters wissen» tambien (lo escrito se queda).
  await chip.click();
  await expect(chip).toHaveCount(0);
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await sameAsEngine(page, await engine(request, baseUrl, { texto: 'JV' }));
  await page.getByRole('combobox', { name: t.aurora.search.partyChoose }).click();
  await page.getByRole('option', { name: new RegExp(jv.nombre.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).first().click();
  await page.getByRole('button', { name: new RegExp(`^${t.aurora.search.clearFilters}`) }).click();
  await expect(page.locator('.active-filter-chips')).toHaveCount(0);
  await expect(box(page)).toHaveValue('JV');

  // Sin nada que encaje: «Niets gevonden» y «Opnieuw beginnen», que lo quita todo.
  await search(page, 'zzzz-geen-factuur');
  await expect(page.getByText(t.aurora.search.noMatches)).toBeVisible();
  await capture(page, 'nl-search-empty');
  await page.getByRole('button', { name: t.aurora.search.startOver }).click();
  await expect(box(page)).toHaveValue('');
  await expect(results(page)).toHaveCount(0);

  // Un resultado abre su factura, en su lista, con el vuelo del orbe.
  await search(page, 'JV');
  const first = links(page).first();
  const number = ((await first.locator('.result-info strong').textContent()) ?? '').trim();
  await first.click();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await landed(page);
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(`${number.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) })).toBeVisible();
  expect(await crumbs(page)).toEqual([entryLabel('payables'), t.nav['invoices-in'].label, number]);
});

test('«Zoeken met filters» desde la conversacion, con lo escrito; y en ingles y en castellano', async ({ page, baseUrl, request }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // La conversacion encuentra «VD26» y ofrece buscarlo con filtros (E4 → E5).
  const ask = page.getByRole('textbox', { name: t.aurora.composer.askLabel });
  await ask.fill('VD26');
  await ask.press('Enter');
  await page.getByRole('button', { name: t.aurora.chat.withFilters }).click();
  await expect(page.getByRole('heading', { level: 1, name: t.aurora.home.searchTitle })).toBeVisible();
  await expect(box(page)).toHaveValue('VD26');
  await expect(page.locator('.search-thinking')).toHaveCount(0, { timeout: 15_000 });
  await sameAsEngine(page, await engine(request, baseUrl, { texto: 'VD26' }));
  for (const lang of ['en', 'es'] as Lang[]) {
    await setLang(page, lang);
    await openMenu(page, lang);
    await openEntry(page, 'search', lang);
    await expect(page.getByRole('heading', { level: 1, name: TEXTS[lang].aurora.home.searchTitle })).toBeVisible();
    await search(page, 'VD26', lang);
    await sameAsEngine(page, await engine(request, baseUrl, { texto: 'VD26' }), lang);
    await toggle(page, lang).click();
    await settled(page);
    await expectAccessible(page, `${lang} zoeken`);
    await expectNoLeftovers(page, lang, `${lang} zoeken`);
    await capture(page, `${lang}-search-filters`);
  }
  await setLang(page, 'nl');
});
