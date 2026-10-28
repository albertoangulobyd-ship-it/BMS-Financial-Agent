// Lo que lee el archivo de Documentos ademas de las listas: los documentos de cada carpeta y la
// ultima lectura de facturas.
// - Los documentos de una carpeta se leen por partes: al abrirla, al abrirla en el arbol o al
//   pasar por encima de ella (paso 16). Lo leido se guarda en memoria para la sesion (no en el
//   navegador) y se vuelve a leer cuando cambia la version (despues de una orden).
// - La ultima lectura (GET /api/v2/lectura) dice que facturas entraron nuevas y cuales estaban
//   repetidas: las marcas verde y naranja (analysis.ts).
import { useCallback, useEffect, useRef, useState } from 'react';
import { paths } from '@/lib/api';
import type { PartyDocuments } from '@/lib/api-types';
import { useRefresh } from '@/lib/refresh';
import { useSession, type Session } from '@/lib/session';
import { NO_ANALYSIS, analysisOf, type Analysis } from './analysis';
import { folderKey, type DocsEntry, type Side } from './documents-model';

interface CacheEntry {
  version: number;
  promise: Promise<PartyDocuments>;
  data?: PartyDocuments;
}

const docsCache = new WeakMap<Session, Map<string, CacheEntry>>();

function cacheOf(session: Session): Map<string, CacheEntry> {
  let byKey = docsCache.get(session);
  if (!byKey) {
    byKey = new Map();
    docsCache.set(session, byKey);
  }
  return byKey;
}

function fetchDocs(session: Session, version: number, side: Side, id: number): CacheEntry {
  const byKey = cacheOf(session);
  const key = folderKey(side, id);
  const hit = byKey.get(key);
  if (hit && hit.version === version) return hit;
  const promise = session.api
    .get<{ documentos: PartyDocuments }>(side === 'client' ? paths.clientDocuments(id) : paths.providerDocuments(id))
    .then((r) => r.documentos);
  // Lo de antes se queda a la vista mientras llega lo nuevo.
  const entry: CacheEntry = { version, promise, data: hit?.data };
  promise.then(
    (data) => {
      entry.data = data;
    },
    () => {
      if (byKey.get(key) === entry) byKey.delete(key);
    }
  );
  byKey.set(key, entry);
  return entry;
}

/** Los documentos de las carpetas leidas y como pedir los de otra. */
export function useFolderDocs(): [ReadonlyMap<string, DocsEntry>, (side: Side, id: number, again?: boolean) => void] {
  const { session } = useSession();
  const { version } = useRefresh();
  const [store, setStore] = useState<ReadonlyMap<string, DocsEntry>>(() => {
    const seed = new Map<string, DocsEntry>();
    if (session) for (const [key, entry] of cacheOf(session)) if (entry.data) seed.set(key, { status: 'ready', docs: entry.data.documentos });
    return seed;
  });
  const asked = useRef(new Map<string, number>());
  const put = (key: string, value: DocsEntry) =>
    setStore((prev) => {
      const next = new Map(prev);
      next.set(key, value);
      return next;
    });
  const ensure = useCallback(
    (side: Side, id: number, again = false) => {
      if (!session) return;
      const key = folderKey(side, id);
      if (!again && asked.current.get(key) === version) return;
      asked.current.set(key, version);
      const entry = fetchDocs(session, version, side, id);
      if (entry.data) put(key, { status: 'ready', docs: entry.data.documentos });
      else setStore((prev) => (prev.get(key)?.status === 'ready' ? prev : new Map(prev).set(key, { status: 'loading' })));
      entry.promise.then(
        (data) => put(key, { status: 'ready', docs: data.documentos }),
        (error: unknown) => {
          asked.current.delete(key);
          put(key, { status: 'error', error });
        }
      );
    },
    [session, version]
  );
  return [store, ensure];
}

/** Las marcas de la ultima lectura (nueva, repetida); sin ella, ninguna. */
export function useLastReading(): Analysis {
  const { session } = useSession();
  const { version } = useRefresh();
  const [analysis, setAnalysis] = useState<Analysis>(NO_ANALYSIS);
  useEffect(() => {
    if (!session) return;
    let alive = true;
    session.api.get<{ lectura: unknown }>(paths.reading).then(
      (r) => alive && setAnalysis(analysisOf(r.lectura)),
      () => alive && setAnalysis(NO_ANALYSIS)
    );
    return () => {
      alive = false;
    };
  }, [session, version]);
  return analysis;
}
