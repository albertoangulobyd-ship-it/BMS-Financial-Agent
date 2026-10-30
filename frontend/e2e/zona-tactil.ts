// La zona tactil del control de la hoja plegada (peticion del dueno del 30-10-2026; bms.css,
// .sheet-fold button::before): una capa transparente que agranda el boton hacia abajo. Las ayudas
// de sus pruebas: quitarla (para comparar con lo de antes, pixel a pixel y medida a medida), el
// puntero grueso (el de una pantalla tactil, con la emulacion de Chromium) y la sonda que la mide
// con document.elementFromPoint: su caja, que cada punto de dentro es del control y que los
// vecinos (la fila de antes, lo de debajo y al lado, la ✕ del dialogo) siguen siendo suyos.
import type { CDPSession, Locator, Page } from '@playwright/test';

/** Sin la zona tactil (la regla de bms.css anulada), o con ella otra vez. Una hoja construida
 *  (adoptedStyleSheets): la CSP de la app no deja meter un <style>. */
export async function withoutHitArea(page: Page, off: boolean): Promise<void> {
  await page.evaluate((off) => {
    const w = window as unknown as { __bmsSinZona?: CSSStyleSheet };
    if (!w.__bmsSinZona) {
      w.__bmsSinZona = new CSSStyleSheet();
      w.__bmsSinZona.replaceSync('.sheet-fold button{position:static!important}.sheet-fold button::before{content:none!important}');
    }
    const sheet = w.__bmsSinZona;
    document.adoptedStyleSheets = [...document.adoptedStyleSheets.filter((s) => s !== sheet), ...(off ? [sheet] : [])];
  }, off);
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
