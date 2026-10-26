"""Durable route health over the existing SQLite store and job scheduler."""
import functools
import hashlib
import json
import platform
import subprocess
from pathlib import Path
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from . import store

router=APIRouter(prefix='/api/engine-health')
PREFIX='__afs_engine_health__:'
ENVIRONMENT={'MODEL_DEPENDENCY_MISSING','CUDA_ABI_CONFLICT','CUDA_OOM','PROCESS_TIMEOUT'}


class RouteWaiting(HTTPException):
    def __init__(self,hold):
        self.hold=hold
        super().__init__(409,hold['reason'])


def admit(payload):
    hold=waiting(payload)
    if hold:raise RouteWaiting(hold)


def classify(message,log=''):
    text=(message+'\n'+log).lower()
    if any(s in text for s in ('out of memory','oom/','memory guard')):return 'CUDA_OOM','Release competing resources; retry the identical profile once, then validate environment before further work'
    if any(s in text for s in ('no kernel image','undefined symbol','dll load failed','invalid device function','not compiled with cuda','compute capability')):return 'CUDA_ABI_CONFLICT','Repair the isolated engine environment / CUDA extension; run one smoke probe'
    if any(s in text for s in ('no module named','no file named','executable not found','weights missing','environment missing','environment or offline weights missing','environment or cached weights missing')):return 'MODEL_DEPENDENCY_MISSING','Restore the pinned dependency/model path; run one smoke probe'
    if 'timeout' in text:return 'PROCESS_TIMEOUT','Inspect stage logs and resource measurements before one unchanged-profile probe'
    if any(s in text for s in ('checksum','hash mismatch','checkpoint changed','config changes','execution differs')):return 'INPUT_OR_CONFIG_INTEGRITY','Restore the pinned source/config; do not retry with altered settings'
    if any(s in text for s in ('empty','no triangles','no geometry')):return 'EMPTY_GEOMETRY','Retain source; repair or regenerate geometry only'
    if 'export' in text or 'reopen' in text:return 'EXPORT_VALIDATION','Retain master and retry only validation/export'
    if any(s in text for s in ('interrupted','server stopped','user requested stop')):return 'INTERRUPTED','Resume from the latest valid stage; no mid-inference restoration claimed'
    return 'UNCLASSIFIED_EXECUTION','Inspect retained exception and stage log; no blind engine substitution'


@functools.lru_cache(maxsize=1)
def device():
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
        gpu=result.stdout.strip() if result.returncode==0 else 'unavailable'
    except (OSError,subprocess.TimeoutExpired):gpu='unavailable'
    return dict(os=platform.platform(),gpu_driver=gpu)


def stat(path):
    try:
        p=Path(path);s=p.stat();return dict(path=str(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns)
    except OSError:return dict(path=str(path),missing=True)


def identity(payload):
    from engines.adapters import ADAPTERS
    from engines.concept_adapter import CONCEPT_ADAPTER
    kind=payload['kind'];engine=payload.get('engine') if kind=='inference' else CONCEPT_ADAPTER.id if kind=='concept' else None
    if payload['kind'] in ('blender','procedural_geometry'):
        from .local_tools import executable
        blender=executable('blender')
        cfg=payload.get('effective_config') or {}
        value=dict(engine='blender_procedural' if payload['kind']=='procedural_geometry' else 'blender_postprocess',version='AFS Blender profile v1',
            environment=stat(blender or 'missing-blender'),device=dict(os=platform.platform(),execution='CPU' if not payload.get('use_gpu') else device()),
            profile={k:cfg.get(k) for k in ('engine_version','checkpoint','geometry','texture','quality')})
        return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest(),value
    if not engine:return None
    adapter=CONCEPT_ADAPTER if engine==CONCEPT_ADAPTER.id else ADAPTERS.get(engine)
    if not adapter:return None
    source,python=adapter.paths();site=python.parent.parent/'Lib/site-packages'
    packages=[stat(p/'METADATA') for pattern in ('torch-*.dist-info','diffusers-*.dist-info','transformers-*.dist-info','xformers-*.dist-info','flash_attn*.dist-info','nvdiffrast*.dist-info','spconv*.dist-info','cumesh*.dist-info') for p in sorted(site.glob(pattern))]
    extensions=[stat(p) for pattern in ('xformers/*.pyd','flash_attn*.pyd','nvdiffrast/*.pyd','cumesh/*.pyd','spconv/*.pyd') for p in sorted(site.glob(pattern))]
    cfg=payload.get('effective_config') or {}
    profile={k:cfg.get(k) for k in ('engine_version','checkpoint','resolution','inference_steps','precision','geometry','texture','quality')}
    if isinstance(profile.get('checkpoint'),dict):profile['checkpoint']=profile['checkpoint'].get('manifest_hash')
    wrapper=store.ROOT/'engines'/('klein_worker.py' if engine==CONCEPT_ADAPTER.id else 'trellis2_worker.py')
    value=dict(engine=engine,version=adapter.version,environment=stat(python),packages=packages,extensions=extensions,wrapper_sha256=store.digest(wrapper),device=device(),profile=profile)
    key=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
    return key,value


def read(key):
    with store.connect() as db:row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(PREFIX+key,)).fetchone()
    return json.loads(row['payload']) if row else None


