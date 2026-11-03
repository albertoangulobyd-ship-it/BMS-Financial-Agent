// El tema claro de Aurora ("Aurora claro · linea fina", scripts/aurora-claro.mjs):
// - src/aurora/claro.css es el que escribe el script (nadie lo edita a mano ni se queda viejo al
//   cambiar una hoja) y todo va bajo html:not(.dark), asi que el oscuro no cambia;
// - cada color pasa por su papel (pagina, superficie, velo, linea, texto, acento, estado, sombra)
//   a la paleta clara, y la paleta pasa WCAG AA;
// - las guardas: DESIGN y la capa a mano solo nombran lo que existe, no hay colores sueltos,
//   ninguna superficie es mas oscura que la pagina y ninguna sombra es un brillo blanco.
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  DESIGN,
  HAND_FILE,
  PALETTE,
  RAW_OK,
  backgroundRole,
  build,
  lch,
  lineRole,
  mapValue,
  parseColor,
  rawColors,
  textRole,
} from './aurora-claro.mjs';

const script = fileURLToPath(new URL('./aurora-claro.mjs', import.meta.url));
const indexCss = fileURLToPath(new URL('../src/index.css', import.meta.url));
const hand = readFileSync(HAND_FILE, 'utf8');

/** Un color opaco [r, g, b]: el token (las alfas, sobre blanco). */
const solid = (value) => {
  const [r, g, b, a] = parseColor(value);
  return [r, g, b].map((x) => x * a + 255 * (1 - a));
};
const lum = (rgb) =>
  rgb
    .map((x) => {
      const c = x / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    })
    .reduce((n, x, i) => n + x * [0.2126, 0.7152, 0.0722][i], 0);
const ratio = (a, b) => {
  const [x, y] = [lum(solid(a)), lum(solid(b))].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};
const P = (name) => PALETTE[name];

/** Las reglas de un texto CSS: [{selectors, decls}] (las de dentro de @media/@supports tambien). */
function rules(css) {
  const out = [];
  const text = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const walk = (s) => {
    let i = 0;
    while (i < s.length) {
      const open = s.indexOf('{', i);
      if (open < 0) break;
      let depth = 1;
      let j = open + 1;
      while (j < s.length && depth > 0) {
        if (s[j] === '{') depth += 1;
        else if (s[j] === '}') depth -= 1;
        j += 1;
      }
      const prelude = s.slice(i, open).trim();
      const body = s.slice(open + 1, j - 1);
      if (prelude.startsWith('@')) walk(body);
      else
        out.push({
          prelude,
          decls: body
            .split(';')
            .map((d) => d.trim())
            .filter(Boolean)
            .map((d) => [d.slice(0, d.indexOf(':')).trim(), d.slice(d.indexOf(':') + 1).trim()]),
        });
      i = j;
    }
  };
  walk(text);
  return out;
}

/** Una lista separada por comas, sin partir dentro de comillas ni de parentesis. */
function splitTop(list) {
  const out = [];
  let depth = 0;
  let quote = null;
  let start = 0;
  for (let i = 0; i < list.length; i += 1) {
    const c = list[i];
    if (quote) {
      if (c === quote) quote = null;
    } else if (c === '"' || c === "'") quote = c;
    else if (c === '(' || c === '[') depth += 1;
    else if (c === ')' || c === ']') depth -= 1;
    else if (c === ',' && depth === 0) {
      out.push(list.slice(start, i));
      start = i + 1;
    }
  }
  out.push(list.slice(start));
  return out.map((s) => s.trim()).filter(Boolean);
}

/** Un valor con var(--l-x) resuelto con la paleta (una vez basta: los tokens no se anidan). */
const resolve = (value) => value.replace(/var\(--l-([\w-]+)\)/g, (_, name) => PALETTE[name] ?? `?${name}`);

