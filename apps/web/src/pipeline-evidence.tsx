/** Compact strategy/gate evidence; no fabricated artistic rating. */
export function PipelineEvidence({specification,evaluations}:{specification:unknown;evaluations?:unknown}){
 const value=specification&&typeof specification==='object'?specification as Record<string,unknown>:{};
 const spec=value.asset_generation_spec as {route?:string;rationale?:string[];limitations?:string[]}|undefined;
 const reports=Array.isArray(evaluations)?evaluations:[],report=reports.at(-1) as {artifact_id:string;gates:{layer:string;outcome:string;mandatory:boolean;limitations:string[]}[]}|undefined;
 if(!spec&&!report)return null;
 return <details className="pipeline-evidence" aria-label="Production strategy and quality evidence"><summary>Strategy &amp; quality evidence</summary>
  {spec&&<><strong>{spec.route==='procedural_castle'?'Named castle assembly / Blender':spec.route==='image_to_3d'?'Image to 3D':spec.route}</strong>{spec.rationale?.map(r=><p key={r}>{r}</p>)}{spec.limitations?.map(r=><p className="muted" key={r}>{r}</p>)}</>}
  {report&&<><p>Latest measured candidate: {report.artifact_id.slice(0,8)}</p><dl>{report.gates.map(g=><div key={g.layer}><dt>{g.layer.replaceAll('_',' ')}{g.mandatory?' / required':''}</dt><dd>{g.outcome.replaceAll('_',' ')}</dd></div>)}</dl><small>Only required technical/structural gates control delivery. Visual observations do not approve the artwork.</small></>}
 </details>;
}
