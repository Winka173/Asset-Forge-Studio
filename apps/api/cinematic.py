"""Pinned multi-GLB cinematic snapshots over the existing Library and worker."""
import json
import math
import uuid
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator,model_serializer
from . import store,studio,jobs
from .inspection import inspect_glb
from engines.quality import fingerprint
from engines.cinematic_audio import Cue

router=APIRouter(prefix='/api/cinematics')
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Object(Strict):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    name:str=Field(min_length=1,max_length=200)
    asset_id:str
    artifact_id:str
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    parent_id:str|None=None
    tag:Literal['subject','hero','boss','crystal','environment','prop']='prop'
    position:tuple[float,float,float]=(0,0,0)
    rotation:tuple[float,float,float]=(0,0,0)
    scale:tuple[float,float,float]=(1,1,1)
    visible:bool=True
    @model_validator(mode='after')
    def sane(self):
        if any(abs(v)>100000 for v in (*self.position,*self.rotation)) or any(not .0001<=v<=10000 for v in self.scale):raise ValueError('Transform outside supported scene range')
        return self
class Shot(Strict):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    name:str=Field(min_length=1,max_length=120)
    duration:float=Field(default=4,gt=0,le=30)
    movement:Literal['orbit','dolly']='orbit'
    target_id:str|None=None
    distance:float=Field(default=12,gt=.01,le=10000)
    elevation:float=Field(default=25,ge=0,le=80)
    azimuth:float=Field(default=35,ge=-360,le=360)
    amount:float=Field(default=30,ge=-180,le=180)
    source_start_frame:int=Field(default=0,ge=0,le=9000)
    motion_duration:float|None=Field(default=None,gt=0,le=30)
    look:Literal['inherit','violet_reveal']='inherit'
    @model_serializer(mode='wrap')
    def compatible(self,handler):
        data=handler(self)
        # Keep old snapshots/request fingerprints compatible when new fields are unused.
        if self.source_start_frame==0:data.pop('source_start_frame',None)
        if self.motion_duration is None:data.pop('motion_duration',None)
        if self.look=='inherit':data.pop('look',None)
        return data
class Scene(Strict):
    schema_version:Literal[1]=1
    project_id:str
    name:str=Field(min_length=1,max_length=200)
    prompt:str=Field(default='',max_length=100000)
    coordinate_system:Literal['glTF Y-up meters']='glTF Y-up meters'
    objects:list[Object]=Field(min_length=1,max_length=500)
    shots:list[Shot]=Field(min_length=1,max_length=30)
    lighting:Literal['studio','moonlight']='studio'
    ground:bool=True
    width:int=Field(default=1920,ge=320,le=3840)
    height:int=Field(default=1080,ge=180,le=2160)
    fps:Literal[12,24,30]=24
    samples:int=Field(default=64,ge=8,le=1024)
    audio_mode:Literal['silent','imported']='silent'
    audio_cues:list[Cue]=Field(default_factory=list,max_length=64)
    duck_music:bool=True
    @model_serializer(mode='wrap')
    def compatible_audio(self,handler):
        data=handler(self)
        if not self.audio_cues:data.pop('audio_cues',None)
        if self.duck_music:data.pop('duck_music',None)
        return data
    @model_validator(mode='after')
    def references(self):
        ids=[o.id for o in self.objects]
        if len(set(ids))!=len(ids):raise ValueError('Duplicate object IDs')
        if len({s.id for s in self.shots})!=len(self.shots):raise ValueError('Duplicate shot IDs')
        parents={o.id:o.parent_id for o in self.objects}
        for obj in self.objects:
            seen={obj.id};parent=obj.parent_id
            while parent:
                if parent not in parents or parent in seen:raise ValueError('Missing parent or cyclic scene hierarchy')
                seen.add(parent);parent=parents[parent]
        if any(s.target_id and s.target_id not in ids for s in self.shots):raise ValueError('Shot target is missing')
        if self.width%2 or self.height%2:raise ValueError('H.264 output dimensions must be even')
        if sum(s.duration for s in self.shots)>300:raise ValueError('This initial render profile supports at most 300 seconds')
        for shot in self.shots:
            count=round(shot.duration*self.fps);motion=round((shot.motion_duration or shot.duration)*self.fps)
            if count<1 or shot.source_start_frame+count>motion:raise ValueError('Clip frame range is outside its source camera motion; reset the trim before extending duration or changing FPS')
        duration=sum(round(s.duration*self.fps) for s in self.shots)/self.fps
        if len({c.id for c in self.audio_cues})!=len(self.audio_cues):raise ValueError('Duplicate audio cue IDs')
        if self.audio_mode=='imported' and not self.audio_cues:raise ValueError('Import audio and add at least one cue, or select Silent')
        for cue in self.audio_cues:
            if cue.start+cue.duration>duration+1e-6:raise ValueError('Audio cue extends beyond the video. Trim or move it: '+cue.name)
            if cue.linked_shot and cue.linked_shot not in {s.id for s in self.shots}:raise ValueError('Audio cue shot link is missing')
            if cue.linked_object_id and cue.linked_object_id not in ids:raise ValueError('Audio cue object link is missing')
        return self