describe('aurora-claro', () => {
  it('claro.css es el que escribe el script (y --comprobar sale con 0)', () => {
    const current = readFileSync(fileURLToPath(new URL('../src/aurora/claro.css', import.meta.url)), 'utf8');
    expect(current).toBe(build());
    const run = spawnSync(process.execPath, [script, '--comprobar'], { encoding: 'utf8' });
    expect(run.status, run.stderr).toBe(0);
  });

  it('cada selector, tambien los de la capa a mano, va bajo html:not(.dark): el oscuro no cambia', () => {
    const all = rules(build());
    expect(all.length).toBeGreaterThan(300);
    for (const { prelude } of all) {
      for (const s of splitTop(prelude)) expect(s, prelude).toMatch(/^html:not\(\.dark\)/);
    }
    for (const { prelude } of rules(hand)) {
      for (const s of splitTop(prelude)) expect(s, prelude).toMatch(/^html:not\(\.dark\)/);
    }
    expect(build()).not.toMatch(/prefers-color-scheme/);
  });

  it('la paleta pasa AA', () => {
    const at = (fg, bg, min) => expect(ratio(P(fg), P(bg)), `${fg} sobre ${bg}`).toBeGreaterThanOrEqual(min);
    for (const ink of ['ink-1', 'ink-2', 'ink-3']) for (const bg of ['page', 'surface', 'subtle', 'accent-soft']) at(ink, bg, 4.5);
    for (const ink of ['ink-1', 'ink-2']) at(ink, 'subtle-2', 4.5);
    for (const bg of ['page', 'surface', 'accent-soft']) at('accent', bg, 4.5);
    at('accent-hover', 'accent-soft', 4.5);
    for (const bg of ['accent', 'accent-hover', 'accent-press', 'danger']) at('on-fill', bg, 4.5);
    for (const tone of ['ok', 'warn', 'danger', 'info']) {
      for (const bg of [`${tone}-soft`, 'surface', 'page']) at(tone, bg, 4.5);
      at(`${tone}-dot`, `${tone}-soft`, 3);
    }
    for (const bg of ['page', 'surface', 'subtle', 'accent-soft']) at('focus', bg, 3);
    for (const bg of ['surface', 'page', 'subtle']) at('field', bg, 3);
    // El aviso de index.css (una nota dentro de una pantalla), en sus tokens del claro.
    const root = readFileSync(indexCss, 'utf8').match(/^:root \{[\s\S]*?^\}/m)[0];
    const token = (name) => root.match(new RegExp(`--${name}: (#[0-9a-f]{6});`))[1];
    expect(ratio(token('notice-foreground'), token('notice'))).toBeGreaterThanOrEqual(4.5);
  });

  it('por papel, no invertido: lo que flota es blanco, los velos son tinta y las sombras siguen siendo sombras', () => {
    // Los grises lila del oscuro son grises neutros.
    expect(textRole(parseColor('#89818f'))).toBe('var(--l-ink-3)');
    expect(textRole(parseColor('#c9c2d2'))).toBe('var(--l-ink-2)');
    expect(backgroundRole(parseColor('#b29acd0c'))).toBe('var(--l-veil-1)');
    // El panel (#101015) es una superficie blanca; el fondo de la pagina, la pagina.
    expect(backgroundRole(parseColor('#101015'))).toBe('var(--l-surface)');
    expect(backgroundRole(parseColor('#08090b'), { page: true })).toBe('var(--l-page)');
    // Un velo blanco es un velo de tinta; una linea blanca casi transparente, una linea fina.
    expect(backgroundRole(parseColor('#ffffff08'))).toBe('var(--l-veil-1)');
    expect(lineRole(parseColor('#ffffff10'))).toBe('var(--l-line-soft)');
    // Una sombra negra sale la sombra; un brillo blanco de fuera, nada; un reflejo de dentro,
    // highlight.
    expect(mapValue('box-shadow', '0 30px 100px #0009')).toBe('0 30px 100px var(--l-shadow)');
    expect(mapValue('box-shadow', '0 0 40px #ffffff55')).toBe('0 0 40px transparent');
    expect(mapValue('box-shadow', 'inset 0 1px 0 rgba(255,255,255,.2)')).toBe('inset 0 1px 0 var(--l-highlight)');
    // Un anillo del acento sale el foco (o su halo); un outline, el foco.
    expect(mapValue('box-shadow', '0 0 0 1px #9e92d0')).toBe('0 0 0 1px var(--l-focus)');
    expect(mapValue('box-shadow', '0 0 0 4px #9c6cba30')).toBe('0 0 0 4px var(--l-focus-ring)');
    expect(mapValue('outline', '1px solid #886b9d')).toBe('1px solid var(--l-focus)');
    // El texto por su nivel; los tonos de estado, su estado; un texto oscuro, sobre un relleno.
    expect(textRole(parseColor('#eee5fa'))).toBe('var(--l-ink-1)');
    expect(textRole(parseColor('#93b4a4'))).toBe('var(--l-ok)');
    expect(textRole(parseColor('#b59a76'))).toBe('var(--l-warn)');
    expect(textRole(parseColor('#f87171'))).toBe('var(--l-danger)');
    expect(textRole(parseColor('#93b9ee'))).toBe('var(--l-info)');
    expect(textRole(parseColor('#17121d'))).toBe('var(--l-on-fill)');
    // Las superficies claras de Aurora (el papel de la hoja, su texto oscuro) no se mapean como
    // oscuras: el papel es blanco y su texto, la tinta.
    const css = build();
    expect(css).toContain('html:not(.dark) .ws-paper{background:var(--l-surface);color:var(--l-ink-1)');
    expect(mapValue('padding', '12px')).toBeNull();
  });

  it('DESIGN solo nombra reglas que existen: una clave falsa hace fallar build()', () => {
    expect(Object.keys(DESIGN).length).toBeGreaterThan(120);
    DESIGN['.una-regla-que-no-existe'] = { color: 'var(--l-ink-1)' };
    try {
      expect(() => build()).toThrow(/DESIGN nombra reglas que no estan en las hojas: \.una-regla-que-no-existe/);
    } finally {
      delete DESIGN['.una-regla-que-no-existe'];
    }
  });

  it('la capa a mano solo nombra clases que existen en una hoja o en un .tsx de src/aurora', () => {
    expect(() => build(undefined, `${hand}\nhtml:not(.dark) .clase-huerfana .doc{color:var(--l-ink-1)}`)).toThrow(/clase-huerfana/);
    // Un atributo o un texto entre comillas no cuenta como clase.
    expect(() => build(undefined, `${hand}\nhtml:not(.dark) .fpb line[stroke=".x"]{stroke:var(--l-ink-1)}`)).not.toThrow();
  });

  it('ningun color suelto: todo es var(--l-*) salvo RAW_OK, cada entrada con su porque', () => {
    expect(rawColors(build())).toEqual([]);
    for (const [color, why] of Object.entries(RAW_OK)) {
      expect(parseColor(color), color).not.toBeNull();
      expect(why.length, color).toBeGreaterThan(10);
    }
    expect(() => build(undefined, `${hand}\nhtml:not(.dark) .doc{color:#123456}`)).toThrow(/colores sueltos[\s\S]*#123456/);
  });

  it('ninguna superficie es mas oscura que la pagina; los rellenos, de una lista cerrada', () => {
    const surfaces = ['surface', 'subtle', 'glass', 'page'];
    const fills = /^(subtle-2|accent(-hover|-press|-soft|-line)?|ink-[1-4]|on-fill|(ok|warn|danger|info)-(soft|dot)|scrim|veil-[123]|line-strong|selection|focus-ring)$/;
    const [pageL] = lch(solid(P('page')));
    const used = new Set();
    for (const { prelude, decls } of rules(build())) {
      for (const [prop, value] of decls) {
        if (prop !== 'background' && prop !== 'background-color') continue;
        for (const [, name] of value.matchAll(/var\(--l-([\w-]+)\)/g)) {
          used.add(name);
          if (surfaces.includes(name)) {
            const [L] = lch(solid(P(name)));
            expect(L, `${prelude}: ${name}`).toBeGreaterThanOrEqual(pageL - 0.005);
          } else expect(name, `${prelude}: ${value}`).toMatch(fills);
        }
      }
    }
    expect([...used]).toEqual(expect.arrayContaining(['surface', 'subtle', 'glass', 'page', 'subtle-2', 'accent']));
  });

  it('ninguna sombra ni brillo de fuera es claro (L > 0,9): en el claro nunca hay un brillo blanco', () => {
    let checked = 0;
    for (const { prelude, decls } of rules(build())) {
      for (const [prop, value] of decls) {
        const layers = [];
        if (prop === 'box-shadow') layers.push(...splitTop(resolve(value)).filter((layer) => !/\binset\b/.test(layer)));
        if (prop === 'filter') for (const m of resolve(value).matchAll(/drop-shadow\(([^()]*(?:\([^()]*\))?[^()]*)\)/g)) layers.push(m[1]);
        for (const layer of layers) {
          for (const token of layer.match(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\bwhite\b/g) ?? []) {
            const [r, g, b] = parseColor(token);
            checked += 1;
            expect(lch([r, g, b])[0], `${prelude}: ${prop} ${value}`).toBeLessThanOrEqual(0.9);
          }
        }
      }
    }
    expect(checked).toBeGreaterThan(40);
  });

  it('lo disenado: lo que flota, la caja, el papel, los campos y la seleccion del arbol', () => {
    const css = build();
    expect(css).toMatch(/html:not\(\.dark\) \.panel\{background:var\(--l-surface\);border:1px solid var\(--l-line\);[^}]*box-shadow:var\(--l-shadow-2\)\}/);
    expect(css).toContain('html:not(.dark) .composer{border:1px solid var(--l-line);background:var(--l-surface);box-shadow:var(--l-shadow-2)}');
    expect(css).toContain('html:not(.dark) .ws-dialog::backdrop{background:var(--l-scrim)');
    expect(css).toContain('html:not(.dark) .ws-paper{background:var(--l-surface);color:var(--l-ink-1);box-shadow:0 0 0 1px var(--l-line-strong),var(--l-shadow-1)}');
    expect(css).toContain('html:not(.dark) .ui-button,html:not(.dark) .filter-combo-trigger,html:not(.dark) .filter-date-trigger{border:1px solid var(--l-field)');
    expect(css).toContain('html:not(.dark) .tree-selection-background{background:var(--l-accent-soft)}');
    expect(css).toContain('html:not(.dark) .primary{background:var(--l-accent);color:var(--l-on-fill)');
    // El anillo de foco: 2 px del acento a 4 px (el de Aurora, 1 px a 6 px).
    expect(css).toContain('html:not(.dark) button:focus-visible,html:not(.dark) input:focus-visible{outline:2px solid var(--l-focus);outline-offset:4px}');
    // La cascada del claro es la del oscuro: lo que Aurora quita sin color tambien se repite.
    expect(css).toContain('html:not(.dark) .primary{background:var(--l-accent);color:var(--l-on-fill);border:0');
  });

  it('inactivo frente a activo: el enviar y el principal sin nada que hacer son grises, no el acento lavado', () => {
    const decl = (selector) => {
      const rule = rules(build()).find(({ prelude }) => splitTop(prelude).includes(`html:not(.dark) ${selector}`));
      expect(rule, selector).toBeTruthy();
      return Object.fromEntries(rule.decls);
    };
    const active = decl('.send');
    for (const disabled of [decl('.send:disabled'), decl('.primary:disabled:not([aria-busy=true])')]) {
      expect(disabled.opacity).toBe('1');
      expect(disabled.background).toBe('var(--l-subtle-2)');
      expect(disabled.background).not.toBe(active.background);
    }
    expect(active.background).toBe('var(--l-accent)');
  });

  it('Procesar es la sala clara del dueno: la pagina y la suricata en tinta', () => {
    const css = build();
    expect(css).toContain('html:not(.dark) .app.process-mode{background:var(--l-page)!important;color:var(--l-ink-1)!important}');
    expect(css).toContain('html:not(.dark) .zur-world,html:not(.dark) .zur-pile{filter:invert(.91)}');
  });

  it('el oscuro intacto: el bloque :root.dark de index.css, byte a byte el de antes', () => {
    // SHA-256 del bloque ":root.dark { ... }" de src/index.css en 5a14f5d (el claro se rehizo
    // encima sin tocarlo). Si cambia, cambia el oscuro: no es cosa del claro.
    const block = readFileSync(indexCss, 'utf8').match(/^:root\.dark \{[\s\S]*?^\}/m)[0];
    expect(createHash('sha256').update(`${block}\n`).digest('hex')).toBe('a1646c2a2b4caf2240dfc31ff6b5d62bc2cfecd3dfe3e73c7e399605efba7280');
  });
});
