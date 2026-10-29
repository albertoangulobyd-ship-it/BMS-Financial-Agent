// La hoja de una factura (E6-h, especificacion §2.3): el <dialog> de Aurora con, de arriba
// abajo, ws-dialog-top (el tipo y el estado, con su ✕), la hoja dibujada desde el registro
// (ws-paper: el numero, la empresa, la marca de la ultima lectura, fecha, vencimiento, base, IVA,
// total, pendiente, estado con su fuente y los pagos, tres como mucho), "Descargar original"
// (ws-download, auditada) y una sola tabla, "Lo que se puede hacer" (.ws-file-table): una fila
// por cosa pendiente, de la mas urgente a la menos (cada hallazgo, cada pago propuesto, cada
// relacion propuesta, la excepcion abierta y la revision si falta) y siempre "Datos leidos" y
// "Pagos, notas e historial". Al pulsar una fila, su tarjeta .detail se abre debajo de la tabla
// con sus ordenes (orders.tsx), y el dialogo se desplaza lo justo para ensenarla. Sin permiso
// para ninguna orden de una fila, la fila se ve igual y su tarjeta no tiene botones. Las ordenes
// y sus reglas son las de la ficha de antes (pasos 15 y 16).
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useEffect, useId, useRef, useState, type MutableRefObject } from 'react';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { catalogFor, fieldLabel, findingDetail, paymentStateLabel, qualityText, ruleText, sourceText, stateLabel, verdict } from '@/i18n/domain';
import { MIN_ACCEPT_REASON, permissionFor } from '@/lib/actions';
import { paths } from '@/lib/api';
import type { FieldInfo, Finding, InvoiceDetail, InvoiceHistory, Person } from '@/lib/api-types';
import { editableInApp, editableText, enumGroup, formatFieldValue, visibleFields } from '@/lib/field-format';
import { NO_VALUE, formatDate, formatDateProse, formatDateTime, formatHours, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { statusLabel } from '@/components/status-pill';
import { FieldInput, Orders, apiErrorMessage, ErrorLine, type OrderField, type OrderSpec } from '../orders';
import { ExceptionLines, exceptionOrders, exceptionState } from '../panels/exception-orders';
import { recordTargetOf } from '../panels/invoice-card';
import { paymentsInOrder, canWithdraw } from '../panels/money-model';
import { ProposalLines, confirmProposalOrder, recordPaymentOrder, useRecordChoices, withdrawOrder } from '../panels/payment-orders';
import { Detail } from '../panels/pieces';
import { useLoad } from '../use-load';
import type { AnalysisStatus } from './analysis';
import { paidSource } from './documents-model';
import { DownloadOriginal, Fact, FileRow, FileTable, Paper, SheetTop, typeLabel } from './sheets';
import { asProposal, foldLabel, foldRows, historyEntries, sheetRows, toScaled, type SheetRow } from './sheet-model';

/** Verificar tiene sentido donde hay una duda; en los demas campos el boton seria ruido. */
const NEEDS_CHECK = new Set(['dudoso', 'discrepancia', 'anomalia']);

/** La rev de la fila de un campo: la de la factura o la de su linea. */
function revOf(invoice: InvoiceDetail, field: FieldInfo): number {
  if (field.tabla === 'factura_linea') return invoice.lineas.find((l) => l.id === field.fila_id)?.rev ?? invoice.rev;
  return invoice.rev;
}

function findField(invoice: InvoiceDetail, table: string, rowId: number, name: string): FieldInfo | undefined {
  if (table === 'factura') return invoice.campos.find((c) => c.campo === name);
  if (table === 'factura_linea') return invoice.lineas.find((l) => l.id === rowId)?.campos.find((c) => c.campo === name);
  return undefined;
}

/** El tipo de una factura, como el de su documento ("Factura de compra"). */
function invoiceType(f: InvoiceDetail): string {
  // El motor llama nota_credito a un abono (consultas._tipo_de_factura).
  const credit = (f.campos.find((c) => c.campo === 'tipo')?.valor ?? 'factura') === 'nota_credito';
  if (f.sentido === 'saliente') return credit ? 'abono_venta' : 'factura_venta';
  return credit ? 'abono_compra' : 'factura_compra';
}

/** El campo del valor nuevo de "Cambiar", con la pieza que le toca. */
function inputFor(field: FieldInfo, lang: Lang, label: string): OrderField {
  const initial = editableText(field);
  if (field.tipo === 'fecha') return { name: 'valor', label, kind: 'date', initial, hideOptional: true };
  if (field.tipo === 'bool') {
    const c = catalogFor(lang).comun;
    return {
      name: 'valor',
      label,
      kind: 'select',
      initial: initial || 'no',
      options: [
        { value: 'si', label: c.si },
        { value: 'no', label: c.no },
      ],
    };
  }
  const group = field.tipo === 'enum' ? enumGroup(field.campo) : null;
  if (group) {
    const options = Object.keys(catalogFor(lang).estados[group]).map((k) => ({
      value: k,
      label: stateLabel(lang, group, k) ?? k,
    }));
    return {
      name: 'valor',
      label,
      kind: 'select',
      initial: initial || options[0]?.value,
      options,
    };
  }
  return { name: 'valor', label, kind: 'text', initial, hideOptional: true };
}

/** El valor nuevo como se vera (un importe escrito 2902,79 se ve € 2.902,79). */
function previewValue(field: FieldInfo, text: string, lang: Lang): string {
  const value = text.trim();
  if (!value) return '—';
  if (['cent', 'mil', 'e4', 'pb'].includes(field.tipo)) {
    const scale = { cent: 2, mil: 3, e4: 4, pb: 2 }[field.tipo as 'cent' | 'mil' | 'e4' | 'pb'];
    const integer = toScaled(value, scale);
    return integer === null ? value : formatFieldValue(field, integer, lang);
  }
  if (field.tipo === 'bool') return formatFieldValue(field, value === 'si', lang);
  return formatFieldValue(field, value, lang);
}

/** Las ordenes de un campo: verificarlo, cambiarlo (o rellenarlo) y deshacer un cambio. */
function fieldOrders(t: Messages, lang: Lang, invoice: InvoiceDetail, field: FieldInfo, can: (p?: string) => boolean, named: boolean): OrderSpec[] {
  if (!editableInApp(field)) return [];
  const name = fieldLabel(lang, field.tabla, field.campo) ?? field.campo;
  const rev = revOf(invoice, field);
  const base = {
    tabla: field.tabla,
    fila_id: field.fila_id,
    campo: field.campo,
    rev,
  };
  const hasValue = field.valor !== null;
  const orders: OrderSpec[] = [];
  if (hasValue && !field.verificado && (NEEDS_CHECK.has(field.calidad ?? '') || named) && can(permissionFor('verificar_campo'))) {
    orders.push({
      action: 'verificar_campo',
      label: fmt(t.fields.verifyThis, { field: name }),
      intro: <p>{fmt(t.fields.verifyIntro, { field: name })}</p>,
      data: () => base,
    });
  }
  if (can(permissionFor('fijar_campo', hasValue))) {
    orders.push({
      action: 'fijar_campo',
      label: fmt(hasValue ? t.fields.editThis : t.fields.fillThis, {
        field: name,
      }),
      intro: <p>{hasValue ? t.fields.editIntro : t.fields.fillIntro}</p>,
      fields: [
        inputFor(field, lang, t.fields.newValue),
        {
          name: 'motivo',
          label: t.action.reason,
          kind: 'text',
          required: hasValue,
          help: hasValue ? t.fields.reasonHelp : undefined,
        },
      ],
      preview: (v) => (
        <p>
          {t.fields.oldValue}: {formatFieldValue(field, field.valor, lang)} → {t.fields.newValue}: {previewValue(field, v.valor ?? '', lang)}
        </p>
      ),
      data: (v) => ({
        ...base,
        valor: v.valor === '' ? null : v.valor,
        motivo: v.motivo || undefined,
      }),
    });
    if (field.revertible) {
      orders.push({
        action: 'revertir_campo',
        label: fmt(t.aurora.sheet.revertThis, { field: name }),
        intro: (
          <p>
            {fmt(t.fields.revertIntro, {
              value: formatFieldValue(field, field.original, lang),
            })}
          </p>
        ),
        fields: [
          {
            name: 'motivo',
            label: t.action.reason,
            kind: 'text',
            required: true,
          },
        ],
        data: (v) => ({ ...base, motivo: v.motivo }),
      });
    }
  }
  return orders;
}

export function InvoiceSheet({
  id,
  analysis,
  escape,
  onClose,
  onLoaded,
  onOpenInvoice,
}: {
  id: number;
  analysis?: AnalysisStatus;
  /** Escape: cerrar primero la tarjeta abierta (true si la habia). */
  escape: MutableRefObject<() => boolean>;
  onClose: () => void;
  onLoaded: (invoice: InvoiceDetail) => void;
  onOpenInvoice: (id: number) => void;
}) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [open, setOpen] = useState<string | null>(null);
  // Plegada al abrir (el <dialog> monta una hoja nueva cada vez: document-workspace.tsx).
  const [expanded, setExpanded] = useState(false);
  const tableId = useId();
  const table = useRef<HTMLDivElement>(null);
  const firstFolded = useRef<number | null>(null);
  const [state] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ factura: InvoiceDetail }>(paths.invoice(id)).then((r) => r.factura),
        session!.api.get<{ personas: Person[] }>(paths.people).then((r) => r.personas),
      ]),
    [session, id, version]
  );
  escape.current = () => {
    if (open === null) return false;
    setOpen(null);
    return true;
  };
  const invoice = state.status === 'ready' ? state.data[0] : null;
  useEffect(() => {
    if (invoice) onLoaded(invoice);
    // Solo al llegar la factura.
  }, [invoice?.id, invoice?.rev]);
  // Al desplegar, el foco va a la primera fila que estaba plegada (con el teclado se sigue ahi).
  useEffect(() => {
    if (firstFolded.current === null) return;
    table.current?.querySelectorAll<HTMLElement>(':scope > a')[firstFolded.current]?.focus();
    firstFolded.current = null;
  }, [expanded]);

  if (!invoice || state.status !== 'ready') {
    return (
      <>
        <SheetTop label={t.records.invoice.label} onClose={onClose} />
        {state.status === 'error' && <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} />}
      </>
    );
  }
  const f = invoice;
  const people = state.data[1];
  const value = (name: string) => f.campos.find((c) => c.campo === name)?.valor ?? null;
  const e = f.estado;
  const paid = paidSource(f);
  const payments = paymentsInOrder(f.pagos ?? []);
  const rows = sheetRows(f);
  const fold = foldRows(rows, expanded);
  const current = fold.shown.find((r) => r.key === open) ?? null;
  const toggle = () => {
    if (expanded) {
      setExpanded(false);
      // Una tarjeta de una fila que se pliega se cierra con ella.
      const folded = foldRows(rows, false);
      if (open !== null && !folded.shown.some((r) => r.key === open)) setOpen(null);
    } else {
      firstFolded.current = fold.shown.length;
      setExpanded(true);
    }
  };
  const late = e?.dias_vencida
    ? fmt(e.dias_vencida === 1 ? t.why.overdueDaysOne : t.why.overdueDays, {
        n: e.dias_vencida,
      })
    : null;
  const paidText = paid
    ? fmt(paid.source === 'banco' ? t.documents.paidBank : paid.source === 'exact' ? t.documents.paidExact : t.documents.paidManual, {
        date: formatDate(paid.date),
      })
    : null;

  return (
    <>
      <SheetTop label={[typeLabel(t, invoiceType(f)), paymentStateLabel(lang, e?.estado_pago)].filter(Boolean).join(' · ')} onClose={onClose} />
      <Paper title={f.numero ?? fmt(t.records.invoice.fallbackTitle, { id: f.id })} subtitle={f.contraparte} analysis={analysis}>
        <Fact label={t.documents.invoiceDate}>{formatDate(value('fecha_factura') as string | null)}</Fact>
        <Fact label={t.documents.due}>
          {formatDate(f.vencimiento?.fecha ?? e?.vencimiento)}
          {late && <small> · {late}</small>}
        </Fact>
        <Fact label={t.documents.base}>{formatMoney(value('base_cent') as number | null)}</Fact>
        <Fact label={t.documents.vat}>{formatMoney(value('iva_cent') as number | null)}</Fact>
        <Fact label={t.documents.total}>{formatMoney(value('total_cent') as number | null)}</Fact>
        <Fact label={t.parties.outstanding}>{formatMoney(e?.pendiente_cent)}</Fact>
        <Fact label={t.documents.state}>
          <span data-testid='paid-source'>
            {paymentStateLabel(lang, e?.estado_pago) ?? NO_VALUE}
            {paidText && <small> · {paidText}</small>}
            {paid?.k3 && <small> · {ruleText(lang, 'K3')?.title ?? 'K3'}</small>}
          </span>
        </Fact>
        <Fact label={t.documents.payments}>
          {payments.length === 0
            ? t.parties.noPayments
            : payments.slice(0, 3).map((p) => (
                <span key={p.id} data-testid='payment' className='block'>
                  {[
                    formatDate(p.fecha_pago),
                    formatMoney(p.importe_cent),
                    stateLabel(lang, 'fuente_aplicacion', p.fuente) ?? p.fuente,
                    stateLabel(lang, 'aplicacion', p.estado) ?? p.estado,
                  ].join(' · ')}
                </span>
              ))}
        </Fact>
      </Paper>
      <DownloadOriginal path={paths.invoiceOriginal(f.id)} name={`${f.numero ?? 'factura'}.pdf`} kept={Boolean(f.original?.guardado)} />
      {f.anulada && <p className='ws-paper-disclaimer'>{t.invoice.cancelled}</p>}
      <FileTable title={t.aurora.sheet.canDo} count={rows.length} id={tableId} tableRef={table}>
        {fold.shown.map((row) => (
          <SheetRowView key={row.key} row={row} invoice={f} current={row.key === open} onOpen={() => setOpen(open === row.key ? null : row.key)} />
        ))}
        {fold.foldable && (
          // El control de plegar, con el boton discreto de la cabecera de la tabla de Aurora.
          <div className='ws-table-head' data-testid='sheet-fold'>
            <button type='button' aria-expanded={expanded} aria-controls={tableId} onClick={toggle}>
              {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />} {foldLabel(t, fold)}
            </button>
          </div>
        )}
      </FileTable>
      {current && <RowCard key={current.key} row={current} invoice={f} people={people} onClose={() => setOpen(null)} onOpenInvoice={onOpenInvoice} />}
    </>
  );
}

