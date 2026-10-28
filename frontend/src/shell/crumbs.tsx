// El nombre de cada paso del camino, para las migas de una pantalla de trabajo
// (aurora/work-screen.tsx): Cuentas por cobrar › Clientes › Gemeente Demodorp › VD26-306.
import { fmt, type Messages } from '@/i18n';
import { idToQuarter, quarterLabel } from '@/lib/format';
import { isRecordId, isViewId, type Route } from '@/screens/registry';

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
