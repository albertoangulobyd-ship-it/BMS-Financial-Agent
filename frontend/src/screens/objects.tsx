// Objecten (Objects): "wat levert elke locatie op, wat kost ze en wat valt op?". Una fila por
// Object, la mas urgente primero, con un buscador y seis columnas: prioridad, Object (codigo,
// nombre y cliente), opbrengst, kosten y marge de este ano (sin btw) y por que. Una fila abre
// su ficha en una pestana.
import { DataTable, type Columns } from '@/components/data-table';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { PriorityPill } from '@/components/priority-pill';
import { SearchBox } from '@/components/search-box';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { Money } from '@/components/values';
import { WhyCell } from '@/components/why-cell';
import { fmt, useT } from '@/i18n';
import { paths } from '@/lib/api';
import type { ObjectRow, ObjectsList } from '@/lib/api-types';
import { formatPercentFromBasisPoints } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useTabState } from '@/lib/tab-memory';
import { matches } from '@/lib/text';
import { priorityRank, whyOf } from '@/lib/why';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

export function ObjectsScreen({ tabId }: { tabId: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(() => session!.api.get<ObjectsList>(paths.objects), [session, version]);
  const [query, setQuery] = useTabState<string>(tabId, 'objects-query', '');
  const nav = t.nav.objects;
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} meta={<HelpTip term='object' />} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && <ObjectsTable list={state.data} query={query} setQuery={setQuery} />}
    </Screen>
  );
}

function ObjectsTable({ list, query, setQuery }: { list: ObjectsList; query: string; setQuery: (q: string) => void }) {
  const { t, lang } = useT();
  const { openRoute } = useTabs();
  // Lo mas urgente primero, como todas las listas (la API los da por codigo).
  const rows = [...list.objetos].sort((a, b) => priorityRank(a.nivel) - priorityRank(b.nivel));
  if (rows.length === 0) return <EmptyState title={t.empty.nothingHere} text={t.objects.empty} />;
  const shown = rows.filter((r) => matches(query, r.codigo, r.nombre, r.cliente));
  const year = { year: list.ano };
  const columns: Columns<ObjectRow> = [
    { key: 'priority', header: t.columns.priority, width: '8rem', cell: (r) => <PriorityPill priority={r.nivel} /> },
    {
      key: 'object',
      header: t.objects.object,
      primary: true,
      width: '15rem',
      cell: (r) => (
        <span className='flex min-w-0 flex-col items-start'>
          <span className='whitespace-nowrap font-mono text-[12.5px]'>{r.codigo}</span>
          <span className='text-[13px] font-normal text-foreground'>{r.nombre ?? '—'}</span>
          <span className='text-xs font-normal text-muted-foreground'>{r.cliente ?? '—'}</span>
        </span>
      ),
    },
    { key: 'revenue', header: fmt(t.objects.revenue, year), align: 'right', width: '8.5rem', cell: (r) => <Money cents={r.ano.ingresos_cent} /> },
    {
      key: 'costs',
      header: fmt(t.objects.costs, year),
      align: 'right',
      width: '8.5rem',
      wideOnly: true,
      cell: (r) => <Money cents={r.ano.costes_cent} />,
    },
    {
      key: 'margin',
      header: fmt(t.objects.margin, year),
      align: 'right',
      width: '8.5rem',
      cell: (r) => <Margin cents={r.ano.margen_cent} pb={r.ano.margen_pb} />,
    },
    { key: 'why', header: t.columns.why, cell: (r) => <WhyCell why={whyOf({ razones: r.razones }, lang, t)} /> },
  ];
  return (
    <>
      <div className='mb-3 flex flex-wrap items-center justify-end gap-3'>
        <SearchBox value={query} onChange={setQuery} placeholder={t.objects.search} />
      </div>
      <DataTable
        columns={columns}
        rows={shown}
        rowKey={(r) => r.id}
        caption={t.nav.objects.description}
        onOpen={(r) => openRoute(recordRoute('object', r.id, 'objects'))}
        openLabel={(r) => fmt(t.common.openRecord, { what: `${t.records.object.label} ${r.codigo}` })}
        empty={<EmptyState title={t.empty.noMatch} text={t.empty.noMatchText} />}
      />
      {shown.length > 0 && (
        <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.parties.total, { shown: shown.length, all: rows.length })}</p>
      )}
    </>
  );
}

/** Un margen: el importe y su porcentaje debajo; en negativo, en el color de "tarde". */
export function Margin({ cents, pb }: { cents: number; pb: number | null }) {
  const negative = cents < 0;
  return (
    <span className='flex flex-col items-end'>
      <Money cents={cents} className={negative ? 'font-medium text-late-foreground' : undefined} />
      {pb !== null && (
        <span className={negative ? 'num text-xs text-late-foreground' : 'num text-xs text-muted-foreground'}>
          {formatPercentFromBasisPoints(pb)}
        </span>
      )}
    </span>
  );
}
