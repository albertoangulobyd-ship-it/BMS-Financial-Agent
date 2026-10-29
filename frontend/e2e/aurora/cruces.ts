// Los tiempos de Aurora (especificacion §6.2): el port de herramientas/cruces.py y de
// herramientas/curvas-teoricas.py. Una transicion se mide por los instantes en que el cambio pasa
// por el 5, el 50 y el 95 % de su recorrido (en una curva que se pasa del final, la primera vez), y
// se comparan dos intervalos, 5 → 50 y 5 → 95, con los de la curva del codigo:
// (u50 − u5) × duracion y (u95 − u5) × duracion. Sin dependencias de las pruebas: lo usan
// aurora-tiempos.spec.ts con la app y herramientas/tiempos-aurora.mts con el prototipo del dueno
// (la misma medida, primero contra Aurora).
//
// La medida es en la linea de tiempo de la animacion del navegador (CSS o la de WAAPI que pone
// motion): se para, se lleva a cada instante (de 5 en 5 ms) y se lee lo que se mueve. Un cuadro
// lento de esta maquina (la onda en WebGL por software) no cambia la curva.

/** Una curva: cubic-bezier(x1, y1, x2, y2), 1 − (1 − t)³ o lineal. */
export type Curve = readonly [number, number, number, number] | 'cubic-out' | 'linear';

/** Las curvas del codigo de Aurora (la tabla de §6.2). */
export const CURVES = {
  orb: [0.22, 0.8, 0.2, 1],
  track: [0.2, 0.8, 0.2, 1],
  particles: [0.16, 1, 0.3, 1],
  flight: [0.4, 0, 0.15, 1],
  ease: [0.25, 0.1, 0.25, 1],
  easeOut: [0, 0, 0.58, 1],
  /** easeInOut de motion: la de un `transition` con duracion y sin `ease`. */
  easeInOut: [0.42, 0, 0.58, 1],
  /** La de motion para `opacity` sin `transition`. */
  motionOpacity: [0.25, 0.1, 0.35, 1],
  folder: [0.22, 1, 0.36, 1],
  hinge: [0.34, 1.36, 0.5, 1],
  flow: [0.19, 1, 0.22, 1],
  bento: [0.32, 0.72, 0, 1],
} as const satisfies Record<string, Curve>;

function bezier([x1, y1, x2, y2]: readonly [number, number, number, number]): (x: number) => number {
  const cx = (t: number) => 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3;
  const cy = (t: number) => 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3;
  return (x) => {
    let lo = 0,
      hi = 1;
    for (let i = 0; i < 60; i += 1) {
      const m = (lo + hi) / 2;
      if (cx(m) < x) lo = m;
      else hi = m;
    }
    return cy((lo + hi) / 2);
  };
}

/** Las fracciones de la duracion en que la curva llega al 5, 50 y 95 % (la primera vez). */
export function fractions(curve: Curve): { u5: number; u50: number; u95: number } {
  const f = curve === 'linear' ? (x: number) => x : curve === 'cubic-out' ? (x: number) => 1 - (1 - x) ** 3 : bezier(curve);
  const cross = (level: number) => {
    const n = 20000;
    for (let i = 0; i <= n; i += 1) if (f(i / n) >= level) return i / n;
    return 1;
  };
  return { u5: cross(0.05), u50: cross(0.5), u95: cross(0.95) };
}

/** Los dos intervalos que se esperan de una curva con su duracion (ms). */
export function theory(curve: Curve, duration: number): { to50: number; to95: number } {
  const { u5, u50, u95 } = fractions(curve);
  return { to50: (u50 - u5) * duration, to95: (u95 - u5) * duration };
}

/** Una curva medida: [t en ms, valor]. */
export type Series = [number, number][];

