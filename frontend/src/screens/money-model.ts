// Cuentas por cobrar y por pagar (paso 16), sin React: que facturas caen en cada ventana y
// tramo (como la cartera del motor, para que la lista sume lo mismo que la cifra que se
// pulso), cuanto falta o cuanto va tarde una factura, el orden de las empresas y de las
// facturas, y que hay que decir de un pago. Lo prueban money-model.test.ts y las pruebas
// en el navegador contra la API.
// Rutas relativas: lo importan tambien las pruebas en el navegador (e2e), sin el alias @.
import type { InvoiceRow } from '../lib/api';
import type { AgeingBucket, Cartera, CarteraParty, InvoicePayment, PaymentProposal } from '../lib/api-types';

export type Side = 'saliente' | 'entrante';

/** El sentido de las facturas de cada entrada: lo que nos deben y lo que debemos. */
export const SIDE_OF = { receivables: 'saliente', payables: 'entrante' } as const satisfies Record<string, Side>;

/** La lista de facturas de cada sentido y la vista del banco de cada uno. */
export const LIST_OF: Record<Side, 'invoices-out' | 'invoices-in'> = { saliente: 'invoices-out', entrante: 'invoices-in' };
export const BANK_OF: Record<Side, 'bank-in' | 'bank-out'> = { saliente: 'bank-in', entrante: 'bank-out' };

/** Un ingreso cobra una venta y un cargo paga una compra: el signo de las lineas del banco. */
export const SIGN_OF: Record<Side, 'entrada' | 'salida'> = { saliente: 'entrada', entrante: 'salida' };

/** Las fichas de la lista de facturas. Las de pago (lo que esta abierto, lo vencido, esta
 *  semana, 30 dias, un tramo) son las de la cartera: la lista suma lo mismo que la cifra. */
export const INVOICE_FILTERS = ['all', 'open', 'vencida', 'week', 'next30', 'por_confirmar', 'pagada', 'necesita_revision'] as const;
export type BaseFilter = (typeof INVOICE_FILTERS)[number];
export type BucketKey = AgeingBucket['clave'];
export const BUCKETS: readonly BucketKey[] = ['al_corriente', '1_30', '31_60', '61_90', 'mas_de_90', 'sin_fecha'];
/** Un tramo de antiguedad tambien es una ficha (se abre desde la barra). */
export type InvoiceFilter = BaseFilter | `tramo:${BucketKey}`;

export function isInvoiceFilter(value: string): value is InvoiceFilter {
  if ((INVOICE_FILTERS as readonly string[]).includes(value)) return true;
  return value.startsWith('tramo:') && (BUCKETS as readonly string[]).includes(value.slice(6));
}

/** Lo que la cartera cuenta: una deuda de este sentido que cuenta, con algo pendiente en
 *  euros (sin abonos: van aparte, R4) y sin pagar. */
export function inCartera(row: Pick<InvoiceRow, 'sentido' | 'cuenta' | 'total_cent' | 'pendiente_cent' | 'estado_pago'>, side: Side): boolean {
  return (
    row.sentido === side &&
    row.cuenta &&
    (row.total_cent ?? 0) > 0 &&
    (row.pendiente_cent ?? 0) > 0 &&
    (row.estado_pago === 'pendiente' || row.estado_pago === 'vencida')
  );
}

/** Un vencimiento (AAAA-MM-DD) entre dos dias, incluidos (null: sin limite). */
export function dueBetween(due: string | null | undefined, from: string | null, to: string | null): boolean {
  if (!due) return false;
  const day = due.slice(0, 10);
  return (from === null || day >= from) && (to === null || day <= to);
}

export interface Windows {
  today: string;
  week: [string, string] | null;
  next30: [string, string] | null;
  buckets: readonly AgeingBucket[];
}

export function windowsOf(c: Pick<Cartera, 'hoy' | 'fechas' | 'tramos'>): Windows {
  return { today: c.hoy, week: c.fechas.semana ?? null, next30: c.fechas.proximos_30 ?? null, buckets: c.tramos };
}

/** Si una fila pasa una ficha. `waiting`: las facturas con un pago propuesto esperando. */
export function matchesFilter(
  filter: InvoiceFilter,
  row: InvoiceRow,
  side: Side,
  windows: Windows | null,
  waiting: ReadonlySet<number>
): boolean {
  switch (filter) {
    case 'all':
      return true;
    case 'necesita_revision':
      return row.estado_revision === 'necesita_revision';
    case 'open':
      return inCartera(row, side);
    case 'vencida':
      return inCartera(row, side) && row.estado_pago === 'vencida';
    case 'pagada':
      return row.estado_pago === 'pagada';
    case 'por_confirmar':
      return waiting.has(row.id);
    case 'week':
      return Boolean(windows?.week) && inCartera(row, side) && dueBetween(row.vencimiento, windows!.week![0], windows!.week![1]);
    case 'next30':
      return Boolean(windows?.next30) && inCartera(row, side) && dueBetween(row.vencimiento, windows!.next30![0], windows!.next30![1]);
    default: {
      const key = filter.slice(6) as BucketKey;
      const bucket = windows?.buckets.find((b) => b.clave === key);
      if (!bucket || !inCartera(row, side)) return false;
      if (key === 'sin_fecha') return !row.vencimiento;
      return dueBetween(row.vencimiento, bucket.vence_desde, bucket.vence_hasta);
    }
  }
}

/** Las fichas de pago van por vencimiento (lo mas antiguo primero); las demas, en el orden
 *  de la API (la prioridad). */
export function sortsByDue(filter: InvoiceFilter): boolean {
  return filter !== 'all' && filter !== 'pagada' && filter !== 'necesita_revision';
}

