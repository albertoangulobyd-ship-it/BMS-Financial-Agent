// Las cuentas de la navegacion que piden hacer algo: facturas bloqueadas, excepciones
// abiertas y cuentas por verificar. Salen del panel; si no se pueden leer, no hay
// insignias (no se inventa un cero).
import { useCallback, useEffect, useState } from 'react';
import type { NavBadge } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { paths, type Panel } from '@/lib/api';
import type { Session } from '@/lib/session';
import type { NavId } from '@/screens/registry';

export type BadgeCounts = Partial<Record<NavId, number>>;

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

export function badgeFor(id: NavId, counts: BadgeCounts, labels: { blocked: string }): NavBadge | undefined {
  const count = counts[id];
  if (!count) return undefined;
  if (id === 'work-queue') return { count, label: labels.blocked, tone: 'blocked' };
  return { count, tone: 'neutral' };
}
