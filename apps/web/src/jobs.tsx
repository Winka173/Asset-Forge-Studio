import { Select } from "./select";
import { apiFetch, apiUrl } from './api';
import { useEffect, useState } from 'react';

type Job = {id: string; status: string; error?: string; created_at: string; payload: {artifact_id: string}};
type Artifact = {id: string; name: string; role: string};
type JobFile = {name: string; bytes: number; url: string};

export function BlenderJobs({artifacts, onChange}: {artifacts: Artifact[]; onChange: () => Promise<void>}) {
  const [jobs, setJobs] = useState<Job[]>([]), [source, setSource] = useState('');
  const [height, setHeight] = useState(''), [yaw, setYaw] = useState('0'), [full, setFull] = useState(true);
  const [error, setError] = useState(''), [files, setFiles] = useState<JobFile[]>([]), [selected, setSelected] = useState('');
  const [pending, setPending] = useState(false);
  const [filter, setFilter] = useState('all'), [expanded, setExpanded] = useState(false);
  const activeStates = ['QUEUED', 'RUNNING', 'GENERATED', 'POSTPROCESSING', 'VALIDATING'];
  const filtered = jobs.filter(j => filter === 'all' || (filter === 'active' ? activeStates.includes(j.status) : filter === 'review' ? j.status === 'REVIEW_REQUIRED' : ['FAILED', 'CANCELLED', 'BLOCKED'].includes(j.status)));
  const visible = expanded ? filtered : filtered.slice(0, 12);
  async function refreshJobs() {
    const res = await apiFetch('/api/jobs'); if (!res.ok) throw new Error(await res.text());
    const result: Job[] = await res.json(); setJobs(result);
    if (result.some(j => j.status === 'REVIEW_REQUIRED')) await onChange();
    if (selected) await inspect(selected);
  }
  useEffect(() => { refreshJobs().catch(e => setError(String(e))); const timer = setInterval(() => refreshJobs().catch(e => setError(String(e))), 2500); return () => clearInterval(timer); }, [selected]);
  async function action(url: string, body?: unknown) {
    setError(''); setPending(true);
    try {
      const res = await apiFetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, ...(body ? {body: JSON.stringify(body)} : {})});
      if (!res.ok) throw new Error(JSON.stringify((await res.json()).detail));
      await refreshJobs();
    } catch (e) { setError(String(e)); } finally { setPending(false); }
  }
  async function inspect(id: string) {
    const res = await apiFetch(`/api/jobs/${id}/files`); if (!res.ok) throw new Error(await res.text());
    setFiles(await res.json()); setSelected(id);
  }
  return <section id="blender-jobs"><div className="section-head"><div><div className="eyebrow">BLENDER / REPEATABLE PIPELINE</div><h2>Master → LOD → benchmark render</h2><p>Sequential worker · raw kept · geometry and PBR still need review</p></div></div>
    <div className="job-form"><label className="field">Source GLB<Select aria-label="Source GLB Blender" value={source} onChange={e => setSource(e.target.value)}><option value="">Choose an imported model</option>{artifacts.filter(a => ['golden', 'candidate'].includes(a.role)).map(a => <option key={a.id} value={a.id}>{a.role} / {a.name}</option>)}</Select></label><label className="field">Target height (m), optional<input type="number" min="0.01" max="1000" value={height} onChange={e => setHeight(e.target.value)} placeholder="Leave empty to keep scale and pivot"/></label><label className="field">Blender Z yaw (degrees)<input type="number" min="-360" max="360" value={yaw} onChange={e => setYaw(e.target.value)}/></label></div>
    <div className="tools"><label><input type="checkbox" checked={full} onChange={e => setFull(e.target.checked)}/> 6 views × mobile + 1440p</label><button disabled={!source || pending} onClick={() => action('/api/jobs/blender', {artifact_id: source, normalize: !!height, target_height_m: height ? Number(height) : null, yaw_degrees: Number(yaw), render: true, resolutions: full ? ['mobile', 'pc1440'] : ['mobile'], views: full ? ['front', 'three_quarter', 'side', 'back', 'top', 'gameplay'] : ['three_quarter']})}>Queue Blender job</button></div>
    <p className="muted">A height scales uniformly and moves the pivot to the bottom centre. The standard camera is a draft setup; check framing in the report before comparing. LOD decimation is not baked or silhouette-approved.</p>
    {error && <div role="alert" className="message error">{error}</div>}
    {jobs.length ? <><div className="history-toolbar"><h3>Processing history <span className="count">{jobs.length}</span></h3><label>Filter jobs<Select aria-label="Filter job history" value={filter} onChange={e => {setFilter(e.target.value); setExpanded(false);}}><option value="all">All ({jobs.length})</option><option value="active">Queued / running ({jobs.filter(j => activeStates.includes(j.status)).length})</option><option value="review">Needs review ({jobs.filter(j => j.status === 'REVIEW_REQUIRED').length})</option><option value="issues">Failed / stopped ({jobs.filter(j => ['FAILED', 'CANCELLED', 'BLOCKED'].includes(j.status)).length})</option></Select></label></div><div className="job-list">{visible.map(j => <div className={`job-row${selected === j.id ? ' selected' : ''}`} key={j.id}><button className="job-select" aria-pressed={selected === j.id} onClick={() => inspect(j.id).catch(e => setError(String(e)))}><span className="mono">{j.id.slice(0, 10)}</span><span className={`state state-${j.status.toLowerCase()}`}>{j.status}</span></button><time dateTime={j.created_at}>{new Date(j.created_at).toLocaleString()}</time>{activeStates.includes(j.status) ? <button disabled={pending} onClick={() => action(`/api/jobs/${j.id}/cancel`)}>Stop</button> : <button className="btn-info" disabled={pending} onClick={() => action(`/api/jobs/${j.id}/retry`)}>Retry as new attempt</button>}{j.error && <p className="error-text">{j.error}</p>}</div>)}</div>{!filtered.length && <p className="empty">No jobs match this filter.</p>}{filtered.length > 12 && <button className="history-expand" onClick={() => setExpanded(!expanded)}>{expanded ? 'Collapse history' : `Show more ${filtered.length - 12} job`}</button>}</> : <p className="muted">No jobs yet. Post-processing needs a real GLB; concept images are not inputs to the Blender mesh pipeline.</p>}
    {selected && <div><h3>Artifacts / {selected.slice(0, 10)}</h3><div className="artifact-links">{files.filter(f => !f.name.endsWith('.png') && !f.name.endsWith('.exr')).map(f => <a key={f.name} href={apiUrl(f.url)} target="_blank" rel="noreferrer">{f.name} <small>{(f.bytes / 1024).toFixed(0)} KiB</small></a>)}</div><div className="render-grid">{files.filter(f => f.name.endsWith('.png') && !f.name.includes('_asset')).map(f => <figure key={f.name}><a href={apiUrl(f.url)} target="_blank" rel="noreferrer"><img src={apiUrl(f.url)} alt={`Real Blender render ${f.name}`}/></a><figcaption>{f.name}</figcaption></figure>)}</div></div>}
  </section>;
}
