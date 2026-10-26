import {useEffect,useState,type ReactNode} from 'react';
import {apiFetch} from './api';
type Item={gid?:string;id:string;name:string;status:string;attention_required?:boolean;attention_reasons?:{message:string}[];needs_review?:boolean;export_status?:string};
type Group={id:string;name:string;project_id:string;kind:string;paused:boolean;started_at?:string;created_at:string;items:Item[]};
type Overview={groups:Group[];standalone:{status:string}[]};
const ACTIVE=['running','preparing','generating','processing','validating','exporting'],WAIT=['queued','paused','pausing','draft'];
const bucket=(i:Item)=>i.attention_required||['needs_attention','failed','blocked','cancelled'].includes(i.status)?'attention':['completed','exported'].includes(i.status)?'done':ACTIVE.includes(i.status)?'active':'waiting';
const COLORS:Record<string,string>={done:'var(--success)',active:'var(--info, #5aa9ff)',waiting:'var(--surface-3)',attention:'var(--warning, #f0a94b)'};
/** Project home: one-glance stats and overall progress instead of a second Create page. Reads the shared production read model; starts nothing. */
export function ProjectDashboard({projectId,projectName,assetCount,versionCount,approvedCount,assetCards,onNavigate,onOpenProduction,onQuickCreate,onNewAsset,diskFreeGb}:{projectId:string;projectName:string;assetCount:number;versionCount:number;approvedCount:number;assetCards:ReactNode;onNavigate:(page:string)=>void;onOpenProduction:(group:string,asset?:string)=>void;onQuickCreate:(prompt:string)=>void;onNewAsset:()=>void;diskFreeGb?:number}){
 const [data,setData]=useState<Overview|null>(null),[quick,setQuick]=useState('');
 useEffect(()=>{let alive=true;const load=async()=>{try{const r=await apiFetch('/api/production');if(r.ok&&alive)setData(await r.json());}catch{/* the cards below still render */}};void load();const t=setInterval(()=>void load(),4000);return()=>{alive=false;clearInterval(t);};},[projectId]);
 const groups=(data?.groups||[]).filter(g=>g.project_id===projectId);
 const items=groups.flatMap(g=>g.items.map(i=>({...i,gid:g.id})));
 const n={done:0,active:0,waiting:0,attention:0};for(const i of items)n[bucket(i) as keyof typeof n]++;
 const total=items.length,exported=items.filter(i=>i.export_status==='exported').length,review=items.filter(i=>i.needs_review).length;
 const attention=items.filter(i=>bucket(i)==='attention').slice(0,5);
 const kpi:[string,string|number,string][]=[['Assets',assetCount,'in this project'],['In production',n.active+n.waiting,`${n.active} running · ${n.waiting} waiting`],['Completed',n.done,total?`${Math.round(100*n.done/total)}% of ${total} planned`:'nothing planned yet'],['Delivered',exported,'files in your game folder'],['Needs attention',n.attention,n.attention?'open Production to fix':'all clear'],['Awaiting review',review,`${approvedCount} approved · ${versionCount} versions`]];
 return <div className="dash">
  <header className="dash-head"><div><div className="overline">{projectName} · dashboard</div><h2>Where things stand</h2></div>
   <form className="dash-quick" onSubmit={e=>{e.preventDefault();const p=quick.trim();if(!p)return;onQuickCreate(p);setQuick('');}}><input aria-label="Quick create prompt" value={quick} onChange={e=>setQuick(e.target.value)} placeholder="Quick create: describe an asset…"/><button className="primary" type="submit" disabled={!quick.trim()}>Start</button></form></header>
  <div className="dash-kpis">{kpi.map(([label,value,hint])=><div key={label} className="dash-kpi" data-warn={label==='Needs attention'&&n.attention>0}><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>)}</div>
  <section className="dash-card" aria-label="Overall progress"><header><h3>Overall progress</h3><button className="text-button" onClick={()=>onNavigate('Production')}>Production →</button></header>
   {total?<><div className="dash-bar" role="img" aria-label={`${n.done} of ${total} completed`}>{(['done','active','attention','waiting'] as const).map(k=>n[k]?<span key={k} style={{width:`${100*n[k]/total}%`,background:COLORS[k]}} title={`${k}: ${n[k]}`}/>:null)}</div>
    <div className="dash-legend">{(['done','active','attention','waiting'] as const).map(k=><span key={k}><i style={{background:COLORS[k]}}/>{({done:'Completed',active:'Running',attention:'Needs attention',waiting:'Waiting'})[k]} {n[k]}</span>)}</div></>
    :<p className="dash-empty">No production yet. Create an asset or import a batch and its progress shows here.</p>}</section>
  <div className="dash-cols">
   <section className="dash-card" aria-label="Runs and batches"><header><h3>Runs and batches</h3><button className="text-button" onClick={()=>onNavigate('Create')}>New →</button></header>
    {groups.length?groups.slice(0,6).map(g=>{const done=g.items.filter(i=>bucket(i)==='done').length,tot=g.items.length,active=g.items.some(i=>bucket(i)==='active');return <button key={g.id} className="dash-row" onClick={()=>onOpenProduction(g.id)}><span><strong>{g.name}</strong><small>{g.kind==='batch'?`${tot} assets`:'single asset'}{g.paused?' · paused':active?' · running':''}</small></span><span className="dash-mini" aria-label={`${done} of ${tot}`}><i style={{width:`${tot?100*done/tot:0}%`}}/></span><b>{done}/{tot}</b></button>;}):<p className="dash-empty">No runs yet.</p>}</section>
   <section className="dash-card" aria-label="Needs attention"><header><h3>Needs attention</h3><button className="text-button" onClick={()=>onNavigate('Library')}>Library →</button></header>
    {attention.length?attention.map(i=><button key={i.id} className="dash-row" onClick={()=>onOpenProduction(i.gid||'',i.id)}><span><strong>{i.name}</strong><small>{i.attention_reasons?.[0]?.message||i.status}</small></span></button>):<p className="dash-empty">All clear. Nothing failed or blocked.</p>}</section>
  </div>
  {diskFreeGb!==undefined&&<p className="dash-foot">Library disk: {diskFreeGb} GB free.</p>}
  <div className="collection-heading"><h2>Recent assets <span>{projectName}</span></h2><button className="text-button" onClick={()=>onNavigate('Library')}>View library →</button></div>
  {assetCount?<div className="asset-grid">{assetCards}</div>:<div className="studio-empty"><h3>A library built from your work.</h3><p>Add your first prompt or image to begin. This project has no assets yet.</p><button className="secondary" onClick={onNewAsset}>Create first asset</button></div>}
 </div>;
}
