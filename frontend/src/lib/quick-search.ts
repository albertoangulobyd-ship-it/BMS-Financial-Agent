// Buscar y abrir (pasos 16 y 17): lo que usa la conversacion (aurora/assistant.ts). Busca los
// sitios de la app por su nombre (en los tres idiomas: quien escribe "btw" en castellano tambien
// llega), clientes, proveedores, Objects y PO en sus listas, y facturas en /api/v2/buscar. No
// contesta preguntas ni inventa nada: cada resultado es un sitio que existe, y abrirlo es ir
// alli. Desde el paso 17 los sitios son los de Aurora (especificacion §2.6): el panel de una
// entrada con la vista de un grupo abierta, la busqueda con sus filtros (E5-p), Documentos (una
// categoria, una carpeta, una hoja) o Procesar. Los nombres y numeros vienen de los datos: se
// pintan como texto.
import { DOCS_ROOT, folderPlace, invoicePlace, type DocsPlace, type PanelEntry, type SearchPreset } from '@/aurora/estado';
import { LANGS, MESSAGES, type Messages } from '@/i18n';
import type { ApiClient, InvoiceRow } from './api';
import { paths } from './api';
import type { ObjectRow, PartyRow, PoRow } from './api-types';
import { formatMoney } from './format';
import { fold, matches } from './text';

/** Los sitios que se pueden abrir por su nombre (los de las pantallas de antes). */
export const PLACE_IDS = [
  'home',
  'work-queue',
  'exceptions',
  'iban-checks',
  'cash-flow',
  'receivables',
  'invoices-out',
  'bank-in',
  'clients',
  'objects',
  'client-pos',
  'import',
  'payables',
  'invoices-in',
  'bank-out',
  'providers',
  'provider-pos',
  'documents',
  'read-invoices',
  'vat',
  'settings',
] as const;
export type PlaceId = (typeof PLACE_IDS)[number];

/** Donde se abre algo: un panel (con la vista de un grupo), la busqueda, Documentos o Procesar. */
export type PlaceTarget =
  | { kind: 'panel'; entry: PanelEntry; view?: string }
  | { kind: 'search'; preset: SearchPreset }
  | { kind: 'documents'; place: DocsPlace }
  | { kind: 'process' };

type Area = 'home' | 'receivables' | 'payables' | 'documents' | 'process' | 'vat';

const PLACES: Readonly<Record<PlaceId, { target: PlaceTarget; area: Area | null; requires?: string }>> = {
  home: { target: { kind: 'panel', entry: 'home' }, area: 'home' },
  'work-queue': { target: { kind: 'panel', entry: 'home', view: 'queue' }, area: 'home' },
  exceptions: { target: { kind: 'panel', entry: 'home', view: 'exceptions' }, area: 'home' },
  'iban-checks': { target: { kind: 'panel', entry: 'home', view: 'iban' }, area: 'home' },
  'cash-flow': { target: { kind: 'panel', entry: 'home', view: 'cashflow' }, area: 'home' },
  receivables: { target: { kind: 'panel', entry: 'receivables' }, area: 'receivables' },
  'invoices-out': { target: { kind: 'search', preset: { sentido: 'saliente' } }, area: 'receivables' },
  'bank-in': { target: { kind: 'panel', entry: 'receivables', view: 'unmatched' }, area: 'receivables' },
  clients: { target: { kind: 'documents', place: { category: 'clients', folder: null, sheet: null } }, area: 'receivables' },
  objects: { target: { kind: 'documents', place: { category: 'clients', folder: null, sheet: null } }, area: 'receivables' },
  'client-pos': { target: { kind: 'documents', place: { category: 'clients', folder: null, sheet: null } }, area: 'receivables' },
  import: { target: { kind: 'panel', entry: 'receivables', view: 'import' }, area: 'receivables', requires: 'importar_datos' },
  payables: { target: { kind: 'panel', entry: 'payables' }, area: 'payables' },
  'invoices-in': { target: { kind: 'search', preset: { sentido: 'entrante' } }, area: 'payables' },
  'bank-out': { target: { kind: 'panel', entry: 'payables', view: 'unmatched' }, area: 'payables' },
  providers: { target: { kind: 'documents', place: { category: 'providers', folder: null, sheet: null } }, area: 'payables' },
  'provider-pos': { target: { kind: 'documents', place: { category: 'providers', folder: null, sheet: null } }, area: 'payables' },
  documents: { target: { kind: 'documents', place: DOCS_ROOT }, area: 'documents' },
  'read-invoices': { target: { kind: 'process' }, area: 'process', requires: 'importar_datos' },
  vat: { target: { kind: 'panel', entry: 'vat' }, area: 'vat' },
  settings: { target: { kind: 'panel', entry: 'settings' }, area: null },
};

