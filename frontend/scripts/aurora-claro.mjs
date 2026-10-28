// El tema claro de las hojas de Aurora (paso 17, especificacion §4.2 T). Aurora solo es oscura;
// el claro es nuestro y es una opcion de Ajustes. Este script lee las hojas que se copian tal
// cual de la entrega del dueno (y las de BMS que van con ellas) y escribe src/aurora/claro.css:
// cada declaracion con un color, repetida bajo html:not(.dark) con el mismo matiz y la
// luminosidad invertida en OKLab (como aurora/palette.css). Las hojas de Aurora no se tocan y el
// tema oscuro no cambia. Un color con transparencia conserva su alfa (el blanco al 8 % pasa a
// negro al 8 %). El texto (color, fill) no pasa de una luminosidad de 0,44 en OKLab: los grises
// de Aurora sobre su fondo oscuro no llegan a 4,5:1 (se dejan asi en el oscuro, que es el suyo),
// pero el claro es nuestro y pasa WCAG AA. Al final, lo que no es un color de una hoja (el logo
// blanco, los orbes que se pintan en un lienzo) va escrito a mano.
//
//   node scripts/aurora-claro.mjs              escribe src/aurora/claro.css
//   node scripts/aurora-claro.mjs --comprobar  sale con 1 si claro.css no es el que saldria
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const src = fileURLToPath(new URL('../src/aurora/', import.meta.url));

/** Las hojas, en el orden en que entran en la app. */
export const SHEETS = [
  'styles.css',
  'workspace-layout.css',
  'chat/ai-actions.css',
  'search/search-workspace.css',
  'finance/finance-bento.css',
  'finance/finance-bento-component.css',
  'bms.css',
];

/** Las propiedades cuyo valor puede llevar un color. */
const COLOR_PROPS = /^(color|background(-color|-image)?|border(-(top|right|bottom|left))?(-color)?|outline(-color)?|box-shadow|text-shadow|fill|stroke|caret-color|scrollbar-color|filter|text-decoration-color|accent-color)$/;

const NAMED = { white: [255, 255, 255, 1], black: [0, 0, 0, 1] };

// ---- OKLab (Bjorn Ottosson), de sRGB y de vuelta.
const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toGamma = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function rgbToOklab([r, g, b]) {
  const [lr, lg, lb] = [r, g, b].map((v) => toLinear(v / 255));
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function oklabToRgb([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const bl = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
  return [r, g, bl].map((v) => Math.round(Math.min(1, Math.max(0, toGamma(Math.min(1, Math.max(0, v))))) * 255));
}

/** El texto, como mucho asi de claro: sobre los fondos claros (luminosidad 0,87 o mas), 4,5:1. */
export const TEXT_MAX_L = 0.44;

/** El mismo matiz con la luminosidad invertida (un poco mas clara arriba: el fondo no es gris);
 *  `maxL`, el tope de luminosidad (el del texto). */
export function invert(rgba, maxL = 1) {
  const [L, a, b] = rgbToOklab(rgba);
  const out = oklabToRgb([Math.min(maxL, Math.max(0, 1.06 - L)), a, b]);
  return [...out, rgba[3]];
}

const hex2 = (n) => n.toString(16).padStart(2, '0');

function format([r, g, b, alpha], original) {
  if (alpha >= 1 && !/^#[0-9a-f]{8}$/i.test(original)) return `#${hex2(r)}${hex2(g)}${hex2(b)}`;
  return `#${hex2(r)}${hex2(g)}${hex2(b)}${hex2(Math.round(alpha * 255))}`;
}

function parseColor(token) {
  const t = token.toLowerCase();
  if (NAMED[t]) return NAMED[t];
  let m = /^#([0-9a-f]{3,8})$/.exec(t);
  if (m) {
    let h = m[1];
    if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join('');
    if (h.length !== 6 && h.length !== 8) return null;
    const n = [0, 2, 4, 6].map((i) => parseInt(h.slice(i, i + 2) || 'ff', 16));
    return [n[0], n[1], n[2], n[3] / 255];
  }
  m = /^rgba?\(([^)]*)\)$/.exec(t);
  if (m) {
    const parts = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    if (parts.length < 3 || parts.some((p) => Number.isNaN(p))) return null;
    return [parts[0], parts[1], parts[2], parts[3] ?? 1];
  }
  return null;
}

const COLOR_TOKEN = /#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(?:white|black)\b/g;

/** El valor con cada color invertido; null si no lleva ninguno. */
export function invertValue(value, maxL = 1) {
  let changed = false;
  const out = value.replace(COLOR_TOKEN, (token) => {
    const rgba = parseColor(token);
    if (!rgba) return token;
    changed = true;
    return format(invert(rgba, maxL), token);
  });
  return changed ? out : null;
}

/** Las propiedades que pintan texto (o el trazo de un dibujo): con el tope del texto. */
const TEXT_PROPS = /^(color|fill|caret-color|-webkit-text-fill-color)$/;

// ---- un lector de CSS que basta para estas hojas (sin cadenas con llaves dentro).
function stripComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, '');
}

