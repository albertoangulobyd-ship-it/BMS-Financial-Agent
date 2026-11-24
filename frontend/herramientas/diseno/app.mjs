// app.mjs — moverse por la app como una persona (el orbe, la rueda, las filas, Escape), para
// las dos herramientas: capturar.mjs (el fichero de diseno) y comparacion.mjs (las fotos del
// tema claro). Elige por la estructura del DOM de la app (como e2e/nav.ts) y, donde hace falta
// decir que fila, por su texto en neerlandes (el idioma de las dos herramientas).
//
// `v` es la vista: { pagina (Page), srv (el de comun.servidor), ancho (1440 | 400), tema }.
import { espera } from './comun.mjs';

const APP = '[data-aurora-root] .app';
const PANEL = 'aside.panel';
const HOJA = 'dialog.ws-dialog[open]';

/** Los textos de la app (frontend/src/i18n/nl.ts) por los que se elige una fila. */
export const NL = {
  teBevestigen: 'Te bevestigen',
  dezeWeek: 'Deze week',
  betalingVastleggen: 'Betaling vastleggen',
  reden: 'Reden',
  overzicht: 'Geef me een overzicht',
  systeem: 'Systeem',
  facturenmailbox: 'Facturenmailbox',
  automatischLezen: 'Automatisch lezen',
};

// ------------------------------------------------------------------ lo basico

/** La pantalla quieta, mirada una vez (como settled() de e2e/fixtures.ts): ninguna animacion con
 *  fin en marcha, una sola pantalla entera, sin vuelo del orbe ni fundidos a medias. */
const QUIETA = () => {
  const corriendo = document.getAnimations().filter((a) => {
    if (a.playState !== 'running') return false;
    const fin = a.effect?.getComputedTiming().endTime;
    return typeof fin === 'number' && Number.isFinite(fin);
  });
  if (corriendo.length > 0) return false;
  const pantallas = Array.from(document.querySelectorAll('[data-aurora-root] > .app-screen'));
  if (pantallas.length > 1 || pantallas.some((el) => getComputedStyle(el).opacity !== '1')) return false;
  if (document.querySelector('.aurora-route-flight, .typing-dots')) return false;
  return !Array.from(document.querySelectorAll('[style*="opacity"]')).some((el) => {
    const o = el.style.opacity;
    return o !== '' && Number(o) > 0 && Number(o) < 1;
  });
};

/** Espera a que no quede ninguna peticion a /api en camino y la pantalla este quieta. */
export async function quieta(v, max = 12_000) {
  const fin = Date.now() + max;
  let calma = 0;
  while (Date.now() < fin) {
    const ok = v.pendientes.size === 0 && (await v.pagina.evaluate(QUIETA).catch(() => false));
    calma = ok ? calma + 1 : 0;
    if (calma >= 4) return true;
    await espera(60);
  }
  v.avisos.push(`no se queda quieta (${v.donde ?? ''})`);
  return false;
}

export async function hasta(v, que, condicion, max = 15_000) {
  const fin = Date.now() + max;
  let ultimo;
  while (Date.now() < fin) {
    try {
      ultimo = await condicion();
      if (ultimo) return ultimo;
    } catch (error) {
      ultimo = error;
    }
    await espera(60);
  }
  throw new Error(`no llega «${que}» (${v.donde ?? ''})${ultimo instanceof Error ? `: ${ultimo.message.split('\n')[0]}` : ''}`);
}

export const $ = (v, selector) => v.pagina.locator(selector);

/** Un clic de persona; si lo que hay que pulsar no para quieto o lo tapa otra cosa (el abanico
 *  de una carpeta, una fila a 400 px), su evento de clic. */
export async function clic(v, lugar) {
  try {
    await lugar.click({ timeout: 3000 });
  } catch {
    await lugar.evaluate((el) => el.click());
  }
}

const clase = (v) => $(v, APP).first().getAttribute('class').then((c) => c ?? '', () => '');
const pantalla = (v) => $(v, '[data-aurora-root]').first().getAttribute('data-screen').catch(() => null);
export const temaVisto = (v) => v.pagina.evaluate(() => (document.documentElement.classList.contains('dark') ? 'dark' : 'light'));

/** Una vista nueva sobre una pagina: cuenta las peticiones a /api en camino y apunta lo raro. */
export function vista(pagina, srv, ancho, tema) {
  const v = { pagina, srv, ancho, tema, pendientes: new Set(), avisos: [], errores: [] };
  pagina.on('request', (r) => {
    if (r.url().includes('/api/')) v.pendientes.add(r);
  });
  const fuera = (r) => v.pendientes.delete(r);
  pagina.on('requestfinished', fuera);
  pagina.on('requestfailed', fuera);
  pagina.on('pageerror', (e) => v.errores.push(`pageerror: ${e.message}`));
  pagina.on('console', (m) => {
    if (m.type() === 'error') v.errores.push(`console: ${m.text()}`);
  });
  return v;
}

