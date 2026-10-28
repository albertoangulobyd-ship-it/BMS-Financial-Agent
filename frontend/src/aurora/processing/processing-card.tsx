// ProcessingCard de Aurora (components/ui/processing-card.tsx, entrega del 28-10-2026), tal cual:
// el marco discreto, la textura tenue y, debajo de la escena, el avance ASCII ligado al progreso.
// Cambios (especificacion §4.2):
// - D: el % y las lineas vienen de la lectura de verdad (document-loader.tsx); el pie dice la
//   lectura real, cuantas facturas y lo gastado; la etiqueta de arriba dice tambien "esperando al
//   lector" (P1 y P2); las dos lineas sin empezar, las de cada estado (especificacion §5.4);
// - I: los textos, del diccionario;
// - el % del motor y el techo de la lectura van en data-motor y data-techo, para las pruebas;
// - las lineas llevan nombres de PDF (texto de un tercero): data-proper-name.
import type {ReactNode} from 'react';
import {useT} from '@/i18n';
import './processing-card.css';
export type ProcessingProgress={value:number;rows:string;status:string};
/** Quiet, monochrome adaptation of the supplied ProcessingCard. Progress is supplied by the scene. */
export function ProcessingCard({running,progress,children,state,idle,footer,engine,ceiling}:{running:boolean;progress:ProcessingProgress;children:ReactNode;state:string;idle:[string,string];footer:string;engine?:number;ceiling?:number}){
 const {t}=useT();const c=t.aurora.process.card;
 const filled=Math.floor(progress.value/5);
 return <section className={'processing-card '+(running?'is-running':'is-queued')} aria-label={c.label} data-motor={engine} data-techo={ceiling}>
  <div className="pc-outline" aria-hidden="true"/>
  <div className="pc-texture" aria-hidden="true">{Array.from({length:5},(_,i)=><span key={i}>{'·  .    :   ·     .  '.repeat(6)}</span>)}</div>
  <div className="pc-label"><span>{c.brand}</span><span>{state}</span></div>
  <div className="pc-scene">{children}</div>
  <div className="pc-reading">
   {running?<><div className="pc-progress" role="progressbar" aria-label={c.progress} aria-valuenow={progress.value} aria-valuemin={0} aria-valuemax={100}><span aria-hidden="true">[{Array.from({length:20},(_,i)=><i key={i} className={i<filled?'filled':''}>{i<filled?'▓':'░'}</i>)}]</span><b>{progress.value}%</b></div><pre data-proper-name={progress.rows?'':undefined}>{progress.rows||c.preparing}</pre><small>{footer}</small></>:<p>{idle[0]}<br/><span>{idle[1]}</span></p>}
  </div>
 </section>;
}
