"""Hunyuan3D-2.1 shape DiT (Tencent Hunyuan Community License: not licensed in the EU, UK or South Korea), offline.

Same contract as the other shape workers: new immutable output dir with source_alpha.png, raw.glb (Y-up) and
generation.json. Texturing is a separate stage (engines/textured_shape_worker.py); Hunyuan3D-Paint is not used.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_XET='1', PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    req = json.loads(Path(parser.parse_args().request).read_text(encoding='utf-8-sig'))
    output = Path(req['output']).resolve(); allowed = Path(os.environ.get('AFS_DATA', Path(__file__).resolve().parents[1] / 'data')).resolve()
    if output.exists() or not output.is_relative_to(allowed): raise ValueError('Require new immutable output inside the data directory')
    output.mkdir(parents=True)
    os.environ.setdefault('HY3DGEN_MODELS', req['models']); os.environ.setdefault('HF_HOME', req.get('hf_home', ''))
    sys.path.insert(0, str(Path(req['engine_path']) / 'hy3dshape'))
    report = dict(status='RUNNING', engine='hunyuan3d21', request=req, network='OFFLINE', input_sha256=digest(req['image']), license='Tencent Hunyuan Community License (excludes EU, UK, South Korea)', timings={})
    import torch
    from PIL import Image
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
    from hy3dshape.postprocessors import DegenerateFaceRemover, FloaterRemover
    image = Image.open(req['image']).convert('RGBA')
    if image.getextrema()[-1][0] == 255: raise ValueError('Real alpha mask required; no implicit segmentation')
    image.save(output / 'source_alpha.png')
    started = time.monotonic(); torch.cuda.reset_peak_memory_stats()
    print('STAGE Hunyuan3D-2.1 / load shape DiT', flush=True)
    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained('tencent/Hunyuan3D-2.1', subfolder='hunyuan3d-dit-v2-1', device='cuda', dtype=torch.float16)
    report['timings']['load'] = time.monotonic() - started
    print('STAGE Hunyuan3D-2.1 / generate shape', flush=True); tick = time.monotonic()
    mesh = pipe(image=image, num_inference_steps=int(req.get('steps', 50)), guidance_scale=5.0, octree_resolution=int(req.get('octree_resolution', 384)),
                num_chunks=20000, generator=torch.Generator().manual_seed(int(req['seed'])))[0]
    report['timings']['generate'] = time.monotonic() - tick
    mesh = DegenerateFaceRemover()(FloaterRemover()(mesh))
    mesh.export(output / 'raw.glb')
    report.update(status='GENERATED_NEEDS_REVIEW', triangles=len(mesh.faces), vertices=len(mesh.vertices), peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                  duration_seconds=time.monotonic() - started, output_sha256=digest(output / 'raw.glb'), pbr='NOT_AVAILABLE_SHAPE_STAGE')
    (output / 'generation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('RESULT ' + json.dumps({k: report[k] for k in ('triangles', 'duration_seconds', 'peak_allocated_bytes')}), flush=True)


if __name__ == '__main__':
    main()
