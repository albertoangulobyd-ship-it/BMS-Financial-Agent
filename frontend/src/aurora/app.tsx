// App de Aurora (main.tsx:23-41 del dueno, entrega del 28-10-2026): el inicio y todo lo que pasa
// en su espacio central, con la misma composicion, las mismas clases y los mismos cambios:
// el saludo, el orbe (la onda o, con Procesar en el centro o pensando, el orbe de particulas),
// "Presiona para navegar", la rueda, el panel, la conversacion, la busqueda y la caja.
// Cambios permitidos (especificacion §4.2):
// - B: la entrada (L0) es este mismo inicio: el saludo pide el codigo, la caja lo recoge y el
//   idioma va donde ira "Presiona para navegar"; al entrar cambia el saludo (0,3 s) y nada mas;
// - B: ocho entradas en la rueda (§1.4); con un panel abierto la rueda se oculta y `active` no
//   se mueve (§1.1); al apoyar el raton en una fila pasa lo de Aurora (la activa va a ella) y el
//   clic abre esa fila aunque se suelte sobre otra;
// - D: la conversacion la contesta el asistente local; la busqueda va a /api/v2/buscar;
// - R: Documentos se abre con el vuelo del orbe (root.tsx);
// - D: Procesar (processMode, main.tsx:23,40) es la lectura de verdad (processing/); como en
//   Aurora, el saludo dice su titulo, no hay orbe ni caja y el espacio central es suyo;
// - I: todos los textos del diccionario.
// El estado vive en aurora/estado.ts: cada clic es una accion.
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ArrowUp } from 'lucide-react';
import { LANGS, fmt, useT, type Lang, type Messages } from '@/i18n';
import { ApiError, type InvoiceRow } from '@/lib/api';
import { useCan, useSession } from '@/lib/session';
import { useTheme } from '@/lib/theme';
import { answerQuestion, type AnswerTarget } from './assistant';
import { Example as AiActions, useConversation } from './chat/ai-actions';
import { WorkspaceComposer } from './composer';
import { DOCS_ROOT, ENTRIES, LAST_ENTRY, entryIndex, flowPhase, folderPlace, invoicePlace, isPanelEntry, visibleEntries, type EntryId } from './estado';
import { BmsLogo } from './logo';
import { SiriWave } from './orb/siri-wave';
import { PanelFor } from './panels';
import { firstName } from './panels/panel-model';
import { introView, type ProcessView } from './processing/process-texts';
import { captureProcessingEntry } from './processing/processing-entry';
import { ProcessingWorkspace } from './processing/processing-workspace';
import { useAurora } from './root';
import { SearchWorkspace } from './search/search-workspace';
import { TextMarquee } from './text-marquee';
import { OrbWorking } from './thinking-orb/orb-working';

/** El nombre de cada entrada de la rueda, en el idioma de la persona. */
export function entryLabel(t: Messages, id: EntryId): string {
  switch (id) {
    case 'settings':
      return t.nav.settings.label;
    case 'search':
      return t.aurora.home.searchEntry;
    default:
      return t.areas[id].label;
  }
}

// Lo que se guarda es la clave del texto, no el texto: al cambiar de idioma, cambia.
type LoginMessage = 'empty' | 'invalid' | 'forbidden' | 'incompatible' | 'unreachable' | 'sessionEnded' | 'loggedOut' | null;

function loginError(error: unknown): LoginMessage {
  if (error instanceof ApiError) {
    if (error.kind === 'unauthorized') return 'invalid';
    if (error.kind === 'forbidden') return 'forbidden';
    if (error.kind === 'incompatible') return 'incompatible';
  }
  return 'unreachable';
}

/** La entrada (L0) con el codigo personal. Sin <form> ni type=password (Edge y Chromium
 *  ofrecerian guardarlo): un campo de texto con los caracteres tapados, Intro para entrar y el
 *  campo vaciado antes de comprobarlo. El codigo vive solo en la memoria de la sesion. */
function useLogin() {
  const { login, notice } = useSession();
  const [token, setToken] = useState('');
  const [error, setError] = useState<LoginMessage>(null);
  const [busy, setBusy] = useState(false);
  const submit = useCallback(async () => {
    if (busy) return;
    const value = token.trim();
    if (!value) {
      setError('empty');
      return;
    }
    setToken('');
    setBusy(true);
    setError(null);
    try {
      await login(value);
    } catch (e) {
      setError(loginError(e));
    } finally {
      setBusy(false);
    }
  }, [busy, token, login]);
  const message: LoginMessage = error ?? notice;
  return { token, setToken, submit, busy, message };
}

