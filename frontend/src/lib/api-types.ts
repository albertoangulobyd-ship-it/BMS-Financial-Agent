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

// ---- paso 15, el resto de pantallas: proveedores, clientes, Objetos, PO, caja, btw,
// importar, la lectura de los pdf y la configuracion. Solo lo que pintan.

/** Una fila de GET /api/v2/proveedores o /api/v2/clientes. */
export interface PartyRow {
  id: number;
  nombre: string;
  exact_id: string | null;
  activo: boolean;
  facturas: number;
  pendiente_cent: number;
  vencido_cent: number;
  ano_facturado_cent: number;
  nivel: string;
  /** Contrato 2.1: los hallazgos pendientes de sus facturas y los suyos. */
  razones?: Reason[];
}

/** Un hallazgo de los `avisos` de un proveedor, un cliente o una PO. */
export interface PartyFinding {
  id: number;
  regla: string;
  severidad: string;
  estado: string;
  factura_id: number | null;
  resultado: string;
  valores: Json;
}

export interface PartyInvoice {
  id: number;
  numero: string | null;
  tipo: string;
  fecha_factura: string | null;
  vencimiento: string | null;
  total_cent: number | null;
  pendiente_cent: number | null;
  estado_pago: string | null;
  cuenta: boolean;
  sustituida: boolean;
}

/** GET /api/v2/proveedores/N y /api/v2/clientes/N (la misma forma, §3 y §4). */
export interface PartyView {
  id: number;
  nombre: string;
  exact_id: string | null;
  btw_id: string | null;
  activo: boolean;
  plazo_pago_dias: number | null;
  hoy: string;
  facturas: number;
  pendiente_cent: number;
  abiertas: number;
  vencido_cent: number;
  vencidas: number;
  ano: number;
  ano_facturado: { facturas: number; base_cent: number; total_cent: number };
  ano_pagado_cent: number;
  abiertas_detalle: { id: number; numero: string | null; vencimiento: string | null; pendiente_cent: number | null; estado_pago: string | null }[];
  por_objeto: { objeto_id: number | null; objeto: string | null; nombre: string | null; facturas: number; importe_cent: number; importe_ano_cent: number; horas_mil: number | null }[];
  plazo_de_pago: { pagadas: number; media_dias: number | null; tarde: number; media_dias_tarde: number | null };
  historial: PartyInvoice[];
  pagos: { aplicacion_id: number; factura_id: number; numero: string | null; fecha: string | null; importe_cent: number; fuente: string }[];
  avisos: { activos: number; aceptados: number; bloqueos: number; hallazgos: PartyFinding[]; excepciones: { id: number; estado: string }[] };
  prioridad: { nivel: string; puntos: number };
  ibanes?: { registro: { id: number; iban: string; estado: string; en_exact: boolean; pagable: boolean }[] };
  telefono_verificacion?: string | null;
  trabajo_sin_facturar?: {
    estado: string;
    periodos: { hallazgo_id: number; desde: string; hasta: string; horas_mil: number | null; valor_cent: number | null; estimado: boolean; objeto_id: number | null }[];
    horas_mil: number | null;
    valor_cent: number | null;
    estimado: boolean;
  };
}

/** Ingresos, costes y margen (sin IVA) de un Objeto en un periodo. */
export interface Economy {
  ingresos_cent: number;
  costes_cent: number;
  margen_cent: number;
  margen_pb: number | null;
  horas_venta_mil: number;
  horas_compra_mil: number;
}

/** Una fila de GET /api/v2/objetos (dentro de `objetos`). */
export interface ObjectRow {
  id: number;
  codigo: string;
  nombre: string | null;
  cliente_id: number | null;
  cliente: string | null;
  siempre: Economy;
  ano: Economy;
  nivel: string;
  razones?: Reason[];
}

export interface ObjectsList {
  hoy: string;
  ano: number;
  objetos: ObjectRow[];
}

export interface PoRow {
  id: number;
  numero: string;
  lado: 'cliente' | 'proveedor';
  parte: { tabla: string; id: number; nombre: string | null };
  fecha_emision: string | null;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  cerrada: boolean;
  valor_cent: number;
  consumido_cent: number;
  restante_cent: number;
  consumido_pb: number;
  restante_pb: number;
  nivel: string;
  razones?: Reason[];
}

export interface WeekHours {
  semana: string;
  cobertura: string | null;
  planificadas_mil: number | null;
  validadas_mil: number | null;
  facturables_mil: number | null;
  proveedor_mil: number | null;
  cliente_mil: number | null;
  sin_facturar_mil: number | null;
}

export interface ObjectInvoice {
  id: number;
  numero: string | null;
  contraparte: string | null;
  fecha_factura: string | null;
  estado_pago: string | null;
  cuenta: boolean;
  importe_objeto_cent: number | null;
  horas_mil: number | null;
}

/** GET /api/v2/objetos/N (§5). */
export interface ObjectView {
  id: number;
  codigo: string;
  nombre: string | null;
  cliente: { id: number; nombre: string } | null;
  requiere_po: boolean | null;
  activo_desde: string | null;
  activo_hasta: string | null;
  ordenes_compra: (PoRow & { cubre_objeto: boolean })[];
  horas: { planning: string; semanas: WeekHours[]; total: WeekHours | null };
  economia: { periodo: Economy & { desde: string; hasta: string }; ano: Economy & { ano: number }; siempre: Economy };
  facturas: { entrantes: ObjectInvoice[]; salientes: ObjectInvoice[] };
  prioridad: { nivel: string; puntos: number };
}

