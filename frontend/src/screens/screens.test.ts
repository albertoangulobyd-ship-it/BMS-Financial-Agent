// Las piezas puras de las pantallas del paso 15: el periodo de un Object, el saldo y el paso
// siguiente de un trimestre, el importe que se escribe en la aangifte, el tamano y el dia de
// un fichero que se importa y el "por que" de una relacion.
import { describe, expect, it } from 'vitest';
import { MESSAGES } from '@/i18n';
import { partyWhy } from '@/lib/why';
import { fileDay, formatSize } from './import';
import { periodRange } from './object';
import { balanceText, nextStep, quarterRows } from './vat';
import { plainAmount } from './vat-quarter';
import type { VatSummary } from '@/lib/api-types';

const nl = MESSAGES.nl;

describe('el periodo de un Object', () => {
  it('el mes en curso es el de la API sin parametros; el anterior y el ano, con sus dias', () => {
    expect(periodRange('month', '2026-10-19')).toBeNull();
    expect(periodRange('lastMonth', '2026-10-19')).toEqual({ desde: '2026-09-01', hasta: '2026-09-30' });
    expect(periodRange('lastMonth', '2026-01-05')).toEqual({ desde: '2025-12-01', hasta: '2025-12-31' });
    expect(periodRange('lastMonth', '2024-03-10')).toEqual({ desde: '2024-02-01', hasta: '2024-02-29' });
    expect(periodRange('year', '2026-10-19')).toEqual({ desde: '2026-01-01', hasta: '2026-10-19' });
  });
});

describe('el btw', () => {
  it('el saldo dice si se paga o se recibe, en euros', () => {
    expect(balanceText(474386, nl)).toBe('€ 4.743,86 te betalen');
    expect(balanceText(-40970, nl)).toBe('€ 409,70 terug');
    expect(balanceText(0, nl)).toBe('niets');
  });

  it('el paso siguiente de cada estado, y nunca "aprobado"', () => {
    expect(nextStep({ estado: 'abierto', terminado: false }, nl)).toBe(nl.vat.nextRunning);
    expect(nextStep({ estado: 'abierto', terminado: true }, nl)).toBe(nl.vat.nextCheck);
    expect(nextStep({ estado: 'listo_revision', terminado: true }, nl)).toBe(nl.vat.nextFile);
    expect(nextStep({ estado: 'presentado', terminado: true }, nl)).toBe(nl.vat.nextFiled);
  });

  it('la lista: el trimestre en curso y los anteriores, sin repetir, el mas nuevo primero', () => {
    const row = (etiqueta: string, estado: string) => ({
      ano: 2026, trimestre: 1, etiqueta, estado, limite_presentacion: null, dias_para_limite: null, '5c': 1, ingresos_cent: 1,
    });
    const summary = {
      hoy: '2026-10-19',
      actual: { etiqueta: '2026-T4', estado: 'abierto', terminado: false, cifras: { '5c': -5 }, limite_presentacion: null, dias_para_limite: 104 },
      por_presentar: [row('2026-T3', 'listo_revision')],
      anteriores: [row('2026-T3', 'listo_revision'), row('2026-T2', 'presentado')],
    } as unknown as VatSummary;
    expect(quarterRows(summary).map((r) => [r.etiqueta, r.terminado])).toEqual([
      ['2026-T4', false],
      ['2026-T3', true],
      ['2026-T2', true],
    ]);
  });

  it('lo declarado se escribe con el menos del teclado, como lo lee el servidor', () => {
    expect(plainAmount(474386)).toBe('4.743,86');
    expect(plainAmount(-40970)).toBe('-409,70');
    expect(plainAmount(0)).toBe('0,00');
  });
});

describe('importar', () => {
  it('el tamano de un fichero en notacion neerlandesa', () => {
    expect(formatSize(500)).toBe('1 kB');
    expect(formatSize(320 * 1024)).toBe('320 kB');
    expect(formatSize(8 * 1024 * 1024)).toBe('8,0 MB');
    expect(formatSize(1.5 * 1024 * 1024)).toBe('1,5 MB');
  });

  it('el dia de un fichero, y hoy si dice ser del futuro', () => {
    const now = new Date('2026-10-19T10:00:00Z');
    expect(fileDay(Date.parse('2026-10-16T08:00:00Z'), now)).toBe('2026-10-16');
    expect(fileDay(Date.parse('2027-01-01T08:00:00Z'), now)).toBe('2026-10-19');
  });
});

describe('el por que de una relacion', () => {
  it('su hallazgo mas urgente, o lo vencido, o nada', () => {
    const overdue = (c: number) => `vencido ${c}`;
    const why = partyWhy(
      { razones: [{ id: 1, regla: 'B2', severidad: 'bloqueo', estado: 'abierto', resultado: 'fallo', valores: { facturas: [9, 10], numero_norm: 'JV2026006' } }] },
      'nl',
      nl,
      overdue
    );
    expect(why?.rule).toBe('B2');
    expect(why?.text).not.toMatch(/factura|número/);
    expect(partyWhy({ razones: [], vencido_cent: 734349 }, 'nl', nl, overdue)?.text).toBe('vencido 734349');
    expect(partyWhy({ razones: [], vencido_cent: 0 }, 'nl', nl, overdue)).toBeNull();
  });
});
