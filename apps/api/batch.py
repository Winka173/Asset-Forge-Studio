"""Project-scoped checkpoint batch orchestration over the same Single Asset APIs."""
import csv
import io
import json
import shutil
import threading
import uuid
import zipfile
from pathlib import Path
import psutil
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from typing import Literal
from pydantic import BaseModel, Field, ValidationError
from . import store, jobs, studio
from .manifest import ManifestItem, parse, diagnostics, MAX_MANIFEST_CHARACTERS, MAX_MANIFEST_ASSETS

router=APIRouter(prefix='/api/batches')
LOCK=threading.RLock()
MODES=['Fast Batch','Quality Batch','Maximum Quality Batch']


def batch(identifier):
    with store.connect() as db:row=db.execute('SELECT payload FROM batches WHERE id=?',(identifier,)).fetchone()
    if not row:raise HTTPException(404,'Không tìm thấy batch')
    result=json.loads(row['payload']);studio.project(result['project_id']);return result


def save(value):
    value['updated_at']=store.now()
    with store.connect() as db:db.execute('UPDATE batches SET payload=? WHERE id=?',(json.dumps(value),value['id']))
    return value


def missing(item):
    if item.get('automation',{}).get('enabled'):return [] if item.get('prompt','').strip() else ['prompt']
    return [k for k in ['target_width_m','target_depth_m','target_height_m'] if item.get(k) is None]+([] if item.get('confirmed') else ['specification_confirmation'])+([] if item.get('prompt','').strip() else ['prompt'])


