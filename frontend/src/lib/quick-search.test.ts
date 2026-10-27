import { describe, expect, it } from 'vitest';
import { MESSAGES } from '@/i18n';
import { invoiceResult, recordResults, screenResults, viewTitle } from './quick-search';

const nl = MESSAGES.nl;
const everyone = () => true;
const readOnly = (permission?: string) => !permission;

describe('buscar y abrir (la caja del inicio y Ctrl+K)', () => {
  it('una pantalla por su nombre en cualquiera de los tres idiomas, dicha en el de la app', () => {
    const vat = screenResults('iva', nl, everyone);
    expect(vat[0]).toMatchObject({ kind: 'screens', label: 'Btw', view: 'vat', route: { screen: 'vat' } });
    expect(screenResults('receivables', nl, everyone).map((r) => r.view)).toEqual(['invoices-out', 'clients', 'objects', 'client-pos']);
    expect(screenResults('werklijst', MESSAGES.es, everyone)[0]!.label).toBe('Cola de trabajo');
    expect(screenResults('', nl, everyone)).toEqual([]);
  });

  it('sin permiso, Importeren y Facturen lezen no salen', () => {
    expect(screenResults('importeren', nl, readOnly)).toEqual([]);
    expect(screenResults('importeren', nl, everyone).map((r) => r.view)).toEqual(['import']);
  });

  it('dos vistas con el mismo nombre se distinguen por donde viven', () => {
    expect(viewTitle('client-pos', nl)).toEqual({ label: 'Inkooporders', detail: 'van klanten · Te ontvangen' });
    expect(viewTitle('provider-pos', nl)).toEqual({ label: 'Inkooporders', detail: 'aan leveranciers · Te betalen' });
  });

  it('clientes, proveedores, Objects y PO de sus listas, sin mayusculas ni acentos', () => {
    const results = recordResults(
      'demo',
      {
        clients: [{ id: 1, nombre: 'Gemeente Demodorp', exact_id: '10003' }],
        providers: [{ id: 2, nombre: 'Démo Brandwacht', exact_id: null }],
        objects: [{ id: 3, codigo: 'GEM-HUIS', nombre: 'Gemeentehuis Demodorp', cliente: 'Gemeente Demodorp' }],
        pos: [{ id: 4, numero: 'PO-DEMO-1', lado: 'proveedor', parte: { tabla: 'proveedor', id: 2, nombre: 'Démo Brandwacht' } }],
      },
      nl
    );
    expect(results.map((r) => [r.kind, r.view, r.route])).toEqual([
      ['clients', 'clients', { screen: 'client', id: 1 }],
      ['providers', 'providers', { screen: 'provider', id: 2 }],
      ['objects', 'objects', { screen: 'object', id: 3 }],
      ['pos', 'provider-pos', { screen: 'purchase-order', id: 4 }],
    ]);
  });

  it('una factura se abre en la lista de su sentido, con su importe en euros', () => {
    expect(invoiceResult({ id: 7, numero: 'KT-1', sentido: 'entrante', contraparte: 'K. T.', total_cent: 123456 }, nl)).toMatchObject({
      view: 'invoices-in',
      route: { screen: 'invoice', id: 7 },
      label: 'KT-1',
      detail: 'K. T. · € 1.234,56',
    });
    expect(invoiceResult({ id: 8, numero: null, sentido: 'saliente', contraparte: null, total_cent: null }, nl)).toMatchObject({
      view: 'invoices-out',
      label: 'Factuur 8',
    });
  });
});
