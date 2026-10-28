// La regla del dueno (paso 17, especificacion §1.1 y §6.4): «No pueden vivir las pantallas y el
// menu al mismo tiempo». El menu es la rueda; una pantalla es un panel (E2), la conversacion
// (E4), la busqueda (E5) o una pantalla de trabajo (Documentos, Procesar, las del motor). En cada
// estado, en cada ancho (los de Aurora a ambos lados de sus cortes: 1150 y 700) y en cada cuadro
// de las transiciones, se ve uno o lo otro, nunca los dos. «Se ve» es de verdad: montado, con
// display y visibility, una opacidad efectiva (la de todos sus padres) por encima de 0,05, con
// tamano y dentro de la ventana. La pantalla que se va (el fundido de 0,18 s de Root) no cuenta,
// pero no recibe clics. Y con un panel abierto, la rueda escondida no manda: ni la rueda del
// raton ni las flechas cambian la entrada activa. Los paneles por dentro (una vista de grupo, una
// tarjeta, una orden abierta e importar), la busqueda con filtros que abre un panel (E5-p) y la
// hoja de una factura con una orden abierta (E6-h, E6-o) cuentan como su pantalla.
import type { Page } from '@playwright/test';
import { expect, login, settled, test } from './fixtures';
import {
  TEXTS,
  app,
  closeSheet,
  entryButton,
  landed,
  openCard,
  openEntry,
  openGroup,
  openMenu,
  openSettingsRow,
  openSheetRow,
  panel,
  panelRow,
  sheetDialog,
  toHome,
} from './nav';

const t = TEXTS.nl;

/** Lo que se ve ahora: la rueda y cada clase de pantalla. */
interface Seen {
  menu: boolean;
  screens: string[];
  /** La pantalla que se va recibe clics (no debe). */
  leavingClickable: boolean;
}

/** La comprobacion, dentro de la pagina (la misma en cada estado y en cada cuadro). */
const SEEN = `(() => {
  const root = document.querySelector('[data-aurora-root]');
  const now = root ? root.getAttribute('data-screen') : null;
  const leaving = (el) => {
    const screen = el.closest('.app-screen');
    return !!screen && screen.getAttribute('data-screen') !== now;
  };
  const shown = (el) => {
    if (!el || !el.isConnected || leaving(el)) return false;
    if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
    let opacity = 1;
    for (let e = el; e; e = e.parentElement) opacity *= parseFloat(getComputedStyle(e).opacity);
    if (opacity < 0.05) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    return r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight;
  };
  const any = (sel) => Array.from(document.querySelectorAll(sel)).some(shown);
  const SCREENS = { panel: 'aside.panel', conversation: '.conversation', search: '.search-workspace', work: '.workspace-host, .ws-layout' };
  const screens = Object.entries(SCREENS).filter(([, sel]) => any(sel)).map(([name]) => name);
  const leavingClickable = Array.from(document.querySelectorAll('[data-aurora-root] > .app-screen'))
    .filter((s) => s.getAttribute('data-screen') !== now)
    .some((s) => getComputedStyle(s).pointerEvents !== 'none');
  return { menu: any('.navigation .nav-item'), screens, leavingClickable };
})()`;

async function seen(page: Page): Promise<Seen> {
  return page.evaluate(SEEN) as Promise<Seen>;
}

/** La regla, ahora: o la rueda o una pantalla (o ninguna de las dos). */
async function expectRule(page: Page, what: string, expected: { menu: boolean; screen?: string }): Promise<void> {
  await settled(page);
  const s = await seen(page);
  expect(s.menu && s.screens.length > 0, `${what}: la rueda y ${s.screens.join(', ')} a la vez`).toBe(false);
  expect(s.menu, `${what}: la rueda`).toBe(expected.menu);
  expect(s.screens, `${what}: la pantalla`).toEqual(expected.screen ? [expected.screen] : []);
}

/** Cada cuadro mientras pasa algo: nunca la rueda y una pantalla a la vez. */
async function expectRuleWhile(page: Page, what: string, action: () => Promise<void>, ms = 1400): Promise<void> {
  await page.evaluate(`(() => {
    const frames = [];
    window.__bmsFrames = frames;
    const tick = () => {
      frames.push(${SEEN});
      if (window.__bmsFrames === frames) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  })()`);
  await action();
  await page.waitForTimeout(ms);
  const frames = (await page.evaluate(`(() => { const f = window.__bmsFrames; window.__bmsFrames = null; return f; })()`)) as Seen[];
  expect(frames.length, `${what}: cuadros medidos`).toBeGreaterThan(5);
  const both = frames.filter((f) => f.menu && f.screens.length > 0);
  expect(both.map((f) => f.screens.join('+')), `${what}: cuadros con la rueda y una pantalla`).toEqual([]);
  expect(frames.filter((f) => f.leavingClickable).length, `${what}: la pantalla que se va recibe clics`).toBe(0);
}

