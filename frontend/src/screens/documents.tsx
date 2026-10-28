// Documentos (paso 16): el archivo de Aurora, como lo diseno el dueno, con los datos de verdad
// (revision §8.5). Una carpeta de cristal por cliente y por proveedor, primero lo que pide
// atencion (lo vencido, luego lo pendiente), las doce primeras y "Ver todas", el buscador de
// carpetas y las pestanas Todas / Clientes / Proveedores; a la izquierda el arbol "Explorar",
// que se maneja entero con el teclado y lee los documentos de una carpeta al abrirla. Una
// carpeta abierta (su ficha: client-documents o provider-documents, con sus migas y "Volver")
// ensena arriba la ficha de solo lectura y sus documentos, y abre la vista previa: la hoja
// dibujada desde el registro, con "Descargar el original" (cada descarga queda en la auditoria
// como documento_abierto). Lo que el sistema enlaza es lo de la decision 7: originales de
// facturas y abonos, justificantes de pago y hojas de PO; los contratos, mas adelante. Ni
// "Agregar muestra" ni nada que cree un documento. Los nombres, numeros y ficheros vienen de
// los datos: se pintan como texto.
import { Download } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  ArchiveEmpty,
  ArchiveHeading,
  ArchiveLayout,
  ArchiveSearch,
  ArchiveTabs,
  CLIENT_ART,
  DocumentPreview,
  FileTable,
  FolderCell,
  FolderGrid,
  FolderProfile,
  PROVIDER_ART,
  type ArchiveFact,
  type ArchiveFile,
} from '@/aurora/documents/archive';
import { hashString, type FolderFile } from '@/aurora/documents/glass-folder';
import { MeerkatScene } from '@/aurora/meerkat/meerkat-scene';
import { Screen, useDocumentTitle } from '@/components/page-header';
import { ErrorState, Loading, TechnicalDetail, errorMessage } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import { Money } from '@/components/values';
import { countText, fmt, useT, type Messages } from '@/i18n';
import { paymentStateLabel, ruleText, stateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { InvoiceDetail, PartyDocument, PartyDocuments, PartyRow, PartyView } from '@/lib/api-types';
import { NO_VALUE, formatDate, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { twinMarks } from '@/lib/twins';
import { useSession, type Session } from '@/lib/session';
import { rememberView, useViewState } from '@/lib/view-memory';
import { partyWhy } from '@/lib/why';
import { useNav } from '@/shell/navigation';
import { useAurora } from '@/aurora/root';
import { useBackToAurora } from '@/aurora/work-screen';
import {
  ARCHIVE_TABS,
  allFolders,
  archiveTree,
  byType,
  countBySide,
  docKey,
  fanDocs,
  firstFolders,
  folderKey,
  invoiceIdOf,
  nodeTarget,
  paidSource,
  purchaseOrderIdOf,
  shownFolders,
  tabOf,
  typesPresent,
  withAncestors,
  type ArchiveTab,
  type DocsEntry,
  type Folder,
  type Side,
} from './documents-model';
import { formatSize } from './import';
import { isViewId, recordRoute, routeKey, type Route } from './registry';
import { useLoad } from './use-load';

/** Lo que el archivo recuerda mientras la app esta abierta (la pestana, la busqueda, "Ver
 *  todas", lo abierto del arbol): lo mismo en la rejilla y dentro de una carpeta. */
const SCOPE = 'documents';

export function DocumentsScreen({ navKey }: { navKey: string }) {
  return <Archive navKey={navKey} folder={null} />;
}

export function PartyDocumentsScreen({ kind, id, navKey }: { kind: Side; id: number; navKey: string }) {
  return <Archive navKey={navKey} folder={{ side: kind, id }} />;
}

function folderRoute(side: Side, id: number): Route {
  return recordRoute(side === 'client' ? 'client-documents' : 'provider-documents', id);
}

function typeLabel(t: Messages, tipo: string): string {
  return (t.documents.types as Record<string, string>)[tipo] ?? tipo;
}

function docName(t: Messages, d: PartyDocument): string {
  return d.numero ? `${typeLabel(t, d.tipo)} ${d.numero}` : typeLabel(t, d.tipo);
}

/** Una frase con un nombre de los datos dentro: el nombre, marcado como tal. */
function withName(template: string, name: string): ReactNode {
  const [before, after] = template.split('{name}');
  return (
    <>
      {before}
      <span data-proper-name=''>{name}</span>
      {after}
    </>
  );
}

// ------------------------------------------------------------ los documentos de cada carpeta
//
// Se leen por partes: al abrir una carpeta, al abrirla en el arbol o al pasar por encima de
// ella. Lo leido se guarda en memoria para la sesion (no en el navegador) y se vuelve a leer
// cuando cambia la version (despues de una orden).

interface CacheEntry {
  version: number;
  promise: Promise<PartyDocuments>;
  data?: PartyDocuments;
}

const docsCache = new WeakMap<Session, Map<string, CacheEntry>>();

function cacheOf(session: Session): Map<string, CacheEntry> {
  let byKey = docsCache.get(session);
  if (!byKey) {
    byKey = new Map();
    docsCache.set(session, byKey);
  }
  return byKey;
}

function fetchDocs(session: Session, version: number, side: Side, id: number): CacheEntry {
  const byKey = cacheOf(session);
  const key = folderKey(side, id);
  const hit = byKey.get(key);
  if (hit && hit.version === version) return hit;
  const promise = session.api
    .get<{ documentos: PartyDocuments }>(side === 'client' ? paths.clientDocuments(id) : paths.providerDocuments(id))
    .then((r) => r.documentos);
  // Lo de antes se queda a la vista mientras llega lo nuevo.
  const entry: CacheEntry = { version, promise, data: hit?.data };
  promise.then(
    (data) => {
      entry.data = data;
    },
    () => {
      if (byKey.get(key) === entry) byKey.delete(key);
    }
  );
  byKey.set(key, entry);
  return entry;
}

function useFolderDocs(): [ReadonlyMap<string, DocsEntry>, (side: Side, id: number, again?: boolean) => void] {
  const { session } = useSession();
  const { version } = useRefresh();
  const [store, setStore] = useState<ReadonlyMap<string, DocsEntry>>(() => {
    const seed = new Map<string, DocsEntry>();
    if (session) for (const [key, entry] of cacheOf(session)) if (entry.data) seed.set(key, { status: 'ready', docs: entry.data.documentos });
    return seed;
  });
  const asked = useRef(new Map<string, number>());
  const put = (key: string, value: DocsEntry) =>
    setStore((prev) => {
      const next = new Map(prev);
      next.set(key, value);
      return next;
    });
  const ensure = useCallback(
    (side: Side, id: number, again = false) => {
      if (!session) return;
      const key = folderKey(side, id);
      if (!again && asked.current.get(key) === version) return;
      asked.current.set(key, version);
      const entry = fetchDocs(session, version, side, id);
      if (entry.data) put(key, { status: 'ready', docs: entry.data.documentos });
      else setStore((prev) => (prev.get(key)?.status === 'ready' ? prev : new Map(prev).set(key, { status: 'loading' })));
      entry.promise.then(
        (data) => put(key, { status: 'ready', docs: data.documentos }),
        (error: unknown) => {
          asked.current.delete(key);
          put(key, { status: 'error', error });
        }
      );
    },
    [session, version]
  );
  return [store, ensure];
}

// ------------------------------------------------------------ el archivo

function Archive({ navKey, folder }: { navKey: string; folder: { side: Side; id: number } | null }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const nav = useNav();
  const { dispatch } = useAurora();
  const backToAurora = useBackToAurora();
  const [lists, retryLists] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
        session!.api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores),
      ]),
    [session, version]
  );
  const [tab, setTab] = useViewState<ArchiveTab>(SCOPE, 'tab', 'all');
  const [query, setQuery] = useViewState<string>(SCOPE, 'query', '');
  const [showAll, setShowAll] = useViewState<boolean>(SCOPE, 'all', false);
  const [expanded, setExpanded] = useViewState<string[]>(SCOPE, 'tree', ['all', 'clients', 'providers']);
  const [preview, setPreview] = useViewState<string | null>(navKey, 'preview', null);
  const [docs, ensureDocs] = useFolderDocs();
  const activeKey = folder ? folderKey(folder.side, folder.id) : null;
  const active = activeKey ? docs.get(activeKey) : undefined;

  const folders = useMemo(() => (lists.status === 'ready' ? allFolders(lists.data[0], lists.data[1]) : []), [lists]);
  const activeFolder = activeKey ? folders.find((f) => f.key === activeKey) : undefined;

  // Lo que lee una carpeta abierta y lo abierto en el arbol.
  useEffect(() => {
    if (folder) ensureDocs(folder.side, folder.id);
  }, [folder?.side, folder?.id, ensureDocs]);
  useEffect(() => {
    for (const id of expanded) {
      const target = nodeTarget(id);
      if (target.kind === 'folder') ensureDocs(target.side, target.id);
    }
  }, [expanded, ensureDocs]);

  // Una vista previa pedida que ya no esta en la carpeta (se leyo de nuevo) se olvida.
  const previewDoc = preview && active?.status === 'ready' ? (active.docs.find((d) => docKey(d) === preview) ?? null) : null;
  useEffect(() => {
    if (preview && active?.status === 'ready' && !previewDoc) setPreview(null);
  }, [preview, active, previewDoc, setPreview]);

  const selectedNode = previewDoc && activeKey ? `${activeKey}/${preview}` : (activeKey ?? tab);
  // Al llegar, el camino hasta lo que se ve queda abierto en el arbol (como en Aurora).
  useEffect(() => {
    const next = withAncestors(expanded, selectedNode);
    if (next.length !== expanded.length) setExpanded(next);
    // Solo al cambiar lo que se ve: despues, la persona abre y cierra lo que quiera.
  }, [selectedNode]);

  const profileTitleId = 'docs-profile';
  const focusProfile = () => {
    const el = document.getElementById(`${profileTitleId}-title`);
    if (!el) return;
    el.focus({ preventScroll: true });
    el.scrollIntoView({ block: 'center' });
  };

  const openFolder = (side: Side, id: number, focus = false) => {
    if (tab !== 'all' && tab !== tabOf(side)) setTab(tabOf(side));
    if (activeKey === folderKey(side, id)) {
      if (focus) focusProfile();
      return;
    }
    nav.openFrom('documents', folderRoute(side, id));
  };
  const toRoot = () => {
    const previous = nav.trail[nav.trail.length - 2];
    if (folder && previous && isViewId(previous.screen) && previous.screen === 'documents') nav.back();
    else nav.go('documents');
  };
  const openPreview = (side: Side, id: number, key: string) => {
    if (activeKey === folderKey(side, id)) {
      setPreview(key);
      return;
    }
    rememberView(routeKey(folderRoute(side, id)), 'preview', key);
    openFolder(side, id);
  };
  const onTreeSelect = (nodeId: string) => {
    const target = nodeTarget(nodeId);
    // El nodo "Inicio" del arbol vuelve al inicio de Aurora sin vuelo (como en Aurora).
    if (target.kind === 'home') dispatch({ type: 'home' });
    else if (target.kind === 'tab') {
      setTab(target.tab);
      if (folder) toRoot();
    } else if (target.kind === 'folder') openFolder(target.side, target.id);
    else if (target.kind === 'doc') openPreview(target.side, target.id, target.doc);
  };

  const partyName = activeFolder?.row.nombre ?? null;
  const title = folder ? (activeFolder ? fmt(t.documents.folderOf, { name: activeFolder.row.nombre }) : fmt(t.records[folder.side === 'client' ? 'client-documents' : 'provider-documents'].fallbackTitle, { id: folder.id })) : t.nav.documents.label;
  useDocumentTitle(title);
  useEffect(() => {
    if (activeFolder) nav.setTitle(navKey, activeFolder.row.nombre);
  }, [activeFolder?.row.nombre, navKey, nav.setTitle]);

  const heading = (
    <ArchiveHeading
      eyebrow={t.documents.eyebrow}
      title={folder && activeFolder ? withName(t.documents.folderOf, activeFolder.row.nombre) : title}
      description={
        folder ? (folder.side === 'client' ? t.documents.questionClient : t.documents.questionProvider) : t.nav.documents.description
      }
      onHome={backToAurora}
    />
  );

  const tree =
    lists.status === 'ready'
      ? {
          nodes: archiveTree(folders, docs, {
            home: t.areas.home.label,
            all: t.nav.documents.label,
            clients: t.documents.clients,
            providers: t.documents.providers,
            loading: t.common.loading,
            failed: t.documents.treeFailed,
            docLabel: (d: PartyDocument) => docName(t, d),
          }),
          expanded,
          onExpandedChange: setExpanded,
          selected: selectedNode,
          onSelectedChange: onTreeSelect,
        }
      : null;

  return (
    <Screen calm>
      <ArchiveLayout
        heading={heading}
        tree={tree}
        hint={[t.documents.hint1, t.documents.hint2]}
        top={
          folder && (
            <FolderPanel
              key={activeKey}
              side={folder.side}
              id={folder.id}
              row={activeFolder}
              entry={active}
              titleId={profileTitleId}
              onPreview={setPreview}
              onRetryDocs={() => ensureDocs(folder.side, folder.id, true)}
            />
          )
        }
      >
        {lists.status === 'loading' && <Loading />}
        {lists.status === 'error' && <ErrorState error={lists.error} onRetry={retryLists} />}
        {lists.status === 'ready' && (
          <Folders
            folders={folders}
            tab={tab}
            setTab={(next) => {
              setTab(next);
              if (folder) toRoot();
            }}
            query={query}
            setQuery={setQuery}
            showAll={showAll}
            setShowAll={setShowAll}
            activeKey={activeKey}
            docs={docs}
            onOpen={openFolder}
            onClose={toRoot}
            onPreview={openPreview}
            onWarm={ensureDocs}
          />
        )}
        <p className='ws-footnote'>{t.documents.later}</p>
      </ArchiveLayout>
      {folder && (
        <Preview
          doc={previewDoc}
          side={folder.side}
          partyName={partyName}
          onClose={() => setPreview(null)}
          onOpenInvoice={(invoiceId) => {
            setPreview(null);
            nav.open(recordRoute('invoice', invoiceId));
          }}
          onOpenPo={(poId) => {
            setPreview(null);
            nav.open(recordRoute('purchase-order', poId));
          }}
        />
      )}
    </Screen>
  );
}

