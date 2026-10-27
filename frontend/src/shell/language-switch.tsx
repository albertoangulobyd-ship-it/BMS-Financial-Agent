// NL | EN | ES: los tres idiomas de la app (el castellano, desde el paso 16). La eleccion se
// guarda por persona. Cada boton lleva el nombre del idioma en ese idioma (lang=...), asi
// cualquiera encuentra el suyo aunque no entienda el que se ve.
import { LANGS, useT, type Lang, type Messages } from '@/i18n';
import { cn } from '@/lib/utils';

function names(t: Messages, code: Lang): { short: string; long: string } {
  const l = t.language;
  if (code === 'nl') return { short: l.nl, long: l.nlLong };
  if (code === 'en') return { short: l.en, long: l.enLong };
  return { short: l.es, long: l.esLong };
}

export function LanguageSwitch() {
  const { t, lang, setLang } = useT();
  return (
    <div role='group' aria-label={t.language.label} className='flex overflow-hidden rounded-md border border-input'>
      {LANGS.map((code, index) => {
        const name = names(t, code);
        return (
          <button
            key={code}
            type='button'
            lang={code}
            aria-pressed={lang === code}
            aria-label={name.long}
            onClick={() => setLang(code)}
            className={cn(
              'min-w-9 px-2.5 py-1 text-xs font-semibold tracking-[0.04em]',
              index > 0 && 'border-l border-input',
              lang === code ? 'bg-primary text-primary-foreground' : 'bg-card text-soft-foreground hover:bg-accent'
            )}
          >
            {name.short}
          </button>
        );
      })}
    </div>
  );
}
