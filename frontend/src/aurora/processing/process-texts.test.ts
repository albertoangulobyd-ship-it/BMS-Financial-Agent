// Lo que dice Procesar en cada estado (especificacion §5.4): el saludo, la nota y las lineas de
// cada etapa, con las cifras de la lectura (dolares en millonesimas, horas de Amsterdam), en los
// tres idiomas, con su singular.
import { describe, expect, it } from 'vitest';
import { MESSAGES } from '@/i18n';
import type { ReadingPass, ReadingRequest, ReadingStatus } from '@/lib/api-types';
import {
  cardState,
  completeNote,
  completeView,
  entryText,
  errorView,
  footerOf,
  idleLines,
  introView,
  lastReading,
  readyNote,
  reasonOf,
  requestNote,
  rowTexts,
  stageLabel,
  whenOf,
} from './process-texts';
import { outcomeOf } from './reading-model';

const es = MESSAGES.es;
const NBSP = ' ';
const NOW = new Date('2026-10-28T12:00:00Z');

function request(estado: ReadingRequest['estado'], extra: Partial<ReadingRequest> = {}): ReadingRequest {
  return {
    id: 7,
    estado,
    origen: 'app',
    viva: ['pedida', 'comprobando', 'contando', 'esperando_aprobacion', 'aprobada', 'leyendo'].includes(estado),
    abandonada: false,
    pedida_por: { id: 1, nombre: 'Ana Demo' },
    pedida_en: '2026-10-28T09:12:00+00:00',
    tomada_en: null,
    motivo: null,
    motivo_codigo: null,
    pdf_nuevos: 12,
    pdf_ya_leidos: 3,
    coste_min_usd_micro: 684_000,
    coste_max_usd_micro: 745_000,
    huella_estimacion: 'abc',
    contada_en: null,
    caduca_en: '2026-10-28T09:27:00+00:00',
    aprobada_por: null,
    aprobada_en: null,
    aprobada_via: null,
    tope_usd_micro: 745_000,
    cancelada_en: null,
    parar_pedido: false,
    terminada_en: '2026-10-28T09:41:00+00:00',
    ...extra,
  };
}

function pass(fase: ReadingPass['fase'], extra: Partial<ReadingPass> = {}): ReadingPass {
  return {
    solicitud_id: 7,
    fase,
    terminada: false,
    total: 12,
    leidas: 0,
    ya_leidas: 0,
    fallidas: 0,
    coste_usd_micro: 210_000,
    documento_actual: null,
    documento_fase: null,
    recientes: [],
    fases: [],
    motivo: null,
    empezada_en: null,
    terminada_en: '2026-10-28T09:41:00+00:00',
    resultado: [],
    ...extra,
  };
}

function status(solicitud: ReadingRequest | null, pasada: ReadingPass | null = null, ultima: ReadingPass | null = null): ReadingStatus {
  return {
    modelo: 'claude',
    extracciones: 4,
    documentos: 4,
    coste_usd_micro: 3_420_000,
    por_documento_usd_micro: 60_000,
    ultima: null,
    pasadas: [],
    estimacion: { por_documento_bajo_usd_micro: 57_000, por_documento_alto_usd_micro: 62_000, medida: true },
    lee_aqui: false,
    solicitud,
    pasada_en_curso: pasada,
    ultima_pasada: ultima,
  };
}

