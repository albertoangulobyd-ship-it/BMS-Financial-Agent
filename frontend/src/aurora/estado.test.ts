// La maquina de estados (especificacion §1.2, §1.3 y §6.6): cada transicion, la regla del dueno
// (o el menu o una pantalla), la rueda escondida que no manda con un panel abierto y los cambios
// de un solo paso (F8 y F9).
import { describe, expect, it } from 'vitest';
import { PLACE_IDS, screenResults } from '@/lib/quick-search';
import { MESSAGES } from '@/i18n';
import {
  ENTRIES,
  INITIAL_STATE,
  LAST_ENTRY,
  DOCS_ROOT,
  START_ENTRY,
  auroraReducer,
  entryIndex,
  folderPlace,
  invoicePlace,
  visibleEntries,
  flowPhase,
  isPanelEntry,
  visibleParts,
  type AuroraAction,
  type AuroraState,
} from './estado';

const run = (actions: AuroraAction[], from: AuroraState = INITIAL_STATE) => actions.reduce(auroraReducer, from);
const E1 = run([{ type: 'orb' }]);
const panelOf = (id: (typeof ENTRIES)[number]) => run([{ type: 'orb' }, { type: 'enterPanel', index: entryIndex(id) }]);

describe('la rueda: entradas, activa inicial y fase de la onda', () => {
  it('ocho entradas en el orden de §1.4, con Procesar al final', () => {
    expect(ENTRIES).toEqual(['settings', 'search', 'documents', 'home', 'receivables', 'payables', 'vat', 'process']);
    expect(LAST_ENTRY).toBe(entryIndex('process'));
  });

  it('empieza con Inicio en el centro y la onda en la fase de Aurora (0)', () => {
    expect(INITIAL_STATE.active).toBe(START_ENTRY);
    expect(ENTRIES[START_ENTRY]).toBe('home');
    expect(flowPhase(START_ENTRY)).toBe(0);
    expect(flowPhase(START_ENTRY + 1)).toBeCloseTo(1.4);
  });

  it('solo las entradas de panel abren un panel', () => {
    expect(ENTRIES.filter((_, i) => isPanelEntry(i))).toEqual(['settings', 'home', 'receivables', 'payables', 'vat']);
  });

  it('un paso por gesto, sin salirse de la rueda', () => {
    expect(run([{ type: 'step', delta: 120 }], E1).active).toBe(START_ENTRY + 1);
    expect(run([{ type: 'step', delta: -3 }], E1).active).toBe(START_ENTRY - 1);
    const bottom = run(Array.from({ length: 12 }, () => ({ type: 'step', delta: 1 }) as const), E1);
    expect(bottom.active).toBe(LAST_ENTRY);
    const top = run(Array.from({ length: 12 }, () => ({ type: 'step', delta: -1 }) as const), E1);
    expect(top.active).toBe(0);
  });

  it('la rueda solo se mueve con el menu a la vista', () => {
    expect(run([{ type: 'step', delta: 1 }]).active).toBe(START_ENTRY);
  });

  it('recuerda la ultima activa al cerrar y volver a abrir', () => {
    const s = run([{ type: 'step', delta: 1 }, { type: 'orb' }, { type: 'orb' }], E1);
    expect(s.open).toBe(true);
    expect(s.active).toBe(START_ENTRY + 1);
  });
});

describe('el orbe como puerta (§1.3)', () => {
  it('E0 abre el menu y E1 lo cierra', () => {
    expect(E1.open).toBe(true);
    expect(run([{ type: 'orb' }], E1).open).toBe(false);
  });

  it('con panel, siempre vuelve a E0', () => {
    const s = run([{ type: 'orb' }], panelOf('receivables'));
    expect(s).toMatchObject({ open: false, panel: null, view: null });
  });

  it('con panel y escribiendo, vuelve a E0 y borra el texto', () => {
    const s = run([{ type: 'text', value: 'hola' }, { type: 'orb' }], panelOf('payables'));
    expect(s).toMatchObject({ open: false, panel: null, chatting: false, text: '' });
  });

  it('E3 vuelve a E0 y borra el texto', () => {
    const s = run([{ type: 'text', value: 'iva' }, { type: 'orb' }]);
    expect(s).toMatchObject({ chatting: false, open: false, text: '' });
  });

  it('E5 vuelve a E0', () => {
    const s = run([{ type: 'orb' }, { type: 'enterSearch', index: entryIndex('search') }, { type: 'orb' }]);
    expect(s).toMatchObject({ searchMode: false, open: false, search: null });
  });

  it('desde una pantalla de trabajo no hace nada (alli el orbe pequeno vuelve al inicio)', () => {
    const work = run([{ type: 'enterDocuments', place: DOCS_ROOT }], E1);
    expect(run([{ type: 'orb' }], work)).toBe(work);
    expect(run([{ type: 'home' }], work)).toMatchObject({ screen: 'home', open: false, panel: null });
  });
});

