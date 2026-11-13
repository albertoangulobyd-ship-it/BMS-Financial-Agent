// El tema claro de las hojas de Aurora ("Aurora claro · linea fina", rehecho el 03-11-2026 tras
// "No me gusto nada el tema blanco" del 02-11-2026). Aurora solo es oscura; el claro es nuestro y
// es una opcion de Ajustes. Este script lee las hojas que se copian tal cual de la entrega del
// dueno (y las de BMS que van con ellas) y escribe src/aurora/claro.css:
// - cada declaracion con un color, repetida bajo html:not(.dark) con el PAPEL que ese color hace
//   en el oscuro (pagina, superficie, velo, linea, texto principal o secundario, acento, estado,
//   sombra...) traducido a la paleta clara (PALETTE, las variables --l-*, definidas una vez). No
//   se invierte nada: lo que flota en el oscuro es blanco en el claro, un velo blanco es un velo
//   de tinta, una sombra sigue siendo una sombra (nunca un brillo blanco) y los grises con matiz
//   lila pasan a grises neutros;
// - las declaraciones de esas mismas propiedades sin color (none, 0, inherit...) y las del
//   contorno (outline-*), tal cual: al ir todas con el mismo prefijo, la cascada del claro es la
//   del oscuro y ninguna regla de despues pierde (ni cambia una caja ni un anillo de foco);
// - ROLES: los papeles que no cuelgan de una regla de las hojas (el placeholder de cualquier
//   campo, tenga o no una regla en Aurora);
// - DESIGN: lo que se disena sobre esas reglas (el panel que flota, la caja, el dialogo...);
// - al final, scripts/aurora-claro-mano.css: lo que no sale de una hoja de SHEETS (las carpetas
//   de cristal, los lienzos, los atributos SVG del resumen, los estados que Aurora no tiene...).
// Ningun color suelto: todo es var(--l-*), salvo RAW_OK. Las hojas de Aurora no se tocan y el
// tema oscuro no cambia: todo va bajo html:not(.dark).
//
//   node scripts/aurora-claro.mjs              escribe src/aurora/claro.css
//   node scripts/aurora-claro.mjs --comprobar  sale con 1 si claro.css no es el que saldria
//   node scripts/aurora-claro.mjs --papeles    lista cada color de las hojas con el papel que le
//                                              toco (para revisar cuando cambien las hojas)
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
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
  'processing/processing-workspace.css',
  'processing/processing-card.css',
  'processing/document-loader.css',
  'documents/document-workspace.css',
  'bms.css',
];

/** La paleta clara (Linear y Stripe: lineas finas neutras; Mercury: un solo color de accion;
 *  Apple: la pagina #f5f5f7 bajo lo blanco). Los contrastes, en docs/app-local.md. */
export const PALETTE = {
  // Superficies: la pagina gris muy clara y lo que flota, blanco; lo hundido deja ver la pagina.
  page: '#f5f5f7',
  surface: '#ffffff',
  subtle: '#f5f5f7',
  'subtle-2': '#ececf0',
  glass: 'rgba(255,255,255,.96)',
  scrim: 'rgba(23,23,28,.16)',
  // La tinta: cuatro grises neutros (ink-4 nunca es texto: solo lo inactivo y lo decorativo).
  'ink-1': '#17171c',
  'ink-2': '#484851',
  'ink-3': '#686871',
  'ink-4': '#a0a0a8',
  'on-fill': '#ffffff',
  // El placeholder de un campo: un texto como otro (4,5:1 o mas sobre la pagina y sobre lo
  // blanco), el gris terciario. Nunca el color del campo a medias (lo que le da Tailwind si
  // nadie lo dice: 2,08 en la busqueda de las listas).
  placeholder: '#686871',
  // Lineas y velos: la misma tinta a distintas alfas; field, el borde de un campo (WCAG 1.4.11).
  'line-soft': 'rgba(17,17,26,.06)',
  line: 'rgba(17,17,26,.09)',
  'line-strong': 'rgba(17,17,26,.14)',
  'line-input': 'rgba(17,17,26,.16)',
  field: '#8a8a93',
  'veil-1': 'rgba(17,17,26,.03)',
  'veil-2': 'rgba(17,17,26,.05)',
  'veil-3': 'rgba(17,17,26,.075)',
  // Un solo color de accion: el lila de Aurora oscurecido para el claro.
  accent: '#6550c4',
  'accent-hover': '#5a45b6',
  'accent-press': '#4e3ca3',
  'accent-soft': '#f0edfb',
  'accent-line': 'rgba(101,80,196,.30)',
  focus: '#6550c4',
  'focus-ring': 'rgba(101,80,196,.18)',
  selection: '#ddd6f6',
  scroll: '#c7c7cc',
  // Los estados: texto oscuro del tono sobre su tinte, su linea y su punto (3:1 sobre el tinte).
  ok: '#17723f',
  'ok-soft': '#e9f6ee',
  'ok-line': '#b9e0c7',
  'ok-dot': '#1f9a55',
  warn: '#94520a',
  'warn-soft': '#fdf3e3',
  'warn-line': '#f0d4a6',
  'warn-dot': '#bf7408',
  danger: '#b8261c',
  'danger-soft': '#fdeeed',
  'danger-line': '#f3c3bf',
  'danger-dot': '#e5483d',
  info: '#1d5bbf',
  'info-soft': '#ebf2fd',
  'info-line': '#bcd2f5',
  'info-dot': '#3b7be8',
  // Sombras de tinta neutra: shadow-2 en lo que flota sobre la pagina, shadow-3 en lo que se
  // abre encima; highlight, solo el reflejo de dentro (inset); tick, las marcas apagadas.
  shadow: 'rgba(16,16,24,.08)',
  'shadow-1': '0 1px 2px rgba(16,16,24,.05)',
  'shadow-2': '0 1px 2px rgba(16,16,24,.04),0 8px 24px rgba(16,16,24,.06)',
  'shadow-3': '0 2px 8px rgba(16,16,24,.06),0 24px 64px -12px rgba(16,16,24,.18)',
  highlight: 'rgba(255,255,255,.6)',
  tick: '#dcdce1',
};