def detail(value):
    snapshot=studio.studio(value['project_id']);artifacts=snapshot['artifacts'];all_jobs=snapshot['jobs']
    for item in value['items']:
        model=next(a for a in snapshot['assets'] if a['id']==item['asset_id'])
        current=[j for j in all_jobs if j['payload'].get('batch_id')==value['id'] and j['payload'].get('asset_id')==item['asset_id'] and j['payload'].get('batch_attempt',0)==item.get('attempt',0)]
        # Request IDs also encode attempt; root Single endpoints propagate it explicitly.
        concepts=[a for a in artifacts if a['role']=='concept' and a.get('asset_id')==item['asset_id']]
        # Explicit manifest reference wins over rejected/generated concepts.
        source=next((a for a in artifacts if a['id'] in item['reference_ids']),None) or (concepts[-1] if concepts else None)
        approved=bool(source and any(a['artifact_id']==source['id'] and a['sha256']==source['sha256'] for a in model.get('concept_approvals',[])))
        item.update(missing_fields=missing(item),jobs=current,versions=model['versions'],exports=model['exports'],
                    concept_artifact_id=source['id'] if source else None,concept_url=source['url'] if source else None,concept_approved=approved,master_artifact_id=model['master_artifact_id'])
        state='Pending'
        if item.get('skipped'):state='Skipped'
        elif any(j['status'] not in jobs.TERMINAL and j['status']!='QUEUED' for j in current):state='Processing' if any(j['payload']['kind']=='blender' and j['status'] not in jobs.TERMINAL and j['status']!='QUEUED' for j in current) else 'Generating'
        elif any(j['status']=='QUEUED' for j in current):state='Pending'
        elif current and current[0]['status'] in ['FAILED','BLOCKED','CANCELLED']:state='QA Failed' if current[0]['payload']['kind']=='blender' else 'Failed/Blocked'
        elif model['versions'] and any(j['payload']['kind']=='inference' and j['status']=='REVIEW_REQUIRED' for j in current):
            state='Approved' if model['master_artifact_id'] in [a['id'] for a in model['versions'] if any(a['metadata'].get('job_id')==j['id'] for j in current)] else 'Ready for Review'
            if state=='Approved' and any(e.get('files') for e in model['exports']):state='Exported'
        elif source:state='Concept Ready' if approved else 'Awaiting Approval'
        item['status']=state
        auto=item.get('automation',{})
        if auto.get('enabled'):
            item['status']={'exported':'Exported','completed':'Technically Validated','blocked':'Blocked','failed':'Failed','paused':'Paused','running':'Generating','queued':'Pending'}.get(auto.get('status'),state)
        if item.get('last_error') and state not in ['Generating','Processing']:item['status']='Failed/Blocked'
        item['effective_config']=None
        item.pop('config_warning',None)
        if source:
            from engines.quality import resolve
            chosen_engine=item['preferred_engine'] if item['preferred_engine']!='auto' else 'trellis2_community'
            try:item['effective_config']=resolve(dict(engine=chosen_engine,quality=item['quality'],quality_lock=item['quality_lock'],prompt=item['prompt'],seeds=[42+n for n in range(item['candidates'])],auto_blender=True,benchmark_height_m=item['target_height_m']),source,value['style_snapshot'])
            except (ValueError,OSError) as exc:item['config_warning']=str(exc)
            if value['mode']=='Maximum Quality Batch' and item['preferred_engine']=='auto' and not source['metadata'].get('has_transparency'):
                item['config_warning']='Auto can use textured TRELLIS.2 with this image; TripoSG requires reviewed alpha. Multi-engine coverage is incomplete until an alpha reference is selected.'
    from engines.adapters import ADAPTERS
    from engines.concept_adapter import CONCEPT_ADAPTER
    from .automation import plan_engines
    count=sum(i['candidates']*len(i.get('automation',{}).get('engines') or plan_engines(i,next((a for a in artifacts if a['id'] in i['reference_ids'] and a['role'] in ('concept','reference')),None))) for i in value['items'] if i['selected'])
    concepts_needed=sum(not i.get('concept_artifact_id') for i in value['items'] if i['selected'])
    warnings=list(value.get('warnings',[]))
    if len(value['items'])>30:warnings.append('Batch lớn: duyệt subset trước. Không tự giảm chất lượng để tăng tốc.')
    value['preflight']=dict(engines={k:a.probe() for k,a in ADAPTERS.items()},concept_engine=CONCEPT_ADAPTER.probe(),ram_free_bytes=psutil.virtual_memory().available,
        disk_free_bytes=shutil.disk_usage(store.DATA).free,estimated_jobs=count*2+concepts_needed,estimated_candidate_jobs=count,estimated_storage_bytes=None,planner='strict_local_structured_parser; optional local metadata adapter',warnings=warnings,
        scheduler=dict(heavy_gpu_concurrency=1,cpu_concurrency=2,quality_downgrade=False))
    value['progress']=dict(total=len(value['items']),completed=sum(i['status'] in ['Approved','Exported'] for i in value['items']),
        active=sum(i['status'] in ['Generating','Processing'] for i in value['items']),blocked=sum(bool(i['missing_fields']) or i['status'] in ['Failed/Blocked','QA Failed'] for i in value['items']))
    if value.get('automation'):
        from datetime import datetime,timezone
        states=[i.get('automation',{}).get('status','pending') for i in value['items']]
        exported=states.count('exported');active=sum(s in ('running','queued') and i.get('started',False) for s,i in zip(states,value['items']))
        value['progress'].update(completed=sum(s in ('exported','completed') for s in states),exported=exported,needs_review=exported,failed=states.count('failed'),blocked=states.count('blocked'),active=sum(s=='running' for s in states),queued=states.count('queued'),pending=sum(s in ('pending','paused') for s in states),remaining=len(states)-exported,pause_state=value['automation'].get('pause_state'),pause_reason=value['automation'].get('pause_reason'),eta_seconds=None,elapsed_seconds=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(value['automation']['started_at'])).total_seconds()))
    return value


def stored(value):
    # Runtime/file QA is always re-derived, not trusted from clients or cached status.
    copy=dict(value);copy.pop('preflight',None);copy.pop('progress',None)
    runtime=['jobs','versions','exports','missing_fields','status','concept_artifact_id','concept_url','concept_approved','master_artifact_id','effective_config']
    copy['items']=[{k:v for k,v in i.items() if k not in runtime} for i in value['items']]
    return copy


class Analyze(BaseModel):
    project_id:str
    name:str=Field(default='Asset batch',min_length=1,max_length=200)
    master_prompt:str=Field(min_length=1,max_length=MAX_MANIFEST_CHARACTERS)
    format:str='auto'
    mode:str='Quality Batch'
    reference_ids:list[str]=Field(default_factory=list,max_length=50)
    source_filename:str=Field(default='manifest.txt',max_length=255)


@router.post('/analyze',status_code=201)
def analyze(body:Analyze):
    return analyze_source(body)


