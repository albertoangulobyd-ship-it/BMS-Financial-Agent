// "Wat aandacht nodig heeft" / "What needs your attention": cada hallazgo pendiente de la
// factura con su nombre, lo que dicen sus datos (escrito desde sus valores), que hacer y
// los botones que la persona puede usar: aceptarlo con un motivo (anular_hallazgo, si la
// regla lo admite), dar la segunda firma a un colega (firmar_anulacion), cerrarlo cuando
// el problema ya no se ve (cerrar_hallazgo) y, si apunta a un campo, verificarlo o
// corregirlo ahi mismo. El codigo de la regla va pequeno y gris: es una referencia.
import { CircleCheck } from 'lucide-react';
import { ActionButton } from '@/components/action-dialog';
import { StatusPill } from '@/components/status-pill';
import { fmt, useT } from '@/i18n';
import { fieldLabel, findingDetail, ruleText } from '@/i18n/domain';
import { MIN_ACCEPT_REASON, permissionFor } from '@/lib/actions';
import type { FieldInfo, Finding, InvoiceDetail, Person } from '@/lib/api-types';
import { useCan, useSession } from '@/lib/session';
import { editableInApp } from '@/lib/field-format';
import { FieldEditButton } from './invoice-fields';
import { findField, revOf } from './invoice-util';

const ORDER: Record<string, number> = { bloqueo: 0, retencion: 1, aviso: 2 };
const STATE_ORDER: Record<string, number> = { abierto: 0, desaparecido: 1, aceptado: 2 };

export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) =>
      (STATE_ORDER[a.estado] ?? 3) - (STATE_ORDER[b.estado] ?? 3) ||
      (ORDER[a.severidad] ?? 3) - (ORDER[b.severidad] ?? 3) ||
      a.id - b.id
  );
}

export function FindingsList({
  invoice,
  people,
  onDone,
}: {
  invoice: InvoiceDetail;
  people: Person[];
  onDone: () => void;
}) {
  const { t } = useT();
  const findings = sortFindings(invoice.hallazgos);
  if (findings.length === 0) {
    return (
      <div className='flex items-center gap-3 rounded-md border border-border bg-card px-4 py-4'>
        <CircleCheck className='h-5 w-5 shrink-0 text-ok-foreground' aria-hidden='true' />
        <div>
          <p className='font-medium'>{t.empty.nothingNeedsAttention}</p>
          <p className='text-[13px] text-muted-foreground'>{t.invoice.noFindings}</p>
        </div>
      </div>
    );
  }
  return (
    <ol className='flex flex-col gap-3'>
      {findings.map((f) => (
        <li key={f.id}>
          <FindingCard finding={f} invoice={invoice} people={people} onDone={onDone} />
        </li>
      ))}
    </ol>
  );
}

