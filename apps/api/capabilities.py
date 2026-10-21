"""Live capability routing: installed, verified and commercially cleared are separate."""
from typing import Literal
from pathlib import Path
from pydantic import BaseModel, Field
from engines.adapters import ADAPTERS
from engines.concept_adapter import CONCEPT_ADAPTER
from engines.plugin_sdk import Stage, StageGraph, Operation
from .asset_contract import AssetType, Provenance
from . import store


LABELS={AssetType.static_3d:'3D Model',AssetType.character:'Character',AssetType.animation:'Rig / Animation',
        AssetType.map_environment:'Map / Environment',AssetType.vfx:'VFX',AssetType.material:'Material',
        AssetType.sprite_2d:'Sprite / 2D',AssetType.ui:'UI',AssetType.audio:'Audio',AssetType.cinematic:'Cinematic'}


class Capability(BaseModel):
    id: str
    label: str
    asset_types: list[AssetType]
    inputs: list[str]
    outputs: list[str]
    installed: bool
    status: Literal['verified_local','experimental','unavailable','planned']
    dependency_health: dict
    license: Provenance
    resource: Literal['gpu','cpu','io']
    min_vram_gb: float | None=None
    tested_platforms: list[str]=Field(default_factory=list)
    target_engine_support: list[str]=Field(default_factory=list)
    constraints: list[str]=Field(default_factory=list)
    evidence: list[str]=Field(default_factory=list)


def registry():
    values=[]
    for identifier,adapter in ADAPTERS.items():
        probe=adapter.probe();is_tripo=identifier=='triposg'
        values.append(Capability(id=identifier,label=identifier,asset_types=[AssetType.static_3d],inputs=['approved_alpha_image'] if is_tripo else ['approved_image'],
            outputs=['glb','geometry']+([] if is_tripo else ['basecolor','metallic_roughness','uv']),installed=probe['installed'],
            status='experimental' if probe['installed'] else 'unavailable',dependency_health=probe,
            license=Provenance(source_code='MIT' if is_tripo else 'community bundle; per-dependency audit',model_weights='MIT' if is_tripo else 'mixed; audit required',
                commercial='review_required' if is_tripo else 'blocked',restrictions=['Input reference rights must be reviewed']+([] if is_tripo else ['Bundled RMBG/DINO and community modifications not cleared commercially'])),
            resource='gpu',min_vram_gb=adapter.min_vram_gb,tested_platforms=['Windows 11 / RTX 5070 Ti 16GB'],
            evidence=['docs/evidence/maximum_quality_comparison.json' if not is_tripo else 'docs/evidence/all_runs.json'],
            constraints=['Existing isolated environment; no automatic weight download','Human quality approval pending']+(['Shape only; no invented PBR'] if is_tripo else ['Measured community CPU-offload profile; not official native 16GB support'])))
    values.append(Capability(id='sdxl_local',label='Local concept image',asset_types=[AssetType.static_3d],inputs=['text'],outputs=['png'],
        installed=CONCEPT_ADAPTER.installed,status='experimental' if CONCEPT_ADAPTER.installed else 'unavailable',dependency_health=CONCEPT_ADAPTER.probe(),
        license=Provenance(source_code='Apache-2.0 diffusers',model_weights='CreativeML Open RAIL++-M',commercial='review_required',restrictions=['Model use restrictions and input rights apply']),
        resource='gpu',min_vram_gb=6,tested_platforms=['Windows 11 / RTX 5070 Ti 16GB'],evidence=['docs/evidence/sdxl_local_concept.json'],constraints=['Requires concept approval; prompt fidelity not guaranteed']))
    # Detect paths without invoking the broad system audit (which starts external tools).
    import os,shutil
    blender=os.environ.get('AFS_BLENDER') or shutil.which('blender')
    if not blender:blender=next((str(p) for p in sorted((Path.home()/'Tools').glob('blender*/blender.exe'),reverse=True)),None)
    values.append(Capability(id='blender_headless',label='Blender postprocessing',asset_types=[AssetType.static_3d],inputs=['glb'],outputs=['blend','glb','fbx','lod','previews'],
        installed=bool(blender and Path(blender).is_file()),status='experimental' if blender else 'unavailable',dependency_health=dict(path=blender),
        license=Provenance(source_code='Blender GPL; asset rights are a separate question',model_weights='not used',commercial='review_required'),resource='cpu',
        tested_platforms=['Windows 11 / Blender 4.5.14'],constraints=['No fabricated missing PBR maps; preserve source master'],evidence=['docs/evidence/studio_exports.json']))
    from engines.unity_editor import probe as unity_probe
    unity=unity_probe()
    values.append(Capability(id='unity_editor',label='Unity native import',asset_types=[AssetType.static_3d],inputs=['validated_fbx_lod4','basecolor','metallic_roughness'],outputs=unity['outputs'],
        installed=unity['installed'],status='experimental' if unity['installed'] else 'unavailable',dependency_health=unity,
        license=Provenance(source_code='AFS Editor importer',model_weights='not used',commercial='review_required',restrictions=['Unity Editor licensing and input rights are separate']),
        resource='gpu',target_engine_support=['unity:6000.4.8f1:Built-in'],constraints=unity['constraints']))
    return dict(schema_version='1.0',providers=[v.model_dump(mode='json') for v in values],asset_types=[dict(id=t.value,label=LABELS[t],status='experimental' if t==AssetType.static_3d else 'planned',
        reason='Existing real Single/Batch pipeline; output/license gates still apply' if t==AssetType.static_3d else 'No complete validated generator/export/native-import slice yet') for t in AssetType],
        scheduler=dict(heavy_gpu_jobs=1,shared_by=['Single','Batch','GPU Blender','native GPU validation']),
        planner=dict(provider='deterministic_structured_schema',local_llm='not configured; no downloads or paid fallback'),
        commercial_policy='Default deny for unknown/research-only provenance; tool installation is not commercial clearance')


