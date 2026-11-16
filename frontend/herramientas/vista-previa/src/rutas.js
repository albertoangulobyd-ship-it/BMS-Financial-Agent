// Que contesta la vista previa a cada peticion de la app, sin tocar la pagina: lo usa el shim
// (src/shim.js), que lo convierte en un Response, y lo prueba frontend/scripts/herramientas.test.mjs.
// `clave` es tambien la que usa grabar.mjs (por comun.mjs) para guardar cada respuesta: asi lo
// que se graba y lo que se busca se nombran igual.

export const LECTURA = '/api/v2/lectura';
const ES_DESCARGA = /^\/api\/v2\/(facturas|documentos)\/\d+\/original$|^\/api\/v2\/btw\/\d{4}-T[1-4]\/hoja\.csv$/;
const NO_SE_GUARDA =
  'VOORBEELD: in deze voorbeeldweergave worden acties niet uitgevoerd of opgeslagen. · PREVIEW: actions are not carried out or saved in this preview.';
const NO_SE_DESCARGA =
  'VOORBEELD: downloaden kan niet in deze voorbeeldweergave. · PREVIEW: downloads are not available in this preview.';

/** La clave de un GET: la ruta sin barra final y la consulta con sus parametros en orden. */
export function clave(url) {
  const [ruta = '', consulta = ''] = url.split('?', 2);
  const limpia = ruta.replace(/\/+$/, '') || '/';
  const pares = [...new URLSearchParams(consulta)].sort((a, b) => (a[0] + '\0' + a[1] < b[0] + '\0' + b[1] ? -1 : 1));
  const q = new URLSearchParams(pares).toString();
  return q ? `${limpia}?${q}` : limpia;
}

/** La ruta y la consulta de lo que se pide, sin el origen ni el fragmento. */
export function rutaDe(input) {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  return url.replace(/^[a-z][a-z0-9+.-]*:\/\/[^/]*/i, '').replace(/#.*$/, '');
}

/**
 * El que contesta con lo grabado (grabacion.json: `contrato`, `respuestas`, `descargas`).
 * Devuelve (url, metodo, token, pasoDeAhora) => { estado, cuerpo, contrato } y, ademas,
 * `aviso: true` si la pagina debe decir que la orden no se guarda, o `sinGrabar: <clave>` si la
 * app pidio algo que no se grabo. `pasoDeAhora()` es el paso de la lectura grabada que toca (o
 * null): solo se pregunta por /api/v2/lectura.
 */
export function crearContestador(datos) {
  const descargas = new Set(datos.descargas);
  const contrato = datos.contrato;
  return (url, metodo, token, pasoDeAhora = () => null) => {
    if (!token || !token.trim()) return { estado: 401, cuerpo: { error: 'falta un token personal valido en X-BMS-Token', codigo: 'sin_token' }, contrato };
    if (metodo !== 'GET' && metodo !== 'HEAD') {
      return { estado: 409, cuerpo: { error: NO_SE_GUARDA, tipo: 'VistaPrevia', codigo: 'vista_previa' }, contrato, aviso: true };
    }
    const k = clave(url);
    const paso = k === LECTURA ? pasoDeAhora() : null;
    if (paso) return { estado: paso.estado, cuerpo: paso.cuerpo, contrato: paso.contrato ?? contrato };
    const grabada = datos.respuestas[k];
    if (grabada) return { estado: grabada.estado, cuerpo: grabada.cuerpo, contrato: grabada.contrato ?? contrato };
    const ruta = k.split('?')[0] ?? k;
    if (descargas.has(ruta) || ES_DESCARGA.test(ruta)) {
      return { estado: 409, cuerpo: { error: NO_SE_DESCARGA, tipo: 'VistaPrevia', codigo: 'vista_previa_descarga' }, contrato };
    }
    return {
      estado: 404,
      cuerpo: { error: 'no existe (niet opgenomen in de voorbeeldweergave · not recorded in the preview)', codigo: 'no_grabado' },
      contrato,
      sinGrabar: k,
    };
  };
}
