// La maquina de estados de Aurora en BMS (paso 17, especificacion §1). Las variables de main.tsx
// del dueno (open, active, panel, chatting, searchMode, el texto de la caja) mas la pantalla de
// Root (el inicio, Documentos o una pantalla de trabajo, con su camino), en un solo reductor
// puro: cada clic es UNA accion que pone todas las variables a la vez, asi que React pinta un
// solo render y nunca hay un estado intermedio a la vista (F8 y F9).
//
// La regla del dueno: o el menu o una pantalla, nunca los dos. Se cumple asi:
// - la rueda solo se monta con open && !chatting (main.tsx:32) y, con un panel abierto, la
//   oculta el CSS en todos los anchos (styles.css, §1.1);
// - con un panel abierto, `active` no se mueve: solo lo cambia entrada(i), que lo deja en la
//   entrada del panel (§1.1, cambio 2). Asi la rueda escondida no cambia nada;
// - el clic en el orbe mira primero si hay panel: con panel, siempre vuelve a E0 (§1.3).
// Sin React: lo prueba estado.test.ts.
// Con ruta relativa: lo lee tambien e2e/nav.ts, que no conoce '@/'.
import { SECTION_VIEWS, type Route, type ViewId } from '../screens/sections';

/** Las ocho entradas de la rueda, en su orden (§1.4). */
export const ENTRIES = ['settings', 'search', 'documents', 'home', 'receivables', 'payables', 'vat', 'process'] as const;
export type EntryId = (typeof ENTRIES)[number];

/** La ultima (Procesar): la del morado y el orbe de particulas (main.tsx:24,30). */
export const LAST_ENTRY = ENTRIES.length - 1;
/** La activa al abrir la rueda por primera vez en una sesion: Inicio (§1.4). */
export const START_ENTRY = ENTRIES.indexOf('home');

/** El permiso que pide una entrada ademas de ver_facturas: sin el, la entrada no esta en la
 *  rueda (como el menu de antes). Solo la ultima lo pide, asi que los indices no cambian. */
export const ENTRY_REQUIRES: Readonly<Partial<Record<EntryId, string>>> = { process: 'importar_datos' };

/** Las entradas que ve quien tiene estos permisos (un principio de ENTRIES). */
export function visibleEntries(can: (permission?: string) => boolean): readonly EntryId[] {
  return ENTRIES.filter((id) => can(ENTRY_REQUIRES[id]));
}

/** Las entradas que abren un panel (E2). */
const PANEL_ENTRIES: readonly EntryId[] = ['settings', 'home', 'receivables', 'payables', 'vat'];

export function entryIndex(id: EntryId): number {
  return ENTRIES.indexOf(id);
}

export function isPanelEntry(index: number): boolean {
  const id = ENTRIES[index];
  return id !== undefined && PANEL_ENTRIES.includes(id);
}

/** Las pantallas del motor que lleva cada panel mientras su contenido se rehace (§2.2): las de
 *  su entrada en screens/sections.ts (con los IBAN en Inicio e Importar en Cuentas por cobrar).
 *  La primera es su resumen. */
export const PANEL_SCREENS: Readonly<Record<'home' | 'receivables' | 'payables' | 'vat', readonly ViewId[]>> = {
  home: SECTION_VIEWS.home,
  receivables: SECTION_VIEWS.receivables,
  payables: SECTION_VIEWS.payables,
  vat: SECTION_VIEWS.vat,
};

/** La entrada de la rueda desde la que se llega a una vista (lo usa tambien e2e/nav.ts). */
export function entryOfView(view: ViewId): EntryId {
  if (view === 'documents') return 'documents';
  if (view === 'read-invoices') return 'process';
  if (view === 'settings') return 'settings';
  for (const entry of ['home', 'receivables', 'payables', 'vat'] as const) if (PANEL_SCREENS[entry].includes(view)) return entry;
  throw new Error(`vista sin entrada: ${view}`);
}

/** La fase de la onda: en E0 recien entrado, la misma que en Aurora (0) (§1.4). */
export function flowPhase(active: number): number {
  return (active - START_ENTRY) * 1.4;
}

/** Donde se esta: el inicio de Aurora (E0 a E5 y L0) o una pantalla con su camino. */
export type Screen = 'home' | 'work';

