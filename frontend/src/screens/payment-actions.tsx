// Las tres ordenes de pagos de Cuentas por cobrar y por pagar (paso 16; revision de Aurora
// §8.4): confirmar lo que el banco propuso (confirmar_pago), decir que no es (retirar_pago,
// con motivo) y apuntar un pago que ya se hizo (marcar_pagada, con motivo; opcional, su linea
// del banco y un documento que lo pruebe). Ninguna paga, aprueba un pago ni prepara un
// fichero de pagos: lo dicen sus dialogos. Cada boton sale solo con el permiso marcar_pagada,
// y cada orden lleva la rev que se vio (si otra persona la cambio antes: 409 y "Opnieuw
// laden"). El texto del banco (contraparte, concepto) es de un tercero: se pinta como texto.
import { useEffect, useState, type ReactNode } from 'react';
import { Check, X } from 'lucide-react';
import { ActionButton, type ActionField } from '@/components/action-dialog';
import { DateText, Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { paths, type InvoiceRow } from '@/lib/api';
import type { BankLine, BankLines, PartyDocuments, PaymentProposal } from '@/lib/api-types';
import { formatDate, formatMoney } from '@/lib/format';
import { useCan, useSession } from '@/lib/session';
import { twinMarks, type TwinMark } from '@/lib/twins';
import { cn } from '@/lib/utils';
import { SIGN_OF, centsToApi, centsToInput, inCartera, linkCandidates, parseEuros, type Side } from './money-model';

/** El dia de hoy en el ordenador (AAAA-MM-DD): un pago apuntado no puede ser de despues. */
function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** La linea del banco y la factura una al lado de la otra, con las tres coincidencias. `twin`:
 *  el "1 van 2" de una factura que comparte numero y relacion con otra de la lista. */
export function ProposalCompare({ proposal: p, twin }: { proposal: PaymentProposal; twin?: TwinMark | undefined }) {
  const { t } = useT();
  const m = p.movimiento;
  return (
    <div className='grid gap-3 text-[13px] sm:grid-cols-2'>
      <div className='rounded-md border border-border bg-muted/40 px-3 py-2'>
        <p className='mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>{t.bank.onBank}</p>
        <p className='flex flex-wrap items-baseline gap-x-2'>
          <DateText value={m?.fecha ?? p.fecha_pago} />
          <Money cents={m?.importe_cent ?? p.importe_cent} className='font-semibold' />
        </p>
        {m?.contraparte && (
          <p className='mt-0.5 break-words' data-proper-name=''>
            {m.contraparte}
          </p>
        )}
        {m?.concepto && (
          <p className='mt-0.5 break-words text-muted-foreground' data-proper-name=''>
            {m.concepto}
          </p>
        )}
      </div>
      <div className='rounded-md border border-border bg-muted/40 px-3 py-2'>
        <p className='mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>{t.bank.invoice}</p>
        <p className='flex flex-wrap items-baseline gap-x-2'>
          <span className='font-mono text-[12.5px] font-medium' data-proper-name=''>
            {p.factura.numero ?? '—'}
          </span>
          {twin && <span className='text-xs text-muted-foreground'>{fmt(t.common.twin, { n: twin.n, of: twin.of })}</span>}
          <Money cents={p.factura.total_cent} className='font-semibold' />
        </p>
        <p className='mt-0.5 break-words' data-proper-name=''>
          {p.factura.parte ?? p.factura.contraparte ?? '—'}
        </p>
        <p className='mt-0.5 text-muted-foreground'>{fmt(t.bank.remaining, { amount: formatMoney(p.factura.pendiente_cent) })}</p>
      </div>
      <MatchList proposal={p} className='sm:col-span-2' />
    </div>
  );
}

/** Referentie ✓, Bedrag ✓, Rekening ✗: en que coincidieron (en texto, no solo el icono). */
export function MatchList({ proposal: p, className }: { proposal: PaymentProposal; className?: string }) {
  const { t } = useT();
  const keys = ['referencia', 'importe', 'contraparte'] as const;
  return (
    <ul aria-label={t.bank.matches} className={cn('flex flex-wrap gap-x-4 gap-y-1 text-[12.5px]', className)}>
      {keys.map((k) => {
        const ok = p.coincidencias[k];
        return (
          <li key={k} className='inline-flex items-center gap-1'>
            {ok ? (
              <Check className='h-3.5 w-3.5 text-ok-foreground' aria-hidden='true' />
            ) : (
              <X className='h-3.5 w-3.5 text-late-foreground' aria-hidden='true' />
            )}
            <span>
              {t.bank.match[k]}: <span className={ok ? 'text-ok-foreground' : 'text-late-foreground'}>{ok ? t.bank.yes : t.bank.no}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Confirmar un pago propuesto: el motivo es opcional (es un clic sobre lo que el sistema ya
 *  propuso). */
export function ConfirmProposalButton({ proposal, onDone, variant = 'default' }: { proposal: PaymentProposal; onDone?: () => void; variant?: 'default' | 'outline' }) {
  const { t } = useT();
  const can = useCan();
  if (!can('marcar_pagada')) return null;
  return (
    <ActionButton
      action='confirmar_pago'
      label={t.bank.confirm}
      variant={variant}
      intro={
        <div className='flex flex-col gap-3'>
          <p>{t.payments.confirmIntro}</p>
          <ProposalCompare proposal={proposal} />
        </div>
      }
      fields={[{ name: 'motivo', label: t.action.note, kind: 'textarea' }]}
      data={(v) => ({ aplicacion_id: proposal.id, rev: proposal.rev, motivo: v.motivo || undefined })}
      onDone={onDone}
    />
  );
}

/** Retirar un pago (una propuesta que no es, un enlace o una marca equivocados): con motivo.
 *  Lo de Exact no se retira aqui: se corrige en Exact (el motor tampoco lo deja). */
export function WithdrawPaymentButton({
  paymentId,
  rev,
  label,
  context,
  onDone,
}: {
  paymentId: number;
  rev: number;
  label: string;
  /** Lo que se retira (la linea al lado de la factura), encima del motivo. */
  context?: ReactNode;
  onDone?: () => void;
}) {
  const { t } = useT();
  const can = useCan();
  if (!can('marcar_pagada')) return null;
  return (
    <ActionButton
      action='retirar_pago'
      label={label}
      intro={
        <div className='flex flex-col gap-3'>
          <p>{t.payments.withdrawIntro}</p>
          {context}
        </div>
      }
      fields={[{ name: 'motivo', label: t.payments.withdrawReason, kind: 'textarea', required: true }]}
      data={(v) => ({ aplicacion_id: paymentId, rev, motivo: v.motivo })}
      onDone={onDone}
    />
  );
}

/** Lo que el dialogo de apuntar un pago necesita saber de la factura. */
export interface RecordTarget {
  id: number;
  rev: number;
  sentido: Side;
  numero: string | null;
  /** Lo que queda (en el signo de la factura). */
  pendiente_cent: number;
  total_cent: number;
  /** Para ofrecer como justificante un documento de su carpeta. */
  party: { kind: 'client' | 'provider'; id: number } | null;
}

function lineLabel(l: BankLine, t: ReturnType<typeof useT>['t']): string {
  return [formatDate(l.fecha), formatMoney(l.resto_cent ?? l.importe_cent), l.contraparte ?? '', l.concepto ?? '']
    .filter(Boolean)
    .join(' · ')
    .concat(l.dias > 0 ? ` (${fmt(l.dias === 1 ? t.bank.ageOne : t.bank.ageDays, { n: l.dias })})` : '');
}

/** Las lineas del banco sin casar del lado de la factura (ingresos para cobrar, cargos para
 *  pagar), cuando se abre el dialogo. */
function useUnmatchedLines(side: Side, active: boolean): BankLine[] {
  const { session } = useSession();
  const [lines, setLines] = useState<BankLine[]>([]);
  useEffect(() => {
    if (!active || !session) return;
    let alive = true;
    session.api
      .get<{ movimientos: BankLines }>(paths.bankLines, { signo: SIGN_OF[side] })
      .then((r) => alive && setLines(r.movimientos.lista.filter((l) => l.importe_cent !== null)))
      .catch(() => alive && setLines([]));
    return () => {
      alive = false;
    };
  }, [active, session, side]);
  return lines;
}

/** Los documentos guardados de la carpeta de la empresa, para el justificante. */
function useEvidenceOptions(party: RecordTarget['party'], active: boolean): { value: string; label: string }[] {
  const { session } = useSession();
  const { t } = useT();
  const [docs, setDocs] = useState<PartyDocuments['documentos']>([]);
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
  }, [active, session, party]);
  const seen = new Set<number>();
  return docs
    .filter((d) => (seen.has(d.id) ? false : (seen.add(d.id), true)))
    .map((d) => ({
      value: String(d.id),
      label: [t.documents.types[d.tipo as keyof typeof t.documents.types] ?? d.tipo, d.numero ?? '', formatDate(d.fecha)].filter(Boolean).join(' · '),
    }));
}

/**
 * Apuntar un pago ya hecho (marcar_pagada): importe (por defecto lo que queda), fecha (no
 * futura; con una linea del banco, la del banco), la linea del banco sin casar si la hay, el
 * motivo (obligatorio) y un justificante de la carpeta. "No se paga nada: se apunta lo que
 * ya se pago". El motor manda: no deja apuntar a mano lo que ya dicen el banco o Exact.
 */
export function RecordPaymentButton({
  target,
  onDone,
  variant = 'outline',
  size = 'sm',
}: {
  target: RecordTarget;
  onDone?: () => void;
  variant?: 'default' | 'outline';
  size?: 'sm' | 'default';
}) {
  const { t } = useT();
  const can = useCan();
  const [open, setOpen] = useState(false);
  const lines = useUnmatchedLines(target.sentido, open);
  const evidence = useEvidenceOptions(target.party, open);
  if (!can('marcar_pagada') || target.pendiente_cent === 0) return null;
  const pending = Math.abs(target.pendiente_cent);
  const sign = target.total_cent < 0 ? -1 : 1;
  const fields: ActionField[] = [
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
      options: [{ value: '', label: t.payments.bankLineNone }, ...lines.map((l) => ({ value: String(l.id), label: lineLabel(l, t) }))],
    },
    { name: 'motivo', label: t.payments.reasonField, kind: 'textarea', required: true, help: t.payments.reasonHelp },
  ];
  if (target.party) {
    fields.push({
      name: 'evidencia_documento_id',
      label: t.payments.evidenceField,
      kind: 'select',
      help: t.payments.evidenceHelp,
      options: [{ value: '', label: t.payments.evidenceNone }, ...evidence],
    });
  }
  const lineOf = (id: string) => lines.find((l) => String(l.id) === id);
  return (
    <ActionButton
      action='marcar_pagada'
      label={t.payments.record}
      variant={variant}
      size={size}
      title={t.payments.record}
      // El boton, el titulo y el envio dicen lo mismo (en castellano salian "Apuntar un pago ya
      // hecho" y "Anotar pago": revision del paso 16).
      submitLabel={t.payments.record}
      intro={<p>{t.payments.recordIntro}</p>}
      fields={fields}
      onToggle={setOpen}
      validate={(v) => {
        const cents = v.importe?.trim() ? parseEuros(v.importe) : null;
        if (v.importe?.trim() && (cents === null || cents <= 0)) return t.payments.badAmount;
        if (cents !== null && cents > pending) return fmt(t.payments.tooMuch, { amount: formatMoney(pending) });
        const line = v.movimiento_id ? lineOf(v.movimiento_id) : undefined;
        const rest = line ? Math.abs(line.resto_cent ?? line.importe_cent ?? 0) : null;
        if (rest !== null && cents !== null && cents > rest) return fmt(t.payments.lineTooSmall, { amount: formatMoney(rest) });
        if (!line && v.fecha_pago && v.fecha_pago > localToday()) return t.payments.future;
        return null;
      }}
      data={(v) => {
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
      }}
      onDone={onDone}
    />
  );
}

/**
 * Desde una linea del banco sin factura: elegir la factura (las pendientes de ese lado) y
 * apuntar el pago con esa linea (marcar_pagada con movimiento_id; el importe, por defecto lo
 * que queda de la linea o de la factura, lo pone el motor). La rev es la de la lista. Ninguna
 * factura viene elegida: la persona elige (las que parecen de esta linea, primero y marcadas).
 */
export function LinkLineButton({ line, side, invoices, onDone }: { line: BankLine; side: Side; invoices: readonly InvoiceRow[]; onDone?: () => void }) {
  const { t } = useT();
  const can = useCan();
  if (!can('marcar_pagada')) return null;
  const open = invoices.filter((f) => inCartera(f, side) && f.rev !== undefined);
  if (open.length === 0) return null;
  const amount = formatMoney(line.resto_cent ?? line.importe_cent);
  const { likely, others } = linkCandidates(line, open);
  const twins = twinMarks(open);
  const option = (f: InvoiceRow, mark: boolean) => {
    const twin = twins.get(f.id);
    const number = `${f.numero ?? String(f.id)}${twin ? ` (${fmt(t.common.twin, { n: twin.n, of: twin.of })})` : ''}`;
    const label = fmt(t.payments.invoiceOption, { number, party: f.contraparte ?? '—', amount: formatMoney(f.pendiente_cent) });
    return { value: String(f.id), label: mark ? fmt(t.payments.likelyMark, { label }) : label };
  };
  return (
    <ActionButton
      action='marcar_pagada'
      label={t.bank.link}
      title={t.payments.record}
      submitLabel={t.payments.record}
      intro={
        <div className='flex flex-col gap-2'>
          <p>{t.payments.recordIntro}</p>
          <p className='rounded-md border border-border bg-muted/40 px-3 py-2 text-[13px]'>
            <span className='num'>{formatDate(line.fecha)}</span> · <span className='num'>{amount}</span>
            {line.contraparte && (
              <>
                {' · '}
                <span data-proper-name=''>{line.contraparte}</span>
              </>
            )}
            {line.concepto && (
              <>
                {' · '}
                <span data-proper-name=''>{line.concepto}</span>
              </>
            )}
          </p>
        </div>
      }
      fields={[
        {
          name: 'factura_id',
          label: t.payments.invoiceField,
          kind: 'select',
          required: true,
          hideOptional: true,
          initial: '',
          options: [{ value: '', label: t.payments.chooseInvoice }, ...likely.map((f) => option(f, true)), ...others.map((f) => option(f, false))],
        },
        { name: 'motivo', label: t.payments.reasonField, kind: 'textarea', required: true, help: t.payments.reasonHelp },
      ]}
      validate={(v) => (open.some((x) => String(x.id) === v.factura_id) ? null : fmt(t.action.required, { field: t.payments.invoiceField }))}
      data={(v) => {
        const f = open.find((x) => String(x.id) === v.factura_id)!;
        return { factura_id: f.id, rev: f.rev, motivo: v.motivo, movimiento_id: line.id };
      }}
      onDone={onDone}
    />
  );
}
