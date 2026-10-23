"""Project/request style anchor for concept generation via locally cached IP-Adapter Plus SDXL (no download)."""
import os
from pathlib import Path

from . import store

WEIGHT_NAME = 'ip-adapter-plus_sdxl_vit-h.safetensors'
# Strength of image-prompt conditioning. Plus adapters also carry composition cues, so the text keeps the subject
# only while the scale stays moderate; measured per project before raising it.
DEFAULT_SCALE = 0.35  # measured: 0.35 kept the castle subject in the anchor style; 0.5 drifted toward the anchor tower, 0.7 copied it
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp')


def adapter_dir():
    hub = Path(os.environ.get('HF_HUB_CACHE') or Path(os.environ.get('HF_HOME', Path.home() / '.cache/huggingface')) / 'hub')
    repo = hub / 'models--h94--IP-Adapter'
    ref = repo / 'refs/main'
    if not ref.is_file():
        return None
    snapshot = repo / 'snapshots' / ref.read_text().strip()
    required = (snapshot / 'sdxl_models' / WEIGHT_NAME, snapshot / 'models/image_encoder/model.safetensors', snapshot / 'models/image_encoder/config.json')
    return snapshot if all(p.is_file() for p in required) else None


def resolve(project_id, project, style_reference_ids=()):
    """Return the worker anchor (paths + identity) or None when no image anchor or adapter is available."""
    directory = adapter_dir()
    anchor_id = next(iter(style_reference_ids or ()), None) or project.get('style_anchor_artifact_id')
    if not directory or not anchor_id:
        return None
    from .studio import scoped_artifact
    record = scoped_artifact(anchor_id, project_id)
    path = store.safe_path(record['relative_path'])
    if path.suffix.lower() not in IMAGE_SUFFIXES or store.digest(path) != record['sha256']:
        return None
    return dict(artifact_id=record['id'], path=str(path), sha256=record['sha256'], adapter_dir=str(directory),
                weight_name=WEIGHT_NAME, scale=float(project.get('style_anchor_scale') or DEFAULT_SCALE))


def locked(anchor):
    """Identity stored in the effective configuration (no machine paths)."""
    return {k: anchor[k] for k in ('artifact_id', 'sha256', 'weight_name', 'scale')} if anchor else None
