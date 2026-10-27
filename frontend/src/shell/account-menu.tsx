// La persona que ha entrado: sus iniciales (sin foto: la app no carga imagenes de fuera)
// y un menu con quien es, el tema (oscuro, claro o seguir a Windows) y "Uitloggen".
import { ChevronDown, LogOut } from 'lucide-react';
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
import { fmt, useT } from '@/i18n';
import { initials } from '@/lib/format';
import { roleOf, useSession } from '@/lib/session';
import { THEME_CHOICES, isThemeChoice, useTheme } from '@/lib/theme';

export function AccountMenu() {
  const { t } = useT();
  const { session, logout } = useSession();
  const { choice, setChoice } = useTheme();
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
          className='flex items-center gap-2 rounded-md border border-transparent py-0.5 pl-0.5 pr-2 hover:bg-sidebar-accent'
        >
          <Avatar className='h-7 w-7'>
            <AvatarFallback className='bg-avatar text-[11px] font-semibold text-avatar-foreground'>
              {initials(name)}
            </AvatarFallback>
          </Avatar>
          <span className='hidden text-sm font-medium lg:inline'>{name}</span>
          <ChevronDown className='h-3.5 w-3.5 text-muted-foreground' aria-hidden='true' />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-60'>
        <DropdownMenuLabel className='font-normal'>
          <span className='block text-xs text-muted-foreground'>{t.account.signedInAs}</span>
          <span className='block font-semibold'>{name}</span>
          <span className='block text-xs text-muted-foreground'>{roleText}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className='text-xs font-normal text-muted-foreground'>{t.theme.label}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={choice} onValueChange={(v) => isThemeChoice(v) && setChoice(v)}>
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
