"""One immutable quality resolver used by Single and Batch. Scheduling never changes it."""
import functools
import hashlib
import json
from pathlib import Path
from .adapters import ADAPTERS, SHAPE_ENGINES
from apps.api import store


def fingerprint(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@functools.lru_cache(maxsize=16)
def _hash_checkpoints(signature):
    return {name:store.digest(name) for name,_,_ in signature}


def checkpoints(engine):
    adapter=ADAPTERS[engine];source,_=adapter.paths()
    roots=adapter.checkpoint_roots() if hasattr(adapter,'checkpoint_roots') else [source/'MODELS']
    # Include conditioning/segmentation weights and sampler configs, not only the 3D backbone.
    paths=sorted(p for root in roots for p in Path(root).rglob('*') if p.is_file() and p.suffix in {'.safetensors','.pt','.pth','.json','.yaml','.ckpt'})
    if not paths: raise ValueError('Checkpoint files missing; no fallback permitted')
    signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
    hashes=_hash_checkpoints(signature)
    return dict(manifest_hash=fingerprint(hashes),files=hashes)


def resolve_concept(prompt,seed,steps,size,project,quality):
    from .concept_adapter import CONCEPT_ADAPTER
    from .concept_conditioning import identity
    source, _ = CONCEPT_ADAPTER.paths()
    paths=sorted(CONCEPT_ADAPTER.weights().rglob('*.safetensors'))
    hashes=_hash_checkpoints(tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths))
    return dict(schema_version=1,stage='concept',engine_id='sdxl_local',engine_version=CONCEPT_ADAPTER.version,
        checkpoint=dict(manifest_hash=fingerprint(hashes),files=hashes),input_prompt=prompt,reference_hashes=[],
        resolution=size,inference_steps=steps,guidance=7,seed=seed,precision='fp16 with upstream VAE float32 upcast',
        geometry=None,texture=None,blender=None,lod=None,export=dict(format='png'),candidate_count=1,
        quality=quality,quality_lock=quality=='Maximum',project_style_hash=fingerprint(project),
        conditioning=identity(CONCEPT_ADAPTER.weights(),source/'venv',store.ROOT/'engines'),
        qa=dict(image_validity=True,human_concept_approval=True,automatic_3d_generation=False))


def resolve_procedural(spec,seed,candidate_count=1):
    script=store.ROOT/'pipelines/blender/assemble_castle.py'
    return dict(schema_version=1,quality=spec['quality'],quality_lock=spec['quality']=='Maximum',stage='geometry',engine_id='blender_procedural',engine_version='four_corner_castle_v1',
        checkpoint=dict(script_sha256=store.digest(script)),input_prompt=spec['original_prompt'],reference_hashes=[r['sha256'] for r in spec['reference_hashes']],
        project_style_hash=spec['source_style_hash'],spec_hash=fingerprint(spec),seed=seed,seeds=[seed],candidate_count=candidate_count,
        resolution=None,inference_steps=None,precision='Blender geometry float32; no neural inference',
        geometry=dict(profile='four_corner_castle_v1',bounds_m=spec['bounds_m'],required_named_components=True),
        texture=dict(size={'Fast':512,'Balanced':1024,'Maximum':2048}[spec['quality']],method='authored_procedural_PBR',ai_texturing=False),
        blender=dict(enabled=True,profile='existing_quality_pipeline_v1',normalize=False,height_m=None),lod=dict(ratios=[.65,.35,.15]),
        export=dict(preserve_master=True,default_format='glb'),qa=dict(technical=True,structural=True,visual='inferred_or_not_evaluated',artistic_approval=False))


def resolve(options, reference, project):
    engine=options['engine'];quality=options.get('quality','Maximum');adapter=ADAPTERS[engine]
    steps=options.get('steps') or (50 if engine in ('triposg','hunyuan3d21') else {'Fast':12,'Balanced':24,'Maximum':32}[quality])
    pipeline=options.get('pipeline_type') or ('512' if quality=='Fast' else '1024_cascade')
    texture=options.get('texture_size') or (2048 if quality=='Fast' else 4096)
    candidate_count=len(options.get('seeds',[42]))
    required=options.get('required_stages',[])
    # Shape engines get a projected basecolor texture (MV-Adapter); metallic/roughness maps are not produced.
    unsupported=[stage for stage in required if stage=='pbr' and engine in SHAPE_ENGINES]
    if any(stage in required for stage in ['normal_bake','ao_bake']):unsupported.extend(s for s in required if s in ['normal_bake','ao_bake'])
    if unsupported:raise ValueError('Engine/pipeline does not implement required stage: '+', '.join(unsupported))
    guidance=7.0
    if engine=='trellis2_community':
        source,_=adapter.paths();cache=source/'MODELS/hub/models--microsoft--TRELLIS.2-4B'
        revision=(cache/'refs/main').read_text().strip()
        args=json.loads((cache/'snapshots'/revision/'pipeline.json').read_text())['args']
        guidance={name:args[name]['params'] | dict(steps=steps) for name in ['sparse_structure_sampler','shape_slat_sampler','tex_slat_sampler']}
    return dict(schema_version=1,quality=quality,quality_lock=options.get('quality_lock',quality=='Maximum'),
        engine_id=engine,engine_version=adapter.version,checkpoint=checkpoints(engine),
        input_prompt=options.get('prompt') or '',reference_hashes=[reference['sha256']],project_style_hash=fingerprint(project),
        resolution=512 if engine in SHAPE_ENGINES or pipeline=='512' else 1024,inference_steps=steps,guidance=guidance,
        seeds=options.get('seeds',[42]),precision='fp16 model defaults; upstream float32/upcast operations preserved',
        geometry=dict(pipeline_type=pipeline,octree_depth=9 if engine=='triposg' else None,decode_chunk_size=10000 if engine=='triposg' else None,
                      # An explicit budget above the default only raises master detail; it never lowers the locked 1 M export.
                      export_triangle_target=max(1000000,int(options.get('triangle_budget') or 0)) if engine=='trellis2_community' else 1000000),
        texture=dict(size=texture,pbr='native basecolor/metallic-roughness' if engine=='trellis2_community' else 'basecolor projected by MV-Adapter'),
        blender=dict(enabled=options.get('auto_blender',True),profile='existing_quality_pipeline_v1',height_m=options.get('benchmark_height_m') or project.get('target_height_m'),
                     render_views=['front','three_quarter','side','back','top','gameplay'],render_resolutions=['mobile','pc1440'],bake='not_requested'),
        lod=dict(ratios=[.65,.35,.15]),export=dict(formats=['glb','fbx'],preserve_master=True),candidate_count=candidate_count,
        qa=dict(mesh_validity=True,geometry_defects=True,dimensions=True,uv_texture_inventory=True,export_reopen=True,per_asset=True,
                human_concept_approval=True,human_master_approval=True,visual_parity='NOT_TESTED'))
