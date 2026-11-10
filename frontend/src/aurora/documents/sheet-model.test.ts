// La hoja de una factura (E6-h, especificacion §2.3): las filas de "Lo que se puede hacer", el
// orden de los hallazgos, un importe tecleado y un pago propuesto de la ficha.
import { describe, expect, it } from 'vitest';
import type { Finding, InvoiceDetail, InvoicePayment } from '@/lib/api-types';
import { es } from '@/i18n/es';
import { en } from '@/i18n/en';
import { nl } from '@/i18n/nl';
import { FOLD_ROWS, SHEET_SCROLL, asProposal, foldLabel, foldRows, rowsThatFit, sheetRows, sortFindings, toScaled, type SheetRow } from './sheet-model';

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

  describe('plegar lo que pasa de cuatro lineas (decision del dueno, 29-10-2026)', () => {
    const rows = (...keys: string[]): SheetRow[] =>
      keys.map((key) =>
        key.startsWith('h')
          ? ({ kind: 'finding', key, finding: finding(Number(key.slice(1)), 'abierto', 'aviso') } as SheetRow)
          : key.startsWith('p')
            ? ({ kind: 'payment', key, payment: payment(Number(key.slice(1)), 'propuesta') } as SheetRow)
            : ({ kind: key, key } as SheetRow)
      );
    const keys = (r: readonly SheetRow[]) => r.map((x) => x.key);

    it('con cuatro filas o menos, todas y sin control, plegada o no', () => {
      expect(FOLD_ROWS).toBe(4);
      for (const list of [rows('read', 'more'), rows('h1', 'review', 'read', 'more')]) {
        for (const expanded of [false, true]) {
          const fold = foldRows(list, expanded);
          expect(keys(fold.shown)).toEqual(keys(list));
          expect(fold).toMatchObject({ hidden: 0, attention: 0, foldable: false });
        }
      }
    });

    it('con mas, plegada: las tres mas urgentes y el control en la cuarta linea', () => {
      const list = rows('h1', 'h2', 'p8', 'exception', 'review', 'read', 'more');
      const fold = foldRows(list, false);
      expect(keys(fold.shown)).toEqual(['h1', 'h2', 'p8']);
      expect(fold.shown.length + 1).toBe(FOLD_ROWS);
      expect(fold).toMatchObject({ hidden: 4, foldable: true });
      // Desplegada, todas en su orden, y el control para volver a plegar.
      const open = foldRows(list, true);
      expect(keys(open.shown)).toEqual(keys(list));
      expect(open).toMatchObject({ hidden: 0, attention: 0, foldable: true });
    });

    it('lo plegado cuenta sus avisos: un hallazgo (abierto o desaparecido) o la excepcion; no un pago, la revision ni las dos de siempre', () => {
      expect(foldRows(rows('h1', 'h2', 'h3', 'h4', 'exception', 'read', 'more'), false).attention).toBe(2);
      expect(foldRows(rows('h1', 'p2', 'p3', 'p4', 'review', 'read', 'more'), false).attention).toBe(0);
      const gone = [{ kind: 'finding', key: 'h9', finding: finding(9, 'desaparecido', 'bloqueo') } as SheetRow];
      expect(foldRows([...rows('h1', 'h2', 'h3'), ...gone, ...rows('read')], false).attention).toBe(1);
    });

    it('el texto del control en los tres idiomas, en singular y en plural', () => {
      const one = foldRows(rows('h1', 'h2', 'p3', 'review', 'read', 'more'), false);
      expect(one).toMatchObject({ hidden: 3, attention: 0 });
      expect(foldLabel(es, one)).toBe('Y 3 líneas más');
      expect(foldLabel(nl, one)).toBe('En nog 3 regels');
      expect(foldLabel(en, one)).toBe('And 3 more lines');
      const alerts = foldRows(rows('h1', 'h2', 'h3', 'h4', 'exception', 'read', 'more'), false);
      expect(foldLabel(es, alerts)).toBe('Y 4 líneas más · 2 piden atención');
      expect(foldLabel(nl, alerts)).toBe('En nog 4 regels · 2 vragen aandacht');
      expect(foldLabel(en, alerts)).toBe('And 4 more lines · 2 need attention');
      const single = foldRows(rows('h1', 'h2', 'h3', 'h4', 'read'), false);
      expect(single).toMatchObject({ hidden: 2, attention: 1 });
      expect(foldLabel(es, single)).toBe('Y 2 líneas más · 1 pide atención');
      expect(foldLabel(nl, single)).toBe('En nog 2 regels · 1 vraagt aandacht');
      expect(foldLabel(en, single)).toBe('And 2 more lines · 1 needs attention');
      // Desplegada, volver a plegar.
      expect(foldLabel(es, foldRows(rows('h1', 'h2', 'h3', 'h4', 'read'), true))).toBe('Ver menos');
      expect(foldLabel(nl, foldRows(rows('h1', 'h2', 'h3', 'h4', 'read'), true))).toBe('Minder tonen');
      expect(foldLabel(en, foldRows(rows('h1', 'h2', 'h3', 'h4', 'read'), true))).toBe('Show fewer');
    });

    it('la factura de verdad: las filas de sheetRows plegadas, con los avisos de detras contados', () => {
      const f = invoice({
        hallazgos: [finding(1, 'abierto', 'bloqueo'), finding(2, 'abierto', 'aviso'), finding(3, 'abierto', 'aviso'), finding(4, 'desaparecido', 'aviso')],
        excepcion: { id: 6, estado: 'abierta' } as never,
      });
      const fold = foldRows(sheetRows(f), false);
      expect(keys(fold.shown)).toEqual(['h1', 'h2', 'h3']);
      expect(fold).toMatchObject({ hidden: 5, attention: 2 });
    });
  });

  describe('la hoja nunca se desplaza mas de 300 px, sea el dia que sea (09-11-2026)', () => {
    const rows = (...keys: string[]): SheetRow[] =>
      keys.map((key) => (key.startsWith('p') ? ({ kind: 'payment', key, payment: payment(Number(key.slice(1)), 'propuesta') } as SheetRow) : ({ kind: key, key } as SheetRow)));
    const keys = (r: readonly SheetRow[]) => r.map((x) => x.key);
    // Lo medido a 400 px (registro, «Las pruebas y el calendario»): una fila mide 74 px, 87 si su
    // nota da dos lineas; la cabecera de la tabla, 28 (el control, 27).
    const ROW = 74;
    const HEAD = 28;

    it('si cabe, nada cambia: la regla de las cuatro filas de siempre', () => {
      expect(SHEET_SCROLL).toBe(300);
      expect(rowsThatFit([ROW, ROW, ROW, ROW], 0, HEAD)).toBe(4);
      expect(rowsThatFit([ROW, ROW, ROW, ROW], -3, HEAD)).toBe(4);
      const list = rows('p1', 'review', 'read', 'more');
      expect(foldRows(list, false, Infinity)).toMatchObject({ hidden: 0, foldable: false });
      expect(foldRows(list, false, 4)).toMatchObject({ hidden: 0, foldable: false });
      // Con mas de cuatro, tres y el control, aunque quepan mas.
      expect(keys(foldRows(rows('p1', 'p2', 'review', 'read', 'more'), false, 5).shown)).toEqual(['p1', 'p2', 'review']);
    });

    it('JV-2026-006 de la base del 28-10-2026 abierta el 10-11-2026: cuatro filas y 332 px a 400 px', () => {
      // Un pago propuesto (otra linea en «Betalingen»), la nota de «Gelezen gegevens» en dos
      // lineas, el boton del original y, vencida desde el 02-11, sus dias de retraso (otra linea,
      // +18 px): 332 px. Plegada con el control, tres filas (unos 285).
      const heights = [ROW, ROW, 87, ROW];
      const n = rowsThatFit(heights, 332 - SHEET_SCROLL, HEAD);
      expect(n).toBe(3);
      const fold = foldRows(rows('p1', 'review', 'read', 'more'), false, n);
      expect(keys(fold.shown)).toEqual(['p1', 'review', 'read']);
      expect(fold).toMatchObject({ hidden: 1, attention: 0, foldable: true });
      expect(foldLabel(nl, fold)).toBe('En nog 1 regel');
      // Desplegada, todas: lo que la persona pide se ve, aunque se desplace.
      expect(foldRows(rows('p1', 'review', 'read', 'more'), true, n)).toMatchObject({ hidden: 0, foldable: true });
    });

    it('cuanto mas larga la hoja (otro dia, otro idioma, otra anchura), menos filas; al menos una', () => {
      // Ya plegada (el control ya esta): se quitan filas desde la ultima hasta liberar lo que sobra.
      expect(rowsThatFit([ROW, ROW, ROW], 10, 0)).toBe(2);
      expect(rowsThatFit([ROW, ROW, ROW], ROW + 1, 0)).toBe(1);
      expect(rowsThatFit([ROW, ROW, ROW], 1000, 0)).toBe(1);
      // Sin control aun, lo que cuesta el control tambien cuenta.
      expect(rowsThatFit([ROW, ROW], ROW - HEAD + 1, HEAD)).toBe(1);
      expect(rowsThatFit([ROW, ROW], ROW - HEAD, HEAD)).toBe(1);
      expect(rowsThatFit([ROW], 500, HEAD)).toBe(1);
      const fold = foldRows(rows('p1', 'p2', 'review', 'read', 'more'), false, 1);
      expect(keys(fold.shown)).toEqual(['p1']);
      expect(fold).toMatchObject({ hidden: 4, foldable: true });
      expect(foldRows(rows('read', 'more'), false, 0).shown).toHaveLength(1);
    });

    it('cada combinacion de filas altas y bajas y de lo que sobra: lo que se quita libera lo que sobra', () => {
      for (let count = 1; count <= 8; count += 1) {
        for (let mask = 0; mask < 1 << count; mask += 1) {
          const heights = Array.from({ length: count }, (_, i) => (mask & (1 << i) ? 87 : ROW));
          for (const control of [0, HEAD]) {
            for (let excess = 1; excess <= 700; excess += 13) {
              const n = rowsThatFit(heights, excess, control);
              expect(n).toBeGreaterThanOrEqual(1);
              expect(n).toBeLessThanOrEqual(count);
              const freed = heights.slice(n).reduce((a, b) => a + b, 0) - (n < count ? control : 0);
              // O cabe, o ya solo queda una.
              if (n > 1) expect(freed).toBeGreaterThanOrEqual(excess);
              // Y no quita una de mas.
              if (n < count) expect(freed - heights[n]!).toBeLessThan(excess);
            }
          }
        }
      }
    });
  });
});
