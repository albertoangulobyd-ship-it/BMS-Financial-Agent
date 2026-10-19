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
import { StatusText } from '@/components/status-text';
import { VAT_TONE } from '@/components/tones';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText } from '@/components/values';
import { fmt, useT, type Messages } from '@/i18n';
import { stateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { VatSummary } from '@/lib/api-types';
import { formatMoney, quarterLabel, quarterToId } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
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
  return t.vat.nothing;
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
  const { t, lang } = useT();
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
      cell: (r) => <StatusText tone={VAT_TONE[r.estado] ?? 'neutral'}>{stateLabel(lang, 'btw', r.estado) ?? r.estado}</StatusText>,
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
      {!summary.actual.configuracion.confirmada && (
        <p className='text-[13px] text-late-foreground'>{t.vat.configNotConfirmed}</p>
      )}
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

export function Deadline({ row }: { row: Pick<QuarterRow, 'estado' | 'limite_presentacion' | 'dias_para_limite'> }) {
  const { t } = useT();
  const days = row.dias_para_limite;
  const filed = row.estado === 'presentado';
  return (
    <span className='flex flex-col'>
      <DateText value={row.limite_presentacion} />
      {!filed && days !== null && (
        <span className={days < 0 ? 'text-xs font-medium text-late-foreground' : days <= 14 ? 'text-xs text-late-foreground' : 'text-xs text-muted-foreground'}>
          {days < 0 ? t.vat.late : fmt(days === 1 ? t.vat.dayLeft : t.vat.daysLeft, { n: days })}
        </span>
      )}
    </span>
  );
}
