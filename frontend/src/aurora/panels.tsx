// Los paneles (E2): el .panel de Aurora (main.tsx:34-39, styles.css:3-4) con sus piezas exactas:
// panel-top con su etiqueta y la ✕, el h2, .panel-desc, .sample-label, .list-title, las filas
// .doc (icono, strong y small, doc-end), la tarjeta .detail y los botones .outline y .primary.
// Cada panel tiene dos niveles (especificacion §2.2): en reposo, una fila por grupo; la vista de
// un grupo, con sus filas (5 como mucho y "Y N mas") y "Volver a …". Escape cierra primero lo
// de dentro: la tarjeta, la vista y, si no hay nada abierto, el panel (como su ✕).
//
// Este paso trae el marco y Ajustes (E2-A) entero. Inicio, Cuentas por cobrar, Cuentas por
// pagar e IVA llevan, mientras su contenido se rehace en el lenguaje de Aurora, una fila por cada
// pantalla del motor que ya tenian: abrirla es ir a esa pantalla, con el vuelo del orbe. Asi
// ninguna funcion se pierde mientras tanto.
import { FileText, LogOut, Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { WithScriptNames } from '@/components/script-names';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { permissionText, roleText, templateCatalog } from '@/i18n/domain';
import { formatWith } from '@/i18n/templates';
import { paths, type Panel } from '@/lib/api';
import type { Company, Isolation, PersonWithRoles } from '@/lib/api-types';
import { formatDate } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { roleOf, useCan, useSession } from '@/lib/session';
import { fold } from '@/lib/text';
import { THEME_CHOICES, useTheme, type ThemeChoice } from '@/lib/theme';
import { VIEWS, viewRoute } from '@/screens/registry';
import { roleIsolation, worstIsolation } from '@/screens/settings';
import { badgeFor, useBadgeCounts } from '@/shell/use-badges';
import { entryLabel } from './app';
import { PANEL_SCREENS, type EntryId } from './estado';
import { useAurora } from './root';

/** Como mucho tantas filas en la vista de un grupo; las demas, escribiendo en .search. */
const VIEW_ROWS = 5;

// ---------------------------------------------------------------- las piezas

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
  /** Escape y la ✕ de arriba: cerrar lo de dentro o el panel. */
  onEscape: () => void;
  children: ReactNode;
}

/** El marco del panel: panel-top, h2, .panel-desc y .sample-label. */
function PanelFrame({ title, description, onEscape, children }: PanelFrameProps) {
  const { t } = useT();
  const { dispatch } = useAurora();
  const sample = useSampleLine();
  const escape = useRef(onEscape);
  escape.current = onEscape;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      // Un desplegable o un dialogo abierto se cierra solo.
      if (document.querySelector('[role="dialog"], [data-radix-popper-content-wrapper]')) return;
      e.preventDefault();
      escape.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return (
    <aside className='panel'>
      <div className='panel-top'>
        <span>{t.aurora.panel.workspace}</span>
        <button aria-label={t.aurora.panel.close} onClick={() => dispatch({ type: 'closePanel' })}>
          <X size={19} />
        </button>
      </div>
      <h2>{title}</h2>
      <p className='panel-desc'>{description}</p>
      <div className='sample-label'>
        <i /> {sample}
      </div>
      {children}
    </aside>
  );
}

interface RowProps {
  label: string;
  /** Lo que es (gris, debajo). */
  note?: string;
  /** La cifra de doc-end (un importe o un numero). */
  figure?: string;
  /** El estado de doc-end. */
  state?: string;
  /** Sin nada pendiente: .paid (#93b4a4). */
  paid?: boolean;
  /** El nombre viene de los datos (una persona, una empresa). */
  data?: boolean;
  onOpen: () => void;
}

