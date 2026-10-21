"""Durable hybrid CPU/GPU subprocess jobs. No network, shell=True, or global environment mutations."""
import contextlib
import json
import os
import subprocess
import threading
import time
import uuid
import re
from pathlib import Path

import psutil

from . import store
from .inspection import inspect_glb

LOCK_ROOT=Path(os.environ.get('AFS_LOCK_ROOT',store.CONFIG_ROOT/'locks'))
WORKER_LOCK = LOCK_ROOT / 'gpu.lock'

TERMINAL = {'REVIEW_REQUIRED', 'FAILED', 'CANCELLED', 'BLOCKED'}
TRANSITIONS = {
    'QUEUED': {'RUNNING', 'CANCELLED', 'BLOCKED'},
    'RUNNING': {'GENERATED', 'POSTPROCESSING', 'FAILED', 'CANCELLED', 'BLOCKED'},
    'GENERATED': {'VALIDATING', 'FAILED', 'CANCELLED', 'BLOCKED'},
    'POSTPROCESSING': {'VALIDATING', 'FAILED', 'CANCELLED', 'BLOCKED'},
    'VALIDATING': {'REVIEW_REQUIRED', 'FAILED', 'CANCELLED', 'BLOCKED'},
}


def decode(row):
    r = dict(row); r['payload'] = json.loads(r['payload']); return r


def get(identifier):
    with store.connect() as db:
        row = db.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone()
    if not row: raise KeyError(identifier)
    return decode(row)


def listing():
    with store.connect() as db:
        values = [decode(r) for r in db.execute('SELECT * FROM jobs ORDER BY created_at DESC')]
    for value in values:
        progress = {'stage': value['status'], 'percent': None, 'scope': 'current_stage_only'}
        log = store.DATA / 'jobs' / value['id'] / 'worker.log'
        if value['status'] not in TERMINAL and log.exists():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 12000)); tail = stream.read().decode('utf-8', errors='replace')
            lines = re.split(r'[\r\n]', tail)
            matches = [re.search(r'([^\r\n:]+):\s*(\d+)%\|', line) for line in lines]
            matches = [m for m in matches if m]
            if matches:
                progress.update(stage=matches[-1][1].strip(), percent=int(matches[-1][2]))
            stages = [line.removeprefix('STAGE ').strip() for line in lines if line.startswith('STAGE ')]
            if stages: progress.update(stage=stages[-1], percent=None)
        value['progress'] = progress
    return values


def transition(identifier, target, error=None):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT status FROM jobs WHERE id=?', (identifier,)).fetchone()
        if not row: raise KeyError(identifier)
        if target not in TRANSITIONS.get(row['status'], set()):
            raise ValueError(f'Invalid job transition {row["status"]} -> {target}')
        db.execute('UPDATE jobs SET status=?,updated_at=?,error=? WHERE id=?', (target, store.now(), error, identifier))


def enqueue(payload, db=None):
    identifier = uuid.uuid4().hex; created = store.now()
    if db is not None:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?)', (identifier, 'QUEUED', created, created, json.dumps(payload), None))
        return decode(db.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone())
    with store.connect() as db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?)', (identifier, 'QUEUED', created, created, json.dumps(payload), None))
    return get(identifier)


def retry(identifier):
    original = get(identifier)
    if original['status'] not in TERMINAL: raise ValueError('Cancel or finish current attempt before retry')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute('SELECT * FROM jobs'):
            item = decode(row)
            if item['payload'].get('retry_of') == identifier and item['status'] not in TERMINAL:
                return item
        return enqueue(original['payload'] | {'retry_of': identifier}, db=db)


@contextlib.contextmanager
def file_lock(path):
    # Same checkout-wide lock across API processes and separate test databases.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as f:
        f.seek(0); f.write(b'0'); f.flush(); f.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try: yield
        finally:
            f.seek(0)
            if os.name == 'nt': msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def exclusive_worker_lock():
    # One GPU resource across Single, Batch, desktop and CLI processes.
    return file_lock(WORKER_LOCK)