/** Una fila de "Lo que se puede hacer": que es (strong) y, en una linea (small), su estado. Lo
 *  que dice cada cosa va en su tarjeta: asi cada fila mide lo de una fila de la ficha de Aurora
 *  (strong y small) y la hoja se desplaza lo menos posible (especificacion §2.3 y §6.1). */
function SheetRowView({ row, invoice: f, current, onOpen }: { row: SheetRow; invoice: InvoiceDetail; current: boolean; onOpen: () => void }) {
  const { t, lang } = useT();
  const s = t.aurora.sheet;
  let title: string;
  let parts: (string | null | undefined)[];
  switch (row.kind) {
    case 'finding': {
      const h = row.finding;
      title = ruleText(lang, h.regla)?.title ?? h.regla;
      parts = [h.estado === 'desaparecido' ? statusLabel(lang, t, 'hallazgo', h.estado) : statusLabel(lang, t, 'severidad', h.severidad)];
      break;
    }
    case 'payment': {
      const p = row.payment;
      title = s.payment;
      parts = [formatDate(p.fecha_pago), formatMoney(p.importe_cent), statusLabel(lang, t, 'aplicacion', p.estado)];
      break;
    }
    case 'relation': {
      const r = row.relation;
      title = s.relation;
      parts = [
        (r.papel === 'origen' ? r.destino_numero : r.origen_numero) ?? `#${r.papel === 'origen' ? r.destino_id : r.origen_id}`,
        statusLabel(lang, t, 'relacion', r.estado),
      ];
      break;
    }
    case 'exception':
      // El titulo de una excepcion abierta por el motor es una frase suya (en castellano): aqui,
      // como en la ficha de antes, "Excepcion" y su estado.
      title = t.invoice.exceptionStep;
      parts = [f.excepcion ? exceptionState(f.excepcion, t, lang) : null];
      break;
    case 'review':
      title = t.invoice.reviewStep;
      parts = [statusLabel(lang, t, 'revision', f.estado?.estado_revision)];
      break;
    case 'read': {
      const e = f.estado;
      const v = verdict(lang, {
        pendientes: f.hallazgos.length,
        aceptados: f.hallazgos.filter((h) => h.estado === 'aceptado').length,
        sin_datos: e?.sin_datos ?? 0,
        campos: (e?.sin_resolver ?? 0) + (e?.dudosos ?? 0),
      });
      title = s.read;
      parts = [v.text];
      break;
    }
    case 'more':
      title = s.more;
      parts = [s.moreNote];
      break;
  }
  const note = parts.filter(Boolean).join(' · ');
  return <FileRow title={title} note={note || undefined} current={current} onOpen={onOpen} />;
}

