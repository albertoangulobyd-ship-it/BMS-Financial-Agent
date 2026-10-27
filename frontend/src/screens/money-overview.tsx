// Cuentas por cobrar y Cuentas por pagar (paso 16; revision de Aurora §8.4): la misma
// pantalla para los dos lados, sobre la cartera del motor (GET /api/v2/cartera), que sale de
// las mismas partidas y la misma funcion que el panel: la tarjeta del inicio, estas cifras,
// los tramos y las empresas dicen los mismos centimos. Arriba, cuatro cifras ("Saldos
// pendientes · No es efectivo disponible"); la antiguedad (a la vista al cobrar, plegada al
// pagar); lo que espera a una persona (pagos propuestos, lineas del banco sin casar, abonos
// sin enlazar, pagos raros); al pagar, lo limpio y lo retenido hasta el domingo con su
// porque; y cada empresa por lo vencido. Cada cifra, tramo y aviso abre la lista que lo
// explica. Solo lee: las ordenes de pagos estan en la factura y en el banco.
import { ArrowRight, CircleCheck, FolderOpen } from 'lucide-react';
import type { ReactNode } from 'react';
import { DataTable, type Columns } from '@/components/data-table';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import { Money } from '@/components/values';
import { fmt, useT, type Messages } from '@/i18n';
import { ruleText } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { Cartera, CarteraInvoice, CarteraParty, SourceFreshness } from '@/lib/api-types';
import { formatDate, formatDateProse, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { cn } from '@/lib/utils';
import { twinMarks, type TwinMark } from '@/lib/twins';
import { rememberView } from '@/lib/view-memory';
import { useNav } from '@/shell/navigation';
import { BANK_OF, LIST_OF, bucketShares, dueState, partiesByOverdue, type BucketKey, type DueState, type InvoiceFilter, type Side } from './money-model';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

export function MoneyOverviewScreen({ side }: { side: Side; navKey: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const area = side === 'saliente' ? t.areas.receivables : t.areas.payables;
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ cartera: Cartera }>(paths.cartera, { sentido: side }).then((r) => r.cartera),
        // La frescura del banco ("bank van 27-10-2026"): si no se puede leer, no se dice.
        session!.api.get<{ fuentes: SourceFreshness[] }>(paths.sources).then(
          (r) => r.fuentes.find((f) => f.fuente === 'banco' && f.tipo === 'extracto') ?? null,
          () => null
        ),
      ]),
    [session, version, side]
  );
  return (
    <Screen calm>
      <PageHeader
        title={area.label}
        description={area.description}
        meta={<HelpTip term={side === 'saliente' ? 'receivables' : 'payables'} />}
      />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && <Overview side={side} cartera={state.data[0]} bank={state.data[1]} />}
    </Screen>
  );
}

