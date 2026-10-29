// Hojas de contactos Aurora | BMS (paso 17, especificacion §6.1): por cada estado de
// e2e/aurora/referencia.json, la captura de Aurora (la de herramientas/capture.cjs o medir-p4.cjs,
// en su carpeta de grabaciones) al lado de la de BMS (la que deja aurora-paridad.spec.ts o
// procesar.spec.ts al comparar las cajas: CAPTURAS_DIR/dark/aurora-<estado>-<ancho>.png). Es para
// mirarlas: los textos y las cifras difieren (son datos); lo que se comprueba solo son las cajas.
//
// Uso (desde frontend/, con PLAYWRIGHT_BROWSERS_PATH si hace falta):
//   node e2e/aurora/hojas.mjs --aurora <grabaciones de Aurora> [--bms <CAPTURAS_DIR>] [--salida <carpeta>]
// Por defecto, --bms es CAPTURAS_DIR (o test-results/capturas) y --salida, <bms>/hojas. Deja una
// hoja por estado, <salida>/<estado>-<ancho>.png, y dice cuales no tienen las dos capturas.
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from '@playwright/test';

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const aurora = arg('aurora');
if (!aurora) {
  console.error('Uso: node e2e/aurora/hojas.mjs --aurora <grabaciones de Aurora> [--bms <CAPTURAS_DIR>] [--salida <carpeta>]');
  process.exit(2);
}
const bms = arg('bms', process.env.CAPTURAS_DIR || join('test-results', 'capturas'));
const out = arg('salida', join(bms, 'hojas'));

/** Cada estado (sin el ancho ni «-reduce»): la grabacion de Aurora y su captura. */
const AURORA = {
  E0: ['inicio', 'inicio'],
  E1: ['menu', 'menu-0'],
  'E1-procesar': ['procesar', 'menu-procesar'],
  'E2-cobrar': ['cobrar', 'panel'],
  'E2-cobrar-tarjeta': ['cobrar', 'detail'],
  'E2-pagar': ['pagar', 'panel'],
  'E2-pagar-tarjeta': ['pagar', 'detail'],
  E3: ['chat', 'chat-typing'],
  E4: ['chat', 'chat-answer'],
  'E4-b': ['resumen', 'bento'],
  E5: ['busqueda', 'search'],
  'E5-resultados': ['busqueda', 'search-results'],
  'E5-filtros': ['busqueda', 'search-filters'],
  E6: ['documentos', 'documentos'],
  'E6-carpeta': ['documentos', 'carpeta'],
  'E6-h': ['documentos', 'preview'],
  'E7-P0': ['procesar', 'procesar-intro'],
  'E7-P4': ['procesar-p4', 'procesar-lectura'],
  'E7-P5': ['procesar', 'procesar-resultado'],
};

/** Las hojas: los estados de la referencia, mas L0 (contra el inicio) y la vista de un grupo
 *  (contra el panel de Aurora). */
const ref = JSON.parse(readFileSync(new URL('./referencia.json', import.meta.url), 'utf8'));
const sheets = [];
for (const key of Object.keys(ref).filter((k) => !k.startsWith('_'))) {
  const [state, width] = key.split('@');
  const reduce = state.endsWith('-reduce');
  const base = state.replace(/-reduce$/, '');
  const [rec, shot] = AURORA[base] ?? [];
  const auroraFile = rec ? join(aurora, `${rec}-${width}${reduce ? '-reduce' : ''}`, `${shot}.png`) : null;
  sheets.push({ name: `${state}-${width}`, width: Number(width), auroraFile, bmsFile: join(bms, 'dark', `aurora-${state}-${width}.png`) });
  if (base === 'E0' && !reduce) sheets.push({ name: `L0-${width}`, width: Number(width), auroraFile, bmsFile: join(bms, 'dark', `aurora-L0-${width}.png`) });
  if (/^E2-(cobrar|pagar)$/.test(base)) {
    sheets.push({ name: `${state}-grupo-${width}`, width: Number(width), auroraFile, bmsFile: join(bms, 'dark', `aurora-${state}-grupo-${width}.png`) });
  }
}

const dataUrl = (file) => (file && existsSync(file) ? `data:image/png;base64,${readFileSync(file).toString('base64')}` : null);
const escape = (text) => text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

function html(sheet, left, right) {
  // A 1440 cada captura va a la mitad; a 400, entera.
  const w = sheet.width > 720 ? 720 : sheet.width;
  const cell = (label, src, file) =>
    `<figure><figcaption>${label}</figcaption>${src ? `<img src="${src}" width="${w}">` : `<div class="none" style="width:${w}px">sin captura<br><small>${escape(file ?? '')}</small></div>`}</figure>`;
  return `<!doctype html><meta charset="utf-8"><style>
    body{margin:0;padding:16px;background:#111;color:#ddd;font:14px/1.4 system-ui,sans-serif}
    h1{margin:0 0 12px;font-size:16px;font-weight:600}
    main{display:flex;gap:16px;align-items:flex-start}
    figure{margin:0}figcaption{margin-bottom:6px;color:#aaa}
    img{display:block;border:1px solid #333}
    .none{display:flex;flex-direction:column;align-items:center;justify-content:center;height:200px;border:1px dashed #555;color:#888;text-align:center}
  </style><h1>${escape(sheet.name)} · Aurora | BMS</h1><main>${cell('Aurora', left, sheet.auroraFile)}${cell('BMS', right, sheet.bmsFile)}</main>`;
}

mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 600 } });
const missing = [];
for (const sheet of sheets) {
  const left = dataUrl(sheet.auroraFile);
  const right = dataUrl(sheet.bmsFile);
  if (!left || !right) missing.push(`${sheet.name}: ${left ? '' : 'Aurora '}${right ? '' : 'BMS'}`.trim());
  await page.setContent(html(sheet, left, right));
  await page.screenshot({ path: join(out, `${sheet.name}.png`), fullPage: true });
}
await browser.close();
console.log(`${sheets.length} hojas en ${out}`);
if (missing.length) console.log(`sin las dos capturas: ${missing.join(' · ')}`);
