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
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ValidationError
from . import store, jobs, studio
from .manifest import ManifestItem, parse

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
    return [k for k in ['target_width_m','target_depth_m','target_height_m'] if item.get(k) is None]+([] if item.get('confirmed') else ['specification_confirmation'])


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
    count=sum(i['candidates']*(2 if value['mode']=='Maximum Quality Batch' and i['preferred_engine']=='auto' else 1) for i in value['items'] if i['selected'])
    warnings=list(value.get('warnings',[]))
    if len(value['items'])>30:warnings.append('Batch lớn: duyệt subset trước. Không tự giảm chất lượng để tăng tốc.')
    value['preflight']=dict(engines={k:a.probe() for k,a in ADAPTERS.items()},concept_engine=CONCEPT_ADAPTER.probe(),ram_free_bytes=psutil.virtual_memory().available,
        disk_free_bytes=shutil.disk_usage(store.DATA).free,estimated_jobs=count,estimated_storage_bytes=None,planner='strict_local_structured_parser; no configured local LLM',warnings=warnings,
        scheduler=dict(heavy_gpu_concurrency=1,cpu_concurrency=2,quality_downgrade=False))
    value['progress']=dict(total=len(value['items']),completed=sum(i['status'] in ['Approved','Exported'] for i in value['items']),
        active=sum(i['status'] in ['Generating','Processing'] for i in value['items']),blocked=sum(bool(i['missing_fields']) or i['status'] in ['Failed/Blocked','QA Failed'] for i in value['items']))
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
    master_prompt:str=Field(min_length=1,max_length=1000000)
    format:str='auto'
    mode:str='Quality Batch'
    reference_ids:list[str]=Field(default_factory=list,max_length=50)


@router.post('/analyze',status_code=201)
def analyze(body:Analyze):
    project=studio.project(body.project_id)
    if body.mode not in MODES:raise HTTPException(400,'Batch quality mode không hợp lệ')
    for ref in body.reference_ids:studio.scoped_artifact(ref,body.project_id)
    try:rows,warnings=parse(body.master_prompt,body.format)
    except (ValueError,ValidationError) as exc:raise HTTPException(400,str(exc))
    identifier=uuid.uuid4().hex;items=[]
    for row in rows:
        item=ManifestItem.model_validate(row).model_dump();item['asset_id']=uuid.uuid5(uuid.UUID(identifier),item['name']).hex
        item['quality']={'Fast Batch':'Fast','Quality Batch':'Balanced','Maximum Quality Batch':'Maximum'}[body.mode]
        item.update(reference_ids=list(dict.fromkeys(body.reference_ids+item['reference_ids'])),attempt=0,started=False,version=1,quality_lock=body.mode=='Maximum Quality Batch')
        for ref in item['reference_ids']:studio.scoped_artifact(ref,body.project_id)
        model=dict(id=item['asset_id'],project_id=body.project_id,name=item['name'],prompt=item['prompt'],category=item['category'],favorite=False,status='Candidate',
            master_artifact_id=None,reference_ids=item['reference_ids'],settings=dict(batch_id=identifier,style_base=project,style_overrides=item['style_constraints']),approvals=[],created_at=store.now(),updated_at=store.now())
        items.append((item,model))
    value=dict(id=identifier,project_id=body.project_id,name=body.name,master_prompt=body.master_prompt,mode=body.mode,paused=True,
        quality_lock=body.mode=='Maximum Quality Batch',style_snapshot=project,warnings=warnings,items=[i for i,_ in items],created_at=store.now(),updated_at=store.now())
    with store.connect() as db:
        for item,model in items:db.execute('INSERT INTO assets VALUES (?,?,?)',(model['id'],body.project_id,json.dumps(model)))
        db.execute('INSERT INTO batches VALUES (?,?,?)',(identifier,body.project_id,json.dumps(value)))
    return detail(value)


@router.get('')
def listing(project_id:str):
    studio.project(project_id)
    with store.connect() as db:values=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches WHERE project_id=?',(project_id,))]
    return [detail(v) for v in values]


@router.get('/{identifier}')
def get(identifier:str):return detail(batch(identifier))


@router.post('/{identifier}/items/{asset_id}')
def edit(identifier:str,asset_id:str,body:dict):
    with LOCK:
        value=batch(identifier);item=next((i for i in value['items'] if i['asset_id']==asset_id),None)
        if not item:raise HTTPException(404,'Asset không thuộc batch')
        allowed=set(ManifestItem.model_fields)-{'asset_id','source_asset_id'}
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
                        engines=[e for e in ['trellis2_community','triposg'] if ADAPTERS[e].installed and (e!='triposg' or source['metadata'].get('has_transparency'))]
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


@router.post('/{identifier}/run')
def run(identifier:str,body:Run):
    with LOCK:
        value=batch(identifier);selected=set(body.selected_ids) if body.selected_ids is not None else {i['asset_id'] for i in value['items'] if i['selected']}
        for item in value['items']:
            if item['asset_id'] in selected and missing(item):raise HTTPException(409,f'{item["name"]}: cần xác nhận '+', '.join(missing(item)))
        for item in value['items']:
            if item['asset_id'] in selected:item['started']=True
        value['paused']=False;save(value)
    return advance(identifier)


class Control(BaseModel):action:str


@router.post('/{identifier}/control')
def control(identifier:str,body:Control):
    with LOCK:
        value=batch(identifier)
        if body.action=='duplicate':
            rows=[{k:v for k,v in i.items() if k in ManifestItem.model_fields and k not in ['asset_id','source_asset_id']} for i in value['items']]
            return analyze(Analyze(project_id=value['project_id'],name=value['name']+' copy',master_prompt=json.dumps(rows),format='json',mode=value['mode']))
        if body.action not in ['pause','resume','cancel']:raise HTTPException(400,'Action không hợp lệ')
        value['paused']=body.action!='resume';save(value)
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
        if body.action=='prioritize':item['priority']=min(1000,max(i['priority'] for i in value['items'])+1)
        elif body.action=='skip':item['skipped']=True
        elif body.action=='regenerate':
            item.update(attempt=item['attempt']+1,started=True,skipped=False)
            item.pop('last_error',None)
        elif body.action=='retry':
            item.pop('last_error',None)
            failed=[j for j in jobs.listing() if j['payload'].get('batch_id')==identifier and j['payload'].get('asset_id')==asset_id and j['status'] in ['FAILED','BLOCKED','CANCELLED']]
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
