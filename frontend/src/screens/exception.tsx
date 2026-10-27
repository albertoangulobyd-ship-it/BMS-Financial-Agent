// Una excepcion, como ficha dentro de Inicio (paso 16; en el paso 15 era un panel lateral sobre
// la lista): de que va (su aviso mas urgente o el asunto que escribio una persona), que pasa,
// que hacer, en que estado esta y quien la lleva, con sus ordenes (zelf oppakken, toewijzen,
// wachten op anderen, oplossen) y la factura. Cuando ya no esta abierta (se resolvio aqui o en
// otro sitio), lo dice y lleva a la lista.
import { CircleCheck } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { ExceptionActions, ExceptionStatus } from '@/components/exception-block';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { Button } from '@/components/ui/button';
import { fmt, useT } from '@/i18n';
import { findingDetail, ruleText } from '@/i18n/domain';
import type { ExceptionRow } from '@/lib/api-types';
import { useNav } from '@/shell/navigation';
import { concerns, exceptionSubject, useExceptions, type Loaded } from './exceptions';
import { recordRoute } from './registry';

export function ExceptionScreen({ id, navKey }: { id: number; navKey: string }) {
  const { t, lang } = useT();
  const { setTitle } = useNav();
  const [state, retry] = useExceptions();
  const row = state.status === 'ready' ? (state.data.rows.find((r) => r.id === id) ?? null) : null;
  // El asunto de la ultima vez que se vio: si se resuelve aqui, la miga sigue diciendo cual era.
  const subject = useRef<string | null>(null);
  if (row) subject.current = exceptionSubject(row, lang, t);
  useEffect(() => {
    if (subject.current) setTitle(navKey, subject.current);
  }, [row, navKey, setTitle]);

  const fallback = fmt(t.records.exception.fallbackTitle, { id });
  if (state.status !== 'ready') {
    return (
      <Screen>
        <PageHeader title={fallback} description={t.nav.exceptions.description} />
        {state.status === 'loading' ? <Loading /> : <ErrorState error={state.error} onRetry={retry} />}
      </Screen>
    );
  }
  if (!row) return <NotOpen title={subject.current ?? fallback} />;
  return <ExceptionDetail row={row} data={state.data} onDone={retry} />;
}

function NotOpen({ title }: { title: string }) {
  const { t } = useT();
  const nav = useNav();
  return (
    <Screen>
      <PageHeader title={title} description={t.nav.exceptions.description} />
      <EmptyState
        icon={CircleCheck}
        title={t.exceptions.notOpen}
        text={t.exceptions.notOpenText}
        action={
          <Button variant='outline' onClick={() => nav.go('exceptions')}>
            {t.exceptions.backToList}
          </Button>
        }
      />
    </Screen>
  );
}

function ExceptionDetail({ row, data, onDone }: { row: ExceptionRow; data: Loaded; onDone: () => void }) {
  const { t, lang } = useT();
  const nav = useNav();
  const c = concerns(row, data.names, t, lang);
  return (
    <Screen>
      <PageHeader
        title={exceptionSubject(row, lang, t)}
        description={c.sub ? `${c.main} · ${c.sub}` : c.main}
        meta={<HelpTip term='exception' />}
        action={
          row.factura_id ? (
            <Button variant='outline' onClick={() => nav.open(recordRoute('invoice', row.factura_id!))}>
              {t.exceptions.openInvoice}
            </Button>
          ) : undefined
        }
      />
      <div className='mb-6'>
        <StatusPill group='prioridad' state={row.nivel} />
      </div>
      <div className='grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]'>
        <section aria-labelledby='exc-what' className='flex flex-col gap-3'>
          <h2 id='exc-what' className='text-[16px] font-semibold'>
            {t.exceptions.whatIsWrong}
          </h2>
          {row.razones.length ? (
            <ul className='flex flex-col divide-y divide-divider rounded-md border border-border bg-card'>
              {row.razones.slice(0, 6).map((r) => (
                <li key={r.id} className='px-4 py-3 text-[13.5px]'>
                  <span className='font-medium'>{ruleText(lang, r.regla)?.title ?? r.regla}</span>{' '}
                  <span className='font-mono text-[11px] text-muted-foreground'>{r.regla}</span>
                  <p className='mt-1 leading-relaxed'>{findingDetail(lang, r.regla, r.resultado, r.valores)}</p>
                  <p className='mt-1 leading-relaxed text-soft-foreground'>
                    <span className='font-medium text-foreground'>{t.invoice.whatToDo} </span>
                    {ruleText(lang, r.regla)?.whatToDo}
                  </p>
                </li>
              ))}
              {row.razones.length > 6 && (
                <li className='px-4 py-2 text-xs text-muted-foreground'>{fmt(t.why.more, { n: row.razones.length - 6 })}</li>
              )}
            </ul>
          ) : (
            // Una excepcion abierta a mano: su asunto lo escribio una persona.
            <p className='rounded-md border border-border bg-card px-4 py-3'>{row.titulo}</p>
          )}
        </section>
        <section aria-labelledby='exc-status' className='flex flex-col gap-3'>
          <h2 id='exc-status' className='text-[16px] font-semibold'>
            {t.columns.status}
          </h2>
          <div className='flex flex-col gap-3 rounded-md border border-border bg-card px-4 py-4'>
            <ExceptionStatus exception={row} />
            <ExceptionActions exception={row} people={data.people} onDone={onDone} />
          </div>
        </section>
      </div>
    </Screen>
  );
}
