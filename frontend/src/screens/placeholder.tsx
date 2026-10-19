// Las pantallas que aun no estan hechas: su titulo y su frase, y nada mas. Las siguientes
// partes del paso 15 las sustituyen una a una (render.tsx dice cual va a cada ruta).
import { Construction } from 'lucide-react';
import { PageHeader, Screen } from '@/components/page-header';
import { EmptyState } from '@/components/states';
import { useT } from '@/i18n';
import type { NavId } from './registry';

export function PlaceholderScreen({ navId }: { navId: NavId }) {
  const { t } = useT();
  const nav = t.nav[navId];
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      <EmptyState icon={Construction} title={t.common.comingSoon} />
    </Screen>
  );
}
