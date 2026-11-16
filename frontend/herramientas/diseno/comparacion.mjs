// comparacion.mjs — las fotos de «ahora» de la comparacion del tema claro (y las dos del
// oscuro), sacadas de la app construida del repo: los mismos nombres, el mismo tamano y el mismo
// estado y encuadre que las que ya hay publicadas. Las diez antes-….jpg (el tema claro VIEJO) no
// se tocan ni se rehacen: este guion no escribe ningun fichero con ese nombre.
//
//   node comparacion.mjs [--repo <ruta>] [--out <carpeta>] [--solo nombre,nombre]
//
// Escribe ahora-<estado>.jpg (10, tema claro) y oscuro-<estado>.jpg (2) en --out (por defecto
// salida/comparacion/ de esta carpeta, que no va en git); --repo es por defecto el repo que la lleva. Del repo solo
// se lee (la base de prueba y el servidor van a .trabajo/).
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { AQUI, argumentos, contexto, espera, lista, navegador, repoDe, servidor } from './comun.mjs';
import * as A from './app.mjs';

const { $, clic, quieta, hasta, HOJA, PANEL, NL } = A;
const args = argumentos();
const { repo, frontend } = repoDe(args);
const out = typeof args.out === 'string' ? resolve(args.out) : join(AQUI, 'salida', 'comparacion');
mkdirSync(out, { recursive: true });

/** La hoja abierta, bajada hasta el final (su ultima fila o su tarjeta, a la vista). */
async function hojaAlFinal(v) {
  await v.pagina.evaluate((sel) => {
    const hoja = document.querySelector(sel);
    const cajas = [hoja, ...hoja.querySelectorAll('*')].filter((el) => el.scrollHeight > el.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(el).overflowY));
    for (const el of cajas) el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
  }, HOJA);
  await quieta(v);
}

/** Cada foto: su nombre (el de las publicadas), su ventana, su tema y como se llega. */
const FOTOS = [
  { nombre: 'ahora-start-1440', ancho: 1440, tema: 'light', llegar: (v) => A.aInicio(v) },
  { nombre: 'ahora-te-ontvangen-1440', ancho: 1440, tema: 'light', llegar: (v) => A.entrada(v, 'receivables') },
  {
    nombre: 'ahora-gesprek-bento-1440',
    ancho: 1440,
    tema: 'light',
    llegar: async (v) => {
      await A.aInicio(v);
      await A.preguntar(v, NL.overzicht);
      await hasta(v, 'el bento', () => $(v, '.finance-bento').isVisible());
    },
  },
  { nombre: 'ahora-documenten-1440', ancho: 1440, tema: 'light', llegar: (v) => A.entrada(v, 'documents') },
  {
    // La hoja de la factura en otra moneda, plegada, con la tarjeta de su primera fila.
    nombre: 'ahora-factuur-kaart-1440',
    ancho: 1440,
    tema: 'light',
    llegar: async (v) => {
      await A.abrirFactura(v, v.srv.numeros.otherCurrency);
      await clic(v, $(v, `${HOJA} .ws-file-table > a`).first());
      await hasta(v, 'la tarjeta de la fila', () => $(v, `${HOJA} .detail`).isVisible());
      // La hoja baja sola hasta la tarjeta: ese es el encuadre.
      await quieta(v);
    },
  },
  {
    // Te betalen > Deze week > la tarjeta de la factura > «Betaling vastleggen», con el motivo
    // escrito y la pregunta de confirmacion a la vista. No se dice que si: no se apunta nada.
    nombre: 'ahora-bevestigen-400',
    ancho: 400,
    tema: 'light',
    llegar: async (v) => {
      await A.entrada(v, 'payables');
      await A.pulsarFila(v, A.filaPanel(v, NL.dezeWeek).first());
      await A.pulsarFila(v, A.filasPanel(v).first());
      const tarjeta = $(v, `${PANEL} .detail`);
      await hasta(v, 'la tarjeta', () => tarjeta.isVisible());
      await clic(v, tarjeta.getByRole('button', { name: NL.betalingVastleggen, exact: true }).first());
      const orden = tarjeta.locator('.order-form');
      await hasta(v, 'el formulario', () => orden.isVisible());
      await orden.getByLabel(NL.reden).first().fill('Contant betaald, kwitantie in de map');
      await clic(v, orden.getByRole('button', { name: NL.betalingVastleggen, exact: true }));
      await hasta(v, 'la confirmacion', () => tarjeta.locator('.chat-export').isVisible());
      await quieta(v);
      await v.pagina.evaluate((sel) => {
        const panel = document.querySelector(sel);
        panel.scrollTo({ top: panel.scrollHeight, behavior: 'instant' });
      }, PANEL);
    },
  },
  {
    nombre: 'ahora-factuur-ingeklapt-400',
    ancho: 400,
    tema: 'light',
    llegar: async (v) => {
      // La de Demo Brandwacht Oost (la del pago que propone el banco), como la publicada.
      await A.abrirFactura(v, v.srv.numeros.oost);
      await hojaAlFinal(v);
    },
  },
  {
    // La ficha del cliente en Documenten, con el pie de su carpeta arriba (como en la publicada:
    // la ficha empieza a 298 px del borde de la ventana).
    nombre: 'ahora-documenten-klant-400',
    ancho: 400,
    tema: 'light',
    llegar: async (v) => {
      await A.entrada(v, 'documents');
      await A.abrirFicha(v, 'Demo Havenbedrijf BV', 'Klanten');
      await v.pagina.evaluate(() => {
        const ficha = document.querySelector('.ws-profile');
        window.scrollBy({ top: ficha.getBoundingClientRect().top - 298, behavior: 'instant' });
      });
    },
  },
  {
    nombre: 'ahora-zoeken-filters-400',
    ancho: 400,
    tema: 'light',
    llegar: async (v) => {
      await A.entrada(v, 'search');
      await clic(v, $(v, 'button.filters-toggle').first());
      await hasta(v, 'los filtros', () => $(v, `${A.APP} [role=combobox]`).first().isVisible());
      await v.pagina.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    },
  },
  { nombre: 'ahora-verwerken-400', ancho: 400, tema: 'light', llegar: (v) => A.entrada(v, 'process') },
  { nombre: 'oscuro-start-1440', ancho: 1440, tema: 'dark', llegar: (v) => A.aInicio(v) },
  { nombre: 'oscuro-documenten-1440', ancho: 1440, tema: 'dark', llegar: (v) => A.entrada(v, 'documents') },
];

