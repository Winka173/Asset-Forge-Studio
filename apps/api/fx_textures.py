"""Seamless effect textures (noise, flame mask, dissolve, caustics, streaks, cells) saved as project artifacts.

CPU only and quick (well under a second at 1024 px), so it runs inline instead of through the job queue.
"""
import uuid
from typing import Literal
from pydantic import BaseModel,Field
from fastapi import APIRouter
from . import store,studio

router=APIRouter(prefix='/api/fx/textures')


class Texture(BaseModel):
    project_id:str
    kind:Literal['noise','flame_mask','dissolve','caustics','streaks','cells']='noise'
    size:Literal[512,1024,2048]=1024
    seed:int=Field(default=42,ge=0,le=2147483647)


def _asset(project_id):
    """One 'Effect textures' asset per game keeps generated textures together in the Library."""
    import json
    identifier=uuid.uuid5(uuid.NAMESPACE_URL,'afs-fx-textures:'+project_id).hex
    asset=dict(id=identifier,project_id=project_id,asset_type='vfx',name='Effect textures',prompt='',original_prompt='',category='Effects',reference_ids=[],settings={},
               favorite=False,status='Candidate',master_artifact_id=None,approvals=[],created_at=store.now())
    with store.connect() as db:db.execute('INSERT INTO assets VALUES (?,?,?) ON CONFLICT(id) DO NOTHING',(identifier,project_id,json.dumps(asset)))
    return identifier


@router.post('',status_code=201)
def create(body:Texture):
    from PIL import Image
    from engines.vfx_textures import generate,seam_error
    studio.project(body.project_id);asset_id=_asset(body.project_id)
    pixels=generate(body.kind,body.size,body.seed)
    target=store.safe_path(f'projects/{body.project_id}/assets/{asset_id}/textures/{body.kind}_{body.size}_{body.seed}.png');target.parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(pixels,'L').save(target)
    with store.connect() as db:row=db.execute('SELECT * FROM artifacts WHERE relative_path=?',(target.relative_to(store.DATA).as_posix(),)).fetchone()
    if row:return store.artifact(row)
    return store.add_artifact(target,'vfx_texture',f'{body.kind.replace("_"," ").title()} · {body.size}px · seed {body.seed}',
                              dict(project_id=body.project_id,asset_id=asset_id,kind=body.kind,size=body.size,seed=body.seed,tileable=True,seam_ratio=round(seam_error(pixels),3),method='frequency-domain noise / wrapped distances'))


@router.get('')
def listing(project_id:str):
    with store.connect() as db:return [store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE project_id=? AND role='vfx_texture' ORDER BY created_at DESC",(project_id,))]
