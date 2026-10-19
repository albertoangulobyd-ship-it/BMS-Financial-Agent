// Importeren (Import): "welk bestand wil je inlezen, en wat zou er gebeuren?". Tres pasos en
// una tarjeta: elegir el fichero (una exportacion de Exact, del banco, de TRNSPRNT, una hoja
// de PO o un maestro), su clase (se reconoce sola, o se elige) y el dia en que se saco.
// "Eerst proberen" lo importa simulando (POST /api/v2/importar con simular: no guarda nada) y
// dice en palabras lo que entraria, cambiaria o se rechazaria; solo despues, con un boton y
// una confirmacion aparte, se importa de verdad. Debajo, de cuando es cada fuente (su
// frescura) y, plegadas, las ultimas importaciones. Ni procesos ni red: el fichero va al
// programa local, como cualquier orden.
import { FileUp, LoaderCircle, TriangleAlert } from 'lucide-react';
import { useRef, useState, type ReactNode } from 'react';
import { DataTable, type Columns } from '@/components/data-table';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { ErrorState, Loading, TechnicalDetail, errorMessage } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { DateText } from '@/components/values';
import { fmt, useT, type Messages } from '@/i18n';
import { importKindLabel, stateLabel } from '@/i18n/domain';
import { ApiError, paths, toBase64, type ImportBatch, type ImportKind, type ImportResult } from '@/lib/api';
import type { ImportHistoryRow, ImportsInfo, SourceFreshness } from '@/lib/api-types';
import { formatDate, formatDateTime, parseTypedDate, todayIso } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useLoad } from './use-load';

/** Lo que diria la prueba de un lote (grupo importar_prueba): con filas rechazadas, con
 *  errores; con avisos o con valores que chocan con uno puesto a mano, con avisos; si no, en
 *  orden. Despues de importar manda el estado de la importacion (grupo importacion). */
export function previewState(b: Pick<ImportBatch, 'rechazadas' | 'avisos' | 'sin_resolver'>): 'ok' | 'avisos' | 'errores' {
  if (b.rechazadas > 0) return 'errores';
  if (b.avisos.length > 0 || b.sin_resolver > 0) return 'avisos';
  return 'ok';
}

/** "1,5 MB" / "320 kB": el tamano de un fichero, en notacion neerlandesa. */
export function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    const tenths = Math.round((bytes * 10) / (1024 * 1024));
    return `${Math.floor(tenths / 10)},${tenths % 10} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} kB`;
}

/** El dia (Amsterdam) en que se guardo el fichero; si dice que es del futuro, hoy. */
export function fileDay(lastModified: number, now: Date = new Date()): string {
  const today = todayIso(now);
  const day = todayIso(new Date(lastModified));
  return day > today ? today : day;
}

export function ImportScreen() {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(() => session!.api.get<ImportsInfo>(paths.imports), [session, version]);
  const nav = t.nav.import;
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <div className='flex max-w-4xl flex-col gap-10'>
          <Importer info={state.data} />
          <Freshness rows={state.data.fuentes} />
          <Section title={t.importing.historyTitle} summary={String(state.data.importaciones.length)}>
            <History rows={state.data.importaciones} />
          </Section>
        </div>
      )}
    </Screen>
  );
}

type Phase = 'idle' | 'trying' | 'previewed' | 'importing' | 'done';

/** Lo que se probo y la importacion de verdad vuelve a mandar tal cual. */
interface TriedWith {
  pick: ImportKind | null;
  exportado: string | null;
  confirmar: boolean;
}

