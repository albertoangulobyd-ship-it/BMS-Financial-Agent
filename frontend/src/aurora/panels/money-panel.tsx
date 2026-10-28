// E2-C y E2-P, los paneles de Cuentas por cobrar y por pagar (especificacion §2.2.2 y §2.2.3),
// con la cartera del motor (GET /api/v2/cartera, la misma funcion que el panel: dicen los mismos
// centimos). En reposo, la cifra principal ("Total pendiente"; la barra, la parte vencida de
// verdad, que en Aurora era fija al 68 %) y una fila por grupo:
// - cobrar: Por confirmar, Sin casar, Vencidas (la busqueda con sus filtros, E5-p), Antiguedad y
//   "+ Importar un extracto o una exportacion" (importar, §2.2.6);
// - pagar: Por confirmar, Sin casar, Esta semana, Con objeciones o bloqueadas y Antiguedad.
// Cada grupo abre su vista y cada fila su tarjeta .detail con sus ordenes: confirmar o retirar un
// pago propuesto, enlazar una linea del banco a su factura, anotar un pago (la tarjeta de una
// factura, §2.2.7). Cada tramo de la antiguedad abre la busqueda de sus facturas (E5-p). Las
// empresas viven en Documentos (§2.3). Nunca se dice "aprobado" ni se prepara un fichero de pago.
import { Plus } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { countText, fmt, useT } from '@/i18n';
import { ruleText } from '@/i18n/domain';
import { paths, type InvoiceRow } from '@/lib/api';
import type { AgeingBucket, BankLine, BankLines, Cartera, CarteraInvoice, PaymentProposal } from '@/lib/api-types';
import { formatDate, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { twinMarks } from '@/lib/twins';
import { SIGN_OF, inCartera, proposalsOf, type BucketKey, type Side } from './money-model';
import { useLoad } from '../use-load';
import { dueLabel } from '../due';
import { entryIndex, type SearchPreset } from '../estado';
import { useOpenInvoice } from '../navigation';
import { Orders, apiErrorMessage, ErrorLine, type OrderSpec } from '../orders';
import { useAurora } from '../root';
import { ImportView } from './import-panel';
import { InvoiceCard } from './invoice-card';
import { Balance, Detail, GroupView, List, PanelFrame, Row } from './pieces';
import { ProposalLines, confirmProposalOrder, linkLineOrder, withdrawOrder } from './payment-orders';

/** De donde se vuelve con "Volver a …" o Escape. */
function parentOfMoneyView(view: string): string | null {
  if (view === 'nodue') return 'ageing';
  if (view === 'import-sources' || view === 'import-history') return 'import';
  return null;
}

const BUCKET_ORDER: readonly BucketKey[] = ['al_corriente', '1_30', '31_60', '61_90', 'mas_de_90'];

/** La busqueda de las facturas de un tramo (E5-p): sus limites de vencimiento, pendientes. */
function bucketPreset(side: Side, b: Pick<AgeingBucket, 'vence_desde' | 'vence_hasta'>): SearchPreset {
  const out: Record<string, string> = { sentido: side, pendiente: 'si' };
  if (b.vence_desde) out.vence_desde = b.vence_desde;
  if (b.vence_hasta) out.vence_hasta = b.vence_hasta;
  return out;
}

/** El tramo mas alto (el mas atrasado) con algo pendiente. */
function worstBucket(buckets: readonly AgeingBucket[]): AgeingBucket | null {
  for (const key of [...BUCKET_ORDER].reverse()) {
    const b = buckets.find((x) => x.clave === key);
    if (b && b.facturas > 0) return b;
  }
  return null;
}

type Card = { kind: 'invoice'; id: number } | { kind: 'proposal'; id: number } | { kind: 'line'; id: number } | null;

interface MoneyData {
  cartera: Cartera;
  proposals: PaymentProposal[];
  invoices: InvoiceRow[];
}

function useMoneyData(side: Side) {
  const { session } = useSession();
  const { version } = useRefresh();
  return useLoad<MoneyData>(
    () =>
      Promise.all([
        session!.api.get<{ cartera: Cartera }>(paths.cartera, { sentido: side }).then((r) => r.cartera),
        session!.api
          .get<{
            propuestas: PaymentProposal[];
          }>(paths.proposals, { sentido: side })
          .then((r) => proposalsOf(r.propuestas, side)),
        session!.api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas),
      ]).then(([cartera, proposals, invoices]) => ({
        cartera,
        proposals,
        invoices,
      })),
    [session, version, side]
  );
}