// ------------------------------------------------------------ la rejilla

function Folders({
  folders,
  tab,
  setTab,
  query,
  setQuery,
  showAll,
  setShowAll,
  activeKey,
  docs,
  onOpen,
  onClose,
  onPreview,
  onWarm,
}: {
  folders: Folder[];
  tab: ArchiveTab;
  setTab: (tab: ArchiveTab) => void;
  query: string;
  setQuery: (query: string) => void;
  showAll: boolean;
  setShowAll: (all: boolean) => void;
  activeKey: string | null;
  docs: ReadonlyMap<string, DocsEntry>;
  onOpen: (side: Side, id: number, focus?: boolean) => void;
  onClose: () => void;
  onPreview: (side: Side, id: number, key: string) => void;
  onWarm: (side: Side, id: number) => void;
}) {
  const { t } = useT();
  if (folders.length === 0) {
    return <ArchiveEmpty mascot={<MeerkatScene label={t.aurora.meerkat} scale={3} />} title={t.empty.nothingHere} text={t.documents.noFolders} />;
  }
  const counts = countBySide(folders);
  const tabLabel: Record<ArchiveTab, string> = { all: t.documents.tabAll, clients: t.documents.clients, providers: t.documents.providers };
  const matching = shownFolders(folders, tab, query);
  const { shown, hidden } = firstFolders(matching, showAll, activeKey);
  return (
    <>
      <div className='ws-toolbar'>
        <ArchiveTabs
          label={t.documents.tabsLabel}
          items={ARCHIVE_TABS.map((id) => ({ id, label: tabLabel[id], count: counts[id] }))}
          value={tab}
          onChange={setTab}
        />
        <ArchiveSearch value={query} onChange={setQuery} label={t.documents.searchLabel} placeholder={t.documents.search} />
      </div>
      {shown.length === 0 ? (
        <ArchiveEmpty
          title={t.documents.noMatch}
          text={t.documents.noMatchText}
          action={
            query ? (
              <button type='button' onClick={() => setQuery('')}>
                {t.documents.clearSearch}
              </button>
            ) : undefined
          }
        />
      ) : (
        <FolderGrid label={tabLabel[tab]}>
          {shown.map((f, i) => {
            const entry = docs.get(f.key);
            const files: FolderFile[] =
              entry?.status === 'ready'
                ? fanDocs(entry.docs).map((d) => ({
                    id: docKey(d),
                    name: typeLabel(t, d.tipo),
                    meta: d.numero ?? undefined,
                    label: fmt(t.documents.previewNamed, { name: docName(t, d) }),
                  }))
                : [];
            return (
              <FolderCell
                key={f.key}
                kind={f.side === 'client' ? t.documents.kindClient : t.documents.kindProvider}
                index={i}
                name={f.row.nombre}
                files={files}
                total={entry?.status === 'ready' ? entry.docs.length : (f.row.documentos ?? 0)}
                art={f.side === 'client' ? CLIENT_ART : PROVIDER_ART}
                seed={hashString(f.key) % 997}
                balance={f.row.deuda_cent > 0 ? fmt(t.documents.outstanding, { amount: formatMoney(f.row.deuda_cent) }) : t.documents.nothingOpen}
                active={f.key === activeKey}
                accessory={f.row.nivel !== 'normal' ? <StatusPill group='prioridad' state={f.row.nivel} /> : undefined}
                onOpenChange={(open) => (open ? onOpen(f.side, f.row.id) : onClose())}
                onFileSelect={(file) => onPreview(f.side, f.row.id, file.id)}
                onOpenProfile={() => onOpen(f.side, f.row.id, true)}
                onWarm={(f.row.documentos ?? 0) > 0 ? () => onWarm(f.side, f.row.id) : undefined}
              />
            );
          })}
        </FolderGrid>
      )}
      {hidden > 0 && (
        <button type='button' className='ws-more' onClick={() => setShowAll(true)}>
          {fmt(t.documents.showAll, { n: matching.length })}
        </button>
      )}
    </>
  );
}