/** Una fila .doc de Aurora: icono, strong y small, doc-end. */
function Row({ label, note, figure, state, paid, data, onOpen }: RowProps) {
  return (
    <button className='doc' onClick={onOpen}>
      <span className='doc-icon'>
        <FileText size={18} />
      </span>
      <span>
        <strong data-proper-name={data ? '' : undefined}>{label}</strong>
        {note !== undefined && <small>{note}</small>}
      </span>
      {(figure !== undefined || state !== undefined) && (
        <span className='doc-end'>
          {figure !== undefined && <strong>{figure}</strong>}
          {state !== undefined && <small className={paid ? 'paid' : ''}>{state}</small>}
        </span>
      )}
    </button>
  );
}

/** El titulo de una lista (.list-title) y sus filas (.doc-list). */
function List({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <>
      <div className='list-title'>
        {title} <span>{count}</span>
      </div>
      <div className='doc-list'>{children}</div>
    </>
  );
}

/** La tarjeta .detail de Aurora, al final de la lista, con su ✕. */
function Detail({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useT();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Si queda fuera de la vista, el panel se desplaza lo justo para ensenarla (sin animacion).
    ref.current?.scrollIntoView({ block: 'nearest' });
  }, [title]);
  return (
    <div className='detail' ref={ref}>
      <button className='detail-close' aria-label={t.aurora.panel.closeDetail} onClick={onClose}>
        <X size={16} />
      </button>
      <FileText size={22} />
      <h3>{title}</h3>
      {children}
    </div>
  );
}

/** La vista de un grupo: el campo .search (si caben mas de 5), 5 filas como mucho, "Y N mas" y
 *  "Volver a …" (§2.2, punto 2). */
function GroupView<T>({
  items,
  title,
  match,
  render,
  backLabel,
  onBack,
  after,
}: {
  items: readonly T[];
  title: string;
  /** El texto de una fila, para el filtro (sin mayusculas ni acentos). */
  match: (item: T) => string;
  render: (item: T) => ReactNode;
  backLabel: string;
  onBack: () => void;
  after?: ReactNode;
}) {
  const { t } = useT();
  const [query, setQuery] = useState('');
  const shown = useMemo(() => {
    const q = fold(query).trim();
    return q ? items.filter((i) => fold(match(i)).includes(q)) : items;
  }, [items, query, match]);
  return (
    <>
      {items.length > VIEW_ROWS && (
        <label className='search'>
          <Search size={17} />
          <input placeholder={t.aurora.panel.searchPlaceholder} value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      )}
      <List title={title} count={shown.length}>
        {shown.slice(0, VIEW_ROWS).map(render)}
        {shown.length === 0 && <p className='empty'>{t.aurora.panel.noMatches}</p>}
        {shown.length > VIEW_ROWS && <p className='empty'>{fmt(t.aurora.panel.more, { n: shown.length - VIEW_ROWS })}</p>}
      </List>
      {after}
      <button className='outline' onClick={onBack}>
        {backLabel}
      </button>
    </>
  );
}

// ---------------------------------------------------------------- Ajustes (E2-A)

/** La frase de cada panel (.panel-desc). */
function panelDescription(t: Messages, entry: 'home' | 'receivables' | 'payables' | 'vat'): string {
  const d = t.aurora.panel.descriptions;
  return { home: d.home, receivables: d.receivables, payables: d.payables, vat: d.vat }[entry];
}

type SystemRow = 'company' | 'isolation' | 'people' | 'backups';

function systemRow(t: Messages, row: SystemRow): { label: string; note: string } {
  const s = t.aurora.settings;
  return {
    company: { label: s.systemRows.company, note: s.systemNotes.company },
    isolation: { label: s.systemRows.isolation, note: s.systemNotes.isolation },
    people: { label: s.systemRows.people, note: s.systemNotes.people },
    backups: { label: s.systemRows.backups, note: s.systemNotes.backups },
  }[row];
}

function themeNote(t: Messages, choice: ThemeChoice): string {
  const n = t.aurora.settings.themeNotes;
  return { dark: n.dark, light: n.light, system: n.system }[choice];
}

