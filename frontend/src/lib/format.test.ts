import { describe, expect, it } from 'vitest';
import { MESSAGES } from '@/i18n';
import {
  MINUS,
  formatCents,
  formatDate,
  formatDateLong,
  formatDateProse,
  formatDateTime,
  formatHours,
  formatMoney,
  formatPercentFromBasisPoints,
  groupThousands,
  initials,
  parseIsoDate,
  toBigInt,
  todayIso,
} from './format';

describe('importes desde centimos', () => {
  it('escribe la notacion neerlandesa con el simbolo del euro', () => {
    expect(formatMoney(3627036)).toBe('€ 36.270,36');
    expect(formatMoney(0)).toBe('€ 0,00');
    expect(formatMoney(5)).toBe('€ 0,05');
    expect(formatMoney(100)).toBe('€ 1,00');
    expect(formatMoney(99999999)).toBe('€ 999.999,99');
    expect(formatMoney(100000000)).toBe('€ 1.000.000,00');
  });

  it('pone el signo menos de verdad delante de la cifra', () => {
    expect(formatMoney(-2476)).toBe(`€ ${MINUS}24,76`);
    expect(formatCents(-1)).toBe(`${MINUS}0,01`);
  });

  it('no pierde un centimo con importes que un float no guarda', () => {
    // 2^53 + 1 centimos no cabe en un numero de JS: como texto o BigInt, si.
    expect(formatCents('9007199254740993')).toBe('90.071.992.547.409,93');
    expect(formatCents(9007199254740993n)).toBe('90.071.992.547.409,93');
    // Un numero que ya no es exacto no se escribe como si lo fuera.
    expect(formatCents(9007199254740994)).toBeNull();
    expect(formatCents(12.5)).toBeNull();
  });

  it('sin dato no es cero', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
    expect(formatMoney('12,50')).toBe('—');
    expect(toBigInt('')).toBeNull();
  });

  it('agrupa los miles con punto', () => {
    expect(groupThousands('1')).toBe('1');
    expect(groupThousands('123')).toBe('123');
    expect(groupThousands('1234')).toBe('1.234');
    expect(groupThousands('1234567')).toBe('1.234.567');
  });
});

describe('horas desde milesimas', () => {
  it('escribe las horas como la API (sin ceros de mas)', () => {
    expect(formatHours(78500)).toBe('78,5');
    expect(formatHours(8000)).toBe('8');
    expect(formatHours(7250)).toBe('7,25');
    expect(formatHours(1333)).toBe('1,333');
    expect(formatHours(1250250)).toBe('1.250,25');
    expect(formatHours(-500)).toBe(`${MINUS}0,5`);
    expect(formatHours(null)).toBe('—');
  });

  it('escribe los porcentajes desde puntos basicos', () => {
    expect(formatPercentFromBasisPoints(2100)).toBe('21 %');
    expect(formatPercentFromBasisPoints(875)).toBe('8,75 %');
    expect(formatPercentFromBasisPoints(1050)).toBe('10,5 %');
  });
});

describe('fechas', () => {
  const nl = MESSAGES.nl;
  const en = MESSAGES.en;

  it('en tablas, dd-mm-aaaa', () => {
    expect(formatDate('2026-10-16')).toBe('16-10-2026');
    expect(formatDate('2026-01-05T08:12:00+00:00')).toBe('05-01-2026');
    expect(formatDate(null)).toBe('—');
    expect(formatDate('16-10-2026')).toBe('—');
    expect(formatDate('2026-02-30')).toBe('—');
  });

  it('en una frase, con el mes abreviado en cada idioma', () => {
    expect(formatDateProse('2026-10-16', nl)).toBe('16 okt 2026');
    expect(formatDateProse('2026-10-16', en)).toBe('16 Oct 2026');
    expect(formatDateProse('2026-03-01', nl)).toBe('1 mrt 2026');
    expect(formatDateProse('2026-05-31', en)).toBe('31 May 2026');
  });

  it('con el dia de la semana, sin depender de la zona del ordenador', () => {
    expect(formatDateLong('2026-10-19', nl)).toBe('maandag 19 oktober 2026');
    expect(formatDateLong('2026-10-16', en)).toBe('Friday 16 October 2026');
  });

  it('un instante en la hora de Amsterdam', () => {
    expect(formatDateTime('2026-10-16T08:12:00+00:00')).toBe('16-10-2026 10:12');
    expect(formatDateTime('2026-12-01T23:30:00Z')).toBe('02-12-2026 00:30');
    expect(formatDateTime('2026-10-16')).toBe('—');
  });

  it('hoy en Amsterdam, aunque en UTC aun sea ayer', () => {
    expect(todayIso(new Date('2026-10-18T22:30:00Z'))).toBe('2026-10-19');
    expect(parseIsoDate('2026-10-19')).toEqual({ year: 2026, month: 10, day: 19 });
  });
});

