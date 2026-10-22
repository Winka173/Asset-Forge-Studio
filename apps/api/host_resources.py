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

GIB=1024**3
HEADROOM=2*GIB
_estimates={}


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
        row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(key,)).fetchone()
    observed=json.loads(row['payload']) if row else None
    result=dict(profile_key=key,profile=value,bytes=max(floor*GIB,observed.get('allowance_bytes',0) if observed else 0),
        planning_floor_gib=floor,observed=observed,basis='Conservative stage allowance; raised by retained measured worker RSS/private peaks. Not a guarantee against external allocations.')
    _estimates[cache_key]=(time.monotonic(),result);return result


def record_peak(payload,identifier,samples):
    peak=max((max(s.get('worker_tree_rss_bytes') or 0,s.get('worker_tree_private_bytes') or 0) for s in samples),default=0)
    if not peak:return
    key,_=profile(payload)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(key,)).fetchone()
        old=json.loads(row['payload']) if row else {}
        if peak<old.get('peak_bytes',0):return
        value=dict(schema_version=1,peak_bytes=peak,allowance_bytes=int(peak*1.15)+GIB,job_id=identifier,at=store.now(),
            scope='Worker tree RSS / Windows private bytes when available, plus planning margin; shared pages may be counted per process.')
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
        if parent.create_time()<record['reserved_at']-2:return 0,False
        if folder.as_posix().lower() not in ' '.join(parent.cmdline()).replace('\\','/').lower():return 0,False
        tree=[parent,*parent.children(recursive=True)]
        return sum(p.memory_info().rss for p in tree if p.is_running()),True
    except psutil.AccessDenied:return 0,None
    except (OSError,ValueError,KeyError,psutil.Error):return 0,False


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
        pending=0;orphan_gpu=False;unknown_claim=False;live=[]
        for entry in ledger.glob('*.json'):
            try:
                record=json.loads(entry.read_text('utf-8'));rss,child_alive=worker_state(record)
                owner_alive=alive(record['owner_pid'],record['owner_created'],record['owner_thread'])
                if owner_alive is None or child_alive is None:
                    unknown_claim=True;continue
                if not owner_alive and not child_alive:
                    entry.unlink();continue
                pending+=max(0,record['allowance_bytes']-rss)
                orphan_gpu|=not owner_alive and child_alive and record['resource']=='gpu'
                live.append(dict(job_id=record['job_id'],resource=record['resource'],unrealized_bytes=max(0,record['allowance_bytes']-rss)))
            except (OSError,ValueError,KeyError,TypeError):
                # Do not discard an unknown live claim and start another heavy stage.
                unknown_claim=True
        available=psutil.virtual_memory().available;usable=max(0,available-pending)
        allowed=not unknown_claim and not (orphan_gpu and kind=='gpu') and usable>=allowance['bytes']+HEADROOM
        reason=None if allowed else 'Resource admission record is unreadable; inspect host-ram claims before starting heavy work' if unknown_claim else 'An earlier GPU worker is still running; waiting for it to exit safely' if orphan_gpu and kind=='gpu' else f"Waiting for RAM / stage allowance {allowance['bytes']/GIB:.1f} GiB + 2 GiB reserve; {usable/GIB:.1f} GiB available after existing claims"
        receipt=dict(schema_version=1,allowed=allowed,reason=reason,reason_code=None if allowed else 'HOST_RAM_ADMISSION',at=store.now(),
            checked_at_epoch=time.time(),available_bytes=available,unrealized_reserved_bytes=pending,usable_bytes=usable,
            headroom_bytes=HEADROOM,allowance=allowance,active_claims=live,quality_settings_changed=False)
        write_receipt(folder,receipt)
        if allowed and path:
            owner=psutil.Process();temporary=path.with_suffix('.part');temporary.write_text(json.dumps(dict(schema_version=1,job_id=job['id'],job_folder=str(folder.resolve()),resource=kind,
                owner_pid=os.getpid(),owner_created=owner.create_time(),owner_thread=threading.get_native_id(),reserved_at=time.time(),allowance_bytes=allowance['bytes'])),'utf-8');temporary.replace(path)
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
