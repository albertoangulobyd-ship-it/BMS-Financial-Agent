// El boton de Aurora con la flecha que entra y el circulo que se llena (paso 16): para la
// accion principal de una pantalla de Aurora ("Empezar", "Ver en Documentos"). Viene de
// flow-button.tsx del prototipo; el texto lo da quien lo usa, ya traducido.
import type { ButtonHTMLAttributes } from 'react';
import { ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import './flow-button.css';

export function FlowButton({ text, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { text: string }) {
  return (
    <span className='aurora-root'>
      <button type='button' className={cn('flow-button', className)} {...props}>
        <ArrowRight className='flow-arrow-left' size={16} aria-hidden='true' />
        <span className='flow-label'>{text}</span>
        <span className='flow-circle' aria-hidden='true' />
        <ArrowRight className='flow-arrow-right' size={16} aria-hidden='true' />
      </button>
    </span>
  );
}
