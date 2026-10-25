import {useEffect,useState} from 'react';
import {apiFetch} from './api';
type Requirement={id:string;kind:string;excerpt:string;target_m?:number};
type Report={summary:{measured:number;mismatches:number;unverified:number};checks:{requirement_id:string;status:string;evidence?:{expected_m:number;actual_m:number;tolerance_m:number}}[]};
type Result={contract:{asset_id:string;artifact_id?:string;requirements:Requirement[];coverage:string;source:string};report:Report|null;visual_evaluator:{available:boolean;reason:string}};
export function RequirementsPanel({assetId,artifactId}:{assetId:string;artifactId?:string}){
 const [value,setValue]=useState<Result|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[expanded,setExpanded]=useState(false);
 useEffect(()=>{let active=true;setValue(null);setError('');setExpanded(false);apiFetch(`/api/production/assets/${assetId}/requirements${artifactId?'?artifact_id='+encodeURIComponent(artifactId):''}`).then(async r=>{if(!r.ok)throw Error('Cannot load prompt requirements');const v=await r.json();if(active)setValue(v);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[assetId,artifactId]);
 async function measure(){if(!artifactId)return;setBusy(true);setError('');try{const response=await apiFetch(`/api/production/assets/${assetId}/requirements/evaluate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({artifact_id:artifactId})});const report=await response.json();if(!response.ok)throw Error(typeof report.detail==='string'?report.detail:'Model measurement failed');setValue(v=>v&&v.contract.asset_id===report.asset_id&&v.contract.artifact_id===report.artifact_id?{...v,report}:v);}catch(e){setError(String(e));}finally{setBusy(false);}}
 const count=value?.contract.requirements.length||0;
 return <details className="asset-requirements"><summary>Prompt requirements{value?count?value.report?` · ${value.report.summary.measured} measured · ${value.report.summary.unverified} not checked`:` · ${count} to check`:' · none to measure':''}</summary>
  {error&&<p role="alert" className="form-error">{error}</p>}{!value&&!error&&<p role="status">Reading the prompt…</p>}
  {value&&!count&&<p className="requirements-empty">Your prompt has no measurable requirements (for example sizes in metres), so there is nothing to check here. The full prompt is still kept.</p>}
  {value&&count>0&&<>{value.report?.summary.mismatches?<p role="status" className="form-error">{value.report.summary.mismatches} size mismatches. Check the measurements before using this version.</p>:null}
   <ul>{value.contract.requirements.slice(0,expanded?undefined:12).map(r=>{const check=value.report?.checks.find(c=>c.requirement_id===r.id);return <li key={r.id}><strong>{r.excerpt}</strong><span>{check?.status.replaceAll('_',' ')||'not checked yet'}</span>{check?.evidence&&<small>Measured {check.evidence.actual_m.toFixed(2)} m · asked {check.evidence.expected_m} m · tolerance {check.evidence.tolerance_m} m</small>}</li>;})}</ul>
   {count>12&&<button className="quiet-button" onClick={()=>setExpanded(!expanded)}>{expanded?'Show fewer':`Show all ${count}`}</button>}
   {artifactId?<button className="quiet-button" disabled={busy} onClick={measure}>{busy?'Measuring…':'Measure this model'}</button>:<small>Select a finished model above to measure it.</small>}</>}
 </details>;
}
