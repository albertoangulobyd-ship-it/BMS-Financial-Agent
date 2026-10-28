// El motor de la suricata (loader-engine.ts) con un DOM y un lienzo de mentira y un reloj que
// avanza a mano, como work/test-new-loader.cjs del dueno (entrega del 28-10-2026): las cinco
// etapas y la pila de 5, la espera con la cabeza, el progreso que no baja y "menos movimiento".
// Ademas (especificacion §5.6): el motor no empieza una etapa que no se ha pedido, finish sin las
// etapas las juega en orden, la etapa en curso se vuelve a anunciar con su linea nueva, la espera
// larga, dispose lo limpia todo, hide funde en 300 ms y despues hace dispose, y el dibujo es
// drawImage de 9 argumentos sin suavizado y a escala entera (3, o 2 a 700 px o menos).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sources } from './loader-sprites';

type Sprite = keyof typeof sources;
const NAME_OF = new Map<string, Sprite>(Object.entries(sources).map(([name, src]) => [src, name as Sprite]));

interface FakeCtx {
  imageSmoothingEnabled: boolean;
  fillStyle: string;
  clearRect(): void;
  fillRect(): void;
  save(): void;
  restore(): void;
  translate(): void;
  scale(): void;
  drawImage(...args: unknown[]): void;
}

interface Env {
  now: number;
  frame: { sprites: { name: Sprite; f: number; w: number }[]; grains: number };
  frames: { at: number; sprites: { name: Sprite; f: number; w: number }[]; grains: number; debug: string; progress: number }[];
  rafs: Map<number, (now: number) => void>;
  timeouts: { at: number; fn: () => void }[];
  listeners: number;
  observers: number;
  contexts: FakeCtx[];
  hostWidth: number;
  /** Avanza el reloj de 16 en 16 ms, pintando cada fotograma. */
  advance(ms: number, each?: () => void): void;
}

function fakeEnv(opts: { reduce?: boolean; mobile?: boolean } = {}): Env {
  const env: Env = {
    now: 0,
    frame: { sprites: [], grains: 0 },
    frames: [],
    rafs: new Map(),
    timeouts: [],
    listeners: 0,
    observers: 0,
    contexts: [],
    hostWidth: 640,
    advance(ms, each) {
      const end = this.now + ms;
      while (this.now < end) {
        this.now += 16;
        const due = this.timeouts.filter((t) => t.at <= this.now);
        this.timeouts = this.timeouts.filter((t) => t.at > this.now);
        due.forEach((t) => t.fn());
        const jobs = [...this.rafs.values()];
        this.rafs.clear();
        this.frame = { sprites: [], grains: 0 };
        jobs.forEach((f) => f(this.now));
        const debug = document.querySelector('output')?.textContent ?? '';
        const progress = (document.querySelector('progress') as unknown as { value: number } | null)?.value ?? 0;
        this.frames.push({ at: this.now, sprites: this.frame.sprites, grains: this.frame.grains, debug, progress });
        each?.();
      }
    },
  };
  let rafId = 0;
  const made: FakeElement[] = [];
  class FakeElement {
    className = '';
    textContent = '';
    hidden = false;
    style: Record<string, string> = {};
    children: FakeElement[] = [];
    parent: FakeElement | null = null;
    attrs: Record<string, string> = {};
    width = 0;
    height = 0;
    max = 0;
    value = 0;
    removed = false;
    constructor(public tag: string) {
      made.push(this);
    }
    setAttribute(k: string, v: string) {
      this.attrs[k] = v;
    }
    append(...nodes: FakeElement[]) {
      for (const n of nodes) {
        n.parent = this;
        this.children.push(n);
      }
    }
    replaceChildren(...nodes: FakeElement[]) {
      this.children = [];
      this.append(...nodes);
    }
    remove() {
      this.removed = true;
    }
    getBoundingClientRect() {
      return { left: 0, top: 0, width: this.width, height: this.height };
    }
    get clientWidth() {
      return env.hostWidth;
    }
    getContext() {
      const ctx: FakeCtx = {
        imageSmoothingEnabled: true,
        fillStyle: '',
        clearRect() {},
        fillRect: () => {
          env.frame.grains++;
        },
        save() {},
        restore() {},
        translate() {},
        scale() {},
        drawImage: (...args: unknown[]) => {
          if (args.length !== 9) throw new Error('drawImage signature');
          const img = args[0] as { src: string };
          const name = NAME_OF.get(img.src);
          if (!name) throw new Error('not an approved sprite');
          env.frame.sprites.push({ name, f: (args[1] as number) / 76, w: args[7] as number });
        },
      };
      env.contexts.push(ctx);
      return ctx;
    }
  }
  vi.stubGlobal('document', {
    hidden: false,
    createElement: (tag: string) => new FakeElement(tag),
    querySelector: (sel: string) => [...made].reverse().find((e) => !e.removed && (sel === 'output' || sel === 'progress') && e.tag === sel) ?? null,
  });
  vi.stubGlobal('window', {
    setTimeout: (fn: () => void, ms: number) => {
      env.timeouts.push({ at: env.now + ms, fn });
      return env.timeouts.length;
    },
  });
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: (q.includes('reduce') && !!opts.reduce) || (q.includes('max-width') && !!opts.mobile),
    addEventListener: () => {
      env.listeners++;
    },
    removeEventListener: () => {
      env.listeners--;
    },
  }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {
        env.observers++;
      }
      disconnect() {
        env.observers--;
      }
    }
  );
  vi.stubGlobal(
    'Image',
    class {
      onload: (() => void) | null = null;
      private s = '';
      get src() {
        return this.s;
      }
      set src(v: string) {
        this.s = v;
        queueMicrotask(() => this.onload?.());
      }
    }
  );
  vi.stubGlobal('requestAnimationFrame', (fn: (now: number) => void) => {
    env.rafs.set(++rafId, fn);
    return rafId;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => env.rafs.delete(id));
  return env;
}

