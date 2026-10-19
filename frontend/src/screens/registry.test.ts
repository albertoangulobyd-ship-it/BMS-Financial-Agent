import { describe, expect, it } from 'vitest';
import { MESSAGES } from '@/i18n';
import { NAV, NAV_IDS, RECORD_IDS, isValidRoute, recordRoute } from './registry';

describe('las pantallas', () => {
  it('cada entrada de la navegacion tiene su titulo y su frase en los dos idiomas', () => {
    for (const lang of ['nl', 'en'] as const) {
      for (const id of NAV_IDS) {
        expect(MESSAGES[lang].nav[id].label.length, id).toBeGreaterThan(0);
        expect(MESSAGES[lang].nav[id].description.length, id).toBeGreaterThan(10);
      }
      for (const id of RECORD_IDS) expect(MESSAGES[lang].records[id].label.length).toBeGreaterThan(0);
    }
  });

  it('estan todas las areas, en el orden de la opcion B', () => {
    expect(NAV.map((n) => n.id)).toEqual(NAV_IDS);
    expect([...new Set(NAV.map((n) => n.group))]).toEqual(['daily', 'invoices', 'parties', 'money', 'data', 'settings']);
  });

  it('una ruta valida es una entrada sin id o una ficha con su id', () => {
    expect(isValidRoute({ screen: 'overview' })).toBe(true);
    expect(isValidRoute({ screen: 'overview', id: 1 })).toBe(false);
    expect(isValidRoute(recordRoute('invoice', 5, 'invoices-in'))).toBe(true);
    expect(isValidRoute({ screen: 'invoice' })).toBe(false);
    expect(isValidRoute({ screen: 'invoice', id: 5, from: 'nope' })).toBe(false);
    expect(isValidRoute({ screen: 'admin' })).toBe(false);
  });

  it('un trimestre del btw va como numero, y solo uno que existe', () => {
    expect(isValidRoute(recordRoute('vat-quarter', 20263, 'vat'))).toBe(true);
    expect(isValidRoute(recordRoute('vat-quarter', 20265, 'vat'))).toBe(false);
    expect(isValidRoute(recordRoute('vat-quarter', 3, 'vat'))).toBe(false);
  });
});
