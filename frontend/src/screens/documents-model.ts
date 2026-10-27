// El archivo de Documentos sin React (paso 16): que carpetas salen y en que orden, que tipos
// de documento hay en una, el arbol "Verkennen" y de donde dice una factura que esta pagada.
// Todo sale de lo que ya contesta la API (/api/v2/clientes, /proveedores, /…/N/documentos y
// /facturas/N); aqui no se calcula ningun importe, solo se ordena y se elige. Lo prueba
// documents-model.test.ts.
import type { TreeNode } from '@/aurora/documents/tree-view';
import type { InvoiceDetail, PartyDocument, PartyRow } from '@/lib/api-types';
import { matches } from '@/lib/text';

export type Side = 'client' | 'provider';
/** Las pestanas de la rejilla: todas, solo clientes o solo proveedores. */
export type ArchiveTab = 'all' | 'clients' | 'providers';
export const ARCHIVE_TABS: readonly ArchiveTab[] = ['all', 'clients', 'providers'];

/** Cuantas carpetas salen antes de "Ver todas" (revision §4.14). */
export const FIRST_FOLDERS = 12;

export interface Folder {
  side: Side;
  row: PartyRow;
  /** "client:3": la carpeta en el arbol y en la memoria de la vista. */
  key: string;
}

export function folderKey(side: Side, id: number): string {
  return `${side}:${id}`;
}

export function tabOf(side: Side): ArchiveTab {
  return side === 'client' ? 'clients' : 'providers';
}

/** Primero lo que pide atencion: lo vencido (mas, antes), despues lo pendiente (mas, antes) y,
 *  a igualdad, el orden de la API (que ya es el de la prioridad). */
export function byAttention<T extends { row: Pick<PartyRow, 'vencido_cent' | 'pendiente_cent'> }>(list: readonly T[]): T[] {
  return list
    .map((item, index) => ({ item, index }))
    .sort(
      (a, b) =>
        Math.max(0, b.item.row.vencido_cent) - Math.max(0, a.item.row.vencido_cent) ||
        Math.max(0, b.item.row.pendiente_cent) - Math.max(0, a.item.row.pendiente_cent) ||
        a.index - b.index
    )
    .map((x) => x.item);
}

/** Todas las carpetas (clientes y proveedores), en el orden de la atencion. */
export function allFolders(clients: readonly PartyRow[], providers: readonly PartyRow[]): Folder[] {
  return byAttention([
    ...clients.map((row) => ({ side: 'client' as const, row, key: folderKey('client', row.id) })),
    ...providers.map((row) => ({ side: 'provider' as const, row, key: folderKey('provider', row.id) })),
  ]);
}

/** Las de una pestana que cumplen la busqueda (nombre o codigo de Exact, sin mayusculas ni
 *  acentos). */
export function shownFolders(folders: readonly Folder[], tab: ArchiveTab, query: string): Folder[] {
  return folders.filter((f) => (tab === 'all' || tabOf(f.side) === tab) && matches(query, f.row.nombre, f.row.exact_id));
}

/** Las primeras doce, salvo que se pidan todas o que la abierta este mas abajo (se ve
 *  siempre). `hidden` es cuantas quedan detras de "Ver todas". */
export function firstFolders(folders: readonly Folder[], showAll: boolean, activeKey: string | null): { shown: Folder[]; hidden: number } {
  const activeAt = activeKey ? folders.findIndex((f) => f.key === activeKey) : -1;
  if (showAll || folders.length <= FIRST_FOLDERS || activeAt >= FIRST_FOLDERS) return { shown: [...folders], hidden: 0 };
  return { shown: folders.slice(0, FIRST_FOLDERS), hidden: folders.length - FIRST_FOLDERS };
}

export function countBySide(folders: readonly Folder[]): Record<ArchiveTab, number> {
  const clients = folders.filter((f) => f.side === 'client').length;
  return { all: folders.length, clients, providers: folders.length - clients };
}

// ------------------------------------------------------------ los documentos de una carpeta

