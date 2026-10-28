// La conversacion de Aurora (E4, paso 17): «Geef me een overzicht», «Dame un resumen general» y
// «Give me an overview» traen el resumen general (el Finance Bento de Aurora) con los datos de
// verdad. Lo de cobrar y lo de pagar son los pendientes de la cartera (GET /api/v2/cartera, al
// centimo) y el resumen dice que son saldos pendientes, no dinero disponible. Con axe y sin
// restos de otro idioma, a 1440 y a 400 px, y sin la rueda (la regla del dueno). «Terug naar
// de ruimte» vuelve a la rueda.
import type { APIRequestContext, Page } from '@playwright/test';
import type { Cartera } from '../src/lib/api-types';
import type { Lang } from '../src/i18n/langs';
import { capture, expect, expectAccessible, expectNoLeftovers, login, settled, test, token } from './fixtures';
import { TEXTS, setLang, toHome, wheel } from './nav';

/** Centimos -> "€ 36.396,20", como lib/format.ts (siempre en notacion neerlandesa). */
function euro(cents: number): string {
  const abs = Math.abs(cents);
  const units = String(Math.floor(abs / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `€\u00a0${cents < 0 ? '−' : ''}${units},${String(abs % 100).padStart(2, '0')}`;
}

/** Lo pendiente de un lado de la cartera, como lo lee el resumen (nunca menos de cero). */
async function pending(request: APIRequestContext, baseUrl: string, sentido: 'saliente' | 'entrante'): Promise<number> {
  const response = await request.get(`${baseUrl}/api/v2/cartera?sentido=${sentido}`, { headers: { 'X-BMS-Token': token('ana') } });
  expect(response.status()).toBe(200);
  return Math.max(0, ((await response.json()) as { cartera: Cartera }).cartera.totales.pendiente_cent);
}

/** Pregunta en la caja del inicio y espera a que conteste. */
async function ask(page: Page, lang: Lang, text: string): Promise<void> {
  const box = page.getByRole('textbox', { name: TEXTS[lang].aurora.composer.askLabel });
  await box.fill(text);
  await box.press('Enter');
  await expect(page.locator('.conversation')).toBeVisible();
  await expect(page.locator('.typing-dots')).toHaveCount(0, { timeout: 15_000 });
}

const QUESTIONS: [Lang, string][] = [
  ['nl', 'Geef me een overzicht'],
  ['es', 'Dame un resumen general'],
  ['en', 'Give me an overview'],
];

test('el resumen general (Finance Bento) con la cartera de verdad, en los tres idiomas', async ({ page, baseUrl, request }) => {
  test.setTimeout(240_000);
  const receivable = await pending(request, baseUrl, 'saliente');
  const payable = await pending(request, baseUrl, 'entrante');
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const [lang, question] of QUESTIONS) {
    await setLang(page, lang);
    await toHome(page);
    await ask(page, lang, question);
    const b = TEXTS[lang].aurora.bento;
    const bento = page.getByRole('region', { name: b.label });
    await expect(bento).toBeVisible();
    // Saldos pendientes, no dinero disponible; y las cifras de la cartera, al centimo.
    await expect(bento).toContainText(b.pending);
    await expect(bento).toContainText(b.pendingNote);
    await expect(bento).toContainText(euro(receivable));
    await expect(bento).toContainText(euro(payable));
    // Mientras se conversa, la rueda no esta.
    await expect(wheel(page)).toHaveCount(0);
    await settled(page);
    await expectAccessible(page, `${lang} resumen general`);
    await expectNoLeftovers(page, lang, `${lang} resumen general`);
    await capture(page, `${lang}-conversation-summary`);
  }
  await page.setViewportSize({ width: 400, height: 860 });
  await settled(page);
  await expectAccessible(page, 'en resumen general a 400 px');
  await capture(page, 'en-mobile-conversation-summary-400');
  await page.setViewportSize({ width: 1440, height: 900 });
  // «Back to the space»: la rueda otra vez, sin la conversacion.
  await page.getByRole('button', { name: TEXTS.en.aurora.chat.back }).click();
  await expect(wheel(page)).toBeVisible();
  await expect(page.locator('.conversation')).toHaveCount(0);
  await setLang(page, 'nl');
});
