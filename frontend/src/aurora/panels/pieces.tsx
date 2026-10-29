// Las piezas del panel de Aurora (main.tsx:34-39 del dueno, styles.css:3-4), exactas: panel-top
// con su etiqueta y la ✕, el h2, .panel-desc, .sample-label, la cifra principal (.balance), el
// titulo de una lista (.list-title), las filas .doc (icono, strong y small, doc-end), la tarjeta
// .detail, el campo .search, .empty, .success y los botones .outline y .primary.
// Cada panel tiene dos niveles (especificacion §2.2): en reposo, una fila por grupo; la vista de
// un grupo, con sus filas (5 como mucho, "Y N mas") y "Volver a …". Escape cierra primero lo de
// dentro: la tarjeta, la vista y, si no hay nada abierto, el panel (como su ✕). Una vista se abre
// arriba del todo; al volver, el panel recupera el desplazamiento que tenia (F6).
import { FileText, Search, X, type LucideIcon } from 'lucide-react';
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { fmt, useT } from '@/i18n';
import { paths, type Panel } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { fold } from '@/lib/text';
import { OrderNotice } from '../orders';
import { useAurora } from '../root';

/** Como mucho tantas filas en la vista de un grupo; las demas, escribiendo en .search. */
export const VIEW_ROWS = 5;

/** De cuando son los datos: la linea .sample-label (§2.2). */
function useSampleLine(): string {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [asOf, setAsOf] = useState<string | null>(null);
  const demo = session?.environment === 'demo';
  useEffect(() => {
    if (!session || demo) return;
    let alive = true;
    session.api.get<{ panel: Panel }>(paths.panel).then(
      (r) => alive && setAsOf(r.panel.estado_del),
      () => undefined
    );
    return () => {
      alive = false;
    };
  }, [session, demo, version]);
  if (demo) return t.aurora.panel.sampleTest;
  return asOf ? fmt(t.aurora.panel.sampleAsOf, { date: formatDate(asOf) }) : t.aurora.panel.sampleEur;
}

interface PanelFrameProps {
  title: string;
  description: string;
  /** La vista abierta (null: en reposo): al cambiar, el desplazamiento de F6. */
  view: string | null;
  /** Escape: cerrar lo de dentro o el panel. */
  onEscape: () => void;
  children: ReactNode;
}

/** El marco del panel: panel-top, h2, .panel-desc, .sample-label y lo de dentro; al final, lo
 *  hecho por la ultima orden (.success). */
export function PanelFrame({ title, description, view, onEscape, children }: PanelFrameProps) {
  const { t } = useT();
  const { dispatch } = useAurora();
  const sample = useSampleLine();
  const ref = useRef<HTMLElement>(null);
  const restScroll = useRef(0);
  const shownView = useRef(view);
  const [notice, setNotice] = useState<string | null>(null);
  const escape = useRef(onEscape);
  escape.current = onEscape;

  const titleId = useId();

  useEffect(() => {
    // Escape, y Alt+← (la salida visible: lo mismo que la ✕, lo de dentro primero; §1.6).
    const onKey = (e: KeyboardEvent) => {
      const back = e.altKey && !e.ctrlKey && e.key === 'ArrowLeft';
      if ((e.key !== 'Escape' && !back) || e.defaultPrevented) return;
      // Un desplegable (fecha, lista) se cierra solo.
      if (document.querySelector('[data-radix-popper-content-wrapper]')) return;
      e.preventDefault();
      escape.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Una vista se abre arriba del todo; al volver al reposo, el desplazamiento que tenia.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || shownView.current === view) return;
    if (shownView.current === null) restScroll.current = el.scrollTop;
    el.scrollTop = view === null ? restScroll.current : 0;
    shownView.current = view;
    setNotice(null);
  }, [view]);

  return (
    <aside className='panel' ref={ref} aria-labelledby={titleId}>
      <div className='panel-top'>
        <span>{t.aurora.panel.workspace}</span>
        <button aria-label={t.aurora.panel.close} onClick={() => dispatch({ type: 'closePanel' })}>
          <X size={19} />
        </button>
      </div>
      {/* El foco llega aqui al abrirse (root.tsx): el lector de pantalla dice que panel es. */}
      <h2 id={titleId} tabIndex={-1}>
        {title}
      </h2>
      <p className='panel-desc'>{description}</p>
      <div className='sample-label'>
        <i /> {sample}
      </div>
      <OrderNotice.Provider value={setNotice}>{children}</OrderNotice.Provider>
      {notice && <Notice text={notice} />}
    </aside>
  );
}

/** Lo hecho por la ultima orden (.success), a la vista. */
function Notice({ text }: { text: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => ref.current?.scrollIntoView({ block: 'nearest' }), [text]);
  return (
    <p className='success' role='status' ref={ref}>
      {text}
    </p>
  );
}

/** La cifra principal del panel (.balance): su etiqueta, la cifra de 33 px, la barra (la parte
 *  que dice `share`, de 0 a 1: en Aurora, fija al 68 %) y su nota. */
export function Balance({ label, figure, share, note }: { label: string; figure: string; share: number | null; note: ReactNode }) {
  const style = share === null ? undefined : ({ '--balance-share': `${Math.round(Math.max(0, Math.min(1, share)) * 100)}%` } as CSSProperties);
  return (
    <div className='balance' data-testid='balance'>
      <span>{label}</span>
      <strong>{figure}</strong>
      <div className='balance-line' style={style} />
      <p>{note}</p>
    </div>
  );
}

