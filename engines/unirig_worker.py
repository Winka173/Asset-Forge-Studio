"""UniRig auto-rigging worker (run with the UniRig venv; cwd = UniRig code checkout).

Skeleton prediction -> skinning -> merge onto the original textured GLB. Windows notes (verified 2026-10-23,
commit 6793c66): torch>=2.6 loads checkpoints weights-only, so the python-box config class is allow-listed instead
of disabling the check; UniRig derives intermediate paths from the input path, so inputs are passed relative to the
code directory. Output is an experimental rigged copy; the source mesh is never modified.
"""
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
from pathlib import Path

SUFFIXES = 'obj,fbx,FBX,dae,glb,gltf,vrm'


def step(args):
    import torch, box
    torch.serialization.add_safe_globals([box.box.Box])
    sys.path.insert(0, os.getcwd())
    if args[0] == '-m':
        sys.argv = [args[1]] + args[2:]; runpy.run_module(args[1], run_name='__main__', alter_sys=True)
    else:
        sys.argv = [args[0]] + args[1:]; runpy.run_path(args[0], run_name='__main__')


def main(request_path):
    req = json.loads(Path(request_path).read_text(encoding='utf-8-sig'))
    code = Path.cwd(); output = Path(req['output']); output.mkdir(parents=True, exist_ok=True)
    work = code / 'afs_runs' / output.parent.name; work.mkdir(parents=True, exist_ok=True)
    source = work / 'input.glb'; shutil.copyfile(req['input'], source)
    rel = lambda p: os.path.relpath(p, code).replace('\\', '/')
    skeleton, skin, rigged = work / 'skeleton.fbx', work / 'skin.fbx', output / 'rigged.glb'
    seed = str(req.get('seed', 12345)); timings = {}

    def run(name, args):
        started = time.monotonic(); print('STAGE ' + name, flush=True)
        code_ = subprocess.call([sys.executable, '-B', __file__, '--step', *args], cwd=code)
        timings[name] = round(time.monotonic() - started, 1)
        if code_ != 0: raise SystemExit(f'UniRig {name} failed with exit code {code_}')

    extract = ['-m', 'src.data.extract', '--config=configs/data/quick_inference.yaml', f'--require_suffix={SUFFIXES}', '--force_override=true',
               '--num_runs=1', '--id=0', '--time=afs', f'--faces_target_count={req.get("faces", 50000)}', '--output_dir=.']
    run('Extract mesh (UniRig)', extract + [f'--input={rel(source)}'])
    run('Predict skeleton (UniRig)', ['run.py', '--task=configs/task/quick_inference_skeleton_articulationxl_ar_256.yaml', f'--seed={seed}',
                                      f'--input={rel(source)}', f'--output={rel(skeleton)}', '--npz_dir=.'])
    run('Extract skeleton (UniRig)', extract + [f'--input={rel(skeleton)}'])
    run('Predict skin weights (UniRig)', ['run.py', '--task=configs/task/quick_inference_unirig_skin.yaml', f'--seed={seed}', f'--input={rel(skeleton)}',
                                          f'--output={rel(skin)}', '--npz_dir=.', '--data_name=raw_data.npz'])
    run('Merge rig onto textured mesh (UniRig)', ['-m', 'src.inference.merge', f'--require_suffix={SUFFIXES}', '--num_runs=1', '--id=0',
                                                  f'--source={rel(skin)}', f'--target={rel(source)}', f'--output={rel(rigged)}'])
    if not rigged.is_file() or rigged.stat().st_size == 0: raise SystemExit('UniRig produced no rigged GLB')
    (output / 'unirig_report.json').write_text(json.dumps(dict(timings=timings, seed=int(seed)), indent=2), encoding='utf-8')
    shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    if sys.argv[1] == '--step': step(sys.argv[2:])
    else: main(sys.argv[sys.argv.index('--request') + 1])
