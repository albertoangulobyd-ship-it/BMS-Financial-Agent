// Las ordenes dentro de una tarjeta (especificacion §2.4): todo pasa en el sitio donde se pide,
// la tarjeta .detail del panel o la de una fila de la hoja de una factura, con las piezas de
// Aurora y ninguna nueva:
// 1. los botones de la tarjeta: .primary la principal y .outline las demas (styles.css:3);
// 2. el formulario dentro de la tarjeta: el texto en la caja de Aurora (.composer e .input-row
//    input, sin aura-slot), la fecha con .filter-date-trigger y GlassCalendar, elegir de una
//    lista con FilterComboBox (.filter-combo-trigger y .ui-command-list), y su frase en p;
// 3. el "si": la tarjeta .chat-export de la conversacion (ai-actions.css:1), con su texto, la
//    orden y "Cancelar";
// 4. el resultado: .success en el panel o ws-toast en Documentos (OrderNotice).
// Cada orden va a POST /api/v2/acciones con la rev o la huella que se vio. Un 409 (otra persona
// lo cambio antes) se dice en la p de la tarjeta y se vuelve a leer. Sin permiso no hay botones:
// lo deciden quienes ponen las ordenes (useCan). Ninguna paga, aprueba ni presenta nada.
import { CalendarDays, ChevronDown } from 'lucide-react';
import { createContext, useContext, useId, useState, type ReactNode } from 'react';
import { LOCALES, fmt, useT, type Lang, type Messages } from '@/i18n';
import { actionText, errorText } from '@/i18n/domain';
import type { ActionName } from '@/lib/actions';
import { ApiError } from '@/lib/api';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { FilterComboBox } from './search/ui/heroui-combo-box';
import { GlassCalendar, longDate } from './search/ui/glass-calendar';
import { Popover, PopoverContent, PopoverTrigger } from './search/ui/popover';

/** Un campo del formulario de una orden. */
export interface OrderField {
  name: string;
  label: string;
  kind: 'text' | 'date' | 'select' | 'iban' | 'tel';
  required?: boolean;
  minLength?: number;
  /** Una linea debajo del campo (p de la tarjeta). */
  help?: string;
  initial?: string;
  options?: { value: string; label: string }[];
  /** Sin "(opcional)" aunque no sea obligatorio (un valor que ya viene puesto). */
  hideOptional?: boolean;
}

export type OrderValues = Record<string, string>;

/** Una orden de una tarjeta: su boton, su formulario y lo que manda. */
export interface OrderSpec {
  action: ActionName;
  /** Lo que dice el boton de la tarjeta (y el del "si"). */
  label: string;
  /** La principal de la tarjeta (.primary); las demas, .outline. */
  primary?: boolean;
  /** Lo que va a pasar, en una o dos frases (lineas p). */
  intro?: ReactNode;
  fields?: OrderField[];
  /** Los datos de la orden a partir de lo escrito (lo fijo: ids, rev, huella). */
  data: (values: OrderValues) => Record<string, unknown>;
  /** Una comprobacion antes de mandar: el texto del problema, o null. */
  validate?: (values: OrderValues) => string | null;
  /** Lo que se ve debajo del primer campo segun lo escrito ("antes -> despues"). */
  preview?: (values: OrderValues) => ReactNode;
  /** Por que no se puede mandar aun (la segunda firma): se dice y no se deja mandar. */
  blocked?: string;
  /** El texto del "si" (por defecto, el del catalogo de la orden). */
  confirm?: string;
  /** El nombre del boton para un lector de pantalla, si el visible no basta. */
  ariaLabel?: string;
}

/** Donde se dice lo hecho: .success en el panel, ws-toast en Documentos. */
export const OrderNotice = createContext<(text: string) => void>(() => undefined);

/** Las ordenes que dejan algo con el nombre de la persona y no se deshacen sin otra orden (sin
 *  frase propia en el catalogo): el "si" lo dice (especificacion §2.4, punto 3). */
const STAYS = new Set<ActionName>(['marcar_pagada']);

/** El texto del "si" de una orden. */
export function confirmText(action: ActionName, lang: Lang, t: Messages): string {
  return actionText(lang, action)?.confirm ?? (STAYS.has(action) ? t.aurora.order.stays : t.aurora.order.yours);
}

/**
 * El error de una orden. "segunda_persona" (la regla de las dos personas) dice, para cada
 * orden, por que; un pago que el motor no deja apuntar, confirmar o retirar asi, que mirar.
 */
export function orderErrorMessage(action: ActionName, error: unknown, t: Messages, lang: Lang): string {
  if (error instanceof ApiError && error.code === 'segunda_persona') {
    const specific = (t.errors.secondPerson as Partial<Record<string, string>>)[action];
    if (specific) return specific;
  }
  if (error instanceof ApiError && error.code === 'estado_no_valido' && PAYMENT_ACTIONS.has(action)) return t.payments.stateError;
  return apiErrorMessage(error, t, lang);
}

