// El orbe de Aurora: la onda de colores de su inicio, que es el asistente (paso 16). Viene de
// siri-wave.tsx del prototipo (WebGL, un triangulo que cubre el lienzo y un sombreador), con
// las reglas de la revision (§4.11 y decision 16):
// - quieto en reposo: dibuja UNA imagen y no pide ningun cuadro mas;
// - se mueve solo con `active` (el asistente trabaja), a 30 imagenes por segundo como mucho;
// - nunca con "menos movimiento", con la ventana oculta ni fuera de pantalla;
// - uno por pantalla (orbRegistry): otro que llegue a la vez sale como el degradado fijo;
// - sin WebGL (o si el sombreador no compila), un degradado fijo con CSS, sin lienzo.
// La logica de cuando se mueve esta en orb-loop.ts y se prueba sin navegador.
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { createFrameLoop, orbRegistry, shouldAnimate, type OrbGate } from './orb-loop';
import { VERTEX_SHADER, WAVE_SHADER } from './wave-shader';
import './aurora-orb.css';

export interface AuroraOrbProps {
  /** El nombre accesible ("Aurora"). */
  label: string;
  /** El lado del cuadrado, en px CSS. */
  size?: number;
  /** El asistente esta trabajando: el orbe se mueve. En reposo, quieto. */
  active?: boolean;
  /** Verde al terminar algo bien (el "hecho" de Procesar). */
  tone?: 'aurora' | 'success';
  /** Cambia el punto de la onda sin girar el lienzo (la rueda lo movia con la entrada activa). */
  flowPhase?: number;
  className?: string;
}

/** La imagen de reposo: el instante en que la onda es la del inicio de Aurora (oro arriba,
 *  cian en medio y violeta abajo; se eligio mirando la onda de 0 a 12 s). */
const REST_MS = 800;

interface GlState {
  gl: WebGLRenderingContext;
  program: WebGLProgram;
  shaders: WebGLShader[];
  buffer: WebGLBuffer | null;
  uniforms: {
    resolution: WebGLUniformLocation | null;
    time: WebGLUniformLocation | null;
    flow: WebGLUniformLocation | null;
    purple: WebGLUniformLocation | null;
    green: WebGLUniformLocation | null;
  };
}

function setupGl(canvas: HTMLCanvasElement): GlState | null {
  let gl: WebGLRenderingContext | null = null;
  try {
    gl = canvas.getContext('webgl', {
      alpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: true,
      preserveDrawingBuffer: false,
      powerPreference: 'low-power',
    });
  } catch {
    gl = null;
  }
  if (!gl) return null;
  const shaders: WebGLShader[] = [];
  const compile = (type: number, source: string): WebGLShader | null => {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      gl.deleteShader(shader);
      return null;
    }
    shaders.push(shader);
    return shader;
  };
  const vs = compile(gl.VERTEX_SHADER, VERTEX_SHADER);
  const fs = compile(gl.FRAGMENT_SHADER, WAVE_SHADER);
  const program = gl.createProgram();
  if (!vs || !fs || !program) {
    shaders.forEach((s) => gl.deleteShader(s));
    return null;
  }
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program);
    shaders.forEach((s) => gl.deleteShader(s));
    return null;
  }
  gl.useProgram(program);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, 'aPos');
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  return {
    gl,
    program,
    shaders,
    buffer,
    uniforms: {
      resolution: gl.getUniformLocation(program, 'iResolution'),
      time: gl.getUniformLocation(program, 'iTime'),
      flow: gl.getUniformLocation(program, 'iFlowPhase'),
      purple: gl.getUniformLocation(program, 'iPurple'),
      green: gl.getUniformLocation(program, 'iGreen'),
    },
  };
}

function disposeGl(state: GlState): void {
  const { gl } = state;
  gl.deleteProgram(state.program);
  state.shaders.forEach((s) => gl.deleteShader(s));
  if (state.buffer) gl.deleteBuffer(state.buffer);
  // El contexto no se pierde a mano (loseContext): con React en modo estricto el mismo lienzo
  // se vuelve a montar y se quedaria sin WebGL. Con un solo orbe por pantalla, el navegador
  // recoge los lienzos que ya no estan.
}

function reducedMotionQuery(): MediaQueryList | null {
  return typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
}

