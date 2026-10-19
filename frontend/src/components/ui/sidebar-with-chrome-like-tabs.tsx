'use client';

/*
 * El componente de navegacion del dueno (barra lateral + pestanas como las de Chrome),
 * con el mismo aspecto, el mismo movimiento, el menu contextual de cada pestana, el
 * "abrir rapido" del boton + y la hoja del movil. Lo que se cambio y por que (paso 15):
 *
 * - NavItem lleva ademas `group` (los apartados Daily, Invoices, Parties...: con quince
 *   pantallas, una lista sin grupos no se entiende), `badge` (solo cuentas que piden hacer
 *   algo) y `hint` (una palabra gris al lado, como "purchase" junto a "In").
 * - Una pestana lleva una ruta (`route`: pantalla y, si es una ficha, su id numerico) y un
 *   titulo, en vez de solo el id del menu: asi una fila abre su factura en una pestana, y
 *   si esa factura ya esta abierta se va a su pestana (`openRoute`). El titulo (un numero
 *   de factura, un nombre) no se guarda: puede ser texto de un documento.
 * - Los textos llegan en `labels` (la app esta en neerlandes e ingles).
 * - Lo que se guarda (pestanas, la activa y si la barra va plegada) no lo lee ni lo
 *   escribe el componente: lo hacen `loadState` y `saveState`, que la app guarda con una
 *   clave por entorno y por persona y comprueba al leer (lib/storage.ts). Antes era una
 *   clave fija de localStorage sin comprobar nada.
 * - Respeta prefers-reduced-motion (desplazamientos y el fundido del contenido de la
 *   pestana sin animar; el resto lo hace MotionConfig en la app).
 * - Accesibilidad: cada boton de icono lleva aria-label; la pestana activa controla el
 *   panel (role tabpanel, que se puede enfocar para desplazarlo con el teclado: patron de
 *   pestanas de WAI-ARIA); el boton de cerrar va fuera del elemento role=tab (un boton
 *   dentro de una pestana es un control anidado) y se cierra tambien con Supr.
 * - La tira de pestanas: solo las pestanas se desplazan; el + y el ... van fuera (a 1024 px
 *   el + quedaba debajo del ...) y un fundido en cada borde dice que hay mas pestanas a ese
 *   lado. La barra lateral no esconde su barra de desplazamiento y en pantallas bajas
 *   (820 px o menos) va mas junta: a 768 px se ven todos los apartados.
 * - Tailwind v4: shrink-0 en vez de flex-shrink-0; h-full en vez de h-screen (las bandas
 *   del servidor van encima); text-destructive en vez de text-red-500.
 * - `toolbar`: lo de la derecha de la tira de pestanas (idioma, persona, datos de prueba).
 * - Sin imagenes de fuera: el logo y la persona son texto (la CSP no deja otra cosa).
 */