function Importer({ info }: { info: ImportsInfo }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { bump } = useRefresh();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState('');
  const [exported, setExported] = useState('');
  const [confirmPlanning, setConfirmPlanning] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [dateProblem, setDateProblem] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  // Lo que se probo (la clase, el dia de exportacion, la confirmacion del planning): la
  // importacion de verdad manda exactamente eso, no lo que diga el formulario despues.
  const [tried, setTried] = useState<TriedWith | null>(null);
  const limit = formatSize(info.limite_bytes);

  /** Algo de lo probado cambio: la prueba ya no vale y hay que volver a probar. */
  function stale() {
    setResult(null);
    setTried(null);
    setPhase('idle');
  }

  function choose(next: File | null) {
    setFile(next);
    setResult(null);
    setTried(null);
    setError(null);
    setConfirmPlanning(false);
    setPhase('idle');
    setProblem(next && next.size > info.limite_bytes ? fmt(t.importing.tooBig, { size: limit }) : null);
    setExported(next ? formatDate(fileDay(next.lastModified)) : '');
  }

  function reset() {
    choose(null);
    setKind('');
    if (inputRef.current) inputRef.current.value = '';
  }

  async function send(simulate: boolean, chosen: ImportKind | null = null) {
    if (!session || !file || problem) return;
    let params: TriedWith;
    if (simulate) {
      const day = exported.trim() ? parseTypedDate(exported) : null;
      if (exported.trim() && day === null) {
        setDateProblem(fmt(t.action.badDate, { field: t.importing.exported }));
        return;
      }
      const pick = chosen ?? (kind ? { fuente: kind.split('/')[0]!, tipo: kind.split('/')[1]! } : null);
      params = { pick, exportado: day, confirmar: confirmPlanning };
    } else {
      // Sin prueba no se importa; con ella, lo mismo que se probo.
      if (tried === null) return;
      params = tried;
    }
    setDateProblem(null);
    setError(null);
    setPhase(simulate ? 'trying' : 'importing');
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const response = await session.api.importFile({
        fichero: file.name,
        contenido: toBase64(bytes),
        ...(params.pick ? { fuente: params.pick.fuente, tipo: params.pick.tipo } : {}),
        simular: simulate,
        exportado: params.exportado ?? undefined,
        confirmar: params.confirmar || undefined,
      });
      setResult(response);
      // La clase que se reconocio se queda elegida: la importacion de verdad es la misma.
      setKind(`${response.fuente}/${response.tipo}`);
      if (simulate) setTried({ ...params, pick: { fuente: response.fuente, tipo: response.tipo } });
      setPhase(simulate ? 'previewed' : 'done');
      if (!simulate) bump();
    } catch (e) {
      setError(e);
      setResult(null);
      setTried(null);
      setPhase('idle');
    }
  }

  const busy = phase === 'trying' || phase === 'importing';
  const nothingGoesIn = result !== null && result.lotes.every((l) => l.repetida || l.aceptadas === 0);
  const needsPlanningConfirm = error instanceof ApiError && error.code === 'pide_confirmacion';
  const candidates = error instanceof ApiError && error.code === 'tipo_ambiguo' ? error.candidates : [];
  const kindName = result ? importKindLabel(lang, result.fuente, result.tipo) : '';

  return (
    <section aria-labelledby='import-form' className='max-w-4xl rounded-md border border-border bg-card'>
      <h2 id='import-form' className='sr-only'>
        {t.nav.import.label}
      </h2>
      <div className='grid grid-cols-1 gap-5 px-5 py-5 md:grid-cols-[12rem_1fr]'>
        <span className='font-medium'>{t.importing.chooseFile}</span>
        <div className='flex flex-col gap-2'>
          <div className='flex flex-wrap items-center gap-3'>
            {/* El selector del navegador va escondido: su texto saldria en el idioma de
                Windows. El boton de la app lo abre. */}
            <input
              ref={inputRef}
              type='file'
              tabIndex={-1}
              aria-hidden='true'
              className='sr-only'
              accept='.csv,.txt,.xml,.sta,.940,.mt940,.yaml,.yml'
              onChange={(e) => choose(e.target.files?.[0] ?? null)}
            />
            <Button type='button' variant='outline' onClick={() => inputRef.current?.click()} disabled={busy}>
              <FileUp className='mr-2 h-4 w-4' aria-hidden='true' />
              {t.importing.chooseButton}
            </Button>
            <span data-testid='import-file' className={file ? 'text-[13.5px]' : 'text-[13px] text-muted-foreground'}>
              {file ? (
                <>
                  <span data-proper-name=''>{file.name}</span> · {formatSize(file.size)}
                </>
              ) : (
                t.importing.noFile
              )}
            </span>
          </div>
          <p className='text-xs leading-relaxed text-muted-foreground'>{fmt(t.importing.fileHelp, { size: limit })}</p>
          {problem && (
            <p role='alert' className='text-[13px] font-medium text-late-foreground'>
              {problem}
            </p>
          )}
        </div>

        <label htmlFor='import-kind' className='font-medium'>
          {t.importing.kind}
        </label>
        <div>
          <select
            id='import-kind'
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              stale();
            }}
            className='h-9 min-w-[16rem] rounded-md border border-input bg-card px-2.5 text-[13px] text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
          >
            <option value=''>{t.importing.auto}</option>
            {info.tipos.map((k) => (
              <option key={`${k.fuente}/${k.tipo}`} value={`${k.fuente}/${k.tipo}`}>
                {importKindLabel(lang, k.fuente, k.tipo)}
              </option>
            ))}
          </select>
        </div>

        <label htmlFor='import-exported' className='font-medium'>
          {t.importing.exported}
        </label>
        <div className='flex flex-col gap-1.5'>
          <Input
            id='import-exported'
            type='text'
            inputMode='numeric'
            placeholder={t.action.datePlaceholder}
            autoComplete='off'
            value={exported}
            onChange={(e) => {
              setExported(e.target.value);
              if (phase !== 'done') stale();
            }}
            className='h-9 w-40'
          />
          <p className='text-xs leading-relaxed text-muted-foreground'>{t.importing.exportedHelp}</p>
          {dateProblem && (
            <p role='alert' className='text-[13px] font-medium text-late-foreground'>
              {dateProblem}
            </p>
          )}
        </div>
      </div>

      <div className='flex flex-wrap items-center gap-3 border-t border-border px-5 py-4'>
        <Button type='button' onClick={() => send(true)} disabled={!file || Boolean(problem) || busy || phase === 'done'}>
          {phase === 'trying' && <LoaderCircle className='mr-2 h-4 w-4 animate-spin motion-reduce:animate-none' aria-hidden='true' />}
          {phase === 'trying' ? t.importing.trying : t.importing.tryFirst}
        </Button>
        <span className='text-[13px] text-muted-foreground'>{t.importing.tryExplain}</span>
      </div>

      {error !== null && (
        <div role='alert' data-testid='import-error' className='flex flex-col gap-2 border-t border-border bg-[#fdf3e8] px-5 py-4 text-[#4a2205]'>
          <p className='font-medium'>{errorMessage(error, t, lang)}</p>
          {candidates.length > 0 && (
            <div className='flex flex-wrap gap-2'>
              {candidates.map((c) => (
                <Button
                  key={`${c.fuente}/${c.tipo}`}
                  type='button'
                  size='sm'
                  variant='outline'
                  onClick={() => {
                    setKind(`${c.fuente}/${c.tipo}`);
                    void send(true, c);
                  }}
                >
                  {importKindLabel(lang, c.fuente, c.tipo)}
                </Button>
              ))}
            </div>
          )}
          {needsPlanningConfirm && (
            <label className='flex items-center gap-2 text-[13px]'>
              <input
                type='checkbox'
                checked={confirmPlanning}
                onChange={(e) => {
                  setConfirmPlanning(e.target.checked);
                  stale();
                }}
              />
              {t.importing.confirmPlanning}
            </label>
          )}
          <TechnicalDetail error={error} />
        </div>
      )}

      {result && (
        <div className='flex flex-col gap-4 border-t border-border px-5 py-5' data-testid='import-result'>
          <div className='flex flex-wrap items-baseline justify-between gap-2'>
            <h3 className='text-[15px] font-semibold'>{phase === 'done' ? t.importing.resultTitle : t.importing.previewTitle}</h3>
            <span className='text-[13px] text-muted-foreground'>{fmt(t.importing.recognisedAs, { kind: kindName })}</span>
          </div>
          <ImportSummary result={result} done={phase === 'done'} />
          {phase === 'done' ? (
            <div className='flex flex-wrap items-center gap-3'>
              <p className='font-medium'>{t.importing.done}</p>
              <Button type='button' variant='outline' size='sm' onClick={reset}>
                {t.importing.another}
              </Button>
            </div>
          ) : nothingGoesIn ? (
            <p className='text-[13px] text-muted-foreground'>{t.importing.nothingToImport}</p>
          ) : (
            <div>
              <Button type='button' onClick={() => setAsking(true)} disabled={busy}>
                {phase === 'importing' && <LoaderCircle className='mr-2 h-4 w-4 animate-spin motion-reduce:animate-none' aria-hidden='true' />}
                {t.importing.importNow}
              </Button>
            </div>
          )}
        </div>
      )}

      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent closeLabel={t.common.close} className='max-w-lg'>
          <DialogHeader>
            <DialogTitle>{t.importing.confirmTitle}</DialogTitle>
            <DialogDescription>{fmt(t.importing.confirmText, { file: file?.name ?? '', kind: kindName })}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setAsking(false)}>
              {t.common.cancel}
            </Button>
            <Button
              type='button'
              onClick={() => {
                setAsking(false);
                void send(false);
              }}
            >
              {t.importing.importNow}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

