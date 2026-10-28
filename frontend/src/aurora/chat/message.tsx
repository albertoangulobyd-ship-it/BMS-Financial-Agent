// Message de Aurora (components/ui/message.tsx, entrega del 28-10-2026), tal cual.
import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Message({ from, className, ...props }: HTMLAttributes<HTMLElement> & { from: 'user' | 'assistant' }) {
  return <article className={cn('chat-message', 'chat-message-' + from, className)} {...props} />;
}

export function MessageContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('message-content', className)} {...props} />;
}
