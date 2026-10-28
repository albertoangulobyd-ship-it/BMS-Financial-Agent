// Las cuentas por comprobar del panel Inicio ("IBAN por verificar", especificacion §2.2.1).
import { describe, expect, it } from 'vitest';
import type { InvoiceRow } from '@/lib/api';
import type { AccountRow } from '@/lib/api-types';
import { accountStep, buildChecks, checkKey, compactIban } from './iban-model';

const invoice = (id: number, regla: string, iban: string, extra: Partial<InvoiceRow> = {}): InvoiceRow =>
  ({ id, sentido: 'entrante', proveedor_id: 2, contraparte: 'Prov', razones: [{ id, regla, estado: 'abierto', valores: { iban } }], ...extra }) as unknown as InvoiceRow;
const account = (estado: string, iban = 'NL91ABNA0417164300'): AccountRow => ({ id: 1, proveedor_id: 2, proveedor: 'Prov', iban, estado }) as unknown as AccountRow;

describe('lo que falta de una cuenta', () => {
  const f = (regla: string) => ({ reason: { regla } as never, invoice: {} as never });
  it('una sola cosa por tarjeta: llamar, ponerla en Exact, mirar lo abierto o nada', () => {
    expect(accountStep({ account: null, findings: [f('F3'), f('F2')] })).toBe('confirm');
    expect(accountStep({ account: account('registrada'), findings: [] })).toBe('confirm');
    expect(accountStep({ account: account('heredada'), findings: [f('F2')] })).toBe('confirm');
    expect(accountStep({ account: account('verificada'), findings: [f('F2')] })).toBe('exact');
    expect(accountStep({ account: account('atestada'), findings: [f('F4')] })).toBe('open');
    expect(accountStep({ account: account('rechazada'), findings: [f('F3')] })).toBe('rejected');
  });
});

describe('las cuentas por comprobar', () => {
  it('una por proveedor e IBAN (sin espacios ni minusculas), con lo visto en cada factura', () => {
    const checks = buildChecks([invoice(1, 'F3', 'nl91 abna 0417 1643 00'), invoice(2, 'F2', 'NL91ABNA0417164300'), invoice(3, 'K4', 'NL91ABNA0417164300')], [account('verificada')]);
    expect(checks).toHaveLength(1);
    expect(checks[0]!.iban).toBe('NL91ABNA0417164300');
    expect(checks[0]!.findings.map((x) => x.invoice.id)).toEqual([1, 2]);
    expect(checks[0]!.account?.estado).toBe('verificada');
    expect(checkKey(checks[0]!)).toBe('2:NL91ABNA0417164300');
  });

  it('una cuenta del registro sin verificar sale aunque ninguna factura la nombre; una aceptada, no', () => {
    const checks = buildChecks([invoice(1, 'F3', 'X', { razones: [{ id: 1, regla: 'F3', estado: 'aceptado', valores: { iban: 'X' } }] } as never)], [account('registrada', 'DE89 3704 0044 0532 0130 00')]);
    expect(checks.map((c) => c.iban)).toEqual(['DE89370400440532013000']);
    expect(compactIban(' de89 3704 ')).toBe('DE893704');
  });
});
