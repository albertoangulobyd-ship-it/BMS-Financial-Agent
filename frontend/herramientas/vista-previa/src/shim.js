// El shim de la vista previa. Se carga ANTES que la app (src/entrada.js) y cambia tres cosas de
// la pagina, nada de la app:
//
// 1. fetch: la app solo habla con /api/v2 de su propio origen (frontend/src/lib/api.ts). Aqui no
//    hay servidor: cada GET se contesta con lo que grabo grabar.mjs del servidor de verdad sobre
//    la base de prueba (grabacion.json, `respuestas`, por ruta y consulta con los parametros en
//    orden). Lo demas:
//    - sin X-BMS-Token: 401 sin_token, como el servidor (la entrada acepta cualquier codigo);
//    - lo que no es GET (una orden, subir un fichero): 409 con el codigo vista_previa, y el
//      aviso de la pagina (#vp-aviso) siete segundos. Nada se guarda;
//    - una descarga (el original de una factura o de un documento, la hoja del btw en CSV): 409
//      con el codigo vista_previa_descarga;
//    - un GET que no se grabo: 404 no_grabado (y se apunta en window.__vpSinGrabar, que mira
//      comprobar.mjs);
//    - lo que no es /api/: falla como falla la red (aqui no hay red).
// 2. Date: «ahora» es el momento de la grabacion (mas lo que lleve abierta la pagina), para que
//    «hoy», «vence en 3 dias» o la semana del calendario digan lo mismo que los datos.
// 3. La lectura de Procesar: /api/v2/lectura contesta, con el boton de la nota de arriba, la
//    leesronde que se grabo (grabacion.json, `lectura.pasos`, cada uno con sus ms): la app la
//    sigue como sigue una de verdad. Al salir de Procesar, se acaba.
//
// Sin dependencias y sin tocar el DOM mas que sus propios elementos (vp-*, src/cuerpo.html).
import grabacion from '@vp/grabacion';
import { crearContestador, rutaDe } from './rutas.js';
import { TEXTOS_VP } from './textos-vp.js';

const datos = grabacion;
// Que se contesta a cada peticion (src/rutas.js, sin tocar la pagina: lo prueba vitest).
const contestador = crearContestador(datos);

// ------------------------------------------------------------------ el reloj

const Reloj = Date;
const desfase = Reloj.parse(datos.grabado) - Reloj.now();
if (Number.isFinite(desfase) && Math.abs(desfase) > 60_000) {
  class Fecha extends Reloj {
    constructor(...args) {
      if (args.length === 0) super(Reloj.now() + desfase);
      else super(...args);
    }
    static now() {
      return Reloj.now() + desfase;
    }
  }
  globalThis.Date = Fecha;
}

// ------------------------------------------------------------------ la lectura grabada

const pasos = datos.lectura?.pasos ?? [];
let opname = null;

function hayOpname() {
  return pasos.length > 1;
}

/** Empieza un segundo antes de que la lectura este pedida. */
function empezarOpname() {
  if (hayOpname()) opname = { inicio: Reloj.now() - Math.max(0, (pasos[1]?.ms ?? 0) - 1000) };
}

function pararOpname() {
  opname = null;
}

/** El paso que toca ahora: el ultimo cuyo momento ya paso. */
function pasoDeAhora() {
  if (!opname) return null;
  const van = Reloj.now() - opname.inicio;
  let paso = null;
  for (const p of pasos) if (p.ms <= van) paso = p;
  return paso ?? pasos[0] ?? null;
}

// ------------------------------------------------------------------ las respuestas

function respuesta(estado, cuerpo, contrato) {
  const headers = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-BMS-Entorno': 'demo' };
  if (contrato) headers['X-BMS-Contrato'] = contrato;
  return new Response(JSON.stringify(cuerpo), { status: estado, headers });
}

function sinGrabar(k) {
  if (typeof window === 'undefined') return;
  (window.__vpSinGrabar ??= []).push(k);
}

function contestar(url, metodo, token) {
  const r = contestador(url, metodo, token, pasoDeAhora);
  if (r.aviso) avisar();
  if (r.sinGrabar) sinGrabar(r.sinGrabar);
  return respuesta(r.estado, r.cuerpo, r.contrato);
}

// Un instante por respuesta: la app pinta su «cargando» como con un servidor, y lo que espera a
// que no quede nada en camino (comprobar.mjs) lo ve en window.__vpPendientes.
const instante = () => new Promise((r) => setTimeout(r, 25));
const pendientes = (n) => {
  if (typeof window !== 'undefined') window.__vpPendientes = Math.max(0, (window.__vpPendientes ?? 0) + n);
};

const fetchGrabado = async (input, init) => {
  const url = rutaDe(input);
  if (!url.startsWith('/api/')) {
    await instante();
    throw new TypeError('Failed to fetch (vista previa: sin red · preview: no network)');
  }
  const peticion = input instanceof Request ? input : null;
  const metodo = (init?.method ?? peticion?.method ?? 'GET').toUpperCase();
  const headers = new Headers(init?.headers ?? peticion?.headers ?? undefined);
  pendientes(1);
  try {
    await instante();
    return contestar(url, metodo, headers.get('X-BMS-Token'));
  } finally {
    pendientes(-1);
  }
};

// ------------------------------------------------------------------ la pagina

let relojAviso;

/** El aviso de que una orden no se guarda, en el idioma que se ve, siete segundos. */
function avisar() {
  if (typeof document === 'undefined') return;
  const aviso = document.getElementById('vp-aviso');
  if (!aviso) return;
  const idioma = document.documentElement.lang;
  aviso.textContent = (TEXTOS_VP[idioma] ?? TEXTOS_VP.nl).vista_previa;
  aviso.hidden = false;
  clearTimeout(relojAviso);
  relojAviso = setTimeout(() => {
    aviso.hidden = true;
  }, 7000);
}

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  window.fetch = fetchGrabado;
  const boton = document.getElementById('vp-opname-boton');
  const banda = document.getElementById('vp-opname');
  boton?.addEventListener('click', () => {
    empezarOpname();
    if (banda) banda.hidden = false;
  });
  // La nota dice «escribe cualquier codigo» solo en la entrada; el boton de la opname solo esta
  // con Procesar abierto, y al salir de Procesar la opname se acaba.
  const mirar = () => {
    const nota = document.getElementById('vp-nota');
    if (nota) nota.classList.toggle('vp-nota--entrada', document.getElementById('token') !== null);
    const enProcesar = document.querySelector('.processing-workspace') !== null;
    if (boton) boton.hidden = !(enProcesar && hayOpname());
    if (!enProcesar && opname) {
      pararOpname();
      if (banda) banda.hidden = true;
    }
  };
  const raiz = document.getElementById('root');
  if (raiz) new MutationObserver(mirar).observe(raiz, { childList: true, subtree: true });
}