const PAYMENT_ACTIONS = new Set<ActionName>(['marcar_pagada', 'confirmar_pago', 'retirar_pago']);

/** El texto de un error de la API: el de su codigo estable y, si no, el de su clase. */
export function apiErrorMessage(error: unknown, t: Messages, lang: Lang): string {
  if (!(error instanceof ApiError)) return t.errors.unexpected;
  const known = errorText(lang, error.code);
  if (known) return known;
  const kinds: Record<string, string> = {
    unauthorized: t.errors.unauthorized,
    forbidden: t.errors.forbidden,
    not_found: t.errors.notFound,
    stale: t.errors.stale,
    conflict: t.errors.conflict,
    bad_request: t.errors.badRequest,
    unavailable: t.errors.unavailable,
    incompatible: t.errors.incompatible,
  };
  return kinds[error.kind] ?? t.errors.unexpected;
}

/** El estado y el codigo de un error, para quien da soporte (nunca la frase del servidor). */
export function technicalCode(error: unknown): string | null {
  if (!(error instanceof ApiError) || !error.code) return null;
  return `${error.status ? `${error.status} ` : ''}${error.code}`;
}

/** Un error en la p de la tarjeta, con su codigo en pequeno. */
export function ErrorLine({ error, message }: { error: unknown; message: string }) {
  const code = technicalCode(error);
  return (
    <p role='alert' className='order-error'>
      {message}
      {code && (
        <>
          {' '}
          <small data-proper-name=''>({code})</small>
        </>
      )}
    </p>
  );
}

