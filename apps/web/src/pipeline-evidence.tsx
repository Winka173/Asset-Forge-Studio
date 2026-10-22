/** Compact strategy/gate evidence; no fabricated artistic rating. */
export function PipelineEvidence({specification,evaluations}:{specification:unknown;evaluations?:unknown}){
 const value=specification&&typeof specification==='object'?specification as Record<string,unknown>:{};
 const spec=value.asset_generation_spec as {route?:string;rationale?:string[];limitations?:string[]}|undefined;
 const reports=Array.isArray(evaluations)?evaluations:[],report=reports.at(-1) as {artifact_id:string;gates:{layer:string;outcome:string;mandatory:boolean;limitations:string[]}[]}|undefined;
 const repairs=Array.isArray(value.quality_repair_history)?value.quality_repair_history as {id:string;root_cause:string;stage:string;action:string;reason:string;budget?:{used:{attempts:number};limits:{max_attempts:number}}}[]:[];
 if(!spec&&!report&&!repairs.length)return null;
 return <details className="pipeline-evidence" aria-label="Production strategy and quality evidence"><summary>Strategy &amp; quality evidence</summary>
  {spec&&<><strong>{spec.route==='procedural_castle'?'Structural blockout / simple Blender geometry':spec.route==='image_to_3d'?'Detailed image-to-3D route':spec.route}</strong>{spec.route==='procedural_castle'&&<p role="note">This is a structural layout study. Technical checks do not establish the detail, materials or artistic quality of the AI tower baseline.</p>}{spec.rationale?.map(r=><p key={r}>{r}</p>)}{spec.limitations?.map(r=><p className="muted" key={r}>{r}</p>)}</>}
  {report&&<><p>Latest measured candidate: {report.artifact_id.slice(0,8)}</p><dl>{report.gates.map(g=><div key={g.layer}><dt>{g.layer.replaceAll('_',' ')}{g.mandatory?' / required':''}</dt><dd>{g.outcome.replaceAll('_',' ')}</dd></div>)}</dl><small>Only required technical/structural gates control delivery. Visual observations do not approve the artwork.</small></>}
  {repairs.length>0&&<details aria-label="Automatic repair history"><summary>Recovery decisions · {repairs.length}</summary>{repairs.map(p=><div key={p.id}><strong>{p.stage} · {p.root_cause.replaceAll('_',' ')}</strong><p>{p.reason}</p><small>{p.action.replaceAll('_',' ')}{p.budget?` · ${p.budget.used.attempts}/${p.budget.limits.max_attempts} automatic repairs used`:''} · quality and original sources preserved</small></div>)}</details>}
 </details>;
}
