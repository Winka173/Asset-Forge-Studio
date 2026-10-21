"""Durable sequential subprocess jobs. No network, shell=True, or global environment mutations."""
import contextlib
import json
import os
import subprocess
import threading
import time
import uuid
import re

import psutil

from . import store
from .inspection import inspect_glb

WORKER_LOCK = store.ROOT / '.local/worker.lock'

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
def exclusive_worker_lock():
    # Same checkout-wide lock across API processes and separate test databases.
    path = WORKER_LOCK; path.parent.mkdir(parents=True, exist_ok=True)
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
        self.stop = threading.Event(); self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop.clear(); self.thread = threading.Thread(target=self.loop, daemon=True); self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=20)

    def loop(self):
        while not self.stop.is_set():
            try:
                with exclusive_worker_lock():
                    # Recover only while owning the lock: a crashed attempt is never silently resumed.
                    with store.connect() as db:
                        db.execute("UPDATE jobs SET status='BLOCKED',error='Worker interrupted; retry creates a new attempt',updated_at=? WHERE status IN ('RUNNING','GENERATED','POSTPROCESSING','VALIDATING')", (store.now(),))
                        row = db.execute("SELECT * FROM jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1").fetchone()
                    if row: self.execute(decode(row))
            except OSError:
                pass  # Another process owns the worker/GPU lock.
            except Exception as exc:
                print(f'AFS_WORKER_ERROR {exc}', flush=True)
            self.stop.wait(0.3)

    def execute(self, job):
        identifier = job['id']; payload = job['payload']; process = None
        folder = store.DATA / 'jobs' / identifier; folder.mkdir(parents=True, exist_ok=True)
        try:
            transition(identifier, 'RUNNING')
            artifact = store.get_artifact(payload['artifact_id'])
            source = store.safe_path(artifact['relative_path'])
            if store.digest(source) != artifact['sha256']: raise ValueError('Immutable source checksum changed')
            if payload['kind'] == 'inference':
                self.inference(job, artifact, source, folder)
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
                process = subprocess.Popen([blender, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
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
            if current not in TERMINAL: transition(identifier, 'FAILED', str(exc))

    def inference(self, job, source_record, source, folder):
        from engines.adapters import ADAPTERS
        from .inspection import inspect_image
        payload = job['payload']; identifier = job['id']; adapter = ADAPTERS[payload['engine']]
        request_path = folder / 'request.json'
        request = {'image': str(source), 'output': str(folder / 'output'), 'seed': payload['seed'],
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
                    gpu = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,power.draw', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10)
                    samples.append({'seconds': time.monotonic()-started, 'all_gpu_memory_mib_and_power_w': gpu.stdout.strip()})
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
                         'project_id': payload.get('project_id') or record.get('project_id'), 'asset_id': payload.get('asset_id') or record.get('asset_id'),
                         'render': True, 'resolutions': ['mobile', 'pc1440'], 'views': ['front', 'three_quarter', 'side', 'back', 'top', 'gameplay'],
                         'parent_job': identifier})
        finally:
            if process and process.poll() is None: kill_tree(process)
            (folder / 'gpu_samples.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')


worker = Worker()
