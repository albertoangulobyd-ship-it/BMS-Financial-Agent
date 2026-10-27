// "Wat aandacht nodig heeft" en las fichas de proveedor, cliente y PO: cada hallazgo
// pendiente con su nombre, lo que dicen sus datos (escrito desde sus valores) y que hacer;
// los de una misma factura juntos, con el boton que la abre en su pestana (donde estan las
// ordenes: aceptar, cerrar, corregir). Lo aceptado sigue a la vista, en gris. El codigo de
// la regla va pequeno.
import { CircleCheck } from 'lucide-react';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import { fmt, useT } from '@/i18n';
import { findingDetail, ruleText } from '@/i18n/domain';
import type { Json } from '@/lib/api-types';

export interface AttentionItem {
  id: number;
  regla: string;
  severidad: string;
  estado: string;
  resultado: string;
  valores: Json;
  factura_id?: number | null;
}

const SEVERITY: Record<string, number> = { bloqueo: 0, retencion: 1, aviso: 2 };
const STATE: Record<string, number> = { abierto: 0, desaparecido: 1, aceptado: 2 };

export function sortAttention<T extends AttentionItem>(items: readonly T[]): T[] {
  return [...items].sort(
    (a, b) =>
      (STATE[a.estado] ?? 3) - (STATE[b.estado] ?? 3) ||
      (SEVERITY[a.severidad] ?? 3) - (SEVERITY[b.severidad] ?? 3) ||
      a.id - b.id
  );
}

export function AttentionList({
  items,
  emptyText,
  invoiceNumber,
  onOpenInvoice,
}: {
  items: readonly AttentionItem[];
  emptyText: string;
  /** El numero de una factura (para el boton), si se conoce. */
  invoiceNumber?: (id: number) => string | null;
  onOpenInvoice?: (id: number) => void;
}) {
  const { t } = useT();
  if (items.length === 0) return <NothingNeedsAttention text={emptyText} />;
  // Los de una misma factura van juntos, con un solo boton para abrirla: cuatro tarjetas
  // con el mismo boton eran ruido. Los grupos, en el orden de su hallazgo mas urgente.
  const groups: { invoice: number | null; items: AttentionItem[] }[] = [];
  for (const item of sortAttention(items)) {
    const invoice = item.factura_id ?? null;
    const group = invoice !== null ? groups.find((g) => g.invoice === invoice) : undefined;
    if (group) group.items.push(item);
    else groups.push({ invoice, items: [item] });
  }
  return (
    <ol className='flex flex-col gap-3'>
      {groups.map((group) => (
        <li key={group.invoice ?? `h-${group.items[0]!.id}`}>
          <section className='rounded-md border border-border bg-card'>
            {group.invoice !== null && (
              <header className='flex flex-wrap items-center justify-between gap-3 border-b border-divider px-4 py-2.5'>
                <span className='text-[13px] text-soft-foreground'>
                  {t.records.invoice.label}{' '}
                  <span className='font-mono text-[12.5px] font-medium text-foreground'>
                    {invoiceNumber?.(group.invoice) ?? group.invoice}
                  </span>
                </span>
                {onOpenInvoice && (
                  <Button type='button' variant='outline' size='sm' onClick={() => onOpenInvoice(group.invoice!)}>
                    {fmt(t.parties.openInvoice, { number: invoiceNumber?.(group.invoice) ?? group.invoice })}
                  </Button>
                )}
              </header>
            )}
            <div className='divide-y divide-divider'>
              {group.items.map((item) => (
                <AttentionCard key={item.id} item={item} />
              ))}
            </div>
          </section>
        </li>
      ))}
      {items.some((i) => i.estado === 'aceptado') && (
        <li className='text-xs text-muted-foreground'>{t.parties.acceptedBy}</li>
      )}
    </ol>
  );
}

export function NothingNeedsAttention({ text }: { text: string }) {
  const { t } = useT();
  return (
    <div className='flex items-center gap-3 rounded-md border border-border bg-card px-4 py-4'>
      <CircleCheck className='h-5 w-5 shrink-0 text-ok-foreground' aria-hidden='true' />
      <div>
        <p className='font-medium'>{t.empty.nothingNeedsAttention}</p>
        <p className='text-[13px] text-muted-foreground'>{text}</p>
      </div>
    </div>
  );
}

function AttentionCard({ item: h }: { item: AttentionItem }) {
  const { t, lang } = useT();
  const rule = ruleText(lang, h.regla);
  const detail = findingDetail(lang, h.regla, h.resultado, h.valores);
  const accepted = h.estado === 'aceptado';
  return (
    <article aria-labelledby={`attention-${h.id}`} className={accepted ? 'bg-muted/40 px-4 py-3.5' : 'px-4 py-3.5'}>
      <header className='flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1'>
        <h3 id={`attention-${h.id}`} className='text-[14.5px] font-semibold'>
          {rule?.title ?? h.regla}
        </h3>
        <span className='flex items-center gap-2 text-xs'>
          {accepted ? <StatusPill group='hallazgo' state={h.estado} /> : <StatusPill group='severidad' state={h.severidad} />}
          <span className='font-mono text-[11px] text-muted-foreground' title={t.invoice.ruleCodeHelp}>
            {h.regla}
          </span>
        </span>
      </header>
      {detail && <p className='mt-1.5 text-[13.5px] leading-relaxed'>{detail}</p>}
      {rule && !accepted && (
        <p className='mt-1.5 text-[13px] leading-relaxed text-soft-foreground'>
          <span className='font-medium text-foreground'>{t.invoice.whatToDo} </span>
          {rule.whatToDo}
        </p>
      )}
    </article>
  );
}
