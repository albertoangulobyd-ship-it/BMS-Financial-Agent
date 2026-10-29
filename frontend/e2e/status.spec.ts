// Los estados con los colores de Aurora (paso 17, especificacion D-31): en una fila de un panel no
// hay pastilla, el estado va en el texto de doc-end small con su color (#b59a76 lo pendiente,
// #93b4a4 lo pagado o en orden y, para lo bloqueado, el rojo de .ui-status.offline, #f87171); en
// una pastilla (.ui-status de Aurora), el punto y SIEMPRE su texto, en verde, naranja, rojo o azul.
// El punto late solo en lo que pide hacer algo ya (el aislamiento que falla o falta) y deja de
// latir para quien pide menos movimiento; en Documentos, la prioridad quieta y las marcas de nueva
// y repetida latiendo, como las de Aurora.
// En claro, los mismos tonos con el contraste de claro.css. Capturas en NL y EN.
import type { Page } from '@playwright/test';
import { capture, expect, expectAccessible, login, test } from './fixtures';
import { TEXTS, chooseTheme, openDocuments, openEntry, openGroup, openSettingsRow, panel, panelRow, setLang } from './nav';

const t = TEXTS.nl;

/** El color del texto de una fila, por su clase (styles.css:9, bms.css y claro.css). */
const ROW = {
  dark: { '': 'rgb(181, 154, 118)', paid: 'rgb(147, 180, 164)', blocked: 'rgb(248, 113, 113)' },
  light: { '': 'rgb(79, 56, 21)', paid: 'rgb(28, 58, 45)', blocked: 'rgb(123, 0, 9)' },
} as const;

/** El color de una pastilla, por su tono (workspace-layout.css:39-42 y claro.css). */
const PILL = {
  dark: { error: 'rgb(248, 113, 113)', warning: 'rgb(223, 173, 114)', success: 'rgb(137, 214, 165)', info: 'rgb(147, 185, 238)' },
  light: { error: 'rgb(123, 0, 9)', warning: 'rgb(69, 28, 0)', success: 'rgb(0, 46, 7)', info: 'rgb(7, 40, 83)' },
} as const;

type Theme = keyof typeof ROW;

interface RowState {
  text: string;
  tone: string;
  color: string;
}

/** El estado de cada fila del panel que se ve: su texto, su clase y su color. */
async function rowStates(page: Page): Promise<RowState[]> {
  return panel(page)
    .locator('.doc-end small')
    .evaluateAll((els) =>
      els
        .filter((e) => e.getBoundingClientRect().width > 0)
        .map((e) => ({ text: (e.textContent ?? '').trim(), tone: e.className, color: getComputedStyle(e).color }))
    );
}

/** Cada fila en el color de su clase; y ninguna pastilla en un panel. */
async function expectRowColors(page: Page, theme: Theme, what: string): Promise<RowState[]> {
  const rows = await rowStates(page);
  expect(rows.length, what).toBeGreaterThan(0);
  for (const r of rows) expect(r.color, `${what}: ${r.text} (${r.tone || 'pendiente'})`).toBe(ROW[theme][r.tone as keyof (typeof ROW)['dark']]);
  await expect(panel(page).locator('[data-slot="status"]')).toHaveCount(0);
  return rows;
}

interface Pill {
  variant: string;
  label: string;
  color: string;
  pings: boolean;
}

/** Las pastillas que se ven en `scope`: su tono, su texto, su color y si su punto late de verdad
 *  (el .animate-ping del punto, con su animacion como la pinta el navegador). */
async function pills(page: Page, scope: string): Promise<Pill[]> {
  return page.locator(scope).evaluateAll((roots) =>
    roots
      .flatMap((root) => Array.from(root.querySelectorAll<HTMLElement>('[data-slot="status"]')))
      .filter((p) => p.getBoundingClientRect().width > 0)
      .map((p) => {
        const ping = p.querySelector('[data-slot="status-indicator"] .animate-ping');
        // Sin data-variant (las nuevas y las repetidas de la ultima lectura, FolderAnalysisStatus
        // de Aurora): el tono por la clase de la pastilla.
        const byClass = { online: 'success', degraded: 'warning', offline: 'error', maintenance: 'info' } as Record<string, string>;
        const cls = Object.keys(byClass).find((c) => p.classList.contains(c));
        return {
          variant: p.dataset.variant ?? (cls ? byClass[cls]! : ''),
          label: (p.querySelector('[data-slot="status-label"]')?.textContent ?? '').trim(),
          color: getComputedStyle(p).color,
          pings: ping !== null && getComputedStyle(ping).animationName !== 'none',
        };
      })
  );
}