def resource_class(payload):
    if payload['kind']=='batch_semantics':return 'cpu'
    return 'cpu' if payload['kind'] in ['blender','unity_import','world_unity'] and not payload.get('use_gpu',False) else 'gpu'


def dependency_readiness(job):
    """Persisted stage dependencies; scheduler changes admission, never quality settings."""
    for identifier in job['payload'].get('depends_on',[]):
        try:parent=get(identifier)
        except KeyError:return 'blocked',f'Missing dependency {identifier}; no automatic replacement'
        if parent['status'] in {'FAILED','BLOCKED','CANCELLED'}:return 'blocked',f'Dependency {identifier} is {parent["status"]}; retry the failed stage explicitly'
        if parent['status']!='REVIEW_REQUIRED':return 'waiting',None
    return 'ready',None


@contextlib.contextmanager
def resource_slot(kind):
    if kind=='gpu':
        with exclusive_worker_lock():yield
        return
    for index in range(max(1,min(4,int(os.environ.get('AFS_CPU_CONCURRENCY','2'))))):
        manager=file_lock(LOCK_ROOT/f'cpu-slot-{index}.lock')
        try:
            manager.__enter__()
        except OSError:continue
        try:yield
        finally:manager.__exit__(None,None,None)
        return
    raise OSError('CPU resource slots busy')


def kill_tree(process):
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in children:
            try: child.kill()
            except psutil.NoSuchProcess: pass
        try: parent.kill()
        except psutil.NoSuchProcess: pass
        psutil.wait_procs(children + [parent], timeout=5)
    except psutil.NoSuchProcess: pass
    process.wait(timeout=10)


