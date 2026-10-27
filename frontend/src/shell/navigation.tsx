// Donde se esta y como se vuelve (paso 16). Sustituye a las pestanas: hay un solo sitio a la
// vista, y un camino (`trail`) desde la vista de su seccion hasta la ficha abierta: una lista
// de Cuentas por cobrar, un cliente, una factura de ese cliente. Las migas lo ensenan y
// "Volver" quita el ultimo paso. Ir a otra entrada (la rueda, la navegacion compacta, una
// vista de la seccion) empieza un camino nuevo. Solo en memoria: no va a localStorage (los
// titulos son texto de documentos) y se pierde al salir.
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react';
import {
  HOME,
  RECORDS,
  isRecordId,
  isViewId,
  routeKey,
  sameRoute,
  sectionOf,
  viewRoute,
  type Route,
  type SectionId,
  type ViewId,
} from '@/screens/registry';

export interface NavValue {
  /** De la vista raiz a lo que se ve (al menos un paso). */
  trail: readonly Route[];
  current: Route;
  /** La seccion donde se esta (null: Ajustes). */
  section: SectionId | null;
  /** Una vista como raiz de un camino nuevo (una entrada, o otra vista de la seccion). */
  go: (view: ViewId) => void;
  /** Una ficha: un paso mas en el camino (si ya estaba en el, se vuelve a ella). Una vista: go. */
  open: (route: Route) => void;
  /** Una ficha desde fuera de su lista (Ctrl+K, la caja del inicio): su vista y la ficha. */
  openFrom: (view: ViewId, route: Route) => void;
  /** Quita el ultimo paso (en la raiz no hace nada). */
  back: () => void;
  /** Vuelve a un paso del camino (una miga). */
  backTo: (index: number) => void;
  /** El titulo de una ficha cuando ya se sabe (su numero, su nombre): para las migas. */
  setTitle: (key: string, title: string | undefined) => void;
  titleOf: (route: Route) => string | undefined;
  /** Sube con cada cambio de sitio (el marco lleva el foco y el desplazamiento). */
  moves: number;
  /** Lo que hizo el ultimo cambio: 'back' vuelve a donde estaba la pagina. */
  lastMove: 'start' | 'forward' | 'back';
}

const NavContext = createContext<NavValue | null>(null);

/** Donde se abre una ficha que llega sin lista (la vista de su tipo; una factura, por su sentido). */
export function defaultViewFor(route: Route, sentido?: 'entrante' | 'saliente' | null): ViewId {
  if (isViewId(route.screen)) return route.screen;
  if (route.screen === 'invoice' && sentido) return sentido === 'entrante' ? 'invoices-in' : 'invoices-out';
  return isRecordId(route.screen) ? RECORDS[route.screen].view : HOME;
}

interface NavState {
  trail: Route[];
  moves: number;
  lastMove: NavValue['lastMove'];
}

type NavAction =
  | { type: 'go'; view: ViewId }
  | { type: 'open'; route: Route }
  | { type: 'openFrom'; view: ViewId; route: Route }
  | { type: 'back' }
  | { type: 'backTo'; index: number };

/** El camino despues de un paso (sin React: lo prueba navigation.test.ts). */
export function nextTrail(trail: readonly Route[], action: NavAction): { trail: Route[]; lastMove: NavValue['lastMove'] } {
  switch (action.type) {
    case 'go':
      return { trail: [viewRoute(action.view)], lastMove: 'forward' };
    case 'open': {
      if (isViewId(action.route.screen)) return { trail: [viewRoute(action.route.screen)], lastMove: 'forward' };
      // Ya estaba en el camino (una factura, su cliente y otra vez la factura): se vuelve a
      // ella en vez de dar vueltas.
      const at = trail.findIndex((r) => sameRoute(r, action.route));
      if (at >= 0) return { trail: trail.slice(0, at + 1), lastMove: 'back' };
      return { trail: [...trail, action.route], lastMove: 'forward' };
    }
    case 'openFrom': {
      const root = viewRoute(action.view);
      return { trail: sameRoute(root, action.route) ? [root] : [root, action.route], lastMove: 'forward' };
    }
    case 'back':
      return { trail: trail.length > 1 ? trail.slice(0, -1) : [...trail], lastMove: 'back' };
    case 'backTo':
      return {
        trail: action.index >= 0 && action.index < trail.length - 1 ? trail.slice(0, action.index + 1) : [...trail],
        lastMove: 'back',
      };
  }
}

