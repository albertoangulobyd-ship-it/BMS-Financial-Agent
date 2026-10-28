// Los paneles (E2): el .panel de Aurora (main.tsx:34-39 del dueno) con lo de cada entrada
// (especificacion §2.2). Cada panel vive en aurora/panels/: Inicio (E2-I), Cuentas por cobrar y
// por pagar (E2-C y E2-P, con Importar dentro de cobrar), IVA (E2-V) y Ajustes (E2-A). Sus piezas
// (el marco, la cifra principal, las filas, la vista de un grupo, la tarjeta) estan en
// panels/pieces.tsx; las ordenes de una tarjeta, en orders.tsx.
import type { EntryId } from './estado';
import { HomePanel } from './panels/home-panel';
import { MoneyPanel } from './panels/money-panel';
import { SettingsPanel } from './panels/settings-panel';
import { VatPanel } from './panels/vat-panel';
import { useAurora } from './root';

/** El panel de una entrada. Cada uno se monta de nuevo al cambiar de entrada (key). */
export function PanelFor({ entry }: { entry: EntryId }) {
  const { state } = useAurora();
  const view = state.view;
  switch (entry) {
    case 'settings':
      return <SettingsPanel key={entry} view={view} />;
    case 'home':
      return <HomePanel key={entry} view={view} />;
    case 'receivables':
      return <MoneyPanel key={entry} side='saliente' view={view} />;
    case 'payables':
      return <MoneyPanel key={entry} side='entrante' view={view} />;
    case 'vat':
      return <VatPanel key={entry} view={view} />;
    default:
      return null;
  }
}
