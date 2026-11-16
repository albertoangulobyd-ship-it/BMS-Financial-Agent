// montar.mjs — de lo capturado (captura/) hace UN fichero HTML que se abre solo, sin red y sin
// dependencias: salida/bms-finance-diseno.html.
//
//   node montar.mjs [--captura <carpeta>] [--salida <fichero>]
//
// Dentro van, una sola vez, la hoja de estilo de la app tal como la sirve y las imagenes (el
// logotipo y lo que ensenaba cada canvas); cada fotograma es su HTML tal cual, en un
// <script type="text/plain">, y se monta en su propio <iframe srcdoc> al acercarse a la
// ventana: asi ningun estilo se sale de su marco ni entra en el. La primera pagina (los colores
// y la escala de letra) sale de la hoja de verdad y de lo que usan los fotogramas.
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { argumentos, CAPTURA, falla, NOMBRE_TEMA, SALIDA, TEMAS } from './comun.mjs';
import { RESTAURAR } from './congelar.mjs';
import { ESTADOS } from './estados.mjs';

const args = argumentos();
const carpeta = typeof args.captura === 'string' ? resolve(args.captura) : CAPTURA;
const salida = typeof args.salida === 'string' ? resolve(args.salida) : SALIDA;
if (!existsSync(join(carpeta, 'captura.json'))) {
  falla(`no hay nada capturado en ${carpeta}: primero npm run diseno:capturar (o node herramientas/diseno/capturar.mjs; unos 9 min)`);
}
const indice = JSON.parse(readFileSync(join(carpeta, 'captura.json'), 'utf8'));

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const sinCierre = (texto, que) => {
  if (/<\/script/i.test(texto)) throw new Error(`${que}: lleva «</script» y no cabe en un <script type="text/plain">`);
  return texto;
};

// ------------------------------------------------------------------ los fotogramas

const orden = ESTADOS.map((e) => e.id);
const ids = Object.keys(indice.marcos).sort((a, b) => {
  const x = indice.marcos[a];
  const y = indice.marcos[b];
  return orden.indexOf(x.estado) - orden.indexOf(y.estado) || y.ancho - x.ancho || TEMAS.indexOf(x.tema) - TEMAS.indexOf(y.tema);
});
const recursos = {};
const hojas = {};
const marcos = [];
const tipos = {};
const colores = { dark: {}, light: {} };
for (const id of ids) {
  const fichero = join(carpeta, `${id}.json`);
  if (!existsSync(fichero)) throw new Error(`falta ${fichero} (vuelve a capturar)`);
  const m = JSON.parse(readFileSync(fichero, 'utf8'));
  // Los recursos del fotograma, a la tabla comun (por su contenido: los que se repiten van una vez).
  let html = m.html.replace(/df-recurso:(\d+)/g, (_, n) => {
    const url = m.recursos[Number(n)];
    if (!url) throw new Error(`${id}: falta el recurso ${n}`);
    const h = `h${createHash('sha256').update(url).digest('hex').slice(0, 12)}`;
    recursos[h] = url;
    return `df-recurso:${h}`;
  });
  html = html.replace(/<style data-df-css="(\d+)"><\/style>/g, (_, n) => {
    const nombre = m.hojas[Number(n)];
    hojas[nombre] ??= readFileSync(join(carpeta, nombre), 'utf8');
    return `<style data-df-css="${nombre}"></style>`;
  });
  if (!html.includes('</body>')) throw new Error(`${id}: sin </body>`);
  marcos.push({ ...indice.marcos[id], nota: m.nota, alto: m.alto, html: sinCierre(html, id) });
  for (const [clave, e] of Object.entries(m.tipos)) {
    const t = (tipos[clave] ??= { n: 0, muestra: e.muestra, estados: new Set() });
    t.n += e.n;
    t.estados.add(m.estado);
  }
  for (const [clave, e] of Object.entries(m.colores)) {
    const t = (colores[m.tema][clave] ??= { n: 0, muestra: e.muestra, estados: new Set() });
    t.n += e.n;
    t.estados.add(m.estado);
  }
}
for (const [nombre, css] of Object.entries(hojas)) {
  sinCierre(css, nombre);
  if (/<\/style/i.test(css)) throw new Error(`${nombre}: lleva «</style»`);
}