/** Los tres tonos de las filas (IVA y la Werklijst) y las pastillas de Documentos, en un tema. */
async function visit(page: Page, theme: Theme) {
  // IVA: el trimestre abierto (pendiente), el que espera control con el plazo cerca (pendiente)
  // y uno ya aangegeven (en orden, verde).
  await openEntry(page, 'vat');
  const vat = await expectRowColors(page, theme, `${theme}: btw`);
  expect(vat.some((r) => r.tone === 'paid')).toBe(true);
  expect(vat.some((r) => r.tone === '')).toBe(true);
  await expectAccessible(page, `${theme}: btw (estados)`);
  // La Werklijst: lo bloqueado en rojo; lo demas, pendiente.
  await openEntry(page, 'home');
  await openGroup(page, t.nav['work-queue'].label);
  const queue = await expectRowColors(page, theme, `${theme}: werklijst`);
  const blocked = queue.filter((r) => r.tone === 'blocked');
  expect(blocked.length).toBeGreaterThan(0);
  for (const r of blocked) expect(r.text).toBe('Geblokkeerd');
  for (const r of queue.filter((q) => q.tone !== 'blocked')) expect(r.text).not.toBe('Geblokkeerd');
  await capture(page, 'nl-status-work-queue');
  // Documentos: las pastillas de las carpetas, con el color de su tono. La prioridad (de BMS)
  // va quieta; las marcas de la ultima lectura (FolderAnalysisStatus de Aurora) laten, como en
  // Aurora: las nuevas en verde y las repetidas en naranja (en la pasada entera,
  // procesar.spec.ts ya leyo; sola, puede no haber ninguna).
  await openDocuments(page);
  const folders = await pills(page, '.ws-grid');
  expect(folders.length).toBeGreaterThan(0);
  expect(folders.some((p) => p.variant === 'error')).toBe(true);
  expect(folders.some((p) => p.variant === 'warning')).toBe(true);
  const analysis = (p: { label: string }) => / (nieuw|herhaald)$/.test(p.label);
  for (const p of folders) {
    expect(p.label, 'una pastilla sin texto').not.toBe('');
    expect(p.color, `${theme}: ${p.label}`).toBe(PILL[theme][p.variant as keyof (typeof PILL)['dark']]);
    expect(p.pings, `${theme}: ${p.label} ${analysis(p) ? 'late, como en Aurora' : 'va quieta'}`).toBe(analysis(p));
  }
  for (const p of folders.filter((f) => / nieuw$/.test(f.label))) expect(p.variant, p.label).toBe('success');
  for (const p of folders.filter((f) => / herhaald$/.test(f.label))) expect(p.variant, p.label).toBe('warning');
  await capture(page, 'nl-status-documents');
}