function Overview({ side, cartera: c, bank }: { side: Side; cartera: Cartera; bank: SourceFreshness | null }) {
  const { t } = useT();
  const nav = useNav();
  const list = LIST_OF[side];
  // Una cifra o un tramo abre la lista de facturas con su ficha puesta (la misma suma).
  const openList = (filter: InvoiceFilter) => {
    rememberView(list, `${list}-filter`, filter);
    rememberView(list, `${list}-query`, '');
    nav.go(list);
  };
  const totals = c.totales;
  const counted = (n: number, many: string, one: string) => fmt(n === 1 ? one : many, { n });
  return (
    <div className='flex flex-col gap-8'>
      <section aria-labelledby='money-figures' className='flex flex-col gap-2'>
        <h2 id='money-figures' className='sr-only'>
          {t.money.figures}
        </h2>
        <div className='grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 xl:grid-cols-4'>
          <Figure
            label={t.money.outstanding}
            cents={totals.pendiente_cent}
            caption={counted(totals.facturas, t.money.inInvoices, t.money.inInvoicesOne)}
            onOpen={() => openList('open')}
            big
          />
          <Figure
            label={t.money.overdue}
            cents={totals.vencido_cent}
            caption={counted(totals.vencidas, t.money.overdueInvoices, t.money.overdueInvoicesOne)}
            late={totals.vencido_cent > 0}
            onOpen={() => openList('vencida')}
          />
          <Figure
            label={t.money.thisWeek}
            cents={totals.semana_cent}
            caption={c.fechas.semana ? fmt(t.money.until, { date: formatDateProse(c.fechas.semana[1], t) }) : undefined}
            onOpen={() => openList('week')}
          />
          <Figure
            label={t.money.next30}
            cents={totals.proximos_30_cent}
            caption={c.fechas.proximos_30 ? fmt(t.money.until, { date: formatDateProse(c.fechas.proximos_30[1], t) }) : undefined}
            onOpen={() => openList('next30')}
          />
        </div>
        {/* Lo que no es: dinero en el banco. Y de cuando son los datos. */}
        <p className='flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground'>
          <span className='font-medium text-soft-foreground'>{t.money.note}</span>
          <span>
            {fmt(t.money.asOf, { date: formatDate(c.estado_del) })}
            {bank?.exportado ? ` · ${fmt(t.money.bankFrom, { date: formatDate(bank.exportado) })}` : ''}
          </span>
          {(!c.al_dia || bank?.caducada) && <StatusPill group='fuente' state='caducada' />}
          {totals.sin_fecha_cent > 0 && <span>{fmt(t.money.noDate, { amount: formatMoney(totals.sin_fecha_cent) })}</span>}
          {c.movido_mes_cent !== null && (
            <span>{fmt(side === 'saliente' ? t.money.receivedMonth : t.money.paidMonth, { amount: formatMoney(c.movido_mes_cent) })}</span>
          )}
        </p>
      </section>

      <Notices side={side} cartera={c} />

      {side === 'saliente' ? (
        <section aria-labelledby='money-ageing'>
          <h2 id='money-ageing' className='mb-3 text-[15px] font-semibold'>
            {t.money.ageing.title}
          </h2>
          <Ageing cartera={c} onOpen={(key) => openList(`tramo:${key}`)} />
        </section>
      ) : (
        <>
          <ThisWeek cartera={c} />
          {/* Al pagar, la antiguedad va plegada: importa mas que esta limpio y que retenido. */}
          <Section title={t.money.ageing.title} summary={`${t.money.overdue}: ${formatMoney(totals.vencido_cent)}`}>
            <Ageing cartera={c} onOpen={(key) => openList(`tramo:${key}`)} />
          </Section>
        </>
      )}

      <Parties side={side} cartera={c} />

      <div>
        <Button variant='link' size='sm' className='h-auto px-0' onClick={() => nav.go(list)}>
          {side === 'saliente' ? t.money.allInvoicesOut : t.money.allInvoicesIn}
          <ArrowRight className='ml-1 h-3.5 w-3.5' aria-hidden='true' />
        </Button>
      </div>
    </div>
  );
}

/** Una de las cuatro cifras: un boton que abre la lista que la explica. */
function Figure({
  label,
  cents,
  caption,
  onOpen,
  late = false,
  big = false,
}: {
  label: string;
  cents: number;
  caption?: string;
  onOpen: () => void;
  late?: boolean;
  big?: boolean;
}) {
  const { t } = useT();
  return (
    <button
      type='button'
      onClick={onOpen}
      aria-label={`${fmt(t.money.showList, { what: label })} (${formatMoney(cents)})`}
      data-testid='money-figure'
      data-label={label}
      className='flex flex-col items-start gap-1 bg-card px-4 py-3 text-left hover:bg-row-hover'
    >
      <span className='text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>{label}</span>
      <Money cents={cents} className={cn('font-semibold tracking-[-0.01em]', big ? 'text-[24px]' : 'text-[19px]', late && 'text-late-foreground')} />
      {caption && <span className='text-xs text-muted-foreground'>{caption}</span>}
    </button>
  );
}

