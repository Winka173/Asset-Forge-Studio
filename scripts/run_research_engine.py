"""Explicit research run using the unified adapter and shared sequential GPU lock."""
import argparse
import json
import subprocess
import time
import uuid
import shutil
from pathlib import Path
from apps.api import jobs, store
from engines.research_adapters import RESEARCH_ADAPTERS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=list(RESEARCH_ADAPTERS), required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--steps', type=int, default=50)
    parser.add_argument('--slat-steps', type=int, default=24)
    parser.add_argument('--project-id', default='runavelle')
    parser.add_argument('--asset-id', default='archer_tower_t3')
    args = parser.parse_args()
    adapter = RESEARCH_ADAPTERS[args.engine]
    if not adapter.installed: raise SystemExit(json.dumps(adapter.probe()))
    run = store.DATA / 'generation' / args.engine / (time.strftime('%Y%m%dT%H%M%S') + f'_{args.seed}_' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True)
    request_path = run / 'request.json'
    command, cwd, request = adapter.generate(dict(image=str(Path(args.image).resolve()), seed=args.seed,
        steps=args.steps, slat_steps=args.slat_steps, output=str(run / 'output'), request_path=str(request_path)), print)
    request_path.write_text(json.dumps(request, indent=2), encoding='utf-8')
    shutil.copyfile(store.ROOT / 'engines/sparse_research_worker.py', run / 'worker_source.py')
    print('RUN_DIRECTORY ' + str(run), flush=True)
    samples = []; process = None
    with jobs.exclusive_worker_lock(), (run / 'worker.log').open('w', encoding='utf-8') as log:
        started = time.monotonic()
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            (run / 'process.json').write_text(json.dumps({'pid': process.pid, 'command': command}))
            while process.poll() is None:
                gpu = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,power.draw', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10)
                samples.append(dict(seconds=time.monotonic() - started, all_gpu_memory_mib_and_power_w=gpu.stdout.strip()))
                time.sleep(1)
        finally:
            if process and process.poll() is None: jobs.kill_tree(process)
            (run / 'gpu_samples.json').write_text(json.dumps(samples, indent=2))
    if process.returncode: raise SystemExit(f'FAILED {process.returncode}; see {run / "worker.log"}')
    meta = adapter.verify_outputs(run / 'output')
    report = json.loads((run / 'output/generation.json').read_text())
    artifact = store.add_artifact(run / 'output/raw.glb', 'candidate', f'{args.engine} research seed {args.seed}', meta | dict(
        engine=args.engine, seed=args.seed, generation=report, license='RESEARCH_ONLY_NEEDS_REVIEW', project_id=args.project_id, asset_id=args.asset_id))
    print('REAL_GENERATION_SUCCESS ' + artifact['id'], flush=True)


if __name__ == '__main__': main()
