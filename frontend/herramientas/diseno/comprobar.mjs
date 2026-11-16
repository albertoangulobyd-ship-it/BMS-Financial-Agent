// comprobar.mjs — la comprobacion del fichero de diseno, abierto como lo abre una persona
// (file://, sin red):
//   - carga sin errores en la consola y sin pedir nada a la red;
//   - la primera pagina trae los colores y la escala de letra, y el indice filtra por tema y ancho;
//   - CADA fotograma se monta, no esta vacio (sus elementos y su texto son los de la app) y se ve
//     como la foto de la pantalla viva del mismo estado, dentro de una tolerancia.
//
//   node comprobar.mjs [--repo <ruta>] [--fichero <html>] [--captura <carpeta>] [--solo id,id]
//
// El repo (por defecto, el que lleva esta carpeta) solo hace falta para cargar su Playwright
// (aqui no hay dependencias). Escribe salida/comprobacion.json y sale con 0 si todo esta bien.
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { argumentos, CAPTURA, espera, falla, navegador, repoDe, SALIDA, TRABAJO } from './comun.mjs';

const args = argumentos();
const { frontend } = repoDe(args);
const fichero = typeof args.fichero === 'string' ? resolve(args.fichero) : SALIDA;
const carpeta = typeof args.captura === 'string' ? resolve(args.captura) : CAPTURA;
if (!existsSync(join(carpeta, 'captura.json'))) {
  falla(`no hay nada capturado en ${carpeta}: primero npm run diseno:capturar (o node herramientas/diseno/capturar.mjs; unos 9 min)`);
}
const indice = JSON.parse(readFileSync(join(carpeta, 'captura.json'), 'utf8'));
const soloIds = typeof args.solo === 'string' ? args.solo.split(',') : null;

/** La tolerancia entre el fotograma y la pantalla viva. Un pixel «distinto» es el que cambia mas
 *  de 48 niveles en algun canal (el suavizado de la letra y el WebP de las texturas quedan por
 *  debajo). Se admite hasta un 1 % de pixeles distintos y una diferencia media de 1,5 niveles. */
const TOLERANCIA = { nivel: 48, distintos: 0.01, media: 1.5 };
const MAX_BYTES = 12 * 1024 * 1024;

/** Dentro de una pagina en blanco: compara dos PNG pixel a pixel. */
async function comparar(a, b, nivel) {
  const leer = async (b64) => {
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const bmp = await createImageBitmap(new Blob([bin], { type: 'image/png' }));
    const lienzo = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = lienzo.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0);
    return ctx.getImageData(0, 0, bmp.width, bmp.height);
  };
  const [x, y] = await Promise.all([leer(a), leer(b)]);
  if (x.width !== y.width || x.height !== y.height) return { medidas: `${x.width}x${x.height} / ${y.width}x${y.height}`, distintos: 1, media: 255, colores: 0 };
  let distintos = 0;
  let suma = 0;
  const vistos = new Set();
  const n = x.width * x.height;
  for (let i = 0; i < n; i += 1) {
    const k = i * 4;
    const d = Math.max(Math.abs(x.data[k] - y.data[k]), Math.abs(x.data[k + 1] - y.data[k + 1]), Math.abs(x.data[k + 2] - y.data[k + 2]));
    suma += d;
    if (d > nivel) distintos += 1;
    if (i % 97 === 0 && vistos.size < 4096) vistos.add((x.data[k] << 16) | (x.data[k + 1] << 8) | x.data[k + 2]);
  }
  return { medidas: `${x.width}x${x.height}`, distintos: distintos / n, media: suma / n, colores: vistos.size };
}

const fallos = [];
const mal = (que) => {
  fallos.push(que);
  console.log(`MAL: ${que}`);
};

