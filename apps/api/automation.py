"""Durable unattended orchestration over the existing Single Asset stage implementations."""
import copy
import hashlib
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from . import store,jobs,studio,intermediates
from engines.adapters import SHAPE_ENGINES
from .quality_repair import RepairBudget

# Concepts generated and compared per asset before image-to-3D when the item does not set its own count.
CONCEPT_CANDIDATES={'Maximum':3,'Balanced':2,'Fast':1}

router=APIRouter(prefix='/api/automation')


class Checkpoints(BaseModel):
    concept:bool=False
    candidate:bool=False
    export:bool=False


class Workflow(BaseModel):
    mode:Literal['auto','assisted','expert']='auto'
    checkpoints:Checkpoints=Field(default_factory=Checkpoints)
    retry_limit:int=Field(default=1,ge=0,le=3)
    disk_reserve_gb:float=Field(default=10,ge=1,le=1000)
    max_active_assets:int=Field(default=2,ge=1,le=4)
    auto_resume:bool=False
    review_policy:Literal['auto','review_flagged','manual_approval']='auto'
    prompt_interpretation:bool=True
    architecture_strategy:Literal['ai_detail','procedural_blockout']='ai_detail'
    repair_budget:RepairBudget=Field(default_factory=RepairBudget)


@router.get('/projects/{project_id}')
def project_workflow(project_id:str):return Workflow.model_validate(studio.project(project_id).get('workflow_settings',{})).model_dump()


def write_project_workflow(db,project_id,body):
    row=db.execute('SELECT payload FROM projects WHERE id=?',(project_id,)).fetchone()
    if not row:raise HTTPException(404,'Game project does not exist')
    value=json.loads(row['payload']);value['workflow_settings']=body.model_dump()
    db.execute('UPDATE projects SET payload=? WHERE id=?',(json.dumps(value),project_id))
    for row in db.execute('SELECT id,payload FROM batches WHERE project_id=?',(project_id,)).fetchall():
        saved=json.loads(row['payload'])
        if saved.get('automation'):
            saved['automation']['settings']['auto_resume']=body.auto_resume
            db.execute('UPDATE batches SET payload=? WHERE id=?',(json.dumps(saved),row['id']))
    return body.model_dump()


@router.post('/projects/{project_id}')
def save_project_workflow(project_id:str,body:Workflow):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        return write_project_workflow(db,project_id,body)


@router.post('/projects/{project_id}/patch')
def patch_project_workflow(project_id:str,body:dict):
    if set(body)-set(Workflow.model_fields):raise HTTPException(422,'Unsupported workflow setting')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM projects WHERE id=?',(project_id,)).fetchone()
        if not row:raise HTTPException(404,'Game project does not exist')
        current=Workflow.model_validate(json.loads(row['payload']).get('workflow_settings',{})).model_dump()
        patch=body.copy()
        for key,schema in (('checkpoints',Checkpoints),('repair_budget',RepairBudget)):
            if key in patch:
                if not isinstance(patch[key],dict) or set(patch[key])-set(schema.model_fields):raise HTTPException(422,'Unsupported '+key+' setting')
                patch[key]=current[key]|patch[key]
        try:validated=Workflow.model_validate(current|patch)
        except ValueError:raise HTTPException(422,'Invalid workflow value; no settings were saved')
        return write_project_workflow(db,project_id,validated)


def resolve_specs(item,project,snapshot):
    """Provisional scale is separate from game constraints and original-source requirements."""
    provenance=copy.deepcopy(item.get('spec_provenance',{}));source=item.get('source_asset_id','');text=item['prompt']
    from .manifest import heading_prompts
    blocks=heading_prompts(text)
    if len(blocks)==1:
        for key in ('target_width_m','target_depth_m','target_height_m'):
            if item.get(key) is None and blocks[0].get(key) is not None:item[key]=blocks[0][key]
    for label,key in (('width','target_width_m'),('height','target_height_m'),('depth','target_depth_m')):
        match=re.search(r'\b'+label+r'\s*(?:(?:is|of|to)\s+|[:=]\s*)?(\d+(?:\.\d+)?)\s*(cm|m)\b',text,re.I)
        if match and (item.get(key) is None or provenance.get(key,{}).get('kind') in ('inherited','inferred','defaulted')):
            item[key]=float(match[1])*(.01 if match[2].lower()=='cm' else 1)
            provenance[key]=dict(kind='explicit',source='Exact '+label+' expression in original prompt',value=item[key])
    explicit_category=bool(item.get('category'))
    category=item.get('category') or ('Building' if source.startswith(('BLD_','WALL_','FUT_SHRINE','FUT_WALL')) or re.search(r'\b(tower|castle|house|gate|shrine)\b',item['name']+' '+text,re.I) else 'Environment' if source.startswith(('BIO_','FUT_ENV')) else 'Boss' if source.startswith('BOSS_') else 'Character' if source.startswith(('GEN_','UNIT_','ENM_')) else 'Prop')
    item['category']=category
    defaults={'Building':(8,8,10),'Environment':(5,5,4),'Boss':(4,4,6),'Character':(1,1,2),'Prop':(2,2,2)}[category if category in ('Building','Environment','Boss','Character','Prop') else 'Prop']
    family=item.get('asset_family') or '_'.join(source.split('_')[:2])
    bible=project.get('art_bible',{});families=bible.get('asset_families',{}) if isinstance(bible,dict) else {}
    inherited=families.get(family,{}) if isinstance(families,dict) else {}
    related=next((a for a in snapshot['assets'] if a.get('master_artifact_id') and a['id']!=item['asset_id'] and a.get('settings',{}).get('source_asset_id','').startswith(family+'_')),None) if family else None
    master=next((a for a in snapshot['artifacts'] if related and a['id']==related['master_artifact_id']),None)
    measured=master.get('metadata',{}).get('dimensions_xyz_m') if master else None
    for i,key in enumerate(('target_width_m','target_depth_m','target_height_m')):
        if item.get(key) is not None:provenance.setdefault(key,dict(kind='explicit',source='source field or user override',value=item[key]));continue
        inherited_value=inherited.get(key) if isinstance(inherited,dict) else None
        # The project-wide height is a default for every type (measured: it made a hero, his sword and shield 10 m tall);
        # the type rule (person 1.8 m, barrel 0.6 m) replaces it. A family's own Art Bible size stays authoritative.
        project_default=key=='target_height_m' and inherited_value is None and isinstance(project.get('target_height_m'),(int,float)) and 0<project.get('target_height_m')<=1000
        if project_default:value,kind,origin=project['target_height_m'],'defaulted','Project default height; replaced by the asset type rule when one matches'
        elif isinstance(inherited_value,(int,float)) and 0<inherited_value<=1000:value,kind,origin=inherited_value,'inherited','Project Art Bible / '+family
        elif measured and len(measured)==3:value,kind,origin=measured[(0,2,1)[i]],'inferred','Approved related master '+master['id']
        else:
            semantic=item.get('semantic_metadata',{});suggestions=[r.get('suggestions',{}).get(('width_m','depth_m','height_m')[i]) for r in semantic.get('chunks',[]) if r.get('suggestions',{}).get(('width_m','depth_m','height_m')[i]) is not None] if semantic.get('source_sha256')==item.get('source_sha256') else []
            if suggestions and len(set(suggestions))==1:value,kind,origin=suggestions[0],'inferred','Validated local semantic suggestions; not artist approved'
            else:value,kind,origin=defaults[i],'defaulted','Conservative provisional '+category+' scale; gameplay dimensions unverified'
        item[key]=float(value);provenance[key]=dict(kind=kind,source=origin,value=float(value),provisional=True)
    item['spec_provenance']=provenance
    # Type-based provisional size (castle, dragon, barrel...) instead of a coarse category default; refined after prompt analysis.
    from .size_rules import apply as apply_size_rule
    from engines.concept_prompt import subject_anchor
    apply_size_rule(item,item['name']+' '+subject_anchor(text));provenance=item['spec_provenance']
    provenance.setdefault('category',dict(kind='explicit' if explicit_category else 'inferred',source='Manifest category' if explicit_category else 'Deterministic name / prompt / source-ID rule',value=category))
    for key,value in (('units',project.get('units','m')),('palette',project.get('palette',[])),('material_language',project.get('material_language','')),('default_style',project.get('default_style',''))):
        provenance.setdefault(key,dict(kind='inherited' if value else 'defaulted',source='Project Art Bible / settings' if value else 'Unspecified; no invented style requirement',value=value))
    item['spec_provenance']=provenance
    return item


