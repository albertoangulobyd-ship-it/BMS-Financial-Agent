#!/usr/bin/env node
// construir.mjs — hace la vista previa navegable: UN .html sin red con la app de verdad.
//
//   node construir.mjs [--repo <ruta del repo>] [--grabacion grabacion/grabacion.json]
//                      [--salida salida/bms-finance-vista-previa.html]
//
// --repo es por defecto el repo que lleva esta carpeta. Del repo SOLO se lee: el codigo de
// frontend/src (por su entrada de verdad, main.tsx), sus dependencias (frontend/node_modules:
// vite, el plugin de React y el de Tailwind) y los catalogos de src/bms_agent/textos. No se usa su vite.config.ts (cargarlo escribiria en
// node_modules/.vite-temp): la configuracion de aqui abajo repite lo que importa de ella (los
// plugins, el alias @ y el target) y cambia lo que hace falta para un solo fichero: una entrada
// propia (src/entrada.js: el shim y despues la app), todo en un chunk (inlineDynamicImports),
// los ficheros como data: y una sola hoja. Lo construido va a .trabajo/dist y de ahi sale el
// .html: <title>, UN <style> (el CSS de la app y despues src/vista-previa.css), el cuerpo
// (src/cuerpo.html) y UN <script type="module">. Sin <html> ni <head> propios: quien lo publica
// lo envuelve (y directamente desde el disco el navegador lo abre igual).
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { AQUI, GRABACION, SALIDA, TRABAJO, argumentos, delRepo, falla, repoDe } from './comun.mjs';
import { TEXTOS_VP } from './src/textos-vp.js';

const MAXIMO = 10 * 1024 * 1024;

const args = argumentos();
const { repo, frontend, src, textos } = repoDe(args);
const grabacion = resolve(typeof args.grabacion === 'string' ? args.grabacion : GRABACION);
const salida = resolve(typeof args.salida === 'string' ? args.salida : SALIDA);
if (!existsSync(grabacion)) {
  // La grabacion no va en git: se hace con grabar.mjs (una vez, y otra si cambia la API).
  falla(
    `todavia no hay grabacion (${grabacion}). Primero, desde frontend/: npm run vista-previa:grabar ` +
      `(o node herramientas/vista-previa/grabar.mjs; unos 10 min), y despues otra vez esta orden.`
  );
}
const dist = join(TRABAJO, 'dist');

const vite = await delRepo(frontend, 'vite');
const react = (await delRepo(frontend, '@vitejs/plugin-react')).default;
const tailwindcss = (await delRepo(frontend, '@tailwindcss/vite')).default;

/** Los dos codigos de la vista previa, en el catalogo de errores de cada idioma (en memoria: el
 *  fichero del repo no se toca). */
function erroresDeLaVistaPrevia() {
  const catalogo = /[\\/]bms_agent[\\/]textos[\\/](nl|en|es)\.json$/;
  let hechos = 0;
  return {
    name: 'vp:errores',
    enforce: 'pre',
    transform(code, id) {
      const m = catalogo.exec(id.split('?')[0]);
      if (!m) return null;
      const datos = JSON.parse(code);
      if (!datos.errores || typeof datos.errores !== 'object') throw new Error(`${id}: sin seccion "errores"`);
      Object.assign(datos.errores, TEXTOS_VP[m[1]]);
      hechos += 1;
      return { code: JSON.stringify(datos), map: null };
    },
    buildEnd() {
      if (hechos !== 3) this.error(`se esperaban los tres catalogos de textos (nl, en, es) y han pasado ${hechos}`);
    },
  };
}

rmSync(dist, { recursive: true, force: true });
await vite.build({
  configFile: false,
  envFile: false,
  root: frontend,
  base: './',
  publicDir: false,
  cacheDir: join(TRABAJO, 'vite-cache'),
  logLevel: 'warn',
  plugins: [erroresDeLaVistaPrevia(), react(), tailwindcss()],
  // Solo ASCII en lo construido (el JS y el CSS; el cuerpo, mas abajo): el fichero sale sin
  // <meta charset> propio (lo pone quien lo publica) y, abierto tal cual desde el disco, el
  // navegador adivina la codificacion; si adivina mal, una expresion regular con letras
  // acentuadas rompe la app antes de pintar nada. Con escapes no hay nada que adivinar.
  esbuild: { charset: 'ascii' },
  resolve: {
    alias: [
      { find: '@vp/grabacion', replacement: grabacion },
      { find: '@vp/app', replacement: join(src, 'main.tsx') },
      { find: '@', replacement: src },
    ],
  },
  build: {
    outDir: dist,
    emptyOutDir: true,
    write: true,
    target: 'es2022',
    sourcemap: false,
    modulePreload: false,
    cssCodeSplit: false,
    reportCompressedSize: false,
    chunkSizeWarningLimit: 20_000,
    // Todo en linea: aqui no hay de donde traer un fichero.
    assetsInlineLimit: () => true,
    rollupOptions: {
      input: join(AQUI, 'src', 'entrada.js'),
      output: { format: 'es', inlineDynamicImports: true, entryFileNames: 'app.js', assetFileNames: '[name][extname]' },
    },
  },
});

function ficheros(carpeta) {
  return readdirSync(carpeta, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? ficheros(join(carpeta, e.name)) : [join(carpeta, e.name)]));
}
const construidos = ficheros(dist);
const js = construidos.filter((f) => f.endsWith('.js'));
const css = construidos.filter((f) => f.endsWith('.css'));
const otros = construidos.filter((f) => !f.endsWith('.js') && !f.endsWith('.css'));
if (js.length !== 1 || css.length !== 1 || otros.length !== 0) {
  throw new Error(`se esperaba un .js y un .css y nada mas, y hay: ${construidos.map((f) => f.slice(dist.length + 1)).join(', ')}`);
}

