// Los idiomas de la app (paso 16), sin React ni diccionarios: lo importan index.tsx, domain.ts,
// leftovers.ts y las pruebas en el navegador (e2e/fixtures.ts), que no compilan JSX.

export type Lang = 'nl' | 'en' | 'es';
export const LANGS: readonly Lang[] = ['nl', 'en', 'es'];
export const DEFAULT_LANG: Lang = 'nl';

export function isLang(value: unknown): value is Lang {
  return value === 'nl' || value === 'en' || value === 'es';
}

/** La etiqueta BCP 47 de cada idioma (mayusculas, minusculas y orden de textos). Las cifras y
 *  las fechas no la usan: van siempre en notacion neerlandesa (lib/format.ts). */
export const LOCALES: Record<Lang, string> = { nl: 'nl-NL', en: 'en-GB', es: 'es-ES' };

/**
 * PENDIENTE (paso 16): el catalogo de dominio en castellano, src/bms_agent/textos/es.json, lo
 * prepara otro trabajo en paralelo y aun no esta en esta rama. Hasta que llegue, la app en
 * castellano dice lo del dominio (reglas, estados, prioridades, campos, errores) con el
 * catalogo en INGLES: es lo que dice DOMAIN_FALLBACK. Al llegar es.json: importarlo en
 * domain.ts y ponerlo en CATALOGS, anadirlo a frontend/build-inputs.json y a
 * tests/test_app_local.py (los catalogos que entran en la huella), quitar la entrada de aqui
 * (i18n.test.ts y e2e/fixtures.ts la leen para saber que restos en ingles se toleran en
 * castellano) y que templates.test.ts pruebe tambien el castellano (lo hace solo si
 * casos.json trae "es").
 */
export const DOMAIN_FALLBACK: Readonly<Partial<Record<Lang, Lang>>> = { es: 'en' };
