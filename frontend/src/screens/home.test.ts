import { describe, expect, it } from 'vitest';
import type { InvoiceRow } from '@/lib/api';
import { MESSAGES } from '@/i18n';
import { FIRST, REFRESH_MS, firstName, moneyCaption, urgentFirst } from './home';

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

  it('el pie de Te ontvangen / Te betalen con su singular (decia "bij 1 klanten")', () => {
    const { nl, en, es } = MESSAGES;
    expect(moneyCaption(nl, 'in', 2, 1)).toBe('openstaand in 2 facturen bij 1 klant');
    expect(moneyCaption(nl, 'out', 1, 3)).toBe('openstaand in 1 factuur bij 3 leveranciers');
    expect(moneyCaption(en, 'in', 2, 1)).toBe('outstanding in 2 invoices from 1 client');
    expect(moneyCaption(en, 'out', 1, 1)).toBe('outstanding in 1 invoice to 1 provider');
    expect(moneyCaption(es, 'in', 2, 1)).toBe('pendiente en 2 facturas de 1 cliente');
    expect(moneyCaption(es, 'out', 0, 0)).toBe('pendiente en 0 facturas a 0 proveedores');
  });
});