/** Los filtros de la busqueda que llegan ya puestos (E5-p): parametros de /api/v2/buscar. */
export type SearchPreset = Readonly<Record<string, string>>;

export interface AuroraState {
  screen: Screen;
  /** La pantalla de trabajo: Documentos o una pantalla del motor, con su camino (migas). */
  work: readonly Route[];
  /** Sube cada vez que se entra en una pantalla de trabajo: empieza su camino de cero. */
  workSeq: number;
  open: boolean;
  active: number;
  panel: number | null;
  /** La vista de un grupo dentro del panel (null: en reposo). */
  view: string | null;
  chatting: boolean;
  searchMode: boolean;
  /** Los filtros con que se entro en la busqueda (E5-p); null: la busqueda vacia. */
  search: SearchPreset | null;
  /** Lo escrito en la caja. */
  text: string;
}

export const INITIAL_STATE: AuroraState = {
  screen: 'home',
  work: [],
  workSeq: 0,
  open: false,
  active: START_ENTRY,
  panel: null,
  view: null,
  chatting: false,
  searchMode: false,
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
  /** Un paso de rueda: la rueda del raton, una flecha o el dedo. */
  /** Un paso de la rueda; `last`: la ultima entrada que ve esta persona (sin permiso para
   *  Procesar, la de antes). */
  | { type: 'step'; delta: number; last?: number }
  /** El foco en una fila de la rueda (Tab). */
  | { type: 'focusEntry'; index: number }
  /** El clic en una entrada que abre un panel. */
  | { type: 'enterPanel'; index: number; view?: string | null }
  /** La entrada Busqueda (o una fila que es una busqueda de facturas: E5-p, F9). */
  | { type: 'enterSearch'; index?: number; preset?: SearchPreset | null }
  /** Una pantalla de trabajo: Documentos, una pantalla del motor o una ficha (con vuelo). */
  | { type: 'enterWork'; trail: readonly Route[]; index?: number }
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
  return { ...state, screen: 'home', open: false, panel: null, view: null, chatting: false, searchMode: false, search: null, text: '' };
}

export function auroraReducer(state: AuroraState, action: AuroraAction): AuroraState {
  switch (action.type) {
    case 'reset':
      return { ...INITIAL_STATE, workSeq: state.workSeq };
    case 'orb': {
      if (state.screen !== 'home') return state;
      // Con panel, siempre cierra y vuelve a E0 (aunque se este escribiendo).
      if (state.panel !== null) return homeState(state);
      if (state.searchMode) return { ...state, searchMode: false, search: null, open: false };
      if (state.chatting) return { ...state, chatting: false, open: false, text: '' };
      // Con Procesar en el centro, el orbe entra en Procesar: lo hace quien llama (enterWork);
      // aqui solo se abre o se cierra el menu.
      return { ...state, open: !state.open };
    }
    case 'openMenu':
      if (state.screen !== 'home' || state.chatting || state.searchMode || state.panel !== null) return state;
      return { ...state, open: true };
    case 'step':
      // Solo con el menu a la vista: con un panel, la rueda escondida no manda.
      if (!state.open || state.chatting || state.panel !== null || state.screen !== 'home') return state;
      return { ...state, active: clampEntry(state.active + Math.sign(action.delta), action.last) };
    case 'focusEntry':
      if (!state.open || state.panel !== null || state.screen !== 'home') return state;
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
        search: action.preset ?? null,
        open: false,
        panel: null,
        view: null,
        chatting: false,
        text: '',
      };
    case 'enterWork':
      return {
        ...homeState(state),
        screen: 'work',
        work: action.trail,
        workSeq: state.workSeq + 1,
        active: action.index === undefined ? state.active : clampEntry(action.index),
      };
    case 'closePanel':
      if (state.panel === null) return state;
      return { ...state, panel: null, view: null, open: true, active: state.panel };
    case 'panelView':
      if (state.panel === null) return state;
      return { ...state, view: action.view };
    case 'text':
      // main.tsx:40: la primera tecla lleva a E3 y cierra el menu (el panel sigue, como en Aurora).
      if (action.value.length) return { ...state, text: action.value, chatting: true, open: false };
      return { ...state, text: action.value };
    case 'send':
      if (!state.text.trim()) return state;
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
  const screen = state.panel !== null || conversation || state.searchMode;
  const menu = state.open && !state.chatting && state.panel === null && !state.searchMode;
  return { menu, screen };
}
