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


SPRITE_SEEDS = [42, 43, 44]


def admit_batch(value, item, auto):
    """A batch item with output 2d takes the Single 2D route: sprite-framed concepts then cutouts (no 3D), as this item's jobs.
    Returns True while the item is handled here (running or finished); 3D items return False."""
    if item.get('output') != '2d': return False
    mine = [j for j in jobs.listing() if j['payload'].get('batch_id') == value['id'] and j['payload'].get('asset_id') == item['asset_id'] and j['payload'].get('batch_attempt', 0) == item['attempt']]
    concepts = [j for j in mine if j['payload']['kind'] == 'concept']; cutouts = [j for j in mine if j['payload']['kind'] == 'sprite_cutout']
    model = studio.asset(item['asset_id'])
    if model.get('asset_type') != 'sprite_2d': model['asset_type'] = 'sprite_2d'; studio.save_asset(model)
    if not concepts:
        prompt = (item.get('prompt_interpretation') or {}).get('generation_prompt_en') or item.get('resolved_prompt') or item['prompt']
        for seed in SPRITE_SEEDS:
            concepts.append(studio.concept(studio.ConceptInput(asset_id=item['asset_id'], request_id=f"{value['id']}:{item['asset_id']}:{item['attempt']}:sprite:{seed}"[:100], prompt=prompt,
                quality=item['quality'], seed=seed, framing='sprite_2d', batch_id=value['id'], batch_attempt=item['attempt'], style_reference_ids=item.get('style_reference_ids', []))))
    for concept in concepts:
        if not any(c['payload'].get('concept_job_id') == concept['id'] for c in cutouts):
            cutouts.append(jobs.enqueue(dict(kind='sprite_cutout', project_id=value['project_id'], asset_id=item['asset_id'], concept_job_id=concept['id'], depends_on=[concept['id']],
                                             batch_id=value['id'], batch_attempt=item['attempt'], sizes=[256, 512, 1024], use_gpu=False, timeout_seconds=300)))
    if any(j['status'] not in jobs.TERMINAL for j in concepts + cutouts):
        auto.update(status='running', stage='2D sprite: concept and cutout'); return True
    good = [j for j in cutouts if j['status'] == 'REVIEW_REQUIRED']
    if good: auto.update(status='exported', stage=f'2D sprites ready ({len(good)} options) in Library', error=None)
    else: auto.update(status='failed', stage='2D sprite', error='No cutout found a clean object in the sprite concepts; Retry makes new options.')
    return True
