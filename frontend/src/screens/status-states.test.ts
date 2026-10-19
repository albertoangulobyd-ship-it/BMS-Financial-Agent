// Los estados que las pantallas derivan de lo que manda la API (el plazo del btw, la prueba
// de una importacion, las senales de una PO, el aislamiento por papeles), y la pastilla que
// les toca segun components/status-pill: que la regla sea la del dueno y que solo lata lo
// que pide hacer algo ya.
import { describe, expect, it } from 'vitest';
import { statusRule } from '@/components/status-pill';
import type { Isolation } from '@/lib/api-types';
import { previewState } from './import';
import { poSignal } from './purchase-order';
import { roleIsolation, worstIsolation } from './settings';
import { DEADLINE_CLOSE_DAYS, deadlineState } from './vat';

describe('el plazo del btw', () => {
  it('pasado y sin aangifte es un error; a 14 dias o menos, un aviso; con margen o presentado, nada', () => {
    expect(deadlineState({ estado: 'abierto', dias_para_limite: -1 })).toBe('plazo_vencido');
    expect(deadlineState({ estado: 'listo_revision', dias_para_limite: 0 })).toBe('plazo_cerca');
    expect(deadlineState({ estado: 'abierto', dias_para_limite: DEADLINE_CLOSE_DAYS })).toBe('plazo_cerca');
    expect(deadlineState({ estado: 'abierto', dias_para_limite: DEADLINE_CLOSE_DAYS + 1 })).toBeNull();
    expect(deadlineState({ estado: 'presentado', dias_para_limite: -30 })).toBeNull();
    expect(deadlineState({ estado: 'abierto', dias_para_limite: null })).toBeNull();
    expect(statusRule('btw', 'plazo_vencido')).toEqual({ variant: 'error', ping: false });
    expect(statusRule('btw', 'plazo_cerca')).toEqual({ variant: 'warning', ping: false });
  });
});

describe('la prueba de una importacion', () => {
  it('con filas rechazadas, errores; con avisos o valores que chocan, avisos; si no, en orden', () => {
    expect(previewState({ rechazadas: 2, avisos: ['x'], sin_resolver: 1 })).toBe('errores');
    expect(previewState({ rechazadas: 0, avisos: ['x'], sin_resolver: 0 })).toBe('avisos');
    expect(previewState({ rechazadas: 0, avisos: [], sin_resolver: 3 })).toBe('avisos');
    expect(previewState({ rechazadas: 0, avisos: [], sin_resolver: 0 })).toBe('ok');
    expect(statusRule('importar_prueba', 'errores').variant).toBe('error');
    expect(statusRule('importar_prueba', 'avisos').variant).toBe('warning');
    expect(statusRule('importar_prueba', 'ok').variant).toBe('success');
  });
});

describe('las senales de una PO', () => {
  it('junto a lo que queda va lo mas serio del valor; junto a la prevision, lo esperado', () => {
    const left = ['P6', 'P4', 'P5', 'P7'];
    const forecast = ['P10', 'P9', 'P8'];
    expect(poSignal(new Set(['P5', 'P7', 'P6']), left)).toBe('P6');
    expect(poSignal(new Set(['P7', 'P5']), left)).toBe('P5');
    expect(poSignal(new Set(['P9', 'P8']), forecast)).toBe('P9');
    expect(poSignal(new Set(['P1', 'P2']), left)).toBeNull();
    // Por encima de su valor, error; cerca del limite, del final o de agotarse, aviso.
    expect(statusRule('po_senal', 'P6').variant).toBe('error');
    expect(statusRule('po_senal', 'P4').variant).toBe('error');
    for (const code of ['P5', 'P7', 'P8', 'P9', 'P10']) expect(statusRule('po_senal', code).variant, code).toBe('warning');
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
    // Lo que falla, falta o es viejo late en rojo; lo correcto, en verde y quieto.
    for (const s of ['falla', 'sin_comprobar', 'caducada']) expect(statusRule('aislamiento', s), s).toEqual({ variant: 'error', ping: true });
    expect(statusRule('aislamiento', 'correcto')).toEqual({ variant: 'success', ping: false });
  });
});