@router.post('/import',status_code=201)
async def import_file(file:UploadFile=File(...),project_id:str=Form(...),name:str=Form('Asset batch'),format:str=Form('auto'),mode:str=Form('Quality Batch'),reference_ids:str=Form('[]')):
    # UploadFile spools to disk; cap reads explicitly instead of accepting an unbounded body.
    content=await file.read(16_000_001)
    if len(content)>16_000_000:raise HTTPException(413,'File exceeds 16 MB. Split the manifest; no data was truncated.')
    try:
        text=content.decode('utf-8-sig')
        body=Analyze(project_id=project_id,name=name,master_prompt=text,format=format,mode=mode,reference_ids=json.loads(reference_ids),source_filename=file.filename or 'manifest.txt')
    except (UnicodeError,ValueError,ValidationError):raise HTTPException(400,'Expected a UTF-8 manifest within the supported limits (10 million characters). Check the file encoding and fields.')
    return analyze_source(body,content)


def analyze_source(body:Analyze,source_bytes:bytes|None=None):
    with LOCK:return _analyze_source(body,source_bytes)


def _analyze_source(body:Analyze,source_bytes:bytes|None=None):
    project=studio.project(body.project_id)
    if body.mode not in MODES:raise HTTPException(400,'Batch quality mode không hợp lệ')
    for ref in body.reference_ids:studio.scoped_artifact(ref,body.project_id)
    original=source_bytes if source_bytes is not None else body.master_prompt.encode('utf-8')
    import hashlib
    original_hash=hashlib.sha256(original).hexdigest()
    with store.connect() as db:
        previous=[json.loads(r['payload']) for r in db.execute("SELECT payload FROM batches WHERE project_id=? AND json_extract(payload,'$.source_file.sha256')=? ORDER BY rowid",(body.project_id,original_hash))]
        existing={}
        for row in db.execute('SELECT payload FROM assets WHERE project_id=? ORDER BY rowid',(body.project_id,)):
            model=json.loads(row['payload']);source_id=model.get('settings',{}).get('source_asset_id')
            if source_id:existing.setdefault(source_id,model)
    for value in previous:
        if value['mode']==body.mode and sorted(value.get('import_reference_ids',[]))==sorted(set(body.reference_ids)):
            result=detail(value);result['reused_import']=True;return result
    try:rows,warnings=parse(body.master_prompt,body.format)
    except ValidationError as exc:
        raise HTTPException(400,'Invalid manifest item: '+'; '.join('.'.join(map(str,e['loc']))+': '+e['msg'] for e in exc.errors(include_input=False,include_context=False)))
    except ValueError as exc:raise HTTPException(400,str(exc))
    identifier=uuid.uuid4().hex;items=[]
    report=diagnostics(body.master_prompt,body.format,rows,warnings)
    folder=store.DATA/'batches'/identifier/'source';folder.mkdir(parents=True,exist_ok=True)
    original_path=folder/'original';original_path.write_bytes(original)
    text_path=folder/'decoded.txt';text_path.write_bytes(body.master_prompt.encode('utf-8'))
    source_file=dict(name=Path(body.source_filename.replace('\\','/')).name,sha256=store.digest(original_path),bytes=len(original),
                     text_sha256=store.digest(text_path),encoding='utf-8-sig',relative_path=original_path.relative_to(store.DATA).as_posix(),
                     original_source_url=f'/api/batches/{identifier}/source',decoded_source_url=f'/api/batches/{identifier}/source?decoded=true')
    report['source_file']=source_file
    for row in rows:
        item=ManifestItem.model_validate(row).model_dump()
        prior=existing.get(item['source_asset_id']) if item['source_asset_id'] else None
        item['asset_id']=prior['id'] if prior else uuid.uuid5(uuid.NAMESPACE_URL,'afs-project-source:'+body.project_id+':'+item['source_asset_id']).hex if item['source_asset_id'] else uuid.uuid5(uuid.UUID(identifier),item['name']).hex
        item['quality']={'Fast Batch':'Fast','Quality Batch':'Balanced','Maximum Quality Batch':'Maximum'}[body.mode]
        item.update(reference_ids=list(dict.fromkeys(body.reference_ids+item['reference_ids'])),attempt=0,started=False,version=1,quality_lock=body.mode=='Maximum Quality Batch')
        for ref in item['reference_ids']:studio.scoped_artifact(ref,body.project_id)
        model=prior or dict(id=item['asset_id'],project_id=body.project_id,name=item['name'],prompt=item['prompt'],category=item['category'],favorite=False,status='Candidate',
            master_artifact_id=None,reference_ids=item['reference_ids'],settings=dict(batch_id=identifier,source_asset_id=item['source_asset_id'],source_status=item['source_status'],style_base=project,style_overrides=item['style_constraints']),approvals=[],created_at=store.now(),updated_at=store.now())
        model.setdefault('source_import_history',[]).append(dict(batch_id=identifier,source_file_sha256=source_file['sha256'],prompt_sha256=hashlib.sha256(item['prompt'].encode()).hexdigest(),at=store.now()))
        items.append((item,model))
    value=dict(id=identifier,project_id=body.project_id,name=body.name,master_prompt=body.master_prompt,mode=body.mode,paused=True,
        quality_lock=body.mode=='Maximum Quality Batch',style_snapshot=project,warnings=warnings,import_reference_ids=list(dict.fromkeys(body.reference_ids)),import_diagnostics=report,source_file=source_file,items=[i for i,_ in items],created_at=store.now(),updated_at=store.now())
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for item,model in items:
            current=db.execute('SELECT payload FROM assets WHERE id=?',(model['id'],)).fetchone()
            if current:
                # A worker may have completed while parsing. Import only appends provenance;
                # it must never replace the latest master, review or immutable prompt.
                latest=json.loads(current['payload'])
                history=latest.setdefault('source_import_history',[])
                history.extend(h for h in model['source_import_history'] if h['batch_id']==identifier and not any(old['batch_id']==identifier for old in history))
                db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(latest),model['id']))
            else:db.execute('INSERT INTO assets VALUES (?,?,?)',(model['id'],body.project_id,json.dumps(model)))
        db.execute('INSERT INTO batches VALUES (?,?,?)',(identifier,body.project_id,json.dumps(value)))
    return detail(value)


