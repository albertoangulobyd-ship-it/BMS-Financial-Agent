// Uitzonderingen / Exceptions: "welke zaken moet iemand nog oplossen, en wie is ermee
// bezig?". Las abiertas, la mas urgente primero: que pasa (el hallazgo mas urgente, en
// palabras normales), de que va (la factura, el cliente, la PO...), en que estado esta y
// quien la lleva, y desde cuando. Una fila abre un panel con lo que hay que saber y las
// ordenes (asignar, esperar a alguien de fuera, resolver), y desde ahi la factura.
import { CircleCheck } from 'lucide-react';
import { useState } from 'react';
import { DataTable, type Columns } from '@/components/data-table';
import { ExceptionActions, ExceptionStatus } from '@/components/exception-block';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { findingDetail, ruleText, stateLabel } from '@/i18n/domain';
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

interface Loaded {
  rows: ExceptionRow[];
  people: Person[];
  names: Names;
}

export function ExceptionsScreen() {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [selected, setSelected] = useState<number | null>(null);
  const [state, retry] = useLoad<Loaded>(async () => {
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
        <>
          <ExceptionsTable data={state.data} onOpen={(r) => setSelected(r.id)} />
          <ExceptionSheet
            data={state.data}
            id={selected}
            onClose={() => setSelected(null)}
            onDone={retry}
          />
        </>
      )}
    </Screen>
  );
}

/** De que va una excepcion: su factura (numero y relacion), o el cliente, la PO, la import. */
function concerns(r: ExceptionRow, names: Names, t: Messages, lang: Lang): { main: string; sub: string | null; twin?: string } {
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
            {c.sub && <span className='text-[13px] text-[#45423c]'>{c.sub}</span>}
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

function ExceptionSheet({
  data,
  id,
  onClose,
  onDone,
}: {
  data: Loaded;
  id: number | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t, lang } = useT();
  const { openRoute } = useTabs();
  const row = data.rows.find((r) => r.id === id) ?? null;
  return (
    <Sheet open={row !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side='right' closeLabel={t.common.close} className='flex w-full flex-col gap-5 overflow-y-auto sm:max-w-lg'>
        {row && (
          <>
            <SheetHeader className='pr-6'>
              {/* De que va (su aviso mas urgente, o el asunto que escribio una persona), no su id. */}
              <SheetTitle>{exceptionSubject(row, lang, t)}</SheetTitle>
              <SheetDescription>
                {(() => {
                  const c = concerns(row, data.names, t, lang);
                  return c.sub ? `${c.main} · ${c.sub}` : c.main;
                })()}
              </SheetDescription>
            </SheetHeader>
            <div>
              <StatusPill group='prioridad' state={row.nivel} />
            </div>
            <section className='flex flex-col gap-3'>
              <h3 className='text-[14px] font-semibold'>{t.exceptions.whatIsWrong}</h3>
              {row.razones.length ? (
                <ul className='flex flex-col gap-3'>
                  {row.razones.slice(0, 6).map((r) => (
                    <li key={r.id} className='text-[13px]'>
                      <span className='font-medium'>{ruleText(lang, r.regla)?.title ?? r.regla}</span>{' '}
                      <span className='font-mono text-[11px] text-muted-foreground'>{r.regla}</span>
                      <p className='leading-relaxed'>{findingDetail(lang, r.regla, r.resultado, r.valores)}</p>
                      <p className='leading-relaxed text-[#45423c]'>
                        <span className='font-medium text-foreground'>{t.invoice.whatToDo} </span>
                        {ruleText(lang, r.regla)?.whatToDo}
                      </p>
                    </li>
                  ))}
                  {row.razones.length > 6 && (
                    <li className='text-xs text-muted-foreground'>{fmt(t.why.more, { n: row.razones.length - 6 })}</li>
                  )}
                </ul>
              ) : (
                // Una excepcion abierta a mano: su asunto lo escribio una persona.
                <p>{row.titulo}</p>
              )}
            </section>
            <section className='flex flex-col gap-3'>
              <h3 className='text-[14px] font-semibold'>{t.columns.status}</h3>
              <ExceptionStatus exception={row} />
              <ExceptionActions exception={row} people={data.people} onDone={onDone} />
            </section>
            {row.factura_id && (
              <div>
                <Button
                  variant='outline'
                  onClick={() => {
                    onClose();
                    openRoute(recordRoute('invoice', row.factura_id!, 'exceptions'));
                  }}
                >
                  {t.exceptions.openInvoice}
                </Button>
              </div>
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
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
      {why.title && <span className='line-clamp-2 text-[13px] font-normal text-[#45423c]'>{why.text}</span>}
      <span className='text-[11px] font-normal text-muted-foreground'>
        {why.rule && <span className='font-mono'>{why.rule}</span>}
        {why.rule && why.more > 0 && ' · '}
        {why.more > 0 && fmt(why.more === 1 ? t.why.moreOne : t.why.more, { n: why.more })}
      </span>
    </span>
  );
}
