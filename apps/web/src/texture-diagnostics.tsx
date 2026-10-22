import {useState} from 'react';
import {apiFetch} from './api';
type ImageEvidence={index:number;width:number;height:number;encoded_bytes:number;mime_type:string;decoded_rgba_sha256:string};
type Binding={material_index:number;material_name:string;channel:string;image_index:number;texcoord:number;encoding:string;packed_channels?:string};
type Evidence={status:string;images:ImageEvidence[];bindings:Binding[]};
const channels:Record<string,string>={base_color:'Base color',metallic_roughness:'Metallic / roughness',normal:'Normal',occlusion:'Ambient occlusion',emissive:'Emissive'};
export function TextureDiagnostics({metadata,assetId,artifactId,onInspected}:{metadata?:Record<string,unknown>;assetId?:string;artifactId?:string;onInspected?:()=>Promise<void>}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const value=metadata?.texture_diagnostics as Evidence|undefined;const canInspect=Boolean(assetId&&artifactId&&onInspected);if(!value&&!canInspect)return null;
 async function inspect(){if(busy)return;setBusy(true);setError('');try{const response=await apiFetch('/api/library/bulk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({asset_ids:[assetId],artifact_id:artifactId,action:'inspect'})});const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'File inspection failed.');if(result.errors.length)throw Error(result.errors.map((e:{error:string})=>e.error).join('; '));await onInspected?.();}catch(e){setError(String(e));}finally{setBusy(false);}}
 return <details className="texture-diagnostics" aria-label="Validated embedded textures"><summary>Textures &amp; PBR · file checks</summary><p>{value?(value.images.length?`${value.images.length} embedded images decoded and verified when inspected. These measurements belong to the selected model.`:'This model contains no embedded images. Materials may use constant values; missing maps were not generated.'):'This version has no recorded texture file checks. Inspect it locally without rerunning AI or changing the model.'}</p>
  {value?.images.map(image=><div className="texture-evidence-image" key={image.index}><strong>Image {image.index+1}<span>{image.width.toLocaleString()} × {image.height.toLocaleString()} px</span></strong><small>{image.mime_type.replace('image/','').toUpperCase()} · {(image.encoded_bytes/1024**2).toFixed(2)} MB embedded</small><ul>{value.bindings.filter(b=>b.image_index===image.index).map((binding,n)=><li key={n}><span>{channels[binding.channel]||binding.channel}</span><small>{binding.material_name} · UV {binding.texcoord} · {binding.encoding}{binding.packed_channels?` · ${binding.packed_channels}`:''}</small></li>)}</ul></div>)}
  {canInspect&&<button disabled={busy} onClick={inspect}>{busy?'Inspecting actual GLB…':'Inspect selected model'}</button>}{error&&<p role="alert">{error}</p>}{busy&&<p role="status">Checking embedded images and geometry locally. No AI generation.</p>}
  <small>File integrity and resolution do not certify visual detail, UV overlap, physically accurate materials or artistic quality. Normal/AO maps appear only when actually embedded.</small>
 </details>;
}
