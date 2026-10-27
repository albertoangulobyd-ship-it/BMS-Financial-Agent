import { describe, expect, it } from 'vitest';
import * as storage from './storage';
import {
  DEVICE_LANG_KEY,
  DEVICE_THEME_KEY,
  forgetSavedTabs,
  loadLang,
  loadTheme,
  personKey,
  saveLang,
  saveTheme,
  type KeyValueStore,
} from './storage';
import { DEFAULT_THEME, resolveTheme } from './theme-choice';

class MemoryStore implements KeyValueStore {
  data = new Map<string, string>();
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
}

class BrokenStore implements KeyValueStore {
  getItem(): string | null {
    throw new Error('SecurityError');
  }
  setItem(): void {
    throw new Error('QuotaExceededError');
  }
}

describe('las claves', () => {
  it('llevan el entorno y la persona: lo de la base de prueba no se mezcla con la real', () => {
    expect(personKey('demo', 1, 'lang')).toBe('bms-app:v1:demo:1:lang');
    expect(personKey('real', 1, 'lang')).not.toBe(personKey('demo', 1, 'lang'));
    expect(personKey('real', 2, 'lang')).toBe('bms-app:v1:real:2:lang');
    expect(personKey('demo', 3, 'theme')).toBe('bms-app:v1:demo:3:theme');
    expect(() => personKey('real', 0, 'lang')).toThrow();
  });
});

describe('el idioma', () => {
  it('se guarda y se lee; lo que no es nl, en o es no vale', () => {
    const store = new MemoryStore();
    saveLang(DEVICE_LANG_KEY, 'en', store);
    expect(loadLang(DEVICE_LANG_KEY, store)).toBe('en');
    saveLang(DEVICE_LANG_KEY, 'es', store);
    expect(loadLang(DEVICE_LANG_KEY, store)).toBe('es');
    for (const other of ['fr', 'ES', ' nl', '']) {
      store.setItem(DEVICE_LANG_KEY, other);
      expect(loadLang(DEVICE_LANG_KEY, store)).toBeNull();
    }
  });

  it('sin localStorage (o con uno que tira) la app sigue', () => {
    expect(loadLang(DEVICE_LANG_KEY, new BrokenStore())).toBeNull();
    expect(() => saveLang(DEVICE_LANG_KEY, 'nl', new BrokenStore())).not.toThrow();
    expect(loadLang(DEVICE_LANG_KEY, null)).toBeNull();
  });
});

describe('el tema', () => {
  it('se guarda y se lee; solo oscuro, claro o seguir a Windows', () => {
    const store = new MemoryStore();
    expect(loadTheme(DEVICE_THEME_KEY, store)).toBeNull();
    for (const theme of ['dark', 'light', 'system'] as const) {
      saveTheme(DEVICE_THEME_KEY, theme, store);
      expect(loadTheme(DEVICE_THEME_KEY, store)).toBe(theme);
    }
    for (const other of ['auto', 'Dark', '{"x":1}', '']) {
      store.setItem(DEVICE_THEME_KEY, other);
      expect(loadTheme(DEVICE_THEME_KEY, store)).toBeNull();
    }
    expect(loadTheme(DEVICE_THEME_KEY, new BrokenStore())).toBeNull();
    expect(() => saveTheme(DEVICE_THEME_KEY, 'light', new BrokenStore())).not.toThrow();
  });

  it('por defecto el oscuro de Aurora; seguir a Windows resuelve con el del sistema', () => {
    expect(DEFAULT_THEME).toBe('dark');
    expect(resolveTheme('dark', false)).toBe('dark');
    expect(resolveTheme('light', true)).toBe('light');
    expect(resolveTheme('system', true)).toBe('dark');
    expect(resolveTheme('system', false)).toBe('light');
  });
});

describe('lo que ya no se guarda', () => {
  it('desde el paso 16 no hay pestanas que guardar: la app empieza siempre en el inicio', () => {
    expect(Object.keys(storage).filter((k) => /^(load|save).*tab/i.test(k))).toEqual([]);
  });
});

describe('las pestanas del paso 15', () => {
  it('se borran al entrar, solo las de esa persona y ese entorno', () => {
    const store = new MemoryStore();
    store.setItem('bms-app:v1:demo:1:tabs', '{"tabs":[{"screen":"overview"}]}');
    store.setItem('bms-app:v1:real:1:tabs', '{"tabs":[]}');
    store.setItem('bms-app:v1:demo:1:lang', 'es');
    forgetSavedTabs('demo', 1, store);
    expect(store.getItem('bms-app:v1:demo:1:tabs')).toBeNull();
    expect(store.getItem('bms-app:v1:real:1:tabs')).not.toBeNull();
    expect(store.getItem('bms-app:v1:demo:1:lang')).toBe('es');
  });

  it('sin poder borrar, la app sigue igual', () => {
    expect(() => forgetSavedTabs('demo', 1, new BrokenStore())).not.toThrow();
    const throwing = { getItem: () => null, setItem: () => undefined, removeItem: () => { throw new Error('SecurityError'); } };
    expect(() => forgetSavedTabs('demo', 1, throwing)).not.toThrow();
    expect(() => forgetSavedTabs('demo', 1, null)).not.toThrow();
  });
});