export type ResultKind = 'screens' | 'clients' | 'providers' | 'objects' | 'pos' | 'invoices';

export interface QuickResult {
  kind: ResultKind;
  key: string;
  /** Lo principal: el nombre del sitio, de la empresa, el numero. */
  label: string;
  /** Debajo, en gris: donde vive, la empresa de una factura... */
  detail?: string;
  /** Donde se abre. */
  target: PlaceTarget;
}

export interface QuickSources {
  clients: Pick<PartyRow, 'id' | 'nombre' | 'exact_id'>[];
  providers: Pick<PartyRow, 'id' | 'nombre' | 'exact_id'>[];
  objects: Pick<ObjectRow, 'id' | 'codigo' | 'nombre' | 'cliente' | 'cliente_id'>[];
  pos: Pick<PoRow, 'id' | 'numero' | 'lado' | 'parte'>[];
}

const LIMIT = { screens: 6, clients: 5, providers: 5, objects: 4, pos: 4, invoices: 8 } as const;

/** El nombre de un sitio y donde vive ("Inkooporders · van klanten", en Te ontvangen). */
export function placeTitle(id: PlaceId, t: Messages): { label: string; detail?: string } {
  const nav = t.nav[id];
  const area = PLACES[id].area;
  const where = area ? t.areas[area].label : undefined;
  const label = nav.label;
  const detail = [nav.hint, where && where !== label ? where : ''].filter(Boolean).join(' · ');
  return detail ? { label, detail } : { label };
}

/** Cuanto se parece un nombre a lo buscado: igual (3), una palabra que empieza asi (2) o, con
 *  tres letras o mas, en medio (1: "iva" esta dentro de "receivables", pero cuenta menos). */
export function nameScore(query: string, name: string | null | undefined): number {
  const q = fold(query).trim();
  const f = fold(name).trim();
  if (!q || !f) return 0;
  if (f === q) return 3;
  if (f.split(/[\s\-·/()]+/).some((w) => w.startsWith(q))) return 2;
  return q.length >= 3 && matches(q, f) ? 1 : 0;
}

/** Los sitios cuyo nombre (o el de su entrada) se parece a lo buscado, en cualquier idioma;
 *  primero los que mas se parecen. */
export function screenResults(query: string, t: Messages, can: (permission?: string) => boolean): QuickResult[] {
  if (!fold(query).trim()) return [];
  const scored: { result: QuickResult; score: number }[] = [];
  PLACE_IDS.forEach((id) => {
    const place = PLACES[id];
    if (!can(place.requires)) return;
    const names = LANGS.flatMap((lang) => {
      const m = MESSAGES[lang];
      return [m.nav[id].label, m.nav[id].hint, place.area ? m.areas[place.area].label : ''];
    });
    const score = Math.max(...names.map((name) => nameScore(query, name)));
    if (score > 0) scored.push({ result: { kind: 'screens', key: `screen:${id}`, ...placeTitle(id, t), target: place.target }, score });
  });
  // De mas a menos parecido; a igualdad, en el orden de las entradas.
  return scored
    .sort((a, b) => b.score - a.score)
    .slice(0, LIMIT.screens)
    .map((s) => s.result);
}

/** Clientes, proveedores, Objects y PO de sus listas (ya cargadas): su carpeta en Documentos,
 *  y la hoja de un Object o de una PO en la carpeta de su empresa. */
