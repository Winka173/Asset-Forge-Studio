"""Production read model and scoped controls over the existing durable queue."""
import json
import asyncio
import hashlib
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,Field
from . import store,jobs,batch,studio
router=APIRouter(prefix='/api/production')


def global_paused():
    with store.connect() as db:
        row=db.execute('SELECT payload FROM drafts WHERE project_id=?',('__afs_production__',)).fetchone()
    return bool(row and json.loads(row['payload']).get('paused'))



def prepare_exit_checkpoint():
    """Temporary shutdown admission hold, distinct from an explicit user Pause."""
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM drafts WHERE project_id=?',('__afs_production__',)).fetchone()
        previous=json.loads(row['payload']) if row else dict(paused=False)
        if previous.get('exit_checkpoint'):return previous
        value=dict(paused=True,updated_at=store.now(),exit_checkpoint=dict(previous=previous,at=store.now()))
        db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',('__afs_production__',json.dumps(value)))
    return value


def restore_exit_checkpoint():
    # Restart and Keep Open restore only our temporary hold. A later explicit
    # Pause/Resume replaces the record and cannot be silently undone here.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM drafts WHERE project_id=?',('__afs_production__',)).fetchone()
        value=json.loads(row['payload']) if row else {}
        if not value.get('exit_checkpoint'):return False
        previous=value['exit_checkpoint']['previous'];previous['updated_at']=store.now()
        db.execute('UPDATE drafts SET payload=? WHERE project_id=?',(json.dumps(previous),'__afs_production__'))
    return True


def eligible(payload):
    if global_paused() or payload.get('production_paused'):return False
    if payload.get('asset_id') and not payload.get('batch_id'):
        try:
            if studio.asset(payload['asset_id']).get('production_paused'):return False
        except HTTPException:return False
    if payload.get('batch_id'):
        value=batch.batch(payload['batch_id']);item=next((i for i in value['items'] if i['asset_id']==payload.get('asset_id')),None)
        return bool(not value['paused'] and item and not item.get('production_paused') and not item.get('skipped'))
    return True


def scheduling_score(job,priority):
    # Aging is unbounded: a long-waiting Normal task eventually outranks new Next work.
    age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(job['created_at'])).total_seconds())
    return priority+age/60


