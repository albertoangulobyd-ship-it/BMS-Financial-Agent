// IBAN-controles / IBAN checks: "welke bankrekeningen moeten nog telefonisch worden
// gecontroleerd?". Cada cuenta nueva o cambiada (los avisos F de las facturas y las del
// registro sin verificar): de que proveedor es, donde aparecio, que se vio y el telefono
// del maestro al que se llama. Verificar es el flujo de siempre (verificar_iban): se
// llama a ESE numero, nunca a uno de la factura, y el IBAN que confirma el proveedor se
// TECLEA (el campo va vacio: nunca se rellena con el del documento). Rechazar dice que
// pasa con la factura. La regla de las dos personas la hace cumplir el servidor, y su
// mensaje se ensena tal cual en el dialogo. Abajo, las cuentas heredadas sin confirmar.
import { CircleCheck, Phone } from 'lucide-react';
import { ActionButton } from '@/components/action-dialog';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState, ErrorState, Loading } from '@/components/states';
import { StatusText } from '@/components/status-text';
import { ACCOUNT_TONE } from '@/components/tones';
import { Button } from '@/components/ui/button';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { fmt, useT } from '@/i18n';
import { findingDetail, ruleText, stateLabel, templateCatalog } from '@/i18n/domain';
import { formatWith } from '@/i18n/templates';
import { paths, type InvoiceRow } from '@/lib/api';
import type { AccountRow, ProviderAccounts, Reason } from '@/lib/api-types';
import { formatDate } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { recordRoute } from './registry';
import { useLoad } from './use-load';

/** Una cuenta por comprobar: un proveedor y un IBAN, con lo que se vio y donde. */
interface Check {
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

export function buildChecks(invoices: InvoiceRow[], accounts: AccountRow[]): Check[] {
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

interface Loaded {
  checks: Check[];
  inherited: AccountRow[];
  providers: Map<number, ProviderAccounts>;
}

export function IbanChecksScreen() {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad<Loaded>(async () => {
    const api = session!.api;
    const [invoices, accounts] = await Promise.all([
      api.get<{ facturas: InvoiceRow[] }>(paths.invoices).then((r) => r.facturas),
      api.get<{ cuentas: AccountRow[] }>(paths.accounts).then((r) => r.cuentas),
    ]);
    const checks = buildChecks(invoices, accounts);
    // El telefono de verificacion es el del maestro: sale de la vista de cada proveedor.
    const ids = [...new Set(checks.map((c) => c.providerId))];
    const providers = await Promise.all(
      ids.map((id) => api.get<{ proveedor: ProviderAccounts }>(paths.provider(id)).then((r) => r.proveedor))
    );
    return {
      checks,
      inherited: accounts.filter((a) => a.estado === 'heredada'),
      providers: new Map(providers.map((p) => [p.id, p])),
    };
  }, [session, version]);
  const nav = t.nav['iban-checks'];

  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'ready' && (
        <div className='flex flex-col gap-8'>
          <p className='max-w-3xl text-[13px] leading-relaxed text-[#45423c]'>{t.iban.rule}</p>
          {state.data.checks.length === 0 ? (
            <EmptyState icon={CircleCheck} title={t.iban.emptyTitle} text={t.iban.emptyText} />
          ) : (
            <ol className='flex flex-col gap-4'>
              {state.data.checks.map((c) => (
                <li key={`${c.providerId}:${c.iban}`}>
                  <CheckCard check={c} provider={state.data.providers.get(c.providerId) ?? null} onDone={retry} />
                </li>
              ))}
            </ol>
          )}
          {state.data.inherited.length > 0 && <Inherited accounts={state.data.inherited} onDone={retry} />}
        </div>
      )}
    </Screen>
  );
}

