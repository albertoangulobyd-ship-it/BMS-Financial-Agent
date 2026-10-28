// Cuanto falta o cuanto va tarde una factura, en palabras ("12 dias tarde", "vence hoy", "en
// 4 dias"): de los dias del motor (`days`: retraso; negativo, lo que falta) o de la fecha y el
// hoy del motor. Lo usan las tarjetas de los paneles y la hoja de una factura.
import { fmt, type Messages } from '@/i18n';
import { dueState, type DueState } from './panels/money-model';

export function dueInfo(due: string | null, today: string | null, days?: number | null): DueState | null {
  if (!due) return { kind: 'none' };
  if (days !== undefined && days !== null) {
    if (days > 0) return { kind: 'late', days };
    return days === 0 ? { kind: 'today' } : { kind: 'ahead', days: -days };
  }
  return today ? dueState(due, today) : null;
}

export function dueLabel(t: Messages, due: string | null, today: string | null, days?: number | null): string | null {
  const d = t.money.due;
  const s = dueInfo(due, today, days);
  if (!s) return null;
  if (s.kind === 'late') return fmt(s.days === 1 ? d.lateOne : d.late, { n: s.days });
  if (s.kind === 'today') return d.today;
  if (s.kind === 'ahead') return fmt(s.days === 1 ? d.aheadOne : d.ahead, { n: s.days });
  return d.none;
}
