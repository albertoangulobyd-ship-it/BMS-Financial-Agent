// Inicio (paso 16): la cara de Aurora sobre el motor de verdad. Arriba, el saludo con el nombre
// de quien entro (/api/v2/yo), el orbe y la rueda con las seis entradas, y la caja que busca
// (/api/v2/buscar y las listas: abre pantallas y fichas; todavia no contesta preguntas, y lo
// dice). Debajo, cuatro tarjetas tranquilas del panel (Atencion, Por cobrar, Por pagar, el IVA
// del trimestre), "Lo primero" solo cuando algo esta bloqueado o es urgente (cinco filas como
// mucho) y la entrada a lo que vive en Inicio: la cola de trabajo, las excepciones y el flujo
// de caja. Se vuelve a leer cada minuto mientras la ventana esta a la vista, y despues de cada
// orden, sin saltar a "Laden…".
import { ArrowRight, CircleCheck, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { WorkspaceComposer } from '@/aurora/composer';
import { AuroraOrb } from '@/aurora/orb/aurora-orb';
import { Wheel, type WheelEntry } from '@/aurora/wheel';
import { HelpTip } from '@/components/help-tip';
import { useDocumentTitle } from '@/components/page-header';
import { PingScope, StatusPill } from '@/components/status-pill';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { SummaryCard, SummaryGrid } from '@/components/summary-card';
import { Button } from '@/components/ui/button';
import { Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { fmt, useT } from '@/i18n';
import { paths, type InvoiceRow, type Panel } from '@/lib/api';
import { formatDate, formatDateProse, quarterLabel } from '@/lib/format';
import { RESULT_KINDS, type QuickResult } from '@/lib/quick-search';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { distinctByNumber } from '@/lib/twins';
import { rememberView } from '@/lib/view-memory';
import { needsPerson, whyOf } from '@/lib/why';
import { cn } from '@/lib/utils';
import { useNav } from '@/shell/navigation';
import { badgeFor, countsFromPanel } from '@/shell/use-badges';
import { useQuickSearch } from '@/shell/use-quick-search';
import { recordRoute, visibleSections, visibleViews, type SectionId, type ViewId } from './registry';
import { useLoad } from './use-load';
import { deadlineState, overdueQuarters } from './vat';

/** "Lo primero": como mucho cinco cosas distintas. */
export const FIRST = 5;
/** Cada cuanto se vuelve a leer el inicio mientras se ve. */
export const REFRESH_MS = 60_000;

/** Lo que no puede esperar: bloqueado o urgente. */
export function urgentFirst(invoices: readonly InvoiceRow[]): InvoiceRow[] {
  return invoices.filter((f) => needsPerson(f) && (f.nivel === 'bloqueada' || f.nivel === 'urgente'));
}

/** El nombre de pila del saludo ("Ana Demo" -> "Ana"); si no parece uno, el nombre entero. */
export function firstName(name: string): string {
  const first = name.trim().split(/\s+/)[0] ?? '';
  return first.length >= 2 && !first.endsWith('.') ? first : name.trim();
}

function clock(date: Date): string {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function useNarrow(): boolean {
  const query = '(max-width: 639px)';
  const [narrow, setNarrow] = useState(() => typeof window.matchMedia === 'function' && window.matchMedia(query).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const m = window.matchMedia(query);
    const on = () => setNarrow(m.matches);
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, []);
  return narrow;
}

/** Vuelve a leer cada minuto mientras la ventana se ve; al volver a ella, si ya toca. */
function useMinuteRefresh(reload: () => void, loadedAt: number | null): void {
  const last = useRef(loadedAt);
  last.current = loadedAt;
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState !== 'visible') return;
      if (last.current !== null && Date.now() - last.current >= REFRESH_MS - 500) reload();
    };
    const timer = window.setInterval(tick, REFRESH_MS);
    document.addEventListener('visibilitychange', tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [reload]);
}

export function HomeScreen() {
  const { t } = useT();
  const { session } = useSession();
  const can = useCan();
  const nav = useNav();
  const { version } = useRefresh();
  const narrow = useNarrow();
  const [loadedAt, setLoadedAt] = useState<number | null>(null);
  const [state, reload] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ panel: Panel }>(paths.panel).then((r) => r.panel),
        session!.api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas),
      ]).then((data) => {
        setLoadedAt(Date.now());
        return data;
      }),
    [session, version]
  );
  useMinuteRefresh(reload, loadedAt);
  useDocumentTitle(t.areas.home.label);

  const sections = visibleSections(can);
  const [active, setActive] = useState(0);
  const [asked, setAsked] = useState('');
  const [text, setText] = useState('');
  const search = useQuickSearch(asked);
  const cards = useRef<HTMLElement>(null);

  const entries: WheelEntry[] = sections.map((id) => ({ id, label: t.areas[id].label, current: id === 'home' }));
  const openSection = (index: number) => {
    const id = sections[index]!;
    if (id === 'home') {
      // Ya se esta en Inicio: a lo que hay debajo de la rueda.
      cards.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
      cards.current?.focus({ preventScroll: true });
      return;
    }
    const first = visibleViews(id, can)[0];
    if (first) nav.go(first);
  };

  const onAsk = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setAsked(text.trim());
  };

  const name = session ? firstName(session.me.nombre) : '';
  const greeting = fmt(t.home.greeting, { name: '\u0000' }).split('\u0000');

  return (
    <div className='aurora-root'>
      <section className='mx-auto flex w-full max-w-[760px] flex-col items-center px-5 pb-6 pt-8 sm:pt-12'>
        <div className='welcome-line text-center'>
          <h1>
            {greeting[0]}
            <strong data-proper-name=''>{name}</strong>
            {greeting[1]}
          </h1>
          <p>{t.home.intro}</p>
        </div>

        <div className='mt-6 flex w-full items-center justify-center gap-3 sm:mt-8 sm:gap-8'>
          <AuroraOrb
            label={t.aurora.orb}
            size={narrow ? 104 : 190}
            active={state.status === 'loading' || (search.loading && asked !== '')}
            flowPhase={active * 1.4}
            className='shrink-0'
          />
          <Wheel
            entries={entries}
            active={active}
            onActive={setActive}
            onOpen={openSection}
            label={t.shell.mainNavigation}
            description={t.shell.wheel}
            row={narrow ? 40 : 46}
            className={cn(narrow ? 'w-[13.5rem] [--wheel-font:18px]' : 'w-[19rem]')}
          />
        </div>

        <div className='mt-6 w-full max-w-[600px] sm:mt-8'>
          <WorkspaceComposer
            mode='search'
            value={text}
            onValueChange={(v) => {
              setText(v);
              if (!v.trim()) setAsked('');
            }}
            onSubmit={onAsk}
            disabled={!text.trim()}
            placeholder={t.ask.placeholder}
            label={t.ask.label}
            submitLabel={t.ask.submit}
          />
          <p className='mt-3 text-center text-[12.5px] text-muted-foreground'>{t.ask.notYet}</p>
          {asked && <AskResults query={asked} results={search.results} loading={search.loading} more={search.moreInvoices} error={search.error} onClose={() => {
            setAsked('');
            setText('');
          }} />}
        </div>
      </section>

      <section
        ref={cards}
        tabIndex={-1}
        aria-label={t.home.cardsLabel}
        className='mx-auto w-full max-w-[1240px] scroll-mt-20 px-5 pb-12 outline-none xl:px-8'
      >
        {state.status === 'loading' && <Loading />}
        {state.status === 'error' && <ErrorState error={state.error} onRetry={reload} />}
        {/* Un resumen: nada late aqui (lo que late esta en la Werklijst y en la ficha). */}
        {state.status === 'ready' && (
          <PingScope scope='none'>
            <HomeContent panel={state.data[0]} invoices={state.data[1]} loadedAt={loadedAt} sections={sections} />
          </PingScope>
        )}
      </section>
    </div>
  );
}

