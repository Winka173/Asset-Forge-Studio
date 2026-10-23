"""Host RAM admission for the existing scheduler; never changes generation settings."""
import contextlib
import hashlib
import json
import os
import time
import threading
import uuid
from pathlib import Path

import psutil
from . import store
from .host_memory import commit_memory

GIB=1024**3
HEADROOM=2*GIB
_estimates={}


def peaks(samples):
    return tuple(max((s.get(key) or 0 for s in samples),default=0)
        for key in ('worker_tree_rss_bytes','worker_tree_private_bytes'))


def observation(rss,private,identifier,previous=None):
    old=previous or {};rss=max(rss,old.get('rss_peak_bytes',old.get('peak_bytes',0)))
    private=max(private,old.get('private_peak_bytes',old.get('peak_bytes',0)))
    physical=int(rss*1.15)+GIB;commit=int(max(private,rss)*1.15)+GIB
    return dict(schema_version=2,peak_bytes=max(rss,private),rss_peak_bytes=rss,private_peak_bytes=private,
        physical_allowance_bytes=physical,commit_allowance_bytes=commit,allowance_bytes=max(physical,commit),
        job_id=identifier,at=store.now(),scope='Resident RSS and private committed bytes measured separately; each allowance keeps 15% + 1 GiB margin. No quality-setting changes.')


def recover_observation(old,payload,db):
    """Split legacy mixed peaks only when retained same-profile samples prove both."""
    if not old or old.get('schema_version')==2:return old
    identifier=old.get('job_id','')
    if not identifier or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in identifier):return old
    try:
        row=db.execute('SELECT payload FROM jobs WHERE id=?',(identifier,)).fetchone()
        if not row or profile(json.loads(row['payload']))[0]!=profile(payload)[0]:return old
        report=json.loads((store.DATA/'jobs'/identifier/'resources.json').read_text('utf-8'))
        rss,private=peaks(report['samples'])
        if not rss or not private or max(rss,private)!=old['peak_bytes']:return old
        if rss!=report['worker_tree_peak_rss_bytes'] or private!=report['worker_tree_peak_private_bytes']:return old
        value=observation(rss,private,identifier);value['recovered_from']='Retained same-job resources.json samples and matching job profile'
        value['legacy_observation']=old
        # Callers hold BEGIN IMMEDIATE: never replace a newer measured peak.
        db.execute('UPDATE drafts SET payload=? WHERE project_id=?',(json.dumps(value),profile(payload)[0]))
        return value
    except (OSError,ValueError,KeyError,TypeError):return old


def profile(payload):
    config=payload.get('effective_config') or {}
    value=dict(kind=payload.get('kind'),engine=payload.get('engine') or config.get('engine_id'),
        checkpoint=(config.get('checkpoint') or {}).get('manifest_hash'),quality=config.get('quality'),
        pipeline_type=payload.get('pipeline_type') or (config.get('geometry') or {}).get('pipeline_type'),precision=config.get('precision'),
        texture_size=payload.get('texture_size') or (config.get('texture') or {}).get('resolution'),
        finishing_only=bool(payload.get('resume_mesh_checkpoint')),use_gpu=bool(payload.get('use_gpu')))
    key='host-memory:v1:'+hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
    return key,value


