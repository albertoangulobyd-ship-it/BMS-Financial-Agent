// Kasstroom (Cash flow): "wat komt er de komende weken binnen, en wat gaat eruit?". Una sola
// tabla: los periodos (ya vencido, esta semana, el resto del mes, los proximos 30 dias, sin
// fecha y todo lo abierto) con lo que entra, lo que sale y el neto, de las facturas abiertas
// por su vencimiento. Debajo, lo que ya se movio este mes segun el banco y, aparte y marcado
// como tal, la estimacion del planning: trabajo aun sin facturar, que no son facturas y no
// se suma a la tabla. Sin graficos.
import { DataTable, type Columns } from '@/components/data-table';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { paths } from '@/lib/api';
import type { CashFlow, CashWindowKey } from '@/lib/api-types';
import { formatDate } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { cn } from '@/lib/utils';
import { useLoad } from './use-load';

const WINDOWS: readonly CashWindowKey[] = ['vencido', 'semana', 'mes', 'proximos_30', 'sin_fecha', 'total'];

interface WindowRow {
  key: CashWindowKey;
  entrada: number | null;
  salida: number | null;
  neto: number | null;
  range: [string, string] | null;
}

export function CashFlowScreen() {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () => session!.api.get<{ flujo_caja: CashFlow }>(paths.cashFlow).then((r) => r.flujo_caja),
    [session, version]
  );
  const nav = t.nav['cash-flow'];
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && <CashFlowContent flow={state.data} />}
    </Screen>
  );
}

function CashFlowContent({ flow }: { flow: CashFlow }) {
  const { t } = useT();
  const e = flow.esperado;
  const rows: WindowRow[] = WINDOWS.filter((k) => k !== 'sin_fecha' || (e.entrada.sin_fecha ?? 0) + (e.salida.sin_fecha ?? 0) !== 0).map(
    (key) => ({
      key,
      entrada: e.entrada[key],
      salida: e.salida[key],
      neto: e.neto[key],
      range: flow.ventanas[key] ?? null,
    })
  );
  const net = (cents: number | null) => (
    <Money cents={cents} className={cn('font-medium', (cents ?? 0) < 0 && 'text-late-foreground')} />
  );
  const columns: Columns<WindowRow> = [
    {
      key: 'period',
      header: t.cash.period,
      cell: (r) => (
        <span className={cn('flex flex-col', r.key === 'total' && 'font-semibold')}>
          <span>{t.cash.windows[r.key]}</span>
          {r.key === 'vencido' && <span className='text-xs font-normal text-muted-foreground'>{t.cash.overdueHelp}</span>}
          {r.range && (
            <span className='num text-xs font-normal text-muted-foreground'>
              {fmt(t.cash.range, { from: formatDate(r.range[0]), to: formatDate(r.range[1]) })}
            </span>
          )}
        </span>
      ),
    },
    { key: 'in', header: t.cash.moneyIn, align: 'right', width: '11rem', cell: (r) => <Money cents={r.entrada} /> },
    { key: 'out', header: t.cash.moneyOut, align: 'right', width: '11rem', cell: (r) => <Money cents={r.salida} /> },
    { key: 'net', header: t.cash.net, align: 'right', width: '11rem', cell: (r) => net(r.neto) },
  ];

  return (
    <div className='flex flex-col gap-8'>
      {flow.facturas === 0 ? (
        <EmptyState title={t.empty.nothingHere} text={t.invoices.empty} />
      ) : (
        <div className='max-w-4xl'>
          <DataTable columns={columns} rows={rows} rowKey={(r) => r.key} caption={t.nav['cash-flow'].description} />
          <p className='mt-2 text-xs text-muted-foreground'>{t.cash.note}</p>
        </div>
      )}

      <section aria-labelledby='cash-real' className='max-w-4xl'>
        <h2 id='cash-real' className='mb-2 text-[15px] font-semibold'>
          {t.cash.realTitle}
        </h2>
        <dl className='grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border text-[13px]'>
          <div className='bg-card px-4 py-3'>
            <dt className='text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>{t.cash.received}</dt>
            <dd className='m-0 mt-1'>
              <Money cents={flow.real.cobrado.mes} className='text-[15px] font-semibold' />
            </dd>
          </div>
          <div className='bg-card px-4 py-3'>
            <dt className='text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>{t.cash.paid}</dt>
            <dd className='m-0 mt-1'>
              <Money cents={flow.real.pagado.mes} className='text-[15px] font-semibold' />
            </dd>
          </div>
        </dl>
        <p className='mt-2 text-xs text-muted-foreground'>{t.cash.bankNote}</p>
      </section>

      <Estimate flow={flow} />
    </div>
  );
}

/** La linea aparte del planning: con borde de rayas y su etiqueta, para que nadie la lea
 *  como facturas. */
function Estimate({ flow }: { flow: CashFlow }) {
  const { t } = useT();
  const est = flow.estimado;
  const hasEstimate = est.importe_cent !== null && est.importe_cent !== undefined;
  const income = (est.entrada_sin_facturar_cent ?? 0) + (est.entrada_planificada_cent ?? 0);
  const costs = (est.salida_sin_facturar_cent ?? 0) + (est.salida_planificada_cent ?? 0);
  return (
    <section aria-labelledby='cash-estimate' className='max-w-4xl rounded-md border border-dashed border-border-strong px-5 py-4'>
      <div className='mb-1 flex flex-wrap items-baseline justify-between gap-3'>
        <h2 id='cash-estimate' className='text-[15px] font-semibold'>
          {t.cash.estimateTitle}
        </h2>
        <span className='rounded-[3px] border border-border-strong px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>
          {t.cash.estimateBadge}
        </span>
      </div>
      <p className='mb-3 text-[13px] text-soft-foreground'>{t.cash.estimateText}</p>
      {hasEstimate ? (
        <dl className='grid max-w-xl grid-cols-[1fr_auto] gap-x-6 gap-y-1.5 text-[13px]'>
          <dt>{t.cash.estimateIn}</dt>
          <dd className='m-0 text-right'>
            <Money cents={income} />
          </dd>
          <dt>{t.cash.estimateOut}</dt>
          <dd className='m-0 text-right'>
            <Money cents={-costs} />
          </dd>
          <dt className='font-semibold'>{t.cash.estimateNet}</dt>
          <dd className='m-0 text-right font-semibold'>
            <Money cents={est.importe_cent} />
          </dd>
        </dl>
      ) : (
        <p className='text-muted-foreground'>{t.cash.noEstimate}</p>
      )}
      {hasEstimate && est.aproximado && <p className='mt-2 text-xs text-muted-foreground'>{t.cash.approximate}</p>}
    </section>
  );
}
