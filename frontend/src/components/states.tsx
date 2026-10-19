// Los tres estados de cualquier pantalla que lee: cargando, error y vacio. Un vacio dice
// algo util ("Niets heeft je aandacht nodig"), no una tabla en blanco.
import type { ReactNode } from 'react';
import { CircleAlert, Inbox, LoaderCircle, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useT, type Lang, type Messages } from '@/i18n';
import { errorText } from '@/i18n/domain';
import { ApiError } from '@/lib/api';
import { cn } from '@/lib/utils';

export function Loading({ label, className }: { label?: string; className?: string }) {
  const { t } = useT();
  return (
    <div role='status' aria-live='polite' className={cn('flex items-center gap-2 py-10 text-muted-foreground', className)}>
      <LoaderCircle className='h-4 w-4 animate-spin motion-reduce:animate-none' aria-hidden='true' />
      <span>{label ?? t.common.loading}</span>
    </div>
  );
}

export function EmptyState({
  title,
  text,
  icon: Icon = Inbox,
  action,
}: {
  title: string;
  text?: string;
  icon?: LucideIcon;
  action?: ReactNode;
}) {
  return (
    <div className='flex flex-col items-center gap-2 rounded-md border border-dashed border-[#d6d1c6] px-6 py-12 text-center'>
      <Icon className='h-6 w-6 text-muted-foreground' aria-hidden='true' />
      <p className='font-medium'>{title}</p>
      {text && <p className='max-w-md text-muted-foreground'>{text}</p>}
      {action && <div className='mt-2'>{action}</div>}
    </div>
  );
}

/** El texto de un error de la API en el idioma de la app: el de su codigo estable
 *  (catalogo de textos, "errores") y, si no trae uno conocido, el de su clase. La frase del
 *  servidor (en castellano) no va aqui: va en TechnicalDetail. */
export function errorMessage(error: unknown, t: Messages, lang: Lang): string {
  if (!(error instanceof ApiError)) return t.errors.unexpected;
  const known = errorText(lang, error.code);
  if (known) return known;
  switch (error.kind) {
    case 'unauthorized':
      return t.errors.unauthorized;
    case 'forbidden':
      return t.errors.forbidden;
    case 'not_found':
      return t.errors.notFound;
    case 'stale':
      return t.errors.stale;
    case 'conflict':
      return t.errors.conflict;
    case 'bad_request':
      return t.errors.badRequest;
    case 'unavailable':
      return t.errors.unavailable;
    case 'incompatible':
      return t.errors.incompatible;
    default:
      return t.errors.unexpected;
  }
}

/** La frase del servidor, en castellano, para quien da soporte: plegada y en pequeno. */
// Para el soporte: el estado HTTP y el codigo estable del error. La frase del servidor
// (`error`) es castellano para la CLI y la auditoria y no se ensena en la app.
export function TechnicalDetail({ error }: { error: unknown }) {
  const { t } = useT();
  if (!(error instanceof ApiError) || !error.code) return null;
  return (
    <details className='text-xs text-muted-foreground'>
      <summary className='cursor-pointer select-none rounded-sm'>{t.errors.technical}</summary>
      <p className='mt-1 font-mono break-words'>
        {error.status ? `${error.status} ` : ''}
        {error.code}
      </p>
    </details>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t, lang } = useT();
  const stale = error instanceof ApiError && error.kind === 'stale';
  return (
    <div role='alert' className='flex flex-col items-start gap-3 rounded-md border border-[#e2c1a8] bg-[#fdf3e8] px-5 py-4'>
      <div className='flex items-center gap-2 font-medium text-[#4a2205]'>
        <CircleAlert className='h-4 w-4' aria-hidden='true' />
        <span>{t.errors.title}</span>
      </div>
      <p className='text-[#4a2205]'>{errorMessage(error, t, lang)}</p>
      <TechnicalDetail error={error} />
      {onRetry && (
        <Button variant='outline' size='sm' onClick={onRetry}>
          {stale ? t.common.reload : t.common.retry}
        </Button>
      )}
    </div>
  );
}
