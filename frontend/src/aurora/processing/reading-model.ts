// Procesar de verdad (paso 17 · B3, especificacion §5.4 y §5.5), sin React: de lo que dice
// GET /api/v2/lectura a lo que se ve (P0 a P8), a lo que se le pide al motor de la suricata
// (setStage, finish, hide) y al techo del %. Lo prueba reading-model.test.ts.
//
// Las reglas, en corto:
// - el cuerpo sale solo con un si aceptado por el servidor (el 200 de aprobar_lectura o la
//   consulta que ve aprobada o leyendo); mientras, solo la cabeza;
// - cada fase de la pasada pide su etapa, en orden y sin saltar ninguna: el motor juega cada una
//   entera y nunca empieza una que la lectura no ha alcanzado;
// - el % es min(motor, techo): el techo sale de la fase y de lo leido, y solo sube;
// - lo que acaba mal con el cuerpo fuera se funde (hide); despues, el error (P6) o un motor nuevo
//   con la cabeza (P7). Nunca se salta del cuerpo a la cabeza sin el fundido;
// - P5 y P6 se ven solo en la visita en que pasan: al entrar, lo terminado es P0.
import type { ReadingPass, ReadingPassRow, ReadingRequest, ReadingStatus } from '@/lib/api-types';

/** Lo que se ve (especificacion §5.4): P0 ready, P1 requested, P2 checking o counting, P3
 *  waiting, P4 reading, P5 done, P6 failed, P7 expired o cancelled, P8 nothing. */
export type Screen = 'ready' | 'requested' | 'checking' | 'counting' | 'waiting' | 'reading' | 'done' | 'failed' | 'expired' | 'cancelled' | 'nothing';

/** Las fases de Aurora (processing-workspace.tsx): la intro con la cabeza, las etapas, el
 *  resultado y el error. */
export type Phase = 'intro' | 'running' | 'complete' | 'error';

/** Las cinco etapas del motor (CONFIG.stages). */
export const STAGES = 5;

/** La pasada de la lectura que se ensena (la de su solicitud, no otra). */
export function passOf(status: ReadingStatus): ReadingPass | null {
  const s = status.solicitud;
  const p = status.pasada_en_curso;
  return s && p && p.solicitud_id === s.id ? p : null;
}

/** Los documentos que la pasada ya termino (leidos, ya leidos o fallidos). */
export function handled(pass: ReadingPass | null): number {
  return pass ? pass.leidas + pass.ya_leidas + pass.fallidas : 0;
}

/** Si la pasada llego a leer algo. */
export function readSomething(pass: ReadingPass | null): boolean {
  return !!pass && (handled(pass) > 0 || pass.resultado.length > 0);
}

/** Lo que se ve segun el servidor, sin la visita (P0 a P8). */
export function screenOf(status: ReadingStatus): Screen {
  const s = status.solicitud ?? null;
  if (!s) return 'ready';
  // Un lector que dejo de dar senales: la lectura no va a seguir (pedir otra la cierra).
  if (s.viva && s.abandonada) return 'failed';
  switch (s.estado) {
    case 'pedida':
      return 'requested';
    case 'comprobando':
      return 'checking';
    case 'contando':
      return 'counting';
    case 'esperando_aprobacion':
      return 'waiting';
    case 'aprobada':
    case 'leyendo':
      return 'reading';
    case 'hecha':
      return 'done';
    case 'fallida':
      return 'failed';
    case 'caducada':
      return 'expired';
    case 'cancelada':
      return readSomething(passOf(status)) ? 'done' : 'cancelled';
    case 'nada_que_leer':
      return 'nothing';
  }
  return 'ready';
}

/** La etapa que ha alcanzado la lectura de verdad (0 a 4; -1 si fallo: ninguna mas). */
export function stageOf(status: ReadingStatus): number {
  const pass = passOf(status);
  if (!pass) return 0;
  switch (pass.fase) {
    case 'cargando':
      return 0;
    case 'leyendo':
      return 1;
    case 'comparando':
      return 2;
    case 'analizando':
      return 3;
    case 'fallida':
      return -1;
    default:
      return 4;
  }
}

