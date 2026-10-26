import {useState} from 'react';
import {apiFetch} from './api';
import {isDesktop, openDesktopFolder} from './desktop';
type Report={path:string;bytes:number;folder:string};
/** One zip with logs, system facts and recent job failures for bug reports (no prompts, personal paths removed). */
export function SupportReport(){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[report,setReport]=useState<Report|null>(null);
 async function create(){setBusy(true);setError('');try{const r=await apiFetch('/api/diagnostics/export',{method:'POST'});if(!r.ok)throw Error((await r.json().catch(()=>({detail:'Report failed'}))).detail);setReport(await r.json());}catch(e){setError(String(e));}finally{setBusy(false);}}
 return <section className="settings-panel support-report" aria-label="Support report"><h2>Support report</h2>
  <p>Creates one zip with the app logs, system and GPU facts, engine status and the latest failed jobs. Prompts and personal folder names are removed. Attach it when you report a bug.</p>
  <button className="primary" disabled={busy} onClick={create}>{busy?'Creating report…':'Export full log'}</button>
  {error&&<p role="alert">{error}</p>}
  {report&&<p role="status">Saved <code>{report.path}</code> ({(report.bytes/1048576).toFixed(2)} MB).{isDesktop()&&<> <button onClick={()=>openDesktopFolder('reports').catch(e=>setError(String(e)))}>Show in folder</button></>}</p>}
 </section>;
}
