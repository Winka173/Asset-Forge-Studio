"""Blender script: render several GLBs of the same asset side by side (same height, same camera, neutral light).

blender -b --factory-startup -P scripts/compare_engines_render.py -- <out.png> <label=path.glb> [label=path.glb ...]
"""
import math
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
out, entries = args[0], [a.split('=', 1) for a in args[1:]]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items} else 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 640 * len(entries), 760
scene.render.film_transparent = False
world = bpy.data.worlds.new('w'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.82, 0.83, 0.86, 1); world.node_tree.nodes['Background'].inputs[1].default_value = 1.0
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 3.0; sun.rotation_euler = (math.radians(50), 0, math.radians(35)); scene.collection.objects.link(sun)
height, spacing = 2.0, 2.6
for index, (label, path) in enumerate(entries):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in set(bpy.data.objects) - before if o.type == 'MESH']
    root = bpy.data.objects.new(label, None); scene.collection.objects.link(root)
    for o in set(bpy.data.objects) - before - {root}:
        if o.parent is None: o.parent = root
    bpy.context.view_layer.update()
    corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    s = height / max(hi.z - lo.z, 1e-6); root.scale = (s, s, s)
    root.location = (index * spacing - (lo.x + hi.x) / 2 * s, -(lo.y + hi.y) / 2 * s, -lo.z * s)
    text = bpy.data.curves.new(label, 'FONT'); text.body = label; text.align_x = 'CENTER'; text.size = 0.16
    caption = bpy.data.objects.new(label + '_text', text); caption.location = (index * spacing, -1.4, 0.02); caption.rotation_euler = (math.radians(70), 0, 0)
    material = bpy.data.materials.new(label + '_ink'); material.diffuse_color = (0.05, 0.05, 0.06, 1); text.materials.append(material)
    scene.collection.objects.link(caption)
centre = (len(entries) - 1) * spacing / 2
camera = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); camera.data.type = 'ORTHO'; camera.data.ortho_scale = spacing * len(entries) * 1.02
camera.location = (centre + 1.2, -12.0, 5.0); scene.collection.objects.link(camera); scene.camera = camera
direction = Vector((centre, 0, 0.9)) - camera.location; camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print('RENDERED', out)