// ------------------------------------------------------------ la ficha de una carpeta abierta

function FolderPanel({
  side,
  id,
  row,
  entry,
  titleId,
  onPreview,
  onRetryDocs,
}: {
  side: Side;
  id: number;
  row: Folder | undefined;
  entry: DocsEntry | undefined;
  titleId: string;
  onPreview: (key: string) => void;
  onRetryDocs: () => void;
}) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const facts = useFactTools();
  const [view, retry] = useLoad(
    () =>
      side === 'provider'
        ? session!.api.get<{ proveedor: PartyView }>(paths.provider(id)).then((r) => r.proveedor)
        : session!.api.get<{ cliente: PartyView }>(paths.client(id)).then((r) => r.cliente),
    [session, side, id, version]
  );
  if (view.status === 'loading') return <Loading />;
  if (view.status === 'error') {
    return (
      <div className='mb-8'>
        <ErrorState error={view.error} onRetry={retry} />
      </div>
    );
  }
  const p = view.data;
  return (
    <FolderProfile
      id={titleId}
      eyebrow={side === 'client' ? t.documents.profileClient : t.documents.profileProvider}
      title={p.nombre}
      subtitle={[p.btw_id, p.exact_id ? `Exact ${p.exact_id}` : null].filter(Boolean).join(' · ') || undefined}
      facts={profileFacts(side, p, row?.row, facts)}
      footer={<FullCardLink side={side} id={id} />}
    >
      <FolderDocuments entry={entry} onPreview={onPreview} onRetry={onRetryDocs} />
    </FolderProfile>
  );
}

