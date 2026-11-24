// E2-A, el panel Ajustes (especificacion §2.2.5): tu cuenta y la de tu equipo. Sin cifra
// principal, como los paneles 0, 1 y 4 de Aurora. En reposo, cuatro filas (Idioma, Tema, Tu
// cuenta y Sistema) y "Salir". Idioma y Tema abren su vista de tres filas: pulsar una la pone al
// momento (la elegida dice "En uso", en verde). Sistema abre la suya: Empresa, Aislamiento (con su
// .ui-status), Personas (otra vista, con .search) y Copias; cada una, su tarjeta con lo que
// ensenaba la pantalla de Ajustes de antes. "Salir" sale al momento y lleva a la entrada.
// Paso 18 (solo Docker, especificacion §6.1): Systeem gana el buzon de facturas y la lectura
// automatica, cada una con su tarjeta (mailbox-card.tsx, auto-read-card.tsx). En la nativa no hay
// correo (GET /api/v2/correo dice entorno nativo) y Systeem se queda como estaba. La vista
// 'mailbox' es Systeem con la tarjeta del buzon abierta (la abre la linea de Inicio).
import { LogOut } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { WithScriptNames } from '@/components/script-names';
import { StatusPill } from '@/components/status-pill';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { permissionText, roleText, templateCatalog } from '@/i18n/domain';
import { formatWith } from '@/i18n/templates';
import { paths } from '@/lib/api';
import type { Company, Isolation, Mailbox, PersonWithRoles } from '@/lib/api-types';
import { rowTone } from '@/components/status-pill';
import { useRefresh } from '@/lib/refresh';
import { roleOf, useCan, useSession } from '@/lib/session';
import { THEME_CHOICES, useTheme, type ThemeChoice } from '@/lib/theme';
import { entryLabel } from '../app';
import { useAurora } from '../root';
import { AutoReadCard } from './auto-read-card';
import { MailboxCard } from './mailbox-card';
import { autoReadState, autoReadStateText, mailboxAvailable, mailboxStateText } from './mailbox-model';
import { roleIsolation, worstIsolation } from './panel-model';
import { Detail, GroupView, List, PanelFrame, Row } from './pieces';

type SystemRow = 'company' | 'isolation' | 'people' | 'backups' | 'mailbox' | 'autoRead';

function systemRow(t: Messages, row: SystemRow): { label: string; note: string } {
  const s = t.aurora.settings;
  return {
    company: { label: s.systemRows.company, note: s.systemNotes.company },
    isolation: { label: s.systemRows.isolation, note: s.systemNotes.isolation },
    people: { label: s.systemRows.people, note: s.systemNotes.people },
    backups: { label: s.systemRows.backups, note: s.systemNotes.backups },
    mailbox: { label: s.systemRows.mailbox, note: s.systemNotes.mailbox },
    autoRead: { label: s.systemRows.autoRead, note: s.systemNotes.autoRead },
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

type SettingsCard = 'account' | 'company' | 'isolation' | 'backups' | 'mailbox' | 'autoRead' | `person:${number}` | null;

/** Lo que el sistema cuenta de si mismo (las lecturas de hoy de settings.tsx) y, desde el paso
 *  18, el buzon de facturas y la lectura automatica (GET /api/v2/correo; si no se puede leer,
 *  Systeem sale igual, sin sus dos filas). Se vuelve a leer tras cada orden (useRefresh). */
function useSystem(enabled: boolean) {
  const { session } = useSession();
  const { version } = useRefresh();
  const can = useCan();
  const admin = can('admin');
  const [data, setData] = useState<{ company: Company; isolation: Isolation; people: PersonWithRoles[] | null; mailbox: Mailbox | null } | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled || !session) return;
    let alive = true;
    Promise.all([
      session.api.get<{ empresa: Company }>(paths.company).then((r) => r.empresa),
      session.api.get<{ aislamiento: Isolation }>(paths.isolation).then((r) => r.aislamiento),
      admin ? session.api.get<{ personas: PersonWithRoles[] }>(paths.people).then((r) => r.personas) : Promise.resolve(null),
      session.api.get<{ correo: Mailbox }>(paths.mailbox).then(
        (r) => r.correo,
        () => null
      ),
    ]).then(
      ([company, isolation, people, mailbox]) => alive && setData({ company, isolation, people, mailbox }),
      () => alive && setFailed(true)
    );
    return () => {
      alive = false;
    };
  }, [enabled, session, admin, version]);
  return { data, failed };
}

