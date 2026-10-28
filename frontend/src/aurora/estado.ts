// La maquina de estados de Aurora en BMS (paso 17, especificacion §1). Las variables de main.tsx
// del dueno (open, active, panel, chatting, searchMode, processMode, el texto de la caja) mas la
// pantalla de Root (el inicio o Documentos) y el sitio dentro de Documentos (la categoria, la
// carpeta y la hoja abierta: lo que en Aurora era la ruta #/documentos/...), en un solo reductor
// puro: cada clic es UNA accion que pone todas las variables a la vez, asi que React pinta un
// solo render y nunca hay un estado intermedio a la vista (F8 y F9).
//
// La regla del dueno: o el menu o una pantalla, nunca los dos. Se cumple asi:
// - la rueda solo se monta con open && !chatting (main.tsx:32) y, con un panel abierto, la
//   oculta el CSS en todos los anchos (styles.css, §1.1);
// - con un panel abierto, `active` no se mueve: solo lo cambia entrada(i), que lo deja en la
//   entrada del panel (§1.1, cambio 2). Asi la rueda escondida no cambia nada;
// - el clic en el orbe mira primero si hay panel: con panel, siempre vuelve a E0 (§1.3).
// Sin React: lo prueba estado.test.ts. Con rutas relativas: lo lee tambien e2e/nav.ts.

/** Las ocho entradas de la rueda, en su orden (§1.4). */
export const ENTRIES = ['settings', 'search', 'documents', 'home', 'receivables', 'payables', 'vat', 'process'] as const;
export type EntryId = (typeof ENTRIES)[number];

/** La ultima (Procesar): la del morado y el orbe de particulas (main.tsx:24,30). */
export const LAST_ENTRY = ENTRIES.length - 1;
/** La activa al abrir la rueda por primera vez en una sesion: Inicio (§1.4). */
export const START_ENTRY = ENTRIES.indexOf('home');

/** El permiso que pide una entrada ademas de ver_facturas: sin el, la entrada no esta en la
 *  rueda. Solo la ultima lo pide, asi que los indices no cambian. */
export const ENTRY_REQUIRES: Readonly<Partial<Record<EntryId, string>>> = { process: 'importar_datos' };

/** Las entradas que ve quien tiene estos permisos (un principio de ENTRIES). */
export function visibleEntries(can: (permission?: string) => boolean): readonly EntryId[] {
  return ENTRIES.filter((id) => can(ENTRY_REQUIRES[id]));
}

/** Las entradas que abren un panel (E2). */
export const PANEL_ENTRIES = ['settings', 'home', 'receivables', 'payables', 'vat'] as const satisfies readonly EntryId[];
export type PanelEntry = (typeof PANEL_ENTRIES)[number];

export function entryIndex(id: EntryId): number {
  return ENTRIES.indexOf(id);
}

export function isPanelEntry(index: number): boolean {
  const id = ENTRIES[index];
  return id !== undefined && (PANEL_ENTRIES as readonly EntryId[]).includes(id);
}

/** La fase de la onda: en E0 recien entrado, la misma que en Aurora (0) (§1.4). */
export function flowPhase(active: number): number {
  return (active - START_ENTRY) * 1.4;
}

// ---------------------------------------------------------------- Documentos (E6)

/** Las dos categorias del arbol (#/documentos/clientes y /proveedores en Aurora). */
export type DocsCategory = 'clients' | 'providers';
export type DocsSide = 'client' | 'provider';

/** Lo que se abre en el <dialog> de Documentos (#/.../archivo/i en Aurora): la hoja de una
 *  factura, un documento de la carpeta (por su clave), un Object o una orden de compra. */
export type DocsSheet =
  | { kind: 'invoice'; id: number }
  | { kind: 'document'; key: string }
  | { kind: 'object'; id: number }
  | { kind: 'po'; id: number };

