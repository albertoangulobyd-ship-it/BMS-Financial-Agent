// El motor de la suricata de Aurora (components/ui/loader-engine.ts, entrega del 28-10-2026), tal
// cual: los mismos tiempos, estados, poses y drawImage por fotograma de los PNG aprobados
// (loader-sprites.ts), con imageSmoothingEnabled=false, image-rendering:pixelated y escalas
// enteras. Cambios (especificacion §4.2, C):
// - la escena se monta nodo a nodo (sin innerHTML);
// - nada en window (setLoaderStage, finishLoader, hideLoader): el modulo devuelve
//   {start,setStage,finish,hide,dispose}; hide es la de Aurora (fundido de 0,3 s y fuera);
// - sin los botones de depuracion (data-next, data-finish); la linea de depuracion (output) se
//   queda oculta, como con debug:false, y dice el estado del motor a las pruebas;
// - TypeScript estricto (los indices que no pueden faltar llevan !).
// La app no llama nunca a start() (pone auto=true y avanzaria solo): pide cada etapa con
// setStage y termina con finish cuando la lectura de verdad llega (especificacion §5.5).
import {sources} from './loader-sprites';
import {takeProcessingEntry} from './processing-entry';

export const CONFIG = {
  paths:sources, FPS:8, SCALE:3, mobileScale:2, walkSpeed:85, pileX:550, areaWidth:640,
  stages:5, DEBUG:true, frameWidth:76, frameHeight:47, anchorX:35, anchorY:41,
  lastFrameHold:120, longWait:6500, particleFall:1400, moundPause:220,
  durations:{'emerge-dig':[180,160,100,100,140,170,240,180],
    'emerge-search':[140,180,180,240,240,360,160,160],
    'moving-document':[220,150,180,260,300,180],
    'enter-burrow':[200,150,140,140,180,240],
    'found-cave':[220,180,150,160,180,300]}
};
const titles=['Cargando las facturas','Leyendo los datos','Comparando los expedientes','Analizando las coincidencias','Organizando los resultados'];
const subtitles=['Preparando las facturas de ejemplo.','Identificando referencias e importes.','Consultando los documentos existentes.','Separando las nuevas de las repetidas.','Guardando el resultado de la demostración.'];
type Sprite=keyof typeof sources;
export type LoaderOptions={externalProgress?:boolean;onProgress?:(progress:{value:number;rows:string;status:string})=>void;files?:string[];auto?:boolean;debug?:boolean;onStage?:(i:number,title:string,subtitle:string)=>void;onFinished?:()=>void};
type Job={sprite:Sprite;frames:number[];move?:number;loop?:boolean;hold?:number;done:()=>void};
export type Loader=ReturnType<typeof mountLoader>;

// C: la escena de Aurora (el mismo arbol, las mismas clases y los mismos textos), nodo a nodo.
function node<K extends keyof HTMLElementTagNameMap>(tag:K,className?:string,text?:string):HTMLElementTagNameMap[K]{
  const el=document.createElement(tag);if(className)el.className=className;if(text!==undefined)el.textContent=text;return el;
}
function scene(){
  const root=node('div','zur-loader'),stage=node('div','zur-stage');
  const world=node('canvas','zur-world'),pile=node('canvas','zur-pile');stage.append(world,pile);
  const text=node('div','zur-text');text.setAttribute('role','status');
  const title=node('p','zur-title','Preparando la animación'),sub=node('p','zur-sub','Cargando las imágenes…');text.append(title,sub);
  const reading=node('div','zur-reading');reading.hidden=true;
  const top=node('div','zur-reading-top');const percent=node('span','zur-percent','0%');top.append(node('span',undefined,'LECTURA SIMULADA'),percent);
  const progress=node('progress','zur-progress');progress.max=100;progress.value=0;progress.setAttribute('aria-label','Avance de la demostración');
  const log=node('pre','zur-file-log');log.setAttribute('aria-label','Archivos de ejemplo');reading.append(top,progress,log);
  const debugBox=node('div','zur-debug'),debug=node('output');debugBox.append(debug);
  root.append(stage,text,reading,debugBox);
  return {root,world,pile,title,sub,reading,progress,percent,log,debugBox,debug};
}

