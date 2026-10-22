import {useEffect,useRef,useState} from 'react';
import {managementCall} from './asset-management';

type Checkpoint={available:boolean;reason?:string;resume_scope?:string;geometry?:{triangles:number;pbr_voxels:number}};
export function CheckpointRecovery({jobId,onQueued}:{jobId:string;onQueued:(jobId:string)=>void}){
 const [value,setValue]=useState<Checkpoint|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const request=useRef(crypto.randomUUID());
 useEffect(()=>{let alive=true;managementCall<Checkpoint>(`/api/production/jobs/${jobId}/native-checkpoint`).then(v=>{if(alive)setValue(v);}).catch(e=>{if(alive)setError(String(e));});return()=>{alive=false;};},[jobId]);
 if(!value?.available)return error?<p role="alert">{error}</p>:null;
 return <section className="native-checkpoint-recovery" aria-label="Native mesh checkpoint recovery"><strong>Your generated geometry is retained.</strong><p>{value.geometry?.triangles.toLocaleString()} native triangles and the original sparse PBR field are available.</p><p>Continue remesh, UV and GLB finishing using the same quality settings. Diffusion will not run again.</p><button className="primary" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const job=await managementCall<{id:string}>(`/api/production/jobs/${jobId}/resume-finishing`,{request_id:request.current});onQueued(job.id);}catch(e){setError(String(e));}finally{setBusy(false);}}}>{busy?'Restoring checkpoint…':'Resume model finishing'}</button><small>Uses the shared GPU queue. Original files are preserved. This resumes a completed stage boundary, not mid-inference.</small>{error&&<p role="alert">{error}</p>}</section>;
}