/** Los bloques de primer nivel: [{prelude, body}] (body sin las llaves). */
function blocks(css) {
  const out = [];
  let i = 0;
  while (i < css.length) {
    const open = css.indexOf('{', i);
    if (open < 0) break;
    const semi = css.indexOf(';', i);
    // Una sentencia sin bloque (@import ...;) antes del bloque.
    if (semi >= 0 && semi < open) {
      i = semi + 1;
      continue;
    }
    let depth = 1;
    let j = open + 1;
    while (j < css.length && depth > 0) {
      if (css[j] === '{') depth += 1;
      else if (css[j] === '}') depth -= 1;
      j += 1;
    }
    out.push({ prelude: css.slice(i, open).trim(), body: css.slice(open + 1, j - 1) });
    i = j;
  }
  return out;
}

function declarations(body) {
  return body
    .split(';')
    .map((d) => d.trim())
    .filter(Boolean)
    .map((d) => {
      const at = d.indexOf(':');
      return at < 0 ? null : { prop: d.slice(0, at).trim(), value: d.slice(at + 1).trim() };
    })
    .filter(Boolean);
}

/** html:not(.dark) delante de cada selector de la lista (:root pasa a ser el propio html). */
function prefix(selectors) {
  return selectors
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => (s.startsWith(':root') ? `html:not(.dark)${s.slice(5)}` : /^(html|body)\b/.test(s) ? `html:not(.dark) ${s}` : `html:not(.dark) ${s}`))
    .join(',');
}

function lightRules(css) {
  const out = [];
  for (const { prelude, body } of blocks(css)) {
    if (prelude.startsWith('@keyframes') || prelude.startsWith('@font-face')) continue;
    if (prelude.startsWith('@media') || prelude.startsWith('@supports')) {
      const inner = lightRules(body);
      if (inner.length) out.push(`${prelude}{${inner.join('')}}`);
      continue;
    }
    if (prelude.startsWith('@layer')) {
      out.push(...lightRules(body));
      continue;
    }
    const decls = declarations(body)
      .filter(({ prop }) => COLOR_PROPS.test(prop) || prop.startsWith('--'))
      .map(({ prop, value }) => {
        const inverted = invertValue(value, TEXT_PROPS.test(prop) ? TEXT_MAX_L : 1);
        return inverted ? `${prop}:${inverted}` : null;
      })
      .filter(Boolean);
    if (decls.length) out.push(`${prefix(prelude)}{${decls.join(';')}}`);
  }
  return out;
}

/** Lo que no es un color de una hoja. */
const BY_HAND = `
/* A mano: el logo es un PNG que un filtro pinta de blanco; en claro, invertido. */
html:not(.dark) .bms-brand svg{filter:invert(1)}
`;

export function build() {
  const rules = SHEETS.flatMap((sheet) => lightRules(stripComments(readFileSync(src + sheet, 'utf8'))));
  return `/* El tema claro de las hojas de Aurora. NO SE EDITA A MANO: lo escribe
   frontend/scripts/aurora-claro.mjs a partir de ${SHEETS.join(', ')}
   (cada color con su luminosidad invertida en OKLab, bajo html:not(.dark)). */
${rules.join('\n')}
${BY_HAND}`;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const text = build();
  const target = src + 'claro.css';
  if (process.argv.includes('--comprobar')) {
    let current = '';
    try {
      current = readFileSync(target, 'utf8');
    } catch {
      current = '';
    }
    if (current !== text) {
      console.error('src/aurora/claro.css no es el que escribe scripts/aurora-claro.mjs');
      process.exit(1);
    }
  } else {
    writeFileSync(target, text);
    console.log(`claro.css: ${text.split('\n').length} lineas`);
  }
}
