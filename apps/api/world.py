"""World Plan approval, immutable source snapshots and native level jobs."""
import hashlib
import json
import os
import uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from . import store,studio,jobs
from .world_plan import WorldPlan,template,terrain
from engines.quality import fingerprint

router=APIRouter(prefix='/api/world')


class Preview(BaseModel):
    project_id:str
    name:str=Field(min_length=1,max_length=200)
    prompt:str=Field(default='',max_length=100000)
    width_m:float=Field(default=256,ge=64,le=512)
    depth_m:float=Field(default=256,ge=64,le=512)
    seed:int=Field(default=42,ge=0,le=4294967295)
    # Any project image (e.g. a character this map must suit); only its colours are used, never its shape.
    style_reference_id:str|None=None


@router.post('/preview-plan')
def preview(body:Preview):
    studio.project(body.project_id)
    plan=template(body.project_id,body.name,body.prompt,body.width_m,body.depth_m,body.seed)
    from .style_profile import terrain_colours
    seeded=terrain_colours(body.project_id,studio.project(body.project_id),[body.style_reference_id] if body.style_reference_id else ())
    if seeded:plan=plan.model_copy(update=seeded|dict(assumptions=plan.assumptions+['Terrain colours seeded from '+('the chosen reference image' if body.style_reference_id else 'the project style palette')+' ('+', '.join(seeded)+'); still provisional until plan approval']))
    _,_,_,qa=terrain(plan)
    return dict(plan=plan.model_dump(),qa=qa,planner='explicit deterministic template; prompt stored as context, not interpreted by AI',enqueued_jobs=0)


class SavePlan(BaseModel):
    plan:WorldPlan
    asset_id:str | None=None
    request_id:str=Field(min_length=8,max_length=100)


@router.post('/plans',status_code=201)
def save_plan(body:SavePlan):
    from engines.world_editor import prop_sources
    plan=body.plan;studio.project(plan.project_id)
    try:terrain(plan);prop_sources(plan)
    except (ValueError,KeyError,OSError) as exc:raise HTTPException(409,str(exc))
    if body.asset_id:
        value=studio.asset(body.asset_id)
        if value['project_id']!=plan.project_id or value.get('asset_type')!='map_environment':raise HTTPException(400,'World Plan belongs to a different game/asset type')
    else:
        identifier=uuid.uuid5(uuid.NAMESPACE_URL,'AFS-world-asset:'+plan.project_id+':'+body.request_id).hex
        value=dict(id=identifier,project_id=plan.project_id,asset_type='map_environment',name=plan.name,prompt=plan.prompt,original_prompt=plan.prompt,original_prompt_sha256=hashlib.sha256(plan.prompt.encode()).hexdigest(),category='Maps',reference_ids=[],settings={},
            favorite=False,status='Candidate',master_artifact_id=None,approvals=[],created_at=store.now(),updated_at=store.now())
    request_hash=fingerprint(body.model_dump());version=uuid.uuid5(uuid.NAMESPACE_URL,'AFS-world-plan:'+body.request_id).hex
    path=store.safe_path(f'projects/{plan.project_id}/assets/{value["id"]}/world_plans/{version}/world_plan.json')
    data=plan.model_dump_json(indent=2).encode();checksum=hashlib.sha256(data).hexdigest()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');cached=studio.cached(db,body.request_id,request_hash)
        if cached:return cached
        if body.asset_id:
            latest=db.execute('SELECT payload FROM assets WHERE id=?',(body.asset_id,)).fetchone()
            if not latest:raise HTTPException(404,'Map asset no longer exists')
            value=json.loads(latest['payload'])
            if value['project_id']!=plan.project_id or value.get('asset_type')!='map_environment':raise HTTPException(409,'Map belongs to a different project or asset type')
        if 'original_prompt' not in value:
            first=db.execute("SELECT * FROM artifacts WHERE asset_id=? AND role='world_plan' ORDER BY created_at LIMIT 1",(value['id'],)).fetchone()
            original=value.get('prompt','')
            if first:
                source=store.safe_path(first['relative_path'])
                if store.digest(source)!=first['sha256']:raise HTTPException(409,'Original World Plan checksum changed; cannot recover immutable prompt')
                original=json.loads(source.read_text(encoding='utf-8'))['prompt']
            value['original_prompt']=original
        value.setdefault('original_prompt_sha256',hashlib.sha256(value['original_prompt'].encode()).hexdigest())
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            if store.digest(path)!=checksum:raise HTTPException(409,'Immutable World Plan path already contains different bytes')
        else:
            temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                with temporary.open('xb') as stream:
                    stream.write(data);stream.flush();os.fsync(stream.fileno())
                temporary.replace(path)
            finally:temporary.unlink(missing_ok=True)
        metadata=dict(project_id=plan.project_id,asset_id=value['id'],schema_version='1.0',license='AFS procedural plan; library/model/reference rights separate',requires_approval=True)
        db.execute('INSERT INTO artifacts (id,role,name,relative_path,sha256,created_at,metadata,project_id,asset_id) VALUES (?,?,?,?,?,?,?,?,?)',
            (version,'world_plan',plan.name+' / World Plan',path.relative_to(store.DATA).as_posix(),checksum,store.now(),json.dumps(metadata),plan.project_id,value['id']))
        value.update(name=plan.name,updated_at=store.now());value['settings']['current_world_plan_id']=version
        db.execute('INSERT INTO assets VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(value['id'],plan.project_id,json.dumps(value)))
        artifact=store.artifact(db.execute('SELECT * FROM artifacts WHERE id=?',(version,)).fetchone());result=dict(asset_id=value['id'],artifact=artifact)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(body.request_id,request_hash,json.dumps(result)))
    return result


