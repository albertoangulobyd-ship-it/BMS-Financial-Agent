// La busqueda de la caja del inicio y de Ctrl+K (lib/quick-search.ts) como estado de React: las
// listas de clientes, proveedores, Objects y PO se leen una vez (y otra vez despues de una
// orden), las facturas se piden al motor con cada busqueda. Lo que llega tarde de una busqueda
// anterior se descarta.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useT } from '@/i18n';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import {
  invoiceResults,
  loadSources,
  recordResults,
  screenResults,
  type QuickResult,
  type QuickSources,
} from '@/lib/quick-search';

export interface QuickSearch {
  results: QuickResult[];
  /** Buscando facturas en el motor (o leyendo las listas). */
  loading: boolean;
  /** Facturas encontradas que no caben en la lista. */
  moreInvoices: number;
  /** La busqueda de facturas fallo (las demas siguen). */
  error: unknown;
}

/**
 * `query` es lo que se busca (vacio: nada). Con `delay` (Ctrl+K, mientras se escribe) las
 * facturas se piden cuando se deja de escribir; sin el (la caja del inicio, al enviar), ya.
 */
export function useQuickSearch(query: string, delay = 0): QuickSearch {
  const { t } = useT();
  const { session } = useSession();
  const can = useCan();
  const { version } = useRefresh();
  const [sources, setSources] = useState<QuickSources | null>(null);
  const [invoices, setInvoices] = useState<{ q: string; results: QuickResult[]; total: number } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const seq = useRef(0);
  const q = query.trim();

  useEffect(() => {
    if (!session || !q) return;
    let alive = true;
    loadSources(session.api).then(
      (s) => alive && setSources(s),
      () => alive && setSources({ clients: [], providers: [], objects: [], pos: [] })
    );
    return () => {
      alive = false;
    };
    // Las listas, una vez por busqueda que empieza y tras cada orden (no con cada letra).
  }, [session, version, q === '']);

  useEffect(() => {
    if (!session || !q) {
      setInvoices(null);
      setError(null);
      return;
    }
    const mine = ++seq.current;
    const timer = window.setTimeout(() => {
      invoiceResults(session.api, q, t).then(
        (r) => {
          if (seq.current !== mine) return;
          setInvoices({ q, ...r });
          setError(null);
        },
        (e: unknown) => {
          if (seq.current !== mine) return;
          setInvoices({ q, results: [], total: 0 });
          setError(e);
        }
      );
    }, delay);
    return () => window.clearTimeout(timer);
  }, [session, q, delay, t, version]);

  return useMemo<QuickSearch>(() => {
    if (!q) return { results: [], loading: false, moreInvoices: 0, error: null };
    const screens = screenResults(q, t, can);
    const records = sources ? recordResults(q, sources, t) : [];
    const current = invoices && invoices.q === q ? invoices : null;
    const found = current?.results ?? [];
    return {
      results: [...screens, ...records, ...found],
      loading: sources === null || current === null,
      moreInvoices: current ? Math.max(0, current.total - found.length) : 0,
      error,
    };
  }, [q, t, can, sources, invoices, error]);
}