@router.get('')
def listing(project_id:str,summary:bool=False):
    studio.project(project_id)
    with store.connect() as db:values=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches WHERE project_id=?',(project_id,))]
    if summary:return [dict(id=v['id'],name=v['name'],project_id=v['project_id'],mode=v['mode'],paused=v['paused'],item_count=len(v['items'])) for v in values]
    return [detail(v) for v in values]


@router.get('/{identifier}')
def get(identifier:str):return detail(batch(identifier))


@router.get('/{identifier}/source')
def source_file(identifier:str,decoded:bool=False):
    value=batch(identifier);source=value.get('source_file')
    if not source:raise HTTPException(404,'Original source was not retained by this older import')
    file=store.safe_path(source['relative_path'])
    if decoded:file=file.parent/'decoded.txt'
    if not file.is_file() or store.digest(file)!=source['text_sha256' if decoded else 'sha256']:raise HTTPException(409,'Original import checksum changed')
    return FileResponse(file,filename='decoded.txt' if decoded else source['name'])


class Selection(BaseModel):
    selected_ids:list[str]=Field(max_length=MAX_MANIFEST_ASSETS)


@router.post('/{identifier}/selection')
def selection(identifier:str,body:Selection):
    """One atomic review-only update, never starts or resumes generation."""
    with LOCK:
        value=batch(identifier);selected=set(body.selected_ids)
        if selected-{i['asset_id'] for i in value['items']}:raise HTTPException(400,'Selection contains assets outside this batch')
        for item in value['items']:item['selected']=item['asset_id'] in selected
        save(value)
    return detail(value)


class Models(BaseModel):
    engines:list[Literal['trellis2_community','triposg','trellis_v1','hunyuan3d21']]=Field(default_factory=list,max_length=4)
    texturer:Literal['','mvadapter','trellis2']=''


class Options(BaseModel):
    keep_final_only:bool


@router.post('/{identifier}/options')
def options(identifier:str,body:Options):
    """Batch-level delivery housekeeping: after each delivered item keep only the final files."""
    with LOCK:
        value=batch(identifier);value['keep_final_only']=body.keep_final_only;save(value)
    return detail(value)


class Kind(BaseModel):
    kind:Literal['auto','building','character','creature','prop','vehicle','nature']


