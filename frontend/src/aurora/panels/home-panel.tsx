// E2-I, el panel Inicio (especificacion §2.2.1): lo que pide atencion, primero. En reposo, la
// cifra principal (cuantas facturas necesitan a una persona; la barra, la parte bloqueada o
// urgente) y una fila por grupo: Lo primero, la Cola de trabajo, las Excepciones, los IBAN por
// verificar y el Flujo de caja de las proximas cuatro semanas. Cada grupo abre su vista (cinco
// filas como mucho y el campo .search si hay mas), y cada fila su tarjeta .detail con sus
// ordenes: la de una factura (§2.2.7), la de una excepcion (llevarla yo, asignar, esperar,
// resolver) y la de una cuenta (confirmar por telefono en tres pasos, rechazar; las cuentas
// heredadas). Sustituye a las pantallas de Inicio, Werklijst, Uitzonderingen, IBAN-controles y
// Kasstroom de los pasos 15 y 16; sus reglas son las mismas (lib/why.ts, iban-model.ts).
import { useState, type ReactNode } from 'react';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { findingDetail, priorityLabel, ruleText, stateLabel, templateCatalog } from '@/i18n/domain';
import { formatWith } from '@/i18n/templates';
import { paths, type InvoiceRow } from '@/lib/api';
import type { AccountRow, CashFlow, ExceptionRow, Person, PoRow, ProviderAccounts } from '@/lib/api-types';
import { formatDate, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { distinctByNumber, twinMarks, type TwinMark } from '@/lib/twins';
import { needsPerson, whyOf } from '@/lib/why';
import { useLoad } from '../use-load';
import { entryIndex } from '../estado';
import { useOpenInvoice } from '../navigation';
import { Orders, apiErrorMessage, ErrorLine, type OrderSpec } from '../orders';
import { useAurora } from '../root';
import { ExceptionLines, exceptionOrders, exceptionState } from './exception-orders';
import { accountStep, buildChecks, checkKey, compactIban, type Check } from './iban-model';
import { InvoiceCard } from './invoice-card';
import { Balance, Detail, GroupView, List, PanelFrame, Row } from './pieces';
import { FIRST, urgentFirst } from './panel-model';
import { weekRanges, type Week } from './weeks';

/** "2 bloqueadas" si hay alguna bloqueada; si no, "3 urgentes" (con su singular). */
function countLabel(h: Messages['aurora']['home'], blocked: number, all: number): string {
  if (blocked > 0) return blocked === 1 ? h.blockedCountOne : fmt(h.blockedCount, { n: blocked });
  return all === 1 ? h.urgentCountOne : fmt(h.urgentCount, { n: all });
}

export type HomeView = 'first' | 'queue' | 'exceptions' | 'iban' | 'cashflow';
type Card = { kind: 'invoice'; id: number } | { kind: 'exception'; id: number } | { kind: 'iban'; key: string } | { kind: 'inherited' } | null;

interface WeekFlow extends Week {
  in: number | null;
  out: number | null;
  net: number | null;
}

interface HomeData {
  invoices: InvoiceRow[];
  exceptions: ExceptionRow[];
  people: Person[];
  clients: Map<number, string>;
  orders: Map<number, { numero: string; parte: string | null }>;
  accounts: AccountRow[];
  weeks: WeekFlow[];
  estimate: CashFlow['estimado'] | null;
}

function useHomeData() {
  const { session } = useSession();
  const { version } = useRefresh();
  return useLoad<HomeData>(async () => {
    const api = session!.api;
    const [invoices, exceptions, people, clients, orders, accounts, flow] = await Promise.all([
      api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas),
      api.get<{ excepciones: ExceptionRow[] }>(paths.exceptions).then((r) => r.excepciones),
      api.get<{ personas: Person[] }>(paths.people).then((r) => r.personas),
      api.get<{ clientes: { id: number; nombre: string }[] }>(paths.clients).then((r) => r.clientes),
      api.get<{ ordenes: PoRow[] }>(paths.purchaseOrders).then((r) => r.ordenes),
      api.get<{ cuentas: AccountRow[] }>(paths.accounts).then((r) => r.cuentas),
      api.get<{ flujo_caja: CashFlow }>(paths.cashFlow).then((r) => r.flujo_caja),
    ]);
    // Las cuatro semanas, cada una con lo que dice el motor de ese periodo (desde y hasta).
    const weeks = await Promise.all(
      weekRanges(flow.hoy).map((w) =>
        api
          .get<{
            flujo_caja: CashFlow;
          }>(paths.cashFlow, { desde: w.from, hasta: w.to })
          .then((r) => ({
            ...w,
            in: r.flujo_caja.esperado.entrada.periodo ?? null,
            out: r.flujo_caja.esperado.salida.periodo ?? null,
            net: r.flujo_caja.esperado.neto.periodo ?? null,
          }))
      )
    );
    return {
      invoices,
      exceptions,
      people,
      clients: new Map(clients.map((c) => [c.id, c.nombre])),
      orders: new Map(orders.map((o) => [o.id, { numero: o.numero, parte: o.parte.nombre }])),
      accounts,
      weeks,
      estimate: flow.estimado.importe_cent === null ? null : flow.estimado,
    };
  }, [session, version]);
}