function FullCardLink({ side, id }: { side: Side; id: number }) {
  const { t } = useT();
  const nav = useNav();
  // La ficha completa vive en su seccion (Te ontvangen › Klanten, Te betalen › Leveranciers),
  // como desde Ctrl+K.
  return (
    <button type='button' className='ws-link' onClick={() => nav.openFrom(side === 'client' ? 'clients' : 'providers', recordRoute(side, id))}>
      {t.documents.fullCard} ↗
    </button>
  );
}

/** Lo que hace falta para escribir la ficha (los textos y la navegacion). */
function useFactTools() {
  const { t, lang } = useT();
  const nav = useNav();
  return { t, lang, nav };
}

/** Los datos de la ficha, de solo lectura: lo de la API, nada calculado aqui. */
function profileFacts(side: Side, p: PartyView, row: PartyRow | undefined, { t, lang, nav }: ReturnType<typeof useFactTools>): ArchiveFact[] {
  const why = partyWhy({ razones: row?.razones, vencido_cent: p.vencido_cent }, lang, t, (cents) =>
    fmt(t.parties.overdue, { amount: formatMoney(cents) })
  );
  const paid = p.plazo_de_pago;
  const pays =
    paid.pagadas === 0 || paid.media_dias === null
      ? t.documents.paysNone
      : paid.tarde > 0
        ? fmt(t.documents.paysAfter, { days: countText(t, 'days', paid.media_dias), late: countText(t, 'times', paid.tarde) })
        : fmt(t.documents.paysAfterOnTime, { days: countText(t, 'days', paid.media_dias) });
  const facts: ArchiveFact[] = [
    { label: t.documents.exactCode, value: p.exact_id ?? NO_VALUE, data: true },
    { label: t.documents.btwId, value: p.btw_id ?? NO_VALUE, data: true },
    { label: t.documents.kvk, value: p.kvk ?? NO_VALUE, data: true },
    {
      label: t.parties.paymentTerm,
      value: p.plazo_pago_dias !== null ? countText(t, 'days', p.plazo_pago_dias) : t.common.unknown,
    },
    {
      label: t.parties.outstanding,
      value: (
        <>
          <Money cents={p.deuda_cent} />
          <small>{fmt(p.abiertas === 1 ? t.parties.openInvoicesCountOne : t.parties.openInvoicesCount, { n: p.abiertas })}</small>
          {p.abonos_sin_enlazar_cent !== 0 && (
            <small data-testid='unlinked-credit'>
              {p.abonos_sin_enlazar_facturas > 1
                ? fmt(t.parties.unlinkedCreditMany, { n: p.abonos_sin_enlazar_facturas, amount: formatMoney(p.abonos_sin_enlazar_cent) })
                : fmt(t.parties.unlinkedCredit, { amount: formatMoney(p.abonos_sin_enlazar_cent) })}
            </small>
          )}
        </>
      ),
    },
    {
      label: t.parties.overdueColumn,
      value: (
        <>
          <Money cents={p.vencido_cent} className={p.vencido_cent > 0 ? 'text-late-foreground' : undefined} />
          {p.vencidas > 0 && <small>{fmt(p.vencidas === 1 ? t.parties.overdueCountOne : t.parties.overdueCount, { n: p.vencidas })}</small>}
        </>
      ),
    },
    { label: side === 'client' ? t.documents.paysClient : t.documents.paysProvider, value: pays },
    {
      label: t.columns.priority,
      value: (
        <>
          <StatusPill group='prioridad' state={p.prioridad.nivel} />
          {why && <small>{why.text}</small>}
        </>
      ),
    },
  ];
  if (side === 'provider') {
    const accounts = p.ibanes?.registro ?? [];
    facts.push(
      {
        label: t.documents.account,
        value:
          accounts.length === 0 ? (
            t.documents.noAccounts
          ) : (
            <span className='flex flex-col gap-1.5'>
              {accounts.map((a) => (
                <span key={a.id} className='flex flex-wrap items-center gap-2'>
                  <span className='font-mono tracking-[0.02em]' data-proper-name=''>
                    {a.iban}
                  </span>
                  <StatusPill group='cuenta' state={a.estado} />
                </span>
              ))}
            </span>
          ),
      },
      {
        label: t.documents.phone,
        value: (
          <>
            {p.telefono_verificacion ? <span data-proper-name=''>{p.telefono_verificacion}</span> : t.parties.noPhone}
            <small>{t.documents.ibanReadOnly}</small>
            <button type='button' className='ws-link mt-1' onClick={() => nav.go('iban-checks')}>
              {t.documents.toIbanChecks} ↗
            </button>
          </>
        ),
      }
    );
  } else {
    const objects = p.objetos ?? [];
    const orders = p.ordenes_compra ?? [];
    const work = p.trabajo_sin_facturar;
    facts.push(
      {
        label: t.nav.objects.label,
        value:
          objects.length === 0 ? (
            t.documents.noneShort
          ) : (
            <span className='ws-chips'>
              {objects.map((o) => (
                <button
                  key={o.id}
                  type='button'
                  className='ws-link'
                  onClick={() => nav.open(recordRoute('object', o.id))}
                  aria-label={fmt(t.common.openRecord, { what: `${t.records.object.label} ${o.codigo}` })}
                  title={o.nombre ?? undefined}
                >
                  <span data-proper-name=''>{o.codigo}</span>
                </button>
              ))}
            </span>
          ),
      },
      {
        label: t.documents.purchaseOrders,
        value:
          orders.length === 0 ? (
            t.documents.noneShort
          ) : (
            <span className='ws-chips'>
              {orders.map((o) => (
                <button
                  key={o.id}
                  type='button'
                  className='ws-link'
                  onClick={() => nav.open(recordRoute('purchase-order', o.id))}
                  aria-label={fmt(t.common.openRecord, { what: `${t.records['purchase-order'].label} ${o.numero}` })}
                >
                  <span data-proper-name=''>{o.numero}</span>
                </button>
              ))}
            </span>
          ),
      },
      {
        label: t.parties.unbilled,
        value:
          !work || work.estado !== 'ok' ? (
            t.parties.noPlanning
          ) : !work.valor_cent && !work.horas_mil ? (
            t.parties.nothingUnbilled
          ) : (
            <>
              <Money cents={work.valor_cent} />
              {work.estimado && <small>{t.parties.estimate}</small>}
            </>
          ),
      }
    );
  }
  const contact = p.contactos?.find((c) => c.activo) ?? p.contactos?.[0];
  if (contact?.nombre) {
    facts.push({
      label: t.documents.contact,
      value: (
        <>
          {contact.nombre}
          {contact.funcion && <small>{contact.funcion}</small>}
          {contact.email && <small>{contact.email}</small>}
        </>
      ),
      data: true,
    });
  }
  if (p.email_facturacion) facts.push({ label: t.documents.invoiceEmail, value: p.email_facturacion, data: true });
  return facts;
}

