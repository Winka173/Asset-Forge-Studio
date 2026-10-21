"""Additive manifest/route API over legacy project/assets. No automatic generation."""
import json
import platform
import uuid
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


def file_ref(record,verify=False):
    path=store.safe_path(record['relative_path'])
    if not path.is_file():raise HTTPException(409,'Manifest input/output file is missing: '+record['id'])
    if verify and store.digest(path)!=record['sha256']:raise HTTPException(409,'Immutable file checksum changed: '+record['id'])
    return ArtifactFile(artifact_id=record['id'],path=record['relative_path'],sha256=record['sha256'],bytes=path.stat().st_size,role=record['role'],integrity='verified' if verify else 'recorded')


def manifest(identifier,verify=False):
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
        stages.append(Stage(id=job['id'],plugin=payload.get('engine') or ('blender_headless' if kind=='blender' else kind),
            operation=Operation.import_test if kind=='unity_import' else Operation.postprocess if kind=='blender' else Operation.generate,
            resource=resource_class(payload),depends_on=list(dict.fromkeys(deps)),input_artifacts=[ref] if ref else [],input_hashes=input_hashes,
            expected_outputs=['png'] if kind=='concept' else ['unity_prefab','unity_scene','import_report'] if kind=='unity_import' else ['glb','fbx','lod','blend','previews'] if kind=='blender' else ['glb'],
            checkpoint=f'jobs/{job["id"]}',effective_config_hash=payload.get('effective_config_hash'),status=states[job['status']],
            acceptance=['Input checksums match','Requested output contract passes technical validation'],evidence_paths=[f'jobs/{job["id"]}/manifest.json']))
        report=store.DATA/'jobs'/job['id']/'output/unity_report.json'
        if kind=='unity_import' and job['status']=='REVIEW_REQUIRED' and report.is_file():
            data=json.loads(report.read_text(encoding='utf-8-sig'))
            imports.append(dict(job_id=job['id'],status='PASS_EDITOR_VALIDATION' if data.get('checks_passed') else 'FAILED_EDITOR_VALIDATION',report_path=report.relative_to(store.DATA).as_posix(),tool='unity',version=data.get('unity_version')))
    candidates=[files[r['id']] for r in records if r['role']=='candidate']
    master=files.get(value.get('master_artifact_id'))
    derives=[files[r['id']] for r in records if r['role']=='candidate' and r['metadata'].get('parent_id')]
    provenance=[]
    for r in records:
        if r['role']=='candidate':provenance.append(Provenance(source_code=r['metadata'].get('license','UNKNOWN'),commercial='blocked' if 'EVALUATION' in r['metadata'].get('license','') else 'review_required',restrictions=['Recorded tool license is not proof of model/input/commercial asset clearance']))
    return AssetManifest(project_id=value['project_id'],asset_id=identifier,asset_type=value.get('asset_type','static_3d'),family_id=value.get('settings',{}).get('family_id'),version=uuid.uuid4().hex,
        status='engine_validated' if any(i['status']=='PASS_EDITOR_VALIDATION' for i in imports) else 'exported' if derives else 'source_generated' if any(r['metadata'].get('generation',{}).get('status')=='GENERATED_NEEDS_REVIEW' for r in records) else 'draft',
        target_engines=project.get('target_engines',[]),units=project.get('units','m'),prompt=value.get('prompt',''),
        references=[files[r['id']] for r in records if r['id'] in value.get('reference_ids',[])],art_bible=project.get('art_bible',{}),
        golden_reference_ids=[r['id'] for r in records if r['role']=='golden'],effective_configs=configs,effective_config_hashes=hashes,graph=StageGraph(stages=stages),
        source_master=master,candidates=candidates,derivatives=derives,expected_outputs=['glb']+(['fbx','lod','blend','previews'] if any(j['payload']['kind']=='blender' for j in current) else []),
        actual_outputs=[files[r['id']] for r in records if r.get('asset_id')==identifier and r['role'] not in ['reference','concept']],licenses=provenance,
        toolchain_versions=dict(python=platform.python_version(),desktop='0.3.0',manifest_sdk='2.0'),import_tests=imports,
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
