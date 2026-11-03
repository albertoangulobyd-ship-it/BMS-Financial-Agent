// Las zonas tactiles (peticiones del dueno del 30-10-2026, el control de la hoja plegada, y del
// 02-11-2026, los demas controles pequenos; bms.css): capas transparentes (::before) que agrandan
// lo que se pulsa sin verse ni mover nada, y el buscador de una lista, cuya caja crece con un
// margen negativo. Las ayudas de sus pruebas: quitarlas (para comparar con lo de antes, pixel a
// pixel y medida a medida), el puntero grueso (el de una pantalla tactil, con la emulacion de
// Chromium) y la sonda del control de la hoja plegada, que lo mide con document.elementFromPoint:
// su caja, que cada punto de dentro es del control y que los vecinos (la fila de antes, lo de
// debajo y al lado, la ✕ del dialogo) siguen siendo suyos.
import type { CDPSession, Locator, Page } from '@playwright/test';

/** Cada control con su zona: lo que es (para los mensajes), su selector, si la regla le pone
 *  position: relative (los que ya estaban posicionados no) y, si su zona es la caja misma (el
 *  buscador de una lista, que no tiene ::before, y «Abrir la ficha»), lo que la deja como antes. */
export interface Zone {
  name: string;
  selector: string;
  relative: boolean;
  box?: string;
}

export const ZONES: readonly Zone[] = [
  { name: 'el control de la hoja plegada', selector: '.sheet-fold button', relative: true },
  { name: 'los idiomas de la entrada', selector: '.discreet-languages button', relative: true },
  { name: 'la ✕ del panel', selector: '.panel-top button', relative: false, box: '.panel-top button{padding:0!important;margin:0!important}' },
  { name: 'la ✕ de la tarjeta de una fila', selector: '.detail-close', relative: false },
  { name: '«Filters wissen» de la busqueda', selector: '.filters-reset', relative: false, box: '.filters-reset{padding:0!important;margin:0 0 0 auto!important}' },
  { name: 'los tiradores del importe', selector: '.amount-thumb', relative: true },
  {
    name: 'el buscador de una lista',
    selector: '.ui-command-input input',
    relative: false,
    box: '.ui-command-input input{padding:0!important;margin:0!important}.ui-command-input input:focus-visible{outline-offset:6px!important}',
  },
  { name: '«Volver al espacio» de la conversacion', selector: '.conversation-top button', relative: false, box: '.conversation-top button{padding:0!important;margin:0!important}' },
  { name: '«Volver a Aurora» de Documentos', selector: 'a.ws-home', relative: false },
  { name: 'las migas de Documentos', selector: '.ws-breadcrumbs a', relative: false, box: '.ws-breadcrumbs a{padding:0!important;margin:0!important}.ws-breadcrumbs a:focus-visible{outline-offset:2px!important}' },
  { name: '«Abrir la ficha» de una carpeta', selector: '.ws-folder-caption > a', relative: false, box: '.ws-folder-caption>a{padding:0!important;margin:0!important}' },
  { name: 'la ✕ de una hoja', selector: '.ws-dialog-top button', relative: false, box: '.ws-dialog-top button{padding:0!important;margin:0!important}' },
  { name: '«Volver al inicio» de Procesar', selector: '.processing-back', relative: false },
];

/** Todas las zonas a la vez, en un selector. */
export const ZONE_SELECTOR = ZONES.map((z) => z.selector).join(', ');

/** La regla que las quita: lo de antes de bms.css, tal cual. */
const OFF = [
  `${ZONES.filter((z) => z.relative).map((z) => z.selector).join(',')}{position:static!important}`,
  `${ZONES.filter((z) => !z.box).map((z) => `${z.selector}::before`).join(',')}{content:none!important}`,
  ...ZONES.map((z) => z.box ?? ''),
  // El anillo del foco, donde lo ponen las hojas de Aurora (6 px los botones, 2 lo demas).
  '.panel-top button:focus-visible,.ws-dialog-top button:focus-visible,.conversation-top button:focus-visible,.filters-reset:focus-visible{outline-offset:6px!important}',
  '.ws-folder-caption>a:focus-visible{outline-offset:2px!important}',
].join('');

