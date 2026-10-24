"""After a game delivery, drop bulky working files the delivered GLB no longer needs.

Default on; a project opts out with cleanup_intermediates=false. Registered artifacts (raw and
processed GLBs, concepts, checks) are never touched, so the Library, re-export, rigging and
uniform-scale revisions keep working. Files an export setting still needs are kept.
"""
import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


_usage = {}


def disk_usage(asset_ids):
    """Bytes in each asset's job folders (the library's working copy), cached for a minute."""
    import os, time
    now = time.time(); wanted = {a for a in asset_ids if now - _usage.get(a, (0, 0))[0] > 60}
    if wanted:
        totals = dict.fromkeys(wanted, 0)
        for job in jobs.listing():
            owner = job['payload'].get('asset_id')
            if owner not in totals: continue
            for root, _, names in os.walk(store.DATA / 'jobs' / job['id']):
                for name in names:
                    try: totals[owner] += os.stat(os.path.join(root, name)).st_size
                    except OSError: pass
        _usage.update({a: (now, b) for a, b in totals.items()})
    return {a: _usage[a][1] for a in asset_ids}


def forget(asset_id):
    _usage.pop(asset_id, None)


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


def plan(asset_id):
    """What "Keep final only" keeps and deletes for one asset, without touching anything.

    Kept: the published version, every file of its completed game delivery (the GLB and any other delivered
    formats such as FBX, LODs, textures, manifest or ZIP stay in the delivery folder untouched), rigged copies
    of it and one thumbnail render. Deleted: every other file in the asset's job folders (JSON receipts stay)
    and the artifact records of the deleted files.
    """
    from . import studio
    from .export_profiles import _schema, _verify_delivery
    model = studio.asset(asset_id); published = model.get('published_artifact_id')
    result = dict(asset_id=asset_id, name=model.get('name'), eligible=False, reason=None, keep=[], delivery=[], delete_files=0, delete_bytes=0)
    if model.get('finalized'): return result | dict(reason='Already reduced to the final files.')
    if not published: return result | dict(reason='No version has been delivered to the game yet.')
    if any(j['payload'].get('asset_id') == asset_id and j['status'] not in jobs.TERMINAL for j in jobs.listing()):
        return result | dict(reason='Work is still running for this asset.')
    _schema()
    with store.connect() as db:
        deliveries = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM selective_exports WHERE asset_id=?', (asset_id,))]
        artifacts = [store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=?', (asset_id,))]
    final = [d for d in deliveries if d.get('delivery_scope', 'game') == 'game' and (d['artifact_id'] == published or store_parent(artifacts, d['artifact_id']) == published)]
    if not final: return result | dict(reason='The published version has no completed game delivery.')
    try:
        for delivery in final: _verify_delivery(delivery)
    except HTTPException as exc: return result | dict(reason=str(exc.detail))
    roots = {published, *(d['artifact_id'] for d in final)}
    keep = roots | {a['id'] for a in artifacts if a['role'] == 'rigged' and a['metadata'].get('parent_id') in roots}
    kept = [a for a in artifacts if a['id'] in keep]
    kept_paths = {a['relative_path'] for a in kept}
    source_job = next((a['metadata'].get('job_id') for a in artifacts if a['id'] == published), None)
    thumbnail = f'jobs/{source_job}/output/fit_three_quarter.png' if source_job else None
    if thumbnail and (store.DATA / thumbnail).is_file(): kept_paths.add(thumbnail)
    doomed = []
    for job in jobs.listing():
        if job['payload'].get('asset_id') != asset_id: continue
        folder = store.DATA / 'jobs' / job['id']
        for file in (folder.rglob('*') if folder.is_dir() else []):
            relative = file.relative_to(store.DATA).as_posix()
            if file.is_file() and relative not in kept_paths and file.suffix.lower() != '.json': doomed.append(file)
    size = lambda path: path.stat().st_size if path.is_file() else 0
    label = lambda a: 'Rigged copy' if a['role'] == 'rigged' else 'Final model' if a['id'] == published else 'Delivered source'
    listed = [dict(label=label(a), file=a['relative_path'].rsplit('/', 1)[-1], bytes=size(store.DATA / a['relative_path'])) for a in kept]
    if thumbnail in kept_paths: listed.append(dict(label='Thumbnail', file='fit_three_quarter.png', bytes=size(store.DATA / thumbnail)))
    return result | dict(eligible=True, published=published, keep_ids=sorted(keep), doomed=[str(f) for f in doomed], keep=listed,
                         delivery=[dict(folder=d['export_directory'], files=[dict(file=f['name'], kind=f.get('kind'), bytes=f.get('bytes')) for f in d['files']]) for d in final],
                         delete_files=len(doomed), delete_bytes=sum(size(f) for f in doomed), library_bytes=disk_usage([asset_id])[asset_id],
                         delivery_bytes=sum(f.get('bytes') or 0 for d in final for f in d['files']))


def public(value):
    return {k: v for k, v in value.items() if k not in ('keep_ids', 'doomed', 'published')}


class Selection(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=500)


@router.post('/finalize/preview')
def preview(body: Selection):
    return [public(plan(asset_id)) for asset_id in dict.fromkeys(body.asset_ids)]


@router.post('/finalize')
def finalize_many(body: Selection):
    return [finalize(asset_id) for asset_id in dict.fromkeys(body.asset_ids)]


@router.post('/assets/{asset_id}/finalize')
def finalize(asset_id: str):
    """Explicit, confirmed user action: keep only the final delivered files (see plan)."""
    from pathlib import Path
    from . import batch, studio
    with batch.LOCK:
        value = plan(asset_id)
        if not value['eligible']: raise HTTPException(409, f"{value['name']}: {value['reason']} Nothing was deleted.")
        freed = 0
        for path in map(Path, value['doomed']):
            if path.is_file(): freed += path.stat().st_size; path.unlink()
        keep = set(value['keep_ids'])
        with store.connect() as db:
            dropped = [r['id'] for r in db.execute('SELECT id, relative_path FROM artifacts WHERE asset_id=?', (asset_id,)) if r['id'] not in keep and r['relative_path'].startswith('jobs/')]
            db.executemany('DELETE FROM artifacts WHERE id=?', [(i,) for i in dropped])
        model = studio.asset(asset_id)
        for field in ('concept_artifact_id', 'master_artifact_id', 'cover_artifact_id'):
            if model.get(field) in dropped: model[field] = None
        model['finalized'] = dict(at=store.now(), artifact_id=value['published'], files=len(value['doomed']), bytes=freed, kept=sorted(keep), before_bytes=value['library_bytes'], after_bytes=value['library_bytes'] - freed)
        forget(asset_id)
        studio.save_asset(model)
        return model['finalized'] | dict(asset_id=asset_id, name=value['name'])


def store_parent(artifacts, artifact_id):
    return next((a['metadata'].get('parent_id') for a in artifacts if a['id'] == artifact_id), None)
