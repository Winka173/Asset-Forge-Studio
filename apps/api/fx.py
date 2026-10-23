"""Editable procedural effect recipes with real Unity output through the shared queue."""
import hashlib
import json
import re
import uuid
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from fastapi import APIRouter,HTTPException
from . import store,studio,jobs
from engines.quality import fingerprint

router=APIRouter(prefix='/api/fx')

class Recipe(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version:Literal['1.0']='1.0'
    project_id:str
    name:str=Field(min_length=1,max_length=200)
    prompt:str=Field(default='',max_length=10000)
    element:Literal['fire','ice','lightning','wind','earth','poison']='fire'
    duration:float=Field(default=2.4,ge=1.2,le=6)
    radius:float=Field(default=1.8,ge=1.3,le=4)
    trail_lifetime:float=Field(default=.18,ge=.04,le=.4)
    intensity:float=Field(default=1.8,ge=.1,le=4)
    segments:int=Field(default=48,ge=12,le=128)
    particle_count:int=Field(default=12,ge=0,le=24)
    seed:int=Field(default=42,ge=0,le=2147483647)
    # Optional project accent for the secondary sparks; the trail keeps the element colour (fire stays fire).
    accent_color:str|None=Field(default=None,pattern=r'^#[0-9a-fA-F]{6}$')
    accent_strength:float=Field(default=.25,ge=0,le=.5)

class Build(BaseModel):
    recipe:Recipe
    asset_id:str|None=None
    request_id:str=Field(min_length=8,max_length=100)

class Plan(BaseModel):
    project_id:str
    prompt:str=Field(default='',max_length=10000)
    name:str=Field(default='',max_length=200)
    overrides:dict=Field(default_factory=dict)
    base_recipe_id:str|None=None

@router.post('/plan')
def plan(body:Plan):
    studio.project(body.project_id)
    aliases={'fire':r'\bfire\b|\bl\u1eeda\b','ice':r'\bice\b|\bfrost\b|\bb\u0103ng\b','lightning':r'\blightning\b|\bs\u00e9t\b','wind':r'\bwind\b|\bgi\u00f3\b','earth':r'\bearth\b|\b\u0111\u1ea5t\b','poison':r'\bpoison\b|\b\u0111\u1ed9c\b'}
    matches=[element for element,pattern in aliases.items() if re.search(pattern,body.prompt,re.I)]
    if len(matches)>1 and 'element' not in body.overrides:raise HTTPException(422,'Choose one element for this recipe. Multi-element composition is not implemented.')
    values={};provenance={}
    if body.base_recipe_id:
        record=studio.scoped_artifact(body.base_recipe_id,body.project_id)
        if record['role']!='fx_recipe':raise HTTPException(400,'Expected an existing effect recipe')
        file=store.safe_path(record['relative_path'])
        if store.digest(file)!=record['sha256']:raise HTTPException(409,'Inherited effect recipe changed')
        values=Recipe.model_validate_json(file.read_text()).model_dump()
        provenance={k:dict(kind='inherited',source='Recipe '+record['sha256']) for k in values}
    values.update(project_id=body.project_id,name=body.name.strip() or values.get('name') or ((matches[0] if matches else 'fire').title()+' sword slash'),prompt=body.prompt)
    provenance.setdefault('element',dict(kind='defaulted',source='Fire slash template'))
    if matches:values['element']=matches[0];provenance['element']=dict(kind='explicit',source='Recognized element in original prompt')
    duration=re.search(r'\b(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s|gi\u00e2y)\b',body.prompt,re.I)
    if duration:values['duration']=float(duration[1]);provenance['duration']=dict(kind='explicit',source='Duration in original prompt')
    if 'accent_color' not in values:
        from .style_profile import accent_colour
        accent=accent_colour(body.project_id,studio.project(body.project_id))
        if accent:values['accent_color']=accent;provenance['accent_color']=dict(kind='inferred',source='Most saturated colour of the project style palette')
    allowed=set(Recipe.model_fields)-{'schema_version','project_id','prompt','name'}
    if set(body.overrides)-allowed:raise HTTPException(422,'Unsupported effect override')
    for key,value in body.overrides.items():values[key]=value;provenance[key]=dict(kind='explicit',source='Advanced effect setting')
    try:recipe=Recipe.model_validate(values)
    except ValueError:raise HTTPException(422,'Effect settings are outside the supported recipe ranges')
    for key in allowed:provenance.setdefault(key,dict(kind='defaulted',source='Maximum procedural effect preset'))
    return dict(recipe=recipe.model_dump(),provenance=provenance,method='Deterministic keyword/duration extraction; arbitrary motion/style instructions remain original context, not AI interpretation',enqueued_jobs=0)

@router.get('/capabilities')
def capabilities():
    from engines.unity_editor import probe
    runtime=probe()
    return dict(installed=runtime['installed'],unity_version=runtime['version'],pipeline=runtime['render_pipeline'],elements=['fire','ice','lightning','wind','earth','poison'],
                method='Deterministic editable swept-blade mesh, shader and accent particles; no AI inference',
                outputs=['unitypackage','editable_runtime_sources','recipe_json','gpu_frame_previews','cold_reopen_report'],
                constraints=['Procedural sword motion is a demonstration, not humanoid animation or retargeting','Built-in pinned Unity profile only','No GLB replacement for realtime shaders/behavior','No target-player performance or artistic acceptance claim'])

@router.post('/build',status_code=201)
def build(body:Build):
    from engines.fx_editor import config_for
    project=studio.project(body.recipe.project_id)
    profile=project.get('engine_profiles',{}).get('unity',{})
    if profile and (profile.get('version','6000.4.8f1')!='6000.4.8f1' or profile.get('render_pipeline','Built-in')!='Built-in'):raise HTTPException(409,'This effect requires the tested Unity 6000.4.8f1 / Built-in profile')
    if body.asset_id:
        asset=studio.asset(body.asset_id)
        if asset['project_id']!=body.recipe.project_id or asset.get('asset_type')!='vfx':raise HTTPException(409,'Effect asset belongs to another game or asset type')
    else:
        asset=dict(id=uuid.uuid5(uuid.NAMESPACE_URL,'afs-fx:'+body.recipe.project_id+':'+body.request_id).hex,project_id=body.recipe.project_id,asset_type='vfx',name=body.recipe.name,prompt=body.recipe.prompt,original_prompt=body.recipe.prompt,category='Effects',reference_ids=[],settings={},favorite=False,status='Candidate',master_artifact_id=None,approvals=[],created_at=store.now())
    checksum=fingerprint(body.model_dump());version=uuid.uuid5(uuid.NAMESPACE_URL,'afs-fx-recipe:'+body.request_id).hex
    data=body.recipe.model_dump_json(indent=2).encode();source_hash=hashlib.sha256(data).hexdigest()
    try:config=config_for(body.recipe.model_dump(),source_hash)
    except ValueError as e:raise HTTPException(409,str(e))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');prior=studio.cached(db,'fx:'+body.request_id,checksum)
        if prior:return prior
        if body.asset_id:
            latest=db.execute('SELECT payload FROM assets WHERE id=?',(body.asset_id,)).fetchone()
            if not latest:raise HTTPException(404,'Effect asset no longer exists')
            # Preserve review/history updates made while probing the native engine.
            asset=json.loads(latest['payload'])
        file=store.safe_path(f'projects/{asset["project_id"]}/assets/{asset["id"]}/fx_recipes/{version}/recipe.json');file.parent.mkdir(parents=True,exist_ok=True)
        if file.exists() and store.digest(file)!=source_hash:raise HTTPException(409,'Immutable recipe path changed')
        if not file.exists():file.write_bytes(data)
        metadata=dict(project_id=asset['project_id'],asset_id=asset['id'],asset_type='vfx',license='AFS procedural source; no third-party model weights or image inputs',project_style_snapshot=project)
        db.execute('INSERT INTO artifacts (id,role,name,relative_path,sha256,created_at,metadata,project_id,asset_id) VALUES (?,?,?,?,?,?,?,?,?)',(version,'fx_recipe',body.recipe.name+' / recipe',file.relative_to(store.DATA).as_posix(),source_hash,store.now(),json.dumps(metadata),asset['project_id'],asset['id']))
        asset.update(name=body.recipe.name,updated_at=store.now());asset.setdefault('settings',{})['current_fx_recipe_id']=version
        asset.setdefault('fx_recipe_versions',[]).append(dict(artifact_id=version,sha256=source_hash,created_at=store.now(),original_prompt_preserved=True))
        db.execute('INSERT INTO assets VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(asset['id'],asset['project_id'],json.dumps(asset)))
        job=jobs.enqueue(dict(kind='fx_unity',engine='unity_fx',project_id=asset['project_id'],asset_id=asset['id'],artifact_id=version,use_gpu=True,effective_config=config,effective_config_hash=fingerprint(config),timeout_seconds=900,purpose='procedural_effect_technical_validation'),db=db)
        result=dict(asset_id=asset['id'],recipe_id=version,job=job)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',('fx:'+body.request_id,checksum,json.dumps(result)))
    return result

class CandidateBuild(Build):
    count:int=Field(default=1,ge=1,le=5)


@router.post('/build-candidates',status_code=201)
def build_candidates(body:CandidateBuild):
    """Durable admission of seed alternatives, all using the existing single GPU queue.

    Reserving the request before the first child makes a retry after partial
    admission safe. It never changes recipe quality or creates five asset identities.
    """
    studio.project(body.recipe.project_id)
    request_key='fx-candidates:'+body.request_id;checksum=fingerprint(body.model_dump())
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');prior=studio.cached(db,request_key,checksum)
        if prior and prior.get('state')=='admitted':return prior
        if not prior:db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(request_key,checksum,json.dumps(dict(state='admitting'))))
    asset_id=body.asset_id;results=[]
    group=uuid.uuid5(uuid.NAMESPACE_URL,'afs-fx-candidates:'+body.recipe.project_id+':'+body.request_id).hex
    for index in range(body.count):
        recipe=body.recipe.model_copy(update=dict(seed=(body.recipe.seed+index)%2147483648))
        child_id=uuid.uuid5(uuid.NAMESPACE_URL,'afs-fx-child:'+group+':'+str(index)).hex
        child=build(Build(recipe=recipe,asset_id=asset_id,request_id=child_id))
        asset_id=child['asset_id'];results.append(child)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT metadata FROM artifacts WHERE id=?',(child['recipe_id'],)).fetchone()
            metadata=json.loads(row['metadata']);metadata.update(candidate_group=group,candidate_index=index+1,candidate_count=body.count)
            db.execute('UPDATE artifacts SET metadata=? WHERE id=?',(json.dumps(metadata),child['recipe_id']))
    result=dict(state='admitted',asset_id=asset_id,candidate_group=group,count=len(results),results=results,quality='Maximum',gpu_concurrency=1)
    with store.connect() as db:db.execute('UPDATE studio_requests SET response=? WHERE id=?',(json.dumps(result),request_key))
    return result


@router.get('/assets/{asset_id}')
def workspace(asset_id:str):
    model=studio.asset(asset_id)
    if model.get('asset_type')!='vfx':raise HTTPException(400,'Asset is not a realtime effect')
    with store.connect() as db:artifacts=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=? ORDER BY created_at',(asset_id,))]
    recipes=[dict(artifact=a,recipe=json.loads(store.safe_path(a['relative_path']).read_text())) for a in artifacts if a['role']=='fx_recipe']
    return dict(asset=model,recipes=recipes,artifacts=artifacts,jobs=[j for j in jobs.listing() if j['payload'].get('asset_id')==asset_id and j['payload']['kind']=='fx_unity'])
