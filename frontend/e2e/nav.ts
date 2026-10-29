// Moverse por la app como una persona (paso 17, la app de Aurora; especificacion §6.6): el orbe y
// "Presiona para navegar" abren la rueda (openMenu); un paso de la rueda (wheelStep); una entrada
// abre su panel (Ajustes, Inicio, Cuentas por cobrar y por pagar, IVA), la busqueda, Documentos
// (la pantalla de trabajo, con el vuelo) o Procesar (el espacio central con la suricata) (openEntry). En un panel, una fila de grupo abre su
// vista (openGroup) y «Volver a …» vuelve (backFromGroup); una fila de una vista abre su tarjeta
// .detail (openCard); la ✕ cierra el panel (closePanel) y el orbe lleva al inicio (home). Una
// factura se abre escribiendo su numero en la caja: la fila de la respuesta lleva con el vuelo a
// su hoja en Documentos (openInvoice), y la tabla de la hoja tiene sus filas (invoiceRow). El
// idioma, el tema y Salir estan en Ajustes (settings). readCount lee el numero de una fila de
// grupo (doc-end) o el de la vista abierta (.list-title). Los nombres salen de los diccionarios
// de la app y de src/aurora/estado.ts: si cambian, las pruebas siguen.
import { expect, type Locator, type Page } from '@playwright/test';
import { ENTRIES, type EntryId } from '../src/aurora/estado';
import { en } from '../src/i18n/en';
import { es } from '../src/i18n/es';
import type { Lang } from '../src/i18n/langs';
import { nl } from '../src/i18n/nl';
import type { ThemeChoice } from '../src/lib/theme-choice';
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

/** Un importe como lo escribe la app (lib/format.ts): euro, espacio que no se parte y notacion
 *  neerlandesa. */
export function euro(cents: number): string {
  const abs = Math.abs(cents);
  const units = Math.floor(abs / 100)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `€ ${cents < 0 ? '−' : ''}${units},${String(abs % 100).padStart(2, '0')}`;
}