def plan_engines(item,source=None):
    from engines.adapters import ADAPTERS
    # Several engines only when the user picked them; Auto is the current default engine (TRELLIS.2) alone.
    explicit=bool(item.get('engines')) or item['preferred_engine']!='auto'
    names=list(item.get('engines') or []) or ([item['preferred_engine']] if item['preferred_engine']!='auto' else ['trellis2_community'])
    # Shape engines cut the subject out themselves (local u2net) when the image has no alpha.
    compatible=[name for name in names if ADAPTERS[name].installed]
    if item['quality']!='Maximum' and not explicit:compatible=compatible[:1]
    return compatible


def start(identifier,selected_ids=None,workflow=None,dry_run=False,request_id=None,regenerate_completed=False,allow_questions=False):
    from . import batch
    from .export_profiles import resolve_project_settings
    with batch.LOCK:
        value=batch.batch(identifier);settings=Workflow.model_validate(workflow or project_workflow(value['project_id'])).model_dump()
        if settings['mode']=='expert':settings['mode']='auto'  # this endpoint is an explicit automatic action
        ids=set(selected_ids if selected_ids is not None else [i['asset_id'] for i in value['items']])
        if ids-{i['asset_id'] for i in value['items']}:raise HTTPException(400,'Asset selection is outside this batch')
        digest,reused=batch.prepare_generation(value,ids,request_id,regenerate_completed,dry_run)
        if reused:return batch.detail(value)
        snapshot=studio.studio(value['project_id']);project=studio.project(value['project_id'])
        for item in value['items']:
            if item['asset_id'] not in ids:continue
            item['allow_questions']=allow_questions  # opt-in per explicit Generate; off means Auto decides
            resolve_specs(item,project,snapshot)
            model=studio.asset(item['asset_id'])
            if not any(j['payload'].get('asset_id')==item['asset_id'] and j['payload'].get('batch_id')==identifier and j['payload'].get('batch_attempt',0)==item['attempt'] for j in snapshot['jobs']):item.setdefault('planner_version',1)
            model.setdefault('original_prompt',item['prompt']);model.setdefault('original_prompt_sha256',hashlib.sha256(model['original_prompt'].encode()).hexdigest())
            if not item['prompt'].strip() and item['name'].strip() and not re.fullmatch(r'(?:untitled(?: asset)?|empty(?: entry)?|asset(?: \d+)?|unknown)',item['name'].strip(),re.I):
                item['resolved_prompt']=item['name'].strip();item['spec_provenance']['generation_prompt']=dict(kind='inferred',source='Original asset name; no original prompt text was replaced',value=item['resolved_prompt'])
            model['resolved_specification']=dict(generation_prompt=item.get('resolved_prompt') or item['prompt'],category=item.get('category'),dimensions={k:item[k] for k in ('target_width_m','target_depth_m','target_height_m')},provenance=item['spec_provenance'],quality=item['quality'],source_prompt_sha256=hashlib.sha256(item['prompt'].encode()).hexdigest(),project_style_snapshot=value['style_snapshot'],artistic_evaluation='not_available')
            studio.save_asset(model)
            from engines.intent_adapter import available
            if settings.get('prompt_interpretation',True) and available() and not item.get('processing_source') and not item.get('revision_id'):
                item.setdefault('interpret_prompt',True)
                item.setdefault('intent_reference_ids',list(dict.fromkeys(item.get('style_reference_ids',[])+item['reference_ids'])))
                item.setdefault('intent_reference_usage','style' if item.get('style_reference_ids') else 'auto')
                item['reference_ids']=[]
            source=next((a for a in snapshot['artifacts'] if a['id'] in item['reference_ids'] and a['role'] in ('concept','reference')),None)
            pinned=item.get('automation',{}).get('engines') or plan_engines(item,source)
            if item.get('automation',{}).get('attempt',item['attempt'])!=item['attempt']:item.pop('automation',None)
            item.setdefault('automation',dict(status='queued',stage='pending',checkpoints={}))
            item['automation'].update(engines=pinned,enabled=True,attempt=item['attempt'],engine_policy='Pin compatible installed engines at start; textured TRELLIS.2 first based on actual local export evidence; no numeric artistic score',human_approved=False)
            item['selected']=True;item['production_cancelled']=False  # an explicit Generate supersedes an earlier cancel
            if not item.get('skipped'):item['started']=True
        if value.get('production_cancelled'):value['production_cancelled']=any(i.get('production_cancelled') for i in value['items'])
        info=dict(total=len(ids),future=sum(i.get('source_status')=='FUTURE' for i in value['items'] if i['asset_id'] in ids),candidate_jobs=sum(i['candidates']*len(i['automation']['engines']) for i in value['items'] if i['asset_id'] in ids),source_hashes_preserved=True)
        if dry_run:return dict(dry_run=True,plan=info,items=[{k:i.get(k) for k in ('asset_id','source_asset_id','source_status','spec_provenance','automation')} for i in value['items'] if i['asset_id'] in ids])
        prior=value.get('automation',{})
        value['automation']=dict(mode=settings['mode'],settings=settings,export_settings=prior.get('export_settings') or resolve_project_settings(value['project_id']),started_at=prior.get('started_at') or store.now(),plan=info,policy='Automatic technical selection and export; no artistic approval',pause_reason=None)
        value['paused']=False;batch.persist_generation(value,request_id,digest)
    return advance(identifier)


