// El (?) junto a una palabra del oficio (Object, PO, BTW, Exception): una explicacion
// corta en palabras normales, con el raton o con el teclado (se abre al enfocarlo).
import { CircleQuestionMark } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { fmt, useT } from '@/i18n';

export type HelpTerm = 'object' | 'po' | 'btw' | 'exception';

export function HelpTip({ term }: { term: HelpTerm }) {
  const { t } = useT();
  const entry = t.help[term];
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type='button'
            aria-label={fmt(t.help.whatIs, { term: entry.term })}
            className='inline-flex h-4 w-4 items-center justify-center rounded-full align-[-2px] text-muted-foreground hover:text-foreground'
          >
            <CircleQuestionMark className='h-3.5 w-3.5' aria-hidden='true' />
          </button>
        </TooltipTrigger>
        <TooltipContent className='max-w-xs text-xs leading-relaxed'>{entry.text}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
