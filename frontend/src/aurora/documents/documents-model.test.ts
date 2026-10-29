// El archivo de Documentos sin React (paso 16): el orden de las carpetas, las doce primeras y
// "Ver todas", las pestanas y la busqueda, los tipos de una carpeta, el abanico, de donde
// sale "pagada" y el arbol que carga por partes.
import { describe, expect, it } from 'vitest';
import type { InvoiceDetail, InvoicePayment, PartyDocument, PartyRow } from '@/lib/api-types';
import {
  FIRST_FOLDERS,
  allFolders,
  archiveTree,
  byAttention,
  docKey,
  fanDocs,
  firstFolders,
  folderKey,
  invoiceIdOf,
  nodeTarget,
  paidSource,
  purchaseOrderIdOf,
  withAncestors,
  type DocsEntry,
} from './documents-model';

function party(id: number, nombre: string, vencido = 0, pendiente = 0, extra: Partial<PartyRow> = {}): PartyRow {
  return {
    id,
    nombre,
    exact_id: `E${id}`,
    activo: true,
    facturas: 1,
    pendiente_cent: pendiente,
    deuda_cent: pendiente,
    abonos_sin_enlazar_cent: 0,
    abonos_sin_enlazar_facturas: 0,
    vencido_cent: vencido,
    ano_facturado_cent: 0,
    nivel: 'normal',
    ...extra,
  };
}

function doc(id: number, tipo: string, vinculo: PartyDocument['vinculo'], extra: Partial<PartyDocument> = {}): PartyDocument {
  return {
    id,
    tipo,
    fecha: '2026-10-01',
    numero: `N-${id}`,
    importe_cent: 1000,
    estado_pago: null,
    nombre: `${id}.pdf`,
    tipo_mime: 'application/pdf',
    bytes: 1200,
    guardado: true,
    sha256: null,
    registrado_en: null,
    vinculo,
    ...extra,
  };
}

describe('las carpetas', () => {
  it('primero lo vencido, despues lo pendiente y, a igualdad, el orden de la API', () => {
    const clients = [party(1, 'A'), party(2, 'B', 0, 500), party(3, 'C', 100, 100)];
    const providers = [party(1, 'P', 0, 900), party(2, 'Q', 300, 300), party(3, 'R')];
    expect(allFolders(clients, providers).map((f) => f.key)).toEqual([
      'provider:2',
      'client:3',
      'provider:1',
      'client:2',
      'client:1',
      'provider:3',
    ]);
    // Un saldo a favor (negativo) no pasa delante de nadie.
    expect(byAttention([{ row: party(9, 'X', 0, -500) }, { row: party(8, 'Y') }]).map((r) => r.row.id)).toEqual([9, 8]);
    // Lo pendiente es la cifra de la cartera (sin restar el abono sin enlazar), la que dice la
    // carpeta: la de 1.000 de deuda y 600 de abono va delante de la de 700.
    const credited = party(5, 'Z', 0, 400, { deuda_cent: 1_000, abonos_sin_enlazar_cent: -600, abonos_sin_enlazar_facturas: 1 });
    expect(byAttention([{ row: party(4, 'W', 0, 700) }, { row: credited }]).map((r) => r.row.id)).toEqual([5, 4]);
  });

  it('las doce primeras y "Ver todas"; la abierta se ve aunque este mas abajo', () => {
    const many = allFolders(
      Array.from({ length: 16 }, (_, i) => party(i + 1, `K${i + 1}`)),
      []
    );
    expect(FIRST_FOLDERS).toBe(12);
    const first = firstFolders(many, false, null);
    expect(first.shown.length).toBe(12);
    expect(first.hidden).toBe(4);
    expect(firstFolders(many, true, null)).toEqual({ shown: many, hidden: 0 });
    expect(firstFolders(many, false, 'client:3').hidden).toBe(4);
    expect(firstFolders(many, false, 'client:15')).toEqual({ shown: many, hidden: 0 });
    expect(firstFolders(many.slice(0, 12), false, null).hidden).toBe(0);
  });
});

describe('los documentos de una carpeta', () => {
  const docs = [
    doc(7, 'justificante_pago', { tabla: 'aplicacion_pago', id: 3, factura_id: 11, estado: 'confirmada', fuente: 'manual' }),
    doc(5, 'factura_compra', { tabla: 'factura', id: 11, factura_id: 11 }),
    doc(5, 'factura_compra', { tabla: 'factura', id: 12, factura_id: 12 }),
    doc(4, 'abono_compra', { tabla: 'factura', id: 13, factura_id: 13 }),
    doc(3, 'orden_compra', { tabla: 'orden_compra', id: 2, orden_compra_id: 2 }),
    doc(2, 'tipo_nuevo', { tabla: 'otra', id: 1 }),
  ];

  it('una fila por enlace: el mismo documento con dos registros son dos filas', () => {
    expect(new Set(docs.map(docKey)).size).toBe(docs.length);
    expect(docKey(docs[1]!)).toBe('5-factura-11');
  });

  it('la factura de un original o de un justificante, y la PO de una hoja', () => {
    expect(invoiceIdOf(docs[0]!)).toBe(11);
    expect(invoiceIdOf(docs[3]!)).toBe(13);
    expect(invoiceIdOf(docs[4]!)).toBeNull();
    expect(purchaseOrderIdOf(docs[4]!)).toBe(2);
    expect(purchaseOrderIdOf(docs[1]!)).toBeNull();
  });

  it('el abanico: las cuatro mas recientes, la mas nueva al final (delante)', () => {
    expect(fanDocs([1, 2, 3, 4, 5, 6])).toEqual([4, 3, 2, 1]);
    expect(fanDocs([1])).toEqual([1]);
    expect(fanDocs([])).toEqual([]);
  });
});