/** De que va una excepcion: su factura (numero y relacion), o el cliente, la PO, la import. */
export function concerns(
  r: ExceptionRow,
  data: Pick<HomeData, 'invoices' | 'clients' | 'orders'>,
  twins: ReadonlyMap<number, TwinMark>,
  t: Messages,
  lang: Lang
): string {
  if (r.factura_id) {
    const f = data.invoices.find((x) => x.id === r.factura_id);
    const twin = twins.get(r.factura_id);
    return [
      f?.numero ?? fmt(t.records.invoice.fallbackTitle, { id: r.factura_id }),
      twin ? fmt(t.common.twin, { n: twin.n, of: twin.of }) : null,
      f?.contraparte ?? null,
    ]
      .filter(Boolean)
      .join(' · ');
  }
  const entity = stateLabel(lang, 'entidad', r.tabla) ?? null;
  if (r.tabla === 'cliente') return [data.clients.get(r.fila_id) ?? `#${r.fila_id}`, entity].filter(Boolean).join(' · ');
  if (r.tabla === 'orden_compra') {
    const po = data.orders.get(r.fila_id);
    return [po?.numero ?? `#${r.fila_id}`, po?.parte ?? entity].filter(Boolean).join(' · ');
  }
  if (r.tabla === 'importacion') return fmt(t.exceptions.importNumber, { id: r.fila_id });
  return `${entity ?? r.tabla} #${r.fila_id}`;
}

/** El asunto de una excepcion: el titulo de su aviso mas urgente o lo que tecleo quien la abrio. */
export function exceptionSubject(row: ExceptionRow, lang: Lang, t: Messages): string {
  const why = whyOf(row, lang, t);
  return why ? (why.title ?? why.text) : row.titulo;
}

/** Una factura en una fila: la empresa, el numero (y su "1 de 2"), el importe y la prioridad. */
function InvoiceRowItem({ row, twin, count, onOpen, current }: { row: InvoiceRow; twin?: TwinMark; count?: number; onOpen: () => void; current: boolean }) {
  const { t, lang } = useT();
  const note = [
    row.numero ?? fmt(t.records.invoice.fallbackTitle, { id: row.id }),
    twin ? fmt(t.common.twin, { n: twin.n, of: twin.of }) : null,
    count && count > 1 ? fmt(t.overview.nextUp.sameNumber, { n: count }) : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <Row
      label={row.contraparte ?? '—'}
      data
      note={note}
      noteData
      figure={formatMoney(row.total_cent)}
      state={priorityLabel(lang, row.nivel) ?? row.nivel}
      tone={row.nivel === 'bloqueada' ? 'blocked' : ''}
      current={current}
      ariaLabel={fmt(t.common.openRecord, {
        what: `${t.records.invoice.label} ${row.numero ?? row.id}`,
      })}
      onOpen={onOpen}
    />
  );
}

