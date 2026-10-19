// Que pinta cada ruta. Lo que aun no esta hecho es un PlaceholderScreen con su titulo y
// su frase; las partes siguientes del paso 15 cambian aqui una linea por pantalla. Las
// del trabajo diario (Overzicht, Werklijst, Uitzonderingen, IBAN-controles, Inkomend,
// Uitgaand y la ficha de factura) ya son las de verdad.
import { ShieldOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState } from '@/components/states';
import type { Tab, TabRoute } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { fmt, useT } from '@/i18n';
import { useCan } from '@/lib/session';
import { ExceptionsScreen } from './exceptions';
import { IbanChecksScreen } from './iban-checks';
import { InvoiceScreen } from './invoice';
import { InvoiceListScreen } from './invoice-list';
import { OverviewScreen } from './overview';
import { PlaceholderScreen } from './placeholder';
import { NAV, RECORDS, isNavId, isRecordId, type NavId, type RecordId } from './registry';
import { SettingsScreen } from './settings';
import { WorkQueueScreen } from './work-queue';

function NavScreen({ id, tabId }: { id: NavId; tabId: string }): ReactNode {
  switch (id) {
    case 'overview':
      return <OverviewScreen />;
    case 'work-queue':
      return <WorkQueueScreen tabId={tabId} />;
    case 'exceptions':
      return <ExceptionsScreen />;
    case 'iban-checks':
      return <IbanChecksScreen />;
    case 'invoices-in':
    case 'invoices-out':
      return <InvoiceListScreen key={id} navId={id} tabId={tabId} />;
    case 'settings':
      return <SettingsScreen />;
    default:
      return <PlaceholderScreen navId={id} />;
  }
}

function RecordScreen({ screen, id, tabId }: { screen: RecordId; id: number; tabId: string }) {
  const { t } = useT();
  if (screen === 'invoice') return <InvoiceScreen id={id} tabId={tabId} />;
  const record = t.records[screen];
  const parent = t.nav[RECORDS[screen].nav];
  return (
    <Screen>
      <PageHeader title={fmt(record.fallbackTitle, { id })} description={parent.description} />
      <EmptyState title={t.common.comingSoon} />
    </Screen>
  );
}

function NoAccess({ id }: { id: NavId }) {
  const { t } = useT();
  return (
    <Screen>
      <PageHeader title={t.nav[id].label} description={t.nav[id].description} />
      <EmptyState icon={ShieldOff} title={t.errors.forbidden} />
    </Screen>
  );
}

export function ScreenFor({ route, tab }: { route: TabRoute; tab: Tab }) {
  const can = useCan();
  if (isNavId(route.screen)) {
    const def = NAV.find((n) => n.id === route.screen);
    if (def?.requires && !can(def.requires)) return <NoAccess id={route.screen} />;
    return <NavScreen id={route.screen} tabId={tab.id} />;
  }
  if (isRecordId(route.screen) && route.id !== undefined) {
    return <RecordScreen screen={route.screen} id={route.id} tabId={tab.id} />;
  }
  return <PlaceholderScreen navId='overview' />;
}
