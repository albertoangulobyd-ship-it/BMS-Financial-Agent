// El cliente de /api/v2. Todo pasa por aqui: la cabecera X-BMS-Token con el token de la
// persona (que vive solo en memoria, en este objeto), JSON, y los errores convertidos en
// tipos que la app sabe decir en neerlandes o ingles. Cada error de la API lleva un
// `codigo` estable (no_autenticado, conflicto, falta_motivo...: docs/integracion-web.md)
// del que sale el texto (i18n/domain.ts, errorText); la frase del servidor va en
// castellano y solo se ensena dentro de "Technische details".
//
// Las rutas se construyen aqui con constantes y ids numericos comprobados: ninguna URL
// sale de un dato de la API, y todas van al mismo origen.

import type { Reason } from './api-types';

export const TOKEN_HEADER = 'X-BMS-Token';
export const CONTRACT_HEADER = 'X-BMS-Contrato';
export const ENVIRONMENT_HEADER = 'X-BMS-Entorno';
/** El numero mayor del contrato v2 que esta app sabe leer (docs/integracion-web.md). */
export const CONTRACT_MAJOR = '2';

export type Environment = 'demo' | 'real';

export type ApiErrorKind =
  | 'unauthorized' // 401: sin token valido; la app vuelve a la entrada
  | 'forbidden' // 403: sin el permiso
  | 'not_found' // 404
  | 'stale' // 409 Conflicto: otra persona cambio la fila (rev) antes
  | 'conflict' // 409 por el estado (no se puede ahora)
  | 'bad_request' // 400 / 413 / 415
  | 'unavailable' // 5xx o el servidor no contesta
  | 'incompatible' // otra version mayor del contrato
  | 'invalid_response'; // lo que llego no es lo que se esperaba

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  /** El tipo de error del servidor (`tipo` en las ordenes), p. ej. "Conflicto". */
  readonly type: string | undefined;
  /** El mensaje del servidor, en castellano: solo en el desplegable de detalles tecnicos. */
  readonly detail: string | undefined;
  /** El codigo estable del error (`codigo`), del que sale el texto en NL o EN. */
  readonly code: string | undefined;

  constructor(kind: ApiErrorKind, status: number, type?: string, detail?: string, code?: string) {
    super(`${kind} (${status})`);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.type = type;
    this.detail = detail;
    this.code = code;
  }
}

/** Un id de la API que va en una ruta: entero positivo, o fuera. */
export function checkId(id: number): number {
  if (!Number.isSafeInteger(id) || id <= 0) throw new ApiError('bad_request', 0, 'id', String(id));
  return id;
}

/** Las lecturas que usa la app (LECTURAS_V2 en serve.py). */
export const paths = {
  me: '/api/v2/yo',
  panel: '/api/v2/panel',
  invoices: '/api/v2/facturas',
  invoice: (id: number) => `/api/v2/facturas/${checkId(id)}`,
  invoiceHistory: (id: number) => `/api/v2/facturas/${checkId(id)}/historial`,
  invoiceOriginal: (id: number) => `/api/v2/facturas/${checkId(id)}/original`,
  search: '/api/v2/buscar',
  exceptions: '/api/v2/excepciones',
  providers: '/api/v2/proveedores',
  provider: (id: number) => `/api/v2/proveedores/${checkId(id)}`,
  clients: '/api/v2/clientes',
  client: (id: number) => `/api/v2/clientes/${checkId(id)}`,
  objects: '/api/v2/objetos',
  object: (id: number) => `/api/v2/objetos/${checkId(id)}`,
  purchaseOrders: '/api/v2/ordenes',
  purchaseOrder: (id: number) => `/api/v2/ordenes/${checkId(id)}`,
  vat: '/api/v2/btw',
  cashFlow: '/api/v2/flujo',
  accounts: '/api/v2/cuentas',
  actions: '/api/v2/acciones',
  people: '/api/v2/personas',
  relations: '/api/v2/relaciones',
  sources: '/api/v2/fuentes',
} as const;

// Un trimestre como 2026-T3; es lo unico de una ruta que no es un id.
const QUARTER = /^\d{4}-T[1-4]$/;
export function vatQuarterPath(quarter: string, sheet: '' | '/hoja' | '/hoja.csv' = ''): string {
  if (!QUARTER.test(quarter)) throw new ApiError('bad_request', 0, 'trimestre', quarter);
  return `/api/v2/btw/${quarter}${sheet}`;
}

export type Query = Record<string, string | number | boolean | undefined | null>;

