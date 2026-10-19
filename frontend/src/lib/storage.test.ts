import { describe, expect, it } from 'vitest';
import { isValidRoute } from '@/screens/registry';
import {
  DEVICE_LANG_KEY,
  cleanRoute,
  loadLang,
  loadTabs,
  parseTabsState,
  personKey,
  saveLang,
  saveTabs,
  type KeyValueStore,
} from './storage';

class MemoryStore implements KeyValueStore {
  data = new Map<string, string>();
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
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
  it('llevan el entorno y la persona: la base de prueba nunca abre una ficha de la real', () => {
    expect(personKey('demo', 1, 'tabs')).toBe('bms-app:v1:demo:1:tabs');
    expect(personKey('real', 1, 'tabs')).not.toBe(personKey('demo', 1, 'tabs'));
    expect(personKey('real', 2, 'lang')).toBe('bms-app:v1:real:2:lang');
    expect(() => personKey('real', 0, 'lang')).toThrow();
  });
});

describe('el idioma', () => {
  it('se guarda y se lee; lo que no es nl o en no vale', () => {
    const store = new MemoryStore();
    saveLang(DEVICE_LANG_KEY, 'en', store);
    expect(loadLang(DEVICE_LANG_KEY, store)).toBe('en');
    store.setItem(DEVICE_LANG_KEY, 'es');
    expect(loadLang(DEVICE_LANG_KEY, store)).toBeNull();
  });

  it('sin localStorage (o con uno que tira) la app sigue', () => {
    expect(loadLang(DEVICE_LANG_KEY, new BrokenStore())).toBeNull();
    expect(() => saveLang(DEVICE_LANG_KEY, 'nl', new BrokenStore())).not.toThrow();
    expect(loadLang(DEVICE_LANG_KEY, null)).toBeNull();
  });
});

describe('las pestanas guardadas', () => {
  const key = personKey('demo', 1, 'tabs');

  it('vuelven tal cual si son validas', () => {
    const store = new MemoryStore();
    const state = {
      tabs: [
        { id: 'tab-1', route: { screen: 'overview' } },
        { id: 'tab-2-1760000000000', route: { screen: 'invoice', id: 12, from: 'work-queue' } },
      ],
      activeTabId: 'tab-2-1760000000000',
      collapsed: true,
    };
    saveTabs(key, state, store);
    expect(loadTabs(key, isValidRoute, store)).toEqual(state);
  });

  it('solo guardan ids y numeros: nunca un titulo ni otra cosa', () => {
    const store = new MemoryStore();
    saveTabs(
      key,
      {
        tabs: [{ id: 'tab-1', route: { screen: 'invoice', id: 3 }, title: 'Van Dijk <script>' } as never],
        activeTabId: 'tab-1',
        collapsed: false,
      },
      store
    );
    const raw = store.getItem(key)!;
    expect(raw).not.toContain('Van Dijk');
    expect(JSON.parse(raw)).toEqual({ tabs: [{ id: 'tab-1', route: { screen: 'invoice', id: 3 } }], activeTabId: 'tab-1', collapsed: false });
  });

  it('descartan lo que no se reconoce', () => {
    const raw = JSON.stringify({
      tabs: [
        { id: 'tab-1', route: { screen: 'overview' } },
        { id: 'tab-1', route: { screen: 'clients' } }, // id repetido
        { id: 'tab-3', route: { screen: 'nope' } }, // pantalla que no existe
        { id: 'tab-4', route: { screen: 'invoice' } }, // ficha sin id
        { id: 'tab-5', route: { screen: 'invoice', id: -1 } },
        { id: 'tab-6', route: { screen: 'invoice', id: 1.5 } },
        { id: 'tab-7', route: { screen: 'invoice', id: '12' } },
        { id: 'tab-8', route: { screen: 'overview', id: 2 } }, // una entrada no lleva id
        { id: 'tab-9', route: { screen: 'invoice', id: 2, from: 'javascript' } },
        { id: '<img>', route: { screen: 'overview' } },
        { id: 'tab-10', route: { screen: 'invoice', id: 7, title: 'x' } },
      ],
      activeTabId: 'tab-3',
      collapsed: 'yes',
    });
    expect(parseTabsState(raw, isValidRoute)).toEqual({
      tabs: [
        { id: 'tab-1', route: { screen: 'overview' } },
        { id: 'tab-10', route: { screen: 'invoice', id: 7 } },
      ],
      activeTabId: 'tab-1',
      collapsed: false,
    });
  });

  it('nada o basura es null (la app abre la de siempre)', () => {
    for (const raw of [null, '', '{', '[]', '{"tabs":[]}', '{"tabs":{}}', 'x'.repeat(30000)]) {
      expect(parseTabsState(raw, isValidRoute)).toBeNull();
    }
    expect(loadTabs(key, isValidRoute, new BrokenStore())).toBeNull();
  });

  it('una ruta solo lleva pantalla, id y origen', () => {
    expect(cleanRoute({ screen: 'invoice', id: 4, from: 'invoices-in', extra: 1 })).toEqual({
      screen: 'invoice',
      id: 4,
      from: 'invoices-in',
    });
    expect(cleanRoute({ screen: 'Invoice' })).toBeNull();
    expect(cleanRoute('overview')).toBeNull();
  });
});
