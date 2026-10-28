// Avatar de Aurora (components/ui/avatar.tsx, entrega del 28-10-2026), tal cual (sin AvatarImage:
// la app no carga imagenes de nadie).
import * as React from 'react';
import { Avatar as Primitive } from 'radix-ui';
import { cn } from '@/lib/utils';

export const Avatar = React.forwardRef<React.ElementRef<typeof Primitive.Root>, React.ComponentPropsWithoutRef<typeof Primitive.Root>>(
  ({ className, ...props }, ref) => <Primitive.Root ref={ref} className={cn('ui-avatar', className)} {...props} />
);
Avatar.displayName = 'Avatar';
export const AvatarFallback = Primitive.Fallback;
