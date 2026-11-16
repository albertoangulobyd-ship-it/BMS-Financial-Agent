// Las herramientas de frontend/herramientas (la vista previa navegable y el fichero de diseno).
// Van aqui porque es donde busca vitest (vite.config.ts, que entra en la huella de lo construido:
// asi no hay que tocarlo). Lo que se prueba sin navegador ni servidor:
// - que contesta la vista previa a cada peticion de la app (vista-previa/src/rutas.js, lo que
//   usa su shim): lo grabado por su clave, 401 sin token, 409 para una orden o una descarga,
//   404 no_grabado para lo demas y la lectura grabada de Procesar;
// - que lo que corre dentro de la pagina publicada no interpreta HTML ni nombra direcciones de
//   fuera (la regla de la app, tests/test_app_local.py, tambien para el shim);
// - que las herramientas toman por defecto el repo que las lleva.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { REPO, argumentos } from '../herramientas/entorno.mjs';
import { LECTURA, clave, crearContestador, rutaDe } from '../herramientas/vista-previa/src/rutas.js';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const vistaPrevia = join(frontend, 'herramientas', 'vista-previa');

const datos = {
  contrato: 'v2-prueba',
  descargas: ['/api/v2/facturas/7/original'],
  respuestas: {
    '/api/v2/facturas': { estado: 200, contrato: 'v2-prueba', cuerpo: { facturas: [{ id: 7 }] } },
    '/api/v2/buscar?limite=8&texto=Demo': { estado: 200, cuerpo: { resultados: ['uno'] } },
    [LECTURA]: { estado: 200, cuerpo: { lectura: null } },
  },
};

describe('la vista previa: que contesta a cada peticion', () => {
  const contestar = crearContestador(datos);

  it('la clave ordena los parametros y quita la barra final', () => {
    expect(clave('/api/v2/buscar/?texto=Demo&limite=8')).toBe('/api/v2/buscar?limite=8&texto=Demo');
    expect(clave('/api/v2/buscar?limite=8&texto=Demo')).toBe(clave('/api/v2/buscar?texto=Demo&limite=8'));
    expect(clave('/')).toBe('/');
    expect(rutaDe('http://127.0.0.1:5173/api/v2/facturas?a=1#x')).toBe('/api/v2/facturas?a=1');
    expect(rutaDe(new URL('https://ejemplo.invalid/api/v2/btw'))).toBe('/api/v2/btw');
    expect(rutaDe({ url: '/api/v2/clientes#arriba' })).toBe('/api/v2/clientes');
  });

  it('sin token, 401 como el servidor', () => {
    for (const token of [null, '', '   ']) expect(contestar('/api/v2/facturas', 'GET', token)).toMatchObject({ estado: 401, cuerpo: { codigo: 'sin_token' } });
  });

  it('lo grabado, por su clave y con su contrato', () => {
    expect(contestar('/api/v2/facturas/', 'GET', 'x')).toEqual({ estado: 200, cuerpo: { facturas: [{ id: 7 }] }, contrato: 'v2-prueba' });
    expect(contestar('/api/v2/buscar?texto=Demo&limite=8', 'GET', 'x')).toMatchObject({ estado: 200, cuerpo: { resultados: ['uno'] } });
    expect(contestar('/api/v2/facturas', 'HEAD', 'x').estado).toBe(200);
  });

  it('una orden no se guarda: 409 vista_previa y el aviso de la pagina', () => {
    for (const metodo of ['POST', 'PUT', 'PATCH', 'DELETE']) {
      expect(contestar('/api/v2/facturas/7/ordenes', metodo, 'x')).toMatchObject({ estado: 409, cuerpo: { codigo: 'vista_previa', tipo: 'VistaPrevia' }, aviso: true });
    }
  });

  it('una descarga, grabada o con forma de descarga: 409 vista_previa_descarga', () => {
    for (const ruta of ['/api/v2/facturas/7/original', '/api/v2/documentos/3/original', '/api/v2/btw/2026-T3/hoja.csv']) {
      const r = contestar(ruta, 'GET', 'x');
      expect(r).toMatchObject({ estado: 409, cuerpo: { codigo: 'vista_previa_descarga' } });
      expect(r.sinGrabar).toBeUndefined();
    }
  });

  it('lo que no se grabo: 404 no_grabado, apuntado con su clave', () => {
    expect(contestar('/api/v2/buscar?texto=otra+cosa&limite=8', 'GET', 'x')).toMatchObject({
      estado: 404,
      cuerpo: { codigo: 'no_grabado' },
      sinGrabar: '/api/v2/buscar?limite=8&texto=otra+cosa',
    });
  });

  it('la lectura grabada de Procesar manda sobre lo grabado, y solo en su ruta', () => {
    const paso = { estado: 200, contrato: 'v2-lectura', cuerpo: { lectura: { solicitud: { estado: 'leyendo' } } } };
    let preguntas = 0;
    const pasoDeAhora = () => ((preguntas += 1), paso);
    expect(contestar(LECTURA, 'GET', 'x', pasoDeAhora)).toEqual({ estado: 200, cuerpo: paso.cuerpo, contrato: 'v2-lectura' });
    expect(contestar('/api/v2/facturas', 'GET', 'x', pasoDeAhora).cuerpo).toEqual({ facturas: [{ id: 7 }] });
    expect(preguntas).toBe(1);
    expect(contestar(LECTURA, 'GET', 'x', () => null).cuerpo).toEqual({ lectura: null });
  });
});

describe('la vista previa: lo que corre en la pagina publicada', () => {
  // Lo mismo que no puede usar la app (tests/test_app_local.py, PROHIBIDO), sin comentarios.
  const PROHIBIDO = ['dangerouslySetInnerHTML', 'innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function', 'Function(', 'srcdoc', 'javascript:', 'sessionStorage', 'document.cookie', 'pushState(', 'replaceState('];
  const sinComentarios = (texto) => texto.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '');
  const pagina = ['entrada.js', 'shim.js', 'rutas.js', 'textos-vp.js', 'cuerpo.html', 'banda-por-defecto.html', 'vista-previa.css'];

  it('no interpreta HTML ni guarda nada', () => {
    const usados = [];
    for (const nombre of pagina) {
      const texto = sinComentarios(readFileSync(join(vistaPrevia, 'src', nombre), 'utf8'));
      for (const p of PROHIBIDO) if (texto.includes(p)) usados.push(`${nombre}: ${p}`);
    }
    expect(usados).toEqual([]);
  });

  it('no nombra ninguna direccion de fuera (el shim contesta /api con lo grabado)', () => {
    const fuera = [];
    for (const nombre of pagina) {
      const texto = readFileSync(join(vistaPrevia, 'src', nombre), 'utf8');
      for (const m of texto.matchAll(/(?:https?:)?\/\/[a-z0-9.-]+\.[a-z]{2,}/gi)) fuera.push(`${nombre}: ${m[0]}`);
      if (/url\(\s*["']?(?!data:)/i.test(texto)) fuera.push(`${nombre}: url()`);
    }
    expect(fuera).toEqual([]);
  });
});

describe('las herramientas: el repo y los argumentos', () => {
  it('por defecto, el repo que las lleva', () => {
    expect(REPO).toBe(join(frontend, '..'));
    expect(existsSync(join(REPO, 'frontend', 'herramientas', 'entorno.mjs'))).toBe(true);
  });

  it('--clave valor y --bandera', () => {
    expect(argumentos(['--solo', 'iframe', '--rapida', '--anchos', '1440', 'suelto'])).toEqual({ _: ['suelto'], solo: 'iframe', rapida: true, anchos: '1440' });
  });
});