/** Los instantes en que el cambio pasa por el 5, 50 y 95 % (y el hueco entre las muestras). */
export function crossings(s: Series): Record<'p5' | 'p50' | 'p95', { t: number; gap: number }> | null {
  if (s.length < 2) return null;
  const v0 = s[0]![1];
  const v1 = s[s.length - 1]![1];
  const d = v1 - v0;
  if (Math.abs(d) < 1e-6) return null;
  const at = (level: number) => {
    const target = v0 + d * level;
    for (let i = 1; i < s.length; i += 1) {
      const [ta, va] = s[i - 1]!;
      const [tb, vb] = s[i]!;
      if ((va - target) * (vb - target) <= 0 && va !== vb) return { t: ta + ((target - va) / (vb - va)) * (tb - ta), gap: tb - ta };
    }
    return null;
  };
  const p5 = at(0.05);
  const p50 = at(0.5);
  const p95 = at(0.95);
  return p5 && p50 && p95 ? { p5, p50, p95 } : null;
}

/** Los dos intervalos medidos de una curva (null si no cruza). */
export function measured(s: Series): { to50: number; to95: number; gap: number } | null {
  const c = crossings(s);
  if (!c) return null;
  return { to50: c.p50.t - c.p5.t, to95: c.p95.t - c.p5.t, gap: Math.max(c.p5.gap, c.p50.gap, c.p95.gap) };
}

/** Lo que falla de una curva medida contra la teorica: ±10 % o una muestra (§6.2). */
export function curveErrors(what: string, want: { to50: number; to95: number }, s: Series): string[] {
  const m = measured(s);
  if (!m) return [`${what}: la curva no cruza el 5, el 50 y el 95 % (de ${s[0]?.[1]} a ${s[s.length - 1]?.[1]})`];
  const out: string[] = [];
  if (Math.abs(m.to50 - want.to50) > Math.max(want.to50 * 0.1, m.gap)) out.push(`${what}: 5→50 ${m.to50.toFixed(0)} ms (teorico ${want.to50.toFixed(0)})`);
  if (Math.abs(m.to95 - want.to95) > Math.max(want.to95 * 0.1, m.gap)) out.push(`${what}: 5→95 ${m.to95.toFixed(0)} ms (teorico ${want.to95.toFixed(0)})`);
  return out;
}

/** Que se lee en cada instante. */
export type Measure = 'cx' | 'cy' | 'x' | 'y' | 'w' | 'h' | 'opacity' | 'scale' | 'rotateX' | 'color' | 'background' | `var:${string}`;

/** Una animacion del navegador de un elemento: la de esa duracion (ms) y, si se dice, la de esa
 *  propiedad (una transicion de CSS o una de WAAPI con esa propiedad en sus fotogramas) o la de ese
 *  nombre (una animacion de CSS). `nth`: el n-esimo elemento del selector (sin el, el primero que
 *  la tenga). */
export interface SeekSpec {
  selector: string;
  /** La duracion (ms); 0: cualquiera (un muelle de motion, cuya duracion sale de su fisica), y se
   *  recorre la que tenga. */
  duration: number;
  property?: string;
  name?: string;
  nth?: number;
  measure: Measure;
  /** De cuanto en cuanto (ms); 5 por defecto. */
  step?: number;
}

/** Lo que se encuentra de la animacion (para decir que no esta). */
export interface Found {
  series: Series;
  delay: number;
  easing: string;
  iterations: number;
  duration: number;
}

/**
 * Dentro de la pagina: espera (cuadro a cuadro, `timeout` ms como mucho) a que el elemento tenga
 * la animacion, la para con las del mismo elemento que empezaron a la vez, las lleva a cada
 * instante de su duracion y lee la medida; despues las deja donde estaban y siguen. Va tal cual a
 * page.evaluate: todo lo que usa esta dentro (en la app, la CSP no deja evaluar texto).
 */
