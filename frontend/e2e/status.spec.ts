// Las alertas con el componente Status del dueno ("Asi quiero las alertas"): cada estado es
// una pastilla con su punto y SIEMPRE su texto; el punto late solo en lo que pide hacer algo
// ya (en la Werklijst, lo bloqueado y lo urgente), y deja de latir para quien pide menos
// movimiento. Capturas de las pastillas en NL y EN, y las pastillas medidas en los dos temas.
import type { Page } from '@playwright/test';
import { capture, chooseTheme, expect, expectAccessible, login, test } from './fixtures';
import { go, setLang, viewHeading } from './nav';

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

  await go(page, 'work-queue');
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
  await go(page, 'invoices-in');
  await expect(page.getByRole('table')).toBeVisible();
  // Que la pantalla de antes ya no este (el fundido al cambiar de sitio).
  await expect(page.getByRole('heading', { level: 1, name: 'Werklijst' })).toHaveCount(0);
  const invoices = await pills(page);
  // Una lista de facturas no late: lo bloqueado tambien esta, pero quieto.
  expect(invoices.filter((q) => q.pings)).toEqual([]);
  expect(invoices.some((p) => p.label === 'Geblokkeerd')).toBe(true);

  // Las cuentas por verificar laten (hay que llamar), en naranja; una ya verificada, no.
  // (Las otras pruebas usan la misma base: aqui puede haber una ya verificada por telefono.)
  await go(page, 'iban-checks');
  await expect(page.getByRole('heading', { level: 1, name: 'Inkoopfacturen' })).toHaveCount(0);
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
  await setLang(page, 'en');
  await go(page, 'work-queue', 'en');
  await expect(page.getByRole('heading', { level: 1, name: 'IBAN checks' })).toHaveCount(0);
  await expect(page.getByRole('table')).toBeVisible();
  const en = await pills(page);
  for (const p of en.filter((q) => q.pings)) expect(p.label).toBe('Blocked');
  await capture(page, 'en-status-work-queue');
  await setLang(page, 'nl');
});

test('un solo sitio late por pantalla: ninguna lista ni tarjeta parpadea', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // El inicio (tarjetas y "Als eerste") y cada lista: nada late.
  await expect(viewHeading(page, 'home')).toBeVisible();
  await expect(page.getByTestId('summary-card').first()).toBeVisible();
  await expect(page.locator('section[aria-labelledby="next-up"] [data-slot="status"]').first()).toBeVisible();
  expect((await pills(page)).filter((p) => p.pings), 'inicio').toEqual([]);
  for (const view of ['exceptions', 'invoices-in', 'invoices-out', 'providers', 'clients', 'objects', 'client-pos', 'provider-pos', 'documents'] as const) {
    await go(page, view);
    await expect(page.locator('[data-slot="status"]').first()).toBeVisible();
    expect((await pills(page)).filter((p) => p.pings), view).toEqual([]);
  }
  // La ficha de una relacion resume: quieta. La de una factura bloqueada: late su cabecera,
  // y solo ella.
  await go(page, 'providers');
  await page.getByRole('table').getByRole('button', { name: /J\. Voorbeeld Beveiliging/ }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: 'J. Voorbeeld Beveiliging (zzp)' })).toBeVisible();
  expect((await pills(page)).filter((p) => p.pings), 'leverancier').toEqual([]);
  await go(page, 'work-queue');
  await page.getByRole('table').getByRole('row').filter({ hasText: 'Geblokkeerd' }).first().getByRole('button').first().click();
  await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
  // La ficha ya cargada (mientras carga, el titulo es "Factuur <id>" y no hay pastillas).
  await expect(page.getByRole('region', { name: 'Wat aandacht nodig heeft' })).toBeVisible();
  const record = (await pills(page)).filter((p) => p.pings);
  expect(record.map((p) => p.label)).toEqual(['Geblokkeerd']);
});

test('quien pide menos movimiento no ve latir nada', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'work-queue');
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
  await go(page, 'settings');
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
  await setLang(page, 'en');
  await expect(page.getByText('Shielding failed').first()).toBeVisible();
  await page.getByText('Shielding', { exact: true }).scrollIntoViewIfNeeded();
  await capture(page, 'en-status-isolation');
  await setLang(page, 'nl');
});

test('el tema es el que elige la persona, no el del sistema, y cada pastilla se lee en los dos', async ({
  page,
  baseUrl,
}) => {
  // Paso 16: el oscuro de Aurora por defecto aunque Windows este en claro (la configuracion de
  // las pruebas emula claro), y el claro aunque Windows este en oscuro si la persona lo eligio.
  // Las clases dark: del componente Status valen con la clase .dark que pone la app en <html>,
  // nunca con prefers-color-scheme (con eso, un Windows en oscuro pintaria los tonos -400
  // sobre un fondo claro: menos de 2:1).
  // La marca de prueba de la cabecera es una pastilla de aviso que siempre esta.
  const ORANGE_400 = 'oklch(0.75 0.183 55.934)';
  const chipColor = () =>
    page.getByTestId('test-data-chip').evaluate((el) => getComputedStyle(el.querySelector('[data-slot="status-label"]') ?? el).color);
  const visit = async (theme: string) => {
    await go(page, 'home');
    await expect(page.getByTestId('summary-card').first()).toBeVisible();
    await expectAccessible(page, `${theme}: inicio`);
    for (const view of ['work-queue', 'iban-checks'] as const) {
      await go(page, view);
      await expect(page.locator('[data-slot="status"]').first()).toBeVisible();
      await expectAccessible(page, `${theme}: ${view}`);
    }
    // Una factura, con su veredicto, sus avisos y sus campos.
    await go(page, 'work-queue');
    await page.getByRole('table').getByRole('button').first().click();
    await expect(page.getByRole('heading', { level: 1, name: /^Factuur / })).toBeVisible();
    await expectAccessible(page, `${theme}: factuur`);
    await go(page, 'home');
  };

  await page.goto(`${baseUrl}/app`);
  await expect(page.locator('html')).toHaveClass(/(^|\s)dark(\s|$)/);
  await login(page);
  await visit('oscuro con Windows en claro');
  // En oscuro, el texto naranja es el claro (-400): se lee sobre el fondo oscuro.
  expect(await chipColor()).toBe(ORANGE_400);

  await page.emulateMedia({ colorScheme: 'dark' });
  await chooseTheme(page, 'light');
  await expect(page.locator('html')).not.toHaveClass(/(^|\s)dark(\s|$)/);
  await visit('claro con Windows en oscuro');
  // En claro, el de siempre (orange-800), no el -400 del oscuro.
  expect(await chipColor()).not.toBe(ORANGE_400);
  await go(page, 'iban-checks');
  await expect(page.locator('[data-slot="status"]').first()).toBeVisible();
  await capture(page, 'nl-status-iban-checks');
});

test('un plazo del btw pasado sin aangifte se ve en el inicio, en rojo', async ({ page, baseUrl }) => {
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
  await expectAccessible(page, 'inicio con un plazo pasado');
  await capture(page, 'nl-home-vat-overdue');
});
