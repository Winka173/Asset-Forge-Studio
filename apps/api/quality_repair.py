"""Cause-specific recovery over the existing job graph, never a second queue."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field
from . import jobs,store,engine_health


class RepairBudget(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_attempts:int=Field(default=3,ge=0,le=12)
    per_stage:int=Field(default=2,ge=0,le=4)
    per_cause:int=Field(default=1,ge=0,le=3)
    gpu_seconds:float=Field(default=7200,ge=0,le=86400)
    cpu_seconds:float=Field(default=7200,ge=0,le=86400)
    disk_gb:float=Field(default=16,ge=0,le=256)


def measurements(job):
    folder=store.DATA/'jobs'/job['id'];path=folder/'resources.json';data={}
    if path.is_file():
        try:data=json.loads(path.read_text('utf-8'))
        except (OSError,ValueError):pass
    elapsed=data.get('duration_seconds')
    if not isinstance(elapsed,(float,int)):
        events=job['payload'].get('stage_events',[])
        started=next((e['at'] for e in events if e['state']=='RUNNING'),None)
        elapsed=max(0,(datetime.fromisoformat(job['updated_at'])-datetime.fromisoformat(started)).total_seconds()) if started else None
    return dict(seconds=elapsed,resource=jobs.resource_class(job['payload']),disk_bytes=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()) if folder.exists() else 0,
        basis='Persisted resource receipt / stage events; disk bytes measured on retained attempt')


def budget_check(value,item,all_jobs,stage,cause,prediction=None):
    limits=RepairBudget.model_validate(value['automation']['settings'].get('repair_budget',{})).model_dump()
    scoped=[j for j in all_jobs if j['payload'].get('batch_id')==value['id'] and j['payload'].get('asset_id')==item['asset_id'] and j['payload'].get('batch_attempt',0)==item['attempt']]
    repairs=[j for j in scoped if j['payload'].get('quality_repair')]
    used=dict(attempts=len(repairs),stage_attempts=sum(j['payload']['kind']==stage for j in repairs),cause_attempts=sum((j['payload']['quality_repair'] or {}).get('root_cause')==cause for j in repairs),gpu_seconds=0.,cpu_seconds=0.,disk_bytes=0)
    for job in scoped:
        measured=measurements(job);used[measured['resource']+'_seconds']+=measured['seconds'] or 0;used['disk_bytes']+=measured['disk_bytes']
    reason=None
    retry_limit=value['automation']['settings'].get('retry_limit',1)
    if used['attempts']>=limits['max_attempts']:reason='Asset repair attempt budget exhausted'
    elif used['stage_attempts']>=min(limits['per_stage'],retry_limit):reason='Stage repair attempt budget exhausted'
    elif used['cause_attempts']>=limits['per_cause']:reason='Same root cause already retried; no-progress stop'
    elif used['disk_bytes']+(prediction or {}).get('disk_bytes',0)>limits['disk_gb']*1024**3:reason='Retained-attempt disk budget exhausted; no source files deleted'
    else:
        for resource in ('gpu','cpu'):
            extra=((prediction or {}).get('seconds') or 0) if (prediction or {}).get('resource')==resource else 0
            if used[resource+'_seconds']+extra>limits[resource+'_seconds']:reason=resource.upper()+' recovery time budget exhausted'
    return dict(allowed=not reason,reason=reason,used=used,limits=limits,
        scope='Current asset attempt across engines; elapsed/disk include failed stages and retained recovery outputs. Prediction reuses the last measured attempt, not a guarantee.')


def remember(item,plan):
    history=item.setdefault('repair_history',[])
    if not any(p['id']==plan['id'] for p in history):history.append(plan)
    item.setdefault('automation',{})['repair_plan']=plan
    return plan


class QualityRepairPlanner:
    def stage(self,value,item,failed,all_jobs):
        cached=item.get('automation',{}).get('repair_plan')
        if cached and cached.get('source_job_id')==failed['id']:return cached
        folder=store.DATA/'jobs'/failed['id'];diagnostic=folder/'diagnostic.json'
        cause,remedy=engine_health.classify(failed.get('error') or '')
        if diagnostic.is_file():
            try:cause=json.loads(diagnostic.read_text('utf-8')).get('root_cause') or cause
            except (OSError,ValueError):pass
        text=(failed.get('error') or '').lower()
        if 'connection reset' in text or 'temporar' in text:cause='TRANSIENT_IO'
        measured=measurements(failed);budget=budget_check(value,item,all_jobs,failed['payload']['kind'],cause,measured)
        plan=dict(schema_version=1,id='repair:'+failed['id'],source_job_id=failed['id'],root_cause=cause,stage=failed['payload']['kind'],engine=failed['payload'].get('engine'),
            action='needs_attention',reason=remedy,at=store.now(),budget=budget,predicted_cost=measured,
            validation=['Re-run the same stage validators and downstream mandatory gates','Retain all successful upstream outputs; never infer artistic approval'],
            quality_preserved=True,effective_config_hash=failed['payload'].get('effective_config_hash'),conditions={})
        if failed['status']=='CANCELLED':plan['reason']='Explicit cancellation is not an automatic retry'
        elif not budget['allowed']:plan['reason']=budget['reason']
        elif cause in ('INTERRUPTED','TRANSIENT_IO'):
            plan.update(action='retry_stage',reason='Restart only the interrupted/transient stage after its process has stopped')
        elif cause=='CUDA_OOM':
            # An unchanged seed with unchanged pressure is not a meaningful fix.
            try:
                import subprocess
                generation=json.loads((folder/'output/generation.json').read_text('utf-8'))
                baseline=generation['environment']['free_vram_start_bytes']
                result=subprocess.run(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
                free=float(result.stdout.strip().splitlines()[0])*1024**2
                plan['conditions']=dict(failed_start_free_bytes=baseline,current_free_bytes=free,required_improvement_bytes=512*1024**2)
                if free-baseline>=512*1024**2:plan.update(action='retry_stage',reason='Measured competing VRAM pressure decreased by at least 512 MiB; one identical-profile retry')
                else:plan['reason']='OOM conditions have not measurably improved; free VRAM or validate an offload profile before retry'
            except (OSError,ValueError,KeyError,IndexError,TypeError,subprocess.TimeoutExpired):plan['reason']='OOM baseline/current VRAM unavailable; no blind retry or quality downgrade'
        elif cause=='PROCESS_TIMEOUT':plan['reason']='Timeout needs a validated checkpoint or an explicitly revised timeout/resource condition; no blind full inference retry'
        elif cause=='EMPTY_GEOMETRY':plan['reason']='Geometry generation must be investigated; texturing/export are not admitted. No unverified alternate engine or seed loop.'
        elif cause=='EXPORT_VALIDATION':plan['reason']='Retained master is available; inspect the failing Blender/export validator before retrying only that stage'
        if budget['allowed'] and failed['status']!='CANCELLED' and cause in ('INTERRUPTED','TRANSIENT_IO','EXPORT_VALIDATION') and failed['payload'].get('engine')=='trellis2_community':
            from .native_checkpoint import checkpoint_for
            try:
                checkpoint=checkpoint_for(failed)
                plan.update(action='retry_stage',reason='Verified decoded geometry/PBR checkpoint retained; resume GLB finishing without diffusion',
                    resume_mesh_checkpoint=checkpoint['source_job_id'],resume_checkpoint_sha256=checkpoint['sha256'],
                    checkpoint_geometry=checkpoint['metadata']['geometry'])
            except (ValueError,KeyError,OSError) as exc:
                if (folder/'output/mesh_checkpoint.json').exists() or failed['payload'].get('resume_mesh_checkpoint'):
                    plan.update(action='needs_attention',reason='Native checkpoint integrity could not be verified: '+str(exc))
        if plan['action']=='retry_stage':
            import psutil
            process=folder/'process.json'
            if process.is_file():
                try:
                    if psutil.pid_exists(json.loads(process.read_text('utf-8'))['pid']):plan.update(action='needs_attention',reason='Prior stage process is still present; do not start a competing retry')
                except (OSError,ValueError,KeyError):plan.update(action='needs_attention',reason='Prior process receipt cannot be verified')
            hold=engine_health.waiting(failed['payload'])
            if hold:plan.update(action='needs_attention',reason=hold['reason'])
        return remember(item,plan)

    def concept(self,value,item,current,rejected):
        issues=sorted({issue for r in rejected for issue in r.get('issues',[]) if issue!='uncertain_source'})
        identifiers=sorted(r['source_sha256'] for r in rejected)
        key=hashlib.sha256(json.dumps([value['id'],item['asset_id'],item['attempt'],identifiers,issues]).encode()).hexdigest()
        cached=next((p for p in item.get('repair_history',[]) if p['id']=='concept-repair:'+key),None)
        if cached:return cached
        cause='CONCEPT_'+('_'.join(issues).upper() or 'UNSUITABLE')
        scoped=[j for j in jobs.listing() if j['payload'].get('asset_id')==item['asset_id'] and j['payload'].get('batch_id')==value['id']]
        previous=[p for p in item.get('repair_history',[]) if p.get('asset_attempt')==item['attempt'] and p.get('action')=='repair_concept' and p.get('executed_job_id')]
        prior_concepts=[j for j in current if j['payload']['kind']=='concept']
        prediction=measurements(max(prior_concepts,key=lambda j:j['created_at'])) if prior_concepts else None
        budget=budget_check(value,item,scoped,'concept',cause,prediction)
        instructions=[]
        if 'missing_requested_subject' in issues:instructions.append('The requested subject is the complete primary object described below; its identity takes priority over any reference appearance.')
        if 'multiple_views_or_panels' in issues:instructions.append('Use one perspective camera exposure of one connected object.')
        if 'cropped_main_object' in issues:instructions.append('Pull the camera back. Keep generous empty space around every extremity and the entire contact base.')
        if 'background_scene' in issues:instructions.append('Photograph the isolated object against a uniform neutral studio sweep.')
        if 'border_or_text' in issues:instructions.append('Only the physical asset and its contact shadow occupy the image.')
        no_progress=bool(previous and previous[-1].get('issues')==issues)
        action='repair_concept' if budget['allowed'] and instructions and not no_progress else 'needs_attention'
        return remember(item,dict(schema_version=1,id='concept-repair:'+key,asset_attempt=item['attempt'],root_cause=cause,stage='concept',engine='sdxl_local',action=action,issues=issues,
            reason='Cause-specific concept conditioning; geometry has not started' if action=='repair_concept' else 'Same observed defect after targeted repair; no-progress stop' if no_progress else budget['reason'] or 'No supported deterministic repair for these observations',
            at=store.now(),budget=budget,predicted_cost=prediction,instructions=instructions,source_hashes=identifiers,quality_preserved=True,
            validation=['Recheck the new image with the current suitability policy','Do not start 3D until the source is admitted']))


def submit_stage_retry(plan,failed):
    """Atomic idempotent admission; crash before batch.save cannot duplicate work."""
    if plan['action']!='retry_stage':return None
    from .studio import cached
    from engines.quality import fingerprint
    import copy
    frozen=copy.deepcopy(plan);frozen.pop('executed_job_id',None)
    payload=failed['payload']|dict(retry_of=failed['id'],quality_repair=frozen)
    if plan.get('resume_mesh_checkpoint'):
        payload.update(resume_mesh_checkpoint=plan['resume_mesh_checkpoint'],resume_checkpoint_sha256=plan['resume_checkpoint_sha256'])
    key=plan['id'];digest=fingerprint(dict(plan_id=key,source_payload=failed['payload']))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');prior=cached(db,key,digest)
        if prior:return prior
        result=jobs.enqueue(payload,db=db)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(key,digest,json.dumps(result)))
    plan['executed_job_id']=result['id']
    return result


planner=QualityRepairPlanner()
