// Inkooporders (Purchase orders): "hoeveel is er van elke PO over, en welke zijn bijna op?".
// Desde el paso 16, una lista por lado: las PO de clientes (las que un cliente dio a BMS) en
// Cuentas por cobrar y las de proveedores (las que BMS dio a un proveedor) en Cuentas por
// pagar. La mas urgente primero, con un buscador y seis columnas: prioridad, la PO (numero, de
// quien o para quien y hasta cuando), waarde, verbruikt (con su porcentaje), over y por que.
// Una fila abre su ficha dentro de la seccion.
import { DataTable, type Columns } from '@/components/data-table';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { SearchBox } from '@/components/search-box';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { useNav } from '@/shell/navigation';
import { Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { fmt, useT } from '@/i18n';
import { stateLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { PoRow } from '@/lib/api-types';
import { formatDate, formatPercentFromBasisPoints } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useViewState } from '@/lib/view-memory';
import { matches } from '@/lib/text';
import { whyOf } from '@/lib/why';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

export function PurchaseOrdersScreen({ side, navKey }: { side: PoRow['lado']; navKey: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () => session!.api.get<{ ordenes: PoRow[] }>(paths.purchaseOrders).then((r) => r.ordenes.filter((o) => o.lado === side)),
    [session, version, side]
  );
  const [query, setQuery] = useViewState<string>(navKey, 'pos-query', '');
  const view = side === 'cliente' ? 'client-pos' : 'provider-pos';
  const nav = t.nav[view];
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} meta={<HelpTip term='po' />} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && <PoTable rows={state.data} query={query} setQuery={setQuery} caption={nav.description} />}
    </Screen>
  );
}

function PoTable({ rows, query, setQuery, caption }: { rows: PoRow[]; query: string; setQuery: (q: string) => void; caption: string }) {
  const { t, lang } = useT();
  const { open: openRoute } = useNav();
  if (rows.length === 0) return <EmptyState title={t.empty.nothingHere} text={t.pos.empty} />;
  const shown = rows.filter((r) => matches(query, r.numero, r.parte.nombre));
  const columns: Columns<PoRow> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => <StatusPill group='prioridad' state={r.nivel} /> },
    {
      key: 'po',
      header: t.pos.po,
      primary: true,
      width: '15rem',
      cell: (r) => <PoCell row={r} />,
    },
    // La waarde es verbruikt mas over: a 1024 px se deja para que quepa "Waarom".
    { key: 'value', header: t.pos.value, align: 'right', width: '8.5rem', wideOnly: true, cell: (r) => <Money cents={r.valor_cent} /> },
    {
      key: 'used',
      header: t.pos.used,
      align: 'right',
      width: '8.5rem',
      cell: (r) => (
        <span className='flex flex-col items-end'>
          <Money cents={r.consumido_cent} />
          <span className='num text-xs text-muted-foreground'>{formatPercentFromBasisPoints(r.consumido_pb)}</span>
        </span>
      ),
    },
    {
      key: 'left',
      header: t.pos.left,
      align: 'right',
      width: '8.5rem',
      cell: (r) => <Money cents={r.restante_cent} className={r.restante_cent <= 0 ? 'font-medium text-late-foreground' : undefined} />,
    },
    { key: 'why', header: t.columns.why, cell: (r) => <WhyCell why={whyOf({ razones: r.razones }, lang, t)} /> },
  ];
  return (
    <>
      <div className='mb-3 flex flex-wrap items-center justify-end gap-3'>
        <SearchBox value={query} onChange={setQuery} placeholder={t.pos.search} />
      </div>
      <DataTable
        columns={columns}
        rows={shown}
        rowKey={(r) => r.id}
        caption={caption}
        onOpen={(r) => openRoute(recordRoute('purchase-order', r.id))}
        openLabel={(r) => fmt(t.common.openRecord, { what: `${t.records['purchase-order'].label} ${r.numero}` })}
        empty={<EmptyState title={t.empty.noMatch} text={t.empty.noMatchText} />}
      />
      {shown.length > 0 && (
        <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.parties.total, { shown: shown.length, all: rows.length })}</p>
      )}
    </>
  );
}

function PoCell({ row: r }: { row: PoRow }) {
  const { t, lang } = useT();
  return (
    <span className='flex min-w-0 flex-col items-start'>
      <span className='whitespace-nowrap font-mono text-[12.5px]'>{r.numero}</span>
      <span className='text-[13px] font-normal text-foreground'>{r.parte.nombre ?? '—'}</span>
      <span className='text-xs font-normal text-muted-foreground'>
        {stateLabel(lang, 'lado_po', r.lado) ?? r.lado} ·{' '}
        <span className='whitespace-nowrap'>{r.fecha_fin ? fmt(t.pos.until, { date: formatDate(r.fecha_fin) }) : t.pos.noEnd}</span>
      </span>
      {r.cerrada && <StatusPill group='po' state='cerrada' className='mt-1' />}
    </span>
  );
}