export function SettingsPanel({ view }: { view: string | null }) {
  const { t, lang, setLang } = useT();
  const { session, logout } = useSession();
  const { choice, setChoice } = useTheme();
  const { dispatch } = useAurora();
  const [card, setCard] = useState<SettingsCard>(view === 'mailbox' ? 'mailbox' : null);
  const system = useSystem(view === 'system' || view === 'people' || view === 'mailbox');
  // Desde la linea de Inicio: Systeem con la tarjeta del buzon.
  useEffect(() => {
    if (view === 'mailbox') setCard('mailbox');
  }, [view]);
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
            tone={code === lang ? 'paid' : ''}
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
          <Row key={c} label={themeName(c)} note={themeNote(t, c)} state={c === choice ? s.inUse : undefined} tone={c === choice ? 'paid' : ''} onOpen={() => setChoice(c)} />
        )}
        backLabel={fmt(t.aurora.panel.backTo, { what: entryLabel(t, 'settings') })}
        onBack={() => setView(null)}
      />
    );
  } else if (view === 'system' || view === 'mailbox') {
    const mailbox = system.data?.mailbox ?? null;
    const mail = mailboxAvailable(mailbox) ? mailbox : null;
    const items: SystemRow[] = ['company', 'isolation', ...(system.data?.people ? (['people'] as const) : []), 'backups', ...(mail ? (['mailbox', 'autoRead'] as const) : [])];
    const isolation = system.data?.isolation;
    const isolationState = !isolation ? undefined : !isolation.aplica ? s.notApplicable : isolation.correcto ? s.isolationOk : s.isolationBad;
    const autoState = mail ? autoReadState(mail.lectura_automatica) : null;
    const stateOf = (k: SystemRow): { state?: string; tone: 'paid' | 'blocked' | '' } => {
      if (k === 'isolation') return { state: isolationState, tone: isolation?.correcto === true ? 'paid' : '' };
      if (k === 'company' && system.data) return { state: system.data.company.completa ? s.complete : s.incomplete, tone: system.data.company.completa ? 'paid' : '' };
      if (k === 'mailbox' && mail) return { state: mailboxStateText(mail.estado, t), tone: rowTone('correo', mail.estado) };
      if (k === 'autoRead' && autoState) return { state: autoReadStateText(autoState, t), tone: rowTone('lectura_automatica', autoState) };
      return { tone: '' };
    };
    body = (
      <GroupView
        items={items}
        title={s.system.toUpperCase()}
        match={(k) => systemRow(t, k).label}
        limit={items.length}
        render={(k) => (
          <Row
            key={k}
            label={systemRow(t, k).label}
            note={systemRow(t, k).note}
            state={stateOf(k).state}
            tone={stateOf(k).tone}
            current={card === k}
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
            {card === 'mailbox' && mail && <MailboxCard mailbox={mail} onClose={() => setCard(null)} />}
            {card === 'autoRead' && mail && <AutoReadCard mailbox={mail} onClose={() => setCard(null)} />}
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
    <PanelFrame title={view === 'people' ? s.systemRows.people : entryLabel(t, 'settings')} description={s.description} view={view} onEscape={onEscape}>
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
          <p>
            <StatusPill group='aislamiento' state={i.correcto ? 'correcto' : worstIsolation(i)} label={isolationState(t, i.correcto ? 'correcto' : worstIsolation(i))} />
          </p>
          {i.papeles.map((p) => (
            <p key={p.papel}>
              {roleName(p.papel)}: <StatusPill group='aislamiento' state={roleIsolation(p)} label={isolationState(t, roleIsolation(p))} />
            </p>
          ))}
          <span>{i.correcto ? t.settings.isolationOk : <WithScriptNames text={t.settings.isolationProblem} />}</span>
        </>
      ) : (
        <p>{i.entorno === 'contenedor' ? t.settings.isolationContainer : t.settings.isolationLocal}</p>
      )}
    </Detail>
  );
}
