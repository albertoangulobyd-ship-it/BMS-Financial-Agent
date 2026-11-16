#!/usr/bin/env node
// grabar.mjs — graba las respuestas de /api/v2 con las que vive la vista previa.
//
//   node grabar.mjs [--repo <ruta del repo>] [--salida grabacion/grabacion.json] [--hoy AAAA-MM-DD]
//
// --repo es por defecto el repo que lleva esta carpeta.
// Como e2e/global-setup.ts del repo: una base de prueba recien hecha (scripts/crear_demo_e2e.py)
// en una carpeta temporal de AQUI (.trabajo/), y el servidor de verdad (bms-agent serve) sobre
// ella en un puerto libre. Del repo solo se lee (PYTHONDONTWRITEBYTECODE: ni un .pyc).
// Despues, cuatro cosas:
//   1. La gira (gira.mjs) por la app de verdad como Ana Demo, entera en neerlandes y las
//      pantallas principales en espanol y en ingles: cada respuesta GET de /api/v2 se guarda
//      (origen "app").
//   2. El cierre: lo que la gira pidio de UNA factura, empresa, Object, orden de compra, trimestre
//      o documento se pide de TODOS (origen "directa"); la busqueda, con cada empresa y cada clase
//      de documento; y la busqueda por texto, con lo que se escribe en la caja: cada numero de
//      factura, cada empresa, Object y orden de compra, y cada nombre de la rueda y de los
//      paneles en los tres idiomas. Lo que el servidor contesta sin JSON (un PDF, un CSV) no se
//      guarda: va a `descargas` (la vista previa dice que ahi no se descarga).
//   3. La lectura de Procesar: se pide como la pide la app, y scripts/simular_lector.py (el
//      lector de las pruebas del repo) da sus pasos sobre la misma base; se guarda lo que va
//      contestando /api/v2/lectura, con sus milisegundos (`lectura.pasos`).
//   4. Las bandas que el servidor pone en /app (DATOS DE PRUEBA), a grabacion/pagina.json.
import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { GRABACION, TRABAJO, argumentos, clave, espera, falla, navegador, python, repoDe } from './comun.mjs';
import { ENTRADAS_PANEL, IDIOMAS, PREGUNTA_RESUMEN, abrirRueda, entrar, gira, ponerIdioma, ponerTema, salir, titulosPanel, titulosRueda } from './gira.mjs';

const args = argumentos();
const { repo, frontend } = repoDe(args);
const salida = resolve(typeof args.salida === 'string' ? args.salida : GRABACION);
const py = python(repo);
const t0 = Date.now();
const dice = (texto) => console.log(`[${String(Math.round((Date.now() - t0) / 1000)).padStart(4)} s] ${texto}`);

// ------------------------------------------------------------------ la base y el servidor

