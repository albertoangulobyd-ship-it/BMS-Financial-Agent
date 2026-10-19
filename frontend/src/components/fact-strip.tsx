// La tira de datos de arriba de una ficha (como la de una factura): que es y como esta, en
// pocas cifras, separadas por lineas finas. A 1440 px van en una fila; mas estrecho, de dos
// en dos, y si son impares la primera ocupa la fila entera (sin huecos grises).
import { Children, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

const XL_COLUMNS: Record<number, string> = {
  2: 'xl:grid-cols-2',
  3: 'xl:grid-cols-3',
  4: 'xl:grid-cols-4',
  5: 'xl:grid-cols-5',
  6: 'xl:grid-cols-3',
};

export function FactStrip({ children, className }: { children: ReactNode; className?: string }) {
  const items = Children.toArray(children).filter(Boolean);
  const odd = items.length % 2 === 1;
  return (
    <dl
      className={cn(
        'mb-8 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border text-[13px]',
        XL_COLUMNS[items.length] ?? 'xl:grid-cols-4',
        className
      )}
    >
      {items.map((item, index) => (
        <div
          key={index}
          className={cn('bg-card px-4 py-3', odd && index === 0 && 'col-span-2 xl:col-span-1')}
        >
          {item}
        </div>
      ))}
    </dl>
  );
}

/** Un dato de la tira: su nombre en mayusculas pequenas, la cifra y una linea gris debajo. */
export function Fact({ label, children, note }: { label: ReactNode; children: ReactNode; note?: ReactNode }) {
  return (
    <>
      <dt className='mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>
        {label}
      </dt>
      <dd className='m-0'>
        {children}
        {note && <span className='mt-0.5 block text-xs text-muted-foreground'>{note}</span>}
      </dd>
    </>
  );
}
