"""Offline FLUX.2 [klein] 4B concept generation from existing local weights; no automatic download.

Replaces the SDXL worker (2026-10-26): on six prompts that SDXL got wrong (house drawn as a castle, knight armed when asked for
empty hands, scenery around the asset) klein judged 12/12 against 11/12 for SDXL and Z-Image-Turbo and was the only model
that drew one clean object on a plain background. It reads a natural-language prompt (no 77-token CLIP windows), runs the
distilled 4-step schedule, and takes the project style anchor as a native reference image (no IP-Adapter).
"""
import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')
sys.dont_write_bytecode = True


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    req = json.loads(Path(parser.parse_args().request).read_text(encoding='utf-8-sig'))
    output = Path(req['output']).resolve(); root = Path(__file__).resolve().parents[1]
    allowed = Path(os.environ.get('AFS_DATA', root / 'data')).resolve()
    if output.exists() or not output.is_relative_to(allowed): raise ValueError('New immutable output required')
    output.mkdir(parents=True); started = time.monotonic()
    report = dict(status='RUNNING', engine='flux2_klein_local', request=req, script_sha256=digest(__file__), network='OFFLINE',
                  purpose='concept_preview_requires_user_approval', license='Apache-2.0 (FLUX.2 [klein] 4B)')
    try:
        weights = Path(req['weights'])
        # Quality Lock: the checkpoint and this worker must be the ones the locked EffectiveGenerationConfig names.
        locked = (req.get('effective_config') or {}).get('checkpoint') or {}
        report['weight_sha256'] = {p.relative_to(weights).as_posix(): digest(p) for p in sorted(weights.rglob('*.safetensors'))}
        if locked.get('files') and sorted(report['weight_sha256'].values()) != sorted(locked['files'].values()):
            raise ValueError('Concept weights changed after admission; no generation started')
        import torch
        from diffusers import Flux2KleinPipeline
        print('STAGE load_klein', flush=True)
        torch.cuda.reset_peak_memory_stats()
        pipe = Flux2KleinPipeline.from_pretrained(str(weights), torch_dtype=torch.bfloat16, local_files_only=True)
        pipe.enable_model_cpu_offload()
        reference = None
        style = req.get('style_anchor')
        if style:
            from PIL import Image
            anchor_path = Path(style['path'])
            if digest(anchor_path) != style['sha256']: raise ValueError('Style anchor image changed after admission; no generation started')
            reference = Image.open(anchor_path).convert('RGB')
            report['style_anchor'] = dict(sha256=style['sha256'], mode='native reference image')
        steps = int(req.get('steps') or 4)
        def progress(pipeline, step, timestep, values):
            print(f'Concept denoising: {round((step + 1) * 100 / steps)}%| step {step + 1}/{steps}', flush=True)
            return values
        print('STAGE concept_denoising', flush=True)
        with torch.inference_mode():
            image = pipe(prompt=req['prompt'], height=req.get('height', req.get('size', 1024)), width=req.get('width', req.get('size', 1024)),
                         num_inference_steps=steps, guidance_scale=float(req.get('guidance_scale', 1.0)),
                         generator=torch.Generator(device='cpu').manual_seed(req['seed']), callback_on_step_end=progress,
                         **(dict(image=[reference]) if reference is not None else {})).images[0]
        image.save(output / 'concept.png')
        report.update(status='GENERATED_NEEDS_REVIEW', output_sha256=digest(output / 'concept.png'),
                      peak_allocated_bytes=torch.cuda.max_memory_allocated(), peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                      torch=str(torch.__version__), gpu=torch.cuda.get_device_name(), dimensions=list(image.size))
    except BaseException as exc:
        report.update(status='FAILED', quality_guard_blocked=False, error=str(exc), traceback=traceback.format_exc()); raise
    finally:
        report['duration_seconds'] = time.monotonic() - started
        (output / 'generation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