export function HomePanel({ view }: { view: string | null }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const can = useCan();
  const { dispatch } = useAurora();
  const [state] = useHomeData();
  const [card, setCard] = useState<Card>(null);
  const h = t.aurora.home;
  const data = state.status === 'ready' ? state.data : null;

  const setView = (next: string | null) => {
    setCard(null);
    dispatch({ type: 'panelView', view: next });
  };
  const onEscape = () => {
    if (card) setCard(null);
    else if (view) setView(null);
    else dispatch({ type: 'closePanel' });
  };
  const back = {
    backLabel: fmt(t.aurora.panel.backTo, { what: t.areas.home.label }),
    onBack: () => setView(null),
  };

  let body: ReactNode = null;
  if (data) {
    const queue = data.invoices.filter(needsPerson);
    const twins = twinMarks(data.invoices);
    const first = distinctByNumber(urgentFirst(data.invoices)).slice(0, FIRST);
    const blocked = queue.filter((f) => f.nivel === 'bloqueada').length;
    const urgent = queue.filter((f) => f.nivel === 'urgente').length;
    const checks = buildChecks(data.invoices, data.accounts).filter((c) => accountStep(c) === 'confirm');
    const inherited = data.accounts.filter((a) => a.estado === 'heredada');
    const net = data.weeks.reduce<number | null>((n, w) => (w.net === null || n === null ? null : n + w.net), 0);
    const invoiceItem = (r: InvoiceRow, count?: number) => (
      <InvoiceRowItem
        key={r.id}
        row={r}
        twin={twins.get(r.id)}
        count={count}
        current={card?.kind === 'invoice' && card.id === r.id}
        onOpen={() => setCard({ kind: 'invoice', id: r.id })}
      />
    );
    if (view === 'first') {
      body = (
        <GroupView
          items={first}
          title={h.first.toUpperCase()}
          match={(x) => `${x.row.numero} ${x.row.contraparte}`}
          render={(x) => invoiceItem(x.row, x.count)}
          {...back}
        />
      );
    } else if (view === 'queue') {
      body = (
        <GroupView
          items={queue}
          title={t.nav['work-queue'].label.toUpperCase()}
          match={(r) => `${r.numero} ${r.contraparte}`}
          render={(r) => invoiceItem(r)}
          {...back}
        />
      );
    } else if (view === 'exceptions') {
      body = (
        <GroupView
          items={data.exceptions}
          title={t.nav.exceptions.label.toUpperCase()}
          match={(r) => `${exceptionSubject(r, lang, t)} ${concerns(r, data, twins, t, lang)}`}
          render={(r) => (
            <Row
              key={r.id}
              label={exceptionSubject(r, lang, t)}
              note={concerns(r, data, twins, t, lang)}
              noteData
              figure={r.importe_cent === null ? undefined : formatMoney(r.importe_cent)}
              state={exceptionState(r, t, lang)}
              ariaLabel={fmt(t.exceptions.openLabel, { id: r.id })}
              current={card?.kind === 'exception' && card.id === r.id}
              onOpen={() => setCard({ kind: 'exception', id: r.id })}
            />
          )}
          {...back}
        />
      );
    } else if (view === 'iban') {
      type Item = { kind: 'check'; check: Check } | { kind: 'inherited' };
      const items: Item[] = [...checks.map((check) => ({ kind: 'check' as const, check })), ...(inherited.length ? [{ kind: 'inherited' as const }] : [])];
      body = (
        <GroupView
          items={items}
          title={h.iban.toUpperCase()}
          match={(x) => (x.kind === 'check' ? `${x.check.provider} ${x.check.iban}` : t.iban.inheritedTitle)}
          render={(x) =>
            x.kind === 'check' ? (
              <Row
                key={checkKey(x.check)}
                label={x.check.provider ?? '—'}
                data
                note={formatWith('iban', x.check.iban, templateCatalog(lang))}
                noteData
                state={x.check.account ? (stateLabel(lang, 'cuenta', x.check.account.estado) ?? x.check.account.estado) : t.status.ibanControl.por_verificar}
                current={card?.kind === 'iban' && card.key === checkKey(x.check)}
                onOpen={() => setCard({ kind: 'iban', key: checkKey(x.check) })}
              />
            ) : (
              <Row
                key='inherited'
                label={t.iban.inheritedTitle}
                note={fmt(inherited.length === 1 ? t.iban.inheritedTextOne : t.iban.inheritedText, { n: inherited.length })}
                figure={String(inherited.length)}
                current={card?.kind === 'inherited'}
                onOpen={() => setCard({ kind: 'inherited' })}
              />
            )
          }
          {...back}
        />
      );
    } else if (view === 'cashflow') {
      const estimate = data.estimate;
      body = (
        <GroupView
          items={data.weeks}
          title={t.nav['cash-flow'].label.toUpperCase()}
          match={(w) => fmt(h.week, { n: w.number })}
          render={(w) => (
            <Row
              key={w.from}
              label={fmt(h.week, { n: w.number })}
              note={`${fmt(t.cash.range, { from: formatDate(w.from), to: formatDate(w.to) })} · ${t.cash.moneyIn} ${formatMoney(w.in)} · ${t.cash.moneyOut} ${formatMoney(w.out)}`}
              figure={formatMoney(w.net)}
              state={h.left}
              ariaLabel={fmt(h.weekOpen, { n: w.number })}
              onOpen={() =>
                dispatch({
                  type: 'enterSearch',
                  index: entryIndex('search'),
                  preset: {
                    pendiente: 'si',
                    vence_desde: w.from,
                    vence_hasta: w.to,
                  },
                })
              }
            />
          )}
          after={
            <p className='empty' data-testid='cash-estimate'>
              {estimate
                ? `${t.cash.estimateBadge}: ${formatMoney(estimate.importe_cent)}${estimate.aproximado ? ` · ${t.cash.approximate}` : ''}`
                : t.cash.noEstimate}
            </p>
          }
          {...back}
        />
      );
    } else {
      const groups = [
        first.length > 0 && (
          <Row
            key='first'
            label={h.first}
            note={h.firstNote}
            figure={String(first.length)}
            state={countLabel(h, first.filter((x) => x.row.nivel === 'bloqueada').length, first.length)}
            tone={first.some((x) => x.row.nivel === 'bloqueada') ? 'blocked' : ''}
            onOpen={() => setView('first')}
          />
        ),
        queue.length > 0 && (
          <Row
            key='queue'
            label={t.nav['work-queue'].label}
            note={h.queueNote}
            figure={String(queue.length)}
            state={blocked > 0 ? (blocked === 1 ? h.blockedCountOne : fmt(h.blockedCount, { n: blocked })) : undefined}
            tone={blocked > 0 ? 'blocked' : ''}
            onOpen={() => setView('queue')}
          />
        ),
        data.exceptions.length > 0 && (
          <Row
            key='exceptions'
            label={t.nav.exceptions.label}
            note={h.exceptionsNote}
            figure={String(data.exceptions.length)}
            state={t.badges.open}
            onOpen={() => setView('exceptions')}
          />
        ),
        (checks.length > 0 || inherited.length > 0) && (
          <Row
            key='iban'
            label={h.iban}
            note={h.ibanNote}
            figure={String(checks.length + inherited.length)}
            state={t.badges.toCheck}
            onOpen={() => setView('iban')}
          />
        ),
        data.weeks.length > 0 && (
          <Row key='cashflow' label={t.nav['cash-flow'].label} note={h.cashNote} figure={formatMoney(net)} state={h.left} onOpen={() => setView('cashflow')} />
        ),
      ].filter(Boolean);
      body = (
        <>
          <Balance
            label={h.attention}
            figure={String(queue.length)}
            share={queue.length ? (blocked + urgent) / queue.length : 0}
            note={`${blocked === 1 ? h.blockedCountOne : fmt(h.blockedCount, { n: blocked })} · ${urgent === 1 ? h.urgentCountOne : fmt(h.urgentCount, { n: urgent })}`}
          />
          <List title={h.listTitle} count={groups.length}>
            {groups}
          </List>
        </>
      );
    }
    // La tarjeta, al final del panel (main.tsx:38).
    if (card?.kind === 'invoice') body = [body, <InvoiceCard key='card' id={card.id} onClose={() => setCard(null)} />];
    if (card?.kind === 'exception') {
      const row = data.exceptions.find((e) => e.id === card.id);
      if (row) {
        body = [
          body,
          <ExceptionCard
            key='card'
            row={row}
            subject={exceptionSubject(row, lang, t)}
            concerns={concerns(row, data, twins, t, lang)}
            invoice={data.invoices.find((f) => f.id === row.factura_id) ?? null}
            orders={can('resolver_aviso') ? exceptionOrders(t, lang, row, data.people, session?.me.id) : []}
            onClose={() => setCard(null)}
          />,
        ];
      }
    }
    if (card?.kind === 'iban') {
      const check = buildChecks(data.invoices, data.accounts).find((c) => checkKey(c) === card.key);
      if (check) body = [body, <IbanCard key={card.key} check={check} onClose={() => setCard(null)} />];
    }
    if (card?.kind === 'inherited' && inherited.length) body = [body, <InheritedCard key='inherited' n={inherited.length} onClose={() => setCard(null)} />];
  }

  const titles: Record<HomeView, string> = {
    first: h.first,
    queue: t.nav['work-queue'].label,
    exceptions: t.nav.exceptions.label,
    iban: h.iban,
    cashflow: t.nav['cash-flow'].label,
  };
  const descriptions: Record<HomeView, string> = {
    first: t.home.firstIntro,
    // La de su fila: en una linea, para que la vista no se desplace mas que la de Aurora (§6.1).
    queue: h.queueNote,
    exceptions: h.exceptionsNote,
    iban: t.iban.rule,
    cashflow: t.cash.note,
  };
  const known = view && view in titles ? (view as HomeView) : null;
  return (
    <PanelFrame
      title={known ? titles[known] : t.areas.home.label}
      description={known ? descriptions[known] : t.aurora.panel.descriptions.home}
      view={view}
      onEscape={onEscape}
    >
      {state.status === 'error' && <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} />}
      {body}
    </PanelFrame>
  );
}