for (const width of [1440, 1151, 1150, 1024, 400] as const) {
  test(`o el menu o una pantalla, a ${width} px, en cada estado y en cada cuadro`, async ({ page, baseUrl }) => {
    test.setTimeout(300_000);
    await page.setViewportSize({ width, height: width === 400 ? 860 : 900 });
    await page.goto(`${baseUrl}/app`);
    // L0 y E0: ni rueda ni pantalla.
    await expectRule(page, 'L0', { menu: false });
    await login(page);
    await expectRule(page, 'E0', { menu: false });
    // E1: la rueda.
    await expectRuleWhile(page, 'E0 → E1', () => page.getByRole('button', { name: t.aurora.home.navigate }).click());
    await expectRule(page, 'E1', { menu: true });
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
      // La rueda escondida no manda: ni la rueda del raton ni las flechas cambian la activa.
      const active = await app(page).getAttribute('data-active');
      await page.mouse.move(width / 3, 450);
      for (const dy of [120, 120, -120]) {
        await page.mouse.wheel(0, dy);
        await page.waitForTimeout(260);
      }
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('ArrowUp');
      expect(await app(page).getAttribute('data-active'), `E2 ${id}: la activa`).toBe(active);
      await expectRule(page, `E2 ${id} tras la rueda`, { menu: false, screen: 'panel' });
      await expectRuleWhile(page, `E2 ${id} → E1`, () => panel(page).getByRole('button', { name: t.aurora.panel.close }).click());
      await expectRule(page, `E1 tras ${id}`, { menu: true });
    }
    // E2-A con una vista de grupo y con una tarjeta.
    await openSettingsRow(page, 'language');
    await expectRule(page, 'E2-A idioma', { menu: false, screen: 'panel' });
    await openSettingsRow(page, 'account');
    await expect(panel(page).locator('.detail')).toBeVisible();
    await expectRule(page, 'E2-A tarjeta', { menu: false, screen: 'panel' });
    // El orbe con un panel: al inicio.
    await expectRuleWhile(page, 'E2 → E0 (orbe)', () => page.locator('button.aurora').click());
    await expectRule(page, 'E0 tras el orbe', { menu: false });

    // E5: la busqueda (desde la rueda).
    await openMenu(page);
    await expectRuleWhile(page, 'E1 → E5', async () => {
      await entryButton(page, 'search').focus();
      await settled(page);
      await entryButton(page, 'search').click();
    });
    await expectRule(page, 'E5', { menu: false, screen: 'search' });

    // E4: la conversacion (con el resumen), desde la rueda abierta.
    await openMenu(page);
    const ask = page.getByRole('textbox', { name: t.aurora.composer.askLabel });
    await ask.fill('Geef me een overzicht');
    await expectRuleWhile(page, 'E1 → E4', () => ask.press('Enter'), 2500);
    await expect(page.locator('.finance-bento')).toBeVisible();
    await expectRule(page, 'E4', { menu: false, screen: 'conversation' });
    // «Terug naar de ruimte»: E1, sin conversacion.
    await expectRuleWhile(page, 'E4 → E1', () => page.getByRole('button', { name: t.aurora.chat.back }).click());
    await expectRule(page, 'E1 tras la conversacion', { menu: true });

    // Pantallas de trabajo: Documentos desde la rueda (con el vuelo) y una del motor desde un panel.
    await expectRuleWhile(
      page,
      'E1 → Documenten',
      async () => {
        await entryButton(page, 'documents').focus();
        await settled(page);
        await entryButton(page, 'documents').click();
      },
      1600
    );
    await landed(page);
    await expectRule(page, 'Documenten', { menu: false, screen: 'work' });
    await expectRuleWhile(page, 'Documenten → E0', () => page.locator('a.ws-home').click(), 1600);
    await landed(page);
    await expectRule(page, 'E0 tras Documenten', { menu: false });

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
    await toHome(page);
    await expectRule(page, 'E0 al final', { menu: false });
  });
}
