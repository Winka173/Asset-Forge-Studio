import {Trash2 as IcTrash} from "lucide-react";
import {useState} from 'react';
import {createPortal} from 'react-dom';
import {managementCall} from './asset-management';
import {ErrorNotice} from './error-notice';
type Plan={name:string;active_jobs:number;jobs:number;artifacts:number;library_bytes:number;batches:string[];game_files:{path:string;bytes:number}[]};
const mb=(n:number)=>n>=2**30?`${(n/2**30).toFixed(1)} GB`:`${(n/2**20).toFixed(1)} MB`;

// Permanent delete of one asset and every file the app made for it; the user types the name to confirm.
export function DeleteAssetButton({assetId,onDeleted,compact=false}:{assetId:string;onDeleted:()=>void;compact?:boolean}){
 const [plan,setPlan]=useState<Plan|null>(null),[typed,setTyped]=useState(''),[game,setGame]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function open(){setError('');setTyped('');try{const value=await managementCall<Plan>(`/api/asset-delete/${assetId}`);setPlan(value);setGame(value.game_files.length>0);}catch(e){setError(String(e));}}
 async function remove(){if(!plan)return;setBusy(true);setError('');try{await managementCall(`/api/asset-delete/${assetId}`,{confirm_name:typed,include_game_files:game});setPlan(null);onDeleted();}catch(e){setError(String(e));}finally{setBusy(false);}}
 return <>
  <button className="production-danger-action" onClick={open} title="Delete this asset and every file the app made for it"><IcTrash size={15} aria-hidden="true"/>{compact?'Delete':'Delete asset'}</button>
  {error&&!plan&&<ErrorNotice message={error} onDismiss={()=>setError('')}/>}
  {plan&&createPortal(<div className="modal-backdrop questions-backdrop" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)setPlan(null);}}><div className="studio-modal" role="dialog" aria-modal="true" aria-label="Delete asset" onKeyDown={e=>{if(e.key==='Escape'&&!busy)setPlan(null);}}>
   <header className="modal-heading"><h2>Delete “{plan.name}”?</h2></header>
   <p>This permanently removes the asset and everything the app made for it. It cannot be undone.</p>
   <ul className="delete-plan">
    <li>{plan.jobs} job{plan.jobs===1?'':'s'}{plan.active_jobs?` (${plan.active_jobs} unfinished, stopped first)`:''} and their working files</li>
    <li>{plan.artifacts} saved file{plan.artifacts===1?'':'s'} (concepts, models, checks, exports)</li>
    <li>Frees about <b>{mb(plan.library_bytes)}</b> in the library</li>
    {plan.batches.length>0&&<li>Removed from batch: {plan.batches.join(', ')}</li>}
   </ul>
   {plan.game_files.length>0&&<label className="delete-game"><span><input type="checkbox" checked={game} onChange={e=>setGame(e.target.checked)}/> Also delete the files delivered to the game folder</span><small>{plan.game_files.map(f=><code key={f.path}>{f.path} ({mb(f.bytes)})</code>)}Only files unchanged since delivery are removed; the game manifest entry goes too.</small></label>}
   <label className="studio-field">Type the asset name to confirm<input aria-label="Asset name to confirm" value={typed} onChange={e=>setTyped(e.target.value)} placeholder={plan.name} autoFocus/></label>
   {error&&<ErrorNotice message={error} onDismiss={()=>setError('')}/>}
   <div className="modal-actions"><button className="quiet-button" disabled={busy} onClick={()=>setPlan(null)}>Keep asset</button><button className="production-danger-action" disabled={busy||typed.trim()!==plan.name.trim()} onClick={remove}><IcTrash size={15} aria-hidden="true"/>{busy?'Deleting...':'Delete permanently'}</button></div>
  </div></div>,document.body)}
 </>;
}
