// Lo que una vista recuerda mientras la app esta abierta (el filtro y la busqueda de una
// lista, el periodo de un Object): al volver de una ficha, o al volver a la entrada mas
// tarde, la lista sigue como estaba. Va por la clave de la ruta (screens/registry.ts,
// routeKey). Solo en memoria: no va a localStorage (podria llevar texto buscado de un
// documento) y se pierde al salir.
import { useCallback, useState } from 'react';

const memory = new Map<string, unknown>();

/** Olvida todo (al salir, para que otra persona no vea la busqueda de la anterior). */
export function forgetViewMemory(): void {
  memory.clear();
}

/** Deja algo recordado para una vista antes de abrirla (la tarjeta "Vencido" del inicio abre
 *  la lista ya con el filtro de vencidas). */
export function rememberView(scope: string, key: string, value: unknown): void {
  memory.set(`${scope}:${key}`, value);
}

export function useViewState<T>(scope: string, key: string, initial: T): [T, (value: T) => void] {
  const slot = `${scope}:${key}`;
  const [value, setValue] = useState<T>(() => (memory.has(slot) ? (memory.get(slot) as T) : initial));
  const set = useCallback(
    (next: T) => {
      memory.set(slot, next);
      setValue(next);
    },
    [slot]
  );
  return [value, set];
}
