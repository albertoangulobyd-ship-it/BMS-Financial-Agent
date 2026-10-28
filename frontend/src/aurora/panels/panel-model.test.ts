// Las piezas puras de los paneles (paso 17), con las pruebas que tenian en las pantallas de los
// pasos 15 y 16: "Lo primero", el saludo, el IVA, importar y el aislamiento, y la tabla de estados
// que les toca (components/status-pill).
import { describe, expect, it } from 'vitest';
import { statusRule } from '@/components/status-pill';
import { MESSAGES } from '@/i18n';
import type { InvoiceRow } from '@/lib/api';
import type { Isolation, VatSummary } from '@/lib/api-types';
import {
  DEADLINE_CLOSE_DAYS,
  FIRST,
  balanceText,
  deadlineState,
  fileDay,
  firstName,
  formatSize,
  nextStep,
  plainAmount,
  previewState,
  primaryImportAction,
  quarterRows,
  roleIsolation,
  urgentFirst,
  worstIsolation,
} from './panel-model';

const nl = MESSAGES.nl;
const row = (id: number, nivel: string, extra: Partial<InvoiceRow> = {}): InvoiceRow =>
  ({ id, numero: `F-${id}`, sentido: 'entrante', nivel, cuenta: true, razones: [{ id, regla: 'X1' }], ...extra }) as unknown as InvoiceRow;

describe('Inicio', () => {
  it('"Lo primero" solo con lo bloqueado o urgente (y como mucho cinco)', () => {
    const rows = [row(1, 'bloqueada'), row(2, 'atencion'), row(3, 'urgente'), row(4, 'normal')];
    expect(urgentFirst(rows).map((r) => r.id)).toEqual([1, 3]);
    expect(urgentFirst([row(5, 'atencion')])).toEqual([]);
    expect(FIRST).toBe(5);
  });

  it('el saludo con el nombre de pila', () => {
    expect(firstName('Ana Demo')).toBe('Ana');
    expect(firstName('  Bram  ')).toBe('Bram');
    expect(firstName('J. Voorbeeld')).toBe('J. Voorbeeld');
  });
});

describe('el IVA', () => {
  it('el saldo dice si se paga o se recibe, en euros', () => {
    expect(balanceText(474386, nl)).toBe('€ 4.743,86 te betalen');
    expect(balanceText(-40970, nl)).toBe('€ 409,70 terug');
    expect(balanceText(0, nl)).toBe('€ 0,00');
  });

  it('el paso siguiente de cada estado, y nunca "aprobado"', () => {
    expect(nextStep({ estado: 'abierto', terminado: false }, nl)).toBe(nl.vat.nextRunning);
    expect(nextStep({ estado: 'abierto', terminado: true }, nl)).toBe(nl.vat.nextCheck);
    expect(nextStep({ estado: 'listo_revision', terminado: true }, nl)).toBe(nl.vat.nextFile);
    expect(nextStep({ estado: 'presentado', terminado: true }, nl)).toBe(nl.vat.nextFiled);
  });

  it('los trimestres: el en curso y los anteriores, sin repetir, el mas nuevo primero', () => {
    const r = (etiqueta: string, estado: string) => ({ ano: 2026, trimestre: 1, etiqueta, estado, limite_presentacion: null, dias_para_limite: null, '5c': 1, ingresos_cent: 1 });
    const summary = {
      hoy: '2026-10-19',
      actual: { etiqueta: '2026-T4', estado: 'abierto', terminado: false, cifras: { '5c': -5 }, limite_presentacion: null, dias_para_limite: 104 },
      por_presentar: [r('2026-T3', 'listo_revision')],
      anteriores: [r('2026-T3', 'listo_revision'), r('2026-T2', 'presentado')],
    } as unknown as VatSummary;
    expect(quarterRows(summary).map((q) => [q.etiqueta, q.terminado])).toEqual([
      ['2026-T4', false],
      ['2026-T3', true],
      ['2026-T2', true],
    ]);
  });

  it('el plazo: pasado y sin declaracion es un error; a 14 dias o menos, un aviso; con margen o presentado, nada', () => {
    expect(deadlineState({ estado: 'abierto', dias_para_limite: -1 })).toBe('plazo_vencido');
    expect(deadlineState({ estado: 'listo_revision', dias_para_limite: 0 })).toBe('plazo_cerca');
    expect(deadlineState({ estado: 'abierto', dias_para_limite: DEADLINE_CLOSE_DAYS })).toBe('plazo_cerca');
    expect(deadlineState({ estado: 'abierto', dias_para_limite: DEADLINE_CLOSE_DAYS + 1 })).toBeNull();
    expect(deadlineState({ estado: 'presentado', dias_para_limite: -30 })).toBeNull();
    expect(deadlineState({ estado: 'abierto', dias_para_limite: null })).toBeNull();
    expect(statusRule('btw', 'plazo_vencido')).toEqual({ variant: 'error', ping: false });
    expect(statusRule('btw', 'plazo_cerca')).toEqual({ variant: 'warning', ping: false });
  });

  it('lo declarado se escribe con el menos del teclado, como lo lee el servidor', () => {
    expect(plainAmount(474386)).toBe('4.743,86');
    expect(plainAmount(-40970)).toBe('-409,70');
    expect(plainAmount(0)).toBe('0,00');
  });
});

