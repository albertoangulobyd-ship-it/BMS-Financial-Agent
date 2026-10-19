import { describe, expect, it, vi } from 'vitest';
import { ApiError, checkId, createApiClient, downloadName, paths, vatQuarterPath } from './api';

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...headers },
  });
}

describe('el cliente de la API', () => {
  it('manda el token en su cabecera, al mismo origen, y lee el entorno', async () => {
    const fetchImpl = vi.fn(async () =>
      respond(200, { id: 1, nombre: 'Ana Demo', permisos: ['ver_facturas'] }, {
        'X-BMS-Entorno': 'demo',
        'X-BMS-Contrato': '2.0',
      })
    );
    const api = createApiClient({ token: 'bms_x', fetchImpl: fetchImpl as unknown as typeof fetch });
    const me = await api.get<{ nombre: string }>(paths.me);
    expect(me.nombre).toBe('Ana Demo');
    expect(api.environment).toBe('demo');
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v2/yo');
    expect((init.headers as Record<string, string>)['X-BMS-Token']).toBe('bms_x');
    expect(init.credentials).toBe('omit');
  });

  it('un 401 avisa (para volver a la entrada) y es unauthorized', async () => {
    const onUnauthorized = vi.fn();
    const api = createApiClient({
      token: 't',
      onUnauthorized,
      fetchImpl: (async () => respond(401, { error: 'falta un token' })) as unknown as typeof fetch,
    });
    await expect(api.get(paths.panel)).rejects.toMatchObject({ kind: 'unauthorized', status: 401 });
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it('un 409 por rev es "otra persona lo cambio"; otro 409 es un conflicto de estado', async () => {
    const stale = createApiClient({
      token: 't',
      fetchImpl: (async () => respond(409, { error: 'esta en la rev 3', tipo: 'Conflicto' })) as unknown as typeof fetch,
    });
    await expect(stale.action('fijar_campo', { rev: 2 })).rejects.toMatchObject({ kind: 'stale' });
    const state = createApiClient({
      token: 't',
      fetchImpl: (async () => respond(409, { error: 'no', tipo: 'NoRevisable' })) as unknown as typeof fetch,
    });
    await expect(state.action('marcar_revisada', {})).rejects.toMatchObject({ kind: 'conflict', type: 'NoRevisable' });
  });

  it('una orden va a /api/v2/acciones con accion, peticion_id y datos', async () => {
    const fetchImpl = vi.fn(async () => respond(200, { ok: true, diferencia: {} }));
    const api = createApiClient({ token: 't', fetchImpl: fetchImpl as unknown as typeof fetch });
    await api.action('anadir_nota', { fila_id: 3, texto: 'hola' }, { requestId: 'abc' });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v2/acciones');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      accion: 'anadir_nota',
      peticion_id: 'abc',
      datos: { fila_id: 3, texto: 'hola' },
    });
  });

  it('se niega a leer otra version mayor del contrato', async () => {
    const api = createApiClient({
      token: 't',
      fetchImpl: (async () => respond(200, {}, { 'X-BMS-Contrato': '3.0' })) as unknown as typeof fetch,
    });
    await expect(api.get(paths.panel)).rejects.toMatchObject({ kind: 'incompatible' });
  });

  it('sin servidor es unavailable; despues de salir no llama', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    });
    const api = createApiClient({ token: 't', fetchImpl: fetchImpl as unknown as typeof fetch });
    await expect(api.get(paths.panel)).rejects.toMatchObject({ kind: 'unavailable' });
    api.dispose();
    await expect(api.get(paths.panel)).rejects.toMatchObject({ kind: 'unauthorized' });
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('las rutas salen de constantes e ids comprobados', () => {
    expect(paths.invoice(12)).toBe('/api/v2/facturas/12');
    expect(() => paths.invoice(0)).toThrow(ApiError);
    expect(() => paths.invoice(1.5)).toThrow(ApiError);
    expect(() => checkId(Number.NaN)).toThrow(ApiError);
    expect(vatQuarterPath('2026-T3', '/hoja.csv')).toBe('/api/v2/btw/2026-T3/hoja.csv');
    expect(() => vatQuarterPath('../yo')).toThrow(ApiError);
  });

  it('una consulta va escapada y no admite rutas de fuera', async () => {
    const fetchImpl = vi.fn(async () => respond(200, {}));
    const api = createApiClient({ token: 't', fetchImpl: fetchImpl as unknown as typeof fetch });
    await api.get(paths.search, { texto: 'a&b=c', vacio: '', pagina: 2 });
    expect((fetchImpl.mock.calls[0] as unknown as [string])[0]).toBe('/api/v2/buscar?texto=a%26b%3Dc&pagina=2');
    await expect(api.get('https://evil.example/x')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('el nombre de una descarga', () => {
  it('sale limpio de Content-Disposition', () => {
    expect(downloadName('attachment; filename="btw-2026-T3.csv"', 'x.csv')).toBe('btw-2026-T3.csv');
    expect(downloadName('attachment; filename="../../etc/passwd"', 'x')).toBe('etcpasswd');
    expect(downloadName('attachment; filename=""', 'factura-12.pdf')).toBe('factura-12.pdf');
    expect(downloadName(null, 'factura-12.pdf')).toBe('factura-12.pdf');
  });
});
