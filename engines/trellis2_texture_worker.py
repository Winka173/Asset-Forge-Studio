"""Texture a shape-only mesh with the TRELLIS.2 texturing pipeline (MIT; upstream microsoft/TRELLIS.2), fully offline.

Experimental alternative to MV-Adapter for TripoSG, TRELLIS v1 and Hunyuan3D-2.1 shapes. INFERENCE NOT YET TESTED.
The mesh is voxelised, a texture latent is sampled from the concept (DINOv3 conditioning) and decoded to native PBR:
base colour, metallic and roughness, baked to a UV atlas (CuMesh unwrap, nvdiffrast raster). No colour finish pass:
the model's own material channels are kept.

Runs in the TRELLIS.2 bundle's venv with the upstream source (the bundle's fork predates the texturing pipeline);
DINOv3 and RMBG-2.0 load from the bundle's MODELS folder, the checkpoints from its offline HF cache.

python trellis2_texture_worker.py --request request.json
request: {"upstream_path", "models_path", "flexgemm_path", "mesh", "image", "output_dir", "seed", "uv_size", "steps", "resolution"}
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

for key, value in {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'TORCHDYNAMO_DISABLE': '1',
                   'OPENCV_IO_ENABLE_OPENEXR': '1', 'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True'}.items(): os.environ.setdefault(key, value)


def local_config(models, output):
    """The published texturing_pipeline.json with every model pointing at local files (absolute paths load offline)."""
    snapshot = next((models / 'hub/models--microsoft--TRELLIS.2-4B/snapshots').glob('*/texturing_pipeline.json')).parent
    config = json.loads((snapshot / 'texturing_pipeline.json').read_text(encoding='utf-8'))
    args = config['args']
    args['models'] = {name: str(snapshot / path) for name, path in args['models'].items()}
    args['image_cond_model']['args']['model_name'] = str(models / 'dinov3')
    args['rembg_model']['args']['model_name'] = str(models / 'RMBG-2.0')
    (output / 'texturing_pipeline.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    return snapshot.name


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    request = json.loads(Path(parser.parse_args().request).read_text(encoding='utf-8'))
    output = Path(request['output_dir']); output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, request['upstream_path'])
    import numpy as np, torch, trimesh
    from PIL import Image
    from trellis2.pipelines import Trellis2TexturingPipeline
    # The bundle's flex_gemm wheel ships only CUDA kernels; explicit GEMM needs > 16 GB at 1024. Load the upstream
    # FlexGEMM triton kernels (pure Python) at runtime so the memory-lean default algorithm works; the bundle is untouched.
    import flex_gemm.kernels as flex_kernels
    if not hasattr(flex_kernels, 'triton'):
        flex_kernels.__path__.append(str(Path(request['flexgemm_path']) / 'flex_gemm/kernels'))
        from flex_gemm.kernels import triton as flex_triton; flex_kernels.triton = flex_triton

    started = time.monotonic(); torch.cuda.reset_peak_memory_stats(); timings = {}
    stage = lambda text: print('STAGE TRELLIS.2 texturing / ' + text, flush=True)
    revision = local_config(Path(request['models_path']), output)
    source = trimesh.load(request['mesh'], force='mesh', process=False)
    low, high = source.bounds; center = (low + high) / 2; scale = 0.99999 / float((high - low).max())
    stage('load models')
    pipe = Trellis2TexturingPipeline.from_pretrained(str(output), config_file='texturing_pipeline.json')
    pipe.low_vram = True; pipe.cuda()
    image = Image.open(request['image']).convert('RGBA')
    params = {'steps': int(request['steps'])} if request.get('steps') else {}
    stage('voxelise shape, sample and bake PBR texture'); tick = time.monotonic()
    with torch.inference_mode():
        textured = pipe.run(trimesh.Trimesh(source.vertices, source.faces, process=False), image, seed=int(request.get('seed', 42)), tex_slat_sampler_params=params,
                            resolution=int(request.get('resolution', 1024)), texture_size=int(request.get('uv_size', 4096)))
    timings['texture'] = round(time.monotonic() - tick, 1)
    # The pipeline works in a unit cube; restore the shape stage's size and position.
    textured.vertices = np.asarray(textured.vertices) / scale + center
    glb = output / 'textured_trellis2.glb'; textured.export(glb)
    report = dict(textured_glb=str(glb), texturer='trellis2_texturing', checkpoint_revision=revision, seconds=round(time.monotonic() - started, 1),
                  peak_vram_gib=round(torch.cuda.max_memory_allocated() / 2**30, 2), uv_size=int(request.get('uv_size', 4096)), seed=int(request.get('seed', 42)),
                  resolution=int(request.get('resolution', 1024)), material='native PBR: base colour, metallic, roughness', timings=timings)
    (output / 'texture_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('RESULT ' + json.dumps(report), flush=True)


if __name__ == '__main__':
    sys.exit(main())
