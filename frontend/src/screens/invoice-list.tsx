// Inkomend / Uitgaand (In / Out): "welke facturen van leveranciers (of aan klanten) zijn
// er, en hoe staan ze ervoor?". Todas las de un sentido, la mas urgente primero, con dos
// filtros sencillos (betaling, nakijken) y un buscador. Seis columnas: prioridad, factura,
// importe, vencimiento, estado (pago y revision, en texto) y por que. Una fila abre su
// factura en una pestana.
import { DataTable, type Columns } from '@/components/data-table';
import { PageHeader, Screen } from '@/components/page-header';
import { SearchBox } from '@/components/search-box';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText, Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { fmt, useT } from '@/i18n';
import { paymentStateLabel, reviewStateLabel } from '@/i18n/domain';
import { paths, type InvoiceRow } from '@/lib/api';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useTabState } from '@/lib/tab-memory';
import { matches } from '@/lib/text';
import { whyOf } from '@/lib/why';
import { recordRoute, type NavId } from './registry';
import { useLoad } from './use-load';

const PAYMENT = ['pendiente', 'vencida', 'pagada', 'anulada', 'acreditada'] as const;
const REVIEW = ['sin_revisar', 'necesita_revision', 'revisada'] as const;

export function InvoiceListScreen({ navId, tabId }: { navId: Extract<NavId, 'invoices-in' | 'invoices-out'>; tabId: string }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const { openRoute } = useTabs();
  const direction = navId === 'invoices-in' ? 'entrante' : 'saliente';
  const [state, retry] = useLoad(
    () =>
      session!.api
        .get<{ facturas: InvoiceRow[] }>(paths.invoices)
        .then((r) => r.facturas.filter((f) => f.sentido === direction)),
    [session, version, direction]
  );
  const [payment, setPayment] = useTabState<string>(tabId, `${navId}-payment`, '');
  const [review, setReview] = useTabState<string>(tabId, `${navId}-review`, '');
  const [query, setQuery] = useTabState<string>(tabId, `${navId}-query`, '');
  const nav = t.nav[navId];

  const columns: Columns<InvoiceRow> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => <StatusPill group='prioridad' state={r.nivel} /> },
    {
      key: 'invoice',
      header: t.columns.invoice,
      primary: true,
      cell: (r) => (
        <span className='flex min-w-0 flex-col items-start'>
          <span className='whitespace-nowrap font-mono text-[12.5px]'>{r.numero ?? '—'}</span>
          <span className='text-[13px] font-normal text-[#45423c]'>{r.contraparte ?? '—'}</span>
        </span>
      ),
    },
    { key: 'amount', header: t.columns.amount, align: 'right', width: '7.5rem', cell: (r) => <Money cents={r.total_cent} /> },
    { key: 'due', header: t.columns.due, width: '7rem', cell: (r) => <DateText value={r.vencimiento} /> },
    {
      key: 'status',
      header: t.columns.status,
      width: '11rem',
      cell: (r) => (
        <span className='flex flex-col items-start gap-1'>
          <StatusPill group='pago' state={r.estado_pago} />
          <StatusPill group='revision' state={r.estado_revision} />
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
          <div className='mb-3 flex flex-wrap items-end justify-between gap-3'>
            <div className='flex flex-wrap items-end gap-3'>
              <Select
                label={t.invoices.paymentFilter}
                value={payment}
                onChange={setPayment}
                options={[
                  { value: '', label: t.invoices.any },
                  ...PAYMENT.map((p) => ({ value: p, label: paymentStateLabel(lang, p) ?? p })),
                ]}
              />
              <Select
                label={t.invoices.reviewFilter}
                value={review}
                onChange={setReview}
                options={[
                  { value: '', label: t.invoices.any },
                  ...REVIEW.map((p) => ({ value: p, label: reviewStateLabel(lang, p) ?? p })),
                ]}
              />
            </div>
            <SearchBox value={query} onChange={setQuery} placeholder={t.workQueue.search} />
          </div>
          <ListBody
            rows={state.data.filter(
              (r) =>
                (!payment || r.estado_pago === payment) &&
                (!review || r.estado_revision === review) &&
                matches(query, r.numero, r.contraparte)
            )}
            total={state.data.length}
            columns={columns}
            caption={nav.description}
            onOpen={(r) => openRoute(recordRoute('invoice', r.id, navId))}
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

export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className='flex flex-col gap-1 text-xs font-medium text-muted-foreground'>
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className='h-9 min-w-[10rem] rounded-md border border-input bg-card px-2.5 text-[13px] font-normal text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
