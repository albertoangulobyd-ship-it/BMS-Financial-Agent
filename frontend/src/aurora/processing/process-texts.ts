// Lo que dice Procesar en cada estado (especificacion §5.4), sin React: el titulo y la linea del
// saludo (main.tsx:29, en el sitio de "Bienvenido"), las dos lineas de la tarjeta sin empezar, la
// nota debajo del boton y las lineas de cada etapa que la app le pasa al motor (setStage). Las
// cifras salen de GET /api/v2/lectura: dolares en millonesimas, horas en la de Amsterdam. Lo
// prueba process-texts.test.ts.
import { SCRIPT_NAMES } from '@/components/script-names';
import { fmt, type Messages } from '@/i18n';
import type { ReadingPassRow, ReadingRequest, ReadingStatus } from '@/lib/api-types';
import { NO_VALUE, formatTimeOfDay, formatUsdMicro } from '@/lib/format';
import { handled, outcomeOf, passOf, type Outcome, type RowTexts, type Screen } from './reading-model';

/** El saludo de Procesar (processView de Aurora): titulo y linea. `alert`, la linea es un aviso;
 *  `properName`, un nombre propio dentro del titulo (el acceso directo, en castellano). */
export interface ProcessView {
  phase: 'intro' | 'running' | 'complete' | 'error';
  title: string;
  detail: string;
  alert?: boolean;
  properName?: string;
}

/** La hora de un instante ("10:41"), en la de Amsterdam. */
export function timeOf(value: string | null | undefined): string {
  return formatTimeOfDay(value)?.time || NO_VALUE;
}

/** "hoy a las 10:41" o "27-10-2026 a las 10:41". */
export function whenOf(value: string | null | undefined, t: Messages, now: Date = new Date()): string {
  const notes = t.aurora.process.notes;
  const at = formatTimeOfDay(value, now);
  if (!at) return NO_VALUE;
  return at.today ? fmt(notes.today, { time: at.time }) : fmt(notes.on, { date: at.date, time: at.time });
}

/** El por que de un final malo, por su codigo (lectura.MOTIVOS), en el idioma de la persona. */
export function reasonOf(code: string | null | undefined, t: Messages): string {
  const r = t.aurora.process.reasons;
  const reasons: Record<string, string> = {
    buzon_vacio: r.buzon_vacio,
    ya_leidas: r.ya_leidas,
    clave: r.clave,
    salida: r.salida,
    aislamiento: r.aislamiento,
    contar: r.contar,
    sin_tarifa: r.sin_tarifa,
    estimacion: r.estimacion,
    lectura: r.lectura,
    interrumpida: r.interrumpida,
    abandonada: r.abandonada,
  };
  return (code && reasons[code]) || r.other;
}

/** Lo que fue de un documento, en la fila del resultado. */
export function entryText(row: ReadingPassRow, t: Messages): string {
  const e = t.aurora.process.entry;
  const texts: Record<string, string> = { nueva: e.nueva, ya_leida: e.ya_leida, posible_duplicado: e.posible_duplicado, fallida: e.fallida };
  return texts[row.estado] ?? row.estado;
}

/** Lo que dice cada linea de la lectura: listo o lo que se hace con el documento de ahora. */
export function rowTexts(t: Messages): RowTexts {
  const c = t.aurora.process.card;
  return { done: c.done, phases: { comparando: c.docPhases.comparando, leyendo: c.docPhases.leyendo, guardando: c.docPhases.guardando } };
}

/** Las facturas nuevas y la horquilla de una cuenta, para P3. */
function waitingTitle(s: ReadingRequest, t: Messages, changed: boolean): string {
  const w = t.aurora.process.waiting;
  const n = s.pdf_nuevos ?? 0;
  const values = { n, min: formatUsdMicro(s.coste_min_usd_micro), max: formatUsdMicro(s.coste_max_usd_micro) };
  if (changed) return fmt(n === 1 ? w.changedOne : w.changed, values);
  return fmt(n === 1 ? w.titleOne : w.title, values);
}

function waitingLine(s: ReadingRequest, t: Messages, changed: boolean): string {
  const w = t.aurora.process.waiting;
  const time = timeOf(s.caduca_en);
  if (changed) return fmt(w.changedLine, { time });
  const already = s.pdf_ya_leidos ?? 0;
  if (already === 0) return fmt(w.lineNone, { time });
  return fmt(already === 1 ? w.lineOne : w.line, { n: already, time });
}

