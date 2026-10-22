"""Versioned prompt deltas over the existing shared batch coordinator and export transaction."""
import copy
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from . import store,studio,jobs,batch,automation
from .manifest import ManifestItem
router=APIRouter(prefix='/api/production')

class RevisionInput(BaseModel):
    parent_artifact_id:str
    prompt:str=Field(min_length=1,max_length=10000)
    method:Literal['auto','modify_existing','regenerate']='auto'
    priority:Literal['next','normal']='next'
    request_id:str=Field(min_length=8,max_length=100)
    cancel_current:bool=False
    auto_replace:bool=False


@router.get('/assets/{asset_id}/animation-clips')
def animation_clips(asset_id:str,artifact_id:str):
    from engines.animation_clip import clips
    model=studio.asset(asset_id);record=studio.scoped_artifact(artifact_id,model['project_id'],asset_id)
    path=store.safe_path(record['relative_path'])
    if path.suffix.lower()!='.glb':raise HTTPException(400,'Choose a self-contained GLB')
    if store.digest(path)!=record['sha256']:raise HTTPException(409,'Source checksum changed')
    try:return clips(path)
    except ValueError as exc:raise HTTPException(409,str(exc))


def origin_config(record):
    seen=set();current=record
    while current and current['id'] not in seen:
        seen.add(current['id']);identifier=current['metadata'].get('job_id')
        if identifier:
            try:
                job=jobs.get(identifier)
                if job['payload'].get('effective_config'):return job,copy.deepcopy(job['payload']['effective_config'])
            except KeyError:pass
        parent=current['metadata'].get('parent_id')
        try:current=store.get_artifact(parent) if parent else None
        except KeyError:current=None
    return None,None