// ------------------------------------------------------------------ entrar, el tema y moverse

/** La pantalla de entrada (sin entrar). */
export async function aLaEntrada(v) {
  v.donde = 'entrada';
  await v.pagina.goto(`${v.srv.base}/app`);
  await hasta(v, 'la entrada', () => $(v, '#token').isVisible());
  await quieta(v);
}

/** Entra con el codigo de Ana (administradora): el saludo. */
export async function entrar(v) {
  if (!(await $(v, '#token').count())) await aLaEntrada(v);
  await $(v, '#token').fill(v.srv.tokens['Ana Demo']);
  await clic(v, $(v, '#login-submit'));
  await hasta(v, 'el inicio', async () => (await $(v, '#token').count()) === 0 && (await $(v, APP).count()) > 0);
  await quieta(v);
}

async function aAurora(v) {
  if ((await pantalla(v)) === 'work') {
    for (let i = 0; i < 4 && (await $(v, HOJA).count()); i += 1) {
      await v.pagina.keyboard.press('Escape');
      await espera(250);
    }
    await clic(v, $(v, 'a.ws-home'));
    await hasta(v, 'el espacio de Aurora', async () => (await pantalla(v)) === 'home');
  }
  await quieta(v);
}

/** El inicio (E0): sin rueda, panel, conversacion, busqueda ni Procesar. */
export async function aInicio(v) {
  await aAurora(v);
  for (let i = 0; i < 6; i += 1) {
    const c = await clase(v);
    if (!/\b(navigating|has-panel|chatting|search-mode|conversation-mode|process-mode)\b/.test(c)) break;
    if (/\bprocess-mode\b/.test(c)) await clic(v, $(v, '.processing-back'));
    else if (await $(v, '.conversation-top button').count()) await clic(v, $(v, '.conversation-top button').first());
    else {
      // Con Procesar en el centro el orbe entra en Procesar: antes, otra entrada al centro.
      if (/\bprocess-highlight\b/.test(c)) await centrar(v, 'vat');
      await clic(v, $(v, 'button.aurora'));
    }
    await hasta(v, 'otro estado', async () => (await clase(v)) !== c);
    await quieta(v);
  }
  await v.pagina.evaluate(() => window.scrollTo(0, 0));
  await quieta(v);
}

/** La rueda abierta y sin panel (E1). */
export async function abrirRueda(v) {
  await aAurora(v);
  const c = await clase(v);
  if (/\bhas-panel\b/.test(c)) await clic(v, $(v, `${PANEL} .panel-top button`));
  else if (!/\bnavigating\b/.test(c) || /\b(chatting|search-mode|process-mode)\b/.test(c)) {
    await aInicio(v);
    await clic(v, $(v, 'button.discreet'));
  }
  await hasta(v, 'la rueda', async () => (await $(v, 'section.navigation').isVisible()) && (await $(v, PANEL).count()) === 0);
  await quieta(v);
}

async function centrar(v, id) {
  const boton = $(v, `.navigation .nav-item[data-entry="${id}"]`);
  if ((await boton.getAttribute('aria-current')) !== 'true') {
    await boton.focus();
    await hasta(v, `${id} en el centro`, async () => (await boton.getAttribute('aria-current')) === 'true');
  }
  await quieta(v);
}

/** Abre una entrada de la rueda (home, receivables, payables, vat, settings, documents, search, process). */
export async function entrada(v, id) {
  await abrirRueda(v);
  await centrar(v, id);
  await clic(v, $(v, `.navigation .nav-item[data-entry="${id}"]`));
  if (id === 'documents') await hasta(v, 'Documenten', async () => (await pantalla(v)) === 'work' && (await $(v, '.ws-grid').count()) > 0);
  else if (id === 'process') {
    await hasta(v, 'Verwerken', async () => /\bprocess-mode\b/.test(await clase(v)) && (await $(v, '.processing-workspace').isVisible()));
    // La entrada de la suricata (las particulas, el monticulo, la cabeza): unos 2,6 s.
    await hasta(v, 'el boton de Verwerken', () => $(v, '.flow-button').isVisible(), 20_000);
    await espera(3200);
  } else if (id === 'search') await hasta(v, 'Zoeken', async () => /\bsearch-mode\b/.test(await clase(v)));
  else await hasta(v, `el panel de ${id}`, () => $(v, `${PANEL} h2`).isVisible());
  await quieta(v);
}

/** El tema, en Ajustes > Tema (sus filas: oscuro, claro y el del sistema). */
export async function ponerTema(v, tema) {
  if ((await temaVisto(v)) === tema) return;
  await entrada(v, 'settings');
  await clic(v, filasPanel(v).nth(1));
  await quieta(v);
  await clic(v, filasPanel(v).nth({ dark: 0, light: 1 }[tema]));
  await hasta(v, `el tema ${tema}`, async () => (await temaVisto(v)) === tema);
  await quieta(v);
  await aInicio(v);
}

