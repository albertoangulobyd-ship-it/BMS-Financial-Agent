// El menu del nombre, arriba a la derecha (paso 16): quien eres, Ajustes (quien eres en detalle,
// la empresa, el aislamiento y, para quien administra, las personas), el idioma, el tema y
// Salir. Las iniciales en lugar de una foto (la app no carga imagenes de fuera) y del zorro
// del prototipo. Cada idioma se nombra en su propio idioma (lang=...), asi cualquiera
// encuentra el suyo aunque no entienda el que se ve.
import { ChevronDown, LogOut, Settings } from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { LANGS, fmt, isLang, useT, type Lang, type Messages } from '@/i18n';
import { initials } from '@/lib/format';
import { roleOf, useSession } from '@/lib/session';
import { THEME_CHOICES, isThemeChoice, useTheme } from '@/lib/theme';
import { useNav } from './navigation';

function languageName(t: Messages, code: Lang): string {
  return code === 'nl' ? t.language.nlLong : code === 'en' ? t.language.enLong : t.language.esLong;
}

export function AccountMenu() {
  const { t, lang, setLang } = useT();
  const { session, logout } = useSession();
  const { choice, setChoice } = useTheme();
  const nav = useNav();
  if (!session) return null;
  const name = session.me.nombre;
  const role = roleOf(session.me.permisos);
  const roleText = { admin: t.account.roleAdmin, staff: t.account.roleStaff, readOnly: t.account.roleReadOnly }[role];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type='button'
          aria-label={fmt(t.account.menu, { name })}
          className='flex items-center gap-2 rounded-full border border-transparent py-0.5 pl-0.5 pr-0.5 hover:bg-accent sm:pr-2'
        >
          <Avatar className='h-7 w-7'>
            <AvatarFallback className='bg-avatar text-[11px] font-semibold text-avatar-foreground'>{initials(name)}</AvatarFallback>
          </Avatar>
          <span className='hidden text-sm font-medium xl:inline' data-proper-name=''>
            {name}
          </span>
          <ChevronDown className='hidden h-3.5 w-3.5 text-muted-foreground sm:block' aria-hidden='true' />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-64'>
        <DropdownMenuLabel className='font-normal'>
          <span className='block text-xs text-muted-foreground'>{t.account.signedInAs}</span>
          <span className='block font-semibold' data-proper-name=''>
            {name}
          </span>
          <span className='block text-xs text-muted-foreground'>{roleText}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => nav.go('settings')}>
          <Settings className='mr-2 h-4 w-4' aria-hidden='true' />
          {t.nav.settings.label}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className='text-xs font-normal text-muted-foreground'>{t.language.label}</DropdownMenuLabel>
        <DropdownMenuRadioGroup aria-label={t.language.label} value={lang} onValueChange={(v) => isLang(v) && setLang(v)}>
          {LANGS.map((code) => (
            <DropdownMenuRadioItem key={code} value={code} lang={code}>
              {languageName(t, code)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className='text-xs font-normal text-muted-foreground'>{t.theme.label}</DropdownMenuLabel>
        <DropdownMenuRadioGroup aria-label={t.theme.label} value={choice} onValueChange={(v) => isThemeChoice(v) && setChoice(v)}>
          {THEME_CHOICES.map((code) => (
            <DropdownMenuRadioItem key={code} value={code}>
              {t.theme[code]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => logout('loggedOut')}>
          <LogOut className='mr-2 h-4 w-4' aria-hidden='true' />
          {t.account.logout}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