/** Las lineas del banco sin casar de un lado; con lo escrito en .search, del servidor (texto). */
function useBankLines(side: Side, active: boolean, text: string) {
  const { session } = useSession();
  const { version } = useRefresh();
  const [lines, setLines] = useState<BankLines | null>(null);
  useEffect(() => {
    if (!active || !session) return;
    let alive = true;
    session.api
      .get<{ movimientos: BankLines }>(paths.bankLines, {
        signo: SIGN_OF[side],
        texto: text || undefined,
      })
      .then((r) => alive && setLines(r.movimientos))
      .catch(() => alive && setLines(null));
    return () => {
      alive = false;
    };
  }, [active, session, side, text, version]);
  return lines;
}

/** Una factura de la cartera en una fila: la empresa, el numero (y por que esta retenida), lo
 *  que queda y cuando vence. */
function CarteraRow({ row, twin, current, onOpen }: { row: CarteraInvoice; twin?: { n: number; of: number }; current: boolean; onOpen: () => void }) {
  const { t, lang } = useT();
  const reason = row.retenida ? row.razones[0] : undefined;
  const mark = twin ? fmt(t.common.twin, { n: twin.n, of: twin.of }) : null;
  return (
    <Row
      label={row.parte ?? '—'}
      data
      note={[row.numero ?? '—', mark, reason ? (ruleText(lang, reason.regla)?.title ?? reason.regla) : null].filter(Boolean).join(' · ')}
      noteData
      figure={formatMoney(row.pendiente_cent)}
      state={dueLabel(t, row.vencimiento, null, row.dias) ?? undefined}
      tone={row.retenida ? 'blocked' : ''}
      current={current}
      ariaLabel={fmt(t.common.openRecord, {
        what: `${t.records.invoice.label} ${row.numero ?? row.id}${mark ? ` (${mark})` : ''}`,
      })}
      onOpen={onOpen}
    />
  );
}

