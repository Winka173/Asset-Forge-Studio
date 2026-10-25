"""Text-to-motion clips with Kimodo (local, NVIDIA) through the shared GPU queue.

One job: Kimodo generates SOMA 77-joint motion (BVH/NPZ, engines/kimodo_worker.py), then Blender converts the BVH
to FBX and GLB clips (pipelines/blender/bvh_to_clip.py). Skeleton-only clips; retargeting onto an AFS-rigged
character is not implemented. Experimental until a real run is recorded.
"""
import json
import subprocess
import uuid
from pathlib import Path
from pydantic import BaseModel,Field
from fastapi import APIRouter,HTTPException,UploadFile,File,Form
from . import store,studio,jobs
from engines.quality import fingerprint

router=APIRouter(prefix='/api/motion')
PYTHON=store.WORKSPACE/'.local/envs/kimodo/Scripts/python.exe'
CODE=Path.home()/'Tools/kimodo/code'
MODELS=Path.home()/'Tools/kimodo/models'
WORKER=store.ROOT/'engines/kimodo_worker.py'
CONVERT=store.ROOT/'pipelines/blender/bvh_to_clip.py'
RETARGET=store.ROOT/'pipelines/blender/retarget_clip.py'
LIMITATIONS=['Experimental: first real run 2026-10-25 (3 s clip, 22 s, 1.1 GB VRAM); motion quality needs artist review','Skeleton-only clip on the SOMA 77-joint skeleton (Hips/Spine1/LeftArm naming)',
             'Unity Humanoid mapping expected from the joint names, not tested','Applying to an AFS auto-rigged character finds its bones by shape (biped only); fingers keep their rest pose',
             'Auto-rig skin weights can drag worn or held props (swords, capes) with the arms on large motions; review the result']


def installed():
    required=[PYTHON,CODE/'kimodo/scripts/generate.py',MODELS/'Kimodo-SOMA-RP-v1.2/model.safetensors',MODELS/'llm2vec-mntp/adapter_model.safetensors',
              MODELS/'llm2vec-supervised/adapter_model.safetensors',MODELS/'Meta-Llama-3-8B-Instruct/model-00004-of-00004.safetensors']
    return all(p.is_file() for p in required)


class Motion(BaseModel):
    project_id:str
    prompt:str=Field(min_length=3,max_length=2000)
    name:str=Field(default='',max_length=200)
    duration:float=Field(default=4.0,ge=1.0,le=10.0)
    seed:int=Field(default=42,ge=0,le=2147483647)
    # Optional rigged character (role 'rigged' artifact) to receive the motion.
    character_artifact_id:str|None=None
    # Or an uploaded character still being auto-rigged: the motion waits for that rig job.
    rig_job_id:str|None=None
    asset_id:str|None=None
    request_id:str=Field(min_length=8,max_length=100)


