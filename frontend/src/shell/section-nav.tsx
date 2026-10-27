// Las vistas de una seccion, encima de la pantalla (paso 16): en Cuentas por cobrar, las
// facturas de venta, los clientes, los Objects y las PO de clientes; en Inicio, la cola de
// trabajo, las excepciones y el flujo de caja. Pastillas como las de los filtros de Aurora; la
// vista donde se esta va marcada (aria-current). Las insignias dicen solo lo que pide hacer algo
// (bloqueadas, excepciones abiertas, cuentas por verificar).
import { fmt, useT } from '@/i18n';
import { cn } from '@/lib/utils';
import type { SectionId, ViewId } from '@/screens/registry';
import type { NavBadge } from './use-badges';

export function SectionNav({
  section,
  views,
  current,
  onGo,
  badge,
}: {
  section: SectionId;
  views: readonly ViewId[];
  current: ViewId;
  onGo: (view: ViewId) => void;
  badge: (view: ViewId) => NavBadge | undefined;
}) {
  const { t } = useT();
  return (
    <nav aria-label={fmt(t.shell.sectionNavigation, { section: t.areas[section].label })} className='mb-1'>
      <ul className='flex flex-wrap items-center gap-1.5'>
        {views.map((view) => {
          const active = view === current;
          const b = badge(view);
          const hint = t.nav[view].hint;
          return (
            <li key={view}>
              <button
                type='button'
                aria-current={active ? 'page' : undefined}
                onClick={() => onGo(view)}
                className={cn(
                  'flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors',
                  active
                    ? 'border-primary/60 bg-primary/15 text-foreground'
                    : 'border-border text-soft-foreground hover:border-border-strong hover:text-foreground'
                )}
              >
                <span>{t.nav[view].label}</span>
                {hint && <span className='text-xs font-normal text-muted-foreground'>{hint}</span>}
                {b && (
                  <span
                    className={cn(
                      'num rounded-full px-1.5 py-px text-[11px] font-semibold leading-4',
                      b.tone === 'blocked' ? 'bg-pill-blocked text-pill-blocked-foreground' : 'bg-muted text-foreground'
                    )}
                  >
                    {b.count}
                    {b.label ? ` ${b.label}` : ''}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
