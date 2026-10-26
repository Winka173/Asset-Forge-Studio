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
sys.path.insert(0,str(Path(__file__).resolve().parent))

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


def weld_coincident(obj):
    """Neural meshes arrive unwelded (UV-split vertices); collapse decimation on them tears holes. Welding coincident
    positions keeps per-loop UVs, so seams survive while the surface decimates as one connected shell."""
    weld = bmesh.new(); weld.from_mesh(obj.data)
    bmesh.ops.remove_doubles(weld, verts=weld.verts, dist=max(max(obj.dimensions), 1e-6) * 1e-6)
    weld.to_mesh(obj.data); weld.free()


def bounds(objects):
    points = [obj.matrix_world @ Vector(v) for obj in objects for v in obj.bound_box]
    return [min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]


def mesh_stats(objects):
    result = []
    for obj in objects:
        bm = bmesh.new(); bm.from_mesh(obj.data)
        obj.data.calc_loop_triangles()
        row = {'name': obj.name, 'triangles': len(obj.data.loop_triangles), 'vertices': len(obj.data.vertices),
                       'non_manifold_edges': sum(not e.is_manifold for e in bm.edges),
                       'boundary_edges': sum(e.is_boundary for e in bm.edges),
                       'loose_vertices': sum(not v.link_edges for v in bm.verts),
                       'uv_layers': len(obj.data.uv_layers),
                       'materials': [m.name if m else None for m in obj.data.materials]}
        # GLB often duplicates positions across UV and hard-normal seams. Analyze a copy;
        # never report those split edges as proven physical holes or mutate the source.
        epsilon = max(max(obj.dimensions), 1e-5) * 1e-7
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=epsilon)
        row['position_weld_analysis'] = {'epsilon_local_m': epsilon,
            'boundary_edges': sum(e.is_boundary for e in bm.edges),
            'non_manifold_edges': sum(not e.is_manifold for e in bm.edges),
            'note': 'analysis only; UV seams may explain raw boundary counts; does not prove no self-intersections'}
        result.append(row)
        bm.free()
    return result


def export_glb(path, objects):
    select(objects)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True,
                              export_animations=False, export_yup=True)


def export_fbx(path, objects):
    select(objects)
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'},
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Z', axis_up='Y',
        path_mode='COPY', embed_textures=True, bake_anim=False, add_leaf_bones=False)


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


