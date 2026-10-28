// Las marcas de la ultima lectura en Documentos: nueva (verde) y repetida (naranja).
import { describe, expect, it } from 'vitest';
import { analysisOf, docAnalysis, statusOf } from './analysis';

describe('la ultima lectura', () => {
  it('nueva es verde; la misma o un posible duplicado, naranja; lo fallido, nada', () => {
    expect(statusOf('nueva')).toBe('new');
    expect(statusOf('ya_leida')).toBe('duplicate');
    expect(statusOf('posible_duplicado')).toBe('duplicate');
    expect(statusOf('fallida')).toBeNull();
    expect(statusOf('leida')).toBeNull();
  });

  it('de la pasada terminada (la de ahora si ya termino; si no, la ultima)', () => {
    const resultado = [
      { documento_id: 10, factura_id: 100, estado: 'nueva' },
      { documento_id: 11, factura_id: 101, estado: 'posible_duplicado' },
      { documento_id: 12, factura_id: null, estado: 'fallida' },
    ];
    const last = analysisOf({ ultima_pasada: { terminada: true, resultado }, pasada_en_curso: { terminada: false, resultado: [{ documento_id: 99, estado: 'nueva' }] } });
    expect([...last.byDocument]).toEqual([
      [10, 'new'],
      [11, 'duplicate'],
    ]);
    expect([...last.byInvoice]).toEqual([
      [100, 'new'],
      [101, 'duplicate'],
    ]);
    const now = analysisOf({ ultima_pasada: { resultado }, pasada_en_curso: { terminada: true, resultado: [{ documento_id: 99, estado: 'nueva' }] } });
    expect([...now.byDocument]).toEqual([[99, 'new']]);
    // Un servidor anterior al contrato 2.5: sin marcas.
    expect(analysisOf({ extracciones: 3 }).byDocument.size).toBe(0);
    expect(analysisOf(null).byInvoice.size).toBe(0);
  });

  it('un documento de una carpeta lleva la suya o la de su factura', () => {
    const a = analysisOf({ ultima_pasada: { resultado: [{ documento_id: 10, factura_id: 100, estado: 'nueva' }, { documento_id: 20, factura_id: 200, estado: 'ya_leida' }] } });
    expect(docAnalysis(a, { id: 10, vinculo: { tabla: 'factura', id: 100 } })).toBe('new');
    expect(docAnalysis(a, { id: 55, vinculo: { tabla: 'factura', id: 200 } })).toBe('duplicate');
    expect(docAnalysis(a, { id: 56, vinculo: { tabla: 'aplicacion_pago', id: 200, factura_id: 200 } })).toBeUndefined();
  });
});
