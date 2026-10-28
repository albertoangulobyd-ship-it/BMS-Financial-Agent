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

export interface SecondSignature {
  solicitante_id: number;
  firmante_id: number;
  firmante: string | null;
  vigente_hasta: string | null;
  caduca_en: string;
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
  /** 2.1: las segundas firmas que ya hay y aun valen (para quien, de quien, el plazo). */
  firmas?: SecondSignature[];
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
  /** Cada pago apuntado de la factura (propuesto, confirmado o retirado), con su fuente. */
  pagos?: InvoicePayment[];
}

/** Un pago de una factura (GET /api/v2/facturas/N, `pagos`). El concepto y la contraparte
 *  son texto del banco: se pintan como texto. */
export interface InvoicePayment {
  id: number;
  rev: number;
  estado: 'propuesta' | 'confirmada' | 'retirada' | string;
  fuente: 'banco' | 'exact' | 'manual' | string;
  metodo: string | null;
  importe_cent: number;
  fecha_pago: string | null;
  movimiento_id: number | null;
  regla: string | null;
  concepto: string | null;
  contraparte: string | null;
  /** Contrato 2.3: quien lo confirmo o lo apunto (null: lo caso el banco solo). */
  persona?: string | null;
  confirmada_en?: string | null;
  retirada_en?: string | null;
  /** Lo que escribio esa persona: texto. */
  motivo?: string | null;
  evidencia_documento_id?: number | null;
  /** El dia y el importe de su linea del banco (con el signo del banco). */
  movimiento_fecha?: string | null;
  movimiento_importe_cent?: number | null;
  /** De uno retirado: quien y por que (texto de una persona). */
  retirada_por?: string | null;
  motivo_retirada?: string | null;
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
  /** Contrato 2.1: sus facturas sin importe en euros (otra moneda), fuera de las sumas. */
  sin_importe?: number;
  nivel: string;
  /** Contrato 2.1: los hallazgos pendientes de sus facturas y los suyos. */
  razones?: Reason[];
  /** Contrato 2.2 (paso 16): cuantos documentos tiene su carpeta. */
  documentos?: number;
  /** Contrato 2.4: lo que queda de sus facturas, la cifra de la cartera ("Openstaand"). */
  deuda_cent: number;
  /** Contrato 2.4: lo que acreditan sus abonos sin enlazar (cero o negativo), aparte. */
  abonos_sin_enlazar_cent: number;
  abonos_sin_enlazar_facturas: number;
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
  /** Contrato 2.4: como en PartyRow (la cifra de la cartera y los abonos sin enlazar). */
  deuda_cent: number;
  abonos_sin_enlazar_cent: number;
  abonos_sin_enlazar_facturas: number;
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
  // Contrato 2.2 (paso 16): lo que el maestro tiene para la ficha de la carpeta en Documentos.
  kvk?: string | null;
  email_facturacion?: string | null;
  direccion?: string | null;
  /** Las personas de contacto del maestro, las activas primero. Su telefono NO es el de
   *  verificar una cuenta (ese es telefono_verificacion). */
  contactos?: { id: number; nombre: string | null; email: string | null; telefono: string | null; funcion: string | null; activo: boolean }[];
  ordenes_compra?: PoRow[];
  documentos?: number;
  /** De un cliente: sus Objetos del maestro. */
  objetos?: { id: number; codigo: string; nombre: string | null; activo_desde: string | null; activo_hasta: string | null }[];
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

/** Un documento de la carpeta de una empresa (contrato 2.2, paso 16:
 *  GET /api/v2/clientes/N/documentos y /proveedores/N/documentos). */
export interface PartyDocument {
  id: number;
  tipo: 'factura_compra' | 'factura_venta' | 'abono_compra' | 'abono_venta' | 'justificante_pago' | 'orden_compra' | 'modificacion_po' | string;
  fecha: string | null;
  numero: string | null;
  importe_cent: number | null;
  estado_pago: string | null;
  /** El nombre del fichero tal como llego: texto de un tercero. */
  nombre: string | null;
  tipo_mime: string | null;
  bytes: number | null;
  guardado: boolean;
  sha256: string | null;
  registrado_en: string | null;
  vinculo: { tabla: string; id: number; factura_id?: number | null; orden_compra_id?: number | null; estado?: string | null; fuente?: string | null };
}

export interface PartyDocuments {
  parte: { tabla: string; id: number; nombre: string | null };
  total: number;
  documentos: PartyDocument[];
}

// ---- Cuentas por cobrar y por pagar (paso 16; contrato 2.2 y 2.3)

/** Un tramo de antiguedad de la cartera (dias de retraso desde el vencimiento). */
export interface AgeingBucket {
  clave: 'al_corriente' | '1_30' | '31_60' | '61_90' | 'mas_de_90' | 'sin_fecha';
  dias_desde: number | null;
  dias_hasta: number | null;
  vence_desde: string | null;
  vence_hasta: string | null;
  facturas: number;
  importe_cent: number;
}

/** Lo que una factura pendiente tiene en la cartera: lo que queda, su vencimiento, los dias
 *  de retraso (negativos: los que faltan) y si esta retenida y por que. */
export interface CarteraInvoice {
  id: number;
  numero: string | null;
  parte_id: number | null;
  parte: string | null;
  pendiente_cent: number;
  vencimiento: string | null;
  dias: number | null;
  retenida: boolean;
  nivel: string | null;
  razones: Reason[];
}

export interface CarteraParty {
  /** null: las facturas sin cliente (o proveedor) del maestro, juntas, al final. */
  id: number | null;
  nombre: string | null;
  facturas: number;
  vencidas: number;
  pendiente_cent: number;
  vencido_cent: number;
  retenido_cent: number;
  mas_antigua_dias: number | null;
  nivel: string | null;
  puntos: number | null;
  razones: Reason[];
  plazo_de_pago: { pagadas: number; media_dias: number | null; tarde: number } | null;
}

export interface CarteraSum {
  facturas: number;
  importe_cent: number;
}

/** GET /api/v2/cartera?sentido=saliente|entrante (`cartera`). */
export interface Cartera {
  sentido: 'saliente' | 'entrante';
  hoy: string;
  estado_del: string | null;
  al_dia: boolean;
  totales: {
    facturas: number;
    vencidas: number;
    pendiente_cent: number;
    vencido_cent: number;
    semana_cent: number;
    mes_cent: number;
    proximos_30_cent: number;
    sin_fecha_cent: number;
  };
  fechas: Record<string, [string, string] | null>;
  movido_mes_cent: number | null;
  tramos: AgeingBucket[];
  retenido: CarteraSum & { lista?: CarteraInvoice[] };
  sin_retener: CarteraSum;
  partes: CarteraParty[];
  por_confirmar: { pagos: number; importe_cent: number };
  sin_casar: { movimientos: number; importe_cent: number };
  abonos_sin_enlazar: CarteraSum & {
    lista: { id: number; numero: string | null; contraparte: string | null; parte_id: number | null; parte: string | null; fecha_factura: string | null; pendiente_cent: number }[];
  };
  sin_importe: number;
  /** Contrato 2.3: lo vencido y lo que vence hasta el domingo, retenido o no. */
  esta_semana?: { hasta: string; retenido: CarteraSum; sin_retener: CarteraSum; facturas: CarteraInvoice[] };
  /** Contrato 2.3: las facturas de este lado con un aviso de pago raro activo. */
  avisos_pago?: { regla: string; facturas: { id: number; numero: string | null; parte_id: number | null; parte: string | null }[] }[];
}

/** Un pago que el banco propuso y espera a una persona (GET /api/v2/pagos/propuestas). El
 *  texto del banco (contraparte, concepto) es de un tercero: va como texto. */
export interface PaymentProposal {
  id: number;
  rev: number;
  lado: 'cobro' | 'pago';
  importe_cent: number;
  fecha_pago: string | null;
  regla: string | null;
  coincidencias: { referencia: boolean; importe: boolean; contraparte: boolean };
  factura: {
    id: number;
    numero: string | null;
    sentido: 'entrante' | 'saliente';
    tipo: string;
    contraparte: string | null;
    proveedor_id: number | null;
    cliente_id: number | null;
    parte: string | null;
    total_cent: number | null;
    pendiente_cent: number | null;
    vencimiento: string | null;
    estado_pago: string | null;
  };
  movimiento: {
    id: number;
    fecha: string | null;
    importe_cent: number | null;
    contraparte: string | null;
    contraparte_iban: string | null;
    concepto: string | null;
    referencia: string | null;
    referencia_e2e: string | null;
  } | null;
}

/** Una linea del banco (GET /api/v2/movimientos). Importes con el signo del banco. */
export interface BankLine {
  id: number;
  fecha: string;
  fecha_valor: string | null;
  importe_cent: number | null;
  moneda: string | null;
  abierto: boolean;
  resto_cent: number | null;
  propia: boolean;
  contraparte: string | null;
  contraparte_iban: string | null;
  concepto: string | null;
  referencia: string | null;
  confirmadas: number;
  propuestas: number;
  dias: number;
}

export interface BankLines {
  hoy: string;
  total: number;
  limite: number;
  entradas: { movimientos: number; importe_cent: number; sin_casar_cent: number };
  salidas: { movimientos: number; importe_cent: number; sin_casar_cent: number };
  lista: BankLine[];
}