/** Los tipos que el archivo conoce, en el orden en que salen en el filtro. Los que hoy enlaza
 *  el motor (consultas._documentos) y dos que aun no: la autofactura de TRNSPRNT y el
 *  extracto del banco (es de la empresa, no de una relacion). El filtro solo ensena los que
 *  hay en la carpeta. */
export const DOC_TYPES = [
  'factura_compra',
  'factura_venta',
  'abono_compra',
  'abono_venta',
  'autofactura',
  'justificante_pago',
  'orden_compra',
  'modificacion_po',
  'extracto',
] as const;

/** Una fila por enlace: el mismo documento puede salir dos veces (dos registros lo enlazan). */
export function docKey(d: Pick<PartyDocument, 'id' | 'vinculo'>): string {
  return `${d.id}-${d.vinculo.tabla}-${d.vinculo.id}`;
}

/** Los tipos que hay en una carpeta, con cuantos, en el orden de DOC_TYPES (uno que el
 *  archivo aun no conoce, al final). */
export function typesPresent(docs: readonly Pick<PartyDocument, 'tipo'>[]): { tipo: string; n: number }[] {
  const counts = new Map<string, number>();
  for (const d of docs) counts.set(d.tipo, (counts.get(d.tipo) ?? 0) + 1);
  const known: readonly string[] = DOC_TYPES;
  const rank = (tipo: string) => (known.includes(tipo) ? known.indexOf(tipo) : known.length);
  return [...counts.entries()].map(([tipo, n]) => ({ tipo, n })).sort((a, b) => rank(a.tipo) - rank(b.tipo));
}

export function byType<T extends Pick<PartyDocument, 'tipo'>>(docs: readonly T[], tipo: string | null): T[] {
  return tipo ? docs.filter((d) => d.tipo === tipo) : [...docs];
}

/** La factura de un documento: la suya (un original) o la del pago (un justificante). */
export function invoiceIdOf(d: Pick<PartyDocument, 'vinculo'>): number | null {
  if (typeof d.vinculo.factura_id === 'number') return d.vinculo.factura_id;
  return d.vinculo.tabla === 'factura' ? d.vinculo.id : null;
}

export function purchaseOrderIdOf(d: Pick<PartyDocument, 'vinculo'>): number | null {
  return typeof d.vinculo.orden_compra_id === 'number' ? d.vinculo.orden_compra_id : null;
}

/** Las hojas del abanico de una carpeta abierta: las cuatro mas recientes, con la mas nueva
 *  delante (la carpeta pinta encima la ultima de la lista). */
export function fanDocs<T>(docs: readonly T[]): T[] {
  return docs.slice(0, 4).reverse();
}

// ------------------------------------------------------------ pagada, segun quien

export interface PaidSource {
  /** Manda el banco, luego Exact, luego lo apuntado a mano (pagos.py). */
  source: 'banco' | 'exact' | 'manual';
  date: string | null;
  /** Apuntada a mano y el banco aun no la trae (lo que vigila K3). */
  notInBank: boolean;
  /** El aviso K3 abierto. */
  k3: boolean;
}

const SOURCE_RANK: Record<PaidSource['source'], number> = { banco: 0, exact: 1, manual: 2 };

/** De donde sale "pagada" (revision §1b, decision 11): el pago confirmado que manda, nunca
 *  solo la palabra. Null si no esta pagada o no hay ningun pago confirmado que lo diga. */
export function paidSource(detail: Pick<InvoiceDetail, 'estado' | 'pagos' | 'hallazgos'>): PaidSource | null {
  if (detail.estado?.estado_pago !== 'pagada') return null;
  const confirmed = (detail.pagos ?? []).filter(
    (p): p is typeof p & { fuente: PaidSource['source'] } => p.estado === 'confirmada' && p.fuente in SOURCE_RANK
  );
  if (confirmed.length === 0) return null;
  const best = [...confirmed].sort(
    (a, b) => SOURCE_RANK[a.fuente] - SOURCE_RANK[b.fuente] || (b.fecha_pago ?? '').localeCompare(a.fecha_pago ?? '')
  )[0]!;
  const k3 = detail.hallazgos.some((h) => h.regla === 'K3' && h.estado === 'abierto');
  return { source: best.fuente, date: best.fecha_pago, notInBank: best.fuente === 'manual', k3 };
}

