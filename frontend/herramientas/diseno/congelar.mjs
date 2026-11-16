// congelar.mjs — parar la pantalla de la app y sacar de ella un fotograma: el DOM de verdad tal
// como esta (con lo que no va en los atributos: lo escrito en los campos, los desplazamientos,
// las hojas modales, por donde van las animaciones) y, de cada <canvas>, una imagen de lo que
// ensenaba. Las tres funciones de aqui corren DENTRO de la pagina (page.addInitScript y
// page.evaluate): no usan nada de fuera de si mismas.

/**
 * Antes de que cargue la app (addInitScript): `window.__df.parar()` deja de dar cuadros de
 * animacion a la app (los <canvas> se quedan en su ultimo dibujo) y pone en pausa las
 * animaciones de CSS; `seguir()` lo suelta todo. El WebGL del orbe guarda su dibujo
 * (preserveDrawingBuffer) para poder leerlo despues; el dibujo es el mismo (un triangulo que
 * cubre el lienzo entero en cada cuadro).
 */
export function INICIO() {
  if (window.__df) return;
  const raf = window.requestAnimationFrame.bind(window);
  const caf = window.cancelAnimationFrame.bind(window);
  let parado = false;
  let n = 0;
  let pausadas = [];
  const aplazados = new Map();
  const reales = new Map();
  const pedir = (id, cb) =>
    reales.set(
      id,
      raf((t) => {
        reales.delete(id);
        if (parado) aplazados.set(id, cb);
        else cb(t);
      })
    );
  window.requestAnimationFrame = (cb) => {
    n += 1;
    if (parado) aplazados.set(n, cb);
    else pedir(n, cb);
    return n;
  };
  window.cancelAnimationFrame = (id) => {
    aplazados.delete(id);
    const real = reales.get(id);
    if (real !== undefined) {
      caf(real);
      reales.delete(id);
    }
  };
  const getContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (tipo, atributos) {
    if (/webgl/i.test(String(tipo))) return getContext.call(this, tipo, { ...(atributos ?? {}), preserveDrawingBuffer: true });
    return getContext.call(this, tipo, atributos);
  };
  const cuadros = (k) => new Promise((ok) => {
    const paso = (i) => (i <= 0 ? ok() : raf(() => paso(i - 1)));
    paso(k);
  });
  window.__df = {
    async parar() {
      parado = true;
      pausadas = document.getAnimations().filter((a) => a.playState === 'running');
      for (const a of pausadas) a.pause();
      // Dos cuadros de verdad: lo ultimo dibujado ya esta en la pantalla.
      await cuadros(2);
    },
    seguir() {
      for (const a of pausadas) {
        try {
          a.play();
        } catch {
          // La animacion ya no existe.
        }
      }
      pausadas = [];
      parado = false;
      const cola = [...aplazados];
      aplazados.clear();
      for (const [id, cb] of cola) pedir(id, cb);
    },
  };
}

/** Una firma barata de lo que se ve, para saber si cambio entre el DOM y la foto. */
export function FIRMA() {
  const r = document.documentElement;
  return [r.querySelectorAll('*').length, r.outerHTML.length, window.scrollX, window.scrollY].join(':');
}

/**
 * El fotograma: una copia del documento con todo lo que hace falta para que, sola y sin la app,
 * se vea igual. Devuelve { html, hojas (las direcciones de las hojas de estilo, en su orden),
 * recursos (lo que ensenaba cada canvas y las imagenes grandes de los atributos, como data:), tipos (los estilos de texto que se usan),
 * colores (los colores que se usan), avisos, datos }.
 */
