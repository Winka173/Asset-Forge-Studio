"""TripoSG shape inference with approved supplied alpha, offline weights and native CPU marching cubes.

Invoked in an isolated environment. No RMBG, cloud inference, or automatic weight download.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'
sys.dont_write_bytecode = True


def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    args = parser.parse_args()
    req = json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
    root = Path(__file__).resolve().parents[1]
    output = Path(req['output']).resolve()
    allowed_data = Path(os.environ.get('AFS_DATA', root / 'data')).resolve()
    if output.exists() or not output.is_relative_to(allowed_data): raise ValueError('Require new immutable configured data directory')
    source = Path(req['engine_path']).resolve(); sys.path.insert(0, str(source))
    output.mkdir(parents=True)
    report = {'status': 'RUNNING', 'engine': 'triposg', 'request': req, 'input_sha256': digest(req['image']),
              'script_sha256': digest(__file__), 'network': 'OFFLINE', 'pbr': 'NOT_AVAILABLE_SHAPE_ONLY', 'mesh_quality_parity': 'NOT_TESTED'}
    started = time.monotonic()
    try:
        from PIL import Image
        import torch
        import numpy as np
        import trimesh
        from triposg.pipelines.pipeline_triposg import TripoSGPipeline
        image = Image.open(req['image']).convert('RGBA')
        if image.getextrema()[-1][0] == 255: raise ValueError('Supply a reviewed alpha input; no implicit RMBG download or unmasked background')
        # TripoSG expects RGB over a white background. The exact conditioned image is retained.
        rgb = Image.new('RGB', image.size, 'white'); rgb.paste(image, mask=image.getchannel('A'))
        rgb.save(output / 'conditioning.png')
        weights = Path(req['weights']).resolve()
        report['weight_sha256'] = {p.relative_to(weights).as_posix(): digest(p) for p in weights.rglob('*.safetensors')}
        report['source_sha256'] = {p.relative_to(source).as_posix(): digest(p) for p in (source / 'triposg').rglob('*.py')}
        report['torch'] = str(torch.__version__); report['cuda'] = torch.version.cuda; report['gpu'] = torch.cuda.get_device_name()
        free, total = torch.cuda.mem_get_info()
        report['free_vram_start_bytes'] = free
        if free < req.get('min_free_vram_gb', 8) * 1024**3: raise RuntimeError('Memory guard: less than 8 GiB free; close GPU applications before retry')
        torch.cuda.reset_peak_memory_stats()
        pipe = TripoSGPipeline.from_pretrained(str(weights), torch_dtype=torch.float16, local_files_only=True)
        pipe.to('cuda')
        native_decode = pipe.vae._decode
        def chunked_decode(*args, **kwargs):
            kwargs.setdefault('num_chunks', req.get('decode_chunk_size', 10000))
            return native_decode(*args, **kwargs)
        pipe.vae._decode = chunked_decode
        # Upstream hierarchical decoder uses true neural SDF samples + CPU marching cubes.
        # This avoids a required diso CUDA compiler while preserving real model inference.
        with torch.inference_mode():
            result = pipe(image=rgb, generator=torch.Generator(device='cuda').manual_seed(req['seed']),
                          num_inference_steps=req.get('steps', 50), guidance_scale=req.get('guidance_scale', 7.0),
                          use_flash_decoder=False, dense_octree_depth=req.get('dense_depth', 7), hierarchical_octree_depth=req.get('octree_depth', 9))
        v, f = result.samples[0]
        if v is None or f is None or not len(f) or not np.isfinite(v).all(): raise RuntimeError('Decoder returned invalid/empty mesh')
        mesh = trimesh.Trimesh(np.asarray(v, dtype=np.float32), np.asarray(f), process=False)
        mesh.export(output / 'raw.glb')
        torch.cuda.synchronize()
        report.update({'status': 'GENERATED_NEEDS_REVIEW', 'triangles': len(mesh.faces),
                       'peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'peak_reserved_bytes': torch.cuda.max_memory_reserved(),
                       'output_sha256': digest(output / 'raw.glb')})
    except BaseException as exc:
        report.update({'status': 'FAILED', 'error': str(exc), 'traceback': traceback.format_exc()}); raise
    finally:
        report['duration_seconds'] = time.monotonic() - started
        (output / 'generation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
