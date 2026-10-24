"""Kimodo BVH (SOMA 77-joint skeleton, centimetres) to game animation clips: FBX and GLB with the skeleton only.

blender -b --factory-startup --python bvh_to_clip.py -- --bvh motion.bvh --output out_dir --name clip
SOMA joint names follow the common Hips/Spine1/LeftArm/LeftForeArm/LeftLeg/LeftShin pattern; Unity Humanoid
auto-mapping is expected to recognise most of them but is not tested here. Retargeting onto an AFS-rigged character
(generic bone names) is a separate, unimplemented step.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--bvh', required=True); parser.add_argument('--output', required=True); parser.add_argument('--name', default='clip')
    a = parser.parse_args(sys.argv[sys.argv.index('--') + 1:]); out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_anim.bvh(filepath=a.bvh, global_scale=0.01, frame_start=1, use_fps_scale=False, update_scene_fps=True, update_scene_duration=True, rotate_mode='NATIVE', axis_forward='-Z', axis_up='Y')
    armature = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE'); armature.name = a.name
    if armature.animation_data and armature.animation_data.action: armature.animation_data.action.name = a.name
    scene = bpy.context.scene
    if armature.animation_data and armature.animation_data.action:  # the importer only ever extends the default 250-frame range
        first, last = armature.animation_data.action.frame_range; scene.frame_start, scene.frame_end = int(first), max(int(first), int(last))
    hips = armature.pose.bones.get('Hips'); travel = []
    for frame in (scene.frame_start, scene.frame_end):
        scene.frame_set(frame); travel.append(list((armature.matrix_world @ hips.head) if hips else armature.location))
    fbx, glb = out / f'{a.name}.fbx', out / f'{a.name}.glb'
    bpy.ops.export_scene.fbx(filepath=str(fbx), object_types={'ARMATURE'}, add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, apply_unit_scale=True)
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', export_animations=True, export_skins=True)
    report = dict(name=a.name, joints=len(armature.data.bones), frames=scene.frame_end - scene.frame_start + 1, fps=scene.render.fps / scene.render.fps_base,
                  hips_start_m=[round(v, 3) for v in travel[0]], hips_end_m=[round(v, 3) for v in travel[-1]], fbx=str(fbx), glb=str(glb),
                  checks=dict(skeleton=len(armature.data.bones) >= 20, fbx_written=fbx.stat().st_size > 0, glb_written=glb.stat().st_size > 0, hips_found=hips is not None),
                  unity_humanoid='expected from standard joint names; not tested', retarget_to_afs_rig='not implemented')
    (out / 'clip.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
