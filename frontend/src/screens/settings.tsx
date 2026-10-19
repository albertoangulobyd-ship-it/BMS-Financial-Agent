// Instellingen / Settings: el idioma y la cuenta. Es lo unico que se puede ajustar desde
// la app; lo demas (personas, roles, politica) se hace con las ordenes del programa.
import { LogOut } from 'lucide-react';
import { PageHeader, Screen } from '@/components/page-header';
import { Button } from '@/components/ui/button';
import { LanguageSwitch } from '@/shell/language-switch';
import { useT } from '@/i18n';
import { roleOf, useSession } from '@/lib/session';

export function SettingsScreen() {
  const { t } = useT();
  const { session, logout } = useSession();
  const nav = t.nav.settings;
  const role = session ? roleOf(session.me.permisos) : 'readOnly';
  const roleText = { admin: t.account.roleAdmin, staff: t.account.roleStaff, readOnly: t.account.roleReadOnly }[role];
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      <div className='flex max-w-2xl flex-col divide-y divide-border rounded-md border border-border bg-card'>
        <section className='flex flex-wrap items-center justify-between gap-4 px-5 py-4'>
          <div>
            <h2 className='font-semibold'>{t.language.label}</h2>
            <p className='text-muted-foreground'>{t.settings.languageHelp}</p>
          </div>
          <LanguageSwitch />
        </section>
        <section className='flex flex-wrap items-center justify-between gap-4 px-5 py-4'>
          <div>
            <h2 className='font-semibold'>
              {t.account.signedInAs} {session?.me.nombre}
            </h2>
            <p className='text-muted-foreground'>
              {roleText}. {t.settings.accountHelp}
            </p>
          </div>
          <Button variant='outline' onClick={() => logout('loggedOut')}>
            <LogOut className='mr-2 h-4 w-4' aria-hidden='true' />
            {t.account.logout}
          </Button>
        </section>
      </div>
    </Screen>
  );
}