/** "Documentos de la carpeta": el filtro de tipo (solo los que hay) y una fila por
 *  documento, con su descarga al lado. */
function FolderDocuments({ entry, onPreview, onRetry }: { entry: DocsEntry | undefined; onPreview: (key: string) => void; onRetry: () => void }) {
  const { t } = useT();
  const [type, setType] = useState<string | null>(null);
  if (!entry || entry.status === 'loading') return <Loading />;
  if (entry.status === 'error') return <ErrorState error={entry.error} onRetry={onRetry} />;
  const docs = entry.docs;
  const present = typesPresent(docs);
  const chosen = type && present.some((p) => p.tipo === type) ? type : null;
  const listed = byType(docs, chosen);
  // Dos facturas con el mismo numero (la misma enviada dos veces): cada una con su "1 van 2".
  const twins = twinMarks(docs.filter((d) => d.vinculo.tabla === 'factura').map((d) => ({ id: d.vinculo.id, numero: d.numero, contraparte: d.tipo })));
  const files: ArchiveFile[] = listed.map((d) => {
    const name = docName(t, d);
    const twin = d.vinculo.tabla === 'factura' ? twins.get(d.vinculo.id) : undefined;
    return {
      id: docKey(d),
      name,
      meta:
        [formatDate(d.fecha), d.importe_cent !== null ? formatMoney(d.importe_cent) : null, twin ? fmt(t.common.twin, { n: twin.n, of: twin.of }) : null]
          .filter((s) => s && s !== NO_VALUE)
          .join(' · ') || undefined,
      status: d.estado_pago ? <StatusPill group='pago' state={d.estado_pago} /> : undefined,
      label: fmt(t.documents.previewNamed, { name }),
      aside: <DownloadOriginal doc={d} name={name} compact />,
    };
  });
  return (
    <FileTable
      title={t.aurora.archive.folderDocuments}
      count={String(docs.length)}
      filter={
        present.length > 1 ? (
          <div role='group' aria-label={t.documents.typeFilter} className='ws-type-filter'>
            <button type='button' aria-pressed={chosen === null} onClick={() => setType(null)}>
              {t.documents.allTypes}
              <span className='ws-tab-count'>{docs.length}</span>
            </button>
            {present.map((p) => (
              <button key={p.tipo} type='button' aria-pressed={chosen === p.tipo} onClick={() => setType(p.tipo)}>
                {typeLabel(t, p.tipo)}
                <span className='ws-tab-count'>{p.n}</span>
              </button>
            ))}
          </div>
        ) : undefined
      }
      files={files}
      onOpenFile={(f) => onPreview(f.id)}
      empty={<ArchiveEmpty mascot={<MeerkatScene label={t.aurora.meerkat} scale={2} />} title={t.documents.empty} />}
    />
  );
}

