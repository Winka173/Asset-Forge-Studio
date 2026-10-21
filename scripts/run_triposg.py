"""Sequential isolated TripoSG run; requires pre-downloaded weights and a supplied alpha input."""
import argparse
import json
import subprocess
import time
import uuid
from contextlib import ExitStack
from pathlib import Path

from apps.api import jobs, store
from apps.api.inspection import inspect_glb


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--steps', type=int, default=50)
    parser.add_argument('--octree-depth', type=int, choices=[8, 9], default=9)
    args = parser.parse_args()
    root = store.ROOT
    weights = root / 'models/triposg'
    if not (weights / 'transformer/diffusion_pytorch_model.safetensors').is_file():
        raise SystemExit('BLOCKED: TripoSG weights not completely downloaded; no inference started')
    run = store.DATA / 'generation/triposg' / (time.strftime('%Y%m%dT%H%M%S') + '_' + str(args.seed) + '_' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True)
    request = {'image': str(Path(args.image).resolve()), 'seed': args.seed, 'steps': args.steps,
               'engine_path': str(root / '.local/engines/TripoSG'), 'weights': str(weights), 'output': str(run / 'output'),
               'dense_depth': 7, 'octree_depth': args.octree_depth, 'decode_chunk_size': 10000, 'input_review': 'NEEDS_REVIEW',
               'license': 'evaluation_only_if_input_mask_uses_RMBG'}
    req_path = run / 'request.json'; req_path.write_text(json.dumps(request, indent=2), encoding='utf-8')
    samples = []; started = time.monotonic(); process = None
    print('RUN_DIRECTORY ' + str(run), flush=True)
    with ExitStack() as stack:
        while True:
            try: stack.enter_context(jobs.exclusive_worker_lock()); break
            except OSError: print('WAITING_FOR_WORKER_LOCK', flush=True); time.sleep(3)
        log = stack.enter_context((run / 'worker.log').open('w', encoding='utf-8'))
        try:
            process = subprocess.Popen([str(root / '.local/envs/triposg/Scripts/python.exe'), '-B', '-u', str(root / 'engines/triposg_worker.py'), '--request', str(req_path)],
                                       cwd=root, stdout=log, stderr=subprocess.STDOUT)
            while process.poll() is None:
                p = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,power.draw', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10)
                samples.append({'seconds': time.monotonic() - started, 'all_gpu_memory_mib_and_power_w': p.stdout.strip()}); time.sleep(1)
        except BaseException:
            if process and process.poll() is None: jobs.kill_tree(process)
            raise
        finally: (run / 'gpu_samples.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')
    if process.returncode: raise SystemExit(f'FAILED exit {process.returncode}; see {run / "worker.log"}')
    output = run / 'output/raw.glb'
    meta = inspect_glb(output); report = json.loads((run / 'output/generation.json').read_text(encoding='utf-8'))
    store.add_artifact(output, 'candidate', f'TripoSG seed {args.seed} depth {args.octree_depth}', meta | {
        'engine': 'triposg', 'seed': args.seed, 'generation': report, 'license': 'EVALUATION_ONLY_INPUT_MASK_LICENSE_REVIEW'})
    print('REAL_GENERATION_SUCCESS ' + str(output), flush=True)


if __name__ == '__main__': main()