def sources(scene):
    studio.project(scene.project_id);records={}
    for obj in scene.objects:
        r=studio.scoped_artifact(obj.artifact_id,scene.project_id,obj.asset_id);path=store.safe_path(r['relative_path'])
        if r['role']!='candidate' or path.suffix.lower()!='.glb':raise ValueError('Scene sources must be real Library GLB candidates')
        if r['sha256']!=obj.sha256 or store.digest(path)!=obj.sha256:raise ValueError('Pinned source checksum changed: '+obj.name)
        inspect_glb(path);records[obj.artifact_id]=r
    return records

@router.get('/sources')
def available(project_id:str):
    studio.project(project_id)
    with store.connect() as db:
        models={r['id']:json.loads(r['payload']) for r in db.execute('SELECT id,payload FROM assets WHERE project_id=?',(project_id,))}
        records=[store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE project_id=? AND role='candidate' ORDER BY created_at",(project_id,))]
    return [dict(id=r['id'],asset_id=r['asset_id'],name=models.get(r['asset_id'],{}).get('name',r['name']),version_name=r['name'],sha256=r['sha256'],url=r['url'],dimensions=r['metadata'].get('dimensions_xyz_m'),category=models.get(r['asset_id'],{}).get('category')) for r in records if r['asset_id'] in models and not models[r['asset_id']].get('archived') and r['relative_path'].lower().endswith('.glb')]

class Save(Strict):
    scene:Scene
    asset_id:str|None=None
    base_scene_id:str|None=None
    request_id:str=Field(min_length=8,max_length=100)

@router.post('/scenes',status_code=201)
def save(body:Save):
    return save_snapshot(body)

def save_snapshot(body,edit=None):
    scene=body.scene
    try:
        sources(scene)
        from .cinematic_audio import sources as audio_sources
        audio_sources(scene)
    except (ValueError,KeyError,OSError) as exc:raise HTTPException(409,str(exc))
    if body.asset_id:
        model=studio.asset(body.asset_id)
        if model['project_id']!=scene.project_id or model.get('asset_type')!='cinematic':raise HTTPException(409,'Cinematic belongs to another game/type')
    digest=fingerprint(body.model_dump() if edit is None else dict(save=body.model_dump(),edit=edit));key='cinematic:'+body.request_id
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');cached=studio.cached(db,key,digest)
        if cached:return cached
        if body.asset_id:model=json.loads(db.execute('SELECT payload FROM assets WHERE id=?',(body.asset_id,)).fetchone()['payload'])
        else:model=dict(id=uuid.uuid5(uuid.NAMESPACE_URL,key+scene.project_id).hex,project_id=scene.project_id,asset_type='cinematic',name=scene.name,prompt=scene.prompt,original_prompt=scene.prompt,status='Draft',settings={},reference_ids=[],approvals=[],created_at=store.now(),updated_at=store.now())
        if body.base_scene_id!=model.get('settings',{}).get('current_scene_id'):raise HTTPException(409,'A newer scene was saved. Reload before saving this draft.')
        identifier=uuid.uuid5(uuid.NAMESPACE_URL,key+digest).hex;path=store.safe_path(f'projects/{scene.project_id}/assets/{model["id"]}/scenes/{identifier}.json');path.parent.mkdir(parents=True,exist_ok=True)
        content=json.dumps(scene.model_dump(),ensure_ascii=False,indent=2).encode();temporary=path.with_suffix('.json.part');temporary.write_bytes(content);temporary.replace(path)
        sha=store.digest(path);metadata=dict(project_id=scene.project_id,asset_id=model['id'],schema_version=1,asset_type='cinematic',parent_id=body.base_scene_id,source_hashes={o.artifact_id:o.sha256 for o in scene.objects},prompt_interpretation='Explicit editable camera presets; original prompt preserved, no semantic AI interpretation')
        if edit:metadata['revision']=edit
        db.execute('INSERT INTO artifacts (id,role,name,relative_path,sha256,created_at,metadata,project_id,asset_id) VALUES (?,?,?,?,?,?,?,?,?)',(identifier,'cinematic_scene',scene.name,path.relative_to(store.DATA).as_posix(),sha,store.now(),json.dumps(metadata),scene.project_id,model['id']))
        model.setdefault('settings',{})['current_scene_id']=identifier;model.setdefault('scene_versions',[]).append(identifier);model['updated_at']=store.now()
        db.execute('INSERT INTO assets VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(model['id'],scene.project_id,json.dumps(model)))
        response=dict(asset_id=model['id'],scene_id=identifier,sha256=sha)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(key,digest,json.dumps(response)))
    return response

def read_scene(identifier):
    record=store.get_artifact(identifier)
    if record['role']!='cinematic_scene':raise ValueError('Expected a cinematic scene')
    path=store.safe_path(record['relative_path'])
    if store.digest(path)!=record['sha256']:raise ValueError('Scene snapshot checksum changed')
    return record,Scene.model_validate_json(path.read_text(encoding='utf-8'))

@router.get('/assets/{asset_id}')
def detail(asset_id:str):
    model=studio.asset(asset_id)
    if model.get('asset_type')!='cinematic':raise HTTPException(409,'Expected a cinematic asset')
    with store.connect() as db:records=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=? ORDER BY created_at',(asset_id,))]
    scenes=[]
    for r in records:
        if r['role']=='cinematic_scene':
            try:_,scene=read_scene(r['id']);scenes.append(dict(id=r['id'],sha256=r['sha256'],scene=scene.model_dump()))
            except (ValueError,OSError) as exc:scenes.append(dict(id=r['id'],error=str(exc)))
    return dict(asset=model,scenes=scenes,artifacts=records,jobs=[j for j in jobs.listing() if j['payload'].get('asset_id')==asset_id])

class Render(Strict):
    scene_id:str
    request_id:str=Field(min_length=8,max_length=100)
@router.post('/render',status_code=201)
def render(body:Render):
    from engines.cinematic import effective_config
    try:record,scene=read_scene(body.scene_id);config=effective_config(record,scene)
    except (ValueError,KeyError,OSError) as exc:raise HTTPException(409,str(exc))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');key='cinematic-render:'+body.request_id;digest=fingerprint(body.model_dump());previous=studio.cached(db,key,digest)
        if previous:return previous
        job=jobs.enqueue(dict(kind='cinematic_render',engine='blender_cinematic',project_id=scene.project_id,asset_id=record['asset_id'],artifact_id=record['id'],use_gpu=False,effective_config=config,effective_config_hash=fingerprint(config),timeout_seconds=86400),db=db)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(key,digest,json.dumps(job)))
    return job

