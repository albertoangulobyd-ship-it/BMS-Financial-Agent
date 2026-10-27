// Las cuentas de la navegacion que piden hacer algo: facturas bloqueadas (Werklijst),
// excepciones abiertas, cuentas por verificar (IBAN-controles) y, desde el paso 16, los pagos
// que el banco propuso y esperan a una persona (el banco de cobrar y el de pagar). Salen del
// panel y de las propuestas; si no se pueden leer, no hay insignias (no se inventa un cero).
// Las ensenan las vistas de cada seccion (shell/section-nav.tsx) y el inicio.
import { useCallback, useEffect, useState } from 'react';
import { paths, type Panel } from '@/lib/api';
import type { PaymentProposal } from '@/lib/api-types';
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

/** Los pagos propuestos que esperan, por lado: los cobros en el banco de cobrar y los pagos
 *  en el de pagar. */
export function countsFromProposals(proposals: readonly PaymentProposal[]): BadgeCounts {
  return {
    'bank-in': proposals.filter((p) => p.factura.sentido === 'saliente').length,
    'bank-out': proposals.filter((p) => p.factura.sentido === 'entrante').length,
  };
}

export function useBadgeCounts(session: Session | null, version = 0): [BadgeCounts, () => void] {
  const [counts, setCounts] = useState<BadgeCounts>({});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!session) return;
    let alive = true;
    // Cada lectura da sus insignias; la que falla no pone ninguna (ni un cero inventado).
    void Promise.allSettled([
      session.api.get<{ panel: Panel }>(paths.panel),
      session.api.get<{ propuestas: PaymentProposal[] }>(paths.proposals),
    ]).then(([panel, proposals]) => {
      if (!alive) return;
      setCounts({
        ...(panel.status === 'fulfilled' ? countsFromPanel(panel.value.panel) : {}),
        ...(proposals.status === 'fulfilled' ? countsFromProposals(proposals.value.propuestas) : {}),
      });
    });
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