def batches():
    with store.connect() as db:return [json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches ORDER BY rowid DESC')]


def job_summary(j):
    return {k:j.get(k) for k in ('id','status','created_at','updated_at','progress','error')}|dict(kind=j['payload']['kind'],engine=j['payload'].get('engine'),seed=j['payload'].get('seed'),artifact_id=j['payload'].get('artifact_id'),asset_id=j['payload'].get('asset_id'),project_id=j['payload'].get('project_id'),batch_id=j['payload'].get('batch_id'),batch_attempt=j['payload'].get('batch_attempt',0),priority=j['payload'].get('priority',0),paused=j['payload'].get('production_paused',False))


def wait_context(all_jobs,models):
    """Shared facts for explaining why waiting assets have not started."""
    with store.connect() as db:row=db.execute('SELECT payload FROM drafts WHERE project_id=?',('__afs_production__',)).fetchone()
    pause=json.loads(row['payload']) if row else {}
    running=[j for j in all_jobs if j['status'] not in jobs.TERMINAL|{'QUEUED'}]
    queued=[j for j in all_jobs if j['status']=='QUEUED']
    name=lambda j:(models.get(j['payload'].get('asset_id')) or {}).get('name') or 'another asset'
    return dict(paused_since=pause.get('updated_at') if pause.get('paused') else None,running=running,queued=queued,name=name)


def wait_reason(i,group,related,auto,context):
    """Why a started asset is not running right now (None while it runs or is finished)."""
    if not context or not i.get('started') or auto.get('status') in ('exported','completed','failed','blocked','cancelled'):return None
    if any(j['status'] not in jobs.TERMINAL|{'QUEUED'} for j in related):return None
    if context['paused_since']:
        return dict(code='paused_all',since=context['paused_since'],message='All production is paused. Press Resume all to continue.')
    if group['paused'] or i.get('production_paused'):return dict(code='paused',message='This asset or its batch is paused. Press Resume to continue.')
    if auto.get('status')=='waiting_for_answers':return dict(code='questions',message='Waiting for your answers to its questions.')
    waiting=next((j for j in related if j['status']=='QUEUED'),None)
    if waiting:
        progress=waiting.get('progress') or {}
        if progress.get('reason_code') in ('HOST_RAM_ADMISSION','HOST_COMMIT_ADMISSION'):return dict(code='ram',message=progress.get('stage') or 'Waiting for free memory.')
        kind=jobs.resource_class(waiting['payload'])
        busy=[j for j in context['running'] if jobs.resource_class(j['payload'])==kind]
        if busy:
            score=scheduling_score(waiting,waiting['payload'].get('priority',0))
            ahead=sum(1 for j in context['queued'] if j['id']!=waiting['id'] and jobs.resource_class(j['payload'])==kind and eligible(j['payload']) and scheduling_score(j,j['payload'].get('priority',0))>score)
            current=busy[0];stage=(current.get('progress') or {}).get('stage') or current['payload']['kind']
            where='the GPU' if kind=='gpu' else 'a CPU slot'
            return dict(code=kind,message=f"Waiting for {where}: {context['name'](current)} is running ({stage}). {ahead} waiting ahead of this asset.",ahead=ahead)
        return dict(code='queued',message='Queued; starting shortly.')
    stage=auto.get('stage') or ''
    if 'dependency' in stage.lower():
        return dict(code='dependency',message='Waiting for assets it depends on: '+', '.join(i.get('dependencies',[])[:4])+'.')
    if auto.get('status') in ('queued','running',None) and i.get('started'):
        others=sum(1 for j in context['running']+context['queued'] if j['payload'].get('batch_id')==group['id'] and j['payload'].get('asset_id')!=i['asset_id'])
        if others:return dict(code='slot',message=f"Waiting for a free production slot; other assets in this batch are in progress ({stage or 'pending'}).")
    return None


def item_summary(i,group,all_jobs,all_paused=False,model=None,context=None):
    related=[j for j in all_jobs if j['payload'].get('asset_id')==i['asset_id'] and j['payload'].get('batch_id')==group['id'] and j['payload'].get('batch_attempt',0)==i.get('attempt',0) and j['payload'].get('kind')!='rig']
    revisions=(model or {}).get('revisions',[])
    if revisions:
        revision_jobs=[j for j in all_jobs if j['id'] in revisions[-1].get('job_ids',[])]
        if revision_jobs and max(j['created_at'] for j in revision_jobs)>=max((j['created_at'] for j in related),default=''):
            related=revision_jobs
        elif not revision_jobs and revisions[-1].get('state') not in ('published','staged','cancelled','failed') and revisions[-1].get('created_at','')>max((j['created_at'] for j in related),default=''):
            related=[]  # a new prompt was just submitted: show its pipeline as pending, not the previous result
    retried={j['payload'].get('retry_of') for j in related};related=[j for j in related if j['id'] not in retried]
    auto=i.get('automation',{});status=auto.get('status') or ('running' if any(j['status'] not in jobs.TERMINAL for j in related) else 'draft')
    active=any(j['status'] not in jobs.TERMINAL|{'QUEUED'} for j in related)
    paused=group['paused'] or i.get('production_paused') or all_paused
    if (i.get('production_cancelled',group.get('production_cancelled')) or i.get('skipped')) and status not in ('exported','completed'):status='cancelled'
    if paused and i.get('started') and status!='cancelled' and status not in ('exported','completed','failed','blocked'):status='pausing' if active else 'paused'
    running=next((j for j in related if j['status'] not in jobs.TERMINAL|{'QUEUED'}),None)
    stage=(running.get('progress') or {}).get('stage') if running else None
    waiting=wait_reason(i,group,related,auto,context)
    return dict(waiting=waiting,id=i['asset_id'],source_id=i.get('source_asset_id'),name=i['name'],status=status,stage=stage or auto.get('stage'),current_stage=stage or auto.get('stage'),attempt=i.get('attempt',0),error=auto.get('error'),selected=i.get('selected'),started=i.get('started'),future=i.get('source_status')=='FUTURE',priority=i.get('priority',0),paused=bool(paused),jobs=[job_summary(j) for j in related])


@router.get('')
def overview():
    from .statuses import refresh_all,FIELDS
    models=refresh_all()
    all_jobs=jobs.listing();groups=[];all_paused=global_paused();seen=set();context=wait_context(all_jobs,models)
    with store.connect() as db:projects={r['id']:json.loads(r['payload'])['name'] for r in db.execute('SELECT id,payload FROM projects')}
    for value in batches():
        if value.get('revision_of'):continue
        # Imported drafts are shown only after explicit generation admission.
        if not any(i.get('started') for i in value['items']) and not any(j['payload'].get('batch_id')==value['id'] for j in all_jobs):continue
        admitted={j['payload'].get('asset_id') for j in all_jobs if j['payload'].get('batch_id')==value['id']}
        items=[item_summary(i,value,all_jobs,all_paused,models.get(i['asset_id']),context) for i in value['items'] if i['asset_id'] not in seen and (i.get('started') or i['asset_id'] in admitted)]
        if not items:continue
        seen.update(i['id'] for i in items)
        for i in items:
            model=models.get(i['id'],{})
            i.update({k:model.get(k) for k in FIELDS})
            i['attention_reasons']=model.get('attention_reasons',[])
            i['stage']=model.get('stage_status',i['stage']) if model.get('production_status')=='completed' else i['stage']
            i['status']=model.get('production_status',i['status'])
            i['needs_review']=model.get('art_review_status')=='not_reviewed' and model.get('production_status')=='completed'
        counts={s:sum(i['status']==s for i in items) for s in ('running','preparing','generating','processing','validating','exporting','queued','paused','pausing','exported','completed','needs_attention','failed','blocked','draft')}
        counts['completed']=sum(i['status'] in ('completed','exported') for i in items)
        counts['running']=sum(i['status'] in ('preparing','generating','processing','validating','exporting') for i in items)
        counts['exported']=sum(i.get('export_status')=='exported' for i in items)
        counts['blocked']=sum(i.get('stage_status')=='blocked' for i in items)
        counts['needs_attention']=sum(bool(i.get('attention_required')) for i in items)
        counts['needs_review']=sum(i.get('needs_review',False) for i in items)
        groups.append(dict(id=value['id'],name=value['name'],project_id=value['project_id'],project_name=projects.get(value['project_id'],value['project_id']),kind='single' if len(items)==1 else 'batch',paused=value['paused'],created_at=value['created_at'],started_at=value.get('automation',{}).get('started_at'),counts=counts,items=items,imported_count=len(value['items']),admitted_count=len(items)))
    standalone={}
    for j in all_jobs:
        asset_id=j['payload'].get('asset_id')
        if not j['payload'].get('batch_id') and asset_id and asset_id not in seen:standalone.setdefault(asset_id,[]).append(j)
    loose=[]
    for asset_id,history in standalone.items():
        retried={j['payload'].get('retry_of') for j in history}
        leaves=[j for j in history if j['id'] not in retried]
        current=next((j for j in leaves if j['status'] not in jobs.TERMINAL),leaves[0]);root=history[-1]
        loose.append(job_summary(current)|dict(id=root['id'],display_name=models.get(asset_id,{}).get('name',asset_id),jobs=[job_summary(j) for j in leaves])|{key:models.get(asset_id,{}).get(key) for key in FIELDS})
    return dict(groups=groups,standalone=loose,paused=all_paused,paused_since=context['paused_since'],gpu_concurrency=1,updated_at=store.now())


def artifact_info(a):return {k:a.get(k) for k in ('id','name','role','url','sha256','metadata','created_at')}


@router.get('/assets/{asset_id}')
def detail(asset_id:str):
    from .statuses import refresh_all,FIELDS
    model=refresh_all().get(asset_id) or studio.asset(asset_id)
    with store.connect() as db:artifacts=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=?',(asset_id,))]
    # Explicit reinspection augments the matching version's displayed evidence;
    # it never changes source bytes, approval, publication or other versions.
    inspection=model.get('latest_inspection') or {}
    for artifact in artifacts:
        if artifact['id']==inspection.get('artifact_id') and artifact['sha256']==inspection.get('sha256'):
            artifact['metadata']={**artifact['metadata'],**inspection['report'],'inspection_at':inspection['at']}
    for reference_id in model.get('reference_ids',[]):
        if not any(a['id']==reference_id for a in artifacts):
            try:
                a=store.get_artifact(reference_id)
                if a.get('project_id')==model['project_id']:artifacts.append(a)
            except KeyError:pass
    related=[j for j in jobs.listing() if j['payload'].get('asset_id')==asset_id];stages=[]
    for j in reversed(related):
        folder=store.DATA/'jobs'/j['id'];resources=folder/'resources.json';metrics=json.loads(resources.read_text()) if resources.exists() else {}
        logs=folder/'worker.log';tail=''
        if logs.exists():
            with logs.open('rb') as stream:stream.seek(max(0,logs.stat().st_size-16000));tail=stream.read().decode('utf-8',errors='replace')
        report=folder/'output/report.json';qa=json.loads(report.read_text()) if report.exists() else None
        preservation=folder/'output/pbr_preservation.json'
        if preservation.is_file():qa={**(qa or {}),'pbr_preservation':json.loads(preservation.read_text(encoding='utf-8'))}
        layout=folder/'concept_layout.json'
        layout_qa=json.loads(layout.read_text(encoding='utf-8')) if layout.is_file() else None
        visual=folder/'model_visual_check.json'
        if visual.is_file():layout_qa=json.loads(visual.read_text(encoding='utf-8'))
        stages.append(job_summary(j)|dict(events=j['payload'].get('stage_events',[]),duration_seconds=metrics.get('duration_seconds'),started_at=metrics.get('started_at') or next((e['at'] for e in j['payload'].get('stage_events',[]) if e['state']=='RUNNING'),None),finished_at=metrics.get('finished_at'),logs=tail,qa=({k:qa.get(k) for k in ('status','checks','after','materials','dimensions_xyz_m_blender','animation','deformation','pbr_preservation')} if qa else layout_qa)))
    from .export_profiles import export_history
    return dict(asset={k:model.get(k) for k in ('id','name','project_id','prompt','status','tags','recovery_notice','reference_ids','master_artifact_id','settings','original_prompt','resolved_specification','quality_evaluations','review_policy','art_reviews','revisions','published_artifact_id','publication_history','approvals','attention_reasons',*FIELDS)},artifacts=[artifact_info(a) for a in artifacts],stages=stages,exports=export_history(asset_id))


class Control(BaseModel):
    action:Literal['pause','resume','cancel','retry_failed','retry_concept','skip_failed','regenerate','prioritize','skip']
    scope:Literal['all','batch','asset','job']
    group_id:str|None=None
    asset_id:str|None=None
    job_id:str|None=None
    priority:Literal['next','normal','batch_order']='normal'
    request_id:str|None=Field(default=None,min_length=8,max_length=100)


@router.post('/control')
def control(body:Control):
    with batch.LOCK:
        if body.scope=='all':
            if body.action not in ('pause','resume'):raise HTTPException(400,'Pause All / Resume All only; cancel requires an explicit asset or batch')
            with store.connect() as db:db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',('__afs_production__',json.dumps(dict(paused=body.action=='pause',updated_at=store.now()))))
            # Resume All intentionally releases explicit per-group/per-asset pauses too.
            if body.action=='resume':
                for group in batches():
                    if group.get('production_cancelled'):continue
                    for item in group['items']:item['production_paused']=False
                    batch.save(group)
                    if any(i.get('started') for i in group['items']):batch.control(group['id'],batch.Control(action='resume'))
                with store.connect() as db:
                    for row in db.execute('SELECT id,payload FROM assets').fetchall():
                        model=json.loads(row['payload'])
                        if model.pop('production_paused',None):db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(model),row['id']))
                    for row in db.execute("SELECT id,payload FROM jobs WHERE status='QUEUED'").fetchall():
                        p=json.loads(row['payload']);p.pop('production_paused',None);db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(p),row['id']))
        elif body.scope in ('batch','asset'):
            if not body.group_id:raise HTTPException(400,'Select a group')
            value=batch.batch(body.group_id)
            if body.scope=='batch':
                result=batch.control(body.group_id,batch.Control(action=body.action))
                for child in batches():
                    if child.get('revision_of')==body.group_id:batch.control(child['id'],batch.Control(action=body.action))
                return result
            if body.asset_id:
                model=studio.asset(body.asset_id)
                revision=next((r for r in reversed(model.get('revisions',[])) if r.get('group_id')),None)
                if revision and revision.get('state') not in ('published','staged','cancelled'):
                    body=body.model_copy(update={'group_id':revision['group_id']});value=batch.batch(body.group_id)
            item=next((i for i in value['items'] if i['asset_id']==body.asset_id),None)
            if not item:raise HTTPException(404,'Asset is outside the selected batch')
            if body.action=='retry_concept':
                from .concept_guard import retry_blocked
                return retry_blocked(value,item,body.request_id)
            if body.action in ('pause','resume'):
                item['production_paused']=body.action=='pause';batch.save(value)
            elif body.action=='prioritize':
                item['priority']={'next':100,'normal':0,'batch_order':-10}[body.priority];batch.save(value)
            elif body.action=='cancel':
                item['skipped']=True;item['production_paused']=True;item.setdefault('automation',{})['status']='cancelled';batch.save(value)
                for j in jobs.listing():
                    if j['payload'].get('batch_id')==body.group_id and j['payload'].get('asset_id')==body.asset_id and j['status'] not in jobs.TERMINAL:jobs.transition(j['id'],'CANCELLED','Cancelled by user')
            else:return batch.item_action(body.group_id,body.asset_id,batch.Control(action='retry' if body.action=='retry_failed' else body.action))
        else:
            if not body.job_id:raise HTTPException(400,'Select a job')
            j=jobs.get(body.job_id)
            asset_id=j['payload'].get('asset_id')
            related=[v for v in jobs.listing() if asset_id and v['payload'].get('asset_id')==asset_id and not v['payload'].get('batch_id')] if not j['payload'].get('batch_id') else [j]
            if not related:related=[j]
            if body.action=='cancel':
                for stage in related:
                    if stage['status'] not in jobs.TERMINAL:jobs.transition(stage['id'],'CANCELLED','Cancelled by user')
            elif body.action=='retry_failed':
                j=next((v for v in related if v['status'] in ('FAILED','BLOCKED','CANCELLED')),j)
                if j['status'] not in ('FAILED','BLOCKED','CANCELLED'):raise HTTPException(409,'Only failed or interrupted stages can be retried. Use Regenerate for a new version.')
                jobs.retry(j['id'])
            elif body.action in ('pause','resume','prioritize'):
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if asset_id and not j['payload'].get('batch_id') and body.action in ('pause','resume'):
                        row=db.execute('SELECT payload FROM assets WHERE id=?',(asset_id,)).fetchone()
                        if row:
                            model=json.loads(row['payload']);model['production_paused']=body.action=='pause'
                            db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(model),asset_id))
                    for stage in related:
                        p=json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(stage['id'],)).fetchone()['payload'])
                        if body.action=='prioritize':p['priority']={'next':100,'normal':0,'batch_order':-10}[body.priority]
                        else:p['production_paused']=body.action=='pause'
                        db.execute('UPDATE jobs SET payload=?,updated_at=? WHERE id=?',(json.dumps(p),store.now(),stage['id']))
            else:raise HTTPException(400,'Unsupported job action')
    return dict(ok=True,paused=global_paused())


