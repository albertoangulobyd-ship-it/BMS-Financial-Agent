// La conversacion de Aurora (components/ui/ai-actions.tsx, entrega del 28-10-2026): el mismo ritmo
// (tres puntos 650 ms como minimo, el texto de 4 en 4 caracteres cada 16 ms), las mismas
// acciones (Regenerar, Util, Poco util, Copiar, Compartir), "Detener respuesta", el aviso de
// 2,5 s y la tarjeta de exportar. Cambios (especificacion §2.5 y §4.1):
// - D: contesta el asistente local (aurora/assistant.ts), que lee /api/v2. Si la lectura tarda
//   mas de 650 ms, los puntos siguen hasta que contesta. Sus filas (E4-r) van con el estilo de
//   los resultados de la busqueda (.search-result) y abren su pantalla con el vuelo;
// - la persona sale con sus iniciales en el circulo .fox-avatar y con su nombre (no el zorro
//   ni "Alberto"); "Aurora • Demo" pasa a "Aurora";
// - I: todos los textos del diccionario;
// - A: el orbe de cada respuesta es una imagen con su nombre (role="img") y los tres puntos, un
//   estado (role="status"): una etiqueta sin papel no la lee nadie (axe, aria-prohibited-attr);
//   la respuesta terminada va tambien en un estado oculto, para que el lector de pantalla la diga.
import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Check, CopyIcon, Download, FileText, FolderOpen, RefreshCcwIcon, ShareIcon, SlidersHorizontal, Square, ThumbsDownIcon, ThumbsUpIcon } from 'lucide-react';
import { useT } from '@/i18n';
import { initials } from '@/lib/format';
import type { Answer, AnswerRow, AnswerTarget } from '../assistant';
import { FinanceBento } from '../finance/finance-bento';
import { SiriWave } from '../orb/siri-wave';
import { Action, Actions } from './actions';
import { Conversation, ConversationContent } from './conversation';
import { Message, MessageContent } from './message';
import './ai-actions.css';

export type ChatMessage = {
  id: string;
  from: 'user' | 'assistant';
  content: string;
  prompt?: string;
  feedback?: 'up' | 'down';
  interrupted?: boolean;
  /** Lo que trajo la respuesta ademas del texto (el resumen, las filas), al terminar de escribirse. */
  answer?: Answer;
};

/** useDemoConversation de Aurora con la respuesta del asistente (asincrona) en lugar de la fija. */
export function useConversation(answer: (prompt: string) => Promise<Answer>, texts: { failed: string; stopped: string }) {
  const words = useRef(texts);
  words.current = texts;
  const [messages, setMessages] = useState<ChatMessage[]>([]),
    [pending, setPending] = useState(false),
    timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined),
    serial = useRef(0),
    generation = useRef(0);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      generation.current += 1;
    },
    []
  );
  function stop() {
    clearTimeout(timer.current);
    generation.current += 1;
    setPending(false);
    setMessages((prev) =>
      prev.map((m, i) => (i === prev.length - 1 && m.from === 'assistant' ? { ...m, content: m.content || words.current.stopped, interrupted: true } : m))
    );
  }
  function generate(prompt: string, base: ChatMessage[]) {
    clearTimeout(timer.current);
    const mine = ++generation.current;
    const id = 'assistant-' + ++serial.current;
    setPending(true);
    setMessages([...base, { id, from: 'assistant', content: '', prompt }]);
    const started = performance.now();
    answer(prompt)
      .catch((): Answer => ({ text: words.current.failed }))
      .then((result) => {
        if (generation.current !== mine) return;
        timer.current = setTimeout(
          () => {
            const full = result.text;
            let cursor = 0;
            const tick = () => {
              cursor = Math.min(full.length, cursor + 4);
              setMessages((prev) =>
                prev.map((m) => (m.id === id ? { ...m, content: full.slice(0, cursor), answer: cursor === full.length ? result : undefined } : m))
              );
              if (cursor < full.length) timer.current = setTimeout(tick, 16);
              else setPending(false);
            };
            tick();
          },
          Math.max(0, 650 - (performance.now() - started))
        );
      });
  }
  function send(prompt: string) {
    if (!prompt.trim() || pending) return;
    generate(prompt, [...messages, { id: 'user-' + ++serial.current, from: 'user', content: prompt.trim() }]);
  }
  function retry(id: string) {
    if (pending) return;
    const at = messages.findIndex((m) => m.id === id),
      m = messages[at];
    if (m?.prompt) generate(m.prompt, messages.slice(0, at));
  }
  function feedback(id: string, value: 'up' | 'down') {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, feedback: m.feedback === value ? undefined : value } : m)));
  }
  function clear() {
    clearTimeout(timer.current);
    generation.current += 1;
    setMessages([]);
    setPending(false);
  }
  return { messages, pending, send, stop, retry, feedback, clear };
}

/** Una fila de la respuesta, con el estilo de los resultados de la busqueda. */
function AnswerRowLink({ row, onOpen }: { row: AnswerRow; onOpen: (target: AnswerTarget) => void }) {
  const open = () => onOpen(row.target);
  return (
    <a
      role='link'
      tabIndex={0}
      className='search-result'
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          open();
        }
      }}
    >
      <span className='result-file-icon'>{row.screen ? <FolderOpen size={19} /> : <FileText size={19} />}</span>
      <div className='result-info'>
        <strong data-proper-name={row.screen ? undefined : ''}>{row.label}</strong>
        {row.detail && <span data-proper-name={row.screen ? undefined : ''}>{row.detail}</span>}
      </div>
      <ArrowUpRight size={15} />
    </a>
  );
}

