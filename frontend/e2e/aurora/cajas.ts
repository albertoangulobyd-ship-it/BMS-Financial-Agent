// Las cajas de la app contra las de Aurora (paso 17, especificacion §6.1): lo que mide
// herramientas/capture.cjs en el prototipo del dueno (e2e/aurora/referencia.json), medido igual en
// BMS, y comparado con las tolerancias de §6.1: x, y y ancho ±4 px (a `y` se le resta el alto de
// las bandas del servidor); el alto ±4 px salvo en lo que depende de los datos (solo que no pase de
// su tope); letra y color exactos; escala ±0,01. Lo usan aurora-paridad.spec.ts y procesar.spec.ts.
import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { capture, expect, settled } from '../fixtures';

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  font: string;
  ls: string;
  color: string;
  scale: number;
  display?: string;
  maxH?: number;
}
type Hidden = { display: 'none' };
type State = Record<string, Box | Hidden | number>;
export type Measured = Record<string, Box | Hidden>;

const REF = JSON.parse(readFileSync(new URL('./referencia.json', import.meta.url), 'utf8')) as Record<string, State>;

/** Los selectores de capture.cjs (los que se comparan). */
const SEL: Record<string, string> = {
  brand: '.bms-brand',
  aurora: '.aurora',
  welcomeH1: '.welcome-line h1',
  welcomeP: '.welcome-line p',
  composer: '.composer',
  composerArea: '.composer-area',
  send: '.send',
  discreet: '.discreet',
  navigation: '.navigation',
  navSelected: '.nav-item.selected',
  heroOrb: '.hero-orb',
  heroWave: '.hero-wave',
  panel: '.panel',
  detail: '.detail',
  conversation: '.conversation',
  bento: '.finance-bento',
  searchFilters: '.search-filters',
  searchResults: '.search-results',
  companion: '.ws-companion',
  wsTitle: '.ws-title-line h1',
  wsGrid: '.ws-grid',
  wsSidebar: '.ws-sidebar',
  wsProfile: '.ws-profile',
  dialog: '.ws-dialog',
  loader: '.document-loader',
  zurWorld: '.zur-world',
  pcReading: '.pc-reading',
  flowButton: '.flow-button',
  processingBack: '.processing-back',
  complete: '.processing-complete',
};

/** Lo que depende de los datos en todos los estados: solo el tope de su alto. */
const DATA_HEIGHT = ['panel', 'detail', 'wsGrid', 'wsSidebar', 'wsProfile', 'dialog'];
/** Lo que depende de los datos tambien en su `y`: la tarjeta va debajo de las filas del panel y
 *  el dialogo se centra segun su alto. */
const DATA_Y = ['detail', 'dialog'];
/** Lo que depende de los datos en cada estado (por su nombre, sin el ancho ni «-reduce»): el
 *  resumen y los resultados (sus filas; la columna de la busqueda los lleva dentro y crece con
 *  ellos, tambien en Aurora), la lectura de la tarjeta de Procesar (sus lineas), la columna de
 *  Procesar (lo que lleva dentro) y, en el resultado, el boton (va debajo de la lista). */
const BY_STATE: Record<string, { h?: string[]; y?: string[]; text?: string[] }> = {
  'E4-b': { h: ['bento'] },
  'E5-resultados': { h: ['searchResults', 'composerArea'] },
  'E5-filtros': { h: ['searchResults', 'composerArea'] },
  'E7-P0': { h: ['composerArea', 'pcReading'] },
  // Leyendo, «Volver al inicio» donde Aurora dice «Cancelar análisis» (punto 4 para el dueno,
  // especificacion §7): su ancho y su `x` (va centrado) son los de su texto.
  'E7-P4': { h: ['composerArea', 'pcReading'], text: ['processingBack'] },
  'E7-P5': { h: ['composerArea', 'complete'], y: ['flowButton'] },
};

/** Las medidas de la app, como capture.cjs mide Aurora (menos las bandas en `y`). */
export async function measure(page: Page): Promise<Measured> {
  await page.mouse.move(1, 1);
  await settled(page);
  return page.evaluate((sel) => {
    const bands = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bms-bandas')) || 0;
    const out: Record<string, unknown> = {};
    for (const [name, s] of Object.entries(sel)) {
      const el = document.querySelector(s);
      if (!el) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none') {
        out[name] = { display: 'none' };
        continue;
      }
      const r = el.getBoundingClientRect();
      const m = /matrix\(([-\d.e]+),\s*([-\d.e]+)/.exec(cs.transform);
      const scale = m ? Math.hypot(Number(m[1]), Number(m[2])) : 1;
      const hidden = r.width === 0 && r.height === 0;
      out[name] = {
        x: Math.round(r.x),
        y: Math.round(r.y - (hidden ? 0 : bands)),
        w: Math.round(r.width),
        h: Math.round(r.height),
        font: `${cs.fontWeight} ${cs.fontSize}/${cs.lineHeight} ${cs.fontFamily.split(',')[0]!.replace(/"/g, '')}`,
        ls: cs.letterSpacing,
        color: cs.color,
        scale,
        maxH: parseFloat(cs.maxHeight) || undefined,
      };
    }
    return out as Measured;
  }, SEL);
}

