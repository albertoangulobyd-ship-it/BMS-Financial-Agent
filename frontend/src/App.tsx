// La app: idioma, tema, sesion y Aurora (paso 17). Con o sin alguien dentro se ve lo mismo, el
// inicio de Aurora (aurora/root.tsx): sin sesion, el saludo pide el codigo personal (L0); al
// entrar, el saludo cambia y todo lo demas se queda donde estaba. El idioma y el tema de la
// entrada son los del ultimo uso en este ordenador; al entrar, los de la persona (si eligio
// unos), y lo que elija se guarda como suyo. Sin MotionConfig: el movimiento reducido es el de
// Aurora (su CSS y useReducedMotion donde Aurora lo pregunta, especificacion D-54).
import { useCallback, useEffect, useRef, useState } from 'react';
import { DEFAULT_LANG, I18nProvider, useT, type Lang } from '@/i18n';
import { Root } from '@/aurora/root';
import { RefreshProvider } from '@/lib/refresh';
import { SessionProvider, type Session } from '@/lib/session';
import {
  DEVICE_LANG_KEY,
  DEVICE_THEME_KEY,
  forgetSavedTabs,
  loadLang,
  loadTheme,
  personKey,
  saveLang,
  saveTheme,
} from '@/lib/storage';
import { DEFAULT_THEME, ThemeProvider, type ThemeChoice } from '@/lib/theme';

/** "Ir al contenido": solo aparece con el teclado. */
function SkipLink() {
  const { t } = useT();
  return (
    <a
      href='#contenido'
      className='skip-link'
      onClick={(e) => {
        e.preventDefault();
        // En una pantalla de trabajo, su cuerpo; en el inicio, la caja (o el codigo al entrar).
        (document.getElementById('contenido') ?? document.querySelector<HTMLElement>('.composer textarea, .composer input'))?.focus();
      }}
    >
      {t.shell.skipToContent}
    </a>
  );
}

export function App() {
  const [lang, setLangState] = useState<Lang>(() => loadLang(DEVICE_LANG_KEY) ?? DEFAULT_LANG);
  const [theme, setThemeState] = useState<ThemeChoice>(() => loadTheme(DEVICE_THEME_KEY) ?? DEFAULT_THEME);
  const person = useRef<Session | null>(null);
  const currentLang = useRef(lang);
  const currentTheme = useRef(theme);

  useEffect(() => {
    currentLang.current = lang;
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    currentTheme.current = theme;
  }, [theme]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    saveLang(DEVICE_LANG_KEY, next);
    const s = person.current;
    if (s) saveLang(personKey(s.environment, s.me.id, 'lang'), next);
  }, []);

  const setTheme = useCallback((next: ThemeChoice) => {
    setThemeState(next);
    saveTheme(DEVICE_THEME_KEY, next);
    const s = person.current;
    if (s) saveTheme(personKey(s.environment, s.me.id, 'theme'), next);
  }, []);

  const onLogin = useCallback((s: Session) => {
    person.current = s;
    forgetSavedTabs(s.environment, s.me.id);
    const langKey = personKey(s.environment, s.me.id, 'lang');
    const ownLang = loadLang(langKey);
    if (ownLang) setLangState(ownLang);
    else saveLang(langKey, currentLang.current);
    const themeKey = personKey(s.environment, s.me.id, 'theme');
    const ownTheme = loadTheme(themeKey);
    if (ownTheme) setThemeState(ownTheme);
    else saveTheme(themeKey, currentTheme.current);
  }, []);

  return (
    <ThemeProvider choice={theme} setChoice={setTheme}>
      <I18nProvider lang={lang} setLang={setLang}>
        <SessionProvider onLogin={onLogin}>
          <RefreshProvider>
            <SkipLink />
            <Root />
          </RefreshProvider>
        </SessionProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