@router.post('/{identifier}/items/{asset_id}/kind')
def item_kind(identifier:str,asset_id:str,body:Kind):
    """Asset type of one item (engines/asset_kind.py); stages that already ran keep their output."""
    with LOCK:
        value=batch(identifier);item=next((i for i in value['items'] if i['asset_id']==asset_id),None)
        if not item:raise HTTPException(404,'Unknown batch item')
        # Chosen in the batch row next to the detected type: deliberate, so Auto never switches it.
        item.update(kind=body.kind,kind_confirmed=True,kind_checked=True);item.pop('kind_note',None);save(value)
        with store.connect() as db:
            row=db.execute('SELECT payload FROM assets WHERE id=?',(asset_id,)).fetchone()
            if row:model=json.loads(row['payload']);model['kind']=body.kind;db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(model),asset_id))
    return detail(value)


@router.post('/{identifier}/models')
def models(identifier:str,body:Models):
    """Batch-wide model choice for items that have not started; started items keep their recorded configuration."""
    with LOCK:
        value=batch(identifier);ids=list(dict.fromkeys(body.engines));changed=0
        for item in value['items']:
            if item.get('started'):continue
            item['engines']=ids if len(ids)>1 else []
            item['preferred_engine']=ids[0] if len(ids)==1 and ids[0]!='trellis2_community' else 'auto'
            item['texturer']=body.texturer;changed+=1
        save(value)
    return detail(value)|dict(models_applied=changed)


@router.post('/{identifier}/items/{asset_id}')
def edit(identifier:str,asset_id:str,body:dict):
    with LOCK:
        value=batch(identifier);item=next((i for i in value['items'] if i['asset_id']==asset_id),None)
        if not item:raise HTTPException(404,'Asset không thuộc batch')
        allowed=set(ManifestItem.model_fields)-{k for k in ManifestItem.model_fields if k.startswith('source_')}-{'asset_id','semantic_metadata'}
        if set(body)-allowed-{'quality_override_confirmed','quality_override_reason'}:raise HTTPException(400,'Trường manifest không hợp lệ')
        if item.get('started') and any(j['status'] not in jobs.TERMINAL and j['payload'].get('asset_id')==asset_id for j in jobs.listing()):raise HTTPException(409,'Đợi checkpoint trước khi sửa cấu hình')
        lower=('quality' in body and body['quality']!=item['quality']) or ('candidates' in body and body['candidates']<item['candidates'])
        if item['quality_lock'] and lower and (not body.get('quality_override_confirmed') or not str(body.get('quality_override_reason','')).strip()):raise HTTPException(409,'Quality Lock: cần xác nhận chủ động và lý do khi thay đổi chất lượng')
        clean={k:v for k,v in item.items() if k in ManifestItem.model_fields};clean.update({k:v for k,v in body.items() if k in allowed})
        try:validated=ManifestItem.model_validate(clean).model_dump()
        except ValidationError as exc:raise HTTPException(400,str(exc))
        for ref in validated['reference_ids']:studio.scoped_artifact(ref,value['project_id'])
        config_fields=allowed-{'selected','priority','skipped','name','category'}
        changed=any(k in body and validated.get(k)!=item.get(k) for k in config_fields)
        history=[j for j in jobs.listing() if j['payload'].get('batch_id')==identifier and j['payload'].get('asset_id')==asset_id]
        if changed and history:
            # Editing completed work creates a new, explicitly unstarted revision.
            # Resume cannot silently rerun old request IDs with a different config.
            item.setdefault('config_revision_history',[]).append(dict(attempt=item['attempt'],version=item['version'],changed_fields=sorted(k for k in config_fields if k in body and validated.get(k)!=item.get(k)),created_at=store.now()))
            item.update(attempt=item['attempt']+1,started=False)
        item.update(validated);item['version']+=1
        item.pop('last_error',None)
        if item['quality_lock'] and lower:item.setdefault('quality_override_history',[]).append(dict(approved=True,changes=body,created_at=store.now()))
        model=studio.asset(asset_id);model.update(name=item['name'],prompt=item['prompt'],category=item['category'],reference_ids=item['reference_ids'])
        model['settings'].update(style_overrides=item['style_constraints']);studio.save_asset(model);save(value)
    return detail(value)


