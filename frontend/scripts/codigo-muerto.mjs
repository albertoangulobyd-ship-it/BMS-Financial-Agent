// Lo que esta en frontend/src y la app no usa (puerta del paso 16, G2: sin codigo muerto). Las
// piezas de Aurora que esperan a un paso posterior (el cargador y la tarjeta de Procesar) no se
// quedan sin montar en src: vuelven de la copia del prototipo cuando su paso las monte. Cuatro
// miradas, todas sin construir:
// - los ficheros: lo que no se alcanza desde src/main.tsx siguiendo los import (y los @import
//   de las hojas);
// - lo exportado: cada declaracion exportada que nadie nombra (ni la app, ni una prueba, ni e2e);
// - la paleta de Aurora: cada variable --au-* que ninguna hoja ni pantalla usa;
// - las hojas: cada clase que ninguna pantalla pone.
// Lo usa scripts/codigo-muerto.test.mjs (npm test). A mano: node scripts/codigo-muerto.mjs
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const src = join(frontend, 'src');

const posix = (path) => relative(frontend, path).split(sep).join('/');
const isTest = (path) => /\.test\.tsx?$/.test(path);
const read = (path) => readFileSync(path, 'utf8');

function filesUnder(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? filesUnder(path) : [path];
  });
}

/** Los ficheros de src que entran en la app (sin pruebas): .ts, .tsx y .css. */
export function sourceFiles() {
  return filesUnder(src).filter((path) => /\.(tsx?|css)$/.test(path) && !isTest(path));
}

function resolveImport(from, spec) {
  let base;
  if (spec.startsWith('@/')) base = join(src, spec.slice(2));
  else if (spec.startsWith('.')) base = resolve(dirname(from), spec);
  else return null; // un paquete
  for (const candidate of [base, `${base}.ts`, `${base}.tsx`, join(base, 'index.ts'), join(base, 'index.tsx')]) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return null;
}

function importsOf(path) {
  const text = read(path);
  if (path.endsWith('.css')) {
    return [...text.matchAll(/@import\s+["']([^"']+)["']/g)].map((m) => m[1]);
  }
  // El analisis de TypeScript (import, export ... from, import() y los import de una hoja).
  return ts.preProcessFile(text, true, true).importedFiles.map((f) => f.fileName);
}

/** Lo que src/main.tsx alcanza, como rutas desde frontend/ (con /). */
export function reachedFiles() {
  const seen = new Set();
  const pending = [join(src, 'main.tsx')];
  while (pending.length) {
    const path = pending.pop();
    if (seen.has(path)) continue;
    seen.add(path);
    for (const spec of importsOf(path)) {
      const target = resolveImport(path, spec);
      if (target && target.startsWith(src)) pending.push(target);
    }
  }
  return new Set([...seen].map(posix));
}

/** Los ficheros de src (sin pruebas) que la app no alcanza, en orden. */
export function unreachedFiles() {
  const reached = reachedFiles();
  return sourceFiles().map(posix).filter((path) => !reached.has(path)).sort();
}

/** Los ficheros que importan las pruebas (vitest y e2e), como rutas desde frontend/. */
export function filesImportedByTests() {
  const tests = [
    ...filesUnder(src).filter(isTest),
    ...filesUnder(join(frontend, 'e2e')).filter((path) => path.endsWith('.ts')),
  ];
  const out = new Set();
  for (const test of tests) {
    for (const spec of importsOf(test)) {
      const target = resolveImport(test, spec);
      if (target && target.startsWith(src)) out.add(posix(target));
    }
  }
  return out;
}

/** Las declaraciones exportadas de src que nadie nombra fuera de su declaracion: ni el resto de
 *  su fichero, ni otro fichero de la app, ni una prueba, ni e2e. `skip` deja fuera carpetas
 *  (rutas desde frontend/ que empiezan asi). */
export function unusedExports({ skip = [] } = {}) {
  const configPath = join(frontend, 'tsconfig.app.json');
  const config = ts.parseJsonConfigFileContent(ts.readConfigFile(configPath, ts.sys.readFile).config, ts.sys, frontend);
  // e2e entra para buscar referencias (importa de src), aunque compile con su propia configuracion.
  const roots = [...config.fileNames, ...filesUnder(join(frontend, 'e2e')).filter((path) => path.endsWith('.ts'))];
  const host = {
    getScriptFileNames: () => roots,
    getScriptVersion: () => '1',
    getScriptSnapshot: (path) => (existsSync(path) ? ts.ScriptSnapshot.fromString(read(path)) : undefined),
    getCurrentDirectory: () => frontend,
    getCompilationSettings: () => config.options,
    getDefaultLibFileName: (options) => ts.getDefaultLibFilePath(options),
    fileExists: ts.sys.fileExists,
    readFile: ts.sys.readFile,
    readDirectory: ts.sys.readDirectory,
    directoryExists: ts.sys.directoryExists,
    getDirectories: ts.sys.getDirectories,
  };
  const service = ts.createLanguageService(host, ts.createDocumentRegistry());
  const program = service.getProgram();
  const out = [];
  for (const file of config.fileNames) {
    const name = posix(file);
    if (isTest(file) || skip.some((prefix) => name.startsWith(prefix))) continue;
    for (const statement of program.getSourceFile(file).statements) {
      const exported = ts.canHaveModifiers(statement) &&
        (ts.getModifiers(statement) ?? []).some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
      if (!exported) continue;
      const names = ts.isVariableStatement(statement)
        ? statement.declarationList.declarations.map((d) => d.name)
        : statement.name
          ? [statement.name]
          : [];
      for (const id of names) {
        const references = (service.findReferences(file, id.getStart()) ?? [])
          .flatMap((symbol) => symbol.references)
          .filter((ref) => !ref.isDefinition);
        if (references.length === 0) out.push(`${name}: ${id.getText()}`);
      }
    }
  }
  return out.sort();
}

