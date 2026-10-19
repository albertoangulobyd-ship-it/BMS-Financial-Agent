// Un trimestre del btw (en su pestana): "kloppen de cijfers, en wat moet er nog gebeuren?".
// Arriba su estado y sus cifras (omzet, btw sobre la omzet, voorbelasting, saldo y plazo);
// despues lo que hay que mirar antes de que las cifras valgan (facturas por revisar, las que
// no entran, lo cambiado despues de dejarlo listo) y los pasos para terminar: bajar el
// werkblad (CSV), dejar el trimestre listo para revisar y, cuando una persona ya presento la
// aangifte en el portal de la Belastingdienst, anotarlo con su referencia. El programa no
// presenta nada. Plegado, las cifras por rubriek.
import { Download, LoaderCircle } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { ActionButton } from '@/components/action-dialog';
import { NothingNeedsAttention } from '@/components/attention-list';
import { DataTable, type Columns } from '@/components/data-table';
import { Fact, FactStrip } from '@/components/fact-strip';
import { HelpTip } from '@/components/help-tip';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { ErrorState, Loading, errorMessage } from '@/components/states';
import { StatusText } from '@/components/status-text';
import { VAT_TONE } from '@/components/tones';
import { Button } from '@/components/ui/button';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { Money } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { actionText, ruleText, stateLabel } from '@/i18n/domain';
import { vatQuarterPath } from '@/lib/api';
import type { VatQuarter, VatRubric } from '@/lib/api-types';
import { MINUS, formatCents, formatDateProse, formatMoney, idToQuarter, quarterLabel } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { recordRoute } from './registry';
import { Deadline, balanceText } from './vat';
import { useLoad } from './use-load';

/** Un importe para escribirlo en un campo: "4.743,86" o "-409,70" (el menos de teclado). */
export function plainAmount(cents: number): string {
  const text = formatCents(Math.abs(cents)) ?? '0,00';
  return cents < 0 ? `-${text}` : text;
}

export function VatQuarterScreen({ id, tabId }: { id: number; tabId: string }) {
  const { t } = useT();
  const { session } = useSession();
  const { setTabTitle } = useTabs();
  const { version } = useRefresh();
  const label = idToQuarter(id);
  const [state, retry] = useLoad(
    () => session!.api.get<{ trimestre: VatQuarter }>(vatQuarterPath(label ?? '')).then((r) => r.trimestre),
    [session, label, version]
  );
  const title = fmt(t.vat.title, { quarter: quarterLabel(label) });
  useEffect(() => {
    setTabTitle(tabId, title);
  }, [title, tabId, setTabTitle]);
  if (state.status !== 'ready') {
    return (
      <Screen>
        <PageHeader title={title} description={t.vat.question} />
        {state.status === 'loading' ? <Loading /> : <ErrorState error={state.error} onRetry={retry} />}
      </Screen>
    );
  }
  return <QuarterDetail quarter={state.data} title={title} />;
}

