// Las cuatro semanas del flujo de caja (panel Inicio, especificacion §2.2.1).
import { describe, expect, it } from 'vitest';
import { isoWeek, weekRanges } from './weeks';

describe('las semanas del flujo de caja', () => {
  it('la semana ISO es la de su jueves (el 1 de enero puede ser de la 53 o de la 1)', () => {
    expect(isoWeek('2026-10-28')).toBe(44);
    expect(isoWeek('2026-01-01')).toBe(1);
    expect(isoWeek('2021-01-03')).toBe(53);
    expect(isoWeek('2024-12-30')).toBe(1);
  });

  it('la primera empieza hoy y acaba el domingo; las otras, de lunes a domingo', () => {
    expect(weekRanges('2026-10-28')).toEqual([
      { number: 44, from: '2026-10-28', to: '2026-11-01' },
      { number: 45, from: '2026-11-02', to: '2026-11-08' },
      { number: 46, from: '2026-11-09', to: '2026-11-15' },
      { number: 47, from: '2026-11-16', to: '2026-11-22' },
    ]);
    // Un domingo: su semana es solo ese dia.
    expect(weekRanges('2026-11-01', 2)).toEqual([
      { number: 44, from: '2026-11-01', to: '2026-11-01' },
      { number: 45, from: '2026-11-02', to: '2026-11-08' },
    ]);
  });
});