export function AuroraOrb({ label, size = 160, active = false, tone = 'aurora', flowPhase = 0, className }: AuroraOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rootRef = useRef<HTMLSpanElement>(null);
  const [mode, setMode] = useState<'webgl' | 'fallback'>('webgl');
  // Lo que cambia sin volver a montar el lienzo: lo lee el bucle en cada imagen.
  const live = useRef({ active, tone, flowPhase });
  live.current = { active, tone, flowPhase };
  const update = useRef<(() => void) | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const root = rootRef.current;
    if (!canvas || !root) return;
    const id = Symbol('aurora-orb');
    if (!orbRegistry.claim(id)) {
      setMode('fallback');
      return;
    }
    const state = setupGl(canvas);
    if (!state) {
      orbRegistry.release(id);
      setMode('fallback');
      return;
    }
    const { gl, uniforms } = state;
    const pixels = Math.max(1, Math.round(size * Math.min(window.devicePixelRatio || 1, 2)));
    canvas.width = pixels;
    canvas.height = pixels;
    gl.viewport(0, 0, pixels, pixels);

    const paint = (elapsedMs: number) => {
      const { tone: currentTone, flowPhase: flow } = live.current;
      gl.uniform2f(uniforms.resolution, pixels, pixels);
      gl.uniform1f(uniforms.time, (REST_MS + elapsedMs) / 1000);
      gl.uniform1f(uniforms.flow, flow);
      gl.uniform1f(uniforms.purple, 0);
      gl.uniform1f(uniforms.green, currentTone === 'success' ? 1 : 0);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const loop = createFrameLoop(paint, {
      now: () => performance.now(),
      request: (cb) => window.requestAnimationFrame(cb),
      cancel: (h) => window.cancelAnimationFrame(h),
    });
    const motion = reducedMotionQuery();
    const gate: OrbGate = {
      active: live.current.active,
      visible: document.visibilityState === 'visible',
      onScreen: true,
      reducedMotion: motion?.matches ?? false,
    };

    // Cada cambio de lo que decide: moverse, o parar y dejar UNA imagen quieta.
    const apply = () => {
      gate.active = live.current.active;
      if (shouldAnimate(gate)) {
        loop.start();
        root.dataset.moving = 'true';
      } else {
        loop.stop();
        paint(loop.elapsed);
        root.dataset.moving = 'false';
      }
    };
    update.current = apply;

    const onVisibility = () => {
      gate.visible = document.visibilityState === 'visible';
      apply();
    };
    const onMotion = () => {
      gate.reducedMotion = motion?.matches ?? false;
      apply();
    };
    const observer =
      typeof IntersectionObserver === 'function'
        ? new IntersectionObserver((entries) => {
            gate.onScreen = entries.some((e) => e.isIntersecting);
            apply();
          })
        : null;
    observer?.observe(root);
    document.addEventListener('visibilitychange', onVisibility);
    motion?.addEventListener('change', onMotion);
    const onLost = (event: Event) => {
      event.preventDefault();
      loop.stop();
      setMode('fallback');
    };
    canvas.addEventListener('webglcontextlost', onLost);
    apply();

    return () => {
      update.current = null;
      loop.stop();
      observer?.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
      motion?.removeEventListener('change', onMotion);
      canvas.removeEventListener('webglcontextlost', onLost);
      disposeGl(state);
      orbRegistry.release(id);
    };
  }, [size]);

  // active, tone o la fase cambian: el bucle decide (sin volver a crear el lienzo).
  useEffect(() => {
    update.current?.();
  }, [active, tone, flowPhase]);

  return (
    <span
      ref={rootRef}
      role='img'
      aria-label={label}
      data-orb={mode}
      data-moving='false'
      className={cn('aurora-orb', tone === 'success' && 'aurora-orb--success', className)}
      style={{ width: size, height: size }}
    >
      {mode === 'webgl' ? (
        <canvas ref={canvasRef} className='aurora-orb__canvas' aria-hidden='true' style={{ width: size, height: size }} />
      ) : (
        <span className='aurora-orb__fallback' aria-hidden='true' />
      )}
    </span>
  );
}

/** La marca pequena del asistente (junto a sus mensajes, en la navegacion compacta): el mismo
 *  degradado que el orbe sin WebGL, sin lienzo y sin movimiento. */
export function AuroraMark({ className, label }: { className?: string; label?: string }) {
  return (
    <span
      className={cn('aurora-orb aurora-orb--mark', className)}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <span className='aurora-orb__fallback' aria-hidden='true' />
    </span>
  );
}