function isolationState(t: Messages, state: string): string {
  const n = t.aurora.settings.isolationStates;
  return ({ correcto: n.correcto, falla: n.falla, caducada: n.caducada, sin_comprobar: n.sin_comprobar } as Record<string, string>)[state] ?? state;
}

function languageName(t: Messages, code: Lang): string {
  return code === 'nl' ? t.language.nlLong : code === 'en' ? t.language.enLong : t.language.esLong;
}

type SettingsCard = 'account' | 'company' | 'isolation' | 'backups' | `person:${number}` | null;

/** Lo que el sistema cuenta de si mismo (las lecturas de hoy de settings.tsx). */
function useSystem(enabled: boolean) {
  const { session } = useSession();
  const can = useCan();
  const admin = can('admin');
  const [data, setData] = useState<{ company: Company; isolation: Isolation; people: PersonWithRoles[] | null } | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled || !session) return;
    let alive = true;
    Promise.all([
      session.api.get<{ empresa: Company }>(paths.company).then((r) => r.empresa),
      session.api.get<{ aislamiento: Isolation }>(paths.isolation).then((r) => r.aislamiento),
      admin ? session.api.get<{ personas: PersonWithRoles[] }>(paths.people).then((r) => r.personas) : Promise.resolve(null),
    ]).then(
      ([company, isolation, people]) => alive && setData({ company, isolation, people }),
      () => alive && setFailed(true)
    );
    return () => {
      alive = false;
    };
  }, [enabled, session, admin]);
  return { data, failed };
}

