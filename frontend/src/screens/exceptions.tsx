// Uitzonderingen / Exceptions: "welke zaken moet iemand nog oplossen, en wie is ermee
// bezig?". Las abiertas, la mas urgente primero: que pasa (el hallazgo mas urgente, en
// palabras normales), de que va (la factura, el cliente, la PO...), en que estado esta y
// quien la lleva, y desde cuando. Una fila abre la excepcion (paso 16: una ficha dentro de
// Inicio, con sus migas y "Volver"; antes, un panel lateral) con lo que hay que saber, las
// ordenes (asignar, esperar a alguien de fuera, resolver) y desde ahi la factura.
import { CircleCheck } from 'lucide-react';
import { DataTable, type Columns } from '@/components/data-table';
import { ExceptionStatus } from '@/components/exception-block';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { useNav } from '@/shell/navigation';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { stateLabel } from '@/i18n/domain';
import { paths, type InvoiceRow } from '@/lib/api';
import type { ExceptionRow, Person, PoRow } from '@/lib/api-types';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { whyOf } from '@/lib/why';
import { recordRoute } from './registry';
import { useLoad } from './use-load';
import { twinMarks, type TwinMark } from '@/lib/twins';

interface Names {
  invoices: Map<number, InvoiceRow>;
  clients: Map<number, string>;
  orders: Map<number, { numero: string; parte: string | null }>;
  /** Las facturas con el mismo numero y relacion que otra ("1 van 2"). */
  twins: Map<number, TwinMark>;
}

export interface Loaded {
  rows: ExceptionRow[];
  people: Person[];
  names: Names;
}

/** Las excepciones abiertas con lo que hace falta para nombrarlas (la lista y la ficha). */
export function useExceptions() {
  const { session } = useSession();
  const { version } = useRefresh();
  return useLoad<Loaded>(async () => {
    const api = session!.api;
    const [rows, people, invoices, clients, orders] = await Promise.all([
      api.get<{ excepciones: ExceptionRow[] }>(paths.exceptions).then((r) => r.excepciones),
      api.get<{ personas: Person[] }>(paths.people).then((r) => r.personas),
      api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas),
      api.get<{ clientes: { id: number; nombre: string }[] }>(paths.clients).then((r) => r.clientes),
      api.get<{ ordenes: PoRow[] }>(paths.purchaseOrders).then((r) => r.ordenes),
    ]);
    return {
      rows,
      people,
      names: {
        invoices: new Map(invoices.map((f) => [f.id, f])),
        clients: new Map(clients.map((c) => [c.id, c.nombre])),
        orders: new Map(orders.map((o) => [o.id, { numero: o.numero, parte: o.parte.nombre }])),
        twins: twinMarks(invoices),
      },
    };
  }, [session, version]);
}

export function ExceptionsScreen() {
  const { t } = useT();
  const { open: openRoute } = useNav();
  const [state, retry] = useExceptions();
  const nav = t.nav.exceptions;

  return (
    <Screen>
      <PageHeader
        title={nav.label}
        description={nav.description}
        meta={<HelpTip term='exception' />}
      />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <ExceptionsTable data={state.data} onOpen={(r) => openRoute(recordRoute('exception', r.id))} />
      )}
    </Screen>
  );
}

/** De que va una excepcion: su factura (numero y relacion), o el cliente, la PO, la import. */
export function concerns(r: ExceptionRow, names: Names, t: Messages, lang: Lang): { main: string; sub: string | null; twin?: string } {
  if (r.factura_id) {
    const f = names.invoices.get(r.factura_id);
    const twin = names.twins.get(r.factura_id);
    return {
      main: f?.numero ?? fmt(t.records.invoice.fallbackTitle, { id: r.factura_id }),
      sub: f?.contraparte ?? null,
      ...(twin ? { twin: fmt(t.common.twin, { n: twin.n, of: twin.of }) } : {}),
    };
  }
  const entity = stateLabel(lang, 'entidad', r.tabla) ?? null;
  if (r.tabla === 'cliente') return { main: names.clients.get(r.fila_id) ?? `#${r.fila_id}`, sub: entity };
  if (r.tabla === 'orden_compra') {
    // La PO y de quien es (el cliente o el proveedor), no la palabra "PO" otra vez.
    const po = names.orders.get(r.fila_id);
    return { main: po?.numero ?? `#${r.fila_id}`, sub: po?.parte ?? entity };
  }
  if (r.tabla === 'importacion') return { main: fmt(t.exceptions.importNumber, { id: r.fila_id }), sub: null };
  return { main: `${entity ?? r.tabla} #${r.fila_id}`, sub: null };
}