describe('el saludo de cada estado (especificacion §5.4)', () => {
  it('P0, el de Aurora', () => {
    expect(introView('ready', null, es)).toEqual({ phase: 'intro', title: 'Déjame revisar tus facturas.', detail: es.aurora.process.ready.line });
  });

  it('P1 nombra el acceso directo del escritorio, como nombre propio', () => {
    const v = introView('requested', status(request('pedida')), es);
    expect(v.title).toBe('Abre «BMS Finanzas - Leer facturas» en el escritorio.');
    expect(v.properName).toBe('BMS Finanzas - Leer facturas');
    expect(introView('requested', null, MESSAGES.nl).title).toBe('Open “BMS Finanzas - Leer facturas” op het bureaublad.');
  });

  it('P2 comprobando y contando', () => {
    expect(introView('checking', null, es).title).toBe('Comprobando la conexión…');
    expect(introView('counting', null, es).detail).toBe('Contar es gratis.');
  });

  it('P3: las facturas nuevas, la horquilla del lote y el plazo, en la hora de Amsterdam', () => {
    const v = introView('waiting', status(request('esperando_aprobacion')), es);
    expect(v.title).toBe(`12 facturas nuevas, entre $${NBSP}0,68 y $${NBSP}0,75.`);
    expect(v.detail).toBe('3 ya leídas no se vuelven a pagar. Tienes hasta las 10:27 para decidir.');
    const one = introView('waiting', status(request('esperando_aprobacion', { pdf_nuevos: 1, pdf_ya_leidos: 1 })), es);
    expect(one.title).toBe(`1 factura nueva, entre $${NBSP}0,68 y $${NBSP}0,75.`);
    expect(one.detail).toBe('1 ya leída no se vuelve a pagar. Tienes hasta las 10:27 para decidir.');
    expect(introView('waiting', status(request('esperando_aprobacion', { pdf_ya_leidos: 0 })), es).detail).toBe('Tienes hasta las 10:27 para decidir.');
  });

  it('P3 con un 409 (la estimacion cambio) y sin respuesta del servidor', () => {
    const changed = introView('waiting', status(request('esperando_aprobacion', { pdf_nuevos: 13 })), es, 'changed');
    expect(changed.title).toBe(`Ha cambiado: 13 facturas nuevas, entre $${NBSP}0,68 y $${NBSP}0,75.`);
    expect(changed.detail).toBe('Míralo otra vez antes de empezar. Tienes hasta las 10:27.');
    const failed = introView('waiting', status(request('esperando_aprobacion')), es, 'sendFailed');
    expect(failed).toMatchObject({ detail: 'No he podido mandar tu sí. Prueba otra vez.', alert: true });
  });

  it('P7 y P8', () => {
    expect(introView('expired', null, es).title).toBe('Nadie respondió en 15 minutos.');
    expect(introView('cancelled', null, es).detail).toBe('El lector apagó la salida. No se ha gastado nada.');
    expect(introView('nothing', status(request('nada_que_leer', { motivo_codigo: 'ya_leidas' })), es).detail).toBe('Las 3 que hay ya están leídas: no se paga nada.');
    expect(introView('nothing', status(request('nada_que_leer', { motivo_codigo: 'buzon_vacio' })), es).detail).toBe('No hay ningún PDF en el buzón: no se paga nada.');
  });
});