const v = (name) => {
  if (!(name in PALETTE)) throw new Error(`--l-${name} no esta en la paleta`);
  return `var(--l-${name})`;
};

/** Las propiedades cuyo valor puede llevar un color. */
const COLOR_PROPS = /^(color|background(-color|-image)?|border(-(top|right|bottom|left))?(-color)?|outline(-color)?|box-shadow|text-shadow|fill|stroke|caret-color|scrollbar-color|filter|text-decoration-color|accent-color|-webkit-text-fill-color)$/;
/** Las del contorno sin color (el anillo de foco): van tal cual, como las de arriba sin color. */
const OUTLINE_PROPS = /^outline-(offset|width|style)$/;

const NAMED = { white: [255, 255, 255, 1], black: [0, 0, 0, 1], transparent: null };

// ---- OKLab (Bjorn Ottosson), de sRGB.
const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

function rgbToOklab([r, g, b]) {
  const [lr, lg, lb] = [r, g, b].map((x) => toLinear(x / 255));
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

/** Luminosidad, croma y matiz (grados) en OKLab. */
export function lch(rgb) {
  const [L, a, b] = rgbToOklab(rgb);
  const h = (Math.atan2(b, a) * 180) / Math.PI;
  return [L, Math.hypot(a, b), h < 0 ? h + 360 : h];
}

export function parseColor(token) {
  const t = token.toLowerCase();
  if (t in NAMED) return NAMED[t];
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

/** El color sobre un fondo (para saber como se ve un color con transparencia). */
function over([r, g, b, a], [br, bg, bb]) {
  return [r * a + br * (1 - a), g * a + bg * (1 - a), b * a + bb * (1 - a)];
}

const DARK_BG = [16, 16, 21];
const PAPER_BG = [237, 234, 241];

/** El tono de un color con matiz: verde, ambar, rojo, azul o lila (null si es un gris). Los
 *  grises de Aurora llevan un poco de lila: hasta un croma de 0,075 siguen siendo grises. */
export function hue(rgb) {
  const [, C, h] = lch(rgb);
  const purple = h >= 270 && h < 350;
  if (C < 0.03 || (purple && C < 0.075)) return null;
  if (purple) return 'accent';
  if (h >= 350 || h < 45) return 'danger';
  if (h < 105) return 'warn';
  if (h < 200) return 'ok';
  return 'info';
}

/** Un texto: por su luminosidad sobre el fondo donde esta (oscuro o, en una superficie clara de
 *  Aurora, el papel), el nivel de tinta; con matiz, su estado o el acento. */
export function textRole(rgba, onLight = false) {
  const seen = over(rgba, onLight ? PAPER_BG : DARK_BG);
  const tone = hue(seen);
  if (tone) return v(tone);
  const [L] = lch(seen);
  if (onLight) return v(L <= 0.4 ? 'ink-1' : L <= 0.55 ? 'ink-2' : 'ink-3');
  // Un texto oscuro en el tema oscuro solo va sobre un relleno claro: en el claro, sobre tinta.
  if (L < 0.3) return v('on-fill');
  return v(L >= 0.86 ? 'ink-1' : L >= 0.68 ? 'ink-2' : 'ink-3');
}

/** El placeholder de un campo: siempre el mismo token, sea cual sea el gris de la hoja. */
export function placeholderRole() {
  return v('placeholder');
}

/** Un velo (fondo con transparencia): tinta muy suave, por su fuerza. */
function veil(alpha) {
  return v(alpha < 0.05 ? 'veil-1' : alpha < 0.1 ? 'veil-2' : 'veil-3');
}

/** Un fondo. `page`: la regla es una pagina. */
export function backgroundRole(rgba, { page = false, onLight = false } = {}) {
  const [r, g, b, a] = rgba;
  const tone = hue([r, g, b]);
  const [L] = lch([r, g, b]);
  if (a >= 0.5) {
    if (tone === 'accent' || (tone && L > 0.5)) return tone === 'accent' ? v('accent') : v(`${tone}-dot`);
    if (tone) return v(`${tone}-soft`);
    if (onLight) return L > 0.75 ? v('surface') : v('ink-1');
    if (L < 0.35) {
      const base = v(page ? 'page' : 'surface');
      // Translucido: la misma superficie con su alfa (sin un color suelto).
      return a >= 0.99 ? base : `color-mix(in srgb,${base} ${Math.round(a * 100)}%,transparent)`;
    }
    // Un relleno claro opaco en el oscuro (una barra, un circulo): tinta en el claro.
    if (L > 0.75) return v('ink-1');
    return v('ink-4');
  }
  if (tone && tone !== 'accent') return v(`${tone}-soft`);
  return veil(a);
}

/** Una linea (borde, contorno, trazo). */
export function lineRole(rgba, { focus = false } = {}) {
  const [r, g, b, a] = rgba;
  const tone = hue([r, g, b]);
  if (focus) return v('focus');
  if (tone && tone !== 'accent') return v(`${tone}-line`);
  if (a >= 0.99) {
    const [L] = lch([r, g, b]);
    return L < 0.35 ? v('line') : v('line-strong');
  }
  const strength = tone === 'accent' ? a * 0.6 : a;
  return v(strength <= 0.07 ? 'line-soft' : strength <= 0.13 ? 'line' : 'line-strong');
}

/** Una capa de sombra: los anillos (0 0 0 Npx) son lineas o el foco; las sombras, la sombra
 *  neutra; un brillo claro de fuera, nada (en el claro nunca hay un brillo blanco fuera de una
 *  pieza); los reflejos claros de dentro, highlight. */
function shadowLayer(layer, focus) {
  const tokens = layer.match(COLOR_TOKEN) ?? [];
  if (!tokens.length) return layer;
  const geometry = layer.replace(COLOR_TOKEN, '').trim();
  const inset = /\binset\b/.test(geometry);
  const lengths = geometry.replace(/\binset\b/, '').trim().split(/\s+/);
  const ring = lengths.length >= 4 && parseFloat(lengths[0]) === 0 && parseFloat(lengths[1]) === 0 && parseFloat(lengths[2]) === 0;
  return layer.replace(COLOR_TOKEN, (token) => {
    const rgba = parseColor(token);
    if (!rgba) return token;
    const [r, g, b, a] = rgba;
    const tone = hue([r, g, b]);
    const [L] = lch([r, g, b]);
    if (ring) {
      if (focus || tone === 'accent') return a >= 0.5 ? v('focus') : v('focus-ring');
      if (tone) return v(`${tone}-line`);
      return lineRole(rgba);
    }
    if (inset) return L > 0.6 && !tone ? v('highlight') : v('line-soft');
    if (L > 0.9) return 'transparent';
    if (tone === 'accent' && a > 0.2) return v('focus-ring');
    return v('shadow');
  });
}

/** Las capas de una lista separada por comas (sin partir dentro de parentesis). */
function layers(value) {
  const out = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < value.length; i += 1) {
    if (value[i] === '(') depth += 1;
    else if (value[i] === ')') depth -= 1;
    else if (value[i] === ',' && depth === 0) {
      out.push(value.slice(start, i));
      start = i + 1;
    }
  }
  out.push(value.slice(start));
  return out;
}

/** Que papel hace una variable por su nombre (las del resumen: --t1, --hair, --acc...). */
function varKind(prop) {
  if (/hair|line|border/.test(prop)) return 'line';
  if (/^--(t\d|fiat|stocks|crypto|acc|vb-on)$/.test(prop)) return 'text';
  return 'background';
}

/** El valor de una declaracion en el claro; null si no lleva ningun color. */
export function mapValue(prop, value, ctx = {}) {
  if (!COLOR_TOKEN.test(value)) return null;
  COLOR_TOKEN.lastIndex = 0;
  const focus = /:focus/.test(ctx.selector ?? '');
  const placeholder = /::placeholder/.test(ctx.selector ?? '');
  const kind = prop.startsWith('--')
    ? varKind(prop)
    : /^(color|fill|caret-color|-webkit-text-fill-color|text-decoration-color|accent-color)$/.test(prop)
      ? 'text'
      : /^background/.test(prop)
        ? 'background'
        : /^(border|outline|stroke)/.test(prop)
          ? 'line'
          : prop;
  if (kind === 'box-shadow') return layers(value).map((layer) => shadowLayer(layer, focus)).join(',');
  if (kind === 'text-shadow') return value.replace(COLOR_TOKEN, 'transparent');
  if (kind === 'filter') return value.replace(COLOR_TOKEN, () => v('shadow'));
  if (kind === 'scrollbar-color') return value.replace(COLOR_TOKEN, () => v('scroll'));
  return value.replace(COLOR_TOKEN, (token) => {
    const rgba = parseColor(token);
    if (!rgba) return token;
    if (kind === 'text') return placeholder ? placeholderRole() : ctx.onAccent ? v('on-fill') : textRole(rgba, ctx.onLight);
    if (kind === 'line') return /^outline/.test(prop) ? v('focus') : lineRole(rgba, { focus });
    return backgroundRole(rgba, ctx);
  });
}

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
    out.push({ prelude: css.slice(i, open).trim().replace(/\s+/g, ' '), body: css.slice(open + 1, j - 1) });
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
      return at < 0 ? null : { prop: d.slice(0, at).trim(), value: d.slice(at + 1).trim().replace(/\s+/g, ' ') };
    })
    .filter(Boolean);
}

