// La huella de lo que entra en la construccion de la app (build-inputs.json), escrita en
// src/bms_agent/web/fuente.json junto a lo construido. Lo construido va en git (Windows y
// Docker no tienen Node); tests/test_app_local.py vuelve a calcular la huella con el mismo
// algoritmo y falla si alguien cambio el frontend sin volver a construir.
//
// El algoritmo (igual en Python): para cada fichero, en orden de ruta, su sha256 con los
// CRLF cambiados a LF (un checkout de Windows no cambia la huella); la huella es el sha256
// de las lineas "<ruta>\0<sha256>\n". La salida (web/) se apunta byte a byte.
//
//   node scripts/fuente.mjs --escribir    despues de vite build (npm run build lo hace)
//   node scripts/fuente.mjs --comprobar   sale con 1 si la huella no es la de fuente.json
import { createHash } from 'node:crypto';
import { lstatSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = fileURLToPath(new URL('../..', import.meta.url));
const web = join(repo, 'src', 'bms_agent', 'web');
const config = JSON.parse(readFileSync(join(repo, 'frontend', 'build-inputs.json'), 'utf8'));

const sha256 = (data) => createHash('sha256').update(data).digest('hex');
const posix = (path) => relative(repo, path).split(sep).join('/');

function normalized(path) {
  const data = readFileSync(path);
  const out = [];
  for (let i = 0; i < data.length; i += 1) {
    if (data[i] === 0x0d && data[i + 1] === 0x0a) continue;
    out.push(data[i]);
  }
  return Buffer.from(out);
}

function walk(path, excluded, files) {
  const stat = lstatSync(path);
  if (stat.isSymbolicLink()) return;
  if (stat.isDirectory()) {
    for (const name of readdirSync(path)) {
      if (name.startsWith('.')) continue;
      walk(join(path, name), excluded, files);
    }
  } else if (stat.isFile() && !excluded.some((suffix) => path.endsWith(suffix))) {
    files.push(path);
  }
}

export function inputs() {
  const files = [];
  for (const entry of config.include) walk(join(repo, ...entry.split('/')), config.exclude, files);
  const out = {};
  for (const path of files.map(posix).sort()) {
    if (!/^[\x20-\x7e]+$/.test(path)) throw new Error(`ruta que no es ASCII: ${path}`);
    out[path] = sha256(normalized(join(repo, ...path.split('/'))));
  }
  return out;
}

export function total(entries) {
  return sha256(Object.entries(entries).map(([path, hash]) => `${path}\0${hash}\n`).join(''));
}

function outputs() {
  const files = [];
  walk(web, [], files);
  const out = {};
  for (const path of files.sort()) {
    const name = relative(web, path).split(sep).join('/');
    if (name === 'fuente.json') continue;
    out[name] = sha256(readFileSync(path));
  }
  return out;
}

const mode = process.argv[2];
const entries = inputs();
if (mode === '--escribir') {
  const record = {
    _nota:
      'Huella de lo que entra en la construccion de la app (frontend/build-inputs.json) y de lo construido. ' +
      'La escribe frontend/scripts/fuente.mjs al construir; tests/test_app_local.py la comprueba. ' +
      'Para rehacerla: cd frontend; npm ci; npm run build.',
    algoritmo: 'sha256 de "<ruta>\\0<sha256 del fichero con CRLF como LF>\\n", en orden de ruta',
    sha256: total(entries),
    entradas: entries,
    salida: outputs(),
  };
  writeFileSync(join(web, 'fuente.json'), `${JSON.stringify(record, null, 2)}\n`);
  console.log(`fuente.json: ${record.sha256} (${Object.keys(entries).length} entradas, ${Object.keys(record.salida).length} ficheros construidos)`);
} else if (mode === '--comprobar') {
  const record = JSON.parse(readFileSync(join(web, 'fuente.json'), 'utf8'));
  const now = total(entries);
  if (record.sha256 !== now) {
    console.log(`La app construida no es la de estas fuentes (${record.sha256} != ${now}): npm run build`);
    process.exit(1);
  }
  console.log(`Al dia: ${now}`);
} else {
  console.log('uso: node scripts/fuente.mjs --escribir | --comprobar');
  process.exit(2);
}
