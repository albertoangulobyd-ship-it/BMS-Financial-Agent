// Documentos (paso 16): una carpeta por cliente y por proveedor, con lo que el sistema ya les
// enlaza (originales de facturas y abonos, justificantes de pago, hojas de PO: decision 7 de la
// revision; los contratos, mas adelante). Lo de aqui funciona de verdad sobre el motor
// (/api/v2/clientes, /proveedores y sus /N/documentos; cada descarga queda en la auditoria como
// documento_abierto); el archivo de Aurora (las carpetas de cristal, el arbol y la vista
// previa dibujada desde el registro, revision §8.5) se monta sobre esto en el paso de
// Documentos. Los nombres de empresas y de ficheros vienen de los datos: se pintan como texto.
import { Download, FolderOpen } from 'lucide-react';
import { useEffect, useState } from 'react';
import { DataTable, type Columns } from '@/components/data-table';
import { PageHeader, Screen } from '@/components/page-header';
import { SearchBox } from '@/components/search-box';
import { EmptyState, ErrorState, Loading, TechnicalDetail, errorMessage } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import { DateText, Money } from '@/components/values';
import { fmt, useT, type Messages } from '@/i18n';
import { paymentStateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { PartyDocument, PartyDocuments, PartyRow } from '@/lib/api-types';
import { formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { matches } from '@/lib/text';
import { useViewState } from '@/lib/view-memory';
import { useNav } from '@/shell/navigation';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

type Side = 'clients' | 'providers';

export function DocumentsScreen({ navKey }: { navKey: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [query, setQuery] = useViewState<string>(navKey, 'docs-query', '');
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
        session!.api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores),
      ]),
    [session, version]
  );
  const nav = t.nav.documents;
  return (
    <Screen calm>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && <Folders query={query} setQuery={setQuery} clients={state.data[0]} providers={state.data[1]} />}
    </Screen>
  );
}

/** Las carpetas de clientes y de proveedores, cada grupo con su titulo (sin pestanas: una
 *  carpeta esta a un clic de la entrada). El buscador mira los dos. */
function Folders({
  query,
  setQuery,
  clients,
  providers,
}: {
  query: string;
  setQuery: (q: string) => void;
  clients: PartyRow[];
  providers: PartyRow[];
}) {
  const { t } = useT();
  if (clients.length + providers.length === 0) return <EmptyState icon={FolderOpen} title={t.empty.nothingHere} text={t.documents.noFolders} />;
  const pick = (rows: PartyRow[]) => rows.filter((r) => matches(query, r.nombre, r.exact_id));
  const shownClients = pick(clients);
  const shownProviders = pick(providers);
  return (
    <div className='flex flex-col gap-6'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <p className='max-w-3xl text-[13px] text-muted-foreground'>{t.documents.later}</p>
        <SearchBox value={query} onChange={setQuery} placeholder={t.documents.search} />
      </div>
      {shownClients.length + shownProviders.length === 0 && <EmptyState title={t.empty.noMatch} text={t.empty.noMatchText} />}
      {shownClients.length > 0 && <FolderGroup side='clients' rows={shownClients} />}
      {shownProviders.length > 0 && <FolderGroup side='providers' rows={shownProviders} />}
    </div>
  );
}