/** Sale (Ajustes > Uitloggen): la pantalla de entrada. */
export async function salir(v) {
  await entrada(v, 'settings');
  await clic(v, $(v, `${PANEL} > button.outline`).last());
  await hasta(v, 'la entrada', () => $(v, '#token').isVisible());
  await quieta(v);
}

// ------------------------------------------------------------------ los paneles

export const filasPanel = (v) => $(v, `${PANEL} button.doc`);

/** La fila del panel que dice `texto` en su titulo. */
export const filaPanel = (v, texto) => $(v, `${PANEL} button.doc`).filter({ has: v.pagina.locator('strong').getByText(texto, { exact: true }) });

const firmaPanel = (v) =>
  v.pagina.evaluate((sel) => {
    const p = document.querySelector(sel);
    if (!p) return '';
    const filas = [...p.querySelectorAll('button.doc')].filter((b) => !b.closest('.detail'));
    return [p.querySelector('h2')?.textContent, p.querySelector('.list-title')?.textContent, filas.length, filas[0]?.textContent].join('|');
  }, PANEL);

/** Pulsa una fila del panel y espera a lo que traiga (otra vista o una tarjeta). */
export async function pulsarFila(v, fila) {
  await clic(v, fila);
  await quieta(v);
}

/**
 * Abre una tarjeta en el panel que se ve: baja por la primera fila de cada vista (hasta tres
 * niveles) hasta que una fila abre una tarjeta (.detail). `rutas` son los caminos a probar,
 * cada uno una lista de indices de fila.
 */
export async function abrirTarjetaDelPanel(v, id, rutas) {
  for (const ruta of rutas) {
    await entrada(v, id);
    let bien = true;
    for (const n of ruta) {
      const fila = filasPanel(v).nth(n);
      if (!(await fila.count())) {
        bien = false;
        break;
      }
      await pulsarFila(v, fila);
      if ((await pantalla(v)) !== 'home' || !(await $(v, PANEL).count())) {
        bien = false;
        break;
      }
    }
    if (bien && (await $(v, `${PANEL} .detail`).count())) return ruta;
    await aInicio(v);
  }
  throw new Error(`ninguna fila del panel ${id} abre una tarjeta (rutas ${JSON.stringify(rutas)})`);
}

// ------------------------------------------------------------------ la conversacion y la busqueda

const caja = (v) => $(v, `${APP} input`).first();

/** Escribe en la caja e Intro, y espera la respuesta. */
export async function preguntar(v, texto) {
  await caja(v).fill(texto);
  await caja(v).press('Enter');
  await hasta(v, 'la conversacion', () => $(v, '.conversation').isVisible());
  await hasta(v, 'la respuesta', async () => (await $(v, '.typing-dots').count()) === 0 && v.pendientes.size === 0, 25_000);
  await quieta(v);
}

/** La hoja de una factura por su numero: se pregunta en el inicio y se pulsa su fila (el vuelo
 *  a su carpeta en Documenten), como openInvoice() de e2e/nav.ts. */
export async function abrirFactura(v, numero) {
  await aInicio(v);
  await preguntar(v, numero);
  const fila = $(v, '.conversation .chat-rows a.search-result').first();
  await hasta(v, `la fila de ${numero}`, () => fila.count());
  await clic(v, fila);
  await hasta(v, 'la hoja de la factura', async () => (await pantalla(v)) === 'work' && (await $(v, `${HOJA} .ws-file-table`).count()) > 0, 25_000);
  await quieta(v);
}

export const pliegue = (v) => $(v, `${HOJA} [data-testid=sheet-fold] button`);

export async function desplegar(v) {
  const p = pliegue(v);
  if ((await p.count()) && (await p.first().getAttribute('aria-expanded')) !== 'true') {
    await clic(v, p.first());
    await quieta(v);
  }
}

// ------------------------------------------------------------------ Documenten

/** Un nodo del arbol «Verkennen» por lo que dice. */
export const nodo = (v, texto) => v.pagina.getByRole('treeitem').filter({ has: v.pagina.locator('.tree-label').getByText(texto, { exact: true }) });

/** La ficha de una empresa desde el arbol (openFolder() de e2e/nav.ts). */
export async function abrirFicha(v, nombre, grupo) {
  if ((await pantalla(v)) !== 'work') await entrada(v, 'documents');
  const g = nodo(v, grupo).first();
  if ((await g.getAttribute('aria-expanded')) !== 'true') await clic(v, g);
  await clic(v, nodo(v, nombre).first());
  await hasta(v, `la ficha de ${nombre}`, () => $(v, '.ws-profile').isVisible());
  await quieta(v);
}

export { APP, PANEL, HOJA, clase, pantalla };
