// Que pinta cada ruta: cada vista y cada ficha tiene su pantalla (una linea por pantalla). La
// clave de la ruta (routeKey) es la de lo que recuerda (filtros) y la de su titulo en las
// migas. Una ruta que no se conoce vuelve al inicio.
import { ShieldOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState } from '@/components/states';
import { useT } from '@/i18n';
import { useCan } from '@/lib/session';
import { CashFlowScreen } from './cash-flow';
import { DocumentsScreen, PartyDocumentsScreen } from './documents';
import { ExceptionScreen } from './exception';
import { ExceptionsScreen } from './exceptions';
import { HomeScreen } from './home';
import { IbanChecksScreen } from './iban-checks';
import { ImportScreen } from './import';
import { InvoiceScreen } from './invoice';
import { InvoiceListScreen } from './invoice-list';
import { ObjectScreen } from './object';
import { ObjectsScreen } from './objects';
import { PartyScreen } from './party';
import { PartyListScreen } from './party-list';
import { PurchaseOrderScreen } from './purchase-order';
import { PurchaseOrdersScreen } from './purchase-orders';
import { ReadInvoicesScreen } from './read-invoices';
import { VIEWS, isRecordId, isViewId, routeKey, type RecordId, type Route, type ViewId } from './registry';
import { SettingsScreen } from './settings';
import { VatScreen } from './vat';
import { VatQuarterScreen } from './vat-quarter';
import { WorkQueueScreen } from './work-queue';

function ViewScreen({ id, navKey }: { id: ViewId; navKey: string }): ReactNode {
  switch (id) {
    case 'home':
      return <HomeScreen />;
    case 'work-queue':
      return <WorkQueueScreen navKey={navKey} />;
    case 'exceptions':
      return <ExceptionsScreen />;
    case 'cash-flow':
      return <CashFlowScreen />;
    case 'invoices-in':
    case 'invoices-out':
      return <InvoiceListScreen key={id} navId={id} navKey={navKey} />;
    case 'providers':
      return <PartyListScreen key={id} kind='provider' navKey={navKey} />;
    case 'clients':
      return <PartyListScreen key={id} kind='client' navKey={navKey} />;
    case 'objects':
      return <ObjectsScreen navKey={navKey} />;
    case 'client-pos':
      return <PurchaseOrdersScreen key={id} side='cliente' navKey={navKey} />;
    case 'provider-pos':
      return <PurchaseOrdersScreen key={id} side='proveedor' navKey={navKey} />;
    case 'iban-checks':
      return <IbanChecksScreen />;
    case 'documents':
      return <DocumentsScreen navKey={navKey} />;
    case 'read-invoices':
      return <ReadInvoicesScreen />;
    case 'import':
      return <ImportScreen />;
    case 'vat':
      return <VatScreen />;
    case 'settings':
      return <SettingsScreen />;
  }
}

function RecordScreen({ screen, id, navKey }: { screen: RecordId; id: number; navKey: string }) {
  switch (screen) {
    case 'invoice':
      return <InvoiceScreen id={id} navKey={navKey} />;
    case 'provider':
    case 'client':
      return <PartyScreen key={screen} kind={screen} id={id} navKey={navKey} />;
    case 'object':
      return <ObjectScreen id={id} navKey={navKey} />;
    case 'purchase-order':
      return <PurchaseOrderScreen id={id} navKey={navKey} />;
    case 'vat-quarter':
      return <VatQuarterScreen id={id} navKey={navKey} />;
    case 'exception':
      return <ExceptionScreen id={id} navKey={navKey} />;
    case 'client-documents':
      return <PartyDocumentsScreen key={screen} kind='client' id={id} navKey={navKey} />;
    case 'provider-documents':
      return <PartyDocumentsScreen key={screen} kind='provider' id={id} navKey={navKey} />;
  }
}

function NoAccess({ id }: { id: ViewId }) {
  const { t } = useT();
  return (
    <Screen>
      <PageHeader title={t.nav[id].label} description={t.nav[id].description} />
      <EmptyState icon={ShieldOff} title={t.errors.forbidden} />
    </Screen>
  );
}

export function ScreenFor({ route }: { route: Route }) {
  const can = useCan();
  const navKey = routeKey(route);
  if (isViewId(route.screen)) {
    const def = VIEWS[route.screen];
    if (def.requires && !can(def.requires)) return <NoAccess id={route.screen} />;
    return <ViewScreen id={route.screen} navKey={navKey} />;
  }
  if (isRecordId(route.screen) && route.id !== undefined) {
    return <RecordScreen screen={route.screen} id={route.id} navKey={navKey} />;
  }
  return <HomeScreen />;
}