/** El nombre de una entrada de la rueda (aurora/app.tsx, entryLabel). */
export function entryLabel(id: EntryId, lang: Lang = 'nl'): string {
  const t = TEXTS[lang];
  if (id === 'settings') return t.nav.settings.label;
  if (id === 'search') return t.aurora.home.searchEntry;
  return t.areas[id].label;
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
/** La tarjeta .detail abierta (en el panel o en la hoja de una factura). */
export const detail = (page: Page) => page.locator('aside.panel .detail, dialog.ws-dialog[open] .detail');
/** Las migas de una pantalla de trabajo. */
export const crumbsNav = (page: Page, lang: Lang = 'nl') => page.getByRole('navigation', { name: TEXTS[lang].shell.breadcrumbs });
/** La hoja de una factura (o de un documento, un Object, una PO): el <dialog> de Documentos. */
export const sheetDialog = (page: Page) => page.locator('dialog.ws-dialog[open]');

/** Una fila de un panel (o de una vista de grupo) por lo que dice su titulo. */
export function panelRow(page: Page, label: string | RegExp): Locator {
  const title = typeof label === 'string' ? page.locator('strong').getByText(label, { exact: true }) : page.locator('strong', { hasText: label });
  return panel(page).locator('button.doc').filter({ has: title });
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

/** De vuelta en el espacio de Aurora: desde una pantalla de trabajo, "Volver a Aurora" (con una
 *  hoja abierta, primero se cierra: Escape). */
export async function toAurora(page: Page): Promise<void> {
  if (await onWorkScreen(page)) {
    if (await sheetDialog(page).count()) {
      await page.keyboard.press('Escape');
      if (await sheetDialog(page).count()) await page.keyboard.press('Escape');
      await expect(sheetDialog(page)).toHaveCount(0);
    }
    await page.locator('a.ws-home').click();
  }
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
    if (!/\b(navigating|has-panel|chatting|search-mode|conversation-mode|process-mode)\b/.test(s)) break;
    // En Procesar no hay orbe: «Volver al inicio».
    if (/\bprocess-mode\b/.test(s)) {
      await page.locator('.processing-back').click();
      await expect.poll(() => state(page)).not.toMatch(/\bprocess-mode\b/);
      continue;
    }
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
  await expect(app(page)).not.toHaveClass(/\b(navigating|has-panel|chatting|search-mode|process-mode)\b/);
  await settled(page);
}

/** El orbe: al inicio (E0) desde cualquier estado. */
export const home = toHome;

/** E1: la rueda abierta y sin panel. */
export async function openMenu(page: Page, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await toAurora(page);
  const s = await state(page);
  if (/\bhas-panel\b/.test(s)) {
    // La ✕ del panel vuelve a la rueda (E1).
    await panel(page).getByRole('button', { name: TEXTS[lang].aurora.panel.close }).click();
  } else if (!/\bnavigating\b/.test(s) || /\b(chatting|search-mode|process-mode)\b/.test(s)) {
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

/** Un paso de la rueda: un gesto de la rueda del raton sobre ella (n > 0, hacia abajo). */
export async function wheelStep(page: Page, n: number): Promise<void> {
  const box = await page.locator('.marquee').boundingBox();
  expect(box, 'la rueda').not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  for (let i = 0; i < Math.abs(n); i += 1) {
    const before = await app(page).getAttribute('data-active');
    await page.mouse.wheel(0, n > 0 ? 120 : -120);
    await expect.poll(() => app(page).getAttribute('data-active')).not.toBe(before);
    // Un gesto cada 240 ms como mucho (main.tsx:25).
    await page.waitForTimeout(260);
  }
  await settled(page);
}

/** Abre una entrada de la rueda: un clic en ella, ya en el centro. */
export async function openEntry(page: Page, id: EntryId, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await openMenu(page, lang);
  await centre(page, id);
  await entryButton(page, id).click();
  if (id === 'documents') {
    await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
    await landed(page);
  } else if (id === 'process') {
    await processLanded(page);
  } else if (id === 'search') {
    await expect(app(page)).toHaveClass(/\bsearch-mode\b/);
  } else {
    await expect(panel(page).getByRole('heading', { level: 2, name: entryLabel(id, lang), exact: true })).toBeVisible();
  }
  await settled(page);
}

/** Procesar (E7): el inicio en processMode, y la entrada de la suricata ya hecha (las
 *  particulas, el monticulo y la cabeza, unos 2,6 s): solo la cabeza espera. */
export async function processLanded(page: Page): Promise<void> {
  await expect(app(page)).toHaveClass(/\bprocess-mode\b/);
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await expect(page.locator('.processing-workspace')).toBeVisible();
  // Despues de la entrada (las particulas, el monticulo, "Entrada · asomando la cabeza"), la
  // linea del motor empieza por "Etapa".
  await expect.poll(() => engineState(page), { timeout: 15_000 }).toMatch(/^Etapa \d\/5 · (?!partículas|montículo)/);
  await settled(page);
}

/** El estado del motor de la suricata (su linea de depuracion, oculta: etapa, accion, pila). */
export async function engineState(page: Page): Promise<string> {
  // Sin esperas: sin la escena (antes de montarse o despues del fundido), una linea vacia.
  return page.evaluate(() => document.querySelector('.zur-debug output')?.textContent ?? '');
}

/** El titulo del panel (su h2: la entrada en reposo, el grupo en su vista). */
export const panelTitle = (page: Page) => panel(page).getByRole('heading', { level: 2 });

/** Abre la vista de un grupo: su fila del panel en reposo (el titulo pasa a ser el del grupo). */
export async function openGroup(page: Page, label: string, title: string = label): Promise<void> {
  await panelRow(page, label).click();
  await expect(panelTitle(page)).toHaveText(title);
  await settled(page);
}

/** «Volver a …» al final de la vista abierta (vuelve al reposo o a la vista de antes). */
export async function backFromGroup(page: Page, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  const prefix = fill(TEXTS[lang].aurora.panel.backTo, { what: '' }).trim();
  const before = await panelTitle(page).textContent();
  await panel(page).getByRole('button', { name: new RegExp(`^${escapeRegExp(prefix)}`) }).click();
  await expect(panelTitle(page)).not.toHaveText(before ?? '');
  await settled(page);
}

/** Abre la tarjeta .detail de una fila (por su titulo o la fila misma) y la devuelve. */
export async function openCard(page: Page, row: string | RegExp | Locator): Promise<Locator> {
  const target = typeof row === 'string' || row instanceof RegExp ? panelRow(page, row).first() : row;
  await target.click();
  const card = detail(page);
  await expect(card).toBeVisible();
  await settled(page);
  return card;
}

/** La ✕ del panel: vuelve a la rueda (E1). */
export async function closePanel(page: Page, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await panel(page).getByRole('button', { name: TEXTS[lang].aurora.panel.close }).click();
  await expect(panel(page)).toHaveCount(0);
  await expect(wheel(page)).toBeVisible();
}

/** El numero de una fila de grupo del panel (su doc-end) o, sin fila, el de la vista abierta
 *  (.list-title). 0 si no esta (un grupo vacio no sale). */
export async function readCount(page: Page, label?: string): Promise<number> {
  const figure = label ? panelRow(page, label).locator('.doc-end strong') : panel(page).locator('.list-title span');
  if (!(await figure.count())) return 0;
  const m = /(\d+)/.exec((await figure.first().textContent()) ?? '');
  return m ? Number(m[1]) : 0;
}

/** Escribe en la caja del inicio e Intro (escribir no es un clic) y espera la respuesta. */
export async function ask(page: Page, text: string, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  const box = page.getByRole('textbox', { name: TEXTS[lang].aurora.composer.askLabel });
  await box.fill(text);
  await box.press('Enter');
  await expect(page.locator('.conversation')).toBeVisible();
  await expect(page.locator('.typing-dots')).toHaveCount(0, { timeout: 15_000 });
}

/** Una fila de la respuesta de la conversacion cuyo nombre (strong) es `label`. */
export function answerRow(page: Page, label: string | RegExp): Locator {
  const strong = typeof label === 'string' ? page.locator('.result-info strong').getByText(label, { exact: true }) : page.locator('.result-info strong', { hasText: label });
  return page.locator('.conversation .chat-rows a.search-result').filter({ has: strong });
}

/**
 * Abre la hoja de una factura como una persona: su numero en la caja del inicio, la fila de la
 * respuesta (la `nth`, si hay dos con el mismo numero) y el vuelo a su carpeta en Documentos.
 * Devuelve el <dialog> de la hoja, ya cargado.
 */
export async function openInvoice(page: Page, number: string, options: { lang?: Lang; nth?: number } = {}): Promise<Locator> {
  const lang = options.lang ?? (await pageLang(page));
  await toHome(page);
  await ask(page, number, lang);
  await answerRow(page, number).nth(options.nth ?? 0).click();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await landed(page);
  const sheet = sheetDialog(page);
  await expect(sheet.getByRole('heading', { level: 2 })).toHaveText(number);
  await expect(sheet.locator('.ws-file-table')).toBeVisible();
  await settled(page);
  return sheet;
}

/** Una fila de la tabla de la hoja abierta ("Lo que se puede hacer") por su titulo. */
export function invoiceRow(page: Page, title: string | RegExp): Locator {
  const strong = typeof title === 'string' ? page.locator('strong').getByText(title, { exact: true }) : page.locator('strong', { hasText: title });
  return sheetDialog(page).locator('.ws-file-table > a').filter({ has: strong });
}

/** El control de plegar de la hoja abierta (con mas de cuatro filas): "En nog N regels". */
export const sheetFold = (page: Page) => sheetDialog(page).getByTestId('sheet-fold').getByRole('button');

/** Despliega la hoja abierta como una persona (su control), si esta plegada; si no, nada. */
export async function unfold(page: Page): Promise<void> {
  const fold = sheetFold(page);
  if ((await fold.count()) === 0 || (await fold.getAttribute('aria-expanded')) === 'true') return;
  await fold.click();
  await expect(fold).toHaveAttribute('aria-expanded', 'true');
}

/** Abre la tarjeta de una fila de la hoja y la devuelve (despliega la hoja si la fila esta
 *  plegada: asi tambien lo de despues ve todas las filas). */
export async function openSheetRow(page: Page, title: string | RegExp): Promise<Locator> {
  if ((await invoiceRow(page, title).count()) === 0) await unfold(page);
  const row = invoiceRow(page, title).first();
  // La fila de la tarjeta abierta la cerraria: si ya esta abierta, se queda.
  if ((await row.getAttribute('aria-current')) !== 'true') await row.click();
  const card = sheetDialog(page).locator('.detail');
  await expect(card).toBeVisible();
  await settled(page);
  return card;
}

/** Cierra la hoja (su ✕): queda la carpeta abierta. */
export async function closeSheet(page: Page, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await sheetDialog(page).getByRole('button', { name: TEXTS[lang].aurora.archive.closePreview }).click();
  await expect(sheetDialog(page)).toHaveCount(0);
}

/**
 * Una orden de una tarjeta: su boton (.primary o .outline), su formulario y, al final, el "si"
 * (.chat-export). `values` va campo a campo por su etiqueta (un desplegable, por su opcion).
 */
export async function giveOrder(
  page: Page,
  card: Locator,
  label: string,
  values: Record<string, string> = {},
  options: { confirm?: boolean } = {}
): Promise<void> {
  await card.getByRole('button', { name: label, exact: true }).first().click();
  await fillOrder(page, card, values);
  if (options.confirm === false) return;
  await card.locator('.order-form').getByRole('button', { name: label, exact: true }).click();
  await card.locator('.chat-export').getByRole('button', { name: label, exact: true }).click();
}

/** Rellena los campos de la orden abierta en una tarjeta. */
export async function fillOrder(page: Page, card: Locator, values: Record<string, string>): Promise<void> {
  for (const [field, value] of Object.entries(values)) {
    const combo = card.getByRole('combobox', { name: new RegExp(`^${escapeRegExp(field)}`) });
    if (await combo.count()) {
      await combo.first().click();
      await page.getByRole('option', { name: value }).first().click();
      continue;
    }
    await card.getByLabel(field).first().fill(value);
  }
}

/** Elige una fecha en un campo de fecha de una orden (el calendario de la busqueda de Aurora):
 *  avanza los meses que hagan falta y pulsa el dia; null lo vacia. */
export async function pickDate(page: Page, scope: Locator, label: string, date: Date | null, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  const s = TEXTS[lang].aurora.search;
  await scope.getByRole('button', { name: new RegExp(`^${escapeRegExp(label)}`) }).click();
  const popover = page.locator('.calendar-popover');
  await expect(popover).toBeVisible();
  if (date === null) {
    await popover.getByRole('button', { name: s.dateClear }).click();
  } else {
    const locale = { nl: 'nl-NL', en: 'en-GB', es: 'es-ES' }[lang];
    const name = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
    for (let i = 0; i < 24 && !(await popover.getByRole('button', { name, exact: true }).count()); i += 1) {
      await popover.getByRole('button', { name: s.nextMonth }).click();
    }
    await popover.getByRole('button', { name, exact: true }).click();
  }
  await expect(popover).toHaveCount(0);
}

/** Las migas despues de "Inicio" (lo que dicen, en orden). */
export async function crumbs(page: Page, language?: Lang): Promise<string[]> {
  const lang = language ?? (await pageLang(page));
  const nav = crumbsNav(page, lang);
  const all = (await nav.locator('a, span[aria-current], li').allTextContents()).map((s) => s.trim()).filter(Boolean);
  // Las migas de Documentos son anclas sueltas; las del marco de Procesar, una lista.
  const items = (await nav.getByRole('listitem').count()) ? (await nav.getByRole('listitem').allTextContents()).map((s) => s.trim()) : all;
  expect(items[0]).toBe(TEXTS[lang].aurora.work.home);
  return items.slice(1);
}

/** Abre Ajustes y una de sus filas (Idioma, Tema, Tu cuenta, Sistema). */
export async function openSettingsRow(page: Page, row: 'language' | 'theme' | 'account' | 'system', language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await openEntry(page, 'settings', lang);
  const s = TEXTS[lang].aurora.settings;
  await panelRow(page, { language: s.language, theme: s.theme, account: s.account, system: s.system }[row]).click();
  await settled(page);
}

/** Ajustes (E2-A): el idioma, el tema o salir. */
export async function settings(page: Page, option: { lang: Lang } | { theme: ThemeChoice } | 'signOut', language?: Lang): Promise<void> {
  if (option === 'signOut') return signOut(page, language);
  if ('lang' in option) return setLang(page, option.lang);
  return chooseTheme(page, option.theme, language);
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

/** Elige el tema en Ajustes > Tema (Donker / Licht / Volg Windows) y espera a que se vea. */
export async function chooseTheme(page: Page, choice: ThemeChoice, language?: Lang): Promise<void> {
  const lang = language ?? (await pageLang(page));
  await openSettingsRow(page, 'theme', lang);
  await panelRow(page, TEXTS[lang].theme[choice]).click();
  if (choice !== 'system') await expect(page.locator('html')).toHaveAttribute('data-theme', choice);
  await settled(page);
}

// ------------------------------------------------------------------ Documentos

/** Documentos desde la rueda (con el vuelo): la rejilla de todas las carpetas. */
export async function openDocuments(page: Page, language?: Lang): Promise<void> {
  await openEntry(page, 'documents', language);
  await expect(page.locator('.ws-grid')).toBeVisible();
}

/** Una carpeta de la rejilla por el nombre de su empresa. */
export function folderCell(page: Page, name: string): Locator {
  return page.getByTestId('folder-cell').filter({ has: page.locator('.gf-title').getByText(name, { exact: true }) });
}

/** Un nodo del arbol "Explorar" por lo que dice. */
export function treeItem(page: Page, label: string | RegExp): Locator {
  const text = typeof label === 'string' ? page.locator('.tree-label').getByText(label, { exact: true }) : page.locator('.tree-label', { hasText: label });
  return page.getByRole('treeitem').filter({ has: text });
}

/** Abre la carpeta de una empresa desde el arbol (esta o no entre las doce de la rejilla). */
export async function openFolder(page: Page, name: string, side: 'client' | 'provider', language?: Lang): Promise<Locator> {
  const lang = language ?? (await pageLang(page));
  const t = TEXTS[lang];
  const group = treeItem(page, side === 'client' ? t.documents.clients : t.documents.providers).first();
  if ((await group.getAttribute('aria-expanded')) !== 'true') await group.click();
  const node = treeItem(page, name).first();
  await node.click();
  const profile = page.getByRole('region', { name: fill(t.aurora.archive.profileOf, { name }), exact: true });
  await expect(profile).toBeVisible();
  await settled(page);
  return profile;
}

/** La ficha de la carpeta abierta (ws-profile). */
export function folderProfile(page: Page, name: string, lang: Lang = 'nl'): Locator {
  return page.getByRole('region', { name: fill(TEXTS[lang].aurora.archive.profileOf, { name }), exact: true });
}

/** Una fila de la tabla de la ficha (un documento, un Object, una PO) por su titulo. */
export function profileRow(page: Page, title: string | RegExp): Locator {
  const strong = typeof title === 'string' ? page.locator('strong').getByText(title, { exact: true }) : page.locator('strong', { hasText: title });
  return page.locator('.ws-profile .ws-file-table > a').filter({ has: strong });
}

// ------------------------------------------------------------------ La gira

/** Cada sitio de la app: cada panel en reposo y cada vista de grupo, la busqueda, Documentos y
 *  Procesar. */
export async function tourAll(page: Page, lang: Lang, visit: (what: string) => Promise<void>) {
  const tx = TEXTS[lang];
  const groups: Record<'home' | 'receivables' | 'payables' | 'vat', string[]> = {
    home: [tx.aurora.home.first, tx.nav['work-queue'].label, tx.nav.exceptions.label, tx.aurora.home.iban, tx.nav['cash-flow'].label],
    receivables: [tx.aurora.money.proposals, tx.aurora.money.unmatched, tx.money.ageing.title],
    payables: [tx.aurora.money.proposals, tx.aurora.money.unmatched, tx.aurora.money.week, tx.money.week.held, tx.money.ageing.title],
    vat: [tx.aurora.vat.older],
  };
  await openEntry(page, 'settings', lang);
  await visit('settings');
  for (const [entry, labels] of Object.entries(groups) as [keyof typeof groups, string[]][]) {
    await openEntry(page, entry, lang);
    await visit(entry);
    for (const label of labels) {
      if (!(await panelRow(page, label).count())) continue;
      await openGroup(page, label);
      await visit(`${entry}-${label}`);
      await page.keyboard.press('Escape');
    }
  }
  await openEntry(page, 'search', lang);
  await visit('search');
  await openDocuments(page, lang);
  await visit('documents');
  await openEntry(page, 'process', lang);
  await visit('process');
}

/** Las ocho entradas, para recorrerlas. */
export { ENTRIES };
