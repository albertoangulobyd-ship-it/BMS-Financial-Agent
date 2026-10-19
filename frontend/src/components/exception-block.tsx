// Una excepcion abierta: en que estado esta, quien la lleva, a quien se espera, y lo que
// la persona puede hacer con ella (asignarla, dejarla esperando a alguien de fuera,
// resolverla). La usan la ficha de una factura y la pantalla de Uitzonderingen. Cada
// orden lleva la rev de la excepcion que se vio (concurrencia optimista).
import { ActionButton } from '@/components/action-dialog';
import { StatusText } from '@/components/status-text';
import { fmt, useT } from '@/i18n';
import { stateLabel } from '@/i18n/domain';
import type { ExceptionInfo, Person } from '@/lib/api-types';
import { formatDateProse, todayIso } from '@/lib/format';
import { useCan, useSession } from '@/lib/session';
import { daysBetween } from '@/lib/text';
import { EXCEPTION_TONE } from '@/components/tones';

const WAITING_ON = ['proveedor', 'cliente', 'contable', 'exact', 'trnsprnt', 'banco', 'otro'] as const;
const RESOLUTIONS = ['corregido', 'aceptado', 'anulado', 'no_procede', 'condicion_desaparecida'] as const;

export function ExceptionStatus({ exception }: { exception: ExceptionInfo }) {
  const { t, lang } = useT();
  const age = daysBetween(exception.creada_en, todayIso());
  const waiting = exception.estado === 'esperando_externo' && exception.esperando_a;
  const status = waiting
    ? fmt(t.exceptions.waitingOn, { who: stateLabel(lang, 'esperando_a', exception.esperando_a) ?? exception.esperando_a ?? '' })
    : (stateLabel(lang, 'excepcion', exception.estado) ?? exception.estado);
  const ageText =
    age === null ? null : age <= 0 ? t.exceptions.openedToday : fmt(age === 1 ? t.exceptions.ageOne : t.exceptions.age, { n: age });
  return (
    <div className='flex flex-col gap-0.5 text-[13px]'>
      <StatusText tone={EXCEPTION_TONE[exception.estado] ?? 'neutral'}>{status}</StatusText>
      <span className='text-muted-foreground'>
        {exception.responsable ? fmt(t.exceptions.owner, { name: exception.responsable }) : t.exceptions.noOwner}
        {ageText && ` · ${ageText}`}
      </span>
      {exception.fecha_seguimiento && (
        <span className='text-muted-foreground'>
          {fmt(t.exceptions.followUp, { date: formatDateProse(exception.fecha_seguimiento, t) })}
        </span>
      )}
    </div>
  );
}

export function ExceptionActions({
  exception,
  people,
  onDone,
}: {
  exception: ExceptionInfo;
  people: Person[];
  onDone: () => void;
}) {
  const { t, lang } = useT();
  const can = useCan();
  const { session } = useSession();
  if (!can('resolver_aviso') || exception.estado === 'resuelta') return null;
  const me = session?.me.id;
  const base = { excepcion_id: exception.id, rev: exception.rev };
  const others = people.filter((p) => p.id !== exception.responsable_id);
  return (
    <div className='flex flex-wrap gap-2'>
      {me !== undefined && exception.responsable_id !== me && (
        <ActionButton
          action='asignar_excepcion'
          label={t.exceptions.takeIt}
          title={t.exceptions.takeIt}
          intro={t.exceptions.takeItIntro}
          data={() => ({ ...base, responsable_id: me })}
          onDone={onDone}
        />
      )}
      {others.length > 0 && (
        <ActionButton
          action='asignar_excepcion'
          label={t.exceptions.assign}
          fields={[
            {
              name: 'responsable_id',
              label: t.exceptions.assignTo,
              kind: 'select',
              required: true,
              initial: String(others[0]!.id),
              options: others.map((p) => ({ value: String(p.id), label: p.nombre })),
            },
          ]}
          data={(v) => ({ ...base, responsable_id: Number(v.responsable_id) })}
          onDone={onDone}
        />
      )}
      <ActionButton
        action='esperar_externo'
        label={t.exceptions.wait}
        fields={[
          {
            name: 'esperando_a',
            label: t.exceptions.waitFor,
            kind: 'select',
            required: true,
            initial: 'proveedor',
            options: WAITING_ON.map((w) => ({ value: w, label: stateLabel(lang, 'esperando_a', w) ?? w })),
          },
          { name: 'fecha_seguimiento', label: t.exceptions.followUpDate, kind: 'date' },
          { name: 'motivo', label: t.action.note, kind: 'textarea' },
        ]}
        data={(v) => ({
          ...base,
          esperando_a: v.esperando_a,
          fecha_seguimiento: v.fecha_seguimiento || null,
          motivo: v.motivo || undefined,
        })}
        onDone={onDone}
      />
      <ActionButton
        action='resolver_excepcion'
        label={t.exceptions.resolve}
        variant='default'
        intro={t.exceptions.resolveIntro}
        fields={[
          {
            name: 'resolucion',
            label: t.exceptions.resolution,
            kind: 'select',
            required: true,
            initial: 'corregido',
            options: RESOLUTIONS.map((r) => ({ value: r, label: stateLabel(lang, 'resolucion', r) ?? r })),
          },
          { name: 'motivo', label: t.exceptions.whatWasDone, kind: 'textarea', required: true },
        ]}
        data={(v) => ({ ...base, resolucion: v.resolucion, motivo: v.motivo })}
        onDone={onDone}
      />
    </div>
  );
}
