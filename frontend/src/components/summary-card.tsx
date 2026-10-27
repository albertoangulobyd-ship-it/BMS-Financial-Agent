// Una tarjeta de resumen: que es (en mayusculas pequenas), una cifra grande con su frase
// y, como mucho, tres filas de detalle. El Overzicht lleva cuatro como maximo.
import type { ReactNode } from 'react';
import { PingScope, StatusPill, type StatusPillProps } from '@/components/status-pill';
import { cn } from '@/lib/utils';

export interface SummaryRow {
  label: string;
  value: ReactNode;
  /** Cuando pide atencion (algo bloqueado, vencido, un plazo cerca): el estado, que se ensena
   *  con su pastilla (components/status-pill) en lugar de la etiqueta. */
  status?: Pick<StatusPillProps, 'group' | 'state' | 'values'>;
}

export function SummaryCard({
  title,
  value,
  caption,
  rows = [],
  action,
  help,
  className,
}: {
  title: string;
  /** Un (?) junto al titulo, para una palabra del oficio (Btw). */
  help?: ReactNode;
  value: ReactNode;
  caption?: string;
  rows?: SummaryRow[];
  /** Un enlace a la pantalla de detalle (un boton pequeno). */
  action?: ReactNode;
  className?: string;
}) {
  return (
    // Una tarjeta resume: su pastilla va quieta (lo que late esta en su pantalla).
    <PingScope scope='none'>
    <section data-testid='summary-card' className={cn('flex flex-col gap-2 bg-card px-4 pb-4 pt-3', className)}>
      <div className='flex items-baseline justify-between gap-2'>
        <h2 className='flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground'>
          {title}
          {help}
        </h2>
        {action}
      </div>
      <div className='flex flex-col'>
        <span className='num text-[19px] font-semibold tracking-[-0.01em]'>{value}</span>
        {caption && <span className='text-xs text-muted-foreground'>{caption}</span>}
      </div>
      {rows.length > 0 && (
        <dl className='grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-[12.5px]'>
          {rows.slice(0, 3).map((row) => (
            <div key={row.label} className='contents'>
              <dt className={row.status ? 'flex items-center' : 'text-soft-foreground'}>
                {row.status ? <StatusPill {...row.status} /> : row.label}
              </dt>
              <dd className={cn('m-0 self-center text-right num', row.status && 'font-medium')}>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
    </PingScope>
  );
}

/** Las tarjetas juntas, separadas por lineas finas (sin sombras). */
export function SummaryGrid({ children }: { children: ReactNode }) {
  return (
    // Cuatro en una fila en la ventana de siempre (1440 px) y dos y dos mas estrecho: con
    // auto-fit, a 1024 px quedaban tres y una con un hueco gris al lado.
    <div className='grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 xl:grid-cols-4'>
      {children}
    </div>
  );
}
