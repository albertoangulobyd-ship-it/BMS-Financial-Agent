// La ficha de un proveedor o un cliente (en su pestana): "wat staat er open en wat valt op?".
// Arriba que es (cuantas facturas y cuanto queda), cinco cifras (prioridad, openstaand,
// vervallen, lo facturado este ano y el plazo de pago o lo que queda por facturar), despues
// lo que necesita atencion (cada hallazgo con que hacer y su factura, que se abre en su
// pestana) y, plegado debajo, las facturas, los pagos, los Objetos, las cuentas y las
// relaciones propuestas. Las ordenes de una factura estan en la factura: aqui solo se mira.
import { useEffect, useMemo, type ReactNode } from 'react';
import { AttentionList } from '@/components/attention-list';
import { DataTable, type Columns } from '@/components/data-table';
import { Fact, FactStrip } from '@/components/fact-strip';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { useNav } from '@/shell/navigation';
import { DateText, Hours, Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { ruleText, stateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { PartyInvoice, PartyView, ProposedRelation } from '@/lib/api-types';
import { formatHours, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { UnlinkedCredit, type PartyKind } from './party-list';
import { recordRoute } from './registry';
import { useLoad } from './use-load';
import { twinMarks, type TwinMark } from '@/lib/twins';

export function PartyScreen({ kind, id, navKey }: { kind: PartyKind; id: number; navKey: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { setTitle } = useNav();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        kind === 'provider'
          ? session!.api.get<{ proveedor: PartyView }>(paths.provider(id)).then((r) => r.proveedor)
          : session!.api.get<{ cliente: PartyView }>(paths.client(id)).then((r) => r.cliente),
        session!.api.get<{ relaciones: ProposedRelation[] }>(paths.relations).then((r) => r.relaciones),
      ]),
    [session, id, kind, version]
  );
  // La pestana toma el nombre (texto del maestro: se pinta como texto).
  const name = state.status === 'ready' ? state.data[0].nombre : null;
  useEffect(() => {
    if (name) setTitle(navKey, name);
  }, [name, navKey, setTitle]);

  if (state.status !== 'ready') {
    return (
      <Screen>
        <PageHeader
          title={fmt(t.records[kind].fallbackTitle, { id })}
          description={kind === 'provider' ? t.parties.questionProvider : t.parties.questionClient}
        />
        {state.status === 'loading' ? <Loading /> : <ErrorState error={state.error} onRetry={retry} />}
      </Screen>
    );
  }
  return <PartyDetail kind={kind} party={state.data[0]} relations={state.data[1]} />;
}

function PartyDetail({ kind, party: p, relations }: { kind: PartyKind; party: PartyView; relations: ProposedRelation[] }) {
  const { t, lang } = useT();
  const { open: openRoute } = useNav();
  const numbers = useMemo(() => new Map(p.historial.map((f) => [f.id, f.numero])), [p.historial]);
  const openInvoice = (invoiceId: number) => openRoute(recordRoute('invoice', invoiceId));
  const invoices = fmt(p.facturas === 1 ? t.parties.invoicesOne : t.parties.invoices, { n: p.facturas });
  const description = `${fmt(kind === 'provider' ? t.parties.isProvider : t.parties.isClient, { invoices })} ${
    p.deuda_cent > 0 ? fmt(t.parties.openAmount, { amount: formatMoney(p.deuda_cent) }) : t.parties.nothingOpen
  }`;
  const first = p.avisos.hallazgos.find((h) => h.estado === 'abierto');
  const reason = first ? ruleText(lang, first.regla)?.title : null;
  // Solo las relaciones propuestas entre facturas de esta relacion.
  const ours = relations.filter((r) => numbers.has(r.origen_id) || numbers.has(r.destino_id));

  return (
    <Screen calm>
      <PageHeader title={p.nombre} description={description} meta={p.exact_id ? `Exact ${p.exact_id}` : undefined} />
      <FactStrip>
        <Fact label={t.columns.priority} note={reason}>
          <StatusPill group='prioridad' state={p.prioridad.nivel} />
        </Fact>
        <Fact
          label={t.parties.outstanding}
          note={fmt(p.abiertas === 1 ? t.parties.openInvoicesCountOne : t.parties.openInvoicesCount, { n: p.abiertas })}
        >
          {/* La cifra de la cartera; los abonos sin enlazar, aparte (revision del paso 16). */}
          <Money cents={p.deuda_cent} className='text-[15px] font-semibold' />
          <UnlinkedCredit party={p} />
        </Fact>
        <Fact
          label={t.parties.overdueColumn}
          note={p.vencidas > 0 ? fmt(p.vencidas === 1 ? t.parties.overdueCountOne : t.parties.overdueCount, { n: p.vencidas }) : undefined}
        >
          <Money
            cents={p.vencido_cent}
            className={p.vencido_cent > 0 ? 'text-[15px] font-semibold text-late-foreground' : 'text-[15px] font-semibold'}
          />
        </Fact>
        <Fact label={fmt(t.parties.billedYear, { year: p.ano })} note={t.parties.inclVat}>
          <Money cents={p.ano_facturado.total_cent} className='text-[15px] font-semibold' />
        </Fact>
        {kind === 'client' ? <UnbilledFact party={p} /> : <TermFact party={p} />}
      </FactStrip>

      <section aria-labelledby='party-attention' className='mb-10'>
        <h2 id='party-attention' className='mb-3 text-[16px] font-semibold'>
          {t.invoice.attentionTitle}
        </h2>
        <AttentionList
          items={p.avisos.hallazgos}
          emptyText={t.parties.nothingStandsOut}
          invoiceNumber={(invoiceId) => numbers.get(invoiceId) ?? null}
          onOpenInvoice={openInvoice}
        />
        {p.avisos.excepciones.length > 0 && (
          <p className='mt-3 text-[13px] text-muted-foreground'>
            {fmt(t.parties.exceptionsOpen, { n: p.avisos.excepciones.length })}
          </p>
        )}
      </section>

      {/* Lo que tiene abierto, a la vista: lo pendiente de una empresa y sus facturas en dos
          clics desde el inicio (revision §5, fila 8). Lo demas, plegado. */}
      <Section title={t.parties.sectionOpen} summary={String(p.abiertas_detalle.length)} defaultOpen={p.abiertas_detalle.length > 0}>
        <OpenInvoices party={p} onOpen={openInvoice} />
      </Section>
      <Section title={t.parties.sectionAll} summary={String(p.historial.length)}>
        <AllInvoices rows={p.historial} onOpen={openInvoice} />
      </Section>
      <Section title={t.parties.sectionPayments} summary={String(p.pagos.length)}>
        <Payments party={p} onOpen={openInvoice} />
      </Section>
      <Section title={t.parties.sectionObjects} summary={String(p.por_objeto.length)}>
        <PerObject party={p} />
      </Section>
      {kind === 'provider' && (
        <Section title={t.parties.sectionAccounts} summary={String(p.ibanes?.registro.length ?? 0)}>
          <Accounts party={p} />
        </Section>
      )}
      {kind === 'client' && (
        <Section title={t.parties.sectionUnbilled} summary={String(p.trabajo_sin_facturar?.periodos.length ?? 0)}>
          <Unbilled party={p} />
        </Section>
      )}
      {ours.length > 0 && (
        <Section title={t.parties.sectionRelations} summary={String(ours.length)}>
          <Relations relations={ours} numbers={numbers} onOpen={openInvoice} />
        </Section>
      )}
    </Screen>
  );
}

function TermFact({ party: p }: { party: PartyView }) {
  const { t } = useT();
  const mean = p.plazo_de_pago.media_dias;
  return (
    <Fact label={t.parties.paymentTerm} note={mean !== null ? fmt(t.parties.paidAfter, { n: mean }) : undefined}>
      <span className='text-[15px] font-semibold'>
        {p.plazo_pago_dias !== null ? fmt(t.parties.days, { n: p.plazo_pago_dias }) : t.common.unknown}
      </span>
    </Fact>
  );
}

function UnbilledFact({ party: p }: { party: PartyView }) {
  const { t } = useT();
  const work = p.trabajo_sin_facturar;
  if (!work || work.estado !== 'ok') {
    return (
      <Fact label={t.parties.unbilled}>
        <span className='text-muted-foreground'>{t.parties.noPlanning}</span>
      </Fact>
    );
  }
  const none = !work.valor_cent && !work.horas_mil;
  return (
    <Fact
      label={t.parties.unbilled}
      note={none ? undefined : `${fmt(t.parties.unbilledHours, { hours: formatHours(work.horas_mil) })}${work.estimado ? ` · ${t.parties.estimate}` : ''}`}
    >
      {none ? (
        <span className='text-[15px] font-semibold'>{t.parties.nothingUnbilled}</span>
      ) : (
        <Money cents={work.valor_cent} className='text-[15px] font-semibold text-late-foreground' />
      )}
    </Fact>
  );
}

function PaymentState({ state }: { state: string | null }) {
  return <StatusPill group='pago' state={state} />;
}

function InvoiceNumber({ value, twin }: { value: string | null; twin?: TwinMark | undefined }) {
  const { t } = useT();
  return (
    <span className='whitespace-nowrap font-mono text-[12.5px]'>
      {value ?? '—'}
      {twin && <span className='ml-1.5 font-sans text-xs font-normal text-muted-foreground'>{fmt(t.common.twin, { n: twin.n, of: twin.of })}</span>}
    </span>
  );
}

/** Las de la misma relacion con el mismo numero, para su "1 van 2". */
const twinsOf = (rows: readonly { id: number; numero: string | null }[]) => twinMarks(rows.map((r) => ({ ...r, contraparte: null })));

function OpenInvoices({ party: p, onOpen }: { party: PartyView; onOpen: (id: number) => void }) {
  const { t } = useT();
  type Row = PartyView['abiertas_detalle'][number];
  const twins = twinsOf(p.abiertas_detalle);
  const columns: Columns<Row> = [
    { key: 'invoice', header: t.columns.invoice, primary: true, cell: (r) => <InvoiceNumber value={r.numero} twin={twins.get(r.id)} /> },
    { key: 'due', header: t.columns.due, width: '8rem', cell: (r) => <DateText value={r.vencimiento} /> },
    { key: 'outstanding', header: t.parties.outstanding, align: 'right', width: '9rem', cell: (r) => <Money cents={r.pendiente_cent} /> },
    { key: 'payment', header: t.parties.payment, width: '9rem', cell: (r) => <PaymentState state={r.estado_pago} /> },
  ];
  return (
    <DataTable
      columns={columns}
      rows={p.abiertas_detalle}
      rowKey={(r) => r.id}
      caption={t.parties.sectionOpen}
      onOpen={(r) => onOpen(r.id)}
      openLabel={(r) => fmt(t.parties.openInvoice, { number: r.numero ?? r.id })}
      empty={<p className='text-muted-foreground'>{t.parties.nothingOpen}</p>}
    />
  );
}

export function AllInvoices({ rows, onOpen }: { rows: PartyInvoice[]; onOpen: (id: number) => void }) {
  const { t } = useT();
  const twins = twinsOf(rows);
  const columns: Columns<PartyInvoice> = [
    { key: 'invoice', header: t.columns.invoice, primary: true, cell: (r) => <InvoiceNumber value={r.numero} twin={twins.get(r.id)} /> },
    { key: 'date', header: t.parties.date, width: '8rem', cell: (r) => <DateText value={r.fecha_factura} /> },
    { key: 'amount', header: t.columns.amount, align: 'right', width: '9rem', cell: (r) => <Money cents={r.total_cent} /> },
    { key: 'outstanding', header: t.parties.outstanding, align: 'right', width: '9rem', cell: (r) => <Money cents={r.pendiente_cent} /> },
    { key: 'payment', header: t.parties.payment, width: '9rem', cell: (r) => <PaymentState state={r.estado_pago} /> },
  ];
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      caption={t.parties.sectionAll}
      onOpen={(r) => onOpen(r.id)}
      openLabel={(r) => fmt(t.parties.openInvoice, { number: r.numero ?? r.id })}
      empty={<p className='text-muted-foreground'>{t.parties.noInvoices}</p>}
    />
  );
}