describe('importar', () => {
  it('el tamano de un fichero con coma decimal', () => {
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
    expect(primaryImportAction('previewed', false)).toBeNull();
    expect(primaryImportAction('done', true)).toBeNull();
  });

  it('el dia de un fichero, y hoy si dice ser del futuro', () => {
    const now = new Date('2026-10-19T10:00:00Z');
    expect(fileDay(Date.parse('2026-10-16T08:00:00Z'), now)).toBe('2026-10-16');
    expect(fileDay(Date.parse('2027-01-01T08:00:00Z'), now)).toBe('2026-10-19');
  });

  it('la prueba de un lote: con rechazadas, errores; con avisos o valores que chocan, avisos; si no, en orden', () => {
    expect(previewState({ rechazadas: 2, avisos: ['x'], sin_resolver: 1 })).toBe('errores');
    expect(previewState({ rechazadas: 0, avisos: ['x'], sin_resolver: 0 })).toBe('avisos');
    expect(previewState({ rechazadas: 0, avisos: [], sin_resolver: 3 })).toBe('avisos');
    expect(previewState({ rechazadas: 0, avisos: [], sin_resolver: 0 })).toBe('ok');
    expect(statusRule('importar_prueba', 'errores').variant).toBe('error');
    expect(statusRule('importar_prueba', 'avisos').variant).toBe('warning');
    expect(statusRule('importar_prueba', 'ok').variant).toBe('success');
  });
});

describe('el aislamiento por papeles', () => {
  const isolation = (papeles: Isolation['papeles']): Isolation => ({ aplica: true, entorno: 'nativo', correcto: false, papeles });
  it('cada papel dice su estado (o, sin el, si va bien) y arriba va lo mas serio', () => {
    expect(roleIsolation({ papel: 'lector', bien: false, estado: 'caducada' })).toBe('caducada');
    expect(roleIsolation({ papel: 'lector', bien: true })).toBe('correcto');
    expect(roleIsolation({ papel: 'lector', bien: false })).toBe('falla');
    const i = isolation([
      { papel: 'consola', bien: true, estado: 'correcto' },
      { papel: 'lector', bien: false, estado: 'sin_comprobar' },
      { papel: 'salida', bien: false, estado: 'caducada' },
      { papel: 'orden', bien: true, estado: 'correcto' },
    ]);
    expect(worstIsolation(i)).toBe('caducada');
    expect(worstIsolation(isolation([{ papel: 'orden', bien: false, estado: 'falla' }, ...i.papeles]))).toBe('falla');
    for (const s of ['falla', 'sin_comprobar', 'caducada']) expect(statusRule('aislamiento', s), s).toEqual({ variant: 'error', ping: true });
    expect(statusRule('aislamiento', 'correcto')).toEqual({ variant: 'success', ping: false });
  });
});
