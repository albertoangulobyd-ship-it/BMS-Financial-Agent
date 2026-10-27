// La ficha de una factura (en su pestana): "wat is deze factuur, wat is er mis en wat moet
// ik doen?". Arriba, que es (numero, relacion, importe con btw, prioridad con su razon,
// pago, revision y lo que dice el sistema: "Geen bezwaren van het systeem" cuando esta
// limpia, nunca "goedgekeurd"). Despues lo que necesita atencion, cada cosa con que hacer
// y sus botones, y la lista corta para terminar (nakijken, uitzondering, notitie). Los
// detalles (campos, regels, referencias, koppelingen, planning, notas, historia, el
// original) van plegados debajo. Tras cada orden se vuelve a leer la ficha y las cuentas.
import { useEffect, type ReactNode } from 'react';
import { ActionButton } from '@/components/action-dialog';
import { ExceptionActions, ExceptionStatus } from '@/components/exception-block';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText, Money } from '@/components/values';
import { fmt, useT, type Lang } from '@/i18n';
import { directionLabel, paymentStateLabel, ruleText, stateLabel, verdict } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { InvoiceDetail, Person } from '@/lib/api-types';
import { formatDateProse, formatMoney } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { FieldsTable } from './invoice-fields';
import { FindingsList, sortFindings } from './invoice-findings';
import {
  AddNoteButton,
  HistoryList,
  LinesTable,
  NoDataList,
  NotesList,
  OriginalDocument,
  PlanningTable,
  ReferencesList,
  RelationsList,
} from './invoice-sections';
import { useLoad } from './use-load';

export function InvoiceScreen({ id, tabId }: { id: number; tabId: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { setTabTitle } = useTabs();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ factura: InvoiceDetail }>(paths.invoice(id)).then((r) => r.factura),
        session!.api.get<{ personas: Person[] }>(paths.people).then((r) => r.personas),
      ]),
    [session, id, version]
  );

  // La pestana toma el numero de la factura (texto del documento: se pinta como texto).
  const numero = state.status === 'ready' ? state.data[0].numero : null;
  useEffect(() => {
    if (numero) setTabTitle(tabId, numero);
  }, [numero, tabId, setTabTitle]);

  const fallback = fmt(t.records.invoice.fallbackTitle, { id });
  if (state.status !== 'ready') {
    return (
      <Screen>
        <PageHeader title={fallback} description={t.invoice.question} />
        {state.status === 'loading' ? <Loading /> : <ErrorState error={state.error} onRetry={retry} />}
      </Screen>
    );
  }
  return <InvoiceView invoice={state.data[0]} people={state.data[1]} reload={retry} />;
}