function Payments({ party: p, onOpen }: { party: PartyView; onOpen: (id: number) => void }) {
  const { t, lang } = useT();
  type Row = PartyView['pagos'][number];
  const columns: Columns<Row> = [
    { key: 'date', header: t.parties.date, width: '8rem', cell: (r) => <DateText value={r.fecha} /> },
    { key: 'invoice', header: t.columns.invoice, primary: true, cell: (r) => <InvoiceNumber value={r.numero} /> },
    { key: 'amount', header: t.columns.amount, align: 'right', width: '9rem', cell: (r) => <Money cents={r.importe_cent} /> },
    {
      key: 'source',
      header: t.parties.according,
      width: '9rem',
      cell: (r) => <span>{stateLabel(lang, 'fuente_aplicacion', r.fuente) ?? r.fuente}</span>,
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={p.pagos}
      rowKey={(r) => r.aplicacion_id}
      caption={t.parties.sectionPayments}
      onOpen={(r) => onOpen(r.factura_id)}
      openLabel={(r) => fmt(t.parties.openInvoice, { number: r.numero ?? r.factura_id })}
      empty={<p className='text-muted-foreground'>{t.parties.noPayments}</p>}
    />
  );
}

function PerObject({ party: p }: { party: PartyView }) {
  const { t } = useT();
  const { open: openRoute } = useNav();
  type Row = PartyView['por_objeto'][number];
  const columns: Columns<Row> = [
    {
      key: 'object',
      header: t.objects.object,
      primary: true,
      cell: (r) => (
        <span className='flex flex-col items-start'>
          <span className='font-mono text-[12.5px]'>{r.objeto ?? '—'}</span>
          {r.nombre && <span className='text-[13px] font-normal text-soft-foreground'>{r.nombre}</span>}
        </span>
      ),
    },
    { key: 'count', header: t.parties.count, align: 'right', width: '7rem', cell: (r) => <span className='num'>{r.facturas}</span> },
    { key: 'amount', header: t.parties.amountExclVat, align: 'right', width: '10rem', cell: (r) => <Money cents={r.importe_cent} /> },
    { key: 'hours', header: t.parties.hours, align: 'right', width: '8rem', cell: (r) => <Hours mil={r.horas_mil} /> },
  ];
  const rows = p.por_objeto;
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.objeto_id ?? 0}
      caption={t.parties.sectionObjects}
      onOpen={(r) => r.objeto_id && openRoute(recordRoute('object', r.objeto_id))}
      openLabel={(r) => fmt(t.common.openRecord, { what: `${t.records.object.label} ${r.objeto ?? ''}` })}
      empty={<p className='text-muted-foreground'>{t.parties.noInvoices}</p>}
    />
  );
}

