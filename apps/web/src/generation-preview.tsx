import './generation-preview.css';

/** Activity artwork, never a streamed mesh or an estimate of inference completion. */
export function GenerationPreview({stage,state='running',onRetry}:{stage:string;state?:'running'|'waiting'|'paused'|'blocked';onRetry?:()=>void}) {
 return <div className="generation-preview" data-state={state} aria-label="Asset generation activity">
  <div className="generation-preview-art" aria-hidden="true">
   <div className="generation-preview-halo" />
   <svg className="generation-preview-mesh" viewBox="0 0 320 300" fill="none">
    <defs><linearGradient id="afs-build-fill" x1="60" y1="40" x2="250" y2="250" gradientUnits="userSpaceOnUse"><stop stopColor="#e8bd80" stopOpacity=".28"/><stop offset="1" stopColor="#8faed5" stopOpacity=".06"/></linearGradient></defs>
    <ellipse className="generation-preview-ground" cx="160" cy="258" rx="115" ry="25"/>
    {[0,1,2].map(n=><g key={n} className="generation-preview-layer" style={{animationDelay:`${n*-.8}s`}} transform={`translate(0 ${n*52})`}>
     <path d="M160 35 240 78 160 122 80 78Z" fill="url(#afs-build-fill)"/>
     <path d="M80 78v43l80 44 80-44V78M160 122v43M80 78l80 44 80-44-80-43Z"/>
     <path d="m120 57 80 43m-80 0 80-43M120 100v43m80-43v43M80 100l80 44 80-44" opacity=".4"/>
    </g>)}
    <path className="generation-preview-scan" d="m50 150 110-60 110 60-110 60Z"/>
    {[['160','35'],['80','130'],['240','182'],['160','269']].map(([cx,cy],i)=><circle className="generation-preview-node" key={cx+cy} cx={cx} cy={cy} r="3" style={{animationDelay:`${i*-.6}s`}}/>)}
   </svg>
  </div>
  <div className="generation-preview-copy" role="status" aria-live="polite" aria-atomic="true">
   <span className="generation-preview-eyebrow">{state==='blocked'?'PRODUCTION NEEDS ATTENTION':state==='paused'?'PRODUCTION PAUSED':state==='waiting'?'WAITING FOR THE NEXT STAGE':'LOCAL CREATION IN PROGRESS'}</span>
   <h2>{state==='blocked'?'Asset needs attention':state==='paused'?'Your progress is saved':state==='waiting'?'Your asset is in the queue':'Building your asset'}</h2><p>{stage}</p>
   <small>The full 3D model appears after processing, validation and delivery finish. Intermediate images stay as thumbnails.</small>
  </div>
  {onRetry&&<button className="generation-preview-details" onClick={onRetry}>Try another concept</button>}
 </div>;
}
