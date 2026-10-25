"""Project/request style anchor for concept generation as a native reference image of FLUX.2 [klein] (no adapter, no download).

Only used when the project's anchor mode is 'image'; the default 'profile' mode passes the anchor as text so its silhouette
never transfers (measured: a reference house turns a requested watchtower into a house)."""
from . import store

IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp')


def resolve(project_id, project, style_reference_ids=()):
    """Return the worker anchor (path + identity) or None when there is no usable image anchor."""
    anchor_id = next(iter(style_reference_ids or ()), None) or project.get('style_anchor_artifact_id')
    if not anchor_id:
        return None
    from .studio import scoped_artifact
    record = scoped_artifact(anchor_id, project_id)
    path = store.safe_path(record['relative_path'])
    if path.suffix.lower() not in IMAGE_SUFFIXES or store.digest(path) != record['sha256']:
        return None
    return dict(artifact_id=record['id'], path=str(path), sha256=record['sha256'], mode='native_reference_image')


def locked(anchor):
    """Identity stored in the effective configuration (no machine paths)."""
    return {k: anchor[k] for k in ('artifact_id', 'sha256', 'mode')} if anchor else None