/** GET /api/v2/ordenes/N (§6). */
export interface PoView extends PoRow {
  hoy: string;
  fuente: string;
  valor_original_cent: number;
  fecha_fin_original: string | null;
  objetos: { id: number; codigo: string; nombre: string | null }[];
  modificaciones: { fecha?: string | null; valor_nuevo_cent?: number | null; fecha_fin_nueva?: string | null }[];
  facturas: { factura_id: number; numero: string | null; fecha_factura: string | null; importe_cent: number; quedaba_cent: number }[];
  prevision: { desde: string | null; semanas: number | null; consumido_ventana_cent: number | null; agotamiento: string | null } | null;
  planificado: { estado: string; valor_cent: number | null } | null;
  sin_facturar: { estado: string; valor_cent: number | null } | null;
  avisos: { activos: number; aceptados: number; hallazgos: PartyFinding[]; excepciones: { id: number; estado: string }[] };
  prioridad: { nivel: string; puntos: number };
}

/** Una relacion propuesta (GET /api/v2/relaciones). */
export interface ProposedRelation {
  id: number;
  rev: number;
  tipo: string;
  fuente: string;
  origen_id: number;
  destino_id: number;
  evidencia_doc: string | null;
}

// ---- caja

export type CashWindowKey = 'vencido' | 'semana' | 'mes' | 'proximos_30' | 'sin_fecha' | 'total';

export interface CashFlow {
  hoy: string;
  ventanas: Record<string, [string, string] | null>;
  esperado: Record<'entrada' | 'salida' | 'neto', Record<CashWindowKey | 'periodo', number | null>>;
  real: {
    cobrado: Record<'semana' | 'mes', number | null>;
    pagado: Record<'semana' | 'mes', number | null>;
    ventanas: Record<string, [string, string] | null>;
  };
  estimado: {
    importe_cent: number | null;
    entrada_sin_facturar_cent?: number;
    entrada_planificada_cent?: number;
    salida_sin_facturar_cent?: number;
    salida_planificada_cent?: number;
    aproximado?: boolean;
  };
  facturas: number;
}

// ---- btw

export interface VatRubric {
  rubrica: string;
  omzet_cent: number | null;
  btw_cent: number | null;
}

export interface VatFigures {
  rubricas: VatRubric[];
  '5a': number;
  '5b': number;
  '5c': number;
  ingresos_cent: number;
  iva_repercutido_cent: number;
  iva_deducible_cent: number;
  a_pagar_cent: number;
  a_devolver_cent: number;
  lineas: number;
  sin_clasificar?: { factura_id: number; numero: string | null; contraparte: string | null }[];
  fuera?: { factura_id: number; numero: string | null; contraparte: string | null }[];
}

export interface VatQuarter {
  ano: number;
  trimestre: number;
  etiqueta: string;
  inicio: string;
  fin: string;
  terminado: boolean;
  limite_presentacion: string | null;
  limite_pago: string | null;
  dias_para_limite: number | null;
  estado: string;
  rev: number | null;
  listo_por: string | null;
  presentado_en: string | null;
  presentado_por: string | null;
  referencia: string | null;
  importe_declarado_cent: number | null;
  hoja_sha256: string;
  hoja_marcada_sha256: string | null;
  hoja_al_dia: boolean;
  cifras_al_dia: boolean;
  configuracion: { sha256: string; confirmada: boolean };
  cifras: VatFigures;
  revisar: { factura_id: number; numero: string | null; contraparte: string | null; reglas: string[] }[];
  diferencias: { factura_id: number; motivo: string }[];
}

/** Un trimestre de la lista (btw.anteriores / por_presentar). */
export interface VatQuarterRow {
  ano: number;
  trimestre: number;
  etiqueta: string;
  estado: string;
  limite_presentacion: string | null;
  dias_para_limite: number | null;
  '5c': number;
  ingresos_cent: number;
}

export interface VatSummary {
  hoy: string;
  actual: VatQuarter;
  por_presentar: VatQuarterRow[];
  anteriores: VatQuarterRow[];
}

// ---- importar, la lectura de los pdf y la configuracion

export interface ImportHistoryRow {
  id: number;
  fuente: string;
  tipo: string;
  estado: string;
  filas_leidas: number;
  filas_aceptadas: number;
  filas_rechazadas: number;
  exportado_en: string | null;
  iniciada_en: string;
  persona: string | null;
  fichero: string | null;
}

export interface SourceFreshness {
  fuente: string;
  tipo: string;
  exportado: string | null;
  edad: number | null;
  unidad: string;
  limite: number | null;
  caducada: boolean | null;
}

export interface ImportsInfo {
  importaciones: ImportHistoryRow[];
  tipos: { fuente: string; tipo: string }[];
  limite_bytes: number;
  fuentes: SourceFreshness[];
}

export interface ReadingStatus {
  modelo: string;
  extracciones: number;
  documentos: number;
  coste_usd_micro: number | null;
  por_documento_usd_micro: number | null;
  ultima: string | null;
  pasadas: { desde: string | null; hasta: string | null; documentos: number; coste_usd_micro: number | null }[];
  estimacion: { por_documento_bajo_usd_micro: number; por_documento_alto_usd_micro: number; medida: boolean } | null;
  lee_aqui: boolean;
}

export interface Company {
  nombre: string;
  otros_nombres: string[];
  btw_id: string | null;
  kvk: string | null;
  cuentas_propias: string[];
  completa: boolean;
}

export interface Isolation {
  aplica: boolean;
  entorno: 'nativo' | 'contenedor' | 'local';
  correcto: boolean | null;
  /** estado (2.1): bien, falla, sin_comprobar o caducada; la pastilla sale de el. */
  papeles: { papel: string; bien: boolean; estado?: string }[];
}

export interface PersonWithRoles extends Person {
  roles?: string[];
}
