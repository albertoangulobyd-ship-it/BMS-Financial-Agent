// La caja de Aurora: "¿Que te gustaria resolver hoy?" (paso 16). La misma caja para preguntar y
// para buscar; solo cambia el icono del boton. Viene de workspace-composer.tsx del prototipo con
// los textos de los diccionarios. Es un <form> con un solo campo: no pide contrasenas ni nada
// que un navegador quiera guardar (la entrada con el token no usa <form>, ver login.tsx).
import type { FormEvent } from 'react';
import { ArrowUp, Search } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useT } from '@/i18n';
import { cn } from '@/lib/utils';

type Props = {
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  mode?: 'chat' | 'search';
  disabled?: boolean;
  autoFocus?: boolean;
  className?: string;
};

export function WorkspaceComposer({ value, onValueChange, onSubmit, mode = 'chat', disabled = false, autoFocus = false, className }: Props) {
  const { t } = useT();
  const texts = t.aurora.composer;
  const searching = mode === 'search';
  return (
    <div className='aurora-root'>
      <form className={cn('composer workspace-composer', className)} onSubmit={onSubmit} role={searching ? 'search' : undefined}>
        <div className='input-row'>
          <span className='aura-slot' aria-hidden='true' />
          <input
            autoFocus={autoFocus}
            value={value}
            onChange={(e) => onValueChange(e.target.value)}
            placeholder={searching ? texts.searchPlaceholder : texts.askPlaceholder}
            aria-label={searching ? texts.searchLabel : texts.askLabel}
            autoComplete='off'
            spellCheck={false}
          />
          <button className='send' type='submit' disabled={disabled} aria-label={searching ? texts.search : texts.send}>
            <AnimatePresence initial={searching} mode='wait'>
              <motion.span
                key={mode}
                className='composer-glyph'
                initial={{ opacity: 0, rotate: -35, scale: 0.65 }}
                animate={{ opacity: 1, rotate: 0, scale: 1 }}
                exit={{ opacity: 0, rotate: 35, scale: 0.65 }}
                transition={{ duration: 0.18 }}
              >
                {searching ? <Search size={19} aria-hidden='true' /> : <ArrowUp size={19} aria-hidden='true' />}
              </motion.span>
            </AnimatePresence>
          </button>
        </div>
      </form>
    </div>
  );
}