def plan_record(identifier):
    try:record=store.get_artifact(identifier)
    except KeyError:raise HTTPException(404,'World Plan not found')
    if record['role']!='world_plan':raise HTTPException(400,'Expected a saved World Plan')
    studio.project(record['project_id'])
    if store.digest(store.safe_path(record['relative_path']))!=record['sha256']:raise HTTPException(409,'World Plan checksum changed')
    return record


@router.post('/plans/{identifier}/approve')
def approve(identifier:str,body:studio.ConceptApproval):
    from engines.world_editor import code_hashes
    record=plan_record(identifier)
    if not body.reviewer.strip():raise HTTPException(400,'Reviewer is required')
    authorization=dict(artifact_id=identifier,sha256=record['sha256'],generator_hash=fingerprint(code_hashes()),reviewer=body.reviewer,
        notes=body.notes,created_at=store.now(),scope='this exact procedural layout/config only; not production artistic approval')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM assets WHERE id=?',(record['asset_id'],)).fetchone()
        if not row:raise HTTPException(404,'Map asset no longer exists')
        value=json.loads(row['payload']);entries=value.setdefault('settings',{}).setdefault('world_plan_approvals',[])
        if not any(all(a.get(k)==authorization[k] for k in ('artifact_id','sha256','generator_hash','reviewer','notes')) for a in entries):entries.append(authorization)
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(value),value['id']))
    return dict(status='PLAN_APPROVED',artifact_id=identifier,sha256=record['sha256'])



class Generate(BaseModel):
    request_id:str=Field(min_length=8,max_length=100)
    render_gpu:bool=True
    commercial:bool=False


@router.post('/plans/{identifier}/generate',status_code=201)
def generate(identifier:str,body:Generate):
    from engines.world_editor import effective_config,code_hashes
    record=plan_record(identifier);asset=studio.asset(record['asset_id'])
    if body.commercial:raise HTTPException(409,'Commercial World output blocked pending procedural/source/library/reference rights clearance')
    approval=any(a.get('artifact_id')==identifier and a.get('sha256')==record['sha256'] and a.get('generator_hash')==fingerprint(code_hashes()) for a in asset['settings'].get('world_plan_approvals',[]))
    if not approval:raise HTTPException(409,'Approve this exact World Plan and generator configuration before generation')
    try:config=effective_config(record,body.render_gpu)
    except (ValueError,KeyError,OSError) as exc:raise HTTPException(409,str(exc))
    request_hash=fingerprint(dict(plan_id=identifier,**body.model_dump()))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');cached=studio.cached(db,body.request_id,request_hash)
        if cached:return cached
        queued=jobs.enqueue(dict(kind='world_unity',engine='unity_world',project_id=record['project_id'],asset_id=record['asset_id'],artifact_id=identifier,use_gpu=body.render_gpu,
            effective_config=config,effective_config_hash=fingerprint(config),timeout_seconds=900,purpose='procedural_world_technical_evaluation',child_jobs=0),db=db)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(body.request_id,request_hash,json.dumps(queued)))
    return queued


