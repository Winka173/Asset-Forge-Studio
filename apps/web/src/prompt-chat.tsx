import {useEffect,useRef,useState} from 'react';
import {MessageSquareText as IcChat,SendHorizontal as IcSend,X as IcX} from 'lucide-react';
import {managementCall,type ManagedArtifact,type ManagedAsset} from './asset-management';
import './prompt-chat.css';

// Floating "keep prompting" panel on the 3D canvas: every message is a revision of the shown model (same revision API as
// Refine), and the revision history reads as the conversation. Originals and delivered versions stay untouched.
type Note={at:number;text:string};
const DONE=['staged','published','failed','cancelled','skipped','blocked','needs_attention'];
const SUGGEST=['Add water inside','Make roof navy','Uniformly scale to height 6 m'];

function reply(r:NonNullable<ManagedAsset['revisions']>[number]){
  if(r.state==='staged')return `v${r.number} is ready as a staged version. Preview it, then use it from Log when you like it.`;
  if(r.state==='published')return `v${r.number} is ready and in use.`;
  if(['failed','blocked','needs_attention'].includes(r.state))return `v${r.number} did not finish. ${(r as {error?:string}).error||'Log has the details.'}`;
  if(r.state==='cancelled'||r.state==='skipped')return `v${r.number} was cancelled.`;
  return `Working on v${r.number}… ${r.plan.explanation}`;
}

export function PromptChat({asset,artifacts,currentArtifactId,onSelectVersion,onChanged}:{asset:ManagedAsset;artifacts:ManagedArtifact[];currentArtifactId?:string;onSelectVersion?:(id:string)=>void;onChanged:()=>Promise<void>|void}){
  const [open,setOpen]=useState(()=>{try{return localStorage.getItem('afs.prompt-chat')==='open';}catch{return false;}});
  const [text,setText]=useState('');const [busy,setBusy]=useState(false);const [notes,setNotes]=useState<Note[]>([]);
  const list=useRef<HTMLDivElement>(null);const changed=useRef(onChanged);changed.current=onChanged;
  const candidates=artifacts.filter(a=>a.role==='candidate');
  const parent=candidates.find(a=>a.id===currentArtifactId)||candidates[candidates.length-1];
  const revisions=asset.revisions||[];const working=revisions.some(r=>!DONE.includes(r.state));
  useEffect(()=>{try{localStorage.setItem('afs.prompt-chat',open?'open':'closed');}catch{}},[open]);
  useEffect(()=>{list.current?.scrollTo({top:list.current.scrollHeight});},[open,revisions.length,notes.length,revisions.map(r=>r.state).join()]);
  // Follow running revisions while the panel is open.
  useEffect(()=>{if(!open||!working)return;const t=setInterval(()=>{Promise.resolve(changed.current()).catch(()=>{});},6000);return()=>clearInterval(t);},[open,working]);
  async function send(){
    const prompt=text.trim();if(!prompt||!parent||busy)return;setBusy(true);
    try{
      const body={parent_artifact_id:parent.id,prompt,method:'auto',priority:'next',request_id:crypto.randomUUID(),cancel_current:false,auto_replace:false};
      await managementCall(`/api/production/assets/${asset.id}/revisions`,body);setText('');await onChanged();
    }catch(e){setNotes(n=>[...n,{at:Date.now(),text:prompt+'\n→ '+String(e).replace(/^Error: /,'')}]);}
    finally{setBusy(false);}
  }
  if(!open)return <button className="prompt-chat-fab" title="Keep prompting on this model" aria-label="Open prompt chat" onClick={()=>setOpen(true)}><IcChat size={20} aria-hidden="true"/>{working&&<span className="prompt-chat-dot" aria-label="A revision is running"/>}</button>;
  return <section className="prompt-chat" aria-label="Prompt chat">
    <header><strong>Prompt on this model</strong><small>{parent?`From ${parent.name}`:'No model yet'}</small><button aria-label="Close prompt chat" onClick={()=>setOpen(false)}><IcX size={16} aria-hidden="true"/></button></header>
    <div className="prompt-chat-list" ref={list}>
      <div className="prompt-chat-msg user original" title={asset.original_prompt??asset.prompt}>{asset.original_prompt??asset.prompt}</div>
      {revisions.map(r=><div key={r.id} className="prompt-chat-pair"><div className="prompt-chat-msg user">{r.prompt}</div>
        <div className={`prompt-chat-msg ai state-${r.state}`}>{reply(r)}{r.artifact_id&&<button onClick={()=>onSelectVersion?.(r.artifact_id!)}>Preview v{r.number}</button>}</div></div>)}
      {notes.map(n=><div key={n.at} className="prompt-chat-msg ai error" role="alert">{n.text}</div>)}
      {!revisions.length&&!notes.length&&<p className="prompt-chat-hint">Describe a change. Water, roof colour, scale and clip speed are edited in Blender; other changes make a new version with AI. The current version stays saved.</p>}
    </div>
    <div className="prompt-chat-suggest">{SUGGEST.map(s=><button key={s} disabled={busy} onClick={()=>setText(s)}>{s}</button>)}</div>
    <div className="prompt-chat-input"><textarea aria-label="Prompt chat message" rows={2} maxLength={10000} value={text} disabled={!parent} placeholder={parent?'Type a change… (Enter to send)':'Waiting for the first model'} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}}}/>
      <button className="primary" aria-label="Send" disabled={busy||!text.trim()||!parent} onClick={send}><IcSend size={16} aria-hidden="true"/></button></div>
  </section>;
}
