// La rueda de Aurora, arreglada (paso 16, decision 1): la navegacion del inicio. Las seis
// entradas se ven siempre y en su orden (en el prototipo se veian tres y dos quedaban tapadas
// por el saludo y la caja); la rueda mueve la entrada activa, que se ve grande y clara, y las
// demas se apagan y encogen segun lo lejos que estan, como en una rueda vista de frente. Al
// principio se probo una rueda que daba la vuelta (la activa siempre en el centro): el orden
// cambiaba al girar y "Procesar" salia encima de "Inicio"; asi se lee siempre igual. Lo que
// se arreglo del prototipo:
// - un clic o un toque en cualquier entrada la abre (en el prototipo, el primer clic solo la
//   centraba: al recibir el foco giraba, la entrada se iba de debajo del raton y el clic se
//   perdia). Aqui el foco con el raton o el dedo no gira nada;
// - la rueda del raton y las flechas giran; deslizar el dedo arriba o abajo tambien. Las
//   flechas dan la vuelta; la rueda del raton no: al llegar a un extremo, desplaza la pagina;
// - Tab llega a cada entrada (gira para ponerla en el centro), Intro la abre, el foco se ve;
// - nombres de verdad (la entrada es un boton con su nombre; la rueda, una navegacion con el
//   suyo y una frase que dice como se usa);
// - con "menos movimiento" gira sin animacion.
// El orden del DOM es el que se ve (el del tabulador).
import { useEffect, useId, useRef, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react';
import { cn } from '@/lib/utils';

export interface WheelEntry {
  id: string;
  label: string;
  /** La pagina donde se esta (aria-current). */
  current?: boolean;
}

interface Props {
  entries: readonly WheelEntry[];
  /** La entrada del centro. */
  active: number;
  onActive: (index: number) => void;
  onOpen: (index: number) => void;
  /** El nombre de la navegacion ("Hoofdmenu"). */
  label: string;
  /** Como se usa, para los lectores de pantalla. */
  description: string;
  /** La altura de cada fila, en px (mas baja en el movil). */
  row?: number;
  className?: string;
}

/** La altura de cada fila, en px. */
export const WHEEL_ROW = 46;

/** Lo lejos que esta una entrada de la activa (0 la activa; de 3 en adelante, igual). */
export function wheelDistance(index: number, active: number): number {
  return Math.min(Math.abs(index - active), 3);
}

/** Un paso de la rueda, dando la vuelta (de la ultima a la primera): las flechas y el dedo. */
export function wheelStep(active: number, step: number, count: number): number {
  return (((active + step) % count) + count) % count;
}

/** Un paso de la rueda del raton, sin dar la vuelta: null en la primera hacia arriba o en la
 *  ultima hacia abajo, y entonces el gesto es de la pagina (se desplaza hasta las tarjetas). */
export function wheelScrollStep(active: number, direction: number, count: number): number | null {
  const next = active + Math.sign(direction);
  return next < 0 || next >= count || direction === 0 ? null : next;
}

export function Wheel({ entries, active, onActive, onOpen, label, description, row = WHEEL_ROW, className }: Props) {
  const count = entries.length;
  const descId = useId();
  const navRef = useRef<HTMLElement>(null);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  // El foco que llega con el raton o el dedo no gira la rueda: el clic tiene que caer en la
  // entrada que se pulso.
  const pointerFocus = useRef(false);
  // Deslizar con el dedo: donde empezo y si ya giro (entonces el toque no abre nada).
  const swipe = useRef<{ id: number; y: number; from: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const live = useRef({ active, count, onActive });
  live.current = { active, count, onActive };

  // La rueda del raton: un paso por gesto, sin dar la vuelta. El listener es nativo y no
  // pasivo, para que la pagina no se desplace mientras la rueda gira; en la primera entrada
  // hacia arriba o en la ultima hacia abajo el gesto pasa a la pagina (revision del paso 16:
  // con el raton en el centro del inicio, la pagina no bajaba nunca a las tarjetas).
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    let acc = 0;
    let last = 0;
    const onWheel = (event: WheelEvent) => {
      const { active: current, count: n, onActive: set } = live.current;
      if (event.deltaY === 0 || wheelScrollStep(current, event.deltaY, n) === null) {
        acc = 0;
        return;
      }
      event.preventDefault();
      const now = performance.now();
      const delta = event.deltaMode === 1 ? event.deltaY * 40 : event.deltaY;
      if (now - last > 260) acc = 0;
      acc += delta;
      if (Math.abs(acc) < 30 || now - last < 160) return;
      last = now;
      const next = wheelScrollStep(current, acc, n);
      acc = 0;
      if (next === null) return;
      set(next);
      // Si el foco estaba en la rueda, va con la entrada del centro (Intro abre lo que se ve).
      if (nav.contains(document.activeElement)) buttons.current[next]?.focus({ preventScroll: true });
    };
    nav.addEventListener('wheel', onWheel, { passive: false });
    return () => nav.removeEventListener('wheel', onWheel);
  }, []);

  const focusEntry = (index: number) => {
    buttons.current[index]?.focus({ preventScroll: true });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    const at = buttons.current.findIndex((b) => b === document.activeElement);
    if (at < 0) return;
    let next: number | null = null;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = wheelStep(at, 1, count);
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = wheelStep(at, -1, count);
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = count - 1;
    if (next === null) return;
    event.preventDefault();
    focusEntry(next);
  };

  const onPointerDown = (event: PointerEvent<HTMLUListElement>) => {
    pointerFocus.current = true;
    // Un gesto nuevo: si el anterior fue deslizar y no dejo clic que tapar, este toque si abre.
    suppressClick.current = false;
    if (event.pointerType === 'mouse') return;
    swipe.current = { id: event.pointerId, y: event.clientY, from: active, moved: false };
  };
  const onPointerMove = (event: PointerEvent<HTMLUListElement>) => {
    const s = swipe.current;
    if (!s || s.id !== event.pointerId) return;
    const dy = s.y - event.clientY;
    if (!s.moved && Math.abs(dy) < 10) return;
    if (!s.moved) {
      s.moved = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }
    const steps = Math.round(dy / (row * 0.8));
    const next = wheelStep(s.from, steps, count);
    if (next !== live.current.active) onActive(next);
  };
  const onPointerEnd = (event: PointerEvent<HTMLUListElement>) => {
    const s = swipe.current;
    if (s && s.id === event.pointerId && s.moved) suppressClick.current = true;
    swipe.current = null;
    // El foco del raton ya llego (pointerdown); lo que venga despues es del teclado.
    window.setTimeout(() => (pointerFocus.current = false), 0);
  };


  return (
    <div className='aurora-root'>
      <nav ref={navRef} aria-label={label} aria-describedby={descId} className={cn('wheel', className)}>
        <p id={descId} className='sr-only'>
          {description}
        </p>
        <ul
          className='wheel-list'
          style={{ height: count * row, '--wheel-row': `${row}px` } as CSSProperties}
          onKeyDown={onKeyDown}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerEnd}
          onPointerCancel={onPointerEnd}
          onClickCapture={(event) => {
            if (!suppressClick.current) return;
            suppressClick.current = false;
            event.preventDefault();
            event.stopPropagation();
          }}
        >
          {entries.map((entry, i) => {
            const distance = wheelDistance(i, active);
            return (
              <li key={entry.id} className='wheel-slot'>
                <button
                  ref={(el) => {
                    buttons.current[i] = el;
                  }}
                  type='button'
                  data-wheel-entry={entry.id}
                  data-distance={distance}
                  aria-current={entry.current ? 'page' : undefined}
                  className={cn('wheel-item', distance === 0 && 'is-active')}
                  onFocus={() => {
                    if (!pointerFocus.current && live.current.active !== i) onActive(i);
                  }}
                  onClick={() => onOpen(i)}
                >
                  <span className='wheel-label'>{entry.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