/** El techo del % (especificacion §5.5): hasta donde ha llegado la lectura, en los cinco tramos
 *  de 20 del motor. */
export function ceilingOf(status: ReadingStatus): number {
  if (screenOf(status) === 'done') return 100;
  const pass = passOf(status);
  if (!pass) return 20;
  switch (pass.fase) {
    case 'cargando':
      return 20;
    case 'leyendo':
      return 20 + (pass.total > 0 ? Math.floor((20 * Math.min(handled(pass), pass.total)) / pass.total) : 0);
    case 'comparando':
      return 60;
    case 'analizando':
      return 80;
    case 'organizando':
      return 99;
    default:
      return readSomething(pass) && pass.fase !== 'fallida' ? 100 : 99;
  }
}

/** El % que se ve: el del motor, sin pasar de lo que va la lectura. */
export function shownProgress(engine: number, ceiling: number): number {
  return Math.max(0, Math.min(engine, ceiling, 100));
}

export interface RowTexts {
  done: string;
  phases: Record<'comparando' | 'leyendo' | 'guardando', string>;
}

/** Las lineas de la lectura (loader-engine.ts:74-75): las dos ultimas terminadas y la de ahora. */
export function rowsOf(pass: ReadingPass | null, texts: RowTexts): string {
  if (!pass) return '';
  const lines = pass.recientes.slice(-2).map((name) => `✓ ${name.padEnd(22)} ${texts.done}`);
  if (pass.documento_actual && !pass.terminada) {
    lines.push(`> ${pass.documento_actual.padEnd(22)} ${texts.phases[pass.documento_fase ?? 'leyendo']}`);
  }
  return lines.join('\n');
}

/** Lo que fue de cada documento al terminar, y las tres cuentas del resultado. */
export interface Outcome {
  rows: ReadingPassRow[];
  fresh: number;
  repeated: number;
  failed: number;
}

const FINAL_ROWS = new Set(['nueva', 'ya_leida', 'posible_duplicado', 'fallida']);

export function outcomeOf(pass: ReadingPass | null): Outcome {
  const rows = (pass?.resultado ?? []).filter((r) => FINAL_ROWS.has(r.estado));
  return {
    rows,
    fresh: rows.filter((r) => r.estado === 'nueva').length,
    repeated: rows.filter((r) => r.estado === 'ya_leida' || r.estado === 'posible_duplicado').length,
    failed: rows.filter((r) => r.estado === 'fallida').length,
  };
}

// ---------------------------------------------------------------- la visita

/** Lo que lleva la pantalla durante una visita a Procesar. */
export interface Drive {
  phase: Phase;
  screen: Screen;
  /** La lectura que sigue esta visita: la viva que se vio o la pedida desde aqui. */
  followed: number | null;
  /** El cuerpo entero ya salio (el motor empezo sus etapas). */
  body: boolean;
  /** La etapa mas alta pedida al motor (-1: ninguna). */
  stage: number;
  /** Ya se le dijo al motor que termine. */
  finishing: boolean;
  /** La escena se funde (hide): despues, el error (P6) o un motor nuevo con la cabeza (P7). */
  hiding: 'error' | 'fresh' | null;
  /** Sube con cada motor nuevo (la key de DocumentLoader). */
  engine: number;
  /** El techo del %, que solo sube. */
  ceiling: number;
}

/** Lo que se le pide al motor, en orden. */
export type Command = { kind: 'stage'; index: number } | { kind: 'finish' } | { kind: 'hide' };

export const START: Drive = {
  phase: 'intro',
  screen: 'ready',
  followed: null,
  body: false,
  stage: -1,
  finishing: false,
  hiding: null,
  engine: 0,
  ceiling: 0,
};

/**
 * Una consulta nueva (o la respuesta a una orden): lo que se ve y lo que se le pide al motor.
 * `approved`: la lectura a la que el servidor ya acepto el si (200 de aprobar_lectura), aunque la
 * consulta aun no lo diga.
 */
