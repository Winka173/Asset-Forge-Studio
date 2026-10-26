import {useCallback,useEffect,useRef,useState} from 'react';
import {apiFetch} from './api';
type Row={id:string;name:string;what:string;bytes:number;requires:string[];status:'installed'|'missing'|'queued'|'running'|'failed'|'cancelled'|'unknown';text:string;error:string;progress:number|null};
type Feature={id:string;name:string;note:string;available:boolean;needs:string[];missing_bytes:number;ready:boolean};
type Inventory={components:Row[];features:Feature[];running:boolean;error:string;bytes_done:number;missing_bytes:number;free_bytes:number;enough_space:boolean;all_installed:boolean};
const gb=(n:number)=>n>=1e9?`${(n/1e9).toFixed(1)} GB`:`${Math.round(n/1e6)} MB`;
const LABEL:Record<Row['status'],string>={installed:'Installed',missing:'Not installed',queued:'Waiting',running:'Installing',failed:'Needs attention',cancelled:'Stopped',unknown:'Checking'};
const KEY='afs.setup.features';
function saved():string[]{try{const v=JSON.parse(localStorage.getItem(KEY)||'null');return Array.isArray(v)?v:['models'];}catch{return ['models'];}}
/** Pick what you want to create; one button installs exactly the parts that need, with visible progress. banner = shown only while the chosen features are not ready. */
export function ComponentsSetup({banner=false}:{banner?:boolean}){
 const [inv,setInv]=useState<Inventory|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[picked,setPicked]=useState<string[]>(saved);
 const started=useRef<{at:number}|null>(null);
 const load=useCallback(async()=>{try{const r=await apiFetch('/api/components');if(!r.ok)throw Error('Cannot read the component list');setInv(await r.json());}catch(e){setError(String(e));}},[]);
 useEffect(()=>{void load();},[load]);
 useEffect(()=>{if(!inv?.running)return;const t=setInterval(()=>void load(),1500);return()=>clearInterval(t);},[inv?.running,load]);
 useEffect(()=>{try{localStorage.setItem(KEY,JSON.stringify(picked));}catch{}},[picked]);
 if(!inv)return error?<p role="alert">{error}</p>:null;
 const ids=Array.from(new Set(inv.features.filter(f=>picked.includes(f.id)&&f.available).flatMap(f=>f.needs)));
 const rows=inv.components.filter(r=>ids.includes(r.id)),others=inv.components.filter(r=>!ids.includes(r.id));
 const need=rows.filter(r=>r.status!=='installed'),missing=need.reduce((s,r)=>s+r.bytes,0),total=rows.reduce((s,r)=>s+r.bytes,0);
 const ready=need.length===0;
 if(banner&&ready)return null;
 async function install(){setBusy(true);setError('');try{const r=await apiFetch('/api/components/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});if(!r.ok)throw Error((await r.json().catch(()=>({detail:'Could not start'}))).detail);started.current={at:Date.now()};setInv(await r.json());}catch(e){setError(String(e));}finally{setBusy(false);}}
 async function cancel(){await apiFetch('/api/components/cancel',{method:'POST'});void load();}
 const pct=total?Math.max(0,Math.min(100,Math.round(100*(total-missing+Math.min(inv.bytes_done,missing))/total))):0;
 const seconds=started.current&&inv.running&&inv.bytes_done>5e7?(Date.now()-started.current.at)/1000:0,rate=seconds?inv.bytes_done/seconds:0,eta=rate?Math.round(Math.max(0,missing-inv.bytes_done)/rate/60):0;
 const space=inv.free_bytes>missing*1.1+5*2**30;
 const toggle=(id:string)=>setPicked(p=>p.includes(id)?p.filter(x=>x!==id):[...p,id]);
 const row=(r:Row)=><li key={r.id} data-status={r.status}>
   <div><strong>{r.name}</strong><small>{r.what} · {gb(r.bytes)}</small></div>
   <span className="components-state">{LABEL[r.status]}</span>
   {r.status==='running'&&<div className="components-bar"><span style={{width:r.progress==null?'30%':Math.round(r.progress*100)+'%'}} data-indeterminate={r.progress==null}/></div>}
   {(r.status==='running'||r.status==='cancelled')&&r.text&&<small className="components-text">{r.text}</small>}
   {r.error&&<small role="alert" className="components-text">{r.error}</small>}
  </li>;
 return <section className={`settings-panel components-setup${banner?' banner':''}`} aria-label="AI components setup">
  <h2>{ready?'Your chosen features are ready':'Set up what you want to create'}</h2>
  <p>Everything runs on your PC (no cloud, no fees). Tick what you want to create; only the parts it needs are downloaded. You can add more later.</p>
  <fieldset className="components-features" disabled={inv.running}><legend>I want to create</legend>
   {inv.features.map(f=><label key={f.id} className={f.available?'':'unavailable'}><input type="checkbox" checked={picked.includes(f.id)&&f.available} disabled={!f.available} onChange={()=>toggle(f.id)}/>
    <span><strong>{f.name}</strong><small>{!f.available?f.note:f.ready?'Ready':f.needs.length?`Needs ${gb(f.missing_bytes)} more`:'No download needed'}{f.available&&f.note?` · ${f.note}`:''}</small></span></label>)}
  </fieldset>
  <div className="components-actions">
   {!ready&&<button className="primary" disabled={busy||inv.running||!space||!ids.length} onClick={install}>{inv.running?'Installing…':need.some(r=>r.status==='failed'||r.status==='cancelled')?'Continue installation':`Download & install (${gb(missing)})`}</button>}
   {inv.running&&<button onClick={cancel}>Stop</button>}
   <span className="components-meta">Free disk: {gb(inv.free_bytes)}{inv.running&&eta>0?` · about ${eta>90?`${Math.round(eta/60)} h`:`${eta} min`} left`:''}</span>
  </div>
  {!space&&!ready&&<p role="alert">Not enough free disk space on the drive that holds your user folder (about {gb(missing*1.1+5*2**30)} needed).</p>}
  {inv.running&&<div className="components-total" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><span style={{width:pct+'%'}}/><b>{pct}%</b></div>}
  {(error||inv.error)&&<p role="alert">{error||inv.error}</p>}
  {rows.length>0&&<ul className="components-list">{rows.map(row)}</ul>}
  {others.length>0&&<details><summary>Other components ({others.length})</summary><ul className="components-list">{others.map(row)}</ul></details>}
 </section>;
}
