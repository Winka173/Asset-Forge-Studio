"""Rig-readiness evidence separates arms clear of the torso from arms against it (weapons do not fake it)."""
import trimesh
from apps.api.rig_readiness import measure


def _figure(path, arm_offset, sword=False):
    parts = [trimesh.creation.box((0.5, 0.8, 0.3), trimesh.transformations.translation_matrix((0, 1.3, 0))),   # torso
             trimesh.creation.box((0.2, 0.3, 0.2), trimesh.transformations.translation_matrix((0, 1.85, 0))),  # head
             trimesh.creation.box((0.18, 0.9, 0.2), trimesh.transformations.translation_matrix((-0.15, 0.45, 0))),
             trimesh.creation.box((0.18, 0.9, 0.2), trimesh.transformations.translation_matrix((0.15, 0.45, 0)))]
    for side in (-1, 1):
        parts.append(trimesh.creation.box((0.12, 0.7, 0.12), trimesh.transformations.translation_matrix((side * arm_offset, 1.3, 0))))
    if sword: parts.append(trimesh.creation.box((1.6, 0.06, 0.06), trimesh.transformations.translation_matrix((0.6, 0.9, 0))))
    trimesh.util.concatenate(parts).export(path); return path


def test_arms_clear_of_the_torso_are_recognised(tmp_path):
    assert measure(_figure(tmp_path / 'apose.glb', 0.55), 'humanoid')['limbs_clear'] is True
    assert measure(_figure(tmp_path / 'down.glb', 0.31), 'humanoid')['limbs_clear'] is False


def test_a_held_weapon_does_not_fake_clear_arms(tmp_path):
    report = measure(_figure(tmp_path / 'sword.glb', 0.31, sword=True), 'humanoid')
    assert report['spread_ratio'] > 0.8 and report['limbs_clear'] is False
