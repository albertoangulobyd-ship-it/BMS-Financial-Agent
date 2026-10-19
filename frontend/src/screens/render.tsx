// Que pinta cada ruta. Lo que aun no esta hecho es un PlaceholderScreen con su titulo y
// su frase; las partes siguientes del paso 15 cambian aqui una linea por pantalla.
import { ShieldOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState } from '@/components/states';
import type { Tab, TabRoute } from '@/components/ui/sidebar-with-chrome-like-tabs';
import { fmt, useT } from '@/i18n';
import { useCan } from '@/lib/session';
import { InvoiceScreen } from './invoice';
import { PlaceholderScreen } from './placeholder';
import { NAV, RECORDS, isNavId, isRecordId, type NavId, type RecordId } from './registry';
import { SettingsScreen } from './settings';
import { WorkQueueScreen } from './work-queue';

function NavScreen({ id }: { id: NavId }): ReactNode {
  switch (id) {
    case 'work-queue':
      return <WorkQueueScreen />;
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
    return <NavScreen id={route.screen} />;
  }
  if (isRecordId(route.screen) && route.id !== undefined) {
    return <RecordScreen screen={route.screen} id={route.id} tabId={tab.id} />;
  }
  return <PlaceholderScreen navId='overview' />;
}