function withQuery(path: string, query?: Query): string {
  if (!path.startsWith('/api/v2/')) throw new ApiError('bad_request', 0, 'path', path);
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    params.append(key, typeof value === 'boolean' ? (value ? 'si' : 'no') : String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

// ---- tipos de lo que contestan (las claves, tal cual las da la API)

export interface Me {
  id: number;
  nombre: string;
  permisos: string[];
}

export interface MoneyBlock {
  facturas: number;
  vencidas: number;
  pendiente_cent: number;
  vencido_cent: number;
  semana_cent: number;
  mes_cent: number;
  proximos_30_cent: number;
  sin_fecha_cent: number;
}

export interface CashWindow {
  entrada_cent: number;
  salida_cent: number;
  neto_cent: number;
}

export interface OverdueList {
  facturas: number;
  pendiente_cent: number;
  sin_importe: number;
  lista: {
    id: number;
    numero: string | null;
    contraparte: string | null;
    vencimiento: string | null;
    dias: number | null;
    pendiente_cent: number | null;
  }[];
}

export interface AttentionCategory {
  clave: string;
  activos: number;
  aceptados: number;
  reglas: Record<string, number>;
  facturas: number;
  factura_ids: number[];
}

export interface PoSide {
  activas: number;
  valor_cent: number;
  consumido_cent: number;
  restante_cent: number;
}

export interface VatDeadline {
  trimestre: string;
  estado: string;
  limite_presentacion: string | null;
  dias_para_limite: number | null;
}

export interface Panel {
  contrato: string;
  hoy: string;
  estado_del: string | null;
  al_dia: boolean;
  fuentes_caducadas: { fuente: string; tipo: string; exportado: string | null; edad: number | null; limite: number | null }[];
  dinero_entra: MoneyBlock;
  dinero_sale: MoneyBlock;
  caja: {
    ventanas: Record<'vencido' | 'semana' | 'mes' | 'proximos_30' | 'total', CashWindow>;
    fechas: Record<string, [string, string] | null>;
    cobrado_mes_cent: number | null;
    pagado_mes_cent: number | null;
    estimado: { importe_cent: number; aproximado: boolean } | null;
  };
  facturacion: {
    estado: 'ok' | 'sin_datos';
    sin_facturar?: { periodos: number; valor_cent: number; horas_mil: number | null; estimado: boolean } | null;
    periodos_sin_factura?: { hallazgo_id: number; cliente_id: number | null; desde: string; hasta: string }[];
    diferencias_planning?: { hallazgos: number; aceptados: number; facturas: number; valor_cent: number };
  };
  ordenes_compra: {
    activas: number;
    cliente: PoSide;
    proveedor: PoSide;
    cerca_del_limite: { id: number; numero: string; lado: string; parte: string | null }[];
    cerca_de_caducar: { id: number; numero: string; lado: string; parte: string | null }[];
    agotamiento_previsto: { id: number; numero: string; lado: string; parte: string | null }[];
    caducadas: { id: number; numero: string; lado: string; parte: string | null }[];
  };
  btw: {
    trimestre: string;
    estado: string;
    ingresos_cent: number;
    iva_repercutido_cent: number;
    iva_deducible_cent: number;
    saldo_cent: number;
    a_pagar_cent: number;
    a_devolver_cent: number;
    limite_presentacion: string | null;
    limite_pago: string | null;
    revisar: number;
    proximo_plazo: VatDeadline | null;
    plazos_pasados: VatDeadline[];
    por_presentar: VatDeadline[];
  };
  atencion: {
    compras_vencidas: OverdueList;
    ventas_vencidas: OverdueList;
    categorias: AttentionCategory[];
    hallazgos: number;
    aceptados: number;
    excepciones: { abiertas: number; por_estado: Record<string, number> };
    bloqueadas: number;
    urgentes: number;
    atencion: number;
  };
}

/** Una fila de GET /api/v2/facturas (la lista y la busqueda). */
export interface InvoiceRow {
  id: number;
  numero: string | null;
  sentido: 'entrante' | 'saliente';
  tipo: string;
  contraparte: string | null;
  proveedor_id: number | null;
  cliente_id: number | null;
  fecha_factura: string | null;
  vencimiento: string | null;
  total_cent: number | null;
  pendiente_cent: number | null;
  estado_pago: string | null;
  estado_revision: string | null;
  nivel: string;
  cuenta: boolean;
  base_cent?: number | null;
  dias_vencida?: number | null;
  sin_resolver?: number;
  dudosos?: number;
  pendientes?: number;
  aceptados?: number;
  sin_datos?: number;
  excepcion?: { id: number; estado: string } | null;
  /** Contrato 2.1: sus hallazgos pendientes, lo mas urgente primero (el "por que"). */
  razones?: Reason[];
}

export interface ActionResult {
  ok: true;
  diferencia: Record<string, unknown>;
}

/** Lo que dice GET /api/v2/acciones de cada orden (su contrato). */
export interface ActionSpec {
  nombre: string;
  permiso: string | null;
  motivo: 'obligatorio' | 'opcional' | 'segun_campo';
  parametros: { nombre: string; tipo: string; obligatorio: boolean }[];
}

// ---- el cliente

export interface ApiClient {
  /** El entorno de la ultima respuesta (cabecera X-BMS-Entorno). */
  readonly environment: Environment;
  get<T>(path: string, query?: Query): Promise<T>;
  /** Una orden: POST /api/v2/acciones con el rev de la fila en `datos` cuando la pide. */
  action(name: string, data: Record<string, unknown>, options?: { requestId?: string }): Promise<ActionResult>;
  /** Una descarga (original, hoja del BTW): fetch con el token, Blob y a[download]. */
  download(path: string, fallbackName: string): Promise<void>;
  /** Olvida el token (al salir): lo que se pida despues da 'unauthorized' sin llamar. */
  dispose(): void;
}

export interface ApiClientOptions {
  token: string;
  /** Lo que se hace con un 401: volver a la entrada, sin el token. */
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
}

function kindFor(status: number, type: string | undefined, code?: string): ApiErrorKind {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 409) return code === 'conflicto' || type === 'Conflicto' ? 'stale' : 'conflict';
  if (status === 400 || status === 413 || status === 415) return 'bad_request';
  return 'unavailable';
}

// Un codigo es una palabra en minusculas: otra cosa no se usa para buscar su texto.
const CODE = /^[a-z_]{1,40}$/;

async function readError(response: Response): Promise<{ type?: string; detail?: string; code?: string }> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object') {
      const record = body as Record<string, unknown>;
      return {
        type: typeof record.tipo === 'string' ? record.tipo : undefined,
        detail: typeof record.error === 'string' ? record.error.slice(0, 2000) : undefined,
        code: typeof record.codigo === 'string' && CODE.test(record.codigo) ? record.codigo : undefined,
      };
    }
  } catch {
    // Un error sin JSON: basta con el codigo.
  }
  return {};
}

