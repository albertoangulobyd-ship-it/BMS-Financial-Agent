// E2-V, el panel IVA (especificacion §2.2.4): cada trimestre, en orden. En reposo, la cifra
// principal (el trimestre en curso: lo que sale a pagar o a devolver; la barra, la parte del
// trimestre que ya ha pasado; la nota, el plazo y el estado), una fila por cada uno de los tres
// ultimos trimestres y "Anteriores", y al final "Descargar la hoja del trimestre". Cada
// trimestre abre su tarjeta .detail: las lineas de la hoja (casilla e importe), lo que hay que
// mirar antes de que las cifras valgan, el estado y sus ordenes (dejarlo listo para revisar,
// anotar la declaracion presentada y reabrirlo; nunca "presentar": la declaracion la presenta una
// persona en el portal de la Belastingdienst) y "Descargar la hoja". Sustituye a las pantallas
// Btw y Kwartaal de los pasos 15 y 16; sus reglas son las mismas (panel-model.ts).
import { Download } from 'lucide-react';
import { useState } from 'react';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { actionText, ruleText } from '@/i18n/domain';
import { paths, vatQuarterPath } from '@/lib/api';
import type { VatQuarter, VatSummary } from '@/lib/api-types';
import { MINUS, formatDate, formatDateProse, formatMoney, quarterLabel } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { daysBetween } from '@/lib/text';
import { rowTone, statusLabel } from '@/components/status-pill';
import { useLoad } from '../use-load';
import { Orders, apiErrorMessage, ErrorLine, type OrderSpec } from '../orders';
import { useAurora } from '../root';
import { Balance, Detail, GroupView, List, PanelFrame, Row } from './pieces';
import { balanceText, deadlineState, nextStep, plainAmount, quarterRows, type QuarterRow } from './panel-model';

/** Lo que dice el estado de un trimestre en su fila: el plazo si pide atencion; si no, el estado. */
function quarterState(t: Messages, lang: Lang, r: QuarterRow): { text: string; tone: 'paid' | 'blocked' | '' } {
  const deadline = deadlineState(r);
  if (deadline) {
    return { text: statusLabel(lang, t, 'btw', deadline, r.dias_para_limite !== null ? { n: r.dias_para_limite } : {}) ?? deadline, tone: rowTone('btw', deadline) };
  }
  return { text: statusLabel(lang, t, 'btw', r.estado) ?? r.estado, tone: rowTone('btw', r.estado) };
}

/** La parte del trimestre que ya ha pasado (de 0 a 1), para la barra de la cifra principal. */
function elapsed(q: Pick<VatQuarter, 'inicio' | 'fin' | 'terminado'>, today: string): number {
  if (q.terminado) return 1;
  const total = daysBetween(q.inicio, q.fin);
  const gone = daysBetween(q.inicio, today);
  if (total === null || gone === null || total <= 0) return 0;
  return Math.max(0, Math.min(1, (gone + 1) / (total + 1)));
}