export function update(prev: Drive, status: ReadingStatus, approved: number | null = null): { drive: Drive; commands: Command[] } {
  // El resultado y el error se quedan hasta que la persona hace algo; un fundido, hasta acabar.
  if (prev.phase === 'complete' || prev.phase === 'error' || prev.hiding) return { drive: prev, commands: [] };
  const s: ReadingRequest | null = status.solicitud ?? null;
  let screen = screenOf(status);
  if (approved !== null && s?.id === approved && screen === 'waiting') screen = 'reading';
  // La viva que se ve es la que sigue la visita (la de un lector que ya no da senales, no).
  const followed = s && s.viva && !s.abandonada ? s.id : prev.followed;
  const ours = s !== null && s.id === followed;
  // Lo que termino antes de esta visita (o una lectura que esta visita no siguio): P0.
  if ((screen === 'done' || screen === 'failed' || screen === 'reading') && !ours) screen = 'ready';
  const drive: Drive = { ...prev, screen, followed };
  const commands: Command[] = [];
  if (!drive.body) {
    if (screen === 'failed') {
      // Falla antes del si: la escena (la cabeza) se funde y despues, el error.
      drive.hiding = 'error';
      commands.push({ kind: 'hide' });
      return { drive, commands };
    }
    if (screen !== 'reading' && screen !== 'done') {
      drive.phase = 'intro';
      return { drive, commands };
    }
    // El si de verdad: sale el cuerpo entero.
    drive.body = true;
    drive.phase = 'running';
  }
  if (screen === 'reading' || screen === 'done') {
    const target = screen === 'done' ? STAGES - 1 : stageOf(status);
    drive.ceiling = Math.max(drive.ceiling, ceilingOf(status));
    for (let i = drive.stage + 1; i <= target; i++) commands.push({ kind: 'stage', index: i });
    // Leyendo, la linea de la etapa 1 se pone al dia en cada consulta con la cuenta nueva.
    if (target === 1 && drive.stage >= 1) commands.push({ kind: 'stage', index: 1 });
    drive.stage = Math.max(drive.stage, target);
    if (screen === 'done' && !drive.finishing) {
      drive.finishing = true;
      commands.push({ kind: 'finish' });
    }
    return { drive, commands };
  }
  // Con el cuerpo fuera y sin nada leido (cancelada, o la lectura desaparecio): fundido y un
  // motor nuevo con la cabeza; si fallo, fundido y el error.
  drive.hiding = screen === 'failed' ? 'error' : 'fresh';
  commands.push({ kind: 'hide' });
  return { drive, commands };
}

/** Acabo el fundido de la escena (0,3 s). */
export function afterHide(prev: Drive, status: ReadingStatus | null): Drive {
  if (prev.hiding === 'error') return { ...prev, hiding: null, phase: 'error', body: false };
  if (prev.hiding === 'fresh') {
    const screen = status ? screenOf(status) : 'cancelled';
    return {
      ...prev,
      hiding: null,
      phase: 'intro',
      body: false,
      stage: -1,
      finishing: false,
      ceiling: 0,
      engine: prev.engine + 1,
      screen: screen === 'reading' || screen === 'done' || screen === 'failed' ? 'cancelled' : screen,
    };
  }
  return prev;
}

/** El motor termino: la centinela, el fundido y el resultado (P5). */
export function finished(prev: Drive): Drive {
  return { ...prev, phase: 'complete', body: false };
}

/** Una lectura pedida desde aqui (pedir_lectura con 200): P1. Desde el error, con un motor nuevo
 *  (la nube de reserva, el monticulo y la cabeza); desde la intro, la misma cabeza sigue. */
export function requested(prev: Drive, id: number): Drive {
  if (prev.phase === 'error' || prev.phase === 'complete') return { ...START, engine: prev.engine + 1, followed: id, screen: 'requested' };
  return { ...prev, followed: id, screen: 'requested', phase: 'intro' };
}
