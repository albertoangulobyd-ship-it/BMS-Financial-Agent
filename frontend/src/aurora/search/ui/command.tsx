// Command de Aurora (components/ui/command.tsx, entrega del 28-10-2026), tal cual (sobre cmdk), sin
// CommandDialog ni CommandSeparator, que la busqueda no usa.
import * as React from 'react';
import { Command as Primitive } from 'cmdk';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';

export const Command = React.forwardRef<React.ElementRef<typeof Primitive>, React.ComponentPropsWithoutRef<typeof Primitive>>(
  ({ className, ...props }, ref) => <Primitive ref={ref} className={cn('ui-command', className)} {...props} />
);
Command.displayName = 'Command';
export const CommandInput = React.forwardRef<React.ElementRef<typeof Primitive.Input>, React.ComponentPropsWithoutRef<typeof Primitive.Input>>(
  ({ className, ...props }, ref) => (
    <div className='ui-command-input'>
      <Search size={15} />
      <Primitive.Input ref={ref} className={className} {...props} />
    </div>
  )
);
CommandInput.displayName = 'CommandInput';
export const CommandList = React.forwardRef<React.ElementRef<typeof Primitive.List>, React.ComponentPropsWithoutRef<typeof Primitive.List>>(
  ({ className, ...props }, ref) => <Primitive.List ref={ref} className={cn('ui-command-list', className)} {...props} />
);
CommandList.displayName = 'CommandList';
export const CommandEmpty = Primitive.Empty,
  CommandGroup = Primitive.Group;
export const CommandItem = React.forwardRef<React.ElementRef<typeof Primitive.Item>, React.ComponentPropsWithoutRef<typeof Primitive.Item>>(
  ({ className, ...props }, ref) => <Primitive.Item ref={ref} className={cn('ui-command-item', className)} {...props} />
);
CommandItem.displayName = 'CommandItem';
