// Los detalles plegados de la ficha de una factura: regels, referencias y PO, koppelingen
// (con confirmar o rechazar lo propuesto), planning, notas, controles sin datos, historia
// en palabras normales y el documento original. Lo escrito por personas y lo que viene de
// un documento (descripciones, referencias, nombres, notas) se pinta tal cual, como texto.
import { Download, FileText } from 'lucide-react';
import { useState } from 'react';
import { ActionButton } from '@/components/action-dialog';
import { errorMessage, ErrorState, Loading, TechnicalDetail } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import { useNav } from '@/shell/navigation';
import { DateText, Hours, Money } from '@/components/values';
import { LOCALES, fmt, useT, type Lang, type Messages } from '@/i18n';
import { catalogFor, fieldLabel, findingDetail, ruleText, stateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { FieldInfo, InvoiceDetail, InvoiceHistory } from '@/lib/api-types';
import { formatFieldValue } from '@/lib/field-format';
import { formatDateTime } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

const cell = 'px-3 py-2 align-top';
const head = 'px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

function field(fields: FieldInfo[], name: string): FieldInfo | undefined {
  return fields.find((f) => f.campo === name);
}

export function LinesTable({ invoice }: { invoice: InvoiceDetail }) {
  const { t, lang } = useT();
  const lines = invoice.lineas.filter((l) => !l.retirada);
  if (!lines.length) return <p className='text-muted-foreground'>{t.sections.noLines}</p>;
  const show = (f: FieldInfo | undefined) => (f ? formatFieldValue(f, f.valor, lang) : '—');
  return (
    <div className='overflow-x-auto rounded-md border border-border bg-card'>
      <table className='w-full border-collapse text-left text-[13px]'>
        <caption className='sr-only'>{t.sections.lines}</caption>
        <thead>
          <tr className='border-b border-border bg-table-head'>
            <th scope='col' className={head}>{t.lines.description}</th>
            <th scope='col' className={`${head} text-right`}>{t.lines.quantity}</th>
            <th scope='col' className={`${head} text-right`}>{t.lines.rate}</th>
            <th scope='col' className={`${head} text-right`}>{t.lines.amount}</th>
            <th scope='col' className={head}>{t.lines.object}</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l) => {
            const unit = field(l.campos, 'unidad_doc')?.valor;
            const imp = l.imputaciones.filter((i) => !i.retirada);
            return (
              <tr key={l.id} className='border-b border-divider last:border-b-0'>
                <td className={cell}>{String(field(l.campos, 'descripcion_doc')?.valor ?? '—')}</td>
                <td className={`${cell} num text-right whitespace-nowrap`}>
                  {show(field(l.campos, 'cantidad_mil'))}
                  {typeof unit === 'string' && unit ? ` ${unit}` : ''}
                </td>
                <td className={`${cell} num text-right whitespace-nowrap`}>{show(field(l.campos, 'tarifa_e4'))}</td>
                <td className={`${cell} num text-right whitespace-nowrap`}>{show(field(l.campos, 'importe_cent'))}</td>
                <td className={cell}>
                  {imp.length
                    ? imp.map((i) => [i.objeto, i.recurso].filter(Boolean).join(' · ')).join(', ')
                    : t.lines.noObject}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ReferencesList({ invoice }: { invoice: InvoiceDetail }) {
  const { t, lang } = useT();
  const refs = invoice.referencias.filter((r) => !r.retirada);
  if (!refs.length) return <p className='text-muted-foreground'>{t.sections.noReferences}</p>;
  return (
    <ul className='flex flex-col gap-1.5'>
      {refs.map((r) => (
        <li key={r.id} className='flex flex-wrap items-baseline gap-x-2'>
          <span className='font-mono text-[12.5px]'>{r.valor ?? '—'}</span>
          <span className='text-muted-foreground'>
            {stateLabel(lang, 'clase_referencia', r.clase) ?? t.sections.unknownReference}
            {r.etiqueta ? ` · ${r.etiqueta}` : ''}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function RelationsList({ invoice, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const { open: openRoute } = useNav();
  const relations = invoice.relaciones.filter((r) => !r.retirada);
  if (!relations.length) return <p className='text-muted-foreground'>{t.sections.noRelations}</p>;
  const codes = catalogFor(lang).codigos as Record<string, string>;
  return (
    <ul className='flex flex-col gap-3'>
      {relations.map((r) => {
        const otherId = r.papel === 'origen' ? r.destino_id : r.origen_id;
        const otherNumber = r.papel === 'origen' ? r.destino_numero : r.origen_numero;
        const verb = codes[r.tipo] ?? r.tipo;
        const other = (
          <Button
            variant='link'
            size='sm'
            className='h-auto px-0 py-0 font-mono text-[12.5px]'
            onClick={() => openRoute(recordRoute('invoice', otherId))}
          >
            {otherNumber ?? `#${otherId}`}
          </Button>
        );
        return (
          <li key={r.id} className='rounded-md border border-border bg-card px-4 py-3'>
            <p className='flex flex-wrap items-baseline gap-x-1.5'>
              {r.papel === 'origen' ? (
                <>
                  <span>{t.relations.thisInvoice}</span>
                  <span>{verb}</span>
                  {other}
                </>
              ) : (
                <>
                  {other}
                  <span>{verb}</span>
                  <span>{t.relations.thisInvoiceObject}</span>
                </>
              )}
              {r.importe_cent !== null && (
                <span className='text-muted-foreground'>
                  (<Money cents={r.importe_cent} />)
                </span>
              )}
            </p>
            <div className='mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground'>
              <StatusPill group='relacion' state={r.estado} />
              <span>{fmt(t.relations.source, { source: stateLabel(lang, 'fuente_relacion', r.fuente) ?? r.fuente })}</span>
            </div>
            {r.evidencia_doc && (
              <p className='mt-1 text-xs text-muted-foreground'>
                {t.relations.evidence} <span className='text-foreground'>{r.evidencia_doc}</span>
              </p>
            )}
            {r.estado === 'propuesta' && can('anular_acreditar') && (
              <div className='mt-3 flex flex-wrap gap-2'>
                <ActionButton
                  action='confirmar_relacion'
                  label={t.relations.confirm}
                  variant='default'
                  fields={[{ name: 'motivo', label: t.action.reason, kind: 'textarea', required: true }]}
                  data={(v) => ({ relacion_id: r.id, rev: r.rev, motivo: v.motivo })}
                  onDone={onDone}
                />
                <ActionButton
                  action='rechazar_relacion'
                  label={t.relations.reject}
                  fields={[{ name: 'motivo', label: t.action.reason, kind: 'textarea', required: true }]}
                  data={(v) => ({ relacion_id: r.id, rev: r.rev, motivo: v.motivo })}
                  onDone={onDone}
                />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function PlanningTable({ invoice }: { invoice: InvoiceDetail }) {
  const { t } = useT();
  const shifts = invoice.conciliacion.flatMap((c) => c.turnos);
  if (!shifts.length) return <p className='text-muted-foreground'>{t.sections.noPlanning}</p>;
  return (
    <div className='overflow-x-auto rounded-md border border-border bg-card'>
      <table className='w-full border-collapse text-left text-[13px]'>
        <caption className='sr-only'>{t.sections.planning}</caption>
        <thead>
          <tr className='border-b border-border bg-table-head'>
            <th scope='col' className={head}>{t.planning.date}</th>
            <th scope='col' className={head}>{t.planning.shift}</th>
            <th scope='col' className={head}>{t.planning.object}</th>
            <th scope='col' className={head}>{t.planning.person}</th>
            <th scope='col' className={`${head} text-right`}>{t.planning.hours}</th>
            <th scope='col' className={head}>{t.planning.status}</th>
          </tr>
        </thead>
        <tbody>
          {shifts.map((s, i) => (
            <tr key={`${s.id_externo}-${i}`} className='border-b border-divider last:border-b-0'>
              <td className={cell}>
                <DateText value={s.fecha} />
                {s.hora_inicio && s.hora_fin && (
                  <span className='ml-2 text-xs text-muted-foreground'>
                    {s.hora_inicio}–{s.hora_fin}
                  </span>
                )}
              </td>
              <td className={`${cell} font-mono text-[12px]`}>{s.id_externo}</td>
              <td className={cell}>{s.objeto ?? '—'}</td>
              <td className={cell}>{s.recurso ?? '—'}</td>
              <td className={`${cell} text-right`}>
                <Hours mil={s.horas_asignadas_mil} />
              </td>
              <td className={cell}>
                <StatusPill group='turno' state={s.estado} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function NotesList({ invoice, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const { t } = useT();
  return (
    <div className='flex flex-col gap-3'>
      {invoice.notas.length === 0 ? (
        <p className='text-muted-foreground'>{t.sections.noNotes}</p>
      ) : (
        <ul className='flex flex-col gap-2'>
          {invoice.notas.map((n) => (
            <li key={n.id} className='rounded-md border border-border bg-card px-3 py-2'>
              <p className='whitespace-pre-wrap'>{n.texto}</p>
              <p className='mt-1 text-xs text-muted-foreground'>
                {n.usuario ?? '—'} · {formatDateTime(n.en)}
              </p>
            </li>
          ))}
        </ul>
      )}
      <AddNoteButton invoiceId={invoice.id} onDone={onDone} />
    </div>
  );
}

export function AddNoteButton({ invoiceId, onDone }: { invoiceId: number; onDone: () => void }) {
  const { t } = useT();
  const can = useCan();
  if (!can('anadir_informacion')) return null;
  return (
    <div>
      <ActionButton
        action='anadir_nota'
        label={t.notes.add}
        fields={[{ name: 'texto', label: t.notes.text, kind: 'textarea', required: true, help: t.notes.help }]}
        data={(v) => ({ tabla: 'factura', fila_id: invoiceId, texto: v.texto })}
        onDone={onDone}
      />
    </div>
  );
}

export function NoDataList({ invoice }: { invoice: InvoiceDetail }) {
  const { t, lang } = useT();
  if (!invoice.reglas_sin_datos.length) return <p className='text-muted-foreground'>{t.sections.allChecked}</p>;
  return (
    <ul className='flex flex-col gap-2'>
      {invoice.reglas_sin_datos.map((r) => (
        <li key={`${r.regla}-${r.clave}`}>
          <span className='font-medium'>{ruleText(lang, r.regla)?.title ?? r.regla}</span>{' '}
          <span className='font-mono text-[11px] text-muted-foreground'>{r.regla}</span>
          <p className='text-[13px] text-soft-foreground'>{findingDetail(lang, r.regla, r.resultado, r.valores)}</p>
        </li>
      ))}
    </ul>
  );
}

// ---- la historia, en palabras normales

interface HistoryEntry {
  at: string;
  text: string;
  who: string | null;
  note: string | null;
}

/** De la historia de la API, una lista de frases: cada cosa que paso, quien y por que. */
export function historyEntries(h: InvoiceHistory, invoice: InvoiceDetail, t: Messages, lang: Lang): HistoryEntry[] {
  const out: HistoryEntry[] = [];
  if (h.documento?.recibido_en) out.push({ at: h.documento.recibido_en, text: t.history.received, who: null, note: null });
  for (const e of h.extracciones) {
    if (e.extraido_en) out.push({ at: e.extraido_en, text: t.history.read, who: null, note: null });
  }
  for (const finding of h.hallazgos) {
    const title = ruleText(lang, finding.regla)?.title ?? finding.regla;
    for (const ev of finding.eventos) {
      const what = stateLabel(lang, 'evento_hallazgo', ev.tipo) ?? ev.tipo;
      out.push({ at: ev.en, text: `${title}: ${what.toLocaleLowerCase(LOCALES[lang])}`, who: ev.usuario, note: ev.nota });
    }
  }
  for (const r of h.revisiones) {
    out.push({
      at: r.en,
      text: r.resultado === 'revisada' ? t.history.reviewed : t.history.returned,
      who: r.usuario,
      note: r.nota,
    });
  }
  for (const x of h.excepciones) {
    if (x.creada_en) out.push({ at: x.creada_en, text: t.history.exceptionOpened, who: null, note: null });
    if (x.resuelta_en) {
      out.push({
        at: x.resuelta_en,
        text: fmt(t.history.exceptionResolved, { how: stateLabel(lang, 'resolucion', x.resolucion) ?? '—' }),
        who: x.resuelta_por,
        note: null,
      });
    }
  }
  for (const n of h.notas) out.push({ at: n.en, text: t.history.note, who: n.usuario, note: n.texto });
  for (const e of h.eventos) {
    if (!e.persona) continue;
    for (const c of e.cambios) {
      const def = invoice.campos.find((f) => f.campo === c.campo && c.tabla === 'factura');
      const label = fieldLabel(lang, c.tabla, c.campo) ?? c.campo;
      const show = (text: string | null) => (def && text !== null ? formatFieldValue(def, text, lang) : (text ?? '—'));
      out.push({
        at: e.en,
        text: fmt(t.history.changed, { field: label, from: show(c.anterior_texto), to: show(c.nuevo_texto) }),
        who: e.usuario,
        note: e.motivo,
      });
    }
    if (e.tipo === 'documento_abierto') out.push({ at: e.en, text: t.history.opened, who: e.usuario, note: null });
  }
  return out.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}

export function HistoryList({ invoice }: { invoice: InvoiceDetail }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () => session!.api.get<{ historial: InvoiceHistory }>(paths.invoiceHistory(invoice.id)).then((r) => r.historial),
    [session, invoice.id, version]
  );
  if (state.status === 'loading') return <Loading />;
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={retry} />;
  const entries = historyEntries(state.data, invoice, t, lang);
  if (!entries.length) return <p className='text-muted-foreground'>{t.history.empty}</p>;
  return (
    <ol className='flex flex-col gap-2 border-l border-border pl-4'>
      {entries.map((e, i) => (
        <li key={i} className='text-[13px]'>
          <span className='mr-2 whitespace-nowrap text-xs text-muted-foreground'>{formatDateTime(e.at)}</span>
          <span>{e.text}</span>
          {e.who && <span className='text-muted-foreground'> · {e.who}</span>}
          {e.note && <span className='block whitespace-pre-wrap text-soft-foreground'>“{e.note}”</span>}
        </li>
      ))}
    </ol>
  );
}

/** "Origineel" arriba en la ficha (paso 16, revision §5: el original de una factura en tres
 *  clics). La misma descarga auditada que la de la seccion plegada; sin original guardado no
 *  sale. Un error lo dice debajo del boton. */
export function OriginalButton({ invoice }: { invoice: InvoiceDetail }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!invoice.original?.guardado) return null;
  async function download() {
    setBusy(true);
    setError(null);
    try {
      await session!.api.download(paths.invoiceOriginal(invoice.id), `${invoice.numero ?? 'factuur'}.pdf`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className='flex flex-col items-end gap-1'>
      <Button variant='outline' size='sm' onClick={download} disabled={busy}>
        <Download className='mr-2 h-4 w-4' aria-hidden='true' />
        {t.original.short}
      </Button>
      {error !== null && (
        <p role='alert' className='max-w-xs text-right text-xs text-late-foreground'>
          {errorMessage(error, t, lang)}
        </p>
      )}
    </div>
  );
}

export function OriginalDocument({ invoice }: { invoice: InvoiceDetail }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const doc = invoice.original;
  if (!doc) return <p className='text-muted-foreground'>{t.original.none}</p>;
  if (!doc.guardado) return <p className='text-muted-foreground'>{t.original.notKept}</p>;
  async function download() {
    setBusy(true);
    setError(null);
    try {
      await session!.api.download(paths.invoiceOriginal(invoice.id), `${invoice.numero ?? 'factuur'}.pdf`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className='flex flex-col items-start gap-2'>
      <p className='flex items-center gap-2'>
        <FileText className='h-4 w-4 text-muted-foreground' aria-hidden='true' />
        <span>{doc.nombre ?? t.original.document}</span>
      </p>
      <p className='text-xs text-muted-foreground'>{t.original.audited}</p>
      <Button variant='outline' size='sm' onClick={download} disabled={busy}>
        <Download className='mr-2 h-4 w-4' aria-hidden='true' />
        {t.original.download}
      </Button>
      {error !== null && (
        <div role='alert' className='text-[13px] text-late-foreground'>
          <p>{errorMessage(error, t, lang)}</p>
          <TechnicalDetail error={error} />
        </div>
      )}
    </div>
  );
}
