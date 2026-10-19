// La ficha de un Object (en su pestana): "wat levert deze locatie op, wat kost ze en klopt de
// planning met de facturen?". Arriba que es (de que cliente, si pide PO), la prioridad, lo
// que entra, lo que cuesta y el margen del periodo elegido (este mes, el anterior o el ano:
// /api/v2/objetos/N con desde y hasta) y las horas planificadas frente a las facturadas.
// Despues, las facturas de la locatie que piden a una persona; plegado, las horas por semana,
// las facturas a la clientela y de los proveedores y las PO.
import { useEffect, useState } from 'react';
import { DataTable, type Columns } from '@/components/data-table';
import { Fact, FactStrip } from '@/components/fact-strip';
import { FilterChips } from '@/components/filter-chips';
import { HelpTip } from '@/components/help-tip';
import { InvoiceAttentionList } from '@/components/invoice-attention';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText, Hours, Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { stateLabel } from '@/i18n/domain';
import { paths, type InvoiceRow } from '@/lib/api';
import type { ObjectInvoice, ObjectView, PoRow, WeekHours } from '@/lib/api-types';
import { formatHours, formatPercentFromBasisPoints, todayIso } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useTabState } from '@/lib/tab-memory';
import { needsPerson } from '@/lib/why';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

export type ObjectPeriod = 'month' | 'lastMonth' | 'year';

// Lo que necesita atencion es una lista corta: las cinco mas urgentes, y cuantas mas hay
// (todas estan en las secciones de facturas, abajo).
const ATTENTION_MAX = 5;

/** Desde y hasta de un periodo, contados desde hoy (AAAA-MM-DD); el mes en curso es el de la
 *  API sin parametros. */
export function periodRange(period: ObjectPeriod, today: string): { desde: string; hasta: string } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(today);
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const pad = (n: number) => String(n).padStart(2, '0');
  if (period === 'month') return null;
  if (period === 'year') return { desde: `${year}-01-01`, hasta: today };
  const prevYear = month === 1 ? year - 1 : year;
  const prevMonth = month === 1 ? 12 : month - 1;
  const lastDay = new Date(Date.UTC(prevYear, prevMonth, 0)).getUTCDate();
  return { desde: `${prevYear}-${pad(prevMonth)}-01`, hasta: `${prevYear}-${pad(prevMonth)}-${pad(lastDay)}` };
}

export function ObjectScreen({ id, tabId }: { id: number; tabId: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { setTabTitle } = useTabs();
  const { version } = useRefresh();
  const [period, setPeriod] = useTabState<ObjectPeriod>(tabId, 'object-period', 'month');
  const [today] = useState(() => todayIso());
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ objeto: ObjectView }>(paths.object(id), periodRange(period, today) ?? undefined).then((r) => r.objeto),
        session!.api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas),
      ]),
    [session, id, version, period, today]
  );
  const code = state.status === 'ready' ? state.data[0].codigo : null;
  useEffect(() => {
    if (code) setTabTitle(tabId, code);
  }, [code, tabId, setTabTitle]);

  if (state.status !== 'ready') {
    return (
      <Screen>
        <PageHeader title={fmt(t.records.object.fallbackTitle, { id })} description={t.objects.question} />
        {state.status === 'loading' ? <Loading /> : <ErrorState error={state.error} onRetry={retry} />}
      </Screen>
    );
  }
  return <ObjectDetail object={state.data[0]} invoices={state.data[1]} period={period} setPeriod={setPeriod} />;
}

