import {useEffect,useRef,useState} from 'react';
import {apiFetch,apiUrl} from './api';
type Job={id:string;status:string;error?:string;progress?:{stage:string}};
type State={supported:boolean;reason?:string;version:string;profile:string;jobs:Job[]};
type File={name:string;url:string;bytes:number};
async function call<T>(url:string,body?:unknown):Promise<T>{const r=await apiFetch(url,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:`Request failed (${r.status})`);return value;}
export function AnimationUnityPanel({assetId,artifactId}:{assetId:string;artifactId:string}){
 const [state,setState]=useState<State|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[files,setFiles]=useState<File[]>([]);const submitting=useRef(false);
 const path=`/api/platform/assets/${assetId}/animation-unity?artifact_id=${encodeURIComponent(artifactId)}`;
 const currentPath=useRef(path);currentPath.current=path;
 useEffect(()=>{let alive=true;setState(null);setError('');setBusy(false);submitting.current=false;const load=()=>call<State>(path).then(value=>{if(alive){setState(value);setError('');}}).catch(e=>{if(alive)setError(String(e));});load();const timer=setInterval(load,5000);return()=>{alive=false;clearInterval(timer);};},[path]);
 const job=state?.jobs[0],terminal=job&&['REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED'].includes(job.status);
 useEffect(()=>{let alive=true;setFiles([]);if(job?.status==='REVIEW_REQUIRED')call<File[]>(`/api/jobs/${job.id}/files`).then(value=>{if(alive)setFiles(value.filter(f=>f.name.startsWith('output/')));}).catch(e=>{if(alive)setError(String(e));});return()=>{alive=false;};},[job?.id,job?.status]);
 async function validate(){if(submitting.current)return;submitting.current=true;setBusy(true);setError('');try{const key=`afs.animation-unity.${assetId}.${artifactId}`;let previous:string|null=null;try{previous=localStorage.getItem(key);}catch{}const id=previous&&!terminal?previous:crypto.randomUUID();localStorage.setItem(key,id);await call(`/api/platform/assets/${assetId}/unity-import`,{artifact_id:artifactId,profile:'6000.4.8f1:Built-in:Animation',render_gpu:false,request_id:id});const value=await call<State>(path);if(currentPath.current===path)setState(value);}catch(e){if(currentPath.current===path)setError(String(e));}finally{if(currentPath.current===path){submitting.current=false;setBusy(false);}}}
 return <details className="asset-motion-refine animation-unity-panel"><summary>Unity animation package <span>{job?.status==='REVIEW_REQUIRED'?'Validated':job?.status||'Technical validation'}</span></summary><p>Existing single clip, untextured Generic rig. Checks real skin weights and motion, reopens the Editor, then imports the package into a clean project. Uses the shared CPU queue; your game folder is unchanged.</p>
 {!state&&!error&&<p role="status">Checking the selected clip and local tools…</p>}{state&&!state.supported&&<p role="status">Unavailable: {state.reason}</p>}
 <button className="primary" disabled={busy||!state?.supported||Boolean(job&&!terminal)} onClick={validate}>{busy?'Queueing validation…':job?'Revalidate animation in Unity':'Validate animation in Unity'}</button>
 {job&&<p role="status">{job.progress?.stage||job.status}{job.error?` / ${job.error}`:''}</p>}{files.filter(f=>/\.unitypackage$|\.json$/.test(f.name)).map(file=><p key={file.url}><a href={apiUrl(file.url)} download>{file.name.replace('output/','')} / {(file.bytes/1048576).toFixed(2)} MB</a></p>)}
 <p>Original GLB is retained. This does not generate motion, rig or retarget a character. Root motion, foot contact and artistic quality remain unreviewed.</p>{error&&<p role="alert">{error}</p>}</details>;
}
