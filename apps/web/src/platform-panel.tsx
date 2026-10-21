import { Select } from "./select";
import {useEffect,useState} from 'react';
import {apiFetch,apiUrl} from './api';

async function call<T>(url:string,body?:unknown):Promise<T>{
 const response=await apiFetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
 const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;
}
type Registry={asset_types:{id:string;label:string;status:string;reason:string}[];providers:{id:string;label:string;status:string;installed:boolean;inputs:string[];outputs:string[];license:{commercial:string};constraints:string[]}[]};
type Route={status:string;capability_gaps:string[];graph:{stages:{id:string;resource:string;expected_outputs:string[]}[]};estimated_heavy_gpu_jobs:number};

export function OutputContract({projectId,assetId,mode,prompt,source,engine,autoBlender}:{projectId:string;assetId?:string;mode:string;prompt:string;source?:string;engine:string;autoBlender:boolean}){
 const [registry,setRegistry]=useState<Registry>();const [output,setOutput]=useState('glb');const [result,setResult]=useState<Route>();const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [snapshot,setSnapshot]=useState<{url:string}>();
 useEffect(()=>{call<Registry>('/api/platform/capabilities').then(setRegistry).catch(e=>setError(String(e)));},[]);
 useEffect(()=>{setResult(undefined);setSnapshot(undefined);setError('');},[projectId,assetId,mode,prompt,source,engine,autoBlender,output]);
 async function preview(){setBusy(true);setError('');try{setResult(await call<Route>('/api/platform/route',{project_id:projectId,asset_type:'static_3d',input_mode:mode,prompt,reference_ids:source?[source]:[],engine,desired_outputs:output==='glb'?['glb']:['glb','fbx','lod'],auto_blender:autoBlender,policy:'Assisted'}));}catch(e){setError(String(e));}finally{setBusy(false);}}
 async function save(){setBusy(true);setError('');try{setSnapshot(await call<{url:string}>(`/api/platform/assets/${assetId}/manifest`,{}));}catch(e){setError(String(e));}finally{setBusy(false);}}
 return <details className="advanced output-contract"><summary>Output contract & readiness</summary>
  <label className="studio-field">Asset type<Select aria-label="Asset type" value="static_3d" disabled title="Additional types remain Planned until a real output and native import slice is verified">{(registry?.asset_types||[{id:'static_3d',label:'3D Model',status:'experimental'}]).map(t=><option key={t.id} value={t.id} disabled={t.id!=='static_3d'}>{t.label}{t.id!=='static_3d'?' · Planned':''}</option>)}</Select></label>
  <label className="studio-field">Expected output<Select aria-label="Requested output contract" value={output} onChange={e=>setOutput(e.target.value)}><option value="glb">3D model · GLB</option><option value="fbx_lod">GLB + FBX + LODs via Blender</option></Select></label>
  <p>Check the local route before spending GPU time. This preview submits no generation jobs; your quality settings stay unchanged.</p>
  <button disabled={busy} onClick={preview}>Check output route</button>
  {result&&<div role="status"><strong>{result.status==='blocked'?'Blocked · setup or review required':'Ready for review · no jobs submitted'}</strong><ol>{result.graph.stages.map(s=><li key={s.id}>{s.id} · {s.resource} → {s.expected_outputs.join(', ')}</li>)}</ol>{result.capability_gaps.map(g=><p key={g}>{g}</p>)}</div>}
  <button disabled={!assetId||busy} onClick={save}>Save manifest v2</button>{snapshot&&<a href={apiUrl(snapshot.url)} download>Download saved manifest</a>}
  {error&&<p role="alert">{error}</p>}
 </details>;
}

export function CapabilityRegistry(){
 const [data,setData]=useState<Registry>();const [error,setError]=useState('');
 useEffect(()=>{call<Registry>('/api/platform/capabilities').then(setData).catch(e=>setError(String(e)));},[]);
 return <section className="settings-panel"><div className="panel-heading"><h2>Output capabilities</h2></div><p>Installed tools, validated outputs and commercial rights are separate. Planned modules have no Generate action.</p>
 {data?.providers.map(p=><details className="advanced" key={p.id}><summary>{p.label} · {p.status}</summary><p>{p.inputs.join(', ')} → {p.outputs.join(', ')}</p><p>Commercial: {p.license.commercial}. {p.constraints.join('. ')}</p></details>)}
 <details className="advanced"><summary>Module readiness</summary>{data?.asset_types.map(t=><p key={t.id}><strong>{t.label} · {t.status}</strong><br/>{t.reason}</p>)}</details>{error&&<p role="alert">{error}</p>}</section>;
}