/** Donde se esta en Documentos: todo, una categoria, una carpeta (con su ficha) y su hoja. */
export interface DocsPlace {
  category: DocsCategory | null;
  folder: { side: DocsSide; id: number } | null;
  sheet: DocsSheet | null;
}

export const DOCS_ROOT: DocsPlace = { category: null, folder: null, sheet: null };

export function categoryOf(side: DocsSide): DocsCategory {
  return side === 'client' ? 'clients' : 'providers';
}

/** La carpeta de una empresa (con su categoria), y su hoja si la hay. */
export function folderPlace(side: DocsSide, id: number, sheet: DocsSheet | null = null): DocsPlace {
  return { category: categoryOf(side), folder: { side, id }, sheet };
}

/** Lo que hace falta de una factura para abrir su hoja en su carpeta. */
export interface InvoiceRef {
  id: number;
  sentido?: 'entrante' | 'saliente' | null;
  cliente_id?: number | null;
  proveedor_id?: number | null;
}

/** La carpeta de una factura: la del cliente (venta) o la del proveedor (compra). */
export function invoicePlace(ref: InvoiceRef): DocsPlace {
  const sheet: DocsSheet = { kind: 'invoice', id: ref.id };
  if (ref.sentido === 'saliente' && ref.cliente_id) return folderPlace('client', ref.cliente_id, sheet);
  if (ref.sentido === 'entrante' && ref.proveedor_id) return folderPlace('provider', ref.proveedor_id, sheet);
  if (ref.cliente_id) return folderPlace('client', ref.cliente_id, sheet);
  if (ref.proveedor_id) return folderPlace('provider', ref.proveedor_id, sheet);
  return { ...DOCS_ROOT, sheet };
}

/** La pantalla de trabajo de Root: Documentos, con su sitio. Procesar no es otra pantalla de
 *  Root: como en Aurora, es el inicio en processMode (main.tsx:23,40). */
export type Work = { kind: 'documents'; place: DocsPlace };

/** Donde se esta: el inicio de Aurora (E0 a E5 y L0) o una pantalla de trabajo. */
export type Screen = 'home' | 'work';

/** Los filtros de la busqueda que llegan ya puestos (E5-p): parametros de /api/v2/buscar. */
export type SearchPreset = Readonly<Record<string, string>>;

export interface AuroraState {
  screen: Screen;
  /** La pantalla de trabajo y, en Documentos, donde se esta. */
  work: Work;
  /** Sube cada vez que se entra en una pantalla de trabajo desde el inicio. */
  workSeq: number;
  open: boolean;
  active: number;
  panel: number | null;
  /** La vista de un grupo dentro del panel (null: en reposo). */
  view: string | null;
  chatting: boolean;
  searchMode: boolean;
  /** Procesar (E7): el espacio central con la suricata, sin orbe, rueda ni caja (main.tsx:40). */
  processMode: boolean;
  /** Los filtros con que se entro en la busqueda (E5-p); null: la busqueda vacia. */
  search: SearchPreset | null;
  /** Lo escrito en la caja. */
  text: string;
}

export const INITIAL_STATE: AuroraState = {
  screen: 'home',
  work: { kind: 'documents', place: DOCS_ROOT },
  workSeq: 0,
  open: false,
  active: START_ENTRY,
  panel: null,
  view: null,
  chatting: false,
  searchMode: false,
  processMode: false,
  search: null,
  text: '',
};

