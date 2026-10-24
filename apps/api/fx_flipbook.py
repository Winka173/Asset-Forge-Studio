"""Simulated fire / smoke / explosion flipbooks: Blender Mantaflow bake + Cycles CPU render through the shared queue.

A CPU job (no GPU slot): bake and render run as two Blender processes (pipelines/blender/fx_flipbook.py). The output
is a straight-alpha sprite sheet plus a report; no AI inference and no artistic approval implied.
"""
import json
import re
import subprocess
import uuid
from typing import Literal
from pydantic import BaseModel,Field
from fastapi import APIRouter,HTTPException
from . import store,studio,jobs
from engines.quality import fingerprint

router=APIRouter(prefix='/api/fx/flipbook')
SCRIPT=store.ROOT/'pipelines/blender/fx_flipbook.py'
# Simulation grid and render samples per quality; frames and cell size stay the user's choice.
QUALITY={'Fast':dict(resolution=64,samples=32),'Balanced':dict(resolution=96,samples=64),'Maximum':dict(resolution=128,samples=64)}
PRESET_WORDS={'explosion':r'\bexplo\w*|\bblast\b|\bboom\b|\bdetonat\w*|\bnổ\b','smoke':r'\bsmoke\w*|\bfog\b|\bmist\b|\bdust\b|\bkhói\b|\bbụi\b|\bsương\b',
              'fire':r'\bfire\b|\bflames?\b|\bburn\w*|\bcampfire\b|\btorch\b|\blửa\b|\bcháy\b'}

class Flipbook(BaseModel):
    project_id:str
    name:str=Field(default='',max_length=200)
    prompt:str=Field(default='',max_length=10000)
    preset:Literal['auto','fire','smoke','explosion']='auto'
    # Stylized (default): flat cartoon bands for stylized/low-poly games; realistic keeps the volumetric shading.
    look:Literal['stylized','realistic']='stylized'
    quality:Literal['Fast','Balanced','Maximum']='Maximum'
    frames:Literal[16,36,64]=36
    cell:Literal[128,256,512]=256
    seed:int=Field(default=42,ge=0,le=2147483647)
    color:str|None=Field(default=None,pattern=r'^#[0-9a-fA-F]{6}$')
    asset_id:str|None=None
    request_id:str=Field(min_length=8,max_length=100)


def resolve(body):
    """Pick the simulation from the prompt when not set; decided and recorded, never blocking."""
    if body.preset!='auto':return body.preset,dict(kind='explicit',source='Effect setting')
    found={name:m.start() for name,pattern in PRESET_WORDS.items() if (m:=re.search(pattern,body.prompt,re.I))}
    if not found:return 'fire',dict(kind='defaulted',source='No fire, smoke or explosion named; fire is the default simulation')
    first=min(found,key=found.get)
    return first,dict(kind='explicit' if len(found)==1 else 'inferred',source='Named in the prompt' if len(found)==1 else f"First of {', '.join(sorted(found,key=found.get))} named in the prompt")