export interface RowProps {
  label: string;
  /** Lo que es (gris, debajo). */
  note?: string;
  /** La cifra de doc-end (un importe o un numero). */
  figure?: string;
  /** El estado de doc-end. */
  state?: string;
  /** El color del estado: .paid (nada pendiente) o .blocked (el rojo de .ui-status.offline). */
  tone?: 'paid' | 'blocked' | '';
  /** El nombre viene de los datos (una persona, una empresa, un numero). */
  data?: boolean;
  /** La nota viene de los datos. */
  noteData?: boolean;
  /** El icono de la fila (FileText, el de la lista de Aurora). */
  icon?: LucideIcon;
  /** El nombre para un lector de pantalla, si el visible no basta. */
  ariaLabel?: string;
  /** La fila de la tarjeta abierta. */
  current?: boolean;
  onOpen: () => void;
}

/** Una fila .doc de Aurora: icono, strong y small, doc-end. */
export function Row({ label, note, figure, state, tone = '', data, noteData, icon: Icon = FileText, ariaLabel, current, onOpen }: RowProps) {
  return (
    <button className='doc' onClick={onOpen} aria-label={ariaLabel} aria-current={current ? 'true' : undefined}>
      <span className='doc-icon'>
        <Icon size={18} />
      </span>
      <span>
        <strong data-proper-name={data ? '' : undefined}>{label}</strong>
        {note !== undefined && note !== '' && <small data-proper-name={noteData ? '' : undefined}>{note}</small>}
      </span>
      {(figure !== undefined || state !== undefined) && (
        <span className='doc-end'>
          {figure !== undefined && <strong>{figure}</strong>}
          {state !== undefined && <small className={tone}>{state}</small>}
        </span>
      )}
    </button>
  );
}

/** El titulo de una lista (.list-title) y sus filas (.doc-list). */
export function List({ title, count, children }: { title: string; count: number | string; children: ReactNode }) {
  return (
    <>
      <div className='list-title'>
        {title} <span>{count}</span>
      </div>
      <div className='doc-list'>{children}</div>
    </>
  );
}

/** La tarjeta .detail de Aurora, al final del panel, con su ✕. Si queda fuera de la vista, el
 *  panel se desplaza lo justo para ensenarla (sin animacion). */
export function Detail({
  title,
  onClose,
  icon: Icon = FileText,
  titleData,
  children,
}: {
  title: string;
  onClose: () => void;
  icon?: LucideIcon;
  titleData?: boolean;
  children: ReactNode;
}) {
  const { t } = useT();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ block: 'nearest' });
  }, [title]);
  return (
    <div className='detail' ref={ref} role='region' aria-label={title}>
      <button className='detail-close' aria-label={t.aurora.panel.closeDetail} onClick={onClose}>
        <X size={16} />
      </button>
      <Icon size={22} />
      <h3 data-proper-name={titleData ? '' : undefined}>{title}</h3>
      {children}
    </div>
  );
}

/** "Volver a …" (.outline) al final de una vista. */
export function BackButton({ label, onBack }: { label: string; onBack: () => void }) {
  return (
    <button className='outline' onClick={onBack}>
      {label}
    </button>
  );
}

/**
 * La vista de un grupo (§2.2, punto 2): el campo .search (si caben mas de 5), 5 filas como mucho,
 * "Y N mas" y "Volver a …". El filtro mira la lista entera, sin mayusculas ni acentos; con
 * `onServerQuery` la lista tiene tope (las lineas del banco) y el filtro va al servidor.
 */
export function GroupView<T>({
  items,
  title,
  match,
  render,
  backLabel,
  onBack,
  after,
  total,
  searchable,
  onServerQuery,
}: {
  items: readonly T[];
  title: string;
  /** El texto de una fila, para el filtro. */
  match: (item: T) => string;
  render: (item: T) => ReactNode;
  backLabel: string;
  onBack: () => void;
  /** Lo que va entre la lista y "Volver" (la tarjeta va despues, al final del panel). */
  after?: ReactNode;
  /** Cuantas hay en total (la lectura tiene tope): "Y N lineas mas". */
  total?: number;
  /** Con .search aunque haya 5 o menos (la lista entera tiene mas). */
  searchable?: boolean;
  onServerQuery?: (query: string) => void;
}) {
  const { t } = useT();
  const [query, setQuery] = useState('');
  const server = useRef(onServerQuery);
  server.current = onServerQuery;
  useEffect(() => {
    if (!server.current) return;
    const timer = setTimeout(() => server.current?.(query.trim()), 250);
    return () => clearTimeout(timer);
  }, [query]);
  const shown = useMemo(() => {
    if (onServerQuery) return items;
    const q = fold(query).trim();
    return q ? items.filter((i) => fold(match(i)).includes(q)) : items;
  }, [items, query, match, onServerQuery]);
  const all = total ?? shown.length;
  const more = all - Math.min(VIEW_ROWS, shown.length);
  return (
    <>
      {(searchable || items.length > VIEW_ROWS || (total ?? 0) > VIEW_ROWS) && (
        <label className='search'>
          <Search size={17} />
          <input placeholder={t.aurora.panel.searchPlaceholder} aria-label={t.aurora.panel.searchPlaceholder} value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      )}
      <List title={title} count={all}>
        {shown.slice(0, VIEW_ROWS).map(render)}
        {shown.length === 0 && <p className='empty'>{query ? t.aurora.panel.noMatches : t.aurora.panel.nothing}</p>}
        {more > 0 && shown.length > 0 && <p className='empty'>{total !== undefined ? (more === 1 ? t.aurora.panel.moreLinesOne : fmt(t.aurora.panel.moreLines, { n: more })) : fmt(t.aurora.panel.more, { n: more })}</p>}
      </List>
      {after}
      <BackButton label={backLabel} onBack={onBack} />
    </>
  );
}