def set_image_kind(settings, file_format):
    """Blender 5.x made multilayer a media type (the OPEN_EXR_MULTILAYER format is only offered under it); 4.x lists it directly."""
    if hasattr(settings, 'media_type'): settings.media_type = 'MULTI_LAYER_IMAGE' if file_format == 'OPEN_EXR_MULTILAYER' else 'IMAGE'
    settings.file_format = file_format


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
            set_image_kind(scene.render.image_settings, 'OPEN_EXR_MULTILAYER')
            scene.render.filepath = str(output / (stem + '_passes.exr'))
            bpy.ops.render.render(write_still=True)
            files.append(stem + '_passes.exr')
            # Save raw asset beauty RGBA; its alpha is the silhouette, unaffected by scale markers.
            set_image_kind(scene.render.image_settings, 'PNG')
            bpy.data.images['Render Result'].save_render(str(output / (stem + '_asset.png')), scene=scene)
            files.append(stem + '_asset.png')
            for extra in extras:
                if extra.type == 'MESH': extra.hide_render = False
            scene.render.film_transparent = False
            scene.render.filepath = str(output / (stem + '.png'))
            bpy.ops.render.render(write_still=True); files.append(stem + '.png')
            scene.render.film_transparent = True
    # Asset-fitted views for visual QA and thumbnails. The fixed-scale benchmark renders above stay comparable across
    # assets, but a 2 m prop occupies only a few pixels in them, which leaves local visual review effectively blind.
    low, high = bounds(objects); center = (Vector(low) + Vector(high)) / 2; extent = max(Vector(high) - Vector(low))
    width, height = cfg['resolutions'].get('mobile', cfg['resolutions'][resolutions[0]])
    scene.render.resolution_x = width; scene.render.resolution_y = height
    camera_data.ortho_scale = extent * 1.2 * max(1.0, width / height)
    for extra in extras:
        if extra.type == 'MESH': extra.hide_render = True
    scene.render.film_transparent = False; scene.render.image_settings.file_format = 'PNG'
    for view_name in selected_views:
        direction = Vector(cfg['views'][view_name]).normalized()
        camera.location = center + direction * cfg['camera_distance_m']
        camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(output / f'fit_{view_name}.png')
        bpy.ops.render.render(write_still=True); files.append(f'fit_{view_name}.png')
    for extra in extras:
        if extra.type == 'MESH': extra.hide_render = False
    camera_data.ortho_scale = cfg['ortho_scale_m']; scene.render.film_transparent = True
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
    material_change=None;geometry_before=None
    if request.get('material_edit'):
        sys.path.insert(0,str(Path(__file__).parent))
        from material_edit import signature,recolor
        geometry_before=signature(objects)
    # Snapshot before repairs/normalization. Packed resources make .blend portable.
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'raw.blend'))
    if request.get('material_edit'):material_change=recolor(objects,request['material_edit'],output)
    # Preserve imported hierarchy/world transforms before mesh-only operations.
    if not request.get('material_edit'):
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
    water_report = None
    if request.get('water') is not None:
        # Requested water surface (well, fountain, pool): a separate "Water" mesh; the model's own meshes stay unchanged.
        sys.path.insert(0, str(Path(__file__).parent))
        from add_water import add_water
        options = dict(request['water']); optional = options.pop('optional', False)
        water, water_report = add_water(objects, **options); write(output / 'water.json', water_report)
        if water: objects.append(water)
        elif not optional: raise ValueError('No basin to hold water: ' + water_report.get('reason', 'no enclosed basin'))
    bpy.context.view_layer.update()
    after = mesh_stats(objects); low, high = bounds(objects)
    if material_change:
        from material_edit import compare
        material_change['geometry_verification']=compare(geometry_before,objects)
    textures = output / 'textures'; textures.mkdir()
    materials = material_inventory(objects, textures)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'master.blend'))
    export_glb(output / 'LOD0.glb', objects)
    if request.get('export_fbx', True): export_fbx(output / 'LOD0.fbx', objects)
    from lod_quality import SurfaceReference
    print('STAGE Measure LOD geometry detail retention against the unchanged master',flush=True)
    surface_reference=SurfaceReference(objects)
    lod_stats = []
    for index, ratio in enumerate(request.get('lod_ratios', [0.65, 0.35, 0.15]), 1):
        if not 0 < ratio < 1: raise ValueError('LOD ratio must be between zero and one')
        duplicates = []
        for obj in objects:
            clone = obj.copy(); clone.data = obj.data.copy(); clone.name = f'{obj.name}_LOD{index}'
            bpy.context.scene.collection.objects.link(clone); duplicates.append(clone)
            weld_coincident(clone)
            modifier = clone.modifiers.new('candidate_decimation', 'DECIMATE'); modifier.use_collapse_triangulate = True
            # Keep a closed-volume minimum on tiny meshes; do not create a one-face LOD.
            triangles = sum(max(0, len(p.vertices)-2) for p in clone.data.polygons)
            modifier.ratio = min(1.0, max(ratio, 8 / max(triangles, 1)))
            select([clone]); bpy.ops.object.modifier_apply(modifier=modifier.name)
        export_glb(output / f'LOD{index}.glb', duplicates)
        if request.get('export_fbx', True): export_fbx(output / f'LOD{index}.fbx', duplicates)
        surface_error=surface_reference.compare(duplicates)
        lod_stats.append({'level': index, 'ratio': ratio, 'meshes': mesh_stats(duplicates), 'quality': 'NEEDS_REVIEW', 'baking': 'NOT_TESTED', 'surface_error':surface_error})
        for clone in duplicates: bpy.data.objects.remove(clone, do_unlink=True)
    # Game-ready derivative: only when an explicit triangle budget is below the master; the master files above stay untouched.
    budget = request.get('game_triangle_budget')
    master_triangles = sum(max(0, len(p.vertices)-2) for obj in objects for p in obj.data.polygons)
    game_ready = {'triangle_budget': budget, 'source_triangles': master_triangles, 'status': 'NOT_REQUESTED' if not budget else 'MASTER_WITHIN_BUDGET'}
    if budget and master_triangles > budget:
        print('STAGE Build game-ready derivative within the triangle budget', flush=True)
        ratio = budget / master_triangles
        duplicates = []
        for obj in objects:
            clone = obj.copy(); clone.data = obj.data.copy(); clone.name = f'{obj.name}_GAME'
            bpy.context.scene.collection.objects.link(clone); duplicates.append(clone)
            weld_coincident(clone)
            modifier = clone.modifiers.new('budget_decimation', 'DECIMATE'); modifier.use_collapse_triangulate = True
            triangles = sum(max(0, len(p.vertices)-2) for p in clone.data.polygons)
            modifier.ratio = min(1.0, max(ratio, 8 / max(triangles, 1)))
            select([clone]); bpy.ops.object.modifier_apply(modifier=modifier.name)
        texture_cap = request.get('game_texture_size')
        if texture_cap:
            # Materials and images are shared with the master; copy them so later renders/exports keep source maps.
            scaled = {}
            for clone in duplicates:
                for slot in clone.material_slots:
                    if not slot.material: continue
                    material = slot.material.copy(); slot.material = material
                    for node in (material.node_tree.nodes if material.use_nodes else []):
                        image = getattr(node, 'image', None)
                        if image is None or max(image.size) <= texture_cap: continue
                        if image.name not in scaled:
                            copy = image.copy(); factor = texture_cap / max(image.size)
                            copy.scale(max(1, round(image.size[0] * factor)), max(1, round(image.size[1] * factor)))
                            scaled[image.name] = copy
                        node.image = scaled[image.name]
            game_ready['texture_cap'] = texture_cap; game_ready['textures_scaled'] = sorted(scaled)
        export_glb(output / 'GAME.glb', duplicates)
        game_ready.update(status='DERIVED', ratio=ratio, meshes=mesh_stats(duplicates), surface_error=surface_reference.compare(duplicates), quality='NEEDS_REVIEW')
        for clone in duplicates: bpy.data.objects.remove(clone, do_unlink=True)
    (output / 'game_ready.json').write_text(json.dumps(game_ready, indent=2), encoding='utf-8')
    del surface_reference
    bpy.ops.mesh.primitive_cube_add(size=1, location=Vector(low).lerp(Vector(high), 0.5))
    collider = bpy.context.object; collider.name = 'COLLIDER_AABB'; collider.dimensions = Vector(high) - Vector(low)
    select([collider]); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    export_glb(output / 'collider.glb', [collider]); bpy.data.objects.remove(collider, do_unlink=True)
    rendered, framing = render_views(objects, output, cfg, request.get('resolutions', ['mobile', 'pc1440']), request.get('views', list(cfg['views']))) if request.get('render', True) else ([], [])
    report = {'status': 'NEEDS_REVIEW', 'input_sha256': sha(source), 'script_sha256': sha(__file__),
              'blender_version': bpy.app.version_string, 'dimensions_xyz_m_blender': [high[i]-low[i] for i in range(3)],
              'normalization': {'applied': request.get('normalize', False), 'target_height_m': target_height, 'scale': scale, 'yaw_degrees': request.get('yaw_degrees', 0)},
              'before': before, 'after': after, 'materials': materials, 'lods': lod_stats,'material_edit':material_change,
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
    reopened_fbx = []
    for path in sorted(output.glob('*.fbx')):
        bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=str(path))
        imported = [o for o in bpy.context.scene.objects if o.type == 'MESH']
        if not imported: raise ValueError(f'FBX export cannot reopen: {path.name}')
        reopened_fbx.append({'file': path.name, 'meshes': mesh_stats(imported), 'bounds_blender_m': bounds(imported)})
    report['reopened_fbx'] = reopened_fbx
    report['checks']['fbx_reopen'] = 'PASS' if reopened_fbx else 'NOT_TESTED'
    report['checks']['fbx_pbr_unity_mapping'] = 'NOT_TESTED'
    report['artifacts'] = [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in output.rglob('*') if p.is_file()]
    write(output / 'report.json', report)
    print('AFS_PIPELINE_SUCCESS ' + str(output / 'report.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    run(json.loads(Path(args.request).read_text(encoding='utf-8-sig')))