describe('pagada, segun quien', () => {
  const pay = (fuente: string, estado: string, fecha: string): InvoicePayment => ({
    id: 1,
    rev: 0,
    estado,
    fuente,
    metodo: null,
    importe_cent: 100,
    fecha_pago: fecha,
    movimiento_id: null,
    regla: null,
    concepto: null,
    contraparte: null,
  });
  const detail = (estado_pago: string, pagos: InvoicePayment[], reglas: string[] = []) =>
    ({
      estado: { estado_pago } as InvoiceDetail['estado'],
      pagos,
      hallazgos: reglas.map((regla) => ({ regla, estado: 'abierto' })) as InvoiceDetail['hallazgos'],
    }) as Pick<InvoiceDetail, 'estado' | 'pagos' | 'hallazgos'>;

  it('manda el banco, luego Exact, luego lo apuntado a mano', () => {
    expect(paidSource(detail('pagada', [pay('manual', 'confirmada', '2026-10-20'), pay('banco', 'confirmada', '2026-10-12')]))).toEqual({
      source: 'banco',
      date: '2026-10-12',
      notInBank: false,
      k3: false,
    });
    expect(paidSource(detail('pagada', [pay('exact', 'confirmada', '2026-10-01'), pay('manual', 'confirmada', '2026-10-02')]))?.source).toBe('exact');
  });

  it('apuntada a mano: aun no se ve en el banco, y el aviso K3 si esta abierto', () => {
    expect(paidSource(detail('pagada', [pay('manual', 'confirmada', '2026-10-02')], ['K3']))).toEqual({
      source: 'manual',
      date: '2026-10-02',
      notInBank: true,
      k3: true,
    });
  });

  it('sin pagar, o sin un pago confirmado que lo diga, no hay fuente', () => {
    expect(paidSource(detail('pendiente', [pay('banco', 'confirmada', '2026-10-02')]))).toBeNull();
    expect(paidSource(detail('pagada', [pay('banco', 'propuesta', '2026-10-02'), pay('banco', 'retirada', '2026-10-01')]))).toBeNull();
    expect(paidSource(detail('pagada', []))).toBeNull();
  });
});

describe('el arbol', () => {
  const texts = {
    home: 'Start',
    all: 'Documenten',
    clients: 'Klanten',
    providers: 'Leveranciers',
    failed: 'Niet gelukt',
    docLabel: (d: PartyDocument) => `${d.tipo} ${d.numero}`,
  };
  const folders = allFolders([party(1, 'Klant', 0, 0, { documentos: 0 })], [party(2, 'Lev', 0, 10, { documentos: 2 })]);

  it('inicio, documentos con sus dos grupos y cada carpeta con su cuenta', () => {
    const tree = archiveTree(folders, new Map(), texts);
    expect(tree.map((n) => n.id)).toEqual(['home', 'all']);
    expect(tree[1]!.meta).toBe('2');
    expect(tree[1]!.children!.map((n) => [n.id, n.meta])).toEqual([
      ['clients', '1'],
      ['providers', '1'],
    ]);
    const [client] = tree[1]!.children![0]!.children!;
    const [provider] = tree[1]!.children![1]!.children!;
    // Sin documentos, una hoja; con documentos aun sin leer, una rama que se puede abrir y no
    // ensena nada mientras (nada de «Cargando…», §6.5).
    expect(client!.children).toBeUndefined();
    expect(client!.lazy).toBeUndefined();
    expect(provider!.children).toBeUndefined();
    expect(provider!.lazy).toBe(true);
  });

  it('una carpeta leida ensena sus documentos; si fallo, lo dice', () => {
    const d = doc(5, 'factura_compra', { tabla: 'factura', id: 11, factura_id: 11 });
    const ready = new Map<string, DocsEntry>([['provider:2', { status: 'ready', docs: [d] }]]);
    const provider = archiveTree(folders, ready, texts)[1]!.children![1]!.children![0]!;
    expect(provider.meta).toBe('1');
    expect(provider.children).toEqual([{ id: 'provider:2/5-factura-11', label: 'factura_compra N-5', proper: true }]);
    const failed = new Map<string, DocsEntry>([['provider:2', { status: 'error' }]]);
    expect(archiveTree(folders, failed, texts)[1]!.children![1]!.children![0]!.children![0]!.label).toBe('Niet gelukt');
  });

  it('que abre cada nodo', () => {
    expect(nodeTarget('home')).toEqual({ kind: 'home' });
    expect(nodeTarget('all')).toEqual({ kind: 'tab', tab: 'all' });
    expect(nodeTarget('providers')).toEqual({ kind: 'tab', tab: 'providers' });
    expect(nodeTarget(folderKey('client', 3))).toEqual({ kind: 'folder', side: 'client', id: 3 });
    expect(nodeTarget('provider:2/5-factura-11')).toEqual({ kind: 'doc', side: 'provider', id: 2, doc: '5-factura-11' });
    expect(nodeTarget('provider:2/…')).toEqual({ kind: 'none' });
    expect(nodeTarget('provider:0')).toEqual({ kind: 'none' });
    expect(nodeTarget('x')).toEqual({ kind: 'none' });
  });

  it('el camino hasta lo que se ve queda abierto', () => {
    expect(withAncestors([], 'provider:2/5-factura-11').sort()).toEqual(['all', 'provider:2', 'providers']);
    expect(withAncestors([], 'client:4').sort()).toEqual(['all', 'client:4', 'clients']);
    expect(withAncestors(['client:1'], 'clients').sort()).toEqual(['all', 'client:1', 'clients']);
    expect(withAncestors([], null)).toEqual(['all']);
  });
});