import React, {
  useState,
  useRef,
  useCallback,
  useMemo,
  useContext,
  createContext,
  useEffect,
} from 'react';
import { motion, AnimatePresence, Reorder, useReducedMotion } from 'framer-motion';
import {
  X,
  Plus,
  PanelLeft,
  Menu,
  type LucideIcon,
  MoreHorizontal,
  ChevronRight,
  ChevronLeft,
  Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';

/**
 * Represents a navigation item in the sidebar.
 */
export interface NavItem {
  /** Unique identifier for the navigation item */
  id: string;
  /** Label text to display */
  label: string;
  /** Icon component to render */
  icon: LucideIcon;
  /** Group heading this item belongs to (consecutive items share it); '' = separator only */
  group?: string;
  /** A small grey word next to the label */
  hint?: string;
  /** A count that needs action; nothing is shown when absent or zero */
  badge?: NavBadge;
}

export interface NavBadge {
  count: number;
  /** Text after the count ("Blocked"); also read by screen readers */
  label?: string;
  tone?: 'blocked' | 'neutral';
}

/**
 * Where a tab is: a screen and, for a record, its numeric id. `from` is the nav item the
 * record was opened from (it stays highlighted in the sidebar).
 */
export interface TabRoute {
  screen: string;
  id?: number;
  from?: string;
}

/**
 * Represents a single browser-like tab.
 */
export interface Tab {
  /** Unique identifier for the tab */
  id: string;
  /** What the tab shows */
  route: TabRoute;
  /** Title set at runtime by the screen (never stored) */
  title?: string;
}

/** What is stored between sessions: ids and numbers only. */
export interface SavedTabsState {
  tabs: { id: string; route: TabRoute }[];
  activeTabId: string;
  collapsed: boolean;
}

export interface SidebarWithTabsLabels {
  newTab: string;
  closeTab: string;
  closeOtherTabs: string;
  closeTabsToRight: string;
  closeTabsToLeft: string;
  closeAllTabs: string;
  quickOpen: string;
  sidebarNavigation: string;
  collapseSidebar: string;
  expandSidebar: string;
  moreTabOptions: string;
  openMenu: string;
  close: string;
  tabs: string;
  mainNavigation: string;
}

const DEFAULT_LABELS: SidebarWithTabsLabels = {
  newTab: 'New Tab',
  closeTab: 'Close Tab',
  closeOtherTabs: 'Close Other Tabs',
  closeTabsToRight: 'Close Tabs to the Right',
  closeTabsToLeft: 'Close Tabs to the Left',
  closeAllTabs: 'Close All Tabs',
  quickOpen: 'Quick Open',
  sidebarNavigation: 'Sidebar Navigation',
  collapseSidebar: 'Collapse sidebar',
  expandSidebar: 'Expand sidebar',
  moreTabOptions: 'More tab options',
  openMenu: 'Open menu',
  close: 'Close',
  tabs: 'Tabs',
  mainNavigation: 'Main',
};

/**
 * Props for the main SidebarWithTabs component.
 */
export interface SidebarWithTabsProps {
  /** Optional custom logo component */
  logo?: React.ReactNode;
  /** Name of the company/application */
  companyName?: string;
  /** List of navigation items */
  navItems: NavItem[];
  /** Function to render content for the active tab */
  renderContent: (route: TabRoute, tab: Tab) => React.ReactNode;
  /** ID of the default active navigation item */
  defaultNavId?: string;
  /** Optional footer content (e.g. user profile) */
  footer?: React.ReactNode;
  /** Content at the right end of the tab strip */
  toolbar?: React.ReactNode;
  /** Label and icon of a route that is not a nav item (a record) */
  describeRoute?: (route: TabRoute) => { label: string; icon?: LucideIcon } | null;
  /** Restore what was stored (already validated), or null */
  loadState?: () => SavedTabsState | null;
  /** Store the layout (ids and numbers only) */
  saveState?: (state: SavedTabsState) => void;
  /** UI texts */
  labels?: Partial<SidebarWithTabsLabels>;
}

interface TabsContextValue {
  tabs: Tab[];
  activeTabId: string;
  activeNavId: string;
  activeRoute: TabRoute;
  setActiveNav: (navId: string) => void;
  addTab: (navId?: string) => void;
  openRoute: (route: TabRoute) => void;
  setTabTitle: (tabId: string, title: string | undefined) => void;
  closeTab: (tabId: string) => void;
  closeOthers: (tabId: string) => void;
  closeToRight: (tabId: string) => void;
  closeToLeft: (tabId: string) => void;
  closeAll: () => void;
  setActiveTab: (tabId: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

/**
 * Custom hook to access tab context.
 * Must be used within a SidebarWithTabs provider.
 */
export function useTabs() {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error('useTabs must be used within SidebarWithTabs');
  }
  return context;
}

/** Two routes show the same thing when screen and id match (where it came from does not count). */
export function sameRoute(a: TabRoute, b: TabRoute): boolean {
  return a.screen === b.screen && (a.id ?? null) === (b.id ?? null);
}

function tabDomId(tabId: string): string {
  return `tab-${tabId.replace(/[^A-Za-z0-9_-]/g, '')}`;
}

/**
 * Individual tab component ensuring accessibility and animation.
 */
function ChromeTab({
  tab,
  isActive,
  isLast,
  canClose,
  label,
  icon: Icon,
  labels,
  hasRightNeighborActive,
  onTabClick,
  onTabClose,
  onCloseOthers,
  onCloseToRight,
  onCloseToLeft,
  hasOtherTabs,
  hasTabsToRight,
  hasTabsToLeft,
}: {
  tab: Tab;
  isActive: boolean;
  isLast: boolean;
  canClose: boolean;
  label: string;
  icon?: LucideIcon;
  labels: SidebarWithTabsLabels;
  hasRightNeighborActive: boolean;
  onTabClick: () => void;
  onTabClose: () => void;
  onCloseOthers: () => void;
  onCloseToRight: () => void;
  onCloseToLeft: () => void;
  hasOtherTabs: boolean;
  hasTabsToRight: boolean;
  hasTabsToLeft: boolean;
}) {
  const tabRef = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();
  const behavior: ScrollBehavior = reduceMotion ? 'auto' : 'smooth';

  useEffect(() => {
    if (isActive && tabRef.current) {
      // Standard scroll into view
      tabRef.current.scrollIntoView({
        behavior,
        block: 'nearest',
        inline: 'center',
      });

      if (isLast) {
        // Tiny timeout to let layout settle
        const timer = setTimeout(() => {
          const plusBtn = tabRef.current
            ?.closest('.flex')
            ?.querySelector('.new-tab-btn');
          if (plusBtn) {
            plusBtn.scrollIntoView({
              behavior,
              block: 'nearest',
              inline: 'center',
            });
          }
        }, 250);
        return () => clearTimeout(timer);
      }
    }
    return undefined;
  }, [isActive, isLast, behavior]);

  // Ensure active tab is centered on initial load (handling refresh)
  useEffect(() => {
    if (isActive && tabRef.current) {
      // Small delay to ensure layout is ready
      const timer = setTimeout(() => {
        tabRef.current?.scrollIntoView({
          behavior: 'auto',
          block: 'nearest',
          inline: 'center',
        });
      }, 200);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, []);

  const handleAuxClick = (e: React.MouseEvent) => {
    if (e.button === 1 && canClose) {
      e.preventDefault();
      onTabClose();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onTabClick();
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      if (canClose) {
        e.preventDefault();
        onTabClose();
      }
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      const nextTab = (e.target as HTMLElement)
        .closest('li')
        ?.nextElementSibling?.querySelector('[role="tab"]') as HTMLElement | null;
      nextTab?.focus();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      const prevTab = (e.target as HTMLElement)
        .closest('li')
        ?.previousElementSibling?.querySelector('[role="tab"]') as HTMLElement | null;
      prevTab?.focus();
    }
  };

  return (
    <ContextMenu>
      <ContextMenuTrigger>
        <div
          role='tab'
          id={tabDomId(tab.id)}
          aria-selected={isActive}
          aria-controls={isActive ? 'tab-panel' : undefined}
          aria-keyshortcuts={canClose ? 'Delete' : undefined}
          tabIndex={isActive ? 0 : -1}
          className={cn(
            'relative flex items-center gap-2 px-4 py-2.5 ml-[10px] sm:ml-0 text-sm cursor-pointer active:cursor-grabbing transition-colors duration-150 min-w-[140px] max-w-[220px] outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar',
            canClose && 'pr-9',
            isActive
              ? 'text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          )}
          onClick={onTabClick}
          onAuxClick={handleAuxClick}
          onKeyDown={handleKeyDown}
          ref={tabRef}
        >
          {isActive && (
            <motion.div
              className='absolute inset-0 bg-background rounded-t-xl'
              layoutId='activeTabBg'
              transition={{ type: 'spring', bounce: 0.15, duration: 0.4 }}
            >
              <div
                className={cn(
                  'absolute -left-3 bottom-0 w-3 h-3 overflow-hidden'
                )}
              >
                <div className='absolute right-0 bottom-0 w-6 h-6 bg-sidebar rounded-full z-1' />
                <div className='absolute inset-0 bg-background' />
              </div>
              <div className='absolute -right-3 bottom-0 w-3 h-3 overflow-hidden'>
                <div className='absolute left-0 bottom-0 w-6 h-6 bg-sidebar rounded-full z-1' />
                <div className='absolute inset-0 bg-background' />
              </div>
            </motion.div>
          )}

          <div className='relative flex items-center gap-2 flex-1 min-w-0'>
            {Icon && <Icon className='h-4 w-4 shrink-0' aria-hidden='true' />}
            <span className='truncate flex-1 font-medium select-none'>
              {label}
            </span>
          </div>

          {!isActive && !hasRightNeighborActive && (
            <div className='absolute right-0 top-1/2 -translate-y-1/2 w-[1px] h-4 bg-sidebar-border' />
          )}
        </div>
        {canClose && (
          // Fuera del role=tab: con el raton se cierra aqui; con el teclado, Supr en la
          // pestana (o su menu contextual).
          <button
            type='button'
            tabIndex={-1}
            aria-hidden='true'
            onClick={(e) => {
              e.stopPropagation();
              onTabClose();
            }}
            className={cn(
              'absolute right-3 top-1/2 -translate-y-1/2 z-10 flex h-5 w-5 items-center justify-center rounded-full transition-colors shrink-0',
              isActive
                ? 'hover:bg-muted text-muted-foreground hover:text-foreground'
                : 'opacity-0 group-hover:opacity-100 hover:bg-sidebar-accent text-muted-foreground hover:text-sidebar-foreground'
            )}
          >
            <X className='h-3 w-3' />
          </button>
        )}
      </ContextMenuTrigger>
      <ContextMenuContent className='w-56'>
        <ContextMenuItem onClick={onTabClose} disabled={!canClose}>
          {labels.closeTab}
        </ContextMenuItem>
        <ContextMenuSeparator />
        <ContextMenuItem onClick={onCloseOthers} disabled={!hasOtherTabs}>
          {labels.closeOtherTabs}
        </ContextMenuItem>
        <ContextMenuItem onClick={onCloseToRight} disabled={!hasTabsToRight}>
          <ChevronRight className='mr-2 h-4 w-4' aria-hidden='true' />
          {labels.closeTabsToRight}
        </ContextMenuItem>
        <ContextMenuItem onClick={onCloseToLeft} disabled={!hasTabsToLeft}>
          <ChevronLeft className='mr-2 h-4 w-4' aria-hidden='true' />
          {labels.closeTabsToLeft}
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

function NavBadgeView({ badge, compact }: { badge?: NavBadge; compact?: boolean }) {
  if (!badge || badge.count <= 0) return null;
  const blocked = badge.tone === 'blocked';
  if (compact) {
    return (
      <span
        className={cn(
          'absolute right-1.5 top-1 h-2 w-2 rounded-full',
          blocked ? 'bg-pill-blocked' : 'bg-muted-foreground'
        )}
        aria-hidden='true'
      />
    );
  }
  return (
    <span
      className={cn(
        'ml-auto inline-flex items-center gap-1 rounded-full px-1.5 text-[11.5px] font-semibold leading-[18px] num shrink-0',
        blocked
          ? 'bg-pill-blocked text-pill-blocked-foreground'
          : 'bg-[#e3ded3] text-sidebar-foreground'
      )}
    >
      <span>{badge.count}</span>
      {badge.label && <span className='font-medium'>{badge.label}</span>}
    </span>
  );
}

function badgeText(badge?: NavBadge): string {
  if (!badge || badge.count <= 0) return '';
  return badge.label ? `${badge.count} ${badge.label}` : String(badge.count);
}

/**
 * Navigation items list component.
 */
function SidebarNavigation({
  navItems,
  activeNavId,
  isCollapsed,
  onItemClick,
  ariaLabel,
}: {
  navItems: NavItem[];
  activeNavId: string;
  isCollapsed: boolean;
  onItemClick: (item: NavItem) => void;
  ariaLabel: string;
}) {
  // Los apartados: los elementos seguidos con el mismo grupo van juntos.
  const groups = useMemo(() => {
    const out: { group: string | undefined; items: NavItem[] }[] = [];
    for (const item of navItems) {
      const last = out[out.length - 1];
      if (last && last.group === item.group) last.items.push(item);
      else out.push({ group: item.group, items: [item] });
    }
    return out;
  }, [navItems]);

  const renderItem = (item: NavItem) => {
    const isActive = item.id === activeNavId;
    const extra = badgeText(item.badge);
    const NavButton = (
      <button
        key={item.id}
        type='button'
        onClick={() => onItemClick(item)}
        aria-current={isActive ? 'page' : undefined}
        aria-label={isCollapsed ? [item.label, extra].filter(Boolean).join(', ') : undefined}
        className={cn(
          'w-full flex items-center gap-3 px-3 py-[7px] short:py-[4px] rounded-lg transition-all duration-150 text-left relative',
          isActive
            ? 'bg-sidebar-accent text-sidebar-accent-foreground font-semibold'
            : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
          isCollapsed && 'justify-center px-0'
        )}
      >
        <item.icon
          aria-hidden='true'
          className={cn(
            'h-[18px] w-[18px] shrink-0',
            isActive
              ? 'text-sidebar-accent-foreground'
              : 'text-muted-foreground'
          )}
        />
        <AnimatePresence>
          {!isCollapsed && (
            <AnimatePresence>
              {!isCollapsed && (
                <motion.span
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  transition={{
                    type: 'spring',
                    stiffness: 300,
                    damping: 30,
                  }}
                  className='text-sm whitespace-nowrap overflow-hidden flex items-baseline gap-2'
                >
                  <span>{item.label}</span>
                  {item.hint && (
                    <span className='text-xs font-normal text-muted-foreground'>
                      {item.hint}
                    </span>
                  )}
                </motion.span>
              )}
            </AnimatePresence>
          )}
        </AnimatePresence>
        <NavBadgeView badge={item.badge} compact={isCollapsed} />
        {isActive && !isCollapsed && (
          <motion.div
            layoutId='activeNavIndicator'
            className='absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-sidebar-primary rounded-r-full'
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          />
        )}
      </button>
    );

    if (isCollapsed) {
      return (
        <Tooltip key={item.id}>
          <TooltipTrigger asChild>{NavButton}</TooltipTrigger>
          <TooltipContent side='right' className='font-medium'>
            {[item.label, extra].filter(Boolean).join(' · ')}
          </TooltipContent>
        </Tooltip>
      );
    }

    return NavButton;
  };

  return (
    <nav className='px-3' aria-label={ariaLabel}>
      {groups.map(({ group, items }, index) => (
        <div
          key={`${group ?? ''}-${index}`}
          role='group'
          aria-label={group || undefined}
          className={cn(
            'space-y-0.5',
            index > 0 && (group ? 'mt-3 short:mt-2' : 'mt-3 short:mt-2 pt-2 border-t border-sidebar-border')
          )}
        >
          {group && !isCollapsed && (
            <div className='px-3 pb-1 short:pb-0.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground select-none'>
              {group}
            </div>
          )}
          {group && isCollapsed && index > 0 && (
            <div className='mx-2 mb-2 h-px bg-sidebar-border' aria-hidden='true' />
          )}
          {items.map(renderItem)}
        </div>
      ))}
    </nav>
  );
}

function MobileSidebar({
  logo,
  companyName,
  navItems,
  activeNavId,
  onItemClick,
  labels,
}: {
  logo?: React.ReactNode;
  companyName: string;
  navItems: NavItem[];
  activeNavId: string;
  onItemClick: (item: NavItem) => void;
  labels: SidebarWithTabsLabels;
}) {
  const [open, setOpen] = useState(false);

  const handleItemClick = (item: NavItem) => {
    onItemClick(item);
    setOpen(false);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant='ghost'
          size='icon'
          aria-label={labels.openMenu}
          className='h-9 w-9 text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent shrink-0'
        >
          <Menu className='h-5 w-5' aria-hidden='true' />
        </Button>
      </SheetTrigger>
      <SheetContent
        side='left'
        className='w-72 p-0 border-r-0'
        closeLabel={labels.close}
        aria-describedby={undefined}
      >
        <SheetTitle className='sr-only'>{labels.sidebarNavigation}</SheetTitle>
        <div className='flex flex-col h-full bg-sidebar'>
          <div className='flex items-center gap-3 p-5 border-b border-sidebar-border'>
            {logo || (
              <div className='flex h-9 w-9 items-center justify-center rounded-xl bg-sidebar-primary'>
                <span className='text-sm font-bold text-sidebar-primary-foreground'>
                  A
                </span>
              </div>
            )}
            <span className='text-base font-bold text-sidebar-foreground'>
              {companyName}
            </span>
          </div>
          <div className='flex-1 py-4 overflow-y-auto'>
            <SidebarNavigation
              navItems={navItems}
              activeNavId={activeNavId}
              isCollapsed={false}
              onItemClick={handleItemClick}
              ariaLabel={labels.mainNavigation}
            />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/**
 * Button to add a new tab, supporting tap-to-add and hold-for-menu interactions.
 */
function NewTabButton({
  navItems,
  onAddTab,
  labels,
}: {
  navItems: NavItem[];
  onAddTab: (navId?: string) => void;
  labels: SidebarWithTabsLabels;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isLongPress = useRef(false);
  const lastTouchTime = useRef(0);

  const handleTouchStart = () => {
    lastTouchTime.current = Date.now();
    isLongPress.current = false;
    timerRef.current = setTimeout(() => {
      isLongPress.current = true;
      setIsOpen(true);
    }, 500);
  };

  const handleTouchEnd = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    const isTouch = Date.now() - lastTouchTime.current < 1000;
    if (isTouch) {
      if (isLongPress.current) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      setIsOpen(false);
      onAddTab();
    } else {
      onAddTab();
    }
  };

  return (
    <HoverCard
      open={isOpen}
      onOpenChange={(open) => {
        // Prevent opening on touch interaction (simulated hover) unless it's a confirmed long press
        const isTouch = Date.now() - lastTouchTime.current < 1000;
        if (open && isTouch && !isLongPress.current) {
          return;
        }
        setIsOpen(open);
      }}
      openDelay={200}
      closeDelay={100}
    >
      <HoverCardTrigger asChild>
        <button
          type='button'
          aria-label={labels.newTab}
          onClick={handleClick}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          className='flex h-9 w-9 items-center justify-center text-muted-foreground transition-colors hover:text-foreground ml-1 mb-0.5 shrink-0 new-tab-btn rounded-lg'
        >
          <Plus className='h-4 w-4' aria-hidden='true' />
        </button>
      </HoverCardTrigger>
      <HoverCardContent
        align='start'
        className='w-56 p-1 bg-popover border-border max-h-[70vh] overflow-y-auto'
        sideOffset={8}
      >
        <div className='text-xs text-muted-foreground px-2 py-1.5 font-medium'>
          {labels.quickOpen}
        </div>
        {navItems.map((item) => (
          <button
            key={item.id}
            type='button'
            onClick={() => {
              setIsOpen(false);
              onAddTab(item.id);
            }}
            className='w-full flex items-center gap-2 px-2 py-1.5 text-sm text-popover-foreground hover:bg-accent rounded-md transition-colors'
          >
            <item.icon className='h-4 w-4 text-muted-foreground' aria-hidden='true' />
            <span>{item.label}</span>
          </button>
        ))}
      </HoverCardContent>
    </HoverCard>
  );
}

/**
 * Main Layout component featuring a sidebar and tabbed navigation.
 */
export function SidebarWithTabs({
  logo,
  companyName = 'Acme Inc',
  navItems,
  renderContent,
  defaultNavId,
  footer,
  toolbar,
  describeRoute,
  loadState,
  saveState,
  labels: labelsProp,
}: SidebarWithTabsProps) {
  const labels = useMemo(() => ({ ...DEFAULT_LABELS, ...labelsProp }), [labelsProp]);
  // MotionConfig reducedMotion='user' quita los desplazamientos, no la opacidad: el
  // fundido del contenido de la pestana se quita aqui.
  const reduceMotion = useReducedMotion();
  // Si hay pestanas escondidas a un lado de la tira (para su fundido).
  const stripRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  const updateEdges = useCallback(() => {
    const el = stripRef.current;
    if (!el) return;
    const left = el.scrollLeft > 1;
    const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
    setEdges((prev) => (prev.left === left && prev.right === right ? prev : { left, right }));
  }, []);
  useEffect(() => {
    const el = stripRef.current;
    if (!el) return undefined;
    updateEdges();
    const observer = new ResizeObserver(updateEdges);
    observer.observe(el);
    const list = el.firstElementChild;
    if (list) observer.observe(list);
    return () => observer.disconnect();
  }, [updateEdges]);
  const defaultNav = defaultNavId || navItems[0]?.id || '';
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTabId, setActiveTabId] = useState('');
  const [isClient, setIsClient] = useState(false);
  const tabCounterRef = useRef(1);

  // Hydrate state from storage (lo valida quien lo da: loadState)
  useEffect(() => {
    setIsClient(true);
    const savedState = loadState?.() ?? null;

    if (savedState && savedState.tabs.length > 0) {
      setTabs(savedState.tabs.map((t) => ({ id: t.id, route: t.route })));
      setActiveTabId(
        savedState.tabs.some((t) => t.id === savedState.activeTabId)
          ? savedState.activeTabId
          : savedState.tabs[0]!.id
      );
      setIsCollapsed(savedState.collapsed);

      // Sync tab counter
      const maxId = savedState.tabs.reduce((max, tab) => {
        const match = tab.id.match(/tab-(\d+)-/);
        return match ? Math.max(max, parseInt(match[1]!, 10)) : max;
      }, 1);
      tabCounterRef.current = maxId;
    } else {
      setTabs([{ id: 'tab-1', route: { screen: defaultNav } }]);
      setActiveTabId('tab-1');
    }
  }, [defaultNav]);

  // Lo que se guarda: ids y numeros, nunca el titulo.
  const snapshot = useCallback(
    (): SavedTabsState => ({
      tabs: tabs.map((t) => ({ id: t.id, route: t.route })),
      activeTabId,
      collapsed: isCollapsed,
    }),
    [tabs, activeTabId, isCollapsed]
  );

  // Persist state efficiently
  useEffect(() => {
    if (!isClient || tabs.length === 0 || !saveState) return;

    const handler = setTimeout(() => {
      saveState(snapshot());
    }, 500); // Debounce to prevent heavy writes

    return () => clearTimeout(handler);
  }, [tabs, activeTabId, isCollapsed, isClient, saveState, snapshot]);

  // Al cerrar o recargar la ventana se guarda ya, sin esperar al medio segundo.
  useEffect(() => {
    if (!isClient || tabs.length === 0 || !saveState) return;
    const flush = () => saveState(snapshot());
    window.addEventListener('pagehide', flush);
    return () => window.removeEventListener('pagehide', flush);
  }, [isClient, tabs.length, saveState, snapshot]);

  useEffect(() => {
    if (isClient && tabs.length === 0) {
      setTabs([{ id: 'tab-1', route: { screen: defaultNav } }]);
      setActiveTabId('tab-1');
    }
  }, [isClient, tabs.length, defaultNav]);

  const activeTab = tabs.find((t) => t.id === activeTabId);
  const activeRoute: TabRoute = activeTab?.route ?? { screen: defaultNav };
  const activeNavId = activeRoute.from ?? activeRoute.screen;
  const activeTabIndex = tabs.findIndex((t) => t.id === activeTabId);

  const setActiveNav = useCallback(
    (navId: string) => {
      setTabs((prev) =>
        prev.map((tab) =>
          tab.id === activeTabId
            ? { id: tab.id, route: { screen: navId } }
            : tab
        )
      );
    },
    [activeTabId]
  );

  const newTabId = useCallback(() => {
    tabCounterRef.current += 1;
    return `tab-${tabCounterRef.current}-${Date.now()}`;
  }, []);

  const addTab = useCallback(
    (navId?: string) => {
      const id = newTabId();
      const newTab: Tab = {
        id,
        route: { screen: navId || defaultNav },
      };
      setTabs((prev) => [...prev, newTab]);
      setActiveTabId(id);
    },
    [defaultNav, newTabId]
  );

  // Una ficha se abre en su pestana; si ya esta abierta, se va a ella.
  const openRoute = useCallback(
    (route: TabRoute) => {
      const existing = tabs.find((t) => sameRoute(t.route, route));
      if (existing) {
        setActiveTabId(existing.id);
        return;
      }
      const id = newTabId();
      setTabs((prev) => [...prev, { id, route }]);
      setActiveTabId(id);
    },
    [tabs, newTabId]
  );

  const setTabTitle = useCallback((tabId: string, title: string | undefined) => {
    setTabs((prev) =>
      prev.map((tab) => (tab.id === tabId && tab.title !== title ? { ...tab, title } : tab))
    );
  }, []);

  const closeTab = useCallback(
    (tabId: string) => {
      if (tabs.length === 1) return;
      const tabIndex = tabs.findIndex((t) => t.id === tabId);
      const newTabs = tabs.filter((t) => t.id !== tabId);
      setTabs(newTabs);

      if (activeTabId === tabId) {
        // Select the next tab (right) if available, otherwise the previous (left)
        const newActiveIndex =
          tabIndex === newTabs.length ? tabIndex - 1 : tabIndex;
        // Ensure we have a valid index
        const safeIndex = Math.max(0, newActiveIndex);
        const next = newTabs[safeIndex];
        if (next) {
          setActiveTabId(next.id);
        }
      }
    },
    [tabs, activeTabId]
  );

  const closeOthers = useCallback((tabId: string) => {
    setTabs((prev) => prev.filter((t) => t.id === tabId));
    setActiveTabId(tabId);
  }, []);

  const closeToRight = useCallback(
    (tabId: string) => {
      const index = tabs.findIndex((t) => t.id === tabId);
      const newTabs = tabs.slice(0, index + 1);
      setTabs(newTabs);
      if (!newTabs.find((t) => t.id === activeTabId)) {
        setActiveTabId(tabId);
      }
    },
    [tabs, activeTabId]
  );

  const closeToLeft = useCallback(
    (tabId: string) => {
      const index = tabs.findIndex((t) => t.id === tabId);
      const newTabs = tabs.slice(index);
      setTabs(newTabs);
      if (!newTabs.find((t) => t.id === activeTabId)) {
        setActiveTabId(tabId);
      }
    },
    [tabs, activeTabId]
  );

  const closeAll = useCallback(() => {
    if (tabs.length <= 1) return;
    const firstTab = tabs[0]!;
    setTabs([firstTab]);
    setActiveTabId(firstTab.id);
  }, [tabs]);

  const setActiveTab = useCallback((tabId: string) => {
    setActiveTabId(tabId);
  }, []);

  const handleNavItemClick = useCallback(
    (item: NavItem) => {
      setActiveNav(item.id);
    },
    [setActiveNav]
  );

  const describe = useCallback(
    (tab: Tab): { label: string; icon?: LucideIcon } => {
      const nav = navItems.find((n) => n.id === tab.route.screen);
      if (nav && tab.route.id === undefined) return { label: nav.label, icon: nav.icon };
      const described = describeRoute?.(tab.route);
      return {
        label: tab.title || described?.label || nav?.label || labels.newTab,
        icon: described?.icon ?? nav?.icon,
      };
    },
    [navItems, describeRoute, labels.newTab]
  );

  const contextValue = useMemo(
    () => ({
      tabs,
      activeTabId,
      activeNavId,
      activeRoute,
      setActiveNav,
      addTab,
      openRoute,
      setTabTitle,
      closeTab,
      closeOthers,
      closeToRight,
      closeToLeft,
      closeAll,
      setActiveTab,
    }),
    [
      tabs,
      activeTabId,
      activeNavId,
      activeRoute,
      setActiveNav,
      addTab,
      openRoute,
      setTabTitle,
      closeTab,
      closeOthers,
      closeToRight,
      closeToLeft,
      closeAll,
      setActiveTab,
    ]
  );

  const canCloseTab = tabs.length > 1;
  const hasOtherTabs = tabs.length > 1;

  return (
    <TooltipProvider delayDuration={0}>
      <TabsContext.Provider value={contextValue}>
        <div className='flex h-full w-full bg-sidebar overflow-hidden'>
          <motion.aside
            initial={false}
            animate={{ width: isCollapsed ? 64 : 248 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className='hidden md:flex flex-col bg-sidebar overflow-hidden shrink-0'
          >
            <div className='flex flex-col h-full overflow-hidden'>
              <div
                className={cn(
                  'flex items-center h-[52px] px-4 border-b border-sidebar-border',
                  isCollapsed ? 'justify-center' : 'justify-between'
                )}
              >
                <div className='flex items-center gap-3 min-w-0'>
                  {logo || (
                    <div className='flex h-8 w-8 items-center justify-center rounded-lg bg-sidebar-primary shrink-0'>
                      <span className='text-sm font-bold text-sidebar-primary-foreground'>
                        A
                      </span>
                    </div>
                  )}
                  <AnimatePresence>
                    {!isCollapsed && (
                      <motion.span
                        initial={{ opacity: 0, width: 0 }}
                        animate={{ opacity: 1, width: 'auto' }}
                        exit={{ opacity: 0, width: 0 }}
                        transition={{
                          type: 'spring',
                          stiffness: 300,
                          damping: 30,
                        }}
                        className='text-sm font-bold text-sidebar-foreground truncate tracking-tight whitespace-nowrap'
                      >
                        {companyName}
                      </motion.span>
                    )}
                  </AnimatePresence>
                </div>
                {!isCollapsed && (
                  <Button
                    variant='ghost'
                    size='icon'
                    aria-label={labels.collapseSidebar}
                    onClick={() => setIsCollapsed(!isCollapsed)}
                    className='h-8 w-8 text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent shrink-0'
                  >
                    <PanelLeft className='h-4 w-4' aria-hidden='true' />
                  </Button>
                )}
              </div>

              {isCollapsed && (
                <div className='flex justify-center py-2 border-b border-sidebar-border'>
                  <Button
                    variant='ghost'
                    size='icon'
                    aria-label={labels.expandSidebar}
                    onClick={() => setIsCollapsed(!isCollapsed)}
                    className='h-8 w-8 text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent shrink-0'
                  >
                    <PanelLeft className='h-4 w-4 rotate-180' aria-hidden='true' />
                  </Button>
                </div>
              )}

              {/* Sin esconder la barra de desplazamiento (si no cabe, se ve que hay mas) y
                  mas junto en pantallas bajas (short: 820 px o menos): a 768 px de alto
                  caben todos los apartados, Instellingen incluido. */}
              <div className='flex-1 py-3 short:py-2 overflow-y-auto [scrollbar-width:thin]'>
                <SidebarNavigation
                  navItems={navItems}
                  activeNavId={activeNavId}
                  isCollapsed={isCollapsed}
                  onItemClick={handleNavItemClick}
                  ariaLabel={labels.mainNavigation}
                />
              </div>

              <div className='p-4 border-t border-sidebar-border h-[73px] flex items-center justify-center overflow-hidden'>
                <AnimatePresence mode='wait'>
                  {!isCollapsed ? (
                    footer ? (
                      <motion.div
                        key='expanded'
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -10 }}
                        transition={{
                          type: 'spring',
                          stiffness: 300,
                          damping: 30,
                        }}
                        className='w-full'
                      >
                        {footer}
                      </motion.div>
                    ) : null
                  ) : (
                    <motion.div
                      key='collapsed'
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      transition={{
                        type: 'spring',
                        stiffness: 300,
                        damping: 30,
                      }}
                      className='flex justify-center'
                    >
                      {logo || (
                        <div className='w-8 h-8 rounded-full bg-muted shrink-0' />
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.aside>

          <div className='flex flex-1 flex-col overflow-hidden relative min-w-0'>
            <div className='flex items-end bg-sidebar pt-2'>
              <div className='md:hidden shrink-0 self-center ml-2'>
                <MobileSidebar
                  logo={logo}
                  companyName={companyName}
                  navItems={navItems}
                  activeNavId={activeNavId}
                  onItemClick={handleNavItemClick}
                  labels={labels}
                />
              </div>

              {/* Solo las pestanas se desplazan; + y ... van fuera, para que nunca se tapen
                  (a 1024 px el + quedaba debajo de ...). Un fundido en el borde dice que hay
                  mas pestanas a ese lado. */}
              <div className='relative flex min-w-0 flex-1 items-end'>
              <div
                ref={stripRef}
                onScroll={updateEdges}
                className='flex min-w-0 flex-1 items-end overflow-x-auto scrollbar-hide'
                style={{ scrollbarWidth: 'none' }}
              >
                <Reorder.Group
                  as='ol'
                  axis='x'
                  values={tabs}
                  onReorder={setTabs}
                  className='flex items-end'
                  role='tablist'
                  aria-label={labels.tabs}
                >
                  <AnimatePresence initial={false}>
                    {tabs.map((tab, index) => {
                      const isActive = tab.id === activeTabId;
                      const isLast = index === tabs.length - 1;
                      const hasRightNeighborActive =
                        index < tabs.length - 1 &&
                        tabs[index + 1]!.id === activeTabId;
                      const { label, icon } = describe(tab);

                      return (
                        <Reorder.Item
                          value={tab}
                          as='li'
                          role='presentation'
                          layout
                          key={tab.id}
                          initial={{ opacity: 0, width: 0 }}
                          animate={{ opacity: 1, width: 'auto' }}
                          exit={{ opacity: 0, width: 0 }}
                          whileDrag={{ cursor: 'grabbing' }}
                          transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
                          className='relative group shrink-0'
                          style={{ zIndex: isActive ? 10 : 1 }}
                        >
                          <ChromeTab
                            tab={tab}
                            isActive={isActive}
                            isLast={isLast}
                            canClose={canCloseTab}
                            label={label}
                            icon={icon}
                            labels={labels}
                            hasRightNeighborActive={hasRightNeighborActive}
                            onTabClick={() => setActiveTab(tab.id)}
                            onTabClose={() => closeTab(tab.id)}
                            onCloseOthers={() => closeOthers(tab.id)}
                            onCloseToRight={() => closeToRight(tab.id)}
                            onCloseToLeft={() => closeToLeft(tab.id)}
                            hasOtherTabs={hasOtherTabs}
                            hasTabsToRight={index < tabs.length - 1}
                            hasTabsToLeft={index > 0}
                          />
                        </Reorder.Item>
                      );
                    })}
                  </AnimatePresence>
                </Reorder.Group>
              </div>
              {edges.left && (
                <div
                  aria-hidden='true'
                  data-testid='tabs-fade-left'
                  className='pointer-events-none absolute inset-y-0 left-0 w-8 bg-linear-to-r from-sidebar to-transparent'
                />
              )}
              {edges.right && (
                <div
                  aria-hidden='true'
                  data-testid='tabs-fade-right'
                  className='pointer-events-none absolute inset-y-0 right-0 w-8 bg-linear-to-l from-sidebar to-transparent'
                />
              )}
              </div>

              <div className='shrink-0'>
                <NewTabButton navItems={navItems} onAddTab={addTab} labels={labels} />
              </div>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type='button'
                    aria-label={labels.moreTabOptions}
                    className='flex h-9 w-9 items-center justify-center text-muted-foreground transition-colors hover:text-foreground hover:bg-sidebar-accent rounded-lg mr-2 mb-0.5 shrink-0'
                  >
                    <MoreHorizontal className='h-5 w-5' aria-hidden='true' />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align='end' className='w-52'>
                  <DropdownMenuItem onClick={() => addTab()}>
                    <Plus className='mr-2 h-4 w-4' aria-hidden='true' />
                    {labels.newTab}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={closeAll}
                    disabled={!hasOtherTabs}
                    className={cn(
                      hasOtherTabs && 'text-destructive focus:text-destructive'
                    )}
                  >
                    <Trash2 className='mr-2 h-4 w-4' aria-hidden='true' />
                    {labels.closeAllTabs}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              {toolbar && (
                <div className='flex items-center gap-2 self-center mr-3 mb-1 shrink-0'>
                  {toolbar}
                </div>
              )}
            </div>

            <main className='flex-1 overflow-hidden bg-sidebar p-0 md:pr-3 md:pb-3'>
              <div
                id='tab-panel'
                role='tabpanel'
                // Se desplaza: con el teclado tiene que poder enfocarse para bajar con las
                // flechas (una pantalla sin botones, como Facturen lezen, no tendria otra forma).
                tabIndex={0}
                aria-labelledby={activeTab ? tabDomId(activeTab.id) : undefined}
                className={cn(
                  'h-full bg-background overflow-auto transition-all duration-300 ease-in-out',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                  'md:rounded-br-3xl md:rounded-bl-3xl md:rounded-tr-3xl',
                  activeTabIndex !== 0 && 'md:rounded-tl-3xl'
                )}
              >
                <AnimatePresence mode='wait'>
                  <motion.div
                    key={`${activeTabId}-${activeRoute.screen}-${activeRoute.id ?? ''}`}
                    initial={reduceMotion ? false : { opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={reduceMotion ? { opacity: 1 } : { opacity: 0 }}
                    transition={{ duration: reduceMotion ? 0 : 0.15 }}
                    className='h-full'
                  >
                    {activeTab ? renderContent(activeRoute, activeTab) : null}
                  </motion.div>
                </AnimatePresence>
              </div>
            </main>
          </div>
        </div>
      </TabsContext.Provider>
    </TooltipProvider>
  );
}