@router.get('/assets/{identifier}')
def workspace(identifier:str):
    value=studio.asset(identifier)
    if value.get('asset_type')!='map_environment':raise HTTPException(400,'Asset is not a World Plan')
    with store.connect() as db:artifacts=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=? ORDER BY created_at',(identifier,))]
    from engines.world_editor import code_hashes
    generator=fingerprint(code_hashes())
    plans=[dict(artifact=a,plan=json.loads(store.safe_path(a['relative_path']).read_text(encoding='utf-8')),approval_current=any(r.get('artifact_id')==a['id'] and r.get('sha256')==a['sha256'] and r.get('generator_hash')==generator for r in value.get('settings',{}).get('world_plan_approvals',[]))) for a in artifacts if a['role']=='world_plan']
    with store.connect() as db:exports=[studio.output_files(dict(id=r['id'],**json.loads(r['payload']))) for r in db.execute('SELECT * FROM asset_exports WHERE asset_id=?',(identifier,))]
    return dict(asset=value,plans=plans,artifacts=artifacts,exports=exports,jobs=[j|dict(plan_id=j['payload']['artifact_id']) for j in jobs.listing() if j['payload'].get('asset_id')==identifier and j['payload']['kind']=='world_unity'])


class ExportWorld(BaseModel):
    job_id:str
    request_id:str=Field(min_length=8,max_length=100)


@router.post('/assets/{identifier}/export',status_code=201)
def export_world(identifier:str,body:ExportWorld):
    value=studio.asset(identifier)
    try:job=jobs.get(body.job_id)
    except KeyError:raise HTTPException(404,'World job not found')
    if value.get('asset_type')!='map_environment' or job['payload'].get('kind')!='world_unity' or job['payload'].get('asset_id')!=identifier or job['status']!='REVIEW_REQUIRED':raise HTTPException(409,'Select a validated native World output belonging to this asset')
    request_hash=fingerprint(dict(asset_id=identifier,**body.model_dump()))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');previous=studio.cached(db,body.request_id,request_hash)
        if previous:return studio.output_files(previous)
        result=dict(id=uuid.uuid4().hex,asset_id=identifier,artifact_id=job['payload']['artifact_id'],native_world_job_id=job['id'],preset='Unity World',format='unitypackage',created_at=store.now(),validation='PASS_EDITOR_VALIDATION',files=[])
        db.execute('INSERT INTO asset_exports VALUES (?,?,?)',(result['id'],identifier,json.dumps({k:v for k,v in result.items() if k!='id'})))
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(body.request_id,request_hash,json.dumps(result)))
    return studio.output_files(result)


class AutoWorld(Preview):
    asset_id:str|None=None
    request_id:str=Field(min_length=8,max_length=100)


@router.post('/auto',status_code=201)
def auto(body:AutoWorld):
    """Prompt -> map in one click: plan, save, automatic technical layout approval, native build (same steps as the manual flow).

    The automatic approval only records that the deterministic layout passed its terrain/prop checks; it is not an
    artistic approval, and the manual Review steps remain available for anyone who wants to check the layout first."""
    from engines.world_editor import code_hashes
    preview_body=Preview(**{k:getattr(body,k) for k in Preview.model_fields})
    plan=WorldPlan.model_validate(preview(preview_body)['plan'])
    saved=save_plan(SavePlan(plan=plan,asset_id=body.asset_id,request_id=body.request_id+':plan'))
    record=saved['artifact'];asset=studio.asset(saved['asset_id'])
    authorization=dict(artifact_id=record['id'],sha256=record['sha256'],generator_hash=fingerprint(code_hashes()),reviewer='Auto (technical layout checks)',
        notes='Automatic: terrain and prop checks passed. Not an artistic approval.',created_at=store.now(),kind='automatic',
        scope='this exact procedural layout/config only; not production artistic approval')
    entries=asset.setdefault('settings',{}).setdefault('world_plan_approvals',[])
    if not any(a.get('artifact_id')==record['id'] and a.get('kind')=='automatic' for a in entries):entries.append(authorization);studio.save_asset(asset)
    job=generate(record['id'],Generate(request_id=body.request_id+':build'))
    return dict(asset_id=saved['asset_id'],plan_id=record['id'],build=job,approval='automatic technical')
