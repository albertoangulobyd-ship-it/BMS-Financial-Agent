// Que pantallas hay y donde viven (paso 16). Seis entradas (las secciones): Inicio, Cuentas
// por cobrar, Cuentas por pagar, Documentos, Procesar e IVA. Cada seccion tiene sus vistas (la
// primera es la que abre la entrada) y cada vista su permiso; Ajustes no es de ninguna: se
// abre desde el menu de la persona. Las fichas (una factura, un cliente...) se abren dentro
// de la seccion donde se esta, con sus migas y "Volver" (shell/navigation.tsx). Una ruta que
// no esta aqui no se abre (isValidRoute).
import {
  Banknote,
  Building2,
  ClipboardList,
  FileInput,
  FileOutput,
  FileText,
  FolderOpen,
  House,
  Landmark,
  LayoutGrid,
  ListChecks,
  MapPin,
  Percent,
  ScanText,
  Settings,
  TriangleAlert,
  Truck,
  Upload,
  Users,
  Wallet,
  ArrowDownToLine,
  ArrowUpFromLine,
  Cog,
  type LucideIcon,
} from 'lucide-react';
import { idToQuarter } from '@/lib/format';

import {
  RECORD_IDS,
  SECTION_IDS,
  SECTION_VIEWS,
  VIEW_IDS,
  VIEW_REQUIRES,
  sectionOfView,
  type RecordId,
  type Route,
  type ScreenId,
  type SectionId,
  type ViewId,
} from './sections';

export { RECORD_IDS, SECTION_IDS, VIEW_IDS };
export type { RecordId, Route, ScreenId, SectionId, ViewId };


export interface SectionDef {
  id: SectionId;
  icon: LucideIcon;
  /** Sus vistas, en el orden de su menu; la primera es la que abre la entrada. */
  views: readonly ViewId[];
}

const SECTION_ICONS: Readonly<Record<SectionId, LucideIcon>> = {
  home: House,
  receivables: ArrowDownToLine,
  payables: ArrowUpFromLine,
  documents: FolderOpen,
  process: Cog,
  vat: Percent,
};

export const SECTIONS: readonly SectionDef[] = SECTION_IDS.map((id) => ({ id, icon: SECTION_ICONS[id], views: SECTION_VIEWS[id] }));

export interface ViewDef {
  id: ViewId;
  /** null: no es de ninguna seccion (Ajustes, desde el menu de la persona). */
  section: SectionId | null;
  icon: LucideIcon;
  /** El permiso que hace falta para verla (todas piden ver_facturas para entrar). */
  requires?: string;
}

const VIEW_ICONS: Readonly<Record<ViewId, LucideIcon>> = {
  home: House,
  'work-queue': ListChecks,
  exceptions: TriangleAlert,
  'cash-flow': Wallet,
  receivables: LayoutGrid,
  'invoices-out': FileOutput,
  'bank-in': Banknote,
  clients: Users,
  objects: MapPin,
  'client-pos': ClipboardList,
  payables: LayoutGrid,
  'invoices-in': FileInput,
  'bank-out': Banknote,
  providers: Truck,
  'provider-pos': ClipboardList,
  'iban-checks': Landmark,
  documents: FolderOpen,
  'read-invoices': ScanText,
  import: Upload,
  vat: Percent,
  settings: Settings,
};

export const VIEWS: Readonly<Record<ViewId, ViewDef>> = Object.fromEntries(
  VIEW_IDS.map((id) => [id, { id, section: sectionOfView(id), icon: VIEW_ICONS[id], requires: VIEW_REQUIRES[id] }])
) as Record<ViewId, ViewDef>;

/** Cada ficha, con la vista donde se abre cuando no se llega desde una lista (Ctrl+K). */
export const RECORDS: Readonly<Record<RecordId, { icon: LucideIcon; view: ViewId }>> = {
  invoice: { icon: FileText, view: 'work-queue' },
  provider: { icon: Truck, view: 'providers' },
  client: { icon: Users, view: 'clients' },
  object: { icon: Building2, view: 'objects' },
  'purchase-order': { icon: ClipboardList, view: 'client-pos' },
  // Un trimestre del btw: su id es el ano por diez mas el trimestre (2026-T3 es 20263).
  'vat-quarter': { icon: Percent, view: 'vat' },
  exception: { icon: TriangleAlert, view: 'exceptions' },
  // La carpeta de una empresa en Documentos (su id es el de la empresa).
  'client-documents': { icon: FolderOpen, view: 'documents' },
  'provider-documents': { icon: FolderOpen, view: 'documents' },
};

export const HOME: ViewId = 'home';

export function isViewId(value: unknown): value is ViewId {
  return typeof value === 'string' && (VIEW_IDS as readonly string[]).includes(value);
}

export function isRecordId(value: unknown): value is RecordId {
  return typeof value === 'string' && (RECORD_IDS as readonly string[]).includes(value);
}

export function sectionDef(id: SectionId): SectionDef {
  return SECTIONS.find((s) => s.id === id)!;
}

/** La seccion de una vista (null: Ajustes). */
export function sectionOf(view: ViewId): SectionId | null {
  return VIEWS[view].section;
}

/** Las vistas de una seccion que la persona puede ver. */
export function visibleViews(section: SectionId, can: (permission?: string) => boolean): ViewId[] {
  return sectionDef(section).views.filter((v) => can(VIEWS[v].requires));
}

/** Las secciones que salen en la navegacion: las que tienen alguna vista para la persona. */
export function visibleSections(can: (permission?: string) => boolean): SectionId[] {
  return SECTIONS.filter((s) => visibleViews(s.id, can).length > 0).map((s) => s.id);
}

/** Una vista va sin id; una ficha, con su id (y un trimestre, solo uno que existe). */
export function isValidRoute(route: Route): boolean {
  if (isViewId(route.screen)) return route.id === undefined;
  if (isRecordId(route.screen)) {
    if (typeof route.id !== 'number' || !Number.isSafeInteger(route.id) || route.id <= 0) return false;
    return route.screen !== 'vat-quarter' || idToQuarter(route.id) !== null;
  }
  return false;
}

/** La ruta de una ficha. */
export function recordRoute(screen: RecordId, id: number): Route {
  return { screen, id };
}

/** La ruta de una vista. */
export function viewRoute(view: ViewId): Route {
  return { screen: view };
}

/** Una clave estable para una ruta: lo que recuerda una vista (filtros) y el titulo de una
 *  ficha van con ella. */
export function routeKey(route: Route): string {
  return route.id === undefined ? route.screen : `${route.screen}:${route.id}`;
}

/** Si dos rutas ensenan lo mismo. */
export function sameRoute(a: Route, b: Route): boolean {
  return a.screen === b.screen && (a.id ?? null) === (b.id ?? null);
}
