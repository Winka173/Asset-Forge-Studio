"""Support report: one zip with logs, system facts and recent job failures, for bug reports. Personal paths and the API token are redacted; prompts are not included."""
import json
import os
import platform
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

from . import jobs, store

router = APIRouter(prefix='/api/diagnostics', tags=['diagnostics'])
LOG_TAIL = 5_000_000
JOB_KEYS = ('kind', 'engine', 'asset_id', 'quality', 'seed', 'steps', 'pipeline_type', 'texture_size')


def redact(text):
    home = str(Path.home())
    for value, label in ((home, '<HOME>'), (home.replace(chr(92), '/'), '<HOME>'), (Path.home().name, '<USER>'), (os.environ.get('AFS_API_TOKEN') or '', '<TOKEN>')):
        if value and len(value) > 2: text = text.replace(value, label)
    return re.sub(r'(?i)(x-afs-token["\': =]+)[0-9a-f]{32,}', r'\1<TOKEN>', text)


def tail(path, limit=LOG_TAIL):
    with open(path, 'rb') as stream:
        size = path.stat().st_size
        stream.seek(max(0, size - limit))
        return stream.read().decode('utf-8', errors='replace')


def run(command):
    try: return subprocess.run(command, capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
    except Exception as error: return f'unavailable: {error}'


def system_facts():
    facts = dict(created_at=store.now(), app_version=os.environ.get('AFS_VERSION') or 'see app title', os=platform.platform(), python=platform.python_version(),
                 gpu=run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.used', '--format=csv,noheader']))
    try:
        import psutil
        facts.update(ram_gb=round(psutil.virtual_memory().total / 2**30, 1), ram_free_gb=round(psutil.virtual_memory().available / 2**30, 1),
                     disk_free_gb={str(p.mountpoint): round(shutil.disk_usage(p.mountpoint).free / 2**30, 1) for p in psutil.disk_partitions() if 'cdrom' not in p.opts})
    except Exception as error: facts['resources'] = f'unavailable: {error}'
    try:
        from engines.adapters import ADAPTERS
        from engines.concept_adapter import CONCEPT_ADAPTER
        facts['engines'] = {k: {x: v for x, v in a.probe().items() if x in ('installed', 'version')} for k, a in ADAPTERS.items()} | {CONCEPT_ADAPTER.id: {'installed': CONCEPT_ADAPTER.installed}}
    except Exception as error: facts['engines'] = f'unavailable: {error}'
    try:
        from . import engine_health
        facts['engine_health'] = [{k: r.get(k) for k in ('signature', 'circuit', 'status', 'root_cause')} for r in engine_health.listing()['records']]
    except Exception as error: facts['engine_health'] = f'unavailable: {error}'
    return facts


def build():
    out = store.DATA / 'diagnostics-exports'
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"AFS-report-{store.now().replace(':', '').replace('-', '')[:15]}.zip"
    rows = jobs.listing()
    summary = [dict(id=j['id'], status=j['status'], error=(j.get('error') or '')[:600], created_at=j.get('created_at'),
                    **{k: j['payload'].get(k) for k in JOB_KEYS if j['payload'].get(k) is not None}) for j in rows[:300]]
    failed = [j for j in rows if j['status'] in ('FAILED', 'BLOCKED')][:20]
    config_dir = Path(os.environ.get('AFS_DESKTOP_CONFIG_DIR') or store.CONFIG_ROOT)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('README.txt', 'Asset Forge Studio support report. Contains logs, system facts and recent job states. Prompts and personal paths are removed.\n')
        bundle.writestr('system.json', redact(json.dumps(system_facts(), indent=2, default=str)))
        bundle.writestr('jobs.json', redact(json.dumps(summary, indent=2, default=str)))
        for log in sorted((config_dir / 'logs').glob('*.log')) if (config_dir / 'logs').is_dir() else []:
            bundle.writestr('logs/' + log.name, redact(tail(log)))
        for j in failed:
            log = store.DATA / 'jobs' / j['id'] / 'worker.log'
            if log.is_file(): bundle.writestr(f"failed-jobs/{j['id'][:8]}-{j['payload'].get('kind', 'job')}.log", redact(tail(log, 200_000)))
    return target


@router.post('/export')
def export_report():
    try: target = build()
    except Exception as error: raise HTTPException(500, f'Could not create the support report: {error}')
    return dict(path=str(target), bytes=target.stat().st_size, folder=str(target.parent))
