// Lo que se abre en el <dialog> de Documentos (document-workspace.tsx:42 del dueno): la parte de
// arriba (ws-dialog-top, con su ✕), la hoja clara dibujada desde el registro (ws-paper, con su
// marca, la marca de agua solo en la base de prueba, el h2, la empresa, la marca de la ultima
// lectura, una dl y el aviso de abajo) y "Descargar original" (ws-download, la descarga
// auditada). Aqui, ademas, las tres hojas que no son una factura (especificacion §2.3): un
// documento de la carpeta (un justificante, la hoja de una PO), un Object (margen, horas y lo
// facturado) y una orden de compra (lo pedido, lo facturado y lo que queda). Sin ordenes: hoy
// tampoco las tienen. Sus facturas, en la tabla de la ficha (ws-file-table), abren su hoja.
import { ChevronRight, Download, FileText, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { fmt, useT, type Messages } from '@/i18n';
import { paymentStateLabel, ruleText, stateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { ObjectInvoice, ObjectView, PartyDocument, PoView } from '@/lib/api-types';
import { NO_VALUE, formatDate, formatDateProse, formatHours, formatMoney, formatPercentFromBasisPoints } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { statusLabel } from '@/components/status-pill';
import { apiErrorMessage, ErrorLine } from '../orders';
import { useOriginalDownload } from '../panels/invoice-card';
import { useLoad } from '../use-load';
import type { AnalysisStatus } from './analysis';
import { invoiceIdOf, purchaseOrderIdOf, type Side } from './documents-model';

/** El nombre de un tipo de documento ("Factura de compra"). */
export function typeLabel(t: Messages, tipo: string): string {
  return (t.documents.types as Record<string, string>)[tipo] ?? tipo;
}

/** Un documento por su nombre: el tipo y su numero. */
export function docName(t: Messages, d: Pick<PartyDocument, 'tipo' | 'numero'>): string {
  return d.numero ? `${typeLabel(t, d.tipo)} ${d.numero}` : typeLabel(t, d.tipo);
}

/** ws-dialog-top: lo que es y su estado, en mayusculas, y la ✕. */
export function SheetTop({ label, onClose }: { label: string; onClose: () => void }) {
  const { t } = useT();
  return (
    <div className='ws-dialog-top'>
      <span>{label.toLocaleUpperCase()}</span>
      <button autoFocus aria-label={t.aurora.archive.closePreview} onClick={onClose}>
        <X size={19} />
      </button>
    </div>
  );
}

/** La marca de la ultima lectura en la hoja: nueva (verde) o repetida (naranja). */
export function FileAnalysis({ status }: { status: AnalysisStatus }) {
  const { t } = useT();
  const a = t.aurora.archive;
  return (
    <div className={'ws-file-analysis ' + status} data-testid='file-analysis'>
      <strong>{status === 'new' ? a.freshTitle : a.repeatedTitle}</strong>
      <p>{status === 'new' ? a.freshNote : a.repeatedNote}</p>
    </div>
  );
}

/** La hoja clara dibujada desde el registro (ws-paper): su dl va en `children`. */
export function Paper({ title, subtitle, analysis, children }: { title: string; subtitle?: string | null; analysis?: AnalysisStatus; children: ReactNode }) {
  const { t } = useT();
  const { session } = useSession();
  return (
    <div className='ws-paper' data-testid='paper'>
      <span className='ws-paper-brand'>
        BMS // <small>finance</small>
      </span>
      {session?.environment === 'demo' && (
        <div className='ws-watermark' aria-hidden='true'>
          {t.aurora.archive.watermark}
        </div>
      )}
      <FileText size={26} />
      <h2 data-proper-name=''>{title}</h2>
      {subtitle && <p data-proper-name=''>{subtitle}</p>}
      {analysis && <FileAnalysis status={analysis} />}
      <hr />
      <dl>{children}</dl>
      <p className='ws-paper-disclaimer'>{t.aurora.archive.drawn}</p>
    </div>
  );
}

/** Un dato de la hoja: dt y dd. */
export function Fact({ label, children, data }: { label: string; children: ReactNode; data?: boolean }) {
  return (
    <>
      <dt>{label}</dt>
      <dd data-proper-name={data ? '' : undefined}>{children}</dd>
    </>
  );
}

/** ws-download: "Descargar original" (queda en la auditoria como documento_abierto). */
export function DownloadOriginal({ path, name, kept }: { path: string; name: string; kept: boolean }) {
  const { t, lang } = useT();
  const original = useOriginalDownload();
  if (!kept) return <p className='ws-paper-disclaimer'>{t.documents.notKept}</p>;
  return (
    <>
      <button className='ws-download' disabled={original.busy} onClick={() => void original.download(path, name)}>
        <Download size={15} /> {t.aurora.card.downloadOriginal}
      </button>
      {original.error !== null && <ErrorLine error={original.error} message={apiErrorMessage(original.error, t, lang)} />}
    </>
  );
}

/** Una fila de la tabla de la ficha o de la hoja (.ws-file-table>a): icono, strong, small, la
 *  em de su estado y la flecha. Un <a> sin href (cambio R): se abre con el raton o el teclado. */
export function FileRow({
  title,
  note,
  status,
  tone,
  data,
  current,
  label,
  onOpen,
}: {
  title: string;
  note?: string;
  status?: string;
  tone?: AnalysisStatus;
  data?: boolean;
  current?: boolean;
  label?: string;
  onOpen: () => void;
}) {
  const toneClass = tone ? 'status-' + tone : undefined;
  return (
    <a
      role='button'
      tabIndex={0}
      aria-label={label}
      aria-current={current ? 'true' : undefined}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <FileText size={17} className={toneClass} />
      <span>
        <strong className={toneClass} data-proper-name={data ? '' : undefined}>
          {title}
        </strong>
        {note && <small data-proper-name={data ? '' : undefined}>{note}</small>}
        {status && <em className={'file-status' + (toneClass ? ' ' + toneClass : '')}>{status}</em>}
      </span>
      <ChevronRight size={15} />
    </a>
  );
}

/** La cabecera de una tabla de la ficha o de la hoja (ws-table-head) y sus filas. */
export function FileTable({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <div className='ws-file-table'>
      <div className='ws-table-head'>
        <span>{title}</span>
        {count !== undefined && <span>{count}</span>}
      </div>
      {children}
    </div>
  );
}

/** La hoja de un documento que no es una factura (un justificante, la hoja de una PO). */
export function DocumentSheet({
  doc,
  side,
  partyName,
  analysis,
  onClose,
  onOpenInvoice,
  onOpenPo,
}: {
  doc: PartyDocument;
  side: Side;
  partyName: string | null;
  analysis?: AnalysisStatus;
  onClose: () => void;
  onOpenInvoice: (id: number) => void;
  onOpenPo: (id: number) => void;
}) {
  const { t, lang } = useT();
  const name = docName(t, doc);
  const invoice = invoiceIdOf(doc);
  const po = purchaseOrderIdOf(doc);
  const kind = side === 'client' ? t.documents.kindClient : t.documents.kindProvider;
  return (
    <>
      <SheetTop label={[typeLabel(t, doc.tipo), paymentStateLabel(lang, doc.estado_pago)].filter(Boolean).join(' · ')} onClose={onClose} />
      <Paper title={name} subtitle={partyName} analysis={analysis}>
        {doc.tipo === 'justificante_pago' ? (
          <>
            <Fact label={t.documents.paymentDate}>{formatDate(doc.fecha)}</Fact>
            <Fact label={t.columns.amount}>{formatMoney(doc.importe_cent)}</Fact>
            <Fact label={t.documents.paymentState}>
              {[stateLabel(lang, 'aplicacion', doc.vinculo.estado), stateLabel(lang, 'fuente_aplicacion', doc.vinculo.fuente)].filter(Boolean).join(' · ') || NO_VALUE}
            </Fact>
          </>
        ) : (
          <>
            <Fact label={t.documents.number} data>
              {doc.numero ?? NO_VALUE}
            </Fact>
            <Fact label={kind} data>
              {partyName ?? NO_VALUE}
            </Fact>
            <Fact label={t.documents.date}>{formatDate(doc.fecha)}</Fact>
            <Fact label={t.documents.value}>{formatMoney(doc.importe_cent)}</Fact>
          </>
        )}
        <Fact label={t.documents.file} data>
          {doc.nombre ?? NO_VALUE}
        </Fact>
        {doc.registrado_en && <Fact label={t.documents.state}>{fmt(t.documents.received, { date: formatDate(doc.registrado_en) })}</Fact>}
      </Paper>
      <DownloadOriginal path={paths.documentOriginal(doc.id)} name={doc.nombre ?? `${doc.numero ?? doc.id}.pdf`} kept={doc.guardado} />
      {invoice !== null && (
        <button className='outline' onClick={() => onOpenInvoice(invoice)}>
          {t.documents.openInvoice}
        </button>
      )}
      {invoice === null && po !== null && (
        <button className='outline' onClick={() => onOpenPo(po)}>
          {t.documents.openPo}
        </button>
      )}
    </>
  );
}

/** Las facturas de un Object o de una PO, en la tabla de su hoja: cada una abre la suya. */
function InvoiceRows({ title, rows, onOpenInvoice }: { title: string; rows: { id: number; numero: string | null; note: string }[]; onOpenInvoice: (id: number) => void }) {
  const { t } = useT();
  if (rows.length === 0) return null;
  return (
    <FileTable title={title} count={rows.length}>
      {rows.map((r) => (
        <FileRow
          key={r.id}
          title={r.numero ?? fmt(t.records.invoice.fallbackTitle, { id: r.id })}
          note={r.note}
          data
          label={fmt(t.common.openRecord, { what: `${t.records.invoice.label} ${r.numero ?? r.id}` })}
          onOpen={() => onOpenInvoice(r.id)}
        />
      ))}
    </FileTable>
  );
}

function objectInvoiceNote(lang: Parameters<typeof paymentStateLabel>[0], f: ObjectInvoice): string {
  return [f.contraparte, formatDate(f.fecha_factura), formatMoney(f.importe_objeto_cent), paymentStateLabel(lang, f.estado_pago)].filter((s) => s && s !== NO_VALUE).join(' · ');
}

/** La hoja de un Object: de que cliente, lo que entra, lo que cuesta, el margen y las horas de
 *  este mes (/api/v2/objetos/N), y sus facturas. */
export function ObjectSheet({ id, onClose, onOpenInvoice }: { id: number; onClose: () => void; onOpenInvoice: (id: number) => void }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state] = useLoad(() => session!.api.get<{ objeto: ObjectView }>(paths.object(id)).then((r) => r.objeto), [session, id, version]);
  if (state.status !== 'ready') {
    return (
      <>
        <SheetTop label={t.records.object.label} onClose={onClose} />
        {state.status === 'error' && <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} />}
      </>
    );
  }
  const o = state.data;
  const e = o.economia.periodo;
  const total = o.horas.total;
  const period = `${formatDate(e.desde)} – ${formatDate(e.hasta)} · ${t.objects.exclVat}`;
  const rows = [...o.facturas.salientes, ...o.facturas.entrantes].map((f) => ({ id: f.id, numero: f.numero, note: objectInvoiceNote(lang, f) }));
  return (
    <>
      <SheetTop label={[t.records.object.label, statusLabel(lang, t, 'prioridad', o.prioridad.nivel)].filter(Boolean).join(' · ')} onClose={onClose} />
      <Paper title={o.codigo} subtitle={o.nombre}>
        <Fact label={t.records.client.label} data>
          {o.cliente?.nombre ?? t.objects.noClient}
        </Fact>
        <Fact label={t.objects.revenueFact}>
          {formatMoney(e.ingresos_cent)}
          <small> · {period}</small>
        </Fact>
        <Fact label={t.objects.costsFact}>{formatMoney(e.costes_cent)}</Fact>
        <Fact label={t.objects.marginFact}>
          {formatMoney(e.margen_cent)}
          {e.margen_pb !== null && <small> · {formatPercentFromBasisPoints(e.margen_pb)}</small>}
        </Fact>
        <Fact label={t.objects.hoursFact}>
          {o.horas.planning === 'ok' && total
            ? `${fmt(t.objects.hoursPlanned, { hours: formatHours(total.planificadas_mil) })} · ${fmt(t.objects.hoursBilled, { hours: formatHours(total.cliente_mil) })}`
            : t.parties.noPlanning}
        </Fact>
        <Fact label={t.objects.sectionPos}>{o.ordenes_compra.length ? o.ordenes_compra.map((p) => p.numero).join(', ') : t.objects.noPos}</Fact>
        {o.requiere_po && <Fact label={t.records['purchase-order'].label}>{t.objects.poRequired}</Fact>}
      </Paper>
      <InvoiceRows title={t.objects.sectionSales} rows={rows} onOpenInvoice={onOpenInvoice} />
    </>
  );
}

