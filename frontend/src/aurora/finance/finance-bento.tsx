// El resumen de Aurora, "Lo importante. Todo en un vistazo." (paso 16): la unica parte del
// prototipo que calculaba algo, y la que la revision quiere conservar (§2) con cifras de verdad.
// Viene de finance-bento.tsx; cambia (revision §4.1, §4.3 y §4.19):
// - las cifras llegan en centimos enteros y se escriben con format.ts (€ 36.270,36 en los tres
//   idiomas); nada de pesos ni de sumar lo guardado en el navegador;
// - el titular ya no es la "Diferencia entre saldos" (se leia como beneficio): es lo vencido
//   por cobrar y por pagar y, debajo, el neto de los proximos 30 dias, con la nota de que no
//   es efectivo disponible;
// - las barras por empresa abren su ficha con onOpenParty (no enlaces #/);
// - sin la tarjeta de "Ultima revision" (era el analisis simulado) ni el contador de
//   documentos; la fecha de los datos la dice quien llama (asOf).
// Lo usara el asistente local al contestar "dame un resumen" (un paso posterior).
import { useId, useState } from 'react';
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { fmt, useT } from '@/i18n';
import { formatDateProse, formatMoney, toBigInt } from '@/lib/format';
import './finance-bento.css';

export interface FinanceParty {
  id: number;
  name: string;
  kind: 'client' | 'provider';
  /** Lo pendiente, en centimos. */
  balanceCent: number;
}

export interface FinanceBentoData {
  /** La fecha de los datos (AAAA-MM-DD). */
  asOf: string;
  receivableCent: number;
  payableCent: number;
  overdueReceivableCent: number;
  overduePayableCent: number;
  /** Lo que entra menos lo que sale en los proximos 30 dias (del flujo de caja). */
  net30Cent: number;
  parties: FinanceParty[];
}

/** Una proporcion con enteros: a / (a + b), de 0 a 1, sin perder centimos por el camino. */
function share(a: number, b: number): number {
  const x = toBigInt(a) ?? 0n;
  const y = toBigInt(b) ?? 0n;
  const total = x + y;
  if (total <= 0n) return 0;
  return Number((x * 10000n) / total) / 10000;
}

/** "1 cliente" o "{n} clientes". */
function countText(n: number, many: string, one: string): string {
  return n === 1 ? one : fmt(many, { n });
}