/** La tarjeta .detail de una fila, con sus ordenes. */
function RowCard({
  row,
  invoice,
  people,
  onClose,
  onOpenInvoice,
}: {
  row: SheetRow;
  invoice: InvoiceDetail;
  people: Person[];
  onClose: () => void;
  onOpenInvoice: (id: number) => void;
}) {
  switch (row.kind) {
    case 'finding':
      return <FindingCard finding={row.finding} invoice={invoice} people={people} onClose={onClose} />;
    case 'payment':
      return <ProposalCard invoice={invoice} paymentId={row.payment.id} onClose={onClose} />;
    case 'relation':
      return <RelationCard invoice={invoice} relationId={row.relation.id} onClose={onClose} onOpenInvoice={onOpenInvoice} />;
    case 'exception':
      return <ExceptionCard invoice={invoice} people={people} onClose={onClose} />;
    case 'review':
      return <ReviewCard invoice={invoice} onClose={onClose} />;
    case 'read':
      return <ReadCard invoice={invoice} onClose={onClose} />;
    case 'more':
      return <MoreCard invoice={invoice} onClose={onClose} />;
  }
}

/** Un hallazgo: que dice, que hacer y sus ordenes (aceptar con motivo, la segunda firma,
 *  cerrarlo si ya no se ve y, si es la lectura de un campo, verificarlo o cambiarlo ahi). */
