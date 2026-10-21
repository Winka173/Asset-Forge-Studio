"""Independent public status dimensions projected from the existing durable production graph."""
import hashlib
import json
import sqlite3
from pathlib import Path
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from typing import Literal
from . import store
router=APIRouter(prefix='/api/production')
FIELDS=('production_status','stage_status','qa_status','export_status','art_review_status','attention_required')
PRODUCTION_STATES={'draft','queued','preparing','generating','processing','validating','exporting','completed','needs_attention','failed','paused','cancelled'}
POLICIES=('auto','review_flagged','manual_approval')


def policy(model,settings=None):
    if model.get('review_policy') in POLICIES:return model['review_policy']
    return (settings or {}).get('review_policy','auto')


def approved(model,artifact_id):
    decisions=sorted([r for r in model.get('art_reviews',[])+model.get('approvals',[]) if r.get('artifact_id')==artifact_id],key=lambda r:r.get('at') or r.get('created_at') or '')
    return bool(decisions and decisions[-1].get('decision','approved')=='approved' and decisions[-1].get('reviewer'))


def migrate():
    with store.SCHEMA_LOCK:
        with store.connect() as db:
            if db.execute("SELECT 1 FROM migrations WHERE id='production_status_dimensions_v1'").fetchone():return
            # Backup before any existing asset payload is changed; SQLite backup includes WAL.
            folder=store.DATA/'backups';folder.mkdir(exist_ok=True)
            target=folder/'studio-before-production-status-v1.sqlite'
            if not target.exists():
                temporary=target.with_suffix('.sqlite.part')
                backup=sqlite3.connect(temporary)
                try:db.backup(backup)
                finally:backup.close()
                temporary.replace(target)
            for row in db.execute('SELECT id,payload FROM assets').fetchall():
                value=json.loads(row['payload']);value.setdefault('legacy_status',value.get('status'))
                value.setdefault('original_prompt',value.get('prompt',''));value.setdefault('original_prompt_sha256',hashlib.sha256(value['original_prompt'].encode()).hexdigest())
                value.setdefault('art_review_status','not_reviewed')
                value.setdefault('status_migration',dict(version=1,at=store.now(),original_status=value.get('status')))
                db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(value),row['id']))
            db.execute("INSERT INTO migrations VALUES ('production_status_dimensions_v1')")