/** Un nombre de fichero de Content-Disposition, limpio (solo letras, cifras, ._- y espacio). */
export function downloadName(disposition: string | null, fallback: string): string {
  const match = disposition ? /filename="([^"]*)"/i.exec(disposition) : null;
  const cleaned = (match?.[1] ?? '').replace(/[^A-Za-z0-9._ -]/g, '').replace(/^[ .]+|[ .]+$/g, '');
  return cleaned.slice(0, 120) || fallback;
}

/** Un id de peticion nuevo: una orden repetida con el mismo id no se aplica dos veces. */
export function newRequestId(): string {
  return globalThis.crypto.randomUUID();
}

export function createApiClient({ token, onUnauthorized, fetchImpl }: ApiClientOptions): ApiClient {
  const doFetch = fetchImpl ?? globalThis.fetch.bind(globalThis);
  let environment: Environment = 'real';
  let current: string | null = token;

  async function send(path: string, init: RequestInit): Promise<Response> {
    if (current === null) throw new ApiError('unauthorized', 0);
    let response: Response;
    try {
      response = await doFetch(path, {
        ...init,
        headers: { ...(init.headers as Record<string, string>), [TOKEN_HEADER]: current },
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        referrerPolicy: 'no-referrer',
      });
    } catch {
      throw new ApiError('unavailable', 0);
    }
    environment = response.headers.get(ENVIRONMENT_HEADER) === 'demo' ? 'demo' : 'real';
    if (!response.ok) {
      const { type, detail, code } = await readError(response);
      if (response.status === 401) onUnauthorized?.();
      throw new ApiError(kindFor(response.status, type, code), response.status, type, detail, code);
    }
    const contract = response.headers.get(CONTRACT_HEADER);
    if (contract && contract.split('.')[0] !== CONTRACT_MAJOR) {
      throw new ApiError('incompatible', response.status, 'contrato', contract);
    }
    return response;
  }

  async function json<T>(response: Response): Promise<T> {
    if (!(response.headers.get('Content-Type') ?? '').startsWith('application/json')) {
      throw new ApiError('invalid_response', response.status);
    }
    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError('invalid_response', response.status);
    }
  }

  return {
    get environment() {
      return environment;
    },
    async get<T>(path: string, query?: Query): Promise<T> {
      const response = await send(withQuery(path, query), {
        method: 'GET',
        headers: { Accept: 'application/json' },
      });
      return json<T>(response);
    },
    async action(name, data, options) {
      const response = await send(paths.actions, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          accion: name,
          peticion_id: options?.requestId ?? newRequestId(),
          datos: data,
        }),
      });
      return json<ActionResult>(response);
    },
    async download(path, fallbackName) {
      const response = await send(withQuery(path), { method: 'GET' });
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement('a');
        link.href = url;
        link.download = downloadName(response.headers.get('Content-Disposition'), fallbackName);
        link.rel = 'noopener';
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        // Un poco despues: algunos navegadores cancelan la descarga si se revoca en el acto.
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    },
    dispose() {
      current = null;
    },
  };
}