function SettingsPanel({ view }: { view: string | null }) {
  const { t, lang, setLang } = useT();
  const { session, logout } = useSession();
  const { choice, setChoice } = useTheme();
  const { dispatch } = useAurora();
  const [card, setCard] = useState<SettingsCard>(null);
  const system = useSystem(view === 'system' || view === 'people');
  const s = t.aurora.settings;
  const me = session?.me;
  const setView = (next: string | null) => {
    setCard(null);
    dispatch({ type: 'panelView', view: next });
  };
  const onEscape = () => {
    if (card) setCard(null);
    else if (view === 'people') setView('system');
    else if (view) setView(null);
    else dispatch({ type: 'closePanel' });
  };
  const themeName = (c: ThemeChoice) => t.theme[c];
  const role = me ? ({ admin: t.account.roleAdmin, staff: t.account.roleStaff, readOnly: t.account.roleReadOnly } as const)[roleOf(me.permisos)] : '';
  const roles = (me?.roles ?? []).map((r) => roleText(lang, r)?.label ?? r);
  const permissions = [...(me?.permisos ?? [])].map((p) => permissionText(lang, p)).filter((p): p is NonNullable<typeof p> => p !== null);
  const languages: Lang[] = ['es', 'nl', 'en'];

  let body: ReactNode;
  if (view === 'language') {
    body = (
      <GroupView
        items={languages}
        title={s.language.toUpperCase()}
        match={(code) => languageName(t, code)}
        render={(code) => (
          <Row
            key={code}
            label={languageName(t, code)}
            note={s.languageNote}
            state={code === lang ? s.inUse : undefined}
            paid={code === lang}
            onOpen={() => setLang(code)}
          />
        )}
        backLabel={fmt(t.aurora.panel.backTo, { what: entryLabel(t, 'settings') })}
        onBack={() => setView(null)}
      />
    );
  } else if (view === 'theme') {
    body = (
      <GroupView
        items={THEME_CHOICES}
        title={s.theme.toUpperCase()}
        match={themeName}
        render={(c) => (
          <Row key={c} label={themeName(c)} note={themeNote(t, c)} state={c === choice ? s.inUse : undefined} paid={c === choice} onOpen={() => setChoice(c)} />
        )}
        backLabel={fmt(t.aurora.panel.backTo, { what: entryLabel(t, 'settings') })}
        onBack={() => setView(null)}
      />
    );
  } else if (view === 'system') {
    const items = (['company', 'isolation', ...(system.data?.people ? (['people'] as const) : []), 'backups'] as const).map((k) => k);
    const isolation = system.data?.isolation;
    const isolationState = !isolation ? undefined : !isolation.aplica ? s.notApplicable : isolation.correcto ? s.isolationOk : s.isolationBad;
    body = (
      <GroupView
        items={items}
        title={s.system.toUpperCase()}
        match={(k) => systemRow(t, k).label}
        render={(k) => (
          <Row
            key={k}
            label={systemRow(t, k).label}
            note={systemRow(t, k).note}
            state={k === 'isolation' ? isolationState : k === 'company' && system.data ? (system.data.company.completa ? s.complete : s.incomplete) : undefined}
            paid={k === 'isolation' ? isolation?.correcto === true : k === 'company' ? system.data?.company.completa === true : false}
            onOpen={() => (k === 'people' ? setView('people') : setCard(k))}
          />
        )}
        backLabel={fmt(t.aurora.panel.backTo, { what: entryLabel(t, 'settings') })}
        onBack={() => setView(null)}
        after={
          <>
            {system.failed && <p className='empty'>{t.errors.unexpected}</p>}
            {card === 'company' && system.data && <CompanyCard company={system.data.company} onClose={() => setCard(null)} />}
            {card === 'isolation' && system.data && <IsolationCard isolation={system.data.isolation} onClose={() => setCard(null)} />}
            {card === 'backups' && (
              <Detail title={systemRow(t, 'backups').label} onClose={() => setCard(null)}>
                <p>
                  <WithScriptNames text={t.settings.backupsText} />
                </p>
              </Detail>
            )}
          </>
        }
      />
    );
  } else if (view === 'people') {
    const people = system.data?.people ?? [];
    const person = typeof card === 'string' && card.startsWith('person:') ? people.find((p) => `person:${p.id}` === card) : undefined;
    body = (
      <GroupView
        items={people}
        title={s.systemRows.people.toUpperCase()}
        match={(p) => p.nombre}
        render={(p) => (
          <Row
            key={p.id}
            label={p.nombre}
            data
            note={(p.roles ?? []).map((r) => roleText(lang, r)?.label ?? r).join(', ') || '—'}
            onOpen={() => setCard(`person:${p.id}`)}
          />
        )}
        backLabel={fmt(t.aurora.panel.backTo, { what: s.system })}
        onBack={() => setView('system')}
        after={
          person && (
            <Detail title={person.nombre} onClose={() => setCard(null)}>
              <p>
                {t.settings.role}: {(person.roles ?? []).map((r) => roleText(lang, r)?.label ?? r).join(', ') || '—'}
              </p>
              <p>
                <WithScriptNames text={t.settings.peopleHelp} />
              </p>
            </Detail>
          )
        }
      />
    );
  } else {
    body = (
      <>
        <List title={s.listTitle} count={4}>
          <Row label={s.language} note={s.languageNote} figure={languageName(t, lang)} onOpen={() => setView('language')} />
          <Row label={s.theme} note={s.themeNote} figure={themeName(choice)} onOpen={() => setView('theme')} />
          <Row label={s.account} note={me?.nombre ?? ''} figure={role} onOpen={() => setCard('account')} />
          <Row label={s.system} note={s.systemNote} onOpen={() => setView('system')} />
        </List>
        {card === 'account' && me && (
          <Detail title={me.nombre} onClose={() => setCard(null)}>
            <p>
              {t.settings.role}: {roles.length ? roles.join(', ') : role}
            </p>
            <p>{t.settings.accountHelp}</p>
            <span>{fmt(s.permissions, { n: permissions.length })}</span>
            {permissions.map((p) => (
              <p key={p.label}>{p.label}</p>
            ))}
          </Detail>
        )}
        <button className='outline' onClick={() => logout('loggedOut')}>
          <LogOut size={15} /> {t.account.logout}
        </button>
      </>
    );
  }
  return (
    <PanelFrame title={view === 'people' ? s.systemRows.people : entryLabel(t, 'settings')} description={s.description} onEscape={onEscape}>
      {body}
    </PanelFrame>
  );
}

