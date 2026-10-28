// Moverse por la app como una persona (paso 17, la app de Aurora): el orbe y "Presiona para
// navegar" abren la rueda; una entrada abre su panel (Ajustes, Inicio, Cuentas por cobrar y por
// pagar, IVA), la busqueda o una pantalla de trabajo (Documentos, Procesar); una fila del panel
// abre su pantalla de trabajo con el vuelo del orbe; las migas y "Volver a Aurora" vuelven. El
// idioma, el tema y Salir estan en Ajustes. Los nombres salen de los diccionarios de la app y la
// forma de las entradas de src/aurora/estado.ts: si cambian, las pruebas siguen.
import { expect, type Locator, type Page } from '@playwright/test';
import { ENTRIES, PANEL_SCREENS, entryOfView, type EntryId } from '../src/aurora/estado';
import { en } from '../src/i18n/en';
import { es } from '../src/i18n/es';
import type { Lang } from '../src/i18n/langs';
import { nl } from '../src/i18n/nl';
import type { ThemeChoice } from '../src/lib/theme-choice';
import { isOverviewView, type ViewId } from '../src/screens/sections';
import { settled } from './fixtures';

export const TEXTS = { nl, en, es } as const;

/** Cada idioma por su nombre en ese idioma (asi se llaman en la entrada y en Ajustes). */
export const LANG_NAMES: Record<Lang, string> = { nl: 'Nederlands', en: 'English', es: 'Español' };

export function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** "{a} van {b}" con los huecos ya puestos. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (hole, name: string) => (name in values ? String(values[name]) : hole));
}

/** El nombre de una entrada de la rueda (aurora/app.tsx, entryLabel). */
export function entryLabel(id: EntryId, lang: Lang = 'nl'): string {
  const t = TEXTS[lang];
  if (id === 'settings') return t.nav.settings.label;
  if (id === 'search') return t.aurora.home.searchEntry;
  return t.areas[id].label;
}

/** Lo que dice la fila de una vista en el panel de su entrada (la primera, "Resumen"). */
export function rowLabel(view: ViewId, lang: Lang = 'nl'): string {
  const entry = entryOfView(view);
  return view === entry ? TEXTS[lang].aurora.panel.overview : TEXTS[lang].nav[view].label;
}

/** La raiz de Aurora: data-screen dice si se ve el inicio o una pantalla de trabajo. */
export const auroraRoot = (page: Page) => page.locator('[data-aurora-root]');
/** El espacio de Aurora (E0 a E5): su clase dice el estado (navigating, has-panel...). */
export const app = (page: Page) => page.locator('[data-aurora-root] .app');
/** El orbe grande. */
export const orb = (page: Page) => page.locator('button.aurora');
/** La rueda (solo existe con el menu abierto). */
export const wheel = (page: Page) => page.locator('section.navigation');
/** Una entrada de la rueda. */
export const entryButton = (page: Page, id: EntryId) => page.locator(`.navigation .nav-item[data-entry="${id}"]`);
/** El panel abierto (E2). */
export const panel = (page: Page) => page.locator('aside.panel');
/** Las migas de una pantalla de trabajo. */
export const crumbsNav = (page: Page, lang: Lang = 'nl') => page.getByRole('navigation', { name: TEXTS[lang].shell.breadcrumbs });

/** Una fila de un panel (o de una vista de grupo) por lo que dice su titulo. */
export function panelRow(page: Page, label: string): Locator {
  return panel(page).locator('button.doc').filter({ has: page.locator('strong').getByText(label, { exact: true }) });
}

/** El saludo del inicio ("Welkom, Ana"). */
export function greeting(page: Page, lang: Lang = 'nl'): Locator {
  const before = TEXTS[lang].aurora.home.greeting.split('{name}')[0]!;
  return page.getByRole('heading', { level: 1, name: new RegExp(`^${escapeRegExp(before)}`) });
}

/** El idioma que se ve (el lang de <html>): las ayudas lo usan si no se les dice otro. */
export async function pageLang(page: Page): Promise<Lang> {
  const lang = await page.locator('html').getAttribute('lang');
  return lang === 'en' || lang === 'es' ? lang : 'nl';
}