function ObjectDetail({
  object: o,
  invoices,
  period,
  setPeriod,
}: {
  object: ObjectView;
  invoices: InvoiceRow[];
  period: ObjectPeriod;
  setPeriod: (p: ObjectPeriod) => void;
}) {
  const { t } = useT();
  const { openRoute } = useTabs();
  const openInvoice = (invoiceId: number) => openRoute(recordRoute('invoice', invoiceId, 'objects'));
  const ids = new Set([...o.facturas.entrantes, ...o.facturas.salientes].map((f) => f.id));
  const attention = invoices.filter((f) => ids.has(f.id) && needsPerson(f));
  const e = o.economia.periodo;
  const total = o.horas.total;
  const description = [
    o.cliente ? fmt(t.objects.siteOf, { client: o.cliente.nombre }) : t.objects.noClient,
    o.requiere_po ? t.objects.poRequired : '',
  ]
    .filter(Boolean)
    .join(' ');
  const periodNote = (
    <span>
      <DateText value={e.desde} /> – <DateText value={e.hasta} /> · {t.objects.exclVat}
    </span>
  );

  return (
    <Screen>
      <PageHeader
        title={o.nombre ?? o.codigo}
        description={description}
        meta={<span className='font-mono'>{o.codigo}</span>}
        action={
          <FilterChips<ObjectPeriod>
            label={t.objects.periodLabel}
            value={period}
            onChange={setPeriod}
            chips={[
              { key: 'month', label: t.objects.thisMonth },
              { key: 'lastMonth', label: t.objects.lastMonth },
              { key: 'year', label: t.objects.thisYear },
            ]}
          />
        }
      />
      <FactStrip>
        <Fact label={t.columns.priority}>
          <StatusPill group='prioridad' state={o.prioridad.nivel} />
        </Fact>
        <Fact label={t.objects.revenueFact} note={periodNote}>
          <Money cents={e.ingresos_cent} className='text-[15px] font-semibold' />
        </Fact>
        <Fact label={t.objects.costsFact} note={periodNote}>
          <Money cents={e.costes_cent} className='text-[15px] font-semibold' />
        </Fact>
        <Fact label={t.objects.marginFact} note={e.margen_pb !== null ? formatPercentFromBasisPoints(e.margen_pb) : undefined}>
          <Money
            cents={e.margen_cent}
            className={e.margen_cent < 0 ? 'text-[15px] font-semibold text-late-foreground' : 'text-[15px] font-semibold'}
          />
        </Fact>
        <Fact
          label={t.objects.hoursFact}
          note={o.horas.planning === 'ok' && total ? fmt(t.objects.hoursBilled, { hours: formatHours(total.cliente_mil) }) : undefined}
        >
          {o.horas.planning === 'ok' && total ? (
            <span className='text-[15px] font-semibold'>{fmt(t.objects.hoursPlanned, { hours: formatHours(total.planificadas_mil) })}</span>
          ) : (
            <span className='text-muted-foreground'>{t.parties.noPlanning}</span>
          )}
        </Fact>
      </FactStrip>

      <section aria-labelledby='object-attention' className='mb-10'>
        <h2 id='object-attention' className='mb-3 text-[16px] font-semibold'>
          {t.invoice.attentionTitle}
        </h2>
        <InvoiceAttentionList rows={attention.slice(0, ATTENTION_MAX)} emptyText={t.objects.attentionEmpty} onOpen={openInvoice} />
        {attention.length > ATTENTION_MAX && (
          <p className='mt-2 text-[13px] text-muted-foreground'>
            {fmt(t.objects.moreInvoices, { n: attention.length - ATTENTION_MAX })}
          </p>
        )}
      </section>

      <Section title={t.objects.sectionWeeks} summary={String(o.horas.semanas.length)}>
        <Weeks object={o} />
      </Section>
      <Section title={t.objects.sectionSales} summary={String(o.facturas.salientes.length)}>
        <ObjectInvoices rows={o.facturas.salientes} onOpen={openInvoice} caption={t.objects.sectionSales} />
      </Section>
      <Section title={t.objects.sectionPurchases} summary={String(o.facturas.entrantes.length)}>
        <ObjectInvoices rows={o.facturas.entrantes} onOpen={openInvoice} caption={t.objects.sectionPurchases} />
      </Section>
      <Section
        title={t.objects.sectionPos}
        summary={String(o.ordenes_compra.length)}
      >
        <ObjectPos rows={o.ordenes_compra} />
      </Section>
    </Screen>
  );
}