function InvoiceView({ invoice: f, people, reload }: { invoice: InvoiceDetail; people: Person[]; reload: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const value = (name: string) => f.campos.find((c) => c.campo === name)?.valor ?? null;
  const total = value('total_cent') as number | null;
  const date = value('fecha_factura') as string | null;
  const e = f.estado;
  const findings = sortFindings(f.hallazgos);
  const pending = findings.length;
  const accepted = findings.filter((h) => h.estado === 'aceptado').length;
  const fieldsToVerify = (e?.sin_resolver ?? 0) + (e?.dudosos ?? 0);
  const v = verdict(lang, { pendientes: pending, aceptados: accepted, sin_datos: e?.sin_datos ?? 0, campos: fieldsToVerify });
  const kind = stateLabel(lang, 'tipo_factura', (value('tipo') as string | null) ?? 'factura') ?? t.records.invoice.label;
  const direction = directionLabel(lang, f.sentido);
  const title = `${kind} ${f.numero ?? f.id}`;
  const template =
    total === null
      ? f.sentido === 'entrante'
        ? t.invoice.whatIsInNoAmount
        : t.invoice.whatIsOutNoAmount
      : f.sentido === 'entrante'
        ? t.invoice.whatIsIn
        : t.invoice.whatIsOut;
  const description = fmt(template, {
    party: f.contraparte ?? '—',
    date: formatDateProse(date, t),
    amount: formatMoney(total),
  });
  const openFindings = findings.filter((h) => h.estado !== 'aceptado');
  const reason = priorityReason(f, lang);

  return (
    <Screen>
      <PageHeader title={title} description={description} meta={direction ?? undefined} />

      {/* Cinco datos en una fila a 1440 px; mas estrecho, la prioridad arriba y los demas
          de dos en dos, sin huecos. */}
      <dl className='mb-8 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border text-[13px] xl:grid-cols-5'>
        <Fact label={t.columns.priority} wide>
          <span className='flex flex-col items-start gap-1'>
            <StatusPill group='prioridad' state={e?.nivel ?? 'normal'} />
            {reason && <span className='text-[12.5px] text-soft-foreground'>{reason}</span>}
          </span>
        </Fact>
        <Fact label={t.invoice.totalLabel}>
          <Money cents={total} className='text-[15px] font-semibold' />
        </Fact>
        <Fact label={t.invoice.dueLabel}>
          <DateText value={f.vencimiento?.fecha} prose />
        </Fact>
        <Fact label={t.invoice.paymentLabel}>
          <StatusPill group='pago' state={e?.estado_pago} />
          {e?.pendiente_cent !== null && e?.pendiente_cent !== undefined && e.estado_pago !== 'pagada' && (
            <span className='mt-1 block text-xs text-muted-foreground'>
              {fmt(t.invoice.outstanding, { amount: formatMoney(e.pendiente_cent) })}
            </span>
          )}
        </Fact>
        <Fact label={t.invoice.reviewLabel}>
          <StatusPill group='revision' state={e?.estado_revision} />
        </Fact>
      </dl>

      {f.anulada && <p className='mb-6 rounded-md border border-border bg-muted px-4 py-3'>{t.invoice.cancelled}</p>}

      <section aria-labelledby='attention' className='mb-8'>
        {/* Lo que dice el sistema va con lo que necesita atencion: la parte mas seria en su
            pastilla y las demas detras, en gris. */}
        <div className='mb-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2'>
          <h2 id='attention' className='text-[16px] font-semibold'>
            {t.invoice.attentionTitle}
            {openFindings.length > 0 && <span className='ml-2 text-[13px] font-normal text-muted-foreground'>{openFindings.length}</span>}
          </h2>
          <div data-testid='verdict' className='flex flex-wrap items-center gap-x-3 gap-y-1'>
            <StatusPill group='veredicto' state={v.main.state} values={v.main.values} />
            {v.parts.length > 1 && (
              <span className='text-xs text-muted-foreground'>
                {v.parts
                  .filter((p) => p !== v.main)
                  .map((p) => p.text)
                  .join('; ')}
              </span>
            )}
          </div>
        </div>
        <FindingsList invoice={f} people={people} onDone={reload} />
      </section>

      <section aria-labelledby='finish' className='mb-10'>
        <h2 id='finish' className='mb-3 text-[16px] font-semibold'>
          {t.invoice.finishTitle}
        </h2>
        <ol className='flex flex-col divide-y divide-divider rounded-md border border-border bg-card'>
          <Step title={t.invoice.reviewStep}>
            <ReviewStep invoice={f} onDone={reload} />
          </Step>
          <Step
            title={
              <span className='inline-flex items-center gap-1'>
                {t.invoice.exceptionStep} <HelpTip term='exception' />
              </span>
            }
          >
            {f.excepcion ? (
              <div className='flex flex-col gap-3'>
                <ExceptionStatus exception={f.excepcion} />
                <ExceptionActions exception={f.excepcion} people={people} onDone={reload} />
              </div>
            ) : (
              <div className='flex flex-wrap items-center gap-3'>
                <span className='text-muted-foreground'>{t.invoice.noException}</span>
                {can('resolver_aviso') && (
                  <ActionButton
                    action='crear_excepcion'
                    label={t.invoice.openException}
                    fields={[
                      { name: 'titulo', label: t.invoice.exceptionSubject, kind: 'text', required: true },
                      { name: 'motivo', label: t.invoice.exceptionWhy, kind: 'textarea' },
                    ]}
                    data={(vals) => ({ tabla: 'factura', fila_id: f.id, titulo: vals.titulo, motivo: vals.motivo || undefined })}
                    onDone={reload}
                  />
                )}
              </div>
            )}
          </Step>
          {can('anadir_informacion') && (
            <Step title={t.invoice.noteStep}>
              <div className='flex flex-wrap items-center gap-3'>
                <span className='text-muted-foreground'>{fmt(t.invoice.notesCount, { n: f.notas.length })}</span>
                <AddNoteButton invoiceId={f.id} onDone={reload} />
              </div>
            </Step>
          )}
        </ol>
      </section>

      <Section title={t.sections.fields}>
        <FieldsTable invoice={f} onDone={reload} />
      </Section>
      <Section title={t.sections.lines} summary={String(f.lineas.filter((l) => !l.retirada).length)}>
        <LinesTable invoice={f} />
      </Section>
      <Section title={t.sections.references} summary={String(f.referencias.filter((r) => !r.retirada).length)}>
        <ReferencesList invoice={f} />
      </Section>
      <Section title={t.sections.relations} summary={String(f.relaciones.filter((r) => !r.retirada).length)}>
        <RelationsList invoice={f} onDone={reload} />
      </Section>
      <Section title={t.sections.planning} summary={String(f.conciliacion.reduce((n, c) => n + c.turnos.length, 0))}>
        <PlanningTable invoice={f} />
      </Section>
      <Section title={t.sections.notes} summary={String(f.notas.length)}>
        <NotesList invoice={f} onDone={reload} />
      </Section>
      <Section title={t.sections.noData} summary={String(f.reglas_sin_datos.length)}>
        <NoDataList invoice={f} />
      </Section>
      <Section title={t.sections.history}>
        <HistoryList invoice={f} />
      </Section>
      <Section title={t.sections.original}>
        <OriginalDocument invoice={f} />
      </Section>
    </Screen>
  );
}

function Fact({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? 'col-span-2 bg-card px-4 py-3 xl:col-span-1' : 'bg-card px-4 py-3'}>
      <dt className='mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>{label}</dt>
      <dd className='m-0'>{children}</dd>
    </div>
  );
}

