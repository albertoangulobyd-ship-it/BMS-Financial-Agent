// GlassCalendar de Aurora (components/ui/glass-calendar.tsx, entrega del 28-10-2026), tal cual.
// Cambios: date-fns pasa a Date e Intl con el idioma de la persona (el mismo texto: "octubre
// 2026", "3 de octubre de 2026"), sin dependencia nueva; (I) los textos del diccionario; el mes
// de partida es el de hoy (el prototipo partia de su fecha de ejemplo); en un formulario de una
// orden (aurora/orders.tsx) la cabecera dice el nombre del campo (`label`).
import { useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { motion } from 'framer-motion';
import { LOCALES, useT } from '@/i18n';

const startOfMonth = (d: Date) => new Date(d.getFullYear(), d.getMonth(), 1);
const addMonths = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth() + n, 1);
const getDaysInMonth = (d: Date) => new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
const isSameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

/** "3 de octubre de 2026" / "3 oktober 2026" / "3 October 2026". */
export function longDate(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
}

export function GlassCalendar({
  selectedDate,
  onDateSelect,
  onClear,
  label,
}: {
  selectedDate?: Date;
  onDateSelect: (date: Date) => void;
  onClear: () => void;
  label?: string;
}) {
  const { t, lang } = useT();
  const s = t.aurora.search;
  const locale = LOCALES[lang];
  const [month, setMonth] = useState(selectedDate ?? new Date()),
    first = startOfMonth(month),
    offset = (first.getDay() + 6) % 7,
    days = getDaysInMonth(month);
  const monthName = new Intl.DateTimeFormat(locale, { month: 'long' }).format(month);
  return (
    <div className='glass-calendar'>
      <div className='calendar-header'>
        <span>
          <CalendarDays size={13} /> {label ?? s.date}
        </span>
        <button type='button' disabled={!selectedDate} onClick={onClear} aria-label={s.dateClear}>
          <X size={14} />
        </button>
      </div>
      <div className='calendar-month'>
        <button type='button' aria-label={s.previousMonth} onClick={() => setMonth(addMonths(month, -1))}>
          <ChevronLeft size={16} />
        </button>
        <motion.strong key={`${month.getFullYear()}-${month.getMonth()}`} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}>
          {`${monthName} ${month.getFullYear()}`}
        </motion.strong>
        <button type='button' aria-label={s.nextMonth} onClick={() => setMonth(addMonths(month, 1))}>
          <ChevronRight size={16} />
        </button>
      </div>
      <div className='calendar-grid'>
        {Array.from(s.weekdays).map((d, i) => (
          <span className='calendar-weekday' key={i}>
            {d}
          </span>
        ))}
        {Array.from({ length: offset }, (_, i) => (
          <span key={'empty' + i} />
        ))}
        {Array.from({ length: days }, (_, i) => {
          const date = new Date(month.getFullYear(), month.getMonth(), i + 1),
            selected = !!selectedDate && isSameDay(date, selectedDate);
          return (
            <button
              type='button'
              key={i}
              aria-label={longDate(date, locale)}
              aria-pressed={selected}
              className={selected ? 'calendar-selected' : ''}
              onClick={() => onDateSelect(date)}
            >
              {i + 1}
            </button>
          );
        })}
      </div>
      <p>{selectedDate ? longDate(selectedDate, locale) : s.dateAny}</p>
    </div>
  );
}