def refresh_all():
    from . import jobs
    migrate()
    with store.connect() as db:
        models={r['id']:json.loads(r['payload']) for r in db.execute('SELECT id,payload FROM assets')}
        artifacts=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts')]
        groups=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches')]
        has_exports=db.execute("SELECT 1 FROM sqlite_master WHERE name='selective_exports'").fetchone()
        exports=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM selective_exports')] if has_exports else []
    all_jobs=jobs.listing()
    grouped={}
    for g in groups:
        for i in g['items']:
            if i.get('started'):grouped[i['asset_id']]=(g,i)
    from .production import global_paused
    all_paused=global_paused()
    for identifier,model in models.items():
        pair=grouped.get(identifier);g,i=pair if pair else ({},{})
        related=[j for j in all_jobs if j['payload'].get('asset_id')==identifier and (not pair or j['payload'].get('batch_id')==g['id'] and j['payload'].get('batch_attempt',0)==i.get('attempt',0))]
        retried={j['payload'].get('retry_of') for j in related};related=[j for j in related if j['id'] not in retried]
        # Revision jobs retain the stable identity and are included in the same status projection.
        revisions=model.get('revisions',[])
        if revisions and revisions[-1].get('state') not in ('published','staged','failed','cancelled'):
            ids=set(revisions[-1].get('job_ids',[]));related=[j for j in all_jobs if j['id'] in ids]
        auto=i.get('automation',{});mine=[a for a in artifacts if a.get('asset_id')==identifier and a['role']=='candidate'];processed=[a for a in mine if a['metadata'].get('stage')=='blender_processed']
        valid_exports=[e for e in exports if e['asset_id']==identifier and e['status']=='COMPLETED'];delivery=next((e for e in reversed(valid_exports) if e.get('delivery_scope')!='staged'),None)
        current_id=revisions[-1].get('artifact_id') if revisions else (processed[-1]['id'] if processed else mine[-1]['id'] if mine else None)
        if revisions:valid_exports=[e for e in valid_exports if e['artifact_id']==current_id]
        decisions=sorted([r for r in model.get('art_reviews',[])+model.get('approvals',[]) if r.get('artifact_id')==current_id],key=lambda r:r.get('at') or r.get('created_at') or '')
        art=(decisions[-1].get('decision','approved') if decisions and decisions[-1].get('reviewer') else 'not_reviewed')
        active=[j for j in related if j['status'] not in jobs.TERMINAL|{'QUEUED'}];queued=[j for j in related if j['status']=='QUEUED'];failed=[j for j in related if j['status'] in ('FAILED','BLOCKED')]
        qa='passed' if valid_exports or any(j['payload']['kind']=='blender' and j['status']=='REVIEW_REQUIRED' for j in related) else 'not_run'
        export='exported' if valid_exports else 'not_exported';stage='completed' if related and all(j['status']=='REVIEW_REQUIRED' for j in related) else 'pending';production='draft';reasons=[]
        if auto.get('status')=='exported' or (valid_exports and not revisions):production='completed'
        elif i.get('started') or queued:production='queued'
        elif mine:production='needs_attention';reasons.append(dict(kind='technical',message='Existing candidate has no completed validated delivery. Run Enhance / Export to finish.'))
        paused=g.get('paused') or i.get('production_paused') or all_paused
        if queued and paused:production='paused';stage='paused'
        if active:
            job=active[0];kind=job['payload']['kind'];stage='running'
            production='validating' if job['status']=='VALIDATING' else 'processing' if kind=='blender' else 'generating'
            if job['status']=='VALIDATING':qa='running'
        elif failed and auto.get('status')!='exported':
            production='failed' if failed[0]['status']=='FAILED' else 'needs_attention';stage='failed' if production=='failed' else 'blocked'
            if failed[0]['payload']['kind']=='blender':qa='failed'
            reasons.append(dict(kind='engine_or_qa',message=failed[0].get('error') or 'Retry the failed stage or change the engine.'))
        elif auto.get('status') in ('blocked','failed'):
            production='failed' if auto['status']=='failed' else 'needs_attention';stage='blocked';reasons.append(dict(kind='manual_approval' if 'Review' in auto.get('stage','') or 'approval' in auto.get('stage','').lower() else 'input_or_dependency',message=auto.get('error') or auto.get('stage')))
        if (i.get('skipped') or g.get('production_cancelled')) and production!='completed':production='cancelled';stage='skipped'
        if production=='completed':stage='completed';qa='passed';reasons=[]
        fields=dict(production_status=production,stage_status=stage,qa_status=qa,export_status=export,art_review_status=art,attention_required=bool(reasons) or production in ('failed','needs_attention'),attention_reasons=reasons,art_review_artifact_id=current_id,published_artifact_id=model.get('published_artifact_id') or (delivery['artifact_id'] if delivery else None))
        if any(model.get(k)!=v for k,v in fields.items()):
            model.setdefault('status_events',[]).append(dict(at=store.now(),previous={k:model.get(k) for k in FIELDS},current={k:fields[k] for k in FIELDS}))
            model.update(fields);model['status_updated_at']=store.now()
            if production=='completed' and model.get('status') in ('Under Review','Needs Review','Candidate'):model['status']='Completed'
            model.setdefault('original_prompt',model.get('prompt',''));model.setdefault('original_prompt_sha256',hashlib.sha256(model['original_prompt'].encode()).hexdigest())
            with store.connect() as db:
                # Only patch status fields; never replace a concurrently edited prompt or review record.
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT payload FROM assets WHERE id=?',(identifier,)).fetchone();latest=json.loads(row['payload'])
                for k in (*FIELDS,'attention_reasons','art_review_artifact_id','published_artifact_id','status_events','status_updated_at','original_prompt','original_prompt_sha256'):latest[k]=model[k]
                if model.get('status')=='Completed':latest['status']='Completed'
                db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(latest),identifier))
                models[identifier]=latest
    return models


class ReviewPolicy(BaseModel):
    review_policy:Literal['auto','review_flagged','manual_approval','inherit']


@router.post('/projects/{project_id}/review-policy')
def project_policy(project_id:str,body:ReviewPolicy):
    from . import automation
    if body.review_policy=='inherit':raise HTTPException(400,'Choose an explicit project policy')
    workflow=automation.project_workflow(project_id);workflow['review_policy']=body.review_policy
    return automation.save_project_workflow(project_id,automation.Workflow.model_validate(workflow))


@router.post('/assets/{asset_id}/review-policy')
def asset_policy(asset_id:str,body:ReviewPolicy):
    from . import studio
    model=studio.asset(asset_id);model['review_policy']=None if body.review_policy=='inherit' else body.review_policy;studio.save_asset(model);return dict(review_policy=body.review_policy)


class Decision(BaseModel):
    asset_id:str
    artifact_id:str
    decision:Literal['approved','rejected']

class BulkReview(BaseModel):
    entries:list[Decision]=Field(min_length=1,max_length=1000)
    reviewer:str=Field(min_length=1,max_length=100)
    notes:str=Field(default='',max_length=4000)


@router.post('/artistic-review')
def review(body:BulkReview):
    from . import studio
    completed=[];errors=[]
    for entry in body.entries:
        try:
            model=studio.asset(entry.asset_id);artifact=studio.scoped_artifact(entry.artifact_id,model['project_id'],entry.asset_id)
            if artifact['role']!='candidate':raise HTTPException(400,'Choose an actual candidate')
            decision=entry.model_dump()|dict(reviewer=body.reviewer,notes=body.notes,sha256=artifact['sha256'],at=store.now(),scope='human_artistic_review_only')
            model.setdefault('art_reviews',[]).append(decision)
            if entry.decision=='approved':model['master_artifact_id']=entry.artifact_id;model['status']='Approved'
            else:model['status']='Rejected'
            studio.save_asset(model);completed.append(decision)
        except HTTPException as e:errors.append(dict(asset_id=entry.asset_id,error=e.detail))
    refresh_all();return dict(completed=completed,errors=errors)
