// Lo que dijo la ultima lectura de facturas de cada documento (especificacion §2.3 y §5): nueva
// (verde) o repetida (naranja), como las marcas del archivo de Aurora (analysisStatus de
// glass-folder-cards.tsx). Sale de GET /api/v2/lectura, del `resultado` de la pasada terminada
// (`ultima_pasada`, o la de ahora si ya termino: contrato 2.5). Sin esos campos (un servidor
// anterior al 2.5) no hay marcas. Sin React: lo prueba analysis.test.ts.

export type AnalysisStatus = 'new' | 'duplicate';

export interface Analysis {
  byDocument: ReadonlyMap<number, AnalysisStatus>;
  byInvoice: ReadonlyMap<number, AnalysisStatus>;
}

export const NO_ANALYSIS: Analysis = { byDocument: new Map(), byInvoice: new Map() };

export interface PassRow {
  documento_id?: unknown;
  factura_id?: unknown;
  estado?: unknown;
}

interface Pass {
  terminada?: unknown;
  resultado?: unknown;
}

/** El estado de un documento de la pasada, en las dos marcas de Aurora (o ninguna). */
export function statusOf(estado: unknown): AnalysisStatus | null {
  if (estado === 'nueva') return 'new';
  if (estado === 'ya_leida' || estado === 'posible_duplicado') return 'duplicate';
  return null;
}

/** Las filas de la ultima pasada terminada que cuenta la lectura: la de ahora solo si ya
 *  termino; si no (una lectura pedida, leyendo, o que acabo sin leer nada), la anterior. */
export function finishedRows(reading: unknown): PassRow[] {
  const r = (reading ?? {}) as { pasada_en_curso?: Pass | null; ultima_pasada?: Pass | null };
  const current = r.pasada_en_curso && r.pasada_en_curso.terminada === true ? r.pasada_en_curso : null;
  const pass = current ?? r.ultima_pasada ?? null;
  return Array.isArray(pass?.resultado) ? (pass.resultado as PassRow[]) : [];
}

/** Las marcas de la ultima pasada terminada que cuenta la lectura. */
export function analysisOf(reading: unknown): Analysis {
  const rows = finishedRows(reading);
  const byDocument = new Map<number, AnalysisStatus>();
  const byInvoice = new Map<number, AnalysisStatus>();
  for (const row of rows) {
    const status = statusOf(row.estado);
    if (!status) continue;
    if (typeof row.documento_id === 'number') byDocument.set(row.documento_id, status);
    if (typeof row.factura_id === 'number') byInvoice.set(row.factura_id, status);
  }
  return { byDocument, byInvoice };
}

/** La marca de un documento de una carpeta: la suya o la de su factura. */
export function docAnalysis(
  analysis: Analysis,
  doc: { id: number; vinculo: { tabla: string; id: number; factura_id?: number | null } }
): AnalysisStatus | undefined {
  const own = analysis.byDocument.get(doc.id);
  if (own) return own;
  if (doc.vinculo.tabla === 'factura') return analysis.byInvoice.get(doc.vinculo.id);
  return undefined;
}
