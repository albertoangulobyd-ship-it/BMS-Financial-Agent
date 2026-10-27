// Overzicht / Overview: "wat heeft vandaag mijn aandacht nodig en hoe staat het geld?".
// Cuatro tarjetas como mucho (aandacht, geld binnen, geld uit, btw dit kwartaal), cada
// una abre la pantalla que la explica, y "Als eerste" con las cinco primeras facturas de
// la werklijst. Nada mas: lo demas vive en su pantalla.
import { ArrowRight } from 'lucide-react';
import { AuroraOrb } from '@/aurora/orb/aurora-orb';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { SummaryCard, SummaryGrid } from '@/components/summary-card';
import { Button } from '@/components/ui/button';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { fmt, useT } from '@/i18n';
import { paths, type InvoiceRow, type Panel } from '@/lib/api';
import { formatDate, formatDateProse, quarterLabel } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { distinctByNumber } from '@/lib/twins';
import { needsPerson, whyOf } from '@/lib/why';
import { CircleCheck } from 'lucide-react';
import { recordRoute, type NavId } from './registry';
import { deadlineState, overdueQuarters } from './vat';
import { useLoad } from './use-load';

const NEXT_UP = 5;

export function OverviewScreen() {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ panel: Panel }>(paths.panel).then((r) => r.panel),
        session!.api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas),
      ]),
    [session, version]
  );
  const nav = t.nav.overview;

  return (
    <Screen calm>
      <PageHeader
        title={nav.label}
        description={nav.description}
        // El orbe de Aurora, el asistente: quieto en reposo; se mueve mientras lee el panel.
        // Un bloque de 160 px cuyo margen negativo lo deja en 56 px de alto, centrado con el
        // titulo y su frase: no empuja la cabecera hacia abajo.
        action={<AuroraOrb label={t.aurora.orb} size={160} active={state.status === 'loading'} className='-my-13 -mr-4 grid' />}
      />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && <OverviewContent panel={state.data[0]} invoices={state.data[1]} />}
    </Screen>
  );
}

function OverviewContent({ panel, invoices }: { panel: Panel; invoices: InvoiceRow[] }) {
  const { t } = useT();
  const { openRoute, setActiveNav } = useTabs();
  const a = panel.atencion;
  const vat = panel.btw;
  const queue = invoices.filter(needsPerson);
  // La misma cuenta que la werklijst: lo que pide a una persona (no solo la prioridad).
  const needing = queue.length;
  const deadline = vat.proximo_plazo;
  // La misma regla que la lista del btw: pasado y sin aangifte, o a 14 dias o menos.
  const deadlineStatus = deadline ? deadlineState(deadline) : null;
  // Un plazo que ya paso sin la aangifte anotada va primero: es lo unico de la tarjeta que
  // pide hacer algo ya, y el proximo plazo no lo dice.
  const overdue = overdueQuarters(vat);
  const open = (id: NavId) => setActiveNav(id);

  const go = (id: NavId, label: string) => (
    <Button variant='link' size='sm' className='h-auto px-0 py-0 text-xs' onClick={() => open(id)}>
      {label}
      <ArrowRight className='ml-1 h-3.5 w-3.5' aria-hidden='true' />
    </Button>
  );

  return (
    <div className='flex flex-col gap-8'>
      {!panel.al_dia && (
        <div role='status' className='-mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]'>
          <StatusPill group='fuente' state='caducada' />
          <span>{fmt(t.overview.stale, { date: formatDate(panel.estado_del) })}</span>
        </div>
      )}
      <SummaryGrid>
        <SummaryCard
          title={t.overview.attention.title}
          value={fmt(needing === 1 ? t.overview.attention.valueOne : t.overview.attention.value, { n: needing })}
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
          action={go('work-queue', t.overview.open.workQueue)}
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
            },
            { label: t.overview.money.next30, value: <Money cents={panel.dinero_entra.proximos_30_cent} /> },
          ]}
          action={go('invoices-out', t.overview.open.invoicesOut)}
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
            },
            { label: t.overview.money.thisWeek, value: <Money cents={panel.dinero_sale.semana_cent} /> },
          ]}
          action={go('invoices-in', t.overview.open.invoicesIn)}
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
                  // Cerca: la pastilla dice los dias ("Nog 12 dagen"), como en Btw y en el
                  // trimestre; si no, en gris.
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
          action={go('vat', t.overview.open.vat)}
        />
      </SummaryGrid>

      <section aria-labelledby='next-up'>
        <div className='mb-2 flex items-baseline justify-between gap-4'>
          <h2 id='next-up' className='text-[15px] font-semibold'>
            {t.overview.nextUp.title}
          </h2>
          {queue.length > NEXT_UP && go('work-queue', fmt(t.overview.nextUp.all, { n: queue.length }))}
        </div>
        {queue.length === 0 ? (
          <EmptyState icon={CircleCheck} title={t.empty.nothingNeedsAttention} text={t.overview.nextUp.empty} />
        ) : (
          <ol className='divide-y divide-divider overflow-hidden rounded-md border border-border bg-card'>
            {/* Cinco cosas distintas: las facturas con el mismo numero y relacion van en una
                fila, con cuantas son (las dos estan en la Werklijst). */}
            {distinctByNumber(queue)
              .slice(0, NEXT_UP)
              .map(({ row, count }) => (
                <NextUpRow key={row.id} row={row} count={count} onOpen={() => openRoute(recordRoute('invoice', row.id, 'work-queue'))} />
              ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function NextUpRow({ row, count, onOpen }: { row: InvoiceRow; count: number; onOpen: () => void }) {
  const { t, lang } = useT();
  return (
    <li>
      <button
        type='button'
        onClick={onOpen}
        aria-label={`${t.records.invoice.label} ${row.numero ?? row.id}`}
        className='grid w-full grid-cols-[8.5rem_minmax(10rem,15rem)_7.5rem_1fr] items-start gap-4 px-4 py-3 text-left hover:bg-row-hover'
      >
        <span>
          <StatusPill group='prioridad' state={row.nivel} />
        </span>
        <span className='flex min-w-0 flex-col'>
          <span data-testid='next-up-number' className='truncate font-mono text-[12.5px] font-medium text-primary'>{row.numero ?? '—'}</span>
          {count > 1 && <span className='text-xs text-muted-foreground'>{fmt(t.overview.nextUp.sameNumber, { n: count })}</span>}
          <span className='truncate text-[13px] text-soft-foreground'>{row.contraparte ?? '—'}</span>
        </span>
        <span className='text-right'>
          <Money cents={row.total_cent} />
        </span>
        <WhyCell why={whyOf(row, lang, t)} />
      </button>
    </li>
  );
}

// El trimestre como se lee vive en lib/format (lo usan tambien el btw y las pestanas).
export { quarterLabel } from '@/lib/format';