class RouteRequest(BaseModel):
    project_id: str
    asset_type: AssetType=AssetType.static_3d
    input_mode: Literal['Text','Image','Text + Image']='Image'
    prompt: str=Field(default='',max_length=100000)
    reference_ids: list[str]=Field(default_factory=list,max_length=50)
    engine: str='auto'
    desired_outputs: list[str]=Field(default_factory=lambda:['glb'],min_length=1,max_length=20)
    commercial: bool=False
    auto_blender: bool=True
    policy: Literal['Manual','Assisted','Auto Batch']='Assisted'


def route(body:RouteRequest):
    from .studio import project,scoped_artifact
    project(body.project_id);refs=[scoped_artifact(i,body.project_id) for i in body.reference_ids]
    caps=registry();gaps=[];warnings=[];stages=[]
    if body.asset_type!=AssetType.static_3d:
        gaps.append(f'{LABELS[body.asset_type]} has no validated output route yet; it will not be replaced by a preview or a mesh')
    native=bool(set(body.desired_outputs)&{'unity_prefab','unity_scene','unitypackage'})
    supported={'glb','fbx','geometry','basecolor','metallic_roughness','uv','lod','blend','previews','unity_prefab','unity_scene','unitypackage'}
    gaps.extend(f'Output contract not implemented: {o}' for o in body.desired_outputs if o not in supported)
    if any(r['role'] not in ['concept','reference'] for r in refs):gaps.append('Image-conditioned route requires image references')
    source=refs[0] if refs else None
    uses_concept=body.input_mode=='Text' or source is None
    if uses_concept and not body.prompt.strip():gaps.append('A prompt or an approved reference image is required')
    if body.input_mode=='Image' and source is None:gaps.append('Image input is missing')
    chosen=body.engine
    if chosen=='auto':chosen=next((e for e in ['trellis2_community','triposg'] if ADAPTERS[e].installed and (e!='triposg' or (source and source['metadata'].get('has_transparency')))),None)
    provider=next((p for p in caps['providers'] if p['id']==chosen),None)
    if not provider or not provider['installed']:gaps.append('No compatible installed local 3D adapter; no fallback will run')
    if chosen=='triposg' and (uses_concept or not source or not source['metadata'].get('has_transparency')):gaps.append('TripoSG requires a reviewed alpha image; no implicit segmentation')
    if chosen=='triposg' and set(body.desired_outputs)&{'basecolor','metallic_roughness','uv'}:gaps.append('Shape-only engine cannot satisfy requested PBR/UV contract')
    if chosen=='triposg' and native:gaps.append('This Unity PBR profile requires real basecolor/MR maps; shape-only native import profile is not validated')
    if native and not next(p for p in caps['providers'] if p['id']=='unity_editor')['installed']:gaps.append('Pinned native Unity Editor/importer is missing')
    needs_blender=native or body.auto_blender or bool(set(body.desired_outputs)&{'fbx','lod','blend','previews'})
    if needs_blender and not next(p for p in caps['providers'] if p['id']=='blender_headless')['installed']:gaps.append('Blender required by requested outputs is missing')
    if body.commercial:gaps.append('Commercial route blocked until source/model/input rights are explicitly reviewed; installed tools do not clear asset rights')
    if body.policy=='Auto Batch':gaps.append('Auto Batch requires an approved family policy bound to specific hashes; no blanket approval is configured')
    if uses_concept and not CONCEPT_ADAPTER.installed:gaps.append('Local concept engine missing; supply an approved image or configure dependencies')
    if body.asset_type==AssetType.static_3d:
        def add(identifier,plugin,operation,resource,outputs,depends=(),approval=False,skip=None):
            stages.append(Stage(id=identifier,plugin=plugin,operation=operation,resource=resource,depends_on=list(depends),
                input_artifacts=[r['id'] for r in refs],input_hashes={r['id']:r['sha256'] for r in refs},expected_outputs=outputs,
                checkpoint=f'{identifier}: immutable artifacts and job report',requires_approval=approval,skip_condition=skip,
                recovery='human_review' if approval else 'retry_exact_config',acceptance=['Requested files exist and hashes match','Technical QA and human approval remain distinct'],evidence_paths=['jobs/{job_id}/manifest.json']))
        previous=[]
        if uses_concept:
            add('concept','sdxl_local',Operation.generate,'gpu',['png']);previous=['concept']
            add('concept_review','human',Operation.review,'human',['approved_concept'],previous,True);previous=['concept_review']
        elif source and source['metadata'].get('requires_concept_approval'):
            add('concept_review','human',Operation.review,'human',['approved_concept'],approval=True);previous=['concept_review']
        add('geometry',chosen or 'missing',Operation.generate,'gpu',['glb'],previous,skip=None)
        previous=['geometry']
        if needs_blender:add('postprocess','blender_headless',Operation.postprocess,'cpu',['glb','fbx','lod','blend','previews'],previous);previous=['postprocess']
        add('qa','mesh_qa',Operation.validate,'cpu',['qa_report'],previous);previous=['qa']
        if native:
            add('native_import','unity_editor',Operation.import_test,'gpu',['unity_prefab','unity_scene','unitypackage','import_report'],previous)
            previous=['native_import'];warnings.append('Unity 6000.4.8f1 / Built-in, single-material 4K PBR profile; additional material/pipeline translations are blocked')
        add('master_review','human',Operation.review,'human',['master_selection'],previous,True)
    graph=StageGraph(stages=stages)
    return dict(schema_version='1.0',status='blocked' if gaps else 'ready_for_review',requested=body.model_dump(mode='json'),selected_engine=chosen,
        graph=graph.model_dump(mode='json'),capability_gaps=gaps,warnings=warnings,dry_run=True,enqueued_jobs=0,
        estimated_heavy_gpu_jobs=sum(s.resource=='gpu' for s in stages),costs=dict(mandatory_api_cost=0,hardware_electricity_disk='user resources',optional_software='separate license requirements'),
        quality='Existing EffectiveGenerationConfig resolver is used at actual enqueue; this preview never alters it')