/** Bajar la hoja de un trimestre (CSV): fetch con el token, Blob y a[download]. */
function useSheetDownload() {
  const { session } = useSession();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const download = async (quarter: string) => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await session.api.download(vatQuarterPath(quarter, '/hoja.csv'), `btw-${quarter}.csv`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return { download, error, busy };
}

export function VatPanel({ view }: { view: string | null }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const { dispatch } = useAurora();
  const [card, setCard] = useState<string | null>(null);
  const sheet = useSheetDownload();
  const [state] = useLoad(() => session!.api.get<{ btw: VatSummary }>(paths.vat).then((r) => r.btw), [session, version]);
  const v = t.aurora.vat;
  const title = view === 'older' ? v.older : t.areas.vat.label;

  const setView = (next: string | null) => {
    setCard(null);
    dispatch({ type: 'panelView', view: next });
  };
  const onEscape = () => {
    if (card) setCard(null);
    else if (view) setView(null);
    else dispatch({ type: 'closePanel' });
  };

  const quarterRow = (r: QuarterRow) => {
    const s = quarterState(t, lang, r);
    return (
      <Row
        key={r.etiqueta}
        label={quarterLabel(r.etiqueta)}
        note={nextStep(r, t)}
        figure={balanceText(r.saldo_cent, t)}
        state={s.text}
        tone={s.tone}
        current={card === r.etiqueta}
        ariaLabel={fmt(t.common.openRecord, { what: fmt(t.vat.title, { quarter: quarterLabel(r.etiqueta) }) })}
        onOpen={() => setCard(r.etiqueta)}
      />
    );
  };

  let body = null;
  if (state.status === 'ready') {
    const summary = state.data;
    const rows = quarterRows(summary);
    const a = summary.actual;
    const balance = a.cifras['5c'];
    if (view === 'older') {
      body = (
        <GroupView
          items={rows.slice(3)}
          title={v.older.toUpperCase()}
          match={(r) => `${quarterLabel(r.etiqueta)} ${r.etiqueta}`}
          render={quarterRow}
          backLabel={fmt(t.aurora.panel.backTo, { what: t.areas.vat.label })}
          onBack={() => setView(null)}
        />
      );
    } else {
      const s = quarterState(t, lang, rows[0]!);
      body = (
        <>
          <Balance
            label={`${quarterLabel(a.etiqueta)} · ${balance > 0 ? t.vat.toPayShort : balance < 0 ? t.vat.refundShort : v.nothingDue}`}
            figure={formatMoney(Math.abs(balance))}
            share={elapsed(a, summary.hoy)}
            note={[a.limite_presentacion ? fmt(v.due, { date: formatDate(a.limite_presentacion) }) : null, s.text].filter(Boolean).join(' · ')}
          />
          <List title={v.listTitle} count={rows.length}>
            {rows.slice(0, 3).map(quarterRow)}
            {rows.length > 3 && (
              <Row
                label={v.older}
                note={v.olderNote}
                figure={String(rows.length - 3)}
                state={quarterLabel(rows[3]!.etiqueta)}
                onOpen={() => setView('older')}
              />
            )}
          </List>
          <button className='outline' disabled={sheet.busy} onClick={() => void sheet.download(a.etiqueta)}>
            <Download size={15} /> {v.download}
          </button>
          {sheet.error !== null && <ErrorLine error={sheet.error} message={apiErrorMessage(sheet.error, t, lang)} />}
        </>
      );
    }
    if (card) body = [body, <QuarterCard key={card} quarter={card} onClose={() => setCard(null)} />];
  }

  return (
    <PanelFrame title={title} description={t.aurora.panel.descriptions.vat} view={view} onEscape={onEscape}>
      {state.status === 'error' && <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} />}
      {body}
    </PanelFrame>
  );
}

