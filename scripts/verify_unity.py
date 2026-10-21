"""Actual isolated Unity Editor import/render validation; never opens a user's game.

The renderer uses an existing Editor license. This script does not activate,
return, copy, or modify licenses. GPU rendering is an explicit separate invocation.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'data/jobs/0cd41c06dfa040908ead8f880ff6593b/output'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024): h.update(block)
    return h.hexdigest()


def prepare(project, source, run, mode):
    for name in ['Assets/Editor', 'Assets/ArcherTower/textures', 'Assets/QA', 'Packages', 'ProjectSettings']:
        (project / name).mkdir(parents=True, exist_ok=True)
    modules = ['imageconversion', 'jsonserialize', 'physics']
    (project / 'Packages/manifest.json').write_text(json.dumps({'dependencies': {f'com.unity.modules.{m}': '1.0.0' for m in modules}}, indent=2))
    shutil.copyfile(ROOT / 'unity-validation/Editor/AssetForgeValidation.cs', project / 'Assets/Editor/AssetForgeValidation.cs')
    manifest = []
    for name in [f'LOD{n}.fbx' for n in range(4)] + ['textures/texture_000.png', 'textures/texture_001.png']:
        original = source / name
        destination = project / 'Assets/ArcherTower' / name
        checksum = digest(original)
        if not destination.exists() or digest(destination) != checksum: shutil.copyfile(original, destination)
        manifest.append({'name': name, 'bytes': original.stat().st_size, 'sha256': checksum, 'copied_sha256': digest(destination)})
    # glTF metallic-roughness stores roughness=G, metallic=B. Unity Standard
    # expects metallic=R and smoothness=A. This is channel conversion, not new PBR.
    mr = np.array(Image.open(source / 'textures/texture_001.png').convert('RGBA'))
    converted = np.zeros_like(mr)
    converted[:, :, 0] = mr[:, :, 2]
    converted[:, :, 3] = 255 - mr[:, :, 1]
    packed = project / 'Assets/ArcherTower/textures/Unity_MetallicSmoothness.png'
    Image.fromarray(converted).save(packed)
    report = json.loads((source / 'report.json').read_text('utf-8'))
    triangles = [sum(m['triangles'] for m in report['after'])] + [sum(m['triangles'] for m in lod['meshes']) for lod in report['lods']]
    request = {'outputPath': str(run), 'mode': mode, 'expectedTriangles': triangles,
               'expectedHeight': report['dimensions_xyz_m_blender'][2]}
    (project / 'QARequest.json').write_text(json.dumps(request, indent=2))
    provenance = {'input_path': str(source), 'input_sha256': report['input_sha256'], 'files': manifest,
                  'derived_texture': {'path': str(packed), 'sha256': digest(packed), 'operation': 'R = source B (metallic); A = 255 - source G (roughness); G=B=0',
                                      'source_sha256': digest(source / 'textures/texture_001.png'), 'color_space': 'linear',
                                      'normal_ao_emission': 'NOT_GENERATED'},
                  'blender_report_sha256': digest(source / 'report.json'), 'expected_lod_triangles': triangles}
    (run / 'source_manifest.json').write_text(json.dumps(provenance, indent=2))
    return provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', choices=['6000.4.8f1', '6000.6.3f1'], default='6000.4.8f1')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--render', action='store_true', help='Uses GPU: coordinate with the sequential engine queue first')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    editor = Path('C:/Program Files/Unity/Hub/Editor') / args.version / 'Editor/Unity.exe'
    if not editor.is_file(): raise SystemExit('Requested installed Unity Editor was not found')
    mode = 'render' if args.render else 'import'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    run = ROOT / '.local/unity-validation-runs' / f'{stamp}_{args.version}_{mode}'
    run.mkdir(parents=True, exist_ok=False)
    project = ROOT / '.local/unity-validation' / args.version
    source = args.source.resolve(strict=True)
    provenance = prepare(project, source, run, mode)
    (project / 'ProjectSettings/ProjectVersion.txt').write_text(f'm_EditorVersion: {args.version}\n')
    metadata = {'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mode': mode,
                'editor': str(editor), 'version': args.version, 'project_path': str(project), 'run_path': str(run),
                'source_manifest': provenance, 'status': 'PREPARED', 'mobile_device_performance': 'NOT_TESTED',
                'mesh_quality_parity': 'NOT_TESTED', 'human_quality_approval': 'NOT_TESTED'}
    evidence = ROOT / f'docs/evidence/unity_{mode}.json'
    if args.prepare_only:
        evidence.write_text(json.dumps(metadata, indent=2)); print(json.dumps({'status': 'PREPARED', 'run_path': str(run)})); return
    command = [str(editor), '-batchmode', '-projectPath', str(project), '-executeMethod', 'AssetForgeValidation.Run',
               '-logFile', str(run / 'unity.log'), '-quit', '-accept-apiupdate']
    if not args.render: command.append('-nographics')
    else: command += ['-force-d3d11']
    metadata['command_flags'] = command[1:]
    started = time.perf_counter()
    with (run / 'console.log').open('wb') as console:
        process = subprocess.Popen(command, stdout=console, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (run / 'process.json').write_text(json.dumps({'pid': process.pid, 'owned_process': True}))
        print(json.dumps({'status': 'UNITY_RUNNING', 'pid': process.pid, 'run_path': str(run), 'mode': mode}), flush=True)
        try: returncode = process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            returncode = -1
            metadata['status'] = 'TIMEOUT'
    metadata.update(returncode=returncode, elapsed_seconds=time.perf_counter() - started,
                    log_path=str(run / 'unity.log'), console_path=str(run / 'console.log'))
    unity_report = run / 'unity_report.json'
    if unity_report.exists():
        metadata['report'] = json.loads(unity_report.read_text('utf-8-sig'))
        metadata['status'] = 'PASS_EDITOR_VALIDATION' if returncode == 0 and metadata['report'].get('checks_passed') else 'FAILED_EDITOR_VALIDATION'
    else:
        logs = (run / 'unity.log').read_text('utf-8', errors='replace') if (run / 'unity.log').exists() else ''
        metadata['status'] = 'LICENSE_BLOCKED' if 'No valid Unity Editor license' in logs or 'No license' in logs else 'UNITY_STARTUP_OR_COMPILATION_FAILED'
    for png in run.glob('*.png'):
        with Image.open(png) as im:
            pixels = np.asarray(im.convert('RGB'))
            metadata.setdefault('images', []).append({'name': png.name, 'width': im.width, 'height': im.height,
                                                      'sha256': digest(png), 'channel_std': pixels.std(axis=(0, 1)).tolist()})
        shutil.copyfile(png, ROOT / 'docs/evidence' / png.name)
    evidence.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps({'status': metadata['status'], 'returncode': returncode, 'seconds': metadata['elapsed_seconds'], 'evidence': str(evidence)}), flush=True)
    if metadata['status'] != 'PASS_EDITOR_VALIDATION': raise SystemExit(1)


if __name__ == '__main__': main()