function ExceptionCard({
  row,
  subject,
  concerns: about,
  invoice,
  orders,
  onClose,
}: {
  row: ExceptionRow;
  subject: string;
  concerns: string;
  invoice: InvoiceRow | null;
  orders: OrderSpec[];
  onClose: () => void;
}) {
  const { t, lang } = useT();
  const openInvoice = useOpenInvoice();
  return (
    <Detail title={subject} onClose={onClose}>
      <p>
        <span data-proper-name=''>{about}</span>
      </p>
      {row.razones.length ? (
        row.razones.slice(0, 3).map((r) => (
          <p key={r.id}>
            {ruleText(lang, r.regla)?.title ?? r.regla}: {findingDetail(lang, r.regla, r.resultado, r.valores)}
          </p>
        ))
      ) : (
        <p>
          <span data-proper-name=''>{row.titulo}</span>
        </p>
      )}
      <ExceptionLines exception={row} />
      <Orders
        orders={orders}
        before={
          row.factura_id ? (
            <button
              type='button'
              className='outline'
              onClick={() =>
                openInvoice({
                  id: row.factura_id!,
                  sentido: invoice?.sentido,
                  cliente_id: invoice?.cliente_id,
                  proveedor_id: invoice?.proveedor_id,
                })
              }
            >
              {t.exceptions.openInvoice}
            </button>
          ) : undefined
        }
      />
    </Detail>
  );
}

