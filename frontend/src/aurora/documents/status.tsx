// Status de Aurora (components/ui/status.tsx, entrega del 28-10-2026): la pastilla .ui-status con
// su punto (online en verde, degraded en naranja, offline en rojo y maintenance en azul;
// workspace-layout.css:38-44). Cambios: StatusIndicator sin el latido cuando `still` (lo decide
// components/status-pill.tsx: solo late lo que pide hacer algo ya); los data-slot para las
// pruebas; StatusLabel sin los textos en ingles por defecto (siempre lleva el suyo).
import type { ComponentProps, HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';
import { Badge } from './badge';

export type AuroraStatus = 'online' | 'offline' | 'maintenance' | 'degraded';

export type StatusProps = ComponentProps<typeof Badge> & { status: AuroraStatus };

export const Status = ({ className, status, ...props }: StatusProps) => (
  <Badge className={cn('flex items-center gap-2', 'group', 'ui-status', status, className)} variant='secondary' data-slot='status' {...props} />
);

export type StatusIndicatorProps = HTMLAttributes<HTMLSpanElement> & { still?: boolean };

export const StatusIndicator = ({ className, still = false, ...props }: StatusIndicatorProps) => (
  <span className={cn('relative flex h-2 w-2', 'ui-status-indicator', className)} aria-hidden='true' data-slot='status-indicator' {...props}>
    {!still && (
      <span
        className={cn(
          'absolute inline-flex h-full w-full animate-ping rounded-full opacity-75',
          'group-[.online]:bg-emerald-500',
          'group-[.offline]:bg-red-500',
          'group-[.maintenance]:bg-blue-500',
          'group-[.degraded]:bg-amber-500'
        )}
      />
    )}
    <span
      className={cn(
        'relative inline-flex h-2 w-2 rounded-full',
        'group-[.online]:bg-emerald-500',
        'group-[.offline]:bg-red-500',
        'group-[.maintenance]:bg-blue-500',
        'group-[.degraded]:bg-amber-500'
      )}
    />
  </span>
);

export type StatusLabelProps = HTMLAttributes<HTMLSpanElement>;

export const StatusLabel = ({ className, children, ...props }: StatusLabelProps) => (
  <span className={cn('text-muted-foreground', 'ui-status-label', className)} data-slot='status-label' {...props}>
    {children}
  </span>
);
