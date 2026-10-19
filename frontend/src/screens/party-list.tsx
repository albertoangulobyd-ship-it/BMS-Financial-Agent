// Leveranciers / Klanten (Providers / Clients): "bij wie staat er wat open, en wat valt op?".
// Una fila por relacion, la mas urgente primero (el orden de la API, §8), con un buscador y
// cinco columnas: prioridad, nombre, openstaand, vervallen y por que (su hallazgo mas urgente,
// escrito desde sus valores). Una fila abre su ficha en una pestana.
import { DataTable, type Columns } from '@/components/data-table';
import { PageHeader, Screen } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { SearchBox } from '@/components/search-box';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { fmt, useT } from '@/i18n';
import { paths } from '@/lib/api';
import type { PartyRow } from '@/lib/api-types';
import { formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useTabState } from '@/lib/tab-memory';
import { matches } from '@/lib/text';
import { partyWhy } from '@/lib/why';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

export type PartyKind = 'provider' | 'client';

export function PartyListScreen({ kind, tabId }: { kind: PartyKind; tabId: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const navId = kind === 'provider' ? 'providers' : 'clients';
  const [state, retry] = useLoad(
    () =>
      kind === 'provider'
        ? session!.api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores)
        : session!.api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
    [session, version, kind]
  );
  const [query, setQuery] = useTabState<string>(tabId, `${navId}-query`, '');
  const nav = t.nav[navId];

  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <PartyTable kind={kind} rows={state.data} query={query} setQuery={setQuery} caption={nav.description} />
      )}
    </Screen>
  );
}

function PartyTable({
  kind,
  rows,
  query,
  setQuery,
  caption,
}: {
  kind: PartyKind;
  rows: PartyRow[];
  query: string;
  setQuery: (q: string) => void;
  caption: string;
}) {
  const { t, lang } = useT();
  const { openRoute } = useTabs();
  const navId = kind === 'provider' ? 'providers' : 'clients';
  if (rows.length === 0) {
    return <EmptyState title={t.empty.nothingHere} text={kind === 'provider' ? t.parties.emptyProviders : t.parties.emptyClients} />;
  }
  const shown = rows.filter((r) => matches(query, r.nombre, r.exact_id));
  const label = t.records[kind].label;
  const overdueText = (cents: number) => fmt(t.parties.overdue, { amount: formatMoney(cents) });

  const columns: Columns<PartyRow> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => <StatusPill group='prioridad' state={r.nivel} /> },
    {
      key: 'name',
      header: t.parties.name,
      primary: true,
      cell: (r) => (
        <span className='flex min-w-0 flex-col items-start'>
          <span className='text-[13.5px]'>{r.nombre}</span>
          <span className='text-xs font-normal text-muted-foreground'>
            {fmt(r.facturas === 1 ? t.parties.invoicesOne : t.parties.invoices, { n: r.facturas })}
            {!r.activo && ` · ${t.parties.inactive}`}
          </span>
        </span>
      ),
    },
    { key: 'outstanding', header: t.parties.outstanding, align: 'right', width: '8rem', cell: (r) => <Money cents={r.pendiente_cent} /> },
    {
      key: 'overdue',
      header: t.parties.overdueColumn,
      align: 'right',
      width: '8rem',
      cell: (r) => <Money cents={r.vencido_cent} className={r.vencido_cent > 0 ? 'font-medium text-late-foreground' : 'text-muted-foreground'} />,
    },
    { key: 'why', header: t.columns.why, cell: (r) => <WhyCell why={partyWhy(r, lang, t, overdueText)} /> },
  ];

  return (
    <>
      <div className='mb-3 flex flex-wrap items-center justify-end gap-3'>
        <SearchBox value={query} onChange={setQuery} placeholder={t.parties.searchName} />
      </div>
      <DataTable
        columns={columns}
        rows={shown}
        rowKey={(r) => r.id}
        caption={caption}
        onOpen={(r) => openRoute(recordRoute(kind, r.id, navId))}
        openLabel={(r) => fmt(t.common.openRecord, { what: `${label} ${r.nombre}` })}
        empty={<EmptyState title={t.empty.noMatch} text={t.empty.noMatchText} />}
      />
      {shown.length > 0 && (
        <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.parties.total, { shown: shown.length, all: rows.length })}</p>
      )}
    </>
  );
}
