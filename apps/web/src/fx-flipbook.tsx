import {Download as IcDownload,ExternalLink as IcExternalLink,Flame as IcFlame} from "lucide-react";
import {useEffect,useState} from 'react';
import {apiUrl} from './api';
import {Select} from './select';
import {ErrorNotice} from './error-notice';
import {managementCall} from './asset-management';
type Sheet={id:string;role?:string;name:string;url:string;metadata:{size_m?:number;job_id?:string;columns:number;rows:number;frames:number;cell_px:number;playback_fps:number;preset:string;blending:string;loop:string}};
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

const TD_PACK=['arrow hit sparks','magic bolt impact, arcane magic','building collapse debris','dust impact when a unit lands','unit death smoke puff','gold coin pickup','tower upgrade level up rays','campfire','wall torch'];

// Seamless shader textures; a 2x2 tile preview shows the seams are invisible.
function TexturePanel({projectId}:{projectId:string}){
 const [kind,setKind]=useState('noise'),[size,setSize]=useState(1024),[items,setItems]=useState<{id:string;name:string;url:string}[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{managementCall<{id:string;name:string;url:string}[]>(`/api/fx/textures?project_id=${encodeURIComponent(projectId)}`).then(setItems).catch(()=>setItems([]));},[projectId]);
 async function make(){setBusy(true);setError('');try{const t=await managementCall<{id:string;name:string;url:string}>('/api/fx/textures',{project_id:projectId,kind,size,seed:Math.floor(Math.random()*100000)});setItems(old=>[t,...old.filter(o=>o.id!==t.id)]);}catch(e){setError(String(e));}finally{setBusy(false);}}
 return <details className="fx-flipbook-more"><summary>Tileable effect textures</summary>{error&&<ErrorNotice message={error} onDismiss={()=>setError('')}/>}<div className="fx-flipbook-options"><label className="studio-field">Type<Select aria-label="Texture type" value={kind} onChange={e=>setKind(e.target.value)}>{[['noise','Noise'],['flame_mask','Flame mask'],['dissolve','Dissolve'],['caustics','Caustics / water light'],['streaks','Streaks / wind'],['cells','Cells / cracks']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</Select></label><label className="studio-field">Size<Select aria-label="Texture size" value={size} onChange={e=>setSize(Number(e.target.value))}>{[512,1024,2048].map(n=><option key={n} value={n}>{n} px</option>)}</Select></label></div><button className="primary" disabled={busy} onClick={make}>{busy?'Making...':'Make texture'}</button><div className="fx-texture-grid">{items.slice(0,12).map(t=><a key={t.id} href={apiUrl(t.url)} download={t.name+'.png'} title={t.name}><span style={{backgroundImage:`url(${apiUrl(t.url)})`}}/><small>{t.name}</small></a>)}</div></details>;
}

// GLB mesh effects: shockwave ring (animated), shield bubble, ground crack decal, projectile trail.
function MeshEffectsPanel({projectId,onProduction}:{projectId:string;onProduction:(jobId:string)=>void}){
 const [kind,setKind]=useState('shockwave'),[colour,setColour]=useState('#ffb347'),[items,setItems]=useState<{id:string;name:string;url:string}[]>([]),[job,setJob]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const load=()=>managementCall<{id:string;name:string;url:string}[]>(`/api/fx/mesh?project_id=${encodeURIComponent(projectId)}`).then(setItems).catch(()=>setItems([]));
 useEffect(()=>{load();const timer=setInterval(load,6000);return()=>clearInterval(timer);},[projectId]);
 async function make(){setBusy(true);setError('');try{const out=await managementCall<{job:{id:string}}>('/api/fx/mesh',{project_id:projectId,kind,color:colour,seed:Math.floor(Math.random()*100000),request_id:'fxmesh-'+crypto.randomUUID()});setJob(out.job.id);}catch(e){setError(String(e));}finally{setBusy(false);}}
 return <details className="fx-flipbook-more"><summary>Mesh effects (GLB)</summary>{error&&<ErrorNotice message={error} onDismiss={()=>setError('')}/>}
  <p>Glowing, see-through meshes for the engine: the shockwave grows over 0.75 s; fading and texture scrolling are done by your shader.</p>
  <div className="fx-flipbook-options"><label className="studio-field">Effect<Select aria-label="Mesh effect" value={kind} onChange={e=>setKind(e.target.value)}><option value="shockwave">Shockwave ring</option><option value="shield">Shield bubble</option><option value="crack">Ground crack decal</option><option value="trail">Projectile trail</option></Select></label>
   <label className="studio-field">Colour<input type="color" aria-label="Mesh effect colour" value={colour} onChange={e=>setColour(e.target.value)}/></label></div>
  <button className="primary" disabled={busy} onClick={make}>{busy?'Queuing...':'Make mesh effect'}</button>{job&&<button className="quiet-button" onClick={()=>onProduction(job)}><IcExternalLink size={14} aria-hidden="true"/>Production</button>}
  {items.length>0&&<div className="fx-downloads">{items.slice(0,8).map(m=><a key={m.id} className="quiet-button" href={apiUrl(m.url)} download={m.name+'.glb'}><IcDownload size={14} aria-hidden="true"/>{m.name}</a>)}</div>}
 </details>;
}

export function FlipbookPanel({projectId,onProduction}:{projectId:string;onProduction:(jobId:string)=>void}){
 const [prompt,setPrompt]=useState(''),[preset,setPreset]=useState('auto'),[look,setLook]=useState('stylized'),[quality,setQuality]=useState('Maximum'),[frames,setFrames]=useState(36),[cell,setCell]=useState(256),[tint,setTint]=useState(''),[palette,setPalette]=useState(true),[assetId,setAssetId]=useState(''),[view,setView]=useState<Workspace|null>(null),[error,setError]=useState(''),[sending,setSending]=useState(false);
 useEffect(()=>{if(!assetId)return;let alive=true;const load=()=>managementCall<Workspace>(`/api/fx/flipbook/assets/${assetId}`).then(v=>{if(alive)setView(v);}).catch(e=>{if(alive)setError(String(e));});load();const timer=setInterval(load,4000);return()=>{alive=false;clearInterval(timer);};},[assetId]);
 const job=view?.jobs.at(-1),sheet=view?.sheets.filter(a=>a.role!=='fx_flipbook_meta').at(-1),meta=view?.sheets.find(a=>a.role==='fx_flipbook_meta'&&a.metadata.job_id===sheet?.metadata.job_id);
 const [list,setList]=useState(''),[queued,setQueued]=useState(0);
 async function many(lines:string[]){setSending(true);setError('');try{const out=await managementCall<unknown[]>('/api/fx/flipbook/batch',{project_id:projectId,lines,look,quality,frames,cell,match_palette:palette,request_id:'fxpack-'+crypto.randomUUID()});setQueued(out.length);}catch(e){setError(String(e));}finally{setSending(false);}}
 async function generate(){if(sending)return;setSending(true);setError('');try{const body={project_id:projectId,prompt,preset,look,quality,frames,cell,color:tint||null,match_palette:palette,asset_id:assetId||null},key='afs.fxflip.'+projectId,signature=JSON.stringify(body);let prior;try{prior=JSON.parse(localStorage.getItem(key)||'null');}catch{}const request_id=prior?.signature===signature?prior.id:crypto.randomUUID();localStorage.setItem(key,JSON.stringify({signature,id:request_id}));const result=await managementCall<{asset_id:string}>('/api/fx/flipbook',{...body,request_id});setAssetId(result.asset_id);}catch(e){setError(String(e));}finally{setSending(false);}}
 return <section className="fx-flipbook" aria-label="Simulated effect flipbook">
  <header><div className="overline">SIMULATED FLIPBOOK / BLENDER MANTAFLOW</div><h3>Fire, smoke &amp; explosions</h3><p>A real gas simulation rendered to a transparent sprite sheet for particle systems. Runs on the CPU, so it never waits for the GPU.</p></header>
  {error&&<ErrorNotice message={error} onDismiss={()=>setError('')}/>}
  <label className="studio-field">Describe the effect<textarea aria-label="Flipbook description" value={prompt} onChange={e=>setPrompt(e.target.value)} rows={2} placeholder="Campfire, chimney smoke, cannon explosion..."/></label>
  <div className="fx-flipbook-options">
   <label className="studio-field">Simulation<Select aria-label="Flipbook simulation" value={preset} onChange={e=>setPreset(e.target.value)}><option value="auto" data-description="Fire, smoke or explosion is picked from the description and recorded.">Let AI decide</option><option value="fire">Fire (loop)</option><option value="campfire">Campfire (loop)</option><option value="torch">Torch (loop)</option><option value="magic">Magic aura / portal (loop)</option><option value="smoke">Smoke (loop)</option><option value="steam">Steam (loop)</option><option value="poison">Poison gas (loop)</option><option value="explosion">Explosion</option><option value="dust">Dust impact</option><option value="sparks">Sparks / hit</option><option value="embers">Embers (loop)</option><option value="debris">Debris / collapse</option><option value="coins">Coin pickup</option><option value="levelup">Level-up rays</option></Select></label>
   <label className="studio-field">Look<Select aria-label="Flipbook look" value={look} onChange={e=>setLook(e.target.value)}><option value="stylized" data-description="Flat cartoon colour bands and crisp edges, for stylized or low-poly games.">Stylized</option><option value="realistic" data-description="Soft volumetric smoke and fire.">Realistic</option></Select></label>
   <label className="studio-field">Quality<Select aria-label="Flipbook quality" value={quality} onChange={e=>setQuality(e.target.value)}><option value="Maximum" data-description="128-voxel simulation. Roughly 15-40 minutes on the CPU.">Maximum</option><option value="Balanced" data-description="96-voxel simulation.">Balanced</option><option value="Fast" data-description="64-voxel simulation, for quick tests.">Fast</option></Select></label>
   <label className="studio-field">Frames<Select aria-label="Flipbook frames" value={frames} onChange={e=>setFrames(Number(e.target.value))}>{[16,36,64].map(n=><option key={n} value={n}>{n} frames</option>)}</Select></label>
   <label className="studio-field">Frame size<Select aria-label="Flipbook frame size" value={cell} onChange={e=>setCell(Number(e.target.value))}>{[128,256,512].map(n=><option key={n} value={n}>{n} px</option>)}</Select></label>
   <label className="studio-field">Project colours<span><input type="checkbox" checked={palette&&!tint} disabled={Boolean(tint)} onChange={e=>setPalette(e.target.checked)}/> Lean smoke and flame edges toward the game palette</span></label>
   <label className="studio-field">Tint<span><input type="checkbox" checked={Boolean(tint)} onChange={e=>setTint(e.target.checked?'#7a5cff':'')}/> Coloured (magic) flame or smoke {tint&&<input type="color" aria-label="Flipbook tint" value={tint} onChange={e=>setTint(e.target.value)}/>}</span></label>
  </div>
  <button className="primary" disabled={sending||busy(job)} onClick={generate}><IcFlame size={15} aria-hidden="true"/>{sending?'Queuing...':busy(job)?'Simulating...':'Generate flipbook'}</button>
  {job&&<p role="status" className="fx-job-status">{job.status==='REVIEW_REQUIRED'?'Simulation and render checks passed. Not an artistic approval.':job.error||job.progress?.stage||job.status} <button className="quiet-button" onClick={()=>onProduction(job.id)}><IcExternalLink size={14} aria-hidden="true"/>Production</button></p>}
  {sheet&&<div className="fx-flipbook-result"><div className="fx-scale"><SheetPlayer sheet={sheet}/>{sheet.metadata.size_m&&<div className="fx-scale-person" title="1.8 m person for scale" style={{height:`${Math.min(100,180/sheet.metadata.size_m)}%`}}/>}</div><div><p>{sheet.metadata.frames} frames, {sheet.metadata.columns}x{sheet.metadata.rows} grid, {sheet.metadata.cell_px} px each, {sheet.metadata.playback_fps} fps. {sheet.metadata.blending}; {sheet.metadata.loop}.</p><a className="quiet-button" href={apiUrl(sheet.url)} download={sheet.name+'.png'}><IcDownload size={14} aria-hidden="true"/>Download sprite sheet</a>{meta&&<a className="quiet-button" href={apiUrl(meta.url)} download={sheet.name+'.afsflipbook.json'}><IcDownload size={14} aria-hidden="true"/>Unity settings (.json)</a>}<a className="quiet-button" href={apiUrl('/api/fx/flipbook/unity-importer')} download="AFSFlipbookImporter.cs"><IcDownload size={14} aria-hidden="true"/>Unity prefab script</a><small>Put the script in an Editor folder; the PNG and its .json together make a Particle System prefab. Not yet tested in Unity.</small>{sheet.metadata.size_m&&<small>Effect is about {sheet.metadata.size_m} m across; the outline is a 1.8 m person.</small>}</div></div>}
  <details className="fx-flipbook-more"><summary>Effect pack &amp; many effects</summary>
   <p>Each line becomes its own effect (Stylized, project colours and the settings above). Runs on the CPU one after another.</p>
   <button className="primary" disabled={sending} onClick={()=>many(TD_PACK)}>Tower-defense pack · {TD_PACK.length} effects</button>
   <label className="studio-field">Or list your own, one per line<textarea aria-label="Effects list" rows={4} value={list} onChange={e=>setList(e.target.value)} placeholder={'arrow hit sparks\ngold coin pickup\ncastle collapse debris'}/></label>
   <button className="quiet-button" disabled={sending||!list.trim()} onClick={()=>many(list.split(/\r?\n/))}>Create these effects</button>
   {queued>0&&<p role="status" className="fx-job-status">{queued} effects queued. Follow them in Production.</p>}
  </details>
  <TexturePanel projectId={projectId}/>
  <MeshEffectsPanel projectId={projectId} onProduction={onProduction}/>
 </section>;
}
