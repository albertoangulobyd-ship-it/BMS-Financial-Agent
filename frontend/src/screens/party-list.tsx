// Leveranciers / Klanten (Providers / Clients): "bij wie staat er wat open, en wat valt op?".
// Una fila por relacion, la mas urgente primero (el orden de la API, §8), con un buscador y
// cinco columnas: prioridad, nombre, openstaand, vervallen y por que (su hallazgo mas urgente,
// escrito desde sus valores). Una fila abre su ficha en una pestana.
import { DataTable, type Columns } from '@/components/data-table';
import { PageHeader, Screen } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { SearchBox } from '@/components/search-box';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { useNav } from '@/shell/navigation';
import { Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { countText, fmt, useT } from '@/i18n';
import { paths } from '@/lib/api';
import type { PartyRow } from '@/lib/api-types';
import { NO_VALUE, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useViewState } from '@/lib/view-memory';
import { matches } from '@/lib/text';
import { partyWhy } from '@/lib/why';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

export type PartyKind = 'provider' | 'client';

export function PartyListScreen({ kind, navKey }: { kind: PartyKind; navKey: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const navId = kind === 'provider' ? 'providers' : 'clients';
  const [state, retry] = useLoad(
    () =>
      kind === 'provider'
        ? session!.api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores)
        : session!.api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
    [session, version, kind]
  );
  const [query, setQuery] = useViewState<string>(navKey, `${navId}-query`, '');
  const nav = t.nav[navId];

  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <PartyTable kind={kind} rows={state.data} query={query} setQuery={setQuery} caption={nav.description} />
      )}
    </Screen>
  );
}

function PartyTable({
  kind,
  rows,
  query,
  setQuery,
  caption,
}: {
  kind: PartyKind;
  rows: PartyRow[];
  query: string;
  setQuery: (q: string) => void;
  caption: string;
}) {
  const { t, lang } = useT();
  const { open: openRoute } = useNav();
  if (rows.length === 0) {
    return <EmptyState title={t.empty.nothingHere} text={kind === 'provider' ? t.parties.emptyProviders : t.parties.emptyClients} />;
  }
  const shown = rows.filter((r) => matches(query, r.nombre, r.exact_id));
  const label = t.records[kind].label;
  const overdueText = (cents: number) => fmt(t.parties.overdue, { amount: formatMoney(cents) });

  const columns: Columns<PartyRow> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => <StatusPill group='prioridad' state={r.nivel} /> },
    {
      key: 'name',
      header: t.parties.name,
      primary: true,
      cell: (r) => (
        <span className='flex min-w-0 flex-col items-start'>
          <span className='text-[13.5px]'>{r.nombre}</span>
          <span className='text-xs font-normal text-muted-foreground'>
            {countText(t, 'invoices', r.facturas)}
            {!r.activo && ` · ${t.parties.inactive}`}
          </span>
        </span>
      ),
    },
    {
      key: 'outstanding',
      header: t.parties.outstanding,
      align: 'right',
      width: '9rem',
      // La cifra de la cartera (la del resumen de Te betalen / Te ontvangen) y, aparte, sus
      // abonos sin enlazar: una empresa, un solo "Openstaand" (revision del paso 16).
      cell: (r) => (
        <span className='flex flex-col items-end'>
          <OutsideEuro cents={r.deuda_cent} outside={r.sin_importe ?? 0} />
          <UnlinkedCredit party={r} className='text-right' />
        </span>
      ),
    },
    {
      key: 'overdue',
      header: t.parties.overdueColumn,
      align: 'right',
      width: '8rem',
      cell: (r) =>
        // Cero en euros con facturas en otra moneda no es "nada vencido": no se sabe en euros.
        r.vencido_cent === 0 && (r.sin_importe ?? 0) > 0 ? (
          <span className='text-muted-foreground'>{NO_VALUE}</span>
        ) : (
          <Money cents={r.vencido_cent} className={r.vencido_cent > 0 ? 'font-medium text-late-foreground' : 'text-muted-foreground'} />
        ),
    },
    { key: 'why', header: t.columns.why, cell: (r) => <WhyCell why={partyWhy(r, lang, t, overdueText)} /> },
  ];

  return (
    <>
      <div className='mb-3 flex flex-wrap items-center justify-end gap-3'>
        <SearchBox value={query} onChange={setQuery} placeholder={t.parties.searchName} />
      </div>
      <DataTable
        columns={columns}
        rows={shown}
        rowKey={(r) => r.id}
        caption={caption}
        onOpen={(r) => openRoute(recordRoute(kind, r.id))}
        openLabel={(r) => fmt(t.common.openRecord, { what: `${label} ${r.nombre}` })}
        empty={<EmptyState title={t.empty.noMatch} text={t.empty.noMatchText} />}
      />
      {shown.length > 0 && (
        <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.parties.total, { shown: shown.length, all: rows.length })}</p>
      )}
    </>
  );
}

/** "Creditnota nog niet gekoppeld: −€ 362,03": lo que acreditan los abonos sin enlazar de una
 *  empresa, debajo de su "Openstaand" (que no los resta: es la cifra de la cartera, R4). */
export function UnlinkedCredit({
  party: p,
  className,
}: {
  party: Pick<PartyRow, 'abonos_sin_enlazar_cent' | 'abonos_sin_enlazar_facturas'>;
  className?: string;
}) {
  const { t } = useT();
  if (!p.abonos_sin_enlazar_cent) return null;
  const amount = formatMoney(p.abonos_sin_enlazar_cent);
  const text =
    p.abonos_sin_enlazar_facturas > 1
      ? fmt(t.parties.unlinkedCreditMany, { n: p.abonos_sin_enlazar_facturas, amount })
      : fmt(t.parties.unlinkedCredit, { amount });
  return (
    <span data-testid='unlinked-credit' className={`block text-xs text-muted-foreground ${className ?? ''}`}>
      {text}
    </span>
  );
}

/** Lo pendiente en euros y, si hay facturas en otra moneda, cuantas quedan fuera de la suma:
 *  "€ 0,00" solo no diria que se debe algo en dolares. */
function OutsideEuro({ cents, outside }: { cents: number; outside: number }) {
  const { t } = useT();
  if (outside === 0) return <Money cents={cents} />;
  return (
    <span className='flex flex-col items-end'>
      {cents === 0 ? <span className='text-muted-foreground'>{NO_VALUE}</span> : <Money cents={cents} />}
      <span className='whitespace-nowrap text-xs text-muted-foreground'>{fmt(outside === 1 ? t.parties.notInEuroOne : t.parties.notInEuro, { n: outside })}</span>
    </span>
  );
}