/** La tarjeta de un trimestre: sus cifras, lo que hay que mirar, el estado y sus ordenes. */
function QuarterCard({ quarter, onClose }: { quarter: string; onClose: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const { session } = useSession();
  const { version } = useRefresh();
  const sheet = useSheetDownload();
  const [state] = useLoad(
    () => session!.api.get<{ trimestre: VatQuarter }>(vatQuarterPath(quarter)).then((r) => r.trimestre),
    [session, quarter, version]
  );
  const title = fmt(t.vat.title, { quarter: quarterLabel(quarter) });
  if (state.status !== 'ready') {
    return (
      <Detail title={title} onClose={onClose}>
        {state.status === 'error' && <ErrorLine error={state.error} message={apiErrorMessage(state.error, t, lang)} />}
      </Detail>
    );
  }
  const q = state.data;
  const c = q.cifras;
  const rubric = (code: string) => t.vat.rubrics[code as keyof typeof t.vat.rubrics] ?? code;
  const outside = [...(c.sin_clasificar ?? []), ...(c.fuera ?? [])];
  const outsideIds = new Set(outside.map((r) => r.factura_id));
  const review = q.revisar.filter((r) => r.reglas.length > 0 || !outsideIds.has(r.factura_id));
  const deadline = deadlineState(q);
  return (
    <Detail title={title} onClose={onClose}>
      <p>{fmt(t.vat.span, { from: formatDateProse(q.inicio, t), to: formatDateProse(q.fin, t) })}</p>
      {c.rubricas.map((r) => (
        <p key={r.rubrica}>
          {r.rubrica} · {rubric(r.rubrica)}: {r.omzet_cent !== null && `${formatMoney(r.omzet_cent)} · `}
          {formatMoney(r.btw_cent)}
        </p>
      ))}
      <p>
        5a · {rubric('5a')}: {formatMoney(c['5a'])}
      </p>
      <p>
        5b · {rubric('5b')}: {formatMoney(c['5b'])}
      </p>
      <p>
        5c · {rubric('5c')}: {balanceText(c['5c'], t)}
      </p>
      {!q.configuracion.confirmada && <p>{t.vat.configNotConfirmed}</p>}
      {q.estado === 'listo_revision' && !q.hoja_al_dia && <p>{t.vat.sheetChanged}</p>}
      {review.slice(0, 3).map((r) => (
        <p key={`r${r.factura_id}`}>
          {t.vat.reviewInvoices}: <span data-proper-name=''>{r.numero ?? r.factura_id}</span>
          {r.contraparte && (
            <>
              {' · '}
              <span data-proper-name=''>{r.contraparte}</span>
            </>
          )}
          {r.reglas.length > 0 && ` · ${r.reglas.map((rule) => ruleText(lang, rule)?.title ?? rule).join(', ')}`}
        </p>
      ))}
      {outside.slice(0, 3).map((r) => (
        <p key={`o${r.factura_id}`}>
          {t.vat.outside}: <span data-proper-name=''>{r.numero ?? r.factura_id}</span>
        </p>
      ))}
      {q.diferencias.slice(0, 3).map((d) => (
        <p key={`d${d.factura_id}`}>
          {t.vat.changedAfter}: {t.vat.changeKinds[d.motivo as keyof typeof t.vat.changeKinds] ?? d.motivo}
        </p>
      ))}
      {q.estado === 'presentado' && (
        <p>
          {fmt(t.vat.filedText, {
            date: formatDateProse(q.presentado_en, t),
            name: q.presentado_por ?? '—',
            ref: q.referencia ?? '—',
            amount: formatMoney(q.importe_declarado_cent),
          })}
        </p>
      )}
      {q.estado === 'listo_revision' && <p>{fmt(t.vat.stepReadyDone, { name: q.listo_por ?? '—' })}</p>}
      <span>
        {[statusLabel(lang, t, 'btw', q.estado), deadline ? statusLabel(lang, t, 'btw', deadline, q.dias_para_limite !== null ? { n: q.dias_para_limite } : {}) : null, nextStep(q, t)]
          .filter(Boolean)
          .join(' · ')}
      </span>
      <Orders
        orders={quarterOrders(q, t, lang, can('gestionar_btw'))}
        before={
          <button type='button' className='outline' disabled={sheet.busy} onClick={() => void sheet.download(q.etiqueta)}>
            <Download size={14} /> {t.vat.downloadSheet}
          </button>
        }
      />
      {sheet.error !== null && <ErrorLine error={sheet.error} message={apiErrorMessage(sheet.error, t, lang)} />}
    </Detail>
  );
}

/** Las ordenes de un trimestre, para quien puede (gestionar_btw): dejarlo listo (terminado y
 *  abierto), anotar la declaracion y reabrirlo (listo para revisar). */
function quarterOrders(q: VatQuarter, t: Messages, lang: Lang, allowed: boolean): OrderSpec[] {
  if (!allowed) return [];
  const motivo = { name: 'motivo', label: t.vat.explanation, kind: 'text' as const, required: true };
  if (q.estado === 'listo_revision' && q.rev !== null) {
    return [
      {
        action: 'btw_anotar_presentacion',
        label: actionText(lang, 'btw_anotar_presentacion')?.label ?? t.vat.stepFile,
        primary: true,
        intro: <p>{t.vat.stepFileText}</p>,
        fields: [
          { name: 'referencia', label: t.vat.reference, kind: 'text', required: true },
          { name: 'importe_declarado', label: t.vat.declared, kind: 'text', required: true, initial: plainAmount(q.cifras['5c']), help: t.vat.declaredHelp },
          { name: 'fecha_presentacion', label: t.vat.filedOn, kind: 'date', help: t.vat.filedOnHelp },
          motivo,
        ],
        data: (v) => ({
          trimestre: q.etiqueta,
          rev: q.rev,
          hoja_sha256: q.hoja_marcada_sha256,
          referencia: v.referencia,
          importe_declarado: (v.importe_declarado ?? '').replace(MINUS, '-'),
          fecha_presentacion: v.fecha_presentacion || undefined,
          motivo: v.motivo,
        }),
      },
      {
        action: 'btw_reabrir',
        label: actionText(lang, 'btw_reabrir')?.label ?? t.vat.stepReady,
        intro: <p>{t.vat.reopenIntro}</p>,
        fields: [motivo],
        data: (v) => ({ trimestre: q.etiqueta, rev: q.rev, motivo: v.motivo }),
      },
    ];
  }
  if (q.estado !== 'presentado' && q.terminado) {
    return [
      {
        action: 'btw_lista_para_revision',
        label: actionText(lang, 'btw_lista_para_revision')?.label ?? t.vat.stepReady,
        primary: true,
        intro: <p>{t.vat.readyIntro}</p>,
        fields: [motivo],
        data: (v) => ({ trimestre: q.etiqueta, hoja_sha256: q.hoja_sha256, motivo: v.motivo }),
      },
    ];
  }
  return [];
}
