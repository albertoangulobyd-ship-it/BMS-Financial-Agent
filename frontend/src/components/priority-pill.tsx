// La prioridad como etiqueta: texto + color + forma (cuadrado, triangulo, circulo), para
// que nunca dependa solo del color. Los cuatro pares difieren en luminosidad.
import { useT } from '@/i18n';
import { isPriority, priorityLabel, type Priority } from '@/i18n/domain';
import { cn } from '@/lib/utils';

const STYLES: Record<Priority, string> = {
  bloqueada: 'bg-pill-blocked text-pill-blocked-foreground border-pill-blocked-border',
  urgente: 'bg-pill-urgent text-pill-urgent-foreground border-pill-urgent-border',
  atencion: 'bg-pill-attention text-pill-attention-foreground border-pill-attention-border',
  normal: 'bg-pill-normal text-pill-normal-foreground border-pill-normal-border',
};

function Shape({ priority }: { priority: Priority }) {
  if (priority === 'bloqueada') {
    return (
      <svg aria-hidden='true' width='9' height='9' viewBox='0 0 10 10'>
        <rect x='1' y='1' width='8' height='8' rx='1' fill='currentColor' />
      </svg>
    );
  }
  if (priority === 'urgente') {
    return (
      <svg aria-hidden='true' width='9' height='9' viewBox='0 0 10 10'>
        <path d='M5 1 9.2 9H.8z' fill='currentColor' />
      </svg>
    );
  }
  if (priority === 'atencion') {
    return (
      <svg aria-hidden='true' width='9' height='9' viewBox='0 0 10 10'>
        <circle cx='5' cy='5' r='3.6' fill='none' stroke='currentColor' strokeWidth='1.6' />
      </svg>
    );
  }
  return null;
}

export function PriorityPill({ priority, className }: { priority: string; className?: string }) {
  const { lang, t } = useT();
  const known: Priority = isPriority(priority) ? priority : 'normal';
  const label = priorityLabel(lang, priority) ?? t.common.unknown;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-[3px] border px-[7px] text-xs font-semibold leading-[18px]',
        STYLES[known],
        className
      )}
    >
      <Shape priority={known} />
      <span>{label}</span>
    </span>
  );
}
