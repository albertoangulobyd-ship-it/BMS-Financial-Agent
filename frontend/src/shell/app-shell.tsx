// El marco de la app una vez dentro: el componente de navegacion del dueno con todas las
// entradas (las que la persona puede ver), las pestanas guardadas por entorno y persona,
// y a la derecha de la tira de pestanas la marca de datos de prueba, NL | EN y la persona.
import { useCallback, useMemo } from 'react';
import {
  SidebarWithTabs,
  type NavItem,
  type SavedTabsState,
  type TabRoute,
} from '@/components/ui/sidebar-with-chrome-like-tabs';
import { fmt, useT } from '@/i18n';
import { formatDateLong, todayIso } from '@/lib/format';
import { useCan, useSession } from '@/lib/session';
import { loadTabs, personKey, saveTabs } from '@/lib/storage';
import { NAV, RECORDS, DEFAULT_SCREEN, isRecordId, isValidRoute } from '@/screens/registry';
import { ScreenFor } from '@/screens/render';
import { AccountMenu } from './account-menu';
import { LanguageSwitch } from './language-switch';
import { TestDataChip } from './test-data-chip';
import { badgeFor, useBadgeCounts } from './use-badges';

function Logo() {
  return (
    <span
      aria-hidden='true'
      className='flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-sidebar-primary text-xs font-semibold tracking-[0.02em] text-sidebar-primary-foreground'
    >
      BM
    </span>
  );
}

export function AppShell() {
  const { t } = useT();
  const { session } = useSession();
  const can = useCan();
  const [counts] = useBadgeCounts(session);

  const navItems: NavItem[] = useMemo(
    () =>
      NAV.filter((n) => can(n.requires)).map((n) => ({
        id: n.id,
        label: t.nav[n.id].label,
        hint: t.nav[n.id].hint || undefined,
        icon: n.icon,
        group: t.groups[n.group],
        badge: badgeFor(n.id, counts, t.badges),
      })),
    [t, can, counts]
  );

  // Lo que vuelve de localStorage se abre solo si la app lo conoce y la persona puede.
  const routeAllowed = useCallback(
    (route: TabRoute) => {
      if (!isValidRoute(route)) return false;
      const def = NAV.find((n) => n.id === route.screen);
      return !def?.requires || can(def.requires);
    },
    [can]
  );

  const tabsKey = session ? personKey(session.environment, session.me.id, 'tabs') : null;
  const loadState = useCallback(
    () => (tabsKey ? loadTabs(tabsKey, routeAllowed) : null),
    [tabsKey, routeAllowed]
  );
  const saveState = useCallback(
    (state: SavedTabsState) => {
      if (tabsKey) saveTabs(tabsKey, state);
    },
    [tabsKey]
  );

  const describeRoute = useCallback(
    (route: TabRoute) => {
      if (!isRecordId(route.screen)) return null;
      return {
        label: fmt(t.records[route.screen].fallbackTitle, { id: route.id ?? '' }),
        icon: RECORDS[route.screen].icon,
      };
    },
    [t]
  );

  const labels = useMemo(() => t.tabs, [t]);

  return (
    <SidebarWithTabs
      // Otra persona u otro entorno es otro estado de pestanas desde cero.
      key={tabsKey ?? 'sin-sesion'}
      logo={<Logo />}
      companyName={t.app.name}
      navItems={navItems}
      defaultNavId={DEFAULT_SCREEN}
      renderContent={(route, tab) => <ScreenFor route={route} tab={tab} />}
      describeRoute={describeRoute}
      loadState={loadState}
      saveState={saveState}
      labels={labels}
      toolbar={
        <>
          <TestDataChip />
          <LanguageSwitch />
          <AccountMenu />
        </>
      }
      footer={
        <div className='px-1 text-xs leading-snug'>
          <p className='text-muted-foreground'>{t.footer.today}</p>
          <p className='font-medium text-sidebar-foreground'>{formatDateLong(todayIso(), t)}</p>
        </div>
      }
    />
  );
}
