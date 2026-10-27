// "Betalingen" en la ficha de una factura (paso 16; revision de Aurora §8.4 f): cada pago
// con su fecha, importe, fuente (banco, Exact o apuntado a mano, y por quien), estado
// (propuesto, confirmado, retirado), su linea del banco y su motivo; lo propuesto se
// confirma o se retira aqui mismo, y lo que no es de Exact se puede retirar. "Pagada" va
// siempre con su fuente: manda el banco, luego Exact, luego lo apuntado a mano, con el aviso
// K3 si el banco no lo trae. El texto del banco y lo que escribio una persona: como texto.
import { Download } from 'lucide-react';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import { DateText, Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { ruleText, stateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { InvoiceDetail, InvoicePayment, PaymentProposal } from '@/lib/api-types';
import { formatDate, formatMoney } from '@/lib/format';
import { useSession } from '@/lib/session';
import { cn } from '@/lib/utils';
import { canWithdraw, paymentsInOrder } from './money-model';
import { paidSource } from './documents-model';
import { ConfirmProposalButton, WithdrawPaymentButton } from './payment-actions';

/** "Betaald volgens de bank op 22-08-2026", "volgens Exact" o "met de hand ... door Ana";
 *  null si no esta pagada. */
export function PaidSourceLine({ invoice: f, className }: { invoice: InvoiceDetail; className?: string }) {
  const { t, lang } = useT();
  const paid = paidSource(f);
  if (!paid) return null;
  const manual = paid.source === 'manual' ? paymentsInOrder(f.pagos ?? []).find((p) => p.fuente === 'manual' && p.estado === 'confirmada') : undefined;
  const text =
    paid.source === 'banco'
      ? fmt(t.payments.paidBank, { date: formatDate(paid.date) })
      : paid.source === 'exact'
        ? fmt(t.payments.paidExact, { date: formatDate(paid.date) })
        : manual?.persona
          ? fmt(t.payments.paidManual, { name: '\u0000', date: formatDate(paid.date) })
          : fmt(t.payments.paidManualNoName, { date: formatDate(paid.date) });
  const [before, after] = text.split('\u0000');
  return (
    <span data-testid='paid-source' className={cn('block text-xs text-soft-foreground', className)}>
      {before}
      {after !== undefined && (
        <>
          <span data-proper-name=''>{manual?.persona}</span>
          {after}
        </>
      )}
      {paid.k3 && <span className='mt-0.5 block font-medium text-late-foreground'>{ruleText(lang, 'K3')?.title ?? 'K3'}</span>}
    </span>
  );
}

/** Lo que una propuesta necesita para su dialogo, a partir del pago de la ficha. */
function asProposal(p: InvoicePayment, f: InvoiceDetail): PaymentProposal {
  const total = (f.campos.find((c) => c.campo === 'total_cent')?.valor as number | null) ?? null;
  const [referencia, importe, contraparte] = ['referencia', 'importe', 'contraparte'].map((k) => (p.regla ?? '').split('+').includes(k));
  return {
    id: p.id,
    rev: p.rev,
    lado: f.sentido === 'saliente' ? 'cobro' : 'pago',
    importe_cent: p.importe_cent,
    fecha_pago: p.fecha_pago,
    regla: p.regla,
    coincidencias: { referencia: referencia!, importe: importe!, contraparte: contraparte! },
    factura: {
      id: f.id,
      numero: f.numero,
      sentido: f.sentido,
      tipo: 'factura',
      contraparte: f.contraparte,
      proveedor_id: null,
      cliente_id: null,
      parte: f.contraparte,
      total_cent: total,
      pendiente_cent: f.estado?.pendiente_cent ?? null,
      vencimiento: f.vencimiento?.fecha ?? null,
      estado_pago: f.estado?.estado_pago ?? null,
    },
    movimiento:
      p.movimiento_id === null
        ? null
        : {
            id: p.movimiento_id,
            fecha: p.movimiento_fecha ?? p.fecha_pago,
            importe_cent: p.movimiento_importe_cent ?? p.importe_cent,
            contraparte: p.contraparte,
            contraparte_iban: null,
            concepto: p.concepto,
            referencia: null,
            referencia_e2e: null,
          },
  };
}

export function InvoicePayments({ invoice: f, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const payments = paymentsInOrder(f.pagos ?? []);
  return (
    <section aria-labelledby='payments' className='mb-8'>
      <h2 id='payments' className='mb-3 text-[16px] font-semibold'>
        {t.payments.title}
        {payments.length > 0 && <span className='ml-2 text-[13px] font-normal text-muted-foreground'>{payments.length}</span>}
      </h2>
      {payments.length === 0 ? (
        <p className='text-[13.5px] text-muted-foreground'>{t.payments.none}</p>
      ) : (
        <ul className='flex flex-col divide-y divide-divider rounded-md border border-border bg-card'>
          {payments.map((p) => {
            const source = stateLabel(lang, 'fuente_aplicacion', p.fuente) ?? p.fuente;
            const who = p.persona ? fmt(t.payments.by, { name: '\u0000' }).split('\u0000') : null;
            const proposal = p.estado === 'propuesta' ? asProposal(p, f) : null;
            return (
              <li key={p.id} data-testid='payment' className='grid grid-cols-1 gap-x-6 gap-y-2 px-4 py-3 text-[13.5px] md:grid-cols-[9rem_1fr_auto]'>
                <span className='flex flex-col items-start gap-1'>
                  <StatusPill group='aplicacion' state={p.estado} />
                </span>
                <span className={cn('flex min-w-0 flex-col gap-0.5', p.estado === 'retirada' && 'text-muted-foreground')}>
                  <span className='flex flex-wrap items-baseline gap-x-2'>
                    <DateText value={p.fecha_pago} />
                    <Money cents={p.importe_cent} className={cn('font-semibold', p.estado === 'retirada' && 'line-through')} />
                    <span>· {source}</span>
                    {p.metodo === 'automatica' && <span className='text-xs text-muted-foreground'>({t.payments.automatic})</span>}
                    {who && (
                      <span className='text-xs text-muted-foreground'>
                        {who[0]}
                        <span data-proper-name=''>{p.persona}</span>
                        {who[1]}
                      </span>
                    )}
                  </span>
                  {p.movimiento_id !== null && (
                    <span className='text-xs text-soft-foreground'>
                      {fmt(t.payments.bankLine, {
                        date: formatDate(p.movimiento_fecha ?? p.fecha_pago),
                        amount: formatMoney(p.movimiento_importe_cent ?? p.importe_cent),
                      })}
                      {(p.contraparte || p.concepto) && (
                        <>
                          {' · '}
                          <span data-proper-name=''>{[p.contraparte, p.concepto].filter(Boolean).join(' · ')}</span>
                        </>
                      )}
                    </span>
                  )}
                  {p.motivo && (
                    <span className='text-xs text-soft-foreground'>
                      {t.payments.reason}: <span data-proper-name=''>{p.motivo}</span>
                    </span>
                  )}
                  {p.estado === 'retirada' && (p.retirada_por || p.motivo_retirada) && (
                    <span className='text-xs text-soft-foreground'>
                      {p.retirada_por && (
                        <>
                          {fmt(t.payments.withdrawnBy, { name: '\u0000' }).split('\u0000')[0]}
                          <span data-proper-name=''>{p.retirada_por}</span>
                          {fmt(t.payments.withdrawnBy, { name: '\u0000' }).split('\u0000')[1]}
                        </>
                      )}
                      {p.retirada_por && p.motivo_retirada ? ': ' : ''}
                      {p.motivo_retirada && <span data-proper-name=''>{p.motivo_retirada}</span>}
                    </span>
                  )}
                  {p.evidencia_documento_id && session && (
                    <Button
                      variant='link'
                      size='sm'
                      className='h-auto self-start px-0 py-0 text-xs'
                      onClick={() => void session.api.download(paths.documentOriginal(p.evidencia_documento_id!), `bewijs-${p.id}`)}
                    >
                      <Download className='mr-1 h-3.5 w-3.5' aria-hidden='true' />
                      {t.payments.evidence}
                    </Button>
                  )}
                  {p.fuente === 'exact' && p.estado !== 'retirada' && <span className='text-xs text-muted-foreground'>{t.payments.exactNote}</span>}
                </span>
                <span className='flex flex-wrap items-start gap-2 md:justify-end'>
                  {proposal && <ConfirmProposalButton proposal={proposal} onDone={onDone} />}
                  {canWithdraw(p) && (
                    <WithdrawPaymentButton
                      paymentId={p.id}
                      rev={p.rev}
                      label={proposal ? t.bank.notThis : t.payments.withdraw}
                      context={
                        <p className='rounded-md border border-border bg-muted/40 px-3 py-2 text-[13px]'>
                          <span className='num'>{formatDate(p.fecha_pago)}</span> · <span className='num'>{formatMoney(p.importe_cent)}</span> · {source}
                        </p>
                      }
                      onDone={onDone}
                    />
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
