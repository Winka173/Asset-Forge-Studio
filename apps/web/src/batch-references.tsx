import {ToastNotice} from './workspace-feedback';
import {useEffect,useRef,useState} from 'react';
import {apiFetch,apiUrl} from './api';

type Reference={id:string;name:string;role:string;url:string};
type Props={projectId:string;assetId?:string;references:Reference[];selected:string[];onSelected:(ids:string[])=>void;onUploaded:(value:Reference)=>void;onBusy:(busy:boolean)=>void;disabled?:boolean;title:string;description:string};

/** Upload uses the same validated, project-scoped artifact endpoint as Single. */
export function BatchReferences({projectId,assetId,references,selected,onSelected,onUploaded,onBusy,disabled,title,description}:Props){
 const [uploading,setUploading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const owner=useRef(''),lock=useRef(false),selectedRef=useRef(selected);
 const scope=projectId+':'+(assetId||'batch');owner.current=scope;selectedRef.current=selected;
 useEffect(()=>{owner.current=scope;setError('');setNotice('');setUploading(false);lock.current=false;return()=>{owner.current='';onBusy(false);};},[scope,onBusy]);
 async function upload(files:File[]){
  if(lock.current||disabled)return;lock.current=true;setUploading(true);onBusy(true);setError('');setNotice('');
  const started=scope,failures:string[]=[];let count=0;
  try{for(const file of files){
   if(owner.current!==started)break;
   try{
    if(!/\.(png|jpe?g|webp)$/i.test(file.name))throw new Error('Only PNG, JPEG and WebP are supported.');
    if(file.size>512*1024*1024)throw new Error('Image exceeds the 512 MiB limit.');
    const data=new FormData();data.append('file',file);
    const response=await apiFetch(`/api/import/reference?project_id=${encodeURIComponent(projectId)}${assetId?'&asset_id='+encodeURIComponent(assetId):''}`,{method:'POST',body:data});
    if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(typeof body.detail==='string'?body.detail:`Upload failed (${response.status}).`);}
    const value:Reference=await response.json();
    if(owner.current!==started)break;
    onUploaded(value);const next=[...new Set([...selectedRef.current,value.id])];selectedRef.current=next;onSelected(next);count++;
   }catch(e){failures.push(`${file.name}: ${e instanceof Error?e.message:String(e)}`);}
  }}finally{if(owner.current===started){lock.current=false;setUploading(false);onBusy(false);setError(failures.join('\n'));if(count)setNotice(`Saved ${count} local images and selected them as the 3D source. Generation has not started.`);}}
 }
 const images=references.filter(ref=>['concept','reference','golden'].includes(ref.role));
 return <section className="batch-reference-upload" aria-label={title} aria-busy={uploading}>
  <div className="batch-reference-heading"><h3>{title}</h3><span>{selected.length} selected</span></div>
  <p>{description}</p>
  <label className="batch-import">{uploading?'Checking and saving images…':'＋ Add reference images'}<input aria-label={assetId?'Upload reference for this asset':'Upload batch reference images'} type="file" accept=".png,.jpg,.jpeg,.webp" multiple disabled={disabled||uploading} onChange={event=>{const files=Array.from(event.target.files||[]);event.target.value='';void upload(files);}}/></label>
  {error&&<p className="error-notice" role="alert">{error}</p>}<ToastNotice message={notice} onDismiss={()=>setNotice('')}/>
  {images.length>0?<details className="batch-reference-picker" open={selected.length>0}><summary>Project references ({images.length})</summary><div className="batch-reference-list">{images.map(ref=><label key={ref.id}><input type="checkbox" disabled={disabled||uploading} checked={selected.includes(ref.id)} onChange={event=>onSelected(event.target.checked?[...new Set([...selected,ref.id])]:selected.filter(id=>id!==ref.id))}/>{ref.role!=='golden'?<img src={apiUrl(ref.url)} alt="" loading="lazy"/>:<span aria-hidden="true">◇</span>}<span>{ref.name}{ref.role==='golden'&&<small>Golden GLB · comparison only, not an image-to-3D source</small>}</span></label>)}</div></details>:<small>No images yet. You can still analyze the prompt and create local concepts later.</small>}
 </section>;
}
