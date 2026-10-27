// Instellingen / Settings / Ajustes: el idioma, el tema, quien eres (rol y lo que puedes
// hacer, en palabras), el bedrijf tal como lo usan las controles (solo lectura), como esta
// afscherming este programa (la comprobacion del aislamiento que el servidor ya lee, por
// partes), las personas (solo para quien administra) y donde se hacen las copias, en una
// frase. Lo unico que se ajusta aqui es el idioma y el tema: lo demas lo hace quien
// administra el programa, fuera de la app (sus .bat se llaman en castellano y la app los nombra
// asi en los tres idiomas: components/script-names.tsx).
import { WithScriptNames } from '@/components/script-names';
import { LogOut } from 'lucide-react';
import type { ReactNode } from 'react';
import { DataTable, type Columns } from '@/components/data-table';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { ErrorState, Loading } from '@/components/states';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import { LanguageSwitch } from '@/shell/language-switch';
import { ThemeSwitch } from '@/shell/theme-switch';
import { useT } from '@/i18n';
import { permissionText, roleText, templateCatalog } from '@/i18n/domain';
import { formatWith } from '@/i18n/templates';
import { paths } from '@/lib/api';
import type { Company, Isolation, PersonWithRoles } from '@/lib/api-types';
import { roleOf, useCan, useSession } from '@/lib/session';
import { useLoad } from './use-load';

export function SettingsScreen() {
  const { t } = useT();
  const nav = t.nav.settings;
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      <div className='flex max-w-3xl flex-col gap-6'>
        <div className='flex flex-col divide-y divide-border rounded-md border border-border bg-card'>
          <LanguageRow />
          <ThemeRow />
          <AccountRow />
        </div>
        <SystemInfo />
      </div>
    </Screen>
  );
}

function Row({ title, children, aside }: { title: ReactNode; children?: ReactNode; aside?: ReactNode }) {
  return (
    <section className='flex flex-wrap items-start justify-between gap-4 px-5 py-4'>
      <div className='min-w-0 flex-1'>
        <h2 className='font-semibold'>{title}</h2>
        {children}
      </div>
      {aside && <div className='shrink-0'>{aside}</div>}
    </section>
  );
}

function LanguageRow() {
  const { t } = useT();
  return (
    <Row title={t.language.label} aside={<LanguageSwitch />}>
      <p className='text-muted-foreground'>{t.settings.languageHelp}</p>
    </Row>
  );
}

function ThemeRow() {
  const { t } = useT();
  return (
    <Row title={t.theme.label} aside={<ThemeSwitch />}>
      <p className='text-muted-foreground'>{t.theme.help}</p>
    </Row>
  );
}

function AccountRow() {
  const { t, lang } = useT();
  const { session, logout } = useSession();
  const me = session?.me;
  const fallback = { admin: t.account.roleAdmin, staff: t.account.roleStaff, readOnly: t.account.roleReadOnly }[
    roleOf(me?.permisos ?? [])
  ];
  const roles = (me?.roles ?? []).map((r) => roleText(lang, r)?.label ?? r);
  const permissions = [...(me?.permisos ?? [])]
    .map((p) => permissionText(lang, p))
    .filter((p): p is NonNullable<typeof p> => p !== null);
  return (
    <Row
      title={`${t.account.signedInAs} ${me?.nombre ?? ''}`}
      aside={
        <Button variant='outline' onClick={() => logout('loggedOut')}>
          <LogOut className='mr-2 h-4 w-4' aria-hidden='true' />
          {t.account.logout}
        </Button>
      }
    >
      <p className='text-muted-foreground'>
        {t.settings.role}: {roles.length ? roles.join(', ') : fallback}. {t.settings.accountHelp}
      </p>
      {/* Catorce permisos son muchos para leerlos siempre: plegados, con su numero. */}
      <div className='mt-3'>
        <Section title={t.settings.permissionsTitle} summary={String(permissions.length)}>
          <ul className='grid grid-cols-1 gap-x-6 gap-y-1.5 text-[13px] md:grid-cols-2'>
            {permissions.map((p) => (
              <li key={p.label}>
                <span className='font-medium'>{p.label}</span>
                <span className='block text-xs text-muted-foreground'>{p.description}</span>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </Row>
  );
}

function SystemInfo() {
  const { session } = useSession();
  const can = useCan();
  const admin = can('admin');
  const [state, retry] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ empresa: Company }>(paths.company).then((r) => r.empresa),
        session!.api.get<{ aislamiento: Isolation }>(paths.isolation).then((r) => r.aislamiento),
        admin
          ? session!.api.get<{ personas: PersonWithRoles[] }>(paths.people).then((r) => r.personas)
          : Promise.resolve(null),
      ]),
    [session, admin]
  );
  if (state.status === 'loading') return <Loading />;
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={retry} />;
  const [company, isolation, people] = state.data;
  return (
    <div className='flex flex-col divide-y divide-border rounded-md border border-border bg-card'>
      <CompanyRow company={company} />
      <IsolationRow isolation={isolation} />
      {people && <PeopleRow people={people} />}
      <BackupsRow />
    </div>
  );
}

