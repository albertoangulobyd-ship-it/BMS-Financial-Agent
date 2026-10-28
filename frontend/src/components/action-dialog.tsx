// Una orden de una persona, siempre igual: un boton abre un dialogo que dice UNA vez, en
// palabras normales, que va a pasar (la frase de la pantalla o, sin ella, la de
// confirmacion del catalogo cuando mueve dinero, btw o el banco; el boton ya dice la orden,
// asi que no se pregunta "Doorgaan?"), pide lo que la orden necesita (un motivo, una
// fecha...) y la manda a
// POST /api/v2/acciones con la rev o la huella que la persona vio. Si otra persona lo
// cambio antes (409, codigo conflicto) lo dice y ofrece volver a cargar; cualquier otro
// error, en neerlandes o ingles por su codigo, con la frase del servidor plegada.
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { LoaderCircle } from 'lucide-react';
import { errorMessage, TechnicalDetail } from '@/components/states';
import { Button, type ButtonProps } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { actionText } from '@/i18n/domain';
import type { ActionName } from '@/lib/actions';
import { ApiError } from '@/lib/api';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { NO_VALUE, formatDate, parseTypedDate } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface ActionField {
  name: string;
  label: string;
  kind: 'textarea' | 'text' | 'date' | 'select' | 'iban' | 'tel';
  required?: boolean;
  minLength?: number;
  help?: string;
  initial?: string;
  options?: { value: string; label: string }[];
  /** No poner "(niet verplicht)" aunque no sea obligatorio (el valor nuevo de un campo). */
  hideOptional?: boolean;
}

type Values = Record<string, string>;

// Lo que no se puede deshacer lleva ademas su aviso aparte, aunque la pantalla ya explique
// la orden: anotar una aangifte ya presentada.
const IRREVERSIBLE = new Set<ActionName>(['btw_anotar_presentacion']);

/** Lo que dice el dialogo: la frase de la pantalla o, sin ella, la del catalogo (la de
 *  confirmar si la hay, si no la descripcion); y el aviso aparte, solo si no se deshace. */
export function dialogTexts(
  action: ActionName,
  hasIntro: boolean,
  texts: { description: string; confirm: string | null } | null
): { description: string | null; warning: string | null } {
  const confirm = texts?.confirm ?? null;
  const warning = IRREVERSIBLE.has(action) ? confirm : null;
  if (hasIntro) return { description: null, warning };
  return { description: warning ? (texts?.description ?? null) : (confirm ?? texts?.description ?? null), warning };
}