/** La tarjeta del "si" (.chat-export de la conversacion): su texto, la orden y "Cancelar". */
export function ConfirmCard({
  text,
  label,
  busy,
  onConfirm,
  onCancel,
}: {
  text: string;
  label: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useT();
  return (
    <div className='chat-export' role='group' aria-label={label}>
      <p>{text}</p>
      <button type='button' onClick={onConfirm} disabled={busy} aria-busy={busy || undefined} data-order-confirm=''>
        {label}
      </button>
      <button type='button' onClick={onCancel}>
        {t.common.cancel}
      </button>
    </div>
  );
}

const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const fromIso = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`);

/** "3 oct 2026" (el "d MMM yyyy" de la busqueda de Aurora). */
function shortDate(iso: string, locale: string): string {
  const date = fromIso(iso);
  const month = new Intl.DateTimeFormat(locale, { month: 'short' }).format(date).replace(/\.$/, '');
  return `${date.getDate()} ${month} ${date.getFullYear()}`;
}

/** Un campo del formulario con las piezas de Aurora. */
export function FieldInput({ field, value, onChange }: { field: OrderField; value: string; onChange: (value: string) => void }) {
  const { t, lang } = useT();
  const id = useId();
  const [open, setOpen] = useState(false);
  const label = field.required || field.hideOptional ? field.label : `${field.label} (${t.action.optional})`;
  if (field.kind === 'select') {
    return (
      <div className='order-field'>
        <FilterComboBox label={label} options={field.options ?? []} value={value} onValueChange={onChange} />
        {field.help && <p>{field.help}</p>}
      </div>
    );
  }
  if (field.kind === 'date') {
    const locale = LOCALES[lang];
    return (
      <div className='order-field filter-date'>
        <span className='filter-label' id={`${id}-label`}>
          {label}
        </span>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button type='button' className='filter-date-trigger' aria-labelledby={`${id}-label ${id}-value`}>
              <CalendarDays size={14} />
              <span id={`${id}-value`}>{value ? shortDate(value, locale) : t.aurora.order.noDate}</span>
              <ChevronDown size={13} />
            </button>
          </PopoverTrigger>
          <PopoverContent className='calendar-popover'>
            <GlassCalendar
              label={field.label}
              selectedDate={value ? fromIso(value) : undefined}
              onDateSelect={(d) => {
                onChange(isoDay(d));
                setOpen(false);
              }}
              onClear={() => {
                onChange('');
                setOpen(false);
              }}
            />
          </PopoverContent>
        </Popover>
        {value && <span className='sr-only'>{longDate(fromIso(value), locale)}</span>}
        {field.help && <p>{field.help}</p>}
      </div>
    );
  }
  return (
    <div className='order-field'>
      <label className='filter-label' htmlFor={id}>
        {label}
      </label>
      <div className='composer'>
        <div className='input-row'>
          <input
            id={id}
            value={value}
            type={field.kind === 'tel' ? 'tel' : 'text'}
            autoComplete='off'
            spellCheck={field.kind === 'text'}
            aria-required={field.required || undefined}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      </div>
      {field.help && <p>{field.help}</p>}
    </div>
  );
}

function initialValues(fields: readonly OrderField[]): OrderValues {
  return Object.fromEntries(fields.map((f) => [f.name, f.initial ?? '']));
}

/**
 * Los botones de las ordenes de una tarjeta y, al pulsar uno, su formulario en la misma tarjeta
 * y despues el "si". `onDone` despues de una orden hecha (ademas de volver a leer: bump).
 */
export function Orders({
  orders,
  onDone,
  before,
}: {
  orders: readonly OrderSpec[];
  onDone?: () => void;
  /** Botones que no son una orden (abrir, descargar), delante de las ordenes. */
  before?: ReactNode;
}) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { bump } = useRefresh();
  const notify = useContext(OrderNotice);
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [stage, setStage] = useState<'form' | 'confirm'>('form');
  const [values, setValues] = useState<OrderValues>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [error, setError] = useState<{ error: unknown; action: ActionName } | null>(null);
  const [busy, setBusy] = useState(false);
  const order = openIndex === null ? null : orders[openIndex];

  function start(index: number) {
    const chosen = orders[index]!;
    setOpenIndex(index);
    setValues(initialValues(chosen.fields ?? []));
    setProblem(null);
    setError(null);
    // Sin nada que escribir, directamente el "si" (salvo que no se pueda mandar aun).
    setStage(chosen.fields?.length || chosen.blocked || chosen.intro ? 'form' : 'confirm');
  }

  function close() {
    setOpenIndex(null);
    setStage('form');
    setProblem(null);
  }

  function check(): boolean {
    if (!order) return false;
    for (const field of order.fields ?? []) {
      const value = (values[field.name] ?? '').trim();
      if (field.required && !value) {
        setProblem(fmt(t.action.required, { field: field.label }));
        return false;
      }
      if (field.minLength && value && value.length < field.minLength) {
        setProblem(fmt(t.action.tooShort, { field: field.label, n: field.minLength }));
        return false;
      }
    }
    const extra = order.validate?.(values) ?? null;
    if (extra) {
      setProblem(extra);
      return false;
    }
    setProblem(null);
    return true;
  }

  async function send() {
    if (!order || !session || busy || order.blocked) return;
    setBusy(true);
    setError(null);
    try {
      await session.api.action(order.action, order.data(values));
      close();
      notify(fmt(t.aurora.order.done, { what: order.label }));
      bump();
      onDone?.();
    } catch (e) {
      if (e instanceof ApiError && e.kind === 'stale') {
        // Otra persona lo cambio antes: se dice y se vuelve a leer (lo de ella se ve).
        close();
        setError({ error: e, action: order.action });
        bump();
        onDone?.();
      } else {
        setStage('form');
        setError({ error: e, action: order.action });
      }
    } finally {
      setBusy(false);
    }
  }

  const errorLine =
    error &&
    (error.error instanceof ApiError && error.error.kind === 'stale' ? (
      <ErrorLine error={error.error} message={t.aurora.order.stale} />
    ) : (
      <ErrorLine error={error.error} message={orderErrorMessage(error.action, error.error, t, lang)} />
    ));

  if (!order) {
    if (orders.length === 0 && !before) return errorLine;
    return (
      <>
        {errorLine}
        <div>
          {before}
          {orders.map((o, i) => (
            <button key={`${o.action}-${i}`} type='button' className={o.primary ? 'primary' : 'outline'} aria-label={o.ariaLabel} onClick={() => start(i)}>
              {o.label}
            </button>
          ))}
        </div>
      </>
    );
  }

  const fields = order.fields ?? [];
  return (
    <div className='order-form'>
      {typeof order.intro === 'string' ? <p>{order.intro}</p> : order.intro}
      {order.blocked && (
        <p role='status' data-testid='action-blocked'>
          {order.blocked}
        </p>
      )}
      {fields.map((field, index) => (
        <div key={field.name}>
          <FieldInput
            field={field}
            value={values[field.name] ?? ''}
            onChange={(v) => {
              setValues((old) => ({ ...old, [field.name]: v }));
              // Lo que faltaba ya se esta arreglando: el aviso no se queda al lado.
              setProblem(null);
            }}
          />
          {index === 0 && order.preview?.(values)}
        </div>
      ))}
      {fields.length === 0 && order.preview?.(values)}
      {problem && (
        <p role='alert' className='order-error'>
          {problem}
        </p>
      )}
      {errorLine}
      <div>
        <button
          type='button'
          className='primary'
          disabled={Boolean(order.blocked) || busy}
          onClick={() => {
            if (check()) setStage('confirm');
          }}
        >
          {order.label}
        </button>
        <button type='button' className='outline' onClick={close}>
          {t.common.cancel}
        </button>
      </div>
      {stage === 'confirm' && (
        <ConfirmCard
          text={order.confirm ?? confirmText(order.action, lang, t)}
          label={order.label}
          busy={busy}
          onConfirm={() => void send()}
          onCancel={() => (fields.length || order.intro ? setStage('form') : close())}
        />
      )}
    </div>
  );
}
