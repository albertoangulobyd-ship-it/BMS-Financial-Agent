// Las seis entradas en pequeno, en todas las pantallas menos el inicio (paso 16, decision 1):
// asi cualquier seccion esta a un clic. La misma lista que la rueda, con su mismo nombre
// ("Hoofdmenu"); la seccion donde se esta va marcada (aria-current) y en claro. En una ventana
// ancha van en la fila de arriba; mas estrecho, en la de abajo, y si no caben en una linea
// pasan a la siguiente (en el movil, dos o tres lineas): siempre las seis a la vista.
import { useT } from '@/i18n';
import { cn } from '@/lib/utils';
import type { SectionId } from '@/screens/registry';

export function CompactNav({
  sections,
  current,
  onGo,
  className,
}: {
  sections: readonly SectionId[];
  current: SectionId | null;
  onGo: (section: SectionId) => void;
  className?: string;
}) {
  const { t } = useT();
  return (
    <nav aria-label={t.shell.mainNavigation} className={cn('min-w-0', className)}>
      <ul className='flex flex-wrap items-center gap-0.5'>
        {sections.map((id) => {
          const active = id === current;
          return (
            <li key={id} className='min-w-0'>
              <button
                type='button'
                aria-current={active ? 'page' : undefined}
                onClick={() => onGo(id)}
                className={cn(
                  'relative whitespace-nowrap rounded-full px-3 py-1.5 text-[13.5px] font-medium tracking-[-0.01em] transition-colors',
                  active
                    ? 'bg-accent text-foreground'
                    : 'text-soft-foreground hover:bg-accent/60 hover:text-foreground'
                )}
              >
                {t.areas[id].label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
