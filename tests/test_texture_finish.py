"""MV-Adapter texture finishing: moves colour toward the concept without replacing detail, adds roughness, no metal."""
import numpy as np
import pytest
from PIL import Image

trimesh = pytest.importorskip('trimesh'); pytest.importorskip('skimage')


def test_texture_moves_toward_concept_and_gains_roughness(tmp_path):
    from engines.texture_finish import finish
    mesh = trimesh.creation.box()
    uv = np.random.default_rng(1).random((len(mesh.vertices), 2))
    pattern = np.zeros((64, 64, 3), np.uint8); pattern[...] = 70; pattern[::8] = 40  # dark stripes = painted detail
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.PBRMaterial(baseColorTexture=Image.fromarray(pattern)))
    mesh.export(tmp_path / 'in.glb')
    concept = np.zeros((32, 32, 4), np.uint8); concept[8:24, 8:24] = (150, 140, 120, 255)  # brighter warm subject
    Image.fromarray(concept).save(tmp_path / 'concept.png')
    report = finish(tmp_path / 'in.glb', tmp_path / 'concept.png', tmp_path / 'out.glb')
    out = trimesh.load(tmp_path / 'out.glb', force='mesh', process=False).visual.material
    finished = np.asarray(out.baseColorTexture.convert('RGB'), np.float32)
    assert report['lightness_shift'] > 0 and finished.mean() > pattern.mean()
    # Partial shift: the stripes (detail) are still darker than the surrounding paint.
    assert finished[::8].mean() < finished[1::8].mean()
    rough = np.asarray(out.metallicRoughnessTexture.convert('RGB'))
    assert rough[..., 2].max() == 0 and 140 <= rough[..., 1].min() <= rough[..., 1].max() <= 243 and out.metallicFactor == 0.0