/** La tarjeta de una cuenta por comprobar: lo que se vio, el telefono del maestro y lo que
 *  falta; confirmar por telefono (los tres pasos, el IBAN tecleado: nunca copiado de la
 *  factura) o rechazar. */
function IbanCard({ check: c, onClose }: { check: Check; onClose: () => void }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const can = useCan();
  const openInvoice = useOpenInvoice();
  const [state] = useLoad(
    () => session!.api.get<{ proveedor: ProviderAccounts }>(paths.provider(c.providerId)).then((r) => r.proveedor),
    [session, c.providerId]
  );
  const provider = state.status === 'ready' ? state.data : null;
  const shown = formatWith('iban', c.iban, templateCatalog(lang));
  const phone = provider?.telefono_verificacion ?? null;
  const invoice = c.findings[0]?.invoice ?? null;
  const seen = new Set<string>();
  const findings = c.findings.filter((f) => !seen.has(f.reason.regla) && seen.add(f.reason.regla));
  const step = accountStep(c);
  const orders: OrderSpec[] = [];
  if (can('confirmar_iban') && state.status === 'ready') {
    if (phone && step === 'confirm') {
      orders.push({
        action: 'verificar_iban',
        label: t.iban.verify,
        primary: true,
        intro: (
          <>
            <p>1. {fmt(t.iban.step1, { phone })}</p>
            <p>2. {t.iban.step2}</p>
            <p>3. {t.iban.step3}</p>
          </>
        ),
        fields: [
          {
            name: 'iban',
            label: t.iban.typedIban,
            kind: 'iban',
            required: true,
            help: t.iban.typedIbanHelp,
          },
          {
            name: 'telefono',
            label: t.iban.phoneCalled,
            kind: 'tel',
            required: true,
            initial: phone,
            help: t.iban.phoneCalledHelp,
          },
          {
            name: 'persona_contactada',
            label: t.iban.spokeTo,
            kind: 'text',
            required: true,
          },
          {
            name: 'motivo',
            label: t.action.note,
            kind: 'text',
            required: true,
            help: t.iban.noteHelp,
          },
        ],
        preview: (v) => <TypedMatch typed={v.iban ?? ''} seen={c.iban} />,
        data: (v) => ({
          proveedor_id: c.providerId,
          iban: compactIban(v.iban ?? ''),
          telefono: v.telefono,
          persona_contactada: v.persona_contactada,
          factura_id: invoice?.id ?? null,
          metodo: 'llamada',
          motivo: v.motivo,
        }),
      });
    }
    orders.push({
      action: 'rechazar_iban',
      label: t.iban.reject,
      intro: <p>{fmt(t.iban.rejectIntro, { iban: shown })}</p>,
      fields: [
        ...(invoice
          ? [
              {
                name: 'decision_facturas',
                label: fmt(t.iban.invoiceDecision, {
                  number: invoice.numero ?? `#${invoice.id}`,
                }),
                kind: 'select' as const,
                initial: '',
                options: [
                  { value: '', label: t.iban.decideLater },
                  {
                    value: 'pagar_a_verificada',
                    label: stateLabel(lang, 'decision_facturas', 'pagar_a_verificada') ?? '',
                  },
                  {
                    value: 'anular',
                    label: stateLabel(lang, 'decision_facturas', 'anular') ?? '',
                  },
                ],
              },
            ]
          : []),
        {
          name: 'motivo',
          label: t.action.reason,
          kind: 'text',
          required: true,
        },
      ],
      data: (v) => ({
        proveedor_id: c.providerId,
        iban: c.iban,
        factura_id: invoice?.id ?? null,
        decision_facturas: v.decision_facturas || null,
        motivo: v.motivo,
      }),
    });
  }
  return (
    <Detail title={provider?.nombre ?? c.provider ?? '—'} onClose={onClose} titleData>
      <p>
        {t.iban.found}: <span data-proper-name=''>{shown}</span>
        {step === 'confirm' && ` · ${t.iban.notCorrectYet}`}
      </p>
      {step !== 'confirm' && <p data-testid='iban-step'>{step === 'exact' ? t.iban.stepExact : step === 'open' ? t.iban.stepOpen : t.iban.stepRejected}</p>}
      {invoice && (
        <p>
          {t.iban.where}: <span data-proper-name=''>{invoice.numero ?? `#${invoice.id}`}</span>
          {invoice.fecha_factura ? ` · ${formatDate(invoice.fecha_factura)}` : ''}
        </p>
      )}
      {findings.length ? (
        findings.map(({ reason: r }) => (
          <p key={r.id}>
            {ruleText(lang, r.regla)?.title ?? r.regla}: {findingDetail(lang, r.regla, r.resultado, r.valores)}
          </p>
        ))
      ) : (
        <p>{t.iban.registeredNotVerified}</p>
      )}
      <p>
        {t.iban.phoneOnFile}: {phone ? <span data-proper-name=''>{phone}</span> : `${t.status.ibanControl.sin_telefono} · ${t.iban.noPhoneHelp}`}
      </p>
      <span>{c.account ? (stateLabel(lang, 'cuenta', c.account.estado) ?? c.account.estado) : t.status.ibanControl.por_verificar}</span>
      <Orders
        orders={orders}
        before={
          invoice ? (
            <button
              type='button'
              className='outline'
              onClick={() =>
                openInvoice({
                  id: invoice.id,
                  sentido: invoice.sentido,
                  cliente_id: invoice.cliente_id,
                  proveedor_id: invoice.proveedor_id,
                })
              }
            >
              {t.exceptions.openInvoice}
            </button>
          ) : undefined
        }
      />
    </Detail>
  );
}

