// Las cifras con su singular (puerta del paso 16: el inicio decia "bij 1 klanten"). En los
// diccionarios, i18n.test.ts mira que cada texto con {n} tenga su <clave>One; aqui, que la
// pantalla que lee el plural lea tambien el singular (si no, el singular no sale nunca). Los de
// `counts` se leen con countText() (i18n/index.tsx), que elige por si solo.
import { describe, expect, it } from 'vitest';
import { nl } from '../src/i18n/nl';
import { filesReading } from './codigo-muerto.mjs';

function pairs(tree, path = []) {
  return Object.entries(tree).flatMap(([key, value]) => {
    if (value && typeof value === 'object') return pairs(value, [...path, key]);
    return key.endsWith('One') && key !== 'One' && Object.hasOwn(tree, key.slice(0, -3))
      ? [[[...path, key.slice(0, -3)], [...path, key]]]
      : [];
  });
}

describe('el singular de las cifras', () => {
  it('quien lee un texto con cifra lee tambien su singular', () => {
    const missing = [];
    for (const [many, one] of pairs(nl)) {
      if (many[0] === 'counts') continue;
      const withOne = new Set(filesReading(one));
      for (const file of filesReading(many)) {
        if (!withOne.has(file)) missing.push(`${file}: ${many.join('.')} sin ${one.at(-1)}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it('las palabras de counts solo se leen con countText()', () => {
    const direct = Object.keys(nl.counts).flatMap((key) => filesReading(['counts', key]).map((file) => `${file}: counts.${key}`));
    expect(direct).toEqual([]);
  });
});
