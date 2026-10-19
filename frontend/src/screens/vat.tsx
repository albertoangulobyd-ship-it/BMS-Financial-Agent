// Btw (VAT): "hoe staat de btw per kwartaal, en wat moet er nog gebeuren?". Una fila por
// trimestre, el mas reciente primero: su estado (en texto y color), el saldo (a pagar o a
// devolver), hasta cuando hay para la aangifte y que hacer ahora, en palabras. Una fila abre
// el trimestre en una pestana. La aangifte la hace una persona en el portal; esto no
// presenta nada.
import { Info } from 'lucide-react';
import { DataTable, type Columns } from '@/components/data-table';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText } from '@/components/values';
import { fmt, useT, type Messages } from '@/i18n';
import { paths } from '@/lib/api';
import type { VatSummary } from '@/lib/api-types';
import { formatMoney, quarterLabel, quarterToId } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { cn } from '@/lib/utils';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

export interface QuarterRow {
  etiqueta: string;
  estado: string;
  terminado: boolean;
  saldo_cent: number;
  limite_presentacion: string | null;
  dias_para_limite: number | null;
}

/** Los trimestres de la lista: el actual y los anteriores, sin repetir, el mas nuevo primero. */
export function quarterRows(summary: VatSummary): QuarterRow[] {
  const seen = new Map<string, QuarterRow>();
  const a = summary.actual;
  seen.set(a.etiqueta, {
    etiqueta: a.etiqueta,
    estado: a.estado,
    terminado: a.terminado,
    saldo_cent: a.cifras['5c'],
    limite_presentacion: a.limite_presentacion,
    dias_para_limite: a.dias_para_limite,
  });
  for (const q of [...summary.por_presentar, ...summary.anteriores]) {
    if (seen.has(q.etiqueta)) continue;
    seen.set(q.etiqueta, {
      etiqueta: q.etiqueta,
      estado: q.estado,
      terminado: true,
      saldo_cent: q['5c'],
      limite_presentacion: q.limite_presentacion,
      dias_para_limite: q.dias_para_limite,
    });
  }
  return [...seen.values()].sort((x, y) => (x.etiqueta < y.etiqueta ? 1 : -1));
}

/** Lo que dice el saldo: a pagar, a devolver o nada. */
export function balanceText(cents: number, t: Messages): string {
  if (cents > 0) return fmt(t.vat.toPay, { amount: formatMoney(cents) });
  if (cents < 0) return fmt(t.vat.refund, { amount: formatMoney(-cents) });
  // Un importe como los demas de la columna (no una palabra).
  return formatMoney(0);
}

export function nextStep(row: Pick<QuarterRow, 'estado' | 'terminado'>, t: Messages): string {
  if (row.estado === 'presentado') return t.vat.nextFiled;
  if (row.estado === 'listo_revision') return t.vat.nextFile;
  return row.terminado ? t.vat.nextCheck : t.vat.nextRunning;
}

export function VatScreen() {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () => session!.api.get<{ btw: VatSummary }>(paths.vat).then((r) => r.btw),
    [session, version]
  );
  const nav = t.nav.vat;
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} meta={<HelpTip term='btw' />} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && <VatList summary={state.data} />}
    </Screen>
  );
}