function Accounts({ party: p }: { party: PartyView }) {
  const { t } = useT();
  type Row = NonNullable<PartyView['ibanes']>['registro'][number];
  const yesNo = (v: boolean) => (v ? t.parties.yes : t.parties.no);
  const columns: Columns<Row> = [
    { key: 'iban', header: t.parties.iban, cell: (r) => <span className='font-mono text-[12.5px] tracking-[0.02em]'>{r.iban}</span> },
    {
      key: 'state',
      header: t.parties.status,
      cell: (r) => <StatusPill group='cuenta' state={r.estado} />,
    },
    { key: 'exact', header: t.parties.inExact, width: '7rem', cell: (r) => yesNo(r.en_exact) },
    { key: 'payable', header: t.parties.payable, width: '7rem', cell: (r) => yesNo(r.pagable) },
  ];
  return (
    <div className='flex flex-col gap-3'>
      <p className='text-[13px]'>
        {p.telefono_verificacion ? fmt(t.parties.phoneForChecks, { phone: p.telefono_verificacion }) : t.parties.noPhone}
      </p>
      <DataTable columns={columns} rows={p.ibanes?.registro ?? []} rowKey={(r) => r.id} caption={t.parties.sectionAccounts} />
      <p className='text-xs text-muted-foreground'>{t.parties.accountsHelp}</p>
    </div>
  );
}