class Refine(Strict):
    scene_id:str
    prompt:str=Field(min_length=1,max_length=4000)
    request_id:str=Field(min_length=8,max_length=100)
    base_scene_id:str

class DraftEdit(Strict):
    scene:Scene
    prompt:str=Field(min_length=1,max_length=4000)

@router.post('/timeline/plan')
def edit_draft(body:DraftEdit):
    from .cinematic_edits import plan
    try:return plan(body.scene,body.prompt)
    except ValueError as exc:raise HTTPException(422,str(exc))

@router.post('/refinements/plan')
def refine_plan(body:Refine):
    from .cinematic_edits import plan
    try:record,scene=read_scene(body.scene_id);result=plan(scene,body.prompt)
    except (ValueError,KeyError,OSError) as exc:raise HTTPException(422,str(exc))
    return result

@router.post('/refinements',status_code=201)
def refine(body:Refine):
    from .cinematic_edits import plan
    try:record,scene=read_scene(body.scene_id);result=plan(scene,body.prompt)
    except (ValueError,KeyError,OSError) as exc:raise HTTPException(422,str(exc))
    edited=Scene.model_validate(result['scene'])
    return save_snapshot(Save(scene=edited,asset_id=record['asset_id'],base_scene_id=body.base_scene_id,request_id=body.request_id),
        edit=dict(source_scene_id=body.scene_id,prompt=body.prompt,operation=result['operation'],changes=result['changes'],method='Deterministic validated timeline edit; no LLM or AI inference'))
