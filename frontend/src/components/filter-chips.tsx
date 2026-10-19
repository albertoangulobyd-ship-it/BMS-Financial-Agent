// Los filtros de una lista como fichas (Alle / Geblokkeerd / Urgent / Aandacht): una se
// elige, se ve cual (color y aria-pressed) y cada una dice cuantas hay.
import { cn } from '@/lib/utils';

export interface Chip<K extends string> {
  key: K;
  label: string;
  count?: number;
}

export function FilterChips<K extends string>({
  label,
  chips,
  value,
  onChange,
}: {
  /** Lo que filtran, para el lector de pantalla. */
  label: string;
  chips: readonly Chip<K>[];
  value: K;
  onChange: (key: K) => void;
}) {
  return (
    <div role='group' aria-label={label} className='flex flex-wrap items-center gap-1.5'>
      {chips.map((chip) => {
        const active = chip.key === value;
        return (
          <button
            key={chip.key}
            type='button'
            aria-pressed={active}
            onClick={() => onChange(chip.key)}
            className={cn(
              'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors',
              active
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-input bg-card text-[#2a2824] hover:bg-accent'
            )}
          >
            <span>{chip.label}</span>
            {chip.count !== undefined && (
              <span className={cn('num text-xs', active ? 'text-primary-foreground/90' : 'text-muted-foreground')}>
                {chip.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
