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
  'receivables',
  'invoices-out',
  'bank-in',
  'clients',
  'objects',
  'client-pos',
  'payables',
  'invoices-in',
  'bank-out',
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

export type ScreenId = ViewId | RecordId;

/** Donde se esta: una vista (sin id) o una ficha (con su id numerico). */
export interface Route {
  screen: ScreenId;
  id?: number;
}

/** Las vistas de cada entrada, en el orden de su panel; la primera es su resumen. Ajustes no es
 *  de ninguna: es su propio panel. Paso 17 (especificacion §2.2): los IBAN pasan a Inicio e
 *  Importar a Cuentas por cobrar, como en los paneles (aurora/estado.ts lee de aqui); Procesar
 *  queda con leer facturas. */
export const SECTION_VIEWS: Readonly<Record<SectionId, readonly ViewId[]>> = {
  home: ['home', 'work-queue', 'exceptions', 'iban-checks', 'cash-flow'],
  // Paso 16 (Cuentas por cobrar y por pagar): el resumen de la cartera abre la entrada, y el
  // banco (lo propuesto por confirmar y lo que no casa) va despues de las facturas.
  receivables: ['receivables', 'invoices-out', 'bank-in', 'clients', 'objects', 'client-pos', 'import'],
  payables: ['payables', 'invoices-in', 'bank-out', 'providers', 'provider-pos'],
  documents: ['documents'],
  process: ['read-invoices'],
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

/** Los resumenes de Cuentas por cobrar y por pagar: su pastilla dice "Resumen" y su titulo
 *  es el de la entrada ("Cuentas por cobrar"). */
export const OVERVIEW_VIEWS = ['receivables', 'payables'] as const satisfies readonly ViewId[];
export type OverviewView = (typeof OVERVIEW_VIEWS)[number];

export function isOverviewView(view: ViewId): view is OverviewView {
  return (OVERVIEW_VIEWS as readonly ViewId[]).includes(view);
}