function LoginComposer({ login }: { login: ReturnType<typeof useLogin> }) {
  const { t } = useT();
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
  }, [login.message]);
  return (
    <div className='composer workspace-composer'>
      <div className='input-row'>
        <span className='aura-slot' aria-hidden='true' />
        <input
          id='token'
          ref={input}
          className='token-input'
          type='text'
          autoComplete='one-time-code'
          autoCapitalize='off'
          autoCorrect='off'
          spellCheck={false}
          data-lpignore='true'
          data-1p-ignore='true'
          value={login.token}
          placeholder={t.aurora.login.placeholder}
          aria-label={t.aurora.login.placeholder}
          aria-describedby='login-line'
          onChange={(e) => login.setToken(e.target.value)}
          onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void login.submit();
            }
          }}
        />
        <button id='login-submit' className='send' type='button' disabled={login.busy} aria-label={t.aurora.login.submit} onClick={() => void login.submit()}>
          <span className='composer-glyph'>
            <ArrowUp size={19} />
          </span>
        </button>
      </div>
    </div>
  );
}

/** El idioma en la entrada, donde ira "Presiona para navegar": cada uno en su idioma. */
function LanguageLine() {
  const { t, lang, setLang } = useT();
  const names: Record<Lang, string> = { es: t.language.esLong, nl: t.language.nlLong, en: t.language.enLong };
  const order: Lang[] = ['es', 'nl', 'en'];
  return (
    <div className='discreet discreet-languages' role='group' aria-label={t.language.label}>
      {order
        .filter((code) => LANGS.includes(code))
        .map((code, i) => (
          <span key={code}>
            {i > 0 && ' · '}
            <button type='button' lang={code} aria-pressed={lang === code} onClick={() => setLang(code)}>
              {names[code]}
            </button>
          </span>
        ))}
    </div>
  );
}

/** El titulo de Procesar en el saludo; el nombre del acceso directo (en castellano en los tres
 *  idiomas, como en el disco) va como nombre propio, y en castellano para el lector de pantalla. */
function ProcessTitle({ view }: { view: ProcessView }) {
  const { lang } = useT();
  const name = view.properName;
  const at = name ? view.title.indexOf(name) : -1;
  if (!name || at < 0) return <>{view.title}</>;
  return (
    <>
      {view.title.slice(0, at)}
      <span data-proper-name='' lang={lang === 'es' ? undefined : 'es'}>
        {name}
      </span>
      {view.title.slice(at + name.length)}
    </>
  );
}

