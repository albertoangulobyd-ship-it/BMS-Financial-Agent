// Cuentas por cobrar y por pagar sin React (paso 16): que facturas caen en cada ficha (como
// la cartera del motor, para que la lista sume lo mismo que la cifra), cuanto falta o va
// tarde una factura, el orden de las empresas y de los pagos, que se puede retirar, y como
// se lee un importe tecleado y como se manda a la API.
import { describe, expect, it } from 'vitest';
import type { InvoiceRow } from '@/lib/api';
import type { AgeingBucket, CarteraParty, InvoicePayment, PaymentProposal } from '@/lib/api-types';
import { countsFromProposals } from '@/shell/use-badges';
import {
  BUCKETS,
  bucketShares,
  byDue,
  canWithdraw,
  centsToApi,
  centsToInput,
  daysBetween,
  dueBetween,
  dueState,
  inCartera,
  isInvoiceFilter,
  isOverdue,
  linkCandidates,
  livePaymentState,
  matchesFilter,
  parseEuros,
  partiesByOverdue,
  paymentsInOrder,
  pendingSum,
  proposalsOf,
  sortsByDue,
  waitingInvoices,
  windowsOf,
  type Windows,
} from './money-model';

function row(id: number, extra: Partial<InvoiceRow> = {}): InvoiceRow {
  return {
    id,
    numero: `F-${id}`,
    sentido: 'saliente',
    tipo: 'factura',
    contraparte: 'Demo BV',
    proveedor_id: null,
    cliente_id: 1,
    fecha_factura: '2026-10-01',
    vencimiento: '2026-10-31',
    total_cent: 10_000,
    pendiente_cent: 10_000,
    estado_pago: 'pendiente',
    estado_revision: 'sin_revisar',
    nivel: 'normal',
    cuenta: true,
    ...extra,
  };
}

function bucket(clave: AgeingBucket['clave'], importe_cent: number, vence_desde: string | null, vence_hasta: string | null): AgeingBucket {
  return { clave, dias_desde: null, dias_hasta: null, vence_desde, vence_hasta, facturas: importe_cent > 0 ? 1 : 0, importe_cent };
}

// Hoy martes 27-10-2026: la semana llega al domingo 1-11 y los 30 dias al 26-11.
const windows: Windows = windowsOf({
  hoy: '2026-10-27',
  fechas: { semana: ['2026-10-27', '2026-11-01'], proximos_30: ['2026-10-27', '2026-11-25'] },
  tramos: [
    bucket('al_corriente', 30_000, '2026-10-27', null),
    bucket('1_30', 0, '2026-09-27', '2026-10-26'),
    bucket('31_60', 0, '2026-08-28', '2026-09-26'),
    bucket('61_90', 10_000, '2026-07-29', '2026-08-27'),
    bucket('mas_de_90', 0, null, '2026-07-28'),
    bucket('sin_fecha', 0, null, null),
  ],
});

function party(id: number | null, nombre: string | null, vencido: number, antigua: number | null, pendiente: number): CarteraParty {
  return {
    id,
    nombre,
    facturas: 1,
    vencidas: vencido > 0 ? 1 : 0,
    pendiente_cent: pendiente,
    vencido_cent: vencido,
    retenido_cent: 0,
    mas_antigua_dias: antigua,
    nivel: null,
    puntos: null,
    razones: [],
    plazo_de_pago: null,
  };
}

function payment(id: number, estado: string, fuente: string, fecha: string | null): InvoicePayment {
  return { id, rev: 1, estado, fuente, metodo: null, importe_cent: 100, fecha_pago: fecha, movimiento_id: null, regla: null, concepto: null, contraparte: null };
}

function proposal(id: number, facturaId: number, sentido: 'saliente' | 'entrante'): PaymentProposal {
  return {
    id,
    rev: 1,
    lado: sentido === 'saliente' ? 'cobro' : 'pago',
    importe_cent: 100,
    fecha_pago: '2026-10-27',
    regla: 'referencia+importe',
    coincidencias: { referencia: true, importe: true, contraparte: false },
    factura: {
      id: facturaId,
      numero: `F-${facturaId}`,
      sentido,
      tipo: 'factura',
      contraparte: null,
      proveedor_id: null,
      cliente_id: null,
      parte: null,
      total_cent: 100,
      pendiente_cent: 100,
      vencimiento: null,
      estado_pago: 'pendiente',
    },
    movimiento: null,
  };
}

