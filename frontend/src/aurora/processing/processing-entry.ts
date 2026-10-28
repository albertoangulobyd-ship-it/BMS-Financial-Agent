// processing-entry.ts de Aurora (components/ui/processing-entry.ts, entrega del 28-10-2026), tal
// cual: antes de entrar en Procesar se leen del lienzo del orbe de particulas los puntos con alfa
// > 0,14 (uno de cada 2 px, como mucho 350) y los sitios del saludo y del orbe; el motor de la
// suricata los toma una sola vez (takeProcessingEntry) para que las particulas caigan desde donde
// estaban. Las dos variables van a .app con setProperty (CSSOM: la CSP lo deja). Unico cambio (B):
// los sitios se cuentan desde main, que baja con las bandas del servidor.
type Entry={centerX:number;centerY:number;top:number;groundY:number;points:{x:number;y:number;alpha:number}[]};
let entry:Entry|null=null;
export function captureProcessingEntry(){
 const app=document.querySelector<HTMLElement>('.app');
 const canvas=app?.querySelector<HTMLCanvasElement>('.aurora .thinking-orb canvas');
 const title=app?.querySelector<HTMLElement>('.welcome-line');
 if(!app||!canvas||!title){entry=null;return;}
 const box=canvas.getBoundingClientRect(),heading=title.getBoundingClientRect();
 const points:Entry['points']=[];
 try{const ctx=canvas.getContext('2d'),data=ctx?.getImageData(0,0,canvas.width,canvas.height).data;
  if(data){for(let y=0;y<canvas.height;y+=2)for(let x=0;x<canvas.width;x+=2){const alpha=data[(y*canvas.width+x)*4+3]!/255;if(alpha>.14)points.push({x:box.left+x/canvas.width*box.width,y:box.top+y/canvas.height*box.height,alpha});}}
 }catch{/* The geometric fallback still starts at the original particle position. */}
 const stride=Math.max(1,Math.ceil(points.length/350));
 entry={centerX:box.left+box.width/2,centerY:box.top+box.height/2,top:box.top,groundY:box.top+box.height/2+80,points:points.filter((_,i)=>i%stride===0)};
 // B: con las bandas del servidor (datos de prueba, aislamiento), main ya baja lo que miden y el
 // saludo y la escena se colocan dentro de main: los sitios se cuentan desde main. Sin bandas,
 // main empieza en 0 y es lo de Aurora.
 const origin=(app.querySelector<HTMLElement>('main')?.getBoundingClientRect().top??0)+window.scrollY;
 app.style.setProperty('--process-heading-y',`${heading.top+window.scrollY-origin}px`);
 app.style.setProperty('--process-scene-y',`${box.top+window.scrollY-28-origin}px`);
}
export function takeProcessingEntry(){const captured=entry;entry=null;return captured;}