function Step({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <li className='grid grid-cols-1 gap-2 px-4 py-3.5 md:grid-cols-[12rem_1fr] md:gap-6'>
      <span className='font-medium'>{title}</span>
      <div>{children}</div>
    </li>
  );
}

/** Nakijken: marcar revisada (con la huella de lo que se vio) o devolver con un motivo. */
function ReviewStep({ invoice: f, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const { t } = useT();
  const can = useCan();
  const last = f.revisiones[0];
  const reviewed = f.estado?.estado_revision === 'revisada';
  const blocked = f.pide_revision.length > 0;
  return (
    <div className='flex flex-col gap-2'>
      {reviewed && last ? (
        <p>{fmt(t.invoice.reviewedBy, { name: last.usuario ?? '—', date: formatDateProse(last.en, t) })}</p>
      ) : blocked ? (
        <p className='text-soft-foreground'>{t.invoice.reviewBlocked}</p>
      ) : (
        <p className='text-soft-foreground'>{t.invoice.reviewReady}</p>
      )}
      {!reviewed && can('revisar_factura') && (
        <div className='flex flex-wrap gap-2'>
          {!blocked && (
            <ActionButton
              action='marcar_revisada'
              label={t.invoice.markReviewed}
              variant='default'
              intro={t.invoice.markReviewedIntro}
              fields={[{ name: 'motivo', label: t.action.note, kind: 'textarea' }]}
              data={(v) => ({ factura_id: f.id, huella: f.huella_contenido, motivo: v.motivo || undefined })}
              onDone={onDone}
            />
          )}
          <ActionButton
            action='devolver_factura'
            label={t.invoice.returnInvoice}
            intro={t.invoice.returnIntro}
            fields={[{ name: 'motivo', label: t.invoice.returnWhy, kind: 'textarea', required: true }]}
            data={(v) => ({ factura_id: f.id, huella: f.huella_contenido, motivo: v.motivo })}
            onDone={onDone}
          />
        </div>
      )}
    </div>
  );
}

/** La razon con nombre de la prioridad: la del hallazgo mas grave, o que va tarde. */
function priorityReason(f: InvoiceDetail, lang: Lang): string | null {
  const first = sortFindings(f.hallazgos).find((h) => h.estado !== 'aceptado');
  if (first) return ruleText(lang, first.regla)?.title ?? null;
  if (f.estado?.estado_pago === 'vencida') return paymentStateLabel(lang, 'vencida');
  return null;
}