@router.get('/characters')
def characters(project_id:str):
    """Auto-rigged characters in this game that a clip can be applied to."""
    with store.connect() as db:rows=[store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE project_id=? AND role='rigged' ORDER BY created_at DESC",(project_id,))]
    return [dict(id=a['id'],name=a['name'],asset_id=a['metadata'].get('asset_id')) for a in rows]


def _asset(project_id,name,request_key):
    asset=dict(id=uuid.uuid5(uuid.NAMESPACE_URL,'afs-motion-char:'+project_id+':'+request_key).hex,project_id=project_id,asset_type='static_3d',name=name,prompt='',original_prompt='',
               category='Characters',reference_ids=[],settings={},favorite=False,status='Candidate',master_artifact_id=None,approvals=[],created_at=store.now())
    with store.connect() as db:db.execute('INSERT INTO assets VALUES (?,?,?) ON CONFLICT(id) DO NOTHING',(asset['id'],project_id,json.dumps(asset)))
    return asset


@router.post('/upload',status_code=201)
async def upload(file:UploadFile=File(...),project_id:str=Form(...)):
    """Bring your own character GLB: a skinned one is used as is, an unrigged one is auto-rigged (UniRig) first."""
    from . import rigging
    studio.project(project_id)
    name=Path(file.filename or 'character.glb').stem[:80] or 'Character';data=await file.read(500_000_001)
    if len(data)>500_000_000:raise HTTPException(413,'GLB is larger than 500 MB')
    if data[:4]!=b'glTF':raise HTTPException(400,'Upload a binary .glb file')
    import hashlib;digest=hashlib.sha256(data).hexdigest();asset=_asset(project_id,name,digest)
    target=store.safe_path(f'projects/{project_id}/assets/{asset["id"]}/uploads/{digest[:16]}.glb');target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():target.write_bytes(data)
    facts=rigging.joints(target);skinned=bool(facts['skins'] and facts['joints']>=2 and facts['skinned_primitives'])
    with store.connect() as db:row=db.execute('SELECT * FROM artifacts WHERE relative_path=?',(target.relative_to(store.DATA).as_posix(),)).fetchone()
    record=store.artifact(row) if row else store.add_artifact(target,'rigged' if skinned else 'character_source',f'{name} / '+('uploaded rigged' if skinned else 'uploaded model'),
                                                               dict(project_id=project_id,asset_id=asset['id'],origin='user_upload',**facts))
    if skinned or record['role']=='rigged':return dict(artifact_id=record['id'],rigged=True,name=name)
    if not rigging.installed():raise HTTPException(409,'This GLB has no skeleton and the local auto-rigger (UniRig) is not installed')
    existing=next((j for j in jobs.listing() if j['payload'].get('kind')=='rig' and j['payload'].get('artifact_id')==record['id']),None)
    job=existing or jobs.enqueue(dict(kind='rig',engine=rigging.ENGINE,project_id=project_id,asset_id=asset['id'],artifact_id=record['id'],source_sha256=record['sha256'],seed=12345,timeout_seconds=1800,name=name+' auto-rig'))
    return dict(artifact_id=record['id'],rigged=False,rig_job_id=job['id'],name=name)


@router.get('/capabilities')
def capabilities():
    return dict(installed=installed(),engine='kimodo-soma-rp-v1.2',license='Code Apache-2.0; weights NVIDIA Open Model License; text encoder Llama 3 Community License',
                needs=dict(vram_gb='under 3 (text encoder on CPU)',free_ram_gb=20,disk_gb=18),outputs=['glb','fbx','bvh','npz'],limitations=LIMITATIONS)


@router.post('',status_code=201)
def create(body:Motion):
    if not installed():raise HTTPException(409,'Kimodo is not installed. Run scripts/install_kimodo.sh (about 18 GB of weights).')
    studio.project(body.project_id);character=None
    if body.character_artifact_id:
        character=store.get_artifact(body.character_artifact_id)
        if character['role']!='rigged' or character['metadata'].get('project_id')!=body.project_id:raise HTTPException(409,'Choose a rigged character from this game')
    elif body.rig_job_id:
        rig=jobs.get(body.rig_job_id)
        if rig['payload'].get('kind')!='rig' or rig['payload'].get('project_id')!=body.project_id:raise HTTPException(409,'Unknown auto-rig job for this game')
    name=body.name.strip() or body.prompt.strip().split('\n')[0][:80]
    # Upstream defaults (100 diffusion steps, 30 fps); the scheduler never lowers them.
    config=dict(schema_version=1,engine_id='kimodo-soma-rp-v1.2',stage='text_to_motion',input_prompt=body.prompt,duration=body.duration,seed=body.seed,steps=100,fps=30,
                text_encoder_device='cpu',worker_sha256=store.digest(WORKER),convert_sha256=store.digest(CONVERT),artistic_approval=False,
                **(dict(character_artifact_id=character['id'],character_sha256=character['sha256'],retarget_sha256=store.digest(RETARGET)) if character else {}),
                **(dict(character_from_rig_job=body.rig_job_id,retarget_sha256=store.digest(RETARGET)) if body.rig_job_id and not character else {}))
    checksum=fingerprint(body.model_dump())
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');prior=studio.cached(db,'motion:'+body.request_id,checksum)
        if prior:return prior
        if body.asset_id:
            row=db.execute('SELECT payload FROM assets WHERE id=?',(body.asset_id,)).fetchone()
            if not row:raise HTTPException(404,'Animation asset no longer exists')
            asset=json.loads(row['payload'])
            if asset['project_id']!=body.project_id or asset.get('asset_type')!='animation':raise HTTPException(409,'Animation asset belongs to another game or asset type')
        else:
            asset=dict(id=uuid.uuid5(uuid.NAMESPACE_URL,'afs-motion:'+body.project_id+':'+body.request_id).hex,project_id=body.project_id,asset_type='animation',name=name,prompt=body.prompt,
                       original_prompt=body.prompt,category='Animations',reference_ids=[],settings={},favorite=False,status='Candidate',master_artifact_id=None,approvals=[],created_at=store.now())
        asset['updated_at']=store.now()
        db.execute('INSERT INTO assets VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(asset['id'],asset['project_id'],json.dumps(asset)))
        job=jobs.enqueue(dict(kind='motion',engine='kimodo',project_id=asset['project_id'],asset_id=asset['id'],name=name+' motion',effective_config=config,
                              effective_config_hash=fingerprint(config),timeout_seconds=3600,purpose='text_to_motion_clip',
                              **(dict(depends_on=[body.rig_job_id]) if config.get('character_from_rig_job') else {})),db=db)
        result=dict(asset_id=asset['id'],job=job)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',('motion:'+body.request_id,checksum,json.dumps(result)))
    return result


@router.get('/assets/{asset_id}')
def workspace(asset_id:str):
    model=studio.asset(asset_id)
    if model.get('asset_type')!='animation':raise HTTPException(400,'Asset is not an animation clip')
    with store.connect() as db:clips=[store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE asset_id=? AND role IN ('animation_clip','animation_clip_fbx','motion_source','animated_character') ORDER BY created_at",(asset_id,))]
    return dict(asset=model,clips=clips,jobs=[j for j in jobs.listing() if j['payload'].get('asset_id')==asset_id and j['payload']['kind']=='motion'],limitations=LIMITATIONS)


def _run(command,cwd,log,job,worker,label):
    log.write(f'STAGE {label}\n');log.flush()
    process=subprocess.Popen(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
    try:
        while process.poll() is None:
            if worker.stop.is_set() or jobs.get(job['id'])['status']=='CANCELLED':
                jobs.kill_tree(process)
                if jobs.get(job['id'])['status']!='CANCELLED':jobs.transition(job['id'],'BLOCKED','Server stopped; retry generates the motion again (no mid-inference resume)')
                return False
            worker.stop.wait(.5)
    finally:
        if process.poll() is None:jobs.kill_tree(process)
    if process.returncode:raise RuntimeError(f'{label} exited {process.returncode}; inspect worker.log')
    return True


def execute(job,folder,worker):
    from .local_tools import executable
    p=job['payload'];config=p['effective_config'];blender=executable('blender')
    if not blender:raise ValueError('Blender executable not found')
    if not installed():raise ValueError('Kimodo environment or weights missing')
    if fingerprint(config)!=p['effective_config_hash'] or store.digest(WORKER)!=config['worker_sha256'] or store.digest(CONVERT)!=config['convert_sha256']:raise ValueError('Motion config/script checksum changed')
    output=folder/'output';request=dict(models_path=str(MODELS),prompt=config['input_prompt'],duration=config['duration'],seed=config['seed'],steps=config['steps'],output=str(output/'kimodo'))
    request_path=folder/'request.json';request_path.write_text(json.dumps(request,indent=2),encoding='utf-8')
    with (folder/'worker.log').open('w',encoding='utf-8') as log:
        if not _run([str(PYTHON),'-B','-u',str(WORKER),'--request',str(request_path)],CODE,log,job,worker,'Kimodo / text-to-motion'):return
        jobs.transition(job['id'],'POSTPROCESSING')
        clip=p.get('name','motion').replace(' motion','').strip() or 'motion'
        safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in clip)[:60] or 'motion'
        if not _run([blender,'-b','--factory-startup','--python-exit-code','1','--python',str(CONVERT),'--','--bvh',str(output/'kimodo/motion.bvh'),'--output',str(output/'clip'),'--name',safe],
                    store.ROOT,log,job,worker,'Blender / BVH to FBX and GLB clip'):return
    jobs.transition(job['id'],'VALIDATING')
    report=json.loads((output/'clip/clip.json').read_text(encoding='utf-8'));motion=json.loads((output/'kimodo/motion_report.json').read_text(encoding='utf-8'))
    if not all(report['checks'].values()) or report['frames']<2:raise ValueError(f"Clip checks failed: {report['checks']}, frames {report['frames']}")
    meta=dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],engine='kimodo',asset_type='animation',frames=report['frames'],fps=report['fps'],joints=report['joints'],
              skeleton='SOMA 77',peak_vram_gib=motion['peak_vram_gib'],license='NVIDIA Open Model License (Kimodo weights)',artistic_approval=False,limitations=LIMITATIONS)
    glb=store.add_artifact(report['glb'],'animation_clip',f'{clip} / clip (GLB)',meta)
    store.add_artifact(report['fbx'],'animation_clip_fbx',f'{clip} / clip (FBX)',meta|dict(parent_id=glb['id']))
    store.add_artifact(output/'kimodo/motion.bvh','motion_source',f'{clip} / motion (BVH)',meta|dict(parent_id=glb['id']))
    store.add_artifact(output/'clip/clip.json','qa_report','Motion clip report',dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],parent_id=glb['id']))
    if config.get('character_from_rig_job'):  # the rig finished before this job was admitted; bind its output now
        rigged=next((a for a in _artifacts_of_job(config['character_from_rig_job']) if a['role']=='rigged'),None)
        if not rigged:raise ValueError('The auto-rig job produced no rigged character')
        config=dict(config,character_artifact_id=rigged['id'],character_sha256=rigged['sha256'])
    if config.get('character_artifact_id') and not retarget(job,folder,worker,config,clip,safe,glb,meta,blender):return
    jobs.transition(job['id'],'REVIEW_REQUIRED')


