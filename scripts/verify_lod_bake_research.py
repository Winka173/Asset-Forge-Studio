"""Research-only real 4K normal/AO bake on retained tower LODs; no AI/quality pass claim."""
import json,os,sys,time,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'.local/lod-bake-research'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');RUN.mkdir(parents=True)
os.environ['AFS_DATA']=str(RUN/'Library');sys.path.insert(0,str(ROOT))
from apps.api import jobs,store
from apps.api.local_tools import executable
from apps.api.inspection import inspect_glb,glb_document
import trimesh,numpy as np
prior=json.loads((ROOT/'.local/lod-quality-real/20261022T131218Z/report.json').read_text('utf-8'))
folder=Path(prior['run'])/'Library/jobs'/prior['job_id']/'output';master=folder/'LOD0.glb';lod=folder/'LOD3.glb'
hashes={str(p):store.digest(p) for p in (master,lod)}
scene=trimesh.load(master,force='scene',process=False);low,high=scene.bounds;center=(low+high)/2;diagonal=float(np.linalg.norm(high-low));target=np.array([center[0],-center[2],center[1]])
cfg=json.loads((ROOT/'benchmarks/archer_tower_t3/benchmark.json').read_text('utf-8'));cfg.update(target_xyz_m=target.tolist(),ortho_scale_m=float(max(high-low))*1.6,camera_distance_m=4*diagonal,resolutions=dict(mobile=[768,768]),review_frame_basis='Common retained master bounds, fixed for both versions; no independent normalization')
for name,vector,power in [('key',[1,-1.5,2],1800),('fill',[-1,-1,1.3],1000)]:
    cfg['lights'][name+'_xyz_m']=(target+diagonal*np.array(vector)).tolist();cfg['lights'][name+'_w']=power*(diagonal/14)**2
benchmark=RUN/'benchmark.json';benchmark.write_text(json.dumps(cfg,indent=2),'utf-8')
request=dict(master=str(master),lod=str(lod),output=str(RUN/'output'),benchmark=str(benchmark),texture_size=4096,cage_extrusion_m=diagonal*.002,max_ray_distance_m=diagonal*.04,bounds_tolerance_m=diagonal*.05)
path=RUN/'request.json';path.write_text(json.dumps(request,indent=2),'utf-8');started=time.monotonic()
report=dict(status='RUNNING_RESEARCH_BAKE',run=str(RUN),request=request,scope='Retained actual generated tower; CPU geometry-to-LOD normal and AO bake, not AI texture synthesis. Visual improvement, coverage and production integration are not established by a completed subprocess.')
try:
    with jobs.resource_slot('cpu'),(RUN/'worker.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([executable('blender'),'-b','-t','8','--factory-startup','--python-exit-code','1','--python',str(ROOT/'pipelines/blender/bake_lod.py'),'--','--request',str(path)],stdout=log,stderr=subprocess.STDOUT,timeout=7200)
    if result.returncode:raise ValueError('Actual bake process failed; see worker.log')
    report.update(status='COMPLETED_RESEARCH_BAKE_NEEDS_REVIEW',qa=inspect_glb(RUN/'output/LOD_baked.glb'),bake=json.loads((RUN/'output/report.json').read_text('utf-8')))
    doc=glb_document(RUN/'output/LOD_baked.glb');report['normal_texture_attached']=any('normalTexture' in m for m in doc.get('materials',[]))
    from PIL import Image
    report['actual_map_statistics']={}
    for name in ('normal','ao'):
        with Image.open(RUN/f'output/lod_{name}.png') as image:
            pixels=np.asarray(image.convert('RGB'),dtype=np.float32);report['actual_map_statistics'][name]=dict(dimensions=list(image.size),min=float(pixels.min()),max=float(pixels.max()),standard_deviation_per_channel=pixels.std(axis=(0,1)).tolist())
    assert all(store.digest(Path(p))==h for p,h in hashes.items());report['sources_preserved']=True
except Exception as exc:report.update(status='FAILED_RESEARCH_BAKE',error=str(exc));raise
finally:
    report['seconds']=time.monotonic()-started;(RUN/'report.json').write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(dict(status=report['status'],run=str(RUN))),flush=True)
