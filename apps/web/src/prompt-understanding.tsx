import './prompt-understanding.css';

/** Read only inferred metadata. Original prompt remains in the asset's immutable source history. */
export function PromptUnderstanding({specification}:{specification:unknown}) {
 const specificationRecord=specification&&typeof specification==='object'?specification as Record<string,unknown>:null;
 const raw=specificationRecord?.prompt_interpretation;
 if(!raw||typeof raw!=='object')return null;
 const value=raw as Record<string,unknown>,chunks=Array.isArray(value.chunks)?value.chunks:[];
 const first=chunks[0]?.interpretation,subject=typeof first?.requested_subject_en==='string'?first.requested_subject_en:'';
 return <details className="prompt-understanding" aria-label="Local prompt understanding">
  <summary><span>Understood request</span><strong>{subject||'Local interpretation saved'}</strong><span>{value.reference_role==='style'?'Style reference':value.reference_role==='source'?'Reconstruct image':'Text concept'}</span></summary>
  <div><p>{typeof first?.reference_description_en==='string'?first.reference_description_en:''}</p>
   <small>Inferred by {String(value.model||'local model')} / CPU. This interpretation is separate from technical QA and artistic approval.</small>
   <details><summary>English generation instructions</summary><pre>{String(value.generation_prompt_en||'')}</pre></details>
   <details><summary>Provenance and source hashes</summary><pre>{JSON.stringify({model:value.model,digest:value.model_digest,source_prompt_sha256:value.source_prompt_sha256,references:value.references},null,2)}</pre></details>
  </div>
 </details>;
}
