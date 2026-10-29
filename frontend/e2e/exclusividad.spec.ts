// La regla del dueno (paso 17, especificacion §1.1 y §6.4): «No pueden vivir las pantallas y el
// menu al mismo tiempo». El menu es la rueda; una pantalla es un panel (E2), la conversacion
// (E4), la busqueda (E5), Documentos (E6) o Procesar (E7). «Se ve» es lo de §1.1, con el
// ayudante e2e/aurora/visible.ts: la caja con area dentro de la ventana, visibility visible y la
// opacidad efectiva (la del elemento por la de todos sus padres) por encima de 0,01.
// - En cada estado asentado, en cada ancho (los de Aurora a los dos lados de sus cortes: 1150 y
//   700), se ve uno u otro, nunca los dos; y nada de lo que ya no existe (§6.5).
// - En cada cuadro de cada transicion, lo mismo. La unica excepcion es E1 → E6 (Documentos desde
//   la rueda): la pantalla que se va (con la rueda) se funde en 0,18 s encima de la que entra
//   (Root, main.tsx:46). Mientras dura, la opacidad efectiva de la rueda no sube nunca y llega a 0
//   antes de 0,18 s mas un cuadro desde el primer cuadro con las dos; la pantalla que se va tiene
//   pointer-events: none y un clic en el sitio de la fila activa de la rueda no le llega. Con
//   «menos movimiento», ningun cuadro con las dos.
// - El ayudante se prueba a si mismo: en el fundido de E1 → E6, a camara lenta, la opacity propia
//   de .navigation es 1 y la efectiva baja de 1 a 0.
// - La rueda escondida no manda (§1.1, cambio 2): con cada panel abierto, a 1440 y a 1024, diez
//   pasos de la rueda del raton hacia abajo y diez hacia arriba sobre el orbe, sobre el hueco de
//   la rueda y sobre el saludo; las flechas y Tab: la activa, su aria-current, la fase de la onda
//   y el morado de Procesar no cambian, y el orbe lleva a E0.
// - Un solo cambio (F9): E4 → E2 y E2 → E5-p, sin ningun render con la rueda sin .has-panel, ni con
//   la conversacion y el panel, ni con el panel y la busqueda (F8, E7 → E2-I, en procesar.spec).
// Los paneles por dentro (vista de grupo, tarjeta, orden e importar), la busqueda con filtros
// (E5-p), las fichas de un cliente y de un proveedor, un Object, una PO y la hoja de una factura
// con una orden abierta (E6-h, E6-o), plegada y desplegada, cuentan como su pantalla.
import type { Page } from '@playwright/test';
import { expect, login, settled, test } from './fixtures';
import {
  TEXTS,
  answerRow,
  app,
  ask,
  closeSheet,
  entryButton,
  landed,
  openCard,
  openEntry,
  openFolder,
  openGroup,
  openInvoice,
  openMenu,
  openSettingsRow,
  openSheetRow,
  panel,
  panelRow,
  processLanded,
  profileRow,
  sheetDialog,
  sheetFold,
  toHome,
} from './nav';
import { goneViolations, installVisible, renderViolations, seen, startFrames, startRenders, takeFrames, takeRenders, type Frame } from './aurora/visible';

const t = TEXTS.nl;
const HAVEN = 'Demo Havenbedrijf BV';
const JV = 'J. Voorbeeld Beveiliging (zzp)';

/** La regla, ahora: o la rueda o una pantalla (o ninguna); y nada de lo que ya no existe. */
async function expectRule(page: Page, what: string, expected: { menu: boolean; screen?: string; home?: boolean }): Promise<void> {
  await settled(page);
  const s = await seen(page);
  expect(s.menu && s.screens.length > 0, `${what}: la rueda y ${s.screens.join(', ')} a la vez`).toBe(false);
  expect(s.menu, `${what}: la rueda`).toBe(expected.menu);
  expect(s.screens, `${what}: la pantalla`).toEqual(expected.screen ? [expected.screen] : []);
  expect(await goneViolations(page, expected.home ?? false), `${what}: lo que ya no existe (§6.5)`).toEqual([]);
}

/** Los cuadros de una transicion contra la regla. `fade`: es E1 → E6, la unica en que la rueda (en
 *  la pantalla que se va) y la pantalla que entra pueden coincidir, dentro del fundido de Root. */
