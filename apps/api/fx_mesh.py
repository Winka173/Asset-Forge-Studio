"""Mesh effects (shockwave ring, shield bubble, ground crack decal, projectile trail) as GLB through the shared queue.

A CPU job: one Blender process builds the mesh, alpha texture and emissive material (pipelines/blender/fx_meshes.py).
"""
import json
import subprocess
import uuid
from typing import Literal
from pydantic import BaseModel,Field
from fastapi import APIRouter,HTTPException
from . import store,studio,jobs
from engines.quality import fingerprint

router=APIRouter(prefix='/api/fx/mesh')
SCRIPT=store.ROOT/'pipelines/blender/fx_meshes.py'
NAMES={'shockwave':'Shockwave ring','shield':'Shield bubble','crack':'Ground crack','trail':'Projectile trail'}


class MeshEffect(BaseModel):
    project_id:str
    kind:Literal['shockwave','shield','crack','trail']
    color:str=Field(default='#ffb347',pattern=r'^#[0-9a-fA-F]{6}$')
    seed:int=Field(default=42,ge=0,le=2147483647)
    request_id:str=Field(min_length=8,max_length=100)


@router.post('',status_code=201)
def create(body:MeshEffect):
    from .local_tools import executable
    if not executable('blender'):raise HTTPException(409,'Blender is not installed')
    studio.project(body.project_id)
    config=dict(schema_version=1,engine_id='blender_fx_mesh',kind=body.kind,color=body.color,seed=body.seed,script_sha256=store.digest(SCRIPT),artistic_approval=False)
    checksum=fingerprint(body.model_dump())
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');prior=studio.cached(db,'fxmesh:'+body.request_id,checksum)
        if prior:return prior
        asset=dict(id=uuid.uuid5(uuid.NAMESPACE_URL,'afs-fxmesh:'+body.project_id+':'+body.request_id).hex,project_id=body.project_id,asset_type='vfx',name=NAMES[body.kind],prompt='',
                   original_prompt='',category='Effects',reference_ids=[],settings={},favorite=False,status='Candidate',master_artifact_id=None,approvals=[],created_at=store.now())
        db.execute('INSERT INTO assets VALUES (?,?,?) ON CONFLICT(id) DO NOTHING',(asset['id'],body.project_id,json.dumps(asset)))
        job=jobs.enqueue(dict(kind='fx_mesh',engine='blender_fx_mesh',project_id=body.project_id,asset_id=asset['id'],name=NAMES[body.kind],effective_config=config,
                              effective_config_hash=fingerprint(config),timeout_seconds=600),db=db)
        result=dict(asset_id=asset['id'],job=job)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',('fxmesh:'+body.request_id,checksum,json.dumps(result)))
    return result


@router.get('')
def listing(project_id:str):
    with store.connect() as db:return [store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE project_id=? AND role='fx_mesh' ORDER BY created_at DESC",(project_id,))]


def execute(job,folder,worker):
    from .local_tools import executable
    p=job['payload'];config=p['effective_config'];blender=executable('blender')
    if fingerprint(config)!=p['effective_config_hash'] or store.digest(SCRIPT)!=config['script_sha256']:raise ValueError('Mesh effect config/script checksum changed')
    request=dict(kind=config['kind'],color=config['color'],seed=config['seed'],output=str(folder/'output'));(folder/'request.json').write_text(json.dumps(request),encoding='utf-8')
    jobs.transition(job['id'],'POSTPROCESSING')
    with (folder/'worker.log').open('w',encoding='utf-8') as log:
        log.write('STAGE Blender / mesh effect\n');log.flush()
        code=subprocess.call([blender,'-b','--factory-startup','--python-exit-code','1','--python',str(SCRIPT),'--','--request',str(folder/'request.json')],stdout=log,stderr=subprocess.STDOUT,timeout=600)
    if code:raise RuntimeError(f'Blender exited {code}; inspect worker.log')
    jobs.transition(job['id'],'VALIDATING')
    report=json.loads((folder/'output/fx_mesh.json').read_text(encoding='utf-8'))
    if not all(report['checks'].values()):raise ValueError(f"Mesh effect checks failed: {report['checks']}")
    store.add_artifact(report['glb'],'fx_mesh',f"{NAMES[config['kind']]} (GLB)",dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],kind=config['kind'],color=config['color'],
                       animated=report['animated'],notes=report['notes'],artistic_approval=False))
    jobs.transition(job['id'],'REVIEW_REQUIRED')