def advance(identifier):
    if batch(identifier).get('automation'):
        from .automation import advance as automatic_advance
        return automatic_advance(identifier)
    with LOCK:
        value=detail(batch(identifier))
        if value['paused']:return value
        from engines.adapters import ADAPTERS
        for item in sorted(value['items'],key=lambda i:-i['priority']):
            if not item.get('started') or item['skipped'] or item['missing_fields']:continue
            if item['status'] in ['Failed/Blocked','QA Failed']:continue
            if any(j['status'] not in jobs.TERMINAL for j in item['jobs']):continue
            dependencies=[next((i for i in value['items'] if i['asset_id']==d or i['name']==d),None) for d in item['dependencies']]
            if any(d is None or d['status'] not in ['Approved','Exported'] for d in dependencies):continue
            try:
                prefix=f'{identifier}:{item["asset_id"]}:{item["attempt"]}'
                if not item['concept_artifact_id']:
                    if item['jobs']:continue
                    result=studio.concept(studio.ConceptInput(asset_id=item['asset_id'],request_id=prefix+':concept',prompt=item['prompt'] or item['name'],quality=item['quality'],batch_id=identifier,batch_attempt=item['attempt']))
                elif item['concept_approved']:
                    source=studio.scoped_artifact(item['concept_artifact_id'],value['project_id'])
                    engines=[item['preferred_engine']]
                    if engines==['auto']:
                        engines=[e for e in ['trellis2_community','triposg'] if ADAPTERS[e].installed and (e not in ('triposg','trellis_v1','hunyuan3d21') or source['metadata'].get('has_transparency'))]
                        if value['mode']!='Maximum Quality Batch':engines=engines[:1]
                    if not engines:raise ValueError('No installed engine supports this input; no fallback or quality downgrade')
                    for engine in engines:
                        if any(j['payload'].get('engine')==engine and j['payload']['kind']=='inference' for j in item['jobs']):continue
                        # Same resolver and same inference/Blender chain as Single Asset.
                        studio.generate(studio.Generate(asset_id=item['asset_id'],artifact_id=source['id'],request_id=prefix+':'+engine,
                            engine=engine,quality=item['quality'],prompt=item['prompt'],seeds=[42+n for n in range(item['candidates'])],auto_blender=True,
                            benchmark_height_m=item['target_height_m'],batch_id=identifier,batch_attempt=item['attempt'],quality_lock=item['quality_lock']))
            except (HTTPException,ValueError,OSError,KeyError) as exc:
                latest=batch(identifier)
                failed=next(i for i in latest["items"] if i["asset_id"]==item["asset_id"])
                failed["last_error"]=str(exc.detail if isinstance(exc,HTTPException) else exc)
                save(latest)
        return detail(batch(identifier))


class Run(BaseModel):
    selected_ids:list[str] | None=None
    automatic:bool=False
    dry_run:bool=False
    request_id:str|None=Field(default=None,min_length=8,max_length=100)
    regenerate_completed:bool=False
    allow_questions:bool=False


def prepare_generation(value,ids,request_id,regenerate_completed,dry_run=False):
    """A new explicit click may start new attempts; retrying that click may not."""
    from engines.quality import fingerprint
    if regenerate_completed and not request_id:raise HTTPException(422,'A request_id is required for explicit regeneration')
    digest=fingerprint(dict(operation='batch_generation',batch_id=value['id'],selected_ids=sorted(ids),regenerate_completed=regenerate_completed))
    if request_id and not dry_run:
        with store.connect() as db:
            if studio.cached(db,request_id,digest):return digest,True
    if regenerate_completed and not dry_run:
        history=jobs.listing()
        for item in value['items']:
            if item['asset_id'] not in ids or not item.get('started'):continue
            stages=[j for j in history if j['payload'].get('batch_id')==value['id'] and j['payload'].get('asset_id')==item['asset_id'] and j['payload'].get('batch_attempt',0)==item.get('attempt',0)]
            if any(j['status'] not in jobs.TERMINAL for j in stages):continue
            if not stages and item.get('automation',{}).get('status') not in ('exported','completed','failed','blocked'):continue
            item.setdefault('generation_history',[]).append(dict(attempt=item['attempt'],automation=item.get('automation'),at=store.now(),request_id=request_id))
            item.update(attempt=item['attempt']+1,started=False,skipped=False)
            item.pop('automation',None);item.pop('last_error',None)
        value.pop('production_cancelled',None)
    return digest,False


def persist_generation(value,request_id,digest):
    value=stored(value);value['updated_at']=store.now()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if request_id and studio.cached(db,request_id,digest):return
        db.execute('UPDATE batches SET payload=? WHERE id=?',(json.dumps(value),value['id']))
        if request_id:db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(request_id,digest,json.dumps(dict(batch_id=value['id'],operation='batch_generation'))))


