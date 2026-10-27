import { describe, expect, it } from 'vitest';
import type { InvoiceRow } from '@/lib/api';
import { FIRST, REFRESH_MS, firstName, urgentFirst } from './home';

const row = (id: number, nivel: string, extra: Partial<InvoiceRow> = {}): InvoiceRow =>
  ({ id, numero: `F-${id}`, sentido: 'entrante', nivel, cuenta: true, razones: [{ id, regla: 'X1' }], ...extra }) as unknown as InvoiceRow;

describe('el inicio', () => {
  it('"Lo primero" solo con lo bloqueado o urgente (y como mucho cinco)', () => {
    const rows = [row(1, 'bloqueada'), row(2, 'atencion'), row(3, 'urgente'), row(4, 'normal')];
    expect(urgentFirst(rows).map((r) => r.id)).toEqual([1, 3]);
    expect(urgentFirst([row(5, 'atencion')])).toEqual([]);
    expect(FIRST).toBe(5);
  });

  it('se vuelve a leer cada minuto', () => {
    expect(REFRESH_MS).toBe(60_000);
  });

  it('el saludo con el nombre de pila', () => {
    expect(firstName('Ana Demo')).toBe('Ana');
    expect(firstName('  Bram  ')).toBe('Bram');
    expect(firstName('J. Voorbeeld')).toBe('J. Voorbeeld');
  });
});
