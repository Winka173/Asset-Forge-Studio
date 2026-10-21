"""Material-neutral geometry diagnostic; output never labelled PBR or Unity evidence."""
import argparse
import json
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_asset import render_views, sha, write

p = argparse.ArgumentParser(); p.add_argument('--request', required=True)
args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
request = json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
cfg = json.loads(Path(request['benchmark']).read_text(encoding='utf-8'))
for candidate in request['candidates']:
    output = Path(candidate['output']).resolve()
    if output.exists(): raise ValueError('Require a new render directory')
    output.mkdir(parents=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=candidate['input'])
    objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    material = bpy.data.materials.new('DiagnosticClay'); material.use_nodes = True
    bsdf = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (0.18,0.18,0.18,1)
    bsdf.inputs['Metallic'].default_value = 0
    bsdf.inputs['Roughness'].default_value = 0.75
    bpy.context.scene.view_layers[0].material_override = material
    files, framing = render_views(objects, output, cfg, ['mobile'], ['three_quarter'])
    write(output/'report.json', {'status':'NEEDS_REVIEW','mode':'common neutral clay geometry diagnostic, NOT PBR/Unity',
        'input_sha256':sha(candidate['input']),'benchmark':cfg,'framing':framing,'files':files})
print('REAL_CLAY_COMPARISON_COMPLETE', flush=True)
