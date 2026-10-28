import { describe, expect, it } from 'vitest';
import { folderPlace } from '@/aurora/estado';
import { MESSAGES } from '@/i18n';
import { invoiceResult, placeTitle, recordResults, screenResults } from './quick-search';

const nl = MESSAGES.nl;
const everyone = () => true;
const readOnly = (permission?: string) => !permission;

describe('buscar y abrir (la conversacion)', () => {
  it('un sitio por su nombre en cualquiera de los tres idiomas, dicho en el de la app', () => {
    const vat = screenResults('iva', nl, everyone);
    expect(vat[0]).toMatchObject({ kind: 'screens', label: 'Btw', target: { kind: 'panel', entry: 'vat' } });
    // Los de Te ontvangen (su nombre en ingles); el primero, el panel ("Receivables" es tambien su titulo).
    expect(screenResults('receivables', nl, everyone).map((r) => r.key)).toEqual([
      'screen:receivables',
      'screen:invoices-out',
      'screen:bank-in',
      'screen:clients',
      'screen:objects',
      'screen:client-pos',
    ]);
    expect(screenResults('werklijst', MESSAGES.es, everyone)[0]!.label).toBe('Cola de trabajo');
    expect(screenResults('', nl, everyone)).toEqual([]);
  });

  it('cada sitio se abre donde vive ahora: un grupo del panel, la busqueda, Documentos o Procesar', () => {
    const target = (q: string) => screenResults(q, MESSAGES.es, everyone)[0]!.target;
    expect(target('cola de trabajo')).toEqual({ kind: 'panel', entry: 'home', view: 'queue' });
    expect(target('facturas de venta')).toEqual({ kind: 'search', preset: { sentido: 'saliente' } });
    expect(target('proveedores')).toEqual({ kind: 'documents', place: { category: 'providers', folder: null, sheet: null } });
  });

  it('sin permiso, Importeren y Facturen lezen no salen', () => {
    expect(screenResults('importeren', nl, readOnly)).toEqual([]);
    expect(screenResults('importeren', nl, everyone).map((r) => r.key)).toEqual(['screen:import']);
  });

  it('dos sitios con el mismo nombre se distinguen por donde viven', () => {
    expect(placeTitle('client-pos', nl)).toEqual({ label: 'Inkooporders', detail: 'van klanten · Te ontvangen' });
    expect(placeTitle('provider-pos', nl)).toEqual({ label: 'Inkooporders', detail: 'aan leveranciers · Te betalen' });
  });

  it('clientes, proveedores, Objects y PO: su carpeta y su hoja en Documentos', () => {
    const results = recordResults(
      'demo',
      {
        clients: [{ id: 1, nombre: 'Gemeente Demodorp', exact_id: '10003' }],
        providers: [{ id: 2, nombre: 'Démo Brandwacht', exact_id: null }],
        objects: [{ id: 3, codigo: 'GEM-HUIS', nombre: 'Gemeentehuis Demodorp', cliente: 'Gemeente Demodorp', cliente_id: 1 }],
        pos: [{ id: 4, numero: 'PO-DEMO-1', lado: 'proveedor', parte: { tabla: 'proveedor', id: 2, nombre: 'Démo Brandwacht' } }],
      },
      nl
    );
    expect(results.map((r) => [r.kind, r.target])).toEqual([
      ['clients', { kind: 'documents', place: folderPlace('client', 1) }],
      ['providers', { kind: 'documents', place: folderPlace('provider', 2) }],
      ['objects', { kind: 'documents', place: folderPlace('client', 1, { kind: 'object', id: 3 }) }],
      ['pos', { kind: 'documents', place: folderPlace('provider', 2, { kind: 'po', id: 4 }) }],
    ]);
  });

  it('una factura se abre en su hoja, con su importe en euros', () => {
    expect(invoiceResult({ id: 7, numero: 'KT-1', sentido: 'entrante', contraparte: 'K. T.', total_cent: 123456, proveedor_id: 5 }, nl)).toMatchObject({
      target: { kind: 'documents', place: folderPlace('provider', 5, { kind: 'invoice', id: 7 }) },
      label: 'KT-1',
      detail: 'K. T. · €\u00a01.234,56',
    });
    expect(invoiceResult({ id: 8, numero: null, sentido: 'saliente', contraparte: null, total_cent: null }, nl)).toMatchObject({ label: 'Factuur 8' });
  });
});
