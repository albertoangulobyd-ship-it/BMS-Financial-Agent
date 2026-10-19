// NL | EN: los dos unicos idiomas de la app. La eleccion se guarda por persona.
import { LANGS, useT } from '@/i18n';
import { cn } from '@/lib/utils';

export function LanguageSwitch() {
  const { t, lang, setLang } = useT();
  return (
    <div role='group' aria-label={t.language.label} className='flex overflow-hidden rounded-md border border-input'>
      {LANGS.map((code, index) => (
        <button
          key={code}
          type='button'
          lang={code}
          aria-pressed={lang === code}
          aria-label={code === 'nl' ? t.language.nlLong : t.language.enLong}
          onClick={() => setLang(code)}
          className={cn(
            'min-w-9 px-2.5 py-1 text-xs font-semibold tracking-[0.04em]',
            index > 0 && 'border-l border-input',
            lang === code ? 'bg-primary text-primary-foreground' : 'bg-card text-[#45423c] hover:bg-accent'
          )}
        >
          {code === 'nl' ? t.language.nl : t.language.en}
        </button>
      ))}
    </div>
  );
}
