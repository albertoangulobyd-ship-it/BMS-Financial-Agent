// capturar.mjs — da la gira por la app de verdad (el servidor del repo sobre una base de prueba
// nueva) y congela cada estado: el DOM tal como esta, una imagen de cada <canvas> y, al lado,
// la foto de la pantalla viva con la que comprobar.mjs compara despues el fotograma.
//
//   node capturar.mjs [--repo <ruta>] [--solo estado,estado] [--anchos 1440,400] [--temas dark,light]
//
// --repo es por defecto el repo que lleva esta carpeta (su app construida, src/bms_agent/web).
//
// Una pasada por tema y ancho, cada una con su servidor y su base (asi las cuatro ven los mismos
// datos, y la lectura de Verwerken de una no cambia las demas). Escribe en captura/:
// <estado>-<ancho>-<tema>.json (el fotograma), .png (la pantalla viva), hoja-N.css (la hoja de
// estilo de la app tal como la sirve), tokens-<tema>.json y captura.json (el indice).
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { argumentos, CAPTURA, contexto, espera, lista, navegador, repoDe, servidor, TEMAS, VENTANAS } from './comun.mjs';
import * as A from './app.mjs';
import { FIRMA, INICIO, SERIALIZAR, TOKENS } from './congelar.mjs';
import { ESTADOS, IDS } from './estados.mjs';

const args = argumentos();
const { repo, frontend } = repoDe(args);
const estados = ESTADOS.filter((e) => lista(args.solo, IDS).includes(e.id));
const anchos = lista(args.anchos, [1440, 400]).map(Number);
const temas = lista(args.temas, TEMAS);
mkdirSync(CAPTURA, { recursive: true });

