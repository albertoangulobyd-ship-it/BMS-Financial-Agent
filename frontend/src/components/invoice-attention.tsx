// Las facturas que piden a una persona, en una lista corta: prioridad, numero y relacion, y
// el por que en palabras normales. Una fila abre la factura en su pestana. La usa la ficha
// de un Object: lo que necesita atencion en una locatie son sus facturas.
import { StatusPill } from '@/components/status-pill';
import { Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { useT } from '@/i18n';
import type { InvoiceRow } from '@/lib/api';
import { whyOf } from '@/lib/why';
import { NothingNeedsAttention } from './attention-list';

export function InvoiceAttentionList({
  rows,
  emptyText,
  onOpen,
}: {
  rows: InvoiceRow[];
  emptyText: string;
  onOpen: (id: number) => void;
}) {
  const { t, lang } = useT();
  if (rows.length === 0) return <NothingNeedsAttention text={emptyText} />;
  return (
    <ol className='divide-y divide-divider overflow-hidden rounded-md border border-border bg-card'>
      {rows.map((row) => (
        <li key={row.id}>
          <button
            type='button'
            onClick={() => onOpen(row.id)}
            aria-label={`${t.records.invoice.label} ${row.numero ?? row.id}`}
            className='grid w-full grid-cols-[8.5rem_minmax(10rem,15rem)_7.5rem_1fr] items-start gap-4 px-4 py-3 text-left hover:bg-row-hover'
          >
            <span>
              <StatusPill group='prioridad' state={row.nivel} />
            </span>
            <span className='flex min-w-0 flex-col'>
              <span className='truncate font-mono text-[12.5px] font-medium text-primary'>{row.numero ?? '—'}</span>
              <span className='truncate text-[13px] text-soft-foreground'>{row.contraparte ?? '—'}</span>
            </span>
            <span className='text-right'>
              <Money cents={row.total_cent} />
            </span>
            <WhyCell why={whyOf(row, lang, t)} />
          </button>
        </li>
      ))}
    </ol>
  );
}
