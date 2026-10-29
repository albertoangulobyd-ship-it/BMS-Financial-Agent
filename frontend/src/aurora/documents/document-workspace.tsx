// document-workspace.tsx del dueno (entrega del 28-10-2026): Documentos, el archivo de Aurora.
// Estructura, nombres, clases y movimiento, los suyos: la marca, "Volver a Aurora", el arbol
// "EXPLORAR" con su pista, las migas, la cabecera con el orbe pequeno (y la pista a los 12 s), la
// rejilla de carpetas de cristal (con su aparicion escalonada), la ficha de la carpeta abierta
// debajo de la rejilla, la nota del pie, el <dialog> de la hoja y el aviso (ws-toast). Cambios
// (especificacion §4.2):
// - D: las carpetas son los clientes y proveedores de verdad (/api/v2/clientes, /proveedores y
//   sus documentos); la rejilla ensena las 12 que piden atencion (lo vencido, luego lo
//   pendiente) y las demas estan en el arbol (D-39); en cada carpeta, su prioridad (.ui-status)
//   junto a las nuevas y repetidas de la ultima lectura (D-41); la ficha dice lo del maestro y
//   su tabla lleva sus documentos, sus Objects y sus ordenes de compra (§2.3); la hoja se dibuja
//   desde el registro (invoice-sheet.tsx, sheets.tsx). Fuera "Agregar muestra", "Descargar
//   muestra TXT" y localStorage. "Datos de demostracion" dice de cuando son los datos;
//   la suricata de las carpetas vacias, fuera (D-44);
// - R: sin direcciones: el sitio (la categoria, la carpeta y la hoja) es estado de la app
//   (estado.ts, accion docs). "Volver a Aurora", la miga "Inicio" y el orbe pequeno vuelven al
//   inicio con el vuelo; el nodo "Inicio" del arbol, sin vuelo;
// - I: los textos, de los diccionarios.
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ArrowLeft, ArrowUpRight, Check, ChevronRight, FolderOpen } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import { PingScope, StatusPill } from '@/components/status-pill';
import { countText, fmt, useT } from '@/i18n';
import { paymentStateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { InvoiceDetail, PartyRow, PartyView } from '@/lib/api-types';
import { NO_VALUE, formatDate, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { twinMarks } from '@/lib/twins';
import { BmsLogo } from '../logo';
import { SiriWave } from '../orb/siri-wave';
import { OrderNotice, apiErrorMessage } from '../orders';
import { useAurora } from '../root';
import { PopoverContainer } from '../search/ui/popover';
import { useLoad } from '../use-load';
import { DOCS_ROOT, categoryOf, folderPlace, type DocsCategory, type DocsPlace, type DocsSheet } from '../estado';
import { docAnalysis, type Analysis } from './analysis';
import {
  allFolders,
  archiveTree,
  docKey,
  fanDocs,
  firstFolders,
  folderKey,
  invoiceIdOf,
  nodeTarget,
  tabOf,
  withAncestors,
  type DocsEntry,
  type Folder,
  type Side,
} from './documents-model';
import { FolderAnalysisStatus } from './folder-analysis-status';
import { useFolderDocs, useLastReading } from './folder-docs';
import { GlassFolder, type ArtRecipe, type FolderFile } from './glass-folder-cards';
import { InvoiceSheet } from './invoice-sheet';
import { DocumentSheet, FileRow, FileTable, ObjectSheet, PoSheet, docName, typeLabel } from './sheets';
import { TreeView } from './tree-view';
import './document-workspace.css';

// El marmol de los clientes y las vetas de los proveedores (document-workspace.tsx:15-16).
const art: ArtRecipe = {
  style: 'marble',
  colors: ['#0a0a10', '#30133f', '#693c83', '#a089bb', '#232d49', '#b3c4d8'],
  scale: 0.65,
  warp: 3.2,
  gloss: 0.45,
  veins: 0.25,
};
const supplierArt: ArtRecipe = {
  ...art,
  style: 'streak',
  colors: ['#0c121b', '#223751', '#617f9c', '#b6bacb', '#432554', '#9b7fad'],
  angle: -0.5,
  warp: 1.7,
};

/** Un sitio de Documentos, en la clave del arbol (lo seleccionado). */
function selectedNode(place: DocsPlace, docs: ReadonlyMap<string, DocsEntry>): string {
  if (!place.folder) return place.category ?? 'all';
  const key = folderKey(place.folder.side, place.folder.id);
  const sheet = place.sheet;
  const entry = docs.get(key);
  if (sheet && entry?.status === 'ready') {
    const doc =
      sheet.kind === 'document'
        ? entry.docs.find((d) => docKey(d) === sheet.key)
        : sheet.kind === 'invoice'
          ? entry.docs.find((d) => d.vinculo.tabla === 'factura' && d.vinculo.id === sheet.id)
          : undefined;
    if (doc) return `${key}/${docKey(doc)}`;
  }
  return key;
}

/** Lo que abre un documento de una carpeta: la hoja de su factura o la suya. */
function sheetOf(d: { vinculo: { tabla: string; id: number } } & Parameters<typeof docKey>[0]): DocsSheet {
  return d.vinculo.tabla === 'factura' ? { kind: 'invoice', id: d.vinculo.id } : { kind: 'document', key: docKey(d) };
}

export function DocumentWorkspace({ place }: { place: DocsPlace }) {
  const { t } = useT();
  const reduced = useReducedMotion();
  const { session } = useSession();
  const { version } = useRefresh();
  const { dispatch, go } = useAurora();
  const [lists] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
        session!.api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores),
      ]),
    [session, version]
  );
  const [docs, ensureDocs] = useFolderDocs();
  const analysis = useLastReading();
  const [notice, setNotice] = useState('');
  const [expanded, setExpanded] = useState<string[]>(['all', 'clients', 'providers']);
  const [showHint, setShowHint] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [dialog, setDialog] = useState<HTMLDialogElement | null>(null);
  const sheetEscape = useRef<() => boolean>(() => false);
  const { category, folder, sheet } = place;
  const activeKey = folder ? folderKey(folder.side, folder.id) : null;
  const folders = useMemo(() => (lists.status === 'ready' ? allFolders(lists.data[0], lists.data[1]) : []), [lists]);
  const selected = activeKey ? folders.find((f) => f.key === activeKey) : undefined;
  const placeKey = `${category}|${activeKey}`;

  const to = useCallback((next: DocsPlace) => dispatch({ type: 'docs', place: next }), [dispatch]);
  const home = useCallback(() => go({ type: 'home' }), [go]);

  // La pista a los 12 s sin una carpeta abierta (document-workspace.tsx:20).
  useEffect(() => {
    setShowHint(false);
    setSpeaking(false);
    if (folder) return;
    let stopTimer: ReturnType<typeof setTimeout> | undefined;
    const timer = setTimeout(() => {
      setShowHint(true);
      setSpeaking(true);
      stopTimer = setTimeout(() => setSpeaking(false), 4200);
    }, 12000);
    return () => {
      clearTimeout(timer);
      clearTimeout(stopTimer);
    };
  }, [placeKey]);

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

  const node = selectedNode(place, docs);
  // Al llegar, el camino hasta lo que se ve queda abierto en el arbol (como en Aurora).
  useEffect(() => {
    setExpanded((prev) => {
      const next = withAncestors(prev, node);
      return next.length === prev.length ? prev : next;
    });
  }, [node]);

  // El <dialog> de la hoja: modal mientras hay una hoja (document-workspace.tsx:21).
  useEffect(() => {
    if (!dialog) return;
    if (sheet && !dialog.open) dialog.showModal();
    if (!sheet && dialog.open) dialog.close();
  }, [sheet, dialog]);
  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(''), 2600);
    return () => clearTimeout(id);
  }, [notice]);

  // Alt+← y el boton "atras" del raton: la salida visible (D-06).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && !e.ctrlKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        home();
      }
    };
    const onMouse = (e: MouseEvent) => {
      if (e.button === 3) {
        e.preventDefault();
        home();
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mouseup', onMouse);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mouseup', onMouse);
    };
  }, [home]);

  const closeSheet = () => to({ ...place, sheet: null });
  const openSheet = (side: Side, id: number, next: DocsSheet) => to(folderPlace(side, id, next));
  const openInvoice = (id: number) => to({ ...place, sheet: { kind: 'invoice', id } });
  // Una factura abierta sin su carpeta (desde la busqueda): su carpeta, cuando se sabe.
  const onInvoiceLoaded = (f: InvoiceDetail) => {
    if (folder) return;
    const value = (name: string) => f.campos.find((c) => c.campo === name)?.valor;
    const client = value('cliente_id');
    const provider = value('proveedor_id');
    if (f.sentido === 'saliente' && typeof client === 'number') to(folderPlace('client', client, { kind: 'invoice', id: f.id }));
    else if (typeof provider === 'number') to(folderPlace('provider', provider, { kind: 'invoice', id: f.id }));
  };

  const onTreeSelect = (id: string) => {
    const target = nodeTarget(id);
    // El nodo "Inicio" del arbol vuelve al inicio sin vuelo (cambio R).
    if (target.kind === 'home') dispatch({ type: 'home' });
    else if (target.kind === 'tab') to(target.tab === 'all' ? DOCS_ROOT : { category: target.tab, folder: null, sheet: null });
    else if (target.kind === 'folder') to(folderPlace(target.side, target.id));
    else if (target.kind === 'doc') {
      const entry = docs.get(folderKey(target.side, target.id));
      const d = entry?.status === 'ready' ? entry.docs.find((x) => docKey(x) === target.doc) : undefined;
      if (d) openSheet(target.side, target.id, sheetOf(d));
    }
  };

  const toneOf = (d: Parameters<typeof docAnalysis>[1]) => docAnalysis(analysis, d);
  const treeNodes =
    lists.status === 'ready'
      ? archiveTree(folders, docs, {
          home: t.aurora.work.home,
          all: t.nav.documents.label,
          clients: t.documents.clients,
          providers: t.documents.providers,
          failed: t.documents.treeFailed,
          docLabel: (d) => docName(t, d),
          docTone: toneOf,
        })
      : [{ id: 'home', label: t.aurora.work.home }];

  const inCategory = folders.filter((f) => !category || tabOf(f.side) === category);
  const { shown } = firstFolders(inCategory, false, activeKey);
  // Con las marcas de una lectura, se leen los documentos de las carpetas a la vista.
  const marked = analysis.byDocument.size + analysis.byInvoice.size > 0;
  useEffect(() => {
    if (!marked) return;
    for (const f of shown) if ((f.row.documentos ?? 0) > 0) ensureDocs(f.side, f.row.id);
  }, [marked, shown.map((f) => f.key).join(','), ensureDocs]);

  const sheetLabel = (() => {
    if (!sheet) return '';
    if (sheet.kind === 'object') return t.records.object.label;
    if (sheet.kind === 'po') return t.records['purchase-order'].label;
    const entry = activeKey ? docs.get(activeKey) : undefined;
    const d =
      entry?.status === 'ready'
        ? entry.docs.find((x) => (sheet.kind === 'document' ? docKey(x) === sheet.key : x.vinculo.tabla === 'factura' && x.vinculo.id === sheet.id))
        : undefined;
    return d ? docName(t, d) : t.records.invoice.label;
  })();
  const categoryLabel = (c: DocsCategory) => (c === 'clients' ? t.documents.clients : t.documents.providers);
  const crumb = (label: string, onSelect: (() => void) | null, data = false, last = false) => (
    <a
      role='link'
      tabIndex={0}
      aria-current={last ? 'page' : undefined}
      data-proper-name={data ? '' : undefined}
      onClick={onSelect ?? undefined}
      onKeyDown={(e) => e.key === 'Enter' && onSelect?.()}
    >
      {label}
    </a>
  );
  const a = t.aurora.archive;

  // Las carpetas y las fichas resumen: ningun punto late aqui (paso 15: ninguna lista ni
  // tarjeta parpadea; lo que pide hacer algo ya esta en el panel de Inicio).
  return (
    <PingScope scope='none'>
      <div className='workspace'>
        <BmsLogo />
        <a className='ws-home' role='link' tabIndex={0} onClick={home} onKeyDown={(e) => e.key === 'Enter' && home()}>
          <ArrowLeft size={15} /> {t.aurora.work.back}
        </a>
        <div className='ws-layout'>
          <aside className='ws-sidebar' aria-label={a.navigation}>
            <p className='ws-eyebrow'>{a.explore.toLocaleUpperCase()}</p>
            <TreeView
              nodes={treeNodes}
              label={a.treeLabel}
              expanded={expanded}
              onExpandedChange={setExpanded}
              selected={node}
              onSelectedChange={onTreeSelect}
            />
            <p className='ws-tree-hint'>
              {t.documents.hint1}
              <br />
              {t.documents.hint2}
            </p>
          </aside>
          <div className='ws-shell'>
            <nav className='ws-breadcrumbs' aria-label={t.shell.breadcrumbs}>
              {crumb(t.aurora.work.home, home)}
              <ChevronRight size={12} />
              {crumb(t.nav.documents.label, () => to(DOCS_ROOT), false, !category && !folder)}
              {(category || folder) && (
                <>
                  <ChevronRight size={12} />
                  {crumb(
                    categoryLabel(category ?? categoryOf(folder!.side)),
                    () =>
                      to({
                        category: category ?? categoryOf(folder!.side),
                        folder: null,
                        sheet: null,
                      }),
                    false,
                    !folder
                  )}
                </>
              )}
              {folder && (
                <>
                  <ChevronRight size={12} />
                  {crumb(selected?.row.nombre ?? NO_VALUE, () => to(folderPlace(folder.side, folder.id)), true, !sheet)}
                </>
              )}
              {sheet && (
                <>
                  <ChevronRight size={12} />
                  <span aria-current='page' data-proper-name=''>
                    {sheetLabel}
                  </span>
                </>
              )}
            </nav>
            {/* "Ir al contenido" (App.tsx) llega aqui, al titulo (ws-shell es display:contents). */}
            <div className='ws-heading' id='contenido' tabIndex={-1}>
              <div>
                <a
                  className={'ws-companion ' + (speaking ? 'ws-speaking' : '')}
                  role='link'
                  tabIndex={0}
                  aria-label={a.home}
                  onClick={home}
                  onKeyDown={(e) => e.key === 'Enter' && home()}
                >
                  <motion.span className='aurora-shared'>
                    <SiriWave size={180} renderScale={1} flowPhase={speaking ? 3.6 : 0} />
                  </motion.span>
                </a>
                <p className='ws-eyebrow'>{t.documents.eyebrow.toLocaleUpperCase()}</p>
                <div className='ws-title-line'>
                  <h1 aria-live='polite'>
                    <AnimatePresence mode='wait' initial={false}>
                      <motion.span
                        key={showHint ? 'hint' : 'welcome'}
                        initial={{ opacity: 0, y: 7 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -7 }}
                        transition={{ duration: 0.3 }}
                      >
                        {showHint ? a.hintTitle : a.title}
                      </motion.span>
                    </AnimatePresence>
                  </h1>
                </div>
                <p>{a.intro}</p>
              </div>
              <SampleChip />
            </div>
            <AnimatePresence mode='wait' initial={false}>
              <motion.div
                key={category ?? 'all'}
                className='ws-grid'
                initial={{ opacity: 1, y: 0 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduced ? { opacity: 0 } : { opacity: 0, y: -8 }}
                transition={{ duration: reduced ? 0 : 0.16 }}
              >
                {shown.map((f, i) => (
                  <FolderCell
                    key={f.key}
                    folder={f}
                    index={i}
                    active={f.key === activeKey}
                    entry={docs.get(f.key)}
                    analysis={analysis}
                    onOpen={() => to(folderPlace(f.side, f.row.id))}
                    onClose={() => to({ category, folder: null, sheet: null })}
                    onWarm={() => (f.row.documentos ?? 0) > 0 && ensureDocs(f.side, f.row.id)}
                    onFile={(next) => openSheet(f.side, f.row.id, next)}
                  />
                ))}
              </motion.div>
            </AnimatePresence>
            {lists.status === 'ready' && shown.length === 0 && (
              <div className='ws-empty'>
                <FolderOpen size={30} />
                <h2>{t.documents.noFolders}</h2>
              </div>
            )}
            <AnimatePresence mode='wait' initial={false}>
              {folder && (
                <motion.section
                  key={activeKey}
                  layout='position'
                  initial={reduced ? { opacity: 1 } : { opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduced ? { opacity: 0 } : { opacity: 0, y: -6 }}
                  transition={{
                    duration: reduced ? 0 : 0.28,
                    ease: [0.22, 1, 0.36, 1],
                  }}
                  className='ws-profile'
                  aria-label={fmt(a.profileOf, {
                    name: selected?.row.nombre ?? NO_VALUE,
                  })}
                >
                  <FolderProfile
                    side={folder.side}
                    id={folder.id}
                    row={selected?.row}
                    entry={docs.get(folderKey(folder.side, folder.id))}
                    analysis={analysis}
                    sheet={sheet}
                    onSheet={(next) => openSheet(folder.side, folder.id, next)}
                    onRetry={() => ensureDocs(folder.side, folder.id, true)}
                  />
                </motion.section>
              )}
            </AnimatePresence>
            <motion.p layout='position' transition={{ duration: reduced ? 0 : 0.3 }} className='ws-footnote'>
              {folders.length > shown.length ? `${a.firstTwelve} ` : ''}
              {t.documents.later}
            </motion.p>
          </div>
        </div>
        <dialog
          ref={setDialog}
          className='ws-dialog'
          aria-label={sheetLabel || undefined}
          onCancel={(e) => {
            e.preventDefault();
            // Un desplegable (fecha, lista) se cierra solo; despues, la tarjeta abierta.
            if (document.querySelector('[data-radix-popper-content-wrapper]')) return;
            if (sheetEscape.current()) return;
            closeSheet();
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) closeSheet();
          }}
        >
          <PopoverContainer.Provider value={dialog}>
            <OrderNotice.Provider value={setNotice}>
              {sheet && (
                <SheetFor
                  key={JSON.stringify(sheet)}
                  sheet={sheet}
                  place={place}
                  partyName={selected?.row.nombre ?? null}
                  docs={docs}
                  analysis={analysis}
                  escape={sheetEscape}
                  onClose={closeSheet}
                  onLoaded={onInvoiceLoaded}
                  onOpenInvoice={openInvoice}
                  onOpenPo={(id) => to({ ...place, sheet: { kind: 'po', id } })}
                />
              )}
            </OrderNotice.Provider>
          </PopoverContainer.Provider>
        </dialog>
        {notice && (
          <div className='ws-toast' role='status'>
            <Check size={15} />
            {notice}
          </div>
        )}
      </div>
    </PingScope>
  );
}

