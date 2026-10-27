// La app: idioma, tema, sesion y, segun haya o no alguien dentro, la entrada o el marco con
// las pestanas. El idioma y el tema de la entrada son los del ultimo uso en este ordenador;
// al entrar, los de la persona (si eligio unos), y lo que elija se guarda como suyo.
import { useCallback, useEffect, useRef, useState } from 'react';
import { MotionConfig } from 'framer-motion';
import { DEFAULT_LANG, I18nProvider, type Lang } from '@/i18n';
import { SessionProvider, useSession, type Session } from '@/lib/session';
import {
  DEVICE_LANG_KEY,
  DEVICE_THEME_KEY,
  loadLang,
  loadTheme,
  personKey,
  saveLang,
  saveTheme,
} from '@/lib/storage';
import { DEFAULT_THEME, ThemeProvider, type ThemeChoice } from '@/lib/theme';
import { LoginScreen } from '@/screens/login';
import { AppShell } from '@/shell/app-shell';

function Gate() {
  const { session } = useSession();
  return session ? <AppShell /> : <LoginScreen />;
}

export function App({ nonce }: { nonce?: string }) {
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
    // reducedMotion="user": con "reducir movimiento" en Windows, framer-motion no anima
    // posiciones ni tamanos. El nonce es el de la pagina (lo pone el servidor en la CSP).
    <MotionConfig reducedMotion='user' nonce={nonce}>
      <ThemeProvider choice={theme} setChoice={setTheme}>
        <I18nProvider lang={lang} setLang={setLang}>
          <SessionProvider onLogin={onLogin}>
            <Gate />
          </SessionProvider>
        </I18nProvider>
      </ThemeProvider>
    </MotionConfig>
  );
}
