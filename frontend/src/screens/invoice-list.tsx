// Inkomend / Uitgaand (In / Out): "welke facturen van leveranciers (of aan klanten) zijn
// er, en hoe staan ze ervoor?". Todas las de un sentido, la mas urgente primero, con fichas
// para filtrar (como la Werklijst: Alle, Vervallen, Openstaand, Controle nodig, Betaald) y un
// buscador. Seis columnas: prioridad, factura, importe, vencimiento, estado (pago y control,
// en texto gris: una sola pastilla de color por fila, la prioridad) y por que. Una fila abre
// su factura en una pestana.
import { DataTable, type Columns } from '@/components/data-table';
import { FilterChips } from '@/components/filter-chips';
import { PageHeader, Screen } from '@/components/page-header';
import { SearchBox } from '@/components/search-box';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { useNav } from '@/shell/navigation';
import { DateText, Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { fmt, useT } from '@/i18n';
import { paymentStateLabel, reviewStateLabel } from '@/i18n/domain';
import { paths, type InvoiceRow } from '@/lib/api';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useViewState } from '@/lib/view-memory';
import { matches } from '@/lib/text';
import { twinMarks } from '@/lib/twins';
import { whyOf } from '@/lib/why';
import { recordRoute, type ViewId } from './registry';
import { useLoad } from './use-load';
import { InvoiceCell } from './work-queue';

/** Las fichas de la lista: una vista cada una (el pago o el control). */
export const INVOICE_FILTERS = ['all', 'vencida', 'pendiente', 'necesita_revision', 'pagada'] as const;
export type InvoiceFilter = (typeof INVOICE_FILTERS)[number];

export function invoiceFilter(filter: InvoiceFilter, r: Pick<InvoiceRow, 'estado_pago' | 'estado_revision'>): boolean {
  if (filter === 'all') return true;
  if (filter === 'necesita_revision') return r.estado_revision === 'necesita_revision';
  return r.estado_pago === filter;
}

export function InvoiceListScreen({ navId, navKey }: { navId: Extract<ViewId, 'invoices-in' | 'invoices-out'>; navKey: string }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const { open: openRoute } = useNav();
  const direction = navId === 'invoices-in' ? 'entrante' : 'saliente';
  const [state, retry] = useLoad(
    () =>
      session!.api
        .get<{ facturas: InvoiceRow[] }>(paths.invoices)
        .then((r) => r.facturas.filter((f) => f.sentido === direction)),
    [session, version, direction]
  );
  const [stored, setFilter] = useViewState<string>(navKey, `${navId}-filter`, 'all');
  const filter: InvoiceFilter = (INVOICE_FILTERS as readonly string[]).includes(stored) ? (stored as InvoiceFilter) : 'all';
  const [query, setQuery] = useViewState<string>(navKey, `${navId}-query`, '');
  const nav = t.nav[navId];
  const twins = twinMarks(state.status === 'ready' ? state.data : []);

  const columns: Columns<InvoiceRow> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => <StatusPill group='prioridad' state={r.nivel} /> },
    {
      key: 'invoice',
      header: t.columns.invoice,
      primary: true,
      cell: (r) => <InvoiceCell numero={r.numero} party={r.contraparte} twin={twins.get(r.id)} />,
    },
    { key: 'amount', header: t.columns.amount, align: 'right', width: '7.5rem', cell: (r) => <Money cents={r.total_cent} /> },
    { key: 'due', header: t.columns.due, width: '7rem', cell: (r) => <DateText value={r.vencimiento} /> },
    {
      key: 'status',
      header: t.columns.status,
      width: '11rem',
      // En texto: el color de la fila lo lleva la prioridad (lo vencido lo dice "Waarom").
      cell: (r) => (
        <span className='flex flex-col items-start text-[13px] leading-snug'>
          <span>{paymentStateLabel(lang, r.estado_pago ?? '') ?? '—'}</span>
          <span className='text-muted-foreground'>{reviewStateLabel(lang, r.estado_revision ?? '') ?? '—'}</span>
        </span>
      ),
    },
    { key: 'why', header: t.columns.why, cell: (r) => <WhyCell why={whyOf(r, lang, t)} /> },
  ];

  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <>
          <div className='mb-3 flex flex-wrap items-center justify-between gap-3'>
            <FilterChips<InvoiceFilter>
              label={t.invoices.filterLabel}
              value={filter}
              onChange={setFilter}
              chips={INVOICE_FILTERS.map((key) => ({
                key,
                label:
                  key === 'all'
                    ? t.invoices.any
                    : key === 'necesita_revision'
                      ? (reviewStateLabel(lang, key) ?? key)
                      : (paymentStateLabel(lang, key) ?? key),
                count: state.data.filter((r) => invoiceFilter(key, r)).length,
              }))}
            />
            <SearchBox value={query} onChange={setQuery} placeholder={t.workQueue.search} />
          </div>
          <ListBody
            rows={state.data.filter((r) => invoiceFilter(filter, r) && matches(query, r.numero, r.contraparte))}
            total={state.data.length}
            columns={columns}
            caption={nav.description}
            onOpen={(r) => openRoute(recordRoute('invoice', r.id))}
          />
        </>
      )}
    </Screen>
  );
}

function ListBody({
  rows,
  total,
  columns,
  caption,
  onOpen,
}: {
  rows: InvoiceRow[];
  total: number;
  columns: Columns<InvoiceRow>;
  caption: string;
  onOpen: (r: InvoiceRow) => void;
}) {
  const { t } = useT();
  if (total === 0) return <EmptyState title={t.empty.nothingHere} text={t.invoices.empty} />;
  return (
    <>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        caption={caption}
        onOpen={onOpen}
        openLabel={(r) => fmt(t.common.openRecord, { what: `${t.records.invoice.label} ${r.numero ?? r.id}` })}
        empty={<EmptyState title={t.empty.noMatch} text={t.empty.noMatchText} />}
      />
      {rows.length > 0 && (
        <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.workQueue.total, { shown: rows.length, all: total })}</p>
      )}
    </>
  );
}
