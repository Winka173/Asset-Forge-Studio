import {redactApiSecrets} from './api';

export function ErrorNotice({message,onRefresh,onEdit,onDismiss}:{message:string;onRefresh?:()=>void;onEdit?:()=>void;onDismiss?:()=>void}) {
 const text=redactApiSecrets(message.replace(/^Error:\s*/,''));
 const resource=/out of memory|\boom\b|vram/i.test(text),disk=/disk|storage|space/i.test(text),engine=/engine|dependency|not installed|unavailable|blender|cuda/i.test(text),network=/fetch|network|connection|offline/i.test(text);
 const title=resource?'GPU memory needs attention':disk?'Check the output drive':engine?'A local tool needs attention':network?'Local connection interrupted':'This action could not finish';
 const guidance=resource?'Keep Maximum Quality. Pause other GPU applications, then retry the failed stage in Production.':disk?'Free space or choose another export folder. Existing models remain in the Library.':engine?'Check the installed tool and engine configuration in Settings. Your prompt and previous outputs are retained.':network?'Reload the local status. This does not submit another generation.':'Check the details below and edit the input if needed. Other assets can keep processing.';
 return <div className="error-notice" role="alert"><div><strong>{title}</strong><p>{guidance}</p><details><summary>Error details</summary><pre>{text}</pre></details></div><div className="error-notice-actions">{onEdit&&<button onClick={onEdit}>Edit input</button>}{engine&&<button onClick={()=>{location.hash='settings';}}>Open Settings</button>}{onRefresh&&<button onClick={onRefresh}>Reload status</button>}{onDismiss&&<button aria-label="Dismiss error" onClick={onDismiss}>Dismiss</button>}</div></div>;
}
