// Lo que contestan las lecturas que usan las pantallas del trabajo diario, con las claves
// tal cual las da la API (docs/integracion-web.md). Solo lo que la app lee; lo demas que
// venga se ignora. Los textos en castellano (titulo, detalle, etiqueta, fuente_texto,
// motivos) estan en la respuesta pero la app no los pinta.

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

/** Un hallazgo pendiente en una lista ("por que"): contrato 2.1. */
export interface Reason {
  id: number;
  regla: string;
  severidad: string;
  estado: string;
  resultado: string;
  valores: Json;
}

export interface FieldInfo {
  tabla: string;
  fila_id: number;
  campo: string;
  tipo: string;
  valor: Json;
  entrada: string | null;
  fuente: string | null;
  original: Json;
  editado: boolean;
  suplementado: boolean;
  corregido: boolean;
  sin_resolver: boolean;
  dudoso: boolean;
  verificado: boolean;
  calidad: string | null;
  cambiado_por: string | null;
  cambiado_en: string | null;
  verificado_por: string | null;
  editable: boolean;
  critico: boolean;
  obligatorio: boolean;
  revertible: boolean;
  motivo: string | null;
}

export interface Finding {
  id: number;
  clave: string;
  regla: string;
  severidad: string;
  estado: string;
  huella: string;
  anulable: boolean;
  pegajosa: boolean;
  calidad: string | null;
  segunda_firma: boolean;
  primera_vez_en: string | null;
  objetivos: { tabla: string; fila_id: number; campo: string | null; papel: string }[];
  resultado: string;
  valores: Json;
}

export interface NoDataRule {
  regla: string;
  clave: string;
  resultado: string;
  valores: Json;
}

export interface ExceptionInfo {
  id: number;
  rev: number;
  titulo: string;
  tabla: string;
  fila_id: number;
  factura_id: number | null;
  estado: string;
  responsable_id: number | null;
  responsable: string | null;
  esperando_a: string | null;
  fecha_seguimiento: string | null;
  creada_en: string | null;
  creada_por: string | null;
  hallazgos?: number[];
}

/** Una fila de GET /api/v2/excepciones. */
export interface ExceptionRow extends ExceptionInfo {
  nivel: string;
  vencimiento: string | null;
  importe_cent: number | null;
  razones: Reason[];
}

export interface LineInfo {
  id: number;
  rev: number;
  orden: number;
  retirada: boolean;
  campos: FieldInfo[];
  imputaciones: {
    id: number;
    retirada: boolean;
    objeto: string | null;
    orden_compra: string | null;
    recurso: string | null;
  }[];
}

export interface RelationInfo {
  id: number;
  rev: number;
  tipo: string;
  estado: string;
  fuente: string;
  importe_cent: number | null;
  origen_id: number;
  origen_numero: string | null;
  destino_id: number;
  destino_numero: string | null;
  evidencia_doc: string | null;
  retirada: boolean;
  mueve: boolean;
  papel: 'origen' | 'destino';
}

export interface ShiftInfo {
  id_externo: string;
  fecha: string;
  hora_inicio: string | null;
  hora_fin: string | null;
  estado: string;
  horas_turno_mil: number | null;
  horas_asignadas_mil: number | null;
  objeto: string | null;
  recurso: string | null;
}

export interface InvoiceState {
  estado_pago: string | null;
  pendiente_cent: number | null;
  vencimiento: string | null;
  dias_vencida: number | null;
  estado_revision: string | null;
  calidad: string | null;
  sin_resolver: number;
  dudosos: number;
  pendientes: number;
  sin_datos: number;
  nivel: string;
  puntos: number;
}

/** GET /api/v2/facturas/N (la ficha). */
export interface InvoiceDetail {
  id: number;
  rev: number;
  sentido: 'entrante' | 'saliente';
  numero: string | null;
  contraparte: string | null;
  anulada: boolean;
  fusionada_en_id: number | null;
  notas_doc: string | null;
  huella_contenido: string;
  campos: FieldInfo[];
  lineas: LineInfo[];
  referencias: { id: number; etiqueta: string | null; valor: string | null; clase: string | null; retirada: boolean }[];
  hallazgos: Finding[];
  reglas_sin_datos: NoDataRule[];
  excepcion: ExceptionInfo | null;
  estado: InvoiceState | null;
  pide_revision: string[];
  revisiones: { id: number; resultado: string; usuario: string | null; en: string; nota: string | null; vigente: boolean }[];
  notas: { id: number; texto: string; usuario: string | null; en: string }[];
  relaciones: RelationInfo[];
  conciliacion: { imputacion_id: number; nivel: string; horas_mil: number | null; turnos: ShiftInfo[] }[];
  original: { documento_id: number; nombre: string | null; tipo: string | null; bytes: number | null; guardado: boolean } | null;
  vencimiento: { fecha: string | null; fuente: string | null; plazo_dias: number | null } | null;
}

/** GET /api/v2/facturas/N/historial. */
export interface InvoiceHistory {
  documento: { recibido_en: string | null; registrado_en: string | null; nombre: string | null } | null;
  extracciones: { id: number; extraido_en: string | null; vigente: boolean }[];
  eventos: {
    id: number;
    en: string;
    tipo: string;
    usuario: string | null;
    persona: boolean;
    motivo: string | null;
    cambios: {
      tabla: string;
      campo: string;
      anterior_texto: string | null;
      nuevo_texto: string | null;
    }[];
  }[];
  revisiones: { id: number; resultado: string; usuario: string | null; en: string; nota: string | null }[];
  hallazgos: {
    id: number;
    regla: string;
    eventos: { tipo: string; estado: string; en: string; usuario: string | null; nota: string | null }[];
  }[];
  excepciones: { id: number; estado: string; creada_en: string | null; resuelta_en: string | null; resuelta_por: string | null; resolucion: string | null }[];
  notas: { id: number; texto: string; usuario: string | null; en: string }[];
}

export interface Person {
  id: number;
  nombre: string;
}

/** Una cuenta del registro (GET /api/v2/cuentas). */
export interface AccountRow {
  id: number;
  proveedor_id: number;
  proveedor: string | null;
  iban: string;
  estado: string;
  en_exact: boolean;
  pagable: boolean;
}

/** Lo que la pantalla de IBAN lee de la vista de un proveedor. */
export interface ProviderAccounts {
  id: number;
  nombre: string | null;
  telefono_verificacion: string | null;
}
