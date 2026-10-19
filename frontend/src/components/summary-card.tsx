// Una tarjeta de resumen: que es (en mayusculas pequenas), una cifra grande con su frase
// y, como mucho, tres filas de detalle. El Overzicht lleva cuatro como maximo.
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface SummaryRow {
  label: string;
  value: ReactNode;
  /** Resaltar (vencido): en el color de "tarde", y con su texto. */
  emphasis?: boolean;
}

export function SummaryCard({
  title,
  value,
  caption,
  rows = [],
  action,
  className,
}: {
  title: string;
  value: ReactNode;
  caption?: string;
  rows?: SummaryRow[];
  /** Un enlace a la pantalla de detalle (un boton pequeno). */
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('flex flex-col gap-2 bg-card px-4 pb-4 pt-3', className)}>
      <div className='flex items-baseline justify-between gap-2'>
        <h2 className='text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground'>{title}</h2>
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
              <dt className={row.emphasis ? 'font-medium text-late-foreground' : 'text-[#45423c]'}>{row.label}</dt>
              <dd className={cn('m-0 text-right num', row.emphasis && 'font-medium text-late-foreground')}>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

/** Las tarjetas juntas, separadas por lineas finas (sin sombras). */
export function SummaryGrid({ children }: { children: ReactNode }) {
  return (
    <div className='grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-px overflow-hidden rounded-md border border-border bg-border'>
      {children}
    </div>
  );
}
