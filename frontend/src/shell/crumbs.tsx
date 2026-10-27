// Las migas y "Volver" (paso 16): dentro de una ficha, de donde se viene (Cuentas por cobrar ›
// Clientes › Gemeente Demodorp › VD26-306). Cada miga vuelve a ese paso; "Volver" quita el
// ultimo. En la raiz de una seccion no hay migas: lo dice la navegacion de arriba.
import { ArrowLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmt, useT, type Messages } from '@/i18n';
import { idToQuarter, quarterLabel } from '@/lib/format';
import { isRecordId, isViewId, sectionDef, sectionOf, type Route } from '@/screens/registry';
import { useNav } from './navigation';

/** El nombre de un paso del camino: una vista por su nombre, una ficha por su titulo. */
export function routeLabel(route: Route, t: Messages, title: string | undefined): string {
  if (isViewId(route.screen)) return t.nav[route.screen].label;
  if (title) return title;
  if (route.screen === 'vat-quarter' && route.id) {
    const quarter = idToQuarter(route.id);
    return fmt(t.records['vat-quarter'].fallbackTitle, { id: quarter ? quarterLabel(quarter) : route.id });
  }
  return isRecordId(route.screen) ? fmt(t.records[route.screen].fallbackTitle, { id: route.id ?? '' }) : '';
}

interface Crumb {
  label: string;
  /** Lo que viene de los datos (un numero, un nombre): no es texto de la app. */
  data: boolean;
  onSelect?: () => void;
}

export function Crumbs() {
  const { t } = useT();
  const nav = useNav();
  if (nav.trail.length <= 1) return null;
  const root = nav.trail[0]!;
  const items: Crumb[] = [];
  const section = isViewId(root.screen) ? sectionOf(root.screen) : null;
  // La seccion, cuando tiene varias vistas (Cuentas por pagar › Facturas de compra › ...); con
  // una sola vista (Documentos, IVA) el nombre de la vista ya lo dice.
  if (section && root.screen !== 'home' && sectionDef(section).views.length > 1) {
    const first = sectionDef(section).views[0]!;
    items.push({ label: t.areas[section].label, data: false, onSelect: () => nav.go(first) });
  }
  nav.trail.forEach((route, i) => {
    const last = i === nav.trail.length - 1;
    items.push({
      label: routeLabel(route, t, nav.titleOf(route)),
      data: !isViewId(route.screen) && nav.titleOf(route) !== undefined,
      onSelect: last ? undefined : () => nav.backTo(i),
    });
  });
  const previous = items[items.length - 2]!;
  return (
    <div className='mb-4 flex flex-wrap items-center gap-x-3 gap-y-1'>
      <Button variant='ghost' size='sm' className='-ml-2 h-8 gap-1.5 px-2' onClick={nav.back} title={fmt(t.shell.backTo, { what: previous.label })}>
        <ArrowLeft className='h-4 w-4' aria-hidden='true' />
        {t.shell.back}
      </Button>
      <nav aria-label={t.shell.breadcrumbs} className='min-w-0'>
        <ol className='flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[13px]'>
          {items.map((item, i) => (
            <li key={i} className='flex min-w-0 items-center gap-1'>
              {i > 0 && <ChevronRight className='h-3.5 w-3.5 shrink-0 text-muted-foreground' aria-hidden='true' />}
              {item.onSelect ? (
                <button
                  type='button'
                  onClick={item.onSelect}
                  className='truncate rounded-sm text-soft-foreground underline-offset-4 hover:text-foreground hover:underline'
                  data-proper-name={item.data ? '' : undefined}
                >
                  {item.label}
                </button>
              ) : (
                <span aria-current='page' className='truncate font-medium text-foreground' data-proper-name={item.data ? '' : undefined}>
                  {item.label}
                </span>
              )}
            </li>
          ))}
        </ol>
      </nav>
    </div>
  );
}
