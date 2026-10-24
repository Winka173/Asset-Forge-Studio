"""After a game delivery, drop bulky working files the delivered GLB no longer needs.

Default on; a project opts out with cleanup_intermediates=false. Registered artifacts (raw and
processed GLBs, concepts, checks) are never touched, so the Library, re-export, rigging and
uniform-scale revisions keep working. Files an export setting still needs are kept.
"""
import re

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