@router.get('/events')
async def events(request:Request):
    async def stream():
        previous=None
        while not getattr(request.app.state,'shutting_down',False) and not await request.is_disconnected():
            with store.connect() as db:
                changes=[tuple(r) for r in db.execute('SELECT id,status,updated_at FROM jobs')]
                changes += [tuple(r) for r in db.execute("SELECT id,json_extract(payload,'$.updated_at') FROM batches")]
                row=db.execute("SELECT payload FROM drafts WHERE project_id='__afs_production__'").fetchone()
                changes.append(tuple(row) if row else ())
            revision=hashlib.sha256(json.dumps(changes).encode()).hexdigest()
            if revision!=previous:
                previous=revision
                yield 'event: queue\ndata: '+json.dumps(dict(revision=revision))+'\n\n'
            else:yield ': heartbeat\n\n'
            await asyncio.sleep(2)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.get('/status')
def global_status():
    with store.connect() as db:counts={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) AS n FROM jobs GROUP BY status')}
    return dict(running=sum(counts.get(s,0) for s in ('RUNNING','GENERATED','POSTPROCESSING','VALIDATING')),queued=counts.get('QUEUED',0),paused=global_paused())

class ResolveInput(BaseModel):
    group_id:str
    asset_ids:list[str]=Field(min_length=1,max_length=1000)
    prompt:str|None=Field(default=None,max_length=100000)
    engine:Literal['auto','trellis2_community','triposg']|None=None


