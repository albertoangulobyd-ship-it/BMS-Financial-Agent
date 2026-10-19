// Las alertas con el componente Status del dueno ("Asi quiero las alertas"): cada estado es
// una pastilla con su punto y SIEMPRE su texto; el punto late solo en lo que pide hacer algo
// ya (en la Werklijst, lo bloqueado y lo urgente), y deja de latir para quien pide menos
// movimiento. Capturas de las pastillas en NL y EN.
import type { Page } from '@playwright/test';
import { capture, expect, expectAccessible, login, test } from './fixtures';

interface Pill {
  variant: string;
  label: string;
  pings: boolean;
}

/** Las pastillas que se ven, con su variante, su texto y si su punto late de verdad (la
 *  animacion del ::before del punto, como la pinta el navegador). */
async function pills(page: Page): Promise<Pill[]> {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('[data-slot="status"]'))
      .filter((p) => p.getBoundingClientRect().width > 0)
      .map((p) => {
        const dot = p.querySelector('[data-slot="status-indicator"]');
        const animation = dot ? getComputedStyle(dot, '::before').animationName : 'none';
        return {
          variant: p.dataset.variant ?? '',
          label: (p.querySelector('[data-slot="status-label"]')?.textContent ?? '').trim(),
          pings: animation !== 'none',
        };
      })
  );
}

test('el punto late solo en lo que pide hacer algo ya, y siempre con su texto', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const menu = page.getByRole('navigation', { name: 'Hoofdmenu' });

  await menu.getByRole('button', { name: /^Werklijst/ }).click();
  await expect(page.getByRole('table')).toBeVisible();
  const queue = await pills(page);
  expect(queue.length).toBeGreaterThan(0);
  for (const p of queue) expect(p.label, 'una pastilla sin texto').not.toBe('');
  // Laten Geblokkeerd (rojo) y Urgent (naranja); Aandacht y Normaal, quietos.
  const pinging = queue.filter((p) => p.pings);
  expect(pinging.length).toBeGreaterThan(0);
  for (const p of pinging) expect(['Geblokkeerd', 'Urgent'], p.label).toContain(p.label);
  for (const p of queue.filter((q) => q.label === 'Aandacht' || q.label === 'Normaal')) expect(p.pings, p.label).toBe(false);
  expect(queue.find((p) => p.label === 'Geblokkeerd')?.variant).toBe('error');
  await capture(page, 'nl-status-work-queue');

  // Una lista de facturas: el pago y el control quietos; solo laten las prioridades que piden algo.
  await menu.getByRole('button', { name: /^Inkomend/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inkomend' })).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
  // Que la pantalla de antes ya no este (la animacion entre pestanas).
  await expect(page.getByRole('heading', { level: 1, name: 'Werklijst' })).toHaveCount(0);
  const invoices = await pills(page);
  for (const p of invoices.filter((q) => q.pings)) expect(['Geblokkeerd', 'Urgent'], p.label).toContain(p.label);
  expect(invoices.some((p) => p.label === 'Openstaand' && !p.pings)).toBe(true);

  // Las cuentas por verificar laten (hay que llamar), en naranja; una ya verificada, no.
  // (Las otras pruebas usan la misma base: aqui puede haber una ya verificada por telefono.)
  await menu.getByRole('button', { name: /^IBAN-controles/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'IBAN-controles' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'Inkomend' })).toHaveCount(0);
  await expect(page.locator('article').first()).toBeVisible();
  const iban = await pills(page);
  expect(iban.length).toBeGreaterThan(1);
  for (const p of iban) {
    const toVerify = p.label === 'Te verifiëren' || p.label === 'Geregistreerd, niet geverifieerd';
    expect(p.pings, p.label).toBe(toVerify);
    if (toVerify) expect(p.variant, p.label).toBe('warning');
  }
  await expectAccessible(page, 'nl iban-controles (pastillas)');

  // La marca de prueba de la cabecera: aviso, sin latir.
  const chip = page.getByTestId('test-data-chip');
  await expect(chip).toHaveAttribute('data-variant', 'warning');
  await expect(chip).toContainText('Testgegevens');
  expect(await chip.evaluate((el) => getComputedStyle(el.querySelector('[data-slot="status-indicator"]')!, '::before').animationName)).toBe('none');

  // En ingles, el mismo estado con su texto.
  await page.getByRole('button', { name: 'English' }).first().click();
  await page.getByRole('navigation', { name: 'Main menu' }).getByRole('button', { name: /^Work queue/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Work queue' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'IBAN checks' })).toHaveCount(0);
  await expect(page.getByRole('table')).toBeVisible();
  const en = await pills(page);
  for (const p of en.filter((q) => q.pings)) expect(['Blocked', 'Urgent'], p.label).toContain(p.label);
  await capture(page, 'en-status-work-queue');
  await page.getByRole('button', { name: 'Nederlands' }).first().click();
});

test('quien pide menos movimiento no ve latir nada', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await page.getByRole('navigation', { name: 'Hoofdmenu' }).getByRole('button', { name: /^Werklijst/ }).click();
  await expect(page.getByRole('table')).toBeVisible();
  const queue = await pills(page);
  expect(queue.some((p) => p.label === 'Geblokkeerd')).toBe(true);
  expect(queue.filter((p) => p.pings)).toEqual([]);
});

test('la afscherming por papeles: lo que falla, falta o es viejo, en rojo y latiendo', async ({ page, baseUrl }) => {
  // En las pruebas no hay instalacion nativa (no hay afscherming que leer): la respuesta de
  // verdad se cambia aqui por la de una instalacion con tres problemas distintos.
  await page.route('**/api/v2/aislamiento', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Record<string, unknown>;
    body.aislamiento = {
      aplica: true,
      entorno: 'nativo',
      correcto: false,
      papeles: [
        { papel: 'consola', bien: true, estado: 'correcto' },
        { papel: 'lector', bien: false, estado: 'falla' },
        { papel: 'salida', bien: false, estado: 'caducada' },
        { papel: 'orden', bien: false, estado: 'sin_comprobar' },
      ],
    };
    await route.fulfill({ response, json: body });
  });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await page.getByRole('navigation', { name: 'Hoofdmenu' }).getByRole('button', { name: /^Instellingen/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Instellingen' })).toBeVisible();
  await expect(page.getByText('Afscherming mislukt').first()).toBeVisible();
  const shown = await pills(page);
  const isolation = shown.filter((p) => p.label.startsWith('Afscherming') || p.label === 'Controle te oud');
  expect(isolation.map((p) => [p.label, p.variant, p.pings])).toEqual([
    ['Afscherming mislukt', 'error', true],
    ['Afscherming in orde', 'success', false],
    ['Afscherming mislukt', 'error', true],
    ['Controle te oud', 'error', true],
    ['Afscherming niet gecontroleerd', 'error', true],
  ]);
  await expectAccessible(page, 'nl instellingen (afscherming)');
  await page.getByText('Afscherming', { exact: true }).scrollIntoViewIfNeeded();
  await capture(page, 'nl-status-isolation');
  await page.getByRole('button', { name: 'English' }).first().click();
  await expect(page.getByText('Shielding failed').first()).toBeVisible();
  await page.getByText('Shielding', { exact: true }).scrollIntoViewIfNeeded();
  await capture(page, 'en-status-isolation');
  await page.getByRole('button', { name: 'Nederlands' }).first().click();
});
