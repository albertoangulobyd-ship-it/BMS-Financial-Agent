// La marca de datos de prueba en la cabecera (ademas de la banda que pone el servidor):
// sale cuando la API contesta con X-BMS-Entorno: demo.
import { FlaskConical } from 'lucide-react';
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
        <span
          tabIndex={0}
          data-testid='test-data-chip'
          className='inline-flex items-center gap-1.5 rounded-full border border-testdata-border bg-testdata px-2.5 py-0.5 text-xs font-semibold text-testdata-foreground'
        >
          <FlaskConical className='h-3.5 w-3.5' aria-hidden='true' />
          {t.testData.chip}
        </span>
      </TooltipTrigger>
      <TooltipContent className='max-w-xs text-xs'>{t.testData.chipHelp}</TooltipContent>
    </Tooltip>
  );
}
