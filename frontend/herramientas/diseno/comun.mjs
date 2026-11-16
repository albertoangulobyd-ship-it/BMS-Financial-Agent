// comun.mjs — lo comun de las herramientas de esta carpeta (capturar, montar, comprobar y
// comparacion): el repo que se les da con --repo (por defecto, el que las lleva; de el SOLO se
// lee: la base de prueba, lo que escribe el servidor y todo lo demas va a .trabajo/ de esta
// carpeta), el servidor de verdad sobre una base de prueba recien hecha (como
// e2e/global-setup.ts) y el contexto del navegador. Los argumentos, el Python y el navegador (el
// Playwright del repo, sin instalar nada) son los de ../entorno.mjs, comunes con la vista previa.
import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { python, repoDe as repoComun } from '../entorno.mjs';

export { argumentos, falla, navegador } from '../entorno.mjs';

export const AQUI = dirname(fileURLToPath(import.meta.url));
export const TRABAJO = join(AQUI, '.trabajo');
export const CAPTURA = join(AQUI, 'captura');
export const SALIDA = join(AQUI, 'salida', 'bms-finance-diseno.html');

/** Las dos ventanas (las de las pruebas del repo: playwright.config.ts y la del movil). */
export const VENTANAS = { 1440: { width: 1440, height: 900 }, 400: { width: 400, height: 860 } };
export const TEMAS = ['dark', 'light'];
export const NOMBRE_TEMA = { dark: 'oscuro', light: 'claro' };

/** Una lista «a,b,c» de un argumento (o todas). */
export function lista(valor, todas) {
  if (typeof valor !== 'string') return todas;
  const pedidas = valor.split(',').map((s) => s.trim()).filter(Boolean);
  return todas.filter((t) => pedidas.includes(String(t)));
}

/** Las rutas del repo, comprobadas. */
export function repoDe(args) {
  return repoComun(args, [
    ['src/bms_agent/web/index.html', 'la app construida: cd frontend; npm run build'],
    ['frontend/node_modules/playwright-core', 'npm ci en frontend/'],
  ]);
}

export const espera = (ms) => new Promise((r) => setTimeout(r, ms));

function puertoLibre() {
  return new Promise((ok, mal) => {
    const s = createServer();
    s.once('error', mal);
    s.listen(0, '127.0.0.1', () => {
      const a = s.address();
      s.close(() => ok(typeof a === 'object' && a ? a.port : 0));
    });
  });
}

let servidores = 0;

/**
 * Una base de prueba nueva y el servidor de verdad sobre ella (los mismos pasos que
 * e2e/global-setup.ts). Todo lo que se escribe va a .trabajo/ (ni un .pyc en el repo).
 * Devuelve la direccion, los codigos de entrada, los numeros de las facturas por su papel, el
 * lector de las pruebas (scripts/simular_lector.py) y parar().
 */
export async function servidor(repo) {
  servidores += 1;
  const carpeta = join(TRABAJO, `servidor-${process.pid}-${servidores}`);
  rmSync(carpeta, { recursive: true, force: true });
  mkdirSync(carpeta, { recursive: true });
  const env = { ...process.env, PYTHONPATH: join(repo, 'src'), PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' };
  delete env.BMS_DB;
  const py = python(repo);
  const hecha = spawnSync(py, [join(repo, 'scripts', 'crear_demo_e2e.py'), '--carpeta', join(carpeta, 'datos')], { cwd: carpeta, env, encoding: 'utf8' });
  if (hecha.status !== 0) throw new Error(`no se ha podido crear la base de prueba:\n${hecha.stdout}\n${hecha.stderr}`);
  const demo = JSON.parse(hecha.stdout.trim().split('\n').pop());
  env.BMS_DB = demo.db;
  const puerto = await puertoLibre();
  let salida = '';
  const proceso = spawn(py, ['-m', 'bms_agent.cli', 'serve', '--db', demo.db, '--puerto', String(puerto), '--facturas', join(carpeta, 'facturas'), '--out', join(carpeta, 'out')], {
    cwd: carpeta,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  proceso.stdout.on('data', (c) => (salida += c.toString()));
  proceso.stderr.on('data', (c) => (salida += c.toString()));
  const base = `http://127.0.0.1:${puerto}`;
  const fin = Date.now() + 60_000;
  for (;;) {
    if (proceso.exitCode !== null) throw new Error(`bms-agent serve se ha parado:\n${salida}`);
    try {
      if ((await fetch(`${base}/app`)).status === 200) break;
    } catch {
      // Aun no escucha.
    }
    if (Date.now() > fin) throw new Error(`bms-agent serve no contesta en ${base}:\n${salida}`);
    await espera(250);
  }
  const hijos = new Set();
  const argsLector = (mas) => [join(repo, 'scripts', 'simular_lector.py'), '--db', demo.db, ...mas];
  return {
    base,
    tokens: demo.tokens,
    numeros: demo.numeros,
    /** Un paso del lector de las pruebas. */
    lector(...mas) {
      const r = spawnSync(py, argsLector(mas), { env, encoding: 'utf8' });
      if (r.status !== 0) throw new Error(`simular_lector ${mas.join(' ')}: ${r.stderr}`);
      return JSON.parse(r.stdout.trim().split('\n').pop());
    },
    /** El lector leyendo mientras se mira la pantalla. */
    lectorEnFondo(...mas) {
      const hijo = spawn(py, argsLector(mas), { env, stdio: 'ignore' });
      hijos.add(hijo);
      hijo.on('exit', () => hijos.delete(hijo));
      return hijo;
    },
    async parar() {
      for (const h of hijos) h.kill();
      proceso.kill();
      await espera(300);
      // En Windows la base puede seguir abierta un momento despues de parar el servidor.
      rmSync(carpeta, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
    },
  };
}

/** Un contexto como el de las pruebas del repo (playwright.config.ts): neerlandes, Amsterdam,
 *  un pixel por pixel. `colorScheme` no decide el tema de la app (lo decide Ajustes > Tema). */
export function contexto(browser, ancho) {
  return browser.newContext({
    viewport: VENTANAS[ancho],
    deviceScaleFactor: 1,
    locale: 'nl-NL',
    timezoneId: 'Europe/Amsterdam',
    colorScheme: 'light',
    serviceWorkers: 'block',
  });
}