/** Que se esta en una pantalla de trabajo. */
export async function onWorkScreen(page: Page): Promise<boolean> {
  return (await auroraRoot(page).getAttribute('data-screen')) === 'work';
}

/** El vuelo del orbe ha terminado (o no habia). */
export async function landed(page: Page): Promise<void> {
  await expect(page.locator('.aurora-route-flight')).toHaveCount(0);
  await expect(page.locator('[data-aurora-root] > .app-screen')).toHaveCount(1);
}

/** De vuelta en el espacio de Aurora: desde una pantalla de trabajo, "Volver a Aurora". */
export async function toAurora(page: Page): Promise<void> {
  if (await onWorkScreen(page)) await page.locator('a.ws-home').click();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await landed(page);
}

/** La clase del espacio (para saber en que estado esta). */
async function state(page: Page): Promise<string> {
  return (await app(page).getAttribute('class')) ?? '';
}

/** E0: el inicio, con la rueda cerrada y sin panel, conversacion ni busqueda. */
export async function toHome(page: Page): Promise<void> {
  await toAurora(page);
  for (let i = 0; i < 3; i += 1) {
    const s = await state(page);
    if (!/\b(navigating|has-panel|chatting|search-mode|conversation-mode)\b/.test(s)) break;
    // En la conversacion (E4) el orbe no esta a la vista: «Terug naar de ruimte» vuelve a la
    // rueda (E1) y de ahi el orbe la cierra.
    const back = page.getByRole('button', { name: TEXTS[await pageLang(page)].aurora.chat.back });
    if (await back.isVisible()) {
      await back.click();
      await expect.poll(() => state(page)).not.toBe(s);
      continue;
    }
    // Con Procesar en el centro el orbe entra en Procesar: antes, otra entrada al centro.
    if (/\bprocess-highlight\b/.test(s)) await centre(page, 'vat');
    await orb(page).click();
    await expect.poll(() => state(page)).not.toBe(s);
  }
  await expect(app(page)).not.toHaveClass(/\b(navigating|has-panel|chatting|search-mode)\b/);
  await settled(page);
}

/** E1: la rueda abierta y sin panel. */
export async function openMenu(page: Page, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await toAurora(page);
  const s = await state(page);
  if (/\bhas-panel\b/.test(s)) {
    // La ✕ del panel vuelve a la rueda (E1).
    await panel(page).getByRole('button', { name: TEXTS[lang].aurora.panel.close }).click();
  } else if (!/\bnavigating\b/.test(s) || /\b(chatting|search-mode)\b/.test(s)) {
    await toHome(page);
    await page.getByRole('button', { name: TEXTS[lang].aurora.home.navigate }).click();
  }
  await expect(wheel(page)).toBeVisible();
  await expect(panel(page)).toHaveCount(0);
}

/** Pone una entrada en el centro de la rueda como con el teclado (Tab la centra). */
export async function centre(page: Page, id: EntryId): Promise<void> {
  const button = entryButton(page, id);
  if ((await button.getAttribute('aria-current')) !== 'true') {
    await button.focus();
    await expect(button).toHaveAttribute('aria-current', 'true');
  }
  await settled(page);
}

/** Abre una entrada de la rueda: un clic en ella, ya en el centro. */
export async function openEntry(page: Page, id: EntryId, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await openMenu(page, lang);
  await centre(page, id);
  await entryButton(page, id).click();
  if (id === 'documents' || id === 'process') {
    await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
    await landed(page);
  } else if (id === 'search') {
    await expect(app(page)).toHaveClass(/\bsearch-mode\b/);
  } else {
    await expect(panel(page).getByRole('heading', { level: 2, name: entryLabel(id, lang), exact: true })).toBeVisible();
  }
  await settled(page);
}

/** El titulo de una vista: su h1 en la pantalla de trabajo (Ajustes: el h2 de su panel). */
export function viewHeading(page: Page, view: ViewId, lang: Lang = 'nl'): Locator {
  const t = TEXTS[lang];
  if (view === 'settings') return panel(page).getByRole('heading', { level: 2, name: t.nav.settings.label, exact: true });
  // Los resumenes de Cuentas por cobrar y por pagar llevan el titulo de su entrada.
  const name = isOverviewView(view) ? t.areas[view].label : t.nav[view].label;
  return page.getByRole('heading', { level: 1, name, exact: true });
}

