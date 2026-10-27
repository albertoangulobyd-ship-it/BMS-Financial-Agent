// La conversacion de Aurora (paso 16): mensajes de la persona y del asistente, los puntos de
// "escribiendo", Detener y Copiar. Viene de ai-actions.tsx, conversation.tsx, message.tsx y
// actions.tsx del prototipo. Lo que se quita (revision §4.17 y §4.18, decision 15):
// - las respuestas fijas por palabras clave (useDemoConversation): aqui no hay ninguna
//   respuesta; quien la usa pone los mensajes. Hasta que exista el asistente local (un paso
//   posterior), la caja del inicio busca y lo dice;
// - "Regenerar", los pulgares y "Compartir conversacion" (descargaba un TXT sin auditoria);
// - el zorro y "Alberto": las iniciales de la persona que ha entrado;
// - un orbe WebGL por mensaje (21 lienzos con 20 preguntas): la marca fija del asistente.
// La conversacion vive solo en memoria (en el estado de quien la monta) y se borra con
// "Conversacion nueva". Todo texto se pinta como texto.
import { useEffect, useRef, useState, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from 'react';
import { Check, CopyIcon, RotateCcw, Square } from 'lucide-react';
import { AuroraMark } from '@/aurora/orb/aurora-orb';
import { useT } from '@/i18n';
import { initials } from '@/lib/format';
import { cn } from '@/lib/utils';
import './conversation.css';

export interface ChatMessage {
  id: string;
  from: 'user' | 'assistant';
  /** El texto (lo que copia "Copiar"). */
  content: string;
  /** Lo que se ve en lugar del texto, si hay algo mas que texto (una lista de resultados). */
  body?: ReactNode;
  /** La respuesta se corto con "Detener". */
  interrupted?: boolean;
}

export function Message({ from, className, ...props }: HTMLAttributes<HTMLElement> & { from: 'user' | 'assistant' }) {
  return <article className={cn('chat-message', 'chat-message-' + from, className)} {...props} />;
}

export function MessageContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('message-content', className)} {...props} />;
}

export function Actions({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('chat-actions', className)} {...props} />;
}

export function Action({ label, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <button type='button' title={label} aria-label={label} className={cn('chat-action', className)} {...props} />;
}

/** Los tres puntos de "escribiendo", quietos con "menos movimiento" (conversation.css). */
export function TypingDots({ label }: { label: string }) {
  return (
    <span className='typing-dots' role='status' aria-label={label}>
      <i />
      <i />
      <i />
    </span>
  );
}

/** La lista de mensajes, que se queda abajo mientras la persona no suba a leer. */
function ConversationContent({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [children]);
  return (
    <div
      ref={ref}
      className='conversation-content'
      onScroll={() => {
        const el = ref.current;
        if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 90;
      }}
    >
      {children}
    </div>
  );
}

export interface ConversationProps {
  messages: ChatMessage[];
  /** El asistente esta trabajando en la ultima respuesta. */
  pending: boolean;
  /** El nombre de quien ha entrado (/api/v2/yo), para su lado de la conversacion. */
  userName: string;
  onStop: () => void;
  onNewConversation: () => void;
}

export function Conversation({ messages, pending, userName, onStop, onNewConversation }: ConversationProps) {
  const { t } = useT();
  const texts = t.aurora.conversation;
  const [copied, setCopied] = useState('');
  const [notice, setNotice] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  function notify(text: string) {
    setNotice(text);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setNotice('');
      setCopied('');
    }, 2500);
  }

  async function copy(m: ChatMessage) {
    try {
      await navigator.clipboard.writeText(m.content);
      setCopied(m.id);
      notify(texts.copied);
    } catch {
      notify(texts.copyFailed);
    }
  }

  return (
    <div className='aurora-root'>
      <section className='conversation' aria-label={texts.label}>
        <div className='conversation-top'>
          <button type='button' onClick={onNewConversation}>
            <RotateCcw size={14} aria-hidden='true' /> {texts.newConversation}
          </button>
          <span>{t.aurora.name}</span>
        </div>
        <ConversationContent>
          {messages.map((m, i) => {
            const last = i === messages.length - 1;
            const working = pending && last && m.from === 'assistant';
            return (
              <Message from={m.from} key={m.id}>
                <div className='message-author'>
                  {m.from === 'assistant' ? (
                    <AuroraMark className={cn('chat-aura', working && 'speaking')} />
                  ) : (
                    <span className='chat-initials' aria-hidden='true'>
                      {initials(userName)}
                    </span>
                  )}
                  <span>{m.from === 'assistant' ? t.aurora.name : userName}</span>
                </div>
                <MessageContent>{m.body ?? (m.content || <TypingDots label={texts.thinking} />)}</MessageContent>
                {m.from === 'assistant' && m.content && !working && (
                  <>
                    <Actions>
                      <Action label={texts.copy} onClick={() => void copy(m)}>
                        {copied === m.id ? <Check size={14} aria-hidden='true' /> : <CopyIcon size={14} aria-hidden='true' />}
                      </Action>
                    </Actions>
                    {m.interrupted && <span className='chat-interrupted'>{texts.stopped}</span>}
                  </>
                )}
              </Message>
            );
          })}
        </ConversationContent>
        {pending && (
          <button type='button' className='chat-stop' onClick={onStop}>
            <Square size={10} aria-hidden='true' /> {texts.stop}
          </button>
        )}
        <div role='status' className='chat-notice' data-empty={notice ? undefined : true}>
          {notice}
        </div>
      </section>
    </div>
  );
}
