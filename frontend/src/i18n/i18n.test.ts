import { describe, expect, it } from 'vitest';
import { MESSAGES, fmt, isLang } from './index';
import { catalogFor } from './domain';

type Tree = { [key: string]: Tree | string | string[] };

function leaves(tree: Tree, prefix = ''): Map<string, string | string[]> {
  const out = new Map<string, string | string[]>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string' || Array.isArray(value)) out.set(path, value);
    else for (const [k, v] of leaves(value, path)) out.set(k, v);
  }
  return out;
}

const holes = (text: string) => [...text.matchAll(/\{([a-zA-Z0-9_]+)\}/g)].map((m) => m[1]).sort();

describe('los textos de la app', () => {
  const nl = leaves(MESSAGES.nl as unknown as Tree);
  const en = leaves(MESSAGES.en as unknown as Tree);

  it('tienen las mismas claves en neerlandes y en ingles', () => {
    expect([...en.keys()].sort()).toEqual([...nl.keys()].sort());
  });

  it('tienen los mismos huecos en los dos idiomas', () => {
    for (const [key, value] of nl) {
      const other = en.get(key)!;
      if (typeof value === 'string') expect(holes(other as string), key).toEqual(holes(value));
      else expect((other as string[]).length, key).toBe(value.length);
    }
  });

  it('no dejan ningun texto vacio salvo los que son a proposito', () => {
    const allowedEmpty = /^(groups\.settings|nav\.[a-z-]+\.hint)$/;
    for (const [lang, map] of [['nl', nl], ['en', en]] as const) {
      for (const [key, value] of map) {
        if (typeof value === 'string' && value.trim() === '') {
          expect(allowedEmpty.test(key), `${lang}:${key}`).toBe(true);
        }
      }
    }
  });

  it('no llevan castellano (la interfaz es solo neerlandes e ingles)', () => {
    const spanish = /\b(factura|proveedor|cliente|pendiente|vencida|bloqueada|aviso|revisar|regla|importe|también|está|qué)\b/i;
    for (const map of [nl, en]) {
      for (const [key, value] of map) {
        for (const text of Array.isArray(value) ? value : [value]) {
          expect(spanish.test(text), `${key}: ${text}`).toBe(false);
        }
      }
    }
  });
});

describe('fmt', () => {
  it('rellena los huecos y deja a la vista los que faltan', () => {
    expect(fmt('Factuur {id}', { id: 12 })).toBe('Factuur 12');
    expect(fmt('{a} en {b}', { a: 'x' })).toBe('x en {b}');
    expect(fmt('{a}', { a: '{b}', b: 'no' })).toBe('{b}');
  });
});

describe('idiomas', () => {
  it('solo nl y en', () => {
    expect(isLang('nl') && isLang('en')).toBe(true);
    expect(isLang('es')).toBe(false);
    expect(isLang(null)).toBe(false);
  });

  it('los textos de dominio tienen las mismas claves en los dos idiomas', () => {
    const nl = leaves(catalogFor('nl') as unknown as Tree);
    const en = leaves(catalogFor('en') as unknown as Tree);
    expect([...en.keys()].sort()).toEqual([...nl.keys()].sort());
  });
});