export function MoneyPanel({ side, view }: { side: Side; view: string | null }) {
  const { t, lang } = useT();
  const can = useCan();
  const { dispatch } = useAurora();
  const [state] = useMoneyData(side);
  const [card, setCard] = useState<Card>(null);
  const [lineQuery, setLineQuery] = useState('');
  const lines = useBankLines(side, view === 'unmatched' || view === null, view === 'unmatched' ? lineQuery : '');
  const m = t.aurora.money;
  const area = side === 'saliente' ? t.areas.receivables : t.areas.payables;
  const data = state.status === 'ready' ? state.data : null;

  const setView = (next: string | null) => {
    setCard(null);
    dispatch({ type: 'panelView', view: next });
  };
  const onEscape = () => {
    if (card) setCard(null);
    else if (view) setView(parentOfMoneyView(view));
    else dispatch({ type: 'closePanel' });
  };
  const backTo = (to: string | null, what: string) => ({
    backLabel: fmt(t.aurora.panel.backTo, { what }),
    onBack: () => setView(to),
  });
  const back = backTo(null, area.label);
  const search = (preset: SearchPreset) => dispatch({ type: 'enterSearch', index: entryIndex('search'), preset });

  let body: ReactNode = null;
  let title = area.label;
  let description = side === 'saliente' ? t.aurora.panel.descriptions.receivables : t.aurora.panel.descriptions.payables;

  if (data) {
    const c = data.cartera;
    const totals = c.totales;
    const week = c.esta_semana;
    const held = c.retenido.lista ?? [];
    const noDue = data.invoices.filter((f) => inCartera(f, side) && !f.vencimiento);
    const twins = twinMarks(
      [...(week?.facturas ?? []), ...held].map((f) => ({
        id: f.id,
        numero: f.numero,
        contraparte: f.parte,
      }))
    );
    const carteraRow = (f: CarteraInvoice) => (
      <CarteraRow
        key={f.id}
        row={f}
        twin={twins.get(f.id)}
        current={card?.kind === 'invoice' && card.id === f.id}
        onOpen={() => setCard({ kind: 'invoice', id: f.id })}
      />
    );
    if (view === 'proposals') {
      title = m.proposals;
      description = t.bank.proposalsIntro;
      const ptwins = twinMarks([
        ...new Map(
          data.proposals.map((p) => [
            p.factura.id,
            {
              id: p.factura.id,
              numero: p.factura.numero,
              contraparte: p.factura.parte ?? p.factura.contraparte,
            },
          ])
        ).values(),
      ]);
      body = (
        <GroupView
          items={data.proposals}
          title={m.proposals.toUpperCase()}
          match={(p) => `${p.factura.numero} ${p.factura.parte} ${p.movimiento?.contraparte} ${p.movimiento?.concepto}`}
          render={(p) => {
            const twin = ptwins.get(p.factura.id);
            const number = `${p.factura.numero ?? p.factura.id}${twin ? ` (${fmt(t.common.twin, { n: twin.n, of: twin.of })})` : ''}`;
            return (
              <Row
                key={p.id}
                label={p.factura.parte ?? p.factura.contraparte ?? '—'}
                data
                note={number}
                noteData
                figure={formatMoney(p.importe_cent)}
                state={formatDate(p.movimiento?.fecha ?? p.fecha_pago)}
                ariaLabel={`${number} · ${formatMoney(p.importe_cent)}`}
                current={card?.kind === 'proposal' && card.id === p.id}
                onOpen={() => setCard({ kind: 'proposal', id: p.id })}
              />
            );
          }}
          {...back}
        />
      );
    } else if (view === 'unmatched') {
      title = m.unmatched;
      description = side === 'saliente' ? t.bank.unmatchedIntroIn : t.bank.unmatchedIntroOut;
      const list = (lines?.lista ?? []).filter((l) => l.importe_cent !== null);
      body = (
        <GroupView
          items={list}
          total={lines?.total ?? list.length}
          searchable
          onServerQuery={setLineQuery}
          title={m.unmatched.toUpperCase()}
          match={(l) => `${l.contraparte} ${l.concepto}`}
          render={(l) => (
            <Row
              key={l.id}
              label={l.contraparte ?? '—'}
              data
              note={[formatDate(l.fecha), l.concepto].filter(Boolean).join(' · ')}
              noteData
              figure={formatMoney(l.resto_cent ?? l.importe_cent)}
              state={l.dias === 0 ? t.bank.ageToday : countText(t, 'days', l.dias)}
              ariaLabel={fmt(t.bank.linkLabel, {
                date: formatDate(l.fecha),
                amount: formatMoney(l.resto_cent ?? l.importe_cent),
              })}
              current={card?.kind === 'line' && card.id === l.id}
              onOpen={() => setCard({ kind: 'line', id: l.id })}
            />
          )}
          {...back}
        />
      );
    } else if (view === 'ageing' || view === 'nodue') {
      if (view === 'nodue') {
        title = t.money.ageing.buckets.sin_fecha;
        description = m.noDueText;
        body = (
          <GroupView
            items={noDue}
            title={t.money.ageing.buckets.sin_fecha.toUpperCase()}
            match={(f) => `${f.numero} ${f.contraparte}`}
            render={(f) => (
              <Row
                key={f.id}
                label={f.contraparte ?? '—'}
                data
                note={f.numero ?? '—'}
                noteData
                figure={formatMoney(f.pendiente_cent)}
                state={t.money.due.none}
                current={card?.kind === 'invoice' && card.id === f.id}
                onOpen={() => setCard({ kind: 'invoice', id: f.id })}
              />
            )}
            {...backTo('ageing', t.money.ageing.title)}
          />
        );
      } else {
        title = t.money.ageing.title;
        description = m.ageingText;
        const buckets = BUCKET_ORDER.map((k) => c.tramos.find((b) => b.clave === k)).filter((b): b is AgeingBucket => Boolean(b));
        const sinFecha = c.tramos.find((b) => b.clave === 'sin_fecha' && b.facturas > 0);
        type Item = { key: BucketKey; bucket: AgeingBucket };
        const items: Item[] = [...buckets, ...(sinFecha ? [sinFecha] : [])].map((bucket) => ({ key: bucket.clave, bucket }));
        body = (
          <>
            <List title={t.money.ageing.title.toUpperCase()} count={totals.facturas}>
              {items.map(({ key, bucket }) => (
                <Row
                  key={key}
                  label={t.money.ageing.buckets[key]}
                  note={fmt(bucket.facturas === 1 ? t.money.ageing.countOne : t.money.ageing.count, { n: bucket.facturas })}
                  figure={formatMoney(bucket.importe_cent)}
                  ariaLabel={`${fmt(t.money.ageing.show, { bucket: t.money.ageing.buckets[key] })} (${formatMoney(bucket.importe_cent)})`}
                  onOpen={() => (key === 'sin_fecha' ? setView('nodue') : search(bucketPreset(side, bucket)))}
                />
              ))}
            </List>
            <button className='outline' onClick={() => setView(null)}>
              {fmt(t.aurora.panel.backTo, { what: area.label })}
            </button>
          </>
        );
      }
    } else if (view === 'week' && week) {
      title = m.week;
      description = fmt(t.money.week.title, { date: formatDate(week.hasta) }) + ' · ' + t.money.week.intro;
      body = <GroupView items={week.facturas} title={m.week.toUpperCase()} match={(f) => `${f.numero} ${f.parte}`} render={carteraRow} {...back} />;
    } else if (view === 'held') {
      title = t.money.week.held;
      description = m.heldText;
      body = <GroupView items={held} title={t.money.week.held.toUpperCase()} match={(f) => `${f.numero} ${f.parte}`} render={carteraRow} {...back} />;
    } else if (view === 'import' || view === 'import-sources' || view === 'import-history') {
      // Las dos vistas de importar llevan el nombre y la nota de su fila, como los demas grupos.
      title = view === 'import-sources' ? t.aurora.import.sources : view === 'import-history' ? t.importing.historyTitle : t.nav.import.label;
      description =
        view === 'import-sources' ? t.aurora.import.sourcesNote : view === 'import-history' ? t.aurora.import.historyNote : t.nav.import.description;
      body = <ImportView view={view} onView={setView} backLabel={fmt(t.aurora.panel.backTo, { what: area.label })} />;
    } else {
      const worst = worstBucket(c.tramos);
      const weekSum = week ? week.retenido.importe_cent + week.sin_retener.importe_cent : 0;
      const weekCount = week ? week.retenido.facturas + week.sin_retener.facturas : 0;
      const groups = [
        data.proposals.length > 0 && (
          <Row
            key='proposals'
            label={m.proposals}
            note={side === 'saliente' ? m.proposalsNoteIn : m.proposalsNoteOut}
            figure={String(data.proposals.length)}
            state={formatMoney(c.por_confirmar.importe_cent)}
            onOpen={() => setView('proposals')}
          />
        ),
        c.sin_casar.movimientos > 0 && (
          <Row
            key='unmatched'
            label={m.unmatched}
            note={side === 'saliente' ? m.unmatchedNoteIn : m.unmatchedNoteOut}
            figure={String(c.sin_casar.movimientos)}
            state={formatMoney(c.sin_casar.importe_cent)}
            onOpen={() => setView('unmatched')}
          />
        ),
        side === 'saliente' && totals.vencidas > 0 && (
          <Row
            key='overdue'
            label={m.overdue}
            note={m.overdueNote}
            figure={formatMoney(totals.vencido_cent)}
            state={fmt(totals.vencidas === 1 ? t.money.overdueInvoicesOne : t.money.overdueInvoices, { n: totals.vencidas })}
            onOpen={() =>
              search({
                sentido: 'saliente',
                vencida: 'si',
                orden: 'vencimiento',
              })
            }
          />
        ),
        side === 'entrante' && week && (
          <Row
            key='week'
            label={m.week}
            note={fmt(t.money.week.title, { date: formatDate(week.hasta) })}
            figure={formatMoney(weekSum)}
            state={fmt(weekCount === 1 ? t.money.ageing.countOne : t.money.ageing.count, { n: weekCount })}
            onOpen={() => setView('week')}
          />
        ),
        side === 'entrante' && held.length > 0 && (
          <Row
            key='held'
            label={t.money.week.held}
            note={m.heldNote}
            figure={formatMoney(c.retenido.importe_cent)}
            state={fmt(c.retenido.facturas === 1 ? t.money.ageing.countOne : t.money.ageing.count, { n: c.retenido.facturas })}
            tone='blocked'
            onOpen={() => setView('held')}
          />
        ),
        totals.facturas > 0 && (
          <Row
            key='ageing'
            label={t.money.ageing.title}
            note={m.ageingNote}
            figure={worst ? formatMoney(worst.importe_cent) : formatMoney(0)}
            state={worst ? t.money.ageing.buckets[worst.clave] : undefined}
            tone={worst && worst.clave !== 'al_corriente' ? '' : 'paid'}
            onOpen={() => setView('ageing')}
          />
        ),
      ].filter(Boolean);
      body = (
        <>
          <Balance
            label={m.total}
            figure={formatMoney(totals.pendiente_cent)}
            share={totals.pendiente_cent > 0 ? totals.vencido_cent / totals.pendiente_cent : 0}
            note={fmt(m.balanceNote, {
              amount: formatMoney(totals.vencido_cent),
              invoices: countText(t, 'invoices', totals.facturas),
            })}
          />
          <List title={m.listTitle} count={groups.length}>
            {groups}
          </List>
          {side === 'saliente' && can('importar_datos') && (
            <button className='outline' onClick={() => setView('import')}>
              <Plus size={15} /> {m.import}
            </button>
          )}
        </>
      );
    }
    if (card?.kind === 'invoice') body = [body, <InvoiceCard key='card' id={card.id} onClose={() => setCard(null)} />];
    if (card?.kind === 'proposal') {
      const p = data.proposals.find((x) => x.id === card.id);
      if (p) body = [body, <ProposalCard key='card' proposal={p} onClose={() => setCard(null)} />];
    }
    if (card?.kind === 'line') {
      const l = lines?.lista.find((x) => x.id === card.id);
      if (l) body = [body, <LineCard key='card' line={l} side={side} invoices={data.invoices} onClose={() => setCard(null)} />];
    }
  }

  return (
    <PanelFrame title={title} description={description} view={view} onEscape={onEscape}>
      {state.status === 'error' && <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} />}
      {body}
    </PanelFrame>
  );
}

