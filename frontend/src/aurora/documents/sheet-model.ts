// La hoja de una factura sin React (especificacion §2.3): el orden de sus hallazgos, las filas
// de "Lo que se puede hacer", un importe tecleado con la escala de su campo, un pago de la ficha
// como propuesta y la historia en palabras normales. Lo prueba sheet-model.test.ts.
import { LOCALES, fmt, type Lang, type Messages } from '@/i18n';
import { fieldLabel, ruleText, stateLabel } from '@/i18n/domain';
import type { Finding, InvoiceDetail, InvoiceHistory, InvoicePayment, PaymentProposal } from '@/lib/api-types';
import { formatFieldValue } from '@/lib/field-format';

const ORDER: Record<string, number> = { bloqueo: 0, retencion: 1, aviso: 2 };
const STATE_ORDER: Record<string, number> = { abierto: 0, desaparecido: 1, aceptado: 2 };

/** Primero lo abierto, luego lo desaparecido sin cerrar y lo aceptado; y lo mas grave antes. */
export function sortFindings(findings: readonly Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) =>
      (STATE_ORDER[a.estado] ?? 3) - (STATE_ORDER[b.estado] ?? 3) ||
      (ORDER[a.severidad] ?? 3) - (ORDER[b.severidad] ?? 3) ||
      a.id - b.id
  );
}

/** Una fila de "Lo que se puede hacer": que es y por que clave se abre su tarjeta. */
export type SheetRow =
  | { kind: 'finding'; key: string; finding: Finding }
  | { kind: 'payment'; key: string; payment: InvoicePayment }
  | { kind: 'relation'; key: string; relation: InvoiceDetail['relaciones'][number] }
  | { kind: 'exception'; key: string }
  | { kind: 'review'; key: string }
  | { kind: 'read'; key: string }
  | { kind: 'more'; key: string };

/**
 * Las filas de la tabla de la hoja, de la mas urgente a la menos: cada hallazgo abierto (o
 * desaparecido sin cerrar), cada pago propuesto, cada relacion propuesta, la excepcion abierta y
 * la revision si falta; despues, siempre, "Datos leidos" y "Pagos, notas e historial".
 */
export function sheetRows(f: InvoiceDetail): SheetRow[] {
  const rows: SheetRow[] = [];
  for (const h of sortFindings(f.hallazgos)) {
    if (h.estado === 'abierto' || h.estado === 'desaparecido') rows.push({ kind: 'finding', key: `h${h.id}`, finding: h });
  }
  for (const p of f.pagos ?? []) if (p.estado === 'propuesta') rows.push({ kind: 'payment', key: `p${p.id}`, payment: p });
  for (const r of f.relaciones) if (!r.retirada && r.estado === 'propuesta') rows.push({ kind: 'relation', key: `r${r.id}`, relation: r });
  if (f.excepcion && f.excepcion.estado !== 'resuelta') rows.push({ kind: 'exception', key: 'exception' });
  if (!f.anulada && f.estado?.estado_revision !== 'revisada') rows.push({ kind: 'review', key: 'review' });
  rows.push({ kind: 'read', key: 'read' }, { kind: 'more', key: 'more' });
  return rows;
}

/** Cuantas filas se ven como mucho con la hoja plegada (decision del dueno, 29-10-2026). */
export const FOLD_ROWS = 4;

/** La tabla de la hoja, plegada o no: lo que se ve y lo que dice el control de plegar. */
export interface SheetFold {
  /** Las filas que se ven, en su orden. */
  shown: SheetRow[];
  /** Cuantas quedan plegadas ahora (0 desplegada o sin nada que plegar). */
  hidden: number;
  /** De las plegadas, cuantas son un aviso abierto (un hallazgo o la excepcion). */
  attention: number;
  /** Si hay control de plegar: solo cuando hay mas de FOLD_ROWS filas. */
  foldable: boolean;
}

/** Un aviso que nunca se pliega sin decirlo: un hallazgo (abierto o desaparecido sin cerrar) o
 *  la excepcion abierta. */
export function needsAttention(row: SheetRow): boolean {
  return row.kind === 'finding' || row.kind === 'exception';
}

/**
 * Con FOLD_ROWS filas o menos, todas y sin control (como antes). Con mas, plegada se ven las
 * FOLD_ROWS - 1 primeras (las mas urgentes) y el control ocupa la cuarta linea; desplegada,
 * todas. Lo plegado cuenta sus avisos para que el control los diga.
 */
export function foldRows(rows: readonly SheetRow[], expanded: boolean): SheetFold {
  if (rows.length <= FOLD_ROWS) return { shown: [...rows], hidden: 0, attention: 0, foldable: false };
  if (expanded) return { shown: [...rows], hidden: 0, attention: 0, foldable: true };
  const shown = rows.slice(0, FOLD_ROWS - 1);
  const rest = rows.slice(FOLD_ROWS - 1);
  return { shown, hidden: rest.length, attention: rest.filter(needsAttention).length, foldable: true };
}

/** El texto del control: "Y 5 lineas mas · 2 piden atencion" plegada, "Ver menos" desplegada. */
export function foldLabel(t: Messages, fold: SheetFold): string {
  const s = t.aurora.sheet;
  if (fold.hidden === 0) return s.foldLess;
  const more = fold.hidden === 1 ? s.foldMoreOne : fmt(s.foldMore, { n: fold.hidden });
  if (fold.attention === 0) return more;
  return `${more} · ${fold.attention === 1 ? s.foldAttentionOne : fmt(s.foldAttention, { n: fold.attention })}`;
}

/** "2902,79" -> 290279 con la escala del campo, sin floats; null si no se entiende. */
export function toScaled(text: string, scale: number): string | null {
  let s = text.replace(/\s/g, '');
  if (/^[+-]?[1-9]\d{0,2}(\.\d{3})+,\d+$/.test(s)) s = s.replace(/\./g, '');
  const m = /^([+-]?)(\d+)(?:[.,](\d+))?$/.exec(s);
  if (!m) return null;
  const decimals = (m[3] ?? '').padEnd(scale, '0');
  if (decimals.length > scale) return null;
  const digits = `${m[2]}${decimals}`.replace(/^0+(?=\d)/, '');
  return `${m[1] === '-' ? '-' : ''}${digits}`;
}

/** Un pago propuesto de la ficha, como lo que necesita su tarjeta (las tres coincidencias). */
export function asProposal(p: InvoicePayment, f: InvoiceDetail): PaymentProposal {
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

export interface HistoryEntry {
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
    out.push({ at: r.en, text: r.resultado === 'revisada' ? t.history.reviewed : t.history.returned, who: r.usuario, note: r.nota });
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
      out.push({ at: e.en, text: fmt(t.history.changed, { field: label, from: show(c.anterior_texto), to: show(c.nuevo_texto) }), who: e.usuario, note: e.motivo });
    }
    if (e.tipo === 'documento_abierto') out.push({ at: e.en, text: t.history.opened, who: e.usuario, note: null });
  }
  return out.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}