/** html:not(.dark) delante de cada selector de la lista (:root pasa a ser el propio html). */
function prefix(selectors) {
  return selectors
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => (s.startsWith(':root') ? `html:not(.dark)${s.slice(5)}` : `html:not(.dark) ${s}`))
    .join(',');
}

/** La luminosidad relativa (WCAG) de un color opaco. */
function luminance([r, g, b]) {
  return [r, g, b].map((x) => toLinear(x / 255)).reduce((n, x, i) => n + x * [0.2126, 0.7152, 0.0722][i], 0);
}

/** Las superficies claras de Aurora con su propio texto oscuro (en la misma regla, un fondo
 *  opaco mas claro que su `color`): {selector, accent}. Con matiz lila son botones (en el claro,
 *  el acento con texto blanco); sin matiz, papel (en el claro, blanco con su texto oscuro). */
function lightSurfaces(css, out = []) {
  for (const { prelude, body } of blocks(css)) {
    if (prelude.startsWith('@')) {
      if (!prelude.startsWith('@keyframes') && !prelude.startsWith('@font-face')) lightSurfaces(body, out);
      continue;
    }
    const decls = declarations(body);
    const bg = decls.find(({ prop }) => prop === 'background' || prop === 'background-color');
    const text = decls.find(({ prop }) => prop === 'color');
    const fill = bg && (bg.value.match(COLOR_TOKEN) ?? []).map(parseColor)[0];
    const ink = text && (text.value.match(COLOR_TOKEN) ?? []).map(parseColor)[0];
    if (fill && ink && fill[3] >= 1 && luminance(fill) > luminance(ink)) {
      const accent = hue(fill.slice(0, 3)) === 'accent';
      out.push(...prelude.split(',').map((x) => ({ selector: x.trim(), accent })));
    }
  }
  return out;
}

