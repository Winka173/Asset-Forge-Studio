"""Real mesh QA fixture exercises Blender; never presented as AI generation or Meshy."""
import json
import subprocess
import uuid
from pathlib import Path

import trimesh

from apps.api import store
from apps.api.inspection import inspect_glb
from scripts.audit import audit


def main():
    run = store.ROOT / '.local/qa' / uuid.uuid4().hex
    run.mkdir(parents=True)
    source = run / 'qa_box_not_ai.glb'
    source.write_bytes(trimesh.creation.box(extents=[2, 10, 3]).export(file_type='glb'))
    request = {'input': str(source), 'output': str(run / 'output'),
               'benchmark': str(store.ROOT / 'benchmarks/archer_tower_t3/benchmark.json'),
               'render': True, 'resolutions': ['mobile'], 'views': ['three_quarter'],
               'normalize': True, 'target_height_m': 10, 'lod_ratios': [0.65, 0.35, 0.15]}
    path = run / 'request.json'; path.write_text(json.dumps(request), encoding='utf-8')
    blender = audit()['blender_path']
    with (run / 'blender.log').open('w', encoding='utf-8') as log:
        p = subprocess.run([blender, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                            str(store.ROOT / 'pipelines/blender/process_asset.py'), '--', '--request', str(path)], stdout=log, stderr=subprocess.STDOUT)
    if p.returncode: raise RuntimeError(f'Blender failed; see {run / "blender.log"}')
    report = json.loads((run / 'output/report.json').read_text(encoding='utf-8'))
    for name in ['LOD0', 'LOD1', 'LOD2', 'LOD3', 'collider']:
        assert inspect_glb(run / f'output/{name}.glb')['triangles'] > 0
    assert report['checks']['export_reopen'] == 'PASS'
    assert abs(report['dimensions_xyz_m_blender'][2] - 10) < 1e-5
    evidence = {'fixture': 'trimesh box, NOT AI generation, NOT Archer Tower, NOT Meshy',
                'run_path': str(run), 'report': report, 'result': 'PASS'}
    target = store.ROOT / 'docs/evidence/blender_smoke.json'
    target.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps({'result': 'PASS', 'run': str(run), 'rendered': report['rendered']}))


if __name__ == '__main__': main()
