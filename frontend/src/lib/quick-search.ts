// Buscar y abrir (paso 16): lo que usan la caja del inicio y Ctrl+K. Busca pantallas por su
// nombre (en los tres idiomas: quien escribe "btw" en castellano tambien llega), clientes,
// proveedores, Objects y PO en sus listas, y facturas en /api/v2/buscar. No contesta
// preguntas ni inventa nada: cada resultado es una pantalla o una ficha que existe, y abrirlo
// es ir alli. Los nombres y numeros vienen de los datos: se pintan como texto.
import { LANGS, MESSAGES, type Messages } from '@/i18n';
import { RECORDS, VIEWS, VIEW_IDS, sectionOf, type Route, type ViewId } from '@/screens/registry';
import type { ApiClient, InvoiceRow } from './api';
import { paths } from './api';
import type { ObjectRow, PartyRow, PoRow } from './api-types';
import { formatMoney } from './format';
import { fold, matches } from './text';

export type ResultKind = 'screens' | 'clients' | 'providers' | 'objects' | 'pos' | 'invoices';
export const RESULT_KINDS: readonly ResultKind[] = ['screens', 'clients', 'providers', 'objects', 'pos', 'invoices'];

export interface QuickResult {
  kind: ResultKind;
  key: string;
  /** Lo principal: el nombre de la pantalla, de la empresa, el numero. */
  label: string;
  /** Debajo, en gris: la seccion, la empresa de una factura... */
  detail?: string;
  /** La vista donde se abre (la raiz del camino). */
  view: ViewId;
  /** Lo que se abre (la misma vista, o una ficha dentro de ella). */
  route: Route;
}

export interface QuickSources {
  clients: Pick<PartyRow, 'id' | 'nombre' | 'exact_id'>[];
  providers: Pick<PartyRow, 'id' | 'nombre' | 'exact_id'>[];
  objects: Pick<ObjectRow, 'id' | 'codigo' | 'nombre' | 'cliente'>[];
  pos: Pick<PoRow, 'id' | 'numero' | 'lado' | 'parte'>[];
}

const LIMIT = { screens: 6, clients: 5, providers: 5, objects: 4, pos: 4, invoices: 8 } as const;

/** El nombre de una vista y donde vive ("Inkooporders · van klanten", en Te ontvangen). */
export function viewTitle(view: ViewId, t: Messages): { label: string; detail?: string } {
  const nav = t.nav[view];
  const section = sectionOf(view);
  const where = section ? t.areas[section].label : undefined;
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

/** Las pantallas cuyo nombre (o el de su seccion) se parece a lo buscado, en cualquier idioma;
 *  primero las que mas se parecen. */
export function screenResults(query: string, t: Messages, can: (permission?: string) => boolean): QuickResult[] {
  if (!fold(query).trim()) return [];
  const scored: { result: QuickResult; score: number }[] = [];
  VIEW_IDS.forEach((view) => {
    if (!can(VIEWS[view].requires)) return;
    const section = sectionOf(view);
    const names = LANGS.flatMap((lang) => {
      const m = MESSAGES[lang];
      return [m.nav[view].label, m.nav[view].hint, section ? m.areas[section].label : ''];
    });
    const score = Math.max(...names.map((name) => nameScore(query, name)));
    if (score > 0) scored.push({ result: { kind: 'screens', key: `screen:${view}`, ...viewTitle(view, t), view, route: { screen: view } }, score });
  });
  // De mas a menos parecido; a igualdad, en el orden de las secciones.
  return scored
    .sort((a, b) => b.score - a.score)
    .slice(0, LIMIT.screens)
    .map((s) => s.result);
}

/** Clientes, proveedores, Objects y PO de sus listas (ya cargadas). */
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
      view: 'clients',
      route: { screen: 'client', id: c.id },
    }));
  const providers = sources.providers
    .filter((p) => matches(query, p.nombre, p.exact_id))
    .slice(0, LIMIT.providers)
    .map<QuickResult>((p) => ({
      kind: 'providers',
      key: `provider:${p.id}`,
      label: p.nombre,
      detail: t.records.provider.label,
      view: 'providers',
      route: { screen: 'provider', id: p.id },
    }));
  const objects = sources.objects
    .filter((o) => matches(query, o.codigo, o.nombre))
    .slice(0, LIMIT.objects)
    .map<QuickResult>((o) => ({
      kind: 'objects',
      key: `object:${o.id}`,
      label: o.nombre ? `${o.codigo} · ${o.nombre}` : o.codigo,
      detail: o.cliente ?? t.records.object.label,
      view: RECORDS.object.view,
      route: { screen: 'object', id: o.id },
    }));
  const pos = sources.pos
    .filter((p) => matches(query, p.numero, p.parte.nombre))
    .slice(0, LIMIT.pos)
    .map<QuickResult>((p) => ({
      kind: 'pos',
      key: `po:${p.id}`,
      label: p.numero,
      detail: p.parte.nombre ?? t.records['purchase-order'].label,
      view: p.lado === 'proveedor' ? 'provider-pos' : 'client-pos',
      route: { screen: 'purchase-order', id: p.id },
    }));
  return [...clients, ...providers, ...objects, ...pos];
}

/** Una factura encontrada, abierta desde la lista de su sentido. */
export function invoiceResult(f: Pick<InvoiceRow, 'id' | 'numero' | 'sentido' | 'contraparte' | 'total_cent'>, t: Messages): QuickResult {
  const party = f.contraparte ?? '';
  const amount = f.total_cent === null ? '' : formatMoney(f.total_cent);
  return {
    kind: 'invoices',
    key: `invoice:${f.id}`,
    label: f.numero ?? `${t.records.invoice.label} ${f.id}`,
    detail: [party, amount].filter(Boolean).join(' · '),
    view: f.sentido === 'entrante' ? 'invoices-in' : 'invoices-out',
    route: { screen: 'invoice', id: f.id },
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
