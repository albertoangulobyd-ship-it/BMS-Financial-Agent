#!/usr/bin/env node
// comprobar.mjs — la autocomprobacion de la vista previa, en un navegador de verdad.
//
//   node comprobar.mjs [--repo <ruta>] [--fichero salida/bms-finance-vista-previa.html]
//                      [--solo file,http,iframe] [--anchos 1440,400] [--capturas <carpeta>]
//                      [--rapida] [--sin-lectura]
//
// --repo es por defecto el repo que lleva esta carpeta (de el solo se usa su Playwright).
// Abre el fichero de tres maneras:
//   file    desde el disco (file://), tal cual sale de construir.mjs;
//   http    por http en una ruta cualquiera que no es /app, tal cual;
//   iframe  como lo ensena quien lo publica: envuelto en su esqueleto (src/envoltorio.html, el
//           que traia el fichero publicado) y dentro de un
//           <iframe sandbox="allow-scripts allow-forms allow-popups allow-modals allow-downloads">
//           de otro origen y sin allow-same-origin (sin localStorage ni cookies).
// En cada una, a 1440 y a 400 px: entra con un codigo cualquiera, da la gira (gira.mjs: la
// misma con la que se grabo) en neerlandes y oscuro (la primera vez, entera), y despues las
// pantallas principales en claro y en los otros dos idiomas; mira tambien que una orden no se
// guarda y lo dice, que una descarga lo dice, el tema del sistema, salir y volver a entrar, y
// (una vez) la lectura grabada de Procesar.
// Falla con: un error en la consola, una peticion a la red (lo que no sea el propio documento),
// una peticion a /api sin grabacion, o desplazamiento horizontal de la pagina.
// Del repo solo usa playwright-core (frontend/node_modules). --fichero vale tambien para el
// fichero publicado de antes (ya envuelto): asi se comparan los dos.
import { createServer } from 'node:http';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { AQUI, SALIDA, TRABAJO, argumentos, espera, falla, navegador, repoDe } from './comun.mjs';
import { abrirImportar, aInicio, entrada, entrar, gira, idiomaVisto, ponerIdioma, ponerTema, quieta, salir, temaVisto } from './gira.mjs';
import { TEXTOS_VP } from './src/textos-vp.js';

const args = argumentos();
const { frontend } = repoDe(args);
const fichero = resolve(typeof args.fichero === 'string' ? args.fichero : SALIDA);
if (!existsSync(fichero)) falla(`no existe ${fichero}: primero npm run vista-previa:construir (o node herramientas/vista-previa/construir.mjs)`);
const solo = typeof args.solo === 'string' ? args.solo.split(',') : ['file', 'http', 'iframe'];
const anchos = (typeof args.anchos === 'string' ? args.anchos.split(',') : ['1440', '400']).map(Number);
const capturas = typeof args.capturas === 'string' ? resolve(args.capturas) : join(dirname(fichero), 'capturas');
const rapida = args.rapida === true;
const SANDBOX = 'allow-scripts allow-forms allow-popups allow-modals allow-downloads';

// ------------------------------------------------------------------ las dos formas del fichero

const leido = readFileSync(fichero, 'utf8');
const envoltorio = readFileSync(join(AQUI, 'src', 'envoltorio.html'), 'utf8');
const [cabeza, pie] = envoltorio.split('<!--vp:fichero-->');
const yaEnvuelto = /^\s*<!doctype/i.test(leido);
let cruda = leido;
if (yaEnvuelto) {
  const desde = leido.indexOf('<title>');
  const hasta = leido.lastIndexOf('</script>') + '</script>'.length;
  cruda = leido.slice(desde, hasta) + '\n';
}
const publicada = yaEnvuelto ? leido : cabeza + cruda + pie;
const carpeta = join(TRABAJO, 'comprobar');
rmSync(carpeta, { recursive: true, force: true });
mkdirSync(carpeta, { recursive: true });
mkdirSync(capturas, { recursive: true });
writeFileSync(join(carpeta, 'cruda.html'), cruda);

// ------------------------------------------------------------------ los dos servidores

