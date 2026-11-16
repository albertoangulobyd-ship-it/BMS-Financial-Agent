// gira.mjs — la gira por la app, UNA para las dos herramientas: grabar.mjs la da sobre el
// servidor de verdad (y graba cada respuesta de /api/v2) y comprobar.mjs la da sobre la vista
// previa (donde todo lo que pida tiene que estar grabado). Asi lo que se comprueba es lo que se
// grabo. Se mueve como una persona (el orbe, la rueda, las filas, Escape) y elige por la
// estructura (clases y atributos del DOM de la app), no por los textos: vale en los tres idiomas
// y con cualquier base de prueba. Lo que escribe (un numero de factura, la pregunta del resumen)
// sale de lo que se ve o de las tres preguntas de e2e/conversacion.spec.ts.
//
// `v` es la vista: { pagina (Page), marco (Page o Frame: donde vive la app), pendientes() (las
// peticiones a /api en camino), grabando (true con el servidor de verdad) }.
import { espera } from './comun.mjs';

export const IDIOMAS = ['nl', 'es', 'en'];
export const NOMBRES_IDIOMA = { nl: 'Nederlands', en: 'English', es: 'Español' };
/** Las preguntas que traen el resumen general (el bento), como en e2e/conversacion.spec.ts. */
export const PREGUNTA_RESUMEN = { nl: 'Geef me een overzicht', es: 'Dame un resumen general', en: 'Give me an overview' };
export const ENTRADAS_PANEL = ['home', 'receivables', 'payables', 'vat', 'settings'];

const APP = '[data-aurora-root] .app';
const PANEL = 'aside.panel';
const HOJA = 'dialog.ws-dialog[open]';

// ------------------------------------------------------------------ lo basico

/** La pantalla quieta, mirada una vez: ninguna animacion con fin en marcha, una sola pantalla
 *  entera, sin vuelo del orbe, sin fundidos a medias y sin los puntos de «escribiendo». */
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

/** Espera a que no quede ninguna peticion en camino y la pantalla este quieta. */
export async function quieta(v, max = 12_000) {
  const fin = Date.now() + max;
  let calma = 0;
  while (Date.now() < fin) {
    const ok = (await v.pendientes()) === 0 && (await v.marco.evaluate(QUIETA).catch(() => false));
    calma = ok ? calma + 1 : 0;
    if (calma >= 3) return true;
    await espera(50);
  }
  v.avisos?.push(`no se queda quieta (${v.donde ?? ''})`);
  return false;
}

/** Espera a que `condicion` (una funcion que mira) sea verdad. */
async function hasta(v, que, condicion, max = 12_000) {
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
  throw new Error(`gira: no llega «${que}» (${v.donde ?? ''})${ultimo instanceof Error ? `: ${ultimo.message.split('\n')[0]}` : ''}`);
}

const $ = (v, selector) => v.marco.locator(selector);

/** Un clic de persona; si lo que hay que pulsar no para quieto o lo tapa otra cosa (el abanico
 *  de una carpeta, una pestana a 400 px), su evento de clic. */
async function clic(v, lugar) {
  try {
    await lugar.click({ timeout: 2500 });
  } catch {
    await lugar.evaluate((el) => el.click());
  }
}

const clase = (v) => $(v, APP).first().getAttribute('class').then((c) => c ?? '', () => '');
const pantalla = (v) => $(v, '[data-aurora-root]').first().getAttribute('data-screen').catch(() => null);
export const idiomaVisto = (v) => v.marco.evaluate(() => document.documentElement.lang || 'nl');
export const temaVisto = (v) => v.marco.evaluate(() => document.documentElement.dataset.theme ?? (document.documentElement.classList.contains('dark') ? 'dark' : 'light'));

async function parada(v, nombre, visita) {
  v.donde = nombre;
  v.traza?.(nombre);
  await quieta(v);
  if (visita) await visita(nombre);
}

