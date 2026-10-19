// Pequenas ayudas de la ficha de una factura: encontrar un campo por su tabla, su fila y
// su nombre, y la rev de la fila de un campo (la de la factura o la de su linea).
import type { FieldInfo, InvoiceDetail } from '@/lib/api-types';

export function findField(invoice: InvoiceDetail, table: string, rowId: number, name: string): FieldInfo | undefined {
  if (table === 'factura') return invoice.campos.find((c) => c.campo === name);
  if (table === 'factura_linea') {
    return invoice.lineas.find((l) => l.id === rowId)?.campos.find((c) => c.campo === name);
  }
  return undefined;
}

/** La rev de la fila de un campo: la de la factura o la de su linea. */
export function revOf(invoice: InvoiceDetail, field: FieldInfo): number {
  if (field.tabla === 'factura_linea') return invoice.lineas.find((l) => l.id === field.fila_id)?.rev ?? invoice.rev;
  return invoice.rev;
}
