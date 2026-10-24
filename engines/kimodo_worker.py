"""Text-to-motion with Kimodo-SOMA-RP-v1.2 (NVIDIA; code Apache-2.0, weights NVIDIA Open Model license), offline.

INFERENCE NOT YET TESTED. Runs in .local/envs/kimodo. Kimodo's own CLI (kimodo.scripts.generate) does the work; this
worker only points it at local files: the motion checkpoint, and the LLM2Vec text encoder whose Llama-3-8B-Instruct
base is a byte-identical local copy (scripts/install_kimodo.sh). The text encoder runs on the CPU
(TEXT_ENCODER_DEVICE=cpu, upstream's small-VRAM mode: < 3 GB of VRAM), the motion diffusion on the GPU.
Output: motion.npz (SOMA 77 joints) and motion.bvh (standard T-pose rest), 30 fps.

python kimodo_worker.py --request request.json
request: {"models_path", "prompt", "duration", "seed", "steps", "output"}
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

for key, value in {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'TEXT_ENCODER_MODE': 'local',
                   'TEXT_ENCODER_DEVICE': 'cpu', 'LOCAL_CACHE': 'true'}.items(): os.environ.setdefault(key, value)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    request = json.loads(Path(parser.parse_args().request).read_text(encoding='utf-8'))
    models = Path(request['models_path']); output = Path(request['output']); output.mkdir(parents=True, exist_ok=True)
    import torch
    import importlib
    loader = importlib.import_module('kimodo.model.load_model')  # the package re-exports a function of the same name
    loader.TEXT_ENCODER_PRESETS['llm2vec']['kwargs'].update(base_model_name_or_path=str(models / 'llm2vec-mntp'), peft_model_name_or_path=str(models / 'llm2vec-supervised'))
    loader._resolve_hf_model_path = lambda name: models / 'Kimodo-SOMA-RP-v1.2'
    from kimodo.scripts import generate
    started = time.monotonic(); torch.cuda.reset_peak_memory_stats()
    print('STAGE Kimodo / encode prompt (CPU) and generate motion', flush=True)
    sys.argv = ['kimodo_gen', request['prompt'], '--duration', str(request.get('duration', 4.0)), '--seed', str(int(request.get('seed', 42))),
                '--diffusion_steps', str(int(request.get('steps', 100))), '--output', str(output / 'motion'), '--bvh', '--bvh_standard_tpose']
    generate.main()
    bvh = output / 'motion.bvh'
    if not bvh.is_file(): raise RuntimeError('Kimodo did not write motion.bvh')
    report = dict(engine='kimodo-soma-rp-v1.2', prompt=request['prompt'], duration=float(request.get('duration', 4.0)), seed=int(request.get('seed', 42)), steps=int(request.get('steps', 100)),
                  bvh=str(bvh), npz=str(output / 'motion.npz'), seconds=round(time.monotonic() - started, 1), peak_vram_gib=round(torch.cuda.max_memory_allocated() / 2**30, 2),
                  text_encoder='LLM2Vec Llama-3-8B-Instruct on CPU', skeleton='SOMA 77 joints')
    (output / 'motion_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('RESULT ' + json.dumps(report), flush=True)


if __name__ == '__main__':
    sys.exit(main())
