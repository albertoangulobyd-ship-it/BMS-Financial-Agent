// La suricata de los estados vacios (paso 16): asoma de la madriguera, mira a los lados y se
// queda quieta vigilando. Es la de Aurora (decision 16: la suricata es la lectura de facturas
// y los estados vacios; el orbe, el asistente). Del prototipo cambia:
// - las tiras blancas aprobadas (sprites.ts); las negras de meerkat-scene no se pintaban nunca;
// - una sola entrada de unos 2,5 s y despues QUIETA: nada se mueve en reposo; con "menos
//   movimiento", con la ventana oculta o fuera de pantalla, directamente la pose quieta;
// - cuadros con setTimeout al ritmo de la tira (unos 6 por segundo), no un bucle de 60;
// - en el tema claro se pinta en negro (filtro en meerkat-scene.css), en el oscuro en blanco;
// - el texto accesible viene de los diccionarios.
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { ANCHOR_X, ANCHOR_Y, FRAME_HEIGHT, FRAME_WIDTH, SPRITES, type SpriteName } from './sprites';
import './meerkat-scene.css';

type Step = [SpriteName, number, number];

// [tira, cuadro, ms que dura]: sale cavando, mira a un lado y a otro, y vigila.
const ENTRANCE: Step[] = [
  ['emerge-dig', 0, 180],
  ['emerge-dig', 1, 160],
  ['emerge-dig', 2, 100],
  ['emerge-dig', 3, 100],
  ['emerge-dig', 4, 140],
  ['emerge-dig', 5, 170],
  ['emerge-dig', 6, 240],
  ['emerge-dig', 7, 180],
  ['emerge-search', 2, 180],
  ['emerge-search', 3, 240],
  ['emerge-search', 4, 240],
  ['emerge-search', 5, 360],
  ['guard-head', 0, 0],
];
const REST: Step = ['guard-head', 0, 0];

function loadImages(): Promise<Partial<Record<SpriteName, HTMLImageElement>>> {
  const names: SpriteName[] = ['emerge-dig', 'emerge-search', 'guard-head'];
  return Promise.all(
    names.map(
      (name) =>
        new Promise<[SpriteName, HTMLImageElement]>((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve([name, img]);
          img.onerror = () => reject(new Error(name));
          img.src = SPRITES[name];
        })
    )
  ).then((entries) => Object.fromEntries(entries));
}

export interface MeerkatSceneProps {
  /** Lo que dice a un lector de pantalla. */
  label: string;
  /** El aumento de los pixeles (la tira es de 76 x 47). */
  scale?: 2 | 3 | 4;
  className?: string;
}

export function MeerkatScene({ label, scale = 3, className }: MeerkatSceneProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    canvas.width = FRAME_WIDTH * scale;
    canvas.height = FRAME_HEIGHT * scale + scale;
    const draw = (images: Partial<Record<SpriteName, HTMLImageElement>>, [name, frame]: Step) => {
      const img = images[name];
      if (!img) return;
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, frame * FRAME_WIDTH, 0, FRAME_WIDTH, FRAME_HEIGHT, 0, 0, FRAME_WIDTH * scale, FRAME_HEIGHT * scale);
      // El suelo, del color de la tira (blanco: el filtro del tema claro lo pasa a negro).
      ctx.fillStyle = '#ffffff';
      ctx.fillRect((ANCHOR_X - 30) * scale, ANCHOR_Y * scale, 60 * scale, Math.max(1, Math.round(scale / 2)));
    };
    const calm = () =>
      document.visibilityState !== 'visible' ||
      (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    loadImages()
      .then((images) => {
        if (disposed) return;
        if (calm()) {
          draw(images, REST);
          return;
        }
        let index = 0;
        const next = () => {
          const step = ENTRANCE[index] ?? REST;
          draw(images, step);
          index += 1;
          if (!disposed && index < ENTRANCE.length && step[2] > 0) timer = setTimeout(next, step[2]);
        };
        next();
      })
      .catch(() => {
        if (!disposed) setFailed(true);
      });
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [scale]);

  return (
    <span className={cn('meerkat-scene', className)}>
      {failed ? null : (
        <canvas
          ref={canvasRef}
          className='meerkat-scene__canvas'
          role='img'
          aria-label={label}
          style={{ width: FRAME_WIDTH * scale, height: FRAME_HEIGHT * scale + scale }}
        />
      )}
    </span>
  );
}