@router.post('/resolve-input')
def resolve_input(body:ResolveInput):
    """Explicit corrections for blocked assets; independent failures do not block the group."""
    from . import automation
    from .statuses import refresh_all
    if body.prompt is None and body.engine is None:raise HTTPException(400,'Enter missing input or select an engine')
    if body.prompt is not None and not body.prompt.strip():raise HTTPException(400,'Enter the essential asset description')
    completed=[];errors=[]
    with batch.LOCK:
        value=batch.batch(body.group_id);ids={i['asset_id'] for i in value['items']}
        if set(body.asset_ids)-ids:raise HTTPException(400,'Selection contains assets from another group')
        models=refresh_all()
        for asset_id in dict.fromkeys(body.asset_ids):
            try:
                model=models[asset_id]
                if not model.get('attention_required'):raise HTTPException(409,'This asset does not need correction. Use Refine for a new revision.')
                if model.get('export_status')=='exported':raise HTTPException(409,'An exported version already exists. Use Refine to preserve game delivery.')
                changes={}
                if body.prompt is not None:changes['prompt']=body.prompt
                if body.engine is not None:changes['preferred_engine']=body.engine
                batch.edit(body.group_id,asset_id,changes)
                latest=batch.batch(body.group_id);item=next(i for i in latest['items'] if i['asset_id']==asset_id)
                item.pop('resolved_prompt',None);item.setdefault('input_resolution_history',[]).append(dict(at=store.now(),changes=changes,original_prompt_sha256=model.get('original_prompt_sha256')))
                item.pop('automation',None);item['skipped']=False;batch.save(latest)
                automation.start(body.group_id,[asset_id],workflow=latest.get('automation',{}).get('settings'))
                completed.append(asset_id)
            except HTTPException as exc:errors.append(dict(asset_id=asset_id,error=exc.detail))
    return dict(completed=completed,errors=errors)
