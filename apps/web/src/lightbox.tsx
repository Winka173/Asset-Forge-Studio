import {ChevronLeft as IcLeft,ChevronRight as IcRight,Download as IcDownload,X as IcX} from "lucide-react";
import {useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
type Shot={src:string;name:string};

// One app-wide image viewer: openImages([...], index) from any thumbnail.
export function openImages(images:Shot[],index=0){dispatchEvent(new CustomEvent('afs-open-images',{detail:{images,index}}));}

export function Lightbox(){
 const [state,setState]=useState<{images:Shot[];index:number}|null>(null);
 useEffect(()=>{const open=(e:Event)=>setState((e as CustomEvent<{images:Shot[];index:number}>).detail);addEventListener('afs-open-images',open);return()=>removeEventListener('afs-open-images',open);},[]);
 useEffect(()=>{if(!state)return;const key=(e:KeyboardEvent)=>{if(e.key==='Escape')setState(null);else if(e.key==='ArrowRight')setState(s=>s&&{...s,index:(s.index+1)%s.images.length});else if(e.key==='ArrowLeft')setState(s=>s&&{...s,index:(s.index-1+s.images.length)%s.images.length});};addEventListener('keydown',key);return()=>removeEventListener('keydown',key);},[state]);
 if(!state||!state.images.length)return null;
 const shot=state.images[state.index],many=state.images.length>1,step=(d:number)=>setState(s=>s&&{...s,index:(s.index+d+s.images.length)%s.images.length});
 return createPortal(<div className="lightbox" role="dialog" aria-modal="true" aria-label={shot.name} onMouseDown={e=>{if(e.target===e.currentTarget)setState(null);}}>
  <header><span>{shot.name}{many?` · ${state.index+1} / ${state.images.length}`:''}</span><a className="icon-button" href={shot.src} download title="Download image" aria-label="Download image"><IcDownload size={17} aria-hidden="true"/></a><button className="icon-button" onClick={()=>setState(null)} aria-label="Close" title="Close (Esc)"><IcX size={18} aria-hidden="true"/></button></header>
  {many&&<button className="lightbox-nav prev" onClick={()=>step(-1)} aria-label="Previous image"><IcLeft size={26} aria-hidden="true"/></button>}
  <img src={shot.src} alt={shot.name}/>
  {many&&<button className="lightbox-nav next" onClick={()=>step(1)} aria-label="Next image"><IcRight size={26} aria-hidden="true"/></button>}
 </div>,document.body);
}
