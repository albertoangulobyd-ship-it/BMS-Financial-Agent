// La tarjeta del buzon de facturas (paso 18, especificacion §6.1; solo Docker): en Instellingen ›
// Systeem › Facturenmailbox. Como va el buzon (su estado, la ultima consulta y la ultima buena,
// el error con lo que hay que hacer, que solo se puede leer ese buzon, el certificado), lo de hoy,
// el latido del trabajo automatico y el disco, los ultimos correos y "Wacht op jou": los correos
// que el programa no pudo leer (con "Afgehandeld") y las facturas que la lectura automatica aparto
// (con el original, "Lezen via Verwerken" si se puede y "Niet vanzelf lezen").
//
// El remitente, el asunto y los nombres de los adjuntos los pone quien manda el correo: van como
// texto (React, nunca HTML), con data-proper-name y SIEMPRE con la etiqueta "niet gecontroleerd".
// No identifican a ningun proveedor ni deciden nada. La app no trae, mueve ni marca nada en el
// buzon (es de solo lectura): "Afgehandeld" solo apunta aqui que una persona ya lo miro.
import { Mail } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { WithScriptNames } from '@/components/script-names';
import { StatusPill } from '@/components/status-pill';
import { fmt, useT, type Messages } from '@/i18n';
import { actionText } from '@/i18n/domain';
import { paths } from '@/lib/api';
import type { MailMessage, Mailbox, WaitingInvoice } from '@/lib/api-types';
import { useCan } from '@/lib/session';
import { entryIndex } from '../estado';
import { ErrorLine, Orders, apiErrorMessage, type OrderSpec } from '../orders';
import { whenOf } from '../processing/process-texts';
import { useAurora } from '../root';
import { useOriginalDownload } from './invoice-card';
import {
  adviceFor,
  attachmentText,
  certState,
  certText,
  exclusionText,
  formatGigabytes,
  knownInstant,
  mailboxErrorText,
  mailboxStateText,
  readableByHand,
} from './mailbox-model';
import { Detail } from './pieces';

/** Cuantas filas de cada lista se ven antes de "Alle N tonen". */
const FIRST_ROWS = 5;

/** "vandaag om 10:41", "27-10-2026 om 10:41" o "nog nooit". */
function when(value: string | null, t: Messages): string {
  return value ? whenOf(value, t) : t.aurora.mailbox.never;
}

/** "Ontvangen vandaag om 10:41" (la hora del servidor de Microsoft), o nada si no se sabe. */
function received(value: string | null, t: Messages): string | null {
  const known = knownInstant(value);
  return known ? fmt(t.aurora.mailbox.received, { when: whenOf(known, t) }) : null;
}

/** La etiqueta de lo que pone quien manda el correo. */
function Unverified() {
  const { t } = useT();
  return (
    <small className='mail-tag' title={t.aurora.mailbox.unverifiedHelp}>
      {t.aurora.mailbox.unverified}
    </small>
  );
}

/** Una lista con sus primeras filas y "Alle N tonen" / "Minder tonen". */
function Folded<T>({ items, render }: { items: readonly T[]; render: (item: T) => ReactNode }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const shown = open ? items : items.slice(0, FIRST_ROWS);
  return (
    <>
      <ul className='mail-list'>{shown.map(render)}</ul>
      {items.length > FIRST_ROWS && (
        <p>
          <button type='button' className='mail-more' aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? t.aurora.mailbox.showLess : fmt(t.aurora.mailbox.showAll, { n: items.length })}
          </button>
        </p>
      )}
    </>
  );
}

/** Un correo: remitente y asunto (sin comprobar), cuando llego y lo que fue de cada adjunto. */
function MailItem({ message: m, advice, orders }: { message: MailMessage; advice?: boolean; orders?: readonly OrderSpec[] }) {
  const { t } = useT();
  const b = t.aurora.mailbox;
  const tip = advice ? adviceFor(m, t) : null;
  return (
    <li>
      <p>
        {b.from}: <strong data-proper-name=''>{m.remitente_doc || '—'}</strong> <Unverified />
      </p>
      <p>
        {b.subject}: {m.asunto_doc ? <span data-proper-name=''>{m.asunto_doc}</span> : b.noSubject} <Unverified />
      </p>
      {received(m.recibido_en, t) && <p>{received(m.recibido_en, t)}</p>}
      {m.adjuntos.map((a, i) => (
        <p key={i}>
          <span data-proper-name=''>{a.nombre_doc || '—'}</span>: {attachmentText(a.resultado, t)}
        </p>
      ))}
      {tip && <p>{tip}</p>}
      {orders && orders.length > 0 && <Orders orders={orders} />}
    </li>
  );
}

/** Una factura que la lectura automatica aparto: por que, su original, leerla a mano si se puede
 *  y apartarla del todo. */
