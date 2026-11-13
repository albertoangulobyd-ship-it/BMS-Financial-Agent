// La guarda del tema claro ("Aurora claro · linea fina", rehecho tras la peticion del dueno del
// 02-11-2026): la gira de los estados principales (e2e/objetivos.ts, tour) en claro, a 1440 x 900 y
// a 400 x 860, y en cada estado:
// 1. axe sin nada serio ni critico y sin ninguna falta de contraste (en claro no se excusa
//    ninguna: e2e/aurora/contraste.json es solo del oscuro), con las pastillas medidas
//    (expectAccessible lleva expectStatusContrast);
// 2. el borde de cada campo de formulario a 3:1 (WCAG 1.4.11, expectFieldBoundary), y cada
//    selector de FORM_FIELDS visto alguna vez (uno que no encuentra nada no guarda nada);
// 2b. cada placeholder a la vista a 4,5:1 contra su fondo de verdad (WCAG 1.4.3,
//    expectPlaceholderContrast: axe no mide un placeholder con alfa), y los cuatro sitios donde
//    los hay (la entrada, la caja, la busqueda de las listas y la de un filtro) medidos;
// 3. lo que axe no mide (el texto sobre el cristal de las carpetas, bajo la marca TEST del papel,
//    las cejas de 8-9 px, la cabecera de Procesar y el resumen), medido en pixeles a 4,5:1;
// 4. un orbe como mucho;
// 5. ninguna violacion de la CSP ni ningun error en la consola (lo vigila fixtures.ts).
// Y el aviso (ws-toast) fuera de la hoja: blanco y legible; y el foco con el teclado en el
// deslizador del importe: un anillo a 3:1 frente a lo que tiene a cada lado (WCAG 1.4.11).
import type { Page } from '@playwright/test';
import {
  expect,
  expectAccessible,
  expectFieldBoundary,
  expectPixelContrast,
  expectPlaceholderContrast,
  focusRingContrast,
  FORM_FIELDS,
  login,
  N,
  settled,
  test,
} from './fixtures';
import { TEXTS, chooseTheme, openEntry, openInvoice, openSheetRow, signOut } from './nav';
import { tour } from './objetivos';

/** Un orbe como mucho a la vista (la onda de Aurora o el companero de Documentos): los orbes con
 *  algun lienzo visible (un orbe puede llevar mas de un lienzo, y uno a opacidad 0 no se ve). */
async function atMostOneOrb(page: Page, what: string) {
  const shown = await page.locator('button.aurora canvas, .ws-companion canvas').evaluateAll((els) => {
    const orbs = new Set<Element>();
    for (const el of els) {
      const r = el.getBoundingClientRect();
      let opaque = true;
      for (let e: Element | null = el; e; e = e.parentElement) if (getComputedStyle(e).opacity === '0') opaque = false;
      const inView = r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
      if (opaque && inView && getComputedStyle(el).visibility !== 'hidden') orbs.add(el.closest('button.aurora, .ws-companion') ?? el);
    }
    return orbs.size;
  });
  expect(shown, `orbes en ${what}`).toBeLessThanOrEqual(1);
}

/** Lo que se mide en pixeles, por estado de la gira (el nombre o su principio). */
const PIXELS: [RegExp, string, number][] = [
  // Las cejas de 8-9 px en mayusculas del panel ("WERKRUIMTE", "WAT AANDACHT VRAAGT").
  [/^E2 (home|receivables|payables|vat)$/, '.panel-top>span', 4.5],
  [/^E2 (home|receivables|payables|vat)$/, '.list-title', 4.5],
  // El resumen (el Finance Bento no tenia ninguna e2e en claro).
  [/^E4 la conversacion con el resumen$/, '.fpb #asof', 4.5],
  [/^E4 la conversacion con el resumen$/, '.fpb .muted', 4.5],
  [/^E4 la conversacion con el resumen$/, '.fpb .cap', 4.5],
  [/^E4 la conversacion con el resumen$/, '.fpb .alg text[fill=white]', 4.5],
  // El nombre y la meta de las carpetas, sobre la peor parte del cristal.
  [/^E6 (Documentos|la ficha de un proveedor|la ficha de un cliente)$/, '.gf-title', 4.5],
  [/^E6 (Documentos|la ficha de un proveedor|la ficha de un cliente)$/, '.gf-meta', 4.5],
  // Los valores del papel, donde los cruza la marca TEST.
  [/^E6(-h plegada| un Object)$/, '.ws-paper dd', 4.5],
  // La cabecera de la tarjeta de Procesar ("AURORA / DOCUMENTEN" y el estado).
  [/^E7 Procesar$/, '.pc-label>span', 4.5],
];

/** Donde hay un placeholder (el `field` de expectPlaceholderContrast): la gira tiene que medir
 *  cada uno. La app no tiene mas: las ordenes van sin placeholder y Ctrl+K se quito en el paso 17. */
