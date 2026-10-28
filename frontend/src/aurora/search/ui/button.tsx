// Button de Aurora (components/ui/button.tsx, entrega del 28-10-2026), tal cual: las clases
// ui-button-* de search-workspace.css.
import * as React from 'react';
import { Slot } from 'radix-ui';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva('ui-button', {
  variants: {
    variant: {
      default: 'ui-button-primary',
      outline: 'ui-button-outline',
      ghost: 'ui-button-ghost',
      secondary: 'ui-button-secondary',
      destructive: 'ui-button-danger',
      link: 'ui-button-link',
    },
    size: { default: 'ui-button-default', sm: 'ui-button-sm', lg: 'ui-button-lg', icon: 'ui-button-icon', xs: 'ui-button-xs' },
  },
  defaultVariants: { variant: 'default', size: 'default' },
});
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild = false, type = 'button', ...props }, ref) => {
  const Comp = asChild ? Slot.Root : 'button';
  return <Comp ref={ref} type={asChild ? undefined : type} className={cn(buttonVariants({ variant, size, className }))} {...props} />;
});
Button.displayName = 'Button';
