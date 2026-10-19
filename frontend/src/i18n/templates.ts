// El lenguaje de las plantillas de los textos de dominio (src/bms_agent/textos/LEEME.md),
// otra vez en TypeScript. La referencia es bms_agent.textos (Python): este modulo tiene
// que dar exactamente lo mismo, y templates.test.ts lo comprueba con cada caso de
// src/bms_agent/textos/casos.json en neerlandes y en ingles.
//
// Por que se reescribe el detalle y no se traduce: el detalle de un hallazgo sale de sus
// `valores` (los enteros y textos que su regla comparo), asi la frase dice lo que dicen
// los datos. Sin floats: importes, horas y porcentajes se escriben con BigInt y texto.
//
// Lo que sale es TEXTO, nunca HTML: los valores pueden traer texto de un documento y la
// pantalla lo pinta con React (textContent), tal cual.

/** Lo que se pinta donde no hay nada (Python: VACIO). */
export const EMPTY = '—';

const FORMATS = ['texto', 'dinero', 'tarifa', 'horas', 'pct', 'fecha', 'trimestre', 'iban', 'codigo'] as const;
const TRANSFORMS = ['cuenta', 'suma', 'abs'] as const;
type Format = (typeof FORMATS)[number];

const isFormat = (f: string): f is Format => (FORMATS as readonly string[]).includes(f);
const isTransform = (f: string): boolean => (TRANSFORMS as readonly string[]).includes(f);
const isFilter = (f: string): boolean => isFormat(f) || isTransform(f);

/** Lo minimo del catalogo de un idioma que necesita el renderizador. */
export interface TemplateCatalog {
  comun: { si: string; no: string };
  codigos: Record<string, string>;
}

export interface Rendered {
  text: string;
  /** Las rutas que faltaban, `codigo:x` y `filtro:x` (para los tests; quien lee ve la raya). */
  missing: string[];
}

// {{ y }} son llaves literales; un marcador es {ruta} o {ruta|filtro|...}.
const PIECE = /\{\{|\}\}|\{([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)((?:\|[a-z]+)*)\}/g;
const NUMBER = /^(-?)(\d+)(?:\/(\d+))?$/;
const DATE = /^(\d{4})-(\d{2})-(\d{2})/;
const IBAN = /^[A-Za-z0-9]+$/;
const QUARTER = /^(\d{4})-T([1-4])$/;
const MISSING = Symbol('missing');

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type Value = Json | bigint | typeof MISSING | undefined;

const isObject = (v: unknown): v is Record<string, Json> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const own = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);

// ------------------------------------------------------------ numeros

/** "1234567" -> "1.234.567". */
function thousands(digits: string): string {
  const groups: string[] = [];
  let rest = digits;
  while (rest.length > 3) {
    groups.unshift(rest.slice(-3));
    rest = rest.slice(0, -3);
  }
  groups.unshift(rest);
  return groups.join('.');
}

/** Un entero en unidades de 10^-scale, con coma decimal y sin ceros de mas (Python: _escala). */
function scaled(value: bigint, scale: number, minimum: number): string {
  const sign = value < 0n ? '-' : '';
  const abs = value < 0n ? -value : value;
  const unit = 10n ** BigInt(scale);
  const whole = abs / unit;
  const rest = abs % unit;
  let decimals = '';
  if (scale) decimals = rest.toString().padStart(scale, '0').replace(/0+$/, '').padEnd(minimum, '0');
  return sign + thousands(whole.toString()) + (decimals ? `,${decimals}` : '');
}

/** Un entero, o un texto que lo es ("181350", o una fraccion "181351/2" redondeada a la
 *  unidad, la mitad lejos de cero). null si no es un numero; un booleano tampoco lo es. */
export function integerOf(value: Value): bigint | null {
  if (typeof value === 'bigint') return value;
  if (typeof value === 'number') return Number.isInteger(value) ? BigInt(value) : null;
  if (typeof value !== 'string') return null;
  const m = NUMBER.exec(value.trim());
  if (!m) return null;
  const numerator = BigInt(m[2]!);
  const divisor = BigInt(m[3] ?? '1');
  if (divisor === 0n) return null;
  let quotient = numerator / divisor;
  const rest = numerator % divisor;
  if (rest && 2n * rest >= divisor) quotient += 1n;
  return m[1] ? -quotient : quotient;
}