/** El saludo de cada estado con la cabeza (P0 a P3, P7 y P8). `notice`: lo que paso con el ultimo
 *  "Empezar" (la estimacion cambio, o no se pudo mandar). */
export function introView(screen: Screen, status: ReadingStatus | null, t: Messages, notice: 'changed' | 'sendFailed' | null = null): ProcessView {
  const p = t.aurora.process;
  const s = status?.solicitud ?? null;
  const view = (title: string, detail: string): ProcessView => ({ phase: 'intro', title, detail });
  switch (screen) {
    case 'requested':
      return {
        ...view(fmt(p.requested.title, { readShortcut: SCRIPT_NAMES.readShortcut }), p.requested.line),
        properName: SCRIPT_NAMES.readShortcut,
      };
    case 'checking':
      return view(p.checking.title, p.checking.line);
    case 'counting':
      return view(p.counting.title, p.counting.line);
    case 'waiting':
      if (!s) return view(p.ready.title, p.ready.line);
      if (notice === 'sendFailed') return { ...view(waitingTitle(s, t, false), p.waiting.sendFailed), alert: true };
      return view(waitingTitle(s, t, notice === 'changed'), waitingLine(s, t, notice === 'changed'));
    case 'expired':
      return view(p.expired.title, p.expired.line);
    case 'cancelled':
      return view(p.cancelled.title, p.cancelled.line);
    case 'nothing': {
      if (s?.motivo_codigo === 'buzon_vacio') return view(p.nothing.title, p.nothing.empty);
      const n = s?.pdf_ya_leidos ?? 0;
      return view(p.nothing.title, n === 1 ? p.nothing.lineOne : fmt(p.nothing.line, { n }));
    }
    default:
      return view(p.ready.title, p.ready.line);
  }
}

/** Las dos lineas de la tarjeta antes de empezar: las de Aurora con el "Empezar" a la vista (P3);
 *  en los demas, lo que cuesta y que no se gasta nada sin un si. */
export function idleLines(screen: Screen, t: Messages): [string, string] {
  const c = t.aurora.process.card;
  return screen === 'waiting' ? [c.start, c.startNote] : [c.idle, c.idleNote];
}

/** La etiqueta de la tarjeta (pc-label): lista, esperando al lector o en proceso. */
export function cardState(screen: Screen, running: boolean, t: Messages): string {
  const c = t.aurora.process.card;
  if (running) return c.running;
  return screen === 'requested' || screen === 'checking' || screen === 'counting' ? c.waiting : c.ready;
}

/** El titulo y la linea de la etapa i, con los datos de la lectura (los que el motor anuncia al
 *  empezarla, como announce en Aurora). */
export function stageLabel(i: number, status: ReadingStatus | null, t: Messages): [string, string] {
  const p = t.aurora.process;
  const pass = status ? passOf(status) : null;
  const s = status?.solicitud ?? null;
  // La pasada cuenta todos los PDF contados (tambien los ya leidos, que no se pagan); las nuevas
  // son las de la cuenta.
  const total = pass?.total ?? s?.pdf_nuevos ?? 0;
  const fresh = s?.pdf_nuevos ?? total;
  switch (i) {
    case 0:
      return [p.stageTitles.loading, fresh === 1 ? p.stageLines.loadingOne : fmt(p.stageLines.loading, { n: fresh })];
    case 1:
      return [p.stageTitles.reading, fmt(p.stageLines.reading, { done: Math.min(handled(pass), total), total })];
    case 2:
      return [p.stageTitles.comparing, p.stageLines.comparing];
    case 3:
      return [p.stageTitles.analyzing, p.stageLines.analyzing];
    default:
      return [p.stageTitles.organizing, p.stageLines.organizing];
  }
}

/** El pie de la tarjeta en las etapas: lectura real, cuantas facturas y lo gastado. */
export function footerOf(status: ReadingStatus | null, t: Messages): string {
  const c = t.aurora.process.card;
  const pass = status ? passOf(status) : null;
  const n = pass?.total ?? status?.solicitud?.pdf_nuevos ?? 0;
  const spent = formatUsdMicro(pass?.coste_usd_micro ?? 0);
  return n === 1 ? fmt(c.footerOne, { spent }) : fmt(c.footer, { n, spent });
}

