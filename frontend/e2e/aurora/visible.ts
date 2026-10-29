// Que se ve de verdad (especificacion §1.1 y §6.4): la regla del dueno, «o el menu o una
// pantalla», mirada desde la pagina. Un elemento se ve cuando se cumplen las tres cosas a la vez:
// 1. su caja (getBoundingClientRect) tiene area y corta la ventana (con display:none, o un
//    antepasado con display:none, la caja sale vacia);
// 2. su visibility calculada es visible;
// 3. su opacidad efectiva pasa de 0,01: el producto de la opacity calculada del elemento y de
//    todos sus antepasados hasta <html>. No basta la suya: el fundido de salida de 0,18 s de Root
//    anima la .app-screen que se va, que es un antepasado de la rueda, y la rueda conserva su
//    opacity 1 durante todo el fundido.
// El ayudante se instala en la pagina (window.__bmsVisible) antes de que cargue la app; lo usan
// exclusividad.spec.ts en cada estado y en cada cuadro, y su propia prueba (que el fundido de
// E1 → E6 baja la opacidad efectiva de la rueda de 1 a 0 con la suya en 1).
// Ademas, lo que ya no existe (§6.5), en cada estado: ni cabecera de la app, ni navegacion
// compacta, ni pastillas de seccion, ni paleta; nada arriba a la derecha en E0 ni en E1; migas
// solo dentro de Documentos; «Datos de prueba» solo en la banda y en .sample-label; nada de IBM
// Plex; ningun backdrop-filter que no sea de Aurora; y nada de «Cargando…».
import type { Page } from '@playwright/test';

/** Lo que se ve en un cuadro. */
export interface Frame {
  /** performance.now() del cuadro. */
  t: number;
  /** La rueda se ve. */
  menu: boolean;
  /** La opacidad efectiva mas alta de sus filas (0 si no esta). */
  menuOpacity: number;
  /** La opacity calculada de .navigation (la suya, sin antepasados). */
  menuOwn: number | null;
  /** La rueda esta en la pantalla que se va (el fundido de Root). */
  menuLeaving: boolean;
  /** Las pantallas que se ven: panel, conversation, search, work, process. */
  screens: string[];
  /** La pantalla que se va recibe clics (pointer-events distinto de none). */
  leavingClickable: boolean;
  /** Lo que hay bajo el centro de la fila activa de la rueda que se va (si se va): una fila de
   *  la rueda (mal: recibiria el clic) u otra cosa. */
  underLeavingRow: 'wheel' | 'other' | null;
  /** Un texto de carga a la vista («Cargando…», «Laden…», «Loading…»). */
  loading: boolean;
}

/** El codigo del ayudante, tal cual se instala en la pagina. */
const SOURCE = `(() => {
  const SCREENS = {
    panel: 'aside.panel',
    conversation: '.conversation',
    search: '.search-workspace',
    work: '.ws-layout',
    process: '.processing-workspace',
  };
  const LOADING = /^(Cargando|Laden|Loading)…$/;
  const effectiveOpacity = (el) => {
    let o = 1;
    for (let e = el; e; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity);
    return o;
  };
  const boxShown = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight;
  };
  const visible = (el) => !!el && el.isConnected && boxShown(el) && getComputedStyle(el).visibility === 'visible' && effectiveOpacity(el) > 0.01;
  const any = (sel) => Array.from(document.querySelectorAll(sel)).some(visible);
  const root = () => document.querySelector('[data-aurora-root]');
  const leavingScreens = () => {
    const r = root();
    const now = r ? r.getAttribute('data-screen') : null;
    return Array.from(document.querySelectorAll('[data-aurora-root] > .app-screen')).filter((s) => s.getAttribute('data-screen') !== now);
  };
  const textNodes = function* () {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) if (n.nodeValue && n.nodeValue.trim()) yield n;
  };
  const frame = () => {
    const rows = Array.from(document.querySelectorAll('.navigation .nav-item'));
    const shownRows = rows.filter(visible);
    const nav = document.querySelector('.navigation');
    const leaving = leavingScreens();
    const menuLeaving = !!nav && leaving.some((s) => s.contains(nav));
    let underLeavingRow = null;
    const active = document.querySelector('.navigation .nav-item.selected');
    if (menuLeaving && active && visible(active)) {
      const r = active.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      underLeavingRow = hit && hit.closest('.navigation') ? 'wheel' : 'other';
    }
    let loading = false;
    for (const n of textNodes()) {
      if (LOADING.test(n.nodeValue.trim()) && n.parentElement && visible(n.parentElement)) { loading = true; break; }
    }
    return {
      t: performance.now(),
      menu: shownRows.length > 0,
      menuOpacity: shownRows.reduce((m, e) => Math.max(m, effectiveOpacity(e)), 0),
      menuOwn: nav ? parseFloat(getComputedStyle(nav).opacity) : null,
      menuLeaving,
      screens: Object.entries(SCREENS).filter(([, sel]) => any(sel)).map(([name]) => name),
      leavingClickable: leaving.some((s) => getComputedStyle(s).pointerEvents !== 'none'),
      underLeavingRow,
      loading,
    };
  };
  // Lo que ya no existe (§6.5). \`home\`: E0 o E1 (nada arriba a la derecha).
  const ALLOWED_BLUR = '.ui-popover, .chat-export, .gf-front, .gf-key--more, .gf-menu, .fpb .glass';
  const GONE = '.app-shell, .app-header, .page-header, .compact-nav, .section-nav, .section-pills, .command-palette, [cmdk-dialog], .account-menu, .test-data-chip, .data-table, .summary-card, .help-tip';
  const gone = (home) => {
    const out = [];
    for (const el of document.querySelectorAll(GONE)) out.push('quitado: ' + el.className);
    const bands = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bms-bandas')) || 0;
    if (home) {
      // Ni iniciales ni boton de la cuenta (§1.2): lo de Aurora (la marca, la rueda) no cuenta.
      for (const el of document.querySelectorAll('button, a, [role=button], img, [role=img]')) {
        if (!visible(el) || el.closest('.navigation, .bms-brand')) continue;
        const r = el.getBoundingClientRect();
        if (r.left > innerWidth - 320 && r.top < bands + 140) out.push('arriba a la derecha: ' + (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().slice(0, 40));
      }
    }
    for (const el of document.querySelectorAll('.ws-breadcrumbs, [aria-label] nav, nav')) {
      const label = (el.getAttribute('aria-label') || '').toLowerCase();
      const crumbs = el.classList.contains('ws-breadcrumbs') || /miga|kruimel|breadcrumb|dónde estás|waar je bent|where you are/.test(label);
      if (crumbs && visible(el) && !el.closest('.ws-layout')) out.push('migas fuera de Documentos');
    }
    for (const n of textNodes()) {
      const p = n.parentElement;
      if (!p || !visible(p)) continue;
      const text = n.nodeValue.trim();
      if (/datos de prueba|testgegevens|test data/i.test(text) && !p.closest('.bms-banda, .sample-label')) out.push('datos de prueba fuera de la banda: ' + text.slice(0, 40));
      if (/Plex/i.test(getComputedStyle(p).fontFamily)) out.push('IBM Plex: ' + text.slice(0, 30));
      if (LOADING.test(text)) out.push('texto de carga: ' + text);
    }
    for (const el of document.querySelectorAll('body *')) {
      const f = getComputedStyle(el).backdropFilter;
      if (f && f !== 'none' && !el.matches(ALLOWED_BLUR) && visible(el)) out.push('backdrop-filter: ' + el.className + ' ' + f);
    }
    return out;
  };
  window.__bmsVisible = { effectiveOpacity, visible, frame, gone };
})()`;