export function recordResults(query: string, sources: QuickSources, t: Messages): QuickResult[] {
  if (!fold(query).trim()) return [];
  const clients = sources.clients
    .filter((c) => matches(query, c.nombre, c.exact_id))
    .slice(0, LIMIT.clients)
    .map<QuickResult>((c) => ({
      kind: 'clients',
      key: `client:${c.id}`,
      label: c.nombre,
      detail: t.records.client.label,
      target: { kind: 'documents', place: folderPlace('client', c.id) },
    }));
  const providers = sources.providers
    .filter((p) => matches(query, p.nombre, p.exact_id))
    .slice(0, LIMIT.providers)
    .map<QuickResult>((p) => ({
      kind: 'providers',
      key: `provider:${p.id}`,
      label: p.nombre,
      detail: t.records.provider.label,
      target: { kind: 'documents', place: folderPlace('provider', p.id) },
    }));
  const objects = sources.objects
    .filter((o) => matches(query, o.codigo, o.nombre))
    .slice(0, LIMIT.objects)
    .map<QuickResult>((o) => ({
      kind: 'objects',
      key: `object:${o.id}`,
      label: o.nombre ? `${o.codigo} · ${o.nombre}` : o.codigo,
      detail: o.cliente ?? t.records.object.label,
      target: {
        kind: 'documents',
        place: o.cliente_id ? folderPlace('client', o.cliente_id, { kind: 'object', id: o.id }) : { ...DOCS_ROOT, sheet: { kind: 'object', id: o.id } },
      },
    }));
  const pos = sources.pos
    .filter((p) => matches(query, p.numero, p.parte.nombre))
    .slice(0, LIMIT.pos)
    .map<QuickResult>((p) => ({
      kind: 'pos',
      key: `po:${p.id}`,
      label: p.numero,
      detail: p.parte.nombre ?? t.records['purchase-order'].label,
      target: { kind: 'documents', place: folderPlace(p.lado === 'proveedor' ? 'provider' : 'client', p.parte.id, { kind: 'po', id: p.id }) },
    }));
  return [...clients, ...providers, ...objects, ...pos];
}

/** Una factura encontrada: su hoja, en la carpeta de su empresa (F3). */
export function invoiceResult(
  f: Pick<InvoiceRow, 'id' | 'numero' | 'sentido' | 'contraparte' | 'total_cent'> & Partial<Pick<InvoiceRow, 'cliente_id' | 'proveedor_id'>>,
  t: Messages
): QuickResult {
  const party = f.contraparte ?? '';
  const amount = f.total_cent === null ? '' : formatMoney(f.total_cent);
  return {
    kind: 'invoices',
    key: `invoice:${f.id}`,
    label: f.numero ?? `${t.records.invoice.label} ${f.id}`,
    detail: [party, amount].filter(Boolean).join(' · '),
    target: { kind: 'documents', place: invoicePlace(f) },
  };
}

/** Las facturas cuyo numero o empresa contiene lo buscado (la busqueda del motor). */
export async function invoiceResults(api: ApiClient, query: string, t: Messages): Promise<{ results: QuickResult[]; total: number }> {
  const q = query.trim();
  if (!q) return { results: [], total: 0 };
  const r = await api.get<{ busqueda: { total: number; facturas: InvoiceRow[] } }>(paths.search, {
    texto: q,
    limite: LIMIT.invoices,
  });
  return { results: r.busqueda.facturas.map((f) => invoiceResult(f, t)), total: r.busqueda.total };
}

/** Las listas de donde salen clientes, proveedores, Objects y PO (una vez por busqueda). */
export async function loadSources(api: ApiClient): Promise<QuickSources> {
  const [clients, providers, objects, pos] = await Promise.all([
    api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
    api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores),
    api.get<{ objetos: ObjectRow[] }>(paths.objects).then((r) => r.objetos),
    api.get<{ ordenes: PoRow[] }>(paths.purchaseOrders).then((r) => r.ordenes),
  ]);
  return { clients, providers, objects, pos };
}