const PLACEHOLDERS: [string, RegExp][] = [
  ['la entrada', /^#token$/],
  ['la caja de escribir y la de la busqueda', /^div\.input-row input$/],
  ['la busqueda de una lista', /^label\.search input$/],
  ['la busqueda de un filtro', /ui-command-input/],
];

for (const size of [
  { width: 1440, height: 900 },
  { width: 400, height: 860 },
]) {
  test(`el claro a ${size.width} px: contraste, campos, texto sobre cristal y un orbe en cada estado`, async ({ page, baseUrl }) => {
    test.setTimeout(2_400_000);
    await page.setViewportSize(size);
    await page.goto(`${baseUrl}/app`);
    // El claro de este ordenador: la entrada ya sale en claro, como la vera Ana al volver.
    await login(page);
    await chooseTheme(page, 'light');
    await signOut(page);
    await expect(page.locator('html')).not.toHaveClass(/(^|\s)dark(\s|$)/);
    const fields: Record<string, number> = {};
    const placeholders = new Set<string>();
    const measured = new Set<string>();
    await tour(page, async (state) => {
      const what = `${state} (claro, ${size.width} px)`;
      await expect(page.locator('html')).not.toHaveClass(/(^|\s)dark(\s|$)/);
      await expectAccessible(page, what);
      for (const [selector, n] of Object.entries(await expectFieldBoundary(page, what))) fields[selector] = (fields[selector] ?? 0) + n;
      for (const m of await expectPlaceholderContrast(page, what)) placeholders.add(m.field);
      for (const [when, selector, min] of PIXELS) {
        if (!when.test(state)) continue;
        await settled(page);
        if ((await expectPixelContrast(page, selector, min, what)).length) measured.add(selector);
      }
      await atMostOneOrb(page, what);
    });
    // La gira paso por cada campo guardado (un selector que no encuentra nada no guarda nada),
    // por cada sitio con placeholder, y midio en pixeles lo que se espera ver a este ancho.
    for (const selector of FORM_FIELDS) expect(fields[selector] ?? 0, `campos medidos en la gira: ${selector}`).toBeGreaterThan(0);
    for (const [name, field] of PLACEHOLDERS) {
      expect([...placeholders].some((p) => field.test(p)), `placeholder medido en la gira: ${name} (${[...placeholders].join(' | ')})`).toBe(true);
    }
    for (const selector of ['.panel-top>span', '.fpb #asof', '.gf-title', '.gf-meta', '.ws-paper dd', '.pc-label>span']) {
      expect(measured, `medido en pixeles: ${selector}`).toContain(selector);
    }
  });
}

test('el aviso (ws-toast) fuera de la hoja, en claro: blanco, opaco y legible', async ({ page, baseUrl }) => {
  const t = TEXTS.nl;
  // La orden se responde aqui (sin tocar la base que comparten las demas pruebas): el aviso sale
  // igual, con el texto de lo hecho.
  await page.route('**/api/v2/acciones', (route) =>
    route.request().method() === 'POST' ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, diferencia: {} }) }) : route.continue()
  );
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await chooseTheme(page, 'light');
  await openInvoice(page, N.oost);
  const more = await openSheetRow(page, t.aurora.sheet.more);
  await more.getByRole('button', { name: t.notes.add, exact: true }).click();
  await more.locator('.order-form').getByLabel(t.notes.text).first().fill('Een notitie voor de proef.');
  await more.locator('.order-form').getByRole('button', { name: t.notes.add, exact: true }).click();
  await more.locator('.chat-export').getByRole('button', { name: t.notes.add, exact: true }).click();
  const toast = page.locator('.ws-toast');
  await expect(toast).toBeVisible();
  // Fuera de la hoja: la hoja es la capa de arriba del navegador y el aviso queda debajo (S10,
  // aparte); se cierra en el acto, sin su animacion, para verlo durante sus 2,6 s.
  await page.locator('dialog.ws-dialog').evaluate((el) => (el as HTMLDialogElement).close());
  await expect(toast).toBeVisible();
  const look = await toast.evaluate((el) => ({ background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color }));
  expect(look.background).toBe('rgb(255, 255, 255)');
  expect(look.color).toBe('rgb(23, 23, 28)');
  const [ratio] = await expectPixelContrast(page, '.ws-toast', 4.5, 'el aviso fuera de la hoja');
  expect(ratio).toBeGreaterThanOrEqual(4.5);
});

for (const size of [
  { width: 1440, height: 900 },
  { width: 400, height: 860 },
]) {
  test(`el foco con el teclado en los tiradores del importe, en claro a ${size.width} px: un anillo a 3:1`, async ({ page, baseUrl }) => {
    await page.setViewportSize(size);
    await page.goto(`${baseUrl}/app`);
    await login(page);
    await chooseTheme(page, 'light');
    await openEntry(page, 'search');
    await page.locator('.filters-toggle').click();
    await expect(page.locator('#search-filters')).toBeVisible();
    const thumbs = page.locator('#search-filters .amount-thumb');
    await expect(thumbs).toHaveCount(2);
    for (const thumb of [thumbs.first(), thumbs.last()]) {
      // Con el teclado, como llega quien no usa el raton: Tab hasta el tirador.
      for (let i = 0; i < 40 && !(await thumb.evaluate((el) => el === document.activeElement)); i += 1) await page.keyboard.press('Tab');
      await expect(thumb).toBeFocused();
      expect(await thumb.evaluate((el) => el.matches(':focus-visible'))).toBe(true);
      await settled(page);
      // Aurora lo marca con un halo de 4 px del lila a 0,19: en claro daba 1,29 frente a lo blanco.
      const ring = await focusRingContrast(page, thumb);
      expect(ring.ratio, `el anillo ${ring.ring} frente a ${ring.inner ?? 'el tirador'} y a ${ring.outer}`).toBeGreaterThanOrEqual(3);
    }
  });
}