test('cada estado en su color de Aurora: el texto de la fila y la pastilla, en oscuro y en claro', async ({ page, baseUrl }) => {
  test.setTimeout(240_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await visit(page, 'dark');
  await chooseTheme(page, 'light');
  await visit(page, 'light');
  // En ingles, el mismo estado con su texto.
  await chooseTheme(page, 'dark');
  await setLang(page, 'en');
  await openEntry(page, 'home', 'en');
  await openGroup(page, TEXTS.en.nav['work-queue'].label);
  const en = await expectRowColors(page, 'dark', 'en: work queue');
  for (const r of en.filter((q) => q.tone === 'blocked')) expect(r.text).toBe('Blocked');
  await capture(page, 'en-status-work-queue');
  await setLang(page, 'nl');
});

test('la afscherming por papeles en Ajustes: lo que falla, falta o es viejo, cada uno con su estado y su punto que late', async ({ page, baseUrl }) => {
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
  // Ajustes > Systeem (E2-A): la fila de la afscherming dice que hay que mirarla, en el color
  // de lo pendiente de Aurora (no el verde de lo pagado), y su tarjeta, cada papel con su estado.
  await openSettingsRow(page, 'system');
  const s = t.aurora.settings;
  const row = panelRow(page, s.systemRows.isolation);
  await expect(row.locator('.doc-end small')).toHaveText(s.isolationBad);
  await expect(row.locator('.doc-end small')).not.toHaveClass(/\bpaid\b/);
  await row.click();
  const card = panel(page).locator('.detail');
  const roles = t.settings.roles;
  for (const [role, state] of [
    [roles.consola, s.isolationStates.correcto],
    [roles.lector, s.isolationStates.falla],
    [roles.salida, s.isolationStates.caducada],
    [roles.orden, s.isolationStates.sin_comprobar],
  ] as const) {
    await expect(card).toContainText(`${role}: ${state}`);
  }
  // Late lo que falla o falta, en rojo; lo correcto, en verde y quieto.
  const shown = await pills(page, 'aside.panel .detail');
  expect(shown.length).toBe(5);
  for (const p of shown) {
    const ok = p.label === s.isolationStates.correcto;
    expect(p.pings, p.label).toBe(!ok);
    expect(p.color, p.label).toBe(PILL.dark[ok ? 'success' : 'error']);
  }
  await expectAccessible(page, 'nl ajustes (afscherming)');
  await capture(page, 'nl-status-isolation');
  await setLang(page, 'en');
  await openSettingsRow(page, 'system');
  await panelRow(page, TEXTS.en.aurora.settings.systemRows.isolation).click();
  await expect(panel(page).locator('.detail')).toContainText(`${TEXTS.en.settings.roles.lector}: ${TEXTS.en.aurora.settings.isolationStates.falla}`);
  await capture(page, 'en-status-isolation');
  await setLang(page, 'nl');
});

test('quien pide menos movimiento no ve latir nada', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/v2/aislamiento', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Record<string, unknown>;
    body.aislamiento = { aplica: true, entorno: 'nativo', correcto: false, papeles: [{ papel: 'lector', bien: false, estado: 'falla' }] };
    await route.fulfill({ response, json: body });
  });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openSettingsRow(page, 'system');
  await panelRow(page, t.aurora.settings.systemRows.isolation).click();
  const shown = await pills(page, 'aside.panel .detail');
  expect(shown.some((p) => p.variant === 'error')).toBe(true);
  expect(shown.filter((p) => p.pings)).toEqual([]);
  // Ni las marcas de nueva y repetida de Documentos (workspace-layout.css de Aurora las para).
  await openDocuments(page);
  const folders = await pills(page, '.ws-grid');
  expect(folders.length).toBeGreaterThan(0);
  expect(folders.filter((p) => p.pings)).toEqual([]);
});

test('un plazo del btw pasado sin aangifte: su fila de IVA lo dice, en rojo', async ({ page, baseUrl }) => {
  // El IVA de unos dias despues del plazo del trimestre anterior sin la presentacion anotada (lo
  // que da btw.resumen ese dia). Se cambia aqui porque la base de prueba es de hoy (y
  // screens.spec.ts, en la misma base, ya anota la de ese trimestre).
  type Row = { etiqueta: string; estado: string; dias_para_limite: number | null };
  await page.route('**/api/v2/btw', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { btw: { por_presentar: Row[]; anteriores: Row[] } };
    const previous = body.btw.por_presentar[0] ?? body.btw.anteriores[0]!;
    const late = { ...previous, estado: 'listo_revision', dias_para_limite: -5 };
    body.btw.por_presentar = [late, ...body.btw.por_presentar.filter((q) => q.etiqueta !== late.etiqueta)];
    body.btw.anteriores = body.btw.anteriores.map((q) => (q.etiqueta === late.etiqueta ? late : q));
    await route.fulfill({ response, json: body });
  });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openEntry(page, 'vat');
  const late = panel(page).locator('.doc-end small', { hasText: t.status.vat.plazo_vencido });
  await expect(late.first()).toBeVisible();
  await expect(late.first()).toHaveClass(/\bblocked\b/);
  await expect(late.first()).toHaveCSS('color', ROW.dark.blocked);
  await expectAccessible(page, 'btw con un plazo pasado');
  await capture(page, 'nl-vat-overdue');
});