/** Descargar el original (con fetch y el token; queda en la auditoria). Lo que no se guardo
 *  lo dice. */
function DownloadOriginal({ doc, name, compact = false }: { doc: PartyDocument; name: string; compact?: boolean }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!doc.guardado) {
    return compact ? (
      <span className='shrink-0 px-2 text-xs text-muted-foreground'>{t.documents.notKept}</span>
    ) : (
      <p className='ws-dialog-error text-muted-foreground'>{t.documents.notKept}</p>
    );
  }
  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      await session!.api.download(paths.documentOriginal(doc.id), doc.nombre ?? `${doc.numero ?? doc.id}.pdf`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const label = fmt(t.documents.downloadNamed, { name });
  return (
    <>
      {compact ? (
        <Button variant='ghost' size='icon' onClick={download} disabled={busy} aria-label={label} title={label} className='shrink-0'>
          <Download className='h-4 w-4' aria-hidden='true' />
        </Button>
      ) : (
        <Button onClick={download} disabled={busy} aria-label={label}>
          <Download className='mr-1.5 h-4 w-4' aria-hidden='true' />
          {t.documents.downloadOriginal}
        </Button>
      )}
      {error !== null && (
        <span role='alert' className='ws-dialog-error basis-full text-late-foreground'>
          {errorMessage(error, t, lang)}
          <TechnicalDetail error={error} />
        </span>
      )}
    </>
  );
}

