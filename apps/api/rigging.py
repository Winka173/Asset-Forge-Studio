"""Experimental auto-rigged copy of delivered characters/creatures (local UniRig, MIT code and weights).

The rigged GLB is a separate artifact for animators to start from; the master and game delivery are untouched and a
failed rig never blocks delivery. Measured on a real character: humanoid 28-joint skeleton in ~4 min, ~6.4 GB VRAM;
skin weights bleed where clothing or props touch the body, and bone names are generic (no humanoid retarget map).
"""
import json
import os
import subprocess
from pathlib import Path
from . import store, jobs

ROOT = Path(os.environ.get('AFS_UNIRIG_ROOT', r'C:\Users\Winka\Tools\unirig'))
ENGINE = 'unirig@6793c664'
LIMITATIONS = ['Experimental automatic rig: review skin weights where clothing or held props touch the body',
               'Generic bone names (bone_0..N); retargeting to Unity Humanoid or Mixamo needs a bone map',
               'No engine import or animation playback has been tested']


def installed():
    return (ROOT / 'venv/Scripts/python.exe').is_file() and (ROOT / 'code/run.py').is_file()


def wanted(item, project):
    """Characters and creatures are almost always animated next; rig them unless the project opted out."""
    if project.get('auto_rig') is False or not installed(): return False
    from engines.concept_prompt import rig_class, subject_anchor
    subject = ((item.get('prompt_interpretation') or {}).get('chunks') or [{}])[0].get('interpretation', {}).get('requested_subject_en') or subject_anchor(item.get('resolved_prompt') or item.get('prompt', ''))
    return rig_class(subject) is not None


def enqueue(value, item, candidate_id):
    existing = next((j for j in jobs.listing() if j['payload'].get('kind') == 'rig' and j['payload'].get('artifact_id') == candidate_id), None)
    if existing: return existing
    record = store.get_artifact(candidate_id)
    return jobs.enqueue(dict(kind='rig', engine=ENGINE, project_id=value['project_id'], asset_id=item['asset_id'], batch_id=value['id'], batch_attempt=item['attempt'],
                             artifact_id=candidate_id, source_sha256=record['sha256'], seed=12345, timeout_seconds=1800, priority=item.get('priority', 0) - 1))


def joints(path):
    from .inspection import glb_document
    doc = glb_document(path)
    skins = doc.get('skins', [])
    weighted = any('JOINTS_0' in p.get('attributes', {}) and 'WEIGHTS_0' in p.get('attributes', {}) for m in doc.get('meshes', []) for p in m.get('primitives', []))
    return dict(skins=len(skins), joints=len(skins[0]['joints']) if skins else 0, skinned_primitives=weighted)


def execute(job, folder):
    p = job['payload']; record = store.get_artifact(p['artifact_id']); source = store.safe_path(record['relative_path'])
    if store.digest(source) != p['source_sha256']: raise ValueError('Rig source changed after admission')
    output = folder / 'output'
    request = dict(input=str(source), output=str(output), seed=p.get('seed', 12345))
    (folder / 'request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
    with (folder / 'worker.log').open('w', encoding='utf-8') as log:
        code = subprocess.call([str(ROOT / 'venv/Scripts/python.exe'), '-B', str(store.ROOT / 'engines/unirig_worker.py'), '--request', str(folder / 'request.json')],
                               cwd=ROOT / 'code', stdout=log, stderr=subprocess.STDOUT, timeout=p.get('timeout_seconds', 1800))
    rigged = output / 'rigged.glb'
    if code != 0 or not rigged.is_file(): raise ValueError(f'UniRig failed (exit {code}); see worker.log')
    facts = joints(rigged)
    if not facts['skins'] or facts['joints'] < 2 or not facts['skinned_primitives']: raise ValueError(f'Rigged GLB has no usable skin: {facts}')
    report = json.loads((output / 'unirig_report.json').read_text(encoding='utf-8')) if (output / 'unirig_report.json').is_file() else {}
    store.add_artifact(rigged, 'rigged', 'Rigged copy (experimental)', dict(project_id=p['project_id'], asset_id=p['asset_id'], job_id=job['id'], parent_id=record['id'],
        engine=ENGINE, license='UniRig code MIT; weights MIT (VAST-AI/UniRig)', experimental=True, limitations=LIMITATIONS, artistic_approval=False, **facts, timings=report.get('timings')))
    jobs.transition(job['id'], 'GENERATED'); jobs.transition(job['id'], 'VALIDATING'); jobs.transition(job['id'], 'REVIEW_REQUIRED')