/** Lo que hizo (o haria) cada lote, en frases cortas; lo rechazado con su fila y su codigo, y
 *  la frase del importador (en castellano, para el soporte) plegada. */
function ImportSummary({ result, done }: { result: ImportResult; done: boolean }) {
  const { t } = useT();
  return (
    <div className='flex flex-col gap-4'>
      {result.lotes.map((batch, index) => (
        <Batch key={`${batch.tipo}-${index}`} batch={batch} done={done} />
      ))}
      <ChecksAfter result={result} />
      {result.pagos && (result.pagos.casados > 0 || result.pagos.propuestas > 0) && (
        <p className='text-[13px]'>{fmt(t.importing.payments, { matched: result.pagos.casados, proposed: result.pagos.propuestas })}</p>
      )}
    </div>
  );
}

function Batch({ batch: b, done }: { batch: ImportBatch; done: boolean }) {
  const { t, lang } = useT();
  const kind = stateLabel(lang, 'tipo_importacion', b.tipo) ?? b.tipo;
  if (b.repetida) {
    return (
      <div className='rounded-md border border-border px-4 py-3'>
        <p className='font-medium'>{kind}</p>
        <p className='text-[13px] text-muted-foreground'>{t.importing.repeated}</p>
      </div>
    );
  }
  const parts: string[] = [
    fmt(t.importing.rowsRead, { n: b.filas_leidas }),
    fmt(done ? t.importing.wentIn : t.importing.goIn, { n: b.aceptadas }),
  ];
  if (b.nuevos) parts.push(fmt(t.importing.newRows, { n: b.nuevos }));
  if (b.cambiados) parts.push(fmt(t.importing.changed, { n: b.cambiados }));
  if (b.rechazadas) parts.push(fmt(t.importing.rejected, { n: b.rechazadas }));
  if (b.retirados) parts.push(fmt(t.importing.removed, { n: b.retirados }));
  return (
    <div className='rounded-md border border-border px-4 py-3'>
      <div className='flex flex-wrap items-baseline justify-between gap-2'>
        <p className='font-medium'>{kind}</p>
        {/* En la proef no se dice "Ingelezen": aun no ha entrado nada; dice como saldria. */}
        {done && b.estado ? <StatusPill group='importacion' state={b.estado} /> : !done && <StatusPill group='importar_prueba' state={previewState(b)} />}
      </div>
      <p className='num text-[13px]'>{parts.join(' · ')}</p>
      {b.cuentas && b.cuentas.nuevas > 0 && (
        <p className='text-[13px]'>{fmt(b.cuentas.nuevas === 1 ? t.importing.accountsNewOne : t.importing.accountsNew, { n: b.cuentas.nuevas })}</p>
      )}
      {b.cuentas?.primer_maestro && <p className='text-xs text-muted-foreground'>{t.importing.firstMaster}</p>}
      {b.sin_resolver > 0 && <p className='text-[13px]'>{fmt(t.importing.unresolved, { n: b.sin_resolver })}</p>}
      {b.rechazos.length > 0 && <Rejections batch={b} />}
      {b.avisos.length > 0 && (
        // Los avisos son frases del importador en castellano (para el soporte y la CLI): la app
        // dice cuantos y donde se leen, sin ensenar el castellano.
        <p className='text-[13px]'>
          {fmt(b.avisos.length === 1 ? t.importing.warningsOne : t.importing.warnings, { n: b.avisos.length })}{' '}
          <span className='text-muted-foreground'>{t.importing.warningsWhere}</span>
        </p>
      )}
    </div>
  );
}

