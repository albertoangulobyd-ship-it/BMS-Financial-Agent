// Comprueba que cada paquete del package-lock.json se publico al menos 14 dias antes
// de una fecha (por defecto, hoy). Necesita red (npm view). Se usa al cambiar
// dependencias: una version recien publicada no ha tenido tiempo de que alguien vea
// si trae algo que no debe. Uso: node scripts/check-lock-age.mjs [AAAA-MM-DD]
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const referencia = process.argv[2] ? new Date(`${process.argv[2]}T00:00:00Z`) : new Date();
const corte = new Date(referencia.getTime() - 14 * 24 * 3600 * 1000);
const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
const paquetes = new Map();
for (const [ruta, info] of Object.entries(lock.packages ?? {})) {
  if (!ruta || !info.version) continue;
  const nombre = info.name ?? ruta.slice(ruta.lastIndexOf('node_modules/') + 'node_modules/'.length);
  paquetes.set(`${nombre}@${info.version}`, { nombre, version: info.version });
}
let malos = 0;
for (const { nombre, version } of paquetes.values()) {
  const fechas = JSON.parse(execFileSync('npm', ['view', nombre, 'time', '--json'], { encoding: 'utf8' }));
  const publicada = fechas[version] ? new Date(fechas[version]) : null;
  if (!publicada || publicada > corte) {
    malos += 1;
    console.log(`DEMASIADO NUEVO o sin fecha: ${nombre}@${version} (${fechas[version] ?? '?'})`);
  }
}
console.log(`${paquetes.size} paquetes; ${malos} publicados despues de ${corte.toISOString().slice(0, 10)}`);
process.exit(malos ? 1 : 0);