/** All character poses come from the approved raster sheets, never procedural drawings. */
export function mountLoader(host:HTMLElement, options:LoaderOptions={}) {
  const parts=scene();host.replaceChildren(parts.root);
  const root=parts.root;
  const entry=takeProcessingEntry();
  const world=parts.world, pile=parts.pile;
  const ctx=world.getContext('2d')!, pctx=pile.getContext('2d')!;
  const title=parts.title, sub=parts.sub, debug=parts.debug;
  parts.debugBox.hidden=!(options.debug??CONFIG.DEBUG);
  const reading=parts.reading;
  const progress=parts.progress;
  const percent=parts.percent;
  const log=parts.log;
  const files=options.files??Array.from({length:CONFIG.stages},(_,i)=>`factura${i+1}.pdf`);
  let lastReading='';
  const images={} as Record<Sprite,HTMLImageElement>;
  const mobile=matchMedia('(max-width:700px)'), reduced=matchMedia('(prefers-reduced-motion:reduce)');
  let scale=mobile.matches?CONFIG.mobileScale:CONFIG.SCALE, width=CONFIG.areaWidth, ground=41*scale, pileX=CONFIG.pileX;
  let x=CONFIG.areaWidth/2, facing=1, stage=-1, requested=0, count=0, ready=false, started=false, startRequested=false, finishing=false, ended=false, disposed=false;
  let raf=0,last=0,clock=0,elapsed=0,frame=0,waitSince=0,autoAt=Infinity,finalAt=Infinity,fadeAt=Infinity;
  let job:Job|null=null,hole:number|null=null,fall:{start:number,x:number,y:number}|null=null;
  let entrance=true;let positioned=false;
  const grains=Array.from({length:180},(_,i)=>{const angle=i*2.399963, radius=Math.sqrt((i+.5)/180);return {u:Math.cos(angle)*radius,v:Math.sin(angle)*radius,delay:(i%11)*24};});
  let action='preload'; const paperOffsets:number[]=[]; const labels=new Map<number,[string,string]>();
  const centerAtPile=()=>Math.min(width-39*scale-10,pileX-60);
  const randomLeft=()=>Math.round(33*scale+10+Math.random()*Math.max(1,Math.min(width*.34,centerAtPile()-80)-(33*scale+10)));
  const frames=(a:number,b:number)=>Array.from({length:b-a+1},(_,i)=>a+i-1);
  function layout(){
    const oldWidth=width;scale=mobile.matches?CONFIG.mobileScale:CONFIG.SCALE;
    width=Math.min(CONFIG.areaWidth,Math.max(240,host.clientWidth||CONFIG.areaWidth));ground=41*scale;
    pileX=Math.min(CONFIG.pileX,width-70);x=Math.max(110,Math.min(width-100,x*width/oldWidth));
    for(const c of [world,pile])c.style.width=width+'px';
    if(entry){const rect=world.getBoundingClientRect();ground=Math.max(41*scale,Math.round(entry.groundY-rect.top));if(!positioned){x=Math.max(33*scale+10,Math.min(width-39*scale-10,entry.centerX-rect.left));positioned=true;}}
    for(const c of [world,pile]){c.width=width;c.height=Math.max(47*scale,ground+6*scale);c.style.width=width+'px';c.style.height=c.height+'px';}
    ctx.imageSmoothingEnabled=pctx.imageSmoothingEnabled=false;
    // Resize resets canvas storage; restore the persistent pile from its immutable offsets.
    if(ready){paperOffsets.forEach((offset,i)=>paper(pctx,0,pileX+offset*scale,ground-i*2*scale));draw();}
  }
  function pose(name:Sprite,f:number,px=x,dir=facing){
    ctx.save();ctx.translate(Math.round(px),ground);ctx.scale(dir,1);
    ctx.drawImage(images[name],f*76,0,76,47,-35*scale,-41*scale,76*scale,47*scale);ctx.restore();
  }
  function paper(c:CanvasRenderingContext2D,f:number,px:number,py:number){
    // Use the full approved cell at an integer scale; its transparent margins preserve its anchor.
    const s=1;
    c.drawImage(images.Paper,f*76,0,76,47,Math.round(px-35*s),Math.round(py-41*s),76*s,47*s);
  }
  function draw(){if(!ready||disposed)return;
    reading.hidden=!started||!!options.externalProgress;
    if(started){
      const status=(fall||(job?.sprite==='moving-document'&&job.frames.length===1))?'guardando':action==='regresando con documento'?'comparando':action==='moving-document'?'leyendo':stage<0?'preparando':'buscando';
      const partial=stage>=0&&count<=stage?({buscando:2,leyendo:7,comparando:12,guardando:17,preparando:0}[status]):0;
      const value=Math.min(100,count*20+partial);
      const rows=files.slice(Math.max(0,count-2),Math.min(files.length,count+1)).map((name,j)=>{
        const i=Math.max(0,count-2)+j;return `${i<count?'✓':'>'} ${name.padEnd(22)} ${i<count?'listo':status+'…'}`;
      }).join('\n');
      const signature=value+'|'+rows;
      if(signature!==lastReading){progress.value=value;percent.textContent=value+'%';log.textContent=rows;lastReading=signature;options.onProgress?.({value,rows,status});}
    }
    ctx.clearRect(0,0,width,world.height);ctx.fillStyle='#fff';ctx.fillRect(10,ground,width-20,scale);
    if(hole!==null)pose('enter-burrow',5,hole,1);
    const current=job;
    if(entrance&&!reduced.matches){
      const landing=CONFIG.particleFall, digging=clock-landing-CONFIG.moundPause;
      if(digging<0){
        action=clock<landing?'partículas cayendo':'montículo formado';
        const rect=entry?world.getBoundingClientRect():null;
        const cloud=entry?.points.length?entry.points.map((p,i)=>({...grains[i%grains.length]!,source:p as {x:number;y:number}|null})):grains.map(g=>({...g,source:null}));
        for(const g of cloud){
          const t=Math.max(0,Math.min(1,(clock-180-g.delay)/900));
          // Ballistic vertical fall; horizontal drift decelerates. No orbital/swirl motion.
          const tx=x+g.u*11*scale, ty=ground-(1-Math.abs(g.u))*Math.abs(g.v)*7*scale;
          const sx=g.source&&rect?g.source.x-rect.left:entry&&rect?entry.centerX-rect.left+g.u*15*scale:x+g.u*15*scale;
          const sy=g.source&&rect?g.source.y-rect.top:entry&&rect?entry.centerY-rect.top+g.v*10*scale:ground-23*scale+g.v*10*scale;
          const px=sx+(tx-sx)*(1-(1-t)*(1-t));
          const py=sy+(ty-sy)*t*t;
          ctx.fillStyle='#fff';const size=Math.max(1,Math.round(scale/3));ctx.fillRect(Math.round(px),Math.round(py),size,size);
        }
      }else{
        action='asomando la cabeza';let time=digging, f=0;
        while(f<3&&time>=CONFIG.durations['emerge-dig'][f]!){time-=CONFIG.durations['emerge-dig'][f]!;f++;}
        if(digging>=CONFIG.durations['emerge-dig'].slice(0,4).reduce((a,b)=>a+b,0))pose('guard-head',0,x,1);else pose('emerge-dig',f,x,1);debug.textContent=`Entrada · ${action} · frame ${f+1}`;
        return;
      }
    }else if(!started){action='cabeza fuera del hoyo';pose('guard-head',reduced.matches?0:[0,1,0,4,0,7][Math.floor(clock/1200)%6]!,x,1);}
    else pose(reduced.matches?'emerge-search':current?.sprite??'emerge-search',reduced.matches?(started?5:1):current?.frames[frame]??(started?5:1));

    if(fall){const t=Math.min(1,(clock-fall.start)/250);paper(ctx,1,fall.x,fall.y+(ground-count*2*scale-fall.y)*t*t);}
    debug.textContent=`Etapa ${Math.max(0,stage)+1}/${CONFIG.stages} · ${action} · frame ${(current?.frames[frame]??(started?5:1))+1} · pila ${count}`;
  }
  function play(sprite:Sprite,fs:number[],done:()=>void,extra:Partial<Job>={}){job={sprite,frames:fs,done,...extra};frame=0;elapsed=0;action=sprite;}
  function walk(target:number,carrying:boolean,done:()=>void){facing=target<x?-1:1;play(carrying?'walking-documento':'emerge-search',carrying?frames(1,4):[6,7],done,{move:target,loop:true});action=carrying?'regresando con documento':'buscando otro documento';}
  function announce(i:number){const [t,s]=labels.get(i)??[titles[i]!,subtitles[i]!];title.textContent=t;sub.textContent=s;options.onStage?.(i,t,s);}
  function beginStage(i:number){stage=i;hole=null;fall=null;autoAt=Infinity;announce(i);
    if(reduced.matches){count=i+1;paperOffsets.push(0);paper(pctx,0,pileX,ground-i*2*scale);x=centerAtPile();waitSince=clock;job=null;autoAt=options.auto?clock+1000:Infinity;draw();return;}
    walk(randomLeft(),false,()=>{hole=x;facing=1;play('moving-document',frames(1,4),()=>walk(centerAtPile(),true,()=>{
      facing=1;play('moving-document',[4],()=>{job=null;action='soltando documento';fall={start:clock,x:pileX,y:ground-13*scale};},{hold:300});
    }));});
  }
  function peek(){facing=1;waitSince=clock;play('emerge-search',[5,4,5],()=>{}, {loop:true,hold:650});action='vigilando';}
  function inspectPile(){
    // Keep the full body above ground after releasing a page. Head-only frames
    // belong exclusively to an actual burrow entrance, never to a pile-side wait.
    const gestures=[[5,4,5],[5,6,7,6,4,5],[5,4,5,4,5]];
    play('emerge-search',gestures[(count-1)%gestures.length]!,()=>{peek();autoAt=options.auto?clock+700:Infinity;},{hold:240});
    action=count%3===2?'olfateando junto a la pila':'revisando la pila';
  }
  function deposited(){const offset=Math.round(Math.random()*2)-1;paperOffsets.push(offset);paper(pctx,0,pileX+offset*scale,ground-count*2*scale);count++;fall=null;
    // One native-pixel landing bounce, with a separately held final pose.
    pile.style.transform=`translateY(${-scale}px)`;pile.style.transition='transform 120ms ease-out';
    requestAnimationFrame(()=>{if(!disposed)pile.style.transform='translateY(0)';});
    inspectPile();
  }
  function variation(){autoAt=Infinity;walk(randomLeft(),false,()=>{hole=x;play('found-cave',frames(1,6),()=>play('emerge-search',frames(2,6),()=>walk(centerAtPile(),false,()=>{hole=null;peek();})));});}
  function final(){if(ended)return;ended=true;hole=null;fall=null;job=null;x=centerAtPile();facing=1;action='centinela';title.textContent='He finalizado con el análisis';sub.textContent='Todos los documentos están en su lugar.';finalAt=clock+1200;draw();}
  function update(dt:number){clock+=dt;
    if(entrance){
      const duration=CONFIG.particleFall+CONFIG.moundPause+CONFIG.durations['emerge-dig'].slice(0,4).reduce((a,b)=>a+b,0)+300+CONFIG.lastFrameHold;
      if(reduced.matches||clock>=duration){entrance=false;action=started?'saliendo':'cabeza fuera del hoyo';if(started)play('emerge-search',frames(3,6),()=>beginStage(0));}
      else return;
    }
    if(!started)return;
    if(ended){if(clock>=finalAt&&fadeAt===Infinity){root.style.opacity='0';fadeAt=clock+300;}if(clock>=fadeAt){dispose();root.remove();options.onFinished?.();}return;}
    if(fall){if(clock-fall.start>=250)deposited();return;}
    if(job){elapsed+=dt;const current=job;
      if(current.move!==undefined){const distance=CONFIG.walkSpeed*dt/1000;x+=Math.sign(current.move-x)*Math.min(Math.abs(current.move-x),distance);if(Math.abs(current.move-x)<.01){x=current.move;job=null;current.done();return;}}
      const times=(CONFIG.durations as Partial<Record<Sprite,number[]>>)[current.sprite];
      const duration=current.hold??((times?.[current.frames[frame]!]??125)*8/CONFIG.FPS);
      if(elapsed>=duration+(frame===current.frames.length-1&&!current.loop?CONFIG.lastFrameHold:0)){
        elapsed-=duration;frame++;if(frame>=current.frames.length){if(current.loop)frame=0;else{job=null;current.done();return;}}
      }
    }
    const waiting=action==='vigilando'||reduced.matches;
    if(waiting&&count>stage&&stage>=0){
      if(options.auto&&clock>=autoAt){requested=Math.min(CONFIG.stages-1,stage+1);if(stage===CONFIG.stages-1)finishing=true;}
      if(finishing&&count>=CONFIG.stages){final();return;}
      if(requested>stage||finishing){beginStage(stage+1);return;}
      if(!reduced.matches&&clock-waitSince>CONFIG.longWait)variation();
    }
  }
  function tick(now:number){if(disposed)return;const dt=last?Math.min(60,now-last):0;last=now;if(!document.hidden){update(dt);draw();}if(!disposed)raf=requestAnimationFrame(tick);}
  function start(){startRequested=true;if(started||!ready)return;started=true;title.textContent='Cargando las facturas';sub.textContent='La suricata está preparando su recorrido.';
    if(reduced.matches){beginStage(0);return;}
    if(!entrance)play('emerge-search',frames(3,6),()=>beginStage(0));
  }
  function setStage(i:number,t?:string,s?:string){if(!Number.isInteger(i)||i<0||i>=CONFIG.stages||ended)return;requested=Math.max(requested,i);if(t)labels.set(i,[t,s??'']);if(i===stage)announce(i);start();}
  function finish(){if(ended)return;finishing=true;requested=CONFIG.stages-1;start();}
  function hide(){root.style.opacity='0';window.setTimeout(()=>{dispose();root.remove();},300);}
  function dispose(){if(disposed)return;disposed=true;cancelAnimationFrame(raf);resize.disconnect();mobile.removeEventListener('change',layout);reduced.removeEventListener('change',motionChange);}
  function motionChange(){if(reduced.matches){entrance=false;job=null;fall=null;x=centerAtPile();facing=1;if(stage>=0&&count<=stage){paperOffsets.push(0);paper(pctx,0,pileX,ground-count*2*scale);count++;}action='centinela';autoAt=options.auto?clock+1000:Infinity;}else if(started&&!ended){if(stage<0)beginStage(0);else peek();}draw();}
  const resize=new ResizeObserver(layout);resize.observe(host);mobile.addEventListener('change',layout);reduced.addEventListener('change',motionChange);layout();
  Promise.all(Object.entries(CONFIG.paths).map(([name,path])=>new Promise<void>((resolve,reject)=>{const img=new Image();img.onload=()=>{images[name as Sprite]=img;resolve();};img.onerror=()=>reject(Error('No se pudo cargar '+name));img.src=path;}))).then(()=>{if(disposed)return;ready=true;layout();title.textContent='Todo empieza con una búsqueda';sub.textContent='Leer, comparar y ordenar, documento a documento.';draw();raf=requestAnimationFrame(tick);if(options.auto||startRequested)start();}).catch(error=>{if(!disposed){title.textContent='No se pudieron cargar las imágenes';sub.textContent=String(error);}});
  return {start:()=>{options.auto=true;start();},setStage,finish,hide,dispose};
}