def estimate(payload):
    key,value=profile(payload);kind=value['kind'];engine=value['engine']
    cache_key=(str(store.DATA),key);cached=_estimates.get(cache_key)
    if cached and time.monotonic()-cached[0]<2:return cached[1]
    # Conservative planning allowances, not hard engine requirements or guarantees.
    # Full TRELLIS allowance covers the retained 15.7M-triangle castle experiment.
    floor=32 if kind=='inference' and engine=='trellis2_community' and not value['finishing_only'] else 10 if kind=='inference' and value['finishing_only'] else 24 if kind=='inference' else 12 if kind=='concept' else 8 if kind in ('blender','unity_import','world_unity','cinematic_render') else 6 if kind in ('prompt_analysis','concept_layout','model_visual_check','batch_semantics','animation_retime') else 4
    if kind=='inference':
        from engines.adapters import ADAPTERS
        adapter=ADAPTERS.get(engine)
        if adapter and hasattr(adapter,'paths'):
            source,python=adapter.paths()
            if not source.is_dir() or not python.is_file():floor=1  # Fail missing-environment validation promptly; no model can load.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(key,)).fetchone()
        observed=recover_observation(json.loads(row['payload']) if row else None,payload,db)
    measured=observed or {}
    result=dict(profile_key=key,profile=value,bytes=max(floor*GIB,measured.get('physical_allowance_bytes',measured.get('allowance_bytes',0))),
        commit_bytes=max(floor*GIB,measured.get('commit_allowance_bytes',measured.get('allowance_bytes',0))),
        planning_floor_gib=floor,observed=observed,basis='Separate resident-RAM and system-commit allowances. Legacy mixed estimates remain conservative unless original samples prove both. Not a guarantee against external allocations.')
    _estimates[cache_key]=(time.monotonic(),result);return result


def record_peak(payload,identifier,samples):
    rss,private=peaks(samples)
    if not max(rss,private):return
    key,_=profile(payload)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(key,)).fetchone()
        old=recover_observation(json.loads(row['payload']) if row else {},payload,db)
        value=observation(rss,private,identifier,old)
        db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',(key,json.dumps(value)))
    _estimates.pop((str(store.DATA),key),None)


def alive(pid,created,thread_id):
    try:
        process=psutil.Process(pid)
        return abs(process.create_time()-created)<.01 and any(t.id==thread_id for t in process.threads())
    except psutil.AccessDenied:return None
    except (psutil.Error,TypeError,ValueError):return False


def worker_state(record):
    """Only recognize a child belonging to this immutable job directory, not a reused PID."""
    folder=Path(record['job_folder'])
    try:
        process=json.loads((folder/'process.json').read_text('utf-8'));parent=psutil.Process(process['pid'])
        if parent.create_time()<record['reserved_at']-2:return 0,0,False
        if folder.as_posix().lower() not in ' '.join(parent.cmdline()).replace('\\','/').lower():return 0,0,False
        memory=[p.memory_info() for p in [parent,*parent.children(recursive=True)] if p.is_running()]
        return sum(m.rss for m in memory),sum(getattr(m,'private',m.rss) for m in memory),True
    except psutil.AccessDenied:return 0,0,None
    except (OSError,ValueError,KeyError,psutil.Error):return 0,0,False


def write_receipt(folder,value):
    previous=folder/'admission.json'
    try:
        old=json.loads(previous.read_text('utf-8'))
        if old['allowed']==value['allowed'] and old.get('reason')==value.get('reason') and time.time()-old['checked_at_epoch']<2:return
    except (OSError,ValueError,KeyError,TypeError):pass
    folder.mkdir(parents=True,exist_ok=True);temporary=folder/('admission-'+uuid.uuid4().hex+'.part')
    temporary.write_text(json.dumps(value,indent=2),'utf-8');temporary.replace(folder/'admission.json')


