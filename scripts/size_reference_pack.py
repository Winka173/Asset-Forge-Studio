"""Blender script: make a light, real-model scale reference for the Size & scale preview.

blender -b --factory-startup -P scripts/size_reference_pack.py -- <in.glb> <out.glb> <height_m> [triangles] [texture_px]
Decimates to about `triangles`, caps textures at `texture_px`, scales to `height_m` with the base at Y=0, centred on X/Z.
"""
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
source, target, height = args[0], args[1], float(args[2])
triangles = int(args[3]) if len(args) > 3 else 20000
texture = int(args[4]) if len(args) > 4 else 512

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=source)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
total = sum(len(p.vertices) - 2 for o in meshes for p in o.data.polygons)
ratio = min(1.0, triangles / max(total, 1))
for obj in meshes:
    if ratio < 1.0:
        modifier = obj.modifiers.new('decimate', 'DECIMATE'); modifier.ratio = ratio
        bpy.context.view_layer.objects.active = obj; bpy.ops.object.modifier_apply(modifier=modifier.name)
for image in bpy.data.images:
    w, h = image.size
    if max(w, h) > texture:
        s = texture / max(w, h); image.scale(max(1, int(w * s)), max(1, int(h * s)))

# Uniform scale to the reference height, base on the ground, centred.
corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
low = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
high = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
scale = height / max(high.z - low.z, 1e-6)
root = bpy.data.objects.new('reference', None); bpy.context.scene.collection.objects.link(root)
for obj in bpy.context.scene.objects:
    if obj.parent is None and obj is not root: obj.parent = root
root.scale = (scale, scale, scale)
root.location = (-(low.x + high.x) / 2 * scale, -(low.y + high.y) / 2 * scale, -low.z * scale)
bpy.ops.export_scene.gltf(filepath=target, export_format='GLB', export_image_format='JPEG', export_apply=True)
print('REFERENCE', target, 'triangles', min(total, triangles), 'from', total, 'scale', round(scale, 4))