export interface CompareOptions {
  /** Lo que no se compara (lo que en este estado es nuestro, o ya se comparo). */
  skip?: string[];
  /** Con `anchor`, la `y` de cada uno se cuenta desde la de ese elemento (en Documentos, la marca:
   *  la pagina se desplaza). */
  anchor?: string;
  /** El nombre del estado en la captura, si no es el de la referencia (L0 se compara con E0). */
  as?: string;
}

/** Cada elemento contra Aurora, con las tolerancias de §6.1. */
export function compare(state: string, ours: Measured, options: CompareOptions = {}): string[] {
  const { skip = [], anchor } = options;
  const ref = REF[state];
  expect(ref, state).toBeDefined();
  const base = state.replace(/@\d+$/, '').replace(/-reduce$/, '');
  const dataHeight = new Set([...DATA_HEIGHT, ...(BY_STATE[base]?.h ?? [])]);
  const dataY = new Set([...DATA_Y, ...(BY_STATE[base]?.y ?? [])]);
  const ownText = new Set(BY_STATE[base]?.text ?? []);
  const out: string[] = [];
  const origin = (m: Record<string, unknown>) => (anchor ? ((m[anchor] as Box | undefined)?.y ?? 0) : 0);
  const [refY, ourY] = [origin(ref!), origin(ours)];
  for (const name of Object.keys(SEL)) {
    if (skip.includes(name)) continue;
    const a = ref![name] as Box | Hidden | undefined;
    if (!a) continue;
    const b = ours[name];
    if ('display' in a && a.display === 'none') {
      // Que no se vea: con display:none o sin montar (el <dialog> cerrado, lo que no esta).
      if (b && !('display' in b) && b.w > 0 && b.h > 0) out.push(`${name}: en Aurora no se ve (${b.x}, ${b.y}, ${b.w} × ${b.h})`);
      continue;
    }
    const want = a as Box;
    if (!b || 'display' in b) {
      out.push(`${name}: no esta`);
      continue;
    }
    const near = (k: 'x' | 'y' | 'w' | 'h') => Math.abs(k === 'y' ? b.y - ourY - (want.y - refY) : b[k] - want[k]) <= 4;
    for (const k of ['x', 'y', 'w'] as const) {
      if (k === 'y' && (dataY.has(name) || name === anchor)) continue;
      if (k !== 'y' && ownText.has(name)) continue;
      if (!near(k)) out.push(`${name}.${k}: ${b[k]} (Aurora ${want[k]})`);
    }
    if (dataHeight.has(name)) {
      if (b.maxH !== undefined && b.h > b.maxH + 1) out.push(`${name}.h: ${b.h} pasa de su tope ${b.maxH}`);
    } else if (!near('h')) out.push(`${name}.h: ${b.h} (Aurora ${want.h})`);
    if (b.font !== want.font) out.push(`${name}.font: ${b.font} (Aurora ${want.font})`);
    if (b.ls !== want.ls) out.push(`${name}.ls: ${b.ls} (Aurora ${want.ls})`);
    if (b.color !== want.color) out.push(`${name}.color: ${b.color} (Aurora ${want.color})`);
    if (Math.abs(b.scale - want.scale) > 0.01) out.push(`${name}.scale: ${b.scale} (Aurora ${want.scale})`);
  }
  return out;
}

/** Mide y compara: `expect` con la lista de diferencias vacia. Y una captura,
 *  CAPTURAS_DIR/<tema>/aurora-<estado>-<ancho>.png, para la hoja de contactos al lado de la de
 *  Aurora (e2e/aurora/hojas.mjs). */
export async function expectLikeAurora(page: Page, state: string, options: CompareOptions = {}): Promise<void> {
  const ours = await measure(page);
  const [name, width] = state.split('@');
  await capture(page, `aurora-${options.as ?? name}-${width}`);
  const ref = REF[state] ?? {};
  const names = Object.keys(SEL).filter((n) => ref[n] !== undefined && !(options.skip ?? []).includes(n));
  const hidden = names.filter((n) => (ref[n] as Hidden).display === 'none');
  // Para el registro: que se comparo (y lo que en Aurora no se ve).
  console.log(`${state}: ${names.length - hidden.length} cajas${hidden.length ? `; sin ver: ${hidden.join(', ')}` : ''}`);
  expect(compare(state, ours, options), state).toEqual([]);
}
