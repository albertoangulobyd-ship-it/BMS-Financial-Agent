// Procesar de verdad, sin React (especificacion §5.4 a §5.6): de GET /api/v2/lectura a lo que se
// ve (P0 a P8), a lo que se le pide al motor (setStage, finish, hide) y al techo del %. El cuerpo
// sale solo con un si aceptado por el servidor; cada fase pide su etapa, en orden; lo que acaba
// mal se funde; P5 y P6 solo en la visita en que pasan.
import { describe, expect, it } from 'vitest';
import type { ReadingPass, ReadingRequest, ReadingStatus } from '@/lib/api-types';
import {
  START,
  afterHide,
  ceilingOf,
  finished,
  outcomeOf,
  requested,
  rowsOf,
  screenOf,
  shownProgress,
  stageOf,
  update,
  type Drive,
} from './reading-model';

function request(estado: ReadingRequest['estado'], extra: Partial<ReadingRequest> = {}): ReadingRequest {
  const live = ['pedida', 'comprobando', 'contando', 'esperando_aprobacion', 'aprobada', 'leyendo'].includes(estado);
  return {
    id: 7,
    estado,
    origen: 'app',
    viva: live,
    abandonada: false,
    pedida_por: { id: 1, nombre: 'Ana Demo' },
    pedida_en: '2026-10-28T09:12:00+00:00',
    tomada_en: '2026-10-28T09:13:00+00:00',
    motivo: null,
    motivo_codigo: null,
    pdf_nuevos: 12,
    pdf_ya_leidos: 3,
    coste_min_usd_micro: 684_000,
    coste_max_usd_micro: 744_000,
    huella_estimacion: 'abc',
    contada_en: '2026-10-28T09:14:00+00:00',
    caduca_en: '2026-10-28T09:29:00+00:00',
    aprobada_por: null,
    aprobada_en: null,
    aprobada_via: null,
    tope_usd_micro: null,
    cancelada_en: null,
    parar_pedido: false,
    terminada_en: live ? null : '2026-10-28T09:41:00+00:00',
    ...extra,
  };
}

function pass(fase: ReadingPass['fase'], extra: Partial<ReadingPass> = {}): ReadingPass {
  return {
    solicitud_id: 7,
    fase,
    terminada: ['hecha', 'fallida', 'cancelada', 'tope'].includes(fase),
    total: 12,
    leidas: 0,
    ya_leidas: 0,
    fallidas: 0,
    coste_usd_micro: 0,
    documento_actual: null,
    documento_fase: null,
    recientes: [],
    fases: [],
    motivo: null,
    empezada_en: '2026-10-28T09:15:00+00:00',
    terminada_en: null,
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
    plazo_respuesta_segundos: 900,
    consulta_cada_segundos: 2,
  };
}

const run = (from: Drive, ...seen: ReadingStatus[]) => {
  let drive = from;
  const commands: string[] = [];
  for (const s of seen) {
    const r = update(drive, s);
    drive = r.drive;
    commands.push(...r.commands.map((c) => (c.kind === 'stage' ? `stage ${c.index}` : c.kind)));
  }
  return { drive, commands };
};

describe('lo que se ve segun el servidor', () => {
  it('cada estado de la peticion es un estado de la pantalla', () => {
    expect(screenOf(status(null))).toBe('ready');
    expect(screenOf(status(request('pedida')))).toBe('requested');
    expect(screenOf(status(request('comprobando')))).toBe('checking');
    expect(screenOf(status(request('contando')))).toBe('counting');
    expect(screenOf(status(request('esperando_aprobacion')))).toBe('waiting');
    expect(screenOf(status(request('aprobada')))).toBe('reading');
    expect(screenOf(status(request('leyendo'), pass('leyendo')))).toBe('reading');
    expect(screenOf(status(request('hecha'), pass('hecha')))).toBe('done');
    expect(screenOf(status(request('fallida')))).toBe('failed');
    expect(screenOf(status(request('caducada')))).toBe('expired');
    expect(screenOf(status(request('nada_que_leer')))).toBe('nothing');
  });

  it('cancelada: sin nada leido, P7; con algo leido, el resultado', () => {
    expect(screenOf(status(request('cancelada')))).toBe('cancelled');
    expect(screenOf(status(request('cancelada'), pass('cancelada', { leidas: 2 })))).toBe('done');
  });

  it('un lector que dejo de dar senales: la lectura no va a seguir', () => {
    expect(screenOf(status(request('leyendo', { abandonada: true }), pass('leyendo')))).toBe('failed');
  });

  it('la pasada de otra peticion no cuenta', () => {
    expect(stageOf(status(request('leyendo'), pass('comparando', { solicitud_id: 6 })))).toBe(0);
  });
});