/** Lo tecleado contra lo visto: el IBAN se escribe tal como lo dice el proveedor. */
function TypedMatch({ typed, seen }: { typed: string; seen: string }) {
  const { t } = useT();
  const value = compactIban(typed);
  if (value.length < 8) return null;
  return value === seen ? (
    <p role='status'>{t.status.ibanTyped.coincide}</p>
  ) : (
    <p role='status'>
      {t.status.ibanTyped.difiere}. {t.iban.differsHelp}
    </p>
  );
}

function InheritedCard({ n, onClose }: { n: number; onClose: () => void }) {
  const { t } = useT();
  const can = useCan();
  return (
    <Detail title={t.iban.inheritedTitle} onClose={onClose}>
      <p>{fmt(n === 1 ? t.iban.inheritedTextOne : t.iban.inheritedText, { n })}</p>
      <Orders
        orders={
          can('confirmar_iban')
            ? [
                {
                  action: 'atestar_iban',
                  label: t.iban.confirmInherited,
                  primary: true,
                  intro: <p>{t.iban.confirmInheritedIntro}</p>,
                  fields: [
                    {
                      name: 'motivo',
                      label: t.action.reason,
                      kind: 'text',
                      required: true,
                    },
                  ],
                  data: (v) => ({ motivo: v.motivo }),
                },
              ]
            : []
        }
      />
    </Detail>
  );
}
