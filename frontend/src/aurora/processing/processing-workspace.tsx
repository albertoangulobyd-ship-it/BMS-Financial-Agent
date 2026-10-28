// ProcessingWorkspace de Aurora (components/processing-workspace.tsx, entrega del 28-10-2026): Procesar
// dentro del espacio central (processing-embedded), con la misma composicion, las mismas clases y
// los mismos movimientos: "Volver al inicio" arriba, la tarjeta con la escena de la suricata (una
// sola instancia del motor entre la intro y las etapas), y debajo la intro (el plan, el
// FlowButton y la nota), el paso de las etapas, el resultado o el error. Su titulo y su linea van
// al saludo (onViewChange, main.tsx:29). Cambios (especificacion §4.2 y §5):
// - D: la lectura de verdad. La pantalla consulta GET /api/v2/lectura cada 2 s mientras esta
//   abierta y manda tres ordenes (pedir_lectura, aprobar_lectura con la huella y el tope de lo
//   que se vio, cancelar_lectura); la app no lee ni lanza nada: lee el lector del escritorio.
//   El cuerpo de la suricata sale solo con un si aceptado por el servidor, cada fase de la pasada
//   pide su etapa (setStage) y el final (finish); lo que acaba mal se funde (hide). Las reglas, en
//   reading-model.ts; los textos de cada estado, en process-texts.ts;
// - D: el resultado son los documentos de la pasada (nueva, ya existia, posible duplicado, no se
//   pudo leer), cada uno lleva a su hoja en Documentos; "Ver en Documentos" (sin vuelo, F5) e
//   "Ir a la cola de trabajo" (F8);
// - B: "Volver al inicio" siempre (la lectura sigue, §7 punto 4); los botones de texto de la nota
//   ("No leer", "Parar la lectura"); el FlowButton guarda su sitio, oculto, cuando no hay nada que
//   pulsar (P1, P2, sin permiso);
// - I: los textos, del diccionario.
import {useCallback,useEffect,useMemo,useRef,useState,type KeyboardEvent as ReactKeyboardEvent} from 'react';
import {AnimatePresence,motion} from 'framer-motion';
import {ArrowLeft,ArrowUpRight,Check,Copy,FileText,ScanLine,ShieldCheck} from 'lucide-react';
import {fmt,useT} from '@/i18n';
import {ApiError,paths} from '@/lib/api';
import type {ReadingPassRow,ReadingStatus} from '@/lib/api-types';
import {useRefresh} from '@/lib/refresh';
import {useCan,useSession} from '@/lib/session';
import {DocumentLoader} from './document-loader';
import {FlowButton} from './flow-button';
import type {Loader} from './loader-engine';
import {cardState,completeNote,completeView,entryText,errorView,footerOf,idleLines,introView,readyNote,requestNote,rowTexts,stageLabel,type ProcessView} from './process-texts';
import {START,STAGES,afterHide,finished,outcomeOf,passOf,requested,rowsOf,update,type Command,type Drive} from './reading-model';
import './processing-workspace.css';

/** Las tres ordenes de la lectura (POST /api/v2/acciones, permiso importar_datos). Ninguna lee:
 *  lo hace el lector. aprobar_lectura es el si al coste de leer, con su tope; no aprueba ninguna
 *  factura ni ningun pago. */
const ORDERS = { request: { action: 'pedir_lectura' }, approve: { action: 'aprobar_lectura' }, cancel: { action: 'cancelar_lectura' } } as const;
/** Pedir, dar el si y parar, solo con este permiso (como la entrada de la rueda). */
const PERMISSION='importar_datos';
/** Lo que dura el fundido de la escena (hide, document-loader.css:2). */
const FADE_MS=300;

type Busy='request'|'start'|'cancel'|null;
type Notice='changed'|'sendFailed'|null;

