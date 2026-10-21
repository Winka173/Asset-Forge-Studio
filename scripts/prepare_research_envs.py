"""Explicit approved setup: separate environments, independent copies of validated CUDA Torch.

No model downloads or changes to the original engine installations.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorized-setup', action='store_true')
    parser.add_argument('--engine', choices=['trellis_v1', 'hi3dgen'], required=True)
    args = parser.parse_args()
    if not args.authorized_setup:
        raise SystemExit('Explicit dependency installation authorization required')
    target = ROOT / '.local/envs' / args.engine
    python = target / 'Scripts/python.exe'
    if not python.exists():
        subprocess.run(['uv', 'venv', '--python', '3.11', str(target)], check=True)
    # These are independent files, not system-site-packages, links, or one shared env.
    source = ROOT / '.local/envs/triposg/Lib/site-packages'
    dest = target / 'Lib/site-packages'
    marker = target / 'base_copy_complete.json'
    if not marker.exists():
        shutil.copytree(source, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
        marker.write_text(json.dumps({'source': str(source), 'method': 'independent copy, no links'}))
    packages = ['spconv-cu126==2.3.8', 'cumm-cu126==0.7.11', 'easydict==1.13',
                'plyfile==1.1.3', 'rembg==2.0.61', 'onnxruntime==1.20.1', 'numpy==1.26.4',
                'opencv-python-headless==4.11.0.86', 'timm==1.0.15', 'kornia==0.8.0']
    subprocess.run(['uv', 'pip', 'install', '--python', str(python), *packages], check=True)
    # Existing compatible wheel is optional; actual kernels must still be tested.
    old = Path.home() / 'Tools/trellis2/code/venv/Lib/site-packages'
    for name in ['flash_attn', 'flash_attn-2.8.3.dist-info', 'flash_attn_2_cuda.cp311-win_amd64.pyd', 'utils3d']:
        item = old / name
        if item.is_dir(): shutil.copytree(item, dest / name, dirs_exist_ok=True)
        elif item.is_file(): shutil.copyfile(item, dest / name)
    subprocess.run(['uv', 'pip', 'check', '--python', str(python)], check=True)
    result = subprocess.run(['uv', 'pip', 'freeze', '--python', str(python)], capture_output=True, text=True, check=True)
    (ROOT / 'engines' / (args.engine + '-requirements.lock.txt')).write_text(result.stdout, encoding='utf-8')
    print('ISOLATED_ENV_READY', args.engine, python, flush=True)


if __name__ == '__main__': main()