function QuarterDetail({ quarter: q, title }: { quarter: VatQuarter; title: string }) {
  const { t, lang } = useT();
  const c = q.cifras;
  const balance = c['5c'];
  return (
    <Screen>
      <PageHeader
        title={title}
        description={fmt(t.vat.span, { from: formatDateProse(q.inicio, t), to: formatDateProse(q.fin, t) })}
        meta={<HelpTip term='btw' />}
      />
      <FactStrip>
        <Fact label={t.vat.status}>
          <StatusText tone={VAT_TONE[q.estado] ?? 'neutral'}>{stateLabel(lang, 'btw', q.estado) ?? q.estado}</StatusText>
        </Fact>
        <Fact label={t.vat.balance} note={balance > 0 ? t.vat.toPayShort : balance < 0 ? t.vat.refundShort : undefined}>
          <Money cents={Math.abs(balance)} className='text-[15px] font-semibold' />
        </Fact>
        <Fact label={t.vat.deadline}>
          <Deadline row={q} />
        </Fact>
        <Fact label={t.vat.revenue}>
          <Money cents={c.ingresos_cent} className='text-[15px] font-semibold' />
        </Fact>
        <Fact label={t.vat.output} note='5a'>
          <Money cents={c.iva_repercutido_cent} className='text-[15px] font-semibold' />
        </Fact>
        <Fact label={t.vat.input} note={`5b · ${t.vat.inputHelp}`}>
          <Money cents={c.iva_deducible_cent} className='text-[15px] font-semibold' />
        </Fact>
      </FactStrip>
      {!q.configuracion.confirmada && <p className='-mt-4 mb-6 text-[13px] text-late-foreground'>{t.vat.configNotConfirmed}</p>}

      <section aria-labelledby='vat-attention' className='mb-8'>
        <h2 id='vat-attention' className='mb-3 text-[16px] font-semibold'>
          {t.invoice.attentionTitle}
        </h2>
        <QuarterAttention quarter={q} />
      </section>

      <section aria-labelledby='vat-finish' className='mb-10'>
        <h2 id='vat-finish' className='mb-3 text-[16px] font-semibold'>
          {t.invoice.finishTitle}
        </h2>
        <ol className='flex flex-col divide-y divide-[#ebe7df] rounded-md border border-border bg-card'>
          <Step title={t.vat.stepSheet}>
            <SheetStep quarter={q} />
          </Step>
          <Step title={t.vat.stepReady}>
            <ReadyStep quarter={q} />
          </Step>
          <Step title={t.vat.stepFile}>
            <FileStep quarter={q} />
          </Step>
        </ol>
      </section>

      <Section title={t.vat.sectionRubrics} summary={String(c.rubricas.length)}>
        <Rubrics quarter={q} />
      </Section>
    </Screen>
  );
}

function Step({ title, children }: { title: string; children: ReactNode }) {
  return (
    <li className='grid grid-cols-1 gap-2 px-4 py-3.5 md:grid-cols-[12rem_1fr] md:gap-6'>
      <span className='font-medium'>{title}</span>
      <div className='flex flex-col gap-2'>{children}</div>
    </li>
  );
}

/** Lo que hay que mirar: facturas por revisar, las que no entran en las cifras y lo que
 *  cambio despues de dejarlo listo. Cada una abre su factura. */
function QuarterAttention({ quarter: q }: { quarter: VatQuarter }) {
  const { t, lang } = useT();
  const { openRoute } = useTabs();
  const open = (id: number) => openRoute(recordRoute('invoice', id, 'vat'));
  const outside = [...(q.cifras.sin_clasificar ?? []), ...(q.cifras.fuera ?? [])];
  // Una factura que no entra en las cifras viene tambien en revisar, sin reglas: se dice una vez, abajo.
  const outsideIds = new Set(outside.map((r) => r.factura_id));
  const review = q.revisar.filter((r) => r.reglas.length > 0 || !outsideIds.has(r.factura_id));
  const changedSheet = q.estado === 'listo_revision' && !q.hoja_al_dia;
  if (review.length === 0 && outside.length === 0 && q.diferencias.length === 0 && !changedSheet) {
    return <NothingNeedsAttention text={t.vat.nothingToCheck} />;
  }
  return (
    <div className='flex flex-col gap-4'>
      {changedSheet && <p className='rounded-md border border-[#e2c1a8] bg-[#fdf3e8] px-4 py-3 text-[#4a2205]'>{t.vat.sheetChanged}</p>}
      {review.length > 0 && (
        <Group title={t.vat.reviewInvoices}>
          {review.map((r) => (
            <InvoiceLine key={r.factura_id} number={r.numero} party={r.contraparte} onOpen={() => open(r.factura_id)}>
              {r.reglas.map((rule) => (
                <span key={rule} className='block'>
                  {ruleText(lang, rule)?.title ?? rule} <span className='font-mono text-[11px] text-muted-foreground'>{rule}</span>
                </span>
              ))}
            </InvoiceLine>
          ))}
        </Group>
      )}
      {outside.length > 0 && (
        <Group title={t.vat.outside}>
          {outside.map((r) => (
            <InvoiceLine key={r.factura_id} number={r.numero} party={r.contraparte} onOpen={() => open(r.factura_id)}>
              {t.vat.outsideText}
            </InvoiceLine>
          ))}
        </Group>
      )}
      {q.diferencias.length > 0 && (
        <Group title={t.vat.changedAfter}>
          {q.diferencias.map((d) => (
            <InvoiceLine key={d.factura_id} number={String(d.factura_id)} party={null} onOpen={() => open(d.factura_id)}>
              {t.vat.changeKinds[d.motivo as keyof typeof t.vat.changeKinds] ?? d.motivo}
            </InvoiceLine>
          ))}
        </Group>
      )}
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className='mb-2 text-[13px] font-semibold text-[#45423c]'>{title}</h3>
      <ul className='divide-y divide-[#ebe7df] overflow-hidden rounded-md border border-border bg-card'>{children}</ul>
    </div>
  );
}