// ------------------------------------------------------------ la vista previa

function Preview({
  doc,
  side,
  partyName,
  onClose,
  onOpenInvoice,
  onOpenPo,
}: {
  doc: PartyDocument | null;
  side: Side;
  partyName: string | null;
  onClose: () => void;
  onOpenInvoice: (invoiceId: number) => void;
  onOpenPo: (poId: number) => void;
}) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const invoiceId = doc && doc.vinculo.tabla === 'factura' ? invoiceIdOf(doc) : null;
  const [detail] = useLoad<InvoiceDetail | null>(
    () => (invoiceId ? session!.api.get<{ factura: InvoiceDetail }>(paths.invoice(invoiceId)).then((r) => r.factura) : Promise.resolve(null)),
    [session, invoiceId, version]
  );
  const name = doc ? docName(t, doc) : '';
  const facts: ArchiveFact[] = [];
  const actions: ReactNode[] = [];
  if (doc) {
    const linkedInvoice = invoiceIdOf(doc);
    const po = purchaseOrderIdOf(doc);
    const kindLabel = side === 'client' ? t.documents.kindClient : t.documents.kindProvider;
    if (doc.vinculo.tabla === 'factura') {
      const d = detail.status === 'ready' ? detail.data : null;
      const field = (campo: string): number | null => {
        const v = d?.campos.find((c) => c.campo === campo)?.valor;
        return typeof v === 'number' ? v : null;
      };
      const text = (campo: string): string | null => {
        const v = d?.campos.find((c) => c.campo === campo)?.valor;
        return typeof v === 'string' ? v : null;
      };
      facts.push(
        { label: t.documents.number, value: doc.numero ?? NO_VALUE, data: true },
        { label: kindLabel, value: partyName ?? d?.contraparte ?? NO_VALUE, data: true },
        { label: t.documents.invoiceDate, value: formatDate(text('fecha_factura') ?? doc.fecha) }
      );
      if (d) {
        const paid = paidSource(d);
        const state = paymentStateLabel(lang, d.estado?.estado_pago) ?? NO_VALUE;
        const open = d.hallazgos.filter((h) => h.estado === 'abierto');
        facts.push(
          {
            label: t.documents.due,
            value: (
              <>
                {formatDate(d.vencimiento?.fecha ?? d.estado?.vencimiento)}
                {d.estado?.dias_vencida ? <small>{fmt(d.estado.dias_vencida === 1 ? t.why.overdueDaysOne : t.why.overdueDays, { n: d.estado.dias_vencida })}</small> : null}
              </>
            ),
          },
          { label: t.documents.base, value: formatMoney(field('base_cent')) },
          { label: t.documents.vat, value: formatMoney(field('iva_cent')) },
          { label: t.documents.total, value: formatMoney(field('total_cent') ?? doc.importe_cent) },
          { label: t.parties.outstanding, value: formatMoney(d.estado?.pendiente_cent) },
          {
            label: t.documents.state,
            value: (
              <>
                {state}
                {paid && (
                  <small>
                    {fmt(paid.source === 'banco' ? t.documents.paidBank : paid.source === 'exact' ? t.documents.paidExact : t.documents.paidManual, {
                      date: formatDate(paid.date),
                    })}
                  </small>
                )}
                {paid?.k3 && <small>{ruleText(lang, 'K3')?.title ?? 'K3'}</small>}
              </>
            ),
          },
          {
            label: t.documents.payments,
            value:
              (d.pagos ?? []).length === 0 ? (
                t.parties.noPayments
              ) : (
                <ul className='ws-paper-list'>
                  {(d.pagos ?? []).map((pay) => (
                    <li key={pay.id}>
                      {[
                        formatDate(pay.fecha_pago),
                        formatMoney(pay.importe_cent),
                        stateLabel(lang, 'fuente_aplicacion', pay.fuente) ?? pay.fuente,
                        stateLabel(lang, 'aplicacion', pay.estado) ?? pay.estado,
                      ].join(' · ')}
                    </li>
                  ))}
                </ul>
              ),
          },
          {
            label: t.documents.warnings,
            value:
              open.length === 0 ? (
                t.documents.noWarnings
              ) : (
                <ul className='ws-paper-list'>
                  {open.slice(0, 3).map((h) => (
                    <li key={h.id}>
                      {ruleText(lang, h.regla)?.title ?? h.regla} <small className='inline'>({h.regla})</small>
                    </li>
                  ))}
                  {open.length > 3 && <li>{fmt(t.documents.moreWarnings, { n: open.length - 3 })}</li>}
                </ul>
              ),
          }
        );
      } else if (detail.status === 'loading') {
        facts.push({ label: t.documents.total, value: formatMoney(doc.importe_cent) }, { label: t.documents.state, value: t.common.loading });
      } else {
        facts.push(
          { label: t.documents.total, value: formatMoney(doc.importe_cent) },
          { label: t.documents.state, value: paymentStateLabel(lang, doc.estado_pago) ?? NO_VALUE }
        );
      }
    } else if (doc.tipo === 'justificante_pago') {
      facts.push(
        { label: t.columns.invoice, value: doc.numero ?? NO_VALUE, data: true },
        { label: kindLabel, value: partyName ?? NO_VALUE, data: true },
        { label: t.documents.paymentDate, value: formatDate(doc.fecha) },
        { label: t.columns.amount, value: formatMoney(doc.importe_cent) },
        {
          label: t.documents.paymentState,
          value: [stateLabel(lang, 'aplicacion', doc.vinculo.estado), stateLabel(lang, 'fuente_aplicacion', doc.vinculo.fuente)].filter(Boolean).join(' · ') || NO_VALUE,
        }
      );
    } else {
      facts.push(
        { label: t.documents.number, value: doc.numero ?? NO_VALUE, data: true },
        { label: kindLabel, value: partyName ?? NO_VALUE, data: true },
        { label: t.documents.date, value: formatDate(doc.fecha) },
        { label: t.documents.value, value: formatMoney(doc.importe_cent) }
      );
    }
    facts.push({
      label: t.documents.file,
      value: (
        <>
          <span data-proper-name=''>{doc.nombre ?? NO_VALUE}</span>
          <small>
            {[doc.bytes ? formatSize(doc.bytes) : null, doc.registrado_en ? fmt(t.documents.received, { date: formatDate(doc.registrado_en) }) : null]
              .filter(Boolean)
              .join(' · ')}
          </small>
        </>
      ),
    });
    actions.push(<DownloadOriginal key='download' doc={doc} name={name} />);
    if (linkedInvoice) {
      actions.push(
        <Button key='invoice' variant='outline' onClick={() => onOpenInvoice(linkedInvoice)}>
          {t.documents.openInvoice}
        </Button>
      );
    } else if (po) {
      actions.push(
        <Button key='po' variant='outline' onClick={() => onOpenPo(po)}>
          {t.documents.openPo}
        </Button>
      );
    }
  }
  return (
    <DocumentPreview
      open={doc !== null}
      onClose={onClose}
      eyebrow={t.documents.previewEyebrow}
      title={name}
      subtitle={partyName ?? undefined}
      facts={facts}
      note={t.documents.previewNote}
    >
      {actions}
    </DocumentPreview>
  );
}
