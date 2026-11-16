// estados.mjs — los estados principales de la app que lleva el fichero de diseno, en el orden
// en que se visitan (el ultimo, la lectura en marcha de Verwerken, cambia la base de prueba: por
// eso cada pasada tiene su servidor y su base). Cada uno dice como se llega a el como una
// persona; `v` es la vista de app.mjs.
import { espera } from './comun.mjs';
import * as A from './app.mjs';

const { $, clic, quieta, hasta, HOJA, PANEL, NL } = A;

/** Abre la tarjeta de una fila del panel de `id`: `camino` son los titulos (o indices) de las
 *  filas que se pulsan, una vista detras de otra. */
async function tarjeta(v, id, camino) {
  await A.entrada(v, id);
  for (const paso of camino) {
    const fila = typeof paso === 'number' ? A.filasPanel(v).nth(paso) : A.filaPanel(v, paso).first();
    await hasta(v, `la fila ${paso} de ${id}`, () => fila.count());
    await A.pulsarFila(v, fila);
  }
  await hasta(v, `la tarjeta de ${id}`, () => $(v, `${PANEL} .detail`).isVisible());
  await quieta(v);
}

/** Verwerken hasta la lectura en marcha: se pide, el lector de las pruebas la toma y cuenta
 *  (4 nuevas y 1 ya leida), se empieza y el lector lee despacio (como e2e/procesar.spec.ts). */
async function lecturaEnMarcha(v) {
  if (!/\bprocess-mode\b/.test(await A.clase(v))) await A.entrada(v, 'process');
  const boton = $(v, '.processing-workspace .flow-button');
  await clic(v, boton);
  await hasta(v, 'la lectura pedida', async () => (await boton.evaluate((el) => getComputedStyle(el).visibility)) === 'hidden');
  v.srv.lector('tomar');
  v.srv.lector('contar', '--nuevas', '4', '--ya-leidas', '1');
  await hasta(v, 'lo contado', async () => (await boton.evaluate((el) => getComputedStyle(el).visibility)) === 'visible', 30_000);
  await quieta(v);
  await clic(v, boton);
  v.srv.lectorEnFondo('leer', '--pausa', '7', '--duplicados', '1');
  await hasta(v, 'la lectura en marcha', () => $(v, '.processing-workspace .processing-loading').isVisible(), 60_000);
  // La suricata entra en el documento (el fundido de la escena) y el primer paso del lector.
  await espera(9000);
  await quieta(v);
}

