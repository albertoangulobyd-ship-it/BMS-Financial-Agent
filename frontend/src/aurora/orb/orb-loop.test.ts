import { describe, expect, it } from 'vitest';
import { MAX_FPS, createFrameLoop, createOrbRegistry, shouldAnimate, type FrameScheduler } from './orb-loop';

/** Un requestAnimationFrame falso: cada `tick` es un cuadro de pantalla. */
function fakeScheduler(hz = 60) {
  let time = 0;
  let next = 1;
  const pending = new Map<number, (t: number) => void>();
  const scheduler: FrameScheduler = {
    now: () => time,
    request: (cb) => {
      const id = next++;
      pending.set(id, cb);
      return id;
    },
    cancel: (id) => {
      pending.delete(id);
    },
  };
  return {
    scheduler,
    pending: () => pending.size,
    /** Avanza `ms` a la frecuencia de la pantalla, llamando a lo que este pedido. */
    run(ms: number) {
      const step = 1000 / hz;
      for (let elapsed = 0; elapsed < ms - 1e-9; elapsed += step) {
        time += step;
        const due = [...pending.entries()];
        pending.clear();
        for (const [, cb] of due) cb(time);
      }
    },
  };
}

describe('cuando se mueve el orbe', () => {
  const base = { active: true, visible: true, onScreen: true, reducedMotion: false };

  it('solo con el asistente trabajando, a la vista, en pantalla y sin "menos movimiento"', () => {
    expect(shouldAnimate(base)).toBe(true);
    expect(shouldAnimate({ ...base, active: false })).toBe(false);
    expect(shouldAnimate({ ...base, visible: false })).toBe(false);
    expect(shouldAnimate({ ...base, onScreen: false })).toBe(false);
    expect(shouldAnimate({ ...base, reducedMotion: true })).toBe(false);
  });
});

describe('el bucle de imagenes', () => {
  it('no pasa de 30 imagenes por segundo con una pantalla de 60, 120 o 144 Hz', () => {
    for (const hz of [60, 120, 144]) {
      const fake = fakeScheduler(hz);
      let draws = 0;
      const loop = createFrameLoop(() => (draws += 1), fake.scheduler);
      loop.start();
      fake.run(2000);
      expect(draws, `${hz} Hz`).toBeLessThanOrEqual(2 * MAX_FPS + 1);
      expect(draws, `${hz} Hz`).toBeGreaterThanOrEqual(2 * MAX_FPS - 2);
      loop.stop();
    }
  });

  it('parado no pide ningun cuadro: en reposo no gasta nada', () => {
    const fake = fakeScheduler();
    let draws = 0;
    const loop = createFrameLoop(() => (draws += 1), fake.scheduler);
    fake.run(1000);
    expect(draws).toBe(0);
    loop.start();
    fake.run(500);
    loop.stop();
    expect(loop.running).toBe(false);
    expect(fake.pending()).toBe(0);
    const before = draws;
    fake.run(3000);
    expect(draws).toBe(before);
  });

  it('el tiempo animado solo avanza mientras se mueve (no salta al volver)', () => {
    const fake = fakeScheduler();
    const seen: number[] = [];
    const loop = createFrameLoop((t) => seen.push(t), fake.scheduler);
    loop.start();
    fake.run(1000);
    loop.stop();
    const paused = loop.elapsed;
    expect(paused).toBeGreaterThan(900);
    fake.run(10_000);
    loop.start();
    fake.run(100);
    expect(loop.elapsed - paused).toBeLessThan(250);
    expect(seen.every((t, i) => i === 0 || t >= seen[i - 1]!)).toBe(true);
  });

  it('pedir 60 imagenes por segundo se queda en 30', () => {
    const fake = fakeScheduler(120);
    let draws = 0;
    const loop = createFrameLoop(() => (draws += 1), fake.scheduler, 60);
    loop.start();
    fake.run(1000);
    expect(draws).toBeLessThanOrEqual(MAX_FPS + 1);
  });
});

describe('un orbe por pantalla', () => {
  it('el primero se queda el WebGL; el segundo no, hasta que el primero se va', () => {
    const registry = createOrbRegistry();
    const a = Symbol('a');
    const b = Symbol('b');
    expect(registry.claim(a)).toBe(true);
    expect(registry.claim(a)).toBe(true);
    expect(registry.claim(b)).toBe(false);
    registry.release(b);
    expect(registry.taken).toBe(true);
    registry.release(a);
    expect(registry.claim(b)).toBe(true);
  });
});