@router.post('',status_code=201)
def create(body:Flipbook):
    from .local_tools import executable
    if not executable('blender'):raise HTTPException(409,'Blender is not installed; simulated effects need the local Blender')
    project=studio.project(body.project_id);preset,provenance=resolve(body)
    name=body.name.strip() or body.prompt.strip().split('\n')[0][:80] or f'{preset.title()} flipbook'
    config=dict(schema_version=1,engine_id='blender_mantaflow',stage='fx_flipbook',preset=preset,preset_provenance=provenance,look=body.look,quality=body.quality,frames=body.frames,cell=body.cell,
                seed=body.seed,color=body.color,input_prompt=body.prompt,script_sha256=store.digest(SCRIPT),**QUALITY[body.quality],
                method='Mantaflow gas simulation, Cycles CPU render, straight-alpha sprite sheet; no AI inference',artistic_approval=False)
    checksum=fingerprint(body.model_dump())
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');prior=studio.cached(db,'fxflip:'+body.request_id,checksum)
        if prior:return prior
        if body.asset_id:
            row=db.execute('SELECT payload FROM assets WHERE id=?',(body.asset_id,)).fetchone()
            if not row:raise HTTPException(404,'Effect asset no longer exists')
            asset=json.loads(row['payload'])
            if asset['project_id']!=body.project_id or asset.get('asset_type')!='vfx':raise HTTPException(409,'Effect asset belongs to another game or asset type')
        else:
            asset=dict(id=uuid.uuid5(uuid.NAMESPACE_URL,'afs-fxflip:'+body.project_id+':'+body.request_id).hex,project_id=body.project_id,asset_type='vfx',name=name,prompt=body.prompt,original_prompt=body.prompt,
                       category='Effects',reference_ids=[],settings={},favorite=False,status='Candidate',master_artifact_id=None,approvals=[],created_at=store.now())
        asset['updated_at']=store.now()
        db.execute('INSERT INTO assets VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(asset['id'],asset['project_id'],json.dumps(asset)))
        job=jobs.enqueue(dict(kind='fx_flipbook',engine='blender_mantaflow',project_id=asset['project_id'],asset_id=asset['id'],name=name+' flipbook',effective_config=config,
                              effective_config_hash=fingerprint(config),project_style_snapshot=project,timeout_seconds=7200,purpose='simulated_effect_flipbook'),db=db)
        result=dict(asset_id=asset['id'],job=job,preset=preset,preset_provenance=provenance)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',('fxflip:'+body.request_id,checksum,json.dumps(result)))
    return result


def execute(job,folder,worker):
    from .local_tools import executable
    p=job['payload'];config=p['effective_config'];blender=executable('blender')
    if not blender:raise ValueError('Blender executable not found')
    if fingerprint(config)!=p['effective_config_hash'] or store.digest(SCRIPT)!=config['script_sha256']:raise ValueError('Flipbook config/script checksum changed')
    output=folder/'output'
    request=dict(preset=config['preset'],look=config.get('look','stylized'),resolution=config['resolution'],frames=config['frames'],cell=config['cell'],samples=config['samples'],seed=config['seed'],color=config['color'],output=str(output))
    request_path=folder/'request.json';request_path.write_text(json.dumps(request,indent=2),encoding='utf-8')
    jobs.transition(job['id'],'POSTPROCESSING')
    with (folder/'worker.log').open('w',encoding='utf-8') as log:
        for phase,label in (('bake','Blender / Mantaflow gas simulation (CPU)'),('render','Blender / Cycles CPU flipbook render')):
            log.write(f'STAGE {label}\n');log.flush()
            process=subprocess.Popen([blender,'-b','-t','6','--factory-startup','--python-exit-code','1','--python',str(SCRIPT),'--','--request',str(request_path),'--phase',phase],stdout=log,stderr=subprocess.STDOUT)
            (folder/'process.json').write_text(json.dumps(dict(pid=process.pid,kind='fx_flipbook',phase=phase)))
            try:
                while process.poll() is None:
                    if worker.stop.is_set() or jobs.get(job['id'])['status']=='CANCELLED':
                        jobs.kill_tree(process)
                        if jobs.get(job['id'])['status']!='CANCELLED':jobs.transition(job['id'],'BLOCKED','Server stopped; retry runs the simulation again (no mid-bake resume)')
                        return
                    worker.stop.wait(.5)
            finally:
                if process.poll() is None:jobs.kill_tree(process)
            if process.returncode:raise RuntimeError(f'Blender {phase} exit {process.returncode}; inspect worker.log')
    jobs.transition(job['id'],'VALIDATING')
    report=json.loads((output/'flipbook.json').read_text(encoding='utf-8'));sheet=output/'flipbook.png'
    if not sheet.is_file() or not all(report['checks'].values()):raise ValueError(f"Flipbook checks failed: {report.get('checks')}")
    meta=dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],engine='blender_mantaflow',asset_type='vfx',preset=config['preset'],columns=report['columns'],rows=report['rows'],
              frames=report['frames'],cell_px=report['cell_px'],playback_fps=report['playback_fps'],blending=report['blending'],loop=report['loop'],
              license='AFS procedural simulation; Blender (GPL) output belongs to the user',artistic_approval=False)
    sheet_record=store.add_artifact(sheet,'fx_flipbook',f"{p.get('name','Effect')} / sprite sheet",meta)
    store.add_artifact(output/'flipbook.json','qa_report','Flipbook simulation and render report',dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],parent_id=sheet_record['id']))
    (folder/'manifest.json').write_text(json.dumps(dict(sheet_artifact=sheet_record['id'],sheet_sha256=sheet_record['sha256'])),encoding='utf-8')
    jobs.transition(job['id'],'REVIEW_REQUIRED')


@router.get('/assets/{asset_id}')
def workspace(asset_id:str):
    model=studio.asset(asset_id)
    if model.get('asset_type')!='vfx':raise HTTPException(400,'Asset is not an effect')
    with store.connect() as db:sheets=[store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE asset_id=? AND role='fx_flipbook' ORDER BY created_at",(asset_id,))]
    return dict(asset=model,sheets=sheets,jobs=[j for j in jobs.listing() if j['payload'].get('asset_id')==asset_id and j['payload']['kind']=='fx_flipbook'])
