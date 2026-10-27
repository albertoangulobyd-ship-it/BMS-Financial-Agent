// Los temas de la app (paso 16): el oscuro de Aurora por defecto, el claro y "seguir a
// Windows". Solo los valores y como se resuelven; sin React, para que storage.ts y las
// pruebas lo usen sin cargar nada mas.

export type ThemeChoice = 'dark' | 'light' | 'system';
export type ResolvedTheme = 'dark' | 'light';

export const THEME_CHOICES: readonly ThemeChoice[] = ['dark', 'light', 'system'];
export const DEFAULT_THEME: ThemeChoice = 'dark';

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === 'dark' || value === 'light' || value === 'system';
}

/** El tema que se pinta: el elegido o, con "seguir a Windows", el del sistema. */
export function resolveTheme(choice: ThemeChoice, systemDark: boolean): ResolvedTheme {
  if (choice === 'system') return systemDark ? 'dark' : 'light';
  return choice;
}
