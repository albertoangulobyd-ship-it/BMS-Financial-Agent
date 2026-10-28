// Conversation de Aurora (components/ui/conversation.tsx, entrega del 28-10-2026), tal cual: la
// vista se queda abajo mientras se lee la respuesta y, cuando llega un resumen, se coloca al
// principio de el (-12 px). Cambio (I): el nombre accesible sale del diccionario.
import { useEffect, useRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Conversation({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={cn('conversation', className)} {...props} />;
}

export function ConversationContent({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement>(null),
    stick = useRef(true),
    shownSummary = useRef<Element | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) {
      const summary = el.querySelector('.chat-message:last-child .finance-bento');
      if (summary && summary !== shownSummary.current) {
        shownSummary.current = summary;
        el.scrollTop += summary.getBoundingClientRect().top - el.getBoundingClientRect().top - 12;
      } else el.scrollTop = el.scrollHeight;
    }
  }, [children]);
  return (
    <div
      ref={ref}
      className={cn('conversation-content', className)}
      onScroll={() => {
        const el = ref.current;
        if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 90;
      }}
      {...props}
    >
      {children}
    </div>
  );
}
