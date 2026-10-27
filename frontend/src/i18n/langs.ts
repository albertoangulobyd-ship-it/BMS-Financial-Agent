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
 * Los idiomas que dicen lo del dominio con el catalogo de otro idioma. Vacio desde que llego
 * src/bms_agent/textos/es.json (paso 16): cada idioma tiene su catalogo. Se queda la forma
 * por si un idioma nuevo llegara antes que su catalogo: i18n.test.ts y e2e/fixtures.ts lo
 * leen para saber que restos de otro idioma se toleran.
 */
export const DOMAIN_FALLBACK: Readonly<Partial<Record<Lang, Lang>>> = {};
