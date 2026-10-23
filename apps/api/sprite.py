"""2D sprite slice: SDXL concept with sprite framing (project style profile applies) -> deterministic cutout -> PNGs.

Each option is one concept seed plus one CPU cutout job that depends on it. The cutout reports measured usability;
an unusable cutout stays visible as a failed option instead of being passed off as a sprite.
"""
import json
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from . import store, jobs, studio

router = APIRouter(prefix='/api/sprites')


class Generate(BaseModel):
    asset_id: str
    request_id: str = Field(min_length=8, max_length=100)
    quality: Literal['Fast', 'Balanced', 'Maximum'] = 'Maximum'
    seeds: list[int] = Field(default=[42, 43, 44], min_length=1, max_length=4)
    sizes: list[Literal[256, 512, 1024]] = Field(default=[256, 512, 1024], min_length=1)


@router.post('/generate', status_code=201)
def generate(body: Generate):
    value = studio.asset(body.asset_id)
    if value.get('asset_type') != 'sprite_2d': raise HTTPException(409, 'Create the asset as a 2D sprite first')
    sizes = sorted(set(body.sizes)) if 512 in body.sizes else sorted({*body.sizes, 512})  # 512 is the library preview
    options = []
    for seed in dict.fromkeys(body.seeds):
        concept = studio.concept(studio.ConceptInput(asset_id=body.asset_id, request_id=f'{body.request_id}:concept:{seed}'[:100], prompt=value['prompt'] or value['name'],
                                                     quality=body.quality, seed=seed, framing='sprite_2d'))
        existing = next((j for j in jobs.listing() if j['payload'].get('kind') == 'sprite_cutout' and j['payload'].get('concept_job_id') == concept['id']), None)
        cutout = existing or jobs.enqueue(dict(kind='sprite_cutout', project_id=value['project_id'], asset_id=body.asset_id, concept_job_id=concept['id'],
                                               depends_on=[concept['id']], sizes=sizes, use_gpu=False, timeout_seconds=300))
        options.append(dict(seed=seed, concept_job_id=concept['id'], cutout_job_id=cutout['id']))
    return dict(asset_id=body.asset_id, options=options)


def execute(job, folder):
    from engines.sprite import cutout, export
    p = job['payload']
    with store.connect() as db:
        row = db.execute("SELECT id FROM artifacts WHERE role='concept' AND asset_id=? AND json_extract(metadata,'$.job_id')=?", (p['asset_id'], p['concept_job_id'])).fetchone()
    if not row: raise ValueError('Concept output for this sprite option is missing')
    source = store.get_artifact(row['id']); path = store.safe_path(source['relative_path'])
    if store.digest(path) != source['sha256']: raise ValueError('Concept image changed after generation')
    harmonized = None
    from .style_profile import anchor as style_anchor, mode
    project = studio.project(p['project_id']); reference = style_anchor(p['project_id'], project) if mode(project) == 'profile' else None
    if reference:
        # Hue-preserving: shares the anchor's contrast/saturation level; a requested red stays red.
        from engines.harmonize import harmonize
        image, harmonized = harmonize(path, reference['path'], 0.5)
        path = folder / 'harmonized.png'; image.save(path)
        harmonized['anchor_sha256'] = reference['record']['sha256']
    sprite, report = cutout(path)
    report.update(source_artifact_id=source['id'], source_sha256=source['sha256'], harmonized=harmonized)
    (folder / 'sprite_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if sprite is None: raise ValueError('Cutout found no object in the concept image')
    for file in export(sprite, folder / 'output', p['sizes']):
        store.add_artifact(file['path'], 'sprite', f"Sprite {file['size']}px", dict(project_id=p['project_id'], asset_id=p['asset_id'], job_id=job['id'], parent_id=source['id'],
            size=file['size'], upscaled=file['upscaled'], usable=report['usable'], cutout=report, artistic_approval=False))
    jobs.transition(job['id'], 'GENERATED'); jobs.transition(job['id'], 'VALIDATING'); jobs.transition(job['id'], 'REVIEW_REQUIRED')
