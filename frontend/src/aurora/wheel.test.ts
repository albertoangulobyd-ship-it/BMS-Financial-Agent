import { describe, expect, it } from 'vitest';
import { wheelDistance, wheelStep } from './wheel';

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
});
