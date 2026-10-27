// Las cuentas de la navegacion que piden hacer algo: facturas bloqueadas (Werklijst),
// excepciones abiertas y cuentas por verificar (IBAN-controles). Salen del panel; si no se
// pueden leer, no hay insignias (no se inventa un cero). Las ensenan las vistas de cada
// seccion (shell/section-nav.tsx) y el inicio.
import { useCallback, useEffect, useState } from 'react';
import { paths, type Panel } from '@/lib/api';
import type { Session } from '@/lib/session';
import type { ViewId } from '@/screens/registry';

export type BadgeCounts = Partial<Record<ViewId, number>>;

export interface NavBadge {
  count: number;
  /** El texto detras de la cuenta ("geblokkeerd"); tambien lo leen los lectores de pantalla. */
  label?: string;
  tone: 'blocked' | 'neutral';
}

export function countsFromPanel(panel: Panel): BadgeCounts {
  const iban = panel.atencion.categorias.find((c) => c.clave === 'iban');
  return {
    'work-queue': panel.atencion.bloqueadas,
    exceptions: panel.atencion.excepciones.abiertas,
    'iban-checks': iban?.activos ?? 0,
  };
}

export function useBadgeCounts(session: Session | null, version = 0): [BadgeCounts, () => void] {
  const [counts, setCounts] = useState<BadgeCounts>({});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!session) return;
    let alive = true;
    session.api.get<{ panel: Panel }>(paths.panel).then(
      (r) => alive && setCounts(countsFromPanel(r.panel)),
      () => alive && setCounts({})
    );
    return () => {
      alive = false;
    };
  }, [session, attempt, version]);
  const refresh = useCallback(() => setAttempt((n) => n + 1), []);
  return [counts, refresh];
}

export function badgeFor(id: ViewId, counts: BadgeCounts, labels: { blocked: string }): NavBadge | undefined {
  const count = counts[id];
  if (!count) return undefined;
  if (id === 'work-queue') return { count, label: labels.blocked, tone: 'blocked' };
  return { count, tone: 'neutral' };
}
