import {useEffect,useRef,useState} from 'react';
import {MessageSquareText as IcChat,SendHorizontal as IcSend,X as IcX} from 'lucide-react';
import {managementCall,type ManagedArtifact,type ManagedAsset} from './asset-management';
import './prompt-chat.css';

// Floating "keep prompting" panel on the 3D canvas. Messages wait on the server; when the model is idle the local AI reads
// all waiting messages together (corrections, cancellations, taking a version back) and runs what remains, each change from
// the newest version. The revision history and those readings are the conversation; originals stay untouched.
type Revision=NonNullable<ManagedAsset['revisions']>[number];
const DONE=['staged','published','failed','cancelled','skipped','blocked','needs_attention'];
const SUGGEST=['Add water inside','Make roof navy','Uniformly scale to height 6 m'];

function reply(r:Revision){
  if(r.state==='staged')return `v${r.number} is ready. Preview it; use it from Log when you like it.`;
  if(r.state==='published')return `v${r.number} is ready and in use.`;
  if(['failed','blocked','needs_attention'].includes(r.state))return `v${r.number} did not finish. ${(r as {error?:string}).error||'Log has the details.'}`;
  if(r.state==='cancelled'||r.state==='skipped')return `v${r.number} was cancelled.`;
  return `Working on v${r.number}…`;
}

