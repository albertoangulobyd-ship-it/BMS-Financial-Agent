// La suricata que lleva los documentos a la pila mientras se leen facturas (paso 16). Es el
// motor del cargador de Aurora (loader-engine.ts del prototipo): el mismo dibujo, las mismas
// tiras blancas y los mismos tiempos. Lo que cambia, de la revision (§4.26 y §8.2):
// - sin funciones globales (window.setLoaderStage, finishLoader, hideLoader) ni botones de
//   depuracion: se maneja solo por lo que devuelve mountLoader (setStage, finish, dispose);
// - sin progreso inventado: el prototipo calculaba un porcentaje y unas filas "leyendo /
//   comparando" a partir de la animacion. Aqui la animacion solo sigue al progreso de verdad
//   (cada setStage es un documento que se ha leido) y las cifras las pinta quien llama;
// - sin textos fijos en castellano: los titulos los da quien llama, ya traducidos;
// - sin el vuelo de particulas desde el orbe del inicio (processing-entry), que leia los
//   pixeles de otro lienzo de la pagina: la suricata sale de un monticulo propio;
// - el bucle se para con la ventana oculta o el cargador fuera de pantalla, y dibuja como
//   mucho 30 veces por segundo (las tiras van a 8 cuadros por segundo).
// Todo lo que crea son elementos con textContent: nada de HTML escrito al vuelo.
import { SPRITES, type SpriteName } from '@/aurora/meerkat/sprites';

export const CONFIG = {
  FPS: 8,
  SCALE: 3,
  mobileScale: 2,
  walkSpeed: 85,
  pileX: 550,
  areaWidth: 640,
  lastFrameHold: 120,
  longWait: 6500,
  particleFall: 1400,
  moundPause: 220,
  durations: {
    'emerge-dig': [180, 160, 100, 100, 140, 170, 240, 180],
    'emerge-search': [140, 180, 180, 240, 240, 360, 160, 160],
    'moving-document': [220, 150, 180, 260, 300, 180],
    'enter-burrow': [200, 150, 140, 140, 180, 240],
    'found-cave': [220, 180, 150, 160, 180, 300],
  } as Record<string, number[]>,
};

const DRAW_MS = 1000 / 30;

/** Los textos que ensena el cargador, ya en el idioma de la persona. */
export interface LoaderTexts {
  /** Mientras cargan las imagenes. */
  preparing: string;
  /** Listo para empezar, antes del primer documento. */
  ready: string;
  readySub: string;
  /** Si las imagenes no cargan (la animacion sobra: el trabajo sigue). */
  imagesFailed: string;
}

export interface LoaderOptions {
  texts: LoaderTexts;
  /** Cuantos documentos hay: la pila tiene uno por cada uno (como mucho 24 en pantalla). */
  total: number;
  onStage?: (index: number) => void;
  onFinished?: () => void;
}

export interface LoaderHandle {
  /** Empieza la animacion (la suricata sale y espera el primer documento). */
  start: () => void;
  /** El documento `index` (desde 0) se esta leyendo: la suricata va a buscarlo. */
  setStage: (index: number, title?: string, subtitle?: string) => void;
  /** Todo leido: deja el ultimo en la pila, vigila y termina. */
  finish: () => void;
  dispose: () => void;
}

interface Job {
  sprite: SpriteName;
  frames: number[];
  move?: number;
  loop?: boolean;
  hold?: number;
  done: () => void;
}

function h(tag: string, attrs: Record<string, string> = {}, ...kids: (Node | string)[]): HTMLElement {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  el.append(...kids);
  return el;
}

