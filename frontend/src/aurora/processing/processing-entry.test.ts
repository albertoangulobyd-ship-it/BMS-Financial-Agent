// La entrada a Procesar (processing-entry.ts, como en Aurora): los puntos del orbe de particulas
// con alfa > 0,14 (uno de cada 2 px, como mucho 350), el suelo 80 px por debajo del centro, los
// sitios del saludo y de la escena en .app, y una sola toma: el motor que viene despues (tras un
// fundido) no tiene captura y usa su nube de reserva.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { captureProcessingEntry, takeProcessingEntry } from './processing-entry';

afterEach(() => {
  vi.unstubAllGlobals();
  takeProcessingEntry();
});

function fakePage(opts: { canvas?: boolean; alpha?: (x: number, y: number) => number; band?: number } = {}) {
  const vars: Record<string, string> = {};
  const w = 100,
    h = 100;
  const data = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) data[(y * w + x) * 4 + 3] = (opts.alpha ?? (() => 255))(x, y);
  const canvas = {
    width: w,
    height: h,
    getBoundingClientRect: () => ({ left: 445, top: 243, width: 270, height: 270 }),
    getContext: () => ({ getImageData: () => ({ data }) }),
  };
  const app = {
    style: { setProperty: (k: string, v: string) => (vars[k] = v) },
    querySelector: (sel: string) =>
      sel === 'main'
        ? { getBoundingClientRect: () => ({ top: opts.band ?? 0 }) }
        : sel.includes('canvas')
          ? opts.canvas === false
            ? null
            : canvas
          : { getBoundingClientRect: () => ({ top: 138 + (opts.band ?? 0), left: 362 }) },
  };
  vi.stubGlobal('document', { querySelector: (sel: string) => (sel === '.app' ? app : null) });
  vi.stubGlobal('window', { scrollY: 0 });
  return vars;
}

describe('la entrada a Procesar', () => {
  it('toma los puntos visibles del orbe, como mucho 350, y el sitio del saludo y de la escena', () => {
    const vars = fakePage();
    captureProcessingEntry();
    const entry = takeProcessingEntry()!;
    expect(entry.points.length).toBeLessThanOrEqual(350);
    expect(entry.points.length).toBeGreaterThan(300);
    expect(entry.centerX).toBe(445 + 135);
    expect(entry.groundY).toBe(243 + 135 + 80);
    expect(vars['--process-heading-y']).toBe('138px');
    expect(vars['--process-scene-y']).toBe(`${243 - 28}px`);
    // Una sola vez.
    expect(takeProcessingEntry()).toBeNull();
  });

  it('con la banda de los datos de prueba, los sitios se cuentan desde main (que ya baja)', () => {
    const vars = fakePage({ band: 28 });
    captureProcessingEntry();
    expect(vars['--process-heading-y']).toBe('138px');
    expect(vars['--process-scene-y']).toBe(`${243 - 28 - 28}px`);
  });

  it('solo los puntos con alfa mayor que 0,14', () => {
    fakePage({ alpha: (x) => (x < 50 ? 30 : 0) });
    captureProcessingEntry();
    const entry = takeProcessingEntry()!;
    // 30/255 < 0,14: ninguno.
    expect(entry.points).toEqual([]);
  });

  it('sin el orbe de particulas (se entra desde una respuesta), sin captura', () => {
    fakePage({ canvas: false });
    captureProcessingEntry();
    expect(takeProcessingEntry()).toBeNull();
  });
});