function checkFrames(what: string, frames: Frame[], fade = false): Frame[] {
  expect(frames.length, `${what}: cuadros medidos`).toBeGreaterThan(5);
  expect(frames.filter((f) => f.loading).length, `${what}: «Cargando…» a la vista (§6.5)`).toBe(0);
  expect(frames.filter((f) => f.leavingClickable).length, `${what}: la pantalla que se va recibe clics`).toBe(0);
  const both = frames.filter((f) => f.menu && f.screens.length > 0);
  if (!fade) {
    expect(both.map((f) => f.screens.join('+')), `${what}: cuadros con la rueda y una pantalla`).toEqual([]);
    return both;
  }
  expect(both.filter((f) => !f.menuLeaving).map((f) => f.screens.join('+')), `${what}: la rueda que no se va, con una pantalla`).toEqual([]);
  console.log(`${what}: ${both.length} cuadros con la rueda que se va y la pantalla que entra (${both.map((f) => f.menuOpacity.toFixed(2)).join(' → ')})`);
  if (both.length > 0) {
    const first = frames.indexOf(both[0]!);
    const last = frames.indexOf(both[both.length - 1]!);
    // La opacidad efectiva de la rueda no sube nunca, del primer cuadro con las dos al primero sin.
    for (let i = first + 1; i <= Math.min(last + 1, frames.length - 1); i += 1) {
      expect(frames[i]!.menuOpacity, `${what}: la rueda sube de ${frames[i - 1]!.menuOpacity.toFixed(3)} a ${frames[i]!.menuOpacity.toFixed(3)}`).toBeLessThanOrEqual(frames[i - 1]!.menuOpacity + 1e-6);
    }
    // Llega a 0 antes de 0,18 s mas un cuadro: el ultimo cuadro con las dos, como mucho a 180 ms del primero.
    expect(both[both.length - 1]!.t - both[0]!.t, `${what}: el fundido dura mas de 0,18 s`).toBeLessThanOrEqual(181);
    // Un clic en el sitio de la fila activa de la rueda que se va no le llega.
    expect(both.filter((f) => f.underLeavingRow === 'wheel').length, `${what}: la rueda que se va recibe el clic`).toBe(0);
  }
  return both;
}

/** Cada cuadro mientras pasa algo. */
async function expectRuleWhile(page: Page, what: string, action: () => Promise<void>, ms = 1400, fade = false): Promise<Frame[]> {
  await startFrames(page);
  await action();
  await page.waitForTimeout(ms);
  return checkFrames(what, await takeFrames(page), fade);
}

/** Documentos desde la rueda (E1 → E6): el vuelo y el fundido de Root. */
async function documentsFromWheel(page: Page): Promise<void> {
  await entryButton(page, 'documents').focus();
  await settled(page);
  await entryButton(page, 'documents').click();
}

test.beforeEach(async ({ page }) => {
  await installVisible(page);
});

