// Root de Aurora (main.tsx:42-46 del dueno, entrega del 28-10-2026): el cambio de pantalla y el
// vuelo del orbe. La pantalla que entra se monta enseguida y la que sale se funde encima en
// 0,18 s (AnimatePresence mode="sync"); al ir a Documentos una copia de la onda vuela del centro de
// .aurora al orbe pequeno de la esquina, 1,05 s con cubic-bezier(.4,0,.15,1), y al volver hace
// el camino inverso. Cambios (especificacion §4.2):
// - R: sin direcciones. La pantalla es estado de la app (aurora/estado.ts) y el vuelo se dispara
//   igual que captureNavigation, con cada accion de "ir a una pantalla" o "volver al inicio";
// - B: la pantalla que sale no recibe clics mientras se funde (la rueda que se va, §1.1);
// - M: sin vuelo con "menos movimiento" (useReducedMotion, como Aurora).
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useSession } from '@/lib/session';
// Las hojas en el orden de main.tsx del dueno: styles.css antes que las de las piezas (la
// conversacion, el resumen, la busqueda) y workspace-layout.css despues; el tema claro, al final.
import './styles.css';
import { App } from './app';
import { DocumentWorkspace } from './documents/document-workspace';
import { INITIAL_STATE, auroraReducer, type AuroraAction, type AuroraState } from './estado';
import { SiriWave } from './orb/siri-wave';
import './workspace-layout.css';
// Procesar: las reglas de .process-mode que Aurora lleva despues de workspace-layout.css.
import './processing/meerkat-scene.css';
import './bms.css';
import './claro.css';

interface AuroraValue {
  state: AuroraState;
  /** Un cambio de estado sin vuelo. */
  dispatch: (action: AuroraAction) => void;
  /** Un cambio de estado; si cambia de pantalla (inicio <-> trabajo), con el vuelo del orbe. */
  go: (action: AuroraAction) => void;
}

const AuroraContext = createContext<AuroraValue | null>(null);

export function useAurora(): AuroraValue {
  const value = useContext(AuroraContext);
  if (!value) throw new Error('useAurora must be used within Root');
  return value;
}

type FlightPoint = { x: number; y: number; scale: number };
type AuroraFlight = { id: number; destination: 'home' | 'documents'; from: FlightPoint; to?: FlightPoint };

export function Root() {
  const reduced = useReducedMotion();
  const { session } = useSession();
  const [state, dispatch] = useReducer(auroraReducer, INITIAL_STATE);
  // Al entrar o salir alguien (tambien una sesion que caduca en una pantalla de trabajo): al
  // inicio, con la rueda en su posicion inicial (§1.4). Sin sesion no hay pantalla de trabajo.
  const person = session ? `${session.environment}:${session.me.id}` : null;
  const lastPerson = useRef(person);
  useEffect(() => {
    if (lastPerson.current === person) return;
    lastPerson.current = person;
    dispatch({ type: 'reset' });
  }, [person]);
  const shown = session ? state.screen : 'home';
  const [flight, setFlight] = useState<AuroraFlight | null>(null);
  const flightSequence = useRef(0);
  const screen = useRef(state.screen);
  screen.current = state.screen;

  // captureNavigation (main.tsx:44): el origen es el centro de .aurora (al ir) o del lienzo del
  // orbe pequeno (al volver); el destino se mide cuando la pantalla nueva ya esta montada.
  const go = useCallback(
    (action: AuroraAction) => {
      const leaving = screen.current;
      const destination =
        leaving === 'home' && action.type === 'enterDocuments'
          ? 'documents'
          : leaving === 'work' && action.type === 'home'
            ? 'home'
            : null;
      if (destination && !reduced) {
        const source = document.querySelector(destination === 'home' ? '.ws-companion canvas' : '.aurora')?.getBoundingClientRect();
        if (source) {
          setFlight({
            id: ++flightSequence.current,
            destination,
            from: { x: source.x + source.width / 2 - 220, y: source.y + source.height / 2 - 220, scale: source.width / 440 },
          });
        }
      }
      dispatch(action);
    },
    [reduced]
  );

  useLayoutEffect(() => {
    if (!flight || flight.to) return;
    const arrived = flight.destination === 'documents' ? state.screen === 'work' : state.screen === 'home';
    if (!arrived) return;
    window.scrollTo(0, 0);
    const target = document.querySelector(flight.destination === 'documents' ? '.ws-companion' : '.aurora')?.getBoundingClientRect();
    if (target)
      setFlight((current) =>
        current?.id === flight.id
          ? {
              ...current,
              to: {
                x: target.x + target.width / 2 - 220,
                y: target.y + target.height / 2 - 220,
                scale: flight.destination === 'documents' ? 180 / 440 : target.width / 440,
              },
            }
          : current
      );
    else setFlight(null);
  }, [state.screen, state.workSeq, flight]);

  // El vuelo es solo una imagen: si su animacion no llega a avisar del final (otra la corta, la
  // ventana estaba oculta), se quita igual al acabar su tiempo, y nunca se queda en pantalla.
  const flightId = flight?.id;
  useEffect(() => {
    if (flightId === undefined) return;
    const timer = setTimeout(() => setFlight((current) => (current?.id === flightId ? null : current)), 1050 + 650);
    return () => clearTimeout(timer);
  }, [flightId]);

  const value = useMemo(() => ({ state, dispatch, go }), [state, go]);
  const key = shown;
  return (
    <AuroraContext.Provider value={value}>
      <div
        className={flight ? 'aurora-route-moving aurora-route-to-' + flight.destination : ''}
        data-screen={key}
        data-aurora-root=''
      >
        <AnimatePresence mode='sync' initial={false}>
          <motion.div
            className='app-screen'
            key={key}
            data-screen={key}
            initial={{ opacity: 1 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, position: 'absolute', top: 0, width: '100%' }}
            transition={{ duration: reduced ? 0 : 0.18 }}
          >
            {/* El inicio que se va se funde con lo que tenia (main.tsx:46: en Aurora su estado es
                suyo): el estado va dentro de la pantalla, y AnimatePresence guarda la que sale
                tal como estaba. Asi Procesar o la rueda se funden, en lugar de verse el inicio. */}
            {shown !== 'work' ? (
              <AuroraContext.Provider value={value}>
                <App />
              </AuroraContext.Provider>
            ) : (
              <DocumentWorkspace key={state.workSeq} place={state.work.place} />
            )}
          </motion.div>
        </AnimatePresence>
        {flight && (
          <motion.div
            key={flight.id}
            className='aurora-route-flight'
            aria-hidden
            initial={flight.from}
            animate={flight.to ?? flight.from}
            transition={{ duration: 1.05, ease: [0.4, 0, 0.15, 1] }}
            onAnimationComplete={() => {
              if (flight.to) setFlight((current) => (current?.id === flight.id ? null : current));
            }}
          >
            <SiriWave size={440} renderScale={1} />
          </motion.div>
        )}
      </div>
    </AuroraContext.Provider>
  );
}
