"""Conservative, versioned strategy selection; no changes to already pinned jobs."""
import hashlib
import json
import re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from . import studio,store


class Requirement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str
    value:str|int|float|list
    provenance:Literal['explicit','inherited','inferred','defaulted']
    source:str
    hard_gate:bool=False


class AssetGenerationSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version:int=1
    asset_id:str
    project_id:str
    original_prompt:str
    original_prompt_sha256:str
    reference_hashes:list[dict]
    subject:str
    category:Literal['organic','hard_surface','architecture','modular_environment','existing_mesh_edit','mixed']
    reference_role:Literal['source','style','none']
    route:Literal['image_to_3d','procedural_castle','existing_mesh_edit']
    rationale:list[str]
    limitations:list[str]
    requirements:list[Requirement]
    bounds_m:list[float]=Field(min_length=3,max_length=3)
    material_colors:dict
    quality:str
    source_style_hash:str
    fallback:str


def plan(value,item):
    from engines.quality import fingerprint
    text=item.get('resolved_prompt') or item['prompt'];interpreted=item.get('prompt_interpretation',{})
    chunks=interpreted.get('chunks') or [{}];subject=chunks[0].get('interpretation',{}).get('requested_subject_en') or text
    refs=list(dict.fromkeys(item.get('intent_reference_ids',[])+item.get('reference_ids',[])+item.get('style_reference_ids',[])))
    images=[studio.scoped_artifact(r,value['project_id']) for r in refs]
    role=interpreted.get('reference_role') or ('style' if item.get('style_reference_ids') else 'source' if item.get('reference_ids') else 'none')
    castle=bool(re.search(r'\bcastle\b|lâu\s+đài',subject,re.I)) and not re.search(r'not (?:a )?castle|không[^\n,.]{0,20}lâu\s+đài',text,re.I)
    category='architecture' if castle or re.search(r'tower|wall|gate|bridge|tháp|tường|cổng',text,re.I) else 'organic' if re.search(r'creature|hero|boss|skull|nhân vật',text,re.I) else 'mixed'
    rationale=[];limitations=[];route='image_to_3d'
    # This first procedural profile has a deliberately narrow capability contract.
    # Shape references, explicit engines and unsupported exact forms always win.
    incompatible=len(text)>350 or bool(re.search(r'photoreal|scan|exact(?:ly)?\s+(?:match|replica)|ruin|floating|dome|destroyed|moat|drawbridge|triangular|AI[- ]?(?:generated )?textur|chính xác như ảnh|(?:no|without) towers|không[^\n,.]{0,30}tháp|sci.fi|futuristic|ice castle|glass castle|(?:4k|8k|4096|8192)[^\n,.]{0,25}textur|textur[^\n,.]{0,25}(?:4k|8k|4096|8192)',text,re.I))
    towers=re.search(r'\b(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|hai|ba|bốn|sáu)\s*(?:corner\s+)?(?:towers?|tháp)\b',text,re.I)
    words=dict(zero=0,one=1,two=2,three=3,four=4,five=5,six=6,seven=7,eight=8,nine=9,ten=10,hai=2,ba=3,bốn=4,sáu=6)
    count=(int(towers[1]) if towers[1].isdigit() else words[towers[1].lower()]) if towers else 4
    from .local_tools import executable
    if castle and role!='source' and item['preferred_engine']=='auto' and not incompatible and count==4 and executable('blender'):
        route='procedural_castle';rationale=['Whole-castle image inference failed structural identity in recent local tests.',
            'This authored assembly profile can directly validate keep, four corner towers, gate opening and joined curtain walls.',
            'Style reference supplies appearance only; it is never reconstructed as the castle.']
        limitations=['Authored parametric architecture, not AI-sculpted ornamentation or exact reference reconstruction.',
            'Procedural PBR textures are authored; artistic quality and Meshy parity are not established.',
            'No AI texture-equivalence claim. LOD silhouette loss and target-game performance still require evaluation.']
    else:rationale=['Preserve explicit shape/engine constraints or use image route for an unsupported procedural profile.']
    project=value['style_snapshot'];bible=project.get('art_bible') or {};palette=bible.get('palette') or {}
    if not isinstance(palette,dict):palette={}
    colors=dict(stone=palette.get('limestone','#b8b3a6'),wood=palette.get('oak','#69442e'),roof=palette.get('slate','#344458'),metal=palette.get('bronze','#99704a'))
    req=[Requirement(id='subject',value=subject,provenance='explicit',source='Original request / inferred translation',hard_gate=True)]
    for key in ('target_width_m','target_depth_m','target_height_m'):
        provenance=item.get('spec_provenance',{}).get(key,{})
        req.append(Requirement(id=key,value=item[key],provenance=provenance.get('kind','defaulted'),source=provenance.get('source','Provisional resolved bounds'),hard_gate=provenance.get('kind')=='explicit'))
    if role=='style' and interpreted.get('chunks'):
        appearance=chunks[0].get('interpretation',{}).get('appearance',{})
        # Never override project/user palette with inferred reference appearance.
        if not palette and any('blue' in c.lower() for c in appearance.get('colors',[])):colors['roof']='#263b59'
    roof=re.search(r'(?:roof|mái)[^\n,.]{0,50}(navy|blue|red|green|đen|đỏ|xanh dương)',text,re.I)
    if roof:
        colors['roof']={'navy':'#263b59','blue':'#285a86','red':'#873b32','green':'#34634d','đen':'#22252a','đỏ':'#873b32','xanh dương':'#285a86'}[roof[1].lower()]
        req.append(Requirement(id='roof_color',value=colors['roof'],provenance='explicit',source=roof[0],hard_gate=True))
    for key,color in colors.items():
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Unsupported project color; expected #RRGGBB: '+key)
    if route=='procedural_castle':
        for name,number in [('keep',1),('corner_tower',4),('gate',1),('curtain_wall',5)]:
            req.append(Requirement(id=name,value=number,provenance='explicit' if name=='corner_tower' and towers else 'defaulted',source='Four-corner castle assembly profile v1; not a claimed user-specified detail',hard_gate=True))
    return AssetGenerationSpec(asset_id=item['asset_id'],project_id=value['project_id'],original_prompt=item['prompt'],original_prompt_sha256=hashlib.sha256(item['prompt'].encode()).hexdigest(),
        reference_hashes=[dict(artifact_id=a['id'],sha256=a['sha256']) for a in images],subject=subject,category=category,reference_role=role,route=route,rationale=rationale,limitations=limitations,
        requirements=req,bounds_m=[item['target_width_m'],item['target_depth_m'],item['target_height_m']],material_colors=colors,quality=item['quality'],source_style_hash=fingerprint(project),
        fallback='No automatic engine/quality substitution. Retain outputs and report unsupported mandatory constraints.').model_dump()


def admit(value,item,auto):
    if not item.get('planner_version'):return None  # Existing batches keep their old route.
    if not item.get('asset_generation_spec'):
        item['asset_generation_spec']=plan(value,item)
        studio.patch_resolved_specification(item['asset_id'],dict(asset_generation_spec=item['asset_generation_spec']))
    spec=AssetGenerationSpec.model_validate(item['asset_generation_spec']).model_dump()
    if spec['original_prompt_sha256']!=hashlib.sha256(item['prompt'].encode()).hexdigest():raise ValueError('Immutable strategy source changed')
    if spec['route']=='procedural_castle':auto['engines']=['blender_procedural']
    return spec