export const ESTADOS = [
  { id: 'login', titulo: 'Inloggen', nota: 'La entrada: el código de acceso, antes de entrar.', llegar: (v) => A.aLaEntrada(v), sinEntrar: true },
  { id: 'start', titulo: 'Start', nota: 'El inicio (E0): el saludo, el orbe y la caja.', llegar: (v) => A.aInicio(v) },
  { id: 'start-wiel', titulo: 'Start met het wiel', nota: 'El inicio con la rueda abierta (E1).', llegar: (v) => A.abrirRueda(v) },
  { id: 'paneel-start-kaart', titulo: 'Paneel Start · kaart open', nota: 'Panel Start › Eerst, con la tarjeta de su primera factura.', llegar: (v) => tarjeta(v, 'home', [0, 0]) },
  { id: 'te-ontvangen', titulo: 'Te ontvangen', nota: 'El panel Te ontvangen en reposo.', llegar: (v) => A.entrada(v, 'receivables') },
  { id: 'te-ontvangen-kaart', titulo: 'Paneel Te ontvangen · kaart open', nota: 'Te ontvangen › Niet gekoppeld, con la tarjeta de una línea del banco sin factura.', llegar: (v) => tarjeta(v, 'receivables', ['Niet gekoppeld', 0]) },
  { id: 'bank', titulo: 'Bank · Te bevestigen', nota: 'La vista del banco: Te ontvangen › Te bevestigen, con la tarjeta de un cobro que propone el banco y sus coincidencias.', llegar: (v) => tarjeta(v, 'receivables', [NL.teBevestigen, 0]) },
  { id: 'te-betalen', titulo: 'Te betalen', nota: 'El panel Te betalen en reposo.', llegar: (v) => A.entrada(v, 'payables') },
  { id: 'te-betalen-kaart', titulo: 'Paneel Te betalen · kaart open', nota: 'Te betalen › Deze week, con la tarjeta de su primera factura.', llegar: (v) => tarjeta(v, 'payables', [NL.dezeWeek, 0]) },
  { id: 'btw-kaart', titulo: 'Paneel Btw · kaart open', nota: 'El panel Btw con la tarjeta del último trimestre terminado.', llegar: (v) => tarjeta(v, 'vat', [1]) },
  { id: 'instellingen', titulo: 'Instellingen', nota: 'El panel Instellingen en reposo.', llegar: (v) => A.entrada(v, 'settings') },
  { id: 'instellingen-kaart', titulo: 'Paneel Instellingen · kaart open', nota: 'Instellingen con la tarjeta de «Jouw account».', llegar: (v) => tarjeta(v, 'settings', [2]) },
  {
    id: 'gesprek-bento',
    titulo: 'Gesprek met het overzicht',
    nota: 'La conversación con el resumen general (el bento), tras preguntar «Geef me een overzicht».',
    llegar: async (v) => {
      await A.aInicio(v);
      await A.preguntar(v, NL.overzicht);
      await hasta(v, 'el bento', () => $(v, '.finance-bento').isVisible());
      await quieta(v);
    },
  },
  {
    id: 'zoeken-filters',
    titulo: 'Zoeken met filters',
    nota: 'La búsqueda con sus filtros abiertos.',
    llegar: async (v) => {
      await A.entrada(v, 'search');
      await clic(v, $(v, 'button.filters-toggle').first());
      await hasta(v, 'los filtros', () => $(v, `${A.APP} [role=combobox]`).first().isVisible());
      await quieta(v);
    },
  },
  {
    id: 'zoeken-filterlijst',
    titulo: 'Zoeken · filterlijst open',
    nota: 'La búsqueda con la lista de un filtro abierta (Klant of leverancier, con su buscador). Documenten no tiene filtros: la lista de filtro de la app es esta.',
    llegar: async (v) => {
      if (!(await $(v, `${A.APP} [role=combobox]`).count())) {
        await A.entrada(v, 'search');
        await clic(v, $(v, 'button.filters-toggle').first());
      }
      await clic(v, $(v, `${A.APP} [role=combobox]`).first());
      await hasta(v, 'las opciones', async () => (await v.pagina.locator('[role=option]').count()) > 0);
      await quieta(v);
    },
    salir: async (v) => {
      await v.pagina.keyboard.press('Escape');
      await quieta(v);
    },
  },
  {
    id: 'ctrl-k',
    titulo: 'Ctrl+K',
    nota: 'Lo que se ve tras pulsar Ctrl+K en el inicio: nada nuevo. La app no tiene paleta ni atajo desde el paso 17 (registro, §6.5).',
    llegar: async (v) => {
      await A.aInicio(v);
      await v.pagina.keyboard.press('Control+k');
      await espera(400);
      await quieta(v);
    },
  },
  { id: 'documenten-mappen', titulo: 'Documenten · mappen', nota: 'Documenten: el árbol y la rejilla de carpetas.', llegar: (v) => A.entrada(v, 'documents') },
  {
    id: 'documenten-map-open',
    titulo: 'Documenten · map open',
    nota: 'Documenten con una carpeta abierta (el abanico de sus documentos).',
    llegar: async (v) => {
      if ((await A.pantalla(v)) !== 'work') await A.entrada(v, 'documents');
      // La primera carpeta que tenga documentos.
      const celdas = $(v, '[data-testid=folder-cell]');
      const total = await celdas.count();
      let cual = 0;
      for (let i = 0; i < total; i += 1) {
        const dice = (await celdas.nth(i).locator('button.gf-hit').getAttribute('aria-label')) ?? '';
        if (!/\b0\b/.test(dice)) {
          cual = i;
          break;
        }
      }
      await clic(v, celdas.nth(cual).locator('button.gf-hit'));
      await espera(900);
      await quieta(v);
    },
    salir: async (v) => {
      const abierta = $(v, '[data-testid=folder-cell] button.gf-hit[aria-expanded=true]');
      if (await abierta.count()) await clic(v, abierta.first());
      await quieta(v);
    },
  },
  {
    id: 'documenten-klantkaart',
    titulo: 'Documenten · kaart van de klant',
    nota: 'Documenten con la ficha de un cliente (Demo Havenbedrijf BV). Si la ficha queda por debajo de la ventana (a 400 px), la página está bajada hasta ella.',
    llegar: async (v) => {
      await A.abrirFicha(v, 'Demo Havenbedrijf BV', 'Klanten');
      // La ficha, a la vista: si empieza en la mitad de abajo de la ventana (o mas alla), se baja
      // la pagina hasta dejarla a 298 px del borde (el encuadre de las fotos de la comparacion).
      await v.pagina.evaluate(() => {
        const arriba = document.querySelector('.ws-profile').getBoundingClientRect().top;
        // A un pixel entero: con un desplazamiento fraccionario la pagina viva pinta la letra medio
        // pixel corrida y el marco (que lo restaura entero) no; la comprobacion lo veia (> 1 %).
        if (arriba > window.innerHeight / 2) window.scrollTo({ top: Math.round(window.scrollY + arriba - 298), behavior: 'instant' });
      });
      await quieta(v);
    },
  },
  { id: 'factuur-ingeklapt', titulo: 'Factuur · ingeklapt', nota: 'La hoja de una factura (la de Demo Brandwacht Oost, con un pago que propone el banco) con sus filas plegadas.', llegar: (v) => A.abrirFactura(v, v.srv.numeros.oost) },
  {
    id: 'factuur-uitgeklapt',
    titulo: 'Factuur · uitgeklapt',
    nota: 'La misma hoja, desplegada.',
    llegar: async (v) => {
      if (!(await $(v, HOJA).count())) await A.abrirFactura(v, v.srv.numeros.oost);
      await A.desplegar(v);
    },
  },
  { id: 'verwerken-start', titulo: 'Verwerken · begin', nota: 'Verwerken al empezar: «Lezen aanvragen».', llegar: (v) => A.entrada(v, 'process') },
  { id: 'verwerken-bezig', titulo: 'Verwerken · bezig', nota: 'Verwerken con la lectura en marcha (el lector de las pruebas, leyendo despacio).', llegar: lecturaEnMarcha },
];

export const IDS = ESTADOS.map((e) => e.id);