mkdirSync(TRABAJO, { recursive: true });
const trabajo = mkdtempSync(join(TRABAJO, 'grabar-'));
const env = { ...process.env, PYTHONPATH: join(repo, 'src'), PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' };
delete env.BMS_DB;
const dia = typeof args.hoy === 'string' ? ['--hoy', args.hoy] : [];
const creada = spawnSync(py, [join(repo, 'scripts', 'crear_demo_e2e.py'), '--carpeta', join(trabajo, 'datos'), ...dia], { cwd: trabajo, env, encoding: 'utf8' });
if (creada.status !== 0) {
  // Sin dejar nada en .trabajo/ y sin la traza de Node: lo que dijo el Python.
  rmSync(trabajo, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
  falla(`no se ha podido crear la base de prueba con ${py}:\n${`${creada.stdout ?? ''}\n${creada.stderr ?? ''}`.trim() || creada.error?.message}`);
}
const demo = JSON.parse(creada.stdout.trim().split('\n').pop());
env.BMS_DB = demo.db;

const puerto = await new Promise((ok, mal) => {
  const s = createServer();
  s.once('error', mal);
  s.listen(0, '127.0.0.1', () => {
    const p = s.address().port;
    s.close(() => ok(p));
  });
});
let registro = '';
const servidor = spawn(py, ['-m', 'bms_agent.cli', 'serve', '--db', demo.db, '--puerto', String(puerto), '--facturas', join(trabajo, 'facturas'), '--out', join(trabajo, 'out')], {
  cwd: trabajo,
  env,
  stdio: ['ignore', 'pipe', 'pipe'],
});
servidor.stdout.on('data', (c) => (registro += c));
servidor.stderr.on('data', (c) => (registro += c));
const base = `http://127.0.0.1:${puerto}`;
const token = demo.tokens['Ana Demo'];

let codigoDeSalida = 1;
async function limpiar() {
  servidor.kill();
  await espera(300);
  // En Windows la base puede seguir abierta un momento despues de parar el servidor.
  rmSync(trabajo, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
}

try {
  for (let i = 0; ; i += 1) {
    if (servidor.exitCode !== null || i > 240) {
      // Como en diseno/comun.mjs: limpia .trabajo/ y lo que dijo el servidor, sin la traza de Node
      // (falla() sale con process.exit, que no pasa por el finally de abajo).
      await limpiar();
      falla(`bms-agent serve ${servidor.exitCode !== null ? 'se ha parado' : `no contesta en ${base}`}:\n${registro}`);
    }
    try {
      if ((await fetch(`${base}/app`)).status === 200) break;
    } catch {
      // Aun no escucha.
    }
    await espera(250);
  }
  dice(`servidor en ${base} sobre ${demo.db}`);

  // ---------------------------------------------------------------- 1. la gira

  const respuestas = {};
  const descargas = new Set();
  let contrato = null;
  let entorno = 'demo';
  let fase = 'gira';
  const deLaBusqueda = new Set();

  function guardar(k, estado, cabeceras, cuerpo, origen) {
    contrato = cabeceras.contrato ?? contrato;
    entorno = cabeceras.entorno ?? entorno;
    // Lo primero que se vio de cada cosa: la gira va antes que la lectura, que cambia la base.
    if (respuestas[k] && fase !== 'gira') return;
    respuestas[k] = { estado, entorno: cabeceras.entorno ?? entorno, contrato: cabeceras.contrato ?? contrato, origen, cuerpo };
  }

  const { browser } = await navegador(frontend);
  const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: 'nl-NL', timezoneId: 'Europe/Amsterdam', colorScheme: 'dark', serviceWorkers: 'block' });
  const pagina = await contexto.newPage();
  let enCamino = 0;
  const errores = [];
  pagina.on('console', (m) => m.type() === 'error' && errores.push(m.text().slice(0, 200)));
  pagina.on('pageerror', (e) => errores.push(String(e.message).slice(0, 200)));
  const esApi = (url) => new URL(url).pathname.startsWith('/api/');
  pagina.on('request', (r) => esApi(r.url()) && (enCamino += 1));
  pagina.on('requestfailed', (r) => esApi(r.url()) && (enCamino = Math.max(0, enCamino - 1)));
  pagina.on('requestfinished', (r) => esApi(r.url()) && (enCamino = Math.max(0, enCamino - 1)));
  const leyendo = [];
  pagina.on('response', (r) => {
    const url = new URL(r.url());
    if (!url.pathname.startsWith('/api/') || r.request().method() !== 'GET' || fase !== 'gira') return;
    const k = clave(url.pathname + url.search);
    const h = r.headers();
    const cabeceras = { contrato: h['x-bms-contrato'], entorno: h['x-bms-entorno'] };
    if (enLaBusqueda) deLaBusqueda.add(k);
    leyendo.push(
      (async () => {
        if ((h['content-type'] ?? '').includes('json')) guardar(k, r.status(), cabeceras, await r.json(), 'app');
        else if (r.status() === 200) descargas.add(k.split('?')[0]);
      })().catch(() => {})
    );
  });
  let enLaBusqueda = false;

  const grabado = new Date().toISOString();
  // Las bandas del servidor, tal cual las pone en /app (antes de que la app les ponga su sitio).
  const bandas = ((await (await fetch(`${base}/app`)).text()).match(/<(\w+)\b[^>]*\bclass="[^"]*\bbms-banda\b[^"]*"[^>]*>[\s\S]*?<\/\1>/g) ?? []).join('\n');
  await pagina.goto(`${base}/app`);
  const v = { pagina, marco: pagina, grabando: true, avisos: [], errores: [], pendientes: async () => enCamino };
  v.traza = (nombre) => /^(panel-[a-z]+|importar|busqueda|documentos|inicio|procesar)$/.test(nombre) && dice(`  ${nombre}`);
  await entrar(v, token);

  const textos = new Set();
  const paradas = [];
  for (const idioma of IDIOMAS) {
    await ponerIdioma(v, idioma);
    await abrirRueda(v);
    for (const t of await titulosRueda(v)) textos.add(t);
    textos.add(PREGUNTA_RESUMEN[idioma]);
    const alFallar = (nombre) => pagina.screenshot({ path: join(dirname(salida), `FALLO-${idioma}-${nombre}.png`) }).catch(() => {});
    await gira(v, { completa: idioma === 'nl', tolerante: true, alFallar }, async (nombre) => {
      paradas.push(`${idioma}-${nombre}`);
      enLaBusqueda = nombre.startsWith('busqueda');
      if (ENTRADAS_PANEL.some((id) => id !== 'settings' && nombre === `panel-${id}`)) for (const t of await titulosPanel(v)) textos.add(t);
    });
    enLaBusqueda = false;
    dice(`gira en ${idioma}: ${paradas.length} paradas, ${Object.keys(respuestas).length} respuestas`);
  }
  // El tema no pide nada a la API, pero se toca como lo tocara quien mire; y salir y volver a entrar.
  await ponerIdioma(v, 'nl');
  for (const tema of ['light', 'system', 'dark']) await ponerTema(v, tema);
  await salir(v);
  await entrar(v, token);
  await espera(500);
  await Promise.all(leyendo);
  for (const a of v.avisos) dice(`aviso: ${a}`);
  for (const e of v.errores) dice(`ERROR EN LA GIRA: ${e}`);
  if (errores.length) dice(`errores en la consola durante la gira: ${[...new Set(errores)].join(' | ')}`);

  // ---------------------------------------------------------------- 2. el cierre

  fase = 'cierre';
  async function directa(ruta) {
    const k = clave(ruta);
    if (respuestas[k] || descargas.has(k.split('?')[0])) return respuestas[k];
    const r = await fetch(base + k, { headers: { 'X-BMS-Token': token } });
    const cabeceras = { contrato: r.headers.get('x-bms-contrato') ?? undefined, entorno: r.headers.get('x-bms-entorno') ?? undefined };
    if ((r.headers.get('content-type') ?? '').includes('json')) {
      respuestas[k] = { estado: r.status, entorno: cabeceras.entorno ?? entorno, contrato: cabeceras.contrato ?? contrato, origen: 'directa', cuerpo: await r.json() };
    } else {
      await r.arrayBuffer();
      if (r.status === 200) descargas.add(k.split('?')[0]);
    }
    return respuestas[k];
  }
  const lista = async (ruta, sacar) => sacar((await directa(ruta))?.cuerpo ?? {}) ?? [];
  const facturas = await lista('/api/v2/facturas', (c) => c.facturas);
  const clientes = await lista('/api/v2/clientes', (c) => c.clientes);
  const proveedores = await lista('/api/v2/proveedores', (c) => c.proveedores);
  const objetos = await lista('/api/v2/objetos', (c) => c.objetos);
  const ordenes = await lista('/api/v2/ordenes', (c) => c.ordenes);
  const trimestres = [...new Set(JSON.stringify((await directa('/api/v2/btw'))?.cuerpo ?? {}).match(/\b\d{4}-T[1-4]\b/g) ?? [])];
  const documentos = new Set();
  for (const c of clientes) for (const d of await lista(`/api/v2/clientes/${c.id}/documentos`, (x) => x.documentos?.documentos)) documentos.add(d.id);
  for (const p of proveedores) for (const d of await lista(`/api/v2/proveedores/${p.id}/documentos`, (x) => x.documentos?.documentos)) documentos.add(d.id);
  const ids = {
    factura: facturas.map((f) => f.id),
    cliente: clientes.map((c) => c.id),
    proveedor: proveedores.map((p) => p.id),
    objeto: objetos.map((o) => o.id),
    orden: ordenes.map((o) => o.id),
    trimestre: trimestres,
    documento: [...documentos],
  };
  dice(`cierre: ${Object.entries(ids).map(([k, l]) => `${l.length} ${k}`).join(', ')}`);

  // Las plantillas: cada clave de la gira con sus ids cambiados por {tipo}.
  const EN_RUTA = [
    [/^(\/api\/v2\/facturas\/)\d+(?=\/|$)/, 'factura'],
    [/^(\/api\/v2\/clientes\/)\d+(?=\/|$)/, 'cliente'],
    [/^(\/api\/v2\/proveedores\/)\d+(?=\/|$)/, 'proveedor'],
    [/^(\/api\/v2\/objetos\/)\d+(?=\/|$)/, 'objeto'],
    [/^(\/api\/v2\/ordenes\/)\d+(?=\/|$)/, 'orden'],
    [/^(\/api\/v2\/documentos\/)\d+(?=\/|$)/, 'documento'],
    [/^(\/api\/v2\/btw\/)\d{4}-T[1-4](?=\/|$)/, 'trimestre'],
  ];
  const EN_CONSULTA = { cliente_id: 'cliente', proveedor_id: 'proveedor', objeto_id: 'objeto', orden_compra_id: 'orden', trimestre: 'trimestre' };
  const plantillas = new Set([
    '/api/v2/facturas/{factura}',
    '/api/v2/facturas/{factura}/historial',
    '/api/v2/facturas/{factura}/original',
    '/api/v2/clientes/{cliente}',
    '/api/v2/clientes/{cliente}/documentos',
    '/api/v2/proveedores/{proveedor}',
    '/api/v2/proveedores/{proveedor}/documentos',
    '/api/v2/objetos/{objeto}',
    '/api/v2/ordenes/{orden}',
    '/api/v2/documentos/{documento}/original',
    '/api/v2/btw/{trimestre}',
    '/api/v2/btw/{trimestre}/hoja',
    '/api/v2/btw/{trimestre}/hoja.csv',
  ]);
  for (const k of Object.keys(respuestas)) {
    let [ruta, consulta = ''] = k.split('?', 2);
    for (const [re, tipo] of EN_RUTA) ruta = ruta.replace(re, `$1{${tipo}}`);
    const pares = [...new URLSearchParams(consulta)];
    if (pares.some(([n]) => n === 'texto')) continue;
    const q = pares.map(([n, valor]) => `${encodeURIComponent(n)}=${EN_CONSULTA[n] ? `{${EN_CONSULTA[n]}}` : encodeURIComponent(valor)}`).join('&');
    const plantilla = q ? `${ruta}?${q}` : ruta;
    if (plantilla.includes('{')) plantillas.add(plantilla);
  }
  for (const plantilla of plantillas) {
    let rutas = [plantilla];
    for (const [tipo, lista_] of Object.entries(ids)) {
      if (!plantilla.includes(`{${tipo}}`)) continue;
      rutas = rutas.flatMap((r) => lista_.map((id) => r.replaceAll(`{${tipo}}`, encodeURIComponent(String(id)))));
    }
    for (const r of rutas.slice(0, 600)) await directa(r);
  }
  dice(`cierre por ids: ${plantillas.size} plantillas, ${Object.keys(respuestas).length} respuestas`);

  // La pantalla de la busqueda: lo que pidio con sus filtros (los parametros que no son un id ni
  // el texto), con cada empresa y cada valor visto de cada filtro, y todas sus combinaciones.
  const fijos = new Map();
  const variables = new Map();
  for (const k of deLaBusqueda) {
    const [ruta, consulta = ''] = k.split('?', 2);
    if (ruta !== '/api/v2/buscar') continue;
    const pares = [...new URLSearchParams(consulta)];
    if (!pares.some(([n]) => n === 'limite') || pares.some(([n, valor]) => n === 'limite' && Number(valor) < 20)) continue;
    for (const [n, valor] of pares) {
      if (n === 'texto' || EN_CONSULTA[n]) continue;
      if (n === 'limite' || n === 'orden') fijos.set(n, valor);
      else variables.set(n, (variables.get(n) ?? new Set()).add(valor));
    }
  }
  if (fijos.size) {
    const empresas = [[], ...ids.cliente.map((id) => [['cliente_id', String(id)]]), ...ids.proveedor.map((id) => [['proveedor_id', String(id)]])];
    let combinaciones = [[]];
    for (const [n, valores] of variables) combinaciones = combinaciones.flatMap((c) => [c, ...[...valores].map((valor) => [...c, [n, valor]])]);
    let cuantas = 0;
    for (const empresa of empresas) {
      for (const c of combinaciones.slice(0, 40)) {
        await directa(`/api/v2/buscar?${new URLSearchParams([...fijos, ...empresa, ...c])}`);
        cuantas += 1;
      }
    }
    dice(`cierre de la busqueda: ${cuantas} combinaciones (${[...variables.keys()].join(', ') || 'sin filtros'})`);
  }

  // La busqueda por texto: lo que se escribe en la caja (la conversacion pide ocho; la pantalla
  // de la busqueda, cincuenta por fecha: las dos formas que haya pedido la gira).
  for (const f of facturas) if (f.numero) textos.add(f.numero);
  for (const x of [...clientes, ...proveedores, ...objetos]) if (x.nombre) textos.add(x.nombre);
  for (const o of objetos) if (o.codigo) textos.add(o.codigo);
  for (const o of ordenes) if (o.numero) textos.add(o.numero);
  const formas = new Set();
  for (const k of Object.keys(respuestas)) {
    const [ruta, consulta = ''] = k.split('?', 2);
    const pares = [...new URLSearchParams(consulta)];
    if (ruta !== '/api/v2/buscar' || !pares.some(([n]) => n === 'texto')) continue;
    if (pares.some(([n]) => EN_CONSULTA[n])) continue;
    formas.add(new URLSearchParams(pares.filter(([n]) => n !== 'texto')).toString());
  }
  for (const forma of formas) for (const texto of textos) await directa(`/api/v2/buscar?${new URLSearchParams([...new URLSearchParams(forma), ['texto', texto]])}`);
  dice(`cierre por texto: ${textos.size} textos × ${formas.size} formas, ${Object.keys(respuestas).length} respuestas, ${descargas.size} descargas`);

  // ---------------------------------------------------------------- 3. la lectura de Procesar

  fase = 'lectura';
  const lector = (...orden) => {
    const r = spawnSync(py, [join(repo, 'scripts', 'simular_lector.py'), '--db', demo.db, ...orden], { env, encoding: 'utf8' });
    if (r.status !== 0) throw new Error(`simular_lector ${orden.join(' ')}: ${r.stderr || r.stdout}`);
    return JSON.parse(r.stdout.trim().split('\n').pop());
  };
  const lectorDeFondo = (...orden) =>
    new Promise((ok, mal) => {
      const hijo = spawn(py, [join(repo, 'scripts', 'simular_lector.py'), '--db', demo.db, ...orden], { env });
      let err = '';
      hijo.stderr.on('data', (c) => (err += c));
      hijo.on('error', mal);
      hijo.on('exit', (codigo) => (codigo === 0 ? ok() : mal(new Error(`simular_lector ${orden.join(' ')} (${codigo}): ${err}`))));
    });
  const pasos = [];
  const inicio = Date.now();
  let mirando = true;
  let ultimo = '';
  const mirar = async () => {
    const r = await fetch(`${base}/api/v2/lectura`, { headers: { 'X-BMS-Token': token } });
    const cuerpo = await r.json();
    const texto = JSON.stringify(cuerpo);
    if (texto !== ultimo) {
      ultimo = texto;
      pasos.push({ ms: Date.now() - inicio, estado: r.status, contrato: r.headers.get('x-bms-contrato') ?? contrato, cuerpo });
    }
    return cuerpo.lectura;
  };
  const vigia = (async () => {
    while (mirando) {
      await mirar().catch(() => {});
      await espera(220);
    }
  })();
  const estadoDe = async () => (await mirar())?.solicitud?.estado ?? null;
  const esperarEstado = async (quiero, max = 60_000) => {
    const fin = Date.now() + max;
    while (Date.now() < fin) {
      const e = await estadoDe();
      if (quiero.includes(e)) return e;
      await espera(200);
    }
    throw new Error(`la lectura no llega a ${quiero.join(' o ')} (esta en ${await estadoDe()})`);
  };
  // La app pide la lectura (Procesar, su boton); el lector la toma y cuenta; la app dice que si
  // (su boton otra vez); el lector lee documento a documento. Los ritmos, los de una lectura
  // de verdad vista deprisa: unos segundos por paso y menos de un segundo por documento.
  const { entrada: abrirEntrada, quieta } = await import('./gira.mjs');
  await abrirEntrada(v, 'process');
  await mirar();
  await pagina.locator('.flow-button').click();
  await esperarEstado(['pedida']);
  await espera(3500);
  lector('tomar');
  await espera(2500);
  lector('contar', '--nuevas', '12', '--ya-leidas', '3');
  await esperarEstado(['esperando_aprobacion']);
  await pagina.locator('.flow-button').waitFor({ state: 'visible', timeout: 30_000 });
  await quieta(v);
  await espera(6000);
  await pagina.locator('.flow-button').click();
  await esperarEstado(['aprobada', 'leyendo']);
  await espera(1500);
  await lectorDeFondo('leer', '--pausa', '0.65', '--duplicados', '1');
  await esperarEstado(['hecha']);
  await espera(1200);
  mirando = false;
  await vigia;
  const lectura = { grabada: new Date(inicio).toISOString(), pasos, duracion: Date.now() - inicio };
  dice(`lectura: ${pasos.length} pasos en ${Math.round(lectura.duracion / 1000)} s (${[...new Set(pasos.map((p) => p.cuerpo.lectura?.solicitud?.estado ?? 'sin pedir'))].join(' → ')})`);
  await browser.close();

  // ---------------------------------------------------------------- lo grabado

  const ordenadas = Object.fromEntries(Object.entries(respuestas));
  const grabacion = { grabado, contrato, respuestas: ordenadas, descargas: [...descargas].sort(), lectura };
  mkdirSync(dirname(salida), { recursive: true });
  writeFileSync(salida, JSON.stringify(grabacion));
  writeFileSync(join(dirname(salida), 'pagina.json'), JSON.stringify({ bandas, grabado }, null, 2) + '\n');
  const porOrigen = Object.values(respuestas).reduce((a, r) => ((a[r.origen] = (a[r.origen] ?? 0) + 1), a), {});
  const resumen = {
    salida,
    bytes: Buffer.byteLength(JSON.stringify(grabacion)),
    grabado,
    contrato,
    respuestas: Object.keys(respuestas).length,
    por_origen: porOrigen,
    por_estado: Object.values(respuestas).reduce((a, r) => ((a[r.estado] = (a[r.estado] ?? 0) + 1), a), {}),
    descargas: descargas.size,
    pasos_lectura: pasos.length,
    textos: textos.size,
    paradas: paradas.length,
    segundos: Math.round((Date.now() - t0) / 1000),
    errores_gira: v.errores,
  };
  writeFileSync(join(dirname(salida), 'grabacion-resumen.json'), JSON.stringify({ ...resumen, textos: [...textos], paradas }, null, 2) + '\n');
  console.log(JSON.stringify(resumen, null, 2));
  codigoDeSalida = v.errores.length ? 1 : 0;
} finally {
  await limpiar();
}
process.exit(codigoDeSalida);