describe('o el menu o una pantalla, nunca los dos (§1.1)', () => {
  it('con un panel abierto, active es su entrada y nada lo mueve', () => {
    const p = panelOf('vat');
    const moved = run(
      [
        { type: 'step', delta: 1 },
        { type: 'step', delta: -1 },
        { type: 'focusEntry', index: LAST_ENTRY },
        { type: 'step', delta: 1 },
      ],
      p
    );
    expect(moved.active).toBe(entryIndex('vat'));
    expect(moved.panel).toBe(entryIndex('vat'));
  });

  it('el clic en el orbe con un panel nunca entra en Procesar, aunque la activa fuera la ultima', () => {
    const atLast = run(Array.from({ length: 8 }, () => ({ type: 'step', delta: 1 }) as const), E1);
    expect(atLast.active).toBe(LAST_ENTRY);
    const p = run([{ type: 'enterPanel', index: entryIndex('vat') }, { type: 'orb' }], atLast);
    expect(p).toMatchObject({ screen: 'home', open: false, panel: null, active: entryIndex('vat') });
  });

  it('el ✕ vuelve a E1 con la entrada del panel en el centro', () => {
    const s = run([{ type: 'closePanel' }], panelOf('receivables'));
    expect(s).toMatchObject({ open: true, panel: null, active: entryIndex('receivables') });
  });

  it('en cada estado, el menu y una pantalla no se ven a la vez', () => {
    const states: [string, AuroraState, boolean][] = [
      ['E0', INITIAL_STATE, false],
      ['E1', E1, false],
      ['E2', panelOf('home'), false],
      ['E2 con vista', run([{ type: 'panelView', view: 'idioma' }], panelOf('settings')), false],
      ['E3', run([{ type: 'text', value: 'x' }], E1), false],
      ['E3 con panel', run([{ type: 'text', value: 'x' }], panelOf('vat')), false],
      ['E4', run([{ type: 'text', value: 'x' }, { type: 'send' }], E1), true],
      ['E5', run([{ type: 'enterSearch', index: 1 }], E1), false],
      ['E6', run([{ type: 'enterDocuments', place: DOCS_ROOT }], E1), false],
      ['E6-h', run([{ type: 'enterDocuments', place: folderPlace('client', 1, { kind: 'invoice', id: 7 }) }], E1), false],
      ['E7', run([{ type: 'enterProcess' }], E1), false],
    ];
    for (const [name, state, conversation] of states) {
      const parts = visibleParts(state, conversation);
      expect(parts.menu && parts.screen, name).toBe(false);
    }
    expect(visibleParts(E1, false).menu).toBe(true);
    expect(visibleParts(panelOf('home'), false)).toEqual({ menu: false, screen: true });
  });
});

