import {ToastNotice} from './workspace-feedback';
import { Select } from "./select";
import { apiFetch } from './api';
import { useEffect, useState } from 'react';

type ImageArtifact = {id: string; role: string; name: string; metadata: {has_transparency?: boolean}};
type Engine = {id: string; installed: boolean; inference: string; blocker: string; verified_generation_count?: number};

export function GenerationPanel({artifacts, onChange}: {artifacts: ImageArtifact[]; onChange: () => Promise<void>}) {
  const [engines, setEngines] = useState<Engine[]>([]), [engine, setEngine] = useState('trellis2_community');
  const [source, setSource] = useState(''), [seeds, setSeeds] = useState('42, 43'), [steps, setSteps] = useState(24);
  const [profile, setProfile] = useState('1024_cascade'), [auto, setAuto] = useState(true), [height, setHeight] = useState(10);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [pending, setPending] = useState(false);
  async function load() { const r = await apiFetch('/api/engines'); if (!r.ok) throw new Error(await r.text()); setEngines((await r.json()).engines); }
  useEffect(() => { load().catch(e => setError(String(e))); }, []);
  const available = artifacts.filter(a => ['concept', 'reference'].includes(a.role) && (engine !== 'triposg' || a.metadata.has_transparency));
  async function upload(file?: File) {
    if (!file) return; setPending(true); setError('');
    try {
      const form = new FormData(); form.append('file', file);
      const r = await apiFetch('/api/import/reference', {method: 'POST', body: form});
      if (!r.ok) throw new Error(JSON.stringify((await r.json()).detail));
      setSource((await r.json()).id); await onChange();
    } catch(e) { setError(String(e)); } finally { setPending(false); }
  }
  async function generate() {
    setError(''); setNotice(''); setPending(true);
    try {
      const values = seeds.split(',').map(s => Number(s.trim()));
      if (!seeds.trim() || values.some(n => !Number.isInteger(n))) throw new Error('Nhập 1–4 seed nguyên, cách nhau bằng dấu phẩy.');
      const r = await apiFetch('/api/jobs/tournament', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({engine, artifact_id: source,
        seeds: values, steps, pipeline_type: profile, texture_size: 4096, auto_blender: auto, benchmark_height_m: height})});
      if (!r.ok) throw new Error(JSON.stringify((await r.json()).detail));
      const result = await r.json(); setNotice(`Đã xếp ${result.jobs.length} seed · tournament ${result.tournament_id.slice(0, 8)}. Xem trạng thái/log ở hàng đợi.`);
    } catch(e) { setError(String(e)); } finally { setPending(false); }
  }
  return <section id="local-generation"><div className="section-head"><div><div className="eyebrow">LOCAL AI / SEQUENTIAL TOURNAMENT</div><h2>Ảnh → nhiều seed → Blender</h2><p>Offline weights · mỗi lượt một subprocess · giữ tất cả output và lần lỗi</p></div><span className="badge">EVALUATION ONLY</span></div>
    <div className="job-form"><label className="field">Engine<Select aria-label="Engine local" value={engine} onChange={e => {setEngine(e.target.value); setSource(''); setSteps(e.target.value === 'triposg' ? 50 : 24);}}><option value="trellis2_community">TRELLIS.2 community / shape + PBR</option><option value="triposg">TripoSG / shape only</option></Select></label><label className="field">Ảnh đầu vào<Select aria-label="Ảnh đầu vào AI" value={source} onChange={e => setSource(e.target.value)}><option value="">Chọn concept / reference</option>{available.map(a => <option key={a.id} value={a.id}>{a.name}{a.metadata.has_transparency ? ' / alpha' : ''}</option>)}</Select></label><label className="field">Seeds (1–4)<input aria-label="Seeds" value={seeds} onChange={e => setSeeds(e.target.value)}/></label></div>
    <div className="job-form"><label className="field">Inference steps<input type="number" min="1" max="100" value={steps} onChange={e => setSteps(Number(e.target.value))}/></label><label className="field">TRELLIS profile<Select aria-label="TRELLIS profile" disabled={engine === 'triposg'} value={profile} onChange={e => setProfile(e.target.value)}><option value="1024_cascade">1024 cascade / 4K atlas</option><option value="512">512 / 4K atlas</option></Select></label><label className="field">Chiều cao benchmark tạm (m)<input type="number" min="0.01" max="1000" value={height} onChange={e => setHeight(Number(e.target.value))}/></label></div>
    <div className="tools"><label><input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)}/> Tự xếp Blender + LOD + 6 góc mobile/1440p</label><button disabled={pending || !source || !engines.find(e => e.id === engine)?.installed} onClick={generate}>Generate local</button><label className="upload">Nhập ảnh / alpha PNG<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => upload(e.target.files?.[0])}/></label></div>
    <p className="muted">TRELLIS là bản community có CPU offload; dependency và mask license còn cần duyệt thương mại. TripoSG cần alpha thật, chỉ sinh geometry, decoder grid 512³. Ảnh conditioning là bản dẫn xuất cần review; không có multi-view được xác nhận. App không tự tải weights hoặc gọi cloud.</p>
    {error && <div role="alert" className="message error">{error}</div>}<ToastNotice message={notice} onDismiss={()=>setNotice('')}/>
    <div className="engine-list">{engines.map(e => <span key={e.id}><b>{e.id}</b> · {e.installed ? 'installed' : 'unavailable'} · inference {e.inference}{e.verified_generation_count ? ` (${e.verified_generation_count})` : ''}<small>{e.blocker}</small></span>)}</div>
  </section>;
}