function Unbilled({ party: p }: { party: PartyView }) {
  const { t } = useT();
  const work = p.trabajo_sin_facturar;
  type Row = NonNullable<PartyView['trabajo_sin_facturar']>['periodos'][number];
  if (!work || work.estado !== 'ok') return <p className='text-muted-foreground'>{t.parties.noPlanning}</p>;
  const columns: Columns<Row> = [
    {
      key: 'period',
      header: t.parties.period,
      cell: (r) => (
        <span>
          <DateText value={r.desde} /> – <DateText value={r.hasta} />
        </span>
      ),
    },
    { key: 'hours', header: t.parties.hours, align: 'right', width: '8rem', cell: (r) => <Hours mil={r.horas_mil} /> },
    {
      key: 'value',
      header: t.parties.value,
      align: 'right',
      width: '10rem',
      cell: (r) => (
        <span>
          <Money cents={r.valor_cent} />
          {r.estimado && <span className='block text-xs text-muted-foreground'>{t.parties.estimate}</span>}
        </span>
      ),
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={work.periodos}
      rowKey={(r) => r.hallazgo_id}
      caption={t.parties.sectionUnbilled}
      empty={<p className='text-muted-foreground'>{t.parties.noUnbilled}</p>}
    />
  );
}

function Relations({
  relations,
  numbers,
  onOpen,
}: {
  relations: ProposedRelation[];
  numbers: Map<number, string | null>;
  onOpen: (id: number) => void;
}) {
  const { t, lang } = useT();
  const invoice = (id: number): ReactNode => <InvoiceNumber value={numbers.get(id) ?? String(id)} />;
  const columns: Columns<ProposedRelation> = [
    { key: 'from', header: t.parties.from, primary: true, cell: (r) => invoice(r.origen_id) },
    { key: 'kind', header: t.parties.kind, cell: (r) => stateLabel(lang, 'tipo_relacion', r.tipo) ?? r.tipo },
    { key: 'to', header: t.parties.to, cell: (r) => invoice(r.destino_id) },
    { key: 'source', header: t.parties.source, cell: (r) => stateLabel(lang, 'fuente_relacion', r.fuente) ?? r.fuente },
  ];
  return (
    <div className='flex flex-col gap-2'>
      <DataTable
        columns={columns}
        rows={relations}
        rowKey={(r) => r.id}
        caption={t.parties.sectionRelations}
        onOpen={(r) => onOpen(r.origen_id)}
        openLabel={(r) => fmt(t.parties.openInvoice, { number: numbers.get(r.origen_id) ?? r.origen_id })}
      />
      <p className='text-xs text-muted-foreground'>{t.parties.relationsHelp}</p>
    </div>
  );
}