/** La superficie clara en la que esta un selector (ella misma, un estado suyo o algo de dentro). */
function surfaceOf(selector, surfaces) {
  return surfaces.find(({ selector: k }) => selector === k || (selector.startsWith(k) && /^[\s>:.[+~]/.test(selector.slice(k.length))));
}

/** Las reglas que son una pagina (su fondo oscuro opaco es el de la pagina, no una superficie). */
const PAGE = /^(:root|\.workspace|\.search-workspace|\.app\.process-mode|\.has-panel \.response|\.document-loader|\.zur-loader)$/;

/** Lo que se disena a mano sobre las reglas de las hojas: por la lista de selectores tal como
 *  esta en la hoja, las declaraciones que sustituyen a las que saldrian (las demas se quedan);
 *  `null` quita la declaracion. */
export const DESIGN = {
  // La pagina: casi blanca y la misma en todas partes (el inicio, Documentos, la busqueda).
  ':root': { color: v('ink-1'), background: v('page') },
  '.workspace': { background: v('page') },
  '.search-workspace': { background: v('page') },
  // La caja (inicio, conversacion y entrada): blanca, con la linea del oscuro y la sombra de lo
  // que flota (la caja de Airbnb).
  // El anillo de foco de Aurora (1 px a 6 px): en el claro, 2 px del acento a 4 px. Las demas
  // reglas de foco conservan su outline-offset (van con el prefijo, mas especificas).
  'button:focus-visible,input:focus-visible': { outline: `2px solid ${v('focus')}`, 'outline-offset': '4px' },
  '.composer': { border: `1px solid ${v('line')}`, background: v('surface'), 'box-shadow': v('shadow-2') },
  '.conversation-mode .composer': { background: v('surface') },
  '.send': { border: '1px solid transparent', background: v('accent'), color: v('on-fill') },
  // El panel flota: blanco, linea fina y una sombra suave.
  '.panel': { background: v('surface'), border: `1px solid ${v('line')}`, 'box-shadow': v('shadow-2') },
  '.doc-icon': { background: v('subtle'), border: `1px solid ${v('line-soft')}`, color: v('ink-2') },
  '.balance-line': { background: `linear-gradient(90deg,${v('accent')} var(--balance-share,68%),${v('subtle-2')} var(--balance-share,68%))` },
  // Los secundarios con su contorno; el principal, el acento sin borde (Aurora: border:0).
  '.outline,.primary': { border: `1px solid ${v('line-strong')}` },
  '.primary': { background: v('accent'), color: v('on-fill') },
  // La tarjeta de una fila: un pozo tranquilo dentro del panel blanco.
  '.detail': { border: `1px solid ${v('line')}`, background: v('subtle') },
  '.detail p,.detail>span': { color: v('ink-2') },
  '.detail h3': { color: v('ink-1') },
  // Las cejas de 7-9 px en mayusculas (o con mucho espaciado): en ink-3 se miden en pixeles por
  // debajo de 4,5 (el suavizado de una letra tan pequena), asi que van en ink-2
  // (e2e/claro.spec.ts las mide).
  '.panel-top': { color: v('ink-2') },
  '.list-title': { color: v('ink-2') },
  '.search-eyebrow': { color: v('ink-2') },
  '[cmdk-group-heading]': { color: v('ink-2') },
  '.fb-eyebrow': { color: v('ink-2') },
  '.processing-eyebrow': { color: v('ink-2') },
  '.zur-reading-top': { color: v('ink-2') },
  '.ws-eyebrow': { color: v('ink-2') },
  '.ws-party-type': { color: v('ink-2') },
  '.ws-dialog-top': { color: v('ink-2') },
  '.panel-top button': { color: v('ink-2') },
  '.order-field .composer': { 'box-shadow': 'none', 'border-color': v('field') },
  // La busqueda de una lista del panel («Zoek bedrijf of document…»): un campo, con su borde a
  // 3:1; lo escrito en la tinta y el placeholder en su papel (ROLES), la lupa en el terciario.
  '.search': { border: `1px solid ${v('field')}`, background: v('surface'), color: v('ink-3') },
  '.search input': { color: v('ink-1') },
  '.filter-label': { color: v('ink-3') },
  '.order-error': { color: `${v('danger')}!important` },
  '.dropzone': { border: `1px dashed ${v('line-input')}`, color: v('ink-2') },
  '.dropzone span': { color: v('ink-3') },
  '.file-chip': { color: v('ink-2'), 'border-bottom': `1px solid ${v('line-soft')}` },
  '.success': { color: v('ok') },
  '.sample-label i': { background: v('ink-3') },
  // La rueda: el elegido en tinta, los demas en el gris terciario.
  '.process-highlight .nav-item.selected': { color: v('accent'), 'text-shadow': 'none' },
  // El orbe en process-highlight: el mismo color que en el resto (scripts/aurora-claro-mano.css),
  // sin el brillo de fuera.
  '.process-highlight .aurora canvas': { filter: 'hue-rotate(var(--aura-hue,0deg)) saturate(1.15)' },
  '.aurora:focus-visible': { 'box-shadow': `0 0 0 2px ${v('focus-ring')}` },
  '.bms-brand>span': { 'border-left': `1px solid ${v('line-strong')}` },
  '.bms-brand': { color: v('ink-1') },
  '.discreet-languages button[aria-pressed=true]': { color: v('ink-1') },
  // El saludo: "Welkom" en la tinta y la linea de debajo en el secundario.
  '.welcome-line p': { color: v('ink-2') },
  // Las pastillas: el tinte suave del estado, su linea y el texto oscuro del mismo tono.
  '.ui-status': { background: v('surface') },
  '.ui-status.online': { color: v('ok'), 'border-color': v('ok-line'), background: v('ok-soft') },
  '.ui-status.degraded': { color: v('warn'), 'border-color': v('warn-line'), background: v('warn-soft') },
  '.ui-status.offline': { color: v('danger'), 'border-color': v('danger-line'), background: v('danger-soft') },
  '.ui-status.maintenance': { color: v('info'), 'border-color': v('info-line'), background: v('info-soft') },
  '.tree-selection-background': { background: v('accent-soft') },
  '.tree-meta': { color: v('ink-3') },
  // La conversacion.
  '.chat-message-user .message-content': { background: v('subtle'), border: `1px solid ${v('line-soft')}`, color: v('ink-1') },
  '.chat-stop': { background: v('surface'), border: `1px solid ${v('line-strong')}`, color: v('ink-2') },
  '.typing-dots i': { background: v('ink-3') },
  '.chat-notice': { background: v('surface'), border: `1px solid ${v('line')}`, color: v('ink-1'), 'box-shadow': v('shadow-3') },
  // El "si" flotante de la conversacion; dentro de un panel, una tarjeta o la hoja va sin
  // sombra (scripts/aurora-claro-mano.css).
  '.chat-export': { background: v('glass'), border: `1px solid ${v('line')}`, 'box-shadow': v('shadow-2') },
  '.chat-export p': { color: v('ink-2') },
  '.chat-export button': { color: v('ink-2') },
  '.chat-action[aria-pressed=true]': { color: v('accent'), background: v('accent-soft') },
  '.chat-action:hover': { color: v('ink-1'), background: v('veil-2') },
  '.fox-avatar': { color: v('ink-2'), border: `1px solid ${v('line')}`, background: v('surface') },
  // La busqueda.
  '.search-hero': { border: `1px solid ${v('line')}`, background: v('surface'), 'box-shadow': v('shadow-2') },
  '.search-hero:focus-within': { 'border-color': v('accent'), 'box-shadow': `0 0 0 3px ${v('focus-ring')}` },
  '.search-submit': { background: v('accent'), color: v('on-fill') },
  '.search-submit:hover': { background: v('accent-hover') },
  '.filters-toggle': { border: `1px solid ${v('line-strong')}`, background: v('surface'), color: v('ink-1') },
  '.filters-toggle.filters-open': { background: v('accent-soft'), color: v('accent-hover') },
  '.filters-toggle>span': { background: v('accent'), color: v('on-fill') },
  // Los campos de formulario: su unico limite visible es el borde, a 3:1 (WCAG 1.4.11).
  '.ui-button,.filter-combo-trigger,.filter-date-trigger': { border: `1px solid ${v('field')}`, background: v('surface'), color: v('ink-1') },
  '.ui-avatar': { background: v('subtle'), color: v('ink-2'), border: `1px solid ${v('line')}` },
  '.ui-popover': { border: `1px solid ${v('line')}`, background: v('surface'), color: v('ink-1'), 'box-shadow': v('shadow-3') },
  '.ui-command-item[data-selected=true]': { background: v('veil-2'), color: v('ink-1') },
  '.ui-command-item>svg:last-child': { color: v('accent') },
  '.calendar-grid button.calendar-selected': { background: v('accent'), color: v('on-fill'), 'box-shadow': 'none' },
  '.calendar-month strong': { color: v('ink-1') },
  '.amount-values': { color: v('ink-1') },
  // El "borrar x" del rango: activo, en el terciario (inactivo, a mano).
  '.amount-heading>button': { color: v('ink-3') },
  '.ui-command-input input': { color: v('ink-1') },
  '.amount-track': { background: v('subtle-2') },
  '.amount-fill': { background: v('accent') },
  '.amount-thumb': { border: `2px solid ${v('accent')}`, background: v('surface'), 'box-shadow': v('shadow-1') },
  // El foco con el teclado en un tirador: el halo de Aurora (4 px del lila a 0,19) da 1,29 sobre
  // lo blanco. En el claro, el anillo de foco de todo lo demas (2 px del acento), a 2 px del
  // tirador, que ya lleva el borde del acento: 6,00 frente al hueco y frente a lo de fuera
  // (WCAG 1.4.11). Ocupa los mismos 4 px que el halo; la sombra es la del tirador en reposo (un
  // hueco pintado de blanco seria un brillo claro de fuera, que el claro no tiene).
  '.amount-thumb:focus-visible': { outline: `2px solid ${v('focus')}`, 'outline-offset': '2px', 'box-shadow': v('shadow-1') },
  '.amount-ghost': { background: v('accent-line') },
  '.active-filter-chips button': { border: `1px solid ${v('line')}`, color: v('ink-1'), background: v('surface') },
  '.result-file-icon': { border: `1px solid ${v('line-soft')}`, background: v('subtle'), color: v('ink-2') },
  '.search-result:hover': { background: v('veil-1') },
  '.result-info strong': { color: v('ink-1') },
  '.result-amount strong': { color: v('ink-1') },
  '.ui-dialog-overlay': { background: v('scrim') },
  '.ui-dialog': { background: v('surface'), border: `1px solid ${v('line')}`, 'box-shadow': v('shadow-3') },
  // El resumen general (Finance Bento): tarjetas blancas con su linea; las cifras en tinta.
  '.fb-card': { border: `1px solid ${v('line-soft')}`, background: v('surface'), 'box-shadow': v('shadow-2') },
  '.fb-hero': { background: v('surface') },
  '.fb-comparison i': { background: v('ink-1') },
  '.fb-comparison>div:last-child i': { background: v('ink-4') },
  '.fb-legend i': { background: v('ink-1') },
  '.fb-legend span:last-child i': { background: v('ink-4') },
  '.fb-bars i': { background: v('ink-1') },
  '.fb-bars a>div': { background: v('subtle-2') },
  '.fb-tabs button[aria-pressed=true]': { background: v('subtle-2'), color: v('ink-1') },
  '.finance-bento .fpb': { '--acc': v('accent') },
  '.finance-bento .fpb .card': { background: v('surface'), border: `1px solid ${v('line-soft')}`, 'box-shadow': v('shadow-2') },
  '.finance-bento .fpb .glass': { background: v('surface') },
  '.finance-bento .fpb .balance-row>div,.finance-bento .fpb .company-bars a>div': { background: v('subtle-2') },
  '.finance-bento .fpb .balance-row i,.finance-bento .fpb .company-bars i': { background: v('ink-1') },
  '.finance-bento .fpb .capsule': { background: v('subtle-2') },
  '.finance-bento .fpb .capsule i': { background: v('ink-1') },
  '.finance-bento .fpb .capsule-chart>div:last-child i': { background: v('ink-4') },
  '.finance-bento .fpb .review-values': { color: v('ink-2') },
  '.fpb': { '--acc': v('accent'), '--t1': v('ink-1'), '--t2': v('ink-2'), '--t3': v('ink-3'), '--hair': v('line'), '--fiat': v('ink-1'), '--stocks': v('ink-3'), '--crypto': v('ink-4') },
  '.fpb .fpb-c': { background: 'transparent', color: v('ink-1') },
  '.fpb .seg': { background: v('subtle-2'), border: `1px solid ${v('line-soft')}` },
  '.fpb .seg button[aria-pressed="true"]': { background: v('surface'), color: v('ink-1') },
  '.fpb .card .rim': { 'box-shadow': 'none' },
  '.fpb .glass': { background: v('surface'), border: `1px solid ${v('line-soft')}`, 'box-shadow': v('shadow-2') },
  '.fpb .solid': { color: v('on-fill') },
  '.fpb .solid .rim': { 'box-shadow': 'none' },
  '.fpb .solid .cap': { color: 'rgba(255,255,255,.82)' }, // RAW_OK
  '.fpb .chip': { background: v('ink-1'), color: v('on-fill') },
  '.fpb .tip': { background: v('surface'), color: v('ink-1'), border: `1px solid ${v('line')}`, 'box-shadow': v('shadow-2') },
  '.fpb .vb-badge': { '--vb-on': v('accent'), background: v('surface'), border: `1px solid ${v('line')}`, color: v('ink-1'), 'box-shadow': 'none' },
  // Procesar: la superficie blanca de Aurora (meerkat-scene.css: "the approved black PNGs live
  // on a clean white processing surface"); la suricata y el suelo, en tinta (BY_HAND).
  '.app.process-mode': { background: `${v('page')}!important`, color: `${v('ink-1')}!important` },
  '.document-loader': { color: v('ink-1'), background: 'transparent' },
  '.zur-loader': { color: v('ink-1'), background: 'transparent' },
  '.process-mode .flow-circle': { background: `${v('ink-1')}!important` },
  '.process-mode .flow-button:hover': { color: `${v('on-fill')}!important` },
  '.process-mode .processing-plan>i': { background: `${v('line-strong')}!important` },
  '.process-mode .analysis-entry': { 'border-color': `${v('line')}!important` },
  '.flow-button': { border: `1px solid ${v('line-input')}`, color: v('ink-1') },
  '.flow-button:hover': { color: v('on-fill') },
  '.flow-circle': { background: v('ink-1') },
  '.processing-progress .reached': { background: v('ink-1'), 'box-shadow': 'none' },
  '.zur-progress': { background: v('subtle-2'), color: v('ink-1') },
  '.zur-progress::-webkit-progress-bar': { background: v('subtle-2') },
  '.zur-progress::-webkit-progress-value': { background: v('ink-1') },
  '.zur-progress::-moz-progress-bar': { background: v('ink-1') },
  '.zur-debug button': { color: v('ink-1'), background: v('surface'), border: `1px solid ${v('line-strong')}` },
  '.zur-debug button:hover': { 'border-color': v('ink-1') },
  '.pc-progress i.filled': { color: v('ink-1') },
  '.pc-progress i': { color: v('line-strong') },
  // El marco de la tarjeta de Procesar y su cabecera ("AURORA / DOCUMENTEN" y el estado, 7 px:
  // en ink-2, como las cejas).
  '.pc-outline': { 'border-color': v('line') },
  '.is-running .pc-outline': { 'border-color': v('line-strong') },
  '.pc-label': { color: v('ink-2') },
  // Documentos.
  '.ws-tabs>a': { color: v('ink-2') },
  '.ws-heading>div>p:last-child': { color: v('ink-2') },
  '.ws-tabs>a[aria-current=page]': { background: v('surface'), color: v('ink-1'), 'box-shadow': `0 0 0 1px ${v('line-soft')},${v('shadow-1')}` },
  '.ws-folder-active': { 'border-color': v('line'), background: v('surface') },
  '.ws-breadcrumbs [aria-current=page]': { color: v('ink-1') },
  '.ws-file-table strong': { color: v('ink-1') },
  '.ws-empty h2': { color: v('ink-1') },
  // .ws-search es la busqueda de Documentos de Aurora: la app no la monta (el campo de verdad es
  // .search, mas arriba). Se deja disenada por si llega; no es uno de FIELDS.
  '.ws-search input': { color: v('ink-1') },
  '.ws-profile': { border: `1px solid ${v('line')}`, background: v('surface'), 'box-shadow': v('shadow-1') },
  '.ws-profile dt': { color: v('ink-3') },
  '.ws-profile dd': { color: v('ink-1') },
  '.ws-demo': { border: `1px solid ${v('line')}`, background: v('surface'), 'box-shadow': v('shadow-1') },
  '.ws-search': { border: `1px solid ${v('field')}`, background: v('surface') },
  '.tree-view': { border: `1px solid ${v('line')}`, background: v('surface'), 'box-shadow': v('shadow-1') },
  '.tree-row': { color: v('ink-2') },
  '.tree-row:hover': { background: v('veil-1'), color: v('ink-1') },
  '.tree-row:focus-visible': { 'box-shadow': `inset 0 0 0 2px ${v('focus')}`, background: 'transparent' },
  '.tree-row.tree-selected': { background: 'transparent', color: v('ink-1') },
  // La hoja: un dialogo blanco que flota sobre la pagina atenuada; el papel, blanco con su
  // linea y una sombra de hoja.
  '.ws-dialog': { border: `1px solid ${v('line')}`, background: v('surface'), color: v('ink-1'), 'box-shadow': v('shadow-3') },
  '.ws-dialog::backdrop': { background: v('scrim') },
  '.ws-paper': { background: v('surface'), color: v('ink-1'), 'box-shadow': `0 0 0 1px ${v('line-strong')},${v('shadow-1')}` },
  '.ws-paper hr': { 'border-top': `1px solid ${v('line')}` },
  '.ws-paper>p': { color: v('ink-3') },
  '.ws-paper dt': { color: v('ink-3') },
  '.ws-paper .ws-paper-disclaimer': { color: v('ink-3') },
  '.ws-download': { background: v('accent'), color: v('on-fill') },
  '.ws-toast': { border: `1px solid ${v('line')}`, background: v('surface'), color: v('ink-1'), 'box-shadow': v('shadow-3') },
  '.ws-file-analysis.new': { background: v('ok-soft'), 'border-color': v('ok-line'), color: v('ok') },
  '.ws-file-analysis.duplicate': { background: v('warn-soft'), 'border-color': v('warn-line'), color: v('warn') },
  '.gf-sheet--new': { 'box-shadow': `inset 0 0 0 1px ${v('ok-line')}!important` },
  '.gf-sheet--duplicate': { 'box-shadow': `inset 0 0 0 1px ${v('warn-line')}!important` },
  '.skip-link': { background: v('ink-1'), color: v('on-fill') },
  // El respaldo sin WebGL (RAW_OK): el radial lila y azul.
  '.siri-wave-fallback,.aurora canvas.siri-wave-fallback': {
    background: 'radial-gradient(ellipse 46% 9% at 50% 50%,rgba(101,80,196,.5),rgba(80,140,255,.22) 55%,transparent 72%)',
  },
  '.aurora:focus-visible::after': { 'box-shadow': `0 0 0 2px ${v('focus')}` },
  '[data-modality=keyboard] .composer:focus-within': { 'border-color': v('accent'), 'box-shadow': `0 0 0 3px ${v('focus-ring')}` },
};

function emitDecls(prelude, decls, seen, colored) {
  // Lo disenado va en la primera regla con ese selector y en las que llevan algun color (una
  // regla de despues sin color, como .panel{top:7dvh}, no lo repite).
  const design = seen.has(prelude) && !colored ? null : DESIGN[prelude];
  const out = new Map(decls);
  if (design) {
    for (const [prop, value] of Object.entries(design)) {
      if (value === null) out.delete(prop);
      else out.set(prop, value);
    }
  }
  return [...out].map(([prop, value]) => `${prop}:${value}`);
}

function lightRules(css, surfaces, seen, report) {
  const out = [];
  for (const { prelude, body } of blocks(css)) {
    if (prelude.startsWith('@keyframes') || prelude.startsWith('@font-face')) continue;
    if (prelude.startsWith('@media') || prelude.startsWith('@supports')) {
      if (/prefers-reduced-motion/.test(prelude)) continue;
      const inner = lightRules(body, surfaces, seen, report);
      if (inner.length) out.push(`${prelude}{${inner.join('')}}`);
      continue;
    }
    if (prelude.startsWith('@layer')) {
      out.push(...lightRules(body, surfaces, seen, report));
      continue;
    }
    const selectors = prelude.split(',').map((x) => x.trim());
    const surface = selectors.map((s) => surfaceOf(s, surfaces)).find(Boolean);
    const ctx = {
      selector: prelude,
      page: selectors.every((s) => PAGE.test(s)),
      onLight: Boolean(surface && !surface.accent),
      onAccent: Boolean(surface && surface.accent),
    };
    let colored = 0;
    const decls = declarations(body)
      .filter(({ prop }) => COLOR_PROPS.test(prop) || OUTLINE_PROPS.test(prop) || prop.startsWith('--'))
      .map(({ prop, value }) => {
        const mapped = OUTLINE_PROPS.test(prop) ? null : mapValue(prop, value, ctx);
        if (mapped !== null) {
          colored += 1;
          if (report) report.push(`${prelude} { ${prop}: ${value} }  ->  ${mapped}`);
          return [prop, mapped];
        }
        // Sin color (none, 0, inherit, una variable...): tal cual, para que la cascada del claro
        // sea la del oscuro. Una variable sin color no hace falta.
        return prop.startsWith('--') ? null : [prop, value];
      })
      .filter(Boolean);
    const emitted = emitDecls(prelude, decls, seen, colored);
    if (DESIGN[prelude]) seen.add(prelude);
    if (emitted.length) out.push(`${prefix(prelude)}{${emitted.join(';')}}`);
  }
  return out;
}

/** Los tokens de la paleta, una vez. */
function tokens() {
  return `html:not(.dark){${Object.entries(PALETTE)
    .map(([name, value]) => `--l-${name}:${value}`)
    .join(';')}}`;
}

/** Los papeles que no cuelgan de una regla de las hojas. El placeholder: el de cualquier campo
 *  del claro, tenga o no su regla en Aurora (el de .search no la tiene y Tailwind le daba el 50 %
 *  del color del campo). Va antes de las reglas de las hojas: las que si nombran un placeholder
 *  pesan mas y llevan el mismo token (mapValue). */
export const ROLES = [`html:not(.dark) ::placeholder{color:${placeholderRole()};opacity:1}`];

/** Los campos de formulario: su unico limite visible es el borde `field`, a 3:1 (WCAG 1.4.11).
 *  Cada uno es de una pieza que la app monta (un .tsx de src/aurora): la prueba falla si alguno
 *  solo esta en una hoja, y e2e/fixtures.ts (FORM_FIELDS) mide estos mismos en el navegador. */
export const FIELDS = ['.order-field .composer', '.filter-combo-trigger', '.filter-date-trigger', '.ui-button', '.search'];

/** Lo que va a mano (scripts/aurora-claro-mano.css): lo que no sale de una hoja de SHEETS o no
 *  se ve desde ella. Se escribe con el prefijo html:not(.dark) explicito y va al final. */
export const HAND_FILE = fileURLToPath(new URL('./aurora-claro-mano.css', import.meta.url));

/** Los unicos colores sueltos de claro.css (fuera de los tokens), cada uno con su porque. */
export const RAW_OK = {
  // El respaldo sin WebGL de la onda: un radial lila y azul (no hay pieza a la que dar papel).
  'rgba(101,80,196,.5)': 'el centro del respaldo sin WebGL (.siri-wave-fallback)',
  'rgba(80,140,255,.22)': 'el borde azul del respaldo sin WebGL',
  // La tarjeta solida del resumen: su subtitulo, blanco a 0,82 sobre la tinta.
  'rgba(255,255,255,.82)': 'el .cap de .fpb .solid, sobre su relleno de tinta',
  // Las carpetas de cristal (glass-folder-cards.css, data-tone light): su receta de cristal.
  'rgba(255,255,255,.28)': 'el tinte del frente de una carpeta, arriba (deja ver el marmol)',
  'rgba(255,255,255,.80)': 'el tinte del frente, al 46 % (donde van el nombre y la pastilla)',
  'rgba(255,255,255,.94)': 'el tinte del frente, abajo',
  '#f0f0f3': 'el respaldo de una carpeta, arriba',
  '#e6e6eb': 'el respaldo de una carpeta, abajo',
  'rgba(255,255,255,.7)': 'el canto del respaldo de una carpeta',
  'rgba(17,17,26,.10)': 'el canto del frente de una carpeta (un color solido sobre cristal blanco)',
  'rgba(16,16,24,.16)': 'la sombra difusa bajo una carpeta (.gf-shadow, con su blur de Aurora)',
  'rgba(16,16,24,.18)': 'la sombra de una hoja de una carpeta (.gf-sheet)',
  'rgba(20,20,22,.96)': '--gf-ink-soft: la meta de una carpeta (monoespaciada fina), 4,5 o mas medida en pixeles',
};

/** Las clases de un texto CSS (.xxx), sin las de dentro de comillas ni de atributos. */
export function classNames(css) {
  const out = new Set();
  for (const { prelude, body } of blocks(stripComments(css))) {
    if (prelude.startsWith('@')) {
      if (!prelude.startsWith('@keyframes')) for (const c of classNames(body)) out.add(c);
      continue;
    }
    const bare = prelude.replace(/"[^"]*"|'[^']*'/g, '').replace(/\[[^\]]*\]/g, '');
    for (const m of bare.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) out.add(m[1]);
  }
  return out;
}

/** Los .tsx de src/aurora (sin sus pruebas): lo que la app monta. */
export function appText() {
  const texts = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx')) texts.push(readFileSync(path, 'utf8'));
    }
  };
  walk(src);
  return texts.join('\n');
}

