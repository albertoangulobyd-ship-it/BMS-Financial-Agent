// El nombre de un fichero o de un acceso directo del escritorio (copia.bat, "BMS Finanzas -
// Leer facturas"): se escribe tal cual se llama, aunque no sea neerlandes ni ingles, y va
// marcado como nombre propio (data-proper-name) para que se vea que es algo que buscar en
// el ordenador y no una frase.
import type { ReactNode } from 'react';

export function ProperName({ children }: { children: ReactNode }) {
  return (
    <code data-proper-name='' className='rounded-sm bg-muted px-1 py-px font-mono text-[12.5px] text-foreground'>
      {children}
    </code>
  );
}

/** Un texto con un hueco {nombre} que es un elemento (no una cadena): lo parte y lo pone. */
export function withNode(template: string, hole: string, node: ReactNode): ReactNode {
  const marker = `{${hole}}`;
  const at = template.indexOf(marker);
  if (at < 0) return template;
  return (
    <>
      {template.slice(0, at)}
      {node}
      {template.slice(at + marker.length)}
    </>
  );
}