def revision_plan(asset_id,body):
    model=studio.asset(asset_id);parent=studio.scoped_artifact(body.parent_artifact_id,model['project_id'],asset_id)
    if parent['role']!='candidate':raise HTTPException(400,'Choose a real model candidate as the parent version')
    if store.digest(store.safe_path(parent['relative_path']))!=parent['sha256']:raise HTTPException(409,'Parent model changed; no revision was queued')
    from .local_tools import executable
    color_edit=re.fullmatch(r'\s*(?:(?:make|set|change|recolor)\s+)?(?:the\s+)?roof(?:\s+(?:material|color))?(?:\s+to)?\s+(navy|blue|red|green|#[0-9a-fA-F]{6})\s*[.!]?\s*',body.prompt,re.I)
    if not color_edit:color_edit=re.fullmatch(r'\s*(?:đổi|làm)(?:\s+màu)?\s+mái(?:\s+(?:thành|sang|màu))?\s+(navy|xanh navy|xanh dương|đỏ|xanh lá|#[0-9a-fA-F]{6})\s*[.!]?\s*',body.prompt,re.I)
    if color_edit and body.method!='regenerate' and executable('blender'):
        from .inspection import glb_document
        doc=glb_document(store.safe_path(parent['relative_path']));roof=set();other=set()
        for node in doc.get('nodes',[]):
            if 'mesh' not in node:continue
            slots={p['material'] for p in doc['meshes'][node['mesh']]['primitives'] if 'material' in p}
            (roof if node.get('name','').startswith('roof_') or node.get('name','').endswith('_roof') else other).update(slots)
        if roof and not roof&other and not doc.get('skins') and not doc.get('animations'):
            color={'navy':'#263b59','blue':'#285a86','red':'#873b32','green':'#34634d','xanh navy':'#263b59','xanh dương':'#285a86','đỏ':'#873b32','xanh lá':'#34634d'}.get(color_edit[1].lower(),color_edit[1])
            names=[doc['materials'][i].get('name') for i in sorted(roof)]
            if all(names):return dict(method='blender_material',earliest_stage='materials',target_height_m=None,material_edit=dict(material_names=names,color_hex=color),
                refinement_goal='Change only named roof basecolor; preserve geometry, topology, UV and other materials',
                explanation='Direct named roof material edit in Blender. No concept or image-to-3D inference. Geometry invariance and export reimport are checked.',
                parent_artifact_id=parent['id'],parent_sha256=parent['sha256'],capabilities=dict(direct_material_edit=True,direct_mesh_edit=False),artistic_evaluation='not_available')
    clip_match=re.fullmatch(r'\s*(?:set\s+)?clip\s+(\d+)\s+speed\s+(?:to\s+)?(\d+(?:\.\d+)?)x\s*[.!]?\s*',body.prompt,re.I)
    if clip_match and body.method!='regenerate':
        from engines.animation_clip import clips
        try:source=clips(store.safe_path(parent['relative_path']))
        except ValueError as exc:raise HTTPException(409,str(exc))
        index=int(clip_match[1])-1;speed=float(clip_match[2])
        if not 0<=index<len(source['clips']):raise HTTPException(400,'Choose an existing clip number from the model viewer; no new animation is synthesized')
        if not source['clips'][index]['retime_supported']:raise HTTPException(409,source['clips'][index]['retime_limitation'])
        if not .25<=speed<=4:raise HTTPException(400,'Clip speed must be between 0.25x and 4x')
        if not source['skins'] or not executable('blender'):raise HTTPException(409,'This verified retiming route requires a skinned GLB and local Blender')
        return dict(method='animation_retime',earliest_stage='animation',clip_index=index,clip_speed=speed,source_clip=source['clips'][index],target_height_m=None,
                    refinement_goal='Retime the selected existing clip; preserve geometry, skinning, materials, all other clips and original constraints',
                    explanation='Change only selected clip key times, then compare actual deformed vertices in headless Blender. This does not generate new motion or rig a static model.',
                    parent_artifact_id=parent['id'],parent_sha256=parent['sha256'],capabilities=dict(direct_mesh_edit=False,direct_material_edit=False,uniform_blender_scale=False,animation_retime=True),artistic_evaluation='not_available')
    match=re.fullmatch(r'\s*(?:please\s+)?uniformly\s+(?:scale|resize)(?:\s+the\s+(?:asset|model))?\s+(?:to\s+)?(?:a\s+)?height\s*(?:of|to|=|:)?\s*(\d+(?:\.\d+)?)\s*(m|cm)\s*[.!]?\s*',body.prompt,re.I)
    height=float(match[1])*(.01 if match[2].lower()=='cm' else 1) if match else None
    supported=bool(height and 0<height<=1000 and executable('blender'))
    method='blender_transform' if supported and body.method!='regenerate' else 'regenerate'
    if method=='regenerate' and (origin_config(parent)[1] or {}).get('engine_id')=='blender_procedural':
        raise HTTPException(409,'This named castle profile currently supports roof recoloring (Make roof navy / red / #RRGGBB) and uniform scaling. Structural regeneration of this assembly is not verified; no unrelated image-to-3D engine was substituted.')
    if body.method=='modify_existing' and not supported:raise HTTPException(400,'Verified edits: Uniformly scale to height 18 m; or Set clip 1 speed to 0.75x for an actually animated/skinned GLB. Other mesh/material/motion editing is unavailable.')
    generic=bool(re.fullmatch(r'\s*(?:make (?:it )?(?:better|prettier)|improve(?: it)?|\u0111\u1eb9p h\u01a1n|l\u00e0m \u0111\u1eb9p h\u01a1n)\s*[.!]?\s*',body.prompt,re.I))
    return dict(method=method,refinement_goal='Balanced silhouette readability, construction coherence and material clarity; preserve explicit style and dimensions' if generic else 'Explicit user revision instructions',earliest_stage='blender' if method=='blender_transform' else 'concept',target_height_m=height if method=='blender_transform' else None,
        explanation='Uniform scaling through the installed Blender pipeline; original geometry and textures remain available.' if method=='blender_transform' else 'Direct prompt-based material/mesh editing is unavailable. Regenerate creates a new text-conditioned concept and 3D candidate. Original images are retained as provenance; SDXL here does not provide image-to-image constraint editing.',
        parent_artifact_id=parent['id'],parent_sha256=parent['sha256'],capabilities=dict(direct_mesh_edit=False,direct_material_edit=False,uniform_blender_scale=supported),artistic_evaluation='not_available')


@router.post('/assets/{asset_id}/revisions/plan')
def plan(asset_id:str,body:RevisionInput):return revision_plan(asset_id,body)