export function ActionDialog({
  open,
  onOpenChange,
  action,
  title,
  intro,
  fields = [],
  data,
  submitLabel,
  onDone,
  children,
  validate,
  preview,
  blocked,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  action: ActionName;
  title?: string;
  /** Lo que va a pasar, en una o dos frases. */
  intro?: ReactNode;
  fields?: ActionField[];
  /** Los datos de la orden a partir de lo escrito (lo fijo: ids, rev, huella). */
  data: (values: Values) => Record<string, unknown>;
  submitLabel?: string;
  onDone?: () => void;
  /** Lo que se ve entre la frase y los campos (p. ej. "antes -> despues"). */
  children?: ReactNode;
  /** Una comprobacion extra antes de mandar: el texto del problema, o null. */
  validate?: (values: Values) => string | null;
  /** Lo que se ve bajo los campos segun lo escrito (p. ej. "antes -> despues"). */
  preview?: (values: Values) => ReactNode;
  /** Por que esta orden no se puede mandar aun (falta la firma de un colega): se dice y el
   *  boton no se deja pulsar, en vez de mandar algo que el servidor va a negar. */
  blocked?: string;
}) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { bump } = useRefresh();
  const texts = actionText(lang, action);
  const formId = useId();
  const [values, setValues] = useState<Values>(() => initialValues(fields));
  const [problem, setProblem] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const alertRef = useRef<HTMLDivElement>(null);

  // Un error de la orden se ve aunque el dialogo sea largo: se lleva a la vista.
  useEffect(() => {
    if (error !== null) alertRef.current?.scrollIntoView({ block: 'nearest' });
  }, [error]);

  function reset(next: boolean) {
    if (next) {
      setValues(initialValues(fields));
      setProblem(null);
      setError(null);
    }
    onOpenChange(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!session || busy || blocked) return;
    for (const field of fields) {
      const value = (values[field.name] ?? '').trim();
      if (field.required && !value) {
        setProblem(fmt(t.action.required, { field: field.label }));
        return;
      }
      if (field.minLength && value && value.length < field.minLength) {
        setProblem(fmt(t.action.tooShort, { field: field.label, n: field.minLength }));
        return;
      }
    }
    for (const field of fields) {
      const value = (values[field.name] ?? '').trim();
      if (field.kind === 'date' && value && parseTypedDate(value) === null) {
        setProblem(fmt(t.action.badDate, { field: field.label }));
        return;
      }
    }
    const sent = apiValues(fields, values);
    const extra = validate?.(sent) ?? null;
    if (extra) {
      setProblem(extra);
      return;
    }
    setProblem(null);
    setError(null);
    setBusy(true);
    try {
      await session.api.action(action, data(sent));
      onOpenChange(false);
      bump();
      onDone?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const stale = error instanceof ApiError && error.kind === 'stale';
  const said = dialogTexts(action, Boolean(intro), texts);
  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent closeLabel={t.common.close} className='max-w-lg'>
        <DialogHeader>
          <DialogTitle>{title ?? texts?.label ?? action}</DialogTitle>
          {/* Lo que va a pasar, en palabras de esta pantalla; sin eso, lo que dice el
              catalogo de la orden. Una sola explicacion, no dos. */}
          {intro ? (
            <DialogDescription asChild>
              <div className='pt-1 text-[13.5px] leading-relaxed text-foreground'>{intro}</div>
            </DialogDescription>
          ) : (
            <DialogDescription>{said.description}</DialogDescription>
          )}
        </DialogHeader>
        {children}
        {/* Lo que impide mandarla, lo primero que se lee. */}
        {blocked && (
          <p role='status' data-testid='action-blocked' className='rounded-md border border-border bg-muted px-3 py-2 text-[13px] font-medium leading-relaxed'>
            {blocked}
          </p>
        )}
        <form id={formId} onSubmit={submit} className='flex flex-col gap-4' noValidate>
          {fields.map((field, index) => (
            <div key={field.name} className='flex flex-col gap-2'>
              <FieldInput
                field={field}
                value={values[field.name] ?? ''}
                onChange={(v) => {
                  setValues((old) => ({ ...old, [field.name]: v }));
                  // Lo que faltaba ya se esta arreglando: el aviso no se queda al lado de lo
                  // elegido ("Vul Factuur in" con la factura ya elegida).
                  setProblem(null);
                }}
              />
              {/* Lo que se va a guardar, justo debajo de lo que se escribe. */}
              {index === 0 && preview?.(apiValues(fields, values))}
            </div>
          ))}
          {fields.length === 0 && preview?.(apiValues(fields, values))}
          {said.warning && (
            <p
              data-testid='action-warning'
              className='rounded-md border border-notice-border bg-notice px-3 py-2 text-[13px] leading-relaxed text-notice-foreground'
            >
              {said.warning}
            </p>
          )}
          {problem && (
            <p role='alert' className='text-sm font-medium text-late-foreground'>
              {problem}
            </p>
          )}
          {error !== null && (
            <div ref={alertRef} role='alert' className='flex flex-col gap-2 rounded-md border border-notice-border bg-notice px-3 py-2 text-notice-foreground'>
              <p className='font-medium'>{actionErrorMessage(action, error, t, lang)}</p>
              <TechnicalDetail error={error} />
            </div>
          )}
        </form>
        <DialogFooter>
          <Button type='button' variant='outline' onClick={() => reset(false)}>
            {t.common.cancel}
          </Button>
          {stale ? (
            <Button
              type='button'
              onClick={() => {
                onOpenChange(false);
                bump();
                onDone?.();
              }}
            >
              {t.common.reload}
            </Button>
          ) : (
            <Button type='submit' form={formId} disabled={busy || Boolean(blocked)}>
              {busy && <LoaderCircle className='mr-2 h-4 w-4 animate-spin motion-reduce:animate-none' aria-hidden='true' />}
              {submitLabel ?? texts?.label ?? t.common.save}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * El error de una orden. "segunda_persona" (la regla de las dos personas) dice, para cada
 * orden, por que: la app sabe cual de los casos es (tu cambiaste el telefono, tu dejaste
 * listo el trimestre, falta la firma de un colega...), y la frase general del catalogo
 * ("o esto, o lo otro") no ayuda a saber que hacer.
 */
export function actionErrorMessage(action: ActionName, error: unknown, t: Messages, lang: Lang): string {
  if (error instanceof ApiError && error.code === 'segunda_persona') {
    const specific = (t.errors.secondPerson as Partial<Record<string, string>>)[action];
    if (specific) return specific;
  }
  // Un pago que el motor no deja apuntar, confirmar o retirar asi (el banco o Exact ya lo
  // traen, no queda nada, la linea ya esta usada): la frase general no dice que mirar.
  if (error instanceof ApiError && error.code === 'estado_no_valido' && PAYMENT_ACTIONS.has(action)) return t.payments.stateError;
  return errorMessage(error, t, lang);
}

const PAYMENT_ACTIONS = new Set<ActionName>(['marcar_pagada', 'confirmar_pago', 'retirar_pago']);

function initialValues(fields: ActionField[]): Values {
  // Una fecha se escribe dd-mm-aaaa (lo que llega de la API es AAAA-MM-DD).
  return Object.fromEntries(
    fields.map((f) => [f.name, f.kind === 'date' && f.initial ? formatDate(f.initial).replace(NO_VALUE, '') : (f.initial ?? '')])
  );
}

/** Lo escrito como lo pide la API: cada fecha en AAAA-MM-DD (vacia si no se lee). */
function apiValues(fields: ActionField[], values: Values): Values {
  const out = { ...values };
  for (const field of fields) {
    if (field.kind === 'date') out[field.name] = parseTypedDate(values[field.name] ?? '') ?? '';
  }
  return out;
}

function FieldInput({ field, value, onChange }: { field: ActionField; value: string; onChange: (v: string) => void }) {
  const { t } = useT();
  const id = useId();
  const helpId = useId();
  const described = field.help ? helpId : undefined;
  const common = {
    id,
    value,
    'aria-describedby': described,
    'aria-required': field.required || undefined,
  };
  return (
    <div className='flex flex-col gap-1.5'>
      <Label htmlFor={id}>
        {field.label}
        {!field.required && !field.hideOptional && (
          <span className='ml-1 font-normal text-muted-foreground'>({t.action.optional})</span>
        )}
      </Label>
      {field.kind === 'textarea' ? (
        <textarea
          {...common}
          rows={3}
          onChange={(e) => onChange(e.target.value)}
          className='min-h-[4.5rem] w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
        />
      ) : field.kind === 'select' ? (
        <select
          {...common}
          onChange={(e) => onChange(e.target.value)}
          className='h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
        >
          {(field.options ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : (
        <Input
          {...common}
          // Las fechas son texto dd-mm-aaaa: el selector del navegador sale en el formato y el
          // idioma de Windows (mm/dd/yyyy, o en castellano).
          type={field.kind === 'tel' ? 'tel' : 'text'}
          inputMode={field.kind === 'date' ? 'numeric' : undefined}
          placeholder={field.kind === 'date' ? t.action.datePlaceholder : undefined}
          autoComplete='off'
          spellCheck={field.kind === 'text'}
          onChange={(e) => onChange(e.target.value)}
          className={cn(field.kind === 'iban' && 'font-mono uppercase tracking-[0.04em]', field.kind === 'date' && 'w-40')}
        />
      )}
      {field.help && (
        <p id={helpId} className='text-xs leading-relaxed text-muted-foreground'>
          {field.help}
        </p>
      )}
    </div>
  );
}

/** Un boton que abre su dialogo de orden. */
export function ActionButton({
  label,
  variant = 'outline',
  size = 'sm',
  icon,
  ariaLabel,
  onToggle,
  ...dialog
}: Omit<Parameters<typeof ActionDialog>[0], 'open' | 'onOpenChange'> & {
  label: string;
  variant?: ButtonProps['variant'];
  size?: ButtonProps['size'];
  icon?: ReactNode;
  /** El nombre del boton para el lector de pantalla, si el visible no basta ("Niet deze"
   *  en una lista de varias propuestas). */
  ariaLabel?: string;
  /** Avisa al abrir y al cerrar (para leer lo que el dialogo ofrece solo cuando se abre). */
  onToggle?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const toggle = (next: boolean) => {
    setOpen(next);
    onToggle?.(next);
  };
  return (
    <>
      <Button type='button' variant={variant} size={size} aria-label={ariaLabel} onClick={() => toggle(true)}>
        {icon}
        {label}
      </Button>
      {open && <ActionDialog {...dialog} open={open} onOpenChange={toggle} />}
    </>
  );
}
