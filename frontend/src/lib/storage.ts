// Lo unico que la app guarda en el navegador: comodidades de cada persona (el idioma y el
// tema). Nunca el token ni un dato de la API. La clave lleva el entorno (demo o real) y el id
// de la persona: lo de una persona no le aparece a otra en el mismo ordenador. Desde el paso
// 16 no se guardan pestanas: la navegacion es la rueda y las seis entradas, y la app empieza
// siempre en el inicio.
//
// localStorage puede no estar (ventana privada, politica de Windows) o tirar al
// escribir: todo va en try/catch, y lo que se lee se comprueba campo a campo.
import { isLang, type Lang } from '@/i18n';
import type { Environment } from './api';
import { isThemeChoice, type ThemeChoice } from './theme-choice';

export const STORAGE_PREFIX = 'bms-app:v1';

/** Lo minimo de Storage que se usa (asi los tests pasan uno falso). */
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem?(key: string): void;
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
export function personKey(environment: Environment, userId: number, what: 'lang' | 'theme'): string {
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

/** El tema del ultimo uso en este ordenador: el de la pantalla de entrada. */
export const DEVICE_THEME_KEY = `${STORAGE_PREFIX}:theme`;

export function loadTheme(key: string, store: KeyValueStore | null = browserStore()): ThemeChoice | null {
  const value = read(store, key);
  return isThemeChoice(value) ? value : null;
}

export function saveTheme(key: string, theme: ThemeChoice, store: KeyValueStore | null = browserStore()): void {
  write(store, key, theme);
}

/**
 * Las pestanas que guardaba el paso 15 (ids de pantalla, ids numericos y si la barra iba
 * plegada) ya no se usan: al entrar se borran, para no dejar nada que no sirva.
 */
export function forgetSavedTabs(environment: Environment, userId: number, store: KeyValueStore | null = browserStore()): void {
  if (!store?.removeItem || !Number.isSafeInteger(userId) || userId <= 0) return;
  try {
    store.removeItem(`${STORAGE_PREFIX}:${environment}:${userId}:tabs`);
  } catch {
    // Prohibido: no pasa nada, nadie lo lee.
  }
}
