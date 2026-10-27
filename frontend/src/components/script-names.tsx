// Los nombres de un acceso directo y de los .bat de la instalacion (windows/comun.ps1, windows/
// y docker/): en el disco se llaman asi, en castellano, sea cual sea el idioma de la app. Los
// tres idiomas los nombran (revision del paso 16: solo el castellano lo hacia, y quien mas los
// necesita es la oficina en neerlandes), como nombres propios: no cuentan como restos de otro
// idioma y no se traducen.
import { Fragment } from 'react';

export const SCRIPT_NAMES = {
  readShortcut: 'BMS Finanzas - Leer facturas',
  company: 'empresa.bat',
  check: 'comprobar.bat',
  people: 'persona.bat',
  backup: 'copia.bat',
  readScript: 'leer-facturas.bat',
} as const;

export type ScriptName = keyof typeof SCRIPT_NAMES;

function isScriptName(key: string): key is ScriptName {
  return Object.prototype.hasOwnProperty.call(SCRIPT_NAMES, key);
}

/** Un texto de la app con {company}, {readShortcut}...: cada hueco, el nombre de verdad. */
export function WithScriptNames({ text }: { text: string }) {
  const parts = text.split(/\{([a-zA-Z]+)\}/);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 && isScriptName(part) ? (
          <span key={i} data-proper-name='' className='font-mono text-[0.95em]'>
            {SCRIPT_NAMES[part]}
          </span>
        ) : (
          <Fragment key={i}>{i % 2 === 1 ? `{${part}}` : part}</Fragment>
        )
      )}
    </>
  );
}
