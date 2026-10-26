import {apiFetch, configureDesktopApi, redactApiSecrets} from './api';
import './desktop.css';

type Session = {phase: string; message: string; api_base?: string; api_token?: string; backend_pid?: number; workspace: string; library: string; logs: string; setup_complete: boolean; version: string};
type Native = {core: {invoke: <T>(command: string,args?:Record<string,unknown>)=>Promise<T>}};
declare global {interface Window {__TAURI__?:Native; __TAURI_INTERNALS__?:unknown;}}
export const isDesktop = () => !!window.__TAURI_INTERNALS__;
function native<T>(command:string,args?:Record<string,unknown>):Promise<T> {if(!window.__TAURI__) return Promise.reject(new Error('Native desktop bridge unavailable'));return window.__TAURI__.core.invoke<T>(command,args);}
export async function openDesktopFolder(scope:'library'|'workspace'|'logs'|'reports') {return native<void>('desktop_open_folder',{scope});}
export async function configureDesktopDirectory(kind:'library'|'workspace') {return native<string|null>('desktop_pick_directory',{kind});}
export async function configureDesktopBlender() {return native<string|null>('desktop_pick_blender');}
export async function desktopInfo() {const value=await native<Session>('desktop_bootstrap');return {phase:value.phase,workspace:value.workspace,library:value.library,logs:value.logs,version:value.version,backend_pid:value.backend_pid};}