export type AuroraAction =
  /** Entra alguien (o sale): E0 (o L0) con la rueda en su posicion inicial. */
  | { type: 'reset' }
  /** El clic en el orbe (§1.3). */
  | { type: 'orb' }
  /** "Presiona para navegar". */
  | { type: 'openMenu' }
  /** Un paso de la rueda; `last`: la ultima entrada que ve esta persona (sin permiso para
   *  Procesar, la de antes). */
  | { type: 'step'; delta: number; last?: number }
  /** El foco en una fila de la rueda (Tab). */
  | { type: 'focusEntry'; index: number }
  /** El clic en una entrada que abre un panel; `view`, con la vista de un grupo ya abierta. */
  | { type: 'enterPanel'; index: number; view?: string | null }
  /** La entrada Busqueda (o una fila que es una busqueda de facturas: E5-p, F9). */
  | { type: 'enterSearch'; index?: number; preset?: SearchPreset | null }
  /** Documentos, desde el inicio (con el vuelo): la entrada, una factura, una carpeta (F3). */
  | { type: 'enterDocuments'; place: DocsPlace; index?: number }
  /** Moverse dentro de Documentos (sin vuelo): el arbol, una carpeta, una hoja. */
  | { type: 'docs'; place: DocsPlace }
  /** Procesar (la lectura de facturas): el inicio en processMode, sin vuelo (main.tsx:23). */
  | { type: 'enterProcess'; index?: number }
  /** "Volver al inicio" de Procesar: E0 (main.tsx:40, onBack). */
  | { type: 'leaveProcess' }
  /** "Ir a la cola de trabajo" del resultado de Procesar: E2-I con la vista de la cola, en un
   *  solo cambio (F8). */
  | { type: 'processToQueue' }
  /** El ✕ del panel: vuelve a E1 con la entrada del panel en el centro. */
  | { type: 'closePanel' }
  /** Abrir o cerrar la vista de un grupo dentro del panel. */
  | { type: 'panelView'; view: string | null }
  /** Lo escrito en la caja. */
  | { type: 'text'; value: string }
  /** Enviar: empieza la conversacion (E4). */
  | { type: 'send' }
  /** "Volver al espacio" de la conversacion: E1. */
  | { type: 'backToSpace' }
  /** Una fila de la respuesta que es una pantalla: E4 -> E2 en un solo cambio (F9). */
  | { type: 'enterFromConversation'; index: number; view?: string | null }
  /** Volver al inicio desde una pantalla de trabajo (el orbe pequeno, "Volver a Aurora"). */
  | { type: 'home' };

function clampEntry(index: number, last: number = LAST_ENTRY): number {
  return Math.max(0, Math.min(last, Math.round(index)));
}

/** E0: el inicio, cerrado. La activa se recuerda (como en Aurora). */
function homeState(state: AuroraState): AuroraState {
  return { ...state, screen: 'home', open: false, panel: null, view: null, chatting: false, searchMode: false, processMode: false, search: null, text: '' };
}

/** Una pantalla de trabajo desde donde se este: lo del inicio se cierra. */
function workState(state: AuroraState, work: Work, index: number | undefined): AuroraState {
  return {
    ...homeState(state),
    screen: 'work',
    work,
    workSeq: state.screen === 'work' ? state.workSeq : state.workSeq + 1,
    active: index === undefined ? state.active : clampEntry(index),
  };
}

