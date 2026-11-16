// entorno.mjs — lo que las dos herramientas de esta carpeta (vista-previa/ y diseno/) toman del
// ordenador: el repositorio (por defecto, el que las lleva), sus dependencias
// (frontend/node_modules: aqui no hay ninguna propia), el Python con el que se hace la base de
// prueba y se arranca el servidor, y el Chromium de Playwright. Sin una ruta de ninguna maquina
// y sin nada de la shell: path.join, fileURLToPath y procesos lanzados sin shell, para que valga
// igual en Linux, macOS y Windows.
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { basename, dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

/** El repositorio que lleva esta carpeta (frontend/herramientas/ -> la raiz). */
export const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** Sale con un mensaje claro, sin la traza de un error: lo que falta y que hacer. */
export function falla(mensaje) {
  console.error(`ERROR: ${mensaje}`);
  process.exit(1);
}

/** --clave valor y --bandera (true). Lo que no empieza por -- va a `_`. */
export function argumentos(argv = process.argv.slice(2)) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (!a.startsWith('--')) {
      out._.push(a);
      continue;
    }
    const siguiente = argv[i + 1];
    if (siguiente === undefined || siguiente.startsWith('--')) out[a.slice(2)] = true;
    else {
      out[a.slice(2)] = siguiente;
      i += 1;
    }
  }
  return out;
}

/** El repo de --repo (por defecto, este) y su frontend/, comprobados. `necesita`: pares
 *  [ruta desde la raiz del repo, con /; que hacer si falta]. Del repo solo se lee. */
export function repoDe(args, necesita = []) {
  const repo = resolve(typeof args.repo === 'string' ? args.repo : REPO);
  const frontend = join(repo, 'frontend');
  if (!existsSync(join(frontend, 'src', 'main.tsx'))) falla(`${repo} no es el repo de BMS Finance (falta frontend/src/main.tsx)`);
  for (const [ruta, falta] of necesita) if (!existsSync(join(repo, ...ruta.split('/')))) falla(`${repo}: falta ${ruta} (${falta})`);
  return { repo, frontend };
}

/** Un modulo de las dependencias del repo (su frontend/node_modules). */
export async function delRepo(frontend, nombre) {
  const require = createRequire(join(frontend, 'package.json'));
  return import(pathToFileURL(require.resolve(nombre)).href);
}

let pythonVisto;

/** El Python con el que se hace la base de prueba y se arranca el servidor, como en
 *  e2e/global-setup.ts: BMS_PYTHON; si no, el de .venv del repo (Linux y macOS, o Windows); si
 *  no, python3 o python del PATH. */
export function python(repo) {
  if (pythonVisto) return pythonVisto;
  if (process.env.BMS_PYTHON) return (pythonVisto = process.env.BMS_PYTHON);
  for (const c of [join(repo, '.venv', 'bin', 'python'), join(repo, '.venv', 'Scripts', 'python.exe')]) if (existsSync(c)) return (pythonVisto = c);
  for (const c of ['python3', 'python']) if (spawnSync(c, ['--version'], { stdio: 'ignore' }).status === 0) return (pythonVisto = c);
  return falla(`no hay Python: ni BMS_PYTHON, ni .venv en ${repo}, ni python3 o python en el PATH. Crea el .venv del repo con sus dependencias o pon BMS_PYTHON=<ruta de ese python>.`);
}

const numero = (carpeta) => Number(/-(\d+)$/.exec(carpeta)?.[1] ?? 0);

/** Donde estan los ejecutables dentro de la carpeta de una compilacion, segun el sistema. */
const DENTRO = {
  chromium_headless_shell: [
    ['chrome-headless-shell-linux64', 'chrome-headless-shell'],
    ['chrome-linux', 'headless_shell'],
    ['chrome-headless-shell-win64', 'chrome-headless-shell.exe'],
    ['chrome-win', 'headless_shell.exe'],
    ['chrome-headless-shell-mac-arm64', 'chrome-headless-shell'],
    ['chrome-headless-shell-mac-x64', 'chrome-headless-shell'],
    ['chrome-mac', 'headless_shell'],
  ],
  chromium: [
    ['chrome-linux64', 'chrome'],
    ['chrome-linux', 'chrome'],
    ['chrome-win64', 'chrome.exe'],
    ['chrome-win', 'chrome.exe'],
    ['chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'],
  ],
};

/**
 * El Chromium con el que se graba, se captura y se comprueba. Por defecto, el del Playwright del
 * repo (el mismo que usan las pruebas e2e), en la carpeta de PLAYWRIGHT_BROWSERS_PATH si esta
 * puesta (si no, la de siempre de Playwright). Nunca se instala nada. Si esa compilacion no esta
 * pero en la misma carpeta hay otra, se usa esa y se dice. BMS_CHROMIUM=<ejecutable> dice uno a
 * mano. undefined = el de Playwright.
 */
export function chromium(pw) {
  if (process.env.BMS_CHROMIUM) {
    if (!existsSync(process.env.BMS_CHROMIUM)) falla(`BMS_CHROMIUM=${process.env.BMS_CHROMIUM}: no existe`);
    return process.env.BMS_CHROMIUM;
  }
  let esperado = '';
  try {
    esperado = pw.chromium.executablePath();
  } catch {
    // Un sistema que Playwright no conoce: se busca a mano.
  }
  if (esperado && existsSync(esperado)) return undefined;
  // La carpeta de los navegadores: la de encima de chromium-<compilacion>.
  let carpeta = esperado ? dirname(esperado) : '';
  while (carpeta && !/^chromium-\d+$/.test(basename(carpeta)) && dirname(carpeta) !== carpeta) carpeta = dirname(carpeta);
  const navegadores = /^chromium-\d+$/.test(basename(carpeta)) ? dirname(carpeta) : process.env.PLAYWRIGHT_BROWSERS_PATH;
  const enLaCarpeta = navegadores && existsSync(navegadores) ? readdirSync(navegadores) : [];
  const candidatos = [];
  for (const clase of ['chromium_headless_shell', 'chromium']) {
    const compilaciones = enLaCarpeta.filter((n) => new RegExp(`^${clase}-\\d+$`).test(n)).sort((a, b) => numero(b) - numero(a));
    for (const c of compilaciones) {
      if (clase === 'chromium' && esperado && carpeta) candidatos.push(join(navegadores, c, relative(carpeta, esperado)));
      for (const partes of DENTRO[clase]) candidatos.push(join(navegadores, c, ...partes));
    }
  }
  const encontrado = candidatos.find((c) => existsSync(c));
  if (encontrado) {
    console.error(`aviso: no esta el Chromium que pide Playwright (${esperado || 'desconocido'}); se usa otra compilacion: ${encontrado}`);
    return encontrado;
  }
  return falla(
    `no esta el Chromium que pide el Playwright del repo (${esperado || 'desconocido'}). Es el mismo que usan las pruebas e2e: ` +
      'pon PLAYWRIGHT_BROWSERS_PATH en la carpeta que lo tiene, o BMS_CHROMIUM=<ejecutable de Chromium>.'
  );
}

/** Playwright (el del repo) y un navegador ya abierto. */
export async function navegador(frontend) {
  const pw = (await delRepo(frontend, 'playwright-core')).default;
  const executablePath = chromium(pw);
  const browser = await pw.chromium.launch(executablePath ? { executablePath } : {});
  return { pw, browser };
}