async function mount(_env: Env, options: Record<string, unknown> = {}) {
  const { mountLoader } = await import('./loader-engine');
  const stages: number[] = [];
  const labels: [number, string, string][] = [];
  let finished = 0;
  const progress: number[] = [];
  const host = document.createElement('div') as unknown as HTMLElement;
  const loader = mountLoader(host, {
    debug: false,
    externalProgress: true,
    onStage: (i, t, s) => {
      stages.push(i);
      labels.push([i, t, s]);
    },
    onFinished: () => finished++,
    onProgress: (p) => progress.push(p.value),
    ...options,
  });
  // Las imagenes se cargan en microtareas.
  await new Promise((r) => setTimeout(r, 0));
  return { loader, stages, labels, progress, finished: () => finished, host };
}

/** Las poses de cuerpo entero (las demas son solo la cabeza o la excavacion). */
const BODY = new Set<Sprite>(['emerge-search', 'moving-document', 'walking-documento', 'found-cave']);

beforeEach(() => {
  vi.resetModules();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('el motor de la suricata', () => {
  it('la intro: las particulas caen, el monticulo, asoma y espera solo la cabeza hasta el si', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    env.advance(9000);
    const first = env.frames.find((f) => f.sprites.length > 0)!;
    // Ningun dibujo del animal hasta que caen las particulas (1400 ms) y se forma el monticulo (220).
    expect(first.at).toBeGreaterThanOrEqual(1620);
    expect(env.frames.filter((f) => f.at < 1400).every((f) => f.grains >= 180)).toBe(true);
    // Primero cava (emerge-dig 0-3) y despues solo la cabeza (guard-head [0,1,0,4,0,7]).
    const after = env.frames.filter((f) => f.at > 2600);
    expect(after.every((f) => f.sprites.every((s) => s.name === 'guard-head'))).toBe(true);
    const heads = new Set(after.flatMap((f) => f.sprites.map((s) => s.f)));
    expect([...heads].every((f) => [0, 1, 4, 7].includes(f))).toBe(true);
    expect(env.frames.some((f) => f.sprites.some((s) => BODY.has(s.name)))).toBe(false);
    expect(m.stages).toEqual([]);
    // Pintado como pixel duro, con la escala entera de escritorio (76 x 3).
    expect(env.contexts.length).toBe(2);
    expect(env.contexts.every((c) => c.imageSmoothingEnabled === false)).toBe(true);
    expect(after[0]!.sprites[0]!.w).toBe(76 * 3);
  });

  it('a 700 px o menos, escala 2', async () => {
    const env = fakeEnv({ mobile: true });
    await mount(env);
    env.advance(3000);
    expect(env.frames.at(-1)!.sprites[0]!.w).toBe(76 * 2);
  });

  it('cinco etapas y la pila de 5, el progreso no baja y llega a 100; junto a la pila, siempre de cuerpo entero', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    m.loader.start();
    let previous = 0;
    for (let i = 0; i < 15000 && !m.finished(); i++) {
      env.advance(16);
      const f = env.frames.at(-1)!;
      expect(f.progress).toBeGreaterThanOrEqual(previous);
      previous = f.progress;
      if (/vigilando|revisando la pila|olfateando junto a la pila/.test(f.debug)) {
        expect(Number(/frame (\d+)/.exec(f.debug)?.[1])).toBeGreaterThanOrEqual(5);
      }
    }
    expect(m.finished()).toBe(1);
    expect(m.stages).toEqual([0, 1, 2, 3, 4]);
    expect(previous).toBe(100);
    expect(env.frames.some((f) => /centinela/.test(f.debug) || f.debug.includes('pila 5'))).toBe(true);
  });

  it('con "menos movimiento": sin particulas, la cabeza fija, cada etapa deja su papel al momento', async () => {
    const env = fakeEnv({ reduce: true });
    const m = await mount(env);
    env.advance(3000);
    expect(env.frames.every((f) => f.grains <= 1)).toBe(true);
    expect(env.frames.every((f) => f.sprites.every((s) => s.name === 'guard-head' && s.f === 0))).toBe(true);
    m.loader.start();
    for (let i = 0; i < 2000 && !m.finished(); i++) env.advance(16);
    expect(m.finished()).toBe(1);
    expect(m.stages).toEqual([0, 1, 2, 3, 4]);
    expect(m.progress.at(-1)).toBe(100);
  });

  it('no empieza una etapa que no se ha pedido; al pedir otra, juega las que faltan en orden', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    env.advance(3000);
    m.loader.setStage(0, 'Cargando', 'Preparando las 3 facturas nuevas.');
    env.advance(40000);
    expect(m.stages).toEqual([0]);
    expect(env.frames.at(-1)!.debug).toContain('pila 1');
    // Sin la etapa siguiente, el % no pasa de 20 + 17.
    expect(Math.max(...m.progress)).toBeLessThanOrEqual(37);
    m.loader.setStage(2, 'Comparando', 'Buscando referencias.');
    for (let i = 0; i < 5000 && m.stages.length < 3; i++) env.advance(16);
    expect(m.stages).toEqual([0, 1, 2]);
    expect(m.labels[0]).toEqual([0, 'Cargando', 'Preparando las 3 facturas nuevas.']);
    expect(m.labels[2]).toEqual([2, 'Comparando', 'Buscando referencias.']);
  });

  it('la etapa en curso se vuelve a anunciar con su linea nueva', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    env.advance(3000);
    m.loader.setStage(0, 'Cargando', 'a');
    m.loader.setStage(1, 'Leyendo', 'Leyendo 1 de 3.');
    for (let i = 0; i < 5000 && m.stages.length < 2; i++) env.advance(16);
    m.loader.setStage(1, 'Leyendo', 'Leyendo 2 de 3.');
    expect(m.labels.at(-1)).toEqual([1, 'Leyendo', 'Leyendo 2 de 3.']);
  });

  it('finish sin las etapas las juega todas en orden, despues la centinela y el fundido', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    env.advance(3000);
    m.loader.finish();
    for (let i = 0; i < 15000 && !m.finished(); i++) env.advance(16);
    expect(m.stages).toEqual([0, 1, 2, 3, 4]);
    expect(m.finished()).toBe(1);
  });

  it('esperando mucho junto a la pila, entra en la cueva y vuelve a salir (6,5 s)', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    env.advance(3000);
    m.loader.setStage(0);
    env.advance(60000);
    expect(m.stages).toEqual([0]);
    expect(env.frames.some((f) => f.sprites.some((s) => s.name === 'found-cave'))).toBe(true);
  });

  it('nunca la cabeza justo despues del cuerpo entero', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    m.loader.start();
    for (let i = 0; i < 15000 && !m.finished(); i++) env.advance(16);
    let body = false;
    for (const f of env.frames) {
      const names = f.sprites.map((s) => s.name);
      if (body) expect(names.includes('guard-head') || names.includes('emerge-dig')).toBe(false);
      if (names.some((n) => BODY.has(n))) body = true;
    }
  });

  it('dispose lo limpia todo: rAF, ResizeObserver y matchMedia', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    env.advance(500);
    expect(env.rafs.size).toBe(1);
    expect(env.observers).toBe(1);
    expect(env.listeners).toBe(2);
    m.loader.dispose();
    expect(env.rafs.size).toBe(0);
    expect(env.observers).toBe(0);
    expect(env.listeners).toBe(0);
    env.advance(500);
    expect(env.rafs.size).toBe(0);
  });

  it('hide funde la escena en 300 ms y despues hace dispose y la quita', async () => {
    const env = fakeEnv();
    const m = await mount(env);
    env.advance(3000);
    const root = (m.host as unknown as { children: { style: Record<string, string>; removed: boolean }[] }).children[0]!;
    m.loader.hide();
    expect(root.style.opacity).toBe('0');
    expect(root.removed).toBe(false);
    env.advance(288);
    expect(env.rafs.size).toBe(1);
    env.advance(32);
    expect(root.removed).toBe(true);
    expect(env.rafs.size).toBe(0);
    expect(env.observers).toBe(0);
  });
});
