import {useEffect,useState} from 'react';
import {apiFetch} from './api';
type Health={key:string;signature:{engine:string;version:string};circuit:string;status:string;root_cause?:string;remediation?:string;observations:{job_id:string;success:boolean;at:string}[]};
export function EngineHealthSettings(){
 const [rows,setRows]=useState<Health[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(''),[notice,setNotice]=useState('');
 async function refresh(){const r=await apiFetch('/api/engine-health');if(!r.ok)throw Error('Cannot read local engine health');setRows((await r.json()).records);}
 useEffect(()=>{refresh().catch(e=>setError(String(e)));},[]);
 async function probe(key:string){setBusy(key);setError('');setNotice('');try{const r=await apiFetch(`/api/engine-health/${key}/probe`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:crypto.randomUUID()})});if(!r.ok){const e=await r.json();throw Error(e.detail||'Probe could not be queued');}const job=await r.json();setNotice(`Smoke retry queued: ${job.id.slice(0,8)}. It uses the original stage settings and the shared scheduler; paused queues remain paused.`);await refresh();}catch(e){setError(String(e));}finally{setBusy('');}}
 return <section className="settings-panel engine-health" aria-label="Verified engine health"><h2>Engine health &amp; recovery</h2><p>Installation alone does not verify inference. Records apply to the exact engine, environment, driver and workflow profile. Checks do not download weights.</p>
  <button onClick={()=>refresh().catch(e=>setError(String(e)))}>Refresh health records</button>{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  {!rows.length&&<p>No execution evidence in this Library yet. Engines remain untested until a real job validates output.</p>}
  {rows.map(row=><details key={row.key}><summary>{row.signature.engine} · {row.status} · {row.circuit==='open'?'Route waiting for repair':row.circuit==='probing'?'Smoke probe queued':'No circuit hold'}</summary><p>{row.signature.version}</p>{row.root_cause&&<p>{row.root_cause.replaceAll('_',' ')}</p>}{row.remediation&&<p>{row.remediation}</p>}<small>{row.observations.length} recorded executions; content rejection does not quarantine other assets.</small>{row.circuit==='open'&&<><p>After fixing the environment, run one retry of the failed stage. This may use the GPU; resolution, steps and texture quality remain unchanged.</p><button className="primary" disabled={Boolean(busy)} onClick={()=>probe(row.key)}>Queue one smoke retry</button></>}</details>)}
 </section>;
}