export function byDue<T extends { id: number; vencimiento: string | null }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => {
    if (a.vencimiento === b.vencimiento) return a.id - b.id;
    if (!a.vencimiento) return 1;
    if (!b.vencimiento) return -1;
    return a.vencimiento < b.vencimiento ? -1 : 1;
  });
}

/** Lo que suman las filas de la cartera (lo que la cifra o el tramo dice). */
export function pendingSum(rows: readonly Pick<InvoiceRow, 'pendiente_cent'>[]): number {
  return rows.reduce((n, r) => n + (r.pendiente_cent ?? 0), 0);
}

// ------------------------------------------------------------ cuanto falta o va tarde

/** Dias entre dos fechas AAAA-MM-DD (b - a), con aritmetica de enteros sobre UTC. */
export function daysBetween(a: string, b: string): number {
  const ms = Date.UTC(+b.slice(0, 4), +b.slice(5, 7) - 1, +b.slice(8, 10)) - Date.UTC(+a.slice(0, 4), +a.slice(5, 7) - 1, +a.slice(8, 10));
  return Math.round(ms / 86_400_000);
}

export type DueState = { kind: 'late'; days: number } | { kind: 'today' } | { kind: 'ahead'; days: number } | { kind: 'none' };

/** "12 dias tarde", "hoy" o "en 4 dias", visto desde `today` (el hoy del motor). */
export function dueState(due: string | null | undefined, today: string): DueState {
  if (!due) return { kind: 'none' };
  const d = daysBetween(today, due.slice(0, 10));
  if (d < 0) return { kind: 'late', days: -d };
  if (d === 0) return { kind: 'today' };
  return { kind: 'ahead', days: d };
}

// ------------------------------------------------------------ las empresas

/** Por lo vencido (mas, antes), lo mas antiguo y lo pendiente; la fila sin empresa al final. */
export function partiesByOverdue(parties: readonly CarteraParty[]): CarteraParty[] {
  return [...parties].sort((a, b) => {
    if ((a.id === null) !== (b.id === null)) return a.id === null ? 1 : -1;
    return (
      b.vencido_cent - a.vencido_cent ||
      (b.mas_antigua_dias ?? -1) - (a.mas_antigua_dias ?? -1) ||
      b.pendiente_cent - a.pendiente_cent ||
      (a.nombre ?? '').localeCompare(b.nombre ?? '') ||
      (a.id ?? 0) - (b.id ?? 0)
    );
  });
}

/** Lo que mide cada tramo en la barra (en milesimas del total; los vacios no salen). */
export function bucketShares(buckets: readonly AgeingBucket[]): { clave: BucketKey; share: number }[] {
  const total = buckets.reduce((n, b) => n + b.importe_cent, 0);
  if (total <= 0) return [];
  return buckets.filter((b) => b.importe_cent > 0).map((b) => ({ clave: b.clave, share: Math.max(8, Math.round((b.importe_cent * 1000) / total)) }));
}

// ------------------------------------------------------------ los pagos

/** Los pagos de una factura en el orden de la ficha: lo que espera primero, luego lo que
 *  cuenta (lo mas reciente arriba) y lo retirado al final. */
export function paymentsInOrder(payments: readonly InvoicePayment[]): InvoicePayment[] {
  const rank = (p: InvoicePayment) => (p.estado === 'propuesta' ? 0 : p.estado === 'confirmada' ? 1 : 2);
  return [...payments].sort((a, b) => rank(a) - rank(b) || (b.fecha_pago ?? '').localeCompare(a.fecha_pago ?? '') || b.id - a.id);
}

/** Se puede retirar un pago que no es de Exact (se corrige en Exact) y no esta retirado. */
export function canWithdraw(p: Pick<InvoicePayment, 'estado' | 'fuente'>): boolean {
  return p.estado !== 'retirada' && p.fuente !== 'exact';
}

/** Las propuestas de un lado (cobro: ventas; pago: compras), lo mas antiguo primero. */
export function proposalsOf(proposals: readonly PaymentProposal[], side: Side): PaymentProposal[] {
  return proposals.filter((p) => p.factura.sentido === side);
}

/** Las facturas con un pago propuesto esperando. */
export function waitingInvoices(proposals: readonly PaymentProposal[]): Set<number> {
  return new Set(proposals.map((p) => p.factura.id));
}

// ------------------------------------------------------------ apuntar un pago

/**
 * Un importe tecleado en euros, en centimos (enteros): "4.970,68", "4970,68", "4970.68" o
 * "4970". Como el servidor, no adivina un grupo de miles suelto ("1.000" no vale: o "1000",
 * o con los decimales "1.000,00"). null si no se lee.
 */
export function parseEuros(text: string): number | null {
  const s = text.replace(/[\s\u00a0€]/g, '');
  let whole: string;
  let frac: string;
  const grouped = /^(\d{1,3}(?:\.\d{3})+),(\d{1,2})$/.exec(s);
  const plain = /^(\d+)(?:[,.](\d{1,2}))?$/.exec(s);
  if (grouped) {
    whole = grouped[1]!.replace(/\./g, '');
    frac = grouped[2]!;
  } else if (plain && !/^\d{1,3}\.\d{3}$/.test(s)) {
    whole = plain[1]!;
    frac = plain[2] ?? '';
  } else {
    return null;
  }
  const cents = Number(whole) * 100 + Number((frac + '00').slice(0, 2));
  return Number.isSafeInteger(cents) ? cents : null;
}

/** Los centimos como los quiere la API en un importe: "4970.68" (texto, nunca float). */
export function centsToApi(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}

/** Los centimos como se escriben en el campo (sin miles, coma decimal): "4970,68". */
export function centsToInput(cents: number): string {
  const abs = Math.abs(cents);
  return `${Math.floor(abs / 100)},${String(abs % 100).padStart(2, '0')}`;
}
