// La tarjeta de una factura en cualquier vista de un panel (especificacion §2.2.7): la tarjeta
// .detail de Aurora con el numero (h3), lineas p (empresa, importe y pendiente, vencimiento o
// retraso, los pagos, tres como mucho, y por que pide atencion), el estado (span) y sus botones:
// "Abrir la factura" (.primary: su hoja en Documentos, con el vuelo), "Descargar original"
// (.outline, la descarga auditada) y, con el permiso marcar_pagada y algo pendiente, "Anotar
// pago" (.outline, con su formulario en la tarjeta). Las demas ordenes de una factura estan en
// su hoja (§2.3).
import { useState } from 'react';
import { fmt, useT } from '@/i18n';
import { paymentStateLabel, ruleText, stateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { InvoiceDetail } from '@/lib/api-types';
import { formatDate, formatMoney, todayIso } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { paidSource } from '../documents/documents-model';
import { paymentsInOrder } from './money-model';
import { useLoad } from '../use-load';
import { dueLabel } from '../due';
import { invoicePlace } from '../estado';
import { Orders, apiErrorMessage, ErrorLine } from '../orders';
import { useGoToDocuments } from '../navigation';
import { Detail } from './pieces';
import { recordPaymentOrder, useRecordChoices, type RecordTarget } from './payment-orders';

/** Lo que una factura deja apuntar: lo que queda, si esta pendiente o vencida. */
export function recordTargetOf(f: InvoiceDetail): RecordTarget | null {
  const value = (name: string) => f.campos.find((c) => c.campo === name)?.valor ?? null;
  const total = value('total_cent') as number | null;
  const left = f.estado?.pendiente_cent ?? null;
  const open = f.estado?.estado_pago === 'pendiente' || f.estado?.estado_pago === 'vencida';
  if (f.anulada || total === null || left === null || left === 0 || !open) return null;
  const providerId = value('proveedor_id') as number | null;
  const clientId = value('cliente_id') as number | null;
  return {
    id: f.id,
    rev: f.rev,
    sentido: f.sentido,
    pendiente_cent: left,
    total_cent: total,
    party: f.sentido === 'saliente' ? (clientId ? { kind: 'client', id: clientId } : null) : providerId ? { kind: 'provider', id: providerId } : null,
  };
}

/** La razon con nombre de la prioridad: la del hallazgo mas urgente abierto, o que va tarde. */
export function priorityReasonOf(f: InvoiceDetail, lang: Parameters<typeof ruleText>[0]): string | null {
  const ORDER: Record<string, number> = { bloqueo: 0, retencion: 1, aviso: 2 };
  const first = [...f.hallazgos]
    .filter((h) => h.estado === 'abierto')
    .sort((a, b) => (ORDER[a.severidad] ?? 3) - (ORDER[b.severidad] ?? 3) || a.id - b.id)[0];
  if (first) return ruleText(lang, first.regla)?.title ?? null;
  if (f.estado?.estado_pago === 'vencida') return paymentStateLabel(lang, 'vencida');
  return null;
}

/** "Descargar original": la descarga auditada (documento_abierto en la auditoria). */
export function useOriginalDownload(): { download: (path: string, name: string) => Promise<void>; busy: boolean; error: unknown } {
  const { session } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const download = async (path: string, name: string) => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await session.api.download(path, name);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return { download, busy, error };
}

export function InvoiceCard({ id, onClose }: { id: number; onClose: () => void }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const can = useCan();
  const goTo = useGoToDocuments();
  const original = useOriginalDownload();
  const [state] = useLoad(() => session!.api.get<{ factura: InvoiceDetail }>(paths.invoice(id)).then((r) => r.factura), [session, id, version]);
  const f = state.status === 'ready' ? state.data : null;
  const target = f && can('marcar_pagada') ? recordTargetOf(f) : null;
  const choices = useRecordChoices(target, target !== null);
  const title = f?.numero ?? fmt(t.records.invoice.fallbackTitle, { id });
  if (!f) {
    return (
      <Detail title={title} onClose={onClose} titleData>
        {state.status === 'error' ? <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} /> : null}
      </Detail>
    );
  }
  const value = (name: string) => f.campos.find((c) => c.campo === name)?.valor ?? null;
  const total = value('total_cent') as number | null;
  const pending = f.estado?.pendiente_cent ?? null;
  const due = f.vencimiento?.fecha ?? f.estado?.vencimiento ?? null;
  const open = f.estado?.estado_pago === 'pendiente' || f.estado?.estado_pago === 'vencida';
  const payments = paymentsInOrder(f.pagos ?? []).slice(0, 3);
  const reason = priorityReasonOf(f, lang);
  const paid = paidSource(f);
  const stateText = paymentStateLabel(lang, f.estado?.estado_pago) ?? t.common.unknown;
  const source = paid
    ? fmt(paid.source === 'banco' ? t.documents.paidBank : paid.source === 'exact' ? t.documents.paidExact : t.documents.paidManual, { date: formatDate(paid.date) })
    : null;
  return (
    <Detail title={title} onClose={onClose} titleData>
      <p>
        <span data-proper-name=''>{f.contraparte ?? '—'}</span>
      </p>
      <p>
        {formatMoney(total)}
        {pending !== null && open ? ` · ${fmt(t.invoice.outstanding, { amount: formatMoney(pending) })}` : ''}
      </p>
      {due && (
        <p>
          {t.invoice.dueLabel}: {formatDate(due)}
          {open ? ` · ${dueLabel(t, due, todayIso()) ?? ''}` : ''}
        </p>
      )}
      {payments.map((p) => (
        <p key={p.id} data-testid='payment'>
          {[formatDate(p.fecha_pago), formatMoney(p.importe_cent), stateLabel(lang, 'fuente_aplicacion', p.fuente) ?? p.fuente, stateLabel(lang, 'aplicacion', p.estado) ?? p.estado].join(' · ')}
        </p>
      ))}
      {reason && <p>{fmt(t.aurora.card.why, { why: reason })}</p>}
      <span>
        {stateText}
        {source ? ` · ${source}` : ''}
      </span>
      {original.error !== null && <ErrorLine error={original.error} message={apiErrorMessage(original.error, t, lang)} />}
      <Orders
        orders={target ? [recordPaymentOrder(t, target, choices.lines, choices.evidence)] : []}
        before={
          <>
            <button type='button' className='primary' onClick={() => goTo(invoicePlace({ id: f.id, sentido: f.sentido, cliente_id: value('cliente_id') as number | null, proveedor_id: value('proveedor_id') as number | null }))}>
              {t.aurora.card.openInvoice}
            </button>
            {f.original?.guardado && (
              <button type='button' className='outline' disabled={original.busy} onClick={() => void original.download(paths.invoiceOriginal(f.id), `${f.numero ?? 'factuur'}.pdf`)}>
                {t.aurora.card.downloadOriginal}
              </button>
            )}
          </>
        }
      />
    </Detail>
  );
}