// ------------------------------------------------------------------ el fichero

/** Dentro de <script>, «</script» cierra el bloque y «<!--» cambia como lo lee el navegador; y
 *  quien publique el fichero puede contar o buscar «<script». En el bundle solo pueden estar
 *  dentro de un texto, donde «<\/», «<\!» y «\x3C» dicen lo mismo (asi lo llevaba el fichero
 *  anterior). Fuera de un texto serian un error de sintaxis: se comprueba despues con node. */
function paraScript(codigo) {
  let cuenta = 0;
  const limpio = codigo
    .replace(/<\/(script)/gi, (_, s) => ((cuenta += 1), `<\\/${s}`))
    .replace(/<!--/g, () => ((cuenta += 1), '<\\!--'))
    .replace(/<(script)/gi, (_, s) => ((cuenta += 1), `\\x3C${s}`));
  return { limpio, cuenta };
}

const indice = readFileSync(join(frontend, 'index.html'), 'utf8');
const titulo = /<title>([^<]*)<\/title>/.exec(indice)?.[1] ?? 'BMS Finance';
const noscript = (/<noscript>[\s\S]*?<\/noscript>/.exec(indice)?.[0] ?? '').replace(/\s+/g, ' ');
// Las bandas del servidor (DATOS DE PRUEBA): las que grabo grabar.mjs de /app, o la de siempre.
const pagina = join(dirname(grabacion), 'pagina.json');
const bandas = existsSync(pagina) ? JSON.parse(readFileSync(pagina, 'utf8')).bandas : null;
const bandaPorDefecto = readFileSync(join(AQUI, 'src', 'banda-por-defecto.html'), 'utf8').trim();
const cuerpo = readFileSync(join(AQUI, 'src', 'cuerpo.html'), 'utf8')
  .replace('<!--vp:bandas-->', () => (typeof bandas === 'string' && bandas.trim() ? bandas.trim() : bandaPorDefecto))
  .replace('<!--vp:noscript-->', () => noscript);

/** Lo que no es ASCII, como referencia numerica de HTML (en un texto o en un atributo dice lo mismo). */
const enHtml = (texto) => texto.replace(/[\u0080-\uffff]/g, (c) => `&#${c.charCodeAt(0)};`);
/** Lo que no es ASCII, como escape de CSS. */
const enCss = (texto) => texto.replace(/[\u0080-\uffff]/g, (c) => `\\${c.charCodeAt(0).toString(16)} `);
/** Lo que no es ASCII, como escape de JavaScript (por si el minificador deja algo). */
const enJs = (texto) => texto.replace(/[\u0080-\uffff]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);

const hoja = enCss(readFileSync(css[0], 'utf8').trimEnd() + '\n\n\n' + readFileSync(join(AQUI, 'src', 'vista-previa.css'), 'utf8'));
if (/<\/style/i.test(hoja)) throw new Error('el CSS lleva «</style»: no se puede poner en linea');
const { limpio: codigo, cuenta: escapados } = paraScript(enJs(readFileSync(js[0], 'utf8')));

// Lo escapado sigue siendo el mismo programa: node lo lee entero sin correrlo.
const comprobado = join(dist, 'app.comprobado.mjs');
writeFileSync(comprobado, codigo);
execFileSync(process.execPath, ['--check', comprobado], { stdio: ['ignore', 'ignore', 'inherit'] });
rmSync(comprobado);

const html = `<title>${enHtml(titulo)}</title>\n<style>${hoja}</style>\n${enHtml(cuerpo)}<script type="module">${codigo.trimEnd()}\n</script>\n`;
if (/[^\x00-\x7f]/.test(html)) throw new Error('el fichero lleva algo que no es ASCII');
mkdirSync(dirname(salida), { recursive: true });
writeFileSync(salida, html);

const bytes = statSync(salida).size;
let commit = '';
try {
  // Sin candados opcionales: asi `git status` no refresca (no escribe) el indice del repo.
  const git = (...orden) => execFileSync('git', ['--no-optional-locks', '-C', repo, ...orden], { encoding: 'utf8', env: { ...process.env, GIT_OPTIONAL_LOCKS: '0' } }).trim();
  commit = git('rev-parse', '--short', 'HEAD');
  if (git('status', '--porcelain', '--', 'frontend/src', 'src/bms_agent/textos')) commit += '+cambios';
} catch {
  // Sin git: no se dice el commit.
}
const g = JSON.parse(readFileSync(grabacion, 'utf8'));
const informe = {
  salida,
  bytes,
  sha256: createHash('sha256').update(html).digest('hex'),
  repo,
  commit,
  grabacion,
  grabado: g.grabado,
  contrato: g.contrato,
  respuestas: Object.keys(g.respuestas).length,
  descargas: g.descargas.length,
  pasos_lectura: g.lectura?.pasos?.length ?? 0,
  css_bytes: Buffer.byteLength(hoja),
  js_bytes: Buffer.byteLength(codigo),
  escapados_en_script: escapados,
};
writeFileSync(join(dirname(salida), 'construccion.json'), JSON.stringify(informe, null, 2) + '\n');
console.log(JSON.stringify(informe, null, 2));
if (bytes >= MAXIMO) {
  console.error(`DEMASIADO GRANDE: ${bytes} bytes (el tope son ${MAXIMO})`);
  process.exit(1);
}