function reducer(state: NavState, action: NavAction): NavState {
  const next = nextTrail(state.trail, action);
  return { trail: next.trail, lastMove: next.lastMove, moves: state.moves + 1 };
}

export function NavigationProvider({ children, initial = HOME }: { children: ReactNode; initial?: ViewId }) {
  const [state, dispatch] = useReducer(reducer, undefined, () => ({ trail: [viewRoute(initial)], moves: 0, lastMove: 'start' as const }));
  const [titles, setTitles] = useState<ReadonlyMap<string, string>>(() => new Map());
  // Lo desplazada que estaba cada paso, para volver a el donde se dejo.
  const scrolls = useRef<number[]>([]);
  const depth = useRef(state.trail.length);
  depth.current = state.trail.length;

  const step = useCallback((action: NavAction) => {
    scrolls.current[depth.current - 1] = window.scrollY;
    dispatch(action);
  }, []);

  const go = useCallback((view: ViewId) => step({ type: 'go', view }), [step]);
  const open = useCallback((route: Route) => step({ type: 'open', route }), [step]);
  const openFrom = useCallback((view: ViewId, route: Route) => step({ type: 'openFrom', view, route }), [step]);
  const back = useCallback(() => step({ type: 'back' }), [step]);
  const backTo = useCallback((index: number) => step({ type: 'backTo', index }), [step]);

  const setTitle = useCallback((key: string, title: string | undefined) => {
    setTitles((prev) => {
      if (prev.get(key) === title) return prev;
      const next = new Map(prev);
      if (title === undefined) next.delete(key);
      else next.set(key, title);
      return next;
    });
  }, []);

  const titleOf = useCallback((route: Route) => titles.get(routeKey(route)), [titles]);

  const { trail, moves, lastMove } = state;

  // Ir adelante empieza arriba; al volver, la pagina donde se dejo. Lo que la pantalla vuelve a
  // leer puede tardar (con la maquina cargada, mas de un segundo): se reintenta mientras la
  // pagina aun no es tan alta, como mucho 4 s, y se deja en cuanto la persona mueve la pagina
  // (la rueda, el dedo, una tecla). Desde la revision del paso 16 la pagina se desplaza de
  // verdad (antes el cuerpo era overflow: hidden y esto no se notaba).
  useEffect(() => {
    if (moves === 0) return;
    if (lastMove !== 'back') {
      window.scrollTo(0, 0);
      return;
    }
    const target = scrolls.current[trail.length - 1] ?? 0;
    scrolls.current.length = trail.length;
    const deadline = performance.now() + 4000;
    let frame = 0;
    let moved = false;
    const stop = () => {
      moved = true;
    };
    const events = ['wheel', 'touchstart', 'keydown', 'mousedown'] as const;
    events.forEach((e) => window.addEventListener(e, stop, { passive: true, once: true }));
    const restore = () => {
      if (moved) return;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      window.scrollTo(0, Math.min(target, Math.max(0, max)));
      if (max < target && performance.now() < deadline) frame = window.requestAnimationFrame(restore);
    };
    restore();
    return () => {
      window.cancelAnimationFrame(frame);
      events.forEach((e) => window.removeEventListener(e, stop));
    };
  }, [moves, lastMove, trail.length]);

  const current = trail[trail.length - 1]!;
  const root = trail[0]!;
  const section = isViewId(root.screen) ? sectionOf(root.screen) : null;

  const value = useMemo<NavValue>(
    () => ({ trail, current, section, go, open, openFrom, back, backTo, setTitle, titleOf, moves, lastMove }),
    [trail, current, section, go, open, openFrom, back, backTo, setTitle, titleOf, moves, lastMove]
  );
  return <NavContext.Provider value={value}>{children}</NavContext.Provider>;
}

export function useNav(): NavValue {
  const value = useContext(NavContext);
  if (!value) throw new Error('useNav must be used within NavigationProvider');
  return value;
}
