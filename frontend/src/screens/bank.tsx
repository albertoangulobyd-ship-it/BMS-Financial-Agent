// El banco de Cuentas por cobrar (los ingresos) y de Cuentas por pagar (los cargos), paso 16:
// lo que el banco trajo y pide a una persona. Arriba, los pagos que el banco caso a medias
// con una factura (GET /api/v2/pagos/propuestas): la linea del banco al lado de la factura,
// las tres coincidencias, y "Bevestigen" o "Niet deze" (con motivo). Debajo, las lineas sin
// ninguna factura (GET /api/v2/movimientos?signo=), que K7 avisara a los pocos dias; cada
// una se puede enlazar a una factura pendiente (apuntar un pago con su linea). Nada de esto
// paga ni prepara una transferencia. El texto del banco es de un tercero: va como texto.
import { CircleCheck } from 'lucide-react';
import { DataTable, type Columns } from '@/components/data-table';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { Button } from '@/components/ui/button';
import { DateText, Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { paths, type InvoiceRow } from '@/lib/api';
import type { BankLine, BankLines, PaymentProposal } from '@/lib/api-types';
import { formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { useNav } from '@/shell/navigation';
import { BANK_OF, SIGN_OF, proposalsOf, type Side } from './money-model';
import { ConfirmProposalButton, LinkLineButton, ProposalCompare, WithdrawPaymentButton } from './payment-actions';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

export function BankScreen({ side }: { side: Side }) {
  const { t } = useT();
  const { session } = useSession();
  const can = useCan();
  const { version } = useRefresh();
  const nav = t.nav[BANK_OF[side]];
  const canLink = can('marcar_pagada');
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ propuestas: PaymentProposal[] }>(paths.proposals, { sentido: side }).then((r) => proposalsOf(r.propuestas, side)),
        session!.api.get<{ movimientos: BankLines }>(paths.bankLines, { signo: SIGN_OF[side] }).then((r) => r.movimientos),
        // Las facturas pendientes, para enlazar una linea (solo a quien puede hacerlo).
        canLink ? session!.api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas) : Promise.resolve([] as InvoiceRow[]),
      ]),
    [session, version, side, canLink]
  );
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <div className='flex flex-col gap-10'>
          <Proposals proposals={state.data[0]} onDone={retry} />
          <Unmatched side={side} lines={state.data[1]} invoices={state.data[2]} onDone={retry} />
        </div>
      )}
    </Screen>
  );
}

function Proposals({ proposals, onDone }: { proposals: PaymentProposal[]; onDone: () => void }) {
  const { t } = useT();
  const nav = useNav();
  return (
    <section aria-labelledby='bank-proposals'>
      <h2 id='bank-proposals' className='flex items-center gap-1.5 text-[16px] font-semibold'>
        {t.bank.proposalsTitle}
        {proposals.length > 0 && <span className='text-[13px] font-normal text-muted-foreground'>{proposals.length}</span>}
        <HelpTip term='proposal' />
      </h2>
      <p className='mb-3 mt-1 max-w-3xl text-[13px] text-muted-foreground'>{t.bank.proposalsIntro}</p>
      {proposals.length === 0 ? (
        <EmptyState icon={CircleCheck} title={t.bank.noProposals} />
      ) : (
        <ul className='flex flex-col gap-3'>
          {proposals.map((p) => {
            const name = `${p.factura.numero ?? p.factura.id} · ${formatMoney(p.importe_cent)}`;
            return (
              <li key={p.id}>
                <article aria-label={name} data-testid='proposal' className='flex flex-col gap-3 rounded-md border border-border bg-card px-4 py-3'>
                  <ProposalCompare proposal={p} />
                  <div className='flex flex-wrap items-center gap-2'>
                    <ConfirmProposalButton proposal={p} onDone={onDone} />
                    <WithdrawPaymentButton paymentId={p.id} rev={p.rev} label={t.bank.notThis} context={<ProposalCompare proposal={p} />} onDone={onDone} />
                    <Button variant='link' size='sm' className='ml-auto h-auto px-0' onClick={() => nav.open(recordRoute('invoice', p.factura.id))}>
                      {t.bank.openInvoice}
                    </Button>
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Unmatched({ side, lines, invoices, onDone }: { side: Side; lines: BankLines; invoices: InvoiceRow[]; onDone: () => void }) {
  const { t } = useT();
  const rows = lines.lista.filter((l) => l.importe_cent !== null);
  const columns: Columns<BankLine> = [
    { key: 'date', header: t.bank.date, width: '7rem', cell: (l) => <DateText value={l.fecha} /> },
    { key: 'amount', header: t.bank.amount, align: 'right', width: '8rem', cell: (l) => <Money cents={l.resto_cent ?? l.importe_cent} /> },
    {
      key: 'who',
      header: t.bank.counterparty,
      cell: (l) => (
        <span className='flex flex-col'>
          <span data-proper-name=''>{l.contraparte ?? '—'}</span>
          {l.concepto && (
            <span className='text-xs text-muted-foreground' data-proper-name=''>
              {l.concepto}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'age',
      header: t.bank.age,
      width: '7rem',
      cell: (l) => (
        <span className='text-[13px] text-soft-foreground'>
          {l.dias === 0 ? t.bank.ageToday : fmt(l.dias === 1 ? t.bank.ageOne : t.bank.ageDays, { n: l.dias })}
        </span>
      ),
    },
    {
      key: 'link',
      header: <span className='sr-only'>{t.bank.link}</span>,
      width: '13rem',
      cell: (l) => <LinkLineButton line={l} side={side} invoices={invoices} onDone={onDone} />,
    },
  ];
  return (
    <section aria-labelledby='bank-unmatched'>
      <h2 id='bank-unmatched' className='flex items-center gap-1.5 text-[16px] font-semibold'>
        {t.bank.unmatchedTitle}
        {lines.total > 0 && <span className='text-[13px] font-normal text-muted-foreground'>{lines.total}</span>}
      </h2>
      <p className='mb-3 mt-1 max-w-3xl text-[13px] text-muted-foreground'>{side === 'saliente' ? t.bank.unmatchedIntroIn : t.bank.unmatchedIntroOut}</p>
      {rows.length === 0 ? (
        <EmptyState icon={CircleCheck} title={t.bank.noUnmatched} />
      ) : (
        <>
          <DataTable columns={columns} rows={rows} rowKey={(l) => l.id} caption={t.bank.unmatchedTitle} />
          {lines.total > rows.length && <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.bank.more, { n: lines.total - rows.length })}</p>}
        </>
      )}
    </section>
  );
}