export function Example({
  messages,
  pending,
  user,
  onRetry,
  onFeedback,
  onBack,
  onStop,
  onOpen,
  onSearch,
  onOpenParty,
}: {
  messages: ChatMessage[];
  pending: boolean;
  /** El nombre de quien escribe. */
  user: string;
  onRetry: (id: string) => void;
  onFeedback: (id: string, value: 'up' | 'down') => void;
  onBack: () => void;
  onStop: () => void;
  onOpen: (target: AnswerTarget) => void;
  onSearch: (query: string) => void;
  onOpenParty: (party: { id: number; type: 'clientes' | 'proveedores' } | null) => void;
}) {
  const { t } = useT();
  const c = t.aurora.chat;
  const [copied, setCopied] = useState(''),
    [notice, setNotice] = useState(''),
    [exportOpen, setExportOpen] = useState(false),
    noticeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(noticeTimer.current), []);
  function notify(text: string) {
    setNotice(text);
    clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => {
      setNotice('');
      setCopied('');
    }, 2500);
  }
  async function copy(m: ChatMessage) {
    try {
      await navigator.clipboard.writeText(m.content);
      setCopied(m.id);
      notify(c.copied);
    } catch {
      notify(c.copyFailed);
    }
  }
  function exportChat() {
    const body = c.exportTitle + '\n\n' + messages.map((m) => (m.from === 'user' ? user : t.aurora.name) + ':\n' + m.content).join('\n\n'),
      url = URL.createObjectURL(new Blob([body], { type: 'text/plain;charset=utf-8' })),
      a = document.createElement('a');
    a.href = url;
    a.download = c.exportFile;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setExportOpen(false);
    notify(c.exported);
  }
  return (
    <Conversation aria-label={c.label}>
      <div className='conversation-top'>
        <button onClick={onBack}>
          <ArrowLeft size={14} /> {c.back}
        </button>
        <span>{t.aurora.name}</span>
      </div>
      <ConversationContent>
        {messages.map((m, i) => (
          <Message from={m.from} key={m.id}>
            <div className='message-author'>
              {m.from === 'assistant' ? (
                <div className={'chat-aura ' + (pending && i === messages.length - 1 ? 'speaking' : '')} role='img' aria-label={pending && i === messages.length - 1 ? c.answering : t.aurora.name}>
                  <SiriWave size={120} renderScale={1} flowPhase={pending ? 1.2 : 0} />
                </div>
              ) : (
                <div className='fox-avatar' role='img' aria-label={user}>
                  <span aria-hidden='true'>{initials(user)}</span>
                </div>
              )}
              <span data-proper-name={m.from === 'user' ? '' : undefined}>{m.from === 'assistant' ? t.aurora.name : user}</span>
            </div>
            <MessageContent>
              {m.answer?.summary ? (
                <>
                  <span className='summary-intro'>{c.summaryIntro}</span>
                  <FinanceBento summary={m.answer.summary} onOpenParty={onOpenParty} />
                </>
              ) : (
                m.content || (
                  <span className='typing-dots' role='status' aria-label={c.thinking}>
                    <i />
                    <i />
                    <i />
                  </span>
                )
              )}
            </MessageContent>
            {m.answer?.rows && (
              <div className='chat-rows'>
                {m.answer.rows.map((row) => (
                  <AnswerRowLink key={row.key} row={row} onOpen={onOpen} />
                ))}
                {m.answer.search && (
                  <button className='filters-toggle chat-search' onClick={() => onSearch(m.answer!.search!)}>
                    <SlidersHorizontal size={14} /> {c.withFilters}
                  </button>
                )}
              </div>
            )}
            {m.from === 'assistant' && m.content && !(pending && i === messages.length - 1) && (
              <>
                <Actions>
                  <Action label={c.regenerate} disabled={pending} onClick={() => onRetry(m.id)}>
                    <RefreshCcwIcon size={14} />
                  </Action>
                  <Action
                    label={c.useful}
                    aria-pressed={m.feedback === 'up'}
                    onClick={() => {
                      onFeedback(m.id, 'up');
                      notify(c.feedbackSaved);
                    }}
                  >
                    <ThumbsUpIcon size={14} />
                  </Action>
                  <Action
                    label={c.notUseful}
                    aria-pressed={m.feedback === 'down'}
                    onClick={() => {
                      onFeedback(m.id, 'down');
                      notify(c.feedbackSaved);
                    }}
                  >
                    <ThumbsDownIcon size={14} />
                  </Action>
                  <Action label={c.copy} onClick={() => copy(m)}>
                    {copied === m.id ? <Check size={14} /> : <CopyIcon size={14} />}
                  </Action>
                  <Action label={c.share} onClick={() => setExportOpen((v) => !v)}>
                    <ShareIcon size={14} />
                  </Action>
                </Actions>
                {m.interrupted && <span className='chat-interrupted'>{c.stopped}</span>}
              </>
            )}
          </Message>
        ))}
      </ConversationContent>
      {/* La respuesta terminada, para el lector de pantalla: el texto llega de 4 en 4 caracteres
          y no se lee mientras tanto (A). */}
      <p className='sr-only' role='status'>
        {!pending && messages.at(-1)?.from === 'assistant' ? messages.at(-1)!.content : ''}
      </p>
      {pending && (
        <button className='chat-stop' onClick={onStop}>
          <Square size={10} /> {c.stop}
        </button>
      )}
      {notice && (
        <div role='status' className='chat-notice'>
          {notice}
        </div>
      )}
      {exportOpen && (
        <div className='chat-export'>
          <p>{c.exportText}</p>
          <button onClick={exportChat}>
            <Download size={13} /> {c.exportDownload}
          </button>
          <button onClick={() => setExportOpen(false)}>{t.common.cancel}</button>
        </div>
      )}
    </Conversation>
  );
}
