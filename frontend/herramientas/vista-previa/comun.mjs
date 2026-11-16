// Lo comun de las tres herramientas (grabar, construir, comprobar): las rutas de esta carpeta y
// del repo que se les da con --repo (por defecto, el que las lleva; del repo SOLO se lee). Los
// argumentos, las dependencias del repo, el Python y el navegador son los de ../entorno.mjs,
// comunes con la herramienta del diseno.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { repoDe as repoComun } from '../entorno.mjs';

export { argumentos, delRepo, falla, navegador, python } from '../entorno.mjs';
export { clave } from './src/rutas.js';

export const AQUI = dirname(fileURLToPath(import.meta.url));
export const TRABAJO = join(AQUI, '.trabajo');
export const GRABACION = join(AQUI, 'grabacion', 'grabacion.json');
export const SALIDA = join(AQUI, 'salida', 'bms-finance-vista-previa.html');

/** Las rutas del repo, comprobadas. */
export function repoDe(args) {
  const { repo, frontend } = repoComun(args, [['frontend/node_modules/vite', 'npm ci en frontend/']]);
  return { repo, frontend, src: join(frontend, 'src'), textos: join(repo, 'src', 'bms_agent', 'textos') };
}

export const espera = (ms) => new Promise((r) => setTimeout(r, ms));