if (!existsSync(fichero)) {
  console.log(`MAL: no existe ${fichero}`);
  process.exit(1);
}
const bytes = statSync(fichero).size;
if (bytes > MAX_BYTES) mal(`el fichero pesa ${bytes} bytes (mas de 12 MB)`);
const fuente = readFileSync(fichero, 'utf8');
// Nada de fuera: ni hojas, ni guiones, ni imagenes, ni letras con direccion.
const deFuera = fuente.match(/<(?:link|script|img|iframe|source)\b[^>]*\s(?:src|href)\s*=\s*["']?(?:https?:)?\/\/[^"'\s>]+/gi) ?? [];
if (deFuera.length) mal(`el fichero nombra recursos de fuera: ${deFuera.slice(0, 3).join(' ; ')}`);
const urlsCss = fuente.match(/url\(\s*(?!(?:["']|&quot;)?(?:data:|df-recurso:|#))[^)]{0,80}/gi) ?? [];
if (urlsCss.length) mal(`el fichero lleva url() que no son data: ${urlsCss.slice(0, 3).join(' ; ')}`);

const { browser } = await navegador(frontend);
const ctx = await browser.newContext({ viewport: { width: 1500, height: 960 }, deviceScaleFactor: 1, locale: 'nl-NL', timezoneId: 'Europe/Amsterdam', colorScheme: 'light', offline: true });
const red = [];
const consola = [];
await ctx.route('**/*', (r) => {
  const u = r.request().url();
  if (u.startsWith('file:')) return r.continue();
  red.push(u);
  return r.abort();
});
const pagina = await ctx.newPage();
pagina.on('request', (r) => {
  if (!/^(file|data|blob|about):/.test(r.url())) red.push(r.url());
});
pagina.on('console', (m) => {
  if (m.type() === 'error') consola.push(m.text());
});
pagina.on('pageerror', (e) => consola.push(`pageerror: ${e.message}`));
const medidor = await ctx.newPage();
await medidor.evaluate(`window.__comparar = ${comparar.toString()}`);

const t0 = Date.now();
const url = pathToFileURL(fichero).href;
await pagina.goto(url);
await pagina.waitForSelector('html[data-df-listo]', { timeout: 30_000 });

// ---------------------------------------------------------------- la primera pagina y el indice
const portada = await pagina.evaluate(() => ({
  marcos: [...document.querySelectorAll('article.marco')].map((a) => ({ id: a.dataset.id, tema: a.dataset.tema, ancho: a.dataset.ancho })),
  tokens: [...document.querySelectorAll('#colores tr[data-token]')].map((tr) => ({ nombre: tr.dataset.token, muestras: tr.querySelectorAll('.muestra i').length })),
  temasConTokens: [3, 5].map((n) => document.querySelectorAll(`#colores tr[data-token] td:nth-child(${n}) code`).length),
  uso: document.querySelectorAll('#colores .uso tr').length,
  letra: document.querySelectorAll('#letra table.letra tbody tr').length,
  indice: document.querySelectorAll('ol.indice li').length,
  muestrasSinColor: [...document.querySelectorAll('.muestra i')].filter((i) => !i.style.background).length,
  temas: [...document.querySelectorAll('button[data-filtro="tema"]')].map((b) => b.dataset.valor),
  anchos: [...document.querySelectorAll('button[data-filtro="ancho"]')].map((b) => b.dataset.valor),
}));
const esperados = Object.keys(indice.marcos);
if (portada.marcos.length !== esperados.length) mal(`el fichero trae ${portada.marcos.length} fotogramas y la captura ${esperados.length}`);
if (portada.tokens.length < 20) mal(`pocos colores con nombre en la primera pagina (${portada.tokens.length})`);
const temasCapturados = [...new Set(Object.values(indice.marcos).map((m) => m.tema))];
const anchosCapturados = [...new Set(Object.values(indice.marcos).map((m) => String(m.ancho)))];
for (const [k, tema] of ['dark', 'light'].entries()) if (temasCapturados.includes(tema) && portada.temasConTokens[k] < 10) mal(`faltan los colores con nombre del tema ${tema} (${portada.temasConTokens[k]})`);
if (temasCapturados.some((t) => !portada.temas.includes(t)) || anchosCapturados.some((a) => !portada.anchos.includes(a))) mal(`el indice no deja filtrar por ${temasCapturados} y ${anchosCapturados}`);
if (portada.uso < 20) mal(`pocos colores en uso (${portada.uso})`);
if (portada.letra < 5) mal(`la escala de letra tiene ${portada.letra} cuerpos`);
if (portada.muestrasSinColor) mal(`${portada.muestrasSinColor} muestras de color sin color`);
const visibles = () => pagina.evaluate(() => [...document.querySelectorAll('article.marco')].filter((a) => !a.hidden).map((a) => `${a.dataset.tema}/${a.dataset.ancho}`));
const filtros = {};
for (const [filtro, valor] of [...portada.temas.filter((t) => t !== 'todos').map((t) => ['tema', t]), ['tema', 'todos'], ...portada.anchos.filter((a) => a !== 'todos').map((a) => ['ancho', a]), ['ancho', 'todos']]) {
  await pagina.click(`button[data-filtro="${filtro}"][data-valor="${valor}"]`);
  const v = await visibles();
  filtros[`${filtro}=${valor}`] = v.length;
  const debe = portada.marcos.filter((m) => valor === 'todos' || m[filtro] === valor).length;
  if (v.length !== debe || (valor !== 'todos' && v.some((x) => !x.split('/').includes(valor)))) mal(`el filtro ${filtro}=${valor} deja ${v.length} fotogramas y deben ser ${debe}`);
}
// Con el indice a la vista y todo sin filtrar, los fotogramas cercanos se montan solos.
await pagina.evaluate(() => document.getElementById('fotogramas').scrollIntoView());
await pagina.waitForFunction(() => document.querySelectorAll('article.marco[data-cargado]').length > 0, null, { timeout: 15_000 }).catch(() => mal('ningun fotograma se monta al llegar a la galeria'));

// ---------------------------------------------------------------- cada fotograma
const resultados = [];
const dirMal = join(TRABAJO, 'comprobar');
mkdirSync(dirMal, { recursive: true });
for (const m of portada.marcos) {
  if (soloIds && !soloIds.includes(m.id)) continue;
  const dato = indice.marcos[m.id];
  const viva = join(carpeta, `${m.id}.png`);
  const r = { id: m.id };
  resultados.push(r);
  try {
    if (!dato || !existsSync(viva)) throw new Error('sin su captura viva');
    await pagina.evaluate((id) => {
      location.hash = `#solo=${id}`;
    }, m.id);
    const marco = pagina.locator(`article.marco[data-id="${m.id}"] iframe`);
    await marco.waitFor({ state: 'visible', timeout: 15_000 });
    const dentro = await (await marco.elementHandle()).contentFrame();
    await dentro.waitForSelector('html[data-df-listo]', { state: 'attached', timeout: 20_000 });
    await dentro.evaluate(async () => {
      await document.fonts.ready;
      await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    });
    await espera(120);
    const caja = await marco.boundingBox();
    const info = await dentro.evaluate(() => ({ elementos: document.querySelectorAll('*').length, texto: (document.body.innerText ?? '').trim().length, ventana: [innerWidth, innerHeight], canvas: document.querySelectorAll('canvas[data-df-canvas]').length, guiones: document.scripts.length }));
    Object.assign(r, info);
    if (!caja || caja.x !== 0 || caja.y !== 0 || caja.width !== dato.ancho || info.ventana[0] !== dato.ancho || info.ventana[1] !== dato.datos.ventana[1]) throw new Error(`el marco mide ${JSON.stringify(caja)} y su ventana ${info.ventana}`);
    // No esta vacio: los elementos y el texto de la app (los guiones y enlaces de carga se quitan).
    if (info.elementos < dato.datos.elementos * 0.9 || info.elementos > dato.datos.elementos + 4) throw new Error(`tiene ${info.elementos} elementos y la app tenia ${dato.datos.elementos}`);
    if (Math.abs(info.texto - dato.datos.texto) > Math.max(8, dato.datos.texto * 0.03)) throw new Error(`tiene ${info.texto} letras a la vista y la app tenia ${dato.datos.texto}`);
    if (info.canvas !== dato.datos.canvas) throw new Error(`tiene ${info.canvas} canvas con imagen y la app tenia ${dato.datos.canvas}`);
    const foto = await pagina.screenshot({ clip: { x: 0, y: 0, width: dato.ancho, height: info.ventana[1] }, caret: 'hide' });
    const c = await medidor.evaluate(([x, y, nivel]) => window.__comparar(x, y, nivel), [foto.toString('base64'), readFileSync(viva).toString('base64'), TOLERANCIA.nivel]);
    Object.assign(r, { distintos: Number((c.distintos * 100).toFixed(3)), media: Number(c.media.toFixed(3)), colores: c.colores });
    if (c.colores < 8) throw new Error(`se ve vacio (${c.colores} colores)`);
    if (c.distintos > TOLERANCIA.distintos || c.media > TOLERANCIA.media) {
      writeFileSync(join(dirMal, `${m.id}.png`), foto);
      throw new Error(`no se ve como la pantalla viva: ${r.distintos} % de pixeles distintos, diferencia media ${r.media} (${c.medidas})`);
    }
    r.bien = true;
  } catch (error) {
    r.bien = false;
    r.error = String(error?.message ?? error).split('\n')[0];
    mal(`${m.id}: ${r.error}`);
  }
}
await pagina.evaluate(() => {
  location.hash = '#fotogramas';
});
await espera(300);

if (red.length) mal(`pide a la red: ${[...new Set(red)].slice(0, 5).join(' ; ')}`);
if (consola.length) mal(`errores en la consola: ${[...new Set(consola)].slice(0, 5).join(' ; ')}`);
await browser.close();

const peor = [...resultados].filter((r) => typeof r.distintos === 'number').sort((a, b) => b.distintos - a.distintos).slice(0, 5).map((r) => `${r.id} ${r.distintos} %`);
const informe = {
  bien: fallos.length === 0,
  fichero,
  bytes,
  fecha: new Date().toISOString(),
  tolerancia: TOLERANCIA,
  fotogramas: resultados.length,
  fotogramasBien: resultados.filter((r) => r.bien).length,
  portada: { tokens: portada.tokens.length, coloresEnUso: portada.uso, cuerposDeLetra: portada.letra, estadosEnElIndice: portada.indice, filtros },
  red,
  consola,
  fallos,
  peores: peor,
  resultados,
};
writeFileSync(join(dirname(fichero), 'comprobacion.json'), JSON.stringify(informe, null, 1));
console.log(`${informe.bien ? 'BIEN' : `MAL (${fallos.length} fallos)`}: ${informe.fotogramasBien} de ${resultados.length} fotogramas como la pantalla viva; ${bytes} bytes; red ${red.length}, consola ${consola.length}; los que mas difieren: ${peor.join(', ')} (${Math.round((Date.now() - t0) / 1000)} s)`);
process.exit(informe.bien ? 0 : 1);