// ------------------------------------------------------------ el arbol "Verkennen"

export type DocsEntry = { status: 'loading' } | { status: 'error'; error?: unknown } | { status: 'ready'; docs: PartyDocument[] };

export interface TreeTexts {
  home: string;
  all: string;
  clients: string;
  providers: string;
  loading: string;
  failed: string;
  docLabel: (d: PartyDocument) => string;
}

export const TREE_HOME = 'home';

/** Inicio; Documentos con los dos grupos; cada carpeta con lo que tiene. Los documentos de
 *  una carpeta se leen al abrirla en el arbol (cargando por partes): hasta entonces, una hoja
 *  que dice que carga. Una carpeta sin documentos es una hoja. */
export function archiveTree(folders: readonly Folder[], docs: ReadonlyMap<string, DocsEntry>, texts: TreeTexts): TreeNode[] {
  const total = folders.reduce((sum, f) => sum + (f.row.documentos ?? 0), 0);
  const group = (side: Side): TreeNode => {
    const mine = folders.filter((f) => f.side === side);
    return {
      id: tabOf(side),
      label: side === 'client' ? texts.clients : texts.providers,
      meta: String(mine.length),
      children: mine.map((f) => folderNode(f, docs.get(f.key), texts)),
    };
  };
  return [
    { id: TREE_HOME, label: texts.home },
    { id: 'all', label: texts.all, meta: String(total), children: [group('client'), group('provider')] },
  ];
}

function folderNode(f: Folder, entry: DocsEntry | undefined, texts: TreeTexts): TreeNode {
  const count = f.row.documentos ?? 0;
  const node: TreeNode = { id: f.key, label: f.row.nombre, proper: true, meta: String(entry?.status === 'ready' ? entry.docs.length : count) };
  if (entry?.status === 'ready') {
    if (entry.docs.length > 0) node.children = entry.docs.map((d) => ({ id: `${f.key}/${docKey(d)}`, label: texts.docLabel(d), proper: true }));
  } else if (count > 0) {
    node.children = [{ id: `${f.key}/…`, label: entry?.status === 'error' ? texts.failed : texts.loading }];
  }
  return node;
}

export type NodeTarget =
  | { kind: 'home' }
  | { kind: 'tab'; tab: ArchiveTab }
  | { kind: 'folder'; side: Side; id: number }
  | { kind: 'doc'; side: Side; id: number; doc: string }
  | { kind: 'none' };

/** Que abre un nodo del arbol. */
export function nodeTarget(nodeId: string): NodeTarget {
  if (nodeId === TREE_HOME) return { kind: 'home' };
  if ((ARCHIVE_TABS as readonly string[]).includes(nodeId)) return { kind: 'tab', tab: nodeId as ArchiveTab };
  const m = /^(client|provider):(\d+)(?:\/(.+))?$/.exec(nodeId);
  if (!m) return { kind: 'none' };
  const side = m[1] as Side;
  const id = Number(m[2]);
  if (!Number.isSafeInteger(id) || id <= 0) return { kind: 'none' };
  if (m[3] === undefined) return { kind: 'folder', side, id };
  return m[3] === '…' ? { kind: 'none' } : { kind: 'doc', side, id, doc: m[3] };
}

/** Lo que el arbol tiene abierto: lo que la persona abrio y, siempre, el camino hasta lo que
 *  se ve (como en Aurora: al abrir una carpeta se abre su rama). */
export function withAncestors(expanded: readonly string[], selected: string | null): string[] {
  const next = new Set(expanded);
  next.add('all');
  const target = selected ? nodeTarget(selected) : { kind: 'none' as const };
  if (target.kind === 'tab' && target.tab !== 'all') next.add(target.tab);
  if (target.kind === 'folder' || target.kind === 'doc') {
    next.add(tabOf(target.side));
    next.add(folderKey(target.side, target.id));
  }
  return [...next];
}
