// La infraestructura de idiomas: neerlandes (por defecto) e ingles, nada mas. El
// idioma lo elige cada persona en la cabecera y se guarda en sus preferencias
// (lib/storage.ts); aqui solo vive el estado y el acceso a los textos.
import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { nl } from './nl';
import { en } from './en';

export type Messages = typeof nl;
export type Lang = 'nl' | 'en';
export const LANGS: readonly Lang[] = ['nl', 'en'];
export const DEFAULT_LANG: Lang = 'nl';

export const MESSAGES: Record<Lang, Messages> = { nl, en };

export function isLang(value: unknown): value is Lang {
  return value === 'nl' || value === 'en';
}

/** Rellena los huecos {nombre} de un texto. Un hueco sin valor se queda como esta (se ve). */
export function fmt(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (hueco, nombre: string) =>
    Object.prototype.hasOwnProperty.call(values, nombre) ? String(values[nombre]) : hueco
  );
}

interface I18nValue {
  lang: Lang;
  t: Messages;
  setLang: (lang: Lang) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({
  lang,
  setLang,
  children,
}: {
  lang: Lang;
  setLang: (lang: Lang) => void;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ lang, t: MESSAGES[lang], setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/** Los textos del idioma actual: `const { t, lang } = useT()`. */
export function useT(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error('useT must be used within I18nProvider');
  return value;
}