function FolderGroup({ side, rows }: { side: Side; rows: PartyRow[] }) {
  const { t } = useT();
  const { open } = useNav();
  const id = `docs-${side}`;
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className='mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground'>
        {side === 'clients' ? t.documents.clients : t.documents.providers}
        <span className='ml-2 font-normal normal-case tracking-normal'>{rows.length}</span>
      </h2>
      <ul className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3'>
        {rows.map((r) => (
          <li key={r.id}>
            <button
              type='button'
              onClick={() => open(recordRoute(side === 'clients' ? 'client-documents' : 'provider-documents', r.id))}
              aria-label={fmt(t.documents.openFolder, { name: r.nombre })}
              className='group flex w-full items-start gap-3 rounded-xl border border-border bg-card px-4 py-3.5 text-left transition-colors hover:border-border-strong hover:bg-row-hover'
            >
              <FolderOpen className='mt-0.5 h-5 w-5 shrink-0 text-primary' aria-hidden='true' />
              <span className='flex min-w-0 flex-1 flex-col gap-0.5'>
                <span className='truncate font-medium' data-proper-name=''>
                  {r.nombre}
                </span>
                <span className='text-xs text-muted-foreground'>{documentCount(r.documentos ?? 0, t)}</span>
                <span className='num text-xs text-soft-foreground'>
                  {r.pendiente_cent > 0 ? fmt(t.documents.outstanding, { amount: formatMoney(r.pendiente_cent) }) : t.documents.nothingOpen}
                </span>
              </span>
              <StatusPill group='prioridad' state={r.nivel} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function documentCount(n: number, t: Messages): string {
  if (n === 0) return t.documents.none;
  return n === 1 ? t.documents.countOne : fmt(t.documents.count, { n });
}

export function PartyDocumentsScreen({ kind, id, navKey }: { kind: 'client' | 'provider'; id: number; navKey: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const { setTitle, open } = useNav();
  const [state, retry] = useLoad(
    () =>
      session!.api
        .get<{ documentos: PartyDocuments }>(kind === 'client' ? paths.clientDocuments(id) : paths.providerDocuments(id))
        .then((r) => r.documentos),
    [session, id, kind, version]
  );
  const name = state.status === 'ready' ? state.data.parte.nombre : null;
  useEffect(() => {
    if (name) setTitle(navKey, name);
  }, [name, navKey, setTitle]);
  const title = name ? fmt(t.documents.folderOf, { name }) : fmt(t.records[kind === 'client' ? 'client-documents' : 'provider-documents'].fallbackTitle, { id });
  return (
    <Screen calm>
      <PageHeader
        title={title}
        description={kind === 'client' ? t.documents.questionClient : t.documents.questionProvider}
        action={
          <Button variant='outline' onClick={() => open(recordRoute(kind, id))}>
            {t.documents.openCard}
          </Button>
        }
      />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && <DocumentTable docs={state.data.documentos} />}
    </Screen>
  );
}

function DocumentTable({ docs }: { docs: PartyDocument[] }) {
  const { t, lang } = useT();
  const typeLabel = (tipo: string) => (t.documents.types as Record<string, string>)[tipo] ?? tipo;
  const columns: Columns<PartyDocument> = [
    {
      key: 'type',
      header: t.documents.type,
      width: '13rem',
      cell: (d) => <span className='text-[13px]'>{typeLabel(d.tipo)}</span>,
    },
    { key: 'date', header: t.documents.date, width: '7rem', cell: (d) => <DateText value={d.fecha} /> },
    {
      key: 'number',
      header: t.documents.number,
      cell: (d) => (
        <span className='flex min-w-0 flex-col'>
          <span className='font-mono text-[12.5px]' data-proper-name=''>
            {d.numero ?? '—'}
          </span>
          {d.nombre && (
            <span className='truncate text-xs text-muted-foreground' data-proper-name=''>
              {d.nombre}
            </span>
          )}
        </span>
      ),
    },
    { key: 'amount', header: t.documents.amount, align: 'right', width: '8rem', cell: (d) => <Money cents={d.importe_cent} /> },
    {
      key: 'state',
      header: t.documents.state,
      width: '9rem',
      cell: (d) => <span className='text-[13px] text-soft-foreground'>{d.estado_pago ? (paymentStateLabel(lang, d.estado_pago) ?? '—') : '—'}</span>,
    },
    { key: 'file', header: t.documents.file, width: '9.5rem', cell: (d) => <DownloadCell doc={d} label={typeLabel(d.tipo)} /> },
  ];
  return (
    <DataTable
      columns={columns}
      rows={docs}
      rowKey={(d) => `${d.id}-${d.vinculo.tabla}-${d.vinculo.id}`}
      caption={t.nav.documents.description}
      empty={<EmptyState icon={FolderOpen} title={t.empty.nothingHere} text={t.documents.empty} />}
    />
  );
}

function DownloadCell({ doc, label }: { doc: PartyDocument; label: string }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!doc.guardado) return <span className='text-xs text-muted-foreground'>{t.documents.notKept}</span>;
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
  return (
    <span className='flex flex-col items-start gap-1'>
      <Button
        variant='outline'
        size='sm'
        onClick={download}
        disabled={busy}
        aria-label={fmt(t.documents.downloadNamed, { name: `${label} ${doc.numero ?? ''}`.trim() })}
      >
        <Download className='mr-1.5 h-3.5 w-3.5' aria-hidden='true' />
        {t.documents.download}
      </Button>
      {error !== null && (
        <span role='alert' className='text-xs text-late-foreground'>
          {errorMessage(error, t, lang)}
          <TechnicalDetail error={error} />
        </span>
      )}
    </span>
  );
}
