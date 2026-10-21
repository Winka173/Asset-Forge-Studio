"""Run explicitly approved existing community engine offline, with checkout-wide GPU lock."""
import argparse
import json
import os
import subprocess
import time
import uuid
from contextlib import ExitStack
from pathlib import Path

from apps.api import jobs, store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--pipeline', choices=['512', '1024_cascade'], default='512')
    parser.add_argument('--allow-community-evaluation', action='store_true')
    parser.add_argument('--image')
    parser.add_argument('--steps', type=int, default=12)
    parser.add_argument('--texture-size', type=int, choices=[2048, 4096], default=2048)
    args = parser.parse_args()
    if not args.allow_community_evaluation: raise SystemExit('Explicit evaluation opt-in required')
    root = store.ROOT
    engine = Path.home() / 'Tools/trellis2/code'
    run = store.DATA / 'generation/trellis2' / (time.strftime('%Y%m%dT%H%M%S') + '_' + str(args.seed) + '_' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True)
    image = Path(args.image).resolve() if args.image else root / 'doc/852446485_1648007553499526_667194451249758572_n.png'
    request = {'image': str(image), 'output': str(run / 'output'), 'engine_path': str(engine),
               'purpose': 'evaluation_only', 'seed': args.seed, 'pipeline_type': args.pipeline, 'steps': args.steps,
               'allow_existing_rmbg_evaluation': not bool(args.image), 'supplied_alpha_input': bool(args.image),
               'input_review': 'NEEDS_REVIEW', 'texture_size': args.texture_size, 'export_triangle_target': 1_000_000}
    request_path = run / 'request.json'; request_path.write_text(json.dumps(request, indent=2), encoding='utf-8')
    print('RUN_DIRECTORY ' + str(run), flush=True)
    samples = []; process = None; started = time.monotonic()
    with ExitStack() as stack:
        while True:
            try:
                stack.enter_context(jobs.exclusive_worker_lock()); break
            except OSError:
                print('WAITING_FOR_SEQUENTIAL_WORKER_LOCK', flush=True); time.sleep(3)
        log = stack.enter_context((run / 'worker.log').open('w', encoding='utf-8'))
        try:
            process = subprocess.Popen([str(engine / 'venv/Scripts/python.exe'), '-B', '-u', str(root / 'engines/trellis2_worker.py'),
                                        '--request', str(request_path), '--allow-community-evaluation'], cwd=engine, stdout=log, stderr=subprocess.STDOUT)
            while process.poll() is None:
                p = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,power.draw', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10)
                samples.append({'seconds': time.monotonic() - started, 'all_gpu_memory_mib_and_power_w': p.stdout.strip()})
                time.sleep(1)
        except BaseException:
            if process and process.poll() is None: jobs.kill_tree(process)
            raise
        finally:
            (run / 'gpu_samples.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')
    if process.returncode: raise SystemExit(f'FAILED exit {process.returncode}; see {run / "worker.log"}')
    output = run / 'output/raw.glb'
    from apps.api.inspection import inspect_glb, inspect_image
    meta = inspect_glb(output)
    generation = json.loads((run / 'output/generation.json').read_text(encoding='utf-8'))
    store.add_artifact(output, 'candidate', f'TRELLIS.2 {args.pipeline} seed {args.seed}', meta | {
        'engine': 'trellis2_community', 'seed': args.seed, 'generation': generation, 'license': 'EVALUATION_ONLY_PENDING_AUDIT'})
    condition = run / 'output/conditioning.png'
    store.add_artifact(condition, 'reference', f'TRELLIS conditioning seed {args.seed}', inspect_image(condition) | {'origin': 'engine_preprocessing', 'approval': 'NEEDS_REVIEW', 'license': 'EVALUATION_ONLY_PENDING_AUDIT'})
    alpha = run / 'output/source_alpha.png'
    if alpha.exists():
        store.add_artifact(alpha, 'reference', f'TRELLIS alpha seed {args.seed}', inspect_image(alpha) | {'origin': 'engine_preprocessing', 'approval': 'NEEDS_REVIEW', 'license': 'EVALUATION_ONLY_PENDING_AUDIT'})
    print('REAL_GENERATION_SUCCESS ' + str(output), flush=True)


if __name__ == '__main__': main()
