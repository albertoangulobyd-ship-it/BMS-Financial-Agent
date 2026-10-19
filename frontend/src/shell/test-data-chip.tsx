// La marca de datos de prueba en la cabecera (ademas de la banda que pone el servidor):
// sale cuando la API contesta con X-BMS-Entorno: demo. Es un estado (warning, sin latido:
// no pide hacer nada), con la pastilla de components/status-pill.
import { StatusPill } from '@/components/status-pill';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useT } from '@/i18n';
import { useSession } from '@/lib/session';

export function TestDataChip() {
  const { t } = useT();
  const { session } = useSession();
  if (session?.environment !== 'demo') return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <StatusPill group='datos_prueba' state='demo' tabIndex={0} data-testid='test-data-chip' />
      </TooltipTrigger>
      <TooltipContent className='max-w-xs text-xs'>{t.testData.chipHelp}</TooltipContent>
    </Tooltip>
  );
}
