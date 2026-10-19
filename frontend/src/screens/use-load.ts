// Leer algo de la API para una pantalla: cargando, error (con reintento) o los datos. Lo
// que llega despues de cambiar de pantalla se descarta. Al volver a leer (tras una orden,
// o con "Opnieuw proberen") lo que ya se veia se queda hasta que llega lo nuevo: la
// pantalla no salta a "Laden…" ni pierde por donde iba la persona.
import { useCallback, useEffect, useRef, useState } from 'react';

export type LoadState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'ready'; data: T };

export function useLoad<T>(load: () => Promise<T>, deps: readonly unknown[]): [LoadState<T>, () => void] {
  const [state, setState] = useState<LoadState<T>>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const hasData = useRef(false);
  useEffect(() => {
    let alive = true;
    if (!hasData.current) setState({ status: 'loading' });
    load().then(
      (data) => {
        if (!alive) return;
        hasData.current = true;
        setState({ status: 'ready', data });
      },
      (error: unknown) => {
        if (!alive) return;
        hasData.current = false;
        setState({ status: 'error', error });
      }
    );
    return () => {
      alive = false;
    };
  }, [...deps, attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return [state, retry];
}