export function SERIALIZAR() {
  const doc = document;
  const raiz = doc.documentElement;
  const clon = raiz.cloneNode(true);
  const o = [raiz, ...raiz.querySelectorAll('*')];
  const c = [clon, ...clon.querySelectorAll('*')];
  if (o.length !== c.length) throw new Error('la copia del documento no casa con el original');
  const avisos = [];
  const hojas = [];
  const recursos = [];
  const grandes = [];
  let canvas = 0;
  const quitar = [];
  const reglas = [];
  const tipos = {};
  const colores = {};
  const contar = (mapa, clave, muestra) => {
    const e = (mapa[clave] ??= { n: 0, muestra });
    e.n += 1;
  };

  // Las animaciones de CSS vivas, por elemento y pseudoelemento.
  const vivas = new Map();
  for (const a of doc.getAnimations()) {
    const destino = a.effect?.target;
    if (!destino || typeof a.animationName !== 'string') continue;
    const pseudo = a.effect.pseudoElement ?? '';
    if (!vivas.has(destino)) vivas.set(destino, {});
    (vivas.get(destino)[pseudo] ??= []).push(a);
  }
  let animados = 0;
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  for (let i = 0; i < o.length; i += 1) {
    const a = o[i];
    const b = c[i];
    const tag = a.localName;
    if (tag === 'script' || tag === 'noscript' || tag === 'base' || (tag === 'meta' && a.httpEquiv) || (tag === 'link' && a.rel !== 'stylesheet')) {
      quitar.push(b);
      continue;
    }
    if (tag === 'link') {
      const estilo = doc.createElement('style');
      estilo.setAttribute('data-df-css', String(hojas.length));
      hojas.push(a.href);
      b.replaceWith(estilo);
      continue;
    }
    if (tag === 'style') {
      if (a.sheet && !a.textContent.trim() && a.sheet.cssRules.length) b.textContent = [...a.sheet.cssRules].map((r) => r.cssText).join('\n');
      continue;
    }
    if (tag === 'head' || tag === 'title' || tag === 'meta') continue;
    if (tag === 'iframe' || tag === 'object' || tag === 'embed' || tag === 'video' || tag === 'audio') avisos.push(`<${tag}> sin tratar`);
    if (tag === 'img' && !/^data:/.test(a.getAttribute('src') ?? '')) avisos.push(`<img src=${a.getAttribute('src')}> sin tratar`);
    const cs = getComputedStyle(a);
    if (tag === 'canvas') {
      // Lo que ensenaba: PNG si es pequeno; si no, WebP (las texturas de las carpetas pesan
      // diez veces menos y no se nota).
      let url = '';
      try {
        url = a.toDataURL('image/png');
        if (url.length > 16_000) {
          const webp = a.toDataURL('image/webp', 0.92);
          if (webp.startsWith('data:image/webp') && webp.length < url.length) url = webp;
        }
      } catch (error) {
        avisos.push(`canvas.${a.className}: ${error.message}`);
      }
      if (cs.backgroundImage !== 'none') avisos.push(`canvas.${a.className} ya tiene fondo`);
      b.setAttribute('data-df-canvas', `${a.width}x${a.height}`);
      b.style.setProperty('background-image', `url("df-recurso:${recursos.length}")`);
      b.style.setProperty('background-size', '100% 100%');
      b.style.setProperty('background-repeat', 'no-repeat');
      b.style.setProperty('background-origin', 'content-box');
      b.style.setProperty('background-clip', 'content-box');
      recursos.push(url);
      canvas += 1;
    } else if (tag === 'input') {
      if (a.type === 'checkbox' || a.type === 'radio') {
        if (a.checked) b.setAttribute('checked', '');
        else b.removeAttribute('checked');
      } else if (a.type !== 'password' && a.type !== 'file') b.setAttribute('value', a.value);
    } else if (tag === 'textarea') b.textContent = a.value;
    else if (tag === 'option') {
      if (a.selected) b.setAttribute('selected', '');
      else b.removeAttribute('selected');
    } else if (tag === 'dialog' && a.open && a.matches(':modal')) b.setAttribute('data-df-modal', '');
    try {
      if (a.matches(':popover-open')) b.setAttribute('data-df-popover', '');
    } catch {
      // Un navegador sin popover.
    }
    if (a.scrollTop || a.scrollLeft) b.setAttribute('data-df-scroll', `${a.scrollLeft},${a.scrollTop}`);
    if (a === doc.activeElement && a !== doc.body && a.matches(':focus-visible')) b.setAttribute('data-df-foco', '');
    if (/url\(\s*(?!["']?(?:data:|df-recurso:|#))/.test(b.getAttribute('style') ?? '')) avisos.push(`<${tag}> con url() en su style`);
    // Una imagen grande dentro de un atributo (el logotipo): va una vez a los recursos del
    // fichero. Se cambia despues, en el texto: tocar el atributo de la copia haria que el
    // navegador intentase cargarla.
    for (const atributo of ['href', 'src', 'xlink:href']) {
      const valor = a.getAttribute(atributo);
      if (valor && valor.startsWith('data:') && valor.length > 2000 && !/[&<>"]/.test(valor) && !grandes.includes(valor)) grandes.push(valor);
    }

    // Por donde va cada animacion de CSS: en el fotograma se queda parada ahi mismo (un retraso
    // negativo y en pausa). La que ya acabo sin dejar nada, se da por acabada.
    for (const pseudo of ['', '::before', '::after']) {
      const estilo = pseudo ? getComputedStyle(a, pseudo) : cs;
      if (!estilo.animationName || estilo.animationName === 'none') continue;
      if (pseudo && (estilo.content === 'none' || estilo.content === 'normal')) continue;
      const lista = [...(vivas.get(a)?.[pseudo] ?? [])];
      const retrasos = estilo.animationName.split(',').map((nombre) => {
        const k = lista.findIndex((x) => x.animationName === nombre.trim());
        if (k < 0) return '-99999s';
        const [x] = lista.splice(k, 1);
        const retraso = Number(x.effect.getTiming().delay) - Number(x.currentTime ?? 0);
        return `${Math.round(retraso * 100) / 100}ms`;
      });
      if (!b.hasAttribute('data-df-anim')) {
        animados += 1;
        b.setAttribute('data-df-anim', String(animados));
      }
      reglas.push(`[data-df-anim="${b.getAttribute('data-df-anim')}"]${pseudo}{animation-delay:${retrasos.join(',')}!important}`);
    }

    // Lo que se usa de verdad: los estilos de texto y los colores de lo que se ve.
    if (cs.display !== 'none' && cs.visibility !== 'hidden' && visible(a)) {
      const texto = [...a.childNodes].filter((x) => x.nodeType === 3).map((x) => x.textContent.trim()).join(' ').trim();
      if (texto) {
        const clave = [cs.fontFamily, cs.fontSize, cs.fontWeight, cs.lineHeight, cs.letterSpacing, cs.textTransform].join('|');
        contar(tipos, clave, texto.slice(0, 40));
        contar(colores, `texto|${cs.color}`, texto.slice(0, 24));
      }
      if (cs.backgroundColor !== 'rgba(0, 0, 0, 0)') contar(colores, `fondo|${cs.backgroundColor}`, `${tag}.${String(a.className?.baseVal ?? a.className).split(' ')[0]}`);
      if (cs.borderTopWidth !== '0px' && cs.borderTopStyle !== 'none') contar(colores, `borde|${cs.borderTopColor}`, `${tag}.${String(a.className?.baseVal ?? a.className).split(' ')[0]}`);
    }
  }
  for (const q of quitar) q.remove();
  const paseo = doc.createTreeWalker(clon, NodeFilter.SHOW_COMMENT);
  const comentarios = [];
  while (paseo.nextNode()) comentarios.push(paseo.currentNode);
  for (const q of comentarios) q.remove();
  if (doc.adoptedStyleSheets?.length) avisos.push('hay adoptedStyleSheets');

  const fijo = doc.createElement('style');
  fijo.setAttribute('data-df-fijo', '');
  fijo.textContent = ['*,*::before,*::after{animation-play-state:paused!important}', ...reglas].join('\n');
  clon.querySelector('head').append(fijo);

  let html = `<!doctype html>\n${clon.outerHTML}`;
  for (const valor of grandes) {
    html = html.split(valor).join(`df-recurso:${recursos.length}`);
    recursos.push(valor);
  }
  if (/<script|<!--/i.test(html)) avisos.push('el fotograma lleva <script o <!--');
  return {
    html,
    hojas,
    recursos,
    tipos,
    colores,
    avisos,
    datos: {
      elementos: o.length,
      texto: (doc.body.innerText ?? '').trim().length,
      canvas,
      animados,
      desplazado: clon.querySelectorAll('[data-df-scroll]').length,
      modal: clon.querySelectorAll('[data-df-modal]').length,
      idioma: raiz.lang,
      oscuro: raiz.classList.contains('dark'),
      ventana: [window.innerWidth, window.innerHeight],
    },
  };
}

/**
 * Lo que va DENTRO de cada fotograma al montarlo (lo unico que corre en el): lo que el HTML
 * solo no puede decir. Abre las hojas modales como modales (su velo y su capa), pone cada
 * desplazamiento en su sitio y el foco donde estaba, y no deja que un enlace se lleve el marco.
 */
export const RESTAURAR = `(() => {
  const d = document;
  for (const el of d.querySelectorAll('dialog[data-df-modal]')) { el.removeAttribute('open'); try { el.showModal(); } catch (e) { el.setAttribute('open', ''); } }
  for (const el of d.querySelectorAll('[data-df-popover]')) { try { el.showPopover(); } catch (e) {} }
  const foco = d.querySelector('[data-df-foco]');
  if (foco) { try { foco.focus({ preventScroll: true }); } catch (e) {} }
  else if (d.activeElement && d.activeElement !== d.body) d.activeElement.blur();
  for (const el of d.querySelectorAll('[data-df-scroll]')) {
    const p = el.getAttribute('data-df-scroll').split(',').map(Number);
    el.scrollTo({ left: p[0], top: p[1], behavior: 'instant' });
  }
  d.addEventListener('click', (e) => { if (e.target instanceof Element && e.target.closest('a[href], button[type=submit]')) e.preventDefault(); }, true);
  d.addEventListener('submit', (e) => e.preventDefault(), true);
  d.documentElement.setAttribute('data-df-listo', '1');
})();`;

/**
 * Los colores con nombre de la hoja de estilo de verdad (las propiedades --… que valen un
 * color) y lo que valen en el tema que se ve. Corre en la pagina.
 */
export function TOKENS() {
  const nombres = new Map();
  const mirar = (reglas) => {
    for (const r of reglas) {
      if (r.cssRules?.length && !(r instanceof CSSStyleRule)) mirar(r.cssRules);
      if (!(r instanceof CSSStyleRule)) continue;
      if (r.cssRules?.length) mirar(r.cssRules);
      for (const p of r.style) {
        if (!p.startsWith('--')) continue;
        const e = nombres.get(p) ?? { donde: [] };
        if (!e.donde.includes(r.selectorText) && e.donde.length < 4) e.donde.push(r.selectorText);
        nombres.set(p, e);
      }
    }
  };
  for (const hoja of document.styleSheets) {
    try {
      mirar(hoja.cssRules);
    } catch {
      // Una hoja de otro origen: no hay.
    }
  }
  const sonda = document.createElement('i');
  sonda.style.cssText = 'position:absolute;width:0;height:0;visibility:hidden';
  (document.querySelector('[data-aurora-root] .app') ?? document.body).append(sonda);
  const salida = [];
  for (const [nombre, e] of nombres) {
    let en = document.documentElement;
    for (const s of e.donde) {
      try {
        const el = document.querySelector(s.split(',')[0]);
        if (el && getComputedStyle(el).getPropertyValue(nombre).trim()) {
          en = el;
          break;
        }
      } catch {
        // Un selector que querySelector no entiende.
      }
    }
    const valor = getComputedStyle(en).getPropertyValue(nombre).trim();
    // Las propiedades internas de Tailwind (--tw-*) no son colores de diseno.
    if (!valor || nombre.startsWith('--tw-')) continue;
    // Solo lo que es un color: lo dice el navegador.
    if (!CSS.supports('color', valor)) {
      if (/^(--text-|--font-|--tracking-|--leading-|--radius|--spacing|--default-font|--default-mono)/.test(nombre)) salida.push({ nombre, valor, donde: e.donde, clase: 'otro' });
      continue;
    }
    sonda.style.color = '';
    sonda.style.color = valor;
    salida.push({ nombre, valor, color: getComputedStyle(sonda).color, donde: e.donde, clase: 'color' });
  }
  sonda.remove();
  return salida;
}
