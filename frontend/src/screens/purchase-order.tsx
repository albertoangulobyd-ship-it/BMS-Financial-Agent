// La ficha de una PO (en su pestana): "hoeveel is er over, en hoe lang komt hij nog toe?".
// Arriba que es (de que cliente o para que proveedor, de cuando a cuando), la prioridad, su
// valor, lo consumido (y su parte), lo que queda y la prevision: cuando se acaba al ritmo de
// las ultimas semanas, y lo esperado contando lo planificado y lo aun sin facturar. Despues
// lo que necesita atencion (P5-P10, con que hacer) y, plegado, sus facturas y sus Objects.
import { useEffect } from 'react';
import { AttentionList } from '@/components/attention-list';
import { DataTable, type Columns } from '@/components/data-table';
import { Fact, FactStrip } from '@/components/fact-strip';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText, Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { ruleText } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { PoView } from '@/lib/api-types';
import { formatDateProse, formatMoney, formatPercentFromBasisPoints } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

// Lo que dice el estado de una PO, de sus hallazgos abiertos (las reglas P): junto a lo que
// queda, lo del valor y el plazo (P6, P4, P5, P7); junto a la prevision, lo esperado (P10,
// P9, P8). Una pastilla por dato, la mas seria; la variante la pone components/status-pill
// (grupo po_senal) y el detalle sigue en "Wat aandacht nodig heeft".
const LEFT_SIGNALS = ['P6', 'P4', 'P5', 'P7'] as const;
const FORECAST_SIGNALS = ['P10', 'P9', 'P8'] as const;

export function poSignal(open: ReadonlySet<string>, order: readonly string[]): string | null {
  return order.find((code) => open.has(code)) ?? null;
}

export function PurchaseOrderScreen({ id, tabId }: { id: number; tabId: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { setTabTitle } = useTabs();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () => session!.api.get<{ orden: PoView }>(paths.purchaseOrder(id)).then((r) => r.orden),
    [session, id, version]
  );
  const number = state.status === 'ready' ? state.data.numero : null;
  useEffect(() => {
    if (number) setTabTitle(tabId, number);
  }, [number, tabId, setTabTitle]);
  if (state.status !== 'ready') {
    return (
      <Screen>
        <PageHeader title={fmt(t.records['purchase-order'].fallbackTitle, { id })} description={t.pos.question} />
        {state.status === 'loading' ? <Loading /> : <ErrorState error={state.error} onRetry={retry} />}
      </Screen>
    );
  }
  return <PoDetail po={state.data} />;
}

