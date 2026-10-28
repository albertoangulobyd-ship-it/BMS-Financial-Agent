// Importar, dentro del panel Cuentas por cobrar (especificacion §2.2.6): el contenido del panel 4
// de Aurora (main.tsx:37 del dueno) en el mismo panel, con el h2 "Importar". La .dropzone elige
// el fichero (una exportacion de Exact, un extracto del banco, la planificacion de TRNSPRNT, una
// hoja de PO o un maestro); su .file-chip con la ✕; la clase (se reconoce sola o se elige, con
// .filter-combo-trigger) y el dia de exportacion (.filter-date-trigger y el calendario).
// "Probar primero" (.primary) lo importa simulando (POST /api/v2/importar con simular: no guarda
// nada) y lo que pasaria sale en una tarjeta .detail, una linea p por cosa. Solo despues,
// "Importar de verdad" (.primary) con su "si" en .chat-export, y al final .success. Sin fichero
// elegido, dos filas: de cuando es cada fuente y las ultimas importaciones (cada una, su vista).
// Las reglas de antes no cambian: una sola accion principal cada vez, lo que se importa es lo
// probado y cambiar la clase o el dia borra la prueba. Ni procesos ni red: el fichero va al
// programa local, como cualquier orden.
import { ArrowUpRight, FileText, Plus, X } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { countText, fmt, useT, type Messages } from '@/i18n';
import { importKindLabel, stateLabel } from '@/i18n/domain';
import { ApiError, paths, toBase64, type ImportBatch, type ImportKind, type ImportResult } from '@/lib/api';
import type { ImportHistoryRow, ImportsInfo, SourceFreshness } from '@/lib/api-types';
import { formatDate } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { rowTone, statusLabel } from '@/components/status-pill';
import { useLoad } from '../use-load';
import { ConfirmCard, ErrorLine, FieldInput, apiErrorMessage } from '../orders';
import { Detail, GroupView, List, Row } from './pieces';
import { fileDay, formatSize, previewState, primaryImportAction, type ImportPhase } from './panel-model';

const AUTO = 'auto';

/** Lo que se probo y la importacion de verdad vuelve a mandar tal cual. */
interface TriedWith {
  pick: ImportKind | null;
  exportado: string | null;
  confirmar: boolean;
}

/** La edad de una fuente: "hoy", "3 dias" o "5 dias laborables". */
function sourceAge(t: Messages, r: Pick<SourceFreshness, 'edad' | 'unidad'>): string {
  if (r.edad === null) return '—';
  if (r.edad === 0) return t.importing.ageToday;
  return countText(t, r.unidad.includes('laborables') ? 'workdays' : 'days', r.edad);
}

function sourceState(r: SourceFreshness): 'al_dia' | 'caducada' | 'sin_limite' {
  return r.caducada === null ? 'sin_limite' : r.caducada ? 'caducada' : 'al_dia';
}

export function ImportView({ view, onView, backLabel }: { view: string; onView: (view: string | null) => void; backLabel: string }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state] = useLoad(() => session!.api.get<ImportsInfo>(paths.imports), [session, version]);
  const back = () => onView('import');
  const backToImport = fmt(t.aurora.panel.backTo, { what: t.nav.import.label });
  if (state.status === 'error') return <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} />;
  if (state.status !== 'ready') return null;
  const info = state.data;

  if (view === 'import-sources') {
    return (
      <GroupView
        items={info.fuentes}
        title={t.aurora.import.sources.toUpperCase()}
        match={(r) => importKindLabel(lang, r.fuente, r.tipo)}
        render={(r) => {
          const s = sourceState(r);
          const limit = countText(t, r.unidad.includes('laborables') ? 'workdays' : 'days', r.limite ?? 0);
          return (
            <Row
              key={`${r.fuente}/${r.tipo}`}
              label={importKindLabel(lang, r.fuente, r.tipo)}
              note={
                r.exportado
                  ? fmt(t.aurora.import.exportedOn, {
                      date: formatDate(r.exportado),
                    })
                  : t.aurora.import.neverExported
              }
              figure={sourceAge(t, r)}
              state={statusLabel(lang, t, 'fuente', s, { n: limit }) ?? s}
              tone={rowTone('fuente', s)}
              onOpen={() => undefined}
            />
          );
        }}
        backLabel={backToImport}
        onBack={back}
      />
    );
  }
  if (view === 'import-history') {
    return (
      <GroupView
        items={info.importaciones}
        title={t.importing.historyTitle.toUpperCase()}
        match={(r: ImportHistoryRow) => `${importKindLabel(lang, r.fuente, r.tipo)} ${r.fichero ?? ''} ${r.persona ?? ''}`}
        render={(r) => (
          // El fichero, de que es y quien lo leyo, el dia y como acabo: en una linea cada cosa,
          // para que la vista no se desplace mas que la de Aurora (especificacion §6.1).
          <Row
            key={r.id}
            label={r.fichero ?? importKindLabel(lang, r.fuente, r.tipo)}
            data={Boolean(r.fichero)}
            note={[r.fichero ? importKindLabel(lang, r.fuente, r.tipo) : null, r.persona].filter(Boolean).join(' · ')}
            noteData
            figure={formatDate(r.iniciada_en)}
            state={statusLabel(lang, t, 'importacion', r.estado) ?? r.estado}
            tone={rowTone('importacion', r.estado)}
            onOpen={() => undefined}
          />
        )}
        backLabel={backToImport}
        onBack={back}
      />
    );
  }
  return <Importer info={info} onView={onView} backLabel={backLabel} />;
}

