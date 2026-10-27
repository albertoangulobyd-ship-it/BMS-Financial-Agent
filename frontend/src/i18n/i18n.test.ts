import { describe, expect, it } from 'vitest';
import { LANGS, MESSAGES, fmt, isLang, type Lang } from './index';
import { DOMAIN_FALLBACK, catalogFor } from './domain';
import { leftoversIn, sharedWords } from './leftovers';

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
const dictionaries = Object.fromEntries(LANGS.map((lang) => [lang, leaves(MESSAGES[lang] as unknown as Tree)])) as Record<
  Lang,
  Map<string, string | string[]>
>;

describe('los textos de la app', () => {
  it('tienen las mismas claves en los tres idiomas', () => {
    const nl = [...dictionaries.nl.keys()].sort();
    for (const lang of LANGS) expect([...dictionaries[lang].keys()].sort(), lang).toEqual(nl);
  });

  it('tienen los mismos huecos en los tres idiomas', () => {
    for (const [key, value] of dictionaries.nl) {
      for (const lang of LANGS) {
        const other = dictionaries[lang].get(key)!;
        if (typeof value === 'string') expect(holes(other as string), `${lang}:${key}`).toEqual(holes(value));
        else expect((other as string[]).length, `${lang}:${key}`).toBe(value.length);
      }
    }
  });

  it('no dejan ningun texto vacio salvo los que son a proposito', () => {
    const allowedEmpty = /^(groups\.settings|nav\.[a-z-]+\.hint)$/;
    for (const lang of LANGS) {
      for (const [key, value] of dictionaries[lang]) {
        if (typeof value === 'string' && value.trim() === '') {
          expect(allowedEmpty.test(key), `${lang}:${key}`).toBe(true);
        }
      }
    }
  });

  it('no llevan restos de otro idioma: cada uno libre de las palabras de los otros dos', () => {
    expect(sharedWords(), 'una palabra en dos listas').toEqual([]);
    const found: string[] = [];
    for (const lang of LANGS) {
      for (const [key, value] of dictionaries[lang]) {
        for (const text of Array.isArray(value) ? value : [value]) {
          const words = leftoversIn(text, lang);
          if (words.length) found.push(`${lang}:${key} ${words.join(',')}: ${text}`);
        }
      }
    }
    expect(found).toEqual([]);
  });

  it('el castellano esta traducido: ninguna frase igual que en ingles o en neerlandes', () => {
    // Iguales a proposito: nombres propios, siglas y codigos (y las palabras del oficio que
    // BMS usa tal cual: Object, IBAN, BTW).
    const same = /^(app\.|language\.(nl|en|es)(Long)?$|units\.|records\.object\.|lines\.object$|planning\.object$|objects\.(object|sectionPos)$|pos\.sectionObjects$|parties\.(iban|no)$|nav\.(objects|vat)\.|help\.object\.term$|vat\.(title|vat)$|overview\.open\.vat$|common\.twin$|parties\.total$|overview\.vat\.caption$|months\.(short|long)\.)/;
    const untranslated: string[] = [];
    for (const [key, value] of dictionaries.es) {
      if (typeof value !== 'string' || same.test(key) || !/\p{L}{3,}.*\s.*\p{L}{3,}/u.test(value)) continue;
      if (value === dictionaries.en.get(key) || value === dictionaries.nl.get(key)) untranslated.push(`${key}: ${value}`);
    }
    expect(untranslated).toEqual([]);
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
  it('neerlandes, ingles y castellano; nada mas', () => {
    expect(LANGS).toEqual(['nl', 'en', 'es']);
    expect(isLang('nl') && isLang('en') && isLang('es')).toBe(true);
    expect(isLang('fr')).toBe(false);
    expect(isLang('ES')).toBe(false);
    expect(isLang(null)).toBe(false);
  });

  it('los textos de dominio tienen las mismas claves en cada idioma', () => {
    const nl = leaves(catalogFor('nl') as unknown as Tree);
    for (const lang of LANGS) {
      expect([...leaves(catalogFor(lang) as unknown as Tree).keys()].sort(), lang).toEqual([...nl.keys()].sort());
    }
  });

  it('cada idioma tiene su propio catalogo de dominio (es.json desde el paso 16)', () => {
    expect(DOMAIN_FALLBACK).toEqual({});
    expect(catalogFor('es')).not.toBe(catalogFor('en'));
    expect(catalogFor('es').idioma).toBe('es');
    expect(catalogFor('en').idioma).toBe('en');
    expect(catalogFor('nl').idioma).toBe('nl');
    expect(DOMAIN_FALLBACK.nl).toBeUndefined();
    expect(DOMAIN_FALLBACK.en).toBeUndefined();
  });
});