@router.post('/{identifier}/run-all')
def run_all(identifier:str,body:Run):
    from .automation import start
    return start(identifier,dry_run=body.dry_run,request_id=body.request_id,regenerate_completed=body.regenerate_completed)


@router.post('/{identifier}/run')
def run(identifier:str,body:Run):
    if body.automatic:
        from .automation import start
        return start(identifier,body.selected_ids,dry_run=body.dry_run,request_id=body.request_id,regenerate_completed=body.regenerate_completed,allow_questions=body.allow_questions)
    with LOCK:
        value=batch(identifier);selected=set(body.selected_ids) if body.selected_ids is not None else {i['asset_id'] for i in value['items'] if i['selected']}
        if selected-{i['asset_id'] for i in value['items']}:raise HTTPException(400,'Asset selection is outside this batch')
        digest,reused=prepare_generation(value,selected,body.request_id,body.regenerate_completed,body.dry_run)
        if reused:return detail(value)
        if body.dry_run:return dict(dry_run=True,plan=dict(total=len(selected)),items=[i['asset_id'] for i in value['items'] if i['asset_id'] in selected])
        for item in value['items']:
            if item['asset_id'] in selected and missing(item):raise HTTPException(409,f'{item["name"]}: cần xác nhận '+', '.join(missing(item)))
        for item in value['items']:
            if item['asset_id'] in selected:item['started']=True
        value['paused']=False;persist_generation(value,body.request_id,digest)
    return advance(identifier)


class Control(BaseModel):action:str


@router.post('/{identifier}/control')
def control(identifier:str,body:Control):
    with LOCK:
        value=batch(identifier)
        if body.action=='duplicate':
            rows=[{k:v for k,v in i.items() if k in ManifestItem.model_fields and k!='asset_id'} for i in value['items']]
            copy=analyze(Analyze(project_id=value['project_id'],name=value['name']+' copy',master_prompt=json.dumps(rows),format='json',mode=value['mode']))
            if value.get('source_file'):
                copy.update(source_file=value['source_file'],import_diagnostics=value['import_diagnostics'],master_prompt=value['master_prompt'])
                save(stored(copy))
            return copy
        if body.action in ('retry_failed','skip_failed'):
            from .automation import leaves
            failures=leaves([j for j in jobs.listing() if j['payload'].get('batch_id')==identifier])
            for item in value['items']:
                auto=item.get('automation',{})
                affected=[j for j in failures if j['payload'].get('asset_id')==item['asset_id'] and j['payload'].get('batch_attempt',0)==item['attempt'] and j['status'] in ('FAILED','BLOCKED','CANCELLED')]
                if auto.get('status') in ('failed','blocked') or affected:
                    auto.pop('retry_required',None)
                    if body.action=='skip_failed':item['skipped']=True;auto['status']='skipped'
                    else:
                        for job in affected:jobs.retry(job['id'])
                        auto.update(status='queued',error=None);item.pop('last_error',None)
            if body.action=='retry_failed':value['paused']=False
            save(stored(value));return detail(value)
        if body.action not in ['pause','resume','cancel']:raise HTTPException(400,'Action không hợp lệ')
        if value.get('automation'):
            value['automation']['pause_reason']='User paused at stage boundary' if body.action=='pause' else 'User cancelled pending work' if body.action=='cancel' else None
        value['paused']=body.action!='resume'
        if body.action=='cancel':value['production_cancelled']=True
        elif body.action=='resume':value['production_cancelled']=False
        # Per-asset record: a later explicit Generate/Regenerate of one asset must not keep showing it as cancelled.
        if body.action in ('cancel','resume'):
            for item in value['items']:item['production_cancelled']=body.action=='cancel'
        save(value)
        if body.action=='cancel':
            for job in jobs.listing():
                if job['payload'].get('batch_id')==identifier and job['status'] not in jobs.TERMINAL:
                    try:jobs.transition(job['id'],'CANCELLED')
                    except ValueError:pass
    return advance(identifier) if body.action=='resume' else detail(value)


