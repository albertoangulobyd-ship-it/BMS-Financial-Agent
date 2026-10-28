// Las piezas puras de los paneles (paso 17), sin React: lo que antes vivia en las pantallas de
// los pasos 15 y 16 (Inicio, IVA, Importar y Ajustes) y que los paneles usan igual. Lo prueba
// panel-model.test.ts.
import { fmt, type Messages } from '@/i18n';
import type { ImportBatch, InvoiceRow } from '@/lib/api';
import type { Isolation, VatSummary } from '@/lib/api-types';
import { formatCents, formatMoney, todayIso } from '@/lib/format';
import { needsPerson } from '@/lib/why';

// ---------------------------------------------------------------- Inicio

/** "Lo primero": como mucho cinco cosas distintas. */
export const FIRST = 5;

/** Lo que no puede esperar: bloqueado o urgente. */
export function urgentFirst(invoices: readonly InvoiceRow[]): InvoiceRow[] {
  return invoices.filter((f) => needsPerson(f) && (f.nivel === 'bloqueada' || f.nivel === 'urgente'));
}

/** El nombre de pila del saludo ("Ana Demo" -> "Ana"); si no parece uno, el nombre entero. */
export function firstName(name: string): string {
  const first = name.trim().split(/\s+/)[0] ?? '';
  return first.length >= 2 && !first.endsWith('.') ? first : name.trim();
}

// ---------------------------------------------------------------- IVA

export interface QuarterRow {
  etiqueta: string;
  estado: string;
  terminado: boolean;
  saldo_cent: number;
  limite_presentacion: string | null;
  dias_para_limite: number | null;
}

/** Los trimestres: el actual y los anteriores, sin repetir, el mas nuevo primero. */
export function quarterRows(summary: VatSummary): QuarterRow[] {
  const seen = new Map<string, QuarterRow>();
  const a = summary.actual;
  seen.set(a.etiqueta, {
    etiqueta: a.etiqueta,
    estado: a.estado,
    terminado: a.terminado,
    saldo_cent: a.cifras['5c'],
    limite_presentacion: a.limite_presentacion,
    dias_para_limite: a.dias_para_limite,
  });
  for (const q of [...summary.por_presentar, ...summary.anteriores]) {
    if (seen.has(q.etiqueta)) continue;
    seen.set(q.etiqueta, {
      etiqueta: q.etiqueta,
      estado: q.estado,
      terminado: true,
      saldo_cent: q['5c'],
      limite_presentacion: q.limite_presentacion,
      dias_para_limite: q.dias_para_limite,
    });
  }
  return [...seen.values()].sort((x, y) => (x.etiqueta < y.etiqueta ? 1 : -1));
}

/** Lo que dice el saldo: a pagar, a devolver o nada. */
export function balanceText(cents: number, t: Messages): string {
  if (cents > 0) return fmt(t.vat.toPay, { amount: formatMoney(cents) });
  if (cents < 0) return fmt(t.vat.refund, { amount: formatMoney(-cents) });
  // Un importe como los demas (no una palabra).
  return formatMoney(0);
}

/** Lo que toca ahora en un trimestre; nunca "aprobado" ni "presentar". */
export function nextStep(row: Pick<QuarterRow, 'estado' | 'terminado'>, t: Messages): string {
  if (row.estado === 'presentado') return t.vat.nextFiled;
  if (row.estado === 'listo_revision') return t.vat.nextFile;
  return row.terminado ? t.vat.nextCheck : t.vat.nextRunning;
}

/** Cuando el plazo pide atencion: pasado y sin aangifte (error) o a 14 dias o menos. */
export const DEADLINE_CLOSE_DAYS = 14;

export function deadlineState(row: Pick<QuarterRow, 'estado' | 'dias_para_limite'>): 'plazo_vencido' | 'plazo_cerca' | null {
  const days = row.dias_para_limite;
  if (row.estado === 'presentado' || days === null) return null;
  if (days < 0) return 'plazo_vencido';
  return days <= DEADLINE_CLOSE_DAYS ? 'plazo_cerca' : null;
}

/** Un importe para escribirlo en un campo: "4.743,86" o "-409,70" (el menos de teclado). */
export function plainAmount(cents: number): string {
  const text = formatCents(Math.abs(cents)) ?? '0,00';
  return cents < 0 ? `-${text}` : text;
}

// ---------------------------------------------------------------- Importar

/** Lo que diria la prueba de un lote: con filas rechazadas, con errores; con avisos o con
 *  valores que chocan con uno puesto a mano, con avisos; si no, en orden. */
export function previewState(b: Pick<ImportBatch, 'rechazadas' | 'avisos' | 'sin_resolver'>): 'ok' | 'avisos' | 'errores' {
  if (b.rechazadas > 0) return 'errores';
  if (b.avisos.length > 0 || b.sin_resolver > 0) return 'avisos';
  return 'ok';
}

/** "1,5 MB" / "320 kB": el tamano de un fichero, con coma decimal. */
export function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    const tenths = Math.round((bytes * 10) / (1024 * 1024));
    return `${Math.floor(tenths / 10)},${tenths % 10} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} kB`;
}

/** El dia (Amsterdam) en que se guardo el fichero; si dice que es del futuro, hoy. */
export function fileDay(lastModified: number, now: Date = new Date()): string {
  const today = todayIso(now);
  const day = todayIso(new Date(lastModified));
  return day > today ? today : day;
}

export type ImportPhase = 'idle' | 'trying' | 'previewed' | 'importing' | 'done';

/** La accion principal (.primary), una sola en cada momento: antes de la prueba, "Probar
 *  primero"; despues, "Importar de verdad". Si con la prueba no entraria nada, o ya se
 *  importo, ninguna (lo dice el texto). */
export function primaryImportAction(phase: ImportPhase, canImport: boolean): 'try' | 'import' | null {
  if (phase === 'idle' || phase === 'trying') return 'try';
  if (phase === 'previewed' || phase === 'importing') return canImport ? 'import' : null;
  return null;
}

// ---------------------------------------------------------------- Ajustes

/** El estado de un papel del aislamiento (o, sin el, si va bien). */
export function roleIsolation(p: Isolation['papeles'][number]): string {
  return p.estado ?? (p.bien ? 'correcto' : 'falla');
}

/** Lo mas serio de los papeles: una prueba que falla, despues lo comprobado hace demasiado y
 *  despues lo que nunca se comprobo. */
export function worstIsolation(i: Isolation): string {
  const states = i.papeles.map(roleIsolation);
  return ['falla', 'caducada', 'sin_comprobar'].find((s) => states.includes(s)) ?? 'falla';
}