for (const width of [1440, 1151, 1150, 1024, 400] as const) {
  test(`o el menu o una pantalla, a ${width} px, en cada estado y en cada cuadro`, async ({ page, baseUrl }) => {
    test.setTimeout(420_000);
    await page.setViewportSize({ width, height: width === 400 ? 860 : 900 });
    await page.goto(`${baseUrl}/app`);
    // L0 y E0: ni rueda ni pantalla, y nada arriba a la derecha.
    await expectRule(page, 'L0', { menu: false, home: true });
    await login(page);
    await expectRule(page, 'E0', { menu: false, home: true });
    // Sin paleta ni su atajo (§6.5): Ctrl+K no abre nada.
    await page.keyboard.press('Control+k');
    await expectRule(page, 'E0 tras Ctrl+K', { menu: false, home: true });
    // E1: la rueda.
    await expectRuleWhile(page, 'E0 → E1', () => page.getByRole('button', { name: t.aurora.home.navigate }).click());
    await expectRule(page, 'E1', { menu: true, home: true });
    // E3: la primera tecla cierra la rueda (main.tsx:40, como en Aurora); escribir no es una pantalla.
    await expectRuleWhile(page, 'E1 → E3', () => page.getByRole('textbox', { name: t.aurora.composer.askLabel }).fill('btw'));
    await expectRule(page, 'E3', { menu: false });
    await page.getByRole('textbox', { name: t.aurora.composer.askLabel }).fill('');

    // E2: cada panel. La rueda, oculta en todos los anchos; la ✕ la devuelve.
    for (const id of ['settings', 'home', 'receivables', 'payables', 'vat'] as const) {
      await openMenu(page);
      await expectRuleWhile(page, `E1 → E2 ${id}`, async () => {
        await entryButton(page, id).focus();
        await settled(page);
        await entryButton(page, id).click();
      });
      await expectRule(page, `E2 ${id}`, { menu: false, screen: 'panel' });
      await expectRuleWhile(page, `E2 ${id} → E1`, () => panel(page).getByRole('button', { name: t.aurora.panel.close }).click());
      await expectRule(page, `E1 tras ${id}`, { menu: true, home: true });
    }
    // E2-A con una vista de grupo y con una tarjeta.
    await openSettingsRow(page, 'language');
    await expectRule(page, 'E2-A idioma', { menu: false, screen: 'panel' });
    await openSettingsRow(page, 'account');
    await expect(panel(page).locator('.detail')).toBeVisible();
    await expectRule(page, 'E2-A tarjeta', { menu: false, screen: 'panel' });
    // El orbe con un panel: al inicio.
    await expectRuleWhile(page, 'E2 → E0 (orbe)', () => page.locator('button.aurora').click());
    await expectRule(page, 'E0 tras el orbe', { menu: false, home: true });

    // E5: la busqueda (desde la rueda).
    await openMenu(page);
    await expectRuleWhile(page, 'E1 → E5', async () => {
      await entryButton(page, 'search').focus();
      await settled(page);
      await entryButton(page, 'search').click();
    });
    await expectRule(page, 'E5', { menu: false, screen: 'search' });
    await page.keyboard.press('Control+k');
    await expectRule(page, 'E5 tras Ctrl+K', { menu: false, screen: 'search' });

    // E4: la conversacion (con el resumen), desde la rueda abierta.
    await openMenu(page);
    const box = page.getByRole('textbox', { name: t.aurora.composer.askLabel });
    await box.fill('Geef me een overzicht');
    await expectRuleWhile(page, 'E1 → E4', () => box.press('Enter'), 2500);
    await expect(page.locator('.finance-bento')).toBeVisible();
    await expectRule(page, 'E4', { menu: false, screen: 'conversation' });
    // «Terug naar de werkruimte»: E1, sin conversacion.
    await expectRuleWhile(page, 'E4 → E1', () => page.getByRole('button', { name: t.aurora.chat.back }).click());
    await expectRule(page, 'E1 tras la conversacion', { menu: true, home: true });

    // E6: Documentos desde la rueda, con el vuelo y el fundido de Root (la unica transicion en que
    // la rueda que se va y la pantalla que entra pueden coincidir).
    await expectRuleWhile(page, 'E1 → Documenten', () => documentsFromWheel(page), 1600, true);
    await landed(page);
    await expectRule(page, 'Documenten', { menu: false, screen: 'work' });
    // Las fichas de un cliente y de un proveedor (su carpeta abierta), un Object y una PO: sin
    // «Cargando…» en ningun cuadro mientras llegan sus documentos.
    await expectRuleWhile(page, 'la ficha de un cliente', async () => void (await openFolder(page, HAVEN, 'client')), 800);
    await expectRule(page, 'E6 ficha de cliente', { menu: false, screen: 'work' });
    await expectRuleWhile(page, 'un Object', () => profileRow(page, `${t.records.object.label} HAVEN-NOORD`).click(), 800);
    await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('HAVEN-NOORD');
    await expectRule(page, 'E6 Object', { menu: false, screen: 'work' });
    await closeSheet(page);
    await expectRuleWhile(page, 'una PO', () => profileRow(page, `${t.records['purchase-order'].label} PO-DEMO-4501`).click(), 800);
    await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('PO-DEMO-4501');
    await expectRule(page, 'E6 PO', { menu: false, screen: 'work' });
    await closeSheet(page);
    await expectRuleWhile(page, 'la ficha de un proveedor', async () => void (await openFolder(page, JV, 'provider')), 800);
    await expectRule(page, 'E6 ficha de proveedor', { menu: false, screen: 'work' });
    await expectRuleWhile(page, 'Documenten → E0', () => page.locator('a.ws-home').click(), 1600);
    await landed(page);
    await expectRule(page, 'E0 tras Documenten', { menu: false, home: true });

    // E7: Procesar desde la rueda (el espacio central con la suricata, sin orbe ni rueda; las
    // particulas del orbe caen al monticulo) y «Terug naar start», al inicio.
    await openMenu(page);
    await expectRuleWhile(
      page,
      'E1 → E7',
      async () => {
        await entryButton(page, 'process').focus();
        await settled(page);
        await entryButton(page, 'process').click();
      },
      2600
    );
    await processLanded(page);
    await expectRule(page, 'E7', { menu: false, screen: 'process' });
    await expectRuleWhile(page, 'E7 → E0', () => page.locator('.processing-back').click());
    await expectRule(page, 'E0 tras Procesar', { menu: false, home: true });

    // E2 por dentro: una vista de grupo, una tarjeta con una orden abierta, e importar.
    await openEntry(page, 'home');
    await openGroup(page, t.nav.exceptions.label);
    await expectRule(page, 'E2-I vista de grupo', { menu: false, screen: 'panel' });
    const exception = await openCard(page, panel(page).locator('.doc-list button.doc').first());
    await expectRule(page, 'E2-I tarjeta', { menu: false, screen: 'panel' });
    await exception.getByRole('button', { name: t.exceptions.resolve, exact: true }).first().click();
    await expect(exception.locator('.order-form')).toBeVisible();
    await expectRule(page, 'E2-I orden', { menu: false, screen: 'panel' });
    await exception.locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
    await openEntry(page, 'receivables');
    await panel(page).getByRole('button', { name: t.aurora.money.import }).click();
    await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(t.nav.import.label);
    await expectRule(page, 'E2-C importar', { menu: false, screen: 'panel' });

    // E5-p: «Vervallen» abre la busqueda con sus filtros (el panel se cierra en el mismo cambio).
    await openEntry(page, 'receivables');
    await expectRuleWhile(page, 'E2-C → E5-p', () => panelRow(page, t.aurora.money.overdue).click(), 1600);
    await expect(page.locator('.active-filter-chips')).toBeVisible();
    await expectRule(page, 'E5-p', { menu: false, screen: 'search' });

    // E6-h y E6-o: «Factuur openen» de una tarjeta (con el vuelo) y una orden dentro de la hoja.
    await openEntry(page, 'home');
    await openGroup(page, t.aurora.home.first);
    const first = await openCard(page, panel(page).locator('.doc-list button.doc').first());
    await expectRuleWhile(page, 'E2 → E6-h', () => first.getByRole('button', { name: t.aurora.card.openInvoice }).click(), 1600);
    await landed(page);
    await expect(sheetDialog(page)).toBeVisible();
    await expectRule(page, 'E6-h', { menu: false, screen: 'work' });
    const more = await openSheetRow(page, t.aurora.sheet.more);
    await more.getByRole('button', { name: t.notes.add, exact: true }).click();
    await expect(more.locator('.order-form')).toBeVisible();
    await expectRule(page, 'E6-o', { menu: false, screen: 'work' });
    await more.locator('.order-form').getByRole('button', { name: t.common.cancel }).click();
    await closeSheet(page);

    // E6-h plegada y desplegada (la de ocho filas): el control de plegar no trae la rueda.
    await openInvoice(page, 'DBO-2026-0417');
    await expectRule(page, 'E6-h plegada', { menu: false, screen: 'work' });
    await expectRuleWhile(page, 'E6-h desplegar', () => sheetFold(page).click(), 600);
    await expect(sheetFold(page)).toHaveAttribute('aria-expanded', 'true');
    await expectRule(page, 'E6-h desplegada', { menu: false, screen: 'work' });
    await expectRuleWhile(page, 'E6-h plegar', () => sheetFold(page).click(), 600);
    await expect(sheetFold(page)).toHaveAttribute('aria-expanded', 'false');
    await expectRule(page, 'E6-h plegada otra vez', { menu: false, screen: 'work' });
    await closeSheet(page);
    await toHome(page);
    await expectRule(page, 'E0 al final', { menu: false, home: true });
  });
}