/** La hoja de una orden de compra: lo pedido, lo facturado, lo que queda y la prevision
 *  (/api/v2/ordenes/N), y sus facturas. */
export function PoSheet({ id, onClose, onOpenInvoice }: { id: number; onClose: () => void; onOpenInvoice: (id: number) => void }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state] = useLoad(() => session!.api.get<{ orden: PoView }>(paths.purchaseOrder(id)).then((r) => r.orden), [session, id, version]);
  if (state.status !== 'ready') {
    return (
      <>
        <SheetTop label={t.records['purchase-order'].label} onClose={onClose} />
        {state.status === 'error' && <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} />}
      </>
    );
  }
  const po = state.data;
  const runsOut = po.prevision?.agotamiento ?? null;
  const beforeEnd = runsOut && (!po.fecha_fin || runsOut <= po.fecha_fin);
  const rows = po.facturas.map((f) => ({
    id: f.factura_id,
    numero: f.numero,
    note: [formatDate(f.fecha_factura), formatMoney(f.importe_cent), `${t.pos.leftAfter}: ${formatMoney(f.quedaba_cent)}`].join(' · '),
  }));
  return (
    <>
      <SheetTop label={[t.records['purchase-order'].label, statusLabel(lang, t, 'prioridad', po.prioridad.nivel)].filter(Boolean).join(' · ')} onClose={onClose} />
      <Paper
        title={po.numero}
        subtitle={fmt(po.lado === 'cliente' ? t.pos.fromClient : t.pos.toProvider, {
          party: po.parte.nombre ?? '—',
          from: formatDateProse(po.fecha_inicio ?? po.fecha_emision, t),
          to: po.fecha_fin ? formatDateProse(po.fecha_fin, t) : t.pos.noEnd,
        })}
      >
        <Fact label={t.pos.value}>
          {formatMoney(po.valor_cent)}
          {po.valor_original_cent !== po.valor_cent && <small> · {fmt(t.pos.changedFrom, { value: formatMoney(po.valor_original_cent) })}</small>}
        </Fact>
        <Fact label={t.pos.used}>
          {formatMoney(po.consumido_cent)}
          <small> · {fmt(t.pos.usedShare, { pct: formatPercentFromBasisPoints(po.consumido_pb) })}</small>
        </Fact>
        <Fact label={t.pos.left}>
          {formatMoney(po.restante_cent)}
          <small> · {po.fecha_fin ? fmt(t.pos.until, { date: formatDate(po.fecha_fin) }) : t.pos.noEnd}</small>
        </Fact>
        <Fact label={t.pos.forecast}>{runsOut ? (beforeEnd ? fmt(t.pos.runsOut, { date: formatDate(runsOut) }) : t.pos.lasts) : t.pos.tooEarly}</Fact>
        <Fact label={t.pos.sectionObjects}>{po.objetos.length ? po.objetos.map((o) => o.codigo).join(', ') : t.pos.noObjects}</Fact>
        <Fact label={t.documents.warnings}>
          {po.avisos.hallazgos.filter((h) => h.estado === 'abierto').map((h) => ruleText(lang, h.regla)?.title ?? h.regla).join(' · ') || t.documents.noWarnings}
        </Fact>
        {po.cerrada && <Fact label={t.vat.status}>{t.pos.closedNote}</Fact>}
      </Paper>
      <InvoiceRows title={t.pos.sectionInvoices} rows={rows} onOpenInvoice={onOpenInvoice} />
    </>
  );
}