def waiting(payload,job_id=None):
    found=identity(payload)
    if not found:return None
    key,_=found;record=read(key)
    if record and record['circuit'] in ('open','probing') and record.get('probe_job_id')!=job_id:
        return dict(code='ENGINE_ROUTE_QUARANTINED',health_key=key,reason='Waiting for engine remediation and a validated smoke probe: '+record.get('root_cause','environment failure'))
    return None


def record_result(job,folder):
    found=identity(job['payload'])
    if not found or job['status'] not in ('REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED'):return
    key,signature=found;log=folder/'worker.log'
    tail=''
    if log.is_file():
        with log.open('rb') as stream:stream.seek(max(0,log.stat().st_size-12000));tail=stream.read().decode('utf-8',errors='replace')
    code,action=classify(job.get('error') or '',tail)
    success=job['status']=='REVIEW_REQUIRED'
    diagnostic=dict(schema_version=1,job_id=job['id'],stage=job['payload']['kind'],health_key=key,signature=signature,
        outcome='VERIFIED' if success else 'FAILED',root_cause=None if success else code,remediation=None if success else action,
        error=job.get('error'),effective_config_hash=job['payload'].get('effective_config_hash'),log_sha256=store.digest(log) if log.is_file() else None,at=store.now())
    path=folder/'diagnostic.json';temp=path.with_suffix('.part');temp.write_text(json.dumps(diagnostic,indent=2),encoding='utf-8');temp.replace(path)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(PREFIX+key,)).fetchone()
        record=json.loads(row['payload']) if row else dict(key=key,signature=signature,circuit='closed',observations=[],failure_counts={},status='Untested')
        if any(o['job_id']==job['id'] for o in record['observations']):return
        record['observations'].append(dict(job_id=job['id'],success=success,root_cause=None if success else code,at=store.now(),diagnostic=str(path.relative_to(store.DATA))))
        record['updated_at']=store.now()
        if success:
            record.update(status='Export Verified' if job['payload']['kind'] in ('blender','procedural_geometry') else 'Inference Verified',circuit='closed',failure_counts={},root_cause=None,probe_job_id=None)
        else:
            count=record['failure_counts'].get(code,0)+1;record['failure_counts'][code]=count;record.update(status='Degraded',root_cause=code,remediation=action)
            if code in ENVIRONMENT and (count>=2 or record.get('probe_job_id')==job['id']):record.update(circuit='open',probe_job_id=None)
        db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',(PREFIX+key,json.dumps(record)))


@router.get('')
def listing():
    with store.connect() as db:records=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM drafts WHERE project_id LIKE ?',(PREFIX+'%',))]
    return dict(records=records,policy='Exact engine/environment/device/profile fingerprint. Installing is not inference verification. Driver/environment changes invalidate matching health. No automatic downloads or engine swaps.')


class Probe(BaseModel):request_id:str=Field(min_length=8,max_length=100)


@router.post('/{key}/probe')
def probe(key:str,body:Probe):
    from . import jobs,studio,batch
    with batch.LOCK:
        record=read(key)
        if not record:raise HTTPException(404,'Engine health record not found')
        if record.get('probe_job_id'):
            previous=jobs.get(record['probe_job_id'])
            if previous['status'] not in jobs.TERMINAL:return previous
        old=next((jobs.get(o['job_id']) for o in reversed(record['observations']) if not o['success']),None)
        if not old:raise HTTPException(409,'No failed stage exists to probe')
        if identity(old['payload'])[0]!=key:raise HTTPException(409,'Environment changed; old health record is stale. Retry with a newly resolved configuration.')
        # Explicitly repeats only the failed stage with its immutable configuration.
        # It shares the global resource lock, pause controls and original job graph.
        cache_key='health-probe:'+hashlib.sha256((key+body.request_id).encode()).hexdigest()
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');previous=studio.cached(db,cache_key,key)
            if previous:return previous
            result=jobs.enqueue(old['payload']|dict(retry_of=old['id'],health_probe=key),db=db)
            record.update(circuit='probing',probe_job_id=result['id'])
            db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',(PREFIX+key,json.dumps(record)))
            db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(cache_key,key,json.dumps(result)))
        return result