/** Un pago que el banco propuso: la linea al lado de la factura, con las tres coincidencias;
 *  confirmar, decir que no es o abrir la factura. */
function ProposalCard({ proposal: p, onClose }: { proposal: PaymentProposal; onClose: () => void }) {
  const { t } = useT();
  const can = useCan();
  const openInvoice = useOpenInvoice();
  const orders: OrderSpec[] = can('marcar_pagada') ? [confirmProposalOrder(t, p), withdrawOrder(t, p, t.payments.withdraw)] : [];
  return (
    <Detail title={p.factura.numero ?? String(p.factura.id)} onClose={onClose} titleData>
      <ProposalLines proposal={p} />
      <span>{t.bank.proposalsTitle}</span>
      <Orders
        orders={orders}
        before={
          <button
            type='button'
            className='outline'
            onClick={() =>
              openInvoice({
                id: p.factura.id,
                sentido: p.factura.sentido,
                cliente_id: p.factura.cliente_id,
                proveedor_id: p.factura.proveedor_id,
              })
            }
          >
            {t.bank.openInvoice}
          </button>
        }
      />
    </Detail>
  );
}

/** Una linea del banco sin factura: lo que dice el banco y "Enlazar a una factura". */
function LineCard({ line: l, side, invoices, onClose }: { line: BankLine; side: Side; invoices: InvoiceRow[]; onClose: () => void }) {
  const { t } = useT();
  const can = useCan();
  const link = can('marcar_pagada') ? linkLineOrder(t, l, side, invoices) : null;
  return (
    <Detail title={`${formatDate(l.fecha)} · ${formatMoney(l.resto_cent ?? l.importe_cent)}`} onClose={onClose}>
      {l.contraparte && (
        <p>
          <span data-proper-name=''>{l.contraparte}</span>
          {l.contraparte_iban && (
            <>
              {' · '}
              <span data-proper-name=''>{l.contraparte_iban}</span>
            </>
          )}
        </p>
      )}
      {l.concepto && (
        <p>
          <span data-proper-name=''>{l.concepto}</span>
        </p>
      )}
      {l.referencia && (
        <p>
          <span data-proper-name=''>{l.referencia}</span>
        </p>
      )}
      <span>{l.dias === 0 ? t.bank.ageToday : countText(t, 'days', l.dias)}</span>
      <Orders orders={link ? [link] : []} />
    </Detail>
  );
}
