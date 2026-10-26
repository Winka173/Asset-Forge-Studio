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

ROOT = Path(os.environ.get('AFS_UNIRIG_ROOT', str(Path.home() / 'Tools/unirig')))
ENGINE = 'unirig@6793c664'
LIMITATIONS = ['Experimental automatic rig: review skin weights where clothing or held props touch the body',
               'Bipeds get Mixamo bone names (Hips, Spine, LeftArm, LeftUpLeg...) for Unity Humanoid auto-mapping (Unity import not tested); other shapes keep generic bone_N names',
               'No engine import or animation playback has been tested']


def installed():
    return (ROOT / 'venv/Scripts/python.exe').is_file() and (ROOT / 'code/run.py').is_file()


def wanted(item, project):
    """Characters and creatures are almost always animated next; rig them unless the project opted out."""
    if project.get('auto_rig') is False or not installed() or item.get('companion_of'): return False  # held props are never rigged
    from engines.concept_prompt import rig_class, subject_anchor
    from . import studio
    try: chosen = item.get('kind') or (studio.asset(item['asset_id']).get('kind') if item.get('asset_id') else None) or 'auto'
    except Exception: chosen = 'auto'
    if chosen != 'auto': return chosen in ('character', 'creature')
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


def animation_ready(rigged, output, folder, facts):
    """Bipeds get standard humanoid (Mixamo) bone names so Unity Humanoid and retargeting tools attach clips directly.
    Returns the GLB to keep and what happened; the generic rig stays when naming is not possible or changes the skin."""
    from .local_tools import executable
    blender = executable('blender')
    if not blender: return rigged, dict(humanoid=False, reason='Blender not found; generic bone names kept')
    named, report = output / 'rigged_humanoid.glb', output / 'humanoid.json'
    with (folder / 'worker.log').open('a', encoding='utf-8') as log:
        subprocess.call([blender, '-b', '--factory-startup', '--python-exit-code', '1', '--python', str(store.ROOT / 'pipelines/blender/humanoid_names.py'), '--',
                         '--input', str(rigged), '--output', str(named), '--report', str(report)], stdout=log, stderr=subprocess.STDOUT, timeout=600)
    result = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else dict(humanoid=False, reason='Naming step failed; see worker.log')
    if result.get('humanoid') and named.is_file() and joints(named) == facts: return named, result
    if result.get('humanoid'): result = dict(humanoid=False, reason='Renamed rig changed the skin; generic bone names kept')
    return rigged, result


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
    rigged, humanoid = animation_ready(rigged, output, folder, facts)
    store.add_artifact(rigged, 'rigged', 'Rigged copy (experimental)', dict(project_id=p['project_id'], asset_id=p['asset_id'], job_id=job['id'], parent_id=record['id'],
        engine=ENGINE, license='UniRig code MIT; weights MIT (VAST-AI/UniRig)', experimental=True, limitations=LIMITATIONS, artistic_approval=False, **facts, timings=report.get('timings'),
        humanoid=humanoid))
    jobs.transition(job['id'], 'GENERATED'); jobs.transition(job['id'], 'VALIDATING'); jobs.transition(job['id'], 'REVIEW_REQUIRED')
