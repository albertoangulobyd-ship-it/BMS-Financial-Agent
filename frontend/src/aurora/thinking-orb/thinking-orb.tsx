// Los orbes de particulas "pensando" de Aurora (paso 16): salen solo mientras algo trabaja de
// verdad (buscar, leer) y se van al acabar. Vienen de thinking-orb.tsx y base-orb.tsx del
// prototipo; cambia: como mucho 30 imagenes por segundo (eran 45), el tema lo dice SOLO la
// clase .dark de la app (no el modo oscuro de Windows) y los textos accesibles vienen de los
// diccionarios. Ya se paraban con la ventana oculta, fuera de pantalla y con "menos
// movimiento" (entonces dibujan una sola imagen quieta).
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { cn } from '@/lib/utils';
import {
  clamp as clampRaw,
  presetFor as presetForRaw,
  renderOrbScene as renderOrbSceneRaw,
  renderers as renderersRaw,
  setupCanvasDpr as setupCanvasDprRaw,
} from './renderer';

export type ThinkingOrbMode = 'orbits' | 'globe' | 'rubik' | 'wave' | 'web' | 'braid' | 'ribbon' | 'ring' | 'morph';

// La frontera con el dibujo sin tipos (renderer.ts): estas firmas y nada mas.
type Scene = unknown;
interface Preset {
  speed: number;
  opts: unknown;
}
const setupCanvasDpr = setupCanvasDprRaw as (
  canvas: HTMLCanvasElement,
  width: number,
  height: number
) => { ctx: CanvasRenderingContext2D; w: number; h: number };
const clamp = clampRaw as (value: number) => number;
const presetFor = presetForRaw as (mode: ThinkingOrbMode, side: number) => Preset;
const renderers = renderersRaw as Record<ThinkingOrbMode, (side: number, time: number, opts: unknown) => Scene>;
const renderOrbScene = renderOrbSceneRaw as (ctx: CanvasRenderingContext2D, scene: Scene, dark: boolean) => void;

const FRAME_MS = 1000 / 30;

/** El tema que se pinta: la clase .dark en <html> (lib/theme.tsx). */
function useDarkTheme(): boolean {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));
  useEffect(() => {
    const root = document.documentElement;
    const check = () => setDark(root.classList.contains('dark'));
    const observer = new MutationObserver(check);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    check();
    return () => observer.disconnect();
  }, []);
  return dark;
}

export interface ThinkingOrbProps {
  /** Que dibujo: orbits (trabajando), globe (buscando), rubik (resolviendo)... */
  mode?: ThinkingOrbMode;
  /** El nombre accesible: lo que esta pasando ("Buscando"). */
  label: string;
  size?: number;
  speed?: number;
  scale?: number;
  className?: string;
  style?: CSSProperties;
}

export function ThinkingOrb({ mode = 'orbits', label, size = 240, speed = 1, scale = 0.72, className, style }: ThinkingOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rootRef = useRef<HTMLElement>(null);
  const dark = useDarkTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    const root = rootRef.current;
    if (!canvas || !root) return;
    let raf = 0;
    let disposed = false;
    let visible = true;
    let last = 0;
    let time = 0;
    let previous = performance.now();
    const media = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    const shouldAnimate = () => !disposed && visible && document.visibilityState === 'visible' && !(media?.matches ?? false);
    const draw = (now: number) => {
      raf = 0;
      if (disposed) return;
      const delta = (now - previous) * 0.001;
      previous = now;
      if (shouldAnimate()) time += delta * Math.max(Number(speed) || 1, 0.05);
      if (!last || now - last >= FRAME_MS - 1) {
        const box = canvas.getBoundingClientRect();
        const { ctx, w, h } = setupCanvasDpr(canvas, box.width || size, box.height || size);
        ctx.clearRect(0, 0, w, h);
        const side = Math.max(8, Math.min(w, h) * clamp(Number(scale) || 0.72));
        const preset = presetFor(mode, side);
        ctx.save();
        ctx.translate((w - side) / 2, (h - side) / 2);
        renderOrbScene(ctx, renderers[mode](side, shouldAnimate() ? time * preset.speed : 0.6 * preset.speed, preset.opts), dark);
        ctx.restore();
        last = now;
      }
      if (shouldAnimate()) raf = requestAnimationFrame(draw);
    };
    const trigger = () => {
      if (raf) cancelAnimationFrame(raf);
      previous = performance.now();
      last = 0;
      draw(previous);
    };
    const resize = new ResizeObserver(trigger);
    resize.observe(root);
    const intersection = new IntersectionObserver(
      ([entry]) => {
        visible = entry?.isIntersecting !== false;
        trigger();
      },
      { rootMargin: '100px', threshold: 0.01 }
    );
    intersection.observe(root);
    document.addEventListener('visibilitychange', trigger);
    media?.addEventListener('change', trigger);
    trigger();
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      resize.disconnect();
      intersection.disconnect();
      document.removeEventListener('visibilitychange', trigger);
      media?.removeEventListener('change', trigger);
    };
  }, [mode, scale, speed, dark, size]);

  return (
    <figure
      ref={rootRef}
      className={cn('thinking-orb', className)}
      style={{
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        isolation: 'isolate',
        userSelect: 'none',
        width: size,
        height: size,
        maxWidth: '100%',
        margin: 0,
        ...style,
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ display: 'block', maxWidth: '100%', maxHeight: '100%', width: `min(100%, ${size}px)`, height: 'auto', aspectRatio: '1 / 1' }}
        role='img'
        aria-label={label}
      />
    </figure>
  );
}