test('el ayudante se prueba a si mismo: en el fundido de E1 → E6 la opacidad propia de la rueda es 1 y la efectiva baja de 1 a 0', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openMenu(page);
  await entryButton(page, 'documents').focus();
  await settled(page);
  const before = await seen(page);
  expect(before.menu, 'antes, la rueda se ve').toBe(true);
  expect(before.menuOpacity, 'antes, su opacidad efectiva').toBeGreaterThan(0.99);
  // A camara lenta (una decima de la velocidad, para muchos cuadros dentro de los 0,18 s).
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Animation.enable');
  await cdp.send('Animation.setPlaybackRate', { playbackRate: 0.1 });
  await startFrames(page);
  await entryButton(page, 'documents').click();
  // El fundido (0,18 s) y lo que espera motion para empezarlo, diez veces mas lentos.
  await expect.poll(() => page.locator('[data-aurora-root] > .app-screen').count(), { timeout: 20_000 }).toBe(1);
  const frames = await takeFrames(page);
  await cdp.send('Animation.setPlaybackRate', { playbackRate: 1 });
  await landed(page);
  const fading = frames.filter((f) => f.menuLeaving && f.menuOwn !== null);
  // La rueda (en la pantalla que se va): su opacity, siempre 1; la efectiva, de 1 a 0 y sin subir.
  expect(fading.length, 'cuadros del fundido').toBeGreaterThan(5);
  expect([...new Set(fading.map((f) => f.menuOwn))], 'la opacity propia de .navigation').toEqual([1]);
  const middle = fading.filter((f) => f.menuOpacity > 0.02 && f.menuOpacity < 0.98);
  expect(middle.length, 'cuadros a medio fundir').toBeGreaterThan(3);
  for (let i = 1; i < fading.length; i += 1) expect(fading[i]!.menuOpacity).toBeLessThanOrEqual(fading[i - 1]!.menuOpacity + 1e-6);
  expect(fading[0]!.menuOpacity, 'al empezar').toBeGreaterThan(0.9);
  // Al final, la rueda no se ve (opacidad efectiva 0 o ya desmontada).
  const after = await seen(page);
  expect(after.menu, 'despues, la rueda no se ve').toBe(false);
  expect(after.screens).toEqual(['work']);
  // Y mientras se veia a medias, el ayudante decia que se veia (por encima de 0,01).
  expect(middle.every((f) => f.menu), 'a medio fundir, se ve').toBe(true);
});

