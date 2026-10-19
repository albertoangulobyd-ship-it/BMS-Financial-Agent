// Werklijst / Work queue: "welke facturen hebben een mens nodig, en welke eerst?". Las que
// piden a alguien (prioridad, hallazgos, una excepcion o campos por verificar), la mas
// urgente primero (el orden de la API, §8). Fichas Alle / Geblokkeerd / Urgent / Aandacht,
// un buscador y cinco columnas: prioridad, factura (numero y relacion), importe,
// vencimiento y por que. Una fila abre su factura en una pestana.
import { CircleCheck } from 'lucide-react';
import { DataTable, type Columns } from '@/components/data-table';
import { FilterChips } from '@/components/filter-chips';
import { PageHeader, Screen } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { SearchBox } from '@/components/search-box';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText, Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { fmt, useT } from '@/i18n';
import { paths, type InvoiceRow } from '@/lib/api';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useTabState } from '@/lib/tab-memory';
import { matches } from '@/lib/text';
import { needsPerson, whyOf } from '@/lib/why';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

type QueueFilter = 'all' | 'bloqueada' | 'urgente' | 'atencion';

export function WorkQueueScreen({ tabId }: { tabId: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () => session!.api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas.filter(needsPerson)),
    [session, version]
  );
  const [filter, setFilter] = useTabState<QueueFilter>(tabId, 'wq-filter', 'all');
  const [query, setQuery] = useTabState<string>(tabId, 'wq-query', '');
  const nav = t.nav['work-queue'];

  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <QueueTable rows={state.data} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} />
      )}
    </Screen>
  );
}

function QueueTable({
  rows,
  filter,
  setFilter,
  query,
  setQuery,
}: {
  rows: InvoiceRow[];
  filter: QueueFilter;
  setFilter: (f: QueueFilter) => void;
  query: string;
  setQuery: (q: string) => void;
}) {
  const { t, lang } = useT();
  const { openRoute } = useTabs();
  const count = (level: QueueFilter) => (level === 'all' ? rows.length : rows.filter((r) => r.nivel === level).length);
  const shown = rows.filter((r) => (filter === 'all' || r.nivel === filter) && matches(query, r.numero, r.contraparte));

  const columns: Columns<InvoiceRow> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => <StatusPill group='prioridad' state={r.nivel} /> },
    {
      key: 'invoice',
      header: t.columns.invoice,
      primary: true,
      cell: (r) => <InvoiceCell numero={r.numero} party={r.contraparte} />,
    },
    { key: 'amount', header: t.columns.amount, align: 'right', width: '7.5rem', cell: (r) => <Money cents={r.total_cent} /> },
    { key: 'due', header: t.columns.due, width: '7rem', cell: (r) => <DateText value={r.vencimiento} /> },
    { key: 'why', header: t.columns.why, cell: (r) => <WhyCell why={whyOf(r, lang, t)} /> },
  ];

  return (
    <>
      <div className='mb-3 flex flex-wrap items-center justify-between gap-3'>
        <FilterChips<QueueFilter>
          label={t.workQueue.filterLabel}
          value={filter}
          onChange={setFilter}
          chips={[
            { key: 'all', label: t.workQueue.filters.all, count: count('all') },
            { key: 'bloqueada', label: t.workQueue.filters.blocked, count: count('bloqueada') },
            { key: 'urgente', label: t.workQueue.filters.urgent, count: count('urgente') },
            { key: 'atencion', label: t.workQueue.filters.attention, count: count('atencion') },
          ]}
        />
        <SearchBox value={query} onChange={setQuery} placeholder={t.workQueue.search} />
      </div>
      {rows.length === 0 ? (
        <EmptyState icon={CircleCheck} title={t.empty.nothingNeedsAttention} text={t.workQueue.empty} />
      ) : (
        <DataTable
          columns={columns}
          rows={shown}
          rowKey={(r) => r.id}
          caption={t.workQueue.caption}
          onOpen={(r) => openRoute(recordRoute('invoice', r.id, 'work-queue'))}
          openLabel={(r) => fmt(t.common.openRecord, { what: `${t.records.invoice.label} ${r.numero ?? r.id}` })}
          empty={<EmptyState title={t.empty.noMatch} text={t.empty.noMatchText} />}
        />
      )}
      {shown.length > 0 && (
        <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.workQueue.total, { shown: shown.length, all: rows.length })}</p>
      )}
    </>
  );
}

/** Numero (mono) y relacion debajo: texto del documento, tal cual. */
export function InvoiceCell({ numero, party }: { numero: string | null; party: string | null }) {
  return (
    <span className='flex min-w-0 flex-col items-start'>
      <span className='whitespace-nowrap font-mono text-[12.5px]'>{numero ?? '—'}</span>
      <span className='text-[13px] font-normal text-[#45423c]'>{party ?? '—'}</span>
    </span>
  );
}