/** Instala el ayudante en la pagina (antes de cargarla: sigue al recargar). */
export async function installVisible(page: Page): Promise<void> {
  await page.addInitScript(SOURCE);
}

/** Lo que se ve ahora. */
export async function seen(page: Page): Promise<Frame> {
  return page.evaluate(() => (window as unknown as { __bmsVisible: { frame: () => Frame } }).__bmsVisible.frame());
}

/** Lo que ya no existe y aun se ve (§6.5): la lista de lo que falla. `home`: E0 o E1. */
export async function goneViolations(page: Page, home = false): Promise<string[]> {
  return page.evaluate((h) => (window as unknown as { __bmsVisible: { gone: (home: boolean) => string[] } }).__bmsVisible.gone(h), home);
}

/** Empieza a apuntar cada cuadro (rAF) hasta que se pidan. */
export async function startFrames(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as { __bmsFrames: Frame[] | null; __bmsVisible: { frame: () => Frame } };
    const frames: Frame[] = [];
    w.__bmsFrames = frames;
    const tick = () => {
      if (w.__bmsFrames !== frames) return;
      frames.push(w.__bmsVisible.frame());
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

/** Los cuadros apuntados desde startFrames (y deja de apuntar). */
export async function takeFrames(page: Page): Promise<Frame[]> {
  return page.evaluate(() => {
    const w = window as unknown as { __bmsFrames: Frame[] | null };
    const out = w.__bmsFrames ?? [];
    w.__bmsFrames = null;
    return out;
  });
}

/** Lo montado en un render (no lo que se ve): para los cambios que tienen que ser uno solo (F8 y
 *  F9, §1.5 y §6.4). */
export interface Render {
  wheel: boolean;
  hasPanel: boolean;
  panel: boolean;
  conversation: boolean;
  search: boolean;
  process: boolean;
}

/** Empieza a apuntar cada render (un MutationObserver: lo que React deja en el DOM al terminar
 *  cada cambio) y cada cuadro (rAF). */
export async function startRenders(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as { __bmsRenders: Render[] | null; __bmsRenderStop: (() => void) | null };
    const out: Render[] = [];
    w.__bmsRenders = out;
    const take = () => {
      const app = document.querySelector('[data-aurora-root] .app');
      out.push({
        wheel: !!document.querySelector('.navigation'),
        hasPanel: !!app && app.classList.contains('has-panel'),
        panel: !!document.querySelector('aside.panel'),
        conversation: !!document.querySelector('.conversation'),
        search: !!document.querySelector('.search-workspace'),
        process: !!document.querySelector('.processing-workspace'),
      });
    };
    const observer = new MutationObserver(take);
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
    let raf = 0;
    const tick = () => {
      take();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    w.__bmsRenderStop = () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
    };
    take();
  });
}

/** Los renders apuntados (y deja de apuntar). */
export async function takeRenders(page: Page): Promise<Render[]> {
  return page.evaluate(() => {
    const w = window as unknown as { __bmsRenders: Render[] | null; __bmsRenderStop: (() => void) | null };
    w.__bmsRenderStop?.();
    const out = w.__bmsRenders ?? [];
    w.__bmsRenders = null;
    return out;
  });
}

/** Lo que no puede pasar en ningun render de un cambio que es uno solo: la rueda montada sin
 *  .has-panel, la conversacion y el panel, el panel y la busqueda, Procesar y el panel. */
export function renderViolations(renders: Render[]): string[] {
  const out = new Set<string>();
  for (const r of renders) {
    if (r.wheel && !r.hasPanel) out.add('la rueda montada sin .has-panel');
    if (r.conversation && r.panel) out.add('la conversacion y el panel');
    if (r.panel && r.search) out.add('el panel y la busqueda');
    if (r.process && r.panel) out.add('Procesar y el panel');
  }
  return [...out];
}