function Importer({ info, onView, backLabel }: { info: ImportsInfo; onView: (view: string | null) => void; backLabel: string }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { bump } = useRefresh();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState(AUTO);
  const [exported, setExported] = useState('');
  const [phase, setPhase] = useState<ImportPhase>('idle');
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  // Lo que se probo: la importacion de verdad manda exactamente eso.
  const [tried, setTried] = useState<TriedWith | null>(null);
  const limit = formatSize(info.limite_bytes);
  const m = t.aurora.import;

  /** Algo de lo probado cambio: la prueba ya no vale y hay que volver a probar. */
  function stale() {
    setResult(null);
    setTried(null);
    setAsking(false);
    setPhase('idle');
  }

  function choose(next: File | null) {
    setFile(next);
    stale();
    setError(null);
    setProblem(next && next.size > info.limite_bytes ? fmt(t.importing.tooBig, { size: limit }) : null);
    setExported(next ? fileDay(next.lastModified) : '');
  }

  function reset() {
    choose(null);
    setKind(AUTO);
    if (inputRef.current) inputRef.current.value = '';
  }

  async function send(simulate: boolean, options: { pick?: ImportKind; confirmar?: boolean } = {}) {
    if (!session || !file || problem) return;
    let params: TriedWith;
    if (simulate) {
      const chosen = options.pick ?? (kind !== AUTO ? { fuente: kind.split('/')[0]!, tipo: kind.split('/')[1]! } : null);
      params = {
        pick: chosen,
        exportado: exported || null,
        confirmar: options.confirmar ?? false,
      };
    } else {
      // Sin prueba no se importa; con ella, lo mismo que se probo.
      if (tried === null) return;
      params = tried;
    }
    setError(null);
    setAsking(false);
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
      if (simulate)
        setTried({
          ...params,
          pick: { fuente: response.fuente, tipo: response.tipo },
        });
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
  const primary = primaryImportAction(phase, result !== null && !nothingGoesIn);
  const oldest = [...info.fuentes].filter((r) => r.edad !== null).sort((a, b) => (b.edad ?? 0) - (a.edad ?? 0))[0];
  const anyStale = info.fuentes.some((r) => r.caducada === true);
  const last = info.importaciones[0];

  return (
    <>
      {/* El selector del navegador va escondido: su texto saldria en el idioma de Windows. */}
      <input
        ref={inputRef}
        type='file'
        tabIndex={-1}
        aria-hidden='true'
        className='sr-only'
        accept='.csv,.txt,.xml,.sta,.940,.mt940,.yaml,.yml'
        onChange={(e) => choose(e.target.files?.[0] ?? null)}
      />
      <button className='dropzone' onClick={() => inputRef.current?.click()} disabled={busy}>
        <Plus />
        <strong>{m.drop}</strong>
        <span>{m.dropHelp}</span>
      </button>
      {file ? (
        <>
          <div className='file-chip' data-testid='import-file'>
            <FileText size={15} />
            <span data-proper-name=''>{file.name}</span> · {formatSize(file.size)}
            <button aria-label={fmt(m.remove, { file: file.name })} onClick={reset} disabled={busy}>
              <X size={14} />
            </button>
          </div>
          {problem && (
            <p role='alert' className='order-error'>
              {problem}
            </p>
          )}
          <FieldInput
            field={{
              name: 'kind',
              label: t.importing.kind,
              kind: 'select',
              hideOptional: true,
              options: [
                { value: AUTO, label: t.importing.auto },
                ...info.tipos.map((k) => ({
                  value: `${k.fuente}/${k.tipo}`,
                  label: importKindLabel(lang, k.fuente, k.tipo),
                })),
              ],
            }}
            value={kind}
            onChange={(v) => {
              setKind(v);
              stale();
            }}
          />
          <FieldInput
            field={{
              name: 'exported',
              label: t.importing.exported,
              kind: 'date',
              hideOptional: true,
              help: t.importing.exportedHelp,
            }}
            value={exported}
            onChange={(v) => {
              setExported(v);
              if (phase !== 'done') stale();
            }}
          />
          {primary === 'try' && (
            <button className='primary' disabled={Boolean(problem) || busy} onClick={() => void send(true)}>
              {phase === 'trying' ? t.importing.trying : t.importing.tryFirst}
              <ArrowUpRight size={16} />
            </button>
          )}
          {error !== null && (
            <div data-testid='import-error' className='order-form'>
              <ErrorLine error={error} message={apiErrorMessage(error, t, lang)} />
              {candidates.map((c) => (
                <button
                  key={`${c.fuente}/${c.tipo}`}
                  className='outline'
                  onClick={() => {
                    setKind(`${c.fuente}/${c.tipo}`);
                    void send(true, { pick: c });
                  }}
                >
                  {importKindLabel(lang, c.fuente, c.tipo)}
                </button>
              ))}
              {needsPlanningConfirm && (
                <button className='outline' onClick={() => void send(true, { confirmar: true })}>
                  {t.importing.confirmPlanning}
                </button>
              )}
            </div>
          )}
          {result && (
            <ImportResultCard result={result} done={phase === 'done'} kindName={kindName} onClose={reset}>
              {phase !== 'done' && nothingGoesIn && <p>{t.importing.nothingToImport}</p>}
              {primary === 'import' && !asking && (
                <div>
                  <button className='primary' disabled={busy} onClick={() => setAsking(true)}>
                    {phase === 'importing' ? t.importing.trying : t.importing.importNow}
                    <ArrowUpRight size={16} />
                  </button>
                </div>
              )}
              {asking && file && (
                <ConfirmCard
                  label={t.importing.confirmTitle}
                  text={fmt(t.importing.confirmText, {
                    file: file.name,
                    kind: kindName,
                  })}
                  busy={busy}
                  onConfirm={() => void send(false)}
                  onCancel={() => setAsking(false)}
                />
              )}
            </ImportResultCard>
          )}
          {phase === 'done' && <Done onAnother={reset} />}
        </>
      ) : (
        <List title={m.listTitle} count={[info.fuentes.length > 0, info.importaciones.length > 0].filter(Boolean).length}>
          {info.fuentes.length > 0 && (
            <Row
              label={m.sources}
              note={m.sourcesNote}
              figure={oldest ? sourceAge(t, oldest) : '—'}
              state={anyStale ? m.someStale : m.allFresh}
              tone={anyStale ? '' : 'paid'}
              onOpen={() => onView('import-sources')}
            />
          )}
          {info.importaciones.length > 0 && (
            <Row
              label={t.importing.historyTitle}
              note={m.historyNote}
              figure={String(info.importaciones.length)}
              state={last ? formatDate(last.iniciada_en) : undefined}
              onOpen={() => onView('import-history')}
            />
          )}
        </List>
      )}
      <p className='privacy'>{m.privacy}</p>
      <button className='outline' onClick={() => onView(null)}>
        {backLabel}
      </button>
    </>
  );
}

/** "Importado" y el aviso, a la vista (.success), con "Otro archivo". */
function Done({ onAnother }: { onAnother: () => void }) {
  const { t } = useT();
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => ref.current?.scrollIntoView({ block: 'nearest' }), []);
  return (
    <>
      <p className='success' role='status' ref={ref}>
        {t.importing.done}
      </p>
      <button className='outline' onClick={onAnother}>
        {t.importing.another}
      </button>
    </>
  );
}

