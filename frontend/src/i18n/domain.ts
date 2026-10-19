// Los textos de dominio (prioridades, estados, reglas...) salen de los catalogos de
// Python, src/bms_agent/textos/nl.json y en.json, que la app importa al construirse: asi
// la CLI, la auditoria y la app dicen lo mismo y no hay una segunda traduccion escondida.
// Este es el UNICO modulo que los importa; las pantallas usan estas funciones y no la
// forma del JSON.
//
// PROVISIONAL (paso 15, base): mientras el catalogo de verdad no este en esta rama, los
// dos import de abajo apuntan a un sustituto minimo (./domain/placeholder-*.json). Al
// llegar el de verdad: cambiar las dos lineas por
//   import nlCatalog from '../../../src/bms_agent/textos/nl.json';
//   import enCatalog from '../../../src/bms_agent/textos/en.json';
// ajustar las funciones a su forma, borrar ./domain/ y anadir los dos ficheros a
// build-inputs.json (la huella de web/fuente.json los tiene que cubrir).
//
// Lo que la API manda en castellano (titulo, detalle, etiqueta, fuente_texto, nota,
// motivos) no se ensena nunca: se queda para la CLI y la auditoria.
import nlCatalog from './domain/placeholder-nl.json';
import enCatalog from './domain/placeholder-en.json';
import type { Lang } from './index';

export type Priority = 'normal' | 'atencion' | 'urgente' | 'bloqueada';
export type PaymentState = 'pendiente' | 'vencida' | 'pagada' | 'anulada' | 'acreditada';
export type ReviewState = 'sin_revisar' | 'necesita_revision' | 'revisada';
export type Direction = 'entrante' | 'saliente';

type Catalog = typeof nlCatalog;
const CATALOGS: Record<Lang, Catalog> = { nl: nlCatalog, en: enCatalog };

export const PRIORITIES: readonly Priority[] = ['normal', 'atencion', 'urgente', 'bloqueada'];

export function isPriority(value: unknown): value is Priority {
  return typeof value === 'string' && (PRIORITIES as readonly string[]).includes(value);
}

function lookup(section: Record<string, string>, key: string | null | undefined): string | null {
  if (!key || !Object.prototype.hasOwnProperty.call(section, key)) return null;
  return section[key] ?? null;
}

/** La prioridad en palabras ("Geblokkeerd"), o null si el codigo no se conoce. */
export function priorityLabel(lang: Lang, priority: string | null | undefined): string | null {
  return lookup(CATALOGS[lang].prioridades, priority);
}

export function paymentStateLabel(lang: Lang, state: string | null | undefined): string | null {
  return lookup(CATALOGS[lang].estados_pago, state);
}

export function reviewStateLabel(lang: Lang, state: string | null | undefined): string | null {
  return lookup(CATALOGS[lang].estados_revision, state);
}

export function directionLabel(lang: Lang, direction: string | null | undefined): string | null {
  return lookup(CATALOGS[lang].sentidos, direction);
}

/** Las secciones del catalogo, para el test de paridad entre idiomas. */
export function catalogFor(lang: Lang): Catalog {
  return CATALOGS[lang];
}