def leaves(stage_jobs):
    replaced={j['payload'].get('retry_of') for j in stage_jobs}
    return [j for j in stage_jobs if j['id'] not in replaced]


def recover_checkpoint(job):
    """Reconcile persisted, hash-validated outputs, never resume diffusion tensors."""
    if job['status']!='BLOCKED' or not any(word in (job.get('error') or '').lower() for word in ('interrupt','server stopped')):return False
    try:
        folder=store.DATA/'jobs'/job['id'];manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        role={'concept':'concept','inference':'candidate','blender':'candidate'}.get(job['payload']['kind'])
        with store.connect() as db:records=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE role=?',(role,))]
        artifact=next(a for a in records if a['metadata'].get('job_id')==job['id'])
        file=store.safe_path(artifact['relative_path'])
        if not manifest or store.digest(file)!=artifact['sha256']:return False
        if job['payload']['kind']=='concept':
            from .inspection import inspect_image
            inspect_image(file)
        else:
            from .inspection import inspect_glb
            inspect_glb(file)
        with store.connect() as db:db.execute("UPDATE jobs SET status='REVIEW_REQUIRED',error=NULL,updated_at=? WHERE id=? AND status='BLOCKED'",(store.now(),job['id']))
        (folder/'recovery.json').write_text(json.dumps(dict(reconciled_at=store.now(),artifact_id=artifact['id'],sha256=artifact['sha256'],mid_inference_resume=False)),encoding='utf-8')
        return True
    except (OSError,ValueError,KeyError,StopIteration):return False


def snapshot_item_state(value,item,all_jobs,artifacts):
    # The post-delivery rig job is a side branch: it never counts as delivery work, a failure or an admission slot.
    current=leaves([j for j in all_jobs if j['payload'].get('batch_id')==value['id'] and j['payload'].get('asset_id')==item['asset_id'] and j['payload'].get('batch_attempt',0)==item['attempt'] and j['payload'].get('kind')!='rig'])
    return current


