// Las piezas puras de las pantallas del paso 15: el periodo de un Object, el saldo y el paso
// siguiente de un trimestre, el importe que se escribe en la aangifte, el tamano y el dia de
// un fichero que se importa y el "por que" de una relacion.
import { describe, expect, it } from 'vitest';
import { MESSAGES } from '@/i18n';
import { partyWhy } from '@/lib/why';
import { fileDay, formatSize, primaryImportAction } from './import';
import { periodRange } from './object';
import { dialogTexts } from '@/components/action-dialog';
import { catalogFor } from '@/i18n/domain';
import { accountStep } from './iban-checks';
import { balanceText, nextStep, overdueQuarters, quarterRows } from './vat';
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
    expect(balanceText(474386, nl)).toBe('€\u00a04.743,86 te betalen');
    expect(balanceText(-40970, nl)).toBe('€\u00a0409,70 terug');
    // Cero es un importe como los demas, no una palabra.
    expect(balanceText(0, nl)).toBe('€\u00a00,00');
  });

  it('un plazo pasado sin aangifte se ve aunque el proximo plazo sea el del trimestre siguiente', () => {
    // Lo que da el panel el 5 de noviembre: proximo_plazo ya es el T4 (87 dias), y el T3 tiene
    // el plazo pasado (-5) sin la presentacion anotada.
    const btw = {
      plazos_pasados: ['2026-T3'],
      por_presentar: [
        { trimestre: '2026-T3', estado: 'listo_revision', limite_presentacion: '2026-10-31', dias_para_limite: -5 },
        { trimestre: '2026-T2', estado: 'presentado', limite_presentacion: '2026-07-31', dias_para_limite: -97 },
      ],
    };
    expect(overdueQuarters(btw)).toEqual(['2026-T3']);
    expect(overdueQuarters({ plazos_pasados: [], por_presentar: [] })).toEqual([]);
    // Solo la etiqueta (por si un trimestre no viniera en por_presentar).
    expect(overdueQuarters({ plazos_pasados: ['2026-T2'], por_presentar: [] })).toEqual(['2026-T2']);
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

  it('una sola accion principal: antes de probar, la prueba; despues, importar de verdad', () => {
    expect(primaryImportAction('idle', false)).toBe('try');
    expect(primaryImportAction('trying', false)).toBe('try');
    expect(primaryImportAction('previewed', true)).toBe('import');
    expect(primaryImportAction('importing', true)).toBe('import');
    // Con la prueba no entraria nada (el mismo fichero otra vez): ni una ni otra.
    expect(primaryImportAction('previewed', false)).toBeNull();
    expect(primaryImportAction('done', true)).toBeNull();
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

describe('lo que falta de una cuenta en IBAN-controles', () => {
  const f = (regla: string) => ({ reason: { regla } as never, invoice: {} as never });
  const account = (estado: string) => ({ estado } as never);
  it('una sola cosa por tarjeta: llamar, ponerla en Exact, mirar lo abierto o nada', () => {
    expect(accountStep({ account: null, findings: [f('F3'), f('F2')] })).toBe('confirm');
    expect(accountStep({ account: account('registrada'), findings: [] })).toBe('confirm');
    expect(accountStep({ account: account('heredada'), findings: [f('F2')] })).toBe('confirm');
    // Verificada por telefono y aun no en los ultimos maestros de Exact (F2).
    expect(accountStep({ account: account('verificada'), findings: [f('F2')] })).toBe('exact');
    expect(accountStep({ account: account('atestada'), findings: [f('F4')] })).toBe('open');
    expect(accountStep({ account: account('rechazada'), findings: [f('F3')] })).toBe('rejected');
  });
});

describe('lo que dice el dialogo de una orden', () => {
  const texts = { description: 'Wat de opdracht doet.', confirm: 'Wat er gebeurt.' };
  it('una sola explicacion: la de la pantalla o, sin ella, la del catalogo', () => {
    expect(dialogTexts('anular_hallazgo', true, texts)).toEqual({ description: null, warning: null });
    expect(dialogTexts('anular_hallazgo', false, texts)).toEqual({ description: 'Wat er gebeurt.', warning: null });
    expect(dialogTexts('anadir_nota', false, { description: 'Notitie.', confirm: null })).toEqual({ description: 'Notitie.', warning: null });
  });
  it('lo que no se deshace lleva su aviso aparte', () => {
    expect(dialogTexts('btw_anotar_presentacion', true, texts)).toEqual({ description: null, warning: 'Wat er gebeurt.' });
    expect(dialogTexts('btw_anotar_presentacion', false, texts)).toEqual({ description: 'Wat de opdracht doet.', warning: 'Wat er gebeurt.' });
  });
  it('ningun texto de confirmacion pregunta "Doorgaan?": el boton dice la orden', () => {
    for (const lang of ['nl', 'en'] as const) {
      for (const [name, a] of Object.entries(catalogFor(lang).acciones as Record<string, { confirmar?: string }>)) {
        expect(a.confirmar ?? '', `${lang} ${name}`).not.toMatch(/Doorgaan\?|Continue\?/);
      }
    }
  });
});
