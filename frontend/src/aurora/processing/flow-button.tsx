// FlowButton de Aurora (components/ui/flow-button.tsx, entrega del 28-10-2026), tal cual: el
// circulo que crece en 0,8 s, la etiqueta que se desliza y las dos flechas.
'use client';
import type {ButtonHTMLAttributes} from 'react';
import {ArrowRight} from 'lucide-react';
export function FlowButton({text='Continuar',className='',...props}:ButtonHTMLAttributes<HTMLButtonElement>&{text?:string}){return <button type="button" className={'flow-button '+className} {...props}><ArrowRight className="flow-arrow-left" size={16}/><span className="flow-label">{text}</span><span className="flow-circle" aria-hidden/><ArrowRight className="flow-arrow-right" size={16}/></button>}