function CheckCard({ check: c, provider, onDone }: { check: Check; provider: ProviderAccounts | null; onDone: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const { openRoute } = useTabs();
  const shown = formatWith('iban', c.iban, templateCatalog(lang));
  const phone = provider?.telefono_verificacion ?? null;
  const invoice = c.findings[0]?.invoice ?? null;
  const seen = new Set<string>();
  const findings = c.findings.filter((f) => !seen.has(f.reason.regla) && seen.add(f.reason.regla));
  return (
    <article className='rounded-md border border-border bg-card px-5 py-4' aria-label={`${c.provider ?? ''} ${shown}`}>
      <header className='flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1'>
        <h2 className='text-[15px] font-semibold'>{provider?.nombre ?? c.provider ?? '—'}</h2>
        {c.account && (
          <StatusText tone={ACCOUNT_TONE[c.account.estado] ?? 'neutral'}>
            {stateLabel(lang, 'cuenta', c.account.estado) ?? c.account.estado}
          </StatusText>
        )}
      </header>
      <dl className='mt-3 grid grid-cols-1 gap-x-8 gap-y-2 text-[13px] md:grid-cols-[11rem_1fr]'>
        <dt className='text-muted-foreground'>{t.iban.found}</dt>
        <dd className='m-0'>
          <span className='font-mono text-[13px] tracking-[0.02em]'>{shown}</span>
          <span className='ml-2 text-xs text-muted-foreground'>{t.iban.notCorrectYet}</span>
        </dd>
        {invoice && (
          <>
            <dt className='text-muted-foreground'>{t.iban.where}</dt>
            <dd className='m-0'>
              <Button
                variant='link'
                size='sm'
                className='h-auto px-0 py-0 font-mono text-[12.5px]'
                onClick={() => openRoute(recordRoute('invoice', invoice.id, 'iban-checks'))}
              >
                {invoice.numero ?? `#${invoice.id}`}
              </Button>
              {invoice.fecha_factura && <span className='ml-2 text-muted-foreground'>{formatDate(invoice.fecha_factura)}</span>}
            </dd>
          </>
        )}
        <dt className='text-muted-foreground'>{t.iban.whatWasSeen}</dt>
        <dd className='m-0 flex flex-col gap-1'>
          {findings.length ? (
            findings.map(({ reason: r }) => (
              <span key={r.id}>
                <span className='font-medium'>{ruleText(lang, r.regla)?.title ?? r.regla}</span>{' '}
                <span className='font-mono text-[11px] text-muted-foreground'>{r.regla}</span>
                <span className='block text-[#45423c]'>{findingDetail(lang, r.regla, r.resultado, r.valores)}</span>
              </span>
            ))
          ) : (
            <span>{t.iban.registeredNotVerified}</span>
          )}
        </dd>
        <dt className='text-muted-foreground'>{t.iban.phoneOnFile}</dt>
        <dd className='m-0'>
          {phone ? (
            <span className='inline-flex items-center gap-1.5 font-medium'>
              <Phone className='h-3.5 w-3.5' aria-hidden='true' />
              {phone}
            </span>
          ) : (
            <span className='text-late-foreground'>{t.iban.noPhone}</span>
          )}
        </dd>
      </dl>
      {can('confirmar_iban') && (
        <div className='mt-4 flex flex-wrap gap-2'>
          {phone && (
            <ActionButton
              action='verificar_iban'
              label={t.iban.verify}
              variant='default'
              intro={
                <ol className='list-decimal space-y-1 pl-5'>
                  <li>{fmt(t.iban.step1, { phone })}</li>
                  <li>{t.iban.step2}</li>
                  <li>{t.iban.step3}</li>
                </ol>
              }
              fields={[
                { name: 'iban', label: t.iban.typedIban, kind: 'iban', required: true, help: t.iban.typedIbanHelp },
                { name: 'telefono', label: t.iban.phoneCalled, kind: 'tel', required: true, initial: phone, help: t.iban.phoneCalledHelp },
                { name: 'persona_contactada', label: t.iban.spokeTo, kind: 'text', required: true },
                { name: 'motivo', label: t.action.note, kind: 'textarea', required: true, help: t.iban.noteHelp },
              ]}
              preview={(v) => <TypedMatch typed={v.iban ?? ''} seen={c.iban} />}
              data={(v) => ({
                proveedor_id: c.providerId,
                iban: compactIban(v.iban ?? ''),
                telefono: v.telefono,
                persona_contactada: v.persona_contactada,
                factura_id: invoice?.id ?? null,
                metodo: 'llamada',
                motivo: v.motivo,
              })}
              onDone={onDone}
            />
          )}
          <ActionButton
            action='rechazar_iban'
            label={t.iban.reject}
            intro={fmt(t.iban.rejectIntro, { iban: shown })}
            fields={[
              ...(invoice
                ? [
                    {
                      name: 'decision_facturas',
                      label: fmt(t.iban.invoiceDecision, { number: invoice.numero ?? `#${invoice.id}` }),
                      kind: 'select' as const,
                      initial: '',
                      options: [
                        { value: '', label: t.iban.decideLater },
                        { value: 'pagar_a_verificada', label: stateLabel(lang, 'decision_facturas', 'pagar_a_verificada') ?? '' },
                        { value: 'anular', label: stateLabel(lang, 'decision_facturas', 'anular') ?? '' },
                      ],
                    },
                  ]
                : []),
              { name: 'motivo', label: t.action.reason, kind: 'textarea', required: true },
            ]}
            data={(v) => ({
              proveedor_id: c.providerId,
              iban: c.iban,
              factura_id: invoice?.id ?? null,
              decision_facturas: v.decision_facturas || null,
              motivo: v.motivo,
            })}
            onDone={onDone}
          />
        </div>
      )}
    </article>
  );
}

/** Lo tecleado contra lo visto: el IBAN se escribe tal como lo dice el proveedor. */
function TypedMatch({ typed, seen }: { typed: string; seen: string }) {
  const { t } = useT();
  const value = compactIban(typed);
  if (value.length < 8) return null;
  return value === seen ? (
    <p className='text-[13px]'>
      <StatusText tone='ok'>{t.iban.matches}</StatusText>
    </p>
  ) : (
    <p role='status' className='text-[13px]'>
      <StatusText tone='late'>{t.iban.differs}</StatusText>
    </p>
  );
}

function Inherited({ accounts, onDone }: { accounts: AccountRow[]; onDone: () => void }) {
  const { t } = useT();
  const can = useCan();
  return (
    <section aria-labelledby='inherited' className='rounded-md border border-border bg-card px-5 py-4'>
      <h2 id='inherited' className='text-[15px] font-semibold'>
        {t.iban.inheritedTitle}
      </h2>
      <p className='mt-1 max-w-3xl text-[13px] text-[#45423c]'>
        {fmt(accounts.length === 1 ? t.iban.inheritedTextOne : t.iban.inheritedText, { n: accounts.length })}
      </p>
      {can('confirmar_iban') && (
        <div className='mt-3'>
          <ActionButton
            action='atestar_iban'
            label={t.iban.confirmInherited}
            intro={t.iban.confirmInheritedIntro}
            fields={[{ name: 'motivo', label: t.action.reason, kind: 'textarea', required: true }]}
            data={(v) => ({ motivo: v.motivo })}
            onDone={onDone}
          />
        </div>
      )}
    </section>
  );
}