describe('iniciales', () => {
  it('las de las dos primeras palabras', () => {
    expect(initials('Ana Demo')).toBe('AD');
    expect(initials('  bram  de  Demo ')).toBe('BD');
    expect(initials('Ünal')).toBe('Ü');
    expect(initials('')).toBe('?');
  });
});

describe('lo que cuesta leer un pdf y los trimestres (paso 15)', () => {
  it('millonesimas de dolar al centimo, la mitad hacia arriba', async () => {
    const { formatUsdMicro } = await import('./format');
    expect(formatUsdMicro(32360)).toBe('$ 0,03');
    expect(formatUsdMicro(35000)).toBe('$ 0,04');
    expect(formatUsdMicro(517760)).toBe('$ 0,52');
    expect(formatUsdMicro(1234567890)).toBe('$ 1.234,57');
    expect(formatUsdMicro(0)).toBe('$ 0,00');
    expect(formatUsdMicro(null)).toBe('—');
    expect(formatUsdMicro(1.5)).toBe('—');
  });

  it('un trimestre va y vuelve como numero de pestana, y solo uno que existe', async () => {
    const { idToQuarter, quarterLabel, quarterToId } = await import('./format');
    expect(quarterToId('2026-T3')).toBe(20263);
    expect(idToQuarter(20263)).toBe('2026-T3');
    expect(quarterToId('2026-T5')).toBeNull();
    expect(idToQuarter(20265)).toBeNull();
    expect(idToQuarter(20260)).toBeNull();
    expect(idToQuarter(3)).toBeNull();
    expect(quarterLabel('2026-T4')).toBe('Q4 2026');
    expect(quarterLabel(null)).toBe('—');
  });
});

describe('las clases de fichero de un tipo_ambiguo', () => {
  it('solo pasan las que tienen forma de fuente y tipo', async () => {
    const { importKinds } = await import('./api');
    expect(
      importKinds([
        { fuente: 'exact', tipo: 'clientes' },
        { fuente: 'Exact', tipo: 'x' },
        { fuente: 'exact' },
        'exact/clientes',
        null,
      ])
    ).toEqual([{ fuente: 'exact', tipo: 'clientes' }]);
    expect(importKinds('nada')).toEqual([]);
  });

  it('el base64 de unos bytes, tambien de los que pasan de un trozo', async () => {
    const { toBase64 } = await import('./api');
    expect(toBase64(new TextEncoder().encode('Crediteurnummer;Naam'))).toBe(btoa('Crediteurnummer;Naam'));
    const big = new Uint8Array(70000).map((_, i) => i % 251);
    expect(atob(toBase64(big)).length).toBe(70000);
  });
});

describe('una fecha tecleada', () => {
  it('dd-mm-aaaa (o con barras, o ya en AAAA-MM-DD) a AAAA-MM-DD, solo si el dia existe', async () => {
    const { parseTypedDate } = await import('./format');
    expect(parseTypedDate('16-10-2026')).toBe('2026-10-16');
    expect(parseTypedDate(' 6/1/2027 ')).toBe('2027-01-06');
    expect(parseTypedDate('2026-10-16')).toBe('2026-10-16');
    expect(parseTypedDate('30-02-2026')).toBeNull();
    expect(parseTypedDate('10/19/2026')).toBeNull();
    expect(parseTypedDate('morgen')).toBeNull();
    expect(parseTypedDate('')).toBeNull();
  });
});
