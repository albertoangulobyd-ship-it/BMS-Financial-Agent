// Verkoopfacturen / Inkoopfacturen: "welke facturen aan klanten (of van leveranciers) zijn
// er, en hoe staan ze ervoor?". Todas las de un sentido, con fichas para filtrar y un
// buscador. Paso 16 (Cuentas por cobrar y por pagar): las fichas de pago son las de la
// cartera del motor (lo que esta abierto, lo vencido, esta semana, 30 dias, un tramo de
// antiguedad) y suman lo mismo que la cifra que se pulso en el resumen; "Por confirmar" son
// las que tienen un pago propuesto por el banco. Seis columnas: prioridad (la unica pastilla
// de color de la fila), factura, lo que queda, vencimiento ("12 dias tarde", "en 4 dias"),
// estado (pago y control, en texto gris) y por que. Una fila abre su factura.
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
import { paymentStateLabel, reviewStateLabel, ruleText } from '@/i18n/domain';
import { paths, type InvoiceRow } from '@/lib/api';
import type { Cartera, PaymentProposal } from '@/lib/api-types';
import { formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useViewState } from '@/lib/view-memory';
import { matches } from '@/lib/text';
import { twinMarks } from '@/lib/twins';
import { whyOf } from '@/lib/why';
import {
  INVOICE_FILTERS,
  byDue,
  isInvoiceFilter,
  livePaymentState,
  matchesFilter,
  pendingSum,
  proposalsOf,
  sortsByDue,
  waitingInvoices,
  windowsOf,
  type InvoiceFilter,
  type Side,
} from './money-model';
import { DueText } from './money-overview';
import { recordRoute, type ViewId } from './registry';
import { useLoad } from './use-load';
import { InvoiceCell } from './work-queue';