function FindingCard({
  finding: h,
  invoice,
  people,
  onDone,
}: {
  finding: Finding;
  invoice: InvoiceDetail;
  people: Person[];
  onDone: () => void;
}) {
  const { t, lang } = useT();
  const can = useCan();
  const { session } = useSession();
  const rule = ruleText(lang, h.regla);
  const detail = findingDetail(lang, h.regla, h.resultado, h.valores);
  const open = h.estado === 'abierto';
  const accepted = h.estado === 'aceptado';
  const gone = h.estado === 'desaparecido';
  const canAccept = (open || accepted) && h.anulable && can('anular_aviso');
  const colleagues = people.filter((p) => p.id !== session?.me.id);

  // Los campos a los que apunta, cuando el problema es la lectura de ese campo (leido con
  // duda o que falta): ahi verificarlo o corregirlo es lo que hay que hacer.
  const targets: FieldInfo[] = [];
  const aboutReading = h.calidad === 'dudoso' || h.calidad === 'faltante';
  for (const o of aboutReading && open ? h.objetivos : []) {
    if (!o.campo) continue;
    const field = findField(invoice, o.tabla, o.fila_id, o.campo);
    if (field && editableInApp(field) && !targets.includes(field)) targets.push(field);
  }

  const showTargets = targets.length > 0 && can('editar_extraccion');
  const showAccept = canAccept && open;
  const showSign = showAccept && h.segunda_firma && colleagues.length > 0;
  const showClose = gone && can('resolver_aviso');

  return (
    <article
      aria-labelledby={`finding-${h.id}`}
      className='rounded-md border border-border bg-card px-4 py-3.5'
    >
      <header className='flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1'>
        <h3 id={`finding-${h.id}`} className='text-[14.5px] font-semibold'>
          {rule?.title ?? h.regla}
        </h3>
        <span className='flex items-center gap-2 text-xs'>
          <StatusPill group='severidad' state={h.severidad} />
          {!open && <StatusPill group='hallazgo' state={h.estado} />}
          <span className='font-mono text-[11px] text-muted-foreground' title={t.invoice.ruleCodeHelp}>
            {h.regla}
          </span>
        </span>
      </header>
      {detail && <p className='mt-1.5 text-[13.5px] leading-relaxed'>{detail}</p>}
      {rule && (
        <p className='mt-1.5 text-[13px] leading-relaxed text-[#45423c]'>
          <span className='font-medium text-foreground'>{t.invoice.whatToDo} </span>
          {gone ? t.invoice.goneWhatToDo : rule.whatToDo}
        </p>
      )}
      {(showTargets || showAccept || showClose) && (
        <div className='mt-3 flex flex-wrap gap-2'>
          {showTargets && targets.slice(0, 2).map((field) => (
            <FieldTargetButtons key={`${field.tabla}:${field.fila_id}:${field.campo}`} field={field} invoice={invoice} onDone={onDone} />
          ))}
          {showAccept && (
            <ActionButton
              action='anular_hallazgo'
              label={t.invoice.accept}
              intro={
                <div className='flex flex-col gap-2'>
                  <p>{t.invoice.acceptIntro}</p>
                  {h.segunda_firma && <p className='font-medium'>{t.invoice.secondSignatureNeeded}</p>}
                </div>
              }
              fields={[
                {
                  name: 'motivo',
                  label: t.action.reason,
                  kind: 'textarea',
                  required: true,
                  minLength: MIN_ACCEPT_REASON,
                  help: fmt(t.invoice.acceptReasonHelp, { n: MIN_ACCEPT_REASON }),
                },
                { name: 'vigente_hasta', label: t.invoice.validUntil, kind: 'date', help: t.invoice.validUntilHelp },
              ]}
              data={(v) => ({ hallazgo_id: h.id, huella: h.huella, motivo: v.motivo, vigente_hasta: v.vigente_hasta || null })}
              onDone={onDone}
            />
          )}
          {showSign && (
            <ActionButton
              action='firmar_anulacion'
              variant='ghost'
              label={t.invoice.giveSecondSignature}
              intro={t.invoice.secondSignatureIntro}
              fields={[
                {
                  name: 'solicitante_id',
                  label: t.invoice.signFor,
                  kind: 'select',
                  required: true,
                  initial: String(colleagues[0]!.id),
                  options: colleagues.map((p) => ({ value: String(p.id), label: p.nombre })),
                },
                { name: 'motivo', label: t.action.reason, kind: 'textarea', required: true },
                { name: 'vigente_hasta', label: t.invoice.validUntil, kind: 'date' },
              ]}
              data={(v) => ({
                hallazgo_id: h.id,
                huella: h.huella,
                solicitante_id: Number(v.solicitante_id),
                motivo: v.motivo,
                vigente_hasta: v.vigente_hasta || null,
              })}
              onDone={onDone}
            />
          )}
          {showClose && (
            <ActionButton
              action='cerrar_hallazgo'
              label={t.invoice.close}
              variant='default'
              intro={t.invoice.closeIntro}
              fields={[{ name: 'motivo', label: t.action.reason, kind: 'textarea', required: true }]}
              data={(v) => ({ hallazgo_id: h.id, huella: h.huella, motivo: v.motivo })}
              onDone={onDone}
            />
          )}
        </div>
      )}
    </article>
  );
}

function FieldTargetButtons({ field, invoice, onDone }: { field: FieldInfo; invoice: InvoiceDetail; onDone: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const label = fieldLabel(lang, field.tabla, field.campo) ?? field.campo;
  const rev = revOf(invoice, field);
  const canVerify = field.valor !== null && !field.verificado && can(permissionFor('verificar_campo'));
  return (
    <>
      {canVerify && (
        <ActionButton
          action='verificar_campo'
          label={fmt(t.fields.verifyThis, { field: label })}
          intro={fmt(t.fields.verifyIntro, { field: label })}
          data={() => ({ tabla: field.tabla, fila_id: field.fila_id, campo: field.campo, rev })}
          onDone={onDone}
        />
      )}
      <FieldEditButton field={field} rev={rev} onDone={onDone} labelPrefix />
    </>
  );
}
