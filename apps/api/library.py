"""Project-scoped asset management, with real files and the shared production worker."""
import json
import uuid
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException,UploadFile,File,Form
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from . import store,studio,jobs,batch,automation,statuses
from .inspection import inspect_glb
router=APIRouter(prefix='/api/library')


def data(project_id):
    studio.project(project_id);models=statuses.refresh_all()
    with store.connect() as db:
        artifacts=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at',(project_id,))]
    return [m for m in models.values() if m['project_id']==project_id],artifacts


def thumbnail_source(artifacts):
    for a in reversed(artifacts):
        if a['role']=='preview' and a['name']=='cinematic_thumbnail.png':
            path=store.safe_path(a['relative_path'])
            if path.is_file():return path,'generated_video',a['sha256']
    for a in reversed(artifacts):
        if a['role']=='preview' and a['metadata'].get('asset_type')=='vfx' and a['name']=='frame_003.png':
            path=store.safe_path(a['relative_path'])
            if path.is_file():return path,'generated_effect',a['sha256']
        if a['role']=='preview' and a['name']=='world_overview.png':
            path=store.safe_path(a['relative_path'])
            if path.is_file():return path,'generated_model',a['sha256']
    for a in reversed(artifacts):
        job=a['metadata'].get('job_id')
        if job and a['metadata'].get('stage')=='blender_processed':
            path=store.DATA/'jobs'/job/'output/mobile_three_quarter.png'
            if path.is_file():return path,'generated_model',a['sha256']
    for a in artifacts:
        if a['role'] in ('reference','concept'):
            path=store.safe_path(a['relative_path'])
            if path.is_file():return path,'reference',a['sha256']
    return None,None,None


@router.get('')
def listing(project_id:str,search:str='',category:str='',status:str='',qa:str='',art:str='',published:str='',favorite:bool=False,sort:str='recent',archived:bool=False,offset:int=0,limit:int=1000):
    models,artifacts=data(project_id);values=[]
    for m in models:
        if bool(m.get('archived'))!=archived:continue
        mine=[a for a in artifacts if a.get('asset_id')==m['id']];candidates=[a for a in mine if a['role']=='candidate'];latest=next((a for a in reversed(candidates) if a['metadata'].get('stage')=='blender_processed'),candidates[-1] if candidates else None)
        _,kind,_=thumbnail_source(mine);size=0
        if latest:
            p=store.safe_path(latest['relative_path']);size=p.stat().st_size if p.exists() else 0
        value={k:m.get(k) for k in ('id','project_id','asset_type','name','category','tags','favorite','updated_at','archived','master_artifact_id','published_artifact_id',*statuses.FIELDS)}
        value.update(source_id=m.get('settings',{}).get('source_asset_id'),thumbnail_url=f'/api/library/assets/{m["id"]}/thumbnail' if kind else None,thumbnail_kind=kind,latest_artifact_id=latest['id'] if latest else None,triangles=latest['metadata'].get('triangles') if latest else None,bytes=size,version_count=max(1+len(m.get('revisions',[])),len(m.get('fx_recipe_versions',[])),len(m.get('scene_versions',[])),sum(a['role']=='world_plan' for a in mine)),candidate_count=len(candidates),published=bool(m.get('published_artifact_id') or m.get('production_status')=='completed' and m.get('export_status')=='exported' and not m.get('revisions')))
        hay=' '.join([m['name'],m.get('settings',{}).get('source_asset_id',''),m.get('category',''),*m.get('tags',[])])
        if search and search.casefold() not in hay.casefold():continue
        if favorite and not m.get('favorite'):continue
        if category and (m.get('category') or 'Unsorted')!=category:continue
        if status=='needs_attention' and not m.get('attention_required'):continue
        if status and status!='needs_attention' and m.get('production_status')!=status:continue
        if qa and m.get('qa_status')!=qa:continue
        if art and m.get('art_review_status')!=art:continue
        if published and value['published']!=(published=='published'):continue
        values.append(value)
    key={'name':lambda v:v['name'].casefold(),'category':lambda v:(v.get('category') or '').casefold(),'size':lambda v:v['bytes'],'version':lambda v:v['version_count']}.get(sort,lambda v:v.get('updated_at') or '')
    values.sort(key=key,reverse=sort in ('recent','size','version'))
    return dict(total=len(values),items=values[max(0,offset):max(0,offset)+max(1,min(limit,1000))],categories=sorted(set(m.get('category') or 'Unsorted' for m in models)))


