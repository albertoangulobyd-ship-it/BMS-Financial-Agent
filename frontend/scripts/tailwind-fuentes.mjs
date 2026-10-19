// Los ficheros que lee Tailwind para decidir que clases van en el CSS construido, sacados
// igual que los saca @tailwindcss/vite: se compila src/index.css (con sus @source) y se
// pasa el escaner de Tailwind (oxide) con la misma raiz (la de Vite, frontend/). Sirve para
// comprobar que todo lo que lee esta dentro de la huella de lo construido
// (build-inputs.json): si Tailwind leyera una prueba o e2e/, una clase escrita alli
// cambiaria el CSS sin cambiar la huella. Lo usan scripts/fuente.mjs (al construir y al
// comprobar) y scripts/tailwind-fuentes.test.mjs.
import { readFileSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from '@tailwindcss/node';
import { Scanner } from '@tailwindcss/oxide';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const repo = join(frontend, '..');

/** Las fuentes del escaner, como en @tailwindcss/vite (la raiz de Vite y los @source). */
export async function tailwindSources(cssPath = join(frontend, 'src', 'index.css')) {
  const compiler = await compile(readFileSync(cssPath, 'utf8'), {
    base: dirname(cssPath),
    onDependency: () => {},
  });
  const root =
    compiler.root === 'none'
      ? []
      : compiler.root === null
        ? [{ base: frontend, pattern: '**/*', negated: false }]
        : [{ ...compiler.root, negated: false }];
  return root.concat(compiler.sources);
}

/** Los ficheros que lee, con su ruta desde la raiz del repositorio (con /), en orden. */
export async function scannedFiles(cssPath) {
  const scanner = new Scanner({ sources: await tailwindSources(cssPath) });
  scanner.scan();
  return scanner.files.map((path) => relative(repo, path).split(sep).join('/')).sort();
}

/** Los que lee y no estan en `inputs` (las rutas de la huella): tiene que estar vacio. */
export async function outsideInputs(inputs, cssPath) {
  const known = new Set(inputs);
  return (await scannedFiles(cssPath)).filter((path) => !known.has(path));
}