function CompanyCard({ company: c, onClose }: { company: Company; onClose: () => void }) {
  const { t, lang } = useT();
  const missing = t.settings.notFilled;
  return (
    <Detail title={c.nombre} onClose={onClose}>
      <p>
        {t.settings.otherNames}: {c.otros_nombres.length ? c.otros_nombres.join(', ') : '—'}
      </p>
      <p>
        {t.settings.vatId}: {c.btw_id ?? missing}
      </p>
      <p>
        {t.settings.kvk}: {c.kvk ?? missing}
      </p>
      <p>
        {t.settings.ownAccounts}: {c.cuentas_propias.length ? c.cuentas_propias.map((iban) => formatWith('iban', iban, templateCatalog(lang))).join(' · ') : missing}
      </p>
      {!c.completa && <span>{t.settings.companyIncomplete}</span>}
      <p>
        <WithScriptNames text={t.settings.companyHelp} />
      </p>
    </Detail>
  );
}

function IsolationCard({ isolation: i, onClose }: { isolation: Isolation; onClose: () => void }) {
  const { t } = useT();
  const roleName = (r: string) => t.settings.roles[r as keyof typeof t.settings.roles] ?? r;
  return (
    <Detail title={t.settings.isolationTitle} onClose={onClose}>
      <p>{t.settings.isolationAlways}</p>
      {i.aplica ? (
        <>
          <span>{i.correcto ? t.settings.isolationOk : <WithScriptNames text={t.settings.isolationProblem} />}</span>
          {i.papeles.map((p) => (
            <p key={p.papel}>
              {roleName(p.papel)}: {isolationState(t, roleIsolation(p))}
            </p>
          ))}
          {!i.correcto && <p>{isolationState(t, worstIsolation(i))}</p>}
        </>
      ) : (
        <p>{i.entorno === 'contenedor' ? t.settings.isolationContainer : t.settings.isolationLocal}</p>
      )}
    </Detail>
  );
}

// ---------------------------------------------------------------- Inicio, cobrar, pagar e IVA
// Sus pantallas, de PANEL_SCREENS (aurora/estado.ts).

function ScreensPanel({ entry }: { entry: keyof typeof PANEL_SCREENS }) {
  const { t } = useT();
  const { session } = useSession();
  const can = useCan();
  const { version } = useRefresh();
  const { dispatch, go } = useAurora();
  const [counts] = useBadgeCounts(session, version);
  const views = PANEL_SCREENS[entry].filter((v) => can(VIEWS[v].requires));
  return (
    <PanelFrame title={entryLabel(t, entry)} description={panelDescription(t, entry)} onEscape={() => dispatch({ type: 'closePanel' })}>
      <List title={t.aurora.panel.screens} count={views.length}>
        {views.map((v) => {
          const badge = badgeFor(v, counts, t.badges);
          return (
            <Row
              key={v}
              label={v === entry ? t.aurora.panel.overview : t.nav[v].label}
              note={t.nav[v].description}
              figure={badge ? String(badge.count) : undefined}
              state={badge?.label}
              onOpen={() => go({ type: 'enterWork', trail: [viewRoute(v)] })}
            />
          );
        })}
      </List>
    </PanelFrame>
  );
}

/** El panel de una entrada. */
export function PanelFor({ entry }: { entry: EntryId }) {
  const { state } = useAurora();
  if (entry === 'settings') return <SettingsPanel view={state.view} />;
  if (entry === 'home' || entry === 'receivables' || entry === 'payables' || entry === 'vat') return <ScreensPanel key={entry} entry={entry} />;
  return null;
}