function FindingCard({ finding: h, invoice, people, onClose }: { finding: Finding; invoice: InvoiceDetail; people: Person[]; onClose: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const { session } = useSession();
  const rule = ruleText(lang, h.regla);
  const detail = findingDetail(lang, h.regla, h.resultado, h.valores);
  const open = h.estado === 'abierto';
  const gone = h.estado === 'desaparecido';
  const colleagues = people.filter((p) => p.id !== session?.me.id);
  const needsSignature = h.segunda_firma && colleagues.length > 0;
  const mine = (h.firmas ?? []).find((f) => f.solicitante_id === session?.me.id) ?? null;
  const orders: OrderSpec[] = [];
  // Los campos a los que apunta, cuando el problema es la lectura de ese campo: dos como mucho.
  if (open && (h.calidad === 'dudoso' || h.calidad === 'faltante')) {
    const targets: FieldInfo[] = [];
    for (const o of h.objetivos) {
      if (!o.campo) continue;
      const field = findField(invoice, o.tabla, o.fila_id, o.campo);
      if (field && editableInApp(field) && !targets.includes(field)) targets.push(field);
    }
    for (const field of targets.slice(0, 2)) orders.push(...fieldOrders(t, lang, invoice, field, can, true).filter((o) => o.action !== 'revertir_campo'));
  }
  if (open && h.anulable && can('anular_aviso')) {
    orders.push({
      action: 'anular_hallazgo',
      label: t.invoice.accept,
      primary: true,
      intro: (
        <>
          <p>{t.invoice.acceptIntro}</p>
          {needsSignature && mine && (
            <p>
              {fmt(t.invoice.secondSignatureGiven, {
                name: mine.firmante ?? '—',
                time: formatDateTime(mine.caduca_en),
              })}
            </p>
          )}
        </>
      ),
      // Sin la firma de un colega el servidor lo negaria: no se deja mandar y se dice que hacer.
      blocked: needsSignature && !mine ? t.invoice.secondSignatureNeeded : undefined,
      fields: [
        {
          name: 'motivo',
          label: t.action.reason,
          kind: 'text',
          required: true,
          minLength: MIN_ACCEPT_REASON,
          help: fmt(t.invoice.acceptReasonHelp, { n: MIN_ACCEPT_REASON }),
        },
        {
          name: 'vigente_hasta',
          label: t.invoice.validUntil,
          kind: 'date',
          help: mine ? t.invoice.validUntilSigned : t.invoice.validUntilHelp,
          ...(mine?.vigente_hasta ? { initial: mine.vigente_hasta } : {}),
        },
      ],
      data: (v) => ({
        hallazgo_id: h.id,
        huella: h.huella,
        motivo: v.motivo,
        vigente_hasta: v.vigente_hasta || null,
      }),
    });
    if (needsSignature) {
      orders.push({
        action: 'firmar_anulacion',
        label: t.invoice.giveSecondSignature,
        intro: <p>{t.invoice.secondSignatureIntro}</p>,
        fields: [
          {
            name: 'solicitante_id',
            label: t.invoice.signFor,
            kind: 'select',
            required: true,
            initial: String(colleagues[0]!.id),
            options: colleagues.map((p) => ({
              value: String(p.id),
              label: p.nombre,
            })),
          },
          {
            name: 'motivo',
            label: t.action.reason,
            kind: 'text',
            required: true,
          },
          { name: 'vigente_hasta', label: t.invoice.validUntil, kind: 'date' },
        ],
        data: (v) => ({
          hallazgo_id: h.id,
          huella: h.huella,
          solicitante_id: Number(v.solicitante_id),
          motivo: v.motivo,
          vigente_hasta: v.vigente_hasta || null,
        }),
      });
    }
  }
  if (gone && can('resolver_aviso')) {
    orders.push({
      action: 'cerrar_hallazgo',
      label: t.invoice.close,
      primary: true,
      intro: <p>{t.invoice.closeIntro}</p>,
      fields: [
        {
          name: 'motivo',
          label: t.action.reason,
          kind: 'text',
          required: true,
        },
      ],
      data: (v) => ({ hallazgo_id: h.id, huella: h.huella, motivo: v.motivo }),
    });
  }
  return (
    <Detail title={rule?.title ?? h.regla} onClose={onClose}>
      {detail && <p>{detail}</p>}
      {rule && (
        <p>
          {t.invoice.whatToDo} {gone ? t.invoice.goneWhatToDo : rule.whatToDo}
        </p>
      )}
      <span>
        {[statusLabel(lang, t, 'severidad', h.severidad), gone ? statusLabel(lang, t, 'hallazgo', h.estado) : null].filter(Boolean).join(' · ')}{' '}
        <small title={t.invoice.ruleCodeHelp}>({h.regla})</small>
      </span>
      <Orders orders={orders} />
    </Detail>
  );
}

/** Un pago que el banco propuso: la linea al lado de la factura, confirmar o retirar. */
function ProposalCard({ invoice: f, paymentId, onClose }: { invoice: InvoiceDetail; paymentId: number; onClose: () => void }) {
  const { t } = useT();
  const can = useCan();
  const p = (f.pagos ?? []).find((x) => x.id === paymentId);
  if (!p) return null;
  const proposal = asProposal(p, f);
  return (
    <Detail title={t.aurora.sheet.payment} onClose={onClose}>
      <ProposalLines proposal={proposal} />
      <span>{t.bank.proposalsTitle}</span>
      <Orders orders={can('marcar_pagada') ? [confirmProposalOrder(t, proposal), withdrawOrder(t, p, t.payments.withdraw)] : []} />
    </Detail>
  );
}

/** Una relacion propuesta con otra factura: confirmar o rechazar, con motivo. */
function RelationCard({
  invoice: f,
  relationId,
  onClose,
  onOpenInvoice,
}: {
  invoice: InvoiceDetail;
  relationId: number;
  onClose: () => void;
  onOpenInvoice: (id: number) => void;
}) {
  const { t, lang } = useT();
  const can = useCan();
  const r = f.relaciones.find((x) => x.id === relationId);
  if (!r) return null;
  const verb = (catalogFor(lang).codigos as Record<string, string>)[r.tipo] ?? r.tipo;
  const otherId = r.papel === 'origen' ? r.destino_id : r.origen_id;
  const other = (r.papel === 'origen' ? r.destino_numero : r.origen_numero) ?? `#${otherId}`;
  const orders: OrderSpec[] = can('anular_acreditar')
    ? [
        {
          action: 'confirmar_relacion',
          label: t.relations.confirm,
          primary: true,
          fields: [
            {
              name: 'motivo',
              label: t.action.reason,
              kind: 'text',
              required: true,
            },
          ],
          data: (v) => ({ relacion_id: r.id, rev: r.rev, motivo: v.motivo }),
        },
        {
          action: 'rechazar_relacion',
          label: t.relations.reject,
          fields: [
            {
              name: 'motivo',
              label: t.action.reason,
              kind: 'text',
              required: true,
            },
          ],
          data: (v) => ({ relacion_id: r.id, rev: r.rev, motivo: v.motivo }),
        },
      ]
    : [];
  return (
    <Detail title={t.aurora.sheet.relation} onClose={onClose}>
      <p>
        {r.papel === 'origen' ? (
          <>
            {t.relations.thisInvoice} {verb} <span data-proper-name=''>{other}</span>
          </>
        ) : (
          <>
            <span data-proper-name=''>{other}</span> {verb} {t.relations.thisInvoiceObject}
          </>
        )}
        {r.importe_cent !== null && ` (${formatMoney(r.importe_cent)})`}
      </p>
      <p>
        {fmt(t.relations.source, {
          source: stateLabel(lang, 'fuente_relacion', r.fuente) ?? r.fuente,
        })}
      </p>
      {r.evidencia_doc && (
        <p>
          {t.relations.evidence} <span data-proper-name=''>{r.evidencia_doc}</span>
        </p>
      )}
      <span>{statusLabel(lang, t, 'relacion', r.estado)}</span>
      <Orders
        orders={orders}
        before={
          <button type='button' className='outline' onClick={() => onOpenInvoice(otherId)}>
            {fmt(t.aurora.sheet.openOther, { number: other })}
          </button>
        }
      />
    </Detail>
  );
}

/** La excepcion abierta: quien la lleva, a quien se espera y sus ordenes. */
function ExceptionCard({ invoice: f, people, onClose }: { invoice: InvoiceDetail; people: Person[]; onClose: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const { session } = useSession();
  const e = f.excepcion;
  if (!e) return null;
  return (
    <Detail title={t.invoice.exceptionStep} onClose={onClose}>
      <ExceptionLines exception={e} />
      <Orders orders={can('resolver_aviso') ? exceptionOrders(t, lang, e, people, session?.me.id) : []} />
    </Detail>
  );
}

/** La revision: marcarla revisada (con la huella de lo que se vio) o pedir otra. */
function ReviewCard({ invoice: f, onClose }: { invoice: InvoiceDetail; onClose: () => void }) {
  const { t } = useT();
  const can = useCan();
  const last = f.revisiones[0];
  const reviewed = f.estado?.estado_revision === 'revisada';
  const blocked = f.pide_revision.length > 0;
  const orders: OrderSpec[] = [];
  if (!reviewed && can('revisar_factura')) {
    if (!blocked) {
      orders.push({
        action: 'marcar_revisada',
        label: t.invoice.markReviewed,
        primary: true,
        intro: <p>{t.invoice.markReviewedIntro}</p>,
        fields: [{ name: 'motivo', label: t.action.note, kind: 'text' }],
        data: (v) => ({
          factura_id: f.id,
          huella: f.huella_contenido,
          motivo: v.motivo || undefined,
        }),
      });
    }
    orders.push({
      action: 'devolver_factura',
      label: t.invoice.returnInvoice,
      intro: <p>{t.invoice.returnIntro}</p>,
      fields: [
        {
          name: 'motivo',
          label: t.invoice.returnWhy,
          kind: 'text',
          required: true,
        },
      ],
      data: (v) => ({
        factura_id: f.id,
        huella: f.huella_contenido,
        motivo: v.motivo,
      }),
    });
  }
  return (
    <Detail title={t.invoice.reviewStep} onClose={onClose}>
      <p>
        {reviewed && last
          ? fmt(t.invoice.reviewedBy, {
              name: last.usuario ?? '—',
              date: formatDateProse(last.en, t),
            })
          : blocked
            ? t.invoice.reviewBlocked
            : t.invoice.reviewReady}
      </p>
      <Orders orders={orders} />
    </Detail>
  );
}

/** "Datos leidos": cada campo con su valor, su fuente y su calidad (lineas p); un campo se
 *  elige y se verifica, se cambia o se deshace su cambio. Las lineas, las referencias, la
 *  planificacion y los controles que no tuvieron datos, tambien en lineas p. */
function ReadCard({ invoice: f, onClose }: { invoice: InvoiceDetail; onClose: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const fields = visibleFields(f.campos);
  const editable = fields.filter((x) => editableInApp(x));
  const firstToCheck = editable.find((x) => NEEDS_CHECK.has(x.calidad ?? '') && !x.verificado) ?? editable[0];
  const [chosen, setChosen] = useState(firstToCheck?.campo ?? '');
  const field = editable.find((x) => x.campo === chosen);
  const lines = f.lineas.filter((l) => !l.retirada);
  const refs = f.referencias.filter((r) => !r.retirada);
  const shifts = f.conciliacion.flatMap((c) => c.turnos);
  const line = (name: string, l: (typeof lines)[number]) => {
    const x = l.campos.find((c) => c.campo === name);
    return x ? formatFieldValue(x, x.valor, lang) : null;
  };
  return (
    <Detail title={t.aurora.sheet.read} onClose={onClose}>
      {fields.map((x) => {
        const quality = qualityText(lang, x.calidad);
        return (
          <p key={x.campo} data-testid='field-line'>
            {fieldLabel(lang, x.tabla, x.campo) ?? x.campo}: <span data-proper-name=''>{formatFieldValue(x, x.valor, lang)}</span>
            {[sourceText(lang, x.fuente)?.label, quality?.label, x.editado && x.cambiado_por ? fmt(t.fields.changedBy, { name: x.cambiado_por }) : null]
              .filter(Boolean)
              .map((s) => ` · ${s}`)
              .join('')}
          </p>
        );
      })}
      {lines.length > 0 && <span>{t.sections.lines}</span>}
      {lines.map((l) => (
        <p key={`l${l.id}`}>
          <span data-proper-name=''>{String(l.campos.find((c) => c.campo === 'descripcion_doc')?.valor ?? '—')}</span>
          {[line('cantidad_mil', l), line('tarifa_e4', l), line('importe_cent', l)]
            .filter(Boolean)
            .map((s) => ` · ${s}`)
            .join('')}
          {l.imputaciones.filter((i) => !i.retirada).length > 0 &&
            ` · ${l.imputaciones
              .filter((i) => !i.retirada)
              .map((i) => [i.objeto, i.recurso].filter(Boolean).join(' · '))
              .join(', ')}`}
        </p>
      ))}
      {refs.length > 0 && <span>{t.sections.references}</span>}
      {refs.map((r) => (
        <p key={`r${r.id}`}>
          <span data-proper-name=''>{r.valor ?? '—'}</span> · {stateLabel(lang, 'clase_referencia', r.clase) ?? t.sections.unknownReference}
          {r.etiqueta ? ` · ${r.etiqueta}` : ''}
        </p>
      ))}
      {shifts.length > 0 && <span>{t.sections.planning}</span>}
      {shifts.map((s, i) => (
        <p key={`s${s.id_externo}-${i}`} data-testid='planning-line'>
          {formatDate(s.fecha)}
          {s.hora_inicio && s.hora_fin ? ` ${s.hora_inicio}–${s.hora_fin}` : ''} · <span data-proper-name=''>{s.id_externo}</span> · {s.objeto ?? '—'} ·{' '}
          {s.recurso ?? '—'} · {formatHours(s.horas_asignadas_mil)} · {statusLabel(lang, t, 'turno', s.estado)}
        </p>
      ))}
      {f.reglas_sin_datos.length > 0 && <span>{t.sections.noData}</span>}
      {f.reglas_sin_datos.map((r) => (
        <p key={`n${r.regla}-${r.clave}`}>
          {ruleText(lang, r.regla)?.title ?? r.regla}: {findingDetail(lang, r.regla, r.resultado, r.valores)}
        </p>
      ))}
      {editable.length > 0 && (
        <div className='order-form'>
          <FieldInput
            field={{
              name: 'campo',
              label: t.aurora.sheet.field,
              kind: 'select',
              hideOptional: true,
              options: editable.map((x) => ({
                value: x.campo,
                label: fieldLabel(lang, x.tabla, x.campo) ?? x.campo,
              })),
            }}
            value={chosen}
            onChange={setChosen}
          />
        </div>
      )}
      {field && <Orders key={field.campo} orders={fieldOrders(t, lang, f, field, can, false)} />}
    </Detail>
  );
}

/** "Pagos, notas e historial": cada pago con su fuente y su estado, las notas y lo que ha
 *  pasado; anotar un pago, retirar uno que no es de Exact, anadir una nota y abrir una
 *  excepcion (si no hay una abierta). */
function MoreCard({ invoice: f, onClose }: { invoice: InvoiceDetail; onClose: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const { session } = useSession();
  const { version } = useRefresh();
  const target = can('marcar_pagada') ? recordTargetOf(f) : null;
  const choices = useRecordChoices(target, target !== null);
  const [history] = useLoad(
    () => session!.api.get<{ historial: InvoiceHistory }>(paths.invoiceHistory(f.id)).then((r) => r.historial),
    [session, f.id, version]
  );
  const payments = paymentsInOrder(f.pagos ?? []);
  const orders: OrderSpec[] = [];
  if (target)
    orders.push({
      ...recordPaymentOrder(t, target, choices.lines, choices.evidence),
      primary: true,
    });
  if (can('marcar_pagada')) {
    for (const p of payments) {
      if (p.estado !== 'propuesta' && canWithdraw(p)) {
        orders.push(
          withdrawOrder(
            t,
            p,
            fmt(t.aurora.sheet.withdrawPayment, {
              date: formatDate(p.fecha_pago),
              amount: formatMoney(p.importe_cent),
            })
          )
        );
      }
    }
  }
  if (can('anadir_informacion')) {
    orders.push({
      action: 'anadir_nota',
      label: t.notes.add,
      fields: [
        {
          name: 'texto',
          label: t.notes.text,
          kind: 'text',
          required: true,
          help: t.notes.help,
        },
      ],
      data: (v) => ({ tabla: 'factura', fila_id: f.id, texto: v.texto }),
    });
  }
  if ((!f.excepcion || f.excepcion.estado === 'resuelta') && can('resolver_aviso')) {
    orders.push({
      action: 'crear_excepcion',
      label: t.invoice.openException,
      fields: [
        {
          name: 'titulo',
          label: t.invoice.exceptionSubject,
          kind: 'text',
          required: true,
        },
        { name: 'motivo', label: t.invoice.exceptionWhy, kind: 'text' },
      ],
      data: (v) => ({
        tabla: 'factura',
        fila_id: f.id,
        titulo: v.titulo,
        motivo: v.motivo || undefined,
      }),
    });
  }
  const evidence = payments.filter((p) => p.evidencia_documento_id);
  const entries = history.status === 'ready' ? historyEntries(history.data, f, t, lang) : [];
  return (
    <Detail title={t.aurora.sheet.more} onClose={onClose}>
      <span>{t.payments.title}</span>
      {payments.length === 0 && <p>{t.payments.none}</p>}
      {payments.map((p) => (
        <p key={p.id} data-testid='payment-line'>
          {[
            formatDate(p.fecha_pago),
            formatMoney(p.importe_cent),
            stateLabel(lang, 'fuente_aplicacion', p.fuente) ?? p.fuente,
            stateLabel(lang, 'aplicacion', p.estado) ?? p.estado,
          ].join(' · ')}
          {p.persona && (
            <>
              {' · '}
              <span data-proper-name=''>{p.persona}</span>
            </>
          )}
          {p.motivo && (
            <>
              {' · '}
              <span data-proper-name=''>{p.motivo}</span>
            </>
          )}
          {p.estado === 'retirada' && p.motivo_retirada && (
            <>
              {' · '}
              <span data-proper-name=''>{p.motivo_retirada}</span>
            </>
          )}
          {p.fuente === 'exact' && p.estado !== 'retirada' && ` · ${t.payments.exactNote}`}
        </p>
      ))}
      <span>{t.sections.notes}</span>
      {f.notas.length === 0 && <p>{t.sections.noNotes}</p>}
      {f.notas.map((n) => (
        <p key={n.id}>
          <span data-proper-name=''>{n.texto}</span> · {n.usuario ?? '—'} · {formatDateTime(n.en)}
        </p>
      ))}
      <span>{t.sections.history}</span>
      {history.status === 'error' && <ErrorLine error={history.error} message={apiErrorMessage(history.error, t, lang)} />}
      {history.status === 'ready' && entries.length === 0 && <p>{t.history.empty}</p>}
      {entries.slice(0, 12).map((e, i) => (
        <p key={i}>
          {formatDateTime(e.at)} · {e.text}
          {e.who && ` · ${e.who}`}
          {e.note && (
            <>
              {' · '}
              <span data-proper-name=''>“{e.note}”</span>
            </>
          )}
        </p>
      ))}
      <Orders
        orders={orders}
        before={
          evidence.length > 0 &&
          session &&
          evidence.map((p) => (
            <button
              key={p.id}
              type='button'
              className='outline'
              onClick={() => void session.api.download(paths.documentOriginal(p.evidencia_documento_id!), `justificante-${p.id}`)}
            >
              {t.payments.evidence} · {formatDate(p.fecha_pago)}
            </button>
          ))
        }
      />
    </Detail>
  );
}
