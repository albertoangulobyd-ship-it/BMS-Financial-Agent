// Lo unico que la app guarda en el navegador: comodidades de cada persona (el idioma, si
// la barra lateral va plegada y que pestanas tenia abiertas, con ids de pantalla e ids
// numericos). Nunca el token ni un dato de la API. La clave lleva el entorno (demo o
// real) y el id de la persona: un id de la base de prueba nunca abre una ficha en la de
// verdad, ni las pestanas de una persona aparecen a otra en el mismo ordenador.
//
// localStorage puede no estar (ventana privada, politica de Windows) o tirar al
// escribir: todo va en try/catch, y lo que se lee se comprueba campo a campo.
import type { SavedTabsState, TabRoute } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { isLang, type Lang } from '@/i18n';
import type { Environment } from './api';

export const STORAGE_PREFIX = 'bms-app:v1';
const MAX_TABS = 30;

/** Lo minimo de Storage que se usa (asi los tests pasan uno falso). */
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function browserStore(): KeyValueStore | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

function read(store: KeyValueStore | null, key: string): string | null {
  if (!store) return null;
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

function write(store: KeyValueStore | null, key: string, value: string): void {
  if (!store) return;
  try {
    store.setItem(key, value);
  } catch {
    // Lleno o prohibido: la comodidad se pierde, la app sigue igual.
  }
}

/** La clave de una preferencia de una persona en un entorno. */
export function personKey(environment: Environment, userId: number, what: 'lang' | 'tabs'): string {
  if (!Number.isSafeInteger(userId) || userId <= 0) throw new Error('user id');
  return `${STORAGE_PREFIX}:${environment}:${userId}:${what}`;
}

/** El idioma del ultimo uso en este ordenador: el de la pantalla de entrada. */
export const DEVICE_LANG_KEY = `${STORAGE_PREFIX}:lang`;

export function loadLang(key: string, store: KeyValueStore | null = browserStore()): Lang | null {
  const value = read(store, key);
  return isLang(value) ? value : null;
}

export function saveLang(key: string, lang: Lang, store: KeyValueStore | null = browserStore()): void {
  write(store, key, lang);
}

const TAB_ID = /^tab-\d{1,6}(-\d{1,16})?$/;

/**
 * Lo guardado de las pestanas, comprobado: cada pestana con un id con su forma, una ruta que
 * la app conoce (isValidRoute) y nada mas. Lo que no cumple se descarta; si no queda
 * ninguna, null (la app abre la de siempre).
 */
export function parseTabsState(
  raw: string | null,
  isValidRoute: (route: TabRoute) => boolean
): SavedTabsState | null {
  if (!raw || raw.length > 20000) return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!data || typeof data !== 'object') return null;
  const record = data as Record<string, unknown>;
  if (!Array.isArray(record.tabs)) return null;
  const seen = new Set<string>();
  const tabs: SavedTabsState['tabs'] = [];
  for (const item of record.tabs.slice(0, MAX_TABS)) {
    if (!item || typeof item !== 'object') continue;
    const { id, route } = item as Record<string, unknown>;
    if (typeof id !== 'string' || !TAB_ID.test(id) || seen.has(id)) continue;
    const clean = cleanRoute(route);
    if (!clean || !isValidRoute(clean)) continue;
    seen.add(id);
    tabs.push({ id, route: clean });
  }
  if (tabs.length === 0) return null;
  const active = typeof record.activeTabId === 'string' && seen.has(record.activeTabId)
    ? record.activeTabId
    : tabs[0]!.id;
  return { tabs, activeTabId: active, collapsed: record.collapsed === true };
}

/** Una ruta con solo lo que puede llevar: pantalla (texto corto), id numerico y origen. */
export function cleanRoute(route: unknown): TabRoute | null {
  if (!route || typeof route !== 'object') return null;
  const { screen, id, from } = route as Record<string, unknown>;
  if (typeof screen !== 'string' || !/^[a-z][a-z-]{0,39}$/.test(screen)) return null;
  const clean: TabRoute = { screen };
  if (id !== undefined) {
    if (typeof id !== 'number' || !Number.isSafeInteger(id) || id <= 0) return null;
    clean.id = id;
  }
  if (from !== undefined) {
    if (typeof from !== 'string' || !/^[a-z][a-z-]{0,39}$/.test(from)) return null;
    clean.from = from;
  }
  return clean;
}

export function loadTabs(
  key: string,
  isValidRoute: (route: TabRoute) => boolean,
  store: KeyValueStore | null = browserStore()
): SavedTabsState | null {
  return parseTabsState(read(store, key), isValidRoute);
}

export function saveTabs(key: string, state: SavedTabsState, store: KeyValueStore | null = browserStore()): void {
  // Se vuelve a limpiar al guardar: lo que se escribe es solo ids y numeros.
  const tabs = state.tabs
    .map((t) => ({ id: t.id, route: cleanRoute(t.route) }))
    .filter((t): t is { id: string; route: TabRoute } => t.route !== null && TAB_ID.test(t.id))
    .slice(0, MAX_TABS);
  write(store, key, JSON.stringify({ tabs, activeTabId: state.activeTabId, collapsed: state.collapsed }));
}
