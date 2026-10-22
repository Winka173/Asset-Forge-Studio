"""Additive manifest/route API over legacy project/assets. No automatic generation."""
import json
import platform
import uuid
from typing import Literal
from pydantic import BaseModel,Field
from fastapi import APIRouter, HTTPException
from . import store,studio,jobs
from .asset_contract import AssetManifest,ArtifactFile,Provenance
from .capabilities import registry,route,RouteRequest
from engines.plugin_sdk import Stage,StageGraph,Operation

router=APIRouter(prefix='/api/platform')


@router.get('/capabilities')
def capabilities():return registry()


@router.post('/route')
def preview(body:RouteRequest):return route(body)


@router.get('/integrations')
def integrations():
    from engines.unity_editor import probe
    return dict(unity=probe(),unreal=dict(installed=False,status='unavailable',reason='No configured/tested Unreal Editor; no native Unreal assets are generated'),
                mcp=dict(required_for_runtime=False,connection_status='Agent-side MCP connection is separate; AFS does not assume it is connected'))


class UnityImport(BaseModel):
    artifact_id: str
    request_id: str=Field(min_length=8,max_length=100)
    render_gpu: bool=True
    profile: Literal['6000.4.8f1:Built-in','6000.4.8f1:Built-in:Animation']='6000.4.8f1:Built-in'
    commercial: bool=False


@router.post('/assets/{identifier}/unity-import',status_code=201)
def unity_import(identifier:str,body:UnityImport):
    from engines.unity_editor import effective_config
    if body.profile.endswith(':Animation'):
        from engines.unity_animation import effective_config
    from engines.quality import fingerprint
    value=studio.asset(identifier);record=studio.scoped_artifact(body.artifact_id,value['project_id'],identifier)
    project=studio.project(value['project_id']);profile=project.get('engine_profiles',{}).get('unity',{})
    if profile and (profile.get('version','6000.4.8f1')!='6000.4.8f1' or profile.get('render_pipeline','Built-in')!='Built-in'):raise HTTPException(409,'Project target is not the tested Unity 6000.4.8f1 / Built-in profile')
    if body.commercial:raise HTTPException(409,'Commercial import preset blocked pending full source/model/reference license clearance')
    try:config=effective_config(record,body.render_gpu)
    except (ValueError,KeyError,OSError) as exc:raise HTTPException(409,str(exc))
    request_hash=fingerprint(dict(asset_id=identifier,**body.model_dump()))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');previous=studio.cached(db,body.request_id,request_hash)
        if previous:return previous
        payload=dict(kind='unity_import',engine='unity_animation' if body.profile.endswith(':Animation') else 'unity_editor',project_id=value['project_id'],asset_id=identifier,artifact_id=record['id'],use_gpu=body.render_gpu,
            effective_config=config,effective_config_hash=fingerprint(config),depends_on=[record['metadata']['job_id']] if record['metadata'].get('job_id') else [],timeout_seconds=900,
            purpose='technical_engine_import_evaluation',target_game_project=None)
        queued=jobs.enqueue(payload,db=db)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(body.request_id,request_hash,json.dumps(queued)))
    return queued


@router.get('/assets/{identifier}/animation-unity')
def animation_unity(identifier:str,artifact_id:str):
    from engines.unity_animation import effective_config
    value=studio.asset(identifier);record=studio.scoped_artifact(artifact_id,value['project_id'],identifier)
    if record['role']!='candidate':raise HTTPException(400,'Choose a model candidate')
    try:config=effective_config(record);supported=True;reason=None
    except (ValueError,KeyError,OSError) as exc:config=None;supported=False;reason=str(exc)
    related=[{k:j.get(k) for k in ('id','status','error','progress')} for j in jobs.listing() if j['payload'].get('engine')=='unity_animation' and j['payload'].get('asset_id')==identifier and j['payload'].get('artifact_id')==artifact_id]
    return dict(supported=supported,reason=reason,version='6000.4.8f1',profile='Existing single untextured Generic clip',jobs=related)


def file_ref(record,verify=False):
    path=store.safe_path(record['relative_path'])
    if not path.is_file():raise HTTPException(409,'Manifest input/output file is missing: '+record['id'])
    if verify and store.digest(path)!=record['sha256']:raise HTTPException(409,'Immutable file checksum changed: '+record['id'])
    return ArtifactFile(artifact_id=record['id'],path=record['relative_path'],sha256=record['sha256'],bytes=path.stat().st_size,role=record['role'],integrity='verified' if verify else 'recorded')


