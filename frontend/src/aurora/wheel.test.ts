import { describe, expect, it } from 'vitest';
import { wheelDistance, wheelScrollStep, wheelStep } from './wheel';
import { stackBands } from '../lib/server-bands';

describe('la rueda del inicio', () => {
  it('cada entrada se apaga segun lo lejos que esta de la activa (de 3 en adelante, igual)', () => {
    expect([0, 1, 2, 3, 4, 5].map((i) => wheelDistance(i, 0))).toEqual([0, 1, 2, 3, 3, 3]);
    expect([0, 1, 2, 3, 4, 5].map((i) => wheelDistance(i, 3))).toEqual([3, 2, 1, 0, 1, 2]);
  });

  it('un paso da la vuelta: de la ultima a la primera y al reves', () => {
    expect(wheelStep(5, 1, 6)).toBe(0);
    expect(wheelStep(0, -1, 6)).toBe(5);
    expect(wheelStep(2, 3, 6)).toBe(5);
    expect(wheelStep(1, -8, 6)).toBe(5);
  });

  it('la rueda del raton no da la vuelta: en un extremo el gesto es de la pagina', () => {
    // Revision del paso 16: bajando desde Btw volvia a Start y la pagina no bajaba nunca.
    expect(wheelScrollStep(5, 120, 6)).toBeNull();
    expect(wheelScrollStep(0, -120, 6)).toBeNull();
    expect(wheelScrollStep(0, 0, 6)).toBeNull();
    expect(wheelScrollStep(4, 120, 6)).toBe(5);
    expect(wheelScrollStep(5, -3, 6)).toBe(4);
    expect(wheelScrollStep(0, 40, 6)).toBe(1);
  });
});

describe('las bandas del servidor', () => {
  it('se apilan una debajo de otra y la cabecera va debajo de todas', () => {
    expect(stackBands([])).toEqual({ tops: [], total: 0 });
    expect(stackBands([24])).toEqual({ tops: [0], total: 24 });
    expect(stackBands([24, 41])).toEqual({ tops: [0, 24], total: 65 });
  });
});