/** Sin las zonas tactiles (las reglas de bms.css anuladas), o con ellas otra vez. Una hoja
 *  construida (adoptedStyleSheets): la CSP de la app no deja meter un <style>. */
export async function withoutHitArea(page: Page, off: boolean): Promise<void> {
  await page.evaluate(
    ([off, css]) => {
      const w = window as unknown as { __bmsSinZona?: CSSStyleSheet };
      if (!w.__bmsSinZona) {
        w.__bmsSinZona = new CSSStyleSheet();
        w.__bmsSinZona.replaceSync(css as string);
      }
      const sheet = w.__bmsSinZona;
      document.adoptedStyleSheets = [...document.adoptedStyleSheets.filter((s) => s !== sheet), ...(off ? [sheet] : [])];
    },
    [off, OFF] as const
  );
}

const sessions = new WeakMap<Page, CDPSession>();

/** El puntero grueso, (pointer: coarse), como en una pantalla tactil, o el raton otra vez. */
export async function coarsePointer(page: Page, on: boolean): Promise<void> {
  let cdp = sessions.get(page);
  if (!cdp) {
    cdp = await page.context().newCDPSession(page);
    sessions.set(page, cdp);
  }
  await cdp.send('Emulation.setTouchEmulationEnabled', on ? { enabled: true, maxTouchPoints: 1 } : { enabled: false });
  const coarse = await page.evaluate(() => matchMedia('(pointer: coarse)').matches);
  if (coarse !== on) throw new Error(`(pointer: coarse) deberia ser ${on}`);
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface HitProbe {
  /** La caja del boton, lo que se ve (13,5 px de alto). */
  text: Box;
  /** La de la zona, segun su estilo (::before). */
  area: Box;
  /** La que da elementFromPoint: de donde a donde el punto es del control. */
  measured: Box;
  /** Lo que no es como debe: un punto de la zona que no es del control, o uno de un vecino que si. */
  misses: string[];
}

/**
 * Mide la zona tactil del control (el boton de `fold`) con elementFromPoint, con el control a la
 * vista en el centro del dialogo: la caja medida (al pixel: elementFromPoint redondea), cada punto
 * de una rejilla (cada 2 px de alto y 4 de ancho, y a 1 px de los bordes) dentro de ella es del
 * control, y los vecinos siguen siendo suyos: la
 * fila de antes (pegada encima), lo de debajo (la tarjeta de una fila, si esta abierta, y su ✕),
 * lo de al lado y, con el dialogo arriba del todo, su ✕.
 */
export async function probeHitArea(fold: Locator): Promise<HitProbe> {
  await fold.evaluate((b) => b.scrollIntoView({ block: 'center' }));
  const probe = await fold.evaluate((btn) => {
    const misses: string[] = [];
    const dialog = btn.closest('dialog')!;
    const line = btn.parentElement!;
    const row = line.previousElementSibling as HTMLElement;
    const at = (x: number, y: number) => document.elementFromPoint(x, y);
    const ours = (x: number, y: number) => btn.contains(at(x, y));
    const b = btn.getBoundingClientRect();
    const s = getComputedStyle(btn, '::before');
    const area = { x: b.left + parseFloat(s.left), y: b.top + parseFloat(s.top), width: parseFloat(s.width), height: parseFloat(s.height) };
    // Lo medido: una columna y una fila de puntos, cada 0,25 px, en el centro de la zona.
    const cx = area.x + Math.min(area.width / 2, 6);
    const cy = area.y + area.height / 2;
    const ys = [] as number[];
    for (let y = b.top - 6; y <= b.top + 64; y += 0.25) if (ours(cx, y)) ys.push(y);
    const xs = [] as number[];
    for (let x = b.left - 6; x <= b.right + 64; x += 0.25) if (ours(x, cy)) xs.push(x);
    const measured = { x: xs[0]!, y: ys[0]!, width: xs[xs.length - 1]! - xs[0]! + 0.25, height: ys[ys.length - 1]! - ys[0]! + 0.25 };
    // La rejilla de dentro, a un pixel de cada borde, y los vecinos, a dos por fuera:
    // elementFromPoint redondea el punto al pixel (como el raton y el dedo).
    const left = area.x + 1;
    const right = area.x + area.width - 1;
    const top = area.y + 1;
    const bottom = area.y + area.height - 1;
    const steps = (from: number, to: number, step: number) => {
      const out: number[] = [];
      for (let v = from; v < to; v += step) out.push(v);
      out.push(to);
      return out;
    };
    const gridX = steps(left, right, 4);
    const gridY = steps(top, bottom, 2);
    for (const y of gridY) for (const x of gridX) if (!ours(x, y)) misses.push(`(${x.toFixed(1)}, ${y.toFixed(1)}) no es del control: ${at(x, y)?.outerHTML.slice(0, 60)}`);
    // La fila de antes, pegada encima: su borde de abajo y algo mas arriba.
    for (const dy of [2, 8]) for (const x of gridX) if (!row.contains(at(x, area.y - dy))) misses.push(`(${x.toFixed(1)}, -${dy}) no es la fila de antes`);
    // Al lado (a la izquierda, el aire del dialogo; a la derecha, la linea del control).
    for (const y of gridY) {
      if (ours(area.x - 2, y)) misses.push(`a la izquierda (${y.toFixed(1)}) es del control`);
      if (ours(area.x + area.width + 2, y)) misses.push(`a la derecha (${y.toFixed(1)}) es del control`);
    }
    // Debajo: ya no es del control; la tarjeta de una fila, si esta, sigue siendo suya entera.
    const view = dialog.getBoundingClientRect();
    const below = area.y + area.height + 2;
    if (below < view.bottom) for (const x of gridX) if (ours(x, below)) misses.push(`debajo (${x.toFixed(1)}) es del control`);
    const card = dialog.querySelector<HTMLElement>('.detail');
    let gap: number | null = null;
    if (card) {
      const c = card.getBoundingClientRect();
      gap = c.top - (area.y + area.height);
      if (gap < 0) misses.push(`la zona pisa la tarjeta (${gap.toFixed(2)} px)`);
      // Fuera de sus esquinas redondeadas (12 px), que no son de nadie.
      for (const x of gridX.filter((x) => x > c.left + 12 && x < c.right - 12)) if (c.top + 2 < view.bottom && !card.contains(at(x, c.top + 2))) misses.push(`el borde de la tarjeta (${x.toFixed(1)}) no es de la tarjeta`);
      const close = card.querySelector<HTMLElement>('.detail-close')!.getBoundingClientRect();
      const [kx, ky] = [close.left + close.width / 2, close.top + close.height / 2];
      if (ky > view.top && ky < view.bottom && !card.querySelector('.detail-close')!.contains(at(kx, ky))) misses.push('la ✕ de la tarjeta no es suya');
    }
    // La ✕ del dialogo, con el dialogo arriba del todo (y luego donde estaba).
    const scroll = dialog.scrollTop;
    dialog.scrollTop = 0;
    const x = dialog.querySelector<HTMLElement>('.ws-dialog-top button')!;
    const k = x.getBoundingClientRect();
    if (!x.contains(at(k.left + k.width / 2, k.top + k.height / 2))) misses.push('la ✕ del dialogo no es suya');
    dialog.scrollTop = scroll;
    return { text: { x: b.left, y: b.top, width: b.width, height: b.height }, area, measured, misses };
  });
  return probe;
}

/** "167 × 27,5" (ancho × alto, en px). */
export const size = (b: Box) => `${Math.round(b.width * 100) / 100} × ${Math.round(b.height * 100) / 100}`;