function servir(paginas) {
  return new Promise((ok) => {
    const s = createServer((req, res) => {
      const cuerpo = paginas[(req.url ?? '').split('?')[0]];
      if (cuerpo === undefined) {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('no');
        return;
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(cuerpo);
    });
    s.listen(0, '127.0.0.1', () => ok({ servidor: s, origen: `http://127.0.0.1:${s.address().port}` }));
  });
}
const RUTA_HTTP = '/artefactos/8f3c/vista-previa.html';
const RUTA_MARCO = '/publicado/1b7e/index.html';
const contenido = await servir({ [RUTA_HTTP]: cruda, [RUTA_MARCO]: publicada });
const anfitrion = await servir({
  '/': `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>anfitrion</title><style>html,body{margin:0;height:100%;overflow:hidden}iframe{display:block;border:0;width:100vw;height:100vh}</style></head><body><iframe id="vista" sandbox="${SANDBOX}" src="${contenido.origen}${RUTA_MARCO}"></iframe></body></html>`,
});
// Una cuarta manera, fuera de las tres de siempre (--solo srcdoc): el mismo iframe sandbox, pero
// con el fichero en su atributo srcdoc (la pagina es about:srcdoc: no tiene ni ruta).
const RUTA_SRCDOC = '/srcdoc';
const anfitrionSrcdoc = await servir({
  [RUTA_SRCDOC]: `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>anfitrion</title><style>html,body{margin:0;height:100%;overflow:hidden}iframe{display:block;border:0;width:100vw;height:100vh}</style></head><body><script>fetch('/contenido').then((r) => r.text()).then((t) => { const f = document.createElement('iframe'); f.id = 'vista'; f.setAttribute('sandbox', '${SANDBOX}'); f.srcdoc = t; document.body.append(f); });</script></body></html>`,
  '/contenido': publicada,
});
const DONDE = {
  srcdoc: { url: `${anfitrionSrcdoc.origen}${RUTA_SRCDOC}`, permitidas: [`${anfitrionSrcdoc.origen}${RUTA_SRCDOC}`, `${anfitrionSrcdoc.origen}/contenido`, 'about:srcdoc'], marco: true },
  // pathToFileURL: en Windows, file:///C:/… (con `file://${ruta}` saldria file://C:\…).
  file: { url: pathToFileURL(join(carpeta, 'cruda.html')).href, permitidas: [pathToFileURL(join(carpeta, 'cruda.html')).href] },
  http: { url: `${contenido.origen}${RUTA_HTTP}`, permitidas: [`${contenido.origen}${RUTA_HTTP}`] },
  iframe: { url: `${anfitrion.origen}/`, permitidas: [`${anfitrion.origen}/`, `${contenido.origen}${RUTA_MARCO}`], marco: true },
};

// ------------------------------------------------------------------ una pasada

const { browser } = await navegador(frontend);
const fallos = [];
const hechas = [];
let lecturaVista = args['sin-lectura'] === true;
let giraEntera = false;

/** Antes que la pagina: apunta cada respuesta 404 no_grabado de su fetch (vale para el fichero
 *  de antes, que no lleva window.__vpSinGrabar). */
function espia() {
  window.__noGrabado = [];
  let puesto = window.fetch;
  Object.defineProperty(window, 'fetch', {
    configurable: true,
    get: () => puesto,
    set(f) {
      puesto = async (...a) => {
        const r = await f(...a);
        if (r.status === 404) {
          const url = typeof a[0] === 'string' ? a[0] : (a[0]?.url ?? String(a[0]));
          r.clone().json().then((j) => j?.codigo === 'no_grabado' && window.__noGrabado.push(url), () => {});
        }
        return r;
      };
    },
  });
}

async function pasada(donde, ancho) {
  const etiqueta = `${donde}-${ancho}`;
  const t0 = Date.now();
  const sitio = DONDE[donde];
  const contexto = await browser.newContext({
    viewport: { width: ancho, height: ancho >= 1000 ? 900 : 800 },
    deviceScaleFactor: 1,
    locale: 'nl-NL',
    timezoneId: 'Europe/Amsterdam',
    colorScheme: 'dark',
    // Sin serviceWorkers: 'block': Playwright lo hace leyendo navigator.serviceWorker en cada
    // marco, y en un iframe sin allow-same-origin esa lectura es un error (suyo, no de la pagina).
    acceptDownloads: true,
  });
  const pagina = await contexto.newPage();
  const aqui = { donde: etiqueta, paso: 'abrir' };
  const fallo = (clase, que) => {
    const linea = `[${aqui.donde} · ${aqui.paso}] ${clase}: ${que}`;
    if (!fallos.includes(linea)) fallos.push(linea);
  };
  pagina.on('console', (m) => m.type() === 'error' && fallo('consola', m.text().slice(0, 300)));
  pagina.on('pageerror', (e) => fallo('error', String(e.message).slice(0, 300)));
  pagina.on('request', (r) => {
    const url = r.url();
    if (url.startsWith('data:') || url.startsWith('blob:') || sitio.permitidas.includes(url)) return;
    fallo('red', `${r.method()} ${url.slice(0, 200)}`);
  });
  await pagina.addInitScript(espia);
  await pagina.goto(sitio.url);
  let marco = pagina;
  if (sitio.marco) {
    await pagina.waitForSelector('#vista', { timeout: 60_000 });
    for (let i = 0; i < 100 && pagina.frames().length < 2; i += 1) await espera(50);
    marco = pagina.frames().find((f) => f !== pagina.mainFrame());
    await marco.waitForLoadState('domcontentloaded');
  }
  const v = { pagina, marco, grabando: false, avisos: [], pendientes: () => marco.evaluate(() => window.__vpPendientes ?? 0).catch(() => 0) };
  if (args.traza === true) v.traza = (nombre) => console.log(`  ${((Date.now() - t0) / 1000).toFixed(1).padStart(6)} s  ${nombre}`);

  let tema = 'dark';
  let idioma = 'nl';
  const vistas = new Set();
  /** En cada parada: nada sin grabar y nada de desplazamiento horizontal; y su captura. */
  /** Nada sin grabar desde la ultima vez que se miro, y nada de desplazamiento horizontal. */
  const revisar = async () => {
    const { sinGrabar, ancho: medidas } = await marco.evaluate(() => {
      const d = document.scrollingElement ?? document.documentElement;
      return { sinGrabar: (window.__noGrabado ?? []).splice(0), ancho: [d.scrollWidth, d.clientWidth, document.body.scrollWidth, window.innerWidth] };
    });
    for (const url of sinGrabar) fallo('sin grabar', url);
    if (medidas[0] - medidas[1] > 1 || medidas[2] - medidas[3] > 1) fallo('desplazamiento horizontal', `scrollWidth ${medidas[0]} > ${medidas[1]} (body ${medidas[2]}, ventana ${medidas[3]})`);
  };
  const visita = (quiero) => async (nombre) => {
    aqui.paso = `${tema}-${idioma}-${nombre}`;
    await revisar();
    const clave = `${tema}-${idioma}-${nombre}`;
    if (quiero(nombre) && !vistas.has(clave)) {
      vistas.add(clave);
      await pagina.screenshot({ path: join(capturas, `${etiqueta}-${clave}.png`) });
    }
  };
  const PRINCIPALES = /^(entrada|inicio|panel-(home|receivables|payables|vat|settings)|panel-home-1|panel-home-1-1-tarjeta|panel-payables-1|importar|importar-2|busqueda-filtros|busqueda-resultado|documentos|documentos-abanico|documentos-abanico-hoja(-desplegada)?|documentos-ficha-1|documentos-ficha-1-hoja-1(-desplegada|-tarjeta)?|bento|conversacion|procesar|procesar-orden|importar-subir|hoja-descarga|entrada-otra-vez|inicio-otra-vez|procesar-lectura-fin)$/;
  const principales = visita((n) => PRINCIPALES.test(n));

  try {
    // La entrada: la nota dice «escribe cualquier codigo», y los tres idiomas estan.
    await marco.waitForSelector('#token');
    await quieta(v);
    await principales('entrada');
    if (!(await marco.locator('#vp-nota.vp-nota--entrada').count())) fallo('entrada', 'la nota no dice que vale cualquier codigo');
    aqui.paso = 'entrar';
    await entrar(v, 'demo');
    if ((await idiomaVisto(v)) !== 'nl') fallo('idioma', `empieza en ${await idiomaVisto(v)}, no en nl`);
    if ((await temaVisto(v)) !== 'dark') fallo('tema', `empieza en ${await temaVisto(v)}, no en oscuro`);
    if (await marco.locator('#vp-nota.vp-nota--entrada').count()) fallo('entrada', 'dentro, la nota sigue pidiendo un codigo');

    // 1. Neerlandes y oscuro: la gira (entera la primera vez; con --rapida, nunca).
    const entera = !rapida && !giraEntera;
    giraEntera = true;
    aqui.paso = 'gira nl oscuro';
    await gira(v, { completa: entera }, principales);
    await revisar();

    // 2. Lo que no se guarda y lo que no se descarga.
    aqui.paso = 'orden';
    await entrada(v, 'process');
    await marco.locator('.flow-button').click();
    await marco.waitForFunction(() => !document.getElementById('vp-aviso')?.hidden, undefined, { timeout: 5000 }).catch(() => fallo('orden', 'no sale el aviso de la pagina (#vp-aviso) al dar una orden'));
    if ((await marco.locator('#vp-aviso').textContent()) !== TEXTOS_VP.nl.vista_previa) fallo('orden', `el aviso dice «${await marco.locator('#vp-aviso').textContent()}»`);
    await quieta(v);
    // Procesar dice sus errores con su frase de siempre («Er ging iets mis…», role=alert): el
    // porque lo dice el aviso de la pagina. (Donde la app ensena el error del servidor, sale el
    // texto del catalogo: se mira mas abajo, al subir un fichero y al descargar.)
    await marco.locator('.processing-workspace [role=alert]').first().waitFor({ timeout: 5000 }).catch(() => fallo('orden', 'Procesar no dice que la orden ha fallado'));
    await principales('procesar-orden');
    await aInicio(v);
    aqui.paso = 'subir';
    if (await abrirImportar(v)) {
      await marco.locator('aside.panel input[type=file]').setInputFiles({ name: 'afschrift.csv', mimeType: 'text/csv', buffer: Buffer.from('Datum;Naam;Bedrag\n2026-11-02;Voorbeeld BV;12,50\n') });
      await marco.locator('[data-testid=import-file]').waitFor({ timeout: 5000 });
      await marco.locator('aside.panel button.primary').first().click();
      await marco.locator('aside.panel').getByText(TEXTOS_VP.nl.vista_previa).first().waitFor({ timeout: 5000 }).catch(() => fallo('subir', 'la vista de importar no dice que el fichero no se guarda'));
      await quieta(v);
      await principales('importar-subir');
    } else fallo('subir', 'no se llega a la vista de importar');
    await aInicio(v);
    aqui.paso = 'descarga';
    await entrada(v, 'documents');
    const celda = marco.locator('[data-testid=folder-cell]').filter({ has: marco.locator('button.gf-hit') }).first();
    await celda.locator('button.gf-hit').click();
    await quieta(v);
    const hojas = marco.locator('button.gf-sheet');
    if (await hojas.count()) {
      await hojas.first().evaluate((el) => el.click());
      await marco.locator('dialog.ws-dialog[open] .ws-download').first().waitFor({ timeout: 8000 });
      await marco.locator('dialog.ws-dialog[open] .ws-download').first().click();
      await marco.locator('dialog.ws-dialog[open]').getByText(TEXTOS_VP.nl.vista_previa_descarga).first().waitFor({ timeout: 5000 }).catch(() => fallo('descarga', 'la hoja no dice que aqui no se descarga'));
      await quieta(v);
      await principales('hoja-descarga');
      await pagina.keyboard.press('Escape');
    } else fallo('descarga', 'ninguna hoja en el abanico de la primera carpeta');
    await aInicio(v);

    // 3. La lectura grabada de Procesar (una vez: dura lo que duro).
    if (!lecturaVista && ancho >= 1000) {
      lecturaVista = true;
      aqui.paso = 'lectura grabada';
      await entrada(v, 'process');
      const boton = marco.locator('#vp-opname-boton');
      if (!(await boton.isVisible())) fallo('lectura', 'en Procesar no esta el boton de la lectura grabada');
      else {
        const titulos = new Set([await marco.locator('.processing-workspace h1').first().textContent()]);
        await boton.click();
        if (!(await marco.locator('#vp-opname').isVisible())) fallo('lectura', 'no sale la banda de la opname');
        const fin = Date.now() + 90_000;
        let quietos = 0;
        while (Date.now() < fin && quietos < 16) {
          const t = await marco.locator('.processing-workspace h1').first().textContent().catch(() => null);
          if (t && !titulos.has(t)) {
            titulos.add(t);
            quietos = 0;
            if (titulos.size === 3 || titulos.size === 5) await pagina.screenshot({ path: join(capturas, `${etiqueta}-lectura-${titulos.size}.png`) });
          } else quietos += 1;
          await espera(500);
        }
        await pagina.screenshot({ path: join(capturas, `${etiqueta}-lectura-fin.png`) });
        if (titulos.size < 4) fallo('lectura', `la lectura grabada solo pasa por ${titulos.size} titulos: ${[...titulos].join(' / ')}`);
        await principales('procesar-lectura-fin');
        await aInicio(v);
        if (await marco.locator('#vp-opname').isVisible()) fallo('lectura', 'fuera de Procesar la banda de la opname sigue');
      }
    }

    // 4. Claro, en neerlandes: las pantallas principales.
    aqui.paso = 'tema claro';
    await ponerTema(v, 'light');
    tema = 'light';
    await gira(v, { completa: false }, principales);

    // 5. El tema del sistema sigue al sistema (aqui, oscuro), y vuelta.
    aqui.paso = 'tema del sistema';
    await ponerTema(v, 'system');
    if ((await temaVisto(v)) !== 'dark') fallo('tema', `con el del sistema (oscuro) se ve ${await temaVisto(v)}`);
    await pagina.emulateMedia({ colorScheme: 'light' });
    await espera(300);
    if ((await temaVisto(v)) !== 'light') fallo('tema', `con el del sistema (claro) se ve ${await temaVisto(v)}`);
    await pagina.emulateMedia({ colorScheme: 'dark' });

    // 6. Espanol e ingles: uno en claro y el otro en oscuro (se turnan de una pasada a otra).
    const turno = hechas.length % 2 === 0 ? { es: 'light', en: 'dark' } : { es: 'dark', en: 'light' };
    for (const otro of ['es', 'en']) {
      aqui.paso = `idioma ${otro}`;
      await ponerTema(v, turno[otro]);
      tema = turno[otro];
      await ponerIdioma(v, otro);
      idioma = otro;
      await gira(v, { completa: false }, principales);
    }

    // 7. Salir, y entrar otra vez en el idioma que se dejo (sin almacenamiento, lo recuerda la
    //    pagina mientras siga abierta).
    aqui.paso = 'salir';
    await salir(v);
    await principales('entrada-otra-vez');
    await ponerIdioma(v, 'nl');
    idioma = 'nl';
    await entrar(v, 'otro codigo');
    await principales('inicio-otra-vez');
    aqui.paso = 'al final';
    await revisar();
  } catch (error) {
    fallo('gira', String(error?.message ?? error).split('\n').slice(0, 3).join(' | '));
    await pagina.screenshot({ path: join(capturas, `${etiqueta}-FALLO.png`) }).catch(() => {});
  }
  for (const a of v.avisos) console.log(`  aviso [${etiqueta}] ${a}`);
  hechas.push({ donde, ancho, segundos: Math.round((Date.now() - t0) / 1000), capturas: vistas.size });
  console.log(`${etiqueta}: ${Math.round((Date.now() - t0) / 1000)} s, ${vistas.size} capturas, ${fallos.length} fallos hasta aqui`);
  await contexto.close();
}

for (const donde of solo) {
  if (!DONDE[donde]) throw new Error(`--solo ${donde}: no es file, http, iframe ni srcdoc`);
  for (const ancho of anchos) await pasada(donde, ancho);
}
await browser.close();
contenido.servidor.close();
anfitrion.servidor.close();
anfitrionSrcdoc.servidor.close();

const informe = { fichero, bytes: Buffer.byteLength(leido), ya_envuelto: yaEnvuelto, pasadas: hechas, capturas, ok: fallos.length === 0, fallos };
writeFileSync(join(dirname(capturas), `comprobacion${typeof args.nombre === 'string' ? `-${args.nombre}` : ''}.json`), JSON.stringify(informe, null, 2) + '\n');
console.log(fallos.length === 0 ? `BIEN: ${hechas.length} pasadas sin fallos` : `MAL: ${fallos.length} fallos\n` + fallos.map((f) => `  ${f}`).join('\n'));
process.exit(fallos.length === 0 ? 0 : 1);