// ------------------------------------------------------------------ entrar y moverse

/** La entrada: el codigo y dentro (el saludo). */
export async function entrar(v, codigo) {
  v.donde = 'entrada';
  await hasta(v, 'la entrada', () => $(v, '#token').count());
  await $(v, '#token').fill(codigo);
  await clic(v, $(v, '#login-submit'));
  await hasta(v, 'el inicio', async () => (await $(v, '#token').count()) === 0 && (await $(v, APP).count()) > 0);
  await quieta(v);
}

/** De vuelta en el espacio de Aurora desde una pantalla de trabajo (Documentos). */
async function aAurora(v) {
  if ((await pantalla(v)) === 'work') {
    for (let i = 0; i < 3 && (await $(v, HOJA).count()); i += 1) {
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
  for (let i = 0; i < 5; i += 1) {
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
}

async function centrar(v, id) {
  const boton = $(v, `.navigation .nav-item[data-entry="${id}"]`);
  if ((await boton.getAttribute('aria-current')) !== 'true') {
    await boton.focus();
    await hasta(v, `${id} en el centro`, async () => (await boton.getAttribute('aria-current')) === 'true');
  }
  await quieta(v);
}

/** Abre una entrada de la rueda. Devuelve false si la persona no la tiene. */
export async function entrada(v, id) {
  await abrirRueda(v);
  if (!(await $(v, `.navigation .nav-item[data-entry="${id}"]`).count())) return false;
  await centrar(v, id);
  await clic(v, $(v, `.navigation .nav-item[data-entry="${id}"]`));
  if (id === 'documents') await hasta(v, 'Documentos', async () => (await pantalla(v)) === 'work' && (await $(v, '.ws-grid').count()) > 0);
  else if (id === 'process') {
    await hasta(v, 'Procesar', async () => /\bprocess-mode\b/.test(await clase(v)) && (await $(v, '.processing-workspace').isVisible()));
    // La entrada de la suricata (las particulas, el monticulo, la cabeza): unos 2,6 s.
    await hasta(v, 'el boton de Procesar', () => $(v, '.flow-button').isVisible(), 20_000).catch(() => {});
  } else if (id === 'search') await hasta(v, 'la busqueda', async () => /\bsearch-mode\b/.test(await clase(v)));
  else await hasta(v, `el panel de ${id}`, () => $(v, `${PANEL} h2`).isVisible());
  await quieta(v);
  return true;
}

// ------------------------------------------------------------------ los paneles

/** Lo que distingue una vista del panel de otra: su titulo, su lista y cuantas filas tiene. */
const firmaPanel = (v) =>
  v.marco.evaluate((sel) => {
    const p = document.querySelector(sel);
    if (!p) return '';
    const filas = [...p.querySelectorAll('button.doc')].filter((b) => !b.closest('.detail'));
    return [p.querySelector('h2')?.textContent, p.querySelector('.list-title')?.textContent, filas.length, filas[0]?.textContent].join('|');
  }, PANEL);

const filasPanel = (v) => $(v, `${PANEL} button.doc`);

/** Lo que dicen las filas del panel a la vista (su titulo). */
export const titulosPanel = (v) =>
  v.marco.evaluate((sel) => [...document.querySelectorAll(`${sel} button.doc`)].map((b) => b.querySelector('strong')?.textContent.trim() ?? '').filter(Boolean), PANEL);

/** Lo que dicen las entradas de la rueda (abierta). */
export const titulosRueda = (v) => v.marco.evaluate(() => [...document.querySelectorAll('.navigation .nav-item')].map((b) => b.textContent.trim()).filter(Boolean));

async function cerrarTarjeta(v) {
  if (await $(v, `${PANEL} .detail-close`).count()) {
    await clic(v, $(v, `${PANEL} .detail-close`).first());
    await hasta(v, 'sin tarjeta', async () => (await $(v, `${PANEL} .detail`).count()) === 0).catch(() => {});
  }
}

/** Abre el panel de una entrada y, fila a fila, la vista a la que lleva `ruta`. */
async function irA(v, id, ruta) {
  await entrada(v, id);
  for (const n of ruta) {
    await clic(v, filasPanel(v).nth(n));
    await quieta(v);
  }
}

/**
 * Recorre la vista del panel que se ve (la de `ruta` dentro de la entrada `id`): cada fila (hasta
 * un tope) abre otra vista (se recorre, hasta `fondo` niveles), una tarjeta, o lleva a otro sitio
 * (una semana del flujo de caja lleva a la busqueda; una fila, a Documentos): se mira y se vuelve.
 */
async function recorrerPanel(v, id, ruta, opciones, visita, fondo) {
  const camino = ['panel', id, ...ruta.map((n) => n + 1)].join('-');
  const reposo = await firmaPanel(v);
  const total = await filasPanel(v).count();
  // La gira corta: cada grupo del panel, y dentro del primero, su primera fila.
  const tope = Math.min(total, opciones.completa ? 40 : ruta.length === 0 ? 8 : 1);
  for (let i = 0; i < tope; i += 1) {
    if (opciones.saltar?.(ruta, i)) continue;
    const fila = filasPanel(v).nth(i);
    if (!(await fila.count())) break;
    await clic(v, fila);
    await quieta(v);
    const nombre = `${camino}-${i + 1}`;
    const quiero = opciones.completa || i < 6 ? visita : null;
    if (!(await $(v, PANEL).count())) {
      // Fuera del panel: otra pantalla.
      await parada(v, `${nombre}-salto`, quiero);
      await irA(v, id, ruta);
      continue;
    }
    const ahora = await firmaPanel(v);
    if (ahora !== reposo) {
      await parada(v, nombre, quiero);
      if (fondo > 1 && !opciones.sinEntrar?.(ruta, i) && (opciones.completa || (ruta.length === 0 && i === 0))) {
        await recorrerPanel(v, id, [...ruta, i], opciones, visita, fondo - 1);
      }
      // «Volver a …» (el boton del final de la vista) vuelve a la vista de antes.
      await cerrarTarjeta(v);
      const volver = $(v, `${PANEL} > button.outline`);
      if ((await firmaPanel(v)) !== reposo && (await volver.count())) {
        await clic(v, volver.last());
        await quieta(v);
      }
      if ((await firmaPanel(v)) !== reposo) await irA(v, id, ruta);
    } else if (await $(v, `${PANEL} .detail`).count()) {
      await parada(v, `${nombre}-tarjeta`, i < 2 ? visita : null);
      await cerrarTarjeta(v);
    }
  }
}

/** Un panel entero: en reposo, sus grupos y sus tarjetas. */
export async function girarPanel(v, id, opciones, visita) {
  if (!(await entrada(v, id))) return;
  await parada(v, `panel-${id}`, visita);
  // En Ajustes, las vistas del idioma y del tema se miran pero no se recorren: sus filas cambian
  // el idioma y el tema (eso lo hacen ponerIdioma y ponerTema).
  const sinEntrar = id === 'settings' ? (ruta, i) => ruta.length === 0 && i < 2 : undefined;
  await recorrerPanel(v, id, [], { ...opciones, sinEntrar }, visita, 3);
}

// ------------------------------------------------------------------ Importar

/** La vista de importar (un fichero del banco o de la administracion): la abre el boton del
 *  final del panel de cobros (o del de pagos) en reposo. false si la persona no puede importar. */
export async function abrirImportar(v) {
  for (const id of ['receivables', 'payables']) {
    if (!(await entrada(v, id))) continue;
    const boton = $(v, `${PANEL} > button.outline`);
    if (!(await boton.count())) continue;
    await clic(v, boton.last());
    await hasta(v, 'la vista de importar', () => $(v, `${PANEL} .dropzone`).isVisible());
    await quieta(v);
    return true;
  }
  return false;
}

/** Importar: la zona de soltar y sus dos filas (las fuentes y el historial). */
export async function girarImportar(v, opciones, visita) {
  if (!(await abrirImportar(v))) return;
  await parada(v, 'importar', visita);
  const filas = await filasPanel(v).count();
  for (let i = 0; i < filas; i += 1) {
    await clic(v, filasPanel(v).nth(i));
    await hasta(v, 'una vista de importar', async () => !(await $(v, `${PANEL} .dropzone`).count()));
    await parada(v, `importar-${i + 1}`, visita);
    await clic(v, $(v, `${PANEL} > button.outline`).last());
    await hasta(v, 'la vista de importar', () => $(v, `${PANEL} .dropzone`).isVisible());
    await quieta(v);
  }
  await aInicio(v);
}

// ------------------------------------------------------------------ Ajustes: idioma, tema, salir

async function filaAjustes(v, n) {
  await entrada(v, 'settings');
  await clic(v, filasPanel(v).nth(n));
  await quieta(v);
}

export async function ponerIdioma(v, idioma) {
  if ((await idiomaVisto(v)) === idioma) return;
  if (await $(v, '#token').count()) {
    await clic(v, v.marco.getByRole('button', { name: NOMBRES_IDIOMA[idioma], exact: true }));
  } else {
    await filaAjustes(v, 0);
    await clic(v, $(v, `${PANEL} button.doc`).filter({ has: v.marco.locator('strong').getByText(NOMBRES_IDIOMA[idioma], { exact: true }) }));
  }
  await hasta(v, `el idioma ${idioma}`, async () => (await idiomaVisto(v)) === idioma);
  await quieta(v);
}

/** El tema en Ajustes > Tema: sus filas son oscuro, claro y el del sistema, en ese orden. */
export async function ponerTema(v, tema) {
  await filaAjustes(v, 1);
  await clic(v, filasPanel(v).nth({ dark: 0, light: 1, system: 2 }[tema]));
  if (tema !== 'system') await hasta(v, `el tema ${tema}`, async () => (await temaVisto(v)) === tema);
  await quieta(v);
}

export async function salir(v) {
  await entrada(v, 'settings');
  await clic(v, $(v, `${PANEL} > button.outline`).last());
  await hasta(v, 'la entrada', () => $(v, '#token').isVisible());
  await quieta(v);
}

// ------------------------------------------------------------------ la conversacion y la busqueda

const caja = (v) => $(v, `${APP} input`).first();

/** Escribe en la caja e Intro, y espera la respuesta. */
export async function preguntar(v, texto) {
  await caja(v).fill(texto);
  await caja(v).press('Enter');
  await hasta(v, 'la conversacion', () => $(v, '.conversation').isVisible());
  await hasta(v, 'la respuesta', async () => (await $(v, '.typing-dots').count()) === 0 && (await v.pendientes()) === 0, 20_000);
  await quieta(v);
}

/** El numero de una factura que se ve: el de la primera fila de «Eerst» en el panel de inicio
 *  (o de la primera vista que tenga facturas). */
export async function unNumero(v) {
  if (v.numero) return v.numero;
  await entrada(v, 'home');
  const grupos = await filasPanel(v).count();
  for (let i = 0; i < grupos && !v.numero; i += 1) {
    const antes = await firmaPanel(v);
    await clic(v, filasPanel(v).nth(i));
    await quieta(v);
    if ((await firmaPanel(v)) === antes) {
      await cerrarTarjeta(v);
      continue;
    }
    const numero = await $(v, `${PANEL} button.doc small[data-proper-name]`).first().textContent({ timeout: 500 }).catch(() => null);
    // «JV-2026-007 · 1 van 2 …»: solo el numero.
    if (numero) v.numero = numero.split(' · ')[0].trim();
    await v.pagina.keyboard.press('Escape');
    await quieta(v);
  }
  if (!v.numero) throw new Error('gira: ninguna factura a la vista en el panel de inicio');
  return v.numero;
}

/** La conversacion: el resumen general (el bento) y un numero de factura; su fila lleva a la hoja. */
export async function girarConversacion(v, opciones, visita) {
  const numero = await unNumero(v);
  const idioma = await idiomaVisto(v);
  await aInicio(v);
  await parada(v, 'inicio', visita);
  await preguntar(v, PREGUNTA_RESUMEN[idioma] ?? PREGUNTA_RESUMEN.nl);
  await hasta(v, 'el bento', () => $(v, '.finance-bento').isVisible());
  await parada(v, 'bento', visita);
  // Las pestanas del bento (clientes y proveedores).
  const pestanas = $(v, '.finance-bento button');
  for (let i = 0; i < Math.min(await pestanas.count(), opciones.completa ? 4 : 2); i += 1) {
    await clic(v, pestanas.nth(i));
    await quieta(v);
  }
  await preguntar(v, numero);
  await parada(v, 'conversacion', visita);
  const fila = $(v, '.conversation .chat-rows a.search-result').first();
  if (await fila.count()) {
    await clic(v, fila);
    await hasta(v, 'la hoja de la factura', async () => (await pantalla(v)) === 'work' && (await $(v, `${HOJA} .ws-file-table`).count()) > 0, 20_000);
    await parada(v, 'conversacion-hoja', visita);
    await girarHoja(v, 'conversacion-hoja', { completa: false, filas: 0 }, null);
  }
  // Ctrl+K: la app no tiene paleta ni atajo (el registro, paso 17, §6.5): no abre nada ni rompe nada.
  await aInicio(v);
  const antes = await clase(v);
  await v.pagina.keyboard.press('Control+k');
  await espera(200);
  if ((await clase(v)) !== antes) throw new Error(`gira: Ctrl+K cambia el estado de «${antes}» a «${await clase(v)}»`);
  await parada(v, 'ctrl-k', visita);
  await aInicio(v);
}

/** La busqueda: sus filtros (la empresa, la clase de documento) y un numero; su fila lleva a la hoja. */
export async function girarBusqueda(v, opciones, visita) {
  const numero = await unNumero(v);
  await entrada(v, 'search');
  await parada(v, 'busqueda', visita);
  await clic(v, $(v, 'button.filters-toggle').first());
  await quieta(v);
  await parada(v, 'busqueda-filtros', visita);
  const cajaBusqueda = $(v, `${APP} input`).first();
  await cajaBusqueda.fill(numero);
  await cajaBusqueda.press('Enter');
  await hasta(v, 'los resultados', async () => (await v.pendientes()) === 0 && (await $(v, 'a.search-result').count()) > 0, 20_000);
  await parada(v, 'busqueda-resultado', visita);
  await cajaBusqueda.fill('');
  await cajaBusqueda.press('Enter');
  await quieta(v);
  // Los desplegables: la clase de documento (cada opcion) y la empresa (cada una, o dos).
  const combos = $(v, `${APP} [role=combobox]`);
  for (let c = 0; c < (await combos.count()); c += 1) {
    await clic(v, combos.nth(c));
    await hasta(v, 'las opciones', async () => (await v.marco.locator('[role=option]').count()) > 0).catch(() => {});
    const opciones_ = await v.marco.locator('[role=option]').count();
    const cuantas = opciones.completa ? opciones_ : Math.min(opciones_, 2);
    if (c === 0) await parada(v, 'busqueda-desplegable', visita);
    for (let o = cuantas - 1; o >= 0; o -= 1) {
      if (!(await v.marco.locator('[role=option]').count())) {
        await clic(v, combos.nth(c));
        await hasta(v, 'las opciones', async () => (await v.marco.locator('[role=option]').count()) > 0).catch(() => {});
      }
      const opcion = v.marco.locator('[role=option]').nth(o);
      if (!(await opcion.count())) break;
      await clic(v, opcion);
      await quieta(v);
    }
    if (await v.marco.locator('[role=option]').count()) await v.pagina.keyboard.press('Escape');
    await quieta(v);
  }
  // Con la busqueda hecha, el orbe vuelve a E0.
  await aInicio(v);
}

// ------------------------------------------------------------------ Documentos

/** La hoja abierta (una factura, un documento, un Object, una PO): plegada, desplegada y la
 *  tarjeta de cada fila. Termina cerrada. */
export async function girarHoja(v, nombre, opciones, visita) {
  await hasta(v, 'la hoja', () => $(v, `${HOJA}`).count());
  await quieta(v);
  if (visita) await parada(v, nombre, visita);
  const pliegue = $(v, `${HOJA} [data-testid=sheet-fold] button`);
  if ((await pliegue.count()) && (await pliegue.first().getAttribute('aria-expanded')) !== 'true') {
    await clic(v, pliegue.first());
    await quieta(v);
    if (visita) await parada(v, `${nombre}-desplegada`, visita);
  }
  const filas = $(v, `${HOJA} .ws-file-table > a`);
  const tope = Math.min(await filas.count(), opciones.completa ? 30 : (opciones.filas ?? 1));
  for (let i = 0; i < tope; i += 1) {
    const fila = filas.nth(i);
    if (!(await fila.count())) break;
    if ((await fila.getAttribute('aria-current')) !== 'true') await clic(v, fila);
    await quieta(v);
    if (visita && i === 0 && (await $(v, `${HOJA} .detail`).count())) await parada(v, `${nombre}-tarjeta`, visita);
  }
  await cerrarHoja(v);
}

async function cerrarHoja(v) {
  for (let i = 0; i < 4 && (await $(v, HOJA).count()); i += 1) {
    await v.pagina.keyboard.press('Escape');
    await espera(200);
  }
  await hasta(v, 'la hoja cerrada', async () => (await $(v, HOJA).count()) === 0);
  await quieta(v);
}

const nodos = (v) => $(v, '[role=treeitem]');

/** Los nodos del arbol que son carpetas de una empresa: los que no son raiz ni categoria (los
 *  que estan dentro de un grupo). */
async function carpetasDelArbol(v) {
  return v.marco.evaluate(() => {
    const todos = [...document.querySelectorAll('[role=treeitem]')];
    return todos.map((n, i) => ({ i, nivel: Number(n.getAttribute('aria-level') ?? 0), abierto: n.getAttribute('aria-expanded'), hoja: n.getAttribute('aria-expanded') === null })).filter((n) => n.hoja && n.nivel >= 3);
  });
}

/** Documentos: la rejilla, el abanico de una carpeta y su hoja, el arbol, y la ficha de cada
 *  empresa con sus filas (documentos, Objects y ordenes de compra). */
export async function girarDocumentos(v, opciones, visita) {
  await entrada(v, 'documents');
  await parada(v, 'documentos', visita);
  // Una carpeta de la rejilla: su abanico, y una hoja desde el.
  // (Abrir una carpeta deja la rejilla en su categoria: las celdas se cuentan cada vez.)
  const celdas = $(v, '[data-testid=folder-cell]');
  for (let i = 0; i < (opciones.completa ? 2 : 1); i += 1) {
    if ((await celdas.count()) <= i || !(await celdas.nth(i).locator('button.gf-hit').count())) break;
    await clic(v, celdas.nth(i).locator('button.gf-hit'));
    await quieta(v);
    if (i === 0) await parada(v, 'documentos-abanico', visita);
    const hojas = celdas.nth(i).locator('button.gf-sheet');
    if ((await hojas.count()) && i < 2) {
      await hojas.first().evaluate((el) => el.click());
      await girarHoja(v, 'documentos-abanico-hoja', { completa: false, filas: 0 }, i === 0 ? visita : null);
    }
    // Otra vez la carpeta: se cierra.
    if (await celdas.nth(i).locator('button.gf-hit').count()) await clic(v, celdas.nth(i).locator('button.gf-hit'));
    await quieta(v);
  }
  // El arbol: las categorias (abiertas) y cada carpeta con su ficha.
  for (let i = 0; i < (await nodos(v).count()); i += 1) {
    const nodo = nodos(v).nth(i);
    if ((await nodo.getAttribute('aria-expanded')) === 'false') {
      await clic(v, nodo);
      await quieta(v);
    }
  }
  const carpetas = await carpetasDelArbol(v);
  // Sin niveles en el arbol: las carpetas son las que abren una ficha.
  const indices = carpetas.length ? carpetas.map((c) => c.i) : [...Array(await nodos(v).count()).keys()].slice(2);
  let fichas = 0;
  let conFilas = 0;
  for (const i of indices) {
    if (!opciones.completa && (conFilas >= 1 || fichas >= 5)) break;
    await clic(v, nodos(v).nth(i));
    await quieta(v);
    if (!(await $(v, '.ws-profile').count())) continue;
    fichas += 1;
    const filas = $(v, '.ws-profile .ws-file-table > a');
    const total = await filas.count();
    if (total) conFilas += 1;
    // Las paradas llevan el nombre de la primera ficha CON filas (documentos-ficha-1), para que la
    // gira corta y la entera se llamen igual.
    const n1 = total ? conFilas : `vacia-${fichas}`;
    await parada(v, `documentos-ficha-${n1}`, visita);
    // En la gira corta: la primera fila (plegada, desplegada y su primera tarjeta).
    const cuales = opciones.completa ? [...Array(total).keys()] : total ? [0] : [];
    for (const n of cuales) {
      await clic(v, filas.nth(n));
      await girarHoja(v, `documentos-ficha-${n1}-hoja-${n + 1}`, opciones, conFilas <= 2 && n === cuales[0] ? visita : null);
    }
  }
  // Las categorias (Klanten, Leveranciers) y la raiz.
  for (const i of opciones.completa ? [...Array(await nodos(v).count()).keys()] : []) {
    const nodo = nodos(v).nth(i);
    if ((await nodo.getAttribute('aria-expanded')) !== null) {
      await clic(v, nodo.locator('.tree-label').first());
      await quieta(v);
    }
  }
  await aInicio(v);
}

// ------------------------------------------------------------------ Procesar

export async function girarProcesar(v, opciones, visita) {
  if (!(await entrada(v, 'process'))) return;
  await parada(v, 'procesar', visita);
  await aInicio(v);
}

// ------------------------------------------------------------------ la gira

/**
 * La gira entera en el idioma y el tema que haya. `completa`: todo (para grabar, y una vez al
 * comprobar); si no, las pantallas principales.
 */
export async function gira(v, opciones, visita) {
  const partes = [
    ...ENTRADAS_PANEL.map((id) => [`panel-${id}`, () => girarPanel(v, id, opciones, visita)]),
    ['importar', () => girarImportar(v, opciones, visita)],
    ['busqueda', () => girarBusqueda(v, opciones, visita)],
    ['documentos', () => girarDocumentos(v, opciones, visita)],
    ['conversacion', () => girarConversacion(v, opciones, visita)],
    ['procesar', () => girarProcesar(v, opciones, visita)],
  ];
  for (const [nombre, parte] of partes) {
    if (!opciones.tolerante) {
      await parte();
      continue;
    }
    // Al grabar: lo que falle de una parte se apunta y se sigue con la siguiente.
    try {
      await parte();
    } catch (error) {
      v.errores?.push(`${nombre}: ${String(error?.message ?? error).split('\n')[0]} (en ${v.donde ?? '?'})`);
      await opciones.alFallar?.(nombre);
      await aInicio(v).catch(() => {});
    }
  }
}
