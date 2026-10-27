// Cuando y con que ritmo se mueve el orbe (paso 16). Sin React y sin el navegador, para
// probarlo con un reloj falso (orb-loop.test.ts). Las reglas, de la revision de Aurora (§4.11):
// quieto en reposo; solo se mueve mientras el asistente trabaja; nunca con "menos movimiento",
// con la ventana oculta ni fuera de pantalla; y como mucho 30 imagenes por segundo. En el
// prototipo dibujaba 60 veces por segundo siempre: en un PC sin tarjeta grafica, unos dos
// nucleos en reposo.

export const MAX_FPS = 30;

/** Lo que decide si el orbe se mueve. */
export interface OrbGate {
  /** El asistente esta trabajando (buscando, leyendo...). */
  active: boolean;
  /** La ventana se ve (document.visibilityState === 'visible'). */
  visible: boolean;
  /** El orbe esta en pantalla (IntersectionObserver). */
  onScreen: boolean;
  /** La persona pidio menos movimiento en el sistema. */
  reducedMotion: boolean;
}

export function shouldAnimate(gate: OrbGate): boolean {
  return gate.active && gate.visible && gate.onScreen && !gate.reducedMotion;
}

export interface FrameScheduler {
  now: () => number;
  request: (callback: (time: number) => void) => number;
  cancel: (handle: number) => void;
}

export interface FrameLoop {
  /** Empieza a dibujar (si no lo hacia ya). */
  start: () => void;
  /** Para: no queda ningun cuadro pedido. */
  stop: () => void;
  readonly running: boolean;
  /** El tiempo animado acumulado, en ms: solo avanza mientras se mueve, asi al volver a
   *  moverse sigue donde estaba en lugar de saltar. */
  readonly elapsed: number;
}

/**
 * Un bucle de requestAnimationFrame que dibuja como mucho `fps` veces por segundo. `draw`
 * recibe el tiempo animado en ms. Parado no pide ningun cuadro: el coste en reposo es cero.
 */
export function createFrameLoop(
  draw: (elapsedMs: number) => void,
  scheduler: FrameScheduler,
  fps: number = MAX_FPS
): FrameLoop {
  const interval = 1000 / Math.min(Math.max(fps, 1), MAX_FPS);
  let handle: number | null = null;
  let elapsed = 0;
  let last = 0;
  let lastDraw = -Infinity;

  const tick = (time: number) => {
    handle = null;
    const now = Number.isFinite(time) ? time : scheduler.now();
    elapsed += Math.min(Math.max(now - last, 0), 100);
    last = now;
    // Un margen de 1 ms: con una pantalla a 60 Hz los cuadros llegan cada 16,7 ms y el de
    // 33,3 ms no tiene que esperar al siguiente.
    if (now - lastDraw >= interval - 1) {
      lastDraw = now;
      draw(elapsed);
    }
    handle = scheduler.request(tick);
  };

  return {
    start() {
      if (handle !== null) return;
      last = scheduler.now();
      lastDraw = -Infinity;
      handle = scheduler.request(tick);
    },
    stop() {
      if (handle !== null) scheduler.cancel(handle);
      handle = null;
    },
    get running() {
      return handle !== null;
    },
    get elapsed() {
      return elapsed;
    },
  };
}

/**
 * Un solo orbe por pantalla: el primero que se monta se queda el WebGL; otro que llegue
 * mientras tanto se pinta con el degradado fijo (sin lienzo). En el prototipo cada respuesta
 * del chat creaba otro orbe: con 20 preguntas habia 21 lienzos y el navegador perdio 5.
 */
export function createOrbRegistry() {
  let owner: symbol | null = null;
  return {
    claim(id: symbol): boolean {
      if (owner === null || owner === id) {
        owner = id;
        return true;
      }
      return false;
    },
    release(id: symbol): void {
      if (owner === id) owner = null;
    },
    get taken(): boolean {
      return owner !== null;
    },
  };
}

export const orbRegistry = createOrbRegistry();