export async function seekWhenRunning(spec: SeekSpec & { timeout?: number }): Promise<Found | null> {
  const matches = (a: Animation) => {
    const timing = a.effect?.getTiming();
    if (!timing || (spec.duration > 0 && Math.round(Number(timing.duration)) !== spec.duration)) return false;
    if (spec.name && (a as CSSAnimation).animationName !== spec.name) return false;
    if (spec.property) {
      const tp = (a as CSSTransition).transitionProperty;
      if (tp !== undefined) return tp === spec.property;
      return (a.effect as KeyframeEffect).getKeyframes().some((f) => spec.property! in f);
    }
    return true;
  };
  // El n-esimo del selector o, sin `nth`, el primero que tenga la animacion.
  const find = (): { el: Element; anim: Animation; all: Animation[] } | null => {
    const els = Array.from(document.querySelectorAll(spec.selector));
    for (const el of spec.nth === undefined ? els : els.slice(spec.nth, spec.nth + 1)) {
      const all = el.getAnimations();
      const anim = all.find(matches);
      if (anim) return { el, anim, all };
    }
    return null;
  };
  const deadline = performance.now() + (spec.timeout ?? 4000);
  let hit = find();
  while (!hit && performance.now() < deadline) {
    await new Promise((r) => requestAnimationFrame(r));
    hit = find();
  }
  if (!hit) return null;
  const { el, anim, all } = hit;
  const timing = anim.effect!.getTiming();
  const delay = Number(timing.delay ?? 0);
  const was = all.map((a) => ({ a, t: a.currentTime, playing: a.playState === 'running' }));
  const start = anim.startTime;
  const together = all.filter((a) => a === anim || (start !== null && a.startTime !== null && Math.abs(Number(a.startTime) - Number(start)) < 1));
  all.forEach((a) => a.pause());
  const read = (): number => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    // Los tres canales y el alfa (de 0 a 255): de transparente a negro tambien es un cambio.
    const rgb = (v: string) => {
      const n = (v.match(/[\d.]+/g) ?? []).map(Number);
      return (n[0] ?? 0) + (n[1] ?? 0) + (n[2] ?? 0) + (n.length > 3 ? n[3]! : 1) * 255;
    };
    switch (spec.measure) {
      case 'cx':
        return r.x + r.width / 2;
      case 'cy':
        return r.y + r.height / 2;
      case 'x':
        return r.x;
      case 'y':
        return r.y;
      case 'w':
        return r.width;
      case 'h':
        return r.height;
      case 'opacity':
        return parseFloat(cs.opacity);
      case 'scale': {
        if (cs.transform === 'none') return cs.scale && cs.scale !== 'none' ? parseFloat(cs.scale) : 1;
        const m = /matrix\(([-\d.e]+),\s*([-\d.e]+)/.exec(cs.transform);
        return m ? Math.hypot(Number(m[1]), Number(m[2])) : 1;
      }
      case 'rotateX': {
        // matrix3d(…): la segunda columna es (0, cos, sin, …) tambien con perspectiva delante.
        const v = /matrix3d\(([^)]*)\)/.exec(cs.transform)?.[1]?.split(',').map(Number);
        return v ? (Math.atan2(v[6]!, v[5]!) * 180) / Math.PI : 0;
      }
      case 'color':
        return rgb(cs.color);
      case 'background':
        return rgb(cs.backgroundColor);
      default:
        return parseFloat(cs.getPropertyValue(spec.measure.slice(4)));
    }
  };
  const series: [number, number][] = [];
  const step = spec.step ?? 5;
  const length = spec.duration > 0 ? spec.duration : Number(timing.duration);
  for (let t = 0; t <= length + 1e-6; t += step) {
    for (const a of together) {
      const end = Number(a.effect?.getComputedTiming().endTime ?? 0);
      a.currentTime = Math.min(end, Number(a.effect?.getTiming().delay ?? 0) + t);
    }
    series.push([t, read()]);
  }
  for (const w of was) {
    w.a.currentTime = w.t;
    if (w.playing) w.a.play();
  }
  return { series, delay, easing: String(timing.easing), iterations: Number(timing.iterations), duration: Number(timing.duration) };
}