def advance(identifier):
    from . import batch
    from .inspection import inspect_image
    from .export_profiles import export_asset
    with batch.LOCK:
        value=batch.batch(identifier)
        if not value.get('automation'):return batch.detail(value)
        settings=value['automation']['settings'];snapshot=studio.studio(value['project_id']);all_jobs=snapshot['jobs'];artifacts=snapshot['artifacts']
        for job in all_jobs:
            if job['payload'].get('batch_id')==identifier and recover_checkpoint(job):job['status']='REVIEW_REQUIRED';job['error']=None
        from .production import eligible
        from .engine_health import waiting,RouteWaiting
        active_assets={j['payload'].get('asset_id') for j in all_jobs if j['payload'].get('batch_id')==identifier and j['status'] not in jobs.TERMINAL and j['payload'].get('kind')!='rig' and
            (j['status']!='QUEUED' or eligible(j['payload']) and not waiting(j['payload'],j['id']))}
        reserve=settings['disk_reserve_gb']*1024**3
        roots={store.DATA,store.WORKSPACE}
        destination=value['automation']['export_settings'].get('output_directory')
        if destination:roots.add(Path(destination))
        if any(root.exists() and shutil.disk_usage(root).free<reserve for root in roots):
            value['paused']=True;value['automation']['pause_reason']='Disk reserve reached; free space and Resume. No sources removed.'
        # Each tick admits a bounded window of assets, not 349 heavyweight jobs.
        for item in sorted(value['items'],key=lambda i:-i['priority']):
            auto=item.get('automation',{})
            if not item.get('started') or not auto.get('enabled') or item.get('skipped'):continue
            current=snapshot_item_state(value,item,all_jobs,artifacts)
            if item.get('revision_id'):
                from .revisions import update_execution
                update_execution(item['asset_id'],item['revision_id'],dict(job_ids=[j['id'] for j in current]))
            running=[j for j in current if j['status'] not in jobs.TERMINAL]
            auto['checkpoints']={j['id']:dict(stage=j['payload']['kind'],state=j['status'],updated_at=j['updated_at']) for j in current}
            if running:
                auto.update(status='running' if any(j['status']!='QUEUED' for j in running) else 'queued',stage=running[0].get('progress',{}).get('stage') or running[0]['payload']['kind']);continue
            if auto.get('status')=='exported':
                # Delivered characters/creatures get an experimental rigged copy; never blocks or changes the delivery.
                winner=(auto.get('candidate_selection') or {}).get('artifact_id')
                if winner and not auto.get('rig_job_id'):
                    from . import rigging
                    if rigging.wanted(item,studio.project(value['project_id'])):auto['rig_job_id']=rigging.enqueue(value,item,winner)['id']
                continue
            if auto.get('retry_required'):continue  # Permanent delivery/config errors wait for explicit Retry.
            from .production import global_paused
            if item.get('production_paused') or global_paused():
                auto['status']='paused';continue
            failures=[j for j in current if j['status'] in ('FAILED','BLOCKED','CANCELLED')]
            if failures:
                from .quality_repair import planner,submit_stage_retry
                failed=failures[0];plan=planner.stage(value,item,failed,all_jobs)
                if not value['paused'] and plan['action']=='retry_stage':
                    submit_stage_retry(plan,failed);auto.update(status='queued',stage='Recover '+failed['payload']['kind'],error=None);active_assets.add(item['asset_id'])
                else:
                    # Several models: a model that cannot recover is dropped and recorded; the others still deliver.
                    lost={j['payload'].get('engine') for j in failures if j['payload']['kind']=='inference'}
                    alive=[e for e in auto.get('engines',[]) if e not in lost]
                    if len(auto.get('engines',[]))>1 and alive and all(j['payload']['kind']=='inference' for j in failures):
                        auto['failed_engines']={j['payload'].get('engine'):(j.get('error') or plan['reason'] or 'failed')[:300] for j in failures}
                    else:
                        auto.update(status='failed' if failed['status']=='FAILED' else 'blocked',stage=failed['payload']['kind'],error=plan['reason'])
                        continue
                if not auto.get('failed_engines') or any(j['payload'].get('engine') not in auto['failed_engines'] for j in failures if j['payload']['kind']=='inference'):continue
            expected=len([e for e in auto.get('engines',[]) if e not in (auto.get('failed_engines') or {})])*item['candidates']
            delivery_ready=bool(expected) and sum(j['payload']['kind'] in ('blender','animation_retime') and j['status']=='REVIEW_REQUIRED' for j in current)>=expected
            if value['paused'] and (not delivery_ready or 'Disk reserve' in (value['automation'].get('pause_reason') or '')):
                if auto.get('status') not in ('failed','blocked','exported','needs_review'):auto['status']='paused'
                continue
            if not delivery_ready and len(active_assets)>=settings['max_active_assets'] and item['asset_id'] not in active_assets:continue
            if not (item.get('resolved_prompt') or item['prompt']).strip() and not item['reference_ids']:auto.update(status='blocked',stage='Needs Input',error='Empty prompt');continue
            dependencies=[next((i for i in value['items'] if d in (i['asset_id'],i.get('source_asset_id'),i['name'])),None) for d in item['dependencies']]
            if any(d is None for d in dependencies):auto.update(status='blocked',stage='Needs Input',error='Unknown dependency ID');continue
            if any(d.get('automation',{}).get('status') not in ('exported','needs_review') for d in dependencies):auto.update(status='queued',stage='Waiting for dependency');continue
            try:
                from .clarify import admit as ask_questions
                if ask_questions(value,item,current,auto):
                    if auto['status']!='waiting_for_answers':active_assets.add(item['asset_id'])
                    continue
                from .clarify import settle_kind
                settle_kind(item)
                from .prompt_intent import admit
                if admit(value,item,current,auto):active_assets.add(item['asset_id']);continue
                # 2D items: sprite concepts and cutouts instead of the 3D pipeline.
                from .sprite import admit_batch as admit_sprite
                if admit_sprite(value,item,auto):
                    if auto['status'] not in ('exported','failed'):active_assets.add(item['asset_id'])
                    continue
                from .asset_strategy import admit as plan_strategy
                spec=plan_strategy(value,item,auto)
                if not auto.get('engines'):auto.update(status='blocked',stage='Needs Input',error='No compatible verified local geometry route; configure Settings. No fallback/download.');continue
                from .revisions import execution_context,update_execution
                revision=execution_context(item)
                processing=bool(item.get('processing_source') or revision and revision['plan']['method'] in ('blender_transform','blender_material','blender_water'))
                if revision and revision['plan']['method']=='animation_retime':
                    if not any(j['payload']['kind']=='animation_retime' for j in current):
                        jobs.enqueue(dict(kind='animation_retime',engine='blender_animation',artifact_id=revision['parent_artifact_id'],project_id=value['project_id'],asset_id=item['asset_id'],batch_id=identifier,batch_attempt=item['attempt'],revision_id=revision['id'],clip_index=revision['plan']['clip_index'],speed=revision['plan']['clip_speed'],
                                          effective_config=revision['effective_config'],effective_config_hash=revision['effective_config_hash'],priority=item['priority'],timeout_seconds=180))
                        active_assets.add(item['asset_id']);auto.update(status='queued',stage='Animation retiming and deformation QA');continue
                elif processing:
                    if not any(j['payload']['kind']=='blender' for j in current):
                        processing_source=item.get('processing_source') or dict(artifact_id=revision['parent_artifact_id'],normalize=True)
                        jobs.enqueue(dict(kind='blender',artifact_id=processing_source['artifact_id'],normalize=False if revision and revision['plan']['method'] in ('blender_material','blender_water') else processing_source.get('normalize',False),target_height_m=revision['plan']['target_height_m'] if revision else None,
                            material_edit=revision['plan'].get('material_edit') if revision else None,water=revision['plan'].get('water') if revision else None,
                            export_fbx=bool(value['automation']['export_settings'].get('fbx')),
                            project_id=value['project_id'],asset_id=item['asset_id'],batch_id=identifier,batch_attempt=item['attempt'],revision_id=revision['id'] if revision else None,
                            effective_config=revision.get('effective_config') if revision else None,effective_config_hash=revision.get('effective_config_hash') if revision else None,render=True,resolutions=['mobile'],views=['front','three_quarter','side','back','top','gameplay']))
                        active_assets.add(item['asset_id']);auto.update(status='queued',stage='Blender revision');continue
                elif spec and spec['route']=='procedural_castle':
                    if not any(j['payload']['kind']=='procedural_geometry' for j in current):
                        from .procedural import submit
                        submit(value,item,spec);auto.update(status='queued',stage='Build named castle geometry / Blender');active_assets.add(item['asset_id']);continue
                    for job in current:
                        if job['payload']['kind']=='procedural_geometry':jobs.ensure_blender(job)
                else:
                    prefix=f'{identifier}:{item["asset_id"]}:{item["attempt"]}'
                    source=next((a for a in artifacts if a['id']==auto.get('concept_selection',{}).get('artifact_id')),None)
                    if source is None:
                        choices=[a for a in artifacts if a['role'] in ('concept','reference') and (a['id'] in item['reference_ids'] or a['role']=='concept' and a.get('asset_id')==item['asset_id'] and any(j['id']==a['metadata'].get('job_id') for j in current))]
                        from .concept_guard import filter_choices
                        # Concept tournament: wait until every concept of this attempt has finished before choosing.
                        if any(j['payload']['kind']=='concept' and j['status'] not in jobs.TERMINAL and j['status']!='REVIEW_REQUIRED' for j in current):
                            active_assets.add(item['asset_id']);auto.update(status='queued',stage='concept');continue
                        choices=filter_choices(value,item,current,choices,auto)
                        if choices is None:
                            if auto.get('status') not in ('blocked','failed','cancelled'):active_assets.add(item['asset_id'])
                            continue
                        valid=[]
                        for choice in choices:
                            try:
                                path=store.safe_path(choice['relative_path'])
                                if store.digest(path)!=choice['sha256']:continue
                                measured=inspect_image(path);valid.append((measured['width']*measured['height'],measured['laplacian_variance_proxy'],choice,measured))
                            except (OSError,ValueError):continue
                        if not valid:
                            if any(j['payload']['kind']=='concept' for j in current):auto.update(status='blocked',stage='concept QA',error='No valid concept output');continue
                            # One shared, shape-free style analysis per anchor before the first concepts of any asset.
                            from .style_profile import ensure as ensure_style
                            # An explicit 'palette only' choice uses measured colours alone; no material/rendering profile is added.
                            style_state='none' if item.get('intent_reference_scope')=='palette_only' else ensure_style(value['project_id'],studio.project(value['project_id']),item.get('style_reference_ids',[]),item.get('priority',0))[0]
                            if style_state=='pending':
                                auto.update(status='queued',stage='Analyze style reference (materials, colours; no shape)');active_assets.add(item['asset_id']);continue
                            # Rig-ready characters are drawn empty-handed; each held weapon/shield becomes its own batch item.
                            from .held_items import ensure_companions,concept_conditioning
                            ensure_companions(value,item,studio.project(value['project_id']),lambda:studio.studio(value['project_id']))
                            hand_directives,hand_negatives=concept_conditioning(item)
                            from .size_rules import aspect as size_aspect
                            concept_count=item.get('concept_candidates') or CONCEPT_CANDIDATES[item['quality']]
                            for index in range(concept_count):
                                studio.concept(studio.ConceptInput(asset_id=item['asset_id'],request_id=prefix+':concept'+(f':{index}' if index else ''),prompt=item.get('resolved_prompt') or item['prompt'],style_reference_ids=item.get('style_reference_ids',[]),interpreted_prompt=item.get('prompt_interpretation',{}).get('generation_prompt_en'),directives=hand_directives,negative_terms=hand_negatives,aspect=size_aspect(item),quality=item['quality'],seed=42+index*7919,batch_id=identifier,batch_attempt=item['attempt']))
                            active_assets.add(item['asset_id']);auto.update(status='queued',stage='concept');continue
                        generated=[v for v in valid if v[2]['role']=='concept' and v[2]['id'] not in item['reference_ids']]
                        if generated and len(generated)==len(valid):
                            # Generated concepts compete on image-to-3D suitability and project style; user references stay authoritative.
                            from .concept_rank import rank,POLICY_VERSION
                            from .style_anchor import resolve as resolve_anchor
                            anchor=resolve_anchor(value['project_id'],studio.project(value['project_id']),item.get('style_reference_ids',[]))
                            # Requested colours come from what the user wrote (original + literal translation), never from the planned design.
                            request_text=' '.join([item['prompt'],*[c.get('interpretation',{}).get('translated_prompt_en','') for c in (item.get('prompt_interpretation') or {}).get('chunks',[])]])
                            ranked=rank([(v[2],store.safe_path(v[2]['relative_path'])) for v in generated],anchor and anchor['path'],request_text)
                            # Bounded tournament repair: a requested colour nobody drew, or no concept inside the frame, earns up to two
                            # extra concepts with a targeted directive before Auto decides with what it has.
                            from .concept_rank import requested_hues,HUE_NAMES
                            from .held_items import concept_conditioning
                            from .size_rules import aspect as size_aspect
                            hues=requested_hues(request_text);best=ranked[0][1]
                            extra=[j for j in current if j['payload']['kind']=='concept' and (j['payload'].get('quality_repair') or {}).get('kind')=='tournament']
                            colour_miss=bool(hues) and best.get('eligible') and best.get('requested_colour_match',1)<0.15
                            if (colour_miss or not best.get('eligible')) and len(extra)<2:
                                directives=(['The subject is predominantly '+' and '.join(HUE_NAMES[h] for h in hues)+'.'] if colour_miss else [])+([] if best.get('eligible') else ['Zoomed out: the entire subject fits inside the frame with wide empty margins on every side.'])
                                studio.concept(studio.ConceptInput(asset_id=item['asset_id'],request_id=prefix+f':tournament-repair:{len(extra)}',prompt=item.get('resolved_prompt') or item['prompt'],
                                    style_reference_ids=item.get('style_reference_ids',[]),interpreted_prompt=item.get('prompt_interpretation',{}).get('generation_prompt_en'),
                                    directives=[*directives,*concept_conditioning(item)[0]],negative_terms=concept_conditioning(item)[1],aspect=size_aspect(item),
                                    quality=item['quality'],seed=1009+len(extra)*7919,batch_id=identifier,batch_attempt=item['attempt'],
                                    quality_repair=dict(kind='tournament',issues=(['requested_colour'] if colour_miss else [])+([] if best.get('eligible') else ['framing']))))
                                active_assets.add(item['asset_id']);auto.update(status='queued',stage='Extra concept: '+' / '.join(d.split(':')[0].rstrip('.') for d in directives));continue
                            if colour_miss:
                                from .concept_guard import record_decision
                                record_decision(auto,dict(stage='concept_colour',decision='Continued with the best-framed concept although the requested colour is weak',
                                    reason=f"Requested colour match {best.get('requested_colour_match')} after {len(extra)} extra concepts",kept_artifact_ids=[ranked[0][0]['id']]))
                            if not ranked[0][1]['eligible']:
                                # Auto production decides instead of waiting: the best-ranked concept continues, with the reason recorded.
                                from .concept_guard import record_decision
                                record_decision(auto,dict(stage='concept_framing',decision='Continued with the best-ranked concept although none keeps the whole subject in frame',
                                    reason=ranked[0][1].get('reason',''),kept_artifact_ids=[ranked[0][0]['id']]))
                            source,ranking=ranked[0][0],ranked[0][1]
                            measured=next(v[3] for v in generated if v[2]['id']==source['id'])
                            selection=dict(artifact_id=source['id'],sha256=source['sha256'],method=f'Concept tournament v{POLICY_VERSION}: whole subject in frame, framing, clean background and style-anchor palette similarity',
                                measurements=measured,ranking=[dict(artifact_id=a['id'],**m) for a,m in ranked],style_anchor=anchor and anchor['sha256'],artistic_approval=False)
                        else:
                            _,_,source,measured=max(valid,key=lambda x:(x[0],x[1],x[2]['id']))
                            selection=dict(artifact_id=source['id'],sha256=source['sha256'],method='Valid image, highest measured pixel count then Laplacian variance; deterministic tie fallback',measurements=measured,artistic_approval=False)
                        auto['concept_selection']=selection
                        batch.save(batch.stored(value))  # hash-bound selection must exist before Single gate checks it
                    if settings['mode']=='assisted' and settings['checkpoints']['concept']:
                        model=studio.asset(item['asset_id'])
                        if not any(a['artifact_id']==source['id'] and a['sha256']==source['sha256'] for a in model.get('concept_approvals',[])):auto.update(status='blocked',stage='Review concept',error='Assisted concept checkpoint');continue
                    inference=[j for j in current if j['payload']['kind']=='inference']
                    if not inference:
                        batch.save(batch.stored(value))
                        for engine in auto['engines']:
                            studio.generate(studio.Generate(asset_id=item['asset_id'],artifact_id=source['id'],request_id=prefix+':'+engine,engine=engine,texturer=item.get('texturer') or None,quality=item['quality'],prompt=item.get('resolved_prompt') or item['prompt'],seeds=item.get('seeds') or [42+n for n in range(item['candidates'])],auto_blender=True,benchmark_height_m=item['target_height_m'],batch_id=identifier,batch_attempt=item['attempt'],quality_lock=item['quality_lock'],triangle_budget=item.get('triangle_budget'),game_texture_size=item.get('game_texture_size')))
                        active_assets.add(item['asset_id']);auto.update(status='queued',stage='image-to-3D');continue
                    for job in inference:jobs.ensure_blender(job)
                processed=[a for a in artifacts if a.get('asset_id')==item['asset_id'] and a['metadata'].get('stage') in ('blender_processed','animation_processed') and any(j['id']==a['metadata'].get('job_id') for j in current)]
                required=len(auto['engines'])*item['candidates']
                if len(processed)<required:
                    auto.update(status='queued',stage='Blender / QA');active_assets.add(item['asset_id']);continue
                from .model_guard import filter_candidates
                processed=filter_candidates(value,item,current,processed,auto)
                if processed is None:active_assets.add(item['asset_id']);continue
                ranking=[]
                for candidate in processed:
                    from .quality_evaluation import evaluate
                    evaluation=evaluate(item,candidate)
                    if not evaluation['eligible']:continue
                    metadata=candidate['metadata'];materials=metadata.get('materials',[])
                    raw=next((a for a in artifacts if a['id']==metadata.get('parent_id')),None)
                    if raw and raw['metadata'].get('engine')=='trellis2_community' and (not metadata.get('images') or not any(m.get('base_color_texture') for m in materials)):
                        raise ValueError('Required textured output missing from processed candidate; no placeholder export')
                    score=[int(any(m.get('base_color_texture') for m in materials)),int(any(m.get('metallic_roughness_texture') for m in materials)),int(all(m.get('has_uv') for m in metadata.get('meshes',[]))),int(all(m.get('winding_consistent') for m in metadata.get('meshes',[])))]
                    ranking.append(dict(artifact_id=candidate['id'],sha256=candidate['sha256'],technical_score=score,triangles=metadata.get('triangles')))
                if not ranking:
                    auto.update(status='blocked',stage='Needs Attention / structural QA',error='No candidate passes every mandatory technical/structural gate. Sources, raw meshes and QA evidence retained.');continue
                ranking.sort(key=lambda r:(r['technical_score'],r['artifact_id']),reverse=True);winner=ranking[0]
                auto.update(status='completed',stage='Technically validated',ranking=ranking,candidate_selection=winner,ranking_method='Texture/UV/winding validity only; tie by stable artifact ID, no artistic score')
                if settings['mode']=='assisted' and settings['checkpoints']['candidate']:
                    master=studio.asset(item['asset_id']).get('master_artifact_id')
                    if master not in [r['artifact_id'] for r in ranking]:auto.update(status='blocked',stage='Choose candidate',error='Assisted candidate checkpoint');continue
                    winner=next(r for r in ranking if r['artifact_id']==master)
                if settings['mode']=='assisted' and settings['checkpoints']['export'] and not auto.get('export_authorized'):
                    auto.update(status='blocked',stage='Review before export',error='Assisted export checkpoint');continue
                from .statuses import policy,approved
                model=studio.asset(item['asset_id'])
                if policy(model,settings)=='manual_approval' and not approved(model,winner['artifact_id']):
                    auto.update(status='blocked',stage='Manual approval before export',error='Manual Approval policy: approve this candidate to publish. Other assets continue.');continue
                export_settings=copy.deepcopy(value['automation']['export_settings'])
                staged=bool(revision and revision.get('previous_delivery_ids') and not revision.get('auto_replace'))
                if staged:
                    from .export_profiles import revision_output_directory
                    export_settings['output_directory']=revision_output_directory()
                exported=export_asset(value['project_id'],item['asset_id'],artifact_id=winner['artifact_id'],settings=export_settings)
                if revision:
                    exported.update(delivery_scope='staged' if staged else 'game',revision_id=revision['id'])
                    with store.connect() as db:db.execute('UPDATE selective_exports SET payload=? WHERE id=?',(json.dumps(exported),exported['id']))
                    # The chat reports what a water edit measured (level, previous level, brim).
                    water=next((json.loads(f.read_text(encoding='utf-8')) for f in (store.DATA/'jobs'/x['id']/'output/water.json' for x in current if x['payload']['kind']=='blender') if f.is_file()),None)
                    update_execution(item['asset_id'],revision['id'],dict(state='staged' if staged else 'published',artifact_id=winner['artifact_id'],artifact_sha256=winner['sha256'],job_ids=[j['id'] for j in current],export_id=exported['id'],qa_status='passed',completed_at=store.now(),water=water))
                auto.update(status='exported',stage='Completed',export=exported,completed_at=store.now());auto.pop('error',None)
                model=studio.asset(item['asset_id'])
                if not model.get('master_artifact_id'):model.update(status='Completed',art_review_status='not_reviewed')
                if not staged:
                    model['published_artifact_id']=winner['artifact_id'];model.setdefault('publication_history',[]).append(dict(artifact_id=winner['artifact_id'],export_id=exported['id'],at=store.now(),action='automatic_delivery',sha256=winner['sha256']))
                model.setdefault('settings',{})['automatic_selection']=winner
                if not staged and intermediates.enabled(studio.project(value['project_id'])):
                    model['settings']['intermediate_cleanup']=intermediates.prune(item['asset_id'],export_settings);intermediates.forget(item['asset_id'])
                studio.save_asset(model)
                if not staged and (value.get('keep_final_only') or studio.project(value['project_id']).get('keep_final_only')):
                    # Keep only the delivered GLB, its source model and the thumbnail; failures leave everything in place.
                    try:intermediates.finalize(item['asset_id'])
                    except Exception as exc:auto['keep_final_error']=str(getattr(exc,'detail',exc))[:300]
            except RouteWaiting as exc:
                auto.update(status='queued',stage=exc.hold['reason'],waiting_engine_key=exc.hold['health_key']);auto.pop('error',None)
            except Exception as exc:
                auto.update(status='blocked' if isinstance(exc,HTTPException) else 'failed',stage=auto.get('stage','production'),error=str(exc.detail if isinstance(exc,HTTPException) else exc),retry_required=True)
        active_running=any(j['payload'].get('batch_id')==identifier and j['status'] not in jobs.TERMINAL and j['status']!='QUEUED' for j in all_jobs)
        for revision_item in value['items']:
            if revision_item.get('repair_history'):
                studio.patch_resolved_specification(revision_item['asset_id'],dict(quality_repair_history=revision_item['repair_history']))
            if revision_item.get('revision_id') and revision_item.get('automation',{}).get('status')!='exported':
                from .revisions import update_execution
                update_execution(revision_item['asset_id'],revision_item['revision_id'],dict(state=revision_item['automation'].get('status','queued'),stage=revision_item['automation'].get('stage')))
        value['automation']['pause_state']=('pausing' if active_running else 'paused') if value['paused'] else 'running'
        batch.save(batch.stored(value))
    return batch.detail(value)


