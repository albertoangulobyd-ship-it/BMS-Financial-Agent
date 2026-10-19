// Dos facturas con el mismo numero y la misma relacion se distinguen en una lista.
import { describe, expect, it } from 'vitest';
import { distinctByNumber, twinMarks } from './twins';

const row = (id: number, numero: string | null, contraparte = 'J. Voorbeeld Beveiliging (zzp)') => ({ id, numero, contraparte });

describe('facturas con el mismo numero', () => {
  it('cada una lleva su "n van m", la que llego antes primero', () => {
    const marks = twinMarks([row(9, 'JV-2026-006'), row(4, 'JV-2026-006'), row(5, 'JV-2026-007'), row(6, null), row(7, null)]);
    expect(marks.get(4)).toEqual({ n: 1, of: 2 });
    expect(marks.get(9)).toEqual({ n: 2, of: 2 });
    expect(marks.has(5)).toBe(false);
    // Sin numero no se agrupan: no son "la misma".
    expect(marks.has(6)).toBe(false);
  });

  it('el mismo numero de otra relacion no es un gemelo', () => {
    expect(twinMarks([row(1, 'F-1', 'A'), row(2, 'F-1', 'B')]).size).toBe(0);
  });

  it('"Als eerste" junta las del mismo numero: cinco filas, cinco cosas', () => {
    const rows = [row(4, 'JV-2026-006'), row(9, 'JV-2026-006'), row(5, 'KT-202608', 'Kees'), row(6, null), row(7, null)];
    expect(distinctByNumber(rows).map((e) => [e.row.id, e.count])).toEqual([
      [4, 2],
      [5, 1],
      [6, 1],
      [7, 1],
    ]);
  });
});