describe('el techo del % (especificacion §5.5)', () => {
  it('cinco tramos de 20 que siguen a la lectura', () => {
    expect(ceilingOf(status(request('aprobada')))).toBe(20);
    expect(ceilingOf(status(request('leyendo'), pass('cargando')))).toBe(20);
    expect(ceilingOf(status(request('leyendo'), pass('leyendo', { leidas: 3 })))).toBe(25);
    expect(ceilingOf(status(request('leyendo'), pass('leyendo', { leidas: 10, ya_leidas: 1, fallidas: 1 })))).toBe(40);
    expect(ceilingOf(status(request('leyendo'), pass('comparando')))).toBe(60);
    expect(ceilingOf(status(request('leyendo'), pass('analizando')))).toBe(80);
    expect(ceilingOf(status(request('leyendo'), pass('organizando')))).toBe(99);
    expect(ceilingOf(status(request('hecha'), pass('hecha', { leidas: 12 })))).toBe(100);
  });

  it('el % que se ve es el del motor sin pasar del techo', () => {
    expect(shownProgress(37, 25)).toBe(25);
    expect(shownProgress(17, 99)).toBe(17);
    expect(shownProgress(100, 100)).toBe(100);
  });
});

describe('las lineas y el resultado', () => {
  it('las dos ultimas terminadas y la de ahora, con el formato del motor', () => {
    const texts = { done: 'listo', phases: { comparando: 'comparando…', leyendo: 'leyendo…', guardando: 'guardando…' } };
    const rows = rowsOf(pass('leyendo', { recientes: ['a.pdf', 'b.pdf', 'c.pdf'], documento_actual: 'd.pdf', documento_fase: 'guardando' }), texts);
    expect(rows.split('\n')).toEqual([`✓ ${'b.pdf'.padEnd(22)} listo`, `✓ ${'c.pdf'.padEnd(22)} listo`, `> ${'d.pdf'.padEnd(22)} guardando…`]);
    expect(rowsOf(null, texts)).toBe('');
  });

  it('nuevas, repetidas (ya leidas y posibles duplicados) y con problemas', () => {
    const o = outcomeOf(
      pass('hecha', {
        resultado: [
          { documento_id: 1, nombre: 'a.pdf', estado: 'nueva' },
          { documento_id: 2, nombre: 'b.pdf', estado: 'ya_leida' },
          { documento_id: 3, nombre: 'c.pdf', estado: 'posible_duplicado' },
          { documento_id: 4, nombre: 'd.pdf', estado: 'fallida' },
          { documento_id: 5, nombre: 'e.pdf', estado: 'leida' },
        ],
      })
    );
    expect([o.fresh, o.repeated, o.failed, o.rows.length]).toEqual([1, 2, 1, 4]);
  });
});

