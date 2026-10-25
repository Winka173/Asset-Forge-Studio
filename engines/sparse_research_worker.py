"""Offline TRELLIS v1 / original-normal-route Hi3DGen experimental inference.

Uses upstream learned geometry decoders and samplers, stage CPU offload and
Blender for downstream rendering. No neural renderer, paid endpoint or fake mesh.
"""
import argparse
import gc
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                  DO_NOT_TRACK='1', SPCONV_ALGO='native', ATTN_BACKEND='flash_attn')
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
# Engine sources (.local) and weights (models) live in the workspace; the packaged app runs this code from a temp folder.
WORKSPACE = Path(os.environ.get('AFS_WORKSPACE') or ROOT)


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    req = json.loads(Path(parser.parse_args().request).read_text(encoding='utf-8-sig'))
    engine = req['engine']; output = Path(req['output']).resolve()
    if engine not in ('trellis_v1', 'hi3dgen'): raise ValueError('Unknown research engine')
    allowed = Path(os.environ.get('AFS_DATA', ROOT / 'data')).resolve()  # the configured library, like the other engine workers
    if output.exists() or not output.is_relative_to(allowed):
        raise ValueError('Require new immutable output inside workspace data')
    output.mkdir(parents=True)
    report = dict(status='RUNNING', engine=engine, request=req, network='OFFLINE',
                  input_sha256=digest(req['image']), script_sha256=digest(__file__),
                  mesh_quality_parity='NOT_TESTED', human_score=None, commercial_approval='NEEDS_REVIEW',
                  pbr='NOT_AVAILABLE_GEOMETRY_TRIAL', timings={})
    started = time.monotonic()
    try:
        import torch
        import numpy as np
        import trimesh
        from PIL import Image
        from torchvision import transforms
        source = Path(req['engine_path']); sys.path.insert(0, str(source))
        report.update(torch=str(torch.__version__), cuda=torch.version.cuda, gpu=torch.cuda.get_device_name())
        torch.cuda.reset_peak_memory_stats()
        def release():
            gc.collect(); torch.cuda.empty_cache()
        def stage(name, fn):
            print('STAGE ' + name, flush=True); tick = time.monotonic()
            result = fn(); torch.cuda.synchronize()
            report['timings'][name] = time.monotonic() - tick
            return result
        image = Image.open(req['image']).convert('RGBA')
        if image.getextrema()[-1][0] == 255:
            raise ValueError('Real alpha mask required; no implicit segmentation download')
        image.save(output / 'source_alpha.png')
        if engine == 'trellis_v1':
            from trellis.pipelines import TrellisImageTo3DPipeline as Pipeline
        else:
            from hi3dgen.pipelines import Hi3DGenPipeline as Pipeline
        # Load local DINO code with pretrained=False, then exact local register checkpoint.
        # This prevents torch.hub's implicit network fetch and keeps model load weights-only.
        def init_dino(self, name):
            dino = torch.hub.load(str(WORKSPACE / '.local/engines/dinov2'), name, source='local', pretrained=False)
            checkpoint = WORKSPACE / 'models/dinov2/dinov2_vitl14_reg4_pretrain.pth'
            dino.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True), strict=True)
            dino.eval(); self.models['image_cond_model'] = dino
            self.image_cond_model_transform = transforms.Compose([
                transforms.Normalize(mean=[.485, .456, .406], std=[.229, .224, .225])])
        Pipeline._init_image_cond_model = init_dino
        # Official device property follows first model; all inactive stages intentionally
        # remain on CPU, so make the intended compute device explicit in this subclass.
        class OffloadedPipeline(Pipeline):
            @property
            def device(self): return torch.device('cuda')
        pipe = stage('load_models', lambda: Pipeline.from_pretrained(req['weights']))
        pipe.__class__ = OffloadedPipeline
        for key in list(pipe.models):
            if key in ('slat_decoder_gs', 'slat_decoder_rf'): del pipe.models[key]
        release()
        image = pipe.preprocess_image(image, **({'resolution': 1024} if engine == 'hi3dgen' else {}))
        if engine == 'hi3dgen':
            # Original official configuration predates the unresolved NiRNE demo route.
            sys.path.insert(0, str(WORKSPACE / '.local/engines/StableNormal'))
            from stablenormal.pipeline_yoso_normal import YOSONormalsPipeline
            from diffusers import AutoencoderKL, UNet2DConditionModel
            import importlib.util
            weights = WORKSPACE / 'models/hi3dgen_normal'
            local_code = weights / 'controlnet/controlnetvae.py'
            spec = importlib.util.spec_from_file_location('afs_audited_controlnet', local_code)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            control = module.ControlNetVAEModel.from_pretrained(str(weights / 'controlnet'), variant='fp16', torch_dtype=torch.float16, local_files_only=True)
            normal = YOSONormalsPipeline(
                vae=AutoencoderKL.from_pretrained(str(weights / 'vae'), variant='fp16', torch_dtype=torch.float16, local_files_only=True),
                unet=UNet2DConditionModel.from_pretrained(str(weights / 'unet'), variant='fp16', torch_dtype=torch.float16, local_files_only=True),
                controlnet=control, safety_checker=None, t_start=0).to('cuda')
            # The official Predictor handles RGBA mask and [-1,1] -> RGB normal mapping.
            import importlib.util
            spec = importlib.util.spec_from_file_location('afs_stablenormal_hub', WORKSPACE / '.local/engines/StableNormal/hubconf.py')
            hub = importlib.util.module_from_spec(spec); spec.loader.exec_module(hub)
            predictor = hub.Predictor(normal)
            image = stage('normal_prediction', lambda: predictor(image, resolution=768, match_input_resolution=True, data_type='object'))
            image.save(output / 'predicted_normals.png')
            normal.to('cpu'); del predictor, normal, control; release()
        image.save(output / 'conditioning.png')
        torch.manual_seed(req['seed'])
        with torch.inference_mode():
            dino = pipe.models['image_cond_model'].cuda()
            cond = stage('image_encoding', lambda: pipe.get_cond([image]))
            dino.cpu(); release()
            flow = pipe.models['sparse_structure_flow_model'].cuda()
            noise = torch.randn(1, flow.in_channels, *([flow.resolution] * 3), device='cuda')
            params = {**pipe.sparse_structure_sampler_params, 'steps': req.get('steps', 50)}
            sampled = stage('sparse_structure_sampling', lambda: pipe.sparse_structure_sampler.sample(flow, noise, **cond, **params, verbose=True))
            latent = sampled.samples if hasattr(sampled, 'samples') else sampled['samples']
            flow.cpu(); del noise, sampled; release()
            decoder = pipe.models['sparse_structure_decoder'].cuda()
            coords = stage('sparse_structure_decode', lambda: torch.argwhere(decoder(latent) > 0)[:, [0, 2, 3, 4]].int())
            decoder.cpu(); del latent; release()
            report['active_voxels'] = int(len(coords))
            flow = pipe.models['slat_flow_model'].cuda()
            slat = stage('slat_sampling', lambda: pipe.sample_slat(cond, coords, {'steps': req.get('slat_steps', 24)}))
            flow.cpu(); release()
            decoder = pipe.models['slat_decoder_mesh'].cuda()
            mesh = stage('mesh_decode', lambda: pipe.decode_slat(slat, formats=['mesh'])['mesh'][0])
            vertices = mesh.vertices.detach().float().cpu().numpy()
            faces = mesh.faces.detach().cpu().numpy()
        if len(faces) == 0 or not np.isfinite(vertices).all(): raise ValueError('Invalid native geometry output')
        np.savez_compressed(output / 'native_geometry.npz', vertices=vertices, faces=faces)
        # Native geometry is Z-up; glTF is Y-up. Keep raw NPZ unchanged and rotate export.
        exported = trimesh.Trimesh(vertices=vertices.copy(), faces=faces, process=False)
        exported.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
        exported.export(output / 'raw.glb')
        report.update(status='GENERATED_NEEDS_REVIEW', triangles=len(faces), native_triangles=len(faces),
                      peak_allocated_bytes=torch.cuda.max_memory_allocated(), peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                      torch_memory_scope='whole worker peak, no reset between stages', output_sha256=digest(output / 'raw.glb'),
                      source_sha256={p.relative_to(source).as_posix(): digest(p) for p in source.rglob('*.py') if '.git' not in p.parts})
    except BaseException as exc:
        report.update(status='FAILED', error=str(exc), traceback=traceback.format_exc()); raise
    finally:
        report['duration_seconds'] = time.monotonic() - started
        (output / 'generation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