export function PromptChat({asset,artifacts,currentArtifactId,onSelectVersion,onChanged}:{asset:ManagedAsset;artifacts:ManagedArtifact[];currentArtifactId?:string;onSelectVersion?:(id:string)=>void;onChanged:()=>Promise<void>|void}){
  const [open,setOpen]=useState(()=>{try{return localStorage.getItem('afs.prompt-chat')==='open';}catch{return false;}});
  const [text,setText]=useState('');const [busy,setBusy]=useState(false);const [errors,setErrors]=useState<{at:number;text:string}[]>([]);
  const list=useRef<HTMLDivElement>(null);const changed=useRef(onChanged);changed.current=onChanged;
  const candidates=artifacts.filter(a=>a.role==='candidate');
  const parent=candidates.find(a=>a.id===currentArtifactId)||candidates[candidates.length-1];
  const revisions=asset.revisions||[];const queue=asset.chat_queue||[];const notes=asset.chat_notes||[];
  const waiting=queue.filter(q=>!q.merged);const planned=queue.filter(q=>q.merged);
  const running=revisions.some(r=>!DONE.includes(r.state));const working=queue.length>0||Boolean(asset.chat_reading)||running;
  const timeline=[...notes.map(n=>({at:n.at,note:n,revision:undefined})),...revisions.map(r=>({at:r.created_at,note:undefined,revision:r}))].sort((a,b)=>a.at.localeCompare(b.at));
  // Show the version the chat went back to; notes that existed when the panel mounted do not move the viewer.
  const seen=useRef(new Set(notes.map(n=>n.id+n.at)));
  useEffect(()=>{for(const n of notes){if(seen.current.has(n.id+n.at))continue;seen.current.add(n.id+n.at);if(n.reverted_to)onSelectVersion?.(n.reverted_to);}},[notes,onSelectVersion]);
  useEffect(()=>{try{localStorage.setItem('afs.prompt-chat',open?'open':'closed');}catch{}},[open]);
  useEffect(()=>{list.current?.scrollTo({top:list.current.scrollHeight});},[open,timeline.length,queue.length,errors.length,asset.chat_reading,revisions.map(r=>r.state).join()]);
  // Follow the chat while something is waiting or running.
  useEffect(()=>{if(!working)return;const t=setInterval(()=>{Promise.resolve(changed.current()).catch(()=>{});},open?4000:10000);return()=>clearInterval(t);},[open,working]);
  async function call(work:()=>Promise<unknown>,label:string){setBusy(true);try{await work();await onChanged();}catch(e){setErrors(x=>[...x,{at:Date.now(),text:label+'\n→ '+String(e).replace(/^Error: /,'')}]);}finally{setBusy(false);}}
  function send(){const prompt=text.trim();if(!prompt||!parent||busy)return;setText('');call(()=>managementCall(`/api/production/assets/${asset.id}/chat`,{parent_artifact_id:parent.id,prompt,request_id:crypto.randomUUID()}),prompt);}
  const remove=(id:string)=>call(()=>managementCall(`/api/production/assets/${asset.id}/chat/${id}/remove`,{}),'Remove');
  if(!open)return <button className="prompt-chat-fab" title="Keep prompting on this model" aria-label="Open prompt chat" onClick={()=>setOpen(true)}><IcChat size={20} aria-hidden="true"/>{working&&<span className="prompt-chat-dot" aria-label="A change is running"/>}</button>;
  return <section className="prompt-chat" aria-label="Prompt chat">
    <header><strong>Prompt on this model</strong><small>{parent?'Changes continue from the newest version':'No model yet'}</small><button aria-label="Close prompt chat" onClick={()=>setOpen(false)}><IcX size={16} aria-hidden="true"/></button></header>
    <div className="prompt-chat-list" ref={list}>
      <div className="prompt-chat-msg user original" title={asset.original_prompt??asset.prompt}>{asset.original_prompt??asset.prompt}</div>
      {timeline.map(({note,revision})=>note?<div key={'n'+note.id+note.at} className="prompt-chat-pair">{note.messages.length>0&&<div className="prompt-chat-msg user">{note.messages.join('\n')}</div>}
        <div className={`prompt-chat-msg ai${note.kind==='error'?' error':''}`}>{note.summary}{note.reverted_to&&<><br/>Back to v{note.reverted_to_version}{note.reverted_to_version===1?' (original)':''}.<button onClick={()=>onSelectVersion?.(note.reverted_to!)}>Preview v{note.reverted_to_version}</button></>}</div></div>
        :revision&&<div key={'r'+revision.id} className={`prompt-chat-msg ai state-${revision.state}`}><small className="prompt-chat-change">Change: {revision.prompt}</small>{reply(revision)}{revision.artifact_id&&<button onClick={()=>onSelectVersion?.(revision.artifact_id!)}>Preview v{revision.number}</button>}</div>)}
      {planned.map((q,n)=><div key={q.id} className="prompt-chat-msg ai state-waiting"><small className="prompt-chat-change">Next {n+1}: {q.prompt}</small>Starts when the change before it finishes.<button disabled={busy} onClick={()=>remove(q.id)}>Remove</button></div>)}
      {waiting.map(q=><div key={q.id} className="prompt-chat-msg user">{q.prompt}<button className="prompt-chat-remove" disabled={busy} aria-label="Remove this message" onClick={()=>remove(q.id)}><IcX size={14} aria-hidden="true"/></button></div>)}
      {waiting.length>0&&<div className="prompt-chat-msg ai state-waiting">{asset.chat_reading?'Reading your messages together…':running||planned.length?'Your messages are read together when the current change finishes.':'Reading your messages…'}</div>}
      {errors.map(n=><div key={n.at} className="prompt-chat-msg ai error" role="alert">{n.text}</div>)}
      {!timeline.length&&!queue.length&&!errors.length&&<p className="prompt-chat-hint">Describe a change. Send several in a row or change your mind ("no water after all"); they are read together, and taking a change back returns to the version before it. Water, roof colour and scale are edited in Blender; other changes make a new version with AI.</p>}
    </div>
    <div className="prompt-chat-suggest">{SUGGEST.map(s=><button key={s} disabled={busy} onClick={()=>setText(s)}>{s}</button>)}</div>
    <div className="prompt-chat-input"><textarea aria-label="Prompt chat message" rows={2} maxLength={10000} value={text} disabled={!parent} placeholder={parent?'Type a change… (Enter to send)':'Waiting for the first model'} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}}}/>
      <button className="primary" aria-label="Send" disabled={busy||!text.trim()||!parent} onClick={send}><IcSend size={16} aria-hidden="true"/></button></div>
  </section>;
}