/** "Datos de demostracion" de Aurora: aqui, de cuando son los datos (cambio D). */
function SampleChip() {
  const { t } = useT();
  const { session } = useSession();
  return (
    <span className='ws-demo'>
      <i /> {session?.environment === 'demo' ? t.aurora.panel.sampleTest : t.aurora.panel.sampleEur}
    </span>
  );
}

/** Una carpeta de la rejilla (document-workspace.tsx:38): su tipo y su numero, la carpeta de
 *  cristal con sus marcas y el pie con el importe y "Abrir ficha". */
function FolderCell({
  folder: f,
  index: i,
  active,
  entry,
  analysis,
  onOpen,
  onClose,
  onWarm,
  onFile,
}: {
  folder: Folder;
  index: number;
  active: boolean;
  entry: DocsEntry | undefined;
  analysis: Analysis;
  onOpen: () => void;
  onClose: () => void;
  onWarm: () => void;
  onFile: (sheet: DocsSheet) => void;
}) {
  const { t } = useT();
  const reduced = useReducedMotion();
  const a = t.aurora.archive;
  const ready = entry?.status === 'ready' ? entry.docs : [];
  const files: FolderFile[] = fanDocs(ready).map((d) => ({
    id: docKey(d),
    name: typeLabel(t, d.tipo),
    meta: d.numero ?? undefined,
    label: fmt(t.documents.previewNamed, { name: docName(t, d) }),
    analysisStatus: docAnalysis(analysis, d),
  }));
  // Las marcas cuentan todos los documentos de la carpeta, no solo los del abanico.
  const marks: FolderFile[] = ready.map((d) => ({
    id: docKey(d),
    name: '',
    analysisStatus: docAnalysis(analysis, d),
  }));
  const kind = (f.side === 'client' ? t.documents.kindClient : t.documents.kindProvider).toLocaleUpperCase();
  return (
    <motion.article
      layout='position'
      initial={reduced ? { opacity: 1 } : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        opacity: {
          duration: reduced ? 0 : 0.32,
          delay: reduced ? 0 : i * 0.045,
        },
        y: {
          duration: reduced ? 0 : 0.4,
          delay: reduced ? 0 : i * 0.045,
          ease: [0.22, 1, 0.36, 1],
        },
        layout: { duration: reduced ? 0 : 0.35 },
      }}
      className={'ws-folder-cell ' + (active ? 'ws-folder-active' : '')}
      onPointerEnter={onWarm}
      data-testid='folder-cell'
    >
      <span className='ws-party-type'>
        {kind}
        <span>{String(i + 1).padStart(2, '0')}</span>
      </span>
      <GlassFolder
        frontAccessory={
          <FolderAnalysisStatus files={marks} before={f.row.nivel !== 'normal' ? <StatusPill group='prioridad' state={f.row.nivel} /> : undefined} />
        }
        label={f.row.nombre}
        art={f.side === 'client' ? art : supplierArt}
        seed={(f.row.id * 7 + (f.side === 'client' ? 3 : 5)) % 997}
        width={264}
        files={files}
        total={entry?.status === 'ready' ? entry.docs.length : (f.row.documentos ?? 0)}
        appear={false}
        open={active}
        onOpenChange={(next) => (next ? onOpen() : onClose())}
        onFileSelect={(file) => {
          const d = ready.find((x) => docKey(x) === file.id);
          if (d) onFile(sheetOf(d));
        }}
      />
      <div className='ws-folder-caption'>
        <span>{f.row.deuda_cent > 0 ? formatMoney(f.row.deuda_cent) : a.upToDate}</span>
        <a
          role='link'
          tabIndex={0}
          onClick={onOpen}
          onKeyDown={(e) => e.key === 'Enter' && onOpen()}
          aria-label={fmt(active ? a.viewProfileNamed : a.openProfileNamed, {
            name: f.row.nombre,
          })}
        >
          {active ? a.viewProfile : a.openProfile}
          <ArrowUpRight size={13} />
        </a>
      </div>
    </motion.article>
  );
}

