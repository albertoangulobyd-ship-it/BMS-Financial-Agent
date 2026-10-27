// Los textos de dominio (reglas, prioridades, estados, campos, fuentes, acciones, errores)
// salen de los catalogos de Python, src/bms_agent/textos/nl.json y en.json (y es.json en
// cuanto llegue: DOMAIN_FALLBACK, en langs.ts), que la app
// importa al construirse: asi la app y lo que se prueba en Python dicen lo mismo y no hay
// una segunda traduccion escondida. Este es el UNICO modulo que los importa; las
// pantallas usan estas funciones y no la forma del JSON. Los dos ficheros entran en la
// huella de web/fuente.json (frontend/build-inputs.json).
//
// Lo que la API manda en castellano (titulo, detalle, etiqueta, fuente_texto, nota,
// motivos, error) no se ensena nunca: se queda para la CLI y la auditoria.
import nlCatalog from '../../../src/bms_agent/textos/nl.json';
import enCatalog from '../../../src/bms_agent/textos/en.json';
import type { Lang } from './index';
import { DOMAIN_FALLBACK } from './langs';
import { fmt } from './index';
import { renderDetail, type RuleTexts, type TemplateCatalog } from './templates';

export type Priority = 'normal' | 'atencion' | 'urgente' | 'bloqueada';
export type Severity = 'bloqueo' | 'retencion' | 'aviso';

type Catalog = typeof nlCatalog;

// Mientras falte es.json, el castellano dice lo del dominio en ingles: DOMAIN_FALLBACK, con su
// PENDIENTE, vive en langs.ts (lo leen tambien las pruebas en el navegador).
export { DOMAIN_FALLBACK };

// Los catalogos tienen la misma forma (lo comprueban tests/test_textos.py y i18n.test.ts).
// es: el ingles, marcado en DOMAIN_FALLBACK, hasta que llegue es.json.
const CATALOGS: Record<Lang, Catalog> = { nl: nlCatalog, en: enCatalog as Catalog, es: enCatalog as Catalog };

export const PRIORITIES: readonly Priority[] = ['normal', 'atencion', 'urgente', 'bloqueada'];

export function isPriority(value: unknown): value is Priority {
  return typeof value === 'string' && (PRIORITIES as readonly string[]).includes(value);
}

const has = (o: object, k: string | null | undefined): k is string =>
  typeof k === 'string' && Object.prototype.hasOwnProperty.call(o, k);

function pick<T>(section: Record<string, T>, key: string | null | undefined): T | null {
  return has(section, key) ? section[key]! : null;
}

/** Las secciones del catalogo, para el test de paridad entre idiomas. */
export function catalogFor(lang: Lang): Catalog {
  return CATALOGS[lang];
}

export function templateCatalog(lang: Lang): TemplateCatalog {
  const c = CATALOGS[lang];
  return { comun: c.comun, codigos: c.codigos as Record<string, string> };
}

// ------------------------------------------------------------ prioridad y gravedad

/** La prioridad en palabras ("Geblokkeerd"), o null si el codigo no se conoce. */
export function priorityLabel(lang: Lang, priority: string | null | undefined): string | null {
  return pick(CATALOGS[lang].prioridad, priority)?.etiqueta ?? null;
}

export function priorityMeaning(lang: Lang, priority: string | null | undefined): string | null {
  return pick(CATALOGS[lang].prioridad, priority)?.significa ?? null;
}

export function severityLabel(lang: Lang, severity: string | null | undefined): string | null {
  return pick(CATALOGS[lang].severidades, severity)?.etiqueta ?? null;
}

/** Lo que hace esa gravedad con la factura, en una frase (la ayuda de su pastilla). */
export function severityMeaning(lang: Lang, severity: string | null | undefined): string | null {
  return pick(CATALOGS[lang].severidades, severity)?.significa ?? null;
}

// ------------------------------------------------------------ estados

type StateGroup = keyof Catalog['estados'];

/** Un estado de la API en palabras: stateLabel(lang, 'pago', 'vencida') -> "Te laat". */
export function stateLabel(lang: Lang, group: StateGroup, state: string | null | undefined): string | null {
  return pick(CATALOGS[lang].estados[group] as Record<string, string>, state);
}

export const paymentStateLabel = (lang: Lang, s: string | null | undefined) => stateLabel(lang, 'pago', s);
export const reviewStateLabel = (lang: Lang, s: string | null | undefined) => stateLabel(lang, 'revision', s);
export const directionLabel = (lang: Lang, s: string | null | undefined) => stateLabel(lang, 'sentido', s);

// ------------------------------------------------------------ reglas y hallazgos

export interface RuleText {
  title: string;
  meaning: string;
  whatToDo: string;
}

export function ruleText(lang: Lang, rule: string | null | undefined): RuleText | null {
  const r = pick(CATALOGS[lang].reglas as Record<string, RuleTexts>, rule);
  return r ? { title: r.titulo, meaning: r.significa, whatToDo: r.que_hacer } : null;
}

/** El detalle de un hallazgo escrito desde sus valores (nunca el castellano de la API). */
export function findingDetail(lang: Lang, rule: string, result: string | null | undefined, values: unknown): string | null {
  const r = pick(CATALOGS[lang].reglas as Record<string, RuleTexts>, rule);
  if (!r) return null;
  return renderDetail(r, result ?? 'fallo', values, templateCatalog(lang)).text;
}