function AskResults({
  query,
  results,
  loading,
  more,
  error,
  onClose,
}: {
  query: string;
  results: QuickResult[];
  loading: boolean;
  more: number;
  error: unknown;
  onClose: () => void;
}) {
  const { t } = useT();
  const nav = useNav();
  const groups = RESULT_KINDS.map((kind) => ({ kind, items: results.filter((r) => r.kind === kind) })).filter((g) => g.items.length);
  const open = (r: QuickResult) => {
    if (r.route.screen === r.view && r.route.id === undefined) nav.go(r.view);
    else nav.openFrom(r.view, r.route);
  };
  return (
    <section aria-labelledby='ask-results' className='mt-5 rounded-xl border border-border bg-card px-4 py-4 text-left'>
      <div className='flex items-start justify-between gap-3'>
        <h2 id='ask-results' className='text-[14px] font-semibold'>
          {fmt(t.ask.resultsFor, { q: '\u0000' }).split('\u0000')[0]}
          <span data-proper-name=''>{query}</span>
          {fmt(t.ask.resultsFor, { q: '\u0000' }).split('\u0000')[1]}
        </h2>
        <Button variant='ghost' size='icon' className='-mr-2 -mt-1 h-7 w-7' aria-label={t.ask.clear} onClick={onClose}>
          <X className='h-4 w-4' aria-hidden='true' />
        </Button>
      </div>
      <div aria-live='polite'>
        {groups.length === 0 && !loading && (
          <div className='py-3'>
            <p className='font-medium'>
              {fmt(t.ask.nothing, { q: '\u0000' }).split('\u0000')[0]}
              <span data-proper-name=''>{query}</span>
              {fmt(t.ask.nothing, { q: '\u0000' }).split('\u0000')[1]}
            </p>
            <p className='mt-1 text-[13px] text-muted-foreground'>{t.ask.nothingText}</p>
          </div>
        )}
        {groups.map((g) => (
          <div key={g.kind} className='mt-3'>
            <h3 className='mb-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground'>{t.ask.groups[g.kind]}</h3>
            <ul className='flex flex-col'>
              {g.items.map((r) => (
                <li key={r.key}>
                  <button
                    type='button'
                    onClick={() => open(r)}
                    className='flex w-full items-baseline justify-between gap-4 rounded-md px-2 py-1.5 text-left hover:bg-row-hover'
                  >
                    <span
                      className={cn('text-[14px] text-foreground', (r.kind === 'invoices' || r.kind === 'pos') && 'font-mono text-[13px]')}
                      data-proper-name={r.kind === 'screens' ? undefined : ''}
                    >
                      {r.label}
                    </span>
                    {r.detail && (
                      <span className='truncate text-xs text-muted-foreground' data-proper-name={r.kind === 'screens' ? undefined : ''}>
                        {r.detail}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {loading && <Loading className='py-3' label={t.ask.searching} />}
        {more > 0 && <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.ask.moreInvoices, { n: more })}</p>}
        {error !== null && !loading && <p className='mt-2 text-xs text-late-foreground'>{t.errors.unexpected}</p>}
      </div>
    </section>
  );
}

function HomeContent({
  panel,
  invoices,
  loadedAt,
  sections,
}: {
  panel: Panel;
  invoices: InvoiceRow[];
  loadedAt: number | null;
  sections: SectionId[];
}) {
  const { t } = useT();
  const nav = useNav();
  const a = panel.atencion;
  const vat = panel.btw;
  const queue = useMemo(() => invoices.filter(needsPerson), [invoices]);
  const urgent = useMemo(() => distinctByNumber(urgentFirst(invoices)).slice(0, FIRST), [invoices]);
  const deadline = vat.proximo_plazo;
  const deadlineStatus = deadline ? deadlineState(deadline) : null;
  const overdue = overdueQuarters(vat);
  const counts = countsFromPanel(panel);

  const link = (view: ViewId, label: string) => (
    <Button variant='link' size='sm' className='h-auto px-0 py-0 text-xs' onClick={() => nav.go(view)}>
      {label}
      <ArrowRight className='ml-1 h-3.5 w-3.5' aria-hidden='true' />
    </Button>
  );
  // "Vencido" abre la lista de su sentido con el filtro de vencidas ya puesto.
  const overdueList = (view: 'invoices-in' | 'invoices-out') => () => {
    rememberView(view, `${view}-filter`, 'vencida');
    nav.go(view);
  };
  const showIn = sections.includes('payables');
  const showOut = sections.includes('receivables');
  // A cuantas empresas les queda algo (de las facturas que ya lee el inicio): lleva a su lista.
  const owing = (direction: InvoiceRow['sentido'], key: 'cliente_id' | 'proveedor_id') =>
    new Set(
      invoices
        .filter((f) => f.sentido === direction && f.cuenta && (f.estado_pago === 'pendiente' || f.estado_pago === 'vencida'))
        .map((f) => f[key])
        .filter((id) => id !== null)
    ).size;
  const clientsOwing = owing('saliente', 'cliente_id');
  const providersOwed = owing('entrante', 'proveedor_id');

  return (
    <div className='flex flex-col gap-8'>
      {!panel.al_dia && (
        <div role='status' className='flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]'>
          <StatusPill group='fuente' state='caducada' />
          <span>{fmt(t.overview.stale, { date: formatDate(panel.estado_del) })}</span>
        </div>
      )}
      <div className='flex flex-col gap-2'>
        <SummaryGrid>
          <SummaryCard
            title={t.overview.attention.title}
            value={fmt(queue.length === 1 ? t.overview.attention.valueOne : t.overview.attention.value, { n: queue.length })}
            caption={t.overview.attention.caption}
            rows={[
              {
                label: t.overview.attention.blocked,
                value: a.bloqueadas,
                status: a.bloqueadas > 0 ? { group: 'prioridad', state: 'bloqueada' } : undefined,
              },
              { label: t.overview.attention.urgent, value: a.urgentes },
              { label: t.overview.attention.exceptions, value: a.excepciones.abiertas },
            ]}
            action={link('work-queue', t.overview.open.workQueue)}
          />
          <SummaryCard
            title={t.overview.moneyIn.title}
            value={<Money cents={panel.dinero_entra.pendiente_cent} />}
            caption={fmt(t.overview.money.caption, { n: panel.dinero_entra.facturas })}
            rows={[
              {
                label: t.overview.money.overdue,
                value: <Money cents={panel.dinero_entra.vencido_cent} />,
                status: panel.dinero_entra.vencido_cent > 0 ? { group: 'pago', state: 'vencida' } : undefined,
                onSelect: showOut ? overdueList('invoices-out') : undefined,
                selectLabel: t.home.overdueOut,
              },
              { label: t.overview.money.next30, value: <Money cents={panel.dinero_entra.proximos_30_cent} /> },
              {
                label: t.home.clientsOpen,
                value: clientsOwing,
                onSelect: showOut ? () => nav.go('clients') : undefined,
                selectLabel: t.home.showClients,
              },
            ]}
            action={showOut ? link('invoices-out', t.overview.open.invoicesOut) : undefined}
          />
          <SummaryCard
            title={t.overview.moneyOut.title}
            value={<Money cents={panel.dinero_sale.pendiente_cent} />}
            caption={fmt(t.overview.money.caption, { n: panel.dinero_sale.facturas })}
            rows={[
              {
                label: t.overview.money.overdue,
                value: <Money cents={panel.dinero_sale.vencido_cent} />,
                status: panel.dinero_sale.vencido_cent > 0 ? { group: 'pago', state: 'vencida' } : undefined,
                onSelect: showIn ? overdueList('invoices-in') : undefined,
                selectLabel: t.home.overdueIn,
              },
              { label: t.overview.money.thisWeek, value: <Money cents={panel.dinero_sale.semana_cent} /> },
              {
                label: t.home.providersOpen,
                value: providersOwed,
                onSelect: showIn ? () => nav.go('providers') : undefined,
                selectLabel: t.home.showProviders,
              },
            ]}
            action={showIn ? link('invoices-in', t.overview.open.invoicesIn) : undefined}
          />
          <SummaryCard
            title={t.overview.vat.title}
            help={<HelpTip term='btw' />}
            value={<Money cents={Math.abs(vat.saldo_cent)} />}
            caption={fmt(t.overview.vat.caption, {
              quarter: quarterLabel(vat.trimestre),
              what: vat.saldo_cent < 0 ? t.overview.vat.refund : vat.saldo_cent > 0 ? t.overview.vat.toPay : t.overview.vat.zero,
            })}
            rows={[
              ...(overdue.length > 0
                ? [
                    {
                      label: t.overview.vat.overdue,
                      value: overdue.map(quarterLabel).join(', '),
                      status: { group: 'btw', state: 'plazo_vencido' } as const,
                    },
                  ]
                : []),
              ...(deadline
                ? [
                    {
                      label: fmt(t.overview.vat.deadline, { quarter: quarterLabel(deadline.trimestre) }),
                      value: formatDateProse(deadline.limite_presentacion, t),
                    },
                    deadlineStatus === 'plazo_cerca'
                      ? {
                          label: t.overview.vat.left,
                          value: '',
                          status: { group: 'btw', state: 'plazo_cerca', values: { n: deadline.dias_para_limite ?? 0 } } as const,
                        }
                      : {
                          label: t.overview.vat.left,
                          value: fmt(deadline.dias_para_limite === 1 ? t.overview.vat.dayLeft : t.overview.vat.daysLeft, {
                            n: deadline.dias_para_limite ?? 0,
                          }),
                        },
                  ]
                : []),
            ]}
            action={link('vat', t.overview.open.vat)}
          />
        </SummaryGrid>
        {loadedAt !== null && (
          <p className='text-right text-xs text-muted-foreground'>{fmt(t.home.updated, { time: clock(new Date(loadedAt)) })}</p>
        )}
      </div>

      {urgent.length > 0 && (
        <section aria-labelledby='next-up'>
          <div className='mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1'>
            <div className='flex flex-wrap items-baseline gap-x-3'>
              <h2 id='next-up' className='text-[15px] font-semibold'>
                {t.overview.nextUp.title}
              </h2>
              <span className='text-[13px] text-muted-foreground'>{t.home.firstIntro}</span>
            </div>
            {queue.length > urgent.length && link('work-queue', fmt(t.overview.nextUp.all, { n: queue.length }))}
          </div>
          <ol className='divide-y divide-divider overflow-hidden rounded-md border border-border bg-card'>
            {/* Cosas distintas: las facturas con el mismo numero y relacion van en una fila. */}
            {urgent.map(({ row, count }) => (
              <FirstRow key={row.id} row={row} count={count} onOpen={() => nav.open(recordRoute('invoice', row.id))} />
            ))}
          </ol>
        </section>
      )}
      {urgent.length === 0 && queue.length === 0 && (
        <EmptyState icon={CircleCheck} title={t.empty.nothingNeedsAttention} text={t.overview.nextUp.empty} />
      )}

      <nav aria-label={t.home.alsoHere}>
        <p className='mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground'>{t.home.alsoHere}</p>
        <ul className='grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-3'>
          {(['work-queue', 'exceptions', 'cash-flow'] as const).map((view) => {
            const badge = badgeFor(view, counts, t.badges);
            const note =
              view === 'work-queue'
                ? fmt(queue.length === 1 ? t.home.waitingOne : t.home.waiting, { n: queue.length })
                : view === 'exceptions'
                  ? fmt(t.home.openCount, { n: a.excepciones.abiertas })
                  : t.home.comingWeeks;
            return (
              <li key={view} className='bg-card'>
                <button
                  type='button'
                  onClick={() => nav.go(view)}
                  className='flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-row-hover'
                >
                  <span className='flex flex-col'>
                    <span className='font-medium'>{t.nav[view].label}</span>
                    <span className='text-xs text-muted-foreground'>{note}</span>
                  </span>
                  <span className='flex items-center gap-2'>
                    {badge?.tone === 'blocked' && (
                      <span className='num rounded-full bg-pill-blocked px-1.5 py-px text-[11px] font-semibold leading-4 text-pill-blocked-foreground'>
                        {badge.count} {badge.label}
                      </span>
                    )}
                    <ArrowRight className='h-4 w-4 text-muted-foreground' aria-hidden='true' />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

function FirstRow({ row, count, onOpen }: { row: InvoiceRow; count: number; onOpen: () => void }) {
  const { t, lang } = useT();
  return (
    <li>
      <button
        type='button'
        onClick={onOpen}
        aria-label={`${t.records.invoice.label} ${row.numero ?? row.id}`}
        className='grid w-full grid-cols-1 items-start gap-x-4 gap-y-1 px-4 py-3 text-left hover:bg-row-hover sm:grid-cols-[8.5rem_minmax(10rem,15rem)_7.5rem_1fr]'
      >
        <span>
          <StatusPill group='prioridad' state={row.nivel} />
        </span>
        <span className='flex min-w-0 flex-col'>
          <span data-testid='next-up-number' className='truncate font-mono text-[12.5px] font-medium text-primary'>
            {row.numero ?? '—'}
          </span>
          {count > 1 && <span className='text-xs text-muted-foreground'>{fmt(t.overview.nextUp.sameNumber, { n: count })}</span>}
          <span className='truncate text-[13px] text-soft-foreground'>{row.contraparte ?? '—'}</span>
        </span>
        <span className='sm:text-right'>
          <Money cents={row.total_cent} />
        </span>
        <WhyCell why={whyOf(row, lang, t)} />
      </button>
    </li>
  );
}