def manifest(identifier,verify=False):
    from .main import app
    value=studio.asset(identifier);project=studio.project(value['project_id'])
    with store.connect() as db:
        records=[store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE project_id=? AND (asset_id=? OR role='golden') AND role!='manifest' ORDER BY created_at",(value['project_id'],identifier))]
    # Shared image references are project-scoped and may belong to another asset.
    known={r['id'] for r in records}
    for ref in value.get('reference_ids',[]):
        if ref not in known:records.append(studio.scoped_artifact(ref,value['project_id']))
    files={r['id']:file_ref(r,verify) for r in records}
    current=[j for j in jobs.listing() if j['payload'].get('asset_id')==identifier]
    job_ids={j['id'] for j in current};stages=[];configs=[];hashes=[];imports=[]
    states={'QUEUED':'queued','RUNNING':'running','GENERATED':'running','POSTPROCESSING':'running','VALIDATING':'running','REVIEW_REQUIRED':'review_required','FAILED':'failed','BLOCKED':'blocked','CANCELLED':'cancelled'}
    from .jobs import resource_class
    for job in current:
        payload=job['payload'];kind=payload['kind'];config=payload.get('effective_config')
        if config and payload['effective_config_hash'] not in hashes:configs.append(config);hashes.append(payload['effective_config_hash'])
        deps=[d for d in payload.get('depends_on',[]) if d in job_ids]
        if payload.get('parent_job') in job_ids:deps.append(payload['parent_job'])
        ref=payload.get('artifact_id');input_hashes={ref:store.get_artifact(ref)['sha256']} if ref else {}
        stages.append(Stage(id=job['id'],plugin=payload.get('engine') or ('blender_headless' if kind=='blender' else 'unity_editor' if kind=='unity_import' else kind),
            operation=Operation.import_test if kind in ['unity_import','world_unity'] else Operation.postprocess if kind=='blender' else Operation.generate,
            resource=resource_class(payload),depends_on=list(dict.fromkeys(deps)),input_artifacts=[ref] if ref else [],input_hashes=input_hashes,
            expected_outputs=['heightmap_16bit','unity_scene','terrain_data','navigation_data','unitypackage'] if kind=='world_unity' else ['png'] if kind=='concept' else ['unity_prefab','unity_scene','import_report'] if kind=='unity_import' else ['glb','fbx','lod','blend','previews'] if kind=='blender' else ['glb'],
            checkpoint=f'jobs/{job["id"]}',effective_config_hash=payload.get('effective_config_hash'),status=states[job['status']],
            acceptance=['Input checksums match','Requested output contract passes technical validation'],evidence_paths=[f'jobs/{job["id"]}/manifest.json']))
        report=store.DATA/'jobs'/job['id']/('output/world_unity_report.json' if kind=='world_unity' else 'output/unity_report.json')
        if kind in ['unity_import','world_unity'] and job['status']=='REVIEW_REQUIRED' and report.is_file():
            data=json.loads(report.read_text(encoding='utf-8-sig'))
            imports.append(dict(job_id=job['id'],status='PASS_EDITOR_VALIDATION' if data.get('checks_passed') else 'FAILED_EDITOR_VALIDATION',report_path=report.relative_to(store.DATA).as_posix(),tool='unity',version=data.get('unity_version')))
    candidates=[files[r['id']] for r in records if r['role']=='candidate']
    master=files.get(value.get('master_artifact_id'))
    derives=[files[r['id']] for r in records if r['role']=='candidate' and r['metadata'].get('parent_id')]
    provenance=[]
    for r in records:
        if r['role'] in ['candidate','engine_package','world_plan']:provenance.append(Provenance(source_code=r['metadata'].get('license','UNKNOWN'),commercial='blocked' if 'EVALUATION' in r['metadata'].get('license','') else 'review_required',restrictions=['Recorded tool license is not proof of model/input/commercial asset clearance']))
    return AssetManifest(project_id=value['project_id'],asset_id=identifier,asset_type=value.get('asset_type','static_3d'),family_id=value.get('settings',{}).get('family_id'),version=uuid.uuid4().hex,
        status='engine_validated' if any(i['status']=='PASS_EDITOR_VALIDATION' for i in imports) else 'exported' if derives else 'source_generated' if any(r['metadata'].get('generation',{}).get('status')=='GENERATED_NEEDS_REVIEW' for r in records) else 'draft',
        target_engines=project.get('target_engines',[]),units='m' if value.get('asset_type')=='map_environment' else project.get('units','m'),prompt=value.get('prompt',''),
        coordinate_system='Unity Y-up; x/east, z/north; 16-bit little-endian RAW rows are z indices' if value.get('asset_type')=='map_environment' else 'per_file; GLB/FBX Y-up, Blender source Z-up; native conversion must be verified',
        references=[files[r['id']] for r in records if r['id'] in value.get('reference_ids',[])],art_bible=project.get('art_bible',{}),
        golden_reference_ids=[r['id'] for r in records if r['role']=='golden'],effective_configs=configs,effective_config_hashes=hashes,graph=StageGraph(stages=stages),
        source_master=master,candidates=candidates,derivatives=derives,expected_outputs=['world_plan','heightmap_16bit','masks','unity_scene','terrain_data','navigation_data','unitypackage'] if value.get('asset_type')=='map_environment' else ['glb']+(['fbx','lod','blend','previews'] if any(j['payload']['kind']=='blender' for j in current) else []),
        actual_outputs=[files[r['id']] for r in records if r.get('asset_id')==identifier and r['role'] not in ['reference','concept']],licenses=provenance,
        toolchain_versions=dict(python=platform.python_version(),desktop=app.version,manifest_sdk='2.0'),import_tests=imports,
        previews=[files[r['id']] for r in records if r['role']=='preview'],approvals=value.get('approvals',[]),
        engine_metadata=dict(legacy_format_preserved=True,master_selection_is_not_production_artistic_approval=True,mesh_quality_parity='NOT_TESTED'))


@router.get('/assets/{identifier}/manifest')
def read_manifest(identifier:str):return manifest(identifier).model_dump(mode='json')


@router.post('/assets/{identifier}/manifest',status_code=201)
def save_manifest(identifier:str):
    value=manifest(identifier,verify=True)
    path=store.safe_path(f'projects/{value.project_id}/assets/{identifier}/manifests/{value.version}/manifest.json');path.parent.mkdir(parents=True,exist_ok=False)
    with path.open('x',encoding='utf-8') as stream:stream.write(value.model_dump_json(indent=2))
    return store.add_artifact(path,'manifest','Asset manifest v2',dict(project_id=value.project_id,asset_id=identifier,schema_version=value.schema_version,source_master_hash=value.source_master.sha256 if value.source_master else None))