describe('lo que la cartera cuenta', () => {
  it('es una deuda de su lado, que cuenta, en euros, con algo pendiente y sin pagar', () => {
    expect(inCartera(row(1), 'saliente')).toBe(true);
    expect(inCartera(row(1, { estado_pago: 'vencida' }), 'saliente')).toBe(true);
    expect(inCartera(row(1), 'entrante')).toBe(false);
    expect(inCartera(row(1, { cuenta: false }), 'saliente')).toBe(false);
    expect(inCartera(row(1, { estado_pago: 'pagada' }), 'saliente')).toBe(false);
    expect(inCartera(row(1, { pendiente_cent: 0 }), 'saliente')).toBe(false);
    // Sin importe en euros no suma en ningun sitio; un abono (total negativo) va aparte.
    expect(inCartera(row(1, { total_cent: null, pendiente_cent: null }), 'saliente')).toBe(false);
    expect(inCartera(row(1, { total_cent: -500, pendiente_cent: -500 }), 'saliente')).toBe(false);
  });

  it('un vencimiento cae en una ventana con sus dos extremos incluidos', () => {
    expect(dueBetween('2026-11-01', '2026-10-27', '2026-11-01')).toBe(true);
    expect(dueBetween('2026-11-02', '2026-10-27', '2026-11-01')).toBe(false);
    expect(dueBetween('2026-10-27T00:00:00', '2026-10-27', null)).toBe(true);
    expect(dueBetween(null, null, null)).toBe(false);
  });
});