/** Donde puede vivir una clase de la capa a mano: las hojas de SHEETS, la de las carpetas de
 *  cristal y los .tsx de src/aurora. */
function knownText() {
  return [...[...SHEETS, 'documents/glass-folder-cards.css'].map((sheet) => readFileSync(src + sheet, 'utf8')), appText()].join('\n');
}

/** Las clases de una lista de selectores que no estan en ningun .tsx de src/aurora (un selector
 *  que solo vive en una hoja no pinta nada en la app). */
export function unmountedClasses(selectors, app = appText()) {
  return orphanClasses(selectors.map((s) => `${s}{}`).join('\n'), app);
}

/** Las clases de la capa a mano que no estan en ninguna hoja ni en ningun .tsx de src/aurora
 *  (una regla huerfana: Aurora cambio y la regla ya no pinta nada). */
export function orphanClasses(hand, known = knownText()) {
  return [...classNames(hand)].filter((name) => !new RegExp(`(^|[^\\w-])${name.replace(/[-]/g, '\\-')}($|[^\\w-])`).test(known));
}

/** Los colores sueltos (#..., rgb[a](...), white, black) en los valores de un texto CSS, salvo los
 *  de RAW_OK, los del bloque de los tokens y los de una mascara. */
export function rawColors(css) {
  const out = [];
  const visit = (text) => {
    for (const { prelude, body } of blocks(stripComments(text))) {
      if (prelude.startsWith('@')) {
        visit(body);
        continue;
      }
      if (prelude === 'html:not(.dark)' && body.trim().startsWith('--l-')) continue;
      for (const { prop, value } of declarations(body)) {
        // Una mascara solo usa la alfa: su #000 no es un color que se vea.
        if (/mask/.test(prop)) continue;
        for (const token of value.match(COLOR_TOKEN) ?? []) if (!(token in RAW_OK)) out.push(`${prelude} -> ${token}`);
      }
    }
  };
  visit(css);
  return out;
}