function Weeks({ object: o }: { object: ObjectView }) {
  const { t } = useT();
  if (o.horas.planning !== 'ok') return <p className='text-muted-foreground'>{t.objects.noPlanning}</p>;
  const hours = (mil: number | null) => <Hours mil={mil} />;
  const columns: Columns<WeekHours> = [
    { key: 'week', header: t.objects.week, width: '7rem', cell: (r) => <span className='num whitespace-nowrap'>{weekLabel(r.semana)}</span> },
    { key: 'planned', header: t.objects.planned, align: 'right', cell: (r) => hours(r.planificadas_mil) },
    { key: 'validated', header: t.objects.validated, align: 'right', cell: (r) => hours(r.validadas_mil) },
    { key: 'client', header: t.objects.billedClient, align: 'right', cell: (r) => hours(r.cliente_mil) },
    { key: 'providers', header: t.objects.billedProviders, align: 'right', cell: (r) => hours(r.proveedor_mil) },
    {
      key: 'not',
      header: t.objects.notBilled,
      align: 'right',
      cell: (r) => (
        <Hours mil={r.sin_facturar_mil} className={(r.sin_facturar_mil ?? 0) > 0 ? 'font-medium text-late-foreground' : undefined} />
      ),
    },
  ];
  return <DataTable columns={columns} rows={o.horas.semanas} rowKey={(r) => r.semana} caption={t.objects.sectionWeeks} />;
}

/** "2026-W31" -> "31 · 2026": la semana primero, que es lo que se busca. */
export function weekLabel(week: string): string {
  const m = /^(\d{4})-W(\d{2})$/.exec(week);
  return m ? `${Number(m[2])} · ${m[1]}` : week;
}

function ObjectInvoices({ rows, onOpen, caption }: { rows: ObjectInvoice[]; onOpen: (id: number) => void; caption: string }) {
  const { t } = useT();
  const columns: Columns<ObjectInvoice> = [
    {
      key: 'invoice',
      header: t.columns.invoice,
      primary: true,
      cell: (r) => <span className='whitespace-nowrap font-mono text-[12.5px]'>{r.numero ?? '—'}</span>,
    },
    { key: 'party', header: t.objects.party, cell: (r) => r.contraparte ?? '—' },
    { key: 'date', header: t.parties.date, width: '8rem', cell: (r) => <DateText value={r.fecha_factura} /> },
    { key: 'amount', header: t.objects.amountObject, align: 'right', width: '9rem', cell: (r) => <Money cents={r.importe_objeto_cent} /> },
    { key: 'hours', header: t.parties.hours, align: 'right', width: '6rem', cell: (r) => <Hours mil={r.horas_mil} /> },
    {
      key: 'payment',
      header: t.parties.payment,
      width: '8.5rem',
      cell: (r) => <StatusPill group='pago' state={r.estado_pago} />,
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      caption={caption}
      onOpen={(r) => onOpen(r.id)}
      openLabel={(r) => fmt(t.parties.openInvoice, { number: r.numero ?? r.id })}
      empty={<p className='text-muted-foreground'>{t.parties.noInvoices}</p>}
    />
  );
}

function ObjectPos({ rows }: { rows: PoRow[] }) {
  const { t, lang } = useT();
  const { openRoute } = useTabs();
  const columns: Columns<PoRow> = [
    {
      key: 'po',
      header: (
        <span className='inline-flex items-center gap-1'>
          {t.pos.po} <HelpTip term='po' />
        </span>
      ),
      primary: true,
      cell: (r) => <span className='whitespace-nowrap font-mono text-[12.5px]'>{r.numero}</span>,
    },
    { key: 'side', header: t.parties.kind, cell: (r) => stateLabel(lang, 'lado_po', r.lado) ?? r.lado },
    { key: 'value', header: t.pos.value, align: 'right', width: '9rem', cell: (r) => <Money cents={r.valor_cent} /> },
    { key: 'used', header: t.pos.used, align: 'right', width: '9rem', cell: (r) => <Money cents={r.consumido_cent} /> },
    { key: 'left', header: t.pos.left, align: 'right', width: '9rem', cell: (r) => <Money cents={r.restante_cent} /> },
  ];
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      caption={t.objects.sectionPos}
      onOpen={(r) => openRoute(recordRoute('purchase-order', r.id, 'purchase-orders'))}
      openLabel={(r) => fmt(t.common.openRecord, { what: `${t.records['purchase-order'].label} ${r.numero}` })}
      empty={<p className='text-muted-foreground'>{t.objects.noPos}</p>}
    />
  );
}