describe('las fichas de la lista', () => {
  const rows = [
    row(1, { vencimiento: '2026-08-23', estado_pago: 'vencida', pendiente_cent: 10_000 }),
    row(2, { vencimiento: '2026-11-01', pendiente_cent: 5_000 }),
    row(3, { vencimiento: '2026-11-25', pendiente_cent: 7_000 }),
    row(4, { vencimiento: '2026-11-26', pendiente_cent: 9_000 }),
    row(5, { vencimiento: null, pendiente_cent: 1_000 }),
    row(6, { estado_pago: 'pagada', pendiente_cent: 0, estado_revision: 'necesita_revision' }),
    row(7, { sentido: 'entrante', vencimiento: '2026-10-30' }),
  ];
  const none = new Set<number>();
  const ids = (filter: Parameters<typeof matchesFilter>[0], waiting: ReadonlySet<number> = none) =>
    rows.filter((r) => matchesFilter(filter, r, 'saliente', windows, waiting)).map((r) => r.id);

  it('"pendiente" es toda la deuda abierta (tambien lo vencido) y suma lo de la cifra', () => {
    expect(ids('open')).toEqual([1, 2, 3, 4, 5]);
    expect(pendingSum(rows.filter((r) => matchesFilter('open', r, 'saliente', windows, none)))).toBe(32_000);
    expect(ids('vencida')).toEqual([1]);
  });

  it('"vencida" va por el hoy del motor, como los tramos, aunque la cache diga "pendiente"', () => {
    // Revision del paso 16: con la cache de la ultima pasada de otro dia, estado_pago seguia
    // en "pendiente" y la ficha se quedaba corta de lo que decia la cifra "Vervallen".
    const stale = [
      row(11, { vencimiento: '2026-10-20', estado_pago: 'pendiente' }),
      row(12, { vencimiento: '2026-10-26', estado_pago: 'pendiente' }),
      row(13, { vencimiento: '2026-10-27', estado_pago: 'pendiente' }),
      row(14, { vencimiento: '2026-08-23', estado_pago: 'vencida' }),
      row(15, { vencimiento: '2026-10-01', estado_pago: 'pagada', pendiente_cent: 0 }),
      row(16, { vencimiento: '2026-10-01', total_cent: -5_000, pendiente_cent: -5_000, estado_pago: 'pendiente' }),
    ];
    const vencidas = stale.filter((r) => matchesFilter('vencida', r, 'saliente', windows, none)).map((r) => r.id);
    expect(vencidas).toEqual([11, 12, 14]);
    // Lo mismo que los tramos de retraso (de 1 dia en adelante).
    const late = stale.filter((r) => (['1_30', '31_60', '61_90', 'mas_de_90'] as const).some((b) => matchesFilter(`tramo:${b}`, r, 'saliente', windows, none)));
    expect(late.map((r) => r.id)).toEqual(vencidas);
    // Sin la cartera todavia, la cache.
    expect(stale.filter((r) => matchesFilter('vencida', r, 'saliente', null, none)).map((r) => r.id)).toEqual([14]);
    expect(isOverdue('2026-10-26', '2026-10-27')).toBe(true);
    expect(isOverdue('2026-10-27', '2026-10-27')).toBe(false);
    expect(isOverdue(null, '2026-10-27')).toBe(false);
  });

  it('la fila dice el estado de pago con el hoy del motor', () => {
    expect(livePaymentState(row(1, { vencimiento: '2026-10-20', estado_pago: 'pendiente' }), '2026-10-27')).toBe('vencida');
    expect(livePaymentState(row(1, { vencimiento: '2026-10-27', estado_pago: 'pendiente' }), '2026-10-27')).toBe('pendiente');
    expect(livePaymentState(row(1, { vencimiento: '2026-11-20', estado_pago: 'vencida' }), '2026-10-27')).toBe('pendiente');
    expect(livePaymentState(row(1, { vencimiento: '2026-10-01', estado_pago: 'pagada', pendiente_cent: 0 }), '2026-10-27')).toBe('pagada');
    // Un abono sin enlazar no vence; sin el hoy del motor, la fila tal cual.
    expect(livePaymentState(row(1, { vencimiento: '2026-10-01', total_cent: -5_000, pendiente_cent: -5_000 }), '2026-10-27')).toBe('pendiente');
    expect(livePaymentState(row(1, { vencimiento: '2026-10-01', estado_pago: 'pendiente' }), null)).toBe('pendiente');
  });

  it('esta semana llega al domingo y los 30 dias a su ultimo dia, incluido', () => {
    expect(ids('week')).toEqual([2]);
    expect(ids('next30')).toEqual([2, 3]);
    // Sin ventanas de la cartera (aun no ha cargado) no se inventa ninguna.
    expect(rows.filter((r) => matchesFilter('week', r, 'saliente', null, none))).toEqual([]);
  });

  it('un tramo de antiguedad va por los vencimientos de la cartera', () => {
    expect(ids('tramo:61_90')).toEqual([1]);
    expect(ids('tramo:al_corriente')).toEqual([2, 3, 4]);
    expect(ids('tramo:sin_fecha')).toEqual([5]);
    expect(ids('tramo:1_30')).toEqual([]);
  });

  it('por confirmar, pagada, a revisar y todas', () => {
    expect(ids('por_confirmar', new Set([3, 6]))).toEqual([3, 6]);
    expect(ids('pagada')).toEqual([6]);
    expect(ids('necesita_revision')).toEqual([6]);
    expect(ids('all')).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it('solo valen las fichas conocidas y los tramos de la cartera', () => {
    expect(isInvoiceFilter('week')).toBe(true);
    for (const b of BUCKETS) expect(isInvoiceFilter(`tramo:${b}`)).toBe(true);
    expect(isInvoiceFilter('tramo:mas_de_900')).toBe(false);
    expect(isInvoiceFilter('pendiente')).toBe(false);
  });

  it('las fichas de pago van por vencimiento, lo sin fecha al final; las demas por prioridad', () => {
    expect(byDue([row(3, { vencimiento: null }), row(2, { vencimiento: '2026-11-01' }), row(1, { vencimiento: '2026-08-23' })]).map((r) => r.id)).toEqual([
      1, 2, 3,
    ]);
    expect(byDue([row(9), row(4)]).map((r) => r.id)).toEqual([4, 9]);
    expect(sortsByDue('open')).toBe(true);
    expect(sortsByDue('tramo:1_30')).toBe(true);
    expect(sortsByDue('all')).toBe(false);
    expect(sortsByDue('pagada')).toBe(false);
  });
});

describe('cuanto falta o va tarde', () => {
  it('cuenta dias enteros, tambien a traves del cambio de hora', () => {
    expect(daysBetween('2026-10-24', '2026-10-26')).toBe(2);
    expect(daysBetween('2026-03-28', '2026-03-30')).toBe(2);
    expect(daysBetween('2026-10-27', '2026-08-23')).toBe(-65);
  });

  it('dice tarde, hoy, cuantos dias faltan o que no tiene fecha', () => {
    expect(dueState('2026-08-23', '2026-10-27')).toEqual({ kind: 'late', days: 65 });
    expect(dueState('2026-10-27', '2026-10-27')).toEqual({ kind: 'today' });
    expect(dueState('2026-10-31', '2026-10-27')).toEqual({ kind: 'ahead', days: 4 });
    expect(dueState(null, '2026-10-27')).toEqual({ kind: 'none' });
  });
});

describe('las empresas y la barra', () => {
  it('lo vencido primero, despues lo mas antiguo y lo pendiente; sin empresa al final', () => {
    const order = partiesByOverdue([
      party(null, null, 99_999, 200, 99_999),
      party(1, 'Alfa', 0, null, 50_000),
      party(2, 'Beta', 4_000, 65, 13_000),
      party(3, 'Gamma', 4_000, 90, 5_000),
      party(4, 'Delta', 0, null, 80_000),
    ]).map((p) => p.nombre);
    expect(order).toEqual(['Gamma', 'Beta', 'Delta', 'Alfa', null]);
  });

  it('la barra mide cada tramo con algo, en milesimas, y un tramo pequeno se sigue viendo', () => {
    expect(bucketShares(windows.buckets)).toEqual([
      { clave: 'al_corriente', share: 750 },
      { clave: '61_90', share: 250 },
    ]);
    expect(bucketShares([bucket('al_corriente', 100_000, null, null), bucket('1_30', 1, null, null)])[1]).toEqual({ clave: '1_30', share: 8 });
    expect(bucketShares([bucket('al_corriente', 0, null, null)])).toEqual([]);
  });
});

describe('los pagos de una factura', () => {
  it('lo que espera arriba, luego lo que cuenta (lo reciente primero) y lo retirado al final', () => {
    const order = paymentsInOrder([
      payment(1, 'retirada', 'banco', '2026-10-27'),
      payment(2, 'confirmada', 'manual', '2026-09-01'),
      payment(3, 'confirmada', 'banco', '2026-10-01'),
      payment(4, 'propuesta', 'banco', '2026-10-20'),
    ]).map((p) => p.id);
    expect(order).toEqual([4, 3, 2, 1]);
  });

  it('se retira lo que no es de Exact y no esta retirado', () => {
    expect(canWithdraw({ estado: 'propuesta', fuente: 'banco' })).toBe(true);
    expect(canWithdraw({ estado: 'confirmada', fuente: 'manual' })).toBe(true);
    expect(canWithdraw({ estado: 'confirmada', fuente: 'exact' })).toBe(false);
    expect(canWithdraw({ estado: 'retirada', fuente: 'banco' })).toBe(false);
  });

  it('las propuestas van a su lado y marcan sus facturas; las insignias cuentan cada banco', () => {
    const list = [proposal(1, 10, 'saliente'), proposal(2, 11, 'entrante'), proposal(3, 12, 'saliente')];
    expect(proposalsOf(list, 'saliente').map((p) => p.id)).toEqual([1, 3]);
    expect([...waitingInvoices(list)]).toEqual([10, 11, 12]);
    expect(countsFromProposals(list)).toEqual({ 'bank-in': 2, 'bank-out': 1 });
    expect(countsFromProposals([])).toEqual({ 'bank-in': 0, 'bank-out': 0 });
  });
});

describe('un importe tecleado', () => {
  it('se lee con coma o punto decimal y con los miles agrupados', () => {
    expect(parseEuros('4.970,68')).toBe(497_068);
    expect(parseEuros('4970,68')).toBe(497_068);
    expect(parseEuros('4970.68')).toBe(497_068);
    expect(parseEuros('€ 4970')).toBe(497_000);
    expect(parseEuros('12,5')).toBe(1_250);
    expect(parseEuros('1.234.567,00')).toBe(123_456_700);
  });

  it('no adivina: un grupo de miles suelto, tres decimales o letras no se leen', () => {
    expect(parseEuros('1.000')).toBeNull();
    expect(parseEuros('12,345')).toBeNull();
    expect(parseEuros('12a')).toBeNull();
    expect(parseEuros('')).toBeNull();
    expect(parseEuros('-5,00')).toBeNull();
  });

  it('va a la API como texto con punto y su signo, y vuelve al campo con coma', () => {
    expect(centsToApi(497_068)).toBe('4970.68');
    expect(centsToApi(-1_250)).toBe('-12.50');
    expect(centsToApi(5)).toBe('0.05');
    expect(centsToInput(-497_068)).toBe('4970,68');
    expect(centsToInput(7)).toBe('0,07');
  });
});

describe('enlazar una linea del banco', () => {
  const invoices = [
    row(1, { numero: 'VD26-301', pendiente_cent: 120_000 }),
    row(2, { numero: 'VD26-302', pendiente_cent: 45_000 }),
    row(3, { numero: 'VD26-303', pendiente_cent: 9_999 }),
  ];
  it('ninguna se elige sola; las que parecen de la linea van primero', () => {
    // Revision del paso 16: se preseleccionaba la primera (la de mas prioridad).
    expect(linkCandidates({ resto_cent: 45_000, importe_cent: 45_000, concepto: 'Betaling', referencia: null }, invoices)).toEqual({
      likely: [invoices[1]],
      others: [invoices[0], invoices[2]],
    });
    const named = linkCandidates({ resto_cent: 1_000, importe_cent: 1_000, concepto: 'Factuur vd26 303 deel', referencia: null }, invoices);
    expect(named.likely.map((f) => f.id)).toEqual([3]);
    const none = linkCandidates({ resto_cent: 7, importe_cent: 7, concepto: null, referencia: null }, invoices);
    expect(none.likely).toEqual([]);
    expect(none.others.map((f) => f.id)).toEqual([1, 2, 3]);
  });
});
