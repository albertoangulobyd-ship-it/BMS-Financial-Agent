// TextMarquee de Aurora (components/ui/text-marquee.tsx, entrega del 28-10-2026): la ventana de
// la rueda y su pista, tal cual (translateY(height/2 - 24 - active*48), filas de 48 px). Cambios
// (especificacion §1.4), ninguno se ve:
// - la rueda del raton va con un listener nativo no pasivo (el onWheel de React es pasivo: la
//   pagina se desplazaba y la consola se quejaba);
// - deslizar el dedo arriba o abajo da un paso, como un gesto de la rueda: sin raton ni flechas
//   (el movil) ninguna entrada se queda sin alcanzar;
// - el nombre accesible (un grupo) sale del diccionario;
// - la ventana no se desplaza al recibir una entrada el foco (la pista ya la centra).
import { useEffect, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface Props {
  children: ReactNode[];
  speed?: number;
  className?: string;
  prefix?: ReactNode;
  height?: number;
  active?: number;
  onActive?: (i: number) => void;
  label: string;
}

/** Lo que tiene que moverse el dedo para dar un paso (px). */
const SWIPE_STEP = 28;

// Interactive adaptation: scrolling remains under the user's control.
export function TextMarquee({ children, className, prefix, height = 310, active = 0, onActive, label }: Props) {
  const last = useRef(0);
  const box = useRef<HTMLDivElement>(null);
  const current = useRef({ active, count: children.length, onActive });
  current.current = { active, count: children.length, onActive };

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const move = (delta: number) => {
      const { active: at, count, onActive: set } = current.current;
      set?.(Math.max(0, Math.min(count - 1, at + Math.sign(delta))));
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (Date.now() - last.current < 220) return;
      last.current = Date.now();
      move(e.deltaY);
    };
    // Un paso por gesto, como la rueda del raton.
    let startY: number | null = null;
    let stepped = false;
    const onTouchStart = (e: TouchEvent) => {
      startY = e.touches.length === 1 ? e.touches[0]!.clientY : null;
      stepped = false;
    };
    const onTouchMove = (e: TouchEvent) => {
      if (startY === null || e.touches.length !== 1) return;
      e.preventDefault();
      const dy = startY - e.touches[0]!.clientY;
      if (stepped || Math.abs(dy) < SWIPE_STEP) return;
      stepped = true;
      move(dy);
    };
    const onTouchEnd = () => {
      startY = null;
    };
    // El foco (Tab) desplaza la ventana para ensenar la entrada, y la pista ya la centra: sin
    // esto, las dos cosas juntas la sacaban del centro.
    const onScroll = () => {
      if (el.scrollTop !== 0) el.scrollTop = 0;
    };
    el.addEventListener('scroll', onScroll);
    el.addEventListener('wheel', onWheel, { passive: false });
    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    el.addEventListener('touchend', onTouchEnd);
    el.addEventListener('touchcancel', onTouchEnd);
    return () => {
      el.removeEventListener('scroll', onScroll);
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('touchend', onTouchEnd);
      el.removeEventListener('touchcancel', onTouchEnd);
    };
  }, []);

  return (
    <div
      ref={box}
      className={cn('marquee', className)}
      style={{ height }}
      onKeyDown={(e) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          onActive?.(Math.max(0, Math.min(children.length - 1, active + (e.key === 'ArrowDown' ? 1 : -1))));
        }
      }}
      tabIndex={0}
      role='group'
      aria-label={label}
    >
      {prefix}
      <div className='marquee-track' style={{ transform: `translateY(${height / 2 - 24 - active * 48}px)` }}>
        {children}
      </div>
    </div>
  );
}
