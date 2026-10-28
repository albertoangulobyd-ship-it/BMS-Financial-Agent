// La hoja de una factura (E6-h, especificacion §2.3): las filas de "Lo que se puede hacer", el
// orden de los hallazgos, un importe tecleado y un pago propuesto de la ficha.
import { describe, expect, it } from 'vitest';
import type { Finding, InvoiceDetail, InvoicePayment } from '@/lib/api-types';
import { asProposal, sheetRows, sortFindings, toScaled } from './sheet-model';

const finding = (id: number, estado: string, severidad: string): Finding => ({ id, estado, severidad, regla: `R${id}` }) as unknown as Finding;
const payment = (id: number, estado: string, extra: Partial<InvoicePayment> = {}): InvoicePayment =>
  ({ id, rev: 1, estado, fuente: 'banco', metodo: null, importe_cent: 1000, fecha_pago: '2026-10-01', movimiento_id: 5, regla: 'referencia+importe', concepto: 'F-1', contraparte: 'X', ...extra }) as InvoicePayment;
const invoice = (extra: Partial<InvoiceDetail> = {}): InvoiceDetail =>
  ({
    id: 7,
    rev: 3,
    numero: 'F-1',
    sentido: 'entrante',
    contraparte: 'X',
    anulada: false,
    campos: [{ campo: 'total_cent', valor: 12100 }],
    estado: { estado_revision: 'pendiente', pendiente_cent: 12100, estado_pago: 'pendiente' },
    vencimiento: { fecha: '2026-11-01' },
    hallazgos: [],
    pagos: [],
    relaciones: [],
    excepcion: null,
    ...extra,
  }) as unknown as InvoiceDetail;

describe('la hoja de una factura', () => {
  it('lo abierto antes que lo desaparecido y lo aceptado; lo mas grave primero', () => {
    const order = sortFindings([finding(1, 'aceptado', 'bloqueo'), finding(2, 'abierto', 'aviso'), finding(3, 'desaparecido', 'bloqueo'), finding(4, 'abierto', 'bloqueo')]);
    expect(order.map((h) => h.id)).toEqual([4, 2, 3, 1]);
  });

  it('una fila por cosa pendiente, de la mas urgente a la menos, y siempre los datos y los pagos', () => {
    const f = invoice({
      hallazgos: [finding(1, 'aceptado', 'bloqueo'), finding(2, 'abierto', 'aviso'), finding(3, 'desaparecido', 'bloqueo')],
      pagos: [payment(8, 'propuesta'), payment(9, 'confirmada')],
      relaciones: [{ id: 4, estado: 'propuesta', retirada: false }, { id: 5, estado: 'confirmada', retirada: false }] as never,
      excepcion: { id: 6, estado: 'abierta' } as never,
    });
    expect(sheetRows(f).map((r) => r.key)).toEqual(['h2', 'h3', 'p8', 'r4', 'exception', 'review', 'read', 'more']);
    // Revisada, sin nada pendiente: solo las dos de siempre.
    expect(sheetRows(invoice({ estado: { estado_revision: 'revisada' } as never })).map((r) => r.key)).toEqual(['read', 'more']);
    // Una excepcion resuelta no es una fila; una factura anulada no pide revision.
    expect(sheetRows(invoice({ anulada: true, excepcion: { id: 6, estado: 'resuelta' } as never })).map((r) => r.key)).toEqual(['read', 'more']);
  });

  it('un importe tecleado con la escala de su campo, sin decimales de coma flotante', () => {
    expect(toScaled('2902,79', 2)).toBe('290279');
    expect(toScaled('1.234,5', 2)).toBe('123450');
    expect(toScaled('-0,5', 2)).toBe('-50');
    expect(toScaled('12,345', 2)).toBeNull();
    expect(toScaled('abc', 2)).toBeNull();
  });

  it('un pago propuesto de la ficha lleva sus tres coincidencias y su linea del banco', () => {
    const p = asProposal(payment(8, 'propuesta', { movimiento_fecha: '2026-10-02', movimiento_importe_cent: -1000 }), invoice());
    expect(p.coincidencias).toEqual({ referencia: true, importe: true, contraparte: false });
    expect(p.lado).toBe('pago');
    expect(p.factura).toMatchObject({ id: 7, total_cent: 12100, pendiente_cent: 12100 });
    expect(p.movimiento).toMatchObject({ id: 5, fecha: '2026-10-02', importe_cent: -1000 });
    expect(asProposal(payment(9, 'propuesta', { movimiento_id: null }), invoice()).movimiento).toBeNull();
  });
});
