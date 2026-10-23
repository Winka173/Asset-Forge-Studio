import {AnimatePresence,motion} from 'motion/react';
import {useEffect, useState} from 'react';
import {createPortal} from 'react-dom';
import {apiFetch,apiUrl} from './api';
import {isDesktop} from './desktop';

function toastStack(){let stack=document.getElementById('afs-toast-stack');if(!stack){stack=document.createElement('div');stack.id='afs-toast-stack';stack.className='afs-toast-stack';document.body.appendChild(stack);}return stack;}
export function ToastNotice({message,onDismiss}:{message:string;onDismiss:()=>void}) {
  useEffect(()=>{if(!message)return;const timer=setTimeout(onDismiss,6500);return()=>clearTimeout(timer);},[message]);
  return createPortal(<AnimatePresence>{message&&<motion.div key={message} className="afs-toast" role="status" layout initial={{opacity:0,y:16,scale:0.97}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,x:48,transition:{duration:0.18}}} transition={{type:'spring',stiffness:420,damping:32}} drag="x" dragConstraints={{left:0,right:0}} dragElastic={0.6} onDragEnd={(_event,info)=>{if(Math.abs(info.offset.x)>90)onDismiss();}}><span className="afs-toast-check" aria-hidden="true">✓</span><span>{message}</span><button aria-label="Dismiss notification" onClick={onDismiss}>×</button></motion.div>}</AnimatePresence>,toastStack());
}
type ExportResult={export_directory:string;delivery_scope?:string;files:{name:string;bytes:number;url:string}[]};
export function AssetExportAction({assetId,artifactId,onChanged}:{assetId:string;artifactId?:string;onChanged?:()=>void}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<ExportResult|null>(null);
  useEffect(()=>{setResult(null);setError('');},[assetId,artifactId]);
  async function exportModel(){setBusy(true);setError('');try{const response=await apiFetch(`/api/export-profiles/assets/${assetId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({artifact_id:artifactId})});const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:`Export failed (${response.status})`);if(!value.files?.length)throw Error('Export returned no files.');setResult(value);onChanged?.();}catch(e){setError(String(e));}finally{setBusy(false);}}
  return <div className="afs-quick-export"><button className="primary afs-export-button" disabled={busy||!artifactId} onClick={exportModel} title={artifactId?'Export this version using your saved project profile. No AI generation.':'A completed model is required before export.'}>{busy?<span className="afs-busy-spinner" aria-hidden="true"/>:<span aria-hidden="true">↓</span>}{busy?'Exporting…':'Export model'}</button><small>{artifactId?'Selected version · saved project profile':'Available when a model is ready'}</small>{error&&<p role="alert" className="form-error">{error}</p>}{result&&<details open className="afs-export-receipt"><summary>{result.delivery_scope==='staged'?'Revision saved separately':'Exported files'}</summary>{result.files.map(f=><a key={f.name} href={apiUrl(f.url)} download={f.name}>{f.name} · {(f.bytes/1048576).toFixed(1)} MB</a>)}<small>{result.export_directory}</small>{isDesktop()&&<button onClick={()=>window.__TAURI__!.core.invoke('desktop_open_export_directory',{path:result.export_directory}).catch(e=>setError(String(e)))}>Open folder</button>}</details>}</div>;
}
