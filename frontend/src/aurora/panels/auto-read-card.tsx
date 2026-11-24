// La tarjeta de la lectura automatica (paso 18, especificacion §5.1 y §6.1; solo Docker): en
// Instellingen › Systeem › Automatisch lezen. Si esta encendida, quien la fijo y cuando, sus
// cuatro valores, lo gastado hoy y este mes y lo que queda hoy; si esta parada, por que, con
// "Weer aanzetten" para una pausa; la lista "Wacht op automatisch lezen" (las facturas que leera,
// las mas antiguas primero) con casillas y "Niet vanzelf lezen"; y, con admin, el formulario.
//
// Lo unico que cambia sin una persona es gastar dinero de la API en leer, dentro de la
// autorizacion que una persona con admin firma aqui (fijar_lectura_automatica, con su motivo).
// Ninguna orden de aqui aprueba, paga ni crea una factura: despues de leer, lo de siempre.
import { ScanLine } from 'lucide-react';
import { useState } from 'react';
import { StatusPill } from '@/components/status-pill';
import { fmt, useT, type Messages } from '@/i18n';
import { actionText } from '@/i18n/domain';
import type { AutoReadingStatus, Mailbox, QueuedInvoice } from '@/lib/api-types';
import { formatDateTime, formatUsdMicro } from '@/lib/format';
import { useCan } from '@/lib/session';
import { Orders, type OrderSpec, type OrderValues } from '../orders';
import { whenOf } from '../processing/process-texts';
import { autoReadState, autoReadStateText, checkForm, formValues, knownInstant, resumable, stopText, type AutoReadForm } from './mailbox-model';
import { Detail } from './pieces';

/** Lo escrito en el formulario, como lo lee checkForm. */
function asForm(v: OrderValues): AutoReadForm {
  return { activa: v.activa ?? '1', capDay: v.capDay ?? '', capMonth: v.capMonth ?? '', maxDocs: v.maxDocs ?? '', maxPerDoc: v.maxPerDoc ?? '' };
}

/** El formulario de la autorizacion (con admin): encender o apagar, los cuatro topes y el motivo. */
function settingsOrder(a: AutoReadingStatus, t: Messages, label: string): OrderSpec {
  const r = t.aurora.autoRead;
  const initial = formValues(a);
  const number = (name: keyof AutoReadForm, text: string, help?: string) => ({ name, label: text, kind: 'text' as const, required: true, initial: initial[name], help });
  return {
    action: 'fijar_lectura_automatica',
    label,
    submit: r.save,
    primary: true,
    intro: r.help,
    fields: [
      {
        name: 'activa',
        label: t.aurora.settings.systemRows.autoRead,
        kind: 'select',
        initial: initial.activa,
        hideOptional: true,
        options: [
          { value: '1', label: t.status.autoRead.encendida },
          { value: '0', label: t.status.autoRead.apagada },
        ],
      },
      number('capDay', r.capDay, r.amountHelp),
      number('capMonth', r.capMonth),
      number('maxDocs', r.maxDocs),
      number('maxPerDoc', r.maxPerDoc),
      { name: 'motivo', label: t.action.reason, kind: 'text', required: true },
    ],
    validate: (v) => {
      const checked = checkForm(asForm(v), t);
      return 'problem' in checked ? checked.problem : null;
    },
    data: (v) => {
      const checked = checkForm(asForm(v), t);
      // validate ya lo miro; el servidor lo vuelve a mirar (lectura_automatica.validar).
      return 'values' in checked ? { ...checked.values, motivo: (v.motivo ?? '').trim() } : {};
    },
  };
}

/** "Wacht op automatisch lezen": las que leera, con casillas para apartar las que no son facturas
 *  (de una vez, hasta 200: las que trae la cola). */
