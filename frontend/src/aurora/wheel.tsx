// La rueda de Aurora (paso 16): la lista de secciones que gira alrededor de la entrada activa.
// Viene de text-marquee.tsx del prototipo tal cual, con el nombre accesible traducido: la rueda
// del raton y las flechas cambian la entrada activa. El siguiente paso la arregla como
// navegacion del inicio (decision 1: un clic abre la entrada, el dedo la mueve, Tab e Intro
// con el foco a la vista, todas las entradas sin tapar el saludo ni la caja).
import { useRef, type ReactNode } from 'react';
import { useT } from '@/i18n';
import { cn } from '@/lib/utils';

interface Props {
  children: ReactNode[];
  className?: string;
  prefix?: ReactNode;
  height?: number;
  /** La altura de cada entrada, en px. */
  itemHeight?: number;
  active?: number;
  onActive?: (index: number) => void;
}

export function Wheel({ children, className, prefix, height = 310, itemHeight = 48, active = 0, onActive }: Props) {
  const { t } = useT();
  const last = useRef(0);
  const clampIndex = (i: number) => Math.max(0, Math.min(children.length - 1, i));
  return (
    <div className='aurora-root'>
      <div
        className={cn('marquee', className)}
        style={{ height }}
        onWheel={(e) => {
          if (Date.now() - last.current < 220) return;
          last.current = Date.now();
          onActive?.(clampIndex(active + Math.sign(e.deltaY)));
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            onActive?.(clampIndex(active + (e.key === 'ArrowDown' ? 1 : -1)));
          }
        }}
        tabIndex={0}
        aria-label={t.aurora.wheel}
      >
        {prefix}
        <div className='marquee-track' style={{ transform: `translateY(${height / 2 - itemHeight / 2 - active * itemHeight}px)` }}>
          {children}
        </div>
      </div>
    </div>
  );
}