/** Va a una vista como lo haria una persona: su entrada en la rueda y, si es de un panel, su fila. */
export async function go(page: Page, view: ViewId, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  const entry = entryOfView(view);
  if (view === 'settings' || entry === 'documents' || entry === 'process') {
    await openEntry(page, entry, lang);
  } else {
    await openEntry(page, entry, lang);
    await panelRow(page, rowLabel(view, lang)).click();
    await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
    await landed(page);
  }
  await expect(viewHeading(page, view, lang)).toBeVisible();
  await settled(page);
}

/** Un paso atras en una pantalla de trabajo: la miga anterior (en la primera, al inicio). */
export async function back(page: Page, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await crumbsNav(page, lang).getByRole('link').last().click();
  await landed(page);
  await settled(page);
}

/** Las migas despues de "Inicio" (lo que dicen, en orden). */
export async function crumbs(page: Page, language?: Lang): Promise<string[]> {
  const lang = language ?? (await pageLang(page));
  const list = crumbsNav(page, lang).getByRole('listitem');
  const all = (await list.allTextContents()).map((s) => s.trim());
  expect(all[0]).toBe(TEXTS[lang].aurora.work.home);
  return all.slice(1);
}

/** Abre Ajustes y una de sus filas (Idioma, Tema, Tu cuenta, Sistema). */
export async function openSettingsRow(page: Page, row: 'language' | 'theme' | 'account' | 'system', language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await openEntry(page, 'settings', lang);
  const s = TEXTS[lang].aurora.settings;
  await panelRow(page, { language: s.language, theme: s.theme, account: s.account, system: s.system }[row]).click();
  await settled(page);
}

/** Cambia el idioma: en la entrada, sus botones; dentro, Ajustes > Idioma. */
export async function setLang(page: Page, lang: Lang): Promise<void> {
  if (await page.locator('#token').count()) {
    await page.getByRole('button', { name: LANG_NAMES[lang], exact: true }).click();
  } else {
    const now = ((await page.locator('html').getAttribute('lang')) ?? 'nl') as Lang;
    if (now !== lang) {
      await openSettingsRow(page, 'language', now);
      await panelRow(page, LANG_NAMES[lang]).click();
    }
  }
  await expect(page.locator('html')).toHaveAttribute('lang', lang);
  await settled(page);
}

/** Sale desde Ajustes y espera a la entrada. */
export async function signOut(page: Page, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await openEntry(page, 'settings', lang);
  await panel(page).getByRole('button', { name: TEXTS[lang].account.logout }).click();
  await expect(page.getByRole('heading', { level: 1, name: TEXTS[lang].aurora.login.welcome })).toBeVisible();
  await expect(page.locator('#token')).toBeVisible();
}

/** El numero de la fila de una vista en el panel de su entrada (0 si no hay). */
export async function readBadge(page: Page, view: ViewId, language?: Lang): Promise<number> {
  const lang = language ?? (await pageLang(page));
  const entry = entryOfView(view);
  if (!((await panel(page).count()) && (await panel(page).locator('h2').textContent()) === entryLabel(entry, lang))) {
    await openEntry(page, entry, lang);
  }
  const figure = panelRow(page, rowLabel(view, lang)).locator('.doc-end strong');
  if (!(await figure.count())) return 0;
  const m = /(\d+)/.exec((await figure.textContent()) ?? '');
  return m ? Number(m[1]) : 0;
}

/** Elige el tema en Ajustes > Tema (Donker / Licht / Volg Windows) y espera a que se vea. */
export async function chooseTheme(page: Page, choice: ThemeChoice, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await openSettingsRow(page, 'theme', lang);
  await panelRow(page, TEXTS[lang].theme[choice]).click();
  if (choice !== 'system') await expect(page.locator('html')).toHaveAttribute('data-theme', choice);
  await settled(page);
}

/** Las vistas de cada panel (src/aurora/estado.ts) y las ocho entradas, para recorrerlas. */
export { ENTRIES, PANEL_SCREENS, entryOfView };
