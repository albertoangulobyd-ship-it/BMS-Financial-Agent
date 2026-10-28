// Popover de Aurora (components/ui/popover.tsx, entrega del 28-10-2026), tal cual, con Radix desde
// el paquete radix-ui que ya usa la app (el mismo @radix-ui/react-popover).
import * as React from 'react';
import { Popover as Primitive } from 'radix-ui';
import { cn } from '@/lib/utils';

export const Popover = Primitive.Root,
  PopoverTrigger = Primitive.Trigger;
export const PopoverContent = React.forwardRef<
  React.ElementRef<typeof Primitive.Content>,
  React.ComponentPropsWithoutRef<typeof Primitive.Content>
>(({ className, align = 'start', sideOffset = 8, ...props }, ref) => (
  <Primitive.Portal>
    <Primitive.Content ref={ref} align={align} sideOffset={sideOffset} collisionPadding={18} className={cn('ui-popover', className)} {...props} />
  </Primitive.Portal>
));
PopoverContent.displayName = 'PopoverContent';