function InvoiceLine({
  number,
  party,
  onOpen,
  children,
}: {
  number: string | null;
  party: string | null;
  onOpen: () => void;
  children: ReactNode;
}) {
  const { t } = useT();
  return (
    <li>
      <button
        type='button'
        onClick={onOpen}
        aria-label={fmt(t.parties.openInvoice, { number: number ?? '' })}
        className='grid w-full grid-cols-[minmax(10rem,16rem)_1fr] items-start gap-4 px-4 py-3 text-left hover:bg-[#f4f1ea]'
      >
        <span className='flex min-w-0 flex-col'>
          <span className='truncate font-mono text-[12.5px] font-medium text-primary'>{number ?? '—'}</span>
          {party && <span className='truncate text-[13px] text-[#45423c]'>{party}</span>}
        </span>
        <span className='text-[13px] leading-snug'>{children}</span>
      </button>
    </li>
  );
}

/** Bajar el werkblad: fetch con el token, Blob y a[download] (api.download). */
function SheetStep({ quarter: q }: { quarter: VatQuarter }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function download() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await session.api.download(vatQuarterPath(q.etiqueta, '/hoja.csv'), `btw-${q.etiqueta}.csv`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <p className='text-[#45423c]'>{t.vat.stepSheetText}</p>
      <div>
        <Button type='button' variant='outline' size='sm' onClick={download} disabled={busy}>
          {busy ? (
            <LoaderCircle className='mr-2 h-4 w-4 animate-spin motion-reduce:animate-none' aria-hidden='true' />
          ) : (
            <Download className='mr-2 h-4 w-4' aria-hidden='true' />
          )}
          {t.vat.downloadSheet}
        </Button>
      </div>
      {error !== null && (
        <p role='alert' className='text-[13px] text-late-foreground'>
          {errorMessage(error, t, lang)}
        </p>
      )}
    </>
  );
}

/** Dejarlo listo para revisar (con la huella del werkblad que se ve) o devolverlo a abierto. */
function ReadyStep({ quarter: q }: { quarter: VatQuarter }) {
  const { t, lang } = useT();
  const can = useCan();
  const allowed = can('gestionar_btw');
  if (q.estado === 'presentado') {
    return <p className='text-[#45423c]'>{q.listo_por ? fmt(t.vat.stepReadyDone, { name: q.listo_por }) : t.vat.nextFiled}</p>;
  }
  if (q.estado === 'listo_revision') {
    return (
      <>
        <p>{fmt(t.vat.stepReadyDone, { name: q.listo_por ?? '—' })}</p>
        {allowed && q.rev !== null && (
          <div>
            <ActionButton
              action='btw_reabrir'
              label={actionText(lang, 'btw_reabrir')?.label ?? t.vat.stepReady}
              intro={t.vat.reopenIntro}
              fields={[{ name: 'motivo', label: t.vat.explanation, kind: 'textarea', required: true }]}
              data={(v) => ({ trimestre: q.etiqueta, rev: q.rev, motivo: v.motivo })}
            />
          </div>
        )}
      </>
    );
  }
  if (!q.terminado) return <p className='text-[#45423c]'>{fmt(t.vat.stepReadyRunning, { date: formatDateProse(q.fin, t) })}</p>;
  return (
    <>
      <p className='text-[#45423c]'>{t.vat.stepReadyText}</p>
      {allowed && (
        <div>
          <ActionButton
            action='btw_lista_para_revision'
            label={actionText(lang, 'btw_lista_para_revision')?.label ?? t.vat.stepReady}
            variant='default'
            intro={t.vat.readyIntro}
            fields={[{ name: 'motivo', label: t.vat.explanation, kind: 'textarea', required: true }]}
            data={(v) => ({ trimestre: q.etiqueta, hoja_sha256: q.hoja_sha256, motivo: v.motivo })}
          />
        </div>
      )}
    </>
  );
}