/** La ficha de la carpeta abierta (ws-profile, debajo de la rejilla, D-40): lo del maestro en
 *  una dl y la tabla con sus documentos, sus Objects y sus ordenes de compra (§2.3). */
function FolderProfile({
  side,
  id,
  row,
  entry,
  analysis,
  sheet,
  onSheet,
  onRetry,
}: {
  side: Side;
  id: number;
  row: PartyRow | undefined;
  entry: DocsEntry | undefined;
  analysis: Analysis;
  sheet: DocsSheet | null;
  onSheet: (sheet: DocsSheet) => void;
  /** Volver a leer los documentos que no se pudieron leer. */
  onRetry: () => void;
}) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [view] = useLoad(
    () =>
      side === 'provider'
        ? session!.api.get<{ proveedor: PartyView }>(paths.provider(id)).then((r) => r.proveedor)
        : session!.api.get<{ cliente: PartyView }>(paths.client(id)).then((r) => r.cliente),
    [session, side, id, version]
  );
  const a = t.aurora.archive;
  const p = view.status === 'ready' ? view.data : null;
  const docs = entry?.status === 'ready' ? entry.docs : [];
  const twins = twinMarks(
    docs
      .filter((d) => d.vinculo.tabla === 'factura')
      .map((d) => ({
        id: d.vinculo.id,
        numero: d.numero,
        contraparte: d.tipo,
      }))
  );
  const objects = p?.objetos ?? [];
  const orders = p?.ordenes_compra ?? [];
  const isCurrent = (s: DocsSheet) => JSON.stringify(s) === JSON.stringify(sheet);
  let facts: ReactNode = null;
  if (p) {
    const paid = p.plazo_de_pago;
    const pays =
      paid.pagadas === 0 || paid.media_dias === null
        ? t.documents.paysNone
        : paid.tarde > 0
          ? fmt(t.documents.paysAfter, {
              days: countText(t, 'days', paid.media_dias),
              late: countText(t, 'times', paid.tarde),
            })
          : fmt(t.documents.paysAfterOnTime, {
              days: countText(t, 'days', paid.media_dias),
            });
    const contact = p.contactos?.find((c) => c.activo) ?? p.contactos?.[0];
    const accounts = p.ibanes?.registro ?? [];
    facts = (
      <dl>
        {contact?.nombre && (
          <>
            <dt>{t.documents.contact}</dt>
            <dd data-proper-name=''>{contact.nombre}</dd>
          </>
        )}
        <dt>{t.documents.exactCode}</dt>
        <dd data-proper-name=''>{p.exact_id ?? NO_VALUE}</dd>
        <dt>{t.parties.paymentTerm}</dt>
        <dd>{p.plazo_pago_dias !== null ? countText(t, 'days', p.plazo_pago_dias) : t.common.unknown}</dd>
        <dt>{t.parties.outstanding}</dt>
        <dd>
          {formatMoney(p.deuda_cent)} · {fmt(p.abiertas === 1 ? t.parties.openInvoicesCountOne : t.parties.openInvoicesCount, { n: p.abiertas })}
          {p.abonos_sin_enlazar_cent !== 0 && (
            <span data-testid='unlinked-credit' className='block'>
              {p.abonos_sin_enlazar_facturas > 1
                ? fmt(t.parties.unlinkedCreditMany, {
                    n: p.abonos_sin_enlazar_facturas,
                    amount: formatMoney(p.abonos_sin_enlazar_cent),
                  })
                : fmt(t.parties.unlinkedCredit, {
                    amount: formatMoney(p.abonos_sin_enlazar_cent),
                  })}
            </span>
          )}
        </dd>
        <dt>{t.parties.overdueColumn}</dt>
        <dd>
          {formatMoney(p.vencido_cent)}
          {p.vencidas > 0 && ` · ${fmt(p.vencidas === 1 ? t.parties.overdueCountOne : t.parties.overdueCount, { n: p.vencidas })}`}
        </dd>
        <dt>{side === 'client' ? t.documents.paysClient : t.documents.paysProvider}</dt>
        <dd>{pays}</dd>
        {side === 'provider' && (
          <>
            <dt>{t.documents.account}</dt>
            <dd>
              {accounts.length === 0
                ? t.documents.noAccounts
                : accounts.map((acc) => (
                    <span key={acc.id} className='block'>
                      <span data-proper-name=''>{acc.iban}</span> <StatusPill group='cuenta' state={acc.estado} />
                    </span>
                  ))}
            </dd>
            <dt>{t.documents.phone}</dt>
            <dd>{p.telefono_verificacion ? <span data-proper-name=''>{p.telefono_verificacion}</span> : t.parties.noPhone}</dd>
          </>
        )}
        {p.email_facturacion && (
          <>
            <dt>{t.documents.invoiceEmail}</dt>
            <dd data-proper-name=''>{p.email_facturacion}</dd>
          </>
        )}
      </dl>
    );
  }
  return (
    <>
      <div>
        <p className='ws-eyebrow'>{(side === 'client' ? t.documents.profileClient : t.documents.profileProvider).toLocaleUpperCase()}</p>
        <h2 data-proper-name='' id='docs-profile-title' tabIndex={-1}>
          {p?.nombre ?? row?.nombre ?? NO_VALUE}
        </h2>
        {p && (
          <p className='ws-tax' data-proper-name=''>
            {[p.btw_id, p.kvk ? `KvK ${p.kvk}` : null].filter(Boolean).join(' · ') || NO_VALUE}
          </p>
        )}
        {facts}
      </div>
      <FileTable title={a.folderDocuments} count={docs.length + objects.length + orders.length}>
        {/* Mientras llegan sus documentos, la tabla vacia: nada de «Cargando…» (§6.5). */}
        {/* Lo vacio de Aurora (ws-empty) con su boton: lo que fallo y volver a probar. */}
        {entry?.status === 'error' && (
          <div className='ws-empty'>
            <p role='alert'>{apiErrorMessage(entry.error, t, lang)}</p>
            <button type='button' onClick={onRetry}>
              {t.common.retry}
            </button>
          </div>
        )}
        {entry?.status === 'ready' && docs.length === 0 && objects.length === 0 && orders.length === 0 && (
          <p className='ws-paper-disclaimer'>{t.documents.empty}</p>
        )}
        {docs.map((d) => {
          const tone = docAnalysis(analysis, d);
          const twin = d.vinculo.tabla === 'factura' ? twins.get(d.vinculo.id) : undefined;
          const next = sheetOf(d);
          return (
            <FileRow
              key={docKey(d)}
              title={docName(t, d)}
              data
              note={[
                formatDate(d.fecha),
                d.importe_cent !== null ? formatMoney(d.importe_cent) : null,
                paymentStateLabel(lang, d.estado_pago),
                twin ? fmt(t.common.twin, { n: twin.n, of: twin.of }) : null,
              ]
                .filter((s) => s && s !== NO_VALUE)
                .join(' · ')}
              status={tone === 'new' ? a.freshStatus : tone === 'duplicate' ? a.repeatedStatus : undefined}
              tone={tone}
              current={isCurrent(next)}
              label={fmt(t.documents.previewNamed, { name: docName(t, d) })}
              onOpen={() => onSheet(next)}
            />
          );
        })}
        {objects.map((o) => (
          <FileRow
            key={`o${o.id}`}
            title={`${t.records.object.label} ${o.codigo}`}
            note={o.nombre ?? undefined}
            data
            current={isCurrent({ kind: 'object', id: o.id })}
            onOpen={() => onSheet({ kind: 'object', id: o.id })}
          />
        ))}
        {orders.map((o) => (
          <FileRow
            key={`p${o.id}`}
            title={`${t.records['purchase-order'].label} ${o.numero}`}
            note={[formatMoney(o.valor_cent), `${t.pos.left} ${formatMoney(o.restante_cent)}`].join(' · ')}
            data
            current={isCurrent({ kind: 'po', id: o.id })}
            onOpen={() => onSheet({ kind: 'po', id: o.id })}
          />
        ))}
      </FileTable>
    </>
  );
}