function WaitingInvoiceItem({ doc, canRead }: { doc: WaitingInvoice; canRead: boolean }) {
  const { t, lang } = useT();
  const { dispatch } = useAurora();
  const original = useOriginalDownload();
  const b = t.aurora.mailbox;
  const setAside: OrderSpec = {
    action: 'excluir_de_lectura_automatica',
    label: actionText(lang, 'excluir_de_lectura_automatica')?.label ?? 'excluir_de_lectura_automatica',
    intro: b.setAsideIntro,
    fields: [{ name: 'motivo', label: t.action.reason, kind: 'text' }],
    data: (v) => ({ documento_ids: [doc.documento_id], motivo: (v.motivo ?? '').trim() || undefined }),
  };
  return (
    <li>
      <p>
        <strong data-proper-name=''>{doc.nombre_original || '—'}</strong>
      </p>
      <p>
        {exclusionText(doc.motivo_codigo, t)}
        {received(doc.recibido_en, t) && <> · {received(doc.recibido_en, t)}</>}
      </p>
      {original.error !== null && <ErrorLine error={original.error} message={apiErrorMessage(original.error, t, lang)} />}
      <Orders
        orders={canRead ? [setAside] : []}
        before={
          <>
            <button
              type='button'
              className='outline'
              disabled={original.busy}
              onClick={() => void original.download(paths.documentOriginal(doc.documento_id), `documento-${doc.documento_id}.pdf`)}
            >
              {t.aurora.card.downloadOriginal}
            </button>
            {canRead && readableByHand(doc.motivo_codigo) && (
              <button type='button' className='outline' onClick={() => dispatch({ type: 'enterProcess', index: entryIndex('process') })}>
                {b.readInProcess}
              </button>
            )}
          </>
        }
      />
    </li>
  );
}

export function MailboxCard({ mailbox: m, onClose }: { mailbox: Mailbox; onClose: () => void }) {
  const { t } = useT();
  const can = useCan();
  const canAct = can('importar_datos');
  const b = t.aurora.mailbox;
  const configured = m.estado !== 'sin_configurar';
  const error = configured ? mailboxErrorText(m.error_codigo, t) : null;
  const cert = certState(m.credencial.dias);
  const certLine = certText(m.credencial, t);
  const waiting = m.esperan_persona;
  const handled = (message: MailMessage): OrderSpec => ({
    action: 'marcar_correo_atendido',
    label: b.handled,
    intro: b.handledIntro,
    fields: [{ name: 'nota', label: t.action.note, kind: 'text' }],
    data: (v) => ({ mensaje_id: message.mensaje_id, nota: (v.nota ?? '').trim() || undefined }),
  });
  return (
    <Detail title={t.aurora.settings.systemRows.mailbox} icon={Mail} onClose={onClose}>
      <p>
        <StatusPill group='correo' state={m.estado} label={mailboxStateText(m.estado, t)} />
      </p>
      {!configured ? (
        <p>
          <WithScriptNames text={b.notSetUp} />
        </p>
      ) : (
        <>
          {error && (
            <p>
              <WithScriptNames text={error} />
            </p>
          )}
          <p>{fmt(b.lastCheck, { when: when(m.ultima_consulta, t) })}</p>
          {m.ultima_buena !== m.ultima_consulta && <p>{fmt(b.lastGood, { when: when(m.ultima_buena, t) })}</p>}
          <p>{fmt(b.today, { messages: m.hoy.mensajes, pdfs: m.hoy.pdf_nuevos })}</p>
          {m.retenido_hasta && <p>{fmt(b.held, { when: whenOf(m.retenido_hasta, t) })}</p>}
          {m.aviso_volumen && <p>{b.volume}</p>}
          {m.alcance.bien === true && <p>{fmt(b.scopeOk, { when: when(m.alcance.comprobado_en, t) })}</p>}
          {m.alcance.bien === false && m.error_codigo !== 'alcance' && <p>{b.errors.alcance}</p>}
          {m.alcance.bien === null && <p>{b.scopeUnchecked}</p>}
          {cert && certLine && (
            <>
              {cert !== 'vigente' && (
                <p>
                  <StatusPill group='certificado' state={cert} />
                </p>
              )}
              <p>
                {certLine}
                {cert !== 'vigente' && (
                  <>
                    {' '}
                    <WithScriptNames text={b.certRenew} />
                  </>
                )}
              </p>
            </>
          )}
        </>
      )}
      <p>
        {m.ciclo.visto_en === null ? (
          b.cycleNever
        ) : m.ciclo.pausado ? (
          <WithScriptNames text={fmt(b.cyclePaused, { when: when(m.ciclo.pausado_desde, t) })} />
        ) : (
          fmt(b.cycle, { when: whenOf(m.ciclo.visto_en, t) })
        )}
        {m.ciclo.disco_libre_bytes !== null && <> · {fmt(b.diskFree, { free: formatGigabytes(m.ciclo.disco_libre_bytes) })}</>}
      </p>
      {m.ciclo.disco_bajo && m.error_codigo !== 'disco' && <p>{b.errors.disco}</p>}

      <div className='list-title'>
        {b.waiting.toUpperCase()} <span>{waiting.correos_total + waiting.documentos_total}</span>
      </div>
      {waiting.correos_total + waiting.documentos_total === 0 && <p>{b.waitingNone}</p>}
      {waiting.correos_total > 0 && (
        <>
          <span>
            {b.waitingMail} ({waiting.correos_total})
          </span>
          <p>{b.unverifiedHelp}</p>
          <Folded items={waiting.correos} render={(message) => <MailItem key={message.mensaje_id} message={message} advice orders={canAct ? [handled(message)] : []} />} />
        </>
      )}
      {waiting.documentos_total > 0 && (
        <>
          <span>
            {b.waitingDocs} ({waiting.documentos_total})
          </span>
          <Folded items={waiting.documentos} render={(doc) => <WaitingInvoiceItem key={doc.documento_id} doc={doc} canRead={canAct} />} />
        </>
      )}

      <div className='list-title'>
        {b.recent.toUpperCase()} <span>{m.recientes.length}</span>
      </div>
      {m.recientes.length === 0 ? <p>{b.recentNone}</p> : <Folded items={m.recientes} render={(message) => <MailItem key={message.mensaje_id} message={message} />} />}
    </Detail>
  );
}