export function InvoiceListScreen({ navId, navKey }: { navId: Extract<ViewId, 'invoices-in' | 'invoices-out'>; navKey: string }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const { open: openRoute } = useNav();
  const side: Side = navId === 'invoices-in' ? 'entrante' : 'saliente';
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas.filter((f) => f.sentido === side)),
        // Las ventanas de la cartera (esta semana, 30 dias, los tramos) y el hoy del motor.
        session!.api.get<{ cartera: Cartera }>(paths.cartera, { sentido: side }).then((r) => r.cartera),
        session!.api.get<{ propuestas: PaymentProposal[] }>(paths.proposals, { sentido: side }).then((r) => proposalsOf(r.propuestas, side)),
      ]),
    [session, version, side]
  );
  const [stored, setFilter] = useViewState<string>(navKey, `${navId}-filter`, 'all');
  const filter: InvoiceFilter = isInvoiceFilter(stored) ? stored : 'all';
  const [query, setQuery] = useViewState<string>(navKey, `${navId}-query`, '');
  const nav = t.nav[navId];
  const rows = state.status === 'ready' ? state.data[0] : [];
  const cartera = state.status === 'ready' ? state.data[1] : null;
  const windows = cartera ? windowsOf(cartera) : null;
  const waiting = waitingInvoices(state.status === 'ready' ? state.data[2] : []);
  const twins = twinMarks(rows);
  const today = cartera?.hoy ?? null;

  const columns: Columns<InvoiceRow> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => <StatusPill group='prioridad' state={r.nivel} /> },
    {
      key: 'invoice',
      header: t.columns.invoice,
      primary: true,
      cell: (r) => <InvoiceCell numero={r.numero} party={r.contraparte} twin={twins.get(r.id)} />,
    },
    {
      key: 'amount',
      header: t.columns.outstanding,
      align: 'right',
      width: '8rem',
      // Lo que queda; si no es el total, el total debajo.
      cell: (r) => (
        <span className='flex flex-col items-end'>
          <Money cents={r.estado_pago === 'pagada' ? 0 : r.pendiente_cent} />
          {r.total_cent !== null && r.pendiente_cent !== r.total_cent && (
            <span className='text-xs text-muted-foreground'>{fmt(t.money.ofTotal, { amount: formatMoney(r.total_cent) })}</span>
          )}
        </span>
      ),
    },
    {
      key: 'due',
      header: t.columns.due,
      width: '9rem',
      cell: (r) => (
        <span className='flex flex-col'>
          <DateText value={r.vencimiento} />
          {(r.estado_pago === 'pendiente' || r.estado_pago === 'vencida') && <DueText due={r.vencimiento} today={today} />}
        </span>
      ),
    },
    {
      key: 'status',
      header: t.columns.status,
      width: '11rem',
      // En texto: el color de la fila lo lleva la prioridad (lo vencido lo dice el vencimiento).
      // El estado de pago con el hoy del motor (la cache puede ser de otro dia) y "pagada"
      // siempre con su fuente (decision 5: el banco, Exact o a mano, con K3).
      cell: (r) => {
        const state = livePaymentState(r, today);
        return (
          <span className='flex flex-col items-start text-[13px] leading-snug'>
            <span data-testid='payment-state'>{paymentStateLabel(lang, state ?? '') ?? '—'}</span>
            {state === 'pagada' && <PaidSourceShort row={r} />}
            {waiting.has(r.id) && <span className='font-medium text-soft-foreground'>{t.money.waitingProposal}</span>}
            <span className='text-muted-foreground'>{reviewStateLabel(lang, r.estado_revision ?? '') ?? '—'}</span>
          </span>
        );
      },
    },
    { key: 'why', header: t.columns.why, cell: (r) => <WhyCell why={whyOf(r, lang, t)} /> },
  ];

  const chipLabel = (key: InvoiceFilter): string => {
    switch (key) {
      case 'all':
        return t.invoices.any;
      case 'open':
        return t.money.outstanding;
      case 'vencida':
      case 'pagada':
        return paymentStateLabel(lang, key) ?? key;
      case 'necesita_revision':
        return reviewStateLabel(lang, key) ?? key;
      case 'week':
        return t.money.chips.week;
      case 'next30':
        return t.money.chips.next30;
      case 'por_confirmar':
        return t.money.chips.toConfirm;
      default:
        return t.money.ageing.buckets[key.slice(6) as keyof typeof t.money.ageing.buckets];
    }
  };
  // Un tramo de antiguedad (se llega desde la barra del resumen) sale como una ficha mas.
  const keys: InvoiceFilter[] = [...INVOICE_FILTERS, ...(filter.startsWith('tramo:') ? [filter] : [])];
  const count = (key: InvoiceFilter) => rows.filter((r) => matchesFilter(key, r, side, windows, waiting)).length;
  const filtered = rows.filter((r) => matchesFilter(filter, r, side, windows, waiting) && matches(query, r.numero, r.contraparte));
  const shown = sortsByDue(filter) ? byDue(filtered) : filtered;

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
              chips={keys.map((key) => ({ key, label: chipLabel(key), count: count(key) }))}
            />
            <SearchBox value={query} onChange={setQuery} placeholder={t.workQueue.search} />
          </div>
          <ListBody
            rows={shown}
            total={rows.length}
            columns={columns}
            caption={nav.description}
            sum={sortsByDue(filter) && filter !== 'por_confirmar' ? pendingSum(shown) : null}
            onOpen={(r) => openRoute(recordRoute('invoice', r.id))}
          />
        </>
      )}
    </Screen>
  );
}

/** De donde sale "pagada" en una fila: "volgens de bank", "volgens Exact" o "met de hand,
 *  nog niet in de bank" (y el aviso K3 mientras siga abierto). */
function PaidSourceShort({ row }: { row: InvoiceRow }) {
  const { t, lang } = useT();
  const source = row.fuente_pago;
  if (!source) return null;
  const k3 = (row.razones ?? []).some((h) => h.regla === 'K3' && h.estado === 'abierto');
  const text = source === 'banco' ? t.payments.listBank : source === 'exact' ? t.payments.listExact : t.payments.listManual;
  return (
    <span data-testid='paid-source-short' className='text-xs text-soft-foreground'>
      {text}
      {k3 && <span className='block font-medium text-late-foreground'>{ruleText(lang, 'K3')?.title ?? 'K3'}</span>}
    </span>
  );
}

function ListBody({
  rows,
  total,
  columns,
  caption,
  sum,
  onOpen,
}: {
  rows: InvoiceRow[];
  total: number;
  columns: Columns<InvoiceRow>;
  caption: string;
  /** Lo que suman las filas de una ficha de pago (lo mismo que su cifra del resumen). */
  sum: number | null;
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
        <p className='mt-2 flex flex-wrap gap-x-3 text-xs text-muted-foreground'>
          <span>{fmt(t.workQueue.total, { shown: rows.length, all: total })}</span>
          {sum !== null && <span data-testid='list-sum'>{fmt(t.money.listSum, { amount: formatMoney(sum) })}</span>}
        </p>
      )}
    </>
  );
}