def _artifacts_of_job(job_id):
    with store.connect() as db:return [store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE metadata LIKE ?',(f'%"job_id": "{job_id}"%',))]


def retarget(job,folder,worker,config,clip,safe,glb,meta,blender):
    """Apply the clip to the chosen auto-rigged character: its mesh, skin and textures with one new clip."""
    character=store.get_artifact(config['character_artifact_id']);source=store.safe_path(character['relative_path'])
    if store.digest(source)!=config['character_sha256'] or store.digest(RETARGET)!=config['retarget_sha256']:raise ValueError('Character or retarget script changed after admission')
    output=folder/'output/character'
    with (folder/'worker.log').open('a',encoding='utf-8') as log:
        if not _run([blender,'-b','--factory-startup','--python-exit-code','1','--python',str(RETARGET),'--','--character',str(source),'--bvh',str(folder/'output/kimodo/motion.bvh'),'--output',str(output),'--name',safe],
                    store.ROOT,log,job,worker,'Blender / apply motion to the rigged character'):return False
    report=json.loads((output/'retarget.json').read_text(encoding='utf-8'))
    if not all(report['checks'].values()):raise ValueError(f"Retarget checks failed: {report['checks']}")
    animated=store.add_artifact(report['glb'],'animated_character',f"{clip} / on {character['name']}",meta|dict(parent_id=glb['id'],character_artifact_id=character['id'],bone_map=report['bone_map'],
                                skeleton='AFS auto-rig (UniRig)',max_extremity_travel_m=report['max_extremity_travel_m']))
    store.add_artifact(output/'retarget.json','qa_report','Retarget report',dict(project_id=meta['project_id'],asset_id=meta['asset_id'],job_id=job['id'],parent_id=animated['id']))
    return True
