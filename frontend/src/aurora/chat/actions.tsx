// Actions de Aurora (components/ui/actions.tsx, entrega del 28-10-2026), tal cual.
import type { ButtonHTMLAttributes, HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Actions({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('chat-actions', className)} {...props} />;
}

export function Action({ label, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <button type='button' title={label} aria-label={label} className={cn('chat-action', className)} {...props} />;
}
