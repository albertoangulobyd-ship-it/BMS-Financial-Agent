// Una pantalla de trabajo (la otra pantalla de Root, como Documentos en Aurora): Documentos, una
// ficha o una pantalla del motor que aun no vive en su panel. El marco es el del archivo de
// Aurora (document-workspace.tsx:36): la marca arriba a la izquierda, "← Volver a Aurora" arriba
// a la derecha, las migas (ws-breadcrumbs, con "Inicio" delante) y el orbe pequeno de la esquina
// (SiriWave de 180 px en su caja de 96x52), que es adonde vuela el orbe al entrar y de donde sale
// al volver. Volver al inicio por el orbe, "Volver a Aurora" o la miga "Inicio" lleva el vuelo
// inverso; Alt+← y el boton "atras" del raton vuelven un paso (o al inicio).
//
// Dentro, la pantalla de siempre (screens/render.tsx) con su camino (shell/navigation.tsx).
// Documentos lleva su propia cabecera con el orbe pequeno (aurora/documents/archive.tsx).
import { ArrowLeft, ChevronRight } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { fmt, useT } from '@/i18n';
import { useSession } from '@/lib/session';
import { isViewId, sectionDef, sectionOf, type Route } from '@/screens/registry';
import { isOverviewView } from '@/screens/sections';
import { ScreenFor } from '@/screens/render';
import { routeLabel } from '@/shell/crumbs';
import { NavigationProvider, useNav } from '@/shell/navigation';
import { BmsLogo } from './logo';
import { SiriWave } from './orb/siri-wave';
import { useAurora } from './root';

/** Las pantallas que traen su propia cabecera con el orbe pequeno (el archivo). */
const OWN_HEADING = new Set(['documents', 'client-documents', 'provider-documents']);

export function WorkScreen({ trail }: { trail: readonly Route[] }) {
  const { session } = useSession();
  // Una sesion que caduca aqui: Root ya pinta la entrada; esta pantalla, que se funde al irse,
  // no pinta nada (sus pantallas leen de la sesion).
  if (!session) return null;
  return (
    <NavigationProvider initial={trail}>
      <TooltipProvider delayDuration={0}>
        <WorkFrame />
      </TooltipProvider>
    </NavigationProvider>
  );
}

/** "Volver a Aurora", el orbe pequeno y la miga "Inicio": al inicio, con el vuelo inverso. */
export function useBackToAurora(): () => void {
  const { go } = useAurora();
  return () => go({ type: 'home' });
}

function HostCrumbs() {
  const { t } = useT();
  const nav = useNav();
  const home = useBackToAurora();
  const root = nav.trail[0]!;
  const section = isViewId(root.screen) ? sectionOf(root.screen) : null;
  const items: { label: string; data: boolean; onSelect?: () => void }[] = [];
  // La entrada de la seccion delante (Inicio no: ya es la primera miga).
  if (section && section !== 'home' && sectionDef(section).views.length > 1 && root.screen !== sectionDef(section).views[0]) {
    items.push({ label: t.areas[section].label, data: false });
  }
  nav.trail.forEach((route, i) => {
    const last = i === nav.trail.length - 1;
    items.push({
      // El resumen de Inicio se llama como su fila del panel ("Resumen"), no "Inicio" otra vez.
      // Los resumenes de cobrar y pagar, con el nombre de su entrada ("Cuentas por pagar").
      label:
        route.screen === 'home'
          ? t.aurora.panel.overview
          : isViewId(route.screen) && isOverviewView(route.screen)
            ? t.areas[route.screen].label
            : routeLabel(route, t, nav.titleOf(route)),
      data: !isViewId(route.screen) && nav.titleOf(route) !== undefined,
      onSelect: last ? undefined : () => nav.backTo(i),
    });
  });
  return (
    <nav className='ws-breadcrumbs' aria-label={t.shell.breadcrumbs}>
      <ol>
        <li>
          <a role='link' tabIndex={0} onClick={home} onKeyDown={(e) => e.key === 'Enter' && home()}>
            {t.aurora.work.home}
          </a>
        </li>
        {items.map((item, i) => (
          <li key={i}>
            <ChevronRight size={12} aria-hidden='true' />
            {item.onSelect ? (
              <a
                role='link'
                tabIndex={0}
                title={fmt(t.shell.backTo, { what: item.label })}
                onClick={item.onSelect}
                onKeyDown={(e) => e.key === 'Enter' && item.onSelect?.()}
                data-proper-name={item.data ? '' : undefined}
              >
                {item.label}
              </a>
            ) : (
              // La entrada de la seccion no es un paso: solo la ultima miga es donde se esta.
              <span aria-current={i === items.length - 1 ? 'page' : undefined} data-proper-name={item.data ? '' : undefined}>
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function WorkFrame() {
  const { t } = useT();
  const nav = useNav();
  const home = useBackToAurora();
  const body = useRef<HTMLDivElement>(null);
  const current = nav.current;
  const root = nav.trail[0]!;
  const section = isViewId(root.screen) ? sectionOf(root.screen) : null;
  const ownHeading = OWN_HEADING.has(current.screen);
  const { back } = nav;
  const depth = nav.trail.length;

  // Alt+← y el boton "atras" del raton: un paso atras; en la raiz, al inicio (la salida visible).
  useEffect(() => {
    const step = () => (depth > 1 ? back() : home());
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && !e.ctrlKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        step();
      }
    };
    const onMouse = (e: MouseEvent) => {
      if (e.button === 3) {
        e.preventDefault();
        step();
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mouseup', onMouse);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mouseup', onMouse);
    };
  }, [back, home, depth]);

  // Despues de cada cambio de sitio, el foco va al contenido.
  useEffect(() => {
    if (nav.moves > 0) body.current?.focus({ preventScroll: true });
  }, [nav.moves]);

  return (
    <div className='workspace workspace-host'>
      <BmsLogo />
      <a className='ws-home' role='link' tabIndex={0} onClick={home} onKeyDown={(e) => e.key === 'Enter' && home()}>
        <ArrowLeft size={15} /> {t.aurora.work.back}
      </a>
      <div className='host-frame'>
        <HostCrumbs />
        {!ownHeading && (
          <div className='ws-heading host-heading'>
            <div>
              <button type='button' className='ws-companion' onClick={home} aria-label={t.aurora.archive.home}>
                <span className='aurora-shared'>
                  <SiriWave size={180} renderScale={1} />
                </span>
              </button>
              <p className='ws-eyebrow'>{(section ? t.areas[section].label : t.nav.settings.label).toLocaleUpperCase()}</p>
            </div>
          </div>
        )}
        {/* role=main y no <main>: las hojas de Aurora dan a main la altura y el recorte del inicio. */}
        <div className='host-body' id='contenido' role='main' ref={body} tabIndex={-1}>
          <ScreenFor route={current} />
        </div>
      </div>
    </div>
  );
}
