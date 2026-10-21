"""Bake actual master geometry to an existing UV LOD; retain before/after at identical locked cameras.

No inferred metal/roughness or invented emission. AO remains a separate geometric map.
blender -b --factory-startup --python-exit-code 1 --python bake_lod.py -- --request request.json
"""
import argparse
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_asset import bounds, export_glb, mesh_stats, render_views, select, sha, write


def run(req):
    output = Path(req['output']).resolve()
    if output.exists(): raise ValueError('Require a new output version directory')
    output.mkdir(parents=True)
    write(output / 'request.json', req)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(req['master']).resolve()))
    masters = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for obj in masters: obj.name = 'MASTER_' + obj.name
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(Path(req['lod']).resolve()))
    targets = [o for o in bpy.context.scene.objects if o not in before and o.type == 'MESH']
    if len(masters) != 1 or len(targets) != 1:
        raise ValueError('Current validated bake lane requires one source and one target mesh; multi-part requires explicit correspondence')
    high, low = masters[0], targets[0]
    if not low.data.uv_layers: raise ValueError('Target LOD has no UV map; cannot validly bake')
    hi_bounds, lo_bounds = bounds([high]), bounds([low])
    distance = max(abs(hi_bounds[i][j]-lo_bounds[i][j]) for i in range(2) for j in range(3))
    if distance > req.get('bounds_tolerance_m', 0.15): raise ValueError('Master/LOD bounds differ; confirm alignment before baking')
    scene = bpy.context.scene; scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = 16
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_cage = False
    scene.render.bake.cage_extrusion = req.get('cage_extrusion_m', 0.02)
    scene.render.bake.max_ray_distance = req.get('max_ray_distance_m', 0.1)
    scene.render.bake.margin = 16
    scene.render.bake.normal_space = 'TANGENT'
    resolution = req.get('texture_size', 2048)
    # Each low material gets its own copy, avoiding edits to the immutable high source.
    for index, material in enumerate(low.data.materials):
        if material: low.data.materials[index] = material.copy()
    if not low.data.materials:
        material = bpy.data.materials.new('LOD_Baked'); material.use_nodes = True; low.data.materials.append(material)
    mats = [m for m in low.data.materials if m]
    images = {}
    for kind in ['NORMAL', 'AO']:
        image = bpy.data.images.new('LOD_' + kind, width=resolution, height=resolution, alpha=False)
        image.colorspace_settings.name = 'Non-Color'
        for mat in mats:
            mat.use_nodes = True
            for node in mat.node_tree.nodes: node.select = False
            node = mat.node_tree.nodes.new('ShaderNodeTexImage'); node.image = image; node.select = True
            mat.node_tree.nodes.active = node
        high.hide_render = False; high.hide_set(False); select([high, low]); bpy.context.view_layer.objects.active = low
        bpy.ops.object.bake(type=kind)
        target = output / f'lod_{kind.lower()}.png'; image.filepath_raw = str(target); image.file_format = 'PNG'; image.save()
        images[kind] = image
    # Retain LOD before attaching normal map; both captures use the same geometry and lighting.
    high.hide_render = True; high.hide_set(True)
    cfg = json.loads(Path(req['benchmark']).read_text(encoding='utf-8'))
    before_folder = output / 'before'; before_folder.mkdir()
    for obj in list(scene.objects):
        if obj.type in {'LIGHT', 'CAMERA'}: bpy.data.objects.remove(obj, do_unlink=True)
    before_renders, before_framing = render_views([low], before_folder, cfg, ['mobile'], ['three_quarter'])
    # Remove metric markers/camera/lights created by first render so second pass is identical.
    for obj in list(scene.objects):
        if obj not in {high, low}: bpy.data.objects.remove(obj, do_unlink=True)
    for mat in mats:
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf: raise ValueError('Target material has no Principled BSDF')
        tex = mat.node_tree.nodes.new('ShaderNodeTexImage'); tex.image = images['NORMAL']
        normal = mat.node_tree.nodes.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value = 1
        mat.node_tree.links.new(tex.outputs['Color'], normal.inputs['Color'])
        mat.node_tree.links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    # AO exported separately; does not get multiplied into albedo or mislabelled metallic/roughness.
    export_glb(output / 'LOD_baked.glb', [low])
    bpy.ops.file.pack_all(); bpy.ops.wm.save_as_mainfile(filepath=str(output / 'baked.blend'))
    after_folder = output / 'after'; after_folder.mkdir()
    after_renders, after_framing = render_views([low], after_folder, cfg, ['mobile'], ['three_quarter'])
    write(output / 'report.json', {'status': 'NEEDS_REVIEW', 'master_sha256': sha(req['master']), 'lod_sha256': sha(req['lod']),
        'script_sha256': sha(__file__), 'texture_size': resolution, 'normal_space': 'tangent', 'ao': 'actual Cycles geometry bake, separate texture',
        'source': mesh_stats([high]), 'target': mesh_stats([low]), 'before': before_renders, 'after': after_renders,
        'framing': before_framing + after_framing, 'checks': {'uv_overlap': 'NOT_TESTED', 'bake_ray_misses': 'NOT_TESTED',
        'visual_improvement': 'NEEDS_REVIEW', 'unity': 'NOT_TESTED', 'human_approval': 'NOT_TESTED'},
        'artifacts': [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in output.rglob('*') if p.is_file()]})
    print('AFS_BAKE_SUCCESS ' + str(output), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--request', required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    run(json.loads(Path(args.request).read_text(encoding='utf-8-sig')))