@router.post('/assets/{asset_id}/revisions',status_code=201)
def create(asset_id:str,body:RevisionInput):
    from .export_profiles import resolve_project_settings,export_history
    from engines.quality import fingerprint
    with batch.LOCK:
        key='revision:'+body.request_id;digest=studio.request_digest(body)
        with store.connect() as db:
            prior=studio.cached(db,key,digest)
            if prior:return prior
        model=studio.asset(asset_id);parent=studio.scoped_artifact(body.parent_artifact_id,model['project_id'],asset_id);planned=revision_plan(asset_id,body)
        active=[j for j in jobs.listing() if j['payload'].get('asset_id')==asset_id and j['status'] not in jobs.TERMINAL]
        if active and not body.cancel_current:raise HTTPException(409,'This asset has unfinished stages. Pause does not cancel them. Wait, or explicitly choose Cancel Current & Replace.')
        if active:
            for j in active:jobs.transition(j['id'],'CANCELLED','Explicit Cancel Current & Replace for revision')
            for g in __import__('apps.api.production',fromlist=['batches']).batches():
                if any(i['asset_id']==asset_id for i in g['items']):
                    for i in g['items']:
                        if i['asset_id']==asset_id:i['skipped']=True
                    batch.save(g)
        parent_job,config=origin_config(parent);quality=(config or {}).get('quality') or model.get('settings',{}).get('quality','Maximum')
        project=studio.project(model['project_id']);base_group=None
        if parent_job and parent_job['payload'].get('batch_id'):
            base_group=batch.batch(parent_job['payload']['batch_id'])
        if base_group and base_group.get('revision_of'):base_group=batch.batch(base_group['revision_of'])
        style=copy.deepcopy(base_group['style_snapshot'] if base_group else model.get('resolved_specification',{}).get('project_style_snapshot') or project)
        settings=copy.deepcopy(base_group.get('automation',{}).get('export_settings') if base_group else None) or resolve_project_settings(model['project_id'])
        original=model.get('original_prompt',model.get('prompt',''));source_spec=copy.deepcopy(model.get('resolved_specification',{}));dims=source_spec.get('dimensions',{})
        from .inspection import inspect_glb
        actual=parent['metadata'].get('dimensions_xyz_m') or inspect_glb(store.safe_path(parent['relative_path']))['dimensions_xyz_m']
        if not dims:
            dims=dict(target_width_m=actual[0],target_height_m=actual[1],target_depth_m=actual[2])
            source_spec['dimension_provenance']=dict(kind='inferred',source='Measured selected parent GLB bounds',value=dims)
        if parent_revision_spec:=next((r.get('effective_specification') for r in model.get('revisions',[]) if r.get('artifact_id')==parent['id']),None):
            source_spec=copy.deepcopy(parent_revision_spec);dims=source_spec.get('dimensions',dims)
        # Preserve the selected parent's effective prompt, not unrelated later experiments.
        parent_revision=next((r for r in model.get('revisions',[]) if r.get('artifact_id')==parent['id']),None)
        inherited_prompt=parent_revision['effective_prompt'] if parent_revision else original
        effective_prompt=inherited_prompt+'\n\nRevision instructions (preserve all other explicit constraints):\n'+body.prompt+'\nRefinement goal: '+planned['refinement_goal']
        rev_id=uuid.uuid4().hex;group_id=uuid.uuid4().hex
        if planned['method']=='blender_transform':
            bounds=actual;height=planned['target_height_m']
            if bounds and bounds[1]>0:dims=dict(target_width_m=bounds[0]*height/bounds[1],target_height_m=height,target_depth_m=bounds[2]*height/bounds[1])
            source_spec.setdefault('provenance',{})['target_height_m']=dict(kind='explicit',source='Revision uniform-scale instruction',value=height)
            if config:
                config['blender']['height_m']=height;config['revision']=dict(id=rev_id,parent=parent['id'],method='explicit_uniform_scale',parent_config_hash=parent_job['payload'].get('effective_config_hash'))
        if planned['method']=='animation_retime':
            config=dict(schema_version=1,quality=quality,operation='animation_retime',clip_index=planned['clip_index'],speed=planned['clip_speed'],source_sha256=parent['sha256'],qa='headless_blender_deformation_comparison',preserve_original_binary=True)
        if planned['method']=='blender_material' and config:config['revision']=dict(id=rev_id,parent=parent['id'],method='named_material_edit',material_edit=planned['material_edit'])
        candidate_count=1 if planned['method'] in ('blender_transform','blender_material','animation_retime') else (config or {}).get('candidate_count',1)
        row=ManifestItem(asset_id=asset_id,name=model['name'],prompt=effective_prompt,source_asset_id=model.get('settings',{}).get('source_asset_id') or asset_id,
            category=model.get('category') or 'Prop',quality=quality,candidates=candidate_count,preferred_engine=(config or {}).get('engine_id') if (config or {}).get('engine_id') in ('triposg','trellis2_community') else 'auto',target_height_m=dims.get('target_height_m'),target_width_m=dims.get('target_width_m'),target_depth_m=dims.get('target_depth_m')).model_dump()
        row['seeds']=list((config or {}).get('seeds') or [42+n for n in range(candidate_count)])[:candidate_count]
        row.update(attempt=0,started=True,version=1,quality_lock=quality=='Maximum',priority=100 if body.priority=='next' else 0,revision_id=rev_id)
        engines=['blender_animation'] if planned['method']=='animation_retime' else [(config or {}).get('engine_id','trellis2_community')] if planned['method'] in ('blender_transform','blender_material') else automation.plan_engines(row)
        if planned['method'] in ('blender_transform','blender_material') and source_spec.get('asset_generation_spec',{}).get('route')=='procedural_castle':
            row['asset_generation_spec']=copy.deepcopy(source_spec['asset_generation_spec']);row['structural_parent_spec_hash']=source_spec.get('structural_parent_spec_hash') or fingerprint(row['asset_generation_spec'])
            if planned['method']=='blender_transform':row['asset_generation_spec']['bounds_m']=[dims['target_width_m'],dims['target_depth_m'],dims['target_height_m']]
            if planned['method']=='blender_material':
                color=planned['material_edit']['color_hex'];row['asset_generation_spec']['material_colors']['roof']=color
                row['asset_generation_spec']['requirements']=[r for r in row['asset_generation_spec']['requirements'] if r['id']!='roof_color']+[dict(id='roof_color',value=color,provenance='explicit',source=body.prompt,hard_gate=True)]
            source_spec['asset_generation_spec']=copy.deepcopy(row['asset_generation_spec']);source_spec['structural_parent_spec_hash']=row['structural_parent_spec_hash']
        row['automation']=dict(enabled=True,engines=engines,attempt=0,status='queued',stage='pending',checkpoints={},human_approved=False)
        workflow=automation.project_workflow(model['project_id']);workflow['mode']='auto'
        value=dict(id=group_id,project_id=model['project_id'],name=model['name'],mode={'Maximum':'Maximum Quality Batch','Balanced':'Quality Batch','Fast':'Fast Batch'}[quality],quality_lock=quality=='Maximum',master_prompt=effective_prompt,style_snapshot=style,items=[row],warnings=[],paused=False,created_at=store.now(),updated_at=store.now(),revision_id=rev_id,revision_of=base_group['id'] if base_group else None,
            automation=dict(settings=workflow,export_settings=settings,mode='auto',started_at=store.now()))
        record=dict(id=rev_id,number=len(model.get('revisions',[]))+2,parent_artifact_id=parent['id'],parent_sha256=parent['sha256'],prompt=body.prompt,effective_prompt=effective_prompt,original_prompt_sha256=hashlib.sha256(original.encode()).hexdigest(),plan=planned,group_id=group_id,state='queued',created_at=store.now(),job_ids=[],quality=quality,effective_config=config,effective_config_hash=fingerprint(config) if config else None,effective_specification=source_spec|dict(dimensions=dims),project_style_snapshot=style,reference_ids=list(model.get('reference_ids',[])),export_settings=settings,auto_replace=body.auto_replace,previous_delivery_ids=[e['id'] for e in export_history(asset_id) if e.get('delivery_scope')!='staged'])
        model.setdefault('original_prompt',original);model.setdefault('original_prompt_sha256',record['original_prompt_sha256']);model.setdefault('revisions',[]).append(record)
        response=dict(revision_id=rev_id,group_id=base_group['id'] if base_group else group_id,execution_group_id=group_id,asset_id=asset_id,plan=planned)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');db.execute('INSERT INTO batches VALUES (?,?,?)',(group_id,model['project_id'],json.dumps(value)))
            db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(model),asset_id));db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(key,digest,json.dumps(response)))
        automation.advance(group_id)
        return response