function Queue({ queue, total, canAct }: { queue: readonly QueuedInvoice[]; total: number; canAct: boolean }) {
  const { t, lang } = useT();
  const r = t.aurora.autoRead;
  const [chosen, setChosen] = useState<ReadonlySet<number>>(new Set());
  const ids = queue.map((q) => q.documento_id);
  const picked = ids.filter((id) => chosen.has(id));
  const toggle = (id: number) =>
    setChosen((old) => {
      const next = new Set(old);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const exclude: OrderSpec = {
    action: 'excluir_de_lectura_automatica',
    label: actionText(lang, 'excluir_de_lectura_automatica')?.label ?? 'excluir_de_lectura_automatica',
    intro: r.excludeIntro,
    blocked: picked.length === 0 ? r.noneSelected : undefined,
    fields: [{ name: 'motivo', label: t.action.reason, kind: 'text' }],
    data: (v) => ({ documento_ids: picked, motivo: (v.motivo ?? '').trim() || undefined }),
  };
  return (
    <>
      <div className='list-title'>
        {r.waitingList.toUpperCase()} <span>{total}</span>
      </div>
      {queue.length === 0 ? (
        <p>{r.waitingNone}</p>
      ) : (
        <>
          {canAct && (
            <p>
              <button type='button' className='mail-more' onClick={() => setChosen(new Set(ids))}>
                {r.selectAll}
              </button>
              {' · '}
              <button type='button' className='mail-more' onClick={() => setChosen(new Set())}>
                {r.selectNone}
              </button>
              {' · '}
              {picked.length === 1 ? r.selectedOne : fmt(r.selected, { n: picked.length })}
            </p>
          )}
          <ul className='mail-list queue-list'>
            {queue.map((q) => {
              const known = knownInstant(q.recibido_en);
              const text = (
                <>
                  <span data-proper-name=''>{q.nombre_original || '—'}</span>
                  {known && <small>{whenOf(known, t)}</small>}
                </>
              );
              return (
                <li key={q.documento_id}>
                  {canAct ? (
                    <label>
                      <input type='checkbox' checked={chosen.has(q.documento_id)} onChange={() => toggle(q.documento_id)} />
                      <span>{text}</span>
                    </label>
                  ) : (
                    <p>{text}</p>
                  )}
                </li>
              );
            })}
          </ul>
          {total > queue.length && <p>{total - queue.length === 1 ? t.why.moreOne : fmt(t.why.more, { n: total - queue.length })}</p>}
          {canAct && <Orders orders={[exclude]} onDone={() => setChosen(new Set())} />}
        </>
      )}
    </>
  );
}

/** "Ingesteld door Ana Demo op 24-11-2026 10:41": el nombre, como nombre propio. */
function SetBy({ a }: { a: Pick<Mailbox['lectura_automatica'], 'fijada_por' | 'fijada_en'> }) {
  const { t } = useT();
  const [before, after = ''] = fmt(t.aurora.autoRead.setBy, { date: formatDateTime(a.fijada_en) }).split('{name}');
  return (
    <p>
      {before}
      <span data-proper-name=''>{a.fijada_por?.nombre ?? '—'}</span>
      {after}
    </p>
  );
}

export function AutoReadCard({ mailbox, onClose }: { mailbox: Mailbox; onClose: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const a = mailbox.lectura_automatica;
  const r = t.aurora.autoRead;
  const state = autoReadState(a);
  const stop = stopText(a, t);
  const set = a.autorizacion_id !== null;
  const label = actionText(lang, 'fijar_lectura_automatica')?.label ?? r.save;
  const resume: OrderSpec = { action: 'reanudar_lectura_automatica', label: r.resume, primary: true, data: () => ({}) };
  return (
    <Detail title={t.aurora.settings.systemRows.autoRead} icon={ScanLine} onClose={onClose}>
      <p>
        <StatusPill group='lectura_automatica' state={state} label={autoReadStateText(state, t)} />
      </p>
      {stop && <p>{stop}</p>}
      {can('importar_datos') && resumable(a) && <Orders orders={[resume]} />}
      {!set ? (
        <p>{r.neverSet}</p>
      ) : (
        <>
          {!a.activa && <p>{r.offNote}</p>}
          <SetBy a={a} />
          <p>
            {r.capDay}: {formatUsdMicro(a.tope_dia_usd_micro)} · {r.capMonth}: {formatUsdMicro(a.tope_mes_usd_micro)}
          </p>
          <p>
            {r.maxDocs}: {a.max_documentos ?? '—'} · {r.maxPerDoc}: {formatUsdMicro(a.max_por_documento_usd_micro)}
          </p>
          <p>
            {fmt(r.spent, {
              spent: formatUsdMicro(a.gastado_hoy_usd_micro),
              cap: formatUsdMicro(a.tope_dia_usd_micro),
              spentMonth: formatUsdMicro(a.gastado_mes_usd_micro),
              capMonth: formatUsdMicro(a.tope_mes_usd_micro),
            })}
          </p>
          {a.activa && <p>{fmt(r.left, { left: formatUsdMicro(a.queda_hoy_usd_micro) })}</p>}
        </>
      )}
      {can('admin') ? <Orders orders={[settingsOrder(a, t, label)]} /> : <span>{r.onlyAdmin}</span>}
      <Queue queue={a.cola ?? []} total={a.elegibles} canAct={can('importar_datos')} />
    </Detail>
  );
}
