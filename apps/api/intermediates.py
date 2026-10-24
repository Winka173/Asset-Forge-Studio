"""After a game delivery, drop bulky working files the delivered GLB no longer needs.

Default on; a project opts out with cleanup_intermediates=false. Registered artifacts (raw and
processed GLBs, concepts, checks) are never touched, so the Library, re-export, rigging and
uniform-scale revisions keep working. Files an export setting still needs are kept.
"""
import json
import re

from fastapi import APIRouter, HTTPException

from . import jobs, store

# (pattern on the path inside the job folder, export setting that still needs it)
RULES = [
    (r'(?:output/)?raw_master\.npz|(?:output/)?mesh_checkpoint\.json', None),
    (r'.*_passes\.exr', None),
    (r'.*\.blend', 'blend'),
    (r'.*LOD[1-3]\.glb', 'lods'),
    (r'.*LOD\d\.fbx', 'fbx'),
    (r'.*textures/.+', 'textures'),
]


def enabled(project):
    return project.get('cleanup_intermediates') is not False


def prune(asset_id, export_settings):
    settings = export_settings or {}
    keep_native = bool(settings.get('unity_package'))
    with store.connect() as db:
        registered = {row['relative_path'] for row in db.execute('SELECT relative_path FROM artifacts WHERE asset_id=?', (asset_id,))}
    removed, freed = [], 0
    for job in jobs.listing():
        if job['payload'].get('asset_id') != asset_id or job['status'] not in jobs.TERMINAL: continue
        folder = store.DATA / 'jobs' / job['id']
        if not folder.is_dir(): continue
        for file in folder.rglob('*'):
            relative = file.relative_to(folder).as_posix()
            if not file.is_file() or f"jobs/{job['id']}/{relative}" in registered: continue
            rule = next((needs for pattern, needs in RULES if re.fullmatch(pattern, relative)), False)
            if rule is False or (rule and settings.get(rule)) or (keep_native and rule in ('fbx', 'textures')): continue
            size = file.stat().st_size
            file.unlink(); removed.append(f"{job['id']}/{relative}"); freed += size
    return dict(files=len(removed), bytes=freed, at=store.now(), scope='terminal jobs of a delivered asset; registered artifacts kept')


router = APIRouter(prefix='/api/production')


@router.post('/assets/{asset_id}/finalize')
def finalize(asset_id: str):
    """Explicit user action: keep only the delivered GLB (plus its rigged copy and one thumbnail render)."""
    from . import batch, studio
    from .export_profiles import _schema, _verify_delivery
    with batch.LOCK:
        model = studio.asset(asset_id); published = model.get('published_artifact_id')
        if not published: raise HTTPException(409, 'Deliver a version to the game before keeping only the final GLB.')
        if any(j['payload'].get('asset_id') == asset_id and j['status'] not in jobs.TERMINAL for j in jobs.listing()):
            raise HTTPException(409, 'Wait for this asset\'s running work to finish.')
        _schema()
        with store.connect() as db:
            deliveries = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM selective_exports WHERE asset_id=?', (asset_id,))]
            artifacts = [store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=?', (asset_id,))]
        final = [d for d in deliveries if d.get('delivery_scope', 'game') == 'game' and (d['artifact_id'] == published or store_parent(artifacts, d['artifact_id']) == published)]
        if not final: raise HTTPException(409, 'The selected version has no completed game delivery; nothing was deleted.')
        for delivery in final: _verify_delivery(delivery)
        keep = {published, *(d['artifact_id'] for d in final), *(a['id'] for a in artifacts if a['role'] == 'rigged' and a['metadata'].get('parent_id') in {published, *(d['artifact_id'] for d in final)})}
        kept_paths = {a['relative_path'] for a in artifacts if a['id'] in keep}
        source_job = next((a['metadata'].get('job_id') for a in artifacts if a['id'] == published), None)
        if source_job: kept_paths.add(f'jobs/{source_job}/output/fit_three_quarter.png')
        removed, freed = 0, 0
        for job in jobs.listing():
            if job['payload'].get('asset_id') != asset_id: continue
            folder = store.DATA / 'jobs' / job['id']
            for file in (folder.rglob('*') if folder.is_dir() else []):
                relative = file.relative_to(store.DATA).as_posix()
                if not file.is_file() or relative in kept_paths or file.suffix.lower() == '.json': continue
                freed += file.stat().st_size; file.unlink(); removed += 1
        dropped = [a['id'] for a in artifacts if a['id'] not in keep and a['relative_path'].startswith('jobs/')]
        with store.connect() as db:
            db.executemany('DELETE FROM artifacts WHERE id=?', [(i,) for i in dropped])
        model = studio.asset(asset_id)
        for field in ('concept_artifact_id', 'master_artifact_id', 'cover_artifact_id'):
            if model.get(field) in dropped: model[field] = None
        model['finalized'] = dict(at=store.now(), artifact_id=published, files=removed, bytes=freed, kept=sorted(keep))
        studio.save_asset(model)
        return model['finalized']


def store_parent(artifacts, artifact_id):
    return next((a['metadata'].get('parent_id') for a in artifacts if a['id'] == artifact_id), None)