class Worker:
    def __init__(self):
        self.stop = threading.Event(); self.thread = None;self.active={}

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop.clear(); self.thread = threading.Thread(target=self.loop, daemon=True); self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=20)

    def loop(self):
        while not self.stop.is_set():
            try:
                # One coordinator per data store, with shared GPU/CPU slots across stores.
                with file_lock(store.DATA/'.scheduler.lock'):
                    with store.connect() as db:
                        db.execute("UPDATE jobs SET status='BLOCKED',error='Worker interrupted; retry creates a new attempt',updated_at=? WHERE status IN ('RUNNING','GENERATED','POSTPROCESSING','VALIDATING')", (store.now(),))
                    while not self.stop.is_set():
                        self.active={k:v for k,v in self.active.items() if v[0].is_alive()}
                        with store.connect() as db:
                            rows=db.execute("SELECT * FROM jobs WHERE status='QUEUED' ORDER BY created_at").fetchall()
                            candidates=[]
                            for row in rows:
                                job=decode(row)
                                if job['id'] in self.active:continue
                                priority=job['payload'].get('priority',0);batch_id=job['payload'].get('batch_id')
                                if batch_id:
                                    parent=db.execute('SELECT payload FROM batches WHERE id=?',(batch_id,)).fetchone()
                                    if not parent:continue
                                    value=json.loads(parent['payload']);item=next((i for i in value['items'] if i['asset_id']==job['payload'].get('asset_id')),None)
                                    if value['paused'] or not item or item.get('skipped'):continue
                                    priority=item['priority']
                                readiness,reason=dependency_readiness(job)
                                if readiness=='blocked':transition(job['id'],'BLOCKED',reason);continue
                                if readiness=='waiting':continue
                                candidates.append((priority,job))
                        counts={kind:sum(v[1]==kind for v in self.active.values()) for kind in ['gpu','cpu']}
                        for _,job in sorted(candidates,key=lambda x:-x[0]):
                            kind=resource_class(job['payload']);limit=1 if kind=='gpu' else max(1,min(4,int(os.environ.get('AFS_CPU_CONCURRENCY','2'))))
                            if counts[kind]>=limit:continue
                            if psutil.virtual_memory().available < (6 if kind=='gpu' else 3)*1024**3:continue
                            thread=threading.Thread(target=self.managed,args=(job,kind),daemon=True)
                            self.active[job['id']]=(thread,kind);counts[kind]+=1;thread.start()
                        self.stop.wait(.3)
                    for thread,_ in list(self.active.values()):thread.join(timeout=20)
            except OSError:
                pass  # Another process owns the worker/GPU lock.
            except Exception as exc:
                print(f'AFS_WORKER_ERROR {exc}', flush=True)
            self.stop.wait(0.3)

    def managed(self,job,kind):
        try:
            with resource_slot(kind):
                if self.stop.is_set() or get(job['id'])['status']!='QUEUED':return
                started=time.monotonic();started_at=store.now();samples=[];finished=threading.Event()
                def monitor():
                    while not finished.wait(.5):
                        rss=None
                        try:
                            record=json.loads((store.DATA/'jobs'/job['id']/'process.json').read_text());parent=psutil.Process(record['pid'])
                            rss=sum(p.memory_info().rss for p in [parent]+parent.children(recursive=True) if p.is_running())
                        except (OSError,ValueError,psutil.Error):pass
                        samples.append(dict(seconds=time.monotonic()-started,worker_tree_rss_bytes=rss,ram_used_bytes=psutil.virtual_memory().used,
                            ram_available_bytes=psutil.virtual_memory().available,cpu_percent=psutil.cpu_percent(),
                            resource=kind))
                        timeout=job['payload'].get('timeout_seconds',7200)
                        if time.monotonic()-started>timeout:
                            try:transition(job['id'],'CANCELLED','TIMEOUT; EffectiveGenerationConfig unchanged')
                            except ValueError:pass
                watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
                try:self.execute(job)
                finally:
                    finished.set();watcher.join(timeout=2)
                    folder=store.DATA/'jobs'/job['id'];folder.mkdir(parents=True,exist_ok=True)
                    (folder/'resources.json').write_text(json.dumps(dict(resource=kind,started_at=started_at,finished_at=store.now(),duration_seconds=time.monotonic()-started,
                        ram_peak_used_bytes=max((s['ram_used_bytes'] for s in samples),default=psutil.virtual_memory().used),
                        worker_tree_peak_rss_bytes=max((s['worker_tree_rss_bytes'] or 0 for s in samples),default=0),samples=samples),indent=2))
                if job['payload'].get('batch_id') and not self.stop.is_set():
                    from .batch import advance
                    advance(job['payload']['batch_id'])
        except OSError:pass  # Slot occupied by another process; remains QUEUED.
        except Exception as exc:print('AFS_SCHEDULER_ERROR',type(exc).__name__,str(exc),flush=True)

    def execute(self, job):
        identifier = job['id']; payload = job['payload']; process = None
        folder = store.DATA / 'jobs' / identifier; folder.mkdir(parents=True, exist_ok=True)
        try:
            transition(identifier, 'RUNNING')
            if payload['kind']=='batch_semantics':
                from .batch_semantics import execute
                execute(job,folder)
                return
            if payload.get('effective_config'):
                from engines.quality import fingerprint,checkpoints
                effective=payload['effective_config']
                if fingerprint(effective)!=payload['effective_config_hash']:
                    transition(identifier,'BLOCKED','EffectiveGenerationConfig hash mismatch; no automatic config changes');return
                if payload['kind']=='inference':
                    actual=dict(engine=payload['engine'],steps=payload['steps'],seed=payload['seed'],pipeline=payload['pipeline_type'],
                                texture=payload['texture_size'] if payload['engine']!='triposg' else None,blender=payload['auto_blender'])
                    locked=dict(engine=effective['engine_id'],steps=effective['inference_steps'],seed=effective['seed'],pipeline=effective['geometry']['pipeline_type'],
                                texture=effective['texture']['size'],blender=effective['blender']['enabled'])
                    if actual!=locked:
                        transition(identifier,'BLOCKED','Execution settings differ from EffectiveGenerationConfig; no automatic config changes');return
                if payload['kind']=='inference' and checkpoints(payload['engine'])!=effective['checkpoint']:
                    transition(identifier,'BLOCKED','Engine checkpoint changed since approval; config must be resolved again');return
            if payload['kind'] == 'concept':
                self.concept(job, folder)
                return
            artifact = store.get_artifact(payload['artifact_id'])
            source = store.safe_path(artifact['relative_path'])
            if store.digest(source) != artifact['sha256']: raise ValueError('Immutable source checksum changed')
            if payload['kind'] == 'inference':
                self.inference(job, artifact, source, folder)
                return
            if payload['kind'] in ['unity_import','world_unity']:
                self.unity_import(job,artifact,folder)
                return
            from scripts.audit import audit
            blender = audit()['blender_path']
            if not blender: raise ValueError('Blender executable not found; set AFS_BLENDER')
            cfg = store.ROOT / 'benchmarks/archer_tower_t3/benchmark.json'
            request = {k: v for k, v in payload.items() if k not in {'kind', 'artifact_id', 'retry_of'}}
            request.update({'input': str(source), 'output': str(folder / 'output'), 'benchmark': str(cfg)})
            request_path = folder / 'request.json'
            request_path.write_text(json.dumps(request, indent=2), encoding='utf-8')
            transition(identifier, 'POSTPROCESSING')
            started = time.monotonic()
            with (folder / 'worker.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen([blender, '-b','-t',str(max(1,min(16,int(os.environ.get('AFS_BLENDER_THREADS','8'))))), '--factory-startup', '--python-exit-code', '1', '--python',
                    str(store.ROOT / 'pipelines/blender/process_asset.py'), '--', '--request', str(request_path)], stdout=log, stderr=subprocess.STDOUT)
                (folder / 'process.json').write_text(json.dumps({'pid': process.pid, 'created_at': store.now(), 'kind': 'blender'}), encoding='utf-8')
                while process.poll() is None:
                    if get(identifier)['status'] == 'CANCELLED' or self.stop.is_set():
                        kill_tree(process)
                        if get(identifier)['status'] != 'CANCELLED': transition(identifier, 'BLOCKED', 'Server stopped; retry creates new attempt')
                        return
                    self.stop.wait(0.2)
            if get(identifier)['status'] == 'CANCELLED': return
            if process.returncode: raise RuntimeError(f'Blender exit {process.returncode}; inspect worker.log')
            transition(identifier, 'VALIDATING')
            report_path = folder / 'output/report.json'
            report = json.loads(report_path.read_text(encoding='utf-8'))
            if report['input_sha256'] != artifact['sha256'] or report['checks']['export_reopen'] != 'PASS':
                raise ValueError('Invalid pipeline output provenance or reopen check')
            inspections = {f'LOD{i}.glb': inspect_glb(folder / f'output/LOD{i}.glb') for i in range(4)}
            report['duration_seconds_including_blender'] = time.monotonic() - started
            # Keep pipeline report immutable; store orchestration metadata in separate manifest.
            manifest = {'job_id': identifier, 'source_artifact_id': artifact['id'], 'source_sha256': artifact['sha256'],
                        'duration_seconds': report['duration_seconds_including_blender'], 'checks': report['checks'],
                        'framing': report['framing'], 'unity': 'NOT_TESTED', 'quality': 'NEEDS_REVIEW', 'glb_inspections': inspections}
            (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            if get(identifier)['status'] == 'CANCELLED': return
            store.add_artifact(folder / 'output/LOD0.glb', 'candidate', artifact['name'] + ' / processed LOD0',
                               inspections['LOD0.glb'] | {'parent_id': artifact['id'], 'parent_sha256': artifact['sha256'],
                                'project_id': payload.get('project_id') or artifact.get('project_id'), 'asset_id': payload.get('asset_id') or artifact.get('asset_id'),
                                'job_id': identifier, 'stage': 'blender_processed', 'license': artifact['metadata'].get('license', 'NEEDS_REVIEW')})
            transition(identifier, 'REVIEW_REQUIRED')
        except Exception as exc:
            if process and process.poll() is None: kill_tree(process)
            current = get(identifier)['status']
            message=str(exc)
            log=folder/'worker.log'
            if log.exists():
                with log.open('rb') as stream:stream.seek(max(0,log.stat().st_size-12000));tail=stream.read().decode('utf-8',errors='replace').lower()
                if 'out of memory' in tail or 'memory guard' in tail:message='OOM/BLOCKED: '+message+'; settings preserved, no automatic downgrade'
            if current not in TERMINAL: transition(identifier, 'BLOCKED' if message.startswith('OOM/') else 'FAILED', message)

    def unity_import(self,job,artifact,folder):
        from engines import unity_editor
        if job['payload']['kind']=='world_unity':
            from engines import world_editor as unity_editor
        from engines.plugin_sdk import Plugin,Operation
        plugin=Plugin('unity_editor',{Operation.prepare:unity_editor.prepare,Operation.validate:unity_editor.validate})
        payload=job['payload'];identifier=job['id'];process=None;samples=[];started=time.monotonic()
        commands=plugin.invoke(Operation.prepare,payload,artifact,folder)
        transition(identifier,'POSTPROCESSING')
        try:
            with (folder/'worker.log').open('w',encoding='utf-8') as log:
                for command,stage in commands:
                    log.write('STAGE '+stage+'\n');log.flush()
                    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    (folder/'process.json').write_text(json.dumps(dict(pid=process.pid,kind='unity_import',stage=stage)))
                    while process.poll() is None:
                        if time.monotonic()-started>int(payload.get('timeout_seconds',900)):
                            kill_tree(process)
                            raise TimeoutError('Native Editor validation timeout; exact settings and partial files retained')
                        if get(identifier)['status']=='CANCELLED' or self.stop.is_set():
                            kill_tree(process)
                            if get(identifier)['status']!='CANCELLED':transition(identifier,'BLOCKED','Desktop stopped; native import checkpoint retained, retry uses a new immutable project')
                            return
                        try:
                            tree=[psutil.Process(process.pid),*psutil.Process(process.pid).children(recursive=True)]
                            ram=sum(p.memory_info().rss for p in tree if p.is_running())
                        except (psutil.NoSuchProcess,psutil.AccessDenied):ram=None
                        sample=dict(seconds=time.monotonic()-started,process_tree_ram_bytes=ram)
                        if payload.get('use_gpu'):
                            gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.used,power.draw,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
                            sample['all_gpu_memory_mib_power_w_utilization_percent']=gpu.stdout.strip()
                        samples.append(sample)
                        self.stop.wait(.5)
                    if process.returncode:raise RuntimeError(f'Unity stage {stage} exited {process.returncode}; inspect unity.log/unity_reopen.log')
            transition(identifier,'VALIDATING')
            report=plugin.invoke(Operation.validate,payload,folder)
            (folder/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            metadata=dict(project_id=payload['project_id'],asset_id=payload['asset_id'],parent_id=artifact['id'],job_id=identifier,engine='unity',version=unity_editor.VERSION,
                stage='engine_imported',asset_type='map_environment' if payload['kind']=='world_unity' else 'static_3d',license=artifact['metadata'].get('license','UNKNOWN'),commercial='NOT_CLEARED',human_quality_approval='NOT_GIVEN')
            outputs=getattr(unity_editor,'OUTPUT_ARTIFACTS',[('AFS_Asset.unitypackage','engine_package'),('AFS_Editor_Importer.zip','editor_package'),('unity_report.json','qa_report'),('unity_reopen_report.json','qa_report')])
            for name,role in outputs:
                store.add_artifact(folder/'output'/name,role,name,metadata)
            registered={name for name,_ in outputs}
            for path in (folder/'output').glob('*.png'):
                if path.name not in registered:store.add_artifact(path,'preview',path.name,metadata|dict(preview_kind='layout_mask' if path.name=='layout_overview.png' else 'unity_render'))
            transition(identifier,'REVIEW_REQUIRED')
        finally:
            if process and process.poll() is None:kill_tree(process)
            (folder/'gpu_samples.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
            (folder/'resource_usage.json').write_text(json.dumps(dict(elapsed_seconds=time.monotonic()-started,peak_process_tree_ram_bytes=max((s.get('process_tree_ram_bytes') or 0 for s in samples),default=0),
                gpu_scope='Whole-device nvidia-smi samples, not engine-exclusive allocation',samples=samples),indent=2),encoding='utf-8')

    def concept(self, job, folder):
        from engines.concept_adapter import CONCEPT_ADAPTER
        payload=job['payload']; identifier=job['id']; request_path=folder/'request.json'
        command,cwd,request=CONCEPT_ADAPTER.generate(payload | dict(output=str(folder/'output'),request_path=str(request_path)),print)
        request_path.write_text(json.dumps(request,indent=2),encoding='utf-8')
        samples=[]; started=time.monotonic(); process=None
        try:
            with (folder/'worker.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
                (folder/'process.json').write_text(json.dumps(dict(pid=process.pid,kind='concept')))
                while process.poll() is None:
                    if get(identifier)['status']=='CANCELLED' or self.stop.is_set():
                        CONCEPT_ADAPTER.cancel(dict(process=process))
                        if get(identifier)['status']!='CANCELLED':transition(identifier,'BLOCKED','Server stopped; new attempt required')
                        return
                    gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.used,power.draw,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
                    samples.append(dict(seconds=time.monotonic()-started,all_gpu_memory_mib_power_w_utilization_percent=gpu.stdout.strip()));self.stop.wait(.5)
            if get(identifier)['status']=='CANCELLED':return
            if process.returncode:raise RuntimeError(f'Local concept engine exit {process.returncode}; inspect worker.log')
            transition(identifier,'GENERATED');transition(identifier,'VALIDATING')
            inspection=CONCEPT_ADAPTER.verify_outputs(folder/'output')
            generation=json.loads((folder/'output/generation.json').read_text())
            if generation['status']!='GENERATED_NEEDS_REVIEW':raise ValueError('Concept inference did not succeed')
            record=store.add_artifact(folder/'output/concept.png','concept',payload.get('name','Local concept'),inspection | dict(
                project_id=payload['project_id'],asset_id=payload['asset_id'],job_id=identifier,origin='sdxl_local',
                requires_concept_approval=True,generation=generation,license=CONCEPT_ADAPTER.license))
            (folder/'manifest.json').write_text(json.dumps(dict(concept_artifact=record['id'],source_prompt=payload['prompt'],human_approval='REQUIRED'),indent=2),encoding='utf-8')
            transition(identifier,'REVIEW_REQUIRED')
        finally:
            if process and process.poll() is None:kill_tree(process)
            (folder/'gpu_samples.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')

    def inference(self, job, source_record, source, folder):
        from engines.adapters import ADAPTERS
        from .inspection import inspect_image
        payload = job['payload']; identifier = job['id']; adapter = ADAPTERS[payload['engine']]
        request_path = folder / 'request.json'
        request = {'image': str(source), 'output': str(folder / 'output'), 'seed': payload['seed'],
                   'effective_config':payload.get('effective_config'),'effective_config_hash':payload.get('effective_config_hash'),
                   'steps': payload['steps'], 'pipeline_type': payload['pipeline_type'], 'texture_size': payload['texture_size'],
                   'export_triangle_target': 1_000_000, 'supplied_alpha_input': bool(source_record['metadata'].get('has_transparency')),
                   'input_review': 'NEEDS_REVIEW', 'request_path': str(request_path)}
        events = []
        command, cwd, request = adapter.generate(request, events.append)
        request_path.write_text(json.dumps(request, indent=2), encoding='utf-8')
        (folder / 'events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
        process = None; samples = []; started = time.monotonic()
        try:
            with (folder / 'worker.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
                (folder / 'process.json').write_text(json.dumps({'pid': process.pid, 'created_at': store.now(), 'kind': 'inference'}), encoding='utf-8')
                while process.poll() is None:
                    if get(identifier)['status'] == 'CANCELLED' or self.stop.is_set():
                        adapter.cancel({'process': process})
                        if get(identifier)['status'] != 'CANCELLED': transition(identifier, 'BLOCKED', 'Server stopped; new attempt required')
                        return
                    gpu = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,power.draw,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10)
                    samples.append({'seconds': time.monotonic()-started, 'all_gpu_memory_mib_power_w_utilization_percent': gpu.stdout.strip()})
                    self.stop.wait(0.5)
            if get(identifier)['status'] == 'CANCELLED': return
            if process.returncode: raise RuntimeError(f'Local engine exit {process.returncode}; inspect worker.log')
            transition(identifier, 'GENERATED'); transition(identifier, 'VALIDATING')
            output = folder / 'output'
            generation = json.loads((output / 'generation.json').read_text(encoding='utf-8'))
            if generation['status'] != 'GENERATED_NEEDS_REVIEW': raise ValueError('Engine did not report successful real generation')
            inspection = adapter.verify_outputs(output)
            record = store.add_artifact(output / 'raw.glb', 'candidate', f'{adapter.id} seed {payload["seed"]} / {identifier[:6]}', inspection | {
                'project_id': payload.get('project_id') or source_record.get('project_id'), 'asset_id': payload.get('asset_id') or source_record.get('asset_id'),
                'engine': adapter.id, 'seed': payload['seed'], 'generation': generation, 'job_id': identifier,
                'parent_id': source_record['id'], 'tournament_id': payload['tournament_id'], 'license': 'EVALUATION_ONLY_PENDING_AUDIT'})
            for name in ['source_alpha.png', 'conditioning.png']:
                path = output / name
                if path.exists(): store.add_artifact(path, 'reference', f'{adapter.id} {name}', inspect_image(path) | {
                    'project_id': payload.get('project_id') or source_record.get('project_id'), 'asset_id': payload.get('asset_id') or source_record.get('asset_id'),
                    'origin': 'engine_preprocessing', 'parent_id': source_record['id'], 'license': 'EVALUATION_ONLY_PENDING_AUDIT'})
            manifest = {'source_artifact': source_record['id'], 'source_sha256': source_record['sha256'],
                        'candidate_artifact': record['id'], 'engine': adapter.id, 'duration_seconds': time.monotonic()-started,
                        'tournament_id': payload['tournament_id'], 'quality': 'NEEDS_REVIEW', 'unity': 'NOT_TESTED', 'mesh_quality_parity': 'NOT_TESTED'}
            (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            transition(identifier, 'REVIEW_REQUIRED')
            if payload.get('auto_blender'):
                height = payload.get('benchmark_height_m')
                enqueue({'kind': 'blender', 'artifact_id': record['id'], 'normalize': bool(height), 'target_height_m': height,
                         'batch_id': payload.get('batch_id'), 'effective_config':payload.get('effective_config'), 'effective_config_hash':payload.get('effective_config_hash'),
                         'batch_attempt':payload.get('batch_attempt',0),
                         'project_id': payload.get('project_id') or record.get('project_id'), 'asset_id': payload.get('asset_id') or record.get('asset_id'),
                         'render': True, 'resolutions': ['mobile', 'pc1440'], 'views': ['front', 'three_quarter', 'side', 'back', 'top', 'gameplay'],
                         'parent_job': identifier,'depends_on':[identifier]})
        finally:
            if process and process.poll() is None: kill_tree(process)
            (folder / 'gpu_samples.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')


worker = Worker()