// ------------------------------------------------------------------ la primera pagina: colores y letra

const tokens = Object.fromEntries(TEMAS.map((t) => [t, existsSync(join(carpeta, `tokens-${t}.json`)) ? JSON.parse(readFileSync(join(carpeta, `tokens-${t}.json`), 'utf8')) : []]));

/** rgb(a) del navegador a #hex (con alfa si no es opaco); lo demas (oklch…), tal cual. */
function hex(color) {
  const m = /^rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(color ?? '');
  if (!m) return color ?? '';
  const h = (n) => Number(n).toString(16).padStart(2, '0');
  const alfa = m[4] === undefined ? 1 : m[4].endsWith('%') ? Number(m[4].slice(0, -1)) / 100 : Number(m[4]);
  return `#${h(m[1])}${h(m[2])}${h(m[3])}${alfa < 1 ? h(Math.round(alfa * 255)) : ''}`;
}
/** #fff y #ffffff son el mismo: no se dice dos veces. */
const largo = (v) => (/^#[0-9a-f]{3}$/i.test(v) ? `#${[...v.slice(1)].map((c) => c + c).join('')}` : v).toLowerCase();
const igual = (a, b) => largo(a) === largo(b);
const muestra = (color) => (color ? `<span class="muestra"><i style="background:${esc(color)}"></i></span>` : '<span class="muestra vacia"></span>');

function familia(nombre) {
  if (nombre.startsWith('--l-')) return 'claro';
  if (nombre.startsWith('--color-') || nombre.startsWith('--tw-')) return 'tailwind';
  return 'app';
}
const FAMILIAS = {
  claro: ['La paleta del tema claro (--l-*)', 'Declarada bajo <code>html:not(.dark)</code> en claro.css (la escribe frontend/scripts/aurora-claro.mjs). En el oscuro no existe: el diseño oscuro de Aurora lleva sus colores escritos en cada regla (están más abajo, en «Colores en uso»).'],
  app: ['Los colores con nombre de la app', 'Las propiedades de <code>:root</code> y <code>:root.dark</code> (frontend/src/index.css) y las que declaran las hojas de Aurora.'],
  tailwind: ['Los de Tailwind que usa la hoja', 'Solo los que la construcción deja en la hoja.'],
};
function tablaTokens() {
  const nombres = [...new Set(TEMAS.flatMap((t) => tokens[t].filter((x) => x.clase === 'color').map((x) => x.nombre)))];
  const de = (tema, nombre) => tokens[tema].find((x) => x.nombre === nombre);
  let out = '';
  let total = 0;
  for (const [clave, [titulo, texto]] of Object.entries(FAMILIAS)) {
    const suyos = nombres.filter((n) => familia(n) === clave);
    if (!suyos.length) continue;
    total += suyos.length;
    out += `<h3>${titulo} <small>${suyos.length}</small></h3><p class="nota">${texto}</p><table class="tokens"><thead><tr><th>Nombre</th><th colspan="2">Oscuro</th><th colspan="2">Claro</th><th>Dónde se declara</th></tr></thead><tbody>`;
    for (const n of suyos) {
      const o = de('dark', n);
      const c = de('light', n);
      const celda = (x) => (x ? `<td class="m">${muestra(x.color)}</td><td><code>${esc(x.valor)}</code>${igual(hex(x.color), x.valor) ? '' : `<br><small>${esc(hex(x.color))}</small>`}</td>` : '<td class="m"></td><td><small>—</small></td>');
      out += `<tr data-token="${esc(n)}"><th><code>${esc(n)}</code></th>${celda(o)}${celda(c)}<td><small>${esc(((o ?? c).donde ?? []).join(' · '))}</small></td></tr>`;
    }
    out += '</tbody></table>';
  }
  return { html: out, total };
}

const ROLES = { texto: 'Texto', fondo: 'Fondos', borde: 'Bordes' };
function tablaUso(tema) {
  let out = '';
  for (const [rol, titulo] of Object.entries(ROLES)) {
    const filas = Object.entries(colores[tema])
      .filter(([k]) => k.startsWith(`${rol}|`))
      .map(([k, e]) => ({ color: k.slice(rol.length + 1), ...e }))
      .sort((a, b) => b.n - a.n)
      .slice(0, 18);
    if (!filas.length) continue;
    out += `<div class="uso"><h4>${titulo}</h4><table class="tokens"><tbody>`;
    for (const f of filas) out += `<tr><td class="m">${muestra(f.color)}</td><td><code>${esc(hex(f.color))}</code></td><td class="n">${f.n}×</td><td><small>${esc(f.muestra)}</small></td></tr>`;
    out += '</tbody></table></div>';
  }
  return out;
}

function tablaLetra() {
  // Por cuerpo de letra, de mayor a menor: sus pesos, interlineados y familias, con una muestra.
  const filas = Object.entries(tipos).map(([clave, e]) => {
    const [familia_, cuerpo, peso, linea, espaciado, caja] = clave.split('|');
    return { familia: familia_, cuerpo, peso, linea, espaciado, caja, n: e.n, muestra: e.muestra, estados: e.estados.size };
  });
  const grupos = new Map();
  for (const f of filas) {
    const k = `${f.cuerpo}|${f.familia}`;
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(f);
  }
  const lista = [...grupos.entries()].sort((a, b) => parseFloat(b[0]) - parseFloat(a[0]) || b[1].reduce((n, f) => n + f.n, 0) - a[1].reduce((n, f) => n + f.n, 0));
  let out = '<table class="tokens letra"><thead><tr><th>Cuerpo</th><th>Familia</th><th>Peso · interlineado · espaciado</th><th>Usos</th><th>Muestra</th></tr></thead><tbody>';
  for (const [k, suyas] of lista) {
    const [cuerpo, familia_] = k.split('|');
    suyas.sort((a, b) => b.n - a.n);
    const principal = suyas[0];
    const variantes = suyas.slice(0, 6).map((f) => `<code>${esc(f.peso)}</code> · ${esc(f.linea)} · ${esc(f.espaciado)}${f.caja !== 'none' ? ` · ${esc(f.caja)}` : ''} <small>(${f.n}×)</small>`).join('<br>') + (suyas.length > 6 ? `<br><small>y ${suyas.length - 6} más</small>` : '');
    const estilo = `font-family:${principal.familia};font-size:${cuerpo};font-weight:${principal.peso};line-height:${principal.linea};letter-spacing:${principal.espaciado};text-transform:${principal.caja}`;
    out += `<tr><th><code>${esc(cuerpo)}</code></th><td><small>${esc(familia_)}</small></td><td>${variantes}</td><td class="n">${suyas.reduce((n, f) => n + f.n, 0)}×</td><td class="ejemplo"><span style="${esc(estilo)}">${esc(principal.muestra)}</span></td></tr>`;
  }
  out += '</tbody></table>';
  const otros = tokens.dark.filter((x) => x.clase === 'otro');
  if (otros.length) {
    out += '<h3>Las medidas con nombre de la hoja</h3><table class="tokens"><tbody>';
    for (const x of otros) out += `<tr><th><code>${esc(x.nombre)}</code></th><td><code>${esc(x.valor)}</code></td><td><small>${esc(x.donde.join(' · '))}</small></td></tr>`;
    out += '</tbody></table>';
  }
  return { html: out, cuerpos: lista.length };
}

const tk = tablaTokens();
const letra = tablaLetra();

// ------------------------------------------------------------------ el documento

const NOTA_ESTADO = Object.fromEntries(ESTADOS.map((e) => [e.id, e.nota]));
const TITULO_ESTADO = Object.fromEntries(ESTADOS.map((e) => [e.id, e.titulo]));
const estados = [...new Set(marcos.map((m) => m.estado))];
const anchos = [...new Set(marcos.map((m) => m.ancho))].sort((a, b) => b - a);
const temas = TEMAS.filter((t) => marcos.some((m) => m.tema === t));

const indiceHtml = estados
  .map((e, i) => {
    const suyos = marcos.filter((m) => m.estado === e);
    const enlaces = suyos.map((m) => `<a href="#m-${m.id}" data-ir="${m.id}">${m.ancho} ${NOMBRE_TEMA[m.tema]}</a>`).join('');
    return `<li><span class="num">${String(i + 1).padStart(2, '0')}</span><span class="que"><b>${esc(TITULO_ESTADO[e] ?? e)}</b><small>${esc(NOTA_ESTADO[e] ?? '')}</small></span><span class="variantes">${enlaces}</span></li>`;
  })
  .join('\n');

const marcosHtml = marcos
  .map(
    (m) => `<article class="marco" id="m-${m.id}" data-id="${m.id}" data-estado="${m.estado}" data-tema="${m.tema}" data-ancho="${m.ancho}" style="--w:${m.ancho};--h:${m.alto}">
<header><h3>${esc(m.titulo)}</h3><p><code>${m.id}</code> · ${m.ancho} × ${m.alto} px · tema ${NOMBRE_TEMA[m.tema]} · <a href="#solo=${m.id}">solo, a tamaño real</a></p><p class="nota">${esc(m.nota ?? '')}</p></header>
<div class="lienzo"><iframe title="${esc(m.titulo)} · ${m.ancho} px · ${NOMBRE_TEMA[m.tema]}" width="${m.ancho}" height="${m.alto}" sandbox="allow-scripts" data-marco="${m.id}"></iframe></div>
</article>`
  )
  .join('\n');

const fecha = new Date().toISOString().slice(0, 10);
const ESTILO = `
:root{color-scheme:dark;--fondo:#16171b;--panel:#1f2026;--linea:#34353d;--tinta:#ececf1;--tinta2:#a9aab4;--acento:#b9a7ff;--escala:.5}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;background:var(--fondo);color:var(--tinta);font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--acento)}
code{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
small{color:var(--tinta2)}
.barra{position:sticky;top:0;z-index:10;display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center;padding:10px 20px;background:rgba(22,23,27,.94);border-bottom:1px solid var(--linea);backdrop-filter:blur(8px)}
.barra h1{margin:0;font-size:15px;font-weight:650;letter-spacing:.01em}
.barra nav{display:flex;gap:14px}
.grupo{display:flex;align-items:center;gap:4px}
.grupo>span{color:var(--tinta2);font-size:12px;margin-right:4px}
.grupo button{font:inherit;font-size:12px;color:var(--tinta);background:var(--panel);border:1px solid var(--linea);border-radius:6px;padding:4px 10px;cursor:pointer}
.grupo button[aria-pressed=true]{background:var(--acento);border-color:var(--acento);color:#17122b;font-weight:600}
#cuenta{color:var(--tinta2);font-size:12px;margin-left:auto}
main{padding:20px}
section{margin:0 0 48px}
h2{font-size:22px;font-weight:600;margin:8px 0 6px}
h3{font-size:15px;margin:28px 0 4px}
h3 small{font-weight:400;margin-left:6px}
h4{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--tinta2);margin:0 0 6px}
p{margin:4px 0}
.nota{color:var(--tinta2);max-width:92ch}
.datos{color:var(--tinta2);font-size:12px}
table.tokens{border-collapse:collapse;margin:8px 0 0;font-size:12px}
table.tokens th,table.tokens td{text-align:left;vertical-align:middle;padding:5px 12px 5px 0;border-bottom:1px solid var(--linea);font-weight:400}
table.tokens thead th{color:var(--tinta2);font-size:11px;letter-spacing:.06em;text-transform:uppercase}
td.m{padding-right:8px!important;width:44px}
td.n{color:var(--tinta2);white-space:nowrap}
.muestra{display:inline-block;width:40px;height:26px;border-radius:5px;border:1px solid var(--linea);overflow:hidden;vertical-align:middle;background:repeating-conic-gradient(#8a8a8a 0 25%,#b5b5b5 0 50%) 0 0/10px 10px}
.muestra i{display:block;width:100%;height:100%}
.muestra.vacia{background:none;border-style:dashed}
.dos{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:24px 40px}
.usos{display:flex;flex-wrap:wrap;gap:16px 36px}
td.ejemplo{max-width:520px;overflow:hidden;white-space:nowrap}
td.ejemplo span{display:inline-block;color:var(--tinta)}
ol.indice{list-style:none;margin:12px 0 0;padding:0;columns:2 520px;column-gap:40px}
ol.indice li{display:flex;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--linea);break-inside:avoid}
ol.indice .num{color:var(--tinta2);font:12px ui-monospace,monospace}
ol.indice .que{flex:1;display:flex;flex-direction:column}
ol.indice .variantes{display:flex;flex-wrap:wrap;gap:4px 10px;justify-content:flex-end;font-size:12px;max-width:220px}
.galeria{display:flex;flex-wrap:wrap;gap:36px 28px;align-items:flex-start}
.marco[hidden]{display:none}
.marco header h3{margin:0}
.marco header p{font-size:12px;color:var(--tinta2);margin:2px 0}
.marco header{max-width:max(calc(var(--w)*var(--escala)*1px),340px);margin-bottom:8px}
.lienzo{width:calc(var(--w)*var(--escala)*1px);height:calc(var(--h)*var(--escala)*1px);overflow:hidden;border-radius:4px;outline:1px solid var(--linea);background:#000}
.lienzo iframe{display:block;border:0;width:calc(var(--w)*1px);height:calc(var(--h)*1px);transform:scale(var(--escala));transform-origin:0 0;background:#fff}
#volver{display:none}
body.solo{--escala:1}
body.solo .barra,body.solo section:not(#fotogramas),body.solo #fotogramas>:not(.galeria),body.solo .marco:not(.elegido),body.solo .marco header{display:none}
body.solo main{padding:0}
body.solo section{margin:0}
body.solo .lienzo{border-radius:0;outline:0}
body.solo #volver{display:block;padding:10px 14px;font-size:12px;color:var(--tinta2)}
`;

const EJECUTAR = `(() => {
  const uno = (s, r) => (r || document).querySelector(s);
  const todos = (s, r) => Array.from((r || document).querySelectorAll(s));
  const css = {};
  for (const s of todos('script[data-df-css]')) css[s.getAttribute('data-df-css')] = s.textContent;
  const recursos = JSON.parse(uno('#df-recursos').textContent);
  const restaurar = uno('#df-restaurar').textContent;
  const marcos = todos('article.marco');

  // El HTML de un fotograma, entero: su HTML guardado, con la hoja de estilo de la app en su
  // sitio, sus imagenes y, al final, lo poco que corre dentro (df-restaurar).
  function componer(id) {
    let html = uno('script[data-df-marco="' + id + '"]').textContent;
    html = html.replace(/<style data-df-css="([^"]+)"><\\/style>/g, (t, n) => '<style data-df-css="' + n + '">' + css[n] + '</style>');
    html = html.replace(/df-recurso:(h[0-9a-f]{12})/g, (t, h) => recursos[h] || t);
    const fin = html.lastIndexOf('</body>');
    return html.slice(0, fin) + '<script>' + restaurar + '</' + 'script>' + html.slice(fin);
  }
  function cargar(art) {
    if (art.dataset.cargado) return;
    art.dataset.cargado = '1';
    uno('iframe', art).srcdoc = componer(art.dataset.id);
  }
  function descargar(art) {
    if (!art.dataset.cargado) return;
    delete art.dataset.cargado;
    uno('iframe', art).removeAttribute('srcdoc');
  }
  // Un fotograma se monta al acercarse a la ventana y se suelta al alejarse.
  const ojo = new IntersectionObserver((entradas) => {
    for (const e of entradas) (e.isIntersecting ? cargar : descargar)(e.target);
  }, { rootMargin: '900px 0px' });
  for (const art of marcos) ojo.observe(art);

  // El indice: por tema y por ancho.
  const filtro = { tema: 'todos', ancho: 'todos' };
  function aplicar() {
    let n = 0;
    const solo = /^#solo=(.+)$/.exec(location.hash);
    document.body.classList.toggle('solo', Boolean(solo));
    for (const art of marcos) {
      const elegido = solo ? art.dataset.id === decodeURIComponent(solo[1]) : (filtro.tema === 'todos' || art.dataset.tema === filtro.tema) && (filtro.ancho === 'todos' || art.dataset.ancho === filtro.ancho);
      art.hidden = !elegido;
      art.classList.toggle('elegido', Boolean(solo) && elegido);
      if (elegido) n += 1;
      if (solo && elegido) cargar(art);
    }
    uno('#cuenta').textContent = n + ' de ' + marcos.length + ' fotogramas';
    for (const b of todos('button[data-filtro]')) b.setAttribute('aria-pressed', String(filtro[b.dataset.filtro] === b.dataset.valor));
    for (const b of todos('button[data-escala]')) b.setAttribute('aria-pressed', String(getComputedStyle(document.documentElement).getPropertyValue('--escala').trim() === b.dataset.escala));
    if (solo) window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }
  document.addEventListener('click', (e) => {
    const b = e.target instanceof Element ? e.target.closest('button[data-filtro],button[data-escala],a[data-ir]') : null;
    if (!b) return;
    if (b.dataset.filtro) filtro[b.dataset.filtro] = b.dataset.valor;
    else if (b.dataset.escala) document.documentElement.style.setProperty('--escala', b.dataset.escala);
    else {
      // Un enlace del indice: que su fotograma se vea aunque el filtro lo esconda.
      const art = document.getElementById('m-' + b.dataset.ir);
      if (art && art.hidden) { filtro.tema = 'todos'; filtro.ancho = 'todos'; }
    }
    aplicar();
  });
  addEventListener('hashchange', aplicar);
  aplicar();
  document.documentElement.setAttribute('data-df-listo', '1');
})();`;

const boton = (filtro, valor, texto) => `<button type="button" data-filtro="${filtro}" data-valor="${valor}" aria-pressed="false">${texto}</button>`;
const documento = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>BMS Finance · fichero de diseño</title>
<style>${ESTILO}</style>
</head>
<body>
<div class="barra">
<h1>BMS Finance · fichero de diseño</h1>
<nav><a href="#colores">Colores</a><a href="#letra">Letra</a><a href="#indice">Índice</a><a href="#fotogramas">Fotogramas</a></nav>
<div class="grupo" role="group" aria-label="Tema"><span>Tema</span>${boton('tema', 'todos', 'Todos')}${temas.map((t) => boton('tema', t, NOMBRE_TEMA[t][0].toUpperCase() + NOMBRE_TEMA[t].slice(1))).join('')}</div>
<div class="grupo" role="group" aria-label="Ancho"><span>Ancho</span>${boton('ancho', 'todos', 'Todos')}${anchos.map((a) => boton('ancho', a, `${a} px`)).join('')}</div>
<div class="grupo" role="group" aria-label="Escala"><span>Escala</span>${[['.25', '25 %'], ['.5', '50 %'], ['1', '100 %']].map(([v, t]) => `<button type="button" data-escala="${v}" aria-pressed="false">${t}</button>`).join('')}</div>
<span id="cuenta"></span>
</div>
<main>
<section id="presentacion">
<h2>Las pantallas de la app, paradas</h2>
<p class="nota">${estados.length} estados de BMS Finance en neerlandés, cada uno a ${anchos.join(' y a ')} px y en los temas ${temas.map((t) => NOMBRE_TEMA[t]).join(' y ')}: ${marcos.length} fotogramas. Cada fotograma es el DOM de verdad de la app con su hoja de estilo de verdad, dentro de su propio marco: el texto se selecciona y los estilos se inspeccionan (clic derecho › Inspeccionar). Cada <code>&lt;canvas&gt;</code> (el orbe, las carpetas, la suricata) sigue en su sitio, parado, con una imagen de lo que enseñaba como fondo. Las animaciones están en pausa en el punto en que se tomó el fotograma.</p>
<p class="datos">Capturado el ${fecha} de <code>${esc((indice.repo?.commit ?? '').slice(0, 12) || '—')}</code> (la app construida: <code>${esc((indice.repo?.fuente ?? '').slice(0, 12) || '—')}</code>) con Chromium ${esc(indice.navegador ?? '')} · sin red, sin dependencias: este fichero lo lleva todo.</p>
</section>
<section id="colores">
<h2>Colores</h2>
<p class="nota">Leídos de la hoja de estilo que sirve la app (${tk.total} propiedades que valen un color) y resueltos por el navegador en cada tema. Debajo, los colores que de verdad pintan los ${marcos.length} fotogramas.</p>
${tk.html}
<h3>Colores en uso</h3>
<p class="nota">Lo que el navegador calcula en lo que se ve de los fotogramas (el color del texto, los fondos y los bordes), con cuántos elementos lo llevan y un ejemplo. Los dieciocho más usados de cada clase.</p>
<div class="dos">${temas.map((t) => `<div><h3>Tema ${NOMBRE_TEMA[t]}</h3><div class="usos">${tablaUso(t)}</div></div>`).join('')}</div>
</section>
<section id="letra">
<h2>Escala de letra</h2>
<p class="nota">Los ${letra.cuerpos} cuerpos que usan los fotogramas, de mayor a menor, con la familia que pide la hoja (<code>Inter, "Segoe UI", sans-serif</code> y la monoespaciada del sistema: la app no trae ficheros de letra), sus pesos, interlineados y espaciados, y una muestra con el estilo más usado de cada uno.</p>
${letra.html}
</section>
<section id="indice">
<h2>Índice</h2>
<p class="nota">Cada estado, con sus fotogramas. Los botones de arriba dejan solo un tema o un ancho.</p>
<ol class="indice">
${indiceHtml}
</ol>
</section>
<section id="fotogramas">
<h2>Fotogramas</h2>
<div class="galeria">
${marcosHtml}
</div>
<p id="volver"><a href="#fotogramas">← Volver a todos los fotogramas</a></p>
</section>
</main>
${Object.entries(hojas).map(([nombre, css]) => `<script type="text/plain" data-df-css="${nombre}">${css}</script>`).join('\n')}
<script type="application/json" id="df-recursos">${JSON.stringify(recursos).replace(/</g, '\\u003c')}</script>
<script type="text/plain" id="df-restaurar">${sinCierre(RESTAURAR, 'df-restaurar')}</script>
${marcos.map((m) => `<script type="text/plain" data-df-marco="${m.id}">${m.html}</script>`).join('\n')}
<script>${EJECUTAR}</script>
</body>
</html>
`;

mkdirSync(dirname(salida), { recursive: true });
writeFileSync(salida, documento);
const bytes = Buffer.byteLength(documento);
const resumen = {
  fichero: salida,
  bytes,
  marcos: marcos.length,
  estados: estados.length,
  recursos: Object.keys(recursos).length,
  bytesRecursos: Object.values(recursos).reduce((n, u) => n + u.length, 0),
  bytesHojas: Object.values(hojas).reduce((n, u) => n + u.length, 0),
  bytesMarcos: marcos.reduce((n, m) => n + m.html.length, 0),
  tokens: tk.total,
  cuerpos: letra.cuerpos,
};
writeFileSync(join(dirname(salida), 'montaje.json'), JSON.stringify(resumen, null, 1));
console.log(JSON.stringify(resumen));
if (bytes > 12 * 1024 * 1024) {
  console.log('MAL: pasa de 12 MB');
  process.exit(1);
}