def check(job,kind,token=None):
    from .jobs import LOCK_ROOT,file_lock
    ledger=LOCK_ROOT/'host-ram';ledger.mkdir(parents=True,exist_ok=True)
    folder=store.DATA/'jobs'/job['id'];path=ledger/(token+'.json') if token else None;allowance=estimate(job['payload'])
    with file_lock(LOCK_ROOT/'ram-admission.lock'):
        pending=0;pending_commit=0;orphan_gpu=False;unknown_claim=False;live=[]
        for entry in ledger.glob('*.json'):
            try:
                record=json.loads(entry.read_text('utf-8'));rss,private,child_alive=worker_state(record)
                if record.get('schema_version',1) not in (1,2):raise ValueError('Unknown resource claim schema')
                owner_alive=alive(record['owner_pid'],record['owner_created'],record['owner_thread'])
                if owner_alive is None or child_alive is None:
                    unknown_claim=True;continue
                if not owner_alive and not child_alive:
                    entry.unlink();continue
                physical=max(0,record.get('physical_allowance_bytes',record['allowance_bytes'])-rss)
                committed=max(0,record.get('commit_allowance_bytes',record['allowance_bytes'])-private)
                pending+=physical;pending_commit+=committed
                orphan_gpu|=not owner_alive and child_alive and record['resource']=='gpu'
                live.append(dict(job_id=record['job_id'],resource=record['resource'],unrealized_bytes=physical,unrealized_commit_bytes=committed))
            except (OSError,ValueError,KeyError,TypeError):
                # Do not discard an unknown live claim and start another heavy stage.
                unknown_claim=True
        available=psutil.virtual_memory().available;commit=commit_memory()
        # Other platforms retain the previous conservative mixed allowance.
        physical_required=allowance['bytes'] if commit else max(allowance['bytes'],allowance['commit_bytes'])
        usable=max(0,available-pending);commit_usable=max(0,commit['available_bytes']-pending_commit) if commit and commit['status']=='measured' else None
        reason=code=None
        if unknown_claim:reason='Resource admission record is unreadable; inspect host-ram claims before starting heavy work'
        elif orphan_gpu and kind=='gpu':reason='An earlier GPU worker is still running; waiting for it to exit safely'
        elif commit and commit['status']!='measured':reason='Windows system commit measurement unavailable; no heavy stage started';code='HOST_COMMIT_ADMISSION'
        elif usable<physical_required+HEADROOM:reason=f"Waiting for RAM / stage allowance {physical_required/GIB:.1f} GiB + 2 GiB reserve; {usable/GIB:.1f} GiB available after existing claims"
        elif commit_usable is not None and commit_usable<allowance['commit_bytes']+HEADROOM:reason=f"Waiting for Windows commit / stage allowance {allowance['commit_bytes']/GIB:.1f} GiB + 2 GiB reserve; {commit_usable/GIB:.1f} GiB available after existing claims";code='HOST_COMMIT_ADMISSION'
        allowed=reason is None
        receipt=dict(schema_version=2,allowed=allowed,reason=reason,reason_code=None if allowed else code or 'HOST_RAM_ADMISSION',at=store.now(),
            checked_at_epoch=time.time(),available_bytes=available,unrealized_reserved_bytes=pending,usable_bytes=usable,
            headroom_bytes=HEADROOM,allowance=allowance,active_claims=live,quality_settings_changed=False,
            commit=commit,usable_commit_bytes=commit_usable,unrealized_commit_reserved_bytes=pending_commit)
        write_receipt(folder,receipt)
        if allowed and path:
            owner=psutil.Process();temporary=path.with_suffix('.part');temporary.write_text(json.dumps(dict(schema_version=2,job_id=job['id'],job_folder=str(folder.resolve()),resource=kind,
                owner_pid=os.getpid(),owner_created=owner.create_time(),owner_thread=threading.get_native_id(),reserved_at=time.time(),
                allowance_bytes=max(physical_required,allowance['commit_bytes']),physical_allowance_bytes=physical_required,commit_allowance_bytes=allowance['commit_bytes'])),'utf-8');temporary.replace(path)
    return receipt,path


@contextlib.contextmanager
def reserve(job,kind):
    receipt,path=check(job,kind,uuid.uuid4().hex)
    try:yield receipt
    finally:
        if receipt['allowed']:path.unlink(missing_ok=True)


def waiting(identifier):
    try:
        value=json.loads((store.DATA/'jobs'/identifier/'admission.json').read_text('utf-8'))
        if not value['allowed'] and time.time()-value['checked_at_epoch']<10:return value
    except (OSError,ValueError,KeyError,TypeError):pass
    return None
