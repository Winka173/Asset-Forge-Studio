"""Front three-quarter render of a model with a 1.75 m person standing at its front, for a human-scale check.

blender -b --factory-startup --python scale_person_render.py -- --input model.glb --output view.png [--person-m 1.75] [--size 768]
The person is a plain red figure (body, head) on the ground in front of the model; the model's own meshes are unchanged.
"""
import argparse
import math
import sys

import bpy
from mathutils import Vector


def main():
    p = argparse.ArgumentParser(); p.add_argument('--input', required=True); p.add_argument('--output', required=True)
    p.add_argument('--person-m', type=float, default=1.75); p.add_argument('--size', type=int, default=768)
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=a.input)
    sc = bpy.context.scene; objs = [o for o in sc.objects if o.type == 'MESH']
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    h = a.person_m; red = bpy.data.materials.new('Person'); red.use_nodes = True
    red.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.85, 0.08, 0.06, 1)
    # Standing just in front of the model's front face (-Y), a little left of centre so it does not hide the entrance.
    x, y = lo.x + (hi.x - lo.x) * 0.3, lo.y - h * 0.4
    bpy.ops.mesh.primitive_cylinder_add(radius=h * 0.13, depth=h * 0.86, location=(x, y, lo.z + h * 0.43)); bpy.context.object.data.materials.append(red)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=h * 0.07, location=(x, y, lo.z + h * 0.93)); bpy.context.object.data.materials.append(red)
    mid = (lo + hi) / 2; size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = size * 1.25
    direction = Vector((0.55, -1.0, 0.35)).normalized(); cam.location = mid + direction * size * 3
    cam.rotation_euler = (mid - cam.location).to_track_quat('-Z', 'Y').to_euler(); cam.data.clip_end = size * 10
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 4; sun.rotation_euler = (math.radians(50), 0, math.radians(30)); sc.collection.objects.link(sun)
    world = bpy.data.worlds.new('w'); world.use_nodes = True; world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.7; sc.world = world
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 16
    sc.render.resolution_x = sc.render.resolution_y = a.size; sc.render.filepath = a.output
    bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    main()
