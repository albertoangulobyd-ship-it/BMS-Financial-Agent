// BASE del paso 15: la werklijst en su forma minima (prioridad, numero, relacion, importe,
// vencimiento y pago), para que la navegacion por pestanas tenga una lista de verdad: una
// fila abre su factura en una pestana. La version completa (con la columna "Waarom" de
// los catalogos de textos) la construye la parte siguiente.
import { DataTable, type Columns } from '@/components/data-table';
import { PageHeader, Screen } from '@/components/page-header';
import { PriorityPill } from '@/components/priority-pill';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { StatusText, type StatusTone } from '@/components/status-text';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText, Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { paymentStateLabel } from '@/i18n/domain';
import { paths, type InvoiceRow } from '@/lib/api';
import { useSession } from '@/lib/session';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

const PAYMENT_TONE: Record<string, StatusTone> = {
  pendiente: 'neutral',
  vencida: 'late',
  pagada: 'ok',
  anulada: 'muted',
  acreditada: 'muted',
};

export function WorkQueueScreen() {
  const { t, lang } = useT();
  const { session } = useSession();
  const { openRoute } = useTabs();
  const [state, retry] = useLoad(
    () => session!.api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas),
    [session]
  );
  const nav = t.nav['work-queue'];

  const columns: Columns<InvoiceRow> = [
    { key: 'priority', header: t.priority.column, width: '8.5rem', cell: (r) => <PriorityPill priority={r.nivel} /> },
    {
      key: 'number',
      header: t.workQueue.columns.number,
      primary: true,
      cell: (r) => <span className='whitespace-nowrap font-mono text-[12.5px]'>{r.numero ?? '—'}</span>,
    },
    { key: 'party', header: t.workQueue.columns.party, cell: (r) => r.contraparte ?? '—' },
    { key: 'amount', header: t.workQueue.columns.amount, align: 'right', cell: (r) => <Money cents={r.total_cent} /> },
    { key: 'due', header: t.workQueue.columns.due, cell: (r) => <DateText value={r.vencimiento} /> },
    {
      key: 'payment',
      header: t.workQueue.columns.payment,
      cell: (r) => (
        <StatusText tone={PAYMENT_TONE[r.estado_pago ?? ''] ?? 'neutral'}>
          {paymentStateLabel(lang, r.estado_pago) ?? t.common.unknown}
        </StatusText>
      ),
    },
  ];

  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <>
          <p className='mb-2 text-xs text-muted-foreground'>
            {fmt(t.workQueue.total, { count: state.data.length })} · {t.workQueue.baseNote}
          </p>
          <DataTable
            columns={columns}
            rows={state.data}
            rowKey={(r) => r.id}
            caption={t.workQueue.caption}
            onOpen={(r) => openRoute(recordRoute('invoice', r.id, 'work-queue'))}
            openLabel={(r) => `${t.records.invoice.label} ${r.numero ?? r.id}`}
            empty={<EmptyState title={t.empty.nothingHere} text={t.workQueue.empty} />}
          />
        </>
      )}
    </Screen>
  );
}
