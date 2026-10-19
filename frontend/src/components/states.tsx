// Los tres estados de cualquier pantalla que lee: cargando, error y vacio. Un vacio dice
// algo util ("Niets heeft je aandacht nodig"), no una tabla en blanco.
import type { ReactNode } from 'react';
import { CircleAlert, Inbox, LoaderCircle, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useT, type Messages } from '@/i18n';
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

/** El texto de un error de la API en el idioma de la app (el del servidor no se ensena). */
export function errorMessage(error: unknown, t: Messages): string {
  if (!(error instanceof ApiError)) return t.errors.unexpected;
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

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useT();
  const stale = error instanceof ApiError && error.kind === 'stale';
  return (
    <div role='alert' className='flex flex-col items-start gap-3 rounded-md border border-[#e2c1a8] bg-[#fdf3e8] px-5 py-4'>
      <div className='flex items-center gap-2 font-medium text-[#4a2205]'>
        <CircleAlert className='h-4 w-4' aria-hidden='true' />
        <span>{t.errors.title}</span>
      </div>
      <p className='text-[#4a2205]'>{errorMessage(error, t)}</p>
      {onRetry && (
        <Button variant='outline' size='sm' onClick={onRetry}>
          {stale ? t.common.reload : t.common.retry}
        </Button>
      )}
    </div>
  );
}