@router.get('/assets/{asset_id}/thumbnail')
def thumbnail(asset_id:str):
    model=studio.asset(asset_id)
    with store.connect() as db:artifacts=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=? ORDER BY created_at',(asset_id,))]
    source,kind,checksum=thumbnail_source(artifacts)
    if not source:raise HTTPException(404,'No real render or reference image exists yet')
    cache=store.DATA/'cache/library-thumbnails'/model['project_id'];cache.mkdir(parents=True,exist_ok=True);target=cache/(checksum+'.webp')
    if not target.exists():
        from PIL import Image
        with Image.open(source) as image:
            image.thumbnail((640,640));temporary=cache/(checksum+'.'+uuid.uuid4().hex+'.part');image.convert('RGB').save(temporary,format='WEBP',quality=88);temporary.replace(target)
    return FileResponse(target,media_type='image/webp',headers={'X-AFS-Preview-Kind':kind})


class Bulk(BaseModel):
    asset_ids:list[str]=Field(min_length=1,max_length=1000)
    action:Literal['archive','restore','category','tags','inspect','export']
    category:str|None=Field(default=None,max_length=200)
    tags:list[str]=Field(default_factory=list,max_length=50)


def patch_metadata(identifier,updates):
    # Read again under the write lock so a concurrent completed worker's master,
    # statuses and revision history are never replaced by a stale UI snapshot.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM assets WHERE id=?',(identifier,)).fetchone()
        if not row:raise HTTPException(404,'Asset no longer exists')
        latest=json.loads(row['payload']);latest.update(updates,updated_at=store.now())
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(latest),identifier))


