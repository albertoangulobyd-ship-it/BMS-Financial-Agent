// Un estado en texto, con un punto de color al lado: el color ayuda, el texto dice.
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export type StatusTone = 'neutral' | 'ok' | 'late' | 'attention' | 'blocked' | 'muted';

const TONES: Record<StatusTone, { text: string; dot: string }> = {
  neutral: { text: 'text-foreground', dot: 'bg-[#8b8578]' },
  ok: { text: 'text-ok-foreground', dot: 'bg-ok-foreground' },
  late: { text: 'text-late-foreground font-medium', dot: 'bg-late-foreground' },
  attention: { text: 'text-pill-attention-foreground', dot: 'bg-pill-attention-foreground' },
  blocked: { text: 'text-pill-blocked font-medium', dot: 'bg-pill-blocked' },
  muted: { text: 'text-muted-foreground', dot: 'bg-[#b5afa3]' },
};

export function StatusText({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: StatusTone;
  children: ReactNode;
  className?: string;
}) {
  const style = TONES[tone];
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap', style.text, className)}>
      <span aria-hidden='true' className={cn('h-1.5 w-1.5 shrink-0 rounded-full', style.dot)} />
      <span>{children}</span>
    </span>
  );
}