export function categoryText(lang: Lang, key: string | null | undefined): { label: string; meaning: string } | null {
  const c = pick(CATALOGS[lang].categorias, key);
  return c ? { label: c.etiqueta, meaning: c.significa } : null;
}

// ------------------------------------------------------------ campos, fuentes y calidad

type FieldTable = keyof Catalog['campos'];

export function fieldLabel(lang: Lang, table: string, field: string): string | null {
  const t = pick(CATALOGS[lang].campos as Record<FieldTable, Record<string, string>>, table);
  return t ? pick(t, field) : null;
}

export function sourceText(lang: Lang, source: string | null | undefined): { label: string; meaning: string } | null {
  const s = pick(CATALOGS[lang].fuentes, source);
  return s ? { label: s.etiqueta, meaning: s.significa } : null;
}

export function qualityText(lang: Lang, quality: string | null | undefined): { label: string; meaning: string } | null {
  const q = pick(CATALOGS[lang].calidad, quality);
  return q ? { label: q.etiqueta, meaning: q.significa } : null;
}

// ------------------------------------------------------------ acciones, roles y errores

export interface ActionText {
  label: string;
  description: string;
  /** La frase del dialogo de confirmacion, solo en lo que mueve dinero, btw o el banco. */
  confirm: string | null;
}

export function actionText(lang: Lang, action: string): ActionText | null {
  const a = pick(CATALOGS[lang].acciones as Record<string, { etiqueta: string; descripcion: string; confirmar?: string }>, action);
  return a ? { label: a.etiqueta, description: a.descripcion, confirm: a.confirmar ?? null } : null;
}

export function roleText(lang: Lang, role: string): { label: string; description: string } | null {
  const r = pick(CATALOGS[lang].roles, role);
  return r ? { label: r.etiqueta, description: r.descripcion } : null;
}

/** Un permiso en palabras ("Facturen bekijken") y que deja hacer. */
export function permissionText(lang: Lang, permission: string): { label: string; description: string } | null {
  const p = pick(CATALOGS[lang].permisos as Record<string, { etiqueta: string; descripcion: string }>, permission);
  return p ? { label: p.etiqueta, description: p.descripcion } : null;
}

/** Una clase de fichero que se importa ("Exact · Leveranciers"). */
export function importKindLabel(lang: Lang, source: string, kind: string): string {
  const s = stateLabel(lang, 'fuente_importacion', source) ?? source;
  const k = stateLabel(lang, 'tipo_importacion', kind) ?? kind;
  return `${s} · ${k}`;
}

/** El texto de un codigo de error de la API (`codigo`), o null si no se conoce. */
export function errorText(lang: Lang, code: string | null | undefined): string | null {
  return pick(CATALOGS[lang].errores, code);
}

// ------------------------------------------------------------ el veredicto

export interface VerdictCounts {
  pendientes: number;
  aceptados: number;
  sin_datos: number;
  /** Campos por resolver o dudosos. */
  campos: number;
}

export type VerdictState = 'limpia' | 'limpia_sin_datos' | 'objeciones' | 'aceptadas' | 'campos';

export interface VerdictPart {
  /** El estado de esta parte (la clave del catalogo "veredicto"). */
  state: VerdictState;
  /** Las cifras de su texto. */
  values: Record<string, number>;
  text: string;
}

/** El texto de una parte del veredicto desde el catalogo, con sus cifras. */
export function verdictPartText(lang: Lang, state: string, values: Record<string, string | number> = {}): string | null {
  const v = CATALOGS[lang].veredicto as Record<string, string>;
  return has(v, state) ? fmt(v[state]!, values) : null;
}

/** Lo que dice el sistema de una factura, como revision.etiqueta_sistema. Nunca "aprobada":
 *  limpia es "Geen bezwaren van het systeem" / "No system objections". `parts` dice cada
 *  parte con su estado, en el orden del texto; `main` es la mas seria (bezwaren, luego
 *  velden, luego lo aceptado): la que va en la pastilla. */
export function verdict(
  lang: Lang,
  c: VerdictCounts
): { text: string; clean: boolean; parts: VerdictPart[]; main: VerdictPart } {
  const part = (state: VerdictState, values: Record<string, number>): VerdictPart => ({
    state,
    values,
    text: verdictPartText(lang, state, values) ?? state,
  });
  if (c.pendientes === 0 && c.campos === 0) {
    const only = c.sin_datos ? part('limpia_sin_datos', { sin_datos: c.sin_datos }) : part('limpia', {});
    return { text: only.text, clean: true, parts: [only], main: only };
  }
  const parts: VerdictPart[] = [];
  if (c.pendientes - c.aceptados > 0) parts.push(part('objeciones', { n: c.pendientes - c.aceptados }));
  if (c.aceptados) parts.push(part('aceptadas', { n: c.aceptados }));
  if (c.campos) parts.push(part('campos', { n: c.campos }));
  const order: VerdictState[] = ['objeciones', 'campos', 'aceptadas'];
  const main = [...parts].sort((a, b) => order.indexOf(a.state) - order.indexOf(b.state))[0]!;
  return { text: parts.map((p) => p.text).join('; '), clean: false, parts, main };
}
