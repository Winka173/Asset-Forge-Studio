"""Texture a shape-only mesh from its concept image with MV-Adapter (Apache-2.0), fully offline.

Used after TripoSG, TRELLIS v1 and Hunyuan3D-2.1 shape stages so every engine delivers a textured GLB.
Six geometry-conditioned SDXL views (768 px) are generated from the concept, then projected onto a UV atlas,
upscaled (RealESRGAN x2) and inpainted (LaMa). CV-CUDA ops run on OpenCV (engines/mvadapter_opencv_ops.patch).

python mvadapter_texture_worker.py --request request.json
request: {"engine_path", "mesh", "image", "output_dir", "seed", "uv_size", "steps"}
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('MVADAPTER_SDXL_VARIANT', 'fp16')  # the local SDXL base cache holds the fp16 weights
os.environ.setdefault('MVADAPTER_PB_BACKEND', 'triton')  # Poisson blending without a JIT C++ build
os.environ.setdefault('MVADAPTER_SEQUENTIAL_CFG', '1')  # guidance 3.0 within 16 GB: halves run in turn, one shared reference state


def reduce_for_uv(source, output, max_faces):
    """UV unwrapping needs a manifold mesh of practical size: quadric-decimate to a texture-master budget, then
    merge duplicate vertices and repair non-manifold edges/vertices (no smoothing, so the silhouette is kept)."""
    import open3d as o3d, numpy as np, trimesh
    from mvadapter.utils.mesh_utils.mesh_process import merge_close_vertices, mesh_to_meshlab, meshlab_to_mesh, remove_isolated_pieces, repair_non_manifold
    mesh = trimesh.load(source, force='mesh', process=False)
    vertices, faces = np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.int64)
    if len(faces) > max_faces:
        print(f'STAGE MV-Adapter / reduce {len(faces):,} faces to {max_faces:,} for UV unwrapping', flush=True)
        work = o3d.t.geometry.TriangleMesh(o3d.core.Device('CPU:0'))
        work.vertex.positions = o3d.core.Tensor(vertices); work.triangle.indices = o3d.core.Tensor(faces)
        work = work.simplify_quadric_decimation(target_reduction=1.0 - max_faces / len(faces))
        vertices, faces = work.vertex.positions.numpy(), work.triangle.indices.numpy()
    print('STAGE MV-Adapter / repair mesh for UV unwrapping', flush=True)
    ms = mesh_to_meshlab(vertices, faces); merge_close_vertices(ms)
    # Floating fragments (TripoSG left ~100 around the base) become ragged texture speckles; parts under 0.2% of the faces go.
    remove_isolated_pieces(ms, mincomponentsize=max(50, int(len(faces) * 0.002))); repair_non_manifold(ms)
    vertices, faces, _ = meshlab_to_mesh(ms)
    target = output / 'shape_for_texture.glb'; trimesh.Trimesh(vertices, faces, process=False).export(target)
    return target


def unwrap(engine, source, target):
    """UV-unwrap in a separate CPU process while the GPU paints the views (same function the texture stage calls)."""
    sys.path.insert(0, engine)
    from mvadapter.utils.mesh_utils.mesh_process import process_raw
    process_raw(source, target, preprocess=False)
    return target


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    request = json.loads(Path(parser.parse_args().request).read_text(encoding='utf-8'))
    engine = Path(request['engine_path']); output = Path(request['output_dir']); output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(engine)); os.chdir(engine)
    import torch
    from PIL import Image
    from mvadapter.pipelines.pipeline_texture import ModProcessConfig, TexturePipeline
    from mvadapter.utils import make_image_grid
    from scripts.inference_ig2mv_sdxl import prepare_pipeline, run_pipeline

    started = time.monotonic()
    mesh_path = reduce_for_uv(Path(request['mesh']), output, int(request.get('max_faces', 300000)))
    if request.get('prepare_only'):  # CPU only: the cleaned, budgeted mesh for another texturer (TRELLIS.2)
        (output / 'prepare_report.json').write_text(json.dumps(dict(mesh=str(mesh_path), seconds=round(time.monotonic() - started, 1)), indent=2), encoding='utf-8')
        return
    torch.cuda.reset_peak_memory_stats()
    stage = lambda text: print('STAGE ' + text, flush=True)
    timings = {'prepare_mesh': round(time.monotonic() - started, 1)}
    from concurrent.futures import ProcessPoolExecutor
    unwrapped = str(mesh_path).replace('.glb', '_unwarp.glb')
    pool = ProcessPoolExecutor(max_workers=1); unwrap_job = pool.submit(unwrap, str(engine), str(mesh_path), unwrapped)
    tick = time.monotonic()
    views = output / 'views.png'; views_peak = 0
    # A retry after a projection failure reuses the already generated views (same seed and inputs).
    if not (request.get('reuse_views') and views.is_file()):
        stage('MV-Adapter / load SDXL multi-view adapter')
        pipe = prepare_pipeline(base_model='stabilityai/stable-diffusion-xl-base-1.0', vae_model='madebyollin/sdxl-vae-fp16-fix', unet_model=None, lora_model=None,
                                adapter_path='huanngzh/mv-adapter', scheduler=None, num_views=6, device='cuda', dtype=torch.float16)
        # Six 768 px views overflow a 16 GB card (each step spilled to shared memory, ~80 s). Accelerate offload
        # breaks MV-Adapter's attention processors, so only the two text encoders leave the GPU between uses;
        # steps, resolution and views stay the same.
        encoders = [pipe.text_encoder, pipe.text_encoder_2]; encode = pipe.encode_prompt
        def encode_on_demand(*args, **kwargs):
            for module in encoders: module.to('cuda')
            try: return encode(*args, **kwargs)
            finally:
                for module in encoders: module.to('cpu')
                torch.cuda.empty_cache()
        pipe.encode_prompt = encode_on_demand
        # Diffusers infers the execution device from the first component; with the encoders parked on the CPU pin it to the GPU.
        type(pipe)._execution_device = property(lambda self: torch.device('cuda'))
        for module in encoders: module.to('cpu')
        torch.cuda.empty_cache(); pipe.enable_vae_tiling()
        image = Image.open(request['image']).convert('RGBA')
        flat = Image.new('RGB', image.size, (255, 255, 255)); flat.paste(image, mask=image.split()[-1])  # concept is already cut out
        stage('MV-Adapter / six geometry-guided views')
        images, _, _, _ = run_pipeline(pipe, mesh_path=str(mesh_path), num_views=6, text=request.get('text', 'high quality game asset, clean albedo'), image=flat,
                                       height=768, width=768, num_inference_steps=int(request.get('steps', 50)), guidance_scale=float(request.get('guidance', 3.0)), seed=int(request.get('seed', 42)),
                                       reference_conditioning_scale=1.0, negative_prompt='watermark, ugly, deformed, noisy, blurry, low contrast, shadows, lighting', device='cuda', remove_bg_fn=None)
        views = output / 'views.png'; make_image_grid(images, rows=1).save(views)
        views_peak = torch.cuda.max_memory_allocated()
        del pipe; torch.cuda.empty_cache()
    timings['views'] = round(time.monotonic() - tick, 1); tick = time.monotonic()
    unwrap_job.result(); pool.shutdown(); timings['wait_for_uv'] = round(time.monotonic() - tick, 1); tick = time.monotonic()
    stage('MV-Adapter / project views to UV texture')
    texture = TexturePipeline(upscaler_ckpt_path=str(engine / 'checkpoints/RealESRGAN_x2plus.pth'), inpaint_ckpt_path=str(engine / 'checkpoints/big-lama.pt'), device='cuda')
    result = texture(mesh_path=unwrapped, save_dir=str(output), save_name='textured', uv_unwarp=False, preprocess_mesh=False, uv_size=int(request.get('uv_size', 4096)),
                     rgb_path=str(views), rgb_process_config=ModProcessConfig(view_upscale=True, inpaint_mode='view'), camera_azimuth_deg=[x - 90 for x in [0, 90, 180, 270, 180, 180]])
    shaded = Path(result.shaded_model_save_path); timings['projection'] = round(time.monotonic() - tick, 1); tick = time.monotonic()
    # Colour fidelity to the concept + roughness map; the untouched MV-Adapter GLB stays next to it.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from engines.texture_finish import finish
    glb = output / 'textured_finished.glb'; material = finish(shaded, request['image'], glb); timings['finish'] = round(time.monotonic() - tick, 1)
    report = dict(engine='mvadapter_texture', textured_glb=str(glb), unfinished_glb=str(shaded), material=material, views=str(views), seconds=round(time.monotonic() - started, 1),
                  peak_vram_gib=round(max(views_peak, torch.cuda.max_memory_allocated()) / 2**30, 2), uv_size=int(request.get('uv_size', 4096)), seed=int(request.get('seed', 42)), timings=timings)
    (output / 'texture_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('RESULT ' + json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