/** Las variables de aurora/palette.css que nadie usa (ni una hoja, ni una pantalla, ni otra
 *  variable de la paleta). */
export function unusedPaletteTokens() {
  const palettePath = join(src, 'aurora', 'palette.css');
  const palette = read(palettePath);
  const elsewhere = sourceFiles().filter((path) => path !== palettePath).map(read).join('\n');
  const insidePalette = new Set([...palette.matchAll(/var\((--au-[\w-]+)/g)].map((m) => m[1]));
  const tokens = new Set([...palette.matchAll(/(--au-[\w-]+)\s*:/g)].map((m) => m[1]));
  return [...tokens]
    .filter((token) => !insidePalette.has(token) && !new RegExp(`${token}(?![\\w-])`).test(elsewhere))
    .sort();
}

/** Las clases de las hojas de src que ninguna pantalla pone (ni index.html). `external` son las
 *  que pone otro (el servidor, las bandas); `verbatim`, las hojas que se copian tal cual de la
 *  entrega del dueno (rutas desde frontend/): sus reglas son las suyas aunque una pieza aun no
 *  las use. */
export function unusedClasses({ external = [], verbatim = [] } = {}) {
  const code = [
    ...sourceFiles().filter((path) => !path.endsWith('.css')),
    join(frontend, 'index.html'),
  ].map(read).join('\n');
  const out = [];
  for (const sheet of sourceFiles().filter((path) => path.endsWith('.css') && !verbatim.includes(posix(path)))) {
    const text = read(sheet).replace(/\/\*[\s\S]*?\*\//g, '').replace(/url\([^)]*\)/g, '');
    const classes = new Set([...text.matchAll(/(?<![\w-])\.([a-zA-Z_][\w-]*)/g)].map((m) => m[1]));
    for (const name of classes) {
      if (external.includes(name)) continue;
      const escaped = name.replace(/[-]/g, '\\-');
      if (!new RegExp(`(?<![\\w-])${escaped}(?![\\w-])`).test(code)) out.push(`${posix(sheet)}: .${name}`);
    }
  }
  return out.sort();
}

const escapeDots = (text) => text.replace(/[.$]/g, (c) => `\\${c}`);

/** Las pantallas (el codigo de la app sin pruebas ni diccionarios), como [ruta, texto]. */
function screenSources() {
  return sourceFiles()
    .filter((path) => !path.endsWith('.css') && !posix(path).startsWith('src/i18n/'))
    .map((path) => [posix(path), read(path)]);
}

/** Si un codigo lee el texto `path` (["aurora", "search", "noAmount"]): con su ruta entera
 *  (t.aurora.search.noAmount) o desde un alias de una parte de ella (const texts =
 *  t.aurora.search; ... texts.noAmount). */
export function readsText(code, path) {
  for (let cut = path.length; cut >= 2; cut -= 1) {
    const head = path.slice(0, cut).join('.');
    const rest = path.slice(cut).join('.');
    if (!new RegExp(`\\bt\\.${escapeDots(head)}(?![\\w$])`).test(code)) continue;
    if (!rest || new RegExp(`\\.${escapeDots(rest)}(?![\\w$])`).test(code)) return true;
  }
  return false;
}

/** Las pantallas que leen un texto (rutas desde frontend/). */
export function filesReading(path) {
  return screenSources()
    .filter(([, code]) => readsText(code, path))
    .map(([name]) => name);
}

/** Los textos de un grupo de un diccionario (`messages[group]`) que ninguna pantalla lee. */
export function unusedTexts(messages, group) {
  const leaves = [];
  const walk = (node, path) => {
    for (const [key, value] of Object.entries(node)) {
      if (value && typeof value === 'object') walk(value, [...path, key]);
      else leaves.push([...path, key]);
    }
  };
  walk(messages[group], [group]);
  const codes = screenSources().map(([, code]) => code);
  return leaves.filter((path) => !codes.some((code) => readsText(code, path))).map((path) => path.join('.'));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const report = {
    unreachedFiles: unreachedFiles(),
    unusedExports: unusedExports(),
    unusedPaletteTokens: unusedPaletteTokens(),
    unusedClasses: unusedClasses(),
  };
  console.log(JSON.stringify(report, null, 2));
}