function CompanyRow({ company: c }: { company: Company }) {
  const { t, lang } = useT();
  const missing = <span className='text-muted-foreground'>{t.settings.notFilled}</span>;
  return (
    <Row title={t.settings.companyTitle}>
      <p className='text-muted-foreground'>
        <WithScriptNames text={t.settings.companyHelp} />
      </p>
      <dl className='mt-3 grid grid-cols-[12rem_1fr] gap-x-4 gap-y-1.5 text-[13px]'>
        <dt className='text-soft-foreground'>{t.parties.name}</dt>
        <dd className='m-0 font-medium'>{c.nombre}</dd>
        <dt className='text-soft-foreground'>{t.settings.otherNames}</dt>
        <dd className='m-0'>{c.otros_nombres.length ? c.otros_nombres.join(', ') : '—'}</dd>
        <dt className='text-soft-foreground'>{t.settings.vatId}</dt>
        <dd className='m-0 font-mono text-[12.5px]'>{c.btw_id ?? missing}</dd>
        <dt className='text-soft-foreground'>{t.settings.kvk}</dt>
        <dd className='m-0 font-mono text-[12.5px]'>{c.kvk ?? missing}</dd>
        <dt className='text-soft-foreground'>{t.settings.ownAccounts}</dt>
        <dd className='m-0 font-mono text-[12.5px]'>
          {/* En grupos de cuatro, como en IBAN-controles. */}
          {c.cuentas_propias.length
            ? c.cuentas_propias.map((iban) => <span key={iban} className='block'>{formatWith('iban', iban, templateCatalog(lang))}</span>)
            : missing}
        </dd>
      </dl>
      <p className='mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]'>
        <StatusPill group='empresa' state={c.completa ? 'completa' : 'incompleta'} />
        {!c.completa && <span>{t.settings.companyIncomplete}</span>}
      </p>
    </Row>
  );
}

/** El estado de un papel como lo manda la API (estado, 2.1); sin el, solo se sabe si va bien. */
export function roleIsolation(p: Isolation['papeles'][number]): string {
  return p.estado ?? (p.bien ? 'correcto' : 'falla');
}

/** Lo mas serio de los papeles, para la frase de arriba: una prueba que falla, despues lo
 *  comprobado hace demasiado y despues lo que nunca se comprobo. */
export function worstIsolation(i: Isolation): string {
  const states = i.papeles.map(roleIsolation);
  return ['falla', 'caducada', 'sin_comprobar'].find((s) => states.includes(s)) ?? 'falla';
}

function IsolationRow({ isolation: i }: { isolation: Isolation }) {
  const { t } = useT();
  const roleName = (r: string) => t.settings.roles[r as keyof typeof t.settings.roles] ?? r;
  return (
    <Row title={t.settings.isolationTitle}>
      <p className='text-muted-foreground'>{t.settings.isolationAlways}</p>
      {i.aplica ? (
        <>
          <p className='mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]'>
            <StatusPill group='aislamiento' state={i.correcto ? 'correcto' : worstIsolation(i)} />
            <span>{i.correcto ? t.settings.isolationOk : <WithScriptNames text={t.settings.isolationProblem} />}</span>
          </p>
          <ul className='mt-3 grid grid-cols-1 gap-x-8 gap-y-1.5 text-[13px] sm:grid-cols-2'>
            {i.papeles.map((p) => (
              <li key={p.papel} className='flex items-center justify-between gap-3'>
                <span>{roleName(p.papel)}</span>
                <StatusPill group='aislamiento' state={roleIsolation(p)} />
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className='mt-2 text-[13px]'>{i.entorno === 'contenedor' ? t.settings.isolationContainer : t.settings.isolationLocal}</p>
      )}
    </Row>
  );
}

function PeopleRow({ people }: { people: PersonWithRoles[] }) {
  const { t, lang } = useT();
  const columns: Columns<PersonWithRoles> = [
    { key: 'name', header: t.settings.name, cell: (p) => p.nombre },
    {
      key: 'role',
      header: t.settings.role,
      cell: (p) => (p.roles ?? []).map((r) => roleText(lang, r)?.label ?? r).join(', ') || '—',
    },
  ];
  return (
    <Row title={t.settings.peopleTitle}>
      <p className='mb-3 text-muted-foreground'>
        <WithScriptNames text={t.settings.peopleHelp} />
      </p>
      <DataTable columns={columns} rows={people} rowKey={(p) => p.id} caption={t.settings.peopleTitle} />
    </Row>
  );
}

function BackupsRow() {
  const { t } = useT();
  return (
    <Row title={t.settings.backupsTitle}>
      <p className='text-muted-foreground'>
        <WithScriptNames text={t.settings.backupsText} />
      </p>
    </Row>
  );
}