function Rejections({ batch: b }: { batch: ImportBatch }) {
  const { t } = useT();
  const shown = b.rechazos.slice(0, 10);
  const codeText = (code: string) => t.importing.rejection[code as keyof Messages['importing']['rejection']] ?? t.importing.rejection.other;
  return (
    <div className='mt-2'>
      <p className='flex items-center gap-1.5 text-[13px] font-medium'>
        <TriangleAlert className='h-3.5 w-3.5 text-muted-foreground' aria-hidden='true' />
        {t.importing.rejectionsTitle}
      </p>
      <ul className='mt-1 flex flex-col gap-1 text-[13px]'>
        {shown.map((r, i) => (
          <li key={`${r.fila}-${i}`}>
            <span className='font-medium'>{r.fila > 0 ? fmt(t.importing.row, { n: r.fila }) : t.importing.wholeFile}</span>
            {': '}
            {codeText(r.codigo)}
          </li>
        ))}
      </ul>
      {b.rechazadas > shown.length && (
        <p className='text-xs text-muted-foreground'>{fmt(t.importing.moreRejections, { n: b.rechazadas - shown.length })}</p>
      )}
      {/* Para el soporte: la fila y el codigo (el motivo del importador es castellano). */}
      <Folded summary={t.errors.technical}>
        <ul className='font-mono text-xs'>
          {shown.map((r, i) => (
            <li key={`${r.fila}-${i}`}>
              {r.fila}: {r.codigo}
            </li>
          ))}
        </ul>
      </Folded>
    </div>
  );
}