def execution_context(item):
    if not item.get('revision_id'):return None
    model=studio.asset(item['asset_id']);return next((r for r in model.get('revisions',[]) if r['id']==item['revision_id']),None)


def update_execution(asset_id,rev_id,fields):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM assets WHERE id=?',(asset_id,)).fetchone();model=json.loads(row['payload']);revision=next(r for r in model['revisions'] if r['id']==rev_id);revision.update(fields)
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(model),asset_id))


@router.post('/assets/{asset_id}/versions/{artifact_id}/publish')
def publish(asset_id:str,artifact_id:str):
    from .export_profiles import export_asset
    from .statuses import approved,policy
    model=studio.asset(asset_id);source=studio.scoped_artifact(artifact_id,model['project_id'],asset_id)
    if policy(model,automation.project_workflow(model['project_id']))=='manual_approval' and not approved(model,artifact_id):raise HTTPException(409,'Manual Approval policy requires an explicit artistic decision before game publication.')
    revision=next((r for r in model.get('revisions',[]) if r.get('artifact_id')==artifact_id),None)
    if revision and revision.get('state') not in ('staged','published'):raise HTTPException(409,'Wait for technical QA and staged export before publishing this version')
    result=export_asset(model['project_id'],asset_id,artifact_id,revision.get('export_settings') if revision else None,allow_publish=True)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');current=json.loads(db.execute('SELECT payload FROM assets WHERE id=?',(asset_id,)).fetchone()['payload'])
        current['published_artifact_id']=artifact_id;current.setdefault('publication_history',[]).append(dict(artifact_id=artifact_id,export_id=result['id'],at=store.now(),action='use_this_version',sha256=source['sha256']))
        if revision:next(r for r in current['revisions'] if r['id']==revision['id']).update(state='published',published_export_id=result['id'])
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(current),asset_id))
    return result