export function FinanceBento({ data: d, onOpenParty }: { data: FinanceBentoData; onOpenParty?: (party: FinanceParty) => void }) {
  const { t } = useT();
  const texts = t.aurora.finance;
  const [group, setGroup] = useState<'client' | 'provider'>('client');
  const id = useId();
  const rows = d.parties.filter((p) => p.kind === group && p.balanceCent > 0).sort((a, b) => b.balanceCent - a.balanceCent);
  const max = Math.max(1, ...rows.map((p) => p.balanceCent));
  const receivableShare = share(d.receivableCent, d.payableCent);
  const pct = Math.round(receivableShare * 100);
  const leader = rows[0];
  const withBalance = (kind: 'client' | 'provider') => d.parties.filter((p) => p.kind === kind && p.balanceCent > 0).length;
  return (
    <div className='aurora-root'>
      <section className='finance-bento' aria-label={texts.label}>
        <header className='fb-header'>
          <div>
            <span className='fb-eyebrow'>{texts.eyebrow}</span>
            <h2>
              {texts.title}
              <br />
              <span>{texts.titleSub}</span>
            </h2>
          </div>
          <span className='fb-stamp'>{fmt(texts.asOf, { date: formatDateProse(d.asOf, t) })}</span>
        </header>
        <div className='fb-grid'>
          <section className='fb-card fb-hero'>
            <span className='fb-eyebrow'>{texts.overdue}</span>
            <strong className='fb-total num'>{formatMoney(d.overdueReceivableCent)}</strong>
            <p>
              {texts.overdueToCollect} · <span className='num'>{formatMoney(d.overduePayableCent)}</span> {texts.overdueToPay}
            </p>
            <div
              className='fb-comparison'
              role='img'
              aria-label={fmt(texts.comparison, { in: formatMoney(d.receivableCent), out: formatMoney(d.payableCent) })}
            >
              <div>
                <span>{texts.receivable}</span>
                <i style={{ width: `${Math.max(1, receivableShare * 100)}%` }} />
                <b className='num'>{formatMoney(d.receivableCent)}</b>
              </div>
              <div>
                <span>{texts.payable}</span>
                <i style={{ width: `${Math.max(1, (1 - receivableShare) * 100)}%` }} />
                <b className='num'>{formatMoney(d.payableCent)}</b>
              </div>
            </div>
            <p className='fb-net'>
              {texts.net30}: <strong className='num'>{formatMoney(d.net30Cent)}</strong>
            </p>
            <small className='fb-note'>{texts.notCash}</small>
          </section>
          <section className='fb-card fb-allocation'>
            <span className='fb-eyebrow'>{texts.distribution}</span>
            <div className='fb-ring'>
              <svg viewBox='0 0 160 160' role='img' aria-labelledby={id}>
                <title id={id}>{fmt(texts.share, { pct })}</title>
                <circle className='fb-ring-track' cx='80' cy='80' r='62' fill='none' strokeWidth='9' />
                <circle
                  className='fb-ring-value'
                  cx='80'
                  cy='80'
                  r='62'
                  fill='none'
                  strokeWidth='9'
                  strokeDasharray={`${receivableShare * 389.56} 389.56`}
                  transform='rotate(-90 80 80)'
                />
              </svg>
              <div>
                <strong>
                  {pct}
                  <small>%</small>
                </strong>
                <span>{texts.toCollect}</span>
              </div>
            </div>
            <div className='fb-legend'>
              <span>
                <i />
                {texts.receivable}
              </span>
              <span>
                <i />
                {texts.payable}
              </span>
            </div>
          </section>
          <section className='fb-card fb-kpi'>
            <ArrowDownLeft size={17} aria-hidden='true' />
            <span>{texts.receivable}</span>
            <strong className='num'>{formatMoney(d.receivableCent)}</strong>
            <small>{countText(withBalance('client'), texts.clientsWithBalance, texts.clientsWithBalanceOne)}</small>
          </section>
          <section className='fb-card fb-kpi'>
            <ArrowUpRight size={17} aria-hidden='true' />
            <span>{texts.payable}</span>
            <strong className='num'>{formatMoney(d.payableCent)}</strong>
            <small>{countText(withBalance('provider'), texts.providersWithBalance, texts.providersWithBalanceOne)}</small>
          </section>
          <section className='fb-card fb-companies'>
            <div className='fb-section-heading'>
              <h3>{texts.where}</h3>
              <div className='fb-tabs' role='group' aria-label={texts.byKind}>
                <button type='button' aria-pressed={group === 'client'} onClick={() => setGroup('client')}>
                  {texts.clients}
                </button>
                <button type='button' aria-pressed={group === 'provider'} onClick={() => setGroup('provider')}>
                  {texts.providers}
                </button>
              </div>
            </div>
            <div className='fb-bars'>
              {rows.map((p) => (
                <button
                  type='button'
                  key={p.id}
                  onClick={() => onOpenParty?.(p)}
                  aria-label={fmt(texts.openParty, { name: p.name, amount: formatMoney(p.balanceCent) })}
                >
                  <span>
                    {p.name}
                    <b className='num'>{formatMoney(p.balanceCent)}</b>
                  </span>
                  <div>
                    <i style={{ width: `${(p.balanceCent / max) * 100}%` }} />
                  </div>
                </button>
              ))}
            </div>
            <p className='fb-note'>{leader ? fmt(texts.leader, { name: leader.name }) : texts.noBalance}</p>
          </section>
        </div>
      </section>
    </div>
  );
}
