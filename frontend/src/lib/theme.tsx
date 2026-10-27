// El tema de la app. El color lo decide SOLO la clase .dark en <html> (index.css define los
// dos juegos de variables, :root y :root.dark): el CSS construido no lleva ninguna consulta
// prefers-color-scheme, asi el modo oscuro de Windows no cambia nada que la persona no haya
// pedido. Con "seguir a Windows" es este modulo quien mira matchMedia y pone o quita la
// clase. index.html ya trae class="dark" (el tema por defecto), para que la primera
// pintura no salga blanca.
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { resolveTheme, type ResolvedTheme, type ThemeChoice } from './theme-choice';

export { DEFAULT_THEME, THEME_CHOICES, isThemeChoice, resolveTheme } from './theme-choice';
export type { ResolvedTheme, ThemeChoice } from './theme-choice';

const SYSTEM_DARK = '(prefers-color-scheme: dark)';

function systemPrefersDark(): boolean {
  try {
    return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(SYSTEM_DARK).matches
      : false;
  } catch {
    return false;
  }
}

/** Pone el tema en <html>: la clase .dark y color-scheme (barras de desplazamiento y
 *  controles del navegador en el mismo tema). */
export function applyTheme(theme: ResolvedTheme, root: HTMLElement = document.documentElement): void {
  root.classList.toggle('dark', theme === 'dark');
  root.dataset.theme = theme;
}

/** Al arrancar, antes de pintar: el tema guardado en este ordenador (o el de por defecto). */
export function applyInitialTheme(choice: ThemeChoice): void {
  applyTheme(resolveTheme(choice, systemPrefersDark()));
}

interface ThemeValue {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setChoice: (choice: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({
  choice,
  setChoice,
  children,
}: {
  choice: ThemeChoice;
  setChoice: (choice: ThemeChoice) => void;
  children: ReactNode;
}) {
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  // Solo con "seguir a Windows" importa lo que diga el sistema, y mientras este elegido.
  useEffect(() => {
    if (choice !== 'system' || typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia(SYSTEM_DARK);
    const change = () => setSystemDark(media.matches);
    change();
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, [choice]);

  const resolved = resolveTheme(choice, systemDark);
  useEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  const value = useMemo(() => ({ choice, resolved, setChoice }), [choice, resolved, setChoice]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/** El tema elegido, el que se pinta y como cambiarlo: `const { choice, resolved } = useTheme()`. */
export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme must be used within ThemeProvider');
  return value;
}