describe('la tarjeta y la nota', () => {
  it('la etiqueta y las dos lineas sin empezar', () => {
    expect(cardState('requested', false, es)).toBe('ESPERANDO AL LECTOR');
    expect(cardState('waiting', false, es)).toBe('LISTA PARA EMPEZAR');
    expect(cardState('waiting', true, es)).toBe('EN PROCESO');
    expect(idleLines('waiting', es)).toEqual(['Una búsqueda a la vez.', 'La revisión comienza cuando pulses Empezar.']);
    expect(idleLines('ready', es)[0]).toBe('Leer un PDF cuesta unos céntimos.');
  });

  it('P0: lo gastado hasta hoy, cada factura a la milesima y como acabo la ultima', () => {
    const last = pass('hecha', {
      resultado: [
        { documento_id: 1, nombre: 'a.pdf', estado: 'nueva' },
        { documento_id: 2, nombre: 'b.pdf', estado: 'ya_leida' },
      ],
    });
    const lines = readyNote(status(request('hecha'), last, last), es, true, NOW);
    expect(lines).toEqual([
      `Gastado hasta hoy: $${NBSP}3,42 · Cada factura, entre $${NBSP}0,057 y $${NBSP}0,062`,
      'La última lectura: hoy a las 10:41 · 1 nueva, 1 repetida.',
    ]);
    expect(readyNote(status(null), es, false, NOW)[0]).toBe('Pedir una lectura lo hace quien puede importar datos.');
    const failed = lastReading(status(request('fallida', { motivo_codigo: 'aislamiento' })), es, NOW);
    expect(failed).toBe('La última lectura no terminó (hoy a las 10:41): El aislamiento no está bien: no se ha leído ni pagado nada. Ejecuta comprobar.bat.');
    expect(whenOf('2026-10-27T09:41:00+00:00', es, NOW)).toBe('27-10-2026 a las 10:41');
  });

  it('P1 a P3: quien la pidio y cuando (o el lector)', () => {
    expect(requestNote(status(request('pedida')), es)).toBe('Pedida por Ana Demo a las 10:12');
    expect(requestNote(status(request('comprobando', { pedida_por: null, origen: 'lector', tomada_en: '2026-10-28T09:13:00+00:00' })), es)).toBe(
      'Pedida desde el lector a las 10:13'
    );
  });

  it('las etapas: los titulos de Aurora y sus lineas con los datos de verdad', () => {
    const s = status(request('leyendo'), pass('leyendo', { leidas: 2, ya_leidas: 1 }));
    expect(stageLabel(0, s, es)).toEqual(['Cargando las facturas', 'Preparando las 12 facturas nuevas.']);
    expect(stageLabel(1, s, es)).toEqual(['Leyendo los datos', 'Leyendo 3 de 12. Identificando referencias, empresas e importes.']);
    expect(stageLabel(2, s, es)[0]).toBe('Comparando los expedientes');
    expect(stageLabel(3, s, es)[1]).toBe('Separando nuevas facturas de las repetidas.');
    expect(stageLabel(4, s, es)).toEqual(['Organizando los resultados', 'Actualizando los expedientes y sus avisos.']);
    expect(stageLabel(0, status(request('aprobada', { pdf_nuevos: 1 })), es)[1]).toBe('Preparando la factura nueva.');
    expect(footerOf(s, es)).toBe(`LECTURA REAL · 12 FACTURAS · GASTADO $${NBSP}0,21`);
  });

  it('las lineas de la lectura en cada idioma', () => {
    expect(rowTexts(es).phases.guardando).toBe('guardando…');
    expect(rowTexts(MESSAGES.nl).done).toBe('klaar');
    expect(rowTexts(MESSAGES.en).phases.leyendo).toBe('reading…');
  });
});

describe('el resultado y el error', () => {
  it('P5: el saludo de Aurora con el numero de facturas, y la nota con el tope o la parada', () => {
    const done = pass('hecha', { resultado: [{ documento_id: 1, nombre: 'a.pdf', estado: 'nueva', numero: 'F-1', empresa: 'Uno' }] });
    expect(completeView(outcomeOf(done), es)).toMatchObject({ title: 'He finalizado con el análisis.', detail: 'Revisé 1 factura. Esto es lo que encontré.' });
    expect(entryText({ documento_id: 1, nombre: 'a', estado: 'posible_duplicado' }, es)).toBe('Posible duplicado');
    expect(completeNote(status(request('hecha'), pass('hecha', { leidas: 12 })), es)).toEqual(['Las repetidas se señalaron sin crear otra copia.']);
    expect(completeNote(status(request('hecha'), pass('tope', { leidas: 11 })), es)[1]).toBe(`Paré en el tope de $${NBSP}0,75 que aprobaste: leí 11 de 12.`);
    expect(completeNote(status(request('cancelada'), pass('cancelada', { leidas: 5 })), es)[1]).toBe('Paraste la lectura: leí 5 de 12.');
  });

  it('P6: nada leido, o una parte, con el por que de su codigo', () => {
    expect(errorView(status(request('fallida', { motivo_codigo: 'aislamiento' })), es)).toMatchObject({
      title: 'No se ha leído nada.',
      detail: 'El aislamiento no está bien: no se ha leído ni pagado nada. Ejecuta comprobar.bat.',
    });
    expect(errorView(status(request('fallida', { motivo_codigo: 'lectura' }), pass('fallida', { leidas: 4 })), es)).toMatchObject({
      title: 'La lectura no terminó.',
      detail: 'La lectura ha fallado. Lo ya leído (4) está en Documentos.',
    });
    expect(reasonOf('no_existe', es)).toBe('El lector no ha podido terminar.');
    expect(reasonOf(null, MESSAGES.en)).toBe('The reader could not finish.');
  });
});