export function App() {
  const { t } = useT();
  // Con "menos movimiento", lo que mueve motion (el saludo, el orbe de particulas y la onda)
  // cambia sin moverse: el CSS de Aurora para las animaciones de CSS no le llega.
  const reduced = useReducedMotion();
  const { resolved } = useTheme();
  const { session } = useSession();
  const can = useCan();
  const { state, dispatch, go } = useAurora();
  const { open, active, panel, chatting, searchMode, processMode, text } = state;
  const [searchThinking, setSearchThinking] = useState(false);
  const [processView, setProcessView] = useState<ProcessView>(() => introView('ready', null, t));
  const wheelTime = useRef(0);
  // La fila de la rueda donde se apoyo el raton (§1.4): al apoyarlo, la activa pasa a ella (el
  // onFocus de Aurora, main.tsx:32) y la pista se desliza; el clic abre esa fila aunque se suelte
  // sobre otra o sobre la pista.
  const pressed = useRef<number | null>(null);
  const loginState = useLogin();
  const api = session?.api;
  const chat = useConversation(
    useCallback(
      (prompt: string) => {
        if (!api) return Promise.reject(new Error('sin sesion'));
        return answerQuestion(prompt, { api, t, can });
      },
      [api, t, can]
    ),
    { failed: t.aurora.chat.failed, stopped: t.aurora.chat.stoppedText }
  );
  const { clear: clearChat } = chat;

  // Al entrar o salir alguien, sin conversacion (el estado lo vuelve a E0 o L0 Root).
  const person = session ? `${session.environment}:${session.me.id}` : null;
  const lastPerson = useRef(person);
  useEffect(() => {
    if (lastPerson.current === person) return;
    lastPerson.current = person;
    clearChat();
  }, [person, clearChat]);

  const loggedIn = session !== null;
  // Sin permiso para importar, Procesar no esta en la rueda (es la ultima: los indices siguen).
  const entries = visibleEntries(can);
  const conversation = chat.messages.length > 0;

  /** Procesar (main.tsx:23, enter(4)): antes de cambiar, las particulas del orbe y los sitios del
   *  saludo y del orbe (captureProcessingEntry); el saludo empieza por el de la intro. */
  function enterProcess(index?: number) {
    captureProcessingEntry();
    setProcessView(introView('ready', null, t));
    dispatch({ type: 'enterProcess', index });
  }

  function enter(i: number) {
    const id = ENTRIES[i]!;
    if (isPanelEntry(i)) {
      dispatch({ type: 'enterPanel', index: i });
      return;
    }
    if (id === 'search') {
      dispatch({ type: 'enterSearch', index: i });
      return;
    }
    // Documentos: la pantalla de trabajo, con el vuelo del orbe (root.tsx). Procesar: aqui mismo.
    if (id === 'documents') go({ type: 'enterDocuments', place: DOCS_ROOT, index: i });
    if (id === 'process') enterProcess(i);
  }

  function orbClick() {
    if (!loggedIn) return;
    // Con Procesar en el centro (y sin panel), el orbe entra en Procesar (main.tsx:30).
    if (panel === null && open && active === LAST_ENTRY) {
      enter(LAST_ENTRY);
      return;
    }
    if (chatting || panel !== null) clearChat();
    dispatch({ type: 'orb' });
  }

  // Alt+← y el boton "atras" del raton: la salida visible de cada estado (§1.6). En un panel, lo
  // hace el panel (como Escape: lo de dentro primero); en Procesar y en Documentos, los suyos.
  const back = useRef<() => boolean>(() => false);
  back.current = () => {
    if (!loggedIn || panel !== null || processMode) return false;
    if (conversation) {
      clearChat();
      dispatch({ type: 'backToSpace' });
      return true;
    }
    if (open || chatting || searchMode) {
      clearChat();
      dispatch({ type: 'orb' });
      return true;
    }
    return false;
  };
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (!e.altKey || e.ctrlKey || e.key !== 'ArrowLeft' || e.defaultPrevented) return;
      if (back.current()) e.preventDefault();
    };
    const onMouse = (e: MouseEvent) => {
      if (e.button === 3 && back.current()) e.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mouseup', onMouse);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mouseup', onMouse);
    };
  }, []);

  function send(e: FormEvent) {
    e.preventDefault();
    if (!text.trim() || chat.pending) return;
    chat.send(text);
    dispatch({ type: 'send' });
  }

  /** Una fila de la respuesta: su panel (con la vista de su grupo), la busqueda con sus filtros,
   *  Documentos o Procesar, en un solo cambio (F9). */
  function openTarget(target: AnswerTarget) {
    clearChat();
    if (target.kind === 'panel') dispatch({ type: 'enterFromConversation', index: entryIndex(target.entry), view: target.view ?? null });
    else if (target.kind === 'search') dispatch({ type: 'enterSearch', index: entryIndex('search'), preset: target.preset });
    else if (target.kind === 'documents') go({ type: 'enterDocuments', place: target.place });
    else enterProcess();
  }

  /** Un resultado de la busqueda: la hoja de la factura en su carpeta (F3). */
  function openInvoice(invoice: InvoiceRow) {
    go({ type: 'enterDocuments', place: invoicePlace(invoice) });
  }

  function openParty(party: { id: number; type: 'clientes' | 'proveedores' } | null) {
    clearChat();
    go({ type: 'enterDocuments', place: party ? folderPlace(party.type === 'clientes' ? 'client' : 'provider', party.id) : DOCS_ROOT });
  }

  const name = session ? firstName(session.me.nombre) : '';
  const greeting = fmt(t.aurora.home.greeting, { name: '\u0000' }).split('\u0000');
  const message = loginState.message;
  const loginLine = message
    ? message === 'sessionEnded'
      ? t.aurora.login.expired
      : message === 'loggedOut'
        ? t.login.loggedOut
        : t.login[message]
    : t.aurora.login.prompt;
  const welcomeKey = !loggedIn ? `login:${message ?? ''}` : processMode ? `process:${processView.title}` : searchMode ? 'search' : 'welcome';
  const highlight = active === LAST_ENTRY && open && panel === null;
  // El nombre del orbe dice lo que hace su clic (orbClick y la accion 'orb'): volver al inicio
  // desde un panel, la busqueda o la caja; entrar en Procesar si esta en el centro; si no, abrir
  // o cerrar la rueda. No cambia nada a la vista.
  const orbLabel =
    panel !== null || searchMode || chatting
      ? t.aurora.home.backHome
      : highlight
        ? fmt(t.aurora.home.openWhat, { what: entryLabel(t, 'process') })
        : open
          ? t.aurora.home.close
          : t.aurora.home.open;

  return (
    <div
      className={
        'app ' +
        (open ? 'navigating ' : '') +
        (panel !== null ? 'has-panel ' : '') +
        (chatting ? 'chatting ' : '') +
        (searchMode ? 'search-mode ' : '') +
        (searchThinking ? 'thinking-active ' : '') +
        (processMode ? 'process-mode ' : '') +
        (conversation ? 'conversation-mode ' : '') +
        (highlight ? 'process-highlight' : '')
      }
      data-active={ENTRIES[active]}
    >
      <BmsLogo />
      <main
        onWheel={(e) => {
          // Con un panel, la rueda escondida no manda (§1.1, cambio 2).
          if (panel !== null) return;
          if (!open || chatting || (e.target as HTMLElement).closest('.panel, .composer-area, .marquee')) return;
          const now = Date.now();
          if (now - wheelTime.current < 240 || Math.abs(e.deltaY) < 8) return;
          wheelTime.current = now;
          dispatch({ type: 'step', delta: e.deltaY, last: entries.length - 1 });
        }}
      >
        {conversation && (
          <AiActions
            messages={chat.messages}
            pending={chat.pending}
            user={session?.me.nombre ?? ''}
            onRetry={chat.retry}
            onFeedback={chat.feedback}
            onStop={chat.stop}
            onBack={() => {
              clearChat();
              dispatch({ type: 'backToSpace' });
            }}
            onOpen={openTarget}
            onSearch={(q) => {
              clearChat();
              dispatch({ type: 'enterSearch', index: entryIndex('search'), preset: { texto: q } });
            }}
            onOpenParty={openParty}
          />
        )}
        <section className='stage' aria-label={t.aurora.home.stage}>
          {!chatting && (
            <div className='welcome-line'>
              <AnimatePresence mode='wait' initial={false}>
                <motion.div
                  key={welcomeKey}
                  initial={reduced ? false : { opacity: 0, y: 7 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduced ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, y: -7 }}
                >
                  <h1>
                    {!loggedIn ? (
                      t.aurora.login.welcome
                    ) : processMode ? (
                      <ProcessTitle view={processView} />
                    ) : searchMode ? (
                      t.aurora.home.searchTitle
                    ) : (
                      <>
                        {greeting[0]}
                        <strong data-proper-name=''>{name}</strong>
                        {greeting[1]}
                      </>
                    )}
                  </h1>
                  <p
                    id={!loggedIn ? 'login-line' : undefined}
                    role={(!loggedIn && message && message !== 'loggedOut') || (processMode && processView.alert) ? 'alert' : undefined}
                  >
                    {!loggedIn
                      ? loginLine
                      : processMode
                        ? processView.detail
                        : searchMode
                          ? searchThinking
                            ? t.aurora.home.searchThinking
                            : t.aurora.home.searchIntro
                          : t.aurora.home.intro}
                  </p>
                </motion.div>
              </AnimatePresence>
            </div>
          )}
          {!processMode && (
          <button
            className={'aurora' + (loggedIn ? '' : ' aurora-locked')}
            aria-label={orbLabel}
            aria-hidden={loggedIn ? undefined : true}
            tabIndex={loggedIn ? undefined : -1}
            onClick={orbClick}
          >
            <motion.span className='aurora-shared'>
              <AnimatePresence initial={false}>
                {searchThinking || (open && active === LAST_ENTRY && panel === null) ? (
                  <motion.span
                    key='orb'
                    className='hero-orb'
                    initial={reduced ? false : { opacity: 0, scale: 0.35, rotate: -25 }}
                    animate={{ opacity: 1, scale: 1, rotate: 0 }}
                    exit={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.65 }}
                    transition={reduced ? { duration: 0 } : { duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
                  >
                    {/* En Aurora, 'ink' (solo hay tema oscuro); en el claro (T), 'paper'. */}
                    <OrbWorking surface={resolved === 'dark' ? 'ink' : 'paper'} size={240} scale={0.72} caption={t.aurora.orb} summary={t.aurora.orbWorking} />
                  </motion.span>
                ) : (
                  <motion.span
                    key='wave'
                    className='hero-wave'
                    initial={reduced ? false : { opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.55 }}
                    transition={{ duration: reduced ? 0 : 0.65 }}
                  >
                    <SiriWave size={440} renderScale={1} variant='wave' flowPhase={flowPhase(active)} />
                  </motion.span>
                )}
              </AnimatePresence>
            </motion.span>
          </button>
          )}
          {!loggedIn && !chatting && <LanguageLine />}
          {loggedIn && !open && !chatting && !searchMode && !processMode && (
            <button className='discreet' onClick={() => dispatch({ type: 'openMenu' })}>
              {t.aurora.home.navigate}
            </button>
          )}
          {loggedIn && open && !chatting && (
            <section
              className='navigation'
              aria-label={t.aurora.home.sections}
              onMouseDownCapture={() => {
                pressed.current = null;
              }}
              onClick={(e) => {
                // Soltado sobre otra fila o sobre la pista (se ha deslizado): la de antes.
                const at = pressed.current;
                if (at === null || e.detail === 0 || (e.target as Element).closest('.nav-item')) return;
                pressed.current = null;
                enter(at);
              }}
            >
              <TextMarquee
                active={active}
                onActive={(i) => dispatch({ type: 'focusEntry', index: i })}
                onEnter={enter}
                height={240}
                label={t.aurora.home.marquee}
              >
                {entries.map((id, i) => (
                  <button
                    key={id}
                    className={'nav-item ' + (active === i ? 'selected' : '')}
                    aria-current={active === i ? 'true' : undefined}
                    data-entry={id}
                    onFocus={() => dispatch({ type: 'focusEntry', index: i })}
                    // Al apoyar el raton, lo de Aurora (onFocus, main.tsx:32): la activa pasa a
                    // esta fila, la pista se desliza y, con Procesar, sale el orbe de particulas
                    // (del que captureProcessingEntry toma las particulas y los sitios). Sin mover
                    // el foco: no se ve y la ventana no se desplaza.
                    onMouseDown={(e) => {
                      e.preventDefault();
                      if (e.button !== 0) return;
                      pressed.current = i;
                      dispatch({ type: 'focusEntry', index: i });
                    }}
                    // El clic abre la fila donde se apoyo (§1.4); con el teclado, esta.
                    onClick={(e) => {
                      const at = e.detail > 0 && pressed.current !== null ? pressed.current : i;
                      pressed.current = null;
                      enter(at);
                    }}
                  >
                    <span>{entryLabel(t, id)}</span>
                  </button>
                ))}
              </TextMarquee>
            </section>
          )}
        </section>
        {loggedIn && panel !== null && <PanelFor entry={ENTRIES[panel]!} />}
        {/* Procesar, para el lector de pantalla: cada estado y cada etapa (el saludo cambia de
            golpe, con su clave). Siempre montado, para que se oiga el primero. */}
        <p className='sr-only' role='status'>
          {processMode ? `${processView.title} ${processView.detail}` : ''}
        </p>
        <section className='composer-area'>
          {!loggedIn ? (
            <LoginComposer login={loginState} />
          ) : processMode ? (
            <ProcessingWorkspace
              embedded
              onViewChange={setProcessView}
              onBack={() => dispatch({ type: 'leaveProcess' })}
              // F5: sin vuelo (en Aurora, location.hash; aqui no hay orbe del que salir).
              onDocuments={() => dispatch({ type: 'enterDocuments', place: DOCS_ROOT })}
              onOpenInvoice={(row) => dispatch({ type: 'enterDocuments', place: invoicePlace({ id: row.factura_id }) })}
              onQueue={() => dispatch({ type: 'processToQueue' })}
            />
          ) : searchMode ? (
            <SearchWorkspace preset={state.search} onSearchingChange={setSearchThinking} onOpenInvoice={openInvoice} />
          ) : (
            <WorkspaceComposer
              value={text}
              onValueChange={(value) => dispatch({ type: 'text', value })}
              onSubmit={send}
              disabled={!text.trim() || chat.pending}
            />
          )}
        </section>
      </main>
    </div>
  );
}