function Folded({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className='mt-1 text-xs text-muted-foreground'>
      <summary className='cursor-pointer select-none rounded-sm'>{summary}</summary>
      <div className='mt-1'>{children}</div>
    </details>
  );
}

function ChecksAfter({ result }: { result: ImportResult }) {
  const { t } = useT();
  const h = result.hallazgos;
  const parts: string[] = [];
  if (h.detectado) parts.push(fmt(t.importing.findingsNew, { n: h.detectado }));
  if (h.cerrado_automatico) parts.push(fmt(t.importing.findingsClosed, { n: h.cerrado_automatico }));
  if (h.reabierto) parts.push(fmt(t.importing.findingsReopened, { n: h.reabierto }));
  return (
    <p className='text-[13px]'>
      <span className='font-medium'>{t.importing.checksAfter}: </span>
      {parts.length ? parts.join(' · ') : t.importing.findingsNone}
    </p>
  );
}

/** De cuando es cada fuente: la edad de su ultima exportacion y si pasa de su limite. */
function Freshness({ rows }: { rows: SourceFreshness[] }) {
  const { t, lang } = useT();
  const age = (r: SourceFreshness) => {
    if (r.edad === null) return '—';
    if (r.edad === 0) return t.importing.ageToday;
    return fmt(r.unidad.includes('laborables') ? t.importing.ageWorkdays : t.importing.ageDays, { n: r.edad });
  };
  const limitText = (r: SourceFreshness) =>
    fmt(r.unidad.includes('laborables') ? t.importing.ageWorkdays : t.importing.ageDays, { n: r.limite ?? 0 });
  const columns: Columns<SourceFreshness> = [
    { key: 'data', header: t.importing.data, cell: (r) => importKindLabel(lang, r.fuente, r.tipo) },
    { key: 'exported', header: t.importing.exported, width: '9rem', cell: (r) => <DateText value={r.exportado} /> },
    { key: 'age', header: t.importing.age, width: '9rem', cell: (r) => <span className='num'>{age(r)}</span> },
    {
      key: 'status',
      header: t.parties.status,
      width: '13rem',
      cell: (r) =>
        r.caducada === null ? (
          <StatusPill group='fuente' state='sin_limite' />
        ) : r.caducada ? (
          <StatusPill group='fuente' state='caducada' values={{ n: limitText(r) }} />
        ) : (
          <StatusPill group='fuente' state='al_dia' />
        ),
    },
  ];
  return (
    <section aria-labelledby='freshness' className='max-w-4xl'>
      <h2 id='freshness' className='mb-2 text-[15px] font-semibold'>
        {t.importing.freshnessTitle}
      </h2>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => `${r.fuente}/${r.tipo}`}
        caption={t.importing.freshnessTitle}
        empty={<p className='text-muted-foreground'>{t.importing.historyEmpty}</p>}
      />
    </section>
  );
}

function History({ rows }: { rows: ImportHistoryRow[] }) {
  const { t, lang } = useT();
  const columns: Columns<ImportHistoryRow> = [
    { key: 'when', header: t.importing.when, width: '9.5rem', cell: (r) => <span className='num whitespace-nowrap'>{formatDateTime(r.iniciada_en)}</span> },
    { key: 'what', header: t.importing.what, width: '12rem', cell: (r) => importKindLabel(lang, r.fuente, r.tipo) },
    { key: 'file', header: t.importing.file, cell: (r) => <span data-proper-name='' className='font-mono text-[12px] [overflow-wrap:anywhere]'>{r.fichero ?? '—'}</span> },
    { key: 'who', header: t.importing.who, width: '8rem', cell: (r) => r.persona ?? '—' },
    {
      key: 'result',
      header: t.importing.result,
      width: '12rem',
      cell: (r) => (
        <span className='flex flex-col'>
          <StatusPill group='importacion' state={r.estado} />
          <span className='num text-xs text-muted-foreground'>
            {fmt(r.filas_leidas === 1 ? t.importing.resultRowsOne : t.importing.resultRows, { accepted: r.filas_aceptadas, read: r.filas_leidas })}
          </span>
        </span>
      ),
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      caption={t.importing.historyTitle}
      empty={<p className='text-muted-foreground'>{t.importing.historyEmpty}</p>}
    />
  );
}
