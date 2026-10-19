// Que pantallas hay y como se llega a ellas. Las de la navegacion (con su grupo, su icono
// y el permiso que piden) y las fichas, que solo se abren desde una fila con su id. Una
// ruta guardada que no esta aqui no se abre (isValidRoute): asi lo que vuelve de
// localStorage nunca pide una pantalla que no existe.
import {
  Building2,
  ClipboardList,
  FileInput,
  FileOutput,
  FileText,
  Landmark,
  LayoutDashboard,
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
  type LucideIcon,
} from 'lucide-react';
import type { TabRoute } from '@/components/ui/sidebar-with-chrome-like-tabs';
import type { Messages } from '@/i18n';

export const NAV_IDS = [
  'overview',
  'work-queue',
  'exceptions',
  'iban-checks',
  'invoices-in',
  'invoices-out',
  'providers',
  'clients',
  'objects',
  'purchase-orders',
  'cash-flow',
  'vat',
  'import',
  'read-invoices',
  'settings',
] as const;
export type NavId = (typeof NAV_IDS)[number];

export const RECORD_IDS = ['invoice', 'provider', 'client', 'object', 'purchase-order'] as const;
export type RecordId = (typeof RECORD_IDS)[number];

export type ScreenId = NavId | RecordId;

export type GroupKey = keyof Messages['groups'];

export interface NavDef {
  id: NavId;
  group: GroupKey;
  icon: LucideIcon;
  /** El permiso que hace falta para ver la entrada (todas piden ver_facturas para entrar). */
  requires?: string;
}

export const NAV: readonly NavDef[] = [
  { id: 'overview', group: 'daily', icon: LayoutDashboard },
  { id: 'work-queue', group: 'daily', icon: ListChecks },
  { id: 'exceptions', group: 'daily', icon: TriangleAlert },
  { id: 'iban-checks', group: 'daily', icon: Landmark },
  { id: 'invoices-in', group: 'invoices', icon: FileInput },
  { id: 'invoices-out', group: 'invoices', icon: FileOutput },
  { id: 'providers', group: 'parties', icon: Truck },
  { id: 'clients', group: 'parties', icon: Users },
  { id: 'objects', group: 'parties', icon: MapPin },
  { id: 'purchase-orders', group: 'parties', icon: ClipboardList },
  { id: 'cash-flow', group: 'money', icon: Wallet },
  { id: 'vat', group: 'money', icon: Percent },
  { id: 'import', group: 'data', icon: Upload, requires: 'importar_datos' },
  { id: 'read-invoices', group: 'data', icon: ScanText, requires: 'importar_datos' },
  { id: 'settings', group: 'settings', icon: Settings },
];

export const RECORDS: Readonly<Record<RecordId, { icon: LucideIcon; nav: NavId }>> = {
  invoice: { icon: FileText, nav: 'work-queue' },
  provider: { icon: Truck, nav: 'providers' },
  client: { icon: Users, nav: 'clients' },
  object: { icon: Building2, nav: 'objects' },
  'purchase-order': { icon: ClipboardList, nav: 'purchase-orders' },
};

export const DEFAULT_SCREEN: NavId = 'overview';

export function isNavId(value: unknown): value is NavId {
  return typeof value === 'string' && (NAV_IDS as readonly string[]).includes(value);
}

export function isRecordId(value: unknown): value is RecordId {
  return typeof value === 'string' && (RECORD_IDS as readonly string[]).includes(value);
}

/** Una pantalla de la navegacion va sin id; una ficha, con su id; `from` es una entrada. */
export function isValidRoute(route: TabRoute): boolean {
  if (route.from !== undefined && !isNavId(route.from)) return false;
  if (isNavId(route.screen)) return route.id === undefined && route.from === undefined;
  if (isRecordId(route.screen)) {
    return typeof route.id === 'number' && Number.isSafeInteger(route.id) && route.id > 0;
  }
  return false;
}

/** La ruta de una ficha, abierta desde una entrada de la navegacion. */
export function recordRoute(screen: RecordId, id: number, from?: NavId): TabRoute {
  return from ? { screen, id, from } : { screen, id };
}