function VatList({ summary }: { summary: VatSummary }) {
  const { t } = useT();
  const { openRoute } = useTabs();
  const rows = quarterRows(summary);
  const columns: Columns<QuarterRow> = [
    {
      key: 'quarter',
      header: t.vat.quarter,
      primary: true,
      width: '9rem',
      cell: (r) => <span className='whitespace-nowrap font-semibold'>{quarterLabel(r.etiqueta)}</span>,
    },
    {
      key: 'status',
      header: t.vat.status,
      width: '15rem',
      cell: (r) => <StatusPill group='btw' state={r.estado} />,
    },
    { key: 'balance', header: t.vat.balance, align: 'right', width: '11rem', cell: (r) => <span className='num'>{balanceText(r.saldo_cent, t)}</span> },
    { key: 'deadline', header: t.vat.deadline, width: '10rem', cell: (r) => <Deadline row={r} /> },
    { key: 'next', header: t.vat.next, cell: (r) => <span className='text-[13px]'>{nextStep(r, t)}</span> },
  ];
  return (
    <div className='flex flex-col gap-4'>
      <p className='flex items-start gap-2 rounded-md border border-border bg-card px-4 py-3 text-[13px] leading-relaxed'>
        <Info className='mt-0.5 h-4 w-4 shrink-0 text-muted-foreground' aria-hidden='true' />
        <span>{t.vat.note}</span>
      </p>
      {!summary.actual.configuracion.confirmada && <ConfigNotConfirmed />}
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.etiqueta}
        caption={t.nav.vat.description}
        onOpen={(r) => {
          const id = quarterToId(r.etiqueta);
          if (id) openRoute(recordRoute('vat-quarter', id, 'vat'));
        }}
        openLabel={(r) => fmt(t.common.openRecord, { what: fmt(t.vat.title, { quarter: quarterLabel(r.etiqueta) }) })}
        empty={<EmptyState title={t.empty.nothingHere} text={t.vat.empty} />}
      />
    </div>
  );
}

/** Los trimestres con el plazo de la aangifte pasado y sin la presentacion anotada, el mas
 *  viejo primero. El panel los da en `por_presentar` (con sus dias, negativos) y sus
 *  etiquetas en `plazos_pasados`; `proximo_plazo` solo mira los que no han pasado, asi que
 *  sin esto el Overzicht saltaria al trimestre siguiente y no diria nada. */
export function overdueQuarters(btw: {
  por_presentar: { trimestre: string; estado: string; dias_para_limite: number | null }[];
  plazos_pasados: string[];
}): string[] {
  const late = btw.por_presentar
    .filter((q) => q.estado !== 'presentado' && q.dias_para_limite !== null && q.dias_para_limite < 0)
    .map((q) => q.trimestre);
  return [...new Set([...late, ...btw.plazos_pasados])].sort();
}

/** Cuando el plazo pide atencion: pasado y sin aangifte (error) o a 14 dias o menos
 *  (warning, con los dias que quedan); con mas margen, solo los dias, en gris. */
export const DEADLINE_CLOSE_DAYS = 14;

export function deadlineState(row: Pick<QuarterRow, 'estado' | 'dias_para_limite'>): 'plazo_vencido' | 'plazo_cerca' | null {
  const days = row.dias_para_limite;
  if (row.estado === 'presentado' || days === null) return null;
  if (days < 0) return 'plazo_vencido';
  return days <= DEADLINE_CLOSE_DAYS ? 'plazo_cerca' : null;
}

export function Deadline({ row }: { row: Pick<QuarterRow, 'estado' | 'limite_presentacion' | 'dias_para_limite'> }) {
  const { t } = useT();
  const days = row.dias_para_limite;
  const filed = row.estado === 'presentado';
  const state = deadlineState(row);
  return (
    <span className='flex flex-col items-start gap-1'>
      <DateText value={row.limite_presentacion} />
      {state ? (
        <StatusPill group='btw' state={state} values={days !== null ? { n: days } : undefined} />
      ) : (
        !filed &&
        days !== null && (
          <span className='text-xs text-muted-foreground'>{fmt(days === 1 ? t.vat.dayLeft : t.vat.daysLeft, { n: days })}</span>
        )
      )}
    </span>
  );
}

/** La configuracion del btw sin confirmar con el asesor: el estado y, al lado, la frase. */
export function ConfigNotConfirmed({ className }: { className?: string }) {
  const { t } = useT();
  return (
    <p className={cn('flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]', className)}>
      <StatusPill group='btw_config' state='sin_confirmar' />
      <span>{t.vat.configNotConfirmed}</span>
    </p>
  );
}