describe('la visita (especificacion §5.4 y §5.5)', () => {
  it('al entrar, lo terminado antes es P0 (P5 y P6 solo en la visita en que pasan)', () => {
    expect(run(START, status(request('hecha'), pass('hecha', { leidas: 3 }))).drive).toMatchObject({ phase: 'intro', screen: 'ready', body: false });
    expect(run(START, status(request('fallida'))).drive).toMatchObject({ phase: 'intro', screen: 'ready' });
    // P7 y P8 si: tienen la cabeza.
    expect(run(START, status(request('caducada'))).drive.screen).toBe('expired');
    expect(run(START, status(request('nada_que_leer'))).drive.screen).toBe('nothing');
  });

  it('mientras no hay un si, solo la cabeza; el cuerpo sale con el si del servidor', () => {
    const waiting = run(START, status(request('pedida')), status(request('contando')), status(request('esperando_aprobacion')));
    expect(waiting.drive).toMatchObject({ phase: 'intro', screen: 'waiting', body: false, followed: 7 });
    expect(waiting.commands).toEqual([]);
    // El 200 de aprobar_lectura, aunque la consulta aun diga que espera.
    const yes = update(waiting.drive, status(request('esperando_aprobacion')), 7);
    expect(yes.drive).toMatchObject({ phase: 'running', body: true, stage: 0, ceiling: 20 });
    expect(yes.commands).toEqual([{ kind: 'stage', index: 0 }]);
    // O el si escrito en la ventana del lector, visto en la consulta.
    const typed = run(waiting.drive, status(request('aprobada')));
    expect(typed.commands).toEqual(['stage 0']);
  });

  it('cada fase pide su etapa, en orden; leyendo, la etapa 1 se pone al dia en cada consulta', () => {
    const reading = run(START, status(request('esperando_aprobacion')), status(request('leyendo'), pass('cargando')));
    expect(reading.commands).toEqual(['stage 0']);
    const one = run(reading.drive, status(request('leyendo'), pass('leyendo', { leidas: 1 })), status(request('leyendo'), pass('leyendo', { leidas: 2 })));
    expect(one.commands).toEqual(['stage 1', 'stage 1']);
    expect(one.drive.ceiling).toBe(23);
    // Comparar y analizar van en una transaccion: de leyendo a organizando, sin saltar ninguna.
    const jump = run(one.drive, status(request('leyendo'), pass('organizando', { leidas: 12 })));
    expect(jump.commands).toEqual(['stage 2', 'stage 3', 'stage 4']);
    expect(jump.drive.ceiling).toBe(99);
    const done = run(jump.drive, status(request('hecha'), pass('hecha', { leidas: 12 })));
    expect(done.commands).toEqual(['finish']);
    expect(done.drive.ceiling).toBe(100);
    // Una sola vez.
    expect(run(done.drive, status(request('hecha'), pass('hecha', { leidas: 12 }))).commands).toEqual([]);
  });

  it('una lectura que acaba entre dos consultas: todas las etapas, en orden, y el final', () => {
    const r = run(START, status(request('esperando_aprobacion')), status(request('hecha'), pass('hecha', { leidas: 2 })));
    expect(r.commands).toEqual(['stage 0', 'stage 1', 'stage 2', 'stage 3', 'stage 4', 'finish']);
  });

  it('volver a una lectura en marcha: la cabeza y despues las etapas ya alcanzadas', () => {
    const r = run(START, status(request('leyendo'), pass('comparando', { leidas: 12 })));
    expect(r.drive).toMatchObject({ phase: 'running', body: true });
    expect(r.commands).toEqual(['stage 0', 'stage 1', 'stage 2']);
  });

  it('el techo nunca baja', () => {
    let drive = run(START, status(request('leyendo'), pass('comparando'))).drive;
    expect(drive.ceiling).toBe(60);
    drive = run(drive, status(request('leyendo'), pass('leyendo', { leidas: 1 }))).drive;
    expect(drive.ceiling).toBe(60);
  });

  it('falla antes del si: la escena se funde y despues el error', () => {
    const r = run(START, status(request('comprobando')), status(request('fallida', { motivo_codigo: 'aislamiento' })));
    expect(r.commands).toEqual(['hide']);
    expect(r.drive.hiding).toBe('error');
    // Durante el fundido no cambia nada.
    expect(run(r.drive, status(request('pedida', { id: 8 }))).commands).toEqual([]);
    expect(afterHide(r.drive, null)).toMatchObject({ phase: 'error', hiding: null, body: false });
  });

  it('falla leyendo: fundido sin terminar la etapa, y el error', () => {
    const r = run(START, status(request('leyendo'), pass('leyendo', { leidas: 2 })), status(request('fallida'), pass('fallida', { leidas: 2 })));
    expect(r.commands).toEqual(['stage 0', 'stage 1', 'hide']);
    expect(afterHide(r.drive, null).phase).toBe('error');
  });

  it('se cancela leyendo sin nada leido: fundido y un motor nuevo con la cabeza (P7)', () => {
    const r = run(START, status(request('aprobada')), status(request('cancelada')));
    expect(r.commands).toEqual(['stage 0', 'hide']);
    expect(r.drive.hiding).toBe('fresh');
    const after = afterHide(r.drive, status(request('cancelada')));
    expect(after).toMatchObject({ phase: 'intro', screen: 'cancelled', body: false, stage: -1, engine: r.drive.engine + 1, ceiling: 0 });
  });

  it('se cancela o llega al tope con algo leido: las etapas que faltan y el resultado', () => {
    const r = run(START, status(request('leyendo'), pass('leyendo', { leidas: 2 })), status(request('hecha'), pass('tope', { leidas: 11 })));
    expect(r.commands).toEqual(['stage 0', 'stage 1', 'stage 2', 'stage 3', 'stage 4', 'finish']);
    const stopped = run(START, status(request('leyendo'), pass('leyendo', { leidas: 2 })), status(request('cancelada'), pass('cancelada', { leidas: 2 })));
    expect(stopped.commands.at(-1)).toBe('finish');
  });

  it('caduca, se cancela o no hay nada que leer antes del si: la cabeza sigue', () => {
    for (const end of ['caducada', 'cancelada', 'nada_que_leer'] as const) {
      const r = run(START, status(request('esperando_aprobacion')), status(request(end)));
      expect(r.commands, end).toEqual([]);
      expect(r.drive.phase, end).toBe('intro');
    }
  });

  it('el resultado y el error se quedan; "Volver a pedir" monta un motor nuevo (P1)', () => {
    const done = finished(run(START, status(request('leyendo'), pass('leyendo'))).drive);
    expect(done.phase).toBe('complete');
    expect(run(done, status(request('pedida', { id: 9 }))).drive).toBe(done);
    const error = { ...START, phase: 'error' as const, engine: 3 };
    expect(requested(error, 9)).toMatchObject({ phase: 'intro', screen: 'requested', engine: 4, followed: 9, body: false });
    // Desde la intro (P0, P7, P8) la misma cabeza sigue.
    const intro = { ...START, screen: 'expired' as const, engine: 2 };
    expect(requested(intro, 9)).toMatchObject({ phase: 'intro', screen: 'requested', engine: 2, followed: 9 });
  });
});
