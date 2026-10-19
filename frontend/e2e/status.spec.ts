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
  // Late solo Geblokkeerd (rojo); Urgent (naranja), Aandacht y Normaal, quietos: la lista
  // donde se trabaja no parpadea entera.
  const pinging = queue.filter((p) => p.pings);
  expect(pinging.length).toBeGreaterThan(0);
  for (const p of pinging) expect(p.label).toBe('Geblokkeerd');
  for (const p of queue.filter((q) => q.label !== 'Geblokkeerd')) expect(p.pings, p.label).toBe(false);
  expect(queue.find((p) => p.label === 'Geblokkeerd')?.variant).toBe('error');
  await capture(page, 'nl-status-work-queue');

  // Una lista de facturas: el pago y el control quietos; solo laten las prioridades que piden algo.
  await menu.getByRole('button', { name: /^Inkomend/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inkomend' })).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
  // Que la pantalla de antes ya no este (la animacion entre pestanas).
  await expect(page.getByRole('heading', { level: 1, name: 'Werklijst' })).toHaveCount(0);
  const invoices = await pills(page);
  // Una lista de facturas no late: lo bloqueado tambien esta, pero quieto.
  expect(invoices.filter((q) => q.pings)).toEqual([]);
  expect(invoices.some((p) => p.label === 'Geblokkeerd')).toBe(true);

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
  for (const p of en.filter((q) => q.pings)) expect(p.label).toBe('Blocked');
  await capture(page, 'en-status-work-queue');
  await page.getByRole('button', { name: 'Nederlands' }).first().click();
});

test('un solo sitio late por pantalla: ninguna lista ni tarjeta parpadea', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const menu = page.getByRole('navigation', { name: 'Hoofdmenu' });
  // El Overzicht (tarjetas y "Als eerste") y cada lista: nada late.
  await expect(page.getByRole('heading', { level: 1, name: 'Overzicht' })).toBeVisible();
  await expect(page.getByTestId('summary-card').first()).toBeVisible();
  expect((await pills(page)).filter((p) => p.pings), 'overzicht').toEqual([]);
  for (const label of ['Uitzonderingen', 'Inkomend', 'Uitgaand', 'Leveranciers', 'Klanten', 'Objecten', 'Inkooporders']) {
    await menu.getByRole('button', { name: new RegExp(`^${label}`) }).click();
    await expect(page.getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
    await expect(page.locator('[data-slot="status"]').first()).toBeVisible();
    expect((await pills(page)).filter((p) => p.pings), label).toEqual([]);
  }
  // La ficha de una relacion resume: quieta. La de una factura bloqueada: late su cabecera,
  // y solo ella.
  await menu.getByRole('button', { name: /^Leveranciers/ }).click();
  await page.getByRole('table').getByRole('button', { name: /J\. Voorbeeld Beveiliging/ }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: 'J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
  expect((await pills(page)).filter((p) => p.pings), 'leverancier').toEqual([]);
  await menu.getByRole('button', { name: /^Werklijst/ }).click();
  await page.getByRole('table').getByRole('row').filter({ hasText: 'Geblokkeerd' }).first().getByRole('button').first().click();
  await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
  const record = (await pills(page)).filter((p) => p.pings);
  expect(record.map((p) => p.label)).toEqual(['Geblokkeerd']);
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

test('con el modo oscuro del sistema la app sigue clara y cada pastilla se lee', async ({ page, baseUrl }) => {
  // La app solo tiene tema claro: un Windows en modo oscuro no cambia nada (las clases
  // dark: del componente Status solo valen con una clase .dark que la app nunca pone).
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const menu = page.getByRole('navigation', { name: 'Hoofdmenu' });
  await expect(page.getByRole('heading', { level: 1, name: 'Overzicht' })).toBeVisible();
  await expect(page.getByTestId('summary-card').first()).toBeVisible();
  await expectAccessible(page, 'oscuro: overzicht');
  await capture(page, 'nl-dark-overview');

  for (const [label, check] of [['Werklijst', 'werklijst'], ['IBAN-controles', 'iban-controles']] as const) {
    await menu.getByRole('button', { name: new RegExp(`^${label}`) }).click();
    await expect(page.getByRole('heading', { level: 1, name: label })).toBeVisible();
    await expect(page.locator('[data-slot="status"]').first()).toBeVisible();
    await expectAccessible(page, `oscuro: ${check}`);
  }
  // Una factura, con su veredicto, sus avisos y sus campos.
  await menu.getByRole('button', { name: /^Werklijst/ }).click();
  await page.getByRole('table').getByRole('button').first().click();
  await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
  await expectAccessible(page, 'oscuro: factuur');
  // El texto de una pastilla verde es el de siempre (green-800), no el -400 del modo oscuro.
  const colors = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('[data-slot="status"][data-variant="success"] [data-slot="status-label"]')).map(
      (el) => getComputedStyle(el).color
    )
  );
  for (const color of colors) expect(color).not.toBe('oklch(0.792 0.209 151.711)');
});

test('un plazo del btw pasado sin aangifte se ve en el Overzicht, en rojo', async ({ page, baseUrl }) => {
  // El panel de un dia despues del plazo del T3 sin la presentacion anotada: proximo_plazo
  // ya es el del T4, y el T3 va en por_presentar con los dias en negativo (lo que da
  // consultas._bloque_btw ese dia). Se cambia aqui porque la base de prueba es de hoy.
  await page.route('**/api/v2/panel', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { panel: { btw: Record<string, unknown> } };
    body.panel.btw.proximo_plazo = { trimestre: '2026-T4', estado: 'abierto', limite_presentacion: '2027-01-31', dias_para_limite: 87 };
    body.panel.btw.plazos_pasados = ['2026-T3'];
    body.panel.btw.por_presentar = [{ trimestre: '2026-T3', estado: 'listo_revision', limite_presentacion: '2026-10-31', dias_para_limite: -5 }];
    await route.fulfill({ response, json: body });
  });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const card = page.getByTestId('summary-card').filter({ hasText: 'Btw dit kwartaal' });
  const late = card.locator('[data-slot="status"]').filter({ hasText: 'Aangifte te laat' });
  await expect(late).toBeVisible();
  await expect(late).toHaveAttribute('data-variant', 'error');
  await expect(card).toContainText('Q3 2026');
  // El proximo plazo sigue, debajo.
  await expect(card).toContainText('Aangifte Q4 2026 uiterlijk');
  await expectAccessible(page, 'overzicht con un plazo pasado');
  await capture(page, 'nl-overview-vat-overdue');
});
