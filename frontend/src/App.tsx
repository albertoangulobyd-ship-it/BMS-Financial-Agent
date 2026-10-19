// La app: idioma, sesion y, segun haya o no alguien dentro, la entrada o el marco con las
// pestanas. El idioma de la entrada es el del ultimo uso en este ordenador; al entrar,
// el de la persona (si eligio uno), y lo que elija se guarda como suyo.
import { useCallback, useEffect, useRef, useState } from 'react';
import { MotionConfig } from 'framer-motion';
import { DEFAULT_LANG, I18nProvider, type Lang } from '@/i18n';
import { SessionProvider, useSession, type Session } from '@/lib/session';
import { DEVICE_LANG_KEY, loadLang, personKey, saveLang } from '@/lib/storage';
import { LoginScreen } from '@/screens/login';
import { AppShell } from '@/shell/app-shell';

function Gate() {
  const { session } = useSession();
  return session ? <AppShell /> : <LoginScreen />;
}

export function App({ nonce }: { nonce?: string }) {
  const [lang, setLangState] = useState<Lang>(() => loadLang(DEVICE_LANG_KEY) ?? DEFAULT_LANG);
  const person = useRef<Session | null>(null);
  const current = useRef(lang);

  useEffect(() => {
    current.current = lang;
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    saveLang(DEVICE_LANG_KEY, next);
    const s = person.current;
    if (s) saveLang(personKey(s.environment, s.me.id, 'lang'), next);
  }, []);

  const onLogin = useCallback((s: Session) => {
    person.current = s;
    const key = personKey(s.environment, s.me.id, 'lang');
    const own = loadLang(key);
    if (own) setLangState(own);
    else saveLang(key, current.current);
  }, []);

  return (
    // reducedMotion="user": con "reducir movimiento" en Windows, framer-motion no anima
    // posiciones ni tamanos. El nonce es el de la pagina (lo pone el servidor en la CSP).
    <MotionConfig reducedMotion='user' nonce={nonce}>
      <I18nProvider lang={lang} setLang={setLang}>
        <SessionProvider onLogin={onLogin}>
          <Gate />
        </SessionProvider>
      </I18nProvider>
    </MotionConfig>
  );
}
