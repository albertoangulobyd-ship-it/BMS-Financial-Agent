import { describe, expect, it } from 'vitest';
import { LANGS, MESSAGES } from '@/i18n';
import {
  RECORDS,
  RECORD_IDS,
  SECTIONS,
  SECTION_IDS,
  VIEWS,
  VIEW_IDS,
  isValidRoute,
  recordRoute,
  routeKey,
  sameRoute,
  sectionOf,
  visibleSections,
  visibleViews,
} from './registry';

const everyone = () => true;
const readOnly = (permission?: string) => !permission;

describe('las seis entradas (paso 16)', () => {
  it('son Inicio, Cuentas por cobrar, Cuentas por pagar, Documentos, Procesar e IVA, en ese orden', () => {
    expect(SECTION_IDS).toEqual(['home', 'receivables', 'payables', 'documents', 'process', 'vat']);
    expect(SECTIONS.map((s) => s.id)).toEqual([...SECTION_IDS]);
    expect(MESSAGES.es.areas.receivables.label).toBe('Cuentas por cobrar');
    expect(MESSAGES.nl.areas.receivables.label).toBe('Te ontvangen');
    expect(MESSAGES.en.areas.payables.label).toBe('Payables');
  });

  it('cada pantalla del paso 15 vive en una seccion (Ajustes, en el menu del nombre)', () => {
    const homed = SECTIONS.flatMap((s) => s.views);
    expect(new Set(homed).size).toBe(homed.length);
    expect([...homed, 'settings'].sort()).toEqual([...VIEW_IDS].sort());
    for (const section of SECTIONS) for (const view of section.views) expect(VIEWS[view].section).toBe(section.id);
    expect(sectionOf('settings')).toBeNull();
    // Donde decidio el dueno: Inicio con la cola, las excepciones y el flujo; cobrar con las
    // ventas, los clientes, los Objects y las PO de clientes; pagar con las compras, los
    // proveedores, sus PO y los IBAN; Procesar con leer facturas e importar. Paso 16 (Cuentas
    // por cobrar y por pagar): cada una abre con su resumen y lleva su banco tras las facturas.
    expect(SECTIONS.find((s) => s.id === 'home')!.views).toEqual(['home', 'work-queue', 'exceptions', 'cash-flow']);
    expect(SECTIONS.find((s) => s.id === 'receivables')!.views).toEqual(['receivables', 'invoices-out', 'bank-in', 'clients', 'objects', 'client-pos']);
    expect(SECTIONS.find((s) => s.id === 'payables')!.views).toEqual(['payables', 'invoices-in', 'bank-out', 'providers', 'provider-pos', 'iban-checks']);
    expect(SECTIONS.find((s) => s.id === 'process')!.views).toEqual(['import', 'read-invoices']);
  });

  it('cada entrada, vista y ficha tiene su nombre y su frase en los tres idiomas', () => {
    for (const lang of LANGS) {
      const t = MESSAGES[lang];
      for (const id of SECTION_IDS) {
        expect(t.areas[id].label.length, `${lang} ${id}`).toBeGreaterThan(0);
        expect(t.areas[id].description.length, `${lang} ${id}`).toBeGreaterThan(10);
      }
      for (const id of VIEW_IDS) {
        expect(t.nav[id].label.length, `${lang} ${id}`).toBeGreaterThan(0);
        expect(t.nav[id].description.length, `${lang} ${id}`).toBeGreaterThan(10);
      }
      for (const id of RECORD_IDS) expect(t.records[id].label.length, `${lang} ${id}`).toBeGreaterThan(0);
    }
  });

  it('quien no importa no ve Procesar; quien solo mira ve las otras cinco', () => {
    expect(visibleSections(everyone)).toEqual([...SECTION_IDS]);
    expect(visibleSections(readOnly)).toEqual(['home', 'receivables', 'payables', 'documents', 'vat']);
    expect(visibleViews('process', readOnly)).toEqual([]);
    expect(visibleViews('receivables', readOnly)).toEqual(['receivables', 'invoices-out', 'bank-in', 'clients', 'objects', 'client-pos']);
  });

  it('cada ficha se abre en una vista que existe', () => {
    for (const id of RECORD_IDS) expect(VIEW_IDS).toContain(RECORDS[id].view);
  });
});

describe('las rutas', () => {
  it('una vista va sin id; una ficha, con su id', () => {
    expect(isValidRoute({ screen: 'home' })).toBe(true);
    expect(isValidRoute({ screen: 'home', id: 1 })).toBe(false);
    expect(isValidRoute(recordRoute('invoice', 5))).toBe(true);
    expect(isValidRoute({ screen: 'invoice' })).toBe(false);
    expect(isValidRoute({ screen: 'invoice', id: 0 })).toBe(false);
    expect(isValidRoute({ screen: 'invoice', id: 2 ** 60 })).toBe(false);
    expect(isValidRoute({ screen: 'admin' as never })).toBe(false);
    expect(isValidRoute({ screen: 'overview' as never })).toBe(false);
  });

  it('un trimestre del btw va como numero, y solo uno que existe', () => {
    expect(isValidRoute(recordRoute('vat-quarter', 20263))).toBe(true);
    expect(isValidRoute(recordRoute('vat-quarter', 20265))).toBe(false);
    expect(isValidRoute(recordRoute('vat-quarter', 3))).toBe(false);
  });

  it('la clave de una ruta: la vista sola, o la ficha con su id', () => {
    expect(routeKey({ screen: 'invoices-out' })).toBe('invoices-out');
    expect(routeKey(recordRoute('client', 4))).toBe('client:4');
    expect(sameRoute(recordRoute('client', 4), { screen: 'client', id: 4 })).toBe(true);
    expect(sameRoute(recordRoute('client', 4), recordRoute('provider', 4))).toBe(false);
  });
});