describe('las transiciones de §1.2', () => {
  it('E1 -> E2 -> vista -> reposo -> E1', () => {
    const p = panelOf('settings');
    expect(p).toMatchObject({ panel: entryIndex('settings'), view: null, open: true });
    const v = run([{ type: 'panelView', view: 'idioma' }], p);
    expect(v.view).toBe('idioma');
    expect(run([{ type: 'panelView', view: null }], v).view).toBe(null);
  });

  it('una entrada que no es de panel no abre un panel', () => {
    expect(run([{ type: 'enterPanel', index: entryIndex('documents') }], E1)).toEqual(E1);
  });

  it('escribir lleva a E3 sin cerrar el panel; enviar lo cierra (E4)', () => {
    const typing = run([{ type: 'text', value: 'resumen' }], panelOf('home'));
    expect(typing).toMatchObject({ chatting: true, open: false, panel: entryIndex('home') });
    const sent = run([{ type: 'send' }], typing);
    expect(sent).toMatchObject({ chatting: true, panel: null, text: '' });
    // Borrar el texto no vuelve a E0.
    expect(run([{ type: 'text', value: '' }], typing).chatting).toBe(true);
  });

  it('enviar sin texto no hace nada', () => {
    expect(run([{ type: 'send' }], E1)).toEqual(E1);
  });

  it('"Volver al espacio" lleva a E1', () => {
    const s = run([{ type: 'text', value: 'x' }, { type: 'send' }, { type: 'backToSpace' }], E1);
    expect(s).toMatchObject({ chatting: false, open: true, text: '' });
  });

  it('Busqueda: cierra el menu y el panel y vacia la caja', () => {
    const s = run([{ type: 'enterSearch', index: entryIndex('search') }], panelOf('receivables'));
    expect(s).toMatchObject({ searchMode: true, open: false, panel: null, text: '', search: null });
  });

  it('E2 -> E5-p en un solo cambio, con los filtros puestos (F9)', () => {
    const preset = { sentido: 'saliente', vencida: 'si', orden: 'vencimiento' };
    const s = run([{ type: 'enterSearch', preset }], panelOf('receivables'));
    expect(s).toMatchObject({ searchMode: true, panel: null, open: false, search: preset });
  });

  it('E4 -> E2 en un solo cambio, con la vista de su grupo (F9)', () => {
    const chat = run([{ type: 'text', value: 'cola' }, { type: 'send' }]);
    const s = run([{ type: 'enterFromConversation', index: entryIndex('home'), view: 'cola' }], chat);
    expect(s).toMatchObject({ chatting: false, open: true, active: entryIndex('home'), panel: entryIndex('home'), view: 'cola' });
  });

  it('una pantalla de trabajo empieza de cero y vuelve a E0; dentro de Documentos se mueve sin vuelo', () => {
    const a = run([{ type: 'enterDocuments', place: DOCS_ROOT, index: entryIndex('documents') }], E1);
    expect(a).toMatchObject({ screen: 'work', open: false, active: entryIndex('documents'), work: { kind: 'documents', place: DOCS_ROOT } });
    // Moverse dentro (una carpeta, su hoja) no vuelve a empezar la pantalla.
    const inside = run([{ type: 'docs', place: folderPlace('provider', 3, { kind: 'po', id: 9 }) }], a);
    expect(inside.workSeq).toBe(a.workSeq);
    expect(inside.work).toEqual({ kind: 'documents', place: { category: 'providers', folder: { side: 'provider', id: 3 }, sheet: { kind: 'po', id: 9 } } });
    // Fuera de Documentos, docs no hace nada.
    expect(run([{ type: 'docs', place: DOCS_ROOT }], E1)).toBe(E1);
    const b = run([{ type: 'home' }, { type: 'enterProcess' }], a);
    expect(b.workSeq).toBe(a.workSeq + 1);
    expect(b.work).toEqual({ kind: 'process' });
  });

  it('la hoja de una factura se abre en la carpeta de su empresa (F3)', () => {
    expect(invoicePlace({ id: 7, sentido: 'saliente', cliente_id: 2, proveedor_id: null })).toEqual(folderPlace('client', 2, { kind: 'invoice', id: 7 }));
    expect(invoicePlace({ id: 8, sentido: 'entrante', cliente_id: null, proveedor_id: 5 })).toEqual(folderPlace('provider', 5, { kind: 'invoice', id: 8 }));
    // Sin empresa conocida, la hoja sola (Documentos la lleva a su carpeta al leerla).
    expect(invoicePlace({ id: 9 })).toEqual({ ...DOCS_ROOT, sheet: { kind: 'invoice', id: 9 } });
  });

  it('entrar o salir vuelve a E0 con Inicio en el centro', () => {
    const s = run([{ type: 'step', delta: 1 }, { type: 'reset' }], E1);
    expect(s).toMatchObject({ screen: 'home', open: false, active: START_ENTRY });
  });

  it('cada pantalla de antes tiene su sitio y se abre por su nombre (ninguna se pierde)', () => {
    const everyone = () => true;
    for (const id of PLACE_IDS) {
      const label = MESSAGES.es.nav[id].label;
      expect(screenResults(label, MESSAGES.es, everyone).map((r) => r.key), id).toContain(`screen:${id}`);
    }
  });

  it('sin permiso para importar, Procesar no esta en la rueda y la rueda no pasa de la anterior', () => {
    expect(visibleEntries(() => true)).toEqual(ENTRIES);
    const readOnly = visibleEntries((p) => p !== 'importar_datos');
    expect(readOnly).toEqual(ENTRIES.filter((id) => id !== 'process'));
    const bottom = run(Array.from({ length: 12 }, () => ({ type: 'step', delta: 1, last: readOnly.length - 1 }) as const), E1);
    expect(bottom.active).toBe(readOnly.length - 1);
  });
});
