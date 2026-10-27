// Moverse por la app como una persona (paso 16): la rueda en el inicio, las seis entradas en
// pequeno en las demas pantallas, las vistas de cada seccion, las migas y "Volver", y el menu
// del nombre (Ajustes, idioma, tema y Salir). Los nombres salen de los diccionarios de la app y
// la forma de las secciones de src/screens/sections.ts: si cambian, las pruebas siguen.
import { expect, type Locator, type Page } from '@playwright/test';
import { en } from '../src/i18n/en';
import { es } from '../src/i18n/es';
import type { Lang } from '../src/i18n/langs';
import { nl } from '../src/i18n/nl';
import { SECTION_VIEWS, sectionOfView, type SectionId, type ViewId } from '../src/screens/sections';
import { ACCOUNT_MENU, settled } from './fixtures';

export const TEXTS = { nl, en, es } as const;

/** Cada idioma por su nombre en ese idioma (asi se llaman en el menu y en la entrada). */
export const LANG_NAMES: Record<Lang, string> = { nl: 'Nederlands', en: 'English', es: 'Español' };

export function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** "{a} van {b}" con los huecos ya puestos. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (hole, name: string) => (name in values ? String(values[name]) : hole));
}

/** La navegacion principal: la rueda (inicio) o las seis entradas en pequeno. */
export function mainMenu(page: Page, lang: Lang = 'nl'): Locator {
  return page.getByRole('navigation', { name: TEXTS[lang].shell.mainNavigation });
}

/** Las vistas de una seccion (las pastillas encima de la pantalla). */
export function sectionMenu(page: Page, section: SectionId, lang: Lang = 'nl'): Locator {
  const t = TEXTS[lang];
  return page.getByRole('navigation', { name: fill(t.shell.sectionNavigation, { section: t.areas[section].label }) });
}

/** El boton de una entrada en la navegacion principal. */
export function sectionButton(page: Page, section: SectionId, lang: Lang = 'nl'): Locator {
  return mainMenu(page, lang).getByRole('button', { name: TEXTS[lang].areas[section].label, exact: true });
}

/** El titulo (h1) de una vista: el saludo en el inicio, su nombre en las demas. */
export function viewHeading(page: Page, view: ViewId, lang: Lang = 'nl'): Locator {
  const t = TEXTS[lang];
  if (view === 'home') {
    const before = t.home.greeting.split('{name}')[0]!;
    return page.getByRole('heading', { level: 1, name: new RegExp(`^${escapeRegExp(before)}`) });
  }
  return page.getByRole('heading', { level: 1, name: t.nav[view].label, exact: true });
}

/** Abre una entrada (un clic: en la rueda o en la navegacion compacta). */
export async function openSection(page: Page, section: SectionId, lang: Lang = 'nl'): Promise<void> {
  await sectionButton(page, section, lang).click();
}

/**
 * Va a una vista como lo haria una persona: su entrada y, si no es la primera de la seccion, su
 * pastilla (en Inicio, sus accesos de "Ook in Start"); Ajustes, desde el menu del nombre.
 */
export async function go(page: Page, view: ViewId, lang: Lang = 'nl'): Promise<void> {
  const t = TEXTS[lang];
  if (view === 'home' && (await viewHeading(page, 'home', lang).count())) {
    // Ya en el inicio: su entrada en la rueda lleva a lo de debajo de la rueda (las tarjetas);
    // quien quiere ver el inicio entero vuelve arriba.
    await page.evaluate(() => window.scrollTo(0, 0));
  } else if (view === 'settings') {
    await page.getByRole('button', { name: ACCOUNT_MENU }).click();
    await page.getByRole('menuitem', { name: t.nav.settings.label }).click();
  } else {
    const section = sectionOfView(view)!;
    await openSection(page, section, lang);
    if (view !== SECTION_VIEWS[section][0]) {
      const name = new RegExp(`^${escapeRegExp(t.nav[view].label)}`);
      if (section === 'home') {
        await page.getByRole('navigation', { name: t.home.alsoHere }).getByRole('button', { name }).click();
      } else {
        await sectionMenu(page, section, lang).getByRole('button', { name }).click();
      }
    }
  }
  await expect(viewHeading(page, view, lang)).toBeVisible();
  await settled(page);
}

/** "Volver": un paso atras dentro de una seccion. */
export async function back(page: Page, lang: Lang = 'nl'): Promise<void> {
  await page.getByRole('button', { name: TEXTS[lang].shell.back, exact: true }).click();
  await settled(page);
}

/** Las migas (lo que dicen, en orden). */
export async function crumbs(page: Page, lang: Lang = 'nl'): Promise<string[]> {
  const list = page.getByRole('navigation', { name: TEXTS[lang].shell.breadcrumbs }).getByRole('listitem');
  return (await list.allTextContents()).map((s) => s.trim());
}

/** Cambia el idioma: en la entrada, sus botones; dentro, el menu del nombre. */
export async function setLang(page: Page, lang: Lang): Promise<void> {
  // Dentro de la app esta el contenido (#contenido) aunque un dialogo que se cierra tape aun el
  // resto para el lector de pantalla (y el boton del nombre no se vea por su papel).
  if (await page.locator('#contenido').count()) {
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.getByRole('button', { name: ACCOUNT_MENU }).click();
    await page.getByRole('menuitemradio', { name: LANG_NAMES[lang] }).click();
    await expect(page.getByRole('menu')).toBeHidden();
  } else {
    await page.getByRole('button', { name: LANG_NAMES[lang] }).first().click();
  }
  await expect(page.locator('html')).toHaveAttribute('lang', lang);
  await settled(page);
}

/** Sale con el menu del nombre y espera a la entrada. */
export async function signOut(page: Page, lang: Lang = 'nl'): Promise<void> {
  await page.getByRole('button', { name: ACCOUNT_MENU }).click();
  await page.getByRole('menuitem', { name: TEXTS[lang].account.logout }).click();
  await expect(page.getByRole('heading', { level: 1, name: TEXTS[lang].login.title })).toBeVisible();
}

/** El numero de la insignia de una vista en las pastillas de su seccion (0 si no hay). */
export async function readBadge(page: Page, view: ViewId, lang: Lang = 'nl'): Promise<number> {
  const section = sectionOfView(view)!;
  const pill = sectionMenu(page, section, lang).getByRole('button', { name: new RegExp(`^${escapeRegExp(TEXTS[lang].nav[view].label)}`) });
  const label = TEXTS[lang].nav[view].label;
  const text = ((await pill.textContent()) ?? '').replace(label, '');
  const m = /(\d+)/.exec(text);
  return m ? Number(m[1]) : 0;
}