function ExceptionsTable({ data, onOpen }: { data: Loaded; onOpen: (r: ExceptionRow) => void }) {
  const { t, lang } = useT();
  if (!data.rows.length) {
    return <EmptyState icon={CircleCheck} title={t.empty.nothingNeedsAttention} text={t.exceptions.empty} />;
  }
  const columns: Columns<ExceptionRow> = [
    { key: 'priority', header: t.columns.priority, width: '8.5rem', cell: (r) => <StatusPill group='prioridad' state={r.nivel} /> },
    {
      key: 'what',
      header: t.exceptions.what,
      primary: true,
      cell: (r) => <WhatCell row={r} />,
    },
    {
      key: 'concerns',
      header: t.exceptions.concerns,
      width: '14rem',
      cell: (r) => {
        const c = concerns(r, data.names, t, lang);
        return (
          <span className='flex flex-col'>
            <span className={r.factura_id ? 'font-mono text-[12.5px]' : undefined}>
              {c.main}
              {c.twin && <span className='ml-1.5 font-sans text-xs text-muted-foreground'>{c.twin}</span>}
            </span>
            {c.sub && <span className='text-[13px] text-soft-foreground'>{c.sub}</span>}
          </span>
        );
      },
    },
    { key: 'status', header: t.columns.status, width: '13.5rem', cell: (r) => <ExceptionStatus exception={r} /> },
  ];
  return (
    <>
      <DataTable
        columns={columns}
        rows={data.rows}
        rowKey={(r) => r.id}
        caption={t.nav.exceptions.description}
        onOpen={onOpen}
        openLabel={(r) => fmt(t.exceptions.openLabel, { id: r.id })}
      />
      <p className='mt-2 text-xs text-muted-foreground'>{fmt(t.exceptions.total, { n: data.rows.length })}</p>
    </>
  );
}

/** Lo que pasa, en palabras normales: el nombre del hallazgo mas urgente (el enlace de la
 *  fila), su detalle debajo y cuantos mas hay. Una excepcion abierta a mano no tiene
 *  hallazgos: su asunto lo escribio una persona y se ensena tal cual. */
/** El asunto de una excepcion en palabras: el titulo de su aviso mas urgente o el asunto que
 *  tecleo quien la abrio (texto de una persona, tal cual). */
export function exceptionSubject(row: ExceptionRow, lang: Lang, t: Messages): string {
  const why = whyOf(row, lang, t);
  return why ? (why.title ?? why.text) : row.titulo;
}

function WhatCell({ row }: { row: ExceptionRow }) {
  const { t, lang } = useT();
  const why = whyOf(row, lang, t);
  if (!why) return <span>{row.titulo}</span>;
  return (
    <span className='flex flex-col items-start gap-0.5'>
      <span>{why.title ?? why.text}</span>
      {why.title && <span className='line-clamp-2 text-[13px] font-normal text-soft-foreground'>{why.text}</span>}
      <span className='text-[11px] font-normal text-muted-foreground'>
        {why.rule && <span className='font-mono'>{why.rule}</span>}
        {why.rule && why.more > 0 && ' · '}
        {why.more > 0 && fmt(why.more === 1 ? t.why.moreOne : t.why.more, { n: why.more })}
      </span>
    </span>
  );
}
