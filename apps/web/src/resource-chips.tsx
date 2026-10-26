import {useEffect,useLayoutEffect,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {isDesktop,openDesktopFolder} from './desktop';
export type Host={ram_used_gib:number;ram_total_gib:number;ram_available_gib:number;cpu_percent:number;disk_free_gib:number;disk_total_gib:number};
export type Gpu={available:boolean;host?:Host;name?:string;used_mib?:number;total_mib?:number;utilization_percent?:number;sampled_at?:string;peak_mib?:number}|null;
type Id='gpu'|'ram'|'disk';
const gb=(mib=0)=>(mib/1024).toFixed(1);
/** Top-bar machine chips (VRAM, RAM, Disk). Every chip opens a details popover drawn in a portal, so nothing clips or covers it. */
export function ResourceChips({gpu}:{gpu:Gpu}){
 const [open,setOpen]=useState<Id|null>(null),[rect,setRect]=useState<DOMRect|null>(null);
 const refs=useRef<Record<string,HTMLButtonElement|null>>({}),panel=useRef<HTMLDivElement>(null);
 useLayoutEffect(()=>{setRect(open?refs.current[open]?.getBoundingClientRect()||null:null);},[open,gpu?.used_mib]);
 useEffect(()=>{
  if(!open)return;
  const close=(e:Event)=>{if(e instanceof KeyboardEvent){if(e.key==='Escape')setOpen(null);return;}const t=e.target as Node;if(panel.current?.contains(t)||refs.current[open]?.contains(t))return;setOpen(null);};
  const away=()=>setOpen(null);
  document.addEventListener('mousedown',close);document.addEventListener('keydown',close);window.addEventListener('resize',away);window.addEventListener('scroll',away,true);
  return()=>{document.removeEventListener('mousedown',close);document.removeEventListener('keydown',close);window.removeEventListener('resize',away);window.removeEventListener('scroll',away,true);};
 },[open]);
 const h=gpu?.host,ramWarn=!!h&&h.ram_available_gib<36,diskWarn=!!h&&h.disk_free_gib<50;
 const chip=(id:Id,label:string,warn:boolean,aria:string,cls='')=><button key={id} ref={el=>{refs.current[id]=el;}} className={`quiet-button res-chip ${cls}${warn?' warn':''}`} aria-expanded={open===id} aria-haspopup="dialog" aria-label={aria} onClick={()=>setOpen(v=>v===id?null:id)}><span className="live-dot"/><span className="res-text">{label}</span></button>;
 let body:ReactNode=null;
 if(open==='gpu')body=<><strong className="gpu-name" title={gpu?.name}>{gpu?.available?gpu.name?.replace('NVIDIA GeForce ',''):'GPU status unavailable'}</strong>
   {gpu?.available&&<div className="gpu-meter"><span style={{width:`${Math.min(100,((gpu.used_mib||0)/(gpu.total_mib||1))*100)}%`}}/><small>{gb(gpu.used_mib)} / {gb(gpu.total_mib)} GB VRAM</small></div>}
   {gpu?.available&&<div className="gpu-live-details" aria-label="Live GPU measurements" data-sampled-at={gpu.sampled_at} data-vram-mib={gpu.used_mib} data-utilization={gpu.utilization_percent}><small>GPU {gpu.utilization_percent?.toFixed(0)}% · peak {gb(gpu.peak_mib)} GB</small><small>Live · 2s sampling · whole GPU</small></div>}
   <small className="studio-version">Local inference only · weights &amp; assets stay on this PC</small></>;
 if(open==='ram'&&h)body=<><strong className="gpu-name">Memory</strong><div className="gpu-meter"><span style={{width:`${Math.min(100,(h.ram_used_gib/(h.ram_total_gib||1))*100)}%`}}/><small>{h.ram_used_gib} / {h.ram_total_gib} GB used · {h.ram_available_gib} GB free</small></div>
   <div className="gpu-live-details"><small>CPU load {Math.round(h.cpu_percent)}%</small></div>
   <small className="studio-version">{ramWarn?'Less than 36 GB free: a 3D (TRELLIS) stage may wait or page to disk.':'A 3D (TRELLIS) stage needs about 36 GB free.'}</small></>;
 if(open==='disk'&&h)body=<><strong className="gpu-name">Library disk</strong><div className="gpu-meter"><span style={{width:`${Math.min(100,((h.disk_total_gib-h.disk_free_gib)/(h.disk_total_gib||1))*100)}%`}}/><small>{h.disk_free_gib} GB free of {h.disk_total_gib} GB</small></div>
   <small className="studio-version">Each delivered asset keeps about 160 MB after working-file cleanup.{diskWarn?' Free space is low.':''}</small>
   {isDesktop()&&<button onClick={()=>openDesktopFolder('library').catch(()=>{})}>Open library folder</button>}</>;
 const style=rect?{top:rect.bottom+8,right:Math.max(8,window.innerWidth-rect.right)}:undefined;
 return <div className="res-chips" aria-label="Machine resources">
  {h&&chip('ram',`RAM ${h.ram_used_gib} / ${h.ram_total_gib} GB`,ramWarn,'Memory status')}
  {h&&chip('disk',`Disk ${h.disk_free_gib} GB free`,diskWarn,'Disk status')}
  {chip('gpu',gpu?.available?`VRAM ${gb(gpu.used_mib)} / ${gb(gpu.total_mib)} GB`:'GPU',false,'GPU status','gpu-chip')}
  {open&&body&&createPortal(<div ref={panel} className="gpu-popover res-popover" role="dialog" aria-label={open==='gpu'?'GPU details':open==='ram'?'Memory details':'Disk details'} style={style}>{body}</div>,document.body)}
 </div>;
}
