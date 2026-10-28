// Una excepcion abierta en una tarjeta (paso 15; desde el paso 17, la tarjeta de su fila en
// "Excepciones" del panel Inicio y la de su fila en la hoja de una factura): en que estado esta,
// quien la lleva y a quien se espera (lineas p), y sus ordenes: llevarla yo, asignarla, esperar
// a alguien de fuera y resolverla (especificacion §2.3.1). Cada orden lleva la rev de la
// excepcion que se vio.
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { stateLabel } from '@/i18n/domain';
import type { ExceptionInfo, Person } from '@/lib/api-types';
import { formatDateProse, todayIso } from '@/lib/format';
import { daysBetween } from '@/lib/text';
import type { OrderSpec } from '../orders';

const WAITING_ON = ['proveedor', 'cliente', 'contable', 'exact', 'trnsprnt', 'banco', 'otro'] as const;
const RESOLUTIONS = ['corregido', 'aceptado', 'anulado', 'no_procede', 'condicion_desaparecida'] as const;

/** El estado de una excepcion en una frase: "Esperando al proveedor" o "Abierta". */
export function exceptionState(e: Pick<ExceptionInfo, 'estado' | 'esperando_a'>, t: Messages, lang: Lang): string {
  if (e.estado === 'esperando_externo' && e.esperando_a) return fmt(t.exceptions.waitingOn, { who: stateLabel(lang, 'esperando_a', e.esperando_a) ?? e.esperando_a });
  return stateLabel(lang, 'excepcion', e.estado) ?? e.estado;
}

/** Quien la lleva, desde cuando y cuando se vuelve a mirar (lineas p de la tarjeta). */
export function ExceptionLines({ exception: e }: { exception: ExceptionInfo }) {
  const { t, lang } = useT();
  const age = daysBetween(e.creada_en, todayIso());
  const ageText = age === null ? null : age <= 0 ? t.exceptions.openedToday : fmt(age === 1 ? t.exceptions.ageOne : t.exceptions.age, { n: age });
  return (
    <>
      <p>
        {e.responsable ? (
          <>
            {fmt(t.exceptions.owner, { name: '\u0000' }).split('\u0000')[0]}
            <span data-proper-name=''>{e.responsable}</span>
            {fmt(t.exceptions.owner, { name: '\u0000' }).split('\u0000')[1]}
          </>
        ) : (
          t.exceptions.noOwner
        )}
        {ageText && ` · ${ageText}`}
      </p>
      {e.fecha_seguimiento && <p>{fmt(t.exceptions.followUp, { date: formatDateProse(e.fecha_seguimiento, t) })}</p>}
      <span>{exceptionState(e, t, lang)}</span>
    </>
  );
}

/** Las ordenes de una excepcion abierta, para quien puede (resolver_aviso). */
export function exceptionOrders(t: Messages, lang: Lang, exception: ExceptionInfo, people: readonly Person[], me: number | undefined): OrderSpec[] {
  if (exception.estado === 'resuelta') return [];
  const base = { excepcion_id: exception.id, rev: exception.rev };
  const others = people.filter((p) => p.id !== exception.responsable_id);
  const orders: OrderSpec[] = [];
  if (me !== undefined && exception.responsable_id !== me) {
    orders.push({
      action: 'asignar_excepcion',
      label: t.exceptions.takeIt,
      intro: <p>{t.exceptions.takeItIntro}</p>,
      data: () => ({ ...base, responsable_id: me }),
    });
  }
  if (others.length > 0) {
    orders.push({
      action: 'asignar_excepcion',
      label: t.exceptions.assign,
      fields: [
        {
          name: 'responsable_id',
          label: t.exceptions.assignTo,
          kind: 'select',
          required: true,
          initial: String(others[0]!.id),
          options: others.map((p) => ({ value: String(p.id), label: p.nombre })),
        },
      ],
      data: (v) => ({ ...base, responsable_id: Number(v.responsable_id) }),
    });
  }
  orders.push({
    action: 'esperar_externo',
    label: t.exceptions.wait,
    fields: [
      {
        name: 'esperando_a',
        label: t.exceptions.waitFor,
        kind: 'select',
        required: true,
        initial: 'proveedor',
        options: WAITING_ON.map((w) => ({ value: w, label: stateLabel(lang, 'esperando_a', w) ?? w })),
      },
      { name: 'fecha_seguimiento', label: t.exceptions.followUpDate, kind: 'date' },
      { name: 'motivo', label: t.action.note, kind: 'text' },
    ],
    data: (v) => ({
      ...base,
      esperando_a: v.esperando_a,
      fecha_seguimiento: v.fecha_seguimiento || null,
      motivo: v.motivo || undefined,
    }),
  });
  orders.push({
    action: 'resolver_excepcion',
    label: t.exceptions.resolve,
    primary: true,
    intro: <p>{t.exceptions.resolveIntro}</p>,
    fields: [
      {
        name: 'resolucion',
        label: t.exceptions.resolution,
        kind: 'select',
        required: true,
        initial: 'corregido',
        options: RESOLUTIONS.map((r) => ({ value: r, label: stateLabel(lang, 'resolucion', r) ?? r })),
      },
      { name: 'motivo', label: t.exceptions.whatWasDone, kind: 'text', required: true },
    ],
    data: (v) => ({ ...base, resolucion: v.resolucion, motivo: v.motivo }),
  });
  return orders;
}