/** La nota de P0, P7 y P8: lo gastado hasta hoy, lo que cuesta cada factura y como acabo la
 *  ultima lectura. Sin el permiso, que pedir lo hace otra persona. */
export function readyNote(status: ReadingStatus | null, t: Messages, allowed: boolean, now: Date = new Date()): string[] {
  const notes = t.aurora.process.notes;
  const lines: string[] = [];
  if (!allowed) lines.push(notes.noPermission);
  if (status) {
    const est = status.estimacion;
    const spent = formatUsdMicro(status.coste_usd_micro ?? 0);
    lines.push(
      est
        ? fmt(notes.spent, { spent, low: formatUsdMicro(est.por_documento_bajo_usd_micro, 3), high: formatUsdMicro(est.por_documento_alto_usd_micro, 3) })
        : fmt(notes.spentOnly, { spent })
    );
    const last = lastReading(status, t, now);
    if (last) lines.push(last);
  }
  return lines;
}

/** Como acabo la ultima lectura (la nota de P0). */
export function lastReading(status: ReadingStatus, t: Messages, now: Date = new Date()): string | null {
  const notes = t.aurora.process.notes;
  const s = status.solicitud ?? null;
  if (s && s.estado === 'fallida') return fmt(notes.lastFailed, { when: whenOf(s.terminada_en, t, now), reason: reasonOf(s.motivo_codigo, t) });
  const pass = status.ultima_pasada ?? null;
  if (!pass || (s && s.viva)) return null;
  const o = outcomeOf(pass);
  const counts = [
    o.fresh === 1 ? notes.newCountOne : fmt(notes.newCount, { n: o.fresh }),
    o.repeated === 1 ? notes.dupCountOne : fmt(notes.dupCount, { n: o.repeated }),
  ].join(', ');
  return fmt(notes.lastDone, { when: whenOf(pass.terminada_en, t, now), counts });
}

/** La nota de P1 a P3: quien la pidio y a que hora. */
export function requestNote(status: ReadingStatus | null, t: Messages): string | null {
  const notes = t.aurora.process.notes;
  const s = status?.solicitud ?? null;
  if (!s) return null;
  if (s.pedida_por) return fmt(notes.requestedBy, { name: s.pedida_por.nombre, time: timeOf(s.pedida_en) });
  return fmt(notes.requestedByReader, { time: timeOf(s.tomada_en ?? s.pedida_en) });
}

/** El saludo del resultado (P5), con las cuentas de Aurora. */
export function completeView(outcome: Outcome, t: Messages): ProcessView {
  const c = t.aurora.process.complete;
  const n = outcome.rows.length;
  return { phase: 'complete', title: c.title, detail: n === 1 ? c.lineOne : fmt(c.line, { n }) };
}

/** La nota del resultado: las repetidas sin copia y, si paro antes, por que. */
export function completeNote(status: ReadingStatus | null, t: Messages): string[] {
  const c = t.aurora.process.complete;
  const lines = [c.note];
  const pass = status ? passOf(status) : null;
  const s = status?.solicitud ?? null;
  if (pass && s) {
    const values = { done: handled(pass), total: pass.total, cap: formatUsdMicro(s.tope_usd_micro) };
    if (pass.fase === 'tope') lines.push(fmt(c.cap, values));
    else if (pass.fase === 'cancelada' || s.estado === 'cancelada') lines.push(fmt(c.stopped, values));
  }
  return lines;
}

/** El saludo del error (P6): nada leido o una parte, y el por que. */
export function errorView(status: ReadingStatus | null, t: Messages): ProcessView {
  const e = t.aurora.process.error;
  const s = status?.solicitud ?? null;
  const pass = status ? passOf(status) : null;
  const reason = reasonOf(s?.abandonada && s.viva ? 'abandonada' : s?.motivo_codigo, t);
  const some = handled(pass);
  if (some > 0) return { phase: 'error', title: e.titleSome, detail: `${reason} ${fmt(e.some, { n: some })}` };
  return { phase: 'error', title: e.title, detail: reason };
}