export function auroraReducer(state: AuroraState, action: AuroraAction): AuroraState {
  switch (action.type) {
    case 'reset':
      return { ...INITIAL_STATE, workSeq: state.workSeq };
    case 'orb': {
      // En Documentos el orbe es el pequeno (vuelve con el vuelo); en Procesar no hay orbe.
      if (state.screen !== 'home' || state.processMode) return state;
      // Con panel, siempre cierra y vuelve a E0 (aunque se este escribiendo).
      if (state.panel !== null) return homeState(state);
      if (state.searchMode) return { ...state, searchMode: false, search: null, open: false };
      if (state.chatting) return { ...state, chatting: false, open: false, text: '' };
      // Con Procesar en el centro, el orbe entra en Procesar: lo hace quien llama
      // (enterProcess); aqui solo se abre o se cierra el menu.
      return { ...state, open: !state.open };
    }
    case 'openMenu':
      if (state.screen !== 'home' || state.chatting || state.searchMode || state.processMode || state.panel !== null) return state;
      return { ...state, open: true };
    case 'step':
      // Solo con el menu a la vista: con un panel, la rueda escondida no manda.
      if (!state.open || state.chatting || state.panel !== null || state.processMode || state.screen !== 'home') return state;
      return { ...state, active: clampEntry(state.active + Math.sign(action.delta), action.last) };
    case 'focusEntry':
      if (!state.open || state.panel !== null || state.processMode || state.screen !== 'home') return state;
      return { ...state, active: clampEntry(action.index) };
    case 'enterPanel': {
      const index = clampEntry(action.index);
      if (!isPanelEntry(index)) return state;
      return {
        ...state,
        screen: 'home',
        open: true,
        active: index,
        panel: index,
        view: action.view ?? null,
        searchMode: false,
        processMode: false,
        search: null,
      };
    }
    case 'enterSearch':
      // main.tsx:32: setSearchMode(true), setOpen(false), setPanel(null) y la caja vacia.
      return {
        ...state,
        screen: 'home',
        active: action.index === undefined ? state.active : clampEntry(action.index),
        searchMode: true,
        processMode: false,
        search: action.preset ?? null,
        open: false,
        panel: null,
        view: null,
        chatting: false,
        text: '',
      };
    case 'enterDocuments':
      return workState(state, { kind: 'documents', place: action.place }, action.index);
    case 'docs':
      if (state.screen !== 'work' || state.work.kind !== 'documents') return state;
      return { ...state, work: { kind: 'documents', place: action.place } };
    case 'enterProcess':
      // main.tsx:23 (enter(4)): fuera la busqueda, la conversacion, la rueda y el panel; con la
      // entrada pulsada, la activa es Procesar (la ultima).
      return { ...homeState(state), processMode: true, active: action.index === undefined ? state.active : clampEntry(action.index) };
    case 'leaveProcess':
      if (!state.processMode) return state;
      return homeState(state);
    case 'processToQueue': {
      // F8: processMode=false, open=true, active=Inicio, panel=Inicio y la vista de la cola, a la
      // vez: la rueda nace con .has-panel y no se ve.
      const home = entryIndex('home');
      return { ...homeState(state), open: true, active: home, panel: home, view: 'queue' };
    }
    case 'closePanel':
      if (state.panel === null) return state;
      return { ...state, panel: null, view: null, open: true, active: state.panel };
    case 'panelView':
      if (state.panel === null) return state;
      return { ...state, view: action.view };
    case 'text':
      // main.tsx:40: la primera tecla lleva a E3 y cierra el menu (el panel sigue, como en Aurora).
      // En Procesar no hay caja.
      if (state.processMode) return state;
      if (action.value.length) return { ...state, text: action.value, chatting: true, open: false };
      return { ...state, text: action.value };
    case 'send':
      if (!state.text.trim() || state.processMode) return state;
      return { ...state, text: '', chatting: true, open: false, panel: null, view: null };
    case 'backToSpace':
      return { ...state, chatting: false, open: true, text: '' };
    case 'enterFromConversation': {
      const index = clampEntry(action.index);
      if (!isPanelEntry(index)) return state;
      return {
        ...state,
        screen: 'home',
        chatting: false,
        text: '',
        open: true,
        active: index,
        panel: index,
        view: action.view ?? null,
        searchMode: false,
        search: null,
      };
    }
    case 'home':
      return homeState(state);
  }
}

/** Lo que se ve (para las pruebas y para quien pinta): o el menu o una pantalla, nunca los dos. */
export function visibleParts(state: AuroraState, conversation: boolean): { menu: boolean; screen: boolean } {
  if (state.screen !== 'home') return { menu: false, screen: true };
  const screen = state.panel !== null || conversation || state.searchMode || state.processMode;
  const menu = state.open && !state.chatting && state.panel === null && !state.searchMode && !state.processMode;
  return { menu, screen };
}
