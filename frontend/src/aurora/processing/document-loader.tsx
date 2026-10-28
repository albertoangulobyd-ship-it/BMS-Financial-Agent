// DocumentLoader de Aurora (components/ui/document-loader.tsx, entrega del 28-10-2026), tal cual:
// UNA sola instancia del motor de la suricata entre la intro (la cabeza) y las etapas (el cuerpo),
// dentro de la ProcessingCard. Cambios (especificacion §4.2 y §5.5):
// - D: no hay start() al pasar a running (pondria auto=true y avanzaria solo cada 700 ms): quien
//   lleva la lectura de verdad pide cada etapa y el final por `handle` (setStage, finish, hide);
// - D: el % que se ve es min(motor, techo) y las lineas son las de la lectura (no las del motor);
// - I: los textos de la tarjeta llegan de la pantalla.
// Un motor nuevo (despues de un fundido) es otra instancia: la pantalla cambia la key.
import {useEffect,useRef,useState,type MutableRefObject} from 'react';
import {mountLoader,type Loader} from './loader-engine';
import './document-loader.css';
import {ProcessingCard,type ProcessingProgress} from './processing-card';
import {shownProgress} from './reading-model';
export function DocumentLoader({running,onStage,onFinished,handle,ceiling,rows,state,idle,footer}:{running:boolean;onStage?:(i:number,title:string,line:string)=>void;onFinished?:()=>void;handle:MutableRefObject<Loader|null>;ceiling:number;rows:string;state:string;idle:[string,string];footer:string}){
 const [progress,setProgress]=useState<ProcessingProgress>({value:0,rows:'',status:'preparando'});
 const engine=useRef<Loader|null>(null);
 const host=useRef<HTMLDivElement>(null),callbacks=useRef({onStage,onFinished});callbacks.current={onStage,onFinished};
 useEffect(()=>{if(!host.current)return;const loader=mountLoader(host.current,{auto:false,debug:false,externalProgress:true,onProgress:setProgress,files:[],onStage:(i,t,s)=>callbacks.current.onStage?.(i,t,s),onFinished:()=>callbacks.current.onFinished?.()});engine.current=loader;handle.current=loader;return()=>{loader.dispose();engine.current=null;if(handle.current===loader)handle.current=null;};},[handle]);
 return <ProcessingCard running={running} progress={{value:shownProgress(progress.value,ceiling),rows,status:progress.status}} state={state} idle={idle} footer={footer} engine={progress.value} ceiling={ceiling}><div className="document-loader" ref={host}/></ProcessingCard>;
}