def startup_recovery():
    from .production import restore_exit_checkpoint
    restore_exit_checkpoint()
    from . import batch
    with batch.LOCK:
        with store.connect() as db:values=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches')]
        for value in values:
            if not value.get('automation'):
                if any(i.get('started') for i in value['items']):value['paused']=True;batch.save(batch.stored(value))
                continue
            auto=value['automation'];opt_in=auto['settings'].get('auto_resume',False)
            # Explicit user pause/cancel is never revoked by startup.
            if not value['paused'] and not opt_in:value['paused']=True;auto['pause_reason']='Application reopened. Manual Resume required; completed checkpoints retained.'
            auto['recovered_at']=store.now();batch.save(batch.stored(value))
    # Native effects, maps and manual engine jobs also use the global queue.
    # Their queued GPU work must obey the same explicit restart opt-in as batches.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute("SELECT id,payload FROM jobs WHERE status='QUEUED'").fetchall():
            payload=json.loads(row['payload'])
            if payload.get('batch_id') or jobs.resource_class(payload)!='gpu':continue
            project=db.execute('SELECT payload FROM projects WHERE id=?',(payload.get('project_id'),)).fetchone()
            settings=json.loads(project['payload']).get('workflow_settings',{}) if project else {}
            if settings.get('auto_resume') is True:continue
            payload['production_paused']=True
            payload['recovery_notice']=dict(at=store.now(),reason='AFS reopened. Pending GPU work waits for manual Resume; no mid-inference resume is claimed.')
            db.execute('UPDATE jobs SET payload=?,updated_at=? WHERE id=?',(json.dumps(payload),store.now(),row['id']))
            if payload.get('asset_id'):
                asset_row=db.execute('SELECT payload FROM assets WHERE id=?',(payload['asset_id'],)).fetchone()
                if asset_row:
                    latest=json.loads(asset_row['payload']);latest.update(production_paused=True,recovery_notice=payload['recovery_notice'])
                    db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(latest),payload['asset_id']))