const fotos = FOTOS.filter((f) => lista(args.solo, FOTOS.map((x) => x.nombre)).includes(f.nombre));
const pasadas = [...new Set(fotos.map((f) => `${f.ancho}|${f.tema}`))];
const { browser } = await navegador(frontend);
const srv = await servidor(repo);
let fallos = 0;
try {
  for (const pasada of pasadas) {
    const [ancho, tema] = [Number(pasada.split('|')[0]), pasada.split('|')[1]];
    const ctx = await contexto(browser, ancho);
    const pagina = await ctx.newPage();
    const v = A.vista(pagina, srv, ancho, tema);
    try {
      await A.entrar(v);
      await A.ponerTema(v, tema);
      for (const foto of fotos.filter((f) => f.ancho === ancho && f.tema === tema)) {
        v.donde = foto.nombre;
        try {
          await foto.llegar(v);
          // El raton fuera de todo, y la pantalla quieta.
          await pagina.mouse.move(ancho - 3, 3);
          await quieta(v);
          await espera(300);
          if ((await A.temaVisto(v)) !== tema) throw new Error(`el tema que se ve no es ${tema}`);
          const jpg = await pagina.screenshot({ type: 'jpeg', quality: 86, caret: 'hide' });
          writeFileSync(join(out, `${foto.nombre}.jpg`), jpg);
          console.log(`${foto.nombre}.jpg ${jpg.length} bytes`);
        } catch (error) {
          fallos += 1;
          console.log(`FALLO ${foto.nombre}: ${String(error?.message ?? error).split('\n')[0]}`);
        }
        await A.aInicio(v).catch(() => {});
      }
    } catch (error) {
      fallos += 1;
      console.log(`FALLO pasada ${pasada}: ${String(error?.message ?? error).split('\n')[0]} (en ${v.donde})`);
    }
    if (v.errores.length) console.log(`  errores de la app: ${[...new Set(v.errores)].slice(0, 4).join(' | ')}`);
    await ctx.close();
  }
} finally {
  await browser.close();
  await srv.parar();
}
console.log(`${fallos ? `CON ${fallos} FALLOS` : 'BIEN'}: ${fotos.length - fallos} fotos en ${out}`);
process.exit(fallos ? 1 : 0);