function PoDetail({ po }: { po: PoView }) {
  const { t, lang } = useT();
  const { openRoute } = useTabs();
  const openInvoice = (invoiceId: number) => openRoute(recordRoute('invoice', invoiceId, 'purchase-orders'));
  const numbers = new Map(po.facturas.map((f) => [f.factura_id, f.numero]));
  const description = fmt(po.lado === 'cliente' ? t.pos.fromClient : t.pos.toProvider, {
    party: po.parte.nombre ?? '—',
    from: formatDateProse(po.fecha_inicio ?? po.fecha_emision, t),
    to: po.fecha_fin ? formatDateProse(po.fecha_fin, t) : t.pos.noEnd,
  });
  const first = po.avisos.hallazgos.find((h) => h.estado === 'abierto');
  const open = new Set(po.avisos.hallazgos.filter((h) => h.estado === 'abierto').map((h) => h.regla));
  const leftSignal = poSignal(open, LEFT_SIGNALS);
  const forecastSignal = poSignal(open, FORECAST_SIGNALS);
  const reason = first ? ruleText(lang, first.regla)?.title : null;
  const runsOut = po.prevision?.agotamiento ?? null;
  const beforeEnd = runsOut && (!po.fecha_fin || runsOut <= po.fecha_fin);
  const expected =
    po.planificado?.estado === 'ok' && po.sin_facturar?.estado === 'ok'
      ? po.consumido_cent + (po.planificado.valor_cent ?? 0) + (po.sin_facturar.valor_cent ?? 0)
      : null;

  return (
    <Screen calm>
      <PageHeader
        title={po.numero}
        description={description}
        meta={
          <span className='inline-flex items-center gap-1'>
            {t.records['purchase-order'].label} <HelpTip term='po' />
          </span>
        }
      />
      {po.cerrada && <p className='mb-6 rounded-md border border-border bg-muted px-4 py-3'>{t.pos.closedNote}</p>}
      <FactStrip>
        <Fact label={t.columns.priority} note={reason}>
          <StatusPill group='prioridad' state={po.prioridad.nivel} />
        </Fact>
        <Fact
          label={t.pos.value}
          note={po.valor_original_cent !== po.valor_cent ? fmt(t.pos.changedFrom, { value: formatMoney(po.valor_original_cent) }) : undefined}
        >
          <Money cents={po.valor_cent} className='text-[15px] font-semibold' />
        </Fact>
        <Fact label={t.pos.used} note={fmt(t.pos.usedShare, { pct: formatPercentFromBasisPoints(po.consumido_pb) })}>
          <Money cents={po.consumido_cent} className='text-[15px] font-semibold' />
        </Fact>
        <Fact label={t.pos.left} note={po.fecha_fin ? fmt(t.pos.until, { date: formatDateProse(po.fecha_fin, t) }) : t.pos.noEnd}>
          <span className='flex flex-col items-start gap-1'>
            <Money
              cents={po.restante_cent}
              className={po.restante_cent <= 0 ? 'text-[15px] font-semibold text-late-foreground' : 'text-[15px] font-semibold'}
            />
            {leftSignal && <StatusPill group='po_senal' state={leftSignal} />}
          </span>
        </Fact>
        <Fact label={t.pos.forecast} note={expected !== null ? fmt(t.pos.expected, { amount: formatMoney(expected) }) : undefined}>
          <span className='flex flex-col items-start gap-1'>
            <span className='text-[15px] font-semibold'>
              {runsOut
                ? beforeEnd
                  ? fmt(t.pos.runsOut, { date: formatDateProse(runsOut, t) })
                  : t.pos.lasts
                : t.pos.tooEarly}
            </span>
            {forecastSignal && <StatusPill group='po_senal' state={forecastSignal} />}
          </span>
        </Fact>
      </FactStrip>

      <section aria-labelledby='po-attention' className='mb-10'>
        <h2 id='po-attention' className='mb-3 text-[16px] font-semibold'>
          {t.invoice.attentionTitle}
        </h2>
        <AttentionList
          items={po.avisos.hallazgos}
          emptyText={t.pos.attentionEmpty}
          invoiceNumber={(invoiceId) => numbers.get(invoiceId) ?? null}
          onOpenInvoice={openInvoice}
        />
      </section>

      <Section title={t.pos.sectionInvoices} summary={String(po.facturas.length)}>
        <PoInvoices po={po} onOpen={openInvoice} />
      </Section>
      <Section title={t.pos.sectionObjects} summary={String(po.objetos.length)}>
        <PoObjects po={po} />
      </Section>
    </Screen>
  );
}

function PoInvoices({ po, onOpen }: { po: PoView; onOpen: (id: number) => void }) {
  const { t } = useT();
  type Row = PoView['facturas'][number];
  const columns: Columns<Row> = [
    { key: 'invoice', header: t.columns.invoice, primary: true, cell: (r) => <span className='font-mono text-[12.5px]'>{r.numero ?? '—'}</span> },
    { key: 'date', header: t.parties.date, width: '8rem', cell: (r) => <DateText value={r.fecha_factura} /> },
    { key: 'amount', header: t.columns.amount, align: 'right', width: '9rem', cell: (r) => <Money cents={r.importe_cent} /> },
    {
      key: 'after',
      header: t.pos.leftAfter,
      align: 'right',
      width: '9rem',
      cell: (r) => <Money cents={r.quedaba_cent - r.importe_cent} />,
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={po.facturas}
      rowKey={(r) => r.factura_id}
      caption={t.pos.sectionInvoices}
      onOpen={(r) => onOpen(r.factura_id)}
      openLabel={(r) => fmt(t.parties.openInvoice, { number: r.numero ?? r.factura_id })}
      empty={<p className='text-muted-foreground'>{t.parties.noInvoices}</p>}
    />
  );
}

function PoObjects({ po }: { po: PoView }) {
  const { t } = useT();
  const { openRoute } = useTabs();
  if (po.objetos.length === 0) return <p className='text-muted-foreground'>{t.pos.noObjects}</p>;
  return (
    <ul className='flex flex-wrap gap-2'>
      {po.objetos.map((o) => (
        <li key={o.id}>
          <button
            type='button'
            onClick={() => openRoute(recordRoute('object', o.id, 'objects'))}
            className='rounded-md border border-border bg-card px-3 py-2 text-left hover:bg-row-hover'
          >
            <span className='block font-mono text-[12.5px] text-primary'>{o.codigo}</span>
            {o.nombre && <span className='block text-[13px] text-soft-foreground'>{o.nombre}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}
