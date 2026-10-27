// El marco de la app una vez dentro (paso 16). Arriba, la marca (lleva al inicio), las seis
// entradas en pequeno (en todas las pantallas menos el inicio, donde la navegacion es la rueda),
// la busqueda (Ctrl+K), la marca de datos de prueba y el menu del nombre (Ajustes, idioma, tema
// y Salir). Debajo, dentro de una ficha, las migas y "Volver"; en la raiz de una seccion, sus
// vistas. La tira de pestanas tipo Chrome del paso 15 ya no es la navegacion: queda en
// components/ui/sidebar-with-chrome-like-tabs.tsx sin montar.
import { Search } from 'lucide-react';
import { motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AuroraMark } from '@/aurora/orb/aurora-orb';
import { BmsLogo } from '@/aurora/logo';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useT } from '@/i18n';
import { RefreshProvider, useRefresh } from '@/lib/refresh';
import { useCan, useSession } from '@/lib/session';
import { cn } from '@/lib/utils';
import { HOME, isViewId, routeKey, visibleSections, visibleViews, type SectionId, type ViewId } from '@/screens/registry';
import { ScreenFor } from '@/screens/render';
import { AccountMenu } from './account-menu';
import { CommandPalette } from './command-palette';
import { CompactNav } from './compact-nav';
import { Crumbs } from './crumbs';
import { NavigationProvider, useNav } from './navigation';
import { SectionNav } from './section-nav';
import { TestDataChip } from './test-data-chip';
import { badgeFor, useBadgeCounts } from './use-badges';

export function AppShell() {
  const { session } = useSession();
  // Una orden hecha en cualquier pantalla sube la version: las insignias, las listas, el
  // inicio y la ficha se vuelven a leer. Otra persona u otro entorno empieza en el inicio.
  return (
    <RefreshProvider>
      <NavigationProvider key={session ? `${session.environment}:${session.me.id}` : 'sin-sesion'}>
        <TooltipProvider delayDuration={0}>
          <Shell />
        </TooltipProvider>
      </NavigationProvider>
    </RefreshProvider>
  );
}

function Shell() {
  const { t } = useT();
  const { session } = useSession();
  const can = useCan();
  const nav = useNav();
  const { version } = useRefresh();
  const [counts] = useBadgeCounts(session, version);
  const [palette, setPalette] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const sections = visibleSections(can);
  const root = nav.trail[0]!;
  const rootView: ViewId = isViewId(root.screen) ? root.screen : HOME;
  const atHome = nav.trail.length === 1 && rootView === HOME;
  const { back } = nav;

  const goSection = useCallback(
    (id: SectionId) => {
      const first = visibleViews(id, can)[0];
      if (first) nav.go(first);
    },
    [nav, can]
  );

  // Ctrl+K abre cualquier pantalla o ficha; Alt+flecha izquierda y el boton "atras" del raton
  // vuelven un paso, como en un navegador.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPalette(true);
      } else if (e.altKey && !e.ctrlKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        back();
      }
    };
    const onMouse = (e: MouseEvent) => {
      if (e.button === 3) {
        e.preventDefault();
        back();
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mouseup', onMouse);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mouseup', onMouse);
    };
  }, [back]);

  // Despues de cada cambio de sitio, el foco va al contenido (quien usa el teclado o un lector
  // de pantalla empieza por la pantalla nueva, no por el menu).
  useEffect(() => {
    if (nav.moves > 0) mainRef.current?.focus({ preventScroll: true });
  }, [nav.moves]);

  const sectionViews =
    nav.section && nav.trail.length === 1 ? visibleViews(nav.section, can).filter((v) => v !== HOME) : [];
  const showSectionNav = !atHome && sectionViews.length > 1;
  const current = nav.current;

  return (
    <div className='flex min-h-full flex-col bg-background'>
      <a
        href='#contenido'
        className='sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-3 focus:top-3'
        onClick={(e) => {
          e.preventDefault();
          mainRef.current?.focus();
        }}
      >
        {t.shell.skipToContent}
      </a>
      <header
        className={cn(
          'sticky top-0 z-30',
          atHome ? 'bg-background' : 'border-b border-border bg-background/95 backdrop-blur-md'
        )}
      >
        <div className='mx-auto flex w-full max-w-[1440px] flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5 sm:gap-x-5 sm:px-6'>
          <button
            type='button'
            onClick={() => nav.go(HOME)}
            aria-label={t.shell.home}
            className='flex shrink-0 items-center gap-2.5 rounded-md py-1 pr-1'
          >
            {!atHome && <AuroraMark className='h-6 w-6' />}
            <BmsLogo compact={!atHome} wordmark='wide' />
          </button>
          {!atHome && (
            <CompactNav
              sections={sections}
              current={nav.section}
              onGo={goSection}
              className='order-last w-full lg:order-none lg:w-auto'
            />
          )}
          <div className='ml-auto flex items-center gap-2'>
            <button
              type='button'
              onClick={() => setPalette(true)}
              aria-keyshortcuts='Control+K'
              className='flex h-8 items-center gap-2 rounded-full border border-border px-2.5 text-[13px] text-soft-foreground hover:border-border-strong hover:text-foreground xl:px-3'
            >
              <Search className='h-3.5 w-3.5' aria-hidden='true' />
              <span className='sr-only xl:not-sr-only'>{t.shell.search}</span>
              <kbd className='hidden rounded border border-border px-1 font-sans text-[11px] text-muted-foreground xl:inline'>
                {t.shell.searchShortcut}
              </kbd>
            </button>
            <TestDataChip />
            <AccountMenu />
          </div>
        </div>
      </header>
      <main
        id='contenido'
        ref={mainRef}
        tabIndex={-1}
        aria-label={atHome ? t.areas.home.label : undefined}
        className='flex-1 outline-none'
      >
        {!atHome && (
          <div className='mx-auto w-full max-w-[1240px] px-5 pt-4 xl:px-8'>
            <Crumbs />
            {showSectionNav && nav.section && (
              <SectionNav
                section={nav.section}
                views={sectionViews}
                current={rootView}
                onGo={nav.go}
                badge={(view) => badgeFor(view, counts, t.badges)}
              />
            )}
          </div>
        )}
        <div id='view'>
          {/* Un fundido corto al cambiar de sitio (con "menos movimiento", ninguno). */}
          <motion.div key={routeKey(current)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.16 }}>
            <ScreenFor route={current} />
          </motion.div>
        </div>
      </main>
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </div>
  );
}
