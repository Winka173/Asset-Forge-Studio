"""Retarget a Kimodo BVH (SOMA skeleton) onto an AFS auto-rigged character (UniRig, generic bone names).

blender -b --factory-startup --python retarget_clip.py -- --character rigged.glb --bvh motion.bvh --output out_dir --name clip

1. Identify the character's humanoid bones from topology and rest positions (root = hips; the chain going up is the
   spine, branching at the chest into neck/head and two arms; the two chains going down are legs; character left is
   up x forward, forward from the feet towards the toes). No reliance on bone_N numbering.
2. Face the source the same way as the character and scale root motion by leg length.
3. Per frame, each mapped bone gets the source bone's world rotation change since rest, after first turning the
   character's rest bone onto the source rest direction. A character bound in A-pose therefore follows a T-pose
   source correctly. Unmapped bones (fingers, extra joints) keep their rest pose relative to their parent.
Writes the character with one clip as GLB (mesh, skin and textures unchanged) plus a report with the bone map.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

UP = Vector((0, 0, 1))


def args():
    p = argparse.ArgumentParser()
    for name in ('--character', '--bvh', '--output'): p.add_argument(name, required=True)
    p.add_argument('--name', default='clip')
    return p.parse_args(sys.argv[sys.argv.index('--') + 1:])


def world_head(arm, bone): return arm.matrix_world @ bone.head_local
def world_tail(arm, bone): return arm.matrix_world @ bone.tail_local


def chain(bone, pick):
    out = [bone]
    while True:
        kids = [c for c in out[-1].children if pick(c)]
        if len(kids) != 1: return out, kids
        out.append(kids[0])


def identify(arm):
    """Humanoid roles for a generic skeleton; raises if the shape is not a recognisable biped."""
    bones = arm.data.bones; roots = [b for b in bones if b.parent is None]
    if len(roots) != 1: raise ValueError(f'Expected one root bone, found {len(roots)}')
    hips = roots[0]; h = world_head(arm, hips)
    up_kids = [c for c in hips.children if world_tail(arm, c).z > h.z]
    down_kids = [c for c in hips.children if world_tail(arm, c).z < h.z]
    if len(up_kids) != 1 or len(down_kids) != 2: raise ValueError('Hips need one spine child and two leg children')
    spine, branch = chain(up_kids[0], lambda c: True)
    chest = spine[-1]
    if len(branch) != 3: raise ValueError(f'Chest should branch into neck and two arms, found {len(branch)}')
    neck = max(branch, key=lambda c: world_tail(arm, c).z - abs(world_head(arm, c).x - h.x))
    shoulders = [c for c in branch if c != neck]
    legs = [chain(k, lambda c: True)[0] for k in down_kids]
    feet = [leg[2] if len(leg) > 3 else leg[-1] for leg in legs]
    toes = [leg[3] if len(leg) > 3 else leg[-1] for leg in legs]
    forward = sum(((world_tail(arm, t) - world_head(arm, f)) for f, t in zip(feet, toes)), Vector()); forward.z = 0
    if forward.length < 1e-4: raise ValueError('Cannot tell which way the character faces from its feet')
    forward.normalize(); left = UP.cross(forward)
    side = lambda b: (world_head(arm, b) - h).dot(left)
    roles = {'Hips': hips}
    spine_names = ['Spine1', 'Spine2', 'Chest']
    for name, bone in zip(spine_names[-len(spine):] if len(spine) <= 3 else spine_names, spine if len(spine) <= 3 else [spine[0], spine[len(spine) // 2], spine[-1]]): roles[name] = bone
    head_chain = chain(neck, lambda c: True)[0]; roles['Neck1'] = head_chain[0]
    if len(head_chain) > 1: roles['Head'] = head_chain[1]
    for shoulder in shoulders:
        prefix = 'Left' if side(shoulder) > 0 else 'Right'; arm_chain = chain(shoulder, lambda c: True)[0]
        for name, bone in zip(('Shoulder', 'Arm', 'ForeArm', 'Hand'), arm_chain): roles[prefix + name] = bone
    for leg in legs:
        prefix = 'Left' if side(leg[0]) > 0 else 'Right'
        for name, bone in zip(('Leg', 'Shin', 'Foot', 'ToeBase'), leg): roles[prefix + name] = bone
    if {'LeftArm', 'RightArm', 'LeftLeg', 'RightLeg'} - roles.keys(): raise ValueError('Could not find both arms and both legs')
    return roles, forward


def import_character(path):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    return next(o for o in new if o.type == 'ARMATURE'), new


def main():
    a = args(); out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    target, imported = import_character(a.character)
    for o in imported:  # the character's own clips (none expected) are dropped so the export holds one clip
        if o.animation_data: o.animation_data_clear()
    bpy.ops.import_anim.bvh(filepath=a.bvh, global_scale=0.01, frame_start=1, use_fps_scale=False, update_scene_fps=True, update_scene_duration=True,
                            rotate_mode='NATIVE', axis_forward='-Z', axis_up='Y')
    source = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE' and o != target)
    first, last = source.animation_data.action.frame_range; scene = bpy.context.scene; scene.frame_start, scene.frame_end = int(first), int(last)
    roles, t_forward = identify(target)
    sb = source.data.bones
    missing = [n for n in roles if n not in sb]
    if missing: raise ValueError(f'Source skeleton lacks {missing}')
    # Face the source like the character (rotation about the vertical through the world origin).
    s_forward = sum(((world_tail(source, sb[n + 'ToeBase']) - world_head(source, sb[n + 'Foot'])) for n in ('Left', 'Right')), Vector()); s_forward.z = 0; s_forward.normalize()
    # Yaw only: rotation_difference of opposite vectors may pick a tilted axis and turn the source upside down.
    face = Matrix.Rotation(math.atan2(t_forward.y, t_forward.x) - math.atan2(s_forward.y, s_forward.x), 4, 'Z')
    leg = lambda arm, bones: (world_head(arm, bones['LeftLeg']) - world_head(arm, bones['LeftFoot'])).length
    scale = leg(target, {k: v for k, v in roles.items()}) / max(leg(source, sb), 1e-6)
    s_rest = {n: (face @ source.matrix_world @ sb[n].matrix_local).to_quaternion() for n in roles}
    t_rest = {n: (target.matrix_world @ b.matrix_local).to_quaternion() for n, b in roles.items()}
    align = {}
    for n, b in roles.items():  # turn the character's rest bone onto the source's rest direction (limbs, neck, head)
        if n == 'Hips': align[n] = Quaternion(); continue
        dt = (world_tail(target, b) - world_head(target, b)); ds = face.to_3x3() @ (world_tail(source, sb[n]) - world_head(source, sb[n]))
        align[n] = dt.normalized().rotation_difference(ds.normalized()) if dt.length > 1e-6 and ds.length > 1e-6 else Quaternion()
    s_hips_rest = face @ world_head(source, sb['Hips']); t_hips_rest = world_head(target, roles['Hips'])
    order = sorted(target.pose.bones, key=lambda pb: len(pb.bone.parent_recursive))
    role_of = {b.name: n for n, b in roles.items()}
    target_inv = target.matrix_world.inverted()
    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        pose = {}  # armature-space pose matrices of the target, parents first
        for pb in order:
            bone = pb.bone; n = role_of.get(bone.name)
            parent_pose = pose[bone.parent.name] if bone.parent else Matrix.Identity(4)
            rest_from_parent = (bone.parent.matrix_local.inverted() @ bone.matrix_local) if bone.parent else bone.matrix_local
            chained = parent_pose @ rest_from_parent
            if n:
                s_now = (face @ source.matrix_world @ source.pose.bones[n].matrix).to_quaternion()
                world_rot = s_now @ s_rest[n].inverted() @ align[n] @ t_rest[n]
                rot = (target_inv.to_quaternion() @ world_rot).to_matrix().to_4x4()
                location = chained.to_translation()
                if n == 'Hips':
                    moved = t_hips_rest + (face @ source.matrix_world @ source.pose.bones['Hips'].head - s_hips_rest) * scale
                    location = target_inv @ moved
                desired = Matrix.Translation(location) @ rot
            else:
                desired = chained
            pose[bone.name] = desired
            pb.matrix_basis = chained.inverted() @ desired  # pose = parent pose @ rest offset @ basis
            pb.keyframe_insert('location', frame=frame); pb.keyframe_insert('rotation_quaternion', frame=frame)
    action = target.animation_data.action; action.name = a.name
    bpy.data.objects.remove(source, do_unlink=True)
    for other in [x for x in bpy.data.actions if x != action]: bpy.data.actions.remove(other)  # only the retargeted clip is exported
    # Motion check: the hands and feet actually move.
    probe = [roles['LeftHand'] if 'LeftHand' in roles else roles['LeftForeArm'], roles['RightFoot'] if 'RightFoot' in roles else roles['RightShin']]
    tracks = []
    for frame in (scene.frame_start, (scene.frame_start + scene.frame_end) // 2, scene.frame_end):
        scene.frame_set(frame); tracks.append([target.matrix_world @ target.pose.bones[b.name].head for b in probe])
    travel = max((tracks[i][j] - tracks[0][j]).length for i in range(1, len(tracks)) for j in range(len(probe)))
    glb = out / f'{a.name}.glb'
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', export_animations=True, export_skins=True, export_animation_mode='ACTIONS')
    report = dict(name=a.name, frames=scene.frame_end - scene.frame_start + 1, fps=scene.render.fps / scene.render.fps_base, bone_map={n: b.name for n, b in roles.items()},
                  mapped=len(roles), character_bones=len(target.data.bones), root_motion_scale=round(scale, 4), glb=str(glb), max_extremity_travel_m=round(travel, 3),
                  checks=dict(bones_mapped=len(roles) >= 14, moves=travel > 0.02, glb_written=glb.stat().st_size > 0),
                  method='world rotation delta from rest with per-bone rest alignment; root motion scaled by leg length')
    (out / 'retarget.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
