// Las proximas cuatro semanas del flujo de caja (especificacion §2.2.1): la de hoy (de hoy al
// domingo) y las tres siguientes (de lunes a domingo), con su numero de semana ISO. Cada una se
// pide al motor con desde y hasta (/api/v2/flujo): nada se calcula aqui. Fechas AAAA-MM-DD, con
// aritmetica sobre UTC. Lo prueba weeks.test.ts.

export interface Week {
  /** El numero de semana ISO 8601 (la del jueves de esa semana). */
  number: number;
  from: string;
  to: string;
}

const DAY = 86_400_000;

function toUtc(iso: string): number {
  return Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
}

function fromUtc(ms: number): string {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
}

/** La semana ISO de un dia: la del jueves de su semana (lunes a domingo). */
export function isoWeek(iso: string): number {
  const ms = toUtc(iso);
  const weekday = (new Date(ms).getUTCDay() + 6) % 7; // lunes 0 ... domingo 6
  const thursday = ms + (3 - weekday) * DAY;
  const year = new Date(thursday).getUTCFullYear();
  const firstThursday = Date.UTC(year, 0, 4);
  const firstWeekday = (new Date(firstThursday).getUTCDay() + 6) % 7;
  const week1Monday = firstThursday - firstWeekday * DAY;
  return 1 + Math.floor((thursday - week1Monday) / (7 * DAY));
}

/** Las cuatro semanas desde hoy: la primera empieza hoy y todas acaban en domingo. */
export function weekRanges(today: string, count = 4): Week[] {
  const start = toUtc(today);
  const weekday = (new Date(start).getUTCDay() + 6) % 7;
  const sunday = start + (6 - weekday) * DAY;
  const out: Week[] = [];
  for (let i = 0; i < count; i += 1) {
    const to = sunday + i * 7 * DAY;
    const from = i === 0 ? start : to - 6 * DAY;
    out.push({ number: isoWeek(fromUtc(to)), from: fromUtc(from), to: fromUtc(to) });
  }
  return out;
}
