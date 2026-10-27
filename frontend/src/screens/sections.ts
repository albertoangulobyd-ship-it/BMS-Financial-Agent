// Las seis entradas, sus vistas y las fichas (paso 16), sin React ni iconos: lo usan
// screens/registry.ts (que les pone iconos y permisos) y las pruebas en el navegador
// (e2e/nav.ts), para llegar a cada pantalla como lo haria una persona.

export const SECTION_IDS = ['home', 'receivables', 'payables', 'documents', 'process', 'vat'] as const;
export type SectionId = (typeof SECTION_IDS)[number];

export const VIEW_IDS = [
  'home',
  'work-queue',
  'exceptions',
  'cash-flow',
  'invoices-out',
  'clients',
  'objects',
  'client-pos',
  'invoices-in',
  'providers',
  'provider-pos',
  'iban-checks',
  'documents',
  'import',
  'read-invoices',
  'vat',
  'settings',
] as const;
export type ViewId = (typeof VIEW_IDS)[number];

export const RECORD_IDS = [
  'invoice',
  'provider',
  'client',
  'object',
  'purchase-order',
  'vat-quarter',
  'exception',
  'client-documents',
  'provider-documents',
] as const;
export type RecordId = (typeof RECORD_IDS)[number];

/** Las vistas de cada entrada, en el orden de su menu; la primera es la que abre la entrada.
 *  Ajustes no es de ninguna: se abre desde el menu del nombre. */
export const SECTION_VIEWS: Readonly<Record<SectionId, readonly ViewId[]>> = {
  home: ['home', 'work-queue', 'exceptions', 'cash-flow'],
  receivables: ['invoices-out', 'clients', 'objects', 'client-pos'],
  payables: ['invoices-in', 'providers', 'provider-pos', 'iban-checks'],
  documents: ['documents'],
  // Importar primero: llegar a importar es un clic (revision §5, fila 20); leer PDF, dos.
  process: ['import', 'read-invoices'],
  vat: ['vat'],
};

/** Las vistas que piden un permiso ademas de ver_facturas. */
export const VIEW_REQUIRES: Readonly<Partial<Record<ViewId, string>>> = {
  'read-invoices': 'importar_datos',
  import: 'importar_datos',
};

/** La entrada de una vista (null: Ajustes). */
export function sectionOfView(view: ViewId): SectionId | null {
  for (const id of SECTION_IDS) if (SECTION_VIEWS[id].includes(view)) return id;
  return null;
}
