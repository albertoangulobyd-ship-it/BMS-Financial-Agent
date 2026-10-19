// Que pinta cada ruta: cada entrada de la navegacion y cada ficha tiene su pantalla (una
// linea por pantalla). Una ruta que no se conoce vuelve al Overzicht.
import { ShieldOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState } from '@/components/states';
import type { Tab, TabRoute } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { useT } from '@/i18n';
import { useCan } from '@/lib/session';
import { CashFlowScreen } from './cash-flow';
import { ExceptionsScreen } from './exceptions';
import { IbanChecksScreen } from './iban-checks';
import { ImportScreen } from './import';
import { InvoiceScreen } from './invoice';
import { InvoiceListScreen } from './invoice-list';
import { ObjectScreen } from './object';
import { ObjectsScreen } from './objects';
import { OverviewScreen } from './overview';
import { PartyScreen } from './party';
import { PartyListScreen } from './party-list';
import { PurchaseOrderScreen } from './purchase-order';
import { PurchaseOrdersScreen } from './purchase-orders';
import { ReadInvoicesScreen } from './read-invoices';
import { NAV, isNavId, isRecordId, type NavId, type RecordId } from './registry';
import { SettingsScreen } from './settings';
import { VatScreen } from './vat';
import { VatQuarterScreen } from './vat-quarter';
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
    case 'providers':
      return <PartyListScreen key={id} kind='provider' tabId={tabId} />;
    case 'clients':
      return <PartyListScreen key={id} kind='client' tabId={tabId} />;
    case 'objects':
      return <ObjectsScreen tabId={tabId} />;
    case 'purchase-orders':
      return <PurchaseOrdersScreen tabId={tabId} />;
    case 'cash-flow':
      return <CashFlowScreen />;
    case 'vat':
      return <VatScreen />;
    case 'import':
      return <ImportScreen />;
    case 'read-invoices':
      return <ReadInvoicesScreen />;
    case 'settings':
      return <SettingsScreen />;
  }
}

function RecordScreen({ screen, id, tabId }: { screen: RecordId; id: number; tabId: string }) {
  switch (screen) {
    case 'invoice':
      return <InvoiceScreen id={id} tabId={tabId} />;
    case 'provider':
    case 'client':
      return <PartyScreen key={screen} kind={screen} id={id} tabId={tabId} />;
    case 'object':
      return <ObjectScreen id={id} tabId={tabId} />;
    case 'purchase-order':
      return <PurchaseOrderScreen id={id} tabId={tabId} />;
    case 'vat-quarter':
      return <VatQuarterScreen id={id} tabId={tabId} />;
  }
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
  return <OverviewScreen />;
}
