import {Download as IcDownload,ExternalLink as IcExternalLink,Flame as IcFlame} from "lucide-react";
import {useEffect,useState} from 'react';
import {apiUrl} from './api';
import {Select} from './select';
import {ErrorNotice} from './error-notice';
import {managementCall} from './asset-management';
type Sheet={id:string;name:string;url:string;metadata:{job_id?:string;columns:number;rows:number;frames:number;cell_px:number;playback_fps:number;preset:string;blending:string;loop:string}};
type Job={id:string;status:string;error?:string;progress?:{stage:string};payload:{effective_config:{preset:string;quality:string}}};
type Workspace={sheets:Sheet[];jobs:Job[]};
const busy=(j?:Job)=>Boolean(j&&!['REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED'].includes(j.status));

// Plays a sprite sheet by stepping the background position, so the preview shows the delivered file itself.
function SheetPlayer({sheet}:{sheet:Sheet}){
 const {columns,rows,frames,playback_fps}=sheet.metadata,[frame,setFrame]=useState(0);
 useEffect(()=>{const timer=setInterval(()=>setFrame(f=>(f+1)%frames),1000/Math.min(30,Math.max(4,playback_fps*2)));return()=>clearInterval(timer);},[frames,playback_fps]);
 const x=frame%columns,y=Math.floor(frame/columns);
 return <div className="fx-flipbook-player" role="img" aria-label={`Animated preview of ${sheet.name}`} style={{backgroundImage:`url(${apiUrl(sheet.url)})`,backgroundSize:`${columns*100}% ${rows*100}%`,backgroundPosition:`${columns>1?x/(columns-1)*100:0}% ${rows>1?y/(rows-1)*100:0}%`}}/>;
}

export function FlipbookPanel({projectId,onProduction}:{projectId:string;onProduction:(jobId:string)=>void}){
 const [prompt,setPrompt]=useState(''),[preset,setPreset]=useState('auto'),[look,setLook]=useState('stylized'),[quality,setQuality]=useState('Maximum'),[frames,setFrames]=useState(36),[cell,setCell]=useState(256),[tint,setTint]=useState(''),[assetId,setAssetId]=useState(''),[view,setView]=useState<Workspace|null>(null),[error,setError]=useState(''),[sending,setSending]=useState(false);
 useEffect(()=>{if(!assetId)return;let alive=true;const load=()=>managementCall<Workspace>(`/api/fx/flipbook/assets/${assetId}`).then(v=>{if(alive)setView(v);}).catch(e=>{if(alive)setError(String(e));});load();const timer=setInterval(load,4000);return()=>{alive=false;clearInterval(timer);};},[assetId]);
 const job=view?.jobs.at(-1),sheet=view?.sheets.at(-1);
 async function generate(){if(sending)return;setSending(true);setError('');try{const body={project_id:projectId,prompt,preset,look,quality,frames,cell,color:tint||null,asset_id:assetId||null},key='afs.fxflip.'+projectId,signature=JSON.stringify(body);let prior;try{prior=JSON.parse(localStorage.getItem(key)||'null');}catch{}const request_id=prior?.signature===signature?prior.id:crypto.randomUUID();localStorage.setItem(key,JSON.stringify({signature,id:request_id}));const result=await managementCall<{asset_id:string}>('/api/fx/flipbook',{...body,request_id});setAssetId(result.asset_id);}catch(e){setError(String(e));}finally{setSending(false);}}
 return <section className="fx-flipbook" aria-label="Simulated effect flipbook">
  <header><div className="overline">SIMULATED FLIPBOOK / BLENDER MANTAFLOW</div><h3>Fire, smoke &amp; explosions</h3><p>A real gas simulation rendered to a transparent sprite sheet for particle systems. Runs on the CPU, so it never waits for the GPU.</p></header>
  {error&&<ErrorNotice message={error} onDismiss={()=>setError('')}/>}
  <label className="studio-field">Describe the effect<textarea aria-label="Flipbook description" value={prompt} onChange={e=>setPrompt(e.target.value)} rows={2} placeholder="Campfire, chimney smoke, cannon explosion..."/></label>
  <div className="fx-flipbook-options">
   <label className="studio-field">Simulation<Select aria-label="Flipbook simulation" value={preset} onChange={e=>setPreset(e.target.value)}><option value="auto" data-description="Fire, smoke or explosion is picked from the description and recorded.">Let AI decide</option><option value="fire">Fire</option><option value="smoke">Smoke</option><option value="explosion">Explosion</option></Select></label>
   <label className="studio-field">Look<Select aria-label="Flipbook look" value={look} onChange={e=>setLook(e.target.value)}><option value="stylized" data-description="Flat cartoon colour bands and crisp edges, for stylized or low-poly games.">Stylized</option><option value="realistic" data-description="Soft volumetric smoke and fire.">Realistic</option></Select></label>
   <label className="studio-field">Quality<Select aria-label="Flipbook quality" value={quality} onChange={e=>setQuality(e.target.value)}><option value="Maximum" data-description="128-voxel simulation. Roughly 15-40 minutes on the CPU.">Maximum</option><option value="Balanced" data-description="96-voxel simulation.">Balanced</option><option value="Fast" data-description="64-voxel simulation, for quick tests.">Fast</option></Select></label>
   <label className="studio-field">Frames<Select aria-label="Flipbook frames" value={frames} onChange={e=>setFrames(Number(e.target.value))}>{[16,36,64].map(n=><option key={n} value={n}>{n} frames</option>)}</Select></label>
   <label className="studio-field">Frame size<Select aria-label="Flipbook frame size" value={cell} onChange={e=>setCell(Number(e.target.value))}>{[128,256,512].map(n=><option key={n} value={n}>{n} px</option>)}</Select></label>
   <label className="studio-field">Tint<span><input type="checkbox" checked={Boolean(tint)} onChange={e=>setTint(e.target.checked?'#7a5cff':'')}/> Coloured (magic) flame or smoke {tint&&<input type="color" aria-label="Flipbook tint" value={tint} onChange={e=>setTint(e.target.value)}/>}</span></label>
  </div>
  <button className="primary" disabled={sending||busy(job)} onClick={generate}><IcFlame size={15} aria-hidden="true"/>{sending?'Queuing...':busy(job)?'Simulating...':'Generate flipbook'}</button>
  {job&&<p role="status" className="fx-job-status">{job.status==='REVIEW_REQUIRED'?'Simulation and render checks passed. Not an artistic approval.':job.error||job.progress?.stage||job.status} <button className="quiet-button" onClick={()=>onProduction(job.id)}><IcExternalLink size={14} aria-hidden="true"/>Production</button></p>}
  {sheet&&<div className="fx-flipbook-result"><SheetPlayer sheet={sheet}/><div><p>{sheet.metadata.frames} frames, {sheet.metadata.columns}x{sheet.metadata.rows} grid, {sheet.metadata.cell_px} px each, {sheet.metadata.playback_fps} fps. {sheet.metadata.blending}; {sheet.metadata.loop}.</p><a className="quiet-button" href={apiUrl(sheet.url)} download={sheet.name+'.png'}><IcDownload size={14} aria-hidden="true"/>Download sprite sheet</a></div></div>}
 </section>;
}