/** Lo que va en el <dialog>: la hoja de una factura, de un documento, de un Object o de una PO. */
function SheetFor({
  sheet,
  place,
  partyName,
  docs,
  analysis,
  escape,
  onClose,
  onLoaded,
  onOpenInvoice,
  onOpenPo,
}: {
  sheet: DocsSheet;
  place: DocsPlace;
  partyName: string | null;
  docs: ReadonlyMap<string, DocsEntry>;
  analysis: Analysis;
  escape: MutableRefObject<() => boolean>;
  onClose: () => void;
  onLoaded: (f: InvoiceDetail) => void;
  onOpenInvoice: (id: number) => void;
  onOpenPo: (id: number) => void;
}) {
  if (sheet.kind === 'invoice') {
    escape.current = () => false;
    return (
      <InvoiceSheet
        id={sheet.id}
        analysis={analysis.byInvoice.get(sheet.id)}
        escape={escape}
        onClose={onClose}
        onLoaded={onLoaded}
        onOpenInvoice={onOpenInvoice}
      />
    );
  }
  escape.current = () => false;
  if (sheet.kind === 'object') return <ObjectSheet id={sheet.id} onClose={onClose} onOpenInvoice={onOpenInvoice} />;
  if (sheet.kind === 'po') return <PoSheet id={sheet.id} onClose={onClose} onOpenInvoice={onOpenInvoice} />;
  const folder = place.folder;
  const entry = folder ? docs.get(folderKey(folder.side, folder.id)) : undefined;
  const doc = entry?.status === 'ready' ? entry.docs.find((d) => docKey(d) === sheet.key) : undefined;
  if (!folder || !doc) return null;
  return (
    <DocumentSheet
      doc={doc}
      side={folder.side}
      partyName={partyName}
      analysis={docAnalysis(analysis, doc)}
      onClose={onClose}
      onOpenInvoice={(id) => onOpenInvoice(invoiceIdOf(doc) ?? id)}
      onOpenPo={onOpenPo}
    />
  );
}
