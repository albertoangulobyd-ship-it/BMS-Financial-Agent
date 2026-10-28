// WorkspaceComposer de Aurora (components/ui/workspace-composer.tsx, entrega del 28-10-2026), tal
// cual: la misma caja, el mismo boton y el mismo cambio de icono (flecha o lupa) en la
// conversacion y en la busqueda. Cambio (I): los textos y los nombres accesibles salen del
// diccionario. Es un <form> con un solo campo: no pide contrasenas (la entrada con el codigo no
// usa <form>, ver login.tsx).
import type { FormEvent } from 'react';
import { ArrowUp, Search } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useT } from '@/i18n';

type Props = {
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  mode?: 'chat' | 'search';
  disabled?: boolean;
  autoFocus?: boolean;
};

/** The same input, spacing and button in both modes; the glyph reflects chat or search. */
export function WorkspaceComposer({ value, onValueChange, onSubmit, mode = 'chat', disabled = false, autoFocus = false }: Props) {
  const { t } = useT();
  const texts = t.aurora.composer;
  const searching = mode === 'search';
  return (
    <form className='composer workspace-composer' onSubmit={onSubmit} role={searching ? 'search' : undefined}>
      <div className='input-row'>
        <span className='aura-slot' aria-hidden='true' />
        <input
          autoFocus={autoFocus}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          placeholder={searching ? texts.searchPlaceholder : texts.askPlaceholder}
          aria-label={searching ? texts.searchLabel : texts.askLabel}
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
              {searching ? <Search size={19} /> : <ArrowUp size={19} />}
            </motion.span>
          </AnimatePresence>
        </button>
      </div>
    </form>
  );
}