_last_tick=0.0
def tick():
    global _last_tick
    if time.monotonic()-_last_tick<2:return
    _last_tick=time.monotonic()
    from . import batch
    with store.connect() as db:values=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches')]
    for value in values:
        if value.get('automation') and any(i.get('started') and not i.get('skipped') and i.get('automation',{}).get('status') not in ('exported','failed') for i in value['items']):
            try:advance(value['id'])
            except HTTPException:continue
    from .revisions import drain_chat_queues
    drain_chat_queues()


class Single(BaseModel):
    asset_id:str
    request_id:str=Field(min_length=8,max_length=100)
    quality:Literal['Fast','Balanced','Maximum']='Maximum'
    engine:Literal['auto','trellis2_community','triposg','trellis_v1','hunyuan3d21']='auto'
    # Generate candidates with each of these engines (Advanced); empty uses `engine`.
    engines:list[Literal['trellis2_community','triposg','trellis_v1','hunyuan3d21']]=Field(default_factory=list,max_length=4)
    texturer:Literal['','mvadapter','trellis2']=''
    seeds:list[int]=Field(default=[42],min_length=1,max_length=5)
    triangle_budget:int|None=Field(default=None,ge=500,le=5_000_000)
    game_texture_size:Literal[1024,2048,4096]|None=None
    reference_id:str|None=None
    reference_usage:Literal['auto','source','palette_style']='source'
    workflow:Workflow|None=None
    # Real-world size confirmed in the Size & scale preview; height drives uniform normalization, width/depth are recorded targets.
    target_width_m:float|None=Field(default=None,gt=0,le=1000)
    target_depth_m:float|None=Field(default=None,gt=0,le=1000)
    target_height_m:float|None=Field(default=None,gt=0,le=1000)
    allow_questions:bool=False