/** Todas las poses salen de las tiras aprobadas, nunca de un dibujo hecho con codigo. */
export function mountLoader(host: HTMLElement, options: LoaderOptions): LoaderHandle {
  const stages = Math.max(1, Math.min(24, Math.floor(options.total) || 1));
  const world = h('canvas', { class: 'zur-world', 'aria-hidden': 'true' }) as HTMLCanvasElement;
  const pile = h('canvas', { class: 'zur-pile', 'aria-hidden': 'true' }) as HTMLCanvasElement;
  const title = h('p', { class: 'zur-title' }, options.texts.preparing);
  const sub = h('p', { class: 'zur-sub' });
  const root = h(
    'div',
    { class: 'zur-loader' },
    h('div', { class: 'zur-stage' }, world, pile),
    h('div', { class: 'zur-text', role: 'status' }, title, sub)
  );
  host.replaceChildren(root);
  const ctx = world.getContext('2d');
  const pctx = pile.getContext('2d');
  const images = {} as Record<SpriteName, HTMLImageElement>;
  const mobile = window.matchMedia('(max-width:700px)');
  const reduced = window.matchMedia('(prefers-reduced-motion:reduce)');
  let scale = mobile.matches ? CONFIG.mobileScale : CONFIG.SCALE;
  let width = CONFIG.areaWidth;
  let ground = 41 * scale;
  let pileX = CONFIG.pileX;
  let x = CONFIG.areaWidth / 2;
  let facing = 1;
  let stage = -1;
  let requested = -1;
  let count = 0;
  let ready = false;
  let started = false;
  let startRequested = false;
  let finishing = false;
  let ended = false;
  let disposed = false;
  let onScreen = true;
  let raf = 0;
  let last = 0;
  let lastDraw = 0;
  let clock = 0;
  let elapsed = 0;
  let frame = 0;
  let waitSince = 0;
  let finalAt = Infinity;
  let job: Job | null = null;
  let hole: number | null = null;
  let fall: { start: number; x: number; y: number } | null = null;
  let entrance = true;
  // Vigilando junto a la pila: el unico momento en que coge el siguiente documento.
  let watching = false;
  const grains = Array.from({ length: 180 }, (_, i) => {
    const angle = i * 2.399963;
    const radius = Math.sqrt((i + 0.5) / 180);
    return { u: Math.cos(angle) * radius, v: Math.sin(angle) * radius, delay: (i % 11) * 24 };
  });
  const paperOffsets: number[] = [];
  const labels = new Map<number, [string, string]>();
  const centerAtPile = () => Math.min(width - 39 * scale - 10, pileX - 60);
  const randomLeft = () =>
    Math.round(33 * scale + 10 + Math.random() * Math.max(1, Math.min(width * 0.34, centerAtPile() - 80) - (33 * scale + 10)));
  const frames = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => a + i - 1);

  function layout() {
    const oldWidth = width;
    scale = mobile.matches ? CONFIG.mobileScale : CONFIG.SCALE;
    width = Math.min(CONFIG.areaWidth, Math.max(240, host.clientWidth || CONFIG.areaWidth));
    ground = 41 * scale;
    pileX = Math.min(CONFIG.pileX, width - 70);
    x = Math.max(110, Math.min(width - 100, (x * width) / oldWidth));
    for (const c of [world, pile]) {
      c.width = width;
      c.height = Math.max(47 * scale, ground + 6 * scale);
      c.style.width = width + 'px';
      c.style.height = c.height + 'px';
    }
    if (ctx) ctx.imageSmoothingEnabled = false;
    if (pctx) pctx.imageSmoothingEnabled = false;
    // Al cambiar de tamano el lienzo se borra: la pila se vuelve a pintar desde sus huecos.
    if (ready && pctx) {
      paperOffsets.forEach((offset, i) => paper(pctx, 0, pileX + offset * scale, ground - i * 2 * scale));
      draw();
    }
  }
  function pose(name: SpriteName, f: number, px = x, dir = facing) {
    if (!ctx) return;
    ctx.save();
    ctx.translate(Math.round(px), ground);
    ctx.scale(dir, 1);
    ctx.drawImage(images[name], f * 76, 0, 76, 47, -35 * scale, -41 * scale, 76 * scale, 47 * scale);
    ctx.restore();
  }
  function paper(c: CanvasRenderingContext2D, f: number, px: number, py: number) {
    // La celda entera a escala 1: sus margenes transparentes conservan el ancla.
    c.drawImage(images.Paper, f * 76, 0, 76, 47, Math.round(px - 35), Math.round(py - 41), 76, 47);
  }
  function draw() {
    if (!ready || disposed || !ctx) return;
    ctx.clearRect(0, 0, width, world.height);
    ctx.fillStyle = '#fff';
    ctx.fillRect(10, ground, width - 20, scale);
    if (hole !== null) pose('enter-burrow', 5, hole, 1);
    const current = job;
    if (entrance && !reduced.matches) {
      const digging = clock - CONFIG.particleFall - CONFIG.moundPause;
      if (digging < 0) {
        // El monticulo: granos que caen y se amontonan donde va a salir.
        for (const g of grains) {
          const t = Math.max(0, Math.min(1, (clock - 180 - g.delay) / 900));
          const tx = x + g.u * 11 * scale;
          const ty = ground - (1 - Math.abs(g.u)) * Math.abs(g.v) * 7 * scale;
          const sx = x + g.u * 15 * scale;
          const sy = ground - 23 * scale + g.v * 10 * scale;
          const px = sx + (tx - sx) * (1 - (1 - t) * (1 - t));
          const py = sy + (ty - sy) * t * t;
          const size = Math.max(1, Math.round(scale / 3));
          ctx.fillRect(Math.round(px), Math.round(py), size, size);
        }
      } else {
        let time = digging;
        let f = 0;
        const dig = CONFIG.durations['emerge-dig']!;
        while (f < 3 && time >= dig[f]!) {
          time -= dig[f]!;
          f++;
        }
        if (digging >= dig.slice(0, 4).reduce((a, b) => a + b, 0)) pose('guard-head', 0, x, 1);
        else pose('emerge-dig', f, x, 1);
        return;
      }
    } else if (!started) {
      pose('guard-head', reduced.matches ? 0 : ([0, 1, 0, 4, 0, 7][Math.floor(clock / 1200) % 6] ?? 0), x, 1);
    } else {
      pose(
        reduced.matches ? 'emerge-search' : (current?.sprite ?? 'emerge-search'),
        reduced.matches ? 5 : (current?.frames[frame] ?? 5)
      );
    }
    if (fall) {
      const t = Math.min(1, (clock - fall.start) / 250);
      paper(ctx, 1, fall.x, fall.y + (ground - count * 2 * scale - fall.y) * t * t);
    }
  }
  function play(sprite: SpriteName, fs: number[], done: () => void, extra: Partial<Job> = {}) {
    watching = false;
    job = { sprite, frames: fs, done, ...extra };
    frame = 0;
    elapsed = 0;
  }
  function walk(target: number, carrying: boolean, done: () => void) {
    facing = target < x ? -1 : 1;
    play(carrying ? 'walking-documento' : 'emerge-search', carrying ? frames(1, 4) : [6, 7], done, {
      move: target,
      loop: true,
    });
  }
  function announce(i: number) {
    const label = labels.get(i);
    if (label) {
      title.textContent = label[0];
      sub.textContent = label[1];
    }
    options.onStage?.(i);
  }
  function beginStage(i: number) {
    stage = i;
    hole = null;
    fall = null;
    announce(i);
    if (reduced.matches) {
      count = i + 1;
      paperOffsets.push(0);
      if (pctx) paper(pctx, 0, pileX, ground - i * 2 * scale);
      x = centerAtPile();
      waitSince = clock;
      job = null;
      draw();
      return;
    }
    walk(randomLeft(), false, () => {
      hole = x;
      facing = 1;
      play('moving-document', frames(1, 4), () =>
        walk(centerAtPile(), true, () => {
          facing = 1;
          play(
            'moving-document',
            [4],
            () => {
              job = null;
              fall = { start: clock, x: pileX, y: ground - 13 * scale };
            },
            { hold: 300 }
          );
        })
      );
    });
  }
  function peek() {
    facing = 1;
    waitSince = clock;
    play('emerge-search', [5, 4, 5], () => {}, { loop: true, hold: 650 });
    watching = true;
  }
  function inspectPile() {
    // El cuerpo entero sobre el suelo junto a la pila: las poses de solo cabeza son de la
    // madriguera, nunca de la espera junto a la pila.
    const gestures = [
      [5, 4, 5],
      [5, 6, 7, 6, 4, 5],
      [5, 4, 5, 4, 5],
    ];
    play('emerge-search', gestures[(count - 1) % gestures.length] ?? [5], () => peek(), { hold: 240 });
  }
  function deposited() {
    const offset = Math.round(Math.random() * 2) - 1;
    paperOffsets.push(offset);
    if (pctx) paper(pctx, 0, pileX + offset * scale, ground - count * 2 * scale);
    count++;
    fall = null;
    inspectPile();
  }
  function variation() {
    walk(randomLeft(), false, () => {
      hole = x;
      play('found-cave', frames(1, 6), () =>
        play('emerge-search', frames(2, 6), () =>
          walk(centerAtPile(), false, () => {
            hole = null;
            peek();
          })
        )
      );
    });
  }
  function final() {
    if (ended) return;
    ended = true;
    hole = null;
    fall = null;
    job = null;
    x = centerAtPile();
    facing = 1;
    finalAt = clock + 1200;
    draw();
  }
  function update(dt: number) {
    clock += dt;
    if (entrance) {
      const duration =
        CONFIG.particleFall +
        CONFIG.moundPause +
        CONFIG.durations['emerge-dig']!.slice(0, 4).reduce((a, b) => a + b, 0) +
        300 +
        CONFIG.lastFrameHold;
      if (reduced.matches || clock >= duration) {
        entrance = false;
        if (started) play('emerge-search', frames(3, 6), () => peek());
      } else return;
    }
    if (!started) return;
    if (ended) {
      if (clock >= finalAt) {
        stop();
        options.onFinished?.();
        finalAt = Infinity;
      }
      return;
    }
    if (fall) {
      if (clock - fall.start >= 250) deposited();
      return;
    }
    if (job) {
      elapsed += dt;
      const current = job;
      if (current.move !== undefined) {
        const distance = (CONFIG.walkSpeed * dt) / 1000;
        x += Math.sign(current.move - x) * Math.min(Math.abs(current.move - x), distance);
        if (Math.abs(current.move - x) < 0.01) {
          x = current.move;
          job = null;
          current.done();
          return;
        }
      }
      const times = CONFIG.durations[current.sprite];
      const duration = current.hold ?? ((times?.[current.frames[frame] ?? 0] ?? 125) * 8) / CONFIG.FPS;
      const holdLast = frame === current.frames.length - 1 && !current.loop ? CONFIG.lastFrameHold : 0;
      if (elapsed >= duration + holdLast) {
        elapsed -= duration;
        frame++;
        if (frame >= current.frames.length) {
          if (current.loop) frame = 0;
          else {
            job = null;
            current.done();
            return;
          }
        }
      }
    }
    // Esperando junto a la pila: sigue con el siguiente documento solo cuando de verdad se
    // esta leyendo (requested), o termina si ya se leyo todo.
    const waiting = watching || reduced.matches;
    if (waiting && !fall && count > stage) {
      if (finishing && requested <= stage) {
        final();
        return;
      }
      if (requested > stage && stage < stages - 1) {
        beginStage(stage + 1);
        return;
      }
      if (!reduced.matches && stage >= 0 && clock - waitSince > CONFIG.longWait) variation();
    }
  }
  function tick(now: number) {
    raf = 0;
    if (disposed) return;
    const dt = last ? Math.min(60, now - last) : 0;
    last = now;
    update(dt);
    if (now - lastDraw >= DRAW_MS - 1) {
      lastDraw = now;
      draw();
    }
    schedule();
  }
  function running(): boolean {
    return !disposed && ready && onScreen && document.visibilityState === 'visible' && !(ended && finalAt === Infinity);
  }
  function schedule() {
    if (!raf && running()) raf = requestAnimationFrame(tick);
  }
  function stop() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
  }
  function resume() {
    stop();
    last = 0;
    schedule();
  }
  function start() {
    startRequested = true;
    if (started || !ready) return;
    started = true;
    if (reduced.matches) return;
    if (!entrance) play('emerge-search', frames(3, 6), () => peek());
  }
  function setStage(i: number, t?: string, s?: string) {
    if (!Number.isInteger(i) || i < 0 || i >= stages || ended) return;
    requested = Math.max(requested, i);
    if (t) labels.set(i, [t, s ?? '']);
    if (i === stage) announce(i);
    start();
  }
  function finish() {
    if (ended) return;
    finishing = true;
    start();
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    stop();
    resize.disconnect();
    intersection.disconnect();
    mobile.removeEventListener('change', layout);
    reduced.removeEventListener('change', motionChange);
    document.removeEventListener('visibilitychange', resume);
  }
  function motionChange() {
    if (reduced.matches) {
      entrance = false;
      job = null;
      fall = null;
      x = centerAtPile();
      facing = 1;
    } else if (started && !ended) peek();
    draw();
  }
  const resize = new ResizeObserver(layout);
  resize.observe(host);
  const intersection = new IntersectionObserver((entries) => {
    onScreen = entries.some((e) => e.isIntersecting);
    resume();
  });
  intersection.observe(host);
  mobile.addEventListener('change', layout);
  reduced.addEventListener('change', motionChange);
  document.addEventListener('visibilitychange', resume);
  layout();
  const names = Object.keys(SPRITES) as SpriteName[];
  Promise.all(
    names.map(
      (name) =>
        new Promise<void>((resolve, reject) => {
          const img = new Image();
          img.onload = () => {
            images[name] = img;
            resolve();
          };
          img.onerror = () => reject(new Error(name));
          img.src = SPRITES[name];
        })
    )
  )
    .then(() => {
      if (disposed) return;
      ready = true;
      layout();
      title.textContent = options.texts.ready;
      sub.textContent = options.texts.readySub;
      draw();
      resume();
      if (startRequested) start();
    })
    .catch(() => {
      if (!disposed) {
        title.textContent = options.texts.imagesFailed;
        sub.textContent = '';
      }
    });
  return { start, setStage, finish, dispose };
}