test('con «menos movimiento», E1 → E6 sin ningun cuadro con la rueda y Documentos a la vez', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openMenu(page);
  const both = await expectRuleWhile(page, 'E1 → Documenten (reduce)', () => documentsFromWheel(page), 1600, true);
  expect(both.length, 'cuadros con la rueda y Documentos').toBe(0);
  await landed(page);
  await expectRule(page, 'Documenten (reduce)', { menu: false, screen: 'work' });
});

for (const width of [1440, 1024] as const) {
  test(`la rueda escondida no manda a ${width} px: diez pasos abajo y diez arriba sobre el orbe, el hueco y el saludo, las flechas y Tab`, async ({ page, baseUrl }) => {
    test.setTimeout(480_000);
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${baseUrl}/app`);
    await login(page);
    for (const id of ['settings', 'home', 'receivables', 'payables', 'vat'] as const) {
      // El hueco: donde esta la rueda en E1.
      await openMenu(page);
      const wheelBox = (await page.locator('.navigation').boundingBox())!;
      await openEntry(page, id);
      await expectRule(page, `E2 ${id}`, { menu: false, screen: 'panel' });
      const state = () =>
        page.evaluate(() => ({
          active: document.querySelector('[data-aurora-root] .app')?.getAttribute('data-active') ?? null,
          current: document.querySelector('.navigation .nav-item[aria-current="true"]')?.getAttribute('data-entry') ?? null,
          phase: document.querySelector('.aurora [data-flow-phase]')?.getAttribute('data-flow-phase') ?? null,
          highlight: document.querySelector('[data-aurora-root] .app')?.classList.contains('process-highlight') ?? false,
          orb: document.querySelectorAll('.aurora .hero-orb').length,
        }));
      const start = await state();
      expect(start.active, `${id}: la activa es la entrada del panel`).toBe(id);
      expect(start.current, `${id}: aria-current`).toBe(id);
      expect(start.phase, `${id}: la fase de la onda`).not.toBeNull();
      const at = async (selector: string) => {
        const b = await page.locator(selector).first().boundingBox();
        return b && b.width > 0 ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null;
      };
      const places = [
        { name: 'el orbe', point: await at('button.aurora') },
        { name: 'el hueco de la rueda', point: { x: wheelBox.x + wheelBox.width / 2, y: wheelBox.y + wheelBox.height / 2 } },
        { name: 'el saludo', point: await page.locator('.welcome-line h1').isVisible() ? await at('.welcome-line h1') : null },
      ];
      const seenStates: string[] = [];
      for (const place of places) {
        if (!place.point) continue;
        await page.mouse.move(place.point.x, place.point.y);
        for (const dy of [...Array<number>(10).fill(120), ...Array<number>(10).fill(-120)]) {
          await page.mouse.wheel(0, dy);
          // Mas que los 240 ms entre gestos de main.tsx:25.
          await page.waitForTimeout(300);
          const now = await state();
          if (now.active !== start.active || now.highlight || now.orb > 0 || now.phase !== start.phase || now.current !== start.current) seenStates.push(`${place.name}: ${JSON.stringify(now)}`);
        }
      }
      // Las flechas y Tab: ninguna fila de la rueda recibe el foco.
      const focused: string[] = [];
      for (const key of ['ArrowDown', 'ArrowDown', 'ArrowUp', 'ArrowUp', ...Array<string>(25).fill('Tab')]) {
        await page.keyboard.press(key);
        const where = await page.evaluate(() => (document.activeElement?.closest('.navigation') ? document.activeElement.getAttribute('data-entry') ?? 'navigation' : null));
        if (where) focused.push(`${key}: ${where}`);
      }
      expect(seenStates, `${id}: la rueda escondida cambio algo`).toEqual([]);
      expect(focused, `${id}: una fila de la rueda con el foco`).toEqual([]);
      expect(await state(), `${id}: al final`).toEqual(start);
      await expectRule(page, `E2 ${id} tras la rueda, las flechas y Tab`, { menu: false, screen: 'panel' });
      // El orbe lleva al inicio (E0), no a Procesar.
      await page.keyboard.press('Escape');
      await page.locator('button.aurora').click();
      await expect(app(page)).not.toHaveClass(/\bprocess-mode\b/);
      await expectRule(page, `E0 tras ${id}`, { menu: false, home: true });
      await expect(page.getByRole('button', { name: t.aurora.home.navigate })).toBeVisible();
    }
  });
}

test('un solo cambio (F9): E4 → E2 y E2 → E5-p, sin ningun render con la rueda sin .has-panel ni dos pantallas', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // E4 → E2: la fila «Btw» de una respuesta abre su panel.
  await ask(page, 'Btw');
  const row = answerRow(page, t.areas.vat.label).first();
  await expect(row).toBeVisible();
  await settled(page);
  await startRenders(page);
  await row.click();
  await expect(panel(page)).toBeVisible();
  await page.waitForTimeout(800);
  const toPanel = await takeRenders(page);
  expect(toPanel.length, 'renders medidos').toBeGreaterThan(3);
  expect(renderViolations(toPanel), 'E4 → E2').toEqual([]);
  expect(toPanel.at(-1), 'al final, el panel de Btw con la rueda escondida').toMatchObject({ panel: true, hasPanel: true, conversation: false });
  await expectRule(page, 'E2 desde la conversacion', { menu: false, screen: 'panel' });
  // E2 → E5-p: «Vervallen» en Te ontvangen.
  await openEntry(page, 'receivables');
  await startRenders(page);
  await panelRow(page, t.aurora.money.overdue).click();
  await expect(page.locator('.active-filter-chips')).toBeVisible();
  await page.waitForTimeout(800);
  const toSearch = await takeRenders(page);
  expect(renderViolations(toSearch), 'E2 → E5-p').toEqual([]);
  expect(toSearch.at(-1), 'al final, la busqueda sola').toMatchObject({ panel: false, search: true, wheel: false });
  await expectRule(page, 'E5-p', { menu: false, screen: 'search' });
});
