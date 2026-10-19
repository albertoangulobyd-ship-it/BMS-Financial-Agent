// El "por que" de una fila, en palabras normales: el hallazgo mas urgente escrito desde
// sus valores (i18n/domain.ts, nunca el castellano de la API) y cuantos mas hay. Sin
// hallazgos, lo que la deja pendiente: una excepcion abierta, campos por verificar o que
// va tarde. Nada, y es una raya.
import { fmt, type Lang, type Messages } from '@/i18n';
import { findingDetail, ruleText } from '@/i18n/domain';
import type { Reason } from './api-types';

export interface Why {
  /** Una frase (el detalle del hallazgo mas urgente). */
  text: string;
  /** El nombre corto de su regla ("Factuurnummer dubbel"), para encabezar. */
  title: string | null;
  /** La regla, en pequeno y gris. */
  rule: string | null;
  /** Cuantos hallazgos mas hay detras. */
  more: number;
}

interface WhyRow {
  razones?: Reason[];
  excepcion?: { id: number; estado: string } | null;
  sin_resolver?: number;
  dudosos?: number;
  estado_pago?: string | null;
  dias_vencida?: number | null;
}

export function whyOf(row: WhyRow, lang: Lang, t: Messages): Why | null {
  const reasons = row.razones ?? [];
  const first = reasons[0];
  if (first) {
    const detail = findingDetail(lang, first.regla, first.resultado, first.valores);
    const rule = ruleText(lang, first.regla);
    return {
      text: detail ?? rule?.meaning ?? first.regla,
      title: rule?.title ?? null,
      rule: first.regla,
      more: reasons.length - 1,
    };
  }
  const fields = (row.sin_resolver ?? 0) + (row.dudosos ?? 0);
  if (fields) return { text: fmt(t.why.fieldsToVerify, { n: fields }), title: null, rule: null, more: 0 };
  if (row.excepcion) return { text: t.why.openException, title: null, rule: null, more: 0 };
  if (row.estado_pago === 'vencida') {
    return {
      text: row.dias_vencida ? fmt(t.why.overdueDays, { n: row.dias_vencida }) : t.why.overdue,
      title: null,
      rule: null,
      more: 0,
    };
  }
  return null;
}

/** Si una factura pide a una persona: prioridad, hallazgos, excepcion o campos. */
export function needsPerson(row: WhyRow & { nivel: string; estado_revision?: string | null }): boolean {
  return (
    row.nivel !== 'normal' ||
    (row.razones?.length ?? 0) > 0 ||
    Boolean(row.excepcion) ||
    (row.sin_resolver ?? 0) + (row.dudosos ?? 0) > 0
  );
}

/** El "por que" de una fila de proveedor, cliente, Objeto o PO: su hallazgo mas urgente
 *  (`razones`, contrato 2.1) o, sin ninguno, lo vencido. */
export function partyWhy(
  row: { razones?: Reason[]; vencido_cent?: number | null },
  lang: Lang,
  t: Messages,
  overdueText: (cents: number) => string
): Why | null {
  const why = whyOf({ razones: row.razones }, lang, t);
  if (why) return why;
  if (row.vencido_cent && row.vencido_cent > 0) {
    return { text: overdueText(row.vencido_cent), title: null, rule: null, more: 0 };
  }
  return null;
}

const RANK: Record<string, number> = { bloqueada: 0, urgente: 1, atencion: 2, normal: 3 };

/** El orden de una prioridad: lo bloqueado primero, lo normal al final. */
export function priorityRank(level: string): number {
  return RANK[level] ?? 4;
}