function element<K extends keyof HTMLElementTagNameMap>(tag:K,text?:string,className?:string) {const value=document.createElement(tag);if(text)value.textContent=text;if(className)value.className=className;return value;}
function startup(message:string,failed=false) {
  const root=document.getElementById('root')!;root.replaceChildren();const shell=element('div',undefined,'desktop-startup');const panel=element('div',undefined,'desktop-startup-panel');
  panel.append(element('span','ASSET FORGE / WINDOWS DESKTOP','desktop-overline'),element('h1','Your local studio.'),element('p',message));
  const state=element('div',undefined,'desktop-startup-state');state.append(element('i',undefined,failed?'failed':'pulse'),element('span',failed?'Startup needs attention':'Starting backend and checking storage'));panel.append(state);
  if(failed){const retry=element('button','Retry backend','desktop-primary');retry.onclick=async()=>{await native('desktop_retry_backend');await bootDesktop();location.reload();};const logs=element('button','Open startup logs');logs.onclick=()=>openDesktopFolder('logs');panel.append(retry,logs);}
  shell.append(panel);root.append(shell);
}
async function ready() {
  for(let attempt=0;attempt<210;attempt++) {const session=await native<Session>('desktop_bootstrap');if(session.phase==='READY'&&session.api_base&&session.api_token){configureDesktopApi(session.api_base,session.api_token);return session;}if(session.phase==='FAILED')throw new Error(session.message);startup(session.message);await new Promise(resolve=>setTimeout(resolve,1000));}
  throw new Error('Startup timed out. Open local logs to inspect the retained error.');
}
async function setup(session:Session):Promise<void> {
  const [gpu,engines,environment]=await Promise.all([apiFetch('/api/gpu').then(r=>r.json()).catch(()=>({available:false})),apiFetch('/api/engines').then(r=>r.json()).catch(()=>({engines:[]})),apiFetch('/api/environment').then(r=>r.json()).catch(()=>({}))]);
  return new Promise(resolve=>{
    const root=document.getElementById('root')!;root.replaceChildren();const shell=element('div',undefined,'desktop-startup');const panel=element('div',undefined,'desktop-setup-panel');panel.append(element('span','FIRST-RUN SETUP / NOTHING DOWNLOADS AUTOMATICALLY','desktop-overline'),element('h1','A local home for your work.'),element('p','The desktop and Python backend are bundled. AI environments, weights and Blender remain managed local dependencies. Your existing library is preserved.'));
    const checks=element('div',undefined,'desktop-setup-checks');
    const rows=[['Backend','Ready · packaged Python runtime'],['GPU',gpu.available?`${gpu.name} · ${(gpu.total_mib/1024).toFixed(1)} GB VRAM`:'Missing / unsupported · check NVIDIA driver'],['Engine environments',`${engines.engines?.filter((e:{installed:boolean})=>e.installed).length || 0} installed · runtime/quality validation remains per engine`],['Blender',environment.blender_path || 'Missing · choose Blender executable'],['SSD',environment.disk_free_bytes?`${(environment.disk_free_bytes/1073741824).toFixed(1)} GB free on audited drive`:'Not measured'],['Library',session.library],['AI workspace',session.workspace]];
    for(const [label,value] of rows){const row=element('div');row.append(element('span',label),element('strong',value));checks.append(row);}panel.append(checks);
    const error=element('p',undefined,'desktop-setup-error');const actions=element('div',undefined,'desktop-setup-actions');
    for(const [label,command,args] of [['Choose library folder','desktop_pick_directory',{kind:'library'}],['Choose AI workspace','desktop_pick_directory',{kind:'workspace'}],['Choose Blender','desktop_pick_blender',{}]] as const){const button=element('button',label);button.onclick=async()=>{button.disabled=true;try{const path=await native<string|null>(command,{...args});if(path){const next=await ready();await setup(next);resolve();}}catch(e){error.textContent=redactApiSecrets(String(e));}finally{button.disabled=false;}};actions.append(button);}
    const proceed=element('button','Open studio','desktop-primary');proceed.onclick=async()=>{proceed.disabled=true;try{await native('desktop_finish_setup');resolve();}catch(e){error.textContent=redactApiSecrets(String(e));proceed.disabled=false;}};panel.append(actions,error,proceed,element('small','Quality Lock, immutable source files and the shared local scheduler remain unchanged. No model weights are bundled or silently downloaded.'));shell.append(panel);root.append(shell);
  });
}
function nativeFeatures() {
  window.addEventListener('afs-desktop-exit',event=>{
    const value=(event as CustomEvent<{phase:string;message:string}>).detail;
    let banner=document.querySelector<HTMLDivElement>('.desktop-checkpoint-exit');
    if(value.phase==='cancelled'){banner?.remove();return;}
    if(!banner){banner=element('div',undefined,'desktop-checkpoint-exit');banner.setAttribute('role','status');document.body.append(banner);}
    banner.dataset.desktopClosing=value.phase;banner.replaceChildren();banner.append(element('strong',value.phase==='error'?'AFS kept open':value.phase==='stopping'?'Checkpoint saved':'Finishing this stage before exit'),element('p',value.message));
    if(value.phase==='waiting'){const keep=element('button','Keep studio open');keep.onclick=()=>{keep.disabled=true;native('desktop_cancel_close').catch(e=>{keep.disabled=false;banner!.append(element('p',redactApiSecrets(String(e))));});};banner.append(keep);}
    if(value.phase==='error'){const dismiss=element('button','Dismiss');dismiss.onclick=()=>banner?.remove();banner.append(dismiss);}
  });

  document.addEventListener('click',event=>{const anchor=(event.target as Element)?.closest<HTMLAnchorElement>('a[download]');if(!anchor)return;const url=new URL(anchor.href);if(url.hostname!=='127.0.0.1'||!url.pathname.startsWith('/api/'))return;event.preventDefault();url.searchParams.delete('afs_token');native('desktop_download',{apiPath:url.pathname+url.search}).catch(e=>{alert(redactApiSecrets(String(e)));});});
  // Asset-level, grouped notifications are owned by WorkspaceTools and require explicit opt-in.

}
export async function bootDesktop() {
  if(!isDesktop())return;
  startup('Preparing persistent storage and the managed local backend…');
  try{const session=await ready();if(!session.setup_complete)await setup(session);nativeFeatures();}catch(e){startup(redactApiSecrets(e instanceof Error?e.message:String(e)),true);throw e;}
}
