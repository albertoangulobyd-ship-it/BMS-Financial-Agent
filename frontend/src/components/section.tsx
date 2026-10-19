// Una seccion plegable: los detalles (campos, lineas, planning, relaciones, historia) van
// plegados debajo de lo importante, y se abren con un clic o con el teclado.
import { useId, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export function Section({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  /** Una linea gris al lado del titulo (cuantas lineas, de cuando es). */
  summary?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <section className='border-t border-border'>
      <h2 className='m-0'>
        <button
          type='button'
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className='flex w-full items-center gap-2 py-3 text-left text-[15px] font-semibold hover:text-primary'
        >
          <ChevronDown
            className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', !open && '-rotate-90')}
            aria-hidden='true'
          />
          <span>{title}</span>
          {summary && <span className='text-xs font-normal text-muted-foreground'>{summary}</span>}
        </button>
      </h2>
      <div id={id} hidden={!open} className='pb-5'>
        {open && children}
      </div>
    </section>
  );
}