@router.post('/single',status_code=201)
def single(body:Single):
    from . import batch
    model=studio.asset(body.asset_id)
    from engines.intent_adapter import available as interpreter_available
    effective_usage=body.reference_usage
    if effective_usage=='auto' and not interpreter_available():effective_usage='palette_style' if body.reference_id and model['prompt'].strip() else 'source'
    if len(set(body.seeds))!=len(body.seeds) or any(seed<0 or seed>=2**32 for seed in body.seeds):raise HTTPException(400,'Use 1–5 distinct seeds in 0..4294967295')
    if body.reference_id:
        reference=studio.scoped_artifact(body.reference_id,model['project_id'])
        if reference['role'] not in ('concept','reference'):raise HTTPException(400,'A reference image is required')
    if effective_usage=='palette_style' and (not body.reference_id or not model['prompt'].strip()):raise HTTPException(422,'Style reference needs a subject prompt and an image')
    if model.get('asset_type','static_3d')!='static_3d':raise HTTPException(409,'This asset type requires its implemented dedicated pipeline')
    with batch.LOCK:
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');prior=studio.cached(db,'auto-single:'+body.request_id,studio.request_digest(body))
            if prior:return dict(batch_id=prior['batch_id'],asset_id=body.asset_id,batch=batch.detail(batch.batch(prior['batch_id'])))
            identifier=uuid.uuid4().hex
            from .manifest import ManifestItem
            row=ManifestItem(name=model['name'],prompt=model['prompt'],asset_id=model['id'],preferred_engine=body.engine,engines=list(dict.fromkeys(body.engines)),texturer=body.texturer,candidates=len(body.seeds),triangle_budget=body.triangle_budget,game_texture_size=body.game_texture_size,quality=body.quality,reference_ids=[body.reference_id] if body.reference_id else []).model_dump()
            row.update(attempt=0,started=False,version=1,quality_lock=body.quality=='Maximum',seeds=body.seeds)
            for key in ('target_width_m','target_depth_m','target_height_m'):
                if getattr(body,key) is not None:
                    row[key]=getattr(body,key);row.setdefault('spec_provenance',{})[key]=dict(kind='explicit',source='Size & scale preview (user confirmed)',value=getattr(body,key))
            if effective_usage=='palette_style':row.update(reference_ids=[],style_reference_ids=[body.reference_id],reference_usage=effective_usage)
            row.update(intent_reference_usage='style' if effective_usage=='palette_style' else body.reference_usage,intent_reference_scope='palette_only' if body.reference_usage=='palette_style' else 'semantic')
            project=studio.project(model['project_id']);value=dict(id=identifier,project_id=model['project_id'],name=model['name'],mode={'Fast':'Fast Batch','Balanced':'Quality Batch','Maximum':'Maximum Quality Batch'}[body.quality],quality_lock=body.quality=='Maximum',master_prompt=model['prompt'],style_snapshot=project,warnings=[],items=[row],paused=True,created_at=store.now(),updated_at=store.now())
            db.execute('INSERT INTO batches VALUES (?,?,?)',(identifier,model['project_id'],json.dumps(value)));db.execute('INSERT INTO studio_requests VALUES (?,?,?)',('auto-single:'+body.request_id,studio.request_digest(body),json.dumps(dict(batch_id=identifier))))
        result=start(identifier,workflow=body.workflow.model_dump() if body.workflow else None,allow_questions=body.allow_questions)
    return dict(batch_id=identifier,asset_id=body.asset_id,batch=result)