const INDICE = join(CAPTURA, 'captura.json');
const indice = existsSync(INDICE) ? JSON.parse(readFileSync(INDICE, 'utf8')) : { marcos: {}, hojas: {} };
let commit = '';
try {
  commit = execFileSync('git', ['--no-optional-locks', '-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
} catch {
  // Sin git: se queda sin decir.
}
const hash = JSON.parse(readFileSync(join(repo, 'src', 'bms_agent', 'web', 'fuente.json'), 'utf8'));
indice.repo = { commit, fuente: Object.values(hash).find((x) => typeof x === 'string' && /^[0-9a-f]{64}$/.test(x)) ?? '' };
const guardar = () => writeFileSync(INDICE, JSON.stringify(indice, null, 1));

/** Para la pantalla, saca el fotograma y la foto, y la suelta. Si la pantalla cambio entre el
 *  DOM y la foto (una respuesta que llega), se repite. */
async function fotograma(v) {
  let ultimo;
  for (let intento = 0; intento < 4; intento += 1) {
    await A.quieta(v);
    await v.pagina.evaluate(() => window.__df.parar());
    try {
      const antes = await v.pagina.evaluate(FIRMA);
      const s = await v.pagina.evaluate(SERIALIZAR);
      const png = await v.pagina.screenshot({ caret: 'hide', animations: 'allow' });
      const despues = await v.pagina.evaluate(FIRMA);
      ultimo = { s, png };
      if (antes === despues) return ultimo;
    } finally {
      await v.pagina.evaluate(() => window.__df.seguir());
    }
    await espera(400);
  }
  v.avisos.push(`la pantalla no para de cambiar (${v.donde})`);
  return ultimo;
}

/** La hoja de estilo de la app tal como la sirve, guardada una vez (por su ruta: el puerto
 *  cambia en cada pasada). Devuelve el nombre del fichero. */
async function hoja(ctx, href) {
  const clave = new URL(href).pathname;
  if (indice.hojas[clave] && existsSync(join(CAPTURA, indice.hojas[clave]))) return indice.hojas[clave];
  const r = await ctx.request.get(href);
  if (!r.ok()) throw new Error(`no se puede leer la hoja de estilo ${href}`);
  const fichero = `hoja-${Object.keys(indice.hojas).length}.css`;
  writeFileSync(join(CAPTURA, fichero), await r.text());
  indice.hojas[clave] = fichero;
  return fichero;
}

const t0 = Date.now();
const { browser } = await navegador(frontend);
indice.navegador = browser.version();
let fallos = 0;

for (const tema of temas) {
  for (const ancho of anchos) {
    const srv = await servidor(repo);
    const ctx = await contexto(browser, ancho);
    await ctx.addInitScript(INICIO);
    const pagina = await ctx.newPage();
    const v = A.vista(pagina, srv, ancho, tema);
    const hecho = [];
    try {
      await A.entrar(v);
      await A.ponerTema(v, tema);
      if (ancho === anchos[0]) writeFileSync(join(CAPTURA, `tokens-${tema}.json`), JSON.stringify(await pagina.evaluate(TOKENS), null, 1));
      let previo = null;
      for (const estado of estados) {
        const id = `${estado.id}-${ancho}-${tema}`;
        v.donde = id;
        const t1 = Date.now();
        try {
          if (previo?.salir) await previo.salir(v);
          previo = null;
          if (estado.sinEntrar) {
            // La entrada, como al abrir la app: se sale (el tema elegido se queda en el
            // ordenador) y se carga de nuevo.
            await A.salir(v);
          } else if (await A.$(v, '#token').count()) await A.entrar(v);
          await estado.llegar(v);
          // El raton, fuera de todo: sin nada «con el raton encima».
          await pagina.mouse.move(ancho - 3, 3);
          const { s, png } = await fotograma(v);
          if ((await A.temaVisto(v)) !== tema) throw new Error(`el tema que se ve no es ${tema}`);
          const hojas = [];
          for (const h of s.hojas) hojas.push(await hoja(ctx, h));
          const marco = {
            id,
            estado: estado.id,
            titulo: estado.titulo,
            nota: estado.nota,
            ancho,
            alto: VENTANAS[ancho].height,
            tema,
            html: s.html,
            hojas,
            recursos: s.recursos,
            tipos: s.tipos,
            colores: s.colores,
          };
          writeFileSync(join(CAPTURA, `${id}.json`), JSON.stringify(marco));
          writeFileSync(join(CAPTURA, `${id}.png`), png);
          indice.marcos[id] = { id, estado: estado.id, titulo: estado.titulo, ancho, tema, datos: s.datos, avisos: s.avisos, bytes: s.html.length, ms: Date.now() - t1 };
          hecho.push(`${estado.id}(${Math.round(s.html.length / 1024)}k${s.avisos.length ? ` AVISOS ${s.avisos.join('; ')}` : ''})`);
          previo = estado;
        } catch (error) {
          fallos += 1;
          console.log(`FALLO ${id}: ${String(error?.message ?? error).split('\n')[0]}`);
          await pagina.screenshot({ path: join(CAPTURA, `FALLO-${id}.png`) }).catch(() => {});
          previo = null;
          await A.aInicio(v).catch(() => {});
        }
        guardar();
      }
    } catch (error) {
      fallos += 1;
      console.log(`FALLO pasada ${ancho}-${tema}: ${String(error?.message ?? error).split('\n')[0]} (en ${v.donde})`);
    }
    console.log(`${tema} ${ancho}: ${hecho.join(' ')}`);
    if (v.avisos.length) console.log(`  avisos: ${[...new Set(v.avisos)].join(' | ')}`);
    if (v.errores.length) console.log(`  errores de la app: ${[...new Set(v.errores)].slice(0, 6).join(' | ')}`);
    await ctx.close();
    await srv.parar();
  }
}
guardar();
await browser.close();
console.log(`${fallos ? `CON ${fallos} FALLOS` : 'BIEN'}: ${Object.keys(indice.marcos).length} fotogramas en ${CAPTURA} (${Math.round((Date.now() - t0) / 1000)} s)`);
process.exit(fallos ? 1 : 0);