@router.post('/{identifier}/items/{asset_id}/action')
def item_action(identifier:str,asset_id:str,body:Control):
    with LOCK:
        value=batch(identifier);item=next((i for i in value['items'] if i['asset_id']==asset_id),None)
        if not item:raise HTTPException(404,'Asset không thuộc batch')
        if body.action=='authorize_export' and item.get('automation'):
            item['automation']['export_authorized']=True
        elif body.action=='prioritize':item['priority']=min(1000,max(i['priority'] for i in value['items'])+1)
        elif body.action=='skip':item['skipped']=True
        elif body.action=='regenerate':
            if any(j['payload'].get('batch_id')==identifier and j['payload'].get('asset_id')==asset_id and j['status'] not in jobs.TERMINAL for j in jobs.listing()):raise HTTPException(409,'Finish or cancel the active asset stages before regenerating. Existing checkpoints are preserved.')
            item.update(attempt=item['attempt']+1,started=True,skipped=False,planner_version=1,production_cancelled=False)
            if value.get('production_cancelled'):value['production_cancelled']=any(i.get('production_cancelled') for i in value['items'])
            item.pop('asset_generation_spec',None)
            if item.get('automation'):
                item['automation']=dict(enabled=True,engines=item['automation']['engines'],attempt=item['attempt'],status='queued',stage='pending',checkpoints={},human_approved=False)
            item.pop('last_error',None)
        elif body.action=='retry':
            item.pop('last_error',None)
            item.get('automation',{}).pop('retry_required',None)
            failed=[j for j in jobs.listing() if j['payload'].get('batch_id')==identifier and j['payload'].get('asset_id')==asset_id and j['payload'].get('batch_attempt',0)==item['attempt'] and j['status'] in ['FAILED','BLOCKED','CANCELLED']]
            if failed:jobs.retry(failed[0]['id'])
        else:raise HTTPException(400,'Action không hợp lệ')
        save(value)
    return advance(identifier)


@router.get('/{identifier}/export')
def export(identifier:str,selection:str='selected',format:str='zip'):
    value=detail(batch(identifier));items=[i for i in value['items'] if selection=='all' or (selection=='approved' and i['status'] in ['Approved','Exported']) or (selection=='selected' and i['selected'])]
    if selection not in ['all','approved','selected']:raise HTTPException(400,'Selection không hợp lệ')
    manifest=json.dumps(dict(batch_id=identifier,project_id=value['project_id'],items=items),indent=2,ensure_ascii=False)
    if format=='json':return Response(manifest,media_type='application/json',headers={'Content-Disposition':'attachment; filename="manifest.json"'})
    if format=='csv':
        buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=['asset_id','name','status','prompt','target_width_m','target_depth_m','target_height_m']);writer.writeheader();writer.writerows({k:i.get(k) for k in writer.fieldnames} for i in items)
        return Response(buffer.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="manifest.csv"'})
    if format!='zip':raise HTTPException(400,'Export format không hợp lệ')
    folder=store.DATA/'batches'/identifier/'exports';folder.mkdir(parents=True,exist_ok=True);target=folder/(uuid.uuid4().hex+'.zip')
    included=[];omitted=[]
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        archive.writestr('manifest.json',manifest)
        for item in items:
            model=studio.asset(item['asset_id']);versions=item['versions'];chosen=next((v for v in versions if v['id']==model['master_artifact_id']),None) or (versions[-1] if versions else None)
            if not chosen:omitted.append(dict(asset_id=item['asset_id'],reason='No generated mesh'));continue
            prefix='Assets/'+item['asset_id']+'/'
            source=store.safe_path(chosen['relative_path'])
            if store.digest(source)!=chosen['sha256']:raise HTTPException(409,'Source checksum changed')
            archive.write(source,prefix+'Master.glb');archive.writestr(prefix+'metadata.json',json.dumps(item,indent=2));included.append(item['asset_id'])
            job_id=chosen['metadata'].get('job_id')
            if job_id:
                source_folder=store.DATA/'jobs'/job_id/'output'
                for file in source_folder.rglob('*'):
                    if file.is_file() and file.suffix.lower() in ['.glb','.fbx','.png','.json']:
                        archive.write(file,prefix+'Outputs/'+file.relative_to(source_folder).as_posix())
        archive.writestr('export_report.json',json.dumps(dict(included_assets=included,omitted_assets=omitted,unity='NOT_TESTED',quality='NEEDS_REVIEW'),indent=2))
    return FileResponse(target,filename='AFS-batch-'+identifier[:8]+'.zip')
