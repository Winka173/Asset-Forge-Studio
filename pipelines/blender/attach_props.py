"""Attach held props (sword, shield, ...) to an auto-rigged character's hand bones so every clip carries them.

blender -b --factory-startup --python attach_props.py -- --character animated.glb --prop sword.glb right_hand 1.0 --prop shield.glb left_hand 0.75
                                                       --output equipped.glb --report report.json
Hands are found by shape (retarget_clip.identify), so generic and humanoid bone names both work. In the rest pose each
prop is scaled to its real size (relative to a 1.8 m person, scaled with the character's height) and placed:
right-hand weapons with the grip in the fist and the blade/head pointing forward, left-hand shields strapped to the
forearm facing forward. Props are parented to the bone, so the clip moves them; the character's mesh, skin, textures
and clips are unchanged. Generated props stand upright (their concepts ask for it), so their long axis is Z.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).parent))
from retarget_clip import UP, identify, import_character, world_head, world_tail  # noqa: E402

PERSON_M = 1.8


def import_prop(path, name):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if not meshes: raise ValueError(f'No mesh in {path}')
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    root = bpy.data.objects.new(name, None); bpy.context.scene.collection.objects.link(root)
    # The root sits at the prop's bottom centre (the grip end of an upright weapon) with world axes.
    root.location = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)); bpy.context.view_layer.update()
    for o in meshes:
        if o.parent is None or o.parent not in meshes:
            world = o.matrix_world.copy(); o.parent = root; o.matrix_world = world
    return root, hi - lo


def orient(size, z_dir, thin_dir):
    """Rotation taking the prop's long axis (local Z, it stands upright) to z_dir and its thinnest axis (a shield's face,
    a blade's flat) towards thin_dir."""
    z = z_dir.normalized(); t = (thin_dir - z * thin_dir.dot(z)).normalized()
    if size.x <= size.y: x, y = t, z.cross(t)
    else: y, x = t, t.cross(z)
    return Matrix((x, y, z)).transposed().to_4x4()


def main():
    p = argparse.ArgumentParser(); p.add_argument('--character', required=True); p.add_argument('--output', required=True); p.add_argument('--report', required=True)
    p.add_argument('--prop', nargs=3, action='append', default=[], metavar=('GLB', 'SOCKET', 'LENGTH_M'))
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm, objects = import_character(a.character)
    arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
    roles, forward = identify(arm); left = UP.cross(forward)
    meshes = [o for o in objects if o.type == 'MESH']
    zs = [(o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box]; height = max(zs) - min(zs); scale_to_char = height / PERSON_M
    attached = []
    for path, socket, length in a.prop:
        side = 'Right' if socket.startswith('right') else 'Left'
        hand, forearm = roles[side + 'Hand'], roles[side + 'ForeArm']
        root, size = import_prop(path, Path(path).stem)
        target = float(length) * scale_to_char; s = target / max(size.z, 1e-6)
        if socket.startswith('right'):
            # Grip a tenth of the way up the weapon, in the fist; blade or head points forward and slightly up.
            grip = world_tail(arm, hand).lerp(world_head(arm, hand), 0.5)
            rot = orient(size, forward + UP * 0.25, left)
            m = Matrix.Translation(grip) @ rot @ Matrix.Translation((0, 0, -0.1 * target)) @ Matrix.Diagonal((s, s, s, 1))
            bone = hand
        else:
            # Shield face forward on the outside of the forearm, its height along the forearm.
            mid = world_head(arm, forearm).lerp(world_tail(arm, forearm), 0.55)
            along = (world_tail(arm, forearm) - world_head(arm, forearm)).normalized()
            rot = orient(size, -along, forward)
            m = Matrix.Translation(mid + forward * 0.06 * height + along * 0.5 * target) @ rot @ Matrix.Diagonal((s, s, s, 1))
            bone = forearm
        root.matrix_world = m; bpy.context.view_layer.update()
        world = root.matrix_world.copy(); root.parent = arm; root.parent_type = 'BONE'; root.parent_bone = bone.name
        bpy.context.view_layer.update(); root.matrix_world = world
        attached.append(dict(prop=Path(path).name, socket=socket, bone=bone.name, length_m=round(target, 3), scale=round(s, 4)))
    arm.data.pose_position = 'POSE'; bpy.context.view_layer.update()
    bpy.ops.export_scene.gltf(filepath=a.output, export_format='GLB', export_animations=True)
    Path(a.report).write_text(json.dumps(dict(attached=attached, character_height_m=round(height, 3)), indent=2), encoding='utf-8')
    print('RESULT', json.dumps(attached))


if __name__ == '__main__':
    main()