/** La antiguedad: una barra con los tramos y cada tramo con cuantas facturas y cuanto; un
 *  tramo abre la lista con esas facturas (la misma suma). */
function Ageing({ cartera: c, onOpen }: { cartera: Cartera; onOpen: (key: BucketKey) => void }) {
  const { t } = useT();
  const shares = bucketShares(c.tramos);
  const buckets = c.tramos.filter((b) => b.clave !== 'sin_fecha' || b.facturas > 0);
  return (
    <div className='flex flex-col gap-3'>
      {shares.length > 0 && (
        <div role='img' aria-label={t.money.ageing.bar} className='flex h-2.5 w-full overflow-hidden rounded-full bg-muted'>
          {shares.map((s) => (
            <span key={s.clave} className={cn('h-full', BUCKET_TONE[s.clave])} style={{ flexGrow: s.share }} />
          ))}
        </div>
      )}
      <ul
        className={cn(
          'grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-3',
          buckets.length === 6 ? 'xl:grid-cols-6' : 'xl:grid-cols-5'
        )}
      >
        {buckets.map((b) => {
          const label = t.money.ageing.buckets[b.clave];
          return (
            <li key={b.clave} className='bg-card'>
              <button
                type='button'
                disabled={b.facturas === 0}
                onClick={() => onOpen(b.clave)}
                aria-label={`${fmt(t.money.ageing.show, { bucket: label })} (${formatMoney(b.importe_cent)})`}
                data-testid='ageing-bucket'
                data-bucket={b.clave}
                className='flex h-full w-full flex-col items-start gap-0.5 px-3 py-2.5 text-left enabled:hover:bg-row-hover disabled:cursor-default'
              >
                <span className='flex items-center gap-1.5 text-[12.5px] text-soft-foreground'>
                  <span className={cn('h-2 w-2 shrink-0 rounded-full', BUCKET_TONE[b.clave])} aria-hidden='true' />
                  {label}
                </span>
                <Money cents={b.importe_cent} className={cn('text-[15px] font-semibold', b.facturas === 0 && 'text-muted-foreground')} />
                <span className='text-xs text-muted-foreground'>
                  {fmt(b.facturas === 1 ? t.money.ageing.countOne : t.money.ageing.count, { n: b.facturas })}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// Los tramos, de tranquilo a urgente (con su texto siempre al lado: el color no es el dato).
const BUCKET_TONE: Record<BucketKey, string> = {
  al_corriente: 'bg-primary/45',
  '1_30': 'bg-amber-400/70',
  '31_60': 'bg-orange-500/75',
  '61_90': 'bg-red-500/75',
  mas_de_90: 'bg-red-700/85',
  sin_fecha: 'bg-muted-foreground/40',
};

/** Lo que espera a una persona, solo si hay algo: pagos propuestos, lineas sin casar, abonos
 *  sin enlazar, facturas sin importe en euros y pagos que no cuadran. */
function Notices({ side, cartera: c }: { side: Side; cartera: Cartera }) {
  const { t, lang } = useT();
  const nav = useNav();
  const bank = BANK_OF[side];
  const n = t.money.notices;
  const items: { key: string; text: ReactNode; onOpen?: () => void; label?: string }[] = [];
  if (c.por_confirmar.pagos > 0) {
    const many = side === 'saliente' ? n.confirmIn : n.confirmOut;
    const one = side === 'saliente' ? n.confirmInOne : n.confirmOutOne;
    items.push({ key: 'confirm', text: fmt(c.por_confirmar.pagos === 1 ? one : many, { n: c.por_confirmar.pagos }), onOpen: () => nav.go(bank) });
  }
  if (c.sin_casar.movimientos > 0) {
    const many = side === 'saliente' ? n.unmatchedIn : n.unmatchedOut;
    const one = side === 'saliente' ? n.unmatchedInOne : n.unmatchedOutOne;
    items.push({ key: 'unmatched', text: fmt(c.sin_casar.movimientos === 1 ? one : many, { n: c.sin_casar.movimientos }), onOpen: () => nav.go(bank) });
  }
  const credits = c.abonos_sin_enlazar;
  if (credits.facturas > 0) {
    items.push({
      key: 'credits',
      text: (
        <span className='flex flex-col gap-1'>
          <span>{fmt(credits.facturas === 1 ? n.creditNotesOne : n.creditNotes, { n: credits.facturas })}</span>
          <span className='flex flex-wrap gap-x-3 gap-y-1'>
            {credits.lista.map((cn_) => (
              <Button
                key={cn_.id}
                variant='link'
                size='sm'
                className='h-auto flex-wrap justify-start whitespace-normal px-0 py-0 text-left text-xs'
                onClick={() => nav.open(recordRoute('invoice', cn_.id))}
              >
                <span className='font-mono' data-proper-name=''>
                  {cn_.numero ?? cn_.id}
                </span>
                <span className='ml-1 text-muted-foreground' data-proper-name=''>
                  {cn_.parte ?? cn_.contraparte ?? ''}
                </span>
                <Money cents={cn_.pendiente_cent} className='ml-1' />
              </Button>
            ))}
          </span>
        </span>
      ),
    });
  }
  if (c.sin_importe > 0) items.push({ key: 'x1', text: fmt(c.sin_importe === 1 ? n.noAmountOne : n.noAmount, { n: c.sin_importe }) });
  for (const alert of c.avisos_pago ?? []) {
    items.push({
      key: `k-${alert.regla}`,
      text: (
        <span className='flex flex-col gap-1'>
          <span>
            {ruleText(lang, alert.regla)?.title ?? alert.regla}
            <span className='ml-2 font-mono text-[11px] text-muted-foreground'>{alert.regla}</span>
          </span>
          <span className='flex flex-wrap gap-x-3 gap-y-1'>
            {alert.facturas.map((f) => (
              <Button key={f.id} variant='link' size='sm' className='h-auto flex-wrap justify-start whitespace-normal px-0 py-0 text-left text-xs' onClick={() => nav.open(recordRoute('invoice', f.id))}>
                <span className='font-mono' data-proper-name=''>
                  {f.numero ?? f.id}
                </span>
                <span className='ml-1 text-muted-foreground' data-proper-name=''>
                  {f.parte ?? ''}
                </span>
              </Button>
            ))}
          </span>
        </span>
      ),
    });
  }
  if (items.length === 0) return null;
  return (
    <section aria-labelledby='money-notices'>
      <h2 id='money-notices' className='mb-2 text-[15px] font-semibold'>
        {n.title}
      </h2>
      <ul className='divide-y divide-divider overflow-hidden rounded-md border border-border bg-card'>
        {items.map((item) => (
          <li key={item.key} className='text-[13.5px]'>
            {item.onOpen ? (
              <button type='button' onClick={item.onOpen} className='flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-row-hover'>
                <span>{item.text}</span>
                <ArrowRight className='h-4 w-4 shrink-0 text-muted-foreground' aria-hidden='true' />
              </button>
            ) : (
              <div className='px-4 py-2.5'>{item.text}</div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Al pagar: lo que toca hasta el domingo, lo limpio y lo retenido con su porque, y lo
 *  retenido que vence despues. Nunca "aprobado": "sin objeciones del sistema". */
function ThisWeek({ cartera: c }: { cartera: Cartera }) {
  const { t } = useT();
  const nav = useNav();
  const week = c.esta_semana;
  if (!week) return null;
  const clean = week.facturas.filter((f) => !f.retenida);
  const held = week.facturas.filter((f) => f.retenida);
  const later = (c.retenido.lista ?? []).filter((f) => !week.facturas.some((w) => w.id === f.id));
  const iban = [...held, ...later].some((f) => f.razones.some((r) => r.regla.startsWith('F')));
  // "1 van 2" en las dos facturas con el mismo numero y la misma relacion, como en las listas.
  const twins = twinMarks([...week.facturas, ...later].map((f) => ({ id: f.id, numero: f.numero, contraparte: f.parte })));
  return (
    <section aria-labelledby='money-week'>
      <h2 id='money-week' className='text-[15px] font-semibold'>
        {fmt(t.money.week.title, { date: formatDateProse(week.hasta, t) })}
      </h2>
      <p className='mb-3 text-[13px] text-muted-foreground'>{t.money.week.intro}</p>
      {week.facturas.length === 0 ? (
        <p className='rounded-md border border-border bg-card px-4 py-3 text-[13.5px]'>{t.money.week.nothing}</p>
      ) : (
        <div className='grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-2'>
          <WeekColumn title={t.money.week.clean} sum={week.sin_retener} rows={clean} empty={null} twins={twins} />
          <WeekColumn title={t.money.week.held} sum={week.retenido} rows={held} empty={t.money.week.nothingHeld} twins={twins} held />
        </div>
      )}
      {later.length > 0 && (
        <div className='mt-3'>
          <h3 className='mb-1 text-[13px] font-semibold text-soft-foreground'>{t.money.week.heldLater}</h3>
          <ul className='divide-y divide-divider overflow-hidden rounded-md border border-border bg-card'>
            {later.map((f) => (
              <WeekRow key={f.id} row={f} twin={twins.get(f.id)} held />
            ))}
          </ul>
        </div>
      )}
      {iban && (
        <Button variant='link' size='sm' className='mt-2 h-auto px-0' onClick={() => nav.go('iban-checks')}>
          {t.money.week.ibanChecks}
          <ArrowRight className='ml-1 h-3.5 w-3.5' aria-hidden='true' />
        </Button>
      )}
    </section>
  );
}

function WeekColumn({
  title,
  sum,
  rows,
  empty,
  twins,
  held = false,
}: {
  title: string;
  sum: { facturas: number; importe_cent: number };
  rows: CarteraInvoice[];
  empty: string | null;
  twins: ReadonlyMap<number, TwinMark>;
  held?: boolean;
}) {
  const { t } = useT();
  return (
    <div className='flex flex-col bg-card' data-testid={held ? 'week-held' : 'week-clean'}>
      <div className='flex items-baseline justify-between gap-3 px-4 pb-2 pt-3'>
        <h3 className='text-[13px] font-semibold'>{title}</h3>
        <span className='text-right text-[13px]'>
          <Money cents={sum.importe_cent} className='font-semibold' />
          <span className='ml-2 text-xs text-muted-foreground'>
            {fmt(sum.facturas === 1 ? t.money.ageing.countOne : t.money.ageing.count, { n: sum.facturas })}
          </span>
        </span>
      </div>
      {rows.length === 0 && empty ? (
        <p className='flex items-center gap-2 px-4 pb-3 text-[13px] text-muted-foreground'>
          <CircleCheck className='h-4 w-4 text-ok-foreground' aria-hidden='true' />
          {empty}
        </p>
      ) : (
        <ul className='divide-y divide-divider border-t border-divider'>
          {rows.map((f) => (
            <WeekRow key={f.id} row={f} twin={twins.get(f.id)} held={held} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Una factura de la semana: numero, empresa, lo que queda, cuando vence y, si esta
 *  retenida, por que (el hallazgo mas urgente, por su nombre). */
function WeekRow({ row: f, held, twin }: { row: CarteraInvoice; held: boolean; twin?: TwinMark | undefined }) {
  const { t, lang } = useT();
  const nav = useNav();
  const reason = f.razones[0];
  const mark = twin ? fmt(t.common.twin, { n: twin.n, of: twin.of }) : null;
  return (
    <li>
      <button
        type='button'
        onClick={() => nav.open(recordRoute('invoice', f.id))}
        aria-label={fmt(t.common.openRecord, { what: `${t.records.invoice.label} ${f.numero ?? f.id}${mark ? ` (${mark})` : ''}` })}
        className='grid w-full grid-cols-[1fr_auto] items-start gap-x-4 gap-y-0.5 px-4 py-2.5 text-left hover:bg-row-hover'
      >
        <span className='flex min-w-0 flex-col'>
          <span className='font-mono text-[12.5px] font-medium text-primary'>
            <span data-proper-name=''>{f.numero ?? '—'}</span>
            {mark && <span className='ml-1.5 font-sans text-xs font-normal text-muted-foreground'>{mark}</span>}
          </span>
          <span className='truncate text-[13px] text-soft-foreground' data-proper-name=''>
            {f.parte ?? '—'}
          </span>
          {held && reason && (
            <span className='text-[12.5px] text-late-foreground'>
              {ruleText(lang, reason.regla)?.title ?? reason.regla}
              <span className='ml-1.5 font-mono text-[11px] text-muted-foreground'>{reason.regla}</span>
            </span>
          )}
        </span>
        <span className='flex flex-col items-end'>
          <Money cents={f.pendiente_cent} className='text-[13.5px]' />
          <DueText due={f.vencimiento} today={null} days={f.dias} />
        </span>
      </button>
    </li>
  );
}

/** Cuanto falta o cuanto va tarde: de los dias del motor (`days`: retraso, negativo lo que
 *  falta) o de la fecha y el hoy del motor. */
function dueInfo(due: string | null, today: string | null, days?: number | null): DueState | null {
  if (!due) return { kind: 'none' };
  if (days !== undefined && days !== null) {
    if (days > 0) return { kind: 'late', days };
    return days === 0 ? { kind: 'today' } : { kind: 'ahead', days: -days };
  }
  return today ? dueState(due, today) : null;
}

export function dueLabel(t: Messages, due: string | null, today: string | null, days?: number | null): string | null {
  const d = t.money.due;
  const s = dueInfo(due, today, days);
  if (!s) return null;
  if (s.kind === 'late') return fmt(s.days === 1 ? d.lateOne : d.late, { n: s.days });
  if (s.kind === 'today') return d.today;
  if (s.kind === 'ahead') return fmt(s.days === 1 ? d.aheadOne : d.ahead, { n: s.days });
  return d.none;
}

/** "12 dagen te laat" (en el color de lo que va mal), "vervalt vandaag" o "over 4 dagen". */
export function DueText({ due, today, days }: { due: string | null; today: string | null; days?: number | null }) {
  const { t } = useT();
  const text = dueLabel(t, due, today, days);
  if (!text) return null;
  const late = dueInfo(due, today, days)?.kind === 'late';
  return <span className={cn('text-xs', late ? 'font-medium text-late-foreground' : 'text-muted-foreground')}>{text}</span>;
}

/** Cada empresa con algo pendiente, lo vencido primero: abre su ficha (su fila) o su carpeta
 *  en Documentos (el boton de la derecha). */
function Parties({ side, cartera: c }: { side: Side; cartera: Cartera }) {
  const { t, lang } = useT();
  const nav = useNav();
  const p = t.money.parties;
  const kind = side === 'saliente' ? 'client' : 'provider';
  const rows = partiesByOverdue(c.partes);
  const title = side === 'saliente' ? p.titleIn : p.titleOut;
  const paysText = (r: CarteraParty) => {
    const pay = r.plazo_de_pago;
    if (!pay || pay.pagadas === 0 || pay.media_dias === null) return null;
    if (side === 'saliente') return fmt(pay.tarde > 0 ? p.paysAfterLate : p.paysAfter, { n: pay.media_dias, late: pay.tarde });
    return fmt(pay.tarde > 0 ? p.wePayAfterLate : p.wePayAfter, { n: pay.media_dias, late: pay.tarde });
  };
  const columns: Columns<CarteraParty> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => (r.nivel ? <StatusPill group='prioridad' state={r.nivel} /> : null) },
    {
      key: 'party',
      header: side === 'saliente' ? t.records.client.label : t.records.provider.label,
      primary: true,
      cell: (r) => {
        const reason = r.razones[0];
        return (
          <span className='flex flex-col items-start'>
            <span data-proper-name=''>{r.nombre ?? (side === 'saliente' ? p.noPartyIn : p.noPartyOut)}</span>
            <span className='text-xs font-normal text-muted-foreground'>
              {[fmt(r.facturas === 1 ? p.openInvoicesOne : p.openInvoices, { n: r.facturas }), paysText(r)].filter(Boolean).join(' · ')}
            </span>
            {side === 'entrante' && r.retenido_cent > 0 && (
              <span className='text-xs font-normal text-late-foreground'>
                {p.held}: {formatMoney(r.retenido_cent)}
                {reason ? ` · ${ruleText(lang, reason.regla)?.title ?? reason.regla}` : ''}
              </span>
            )}
            {side === 'saliente' && reason && (
              <span className='text-xs font-normal text-soft-foreground'>{ruleText(lang, reason.regla)?.title ?? reason.regla}</span>
            )}
          </span>
        );
      },
    },
    { key: 'outstanding', header: t.columns.outstanding, align: 'right', width: '8rem', cell: (r) => <Money cents={r.pendiente_cent} /> },
    {
      key: 'overdue',
      header: t.money.overdue,
      align: 'right',
      width: '8rem',
      cell: (r) => (r.vencido_cent > 0 ? <Money cents={r.vencido_cent} className='text-late-foreground' /> : <Money cents={0} className='text-muted-foreground' />),
    },
    {
      key: 'oldest',
      header: p.oldest,
      width: '9rem',
      cell: (r) =>
        r.mas_antigua_dias ? (
          <span className='text-[13px] font-medium text-late-foreground'>
            {fmt(r.mas_antigua_dias === 1 ? t.money.due.lateOne : t.money.due.late, { n: r.mas_antigua_dias })}
          </span>
        ) : (
          <span className='text-muted-foreground'>—</span>
        ),
    },
    {
      key: 'folder',
      header: <span className='sr-only'>{p.folder}</span>,
      width: '6rem',
      cell: (r) =>
        r.id !== null ? (
          <Button
            variant='ghost'
            size='sm'
            className='h-7 px-2'
            aria-label={fmt(p.folderLabel, { name: r.nombre ?? '' })}
            onClick={(e) => {
              e.stopPropagation();
              nav.openFrom('documents', recordRoute(kind === 'client' ? 'client-documents' : 'provider-documents', r.id!));
            }}
          >
            <FolderOpen className='mr-1 h-3.5 w-3.5' aria-hidden='true' />
            {p.folder}
          </Button>
        ) : null,
    },
  ];
  return (
    <section aria-labelledby='money-parties'>
      <div className='mb-2 flex flex-wrap items-baseline gap-x-3'>
        <h2 id='money-parties' className='text-[15px] font-semibold'>
          {title}
        </h2>
        <span className='text-[13px] text-muted-foreground'>{side === 'saliente' ? p.introIn : p.introOut}</span>
      </div>
      {rows.length === 0 ? (
        <EmptyState icon={CircleCheck} title={p.none} />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id ?? 0}
          caption={title}
          onOpen={(r) => r.id !== null && nav.open(recordRoute(kind, r.id))}
          openLabel={(r) => fmt(t.common.openRecord, { what: r.nombre ?? '' })}
        />
      )}
    </section>
  );
}