const NUMERIC: Record<string, (n: bigint) => string> = {
  dinero: (cent) => `€ ${scaled(cent, 2, 2)}`,
  tarifa: (e4) => `€ ${scaled(e4, 4, 2)}`,
  horas: (mil) => scaled(mil, 3, 0),
  pct: (pb) => `${scaled(pb, 2, 0)}%`,
};

function date(iso: string): string {
  const m = DATE.exec(iso);
  return m ? `${m[3]}-${m[2]}-${m[1]}` : iso;
}

function quarter(label: string): string {
  const m = QUARTER.exec(label);
  return m ? `Q${m[2]} ${m[1]}` : label;
}

/** Un IBAN en grupos de cuatro; uno ya enmascarado (NL..4300) se deja tal cual. */
function iban(text: string): string {
  const compact = text.split(/\s+/).join('');
  if (!IBAN.test(compact)) return text;
  const upper = compact.toUpperCase();
  const groups: string[] = [];
  for (let i = 0; i < upper.length; i += 4) groups.push(upper.slice(i, i + 4));
  return groups.join(' ');
}

/** Como escribe Python str() lo que no tiene formato (un entero, un texto, un booleano...). */
function pythonStr(value: Json | bigint): string {
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (value === null) return 'None';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'bigint') return String(value);
  if (Array.isArray(value)) return `[${value.map(pythonRepr).join(', ')}]`;
  return `{${Object.entries(value).map(([k, v]) => `${pythonRepr(k)}: ${pythonRepr(v)}`).join(', ')}}`;
}

