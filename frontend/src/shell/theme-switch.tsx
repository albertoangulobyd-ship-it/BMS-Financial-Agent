// Oscuro | Claro | Seguir a Windows (paso 16). El oscuro de Aurora es el de por defecto; la
// eleccion se guarda por persona, como el idioma (App.tsx y lib/storage.ts).
import { Monitor, Moon, Sun } from 'lucide-react';
import { useT } from '@/i18n';
import { THEME_CHOICES, useTheme, type ThemeChoice } from '@/lib/theme';
import { cn } from '@/lib/utils';

const ICONS: Record<ThemeChoice, typeof Moon> = { dark: Moon, light: Sun, system: Monitor };

export function ThemeSwitch() {
  const { t } = useT();
  const { choice, setChoice } = useTheme();
  return (
    <div role='group' aria-label={t.theme.label} className='flex flex-wrap overflow-hidden rounded-md border border-input'>
      {THEME_CHOICES.map((code, index) => {
        const Icon = ICONS[code];
        return (
          <button
            key={code}
            type='button'
            aria-pressed={choice === code}
            onClick={() => setChoice(code)}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium',
              index > 0 && 'border-l border-input',
              choice === code ? 'bg-primary text-primary-foreground' : 'bg-card text-soft-foreground hover:bg-accent'
            )}
          >
            <Icon className='h-3.5 w-3.5' aria-hidden='true' />
            {t.theme[code]}
          </button>
        );
      })}
    </div>
  );
}
