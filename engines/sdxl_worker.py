"""Offline SDXL concept generation from existing local weights; no automatic download."""
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
    report = dict(status='RUNNING', engine='sdxl_local', request=req, script_sha256=digest(__file__), network='OFFLINE',
                  model_revision='462165984030d82259a11f4367a4eed129e94a7b', purpose='concept_preview_requires_user_approval',
                  license='CreativeML Open RAIL++-M; code Apache-2.0; use restrictions apply')
    try:
        import torch
        from diffusers import StableDiffusionXLPipeline, DPMSolverMultistepScheduler
        print('STAGE load_sdxl', flush=True)
        torch.cuda.reset_peak_memory_stats()
        weights = Path(req['weights'])
        report['weight_sha256'] = {p.relative_to(weights).as_posix(): digest(p) for p in weights.rglob('*.safetensors')}
        pipe = StableDiffusionXLPipeline.from_pretrained(str(weights), variant='fp16', torch_dtype=torch.float16,
                use_safetensors=True, local_files_only=True, add_watermarker=False)
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, algorithm_type='dpmsolver++', use_karras_sigmas=True)
        pipe.enable_model_cpu_offload(); pipe.vae.enable_slicing(); pipe.vae.enable_tiling()
        prompt = req['prompt']
        negative = req.get('negative_prompt', 'text, watermark, logo, collage, multiple objects, cropped, cut off, blurry, low quality, floating parts, broken perspective')
        # Encode all prompt tokens in CLIP windows, retaining BOS/EOS per window.
        # This is explicit long-prompt conditioning, not silent tokenizer truncation.
        def encode(text, chunks):
            embeddings, pools = [], []
            for tokenizer, encoder in [(pipe.tokenizer, pipe.text_encoder), (pipe.tokenizer_2, pipe.text_encoder_2)]:
                tokens = tokenizer(text, add_special_tokens=False).input_ids
                windows, pooled = [], []
                encoder.to('cuda')
                for i in range(chunks):
                    ids = [tokenizer.bos_token_id] + tokens[i*75:(i+1)*75] + [tokenizer.eos_token_id]
                    ids += [tokenizer.pad_token_id] * (77-len(ids))
                    result = encoder(torch.tensor([ids], device='cuda'), output_hidden_states=True)
                    windows.append(result.hidden_states[-2])
                    if result[0].ndim == 2: pooled.append(result[0])
                embeddings.append(torch.cat(windows, dim=1)); pools.append(torch.stack(pooled).mean(0) if pooled else None)
                encoder.to('cpu'); torch.cuda.empty_cache()
            return torch.cat(embeddings, dim=-1), pools[-1]
        chunks = max(1, *( (len(t(text, add_special_tokens=False).input_ids)+74)//75 for t in [pipe.tokenizer,pipe.tokenizer_2] for text in [prompt,negative]))
        if chunks > 64: raise ValueError('Concept conditioning exceeds 4800 CLIP tokens; source remains saved, no silent truncation')
        with torch.inference_mode():
            print('STAGE encode_prompt', flush=True)
            embeds, pooled = encode(prompt, chunks); neg_embeds, neg_pooled = encode(negative, chunks)
            report['prompt_encoding'] = dict(chunks=chunks, tokens_not_truncated=True, pooled='mean across CLIP-2 chunks', experimental_long_prompt=chunks>1)
            def progress(pipeline, step, timestep, values):
                print(f'Concept denoising: {round((step+1)*100/req["steps"])}%| step {step+1}/{req["steps"]}', flush=True)
                return values
            print('STAGE concept_denoising', flush=True)
            image = pipe(prompt_embeds=embeds, pooled_prompt_embeds=pooled, negative_prompt_embeds=neg_embeds,
                         negative_pooled_prompt_embeds=neg_pooled, height=req.get('size',1024), width=req.get('size',1024),
                         num_inference_steps=req['steps'], guidance_scale=req.get('guidance_scale',7),
                         generator=torch.Generator(device='cpu').manual_seed(req['seed']), callback_on_step_end=progress).images[0]
        image.save(output / 'concept.png')
        report.update(status='GENERATED_NEEDS_REVIEW', output_sha256=digest(output/'concept.png'),
                      peak_allocated_bytes=torch.cuda.max_memory_allocated(), peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                      torch=str(torch.__version__), gpu=torch.cuda.get_device_name(), dimensions=list(image.size))
    except BaseException as exc:
        report.update(status='FAILED', error=str(exc), traceback=traceback.format_exc()); raise
    finally:
        report['duration_seconds'] = time.monotonic()-started
        (output/'generation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__ == '__main__': main()
