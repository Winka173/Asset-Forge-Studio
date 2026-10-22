"""Prepared evaluation runner for the discovered Windows community installation.

INFERENCE NOT TESTED. Requires explicit user opt-in; offline only; never writes to engine installation.
Run using the engine's own Python, from its code directory. All outputs must be in this project's data.
"""
import argparse
import hashlib
import inspect
import json
import os
import sys
import time
import traceback
from pathlib import Path

for key, value in {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
                   'DO_NOT_TRACK': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'TORCHDYNAMO_DISABLE': '1',
                   'OPENCV_IO_ENABLE_OPENEXR': '1'}.items(): os.environ[key] = value
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engines import mesh_checkpoint


def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True)
    parser.add_argument('--allow-community-evaluation', action='store_true')
    args = parser.parse_args()
    if not args.allow_community_evaluation:
        raise SystemExit('BLOCKED: explicit community evaluation opt-in required. No inference started.')
    req = json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
    root = Path(__file__).resolve().parents[1]
    output = Path(req['output']).resolve()
    allowed_data = Path(os.environ.get('AFS_DATA', root / 'data')).resolve()
    if not output.is_relative_to(allowed_data) or output.exists():
        raise ValueError('Output must be a NEW directory beneath this project data/')
    if req.get('purpose') != 'evaluation_only': raise ValueError('Commercial use blocked pending dependency/weights license audit')
    engine = Path(req['engine_path']).resolve()
    if Path.cwd().resolve() != engine: raise ValueError('Run with cwd set to engine code directory')
    # Offline cache, build caches, and remote-code module cache remain project-local where possible.
    os.environ['HF_HUB_CACHE'] = str(engine / 'MODELS/hub')
    os.environ['HUGGINGFACE_HUB_CACHE'] = str(engine / 'MODELS/hub')
    os.environ['HF_MODULES_CACHE'] = str(root / '.local/hf_modules')
    os.environ['TORCH_EXTENSIONS_DIR'] = str(root / '.local/torch_extensions')
    os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'garbage_collection_threshold:0.65'
    sys.path.insert(0, str(engine))
    output.mkdir(parents=True)
    manifest = {'status': 'RUNNING', 'purpose': 'evaluation_only', 'request': req, 'network': 'HF and Transformers offline',
                'script_sha256': digest(__file__), 'source_sha256': digest(req['image']), 'parity_with_meshy': 'NOT_TESTED'}
    manifest_path = output / 'generation.json'
    started = time.monotonic()
    try:
        import torch
        import numpy as np
        from PIL import Image
        from pipeline_worker import _apply_patches
        _apply_patches()
        from trellis2.pipelines import Trellis2ImageTo3DPipeline
        import o_voxel
        if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
        free, total = torch.cuda.mem_get_info()
        if free < req.get('min_free_vram_gb', 10) * 1024**3: raise RuntimeError('Insufficient free VRAM; close GPU apps or lower approved memory profile')
        manifest['environment'] = {'torch': str(torch.__version__), 'cuda': torch.version.cuda,
                                   'gpu': torch.cuda.get_device_name(), 'free_vram_start_bytes': free, 'total_vram_bytes': total}
        manifest['engine_source_files'] = {p.relative_to(engine).as_posix(): digest(p) for p in sorted((engine / 'trellis2').rglob('*.py'))}
        cache = engine / 'MODELS/hub/models--microsoft--TRELLIS.2-4B'
        revision = (cache / 'refs/main').read_text().strip()
        manifest['model_revision'] = revision
        snapshot = cache / 'snapshots' / revision
        manifest['pipeline_json_sha256'] = digest(snapshot / 'pipeline.json')
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        torch.cuda.reset_peak_memory_stats()
        # The community elastic decoder resets PyTorch counters between stages.
        # Aggregate maxima BEFORE each reset so reported peaks cover the whole worker.
        phase_peaks = {'allocated': 0, 'reserved': 0}
        native_reset = torch.cuda.reset_peak_memory_stats
        def tracked_reset(device=None):
            phase_peaks['allocated'] = max(phase_peaks['allocated'], torch.cuda.max_memory_allocated(device))
            phase_peaks['reserved'] = max(phase_peaks['reserved'], torch.cuda.max_memory_reserved(device))
            return native_reset(device)
        torch.cuda.reset_peak_memory_stats = tracked_reset
        pipeline_type = req.get('pipeline_type', '512')
        if pipeline_type not in {'512', '1024_cascade'}: raise ValueError('Unsupported evaluated memory profile')
        if req.get('resume_mesh_checkpoint'):
            print('STAGE Restore validated native geometry and PBR checkpoint; diffusion is not rerun', flush=True)
            checkpoint_path=Path(req['resume_mesh_checkpoint']).resolve()
            if not checkpoint_path.is_relative_to(allowed_data):raise ValueError('Checkpoint must remain inside the active Library')
            metadata,arrays=mesh_checkpoint.verify(checkpoint_path,req,manifest['source_sha256'],revision,req['resume_checkpoint_sha256'],load_arrays=True)
            from types import SimpleNamespace
            mesh=SimpleNamespace(**{key:torch.from_numpy(value).cuda() for key,value in arrays.items()},
                voxel_size=metadata['voxel_size'])
            layout={name:slice(*indices) for name,indices in metadata['attr_layout'].items()}
            manifest.update(raw_triangles=metadata['geometry']['triangles'],inference_reused=True,
                native_checkpoint=dict(path=str(checkpoint_path),sha256=req['resume_checkpoint_sha256'],native_sha256=metadata['native_sha256']),
                resume_scope=metadata['resume_scope'])
            del arrays
        else:
            pipe = Trellis2ImageTo3DPipeline.from_pretrained(str(snapshot))
            pipe.low_vram = True; pipe.cuda()
            image = Image.open(req['image']).convert('RGBA')
            if req.get('supplied_alpha_input', False):
                if image.getextrema()[-1][0] == 255: raise ValueError('supplied_alpha_input requires a real non-opaque alpha mask')
                conditioned = pipe.preprocess_image(image)
            else:
                if not req.get('allow_existing_rmbg_evaluation', False): raise ValueError('Provide approved alpha input or separately authorize bundled RMBG evaluation')
                pipe.rembg_model.to(pipe.device)
                segmented = pipe.rembg_model(image.convert('RGB'))
                segmented.save(output / 'source_alpha.png')
                pipe.rembg_model.cpu()
                conditioned = pipe.preprocess_image(segmented)
            conditioned.save(output / 'conditioning.png')
            params = {'steps': req.get('steps', 12)}
            with torch.inference_mode():
                mesh = pipe.run(conditioned, seed=req['seed'], preprocess_image=False,
                                sparse_structure_sampler_params=params, shape_slat_sampler_params=params,
                                tex_slat_sampler_params=params, pipeline_type=pipeline_type)[0]
            print('STAGE Validate native geometry and sparse PBR before GLB finishing', flush=True)
            metadata=mesh_checkpoint.save(output,dict(vertices=mesh.vertices.detach().cpu().numpy(),
                faces=mesh.faces.detach().cpu().numpy(),attrs=mesh.attrs.detach().cpu().numpy(),coords=mesh.coords.detach().cpu().numpy()),
                req,manifest['source_sha256'],revision,pipe.pbr_attr_layout,mesh.voxel_size)
            manifest.update(raw_triangles=len(mesh.faces),inference_reused=False,
                native_checkpoint=dict(path=str(output/'mesh_checkpoint.json'),sha256=digest(output/'mesh_checkpoint.json'),native_sha256=metadata['native_sha256']))
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            layout=pipe.pbr_attr_layout
            for model in pipe.models.values(): model.cpu()
            pipe.image_cond_model.cpu()
            if pipe.rembg_model is not None: pipe.rembg_model.cpu()
            del pipe
        torch.cuda.empty_cache()
        with torch.inference_mode():
            print('STAGE GLB remesh, UV and native PBR finishing', flush=True)
            mesh.attrs = mesh.attrs.float()
            kwargs = dict(vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs, coords=mesh.coords,
                          attr_layout=layout, aabb=[[-0.5]*3, [0.5]*3],
                          decimation_target=req.get('export_triangle_target', 1_000_000), texture_size=req.get('texture_size', 2048),
                          remesh=True, remesh_band=1, remesh_project=0)
            signature = inspect.signature(o_voxel.postprocess.to_glb).parameters
            if 'grid_size' in signature: kwargs['grid_size'] = 512 if pipeline_type == '512' else 1024
            elif 'voxel_size' in signature: kwargs['voxel_size'] = mesh.voxel_size
            else: raise RuntimeError('Unknown local GLB exporter signature; do not guess')
            glb = o_voxel.postprocess.to_glb(**kwargs)
            glb.export(output / 'raw.glb')
        torch.cuda.synchronize()
        manifest.update({'status': 'GENERATED_NEEDS_REVIEW', 'peak_allocated_bytes': max(phase_peaks['allocated'], torch.cuda.max_memory_allocated()),
                         'peak_reserved_bytes': max(phase_peaks['reserved'], torch.cuda.max_memory_reserved()),
                         'peak_scope': 'whole-process Torch maxima aggregated across upstream resets; excludes CUDA context and other GPU apps',
                         'output_sha256': digest(output / 'raw.glb')})
    except BaseException as exc:
        manifest.update({'status': 'FAILED', 'error': str(exc), 'traceback': traceback.format_exc()})
        raise
    finally:
        manifest['duration_seconds'] = time.monotonic() - started
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
