// BASE del paso 15: la ficha de una factura en su forma minima (que es y de quien), para
// probar que una fila abre su ficha en una pestana y que la pestana toma su titulo. Lo
// que esta mal y que hacer, y los detalles plegados, los construye la parte siguiente.
import { useEffect } from 'react';
import { PageHeader, Screen } from '@/components/page-header';
import { Section } from '@/components/section';
import { ErrorState, Loading } from '@/components/states';
import { useTabs } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { DateText } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { directionLabel } from '@/i18n/domain';
import { paths } from '@/lib/api';
import { useSession } from '@/lib/session';
import { useLoad } from './use-load';

interface InvoiceDetail {
  id: number;
  rev: number;
  sentido: 'entrante' | 'saliente';
  numero: string | null;
  contraparte: string | null;
  // La ficha da el vencimiento con su procedencia; aqui basta la fecha.
  vencimiento: { fecha: string | null } | null;
}

export function InvoiceScreen({ id, tabId }: { id: number; tabId: string }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { setTabTitle } = useTabs();
  const [state, retry] = useLoad(
    () => session!.api.get<{ factura: InvoiceDetail }>(paths.invoice(id)).then((r) => r.factura),
    [session, id]
  );

  // La pestana toma el numero de la factura (texto del documento: se pinta como texto).
  const numero = state.status === 'ready' ? state.data.numero : null;
  useEffect(() => {
    if (numero) setTabTitle(tabId, numero);
  }, [numero, tabId, setTabTitle]);

  const fallback = fmt(t.records.invoice.fallbackTitle, { id });
  if (state.status === 'loading') {
    return (
      <Screen>
        <PageHeader title={fallback} description={t.invoice.baseNote} />
        <Loading />
      </Screen>
    );
  }
  if (state.status === 'error') {
    return (
      <Screen>
        <PageHeader title={fallback} description={t.invoice.baseNote} />
        <ErrorState error={state.error} onRetry={retry} />
      </Screen>
    );
  }
  const f = state.data;
  return (
    <Screen>
      <PageHeader
        title={`${t.records.invoice.label} ${f.numero ?? f.id}`}
        description={t.invoice.baseNote}
        meta={directionLabel(lang, f.sentido) ?? undefined}
      />
      <dl className='mb-6 grid max-w-xl grid-cols-[10rem_1fr] gap-y-2'>
        <dt className='text-muted-foreground'>{t.invoice.partyLabel}</dt>
        <dd className='m-0'>{f.contraparte ?? '—'}</dd>
        <dt className='text-muted-foreground'>{t.invoice.dueLabel}</dt>
        <dd className='m-0'>
          <DateText value={f.vencimiento?.fecha} prose />
        </dd>
      </dl>
      <Section title={t.common.details}>
        <p className='text-muted-foreground'>{t.common.comingSoon}</p>
      </Section>
    </Screen>
  );
}