/** Anotar la aangifte que una persona ya presento en el portal (no presenta nada). */
function FileStep({ quarter: q }: { quarter: VatQuarter }) {
  const { t, lang } = useT();
  const can = useCan();
  if (q.estado === 'presentado') {
    return (
      <p>
        {fmt(t.vat.filedText, {
          date: formatDateProse(q.presentado_en, t),
          name: q.presentado_por ?? '—',
          ref: q.referencia ?? '—',
          amount: formatMoney(q.importe_declarado_cent),
        })}
      </p>
    );
  }
  if (q.estado !== 'listo_revision') return <p className='text-[#45423c]'>{t.vat.stepFileWait}</p>;
  return (
    <>
      <p className='text-[#45423c]'>{t.vat.stepFileText}</p>
      {can('gestionar_btw') && q.rev !== null && (
        <div>
          <ActionButton
            action='btw_anotar_presentacion'
            label={actionText(lang, 'btw_anotar_presentacion')?.label ?? t.vat.stepFile}
            fields={[
              { name: 'referencia', label: t.vat.reference, kind: 'text', required: true },
              {
                name: 'importe_declarado',
                label: t.vat.declared,
                kind: 'text',
                required: true,
                initial: plainAmount(q.cifras['5c']),
                help: t.vat.declaredHelp,
              },
              { name: 'fecha_presentacion', label: t.vat.filedOn, kind: 'date', help: t.vat.filedOnHelp },
              { name: 'motivo', label: t.vat.explanation, kind: 'textarea', required: true },
            ]}
            data={(v) => ({
              trimestre: q.etiqueta,
              rev: q.rev,
              hoja_sha256: q.hoja_marcada_sha256,
              referencia: v.referencia,
              importe_declarado: (v.importe_declarado ?? '').replace(MINUS, '-'),
              fecha_presentacion: v.fecha_presentacion || undefined,
              motivo: v.motivo,
            })}
          />
        </div>
      )}
    </>
  );
}

function Rubrics({ quarter: q }: { quarter: VatQuarter }) {
  const { t } = useT();
  const c = q.cifras;
  const label = (code: string) => t.vat.rubrics[code as keyof typeof t.vat.rubrics] ?? code;
  const rows: VatRubric[] = [
    ...c.rubricas,
    { rubrica: '5a', omzet_cent: null, btw_cent: c['5a'] },
    { rubrica: '5b', omzet_cent: null, btw_cent: c['5b'] },
    { rubrica: '5c', omzet_cent: null, btw_cent: c['5c'] },
  ];
  const columns: Columns<VatRubric> = [
    { key: 'rubric', header: t.vat.rubric, width: '6rem', cell: (r) => <span className='font-mono text-[12.5px]'>{r.rubrica}</span> },
    { key: 'description', header: t.vat.description, cell: (r) => label(r.rubrica) },
    {
      key: 'turnover',
      header: t.vat.turnover,
      align: 'right',
      width: '10rem',
      cell: (r) => (r.omzet_cent === null ? <span className='text-muted-foreground'>—</span> : <Money cents={r.omzet_cent} />),
    },
    { key: 'vat', header: t.vat.vat, align: 'right', width: '10rem', cell: (r) => <Money cents={r.btw_cent} /> },
  ];
  return (
    <div className='flex flex-col gap-2'>
      <DataTable columns={columns} rows={rows} rowKey={(r) => r.rubrica} caption={t.vat.sectionRubrics} />
      <p className='text-xs text-muted-foreground'>{balanceText(c['5c'], t)}</p>
    </div>
  );
}