/** Lo que pasaria (o lo que ha pasado): una tarjeta .detail con una linea p por cosa. */
function ImportResultCard({
  result,
  done,
  kindName,
  onClose,
  children,
}: {
  result: ImportResult;
  done: boolean;
  kindName: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useT();
  const h = result.hallazgos;
  const checks: string[] = [];
  if (h.detectado) checks.push(fmt(h.detectado === 1 ? t.importing.findingsNewOne : t.importing.findingsNew, { n: h.detectado }));
  if (h.cerrado_automatico)
    checks.push(fmt(h.cerrado_automatico === 1 ? t.importing.findingsClosedOne : t.importing.findingsClosed, { n: h.cerrado_automatico }));
  if (h.reabierto) checks.push(fmt(h.reabierto === 1 ? t.importing.findingsReopenedOne : t.importing.findingsReopened, { n: h.reabierto }));
  return (
    <div data-testid='import-result'>
      <Detail title={done ? t.importing.resultTitle : t.importing.previewTitle} onClose={onClose}>
        <p>{fmt(t.importing.recognisedAs, { kind: kindName })}</p>
        {result.lotes.map((batch, index) => (
          <BatchLines key={`${batch.tipo}-${index}`} batch={batch} done={done} />
        ))}
        <p>
          {t.importing.checksAfter}: {checks.length ? checks.join(' · ') : t.importing.findingsNone}
        </p>
        {result.pagos && (result.pagos.casados > 0 || result.pagos.propuestas > 0) && (
          <p>
            {fmt(t.importing.payments, {
              matched: fmt(result.pagos.casados === 1 ? t.importing.paymentsMatchedOne : t.importing.paymentsMatched, { n: result.pagos.casados }),
              proposed: fmt(result.pagos.propuestas === 1 ? t.importing.paymentsProposedOne : t.importing.paymentsProposed, { n: result.pagos.propuestas }),
            })}
          </p>
        )}
        {children}
      </Detail>
    </div>
  );
}

/** Lo que hizo (o haria) un lote, en lineas p: leidas, entrarian, nuevas, cambian, rechazadas
 *  con su motivo, cuentas nuevas y avisos; y su estado en el span. */
function BatchLines({ batch: b, done }: { batch: ImportBatch; done: boolean }) {
  const { t, lang } = useT();
  const kind = stateLabel(lang, 'tipo_importacion', b.tipo) ?? b.tipo;
  if (b.repetida) {
    return (
      <p>
        {kind}: {t.importing.repeated}
      </p>
    );
  }
  const parts: string[] = [
    fmt(b.filas_leidas === 1 ? t.importing.rowsReadOne : t.importing.rowsRead, {
      n: b.filas_leidas,
    }),
    done
      ? fmt(b.aceptadas === 1 ? t.importing.wentInOne : t.importing.wentIn, {
          n: b.aceptadas,
        })
      : fmt(b.aceptadas === 1 ? t.importing.goInOne : t.importing.goIn, {
          n: b.aceptadas,
        }),
  ];
  if (b.nuevos)
    parts.push(
      fmt(b.nuevos === 1 ? t.importing.newRowsOne : t.importing.newRows, {
        n: b.nuevos,
      })
    );
  if (b.cambiados)
    parts.push(
      fmt(b.cambiados === 1 ? t.importing.changedOne : t.importing.changed, {
        n: b.cambiados,
      })
    );
  if (b.rechazadas)
    parts.push(
      fmt(b.rechazadas === 1 ? t.importing.rejectedOne : t.importing.rejected, {
        n: b.rechazadas,
      })
    );
  if (b.retirados)
    parts.push(
      fmt(b.retirados === 1 ? t.importing.removedOne : t.importing.removed, {
        n: b.retirados,
      })
    );
  const codeText = (code: string) => t.importing.rejection[code as keyof Messages['importing']['rejection']] ?? t.importing.rejection.other;
  const shown = b.rechazos.slice(0, 3);
  const state = done && b.estado ? statusLabel(lang, t, 'importacion', b.estado) : statusLabel(lang, t, 'importar_prueba', previewState(b));
  return (
    <>
      <p>
        {kind}: {parts.join(' · ')}
      </p>
      {shown.map((r, i) => (
        <p key={`${r.fila}-${i}`}>
          {r.fila > 0 ? fmt(t.importing.row, { n: r.fila }) : t.importing.wholeFile}: {codeText(r.codigo)} <small data-proper-name=''>({r.codigo})</small>
        </p>
      ))}
      {b.rechazadas > shown.length && shown.length > 0 && <p>{fmt(t.importing.moreRejections, { n: b.rechazadas - shown.length })}</p>}
      {b.cuentas && b.cuentas.nuevas > 0 && (
        <p>{fmt(b.cuentas.nuevas === 1 ? t.importing.accountsNewOne : t.importing.accountsNew, { n: b.cuentas.nuevas })}</p>
      )}
      {b.cuentas?.primer_maestro && <p>{t.importing.firstMaster}</p>}
      {b.sin_resolver > 0 && <p>{fmt(b.sin_resolver === 1 ? t.importing.unresolvedOne : t.importing.unresolved, { n: b.sin_resolver })}</p>}
      {b.avisos.length > 0 && (
        <p>
          {fmt(b.avisos.length === 1 ? t.importing.warningsOne : t.importing.warnings, { n: b.avisos.length })} · {t.importing.warningsWhere}
        </p>
      )}
      {state && <span>{state}</span>}
    </>
  );
}
