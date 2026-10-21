"""Headless only: immutable input -> metric master, LODs, collider, PBR inventory, locked renders.

blender -b --factory-startup --python-exit-code 1 --python process_asset.py -- --request request.json
No execution in the user's current scene. No inferred missing PBR maps.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def select(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def bounds(objects):
    points = [obj.matrix_world @ Vector(v) for obj in objects for v in obj.bound_box]
    return [min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]


def mesh_stats(objects):
    result = []
    for obj in objects:
        bm = bmesh.new(); bm.from_mesh(obj.data)
        obj.data.calc_loop_triangles()
        result.append({'name': obj.name, 'triangles': len(obj.data.loop_triangles), 'vertices': len(obj.data.vertices),
                       'non_manifold_edges': sum(not e.is_manifold for e in bm.edges),
                       'boundary_edges': sum(e.is_boundary for e in bm.edges),
                       'loose_vertices': sum(not v.link_edges for v in bm.verts),
                       'uv_layers': len(obj.data.uv_layers),
                       'materials': [m.name if m else None for m in obj.data.materials]})
        bm.free()
    return result


def export_glb(path, objects):
    select(objects)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True,
                              export_animations=False, export_yup=True)


def material_inventory(objects, folder):
    materials = {m for o in objects for m in o.data.materials if m}
    result = []
    channels = {'Base Color': 'base_color', 'Metallic': 'metallic', 'Roughness': 'roughness',
                'Normal': 'normal', 'Emission Color': 'emissive'}
    image_paths = {}
    for m in materials:
        row = {'name': m.name, 'channels': {}, 'ao': 'NOT_TESTED', 'plausibility': 'NOT_TESTED'}
        if not m.use_nodes:
            row['status'] = 'NEEDS_REVIEW'; result.append(row); continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf:
            row['status'] = 'NEEDS_REVIEW'; result.append(row); continue
        for socket_name, channel in channels.items():
            socket = bsdf.inputs.get(socket_name)
            if not socket:
                row['channels'][channel] = {'status': 'MISSING'}; continue
            images, visited = set(), set()
            def upstream(node):
                if node in visited: return
                visited.add(node)
                if node.type == 'TEX_IMAGE' and node.image: images.add(node.image)
                for inp in node.inputs:
                    for link in inp.links: upstream(link.from_node)
            for link in socket.links: upstream(link.from_node)
            files = []
            for image in images:
                if image not in image_paths:
                    target = folder / f'texture_{len(image_paths):03d}.png'
                    # Export actual image pixels; preserve the source .blend node graph for packed channels.
                    image.filepath_raw = str(target); image.file_format = 'PNG'; image.save()
                    image_paths[image] = target.name
                files.append({'file': image_paths[image], 'source_name': image.name, 'color_space': image.colorspace_settings.name,
                              'size': list(image.size), 'note': 'actual source image; packed channels may share one file'})
            value = socket.default_value
            row['channels'][channel] = {'status': 'TEXTURE' if files else ('NODE_GRAPH_REQUIRES_REVIEW' if socket.is_linked else 'CONSTANT'),
                                         'textures': files, 'constant': list(value) if hasattr(value, '__len__') else value}
        row['status'] = 'NEEDS_REVIEW'; result.append(row)
    return result


def render_views(objects, output, cfg, resolutions, selected_views):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.view_settings.view_transform = cfg['view_transform']
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = cfg['exposure']
    scene.view_settings.gamma = 1
    if not scene.world:
        scene.world = bpy.data.worlds.new('BenchmarkWorld')
    scene.world.use_nodes = True
    background = next(n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND')
    background.inputs[0].default_value = (*cfg['background'], 1)
    background.inputs[1].default_value = 0.5
    target = Vector(cfg['target_xyz_m'])
    camera_data = bpy.data.cameras.new('BenchmarkCamera'); camera_data.type = 'ORTHO'
    camera_data.ortho_scale = cfg['ortho_scale_m']
    camera = bpy.data.objects.new('BenchmarkCamera', camera_data); scene.collection.objects.link(camera); scene.camera = camera
    extras = []
    for name in ('key', 'fill'):
        data = bpy.data.lights.new(name, 'AREA'); data.energy = cfg['lights'][name + '_w']; data.shape = 'DISK'; data.size = 7
        obj = bpy.data.objects.new(name, data); scene.collection.objects.link(obj)
        obj.location = cfg['lights'][name + '_xyz_m']; obj.rotation_euler = (target - obj.location).to_track_quat('-Z', 'Y').to_euler()
        extras.append(obj)
    # Visible metric references; not an alleged rigged character.
    for name, loc, dimensions in [('scale_1.8m', (-6, 0, 0.9), (0.4, 0.4, 1.8)), ('wall_2m', (-8, 0, 1), (2, 0.4, 2))]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        marker = bpy.context.object; marker.name = name; marker.dimensions = dimensions
        extras.append(marker)
    files = []
    from bpy_extras.object_utils import world_to_camera_view
    framing = []
    layer = scene.view_layers[0]
    layer.use_pass_normal = True; layer.use_pass_z = True
    # EXR stores real normal/Z passes alongside beauty. No proxy depth claimed.
    scene.render.film_transparent = True
    for resolution_name in resolutions:
        width, height = cfg['resolutions'][resolution_name]
        scene.render.resolution_x = width; scene.render.resolution_y = height; scene.render.resolution_percentage = 100
        for view_name in selected_views:
            direction = Vector(cfg['views'][view_name]).normalized()
            camera.location = target + direction * cfg['camera_distance_m']
            camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
            bpy.context.view_layer.update()
            projected = [world_to_camera_view(scene, camera, o.matrix_world @ Vector(v)) for o in objects for v in o.bound_box]
            clipped = any(p.z < 0 or not 0 <= p.x <= 1 or not 0 <= p.y <= 1 for p in projected)
            framing.append({'resolution': resolution_name, 'view': view_name, 'status': 'FAIL' if clipped else 'PASS'})
            stem = f'{resolution_name}_{view_name}'
            # Mask pass excludes metric markers and lighting geometry, based on true transparency.
            for extra in extras:
                if extra.type == 'MESH': extra.hide_render = True
            scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
            scene.render.filepath = str(output / (stem + '_passes.exr'))
            bpy.ops.render.render(write_still=True)
            files.append(stem + '_passes.exr')
            # Save raw asset beauty RGBA; its alpha is the silhouette, unaffected by scale markers.
            scene.render.image_settings.file_format = 'PNG'
            bpy.data.images['Render Result'].save_render(str(output / (stem + '_asset.png')), scene=scene)
            files.append(stem + '_asset.png')
            for extra in extras:
                if extra.type == 'MESH': extra.hide_render = False
            scene.render.film_transparent = False
            scene.render.filepath = str(output / (stem + '.png'))
            bpy.ops.render.render(write_still=True); files.append(stem + '.png')
            scene.render.film_transparent = True
    return files, framing


def run(request):
    source = Path(request['input']).resolve(); output = Path(request['output']).resolve()
    if output.exists(): raise ValueError('Output must be a new immutable directory')
    output.mkdir(parents=True)
    cfg_path = Path(request['benchmark']).resolve(); cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    write(output / 'request.json', request); write(output / 'benchmark.json', cfg)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not objects: raise ValueError('No mesh after import')
    before = mesh_stats(objects)
    # Snapshot before repairs/normalization. Packed resources make .blend portable.
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'raw.blend'))
    # Preserve imported hierarchy/world transforms before mesh-only operations.
    for obj in objects:
        matrix = obj.matrix_world.copy(); obj.parent = None; obj.matrix_world = matrix
    select(objects); bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    yaw = math.radians(request.get('yaw_degrees', 0))
    for obj in objects:
        # Rotate geometry and positions as one asset, not each component around its own origin.
        from mathutils import Matrix
        obj.matrix_world = Matrix.Rotation(yaw, 4, 'Z') @ obj.matrix_world
    low, high = bounds(objects)
    target_height = request.get('target_height_m')
    scale = target_height / (high[2] - low[2]) if target_height else 1.0
    if not math.isfinite(scale) or scale <= 0: raise ValueError('Invalid normalization scale')
    if request.get('normalize', False):
        center = Vector(((low[0]+high[0])/2, (low[1]+high[1])/2, low[2]))
        for obj in objects:
            obj.location = (obj.location - center) * scale; obj.scale *= scale
        select(objects); bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    elif target_height:
        raise ValueError('target_height_m requires normalize=true')
    epsilon = request.get('merge_distance_m', 0)
    for obj in objects:
        bm = bmesh.new(); bm.from_mesh(obj.data)
        if epsilon > 0: bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=epsilon)
        if request.get('recalculate_normals', False): bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data); bm.free(); obj.data.update()
    bpy.context.view_layer.update()
    after = mesh_stats(objects); low, high = bounds(objects)
    textures = output / 'textures'; textures.mkdir()
    materials = material_inventory(objects, textures)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'master.blend'))
    export_glb(output / 'LOD0.glb', objects)
    lod_stats = []
    for index, ratio in enumerate(request.get('lod_ratios', [0.65, 0.35, 0.15]), 1):
        if not 0 < ratio < 1: raise ValueError('LOD ratio must be between zero and one')
        duplicates = []
        for obj in objects:
            clone = obj.copy(); clone.data = obj.data.copy(); clone.name = f'{obj.name}_LOD{index}'
            bpy.context.scene.collection.objects.link(clone); duplicates.append(clone)
            modifier = clone.modifiers.new('candidate_decimation', 'DECIMATE')
            # Keep a closed-volume minimum on tiny meshes; do not create a one-face LOD.
            triangles = sum(max(0, len(p.vertices)-2) for p in clone.data.polygons)
            modifier.ratio = min(1.0, max(ratio, 8 / max(triangles, 1)))
            select([clone]); bpy.ops.object.modifier_apply(modifier=modifier.name)
        export_glb(output / f'LOD{index}.glb', duplicates)
        lod_stats.append({'level': index, 'ratio': ratio, 'meshes': mesh_stats(duplicates), 'quality': 'NEEDS_REVIEW', 'baking': 'NOT_TESTED'})
        for clone in duplicates: bpy.data.objects.remove(clone, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=1, location=Vector(low).lerp(Vector(high), 0.5))
    collider = bpy.context.object; collider.name = 'COLLIDER_AABB'; collider.dimensions = Vector(high) - Vector(low)
    select([collider]); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    export_glb(output / 'collider.glb', [collider]); bpy.data.objects.remove(collider, do_unlink=True)
    rendered, framing = render_views(objects, output, cfg, request.get('resolutions', ['mobile', 'pc1440']), request.get('views', list(cfg['views']))) if request.get('render', True) else ([], [])
    report = {'status': 'NEEDS_REVIEW', 'input_sha256': sha(source), 'script_sha256': sha(__file__),
              'blender_version': bpy.app.version_string, 'dimensions_xyz_m_blender': [high[i]-low[i] for i in range(3)],
              'normalization': {'applied': request.get('normalize', False), 'target_height_m': target_height, 'scale': scale, 'yaw_degrees': request.get('yaw_degrees', 0)},
              'before': before, 'after': after, 'materials': materials, 'lods': lod_stats,
              'framing': framing, 'rendered': rendered,
              'checks': {'export_reopen': 'NOT_TESTED', 'uv_overlap': 'NOT_TESTED', 'self_intersections': 'NOT_TESTED',
                         'lod_silhouette_error': 'NOT_TESTED', 'normal_bake': 'NOT_TESTED', 'unity': 'NOT_TESTED', 'human_review': 'NOT_TESTED',
                         'pbr_reconstruction': 'NOT_TESTED', 'modular_connectors': 'NOT_TESTED'}}
    # Reopen every GLB export using actual Blender importer and check geometry survives.
    reopen = []
    for path in sorted(output.glob('*.glb')):
        bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(path))
        imported = [o for o in bpy.context.scene.objects if o.type == 'MESH']
        if not imported: raise ValueError(f'Export cannot reopen: {path.name}')
        reopen.append({'file': path.name, 'meshes': mesh_stats(imported)})
    report['reopened'] = reopen; report['checks']['export_reopen'] = 'PASS'
    report['artifacts'] = [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in output.rglob('*') if p.is_file()]
    write(output / 'report.json', report)
    print('AFS_PIPELINE_SUCCESS ' + str(output / 'report.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    run(json.loads(Path(args.request).read_text(encoding='utf-8-sig')))