export function ProcessingWorkspace({onBack,onViewChange,onDocuments,onQueue,onOpenInvoice,embedded=false}:{onBack:()=>void;onViewChange?:(view:ProcessView)=>void;onDocuments:()=>void;onQueue:()=>void;onOpenInvoice:(row:ReadingPassRow&{factura_id:number})=>void;embedded?:boolean}){
 const {t}=useT();const p=t.aurora.process;
 const {session}=useSession();const api=session?.api;const can=useCan();const allowed=can(PERMISSION);
 const {bump}=useRefresh();
 const [status,setStatus]=useState<ReadingStatus|null>(null);
 const [drive,setDriveState]=useState<Drive>(START);
 const [announced,setAnnounced]=useState<{i:number;title:string;line:string}|null>(null);
 const [busy,setBusy]=useState<Busy>(null);
 const [notice,setNotice]=useState<Notice>(null);
 const [orderError,setOrderError]=useState(false);
 const loader=useRef<Loader|null>(null);
 const statusRef=useRef<ReadingStatus|null>(null),driveRef=useRef<Drive>(START),approved=useRef<number|null>(null);
 const pending=useRef<Command[]>([]),hideTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
 const seq=useRef(0),applied=useRef(0);
 const texts=useRef(t);texts.current=t;
 const setDrive=useCallback((next:Drive)=>{driveRef.current=next;setDriveState(next);},[]);

 // Lo que se le pide al motor, en orden; si aun no esta montado, cuando lo este.
 const run=useCallback((commands:Command[])=>{
  for(const c of commands){
   const engine=loader.current;
   if(c.kind==='hide'){
    engine?.hide();clearTimeout(hideTimer.current);
    hideTimer.current=setTimeout(()=>{const next=afterHide(driveRef.current,statusRef.current);setDrive(next);setAnnounced(null);},FADE_MS);
    continue;
   }
   if(!engine){pending.current.push(c);continue;}
   if(c.kind==='stage'){const [title,line]=stageLabel(c.index,statusRef.current,texts.current);engine.setStage(c.index,title,line);}
   else engine.finish();
  }
 },[setDrive]);

 const apply=useCallback((next:ReadingStatus)=>{
  statusRef.current=next;setStatus(next);
  const before=driveRef.current;const {drive:after,commands}=update(before,next,approved.current);
  if(after!==before){
   if(after.screen!==before.screen)setNotice(null);
   if(after.body&&!before.body)setAnnounced(null);
   setDrive(after);
  }
  if(commands.length)run(commands);
 },[run,setDrive]);

 // GET /api/v2/lectura: la consulta de cada 2 s y la de despues de una orden; solo vale la ultima.
 const load=useCallback(()=>{
  if(!api)return Promise.resolve();
  const mine=++seq.current;
  return api.get<{lectura:ReadingStatus}>(paths.reading).then((r)=>{if(mine>applied.current){applied.current=mine;apply(r.lectura);}},()=>undefined);
 },[api,apply]);

 useEffect(()=>{
  let alive=true,timer:ReturnType<typeof setTimeout>|undefined;
  const tick=()=>{void load().then(()=>{if(alive)timer=setTimeout(tick,Math.max(1,statusRef.current?.consulta_cada_segundos??2)*1000);});};
  tick();
  return()=>{alive=false;clearTimeout(timer);clearTimeout(hideTimer.current);};
 },[load]);

 // Un motor nuevo (otra key): lo que se le pidio mientras no estaba.
 useEffect(()=>{const engine=loader.current;if(!engine||!pending.current.length)return;const queued=pending.current;pending.current=[];run(queued);},[drive.engine,drive.phase,run]);

 // Alt+<- y el boton "atras" del raton: la salida visible ("Volver al inicio").
 const back=useRef(onBack);back.current=onBack;
 useEffect(()=>{
  const onKey=(e:KeyboardEvent)=>{if(e.altKey&&!e.ctrlKey&&e.key==='ArrowLeft'){e.preventDefault();back.current();}};
  const onMouse=(e:MouseEvent)=>{if(e.button===3){e.preventDefault();back.current();}};
  window.addEventListener('keydown',onKey);window.addEventListener('mouseup',onMouse);
  return()=>{window.removeEventListener('keydown',onKey);window.removeEventListener('mouseup',onMouse);};
 },[]);

 async function requestReading(){
  if(!api||busy)return;setBusy('request');setOrderError(false);
  try{
   const r=await api.action(ORDERS.request.action,{});
   const id=Number((r.diferencia.detalle as {solicitud_id?:unknown}|undefined)?.solicitud_id);
   approved.current=null;setNotice(null);setAnnounced(null);
   if(Number.isSafeInteger(id)&&id>0)setDrive(requested(driveRef.current,id));
  }catch{setOrderError(true);}
  finally{setBusy(null);}
  void load();
 }

 async function start(){
  const s=statusRef.current?.solicitud;
  if(!api||busy||!s||s.estado!=='esperando_aprobacion')return;
  setBusy('start');
  try{
   await api.action(ORDERS.approve.action,{solicitud_id:s.id,huella_estimacion:s.huella_estimacion,tope_usd_micro:s.coste_max_usd_micro});
   // El servidor acepto el si: ahora sale el cuerpo (aunque la consulta aun no lo diga).
   approved.current=s.id;setNotice(null);
   if(statusRef.current)apply(statusRef.current);
  }catch(e){
   if(e instanceof ApiError&&e.code==='conflicto')setNotice('changed');
   else if(!(e instanceof ApiError)||e.kind==='unavailable'||e.kind==='invalid_response')setNotice('sendFailed');
  }finally{setBusy(null);}
  void load();
 }

 async function cancel(){
  const s=statusRef.current?.solicitud;
  if(!api||busy||!s)return;setBusy('cancel');setOrderError(false);
  try{await api.action(ORDERS.cancel.action,{solicitud_id:s.id});}catch{setOrderError(true);}
  finally{setBusy(null);}
  void load();
 }

 const onFinished=useCallback(()=>{setDrive(finished(driveRef.current));bump();},[setDrive,bump]);
 const onStage=useCallback((i:number,title:string,line:string)=>setAnnounced({i,title,line}),[]);

 const pass=status?passOf(status):null;
 const outcome=useMemo(()=>outcomeOf(pass),[pass]);
 const phase=drive.phase;
 const view:ProcessView=phase==='running'?(()=>{const [title,line]=announced?[announced.title,announced.line]:stageLabel(0,status,t);return {phase,title,detail:line};})():phase==='complete'?completeView(outcome,t):phase==='error'?errorView(status,t):introView(drive.screen,status,t,notice);
 const notify=useRef(onViewChange);notify.current=onViewChange;
 useEffect(()=>{notify.current?.(view);},[view.phase,view.title,view.detail,view.alert,view.properName]);

 // El boton de la intro: pedir (P0, P7, P8) o empezar (P3); en P1 y P2 guarda su sitio, oculto.
 const screen=drive.screen;
 const live=status?.solicitud?.viva??false;
 const askable=screen==='ready'||screen==='expired'||screen==='cancelled'||screen==='nothing';
 const button=screen==='waiting'?{text:p.start,onClick:start,busy:busy==='start'}:{text:p.request,onClick:requestReading,busy:busy==='request'};
 const hidden=!allowed||!(askable||screen==='waiting');
 const note:string[]=askable?readyNote(status,t,allowed):[requestNote(status,t)??''];
 const canStop=allowed&&live&&!status?.solicitud?.parar_pedido;
 const rows=rowsOf(pass,rowTexts(t));
 const open=(row:ReadingPassRow)=>{if(typeof row.factura_id==='number'&&row.factura_id>0)onOpenInvoice({...row,factura_id:row.factura_id});else onDocuments();};
 const keyOpen=(row:ReadingPassRow)=>(e:ReactKeyboardEvent)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(row);}};
 const done=completeNote(status,t);

 return <section className={'processing-workspace processing-'+phase+(embedded?' processing-embedded':'')} aria-label={p.label}><button className="processing-back" onClick={onBack}><ArrowLeft size={13}/>{p.back}</button><div className="processing-core">{(phase==='intro'||phase==='running')&&<DocumentLoader key={drive.engine} handle={loader} running={phase==='running'} onStage={onStage} onFinished={onFinished} ceiling={drive.ceiling} rows={rows} state={cardState(screen,phase==='running',t)} idle={idleLines(screen,t)} footer={footerOf(status,t)}/>}<AnimatePresence mode="wait" initial={false}>{phase==='intro'?<motion.div className="processing-intro" key="intro" initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-10}}><p className="processing-eyebrow">{p.eyebrow}</p><h1>{view.title}</h1><p className="processing-description">{view.detail}</p><div className="processing-plan"><span><ScanLine size={15}/> {p.plan.read}</span><i/><span><Copy size={15}/> {p.plan.compare}</span><i/><span><ShieldCheck size={15}/> {p.plan.analyze}</span></div><FlowButton text={button.text} onClick={()=>void button.onClick()} aria-busy={button.busy||undefined} aria-hidden={hidden||undefined} inert={hidden} style={hidden?{visibility:'hidden'}:undefined}/><p className="processing-demo">{note.map((line,i)=><span key={i}>{i>0&&<br/>}{line}</span>)}{allowed&&live&&!askable&&<> · <button type="button" className="processing-link" onClick={()=>void cancel()}>{p.notRead}</button></>}{orderError&&<span role="alert"><br/>{t.errors.unexpected}</span>}</p></motion.div>:phase==='running'?<motion.div key="running" className="processing-loading" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0,scale:.94}}><p className="processing-demo">{fmt(p.step,{n:(announced?.i??0)+1,total:STAGES})}{canStop?<> · <button type="button" className="processing-link" onClick={()=>void cancel()}>{p.stop}</button></>:status?.solicitud?.parar_pedido?<> · {p.stopping}</>:null}</p></motion.div>:phase==='complete'?<motion.div key="complete" className="processing-complete" initial={{opacity:0}} animate={{opacity:1}}><p className="processing-eyebrow">{p.complete.eyebrow}</p><h1>{p.complete.title}</h1><p className="processing-description">{view.detail}</p><div className="analysis-counts"><div className="analysis-new"><strong>{outcome.fresh}</strong><span>{p.complete.new}</span></div><span className="analysis-divider"/><div className="analysis-duplicate"><strong>{outcome.repeated}</strong><span>{p.complete.duplicate}</span></div>{outcome.failed>0&&<><span className="analysis-divider"/><div className="analysis-failed"><strong>{outcome.failed}</strong><span>{p.complete.failed}</span></div></>}</div><div className="analysis-report-list">{outcome.rows.map((e,i)=><a key={i+':'+e.nombre} className={'analysis-entry '+(e.estado==='nueva'?'new':e.estado==='fallida'?'failed':'duplicate')} role="link" tabIndex={0} onClick={()=>open(e)} onKeyDown={keyOpen(e)}><span className="analysis-entry-icon">{e.estado==='nueva'?<Check size={14}/>:e.estado==='fallida'?<FileText size={13}/>:<Copy size={13}/>}</span><span><strong data-proper-name="">{e.numero||e.nombre}</strong><small data-proper-name="">{e.empresa||e.nombre}</small></span><span className="analysis-entry-status">{entryText(e,t)}</span><ArrowUpRight size={13}/></a>)}</div><FlowButton text={p.documents} className="flow-success" onClick={onDocuments}/><p className="processing-demo">{done.map((line,i)=><span key={i}>{i>0&&<br/>}{line}</span>)}{outcome.fresh>0&&<> · <button type="button" className="processing-link" onClick={onQueue}>{p.queue}</button></>}</p></motion.div>:<motion.div key="error" initial={{opacity:0}} animate={{opacity:1}} className="processing-error"><FileText size={30}/><h1>{view.title}</h1><p role="alert">{view.detail}</p>{allowed&&<FlowButton text={p.again} onClick={()=>void requestReading()} aria-busy={busy==='request'||undefined}/>}</motion.div>}</AnimatePresence></div></section>;
}
