"""Give an auto-rigged biped standard humanoid bone names so animation clips attach directly.

blender -b --factory-startup --python humanoid_names.py -- --input rigged.glb --output named.glb --report report.json
UniRig names bones bone_0..N. The bones are identified by shape (retarget_clip.identify: hips, spine, neck/head, arms,
legs) and renamed to the Mixamo naming that Unity's Humanoid auto-mapping and common retargeting tools recognise.
Vertex groups follow the rename, so skin weights, mesh and textures are unchanged. Not a biped (four legs, wings):
nothing is renamed and the report says why.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).parent))
from retarget_clip import identify, import_character  # noqa: E402

# retarget_clip roles -> Mixamo names (Unity Humanoid maps these automatically).
MIXAMO = dict(Hips='Hips', Spine1='Spine', Spine2='Spine1', Chest='Spine2', Neck1='Neck', Head='Head')
for side in ('Left', 'Right'):
    MIXAMO.update({side + 'Shoulder': side + 'Shoulder', side + 'Arm': side + 'Arm', side + 'ForeArm': side + 'ForeArm', side + 'Hand': side + 'Hand',
                   side + 'Leg': side + 'UpLeg', side + 'Shin': side + 'Leg', side + 'Foot': side + 'Foot', side + 'ToeBase': side + 'ToeBase'})


def main():
    p = argparse.ArgumentParser(); p.add_argument('--input', required=True); p.add_argument('--output', required=True); p.add_argument('--report', required=True)
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm, _ = import_character(a.input)
    try: roles, _ = identify(arm)
    except ValueError as exc:
        Path(a.report).write_text(json.dumps(dict(humanoid=False, reason=str(exc)), indent=2), encoding='utf-8'); print('RESULT not a biped:', exc); return
    renamed = {}
    for role, bone in roles.items():
        target = MIXAMO.get(role)
        if target and bone.name != target: renamed[bone.name] = target
    # Two passes so a new name never collides with a bone that still has its old name.
    for old in renamed: arm.data.bones[old].name = '__afs_' + old
    for old, new in renamed.items(): arm.data.bones['__afs_' + old].name = new
    bpy.ops.export_scene.gltf(filepath=a.output, export_format='GLB', export_animations=False)
    Path(a.report).write_text(json.dumps(dict(humanoid=True, naming='mixamo', bone_map=renamed, bones=len(arm.data.bones)), indent=2), encoding='utf-8')
    print('RESULT renamed', len(renamed))


if __name__ == '__main__':
    main()
