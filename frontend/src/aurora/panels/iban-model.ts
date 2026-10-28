// Las cuentas por comprobar por telefono (paso 15, IBAN-controles; desde el paso 17, el grupo
// "IBAN por verificar" del panel Inicio), sin React: cada cuenta nueva o cambiada (los avisos F
// de las facturas y las del registro sin verificar) con su proveedor, lo que se vio y donde, y lo
// que falta de ella en una frase. Lo prueba iban-model.test.ts.
import type { InvoiceRow } from '@/lib/api';
import type { AccountRow, Reason } from '@/lib/api-types';

/** Una cuenta por comprobar: un proveedor y un IBAN, con lo que se vio y donde. */
export interface Check {
  providerId: number;
  provider: string | null;
  iban: string;
  account: AccountRow | null;
  findings: { reason: Reason; invoice: InvoiceRow }[];
}

/** El IBAN sin espacios y en mayusculas, para comparar lo tecleado con lo visto. */
export function compactIban(text: string): string {
  return text.replace(/\s+/g, '').toUpperCase();
}

const REVISAR_EN_LA_CUENTA = new Set(['registrada']);
// Las que ya se comprobaron por telefono (o se confirmaron): no se vuelven a verificar.
const YA_COMPROBADA = new Set(['verificada', 'atestada']);

/**
 * Lo que falta de una cuenta, en una frase: confirmarla por telefono (nueva, sin registrar o sin
 * verificar), ponerla en Exact (verificada, pero el aviso F2 dice que no esta en los ultimos
 * maestros), mirar lo que queda abierto (verificada, con otro aviso) o nada mas (rechazada). Asi
 * una tarjeta nunca dice a la vez "verificada" y "aun sin confirmar".
 */
export type AccountStep = 'confirm' | 'exact' | 'open' | 'rejected';

export function accountStep(check: Pick<Check, 'account' | 'findings'>): AccountStep {
  const estado = check.account?.estado;
  if (estado === 'rechazada') return 'rejected';
  if (estado && YA_COMPROBADA.has(estado)) {
    return check.findings.some((f) => f.reason.regla === 'F2') ? 'exact' : 'open';
  }
  return 'confirm';
}

export function buildChecks(invoices: readonly InvoiceRow[], accounts: readonly AccountRow[]): Check[] {
  const checks = new Map<string, Check>();
  const key = (p: number, iban: string) => `${p}:${compactIban(iban)}`;
  for (const f of invoices) {
    if (f.proveedor_id === null || f.sentido !== 'entrante') continue;
    for (const r of f.razones ?? []) {
      if (!/^F\d+$/.test(r.regla) || r.estado === 'aceptado') continue;
      const iban = (r.valores as Record<string, unknown> | null)?.iban;
      if (typeof iban !== 'string' || !iban) continue;
      const k = key(f.proveedor_id, iban);
      const check = checks.get(k) ?? {
        providerId: f.proveedor_id,
        provider: f.contraparte,
        iban: compactIban(iban),
        account: null,
        findings: [],
      };
      check.findings.push({ reason: r, invoice: f });
      checks.set(k, check);
    }
  }
  for (const a of accounts) {
    const k = key(a.proveedor_id, a.iban);
    const existing = checks.get(k);
    if (existing) existing.account = a;
    else if (REVISAR_EN_LA_CUENTA.has(a.estado)) {
      checks.set(k, { providerId: a.proveedor_id, provider: a.proveedor, iban: compactIban(a.iban), account: a, findings: [] });
    }
  }
  return [...checks.values()];
}

/** La clave de una cuenta por comprobar (la tarjeta abierta). */
export function checkKey(c: Pick<Check, 'providerId' | 'iban'>): string {
  return `${c.providerId}:${c.iban}`;
}
