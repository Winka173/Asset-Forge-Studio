import {useEffect,useState} from 'react';
import {apiFetch,apiUrl} from './api';
type Job={id:string;status:string;error?:string;payload:Record<string,unknown>};
type File={name:string;bytes:number;url:string};
async function call<T>(url:string,body?:unknown):Promise<T>{const r=await apiFetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;}

export function UnityImportPanel({assetId,artifactId,stage,jobs,onRefresh}:{assetId:string;artifactId:string;stage:string;jobs:Job[];onRefresh:()=>Promise<void>}){
 const [integration,setIntegration]=useState<{installed:boolean;version:string;render_pipeline:string}>();const [render,setRender]=useState(true);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [files,setFiles]=useState<File[]>([]);
 const job=jobs.find(j=>j.payload.kind==='unity_import'&&j.payload.asset_id===assetId&&j.payload.artifact_id===artifactId);
 const terminal=job&&['REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED'].includes(job.status);
 useEffect(()=>{call<{unity:typeof integration}>('/api/platform/integrations').then(d=>setIntegration(d.unity)).catch(e=>setError(String(e)));},[]);
 useEffect(()=>{setFiles([]);if(job?.status==='REVIEW_REQUIRED')call<File[]>(`/api/jobs/${job.id}/files`).then(f=>setFiles(f.filter(f=>f.name.startsWith('output/')))).catch(e=>setError(String(e)));},[job?.id,job?.status]);
 async function validate(){setBusy(true);setError('');try{const key=`afs.unity.${assetId}`;const fingerprint=JSON.stringify({artifactId,render});const prior=JSON.parse(localStorage.getItem(key)||'null');const requestId=prior?.fingerprint===fingerprint&&!terminal?prior.requestId:crypto.randomUUID();localStorage.setItem(key,JSON.stringify({fingerprint,requestId}));await call(`/api/platform/assets/${assetId}/unity-import`,{artifact_id:artifactId,request_id:requestId,render_gpu:render});await onRefresh();}catch(e){setError(String(e));}finally{setBusy(false);}}
 return <details className="asset-details advanced unity-import-panel"><summary>Unity native package & validation <span>{job?.status||'Experimental'}</span></summary>
 <p>Unity {integration?.version||'6000.4.8f1'} · {integration?.render_pipeline||'Built-in'}. Creates editable prefab, scene, materials, LODGroup and box collider in an isolated AFS project. Your game repository is not changed.</p>
 {stage!=='blender_processed'&&<p>Select a Blender processed LOD0 version first. Raw GLB and unsupported material profiles are blocked.</p>}
 {!integration?.installed&&<p>Pinned Editor or importer unavailable. No native package will be simulated.</p>}
 <label><input type="checkbox" checked={render} onChange={e=>setRender(e.target.checked)} disabled={busy||Boolean(job&&!terminal)}/> Render GPU previews through the shared scheduler</label>
 <button disabled={busy||!integration?.installed||stage!=='blender_processed'||Boolean(job&&!terminal)} onClick={validate}>{job?'Revalidate in Unity':'Validate in Unity'}</button>
 {job&&<p role="status">Native import: {job.status}{job.error?` · ${job.error}`:''}. Passing Editor checks does not establish artistic approval or game-ready performance.</p>}
 {files.filter(f=>/\.unitypackage$|\.zip$|\.json$/.test(f.name)).map(f=><p key={f.url}><a href={apiUrl(f.url)} download>{f.name.replace('output/','')} · {(f.bytes/1048576).toFixed(1)} MB</a></p>)}
 {files.some(f=>f.name.endsWith('.png'))&&<div style={{display:'grid',gridTemplateColumns:'repeat(3,minmax(0,1fr))',gap:8}}>{files.filter(f=>f.name.endsWith('.png')).map(f=><a key={f.url} href={apiUrl(f.url)} download><img src={apiUrl(f.url)} style={{width:'100%'}} alt={`Actual Unity Editor render ${f.name}`}/></a>)}</div>}
 <p>Commercial source/model/reference rights remain a separate gate. No normal, AO or emission maps are fabricated.</p>{error&&<p role="alert">{error}</p>}
 </details>;
}