export function build(report, hand = readFileSync(HAND_FILE, 'utf8')) {
  const sheets = SHEETS.map((sheet) => stripComments(readFileSync(src + sheet, 'utf8')));
  const surfaces = sheets.flatMap((css) => lightSurfaces(css));
  const seen = new Set();
  const rules = sheets.flatMap((css) => lightRules(css, surfaces, seen, report));
  const missing = Object.keys(DESIGN).filter((k) => !seen.has(k));
  if (missing.length) throw new Error(`DESIGN nombra reglas que no estan en las hojas: ${missing.join(' | ')}`);
  const orphans = orphanClasses(hand);
  if (orphans.length) throw new Error(`aurora-claro-mano.css nombra clases que no estan en las hojas ni en src/aurora: ${orphans.join(' ')}`);
  const text = `/* El tema claro de las hojas de Aurora. NO SE EDITA A MANO: lo escribe
   frontend/scripts/aurora-claro.mjs a partir de ${SHEETS.join(', ')}
   (cada color, por el papel que hace en el oscuro, con la paleta clara --l-*, bajo html:not(.dark))
   y de frontend/scripts/aurora-claro-mano.css (lo disenado a mano). */
${tokens()}
${ROLES.join('\n')}
${rules.join('\n')}
${hand}`;
  const raw = rawColors(text);
  if (raw.length) throw new Error(`claro.css lleva colores sueltos (ni --l-* ni RAW_OK):\n${raw.join('\n')}`);
  return text;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  if (process.argv.includes('--papeles')) {
    const report = [];
    build(report);
    console.log(report.join('\n'));
    process.exit(0);
  }
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
