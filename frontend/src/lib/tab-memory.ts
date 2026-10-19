// Lo que una pestana recuerda mientras la app esta abierta (el filtro y la busqueda de una
// lista): al volver de una ficha, la lista sigue como estaba. Solo en memoria: no va a
// localStorage (podria llevar texto buscado de un documento) y se pierde al salir.
import { useCallback, useState } from 'react';

const memory = new Map<string, unknown>();

/** Olvida todo (al salir, para que otra persona no vea la busqueda de la anterior). */
export function forgetTabMemory(): void {
  memory.clear();
}

export function useTabState<T>(tabId: string, key: string, initial: T): [T, (value: T) => void] {
  const slot = `${tabId}:${key}`;
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
