// Como se escriben importes, horas y fechas. Siempre en notacion neerlandesa (36.270,36),
// tambien con la app en ingles: es como lo lee la empresa y como lo imprimen sus
// facturas. Los importes llegan en centimos enteros (*_cent) y las horas en milesimas
// (*_mil): se escriben con aritmetica de enteros (BigInt y texto), nunca con float, para
// que un centimo no se pierda ni aparezca por redondeo.
import type { Messages } from '@/i18n';

/** El signo menos de verdad (U+2212): mas legible que el guion en cifras alineadas. */
export const MINUS = '−';
/** Lo que se ensena cuando no hay dato: sin datos no es cero. */
export const NO_VALUE = '—';

/** Un entero de la API (numero sin decimales, o texto de cifras) como BigInt; null si no lo es. */
export function toBigInt(value: number | bigint | string | null | undefined): bigint | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'bigint') return value;
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) ? BigInt(value) : null;
  }
  return /^-?\d+$/.test(value) ? BigInt(value) : null;
}

/** 1234567 -> "1.234.567" (miles con punto). */
export function groupThousands(digits: string): string {
  let out = '';
  for (let i = 0; i < digits.length; i += 1) {
    const fromEnd = digits.length - i;
    out += digits[i];
    if (fromEnd > 1 && fromEnd % 3 === 1) out += '.';
  }
  return out;
}

/** Centimos -> "36.270,36" (sin simbolo). null si el valor no es un entero. */
export function formatCents(value: number | bigint | string | null | undefined): string | null {
  const cents = toBigInt(value);
  if (cents === null) return null;
  const negative = cents < 0n;
  const abs = negative ? -cents : cents;
  const euros = (abs / 100n).toString();
  const rest = (abs % 100n).toString().padStart(2, '0');
  return `${negative ? MINUS : ''}${groupThousands(euros)},${rest}`;
}

/** Centimos -> "€ 36.270,36" / "€ −24,76"; sin dato, "—". */
export function formatMoney(value: number | bigint | string | null | undefined): string {
  const text = formatCents(value);
  return text === null ? NO_VALUE : `€ ${text}`;
}

/** Milesimas de hora -> "78,5" / "8" / "1.250,25" (sin ceros de mas a la derecha). */
export function formatHours(value: number | bigint | string | null | undefined): string {
  const mil = toBigInt(value);
  if (mil === null) return NO_VALUE;
  const negative = mil < 0n;
  const abs = negative ? -mil : mil;
  const whole = groupThousands((abs / 1000n).toString());
  const fraction = (abs % 1000n).toString().padStart(3, '0').replace(/0+$/, '');
  return `${negative ? MINUS : ''}${whole}${fraction ? `,${fraction}` : ''}`;
}

/** Puntos basicos -> "21 %" / "8,75 %". */
export function formatPercentFromBasisPoints(value: number | bigint | string | null | undefined): string {
  const pb = toBigInt(value);
  if (pb === null) return NO_VALUE;
  const negative = pb < 0n;
  const abs = negative ? -pb : pb;
  const whole = groupThousands((abs / 100n).toString());
  const fraction = (abs % 100n).toString().padStart(2, '0').replace(/0+$/, '');
  return `${negative ? MINUS : ''}${whole}${fraction ? `,${fraction}` : ''} %`;
}

interface IsoDate {
  year: number;
  month: number;
  day: number;
}

/** "2026-10-16" (o el principio de un instante ISO) -> sus partes, sin pasar por Date. */
export function parseIsoDate(value: string | null | undefined): IsoDate | null {
  if (!value) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  // El dia tiene que existir (30 de febrero no).
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) return null;
  return { year, month, day };
}

/** En tablas: "16-10-2026". */
export function formatDate(value: string | null | undefined): string {
  const d = parseIsoDate(value);
  if (!d) return NO_VALUE;
  return `${String(d.day).padStart(2, '0')}-${String(d.month).padStart(2, '0')}-${d.year}`;
}

/** En una frase: "16 okt 2026" / "16 Oct 2026". */
export function formatDateProse(value: string | null | undefined, t: Messages): string {
  const d = parseIsoDate(value);
  if (!d) return NO_VALUE;
  return `${d.day} ${t.months.short[d.month - 1]} ${d.year}`;
}

/** Con el dia de la semana: "maandag 19 oktober 2026" / "Monday 19 October 2026". */
export function formatDateLong(value: string | null | undefined, t: Messages): string {
  const d = parseIsoDate(value);
  if (!d) return NO_VALUE;
  const weekday = new Date(Date.UTC(d.year, d.month - 1, d.day)).getUTCDay();
  return `${t.months.weekdays[weekday]} ${d.day} ${t.months.long[d.month - 1]} ${d.year}`;
}

/** Un instante ISO con hora, en la hora de Amsterdam: "16-10-2026 10:12". */
export function formatDateTime(value: string | null | undefined): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}T/.test(value)) return NO_VALUE;
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return NO_VALUE;
  const parts = new Intl.DateTimeFormat('nl-NL', {
    timeZone: 'Europe/Amsterdam',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(instant);
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? '';
  return `${get('day')}-${get('month')}-${get('year')} ${get('hour')}:${get('minute')}`;
}

/** La fecha de hoy en la hora de Amsterdam, como "2026-10-19". */
export function todayIso(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Amsterdam',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

/** Las iniciales de un nombre escrito por una persona: "Ana Demo" -> "AD". */
export function initials(name: string | null | undefined): string {
  const words = (name ?? '').trim().split(/\s+/).filter(Boolean);
  const letters = words.slice(0, 2).map((w) => Array.from(w)[0] ?? '');
  return letters.join('').toLocaleUpperCase('nl-NL') || '?';
}