function pythonRepr(value: Json | bigint): string {
  if (typeof value !== 'string') return pythonStr(value);
  const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
  const escaped = value.replace(/\\/g, '\\\\').replace(quote === "'" ? /'/g : /"/g, `\\${quote}`);
  return `${quote}${escaped}${quote}`;
}

// ------------------------------------------------------------ plantillas

function filtersOf(piece: string | undefined): string[] {
  const filters = (piece ?? '').split('|').filter(Boolean);
  return filters.length ? filters : ['texto'];
}

/** El valor de una ruta ("periodos.0.1"), o MISSING si no esta. */
function lookup(values: Json, path: string): Value {
  let current: Json = values;
  for (const segment of path.split('.')) {
    if (isObject(current) && own(current, segment)) {
      current = current[segment]!;
    } else if (Array.isArray(current) && /^\d+$/.test(segment) && Number(segment) < current.length) {
      current = current[Number(segment)]!;
    } else {
      return MISSING;
    }
  }
  return current;
}

type Transformed = Json | bigint;

function transform(value: Transformed, filter: string): Transformed {
  if (filter === 'cuenta') {
    if (Array.isArray(value)) return BigInt(value.length);
    if (isObject(value)) return BigInt(Object.keys(value).length);
    return integerOf(value);
  }
  if (filter === 'suma') {
    if (!Array.isArray(value)) return integerOf(value);
    const numbers = value.map(integerOf);
    if (numbers.some((n) => n === null)) return null;
    return numbers.reduce<bigint>((a, n) => a + (n as bigint), 0n);
  }
  if (Array.isArray(value)) return value.map((v) => transform(v, filter)) as Json[];
  const number = integerOf(value);
  if (number === null) return null;
  return number < 0n ? -number : number;
}

function one(value: Transformed, format: Format, catalog: TemplateCatalog, path: string, missing: string[]): string {
  if (value === null || value === undefined) return EMPTY;
  if (isObject(value)) {
    missing.push(path);
    return EMPTY;
  }
  if (format in NUMERIC) {
    const number = integerOf(value);
    if (number !== null) return NUMERIC[format]!(number);
  } else if (format === 'fecha' && typeof value === 'string') {
    return date(value);
  } else if (format === 'trimestre' && typeof value === 'string') {
    return quarter(value);
  } else if (format === 'iban' && typeof value === 'string') {
    return iban(value);
  } else if (format === 'codigo' && typeof value === 'string') {
    if (own(catalog.codigos, value)) return catalog.codigos[value]!;
    missing.push(`codigo:${value}`);
    return value;
  }
  if (typeof value === 'boolean') return value ? catalog.comun.si : catalog.comun.no;
  return pythonStr(value);
}

function paint(value: Transformed, filters: string[], catalog: TemplateCatalog, path: string, missing: string[]): string {
  let before = filters.slice(0, -1);
  let last = filters[filters.length - 1]!;
  if (isTransform(last)) {
    before = [...before, last];
    last = 'texto';
  }
  const bad = before.filter((f) => !isTransform(f));
  if (bad.length || !isFormat(last)) {
    for (const f of [...bad, last]) if (!isFilter(f) || bad.includes(f)) missing.push(`filtro:${f}`);
    return EMPTY;
  }
  for (const filter of before) value = transform(value, filter);
  if (Array.isArray(value)) {
    if (!value.length) return EMPTY;
    return value.map((v) => one(v, last as Format, catalog, path, missing)).join(', ');
  }
  return one(value, last, catalog, path, missing);
}

/** Un valor con un formato del lenguaje ("tarifa", "horas", "iban"...), fuera de una frase. */
export function formatWith(format: string, value: unknown, catalog: TemplateCatalog): string {
  return paint((value ?? null) as Json, [format], catalog, '', []);
}

/** La plantilla con cada marcador sustituido, y lo que faltaba (Python: pintar). */
export function renderTemplate(template: string, values: unknown, catalog: TemplateCatalog): Rendered {
  const data = (values ?? {}) as Json;
  const missing: string[] = [];
  const text = template.replace(PIECE, (piece: string, path: string | undefined, filters: string | undefined) => {
    if (piece === '{{') return '{';
    if (piece === '}}') return '}';
    const value = lookup(data, path!);
    if (value === MISSING) {
      missing.push(path!);
      return EMPTY;
    }
    return paint(value as Json, filtersOf(filters), catalog, path!, missing);
  });
  return { text, missing };
}

// ------------------------------------------------------------ variantes

export interface Variant {
  cuando?: string[];
  texto?: string;
  partes?: { cuando?: string[]; texto: string }[];
}

function rawText(value: Json): string {
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return pythonStr(value);
}

/** Una condicion: "ruta" (esta y no es null ni una lista vacia), "!ruta" o "ruta=valor". */
export function holds(condition: string, values: unknown): boolean {
  if (condition.startsWith('!')) return !holds(condition.slice(1), values);
  const at = condition.indexOf('=');
  const path = at < 0 ? condition : condition.slice(0, at);
  const value = lookup((values ?? {}) as Json, path);
  if (value === MISSING || value === null || value === undefined) return false;
  if (Array.isArray(value) && value.length === 0) return false;
  return at < 0 ? true : rawText(value as Json) === condition.slice(at + 1);
}

const valid = (piece: { cuando?: string[] }, values: unknown) => (piece.cuando ?? []).every((c) => holds(c, values));

/** La primera variante que vale, con su posicion y las plantillas que escribe. */
export function chooseVariant(variants: readonly Variant[], values: unknown): { index: number; templates: string[] } | null {
  for (let index = 0; index < variants.length; index += 1) {
    const variant = variants[index]!;
    if (!valid(variant, values)) continue;
    if (!variant.partes) return { index, templates: [variant.texto ?? ''] };
    const parts = variant.partes.filter((p) => valid(p, values)).map((p) => p.texto);
    if (parts.length) return { index, templates: parts };
  }
  return null;
}

export interface RuleTexts {
  titulo: string;
  significa: string;
  que_hacer: string;
  detalle: Record<string, Variant[] | undefined>;
}

/** El detalle de un resultado (fallo o sin_datos) de una regla, en un idioma. Sin plantilla
 *  para ese resultado, el significado de la regla: nunca el castellano de la API. */
export function renderDetail(
  rule: RuleTexts,
  result: string,
  values: unknown,
  catalog: TemplateCatalog
): Rendered & { variant: number | null } {
  const variants = own(rule.detalle, result) ? rule.detalle[result] : undefined;
  if (!variants || !variants.length) return { text: rule.significa, missing: [], variant: null };
  const chosen = chooseVariant(variants, values);
  if (!chosen) return { text: rule.significa, missing: [], variant: null };
  const painted = chosen.templates.map((t) => renderTemplate(t, values, catalog));
  return {
    text: painted.map((p) => p.text).join(' '),
    missing: painted.flatMap((p) => p.missing),
    variant: chosen.index,
  };
}