@router.post('/bulk')
def bulk(body:Bulk):
    from .export_profiles import export_asset,export_history
    completed=[];errors=[]
    for identifier in dict.fromkeys(body.asset_ids):
        try:
            model=studio.asset(identifier)
            if body.action in ('archive','restore'):
                if body.action=='archive' and any(j['payload'].get('asset_id')==identifier and j['status'] not in jobs.TERMINAL for j in jobs.listing()):raise HTTPException(409,'Finish or cancel active production before archiving. No files were deleted.')
                patch_metadata(identifier,dict(archived=body.action=='archive'));completed.append(dict(asset_id=identifier,archived=body.action=='archive'))
            elif body.action in ('category','tags'):
                if body.action=='category':
                    if not body.category or not body.category.strip():raise HTTPException(400,'Enter a category')
                    model['category']=body.category.strip()
                else:model['tags']=list(dict.fromkeys(t.strip()[:100] for t in body.tags if t.strip()))
                patch_metadata(identifier,{key:model[key] for key in ('category','tags') if key in model and key==('category' if body.action=='category' else 'tags')});completed.append(dict(asset_id=identifier))
            else:
                with store.connect() as db:mine=[store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE asset_id=? AND role='candidate' ORDER BY created_at DESC",(identifier,))]
                record=next((a for a in mine if a['metadata'].get('stage')=='blender_processed'),mine[0] if mine else None)
                if not record:raise HTTPException(409,'No real model exists for this asset')
                path=store.safe_path(record['relative_path'])
                if store.digest(path)!=record['sha256']:raise HTTPException(409,'Model checksum changed')
                if body.action=='inspect':
                    report=inspect_glb(path);model['latest_inspection']=dict(at=store.now(),artifact_id=record['id'],sha256=record['sha256'],report=report);studio.save_asset(model);completed.append(dict(asset_id=identifier,report=report))
                else:
                    if model.get('qa_status')!='passed' and record['metadata'].get('stage')!='blender_processed':raise HTTPException(409,'Technical postprocessing / QA is unfinished. Open Production before exporting this model.')
                    revision=next((r for r in model.get('revisions',[]) if r.get('artifact_id')==record['id']),None)
                    settings=revision.get('export_settings',{}).copy() if revision else None
                    if revision and model.get('published_artifact_id')!=record['id']:settings['output_directory']=str(store.DATA/'revision-previews')
                    result=export_asset(model['project_id'],identifier,record['id'],settings)
                    if revision and model.get('published_artifact_id')!=record['id']:
                        result.update(delivery_scope='staged',revision_id=revision['id'])
                        with store.connect() as db:db.execute('UPDATE selective_exports SET payload=? WHERE id=?',(json.dumps(result),result['id']))
                    completed.append(result)
        except (HTTPException,ValueError,OSError) as e:errors.append(dict(asset_id=identifier,error=str(e.detail if isinstance(e,HTTPException) else e)))
    return dict(completed=completed,errors=errors,inference_started=False)


@router.get('/storage')
def storage(project_id:str):
    models,artifacts=data(project_id);totals=dict(sources=0,candidates=0,masters=0,exports=0,thumbnails=0,reproducible_caches=0);seen=set();masters={m.get('master_artifact_id') for m in models}
    for a in sorted(artifacts,key=lambda a:a['id'] not in masters):
        p=store.safe_path(a['relative_path'])
        if str(p) in seen or not p.is_file():continue
        seen.add(str(p));category='masters' if a['id'] in masters else 'candidates' if a['role']=='candidate' else 'thumbnails' if a['role']=='preview' else 'sources';totals[category]+=p.stat().st_size
    from .export_profiles import _schema
    _schema()
    with store.connect() as db:exports=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM selective_exports')]
    for e in exports:
        if e['project_id']!=project_id:continue
        for f in e['files']:
            p=Path(e['export_directory'])/f['name']
            if str(p) not in seen and p.is_file():seen.add(str(p));totals['exports']+=p.stat().st_size
    cache=store.DATA/'cache/library-thumbnails'/project_id
    if cache.exists():totals['reproducible_caches']=sum(p.stat().st_size for p in cache.glob('*.webp') if p.is_file())
    return dict(bytes=totals,total_bytes=sum(totals.values()),scope='Unique registered project files plus thumbnail caches; engine weights and unregistered job intermediates excluded',cache_cleanup_available=totals['reproducible_caches']>0)


@router.post('/projects/{project_id}/cleanup-thumbnails')
def cleanup(project_id:str):
    studio.project(project_id);root=(store.DATA/'cache/library-thumbnails').resolve();target=(root/project_id).resolve()
    if target.parent!=root:raise HTTPException(400,'Invalid project cache path')
    removed=0
    if target.exists():
        for p in target.glob('*.webp'):
            if p.resolve().parent==target and not p.is_symlink():removed+=p.stat().st_size;p.unlink()
    return dict(removed_bytes=removed,sources_preserved=True,regenerated_on_next_thumbnail_request=True)


@router.post('/import',status_code=201)
async def import_glb(file:UploadFile=File(...),project_id:str=Form(...)):
    studio.project(project_id)
    if Path(file.filename or '').suffix.lower()!='.glb':raise HTTPException(400,'Only validated GLB import is currently supported')
    root=store.DATA/'imports';root.mkdir(parents=True,exist_ok=True);temporary=root/(uuid.uuid4().hex+'.glb.part');count=0
    try:
        with temporary.open('wb') as output:
            while part:=await file.read(1024*1024):
                count+=len(part)
                if count>512*1024**2:raise HTTPException(413,'GLB exceeds the 512 MiB local import limit')
                output.write(part)
        try:qa=inspect_glb(temporary)
        except (ValueError,OSError) as e:raise HTTPException(400,'Invalid GLB: '+str(e))
        checksum=store.digest(temporary)
        with batch.LOCK:
            with store.connect() as db:existing=db.execute("SELECT asset_id FROM artifacts WHERE project_id=? AND sha256=? AND asset_id IS NOT NULL",(project_id,checksum)).fetchone()
            if existing:return dict(asset_id=existing['asset_id'],duplicate=True,sha256=checksum)
            target=root/(checksum+'.glb')
            if target.exists():
                if store.digest(target)!=checksum:raise HTTPException(409,'Existing imported source was changed')
            else:temporary.replace(target)
            model=studio.create_asset(studio.AssetInput(project_id=project_id,name=Path(file.filename).stem,prompt='',category='Imported'))
            record=store.add_artifact(target,'candidate',Path(file.filename).name,qa|dict(project_id=project_id,asset_id=model['id'],stage='external_import',license='User supplied; commercial rights not verified'))
            from .manifest import ManifestItem
            from .export_profiles import resolve_project_settings
            identifier=uuid.uuid4().hex;item=ManifestItem(asset_id=model['id'],name=model['name'],prompt='Technical postprocessing of imported '+model['name'],category='Imported',quality='Maximum').model_dump();item.update(attempt=0,started=True,version=1,quality_lock=True,processing_source=dict(artifact_id=record['id'],normalize=False),automation=dict(enabled=True,engines=['external_import'],attempt=0,status='queued',stage='Blender import QA',checkpoints={}))
            value=dict(id=identifier,project_id=project_id,name=model['name'],mode='Maximum Quality Batch',quality_lock=True,master_prompt='',style_snapshot=studio.project(project_id),items=[item],warnings=[],paused=False,created_at=store.now(),updated_at=store.now(),automation=dict(settings=automation.project_workflow(project_id),export_settings=resolve_project_settings(project_id),mode='auto',started_at=store.now()))
            with store.connect() as db:db.execute('INSERT INTO batches VALUES (?,?,?)',(identifier,project_id,json.dumps(value)))
            automation.advance(identifier)
            return dict(asset_id=model['id'],group_id=identifier,duplicate=False,sha256=checksum,qa=qa,postprocessing='Queued in shared CPU scheduler; not yet a completed export')
    finally:
        if temporary.exists():temporary.unlink()
        await file.close()