/** Lo que se muestrea cuadro a cuadro (lo que no es una animacion del navegador). */
export interface SampleSpec {
  selector: string;
  /** `text`: cuantos caracteres tiene; `dots`: el numero que pinta una cifra de puntos de Finance
   *  Bento (sus circulos encendidos, leidos con la rejilla de 5 × 7 del componente). */
  read: 'text' | 'dots';
  /** Se para cuando el valor lleva este tiempo quieto despues de haber cambiado (ms). */
  quiet?: number;
  timeout?: number;
}

/**
 * Dentro de la pagina: desde ya, en cada cuadro, [ms desde el principio, valor] hasta que el valor
 * cambia y se queda quieto `quiet` ms. Va tal cual a page.evaluate (todo lo que usa esta dentro).
 */
export async function sampleInPage(spec: SampleSpec): Promise<[number, number][]> {
  // La rejilla de 5 × 7 de la cifra de puntos (finance-bento-component.tsx), solo lo que se lee.
  const F: Record<string, string[]> = {
    '0': ['01110', '10001', '10011', '10101', '11001', '10001', '01110'],
    '1': ['00100', '01100', '00100', '00100', '00100', '00100', '01110'],
    '2': ['01110', '10001', '00001', '00010', '00100', '01000', '11111'],
    '3': ['11111', '00010', '00100', '00010', '00001', '10001', '01110'],
    '4': ['00010', '00110', '01010', '10010', '11111', '00010', '00010'],
    '5': ['11111', '10000', '11110', '00001', '00001', '10001', '01110'],
    '6': ['00110', '01000', '10000', '11110', '10001', '10001', '01110'],
    '7': ['11111', '00001', '00010', '00100', '01000', '01000', '01000'],
    '8': ['01110', '10001', '10001', '01110', '10001', '10001', '01110'],
    '9': ['01110', '10001', '10001', '01111', '00001', '00010', '01100'],
    $: ['00100', '01111', '10100', '01110', '00101', '11110', '00100'],
    '€': ['00111', '01000', '11110', '01000', '11110', '01000', '00111'],
    '-': ['00000', '00000', '00000', '11111', '00000', '00000', '00000'],
  };
  const dots = (): number | null => {
    const svg = document.querySelector(spec.selector);
    if (!svg) return null;
    const circles = Array.from(svg.querySelectorAll('circle'));
    if (!circles.length) return null;
    const cols = Math.floor(circles.length / 7);
    const lit = (c: number, r: number) => circles[c * 7 + r]?.getAttribute('opacity') === '1';
    const col = (c: number) => Array.from({ length: 7 }, (_, r) => (lit(c, r) ? '1' : '0'));
    let digits = '';
    let x = 0;
    while (x < cols) {
      let matched = false;
      for (const [ch, rows] of Object.entries(F)) {
        if (x + 5 > cols) break;
        let ok = true;
        for (let k = 0; k < 5 && ok; k += 1) {
          const c = col(x + k);
          for (let r = 0; r < 7 && ok; r += 1) if (c[r] !== rows[r]![k]) ok = false;
        }
        if (ok) {
          if (/\d/.test(ch)) digits += ch;
          x += 6;
          matched = true;
          break;
        }
      }
      if (!matched) x += 1; // un separador (1 columna), un espacio o el hueco entre cifras
    }
    return digits ? Number(digits) : null;
  };
  const read = (): number | null => {
    if (spec.read === 'dots') return dots();
    const el = document.querySelector(spec.selector);
    return el ? (el.textContent ?? '').length : null;
  };
  const t0 = performance.now();
  const out: [number, number][] = [];
  const quiet = spec.quiet ?? 400;
  const deadline = t0 + (spec.timeout ?? 15000);
  let changedAt = -1;
  let last: number | null = null;
  for (;;) {
    await new Promise((r) => requestAnimationFrame(r));
    const now = performance.now();
    const v = read();
    if (v !== null) {
      if (last !== null && v !== last) changedAt = now;
      out.push([now - t0, v]);
      last = v;
    }
    if (changedAt >= 0 && now - changedAt > quiet) break;
    if (now > deadline) break;
  }
  return out;
}
