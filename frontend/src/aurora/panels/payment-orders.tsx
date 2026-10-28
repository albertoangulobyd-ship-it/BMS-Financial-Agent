// Las tres ordenes de pagos (paso 16; especificacion §2.3.1) como ordenes de una tarjeta
// (aurora/orders.tsx): confirmar lo que el banco propuso (confirmar_pago), decir que no es
// (retirar_pago, con motivo), apuntar un pago que ya se hizo (marcar_pagada, con motivo; su
// linea del banco y un justificante, si los hay) y enlazar una linea del banco a su factura
// (marcar_pagada con movimiento_id). Ninguna paga, aprueba un pago ni prepara un fichero de
// pagos: lo dicen sus frases. Cada orden lleva la rev que se vio. Las reglas de cada una son las
// del paso 16 (screens/payment-actions.tsx de antes): el motivo, la fecha que no es futura, el
// importe que no pasa de lo que queda, ninguna factura elegida sola al enlazar.
import { Check, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { countText, fmt, useT, type Messages } from '@/i18n';
import { paths, type InvoiceRow } from '@/lib/api';
import type { BankLine, BankLines, PartyDocuments, PaymentProposal } from '@/lib/api-types';
import { formatDate, formatMoney } from '@/lib/format';
import { useSession } from '@/lib/session';
import { twinMarks } from '@/lib/twins';
import { SIGN_OF, centsToApi, centsToInput, inCartera, linkCandidates, parseEuros, type Side } from './money-model';
import type { OrderSpec } from '../orders';

/** El dia de hoy en el ordenador (AAAA-MM-DD): un pago apuntado no puede ser de despues. */
export function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Referentie ✓, Bedrag ✓, Rekening ✗: en que coincidieron (en texto, no solo el icono). */
export function MatchLine({ proposal: p }: { proposal: Pick<PaymentProposal, 'coincidencias'> }) {
  const { t } = useT();
  const keys = ['referencia', 'importe', 'contraparte'] as const;
  return (
    <p aria-label={t.bank.matches} className='order-matches'>
      {keys.map((k) => {
        const ok = p.coincidencias[k];
        return (
          <span key={k}>
            {ok ? <Check size={11} aria-hidden='true' /> : <X size={11} aria-hidden='true' />} {t.bank.match[k]}: {ok ? t.bank.yes : t.bank.no}
          </span>
        );
      })}
    </p>
  );
}

/** La linea del banco y la factura de una propuesta, en lineas p de la tarjeta. */
export function ProposalLines({ proposal: p }: { proposal: PaymentProposal }) {
  const { t } = useT();
  const m = p.movimiento;
  return (
    <>
      <p>
        {t.bank.onBank}: {formatDate(m?.fecha ?? p.fecha_pago)} · {formatMoney(m?.importe_cent ?? p.importe_cent)}
        {m?.contraparte && (
          <>
            {' · '}
            <span data-proper-name=''>{m.contraparte}</span>
          </>
        )}
      </p>
      {m?.concepto && (
        <p>
          <span data-proper-name=''>{m.concepto}</span>
        </p>
      )}
      <p>
        {t.bank.invoice}: <span data-proper-name=''>{p.factura.numero ?? '—'}</span> · {formatMoney(p.factura.total_cent)} ·{' '}
        {fmt(t.bank.remaining, { amount: formatMoney(p.factura.pendiente_cent) })}
      </p>
      <MatchLine proposal={p} />
    </>
  );
}

/** Confirmar un pago propuesto: el motivo es opcional (es un clic sobre lo que ya se propuso). */
export function confirmProposalOrder(t: Messages, proposal: Pick<PaymentProposal, 'id' | 'rev'>, primary = true): OrderSpec {
  return {
    action: 'confirmar_pago',
    label: t.bank.confirm,
    primary,
    intro: <p>{t.payments.confirmIntro}</p>,
    fields: [{ name: 'motivo', label: t.action.note, kind: 'text' }],
    data: (v) => ({ aplicacion_id: proposal.id, rev: proposal.rev, motivo: v.motivo || undefined }),
  };
}

/** Retirar un pago (una propuesta que no es, un enlace o una marca equivocados): con motivo.
 *  Lo de Exact no se retira aqui: se corrige en Exact (el motor tampoco lo deja). */
export function withdrawOrder(t: Messages, payment: { id: number; rev: number }, label: string): OrderSpec {
  return {
    action: 'retirar_pago',
    label,
    intro: <p>{t.payments.withdrawIntro}</p>,
    fields: [{ name: 'motivo', label: t.payments.withdrawReason, kind: 'text', required: true }],
    data: (v) => ({ aplicacion_id: payment.id, rev: payment.rev, motivo: v.motivo }),
  };
}

/** Lo que apuntar un pago necesita saber de la factura. */
export interface RecordTarget {
  id: number;
  rev: number;
  sentido: Side;
  /** Lo que queda (en el signo de la factura). */
  pendiente_cent: number;
  total_cent: number;
  /** Para ofrecer como justificante un documento de su carpeta. */
  party: { kind: 'client' | 'provider'; id: number } | null;
}

function lineLabel(l: BankLine, t: Messages): string {
  return [formatDate(l.fecha), formatMoney(l.resto_cent ?? l.importe_cent), l.contraparte ?? '', l.concepto ?? '']
    .filter(Boolean)
    .join(' · ')
    .concat(l.dias > 0 ? ` (${countText(t, 'days', l.dias)})` : '');
}

/** Las lineas del banco sin casar del lado de la factura y los documentos guardados de su
 *  carpeta (para el justificante), cuando se puede apuntar un pago. */
export function useRecordChoices(target: RecordTarget | null, active: boolean): { lines: BankLine[]; evidence: { value: string; label: string }[] } {
  const { session } = useSession();
  const { t } = useT();
  const [lines, setLines] = useState<BankLine[]>([]);
  const [docs, setDocs] = useState<PartyDocuments['documentos']>([]);
  const side = target?.sentido ?? null;
  const party = target?.party ?? null;
  useEffect(() => {
    if (!active || !session || !side) return;
    let alive = true;
    session.api
      .get<{ movimientos: BankLines }>(paths.bankLines, { signo: SIGN_OF[side] })
      .then((r) => alive && setLines(r.movimientos.lista.filter((l) => l.importe_cent !== null)))
      .catch(() => alive && setLines([]));
    return () => {
      alive = false;
    };
  }, [active, session, side]);
  useEffect(() => {
    if (!active || !session || !party) return;
    let alive = true;
    const path = party.kind === 'client' ? paths.clientDocuments(party.id) : paths.providerDocuments(party.id);
    session.api
      .get<{ documentos: PartyDocuments }>(path)
      .then((r) => alive && setDocs(r.documentos.documentos.filter((d) => d.guardado)))
      .catch(() => alive && setDocs([]));
    return () => {
      alive = false;
    };
  }, [active, session, party?.kind, party?.id]);
  const seen = new Set<number>();
  const evidence = docs
    .filter((d) => (seen.has(d.id) ? false : (seen.add(d.id), true)))
    .map((d) => ({
      value: String(d.id),
      label: [t.documents.types[d.tipo as keyof typeof t.documents.types] ?? d.tipo, d.numero ?? '', formatDate(d.fecha)].filter(Boolean).join(' · '),
    }));
  return { lines, evidence };
}

/**
 * Apuntar un pago ya hecho (marcar_pagada): importe (por defecto lo que queda), fecha (no
 * futura; con una linea del banco, la del banco), la linea del banco sin casar si la hay, el
 * motivo (obligatorio) y un justificante de la carpeta. "No se paga nada: se apunta lo que ya se
 * pago". El motor manda: no deja apuntar a mano lo que ya dicen el banco o Exact.
 */
export function recordPaymentOrder(t: Messages, target: RecordTarget, lines: readonly BankLine[], evidence: readonly { value: string; label: string }[]): OrderSpec {
  const pending = Math.abs(target.pendiente_cent);
  const sign = target.total_cent < 0 ? -1 : 1;
  const lineOf = (id: string) => lines.find((l) => String(l.id) === id);
  return {
    action: 'marcar_pagada',
    label: t.payments.record,
    intro: <p>{t.payments.recordIntro}</p>,
    fields: [
      {
        name: 'importe',
        label: t.payments.amount,
        kind: 'text',
        initial: centsToInput(pending),
        help: fmt(t.payments.amountHelp, { amount: formatMoney(pending) }),
        hideOptional: true,
      },
      { name: 'fecha_pago', label: t.payments.payDate, kind: 'date', initial: localToday(), help: t.payments.payDateHelp, hideOptional: true },
      {
        name: 'movimiento_id',
        label: t.payments.bankLineField,
        kind: 'select',
        help: t.payments.bankLineHelp,
        initial: '',
        options: [{ value: '', label: t.payments.bankLineNone }, ...lines.map((l) => ({ value: String(l.id), label: lineLabel(l, t) }))],
      },
      { name: 'motivo', label: t.payments.reasonField, kind: 'text', required: true, help: t.payments.reasonHelp },
      ...(target.party
        ? [
            {
              name: 'evidencia_documento_id',
              label: t.payments.evidenceField,
              kind: 'select' as const,
              help: t.payments.evidenceHelp,
              initial: '',
              options: [{ value: '', label: t.payments.evidenceNone }, ...evidence],
            },
          ]
        : []),
    ],
    validate: (v) => {
      const cents = v.importe?.trim() ? parseEuros(v.importe) : null;
      if (v.importe?.trim() && (cents === null || cents <= 0)) return t.payments.badAmount;
      if (cents !== null && cents > pending) return fmt(t.payments.tooMuch, { amount: formatMoney(pending) });
      const line = v.movimiento_id ? lineOf(v.movimiento_id) : undefined;
      const rest = line ? Math.abs(line.resto_cent ?? line.importe_cent ?? 0) : null;
      if (rest !== null && cents !== null && cents > rest) return fmt(t.payments.lineTooSmall, { amount: formatMoney(rest) });
      if (!line && v.fecha_pago && v.fecha_pago > localToday()) return t.payments.future;
      return null;
    },
    data: (v) => {
      const cents = v.importe?.trim() ? parseEuros(v.importe) : null;
      const line = v.movimiento_id ? Number(v.movimiento_id) : undefined;
      return {
        factura_id: target.id,
        rev: target.rev,
        motivo: v.motivo,
        importe: cents === null ? undefined : centsToApi(sign * cents),
        // Con una linea del banco vale su fecha: no se manda otra.
        fecha_pago: line ? undefined : v.fecha_pago || undefined,
        movimiento_id: line,
        evidencia_documento_id: v.evidencia_documento_id ? Number(v.evidencia_documento_id) : undefined,
      };
    },
  };
}

/**
 * Desde una linea del banco sin factura: elegir la factura (las pendientes de ese lado) y apuntar
 * el pago con esa linea. Ninguna factura viene elegida: la persona elige (las que parecen de esta
 * linea, primero y marcadas). null si no hay ninguna que enlazar.
 */
export function linkLineOrder(t: Messages, line: BankLine, side: Side, invoices: readonly InvoiceRow[]): OrderSpec | null {
  const open = invoices.filter((f) => inCartera(f, side) && f.rev !== undefined);
  if (open.length === 0) return null;
  const { likely, others } = linkCandidates(line, open);
  const twins = twinMarks(open);
  const option = (f: InvoiceRow, mark: boolean) => {
    const twin = twins.get(f.id);
    const number = `${f.numero ?? String(f.id)}${twin ? ` (${fmt(t.common.twin, { n: twin.n, of: twin.of })})` : ''}`;
    const label = fmt(t.payments.invoiceOption, { number, party: f.contraparte ?? '—', amount: formatMoney(f.pendiente_cent) });
    return { value: String(f.id), label: mark ? fmt(t.payments.likelyMark, { label }) : label };
  };
  return {
    action: 'marcar_pagada',
    label: t.bank.link,
    primary: true,
    intro: <p>{t.payments.recordIntro}</p>,
    fields: [
      {
        name: 'factura_id',
        label: t.payments.invoiceField,
        kind: 'select',
        required: true,
        hideOptional: true,
        initial: '',
        options: [{ value: '', label: t.payments.chooseInvoice }, ...likely.map((f) => option(f, true)), ...others.map((f) => option(f, false))],
      },
      { name: 'motivo', label: t.payments.reasonField, kind: 'text', required: true, help: t.payments.reasonHelp },
    ],
    validate: (v) => (open.some((x) => String(x.id) === v.factura_id) ? null : fmt(t.action.required, { field: t.payments.invoiceField })),
    data: (v) => {
      const f = open.find((x) => String(x.id) === v.factura_id)!;
      return { factura_id: f.id, rev: f.rev, motivo: v.motivo, movimiento_id: line.id };
    },
  };
}
