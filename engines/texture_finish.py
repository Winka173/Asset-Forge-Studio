"""Material finishing for MV-Adapter textures (shape engines): colour fidelity to the concept and a roughness map.

- Colour: the projected texture tends to come out greyer/darker than the concept. Surface colours (sampled at face
  UVs) are moved part of the way toward the concept foreground in Lab: mean shift on L, a, b and a bounded contrast
  match on L. Bounded and partial, so the painted detail is untouched.
- Roughness: glTF metallicRoughness map (G = roughness from albedo brightness, 0.55-0.95; B = metallic 0). Painted
  albedo carries no metal information, so metallic stays 0 rather than guessed.
The untouched MV-Adapter GLB is kept next to the finished one for provenance.
"""
import numpy as np
from PIL import Image


def _lab(rgb):
    from skimage.color import rgb2lab
    return rgb2lab(np.clip(rgb, 0, 1))


def _rgb(lab):
    from skimage.color import lab2rgb
    return np.clip(lab2rgb(lab), 0, 1)


def surface_samples(mesh, texture):
    uv = mesh.visual.uv[mesh.faces].mean(axis=1)
    h, w = texture.shape[:2]
    x = np.clip((uv[:, 0] * (w - 1)).round().astype(int), 0, w - 1); y = np.clip(((1 - uv[:, 1]) * (h - 1)).round().astype(int), 0, h - 1)
    return texture[y, x]


def finish(source_glb, concept_png, target_glb, strength=0.6):
    import trimesh
    mesh = trimesh.load(source_glb, force='mesh', process=False)
    material = mesh.visual.material
    base = material.baseColorTexture
    texture = np.asarray(base.convert('RGB'), np.float32) / 255
    concept = np.asarray(Image.open(concept_png).convert('RGBA'), np.float32) / 255
    subject = concept[concept[..., 3] > 0.5][:, :3]
    surface = surface_samples(mesh, texture)
    lab_concept, lab_surface = _lab(subject[None])[0], _lab(surface[None])[0]
    mean_c, mean_s = lab_concept.mean(0), lab_surface.mean(0)
    contrast = float(np.clip(lab_concept[:, 0].std() / max(lab_surface[:, 0].std(), 1e-3), 0.85, 1.25))
    lab = _lab(texture)
    lab[..., 0] = (lab[..., 0] - mean_s[0]) * (1 + strength * (contrast - 1)) + mean_s[0] + strength * (mean_c[0] - mean_s[0])
    lab[..., 1:] += strength * (mean_c[1:] - mean_s[1:])
    finished = _rgb(lab)
    luminance = _lab(finished)[..., 0] / 100
    spread = max(float(luminance.std()), 1e-3)
    roughness = np.clip(0.85 - 0.12 * (luminance - float(np.median(luminance))) / spread, 0.55, 0.95)
    packed = np.zeros(finished.shape, np.float32); packed[..., 1] = roughness  # G = roughness, B = metallic (0)
    material.baseColorTexture = Image.fromarray((finished * 255).round().astype(np.uint8))
    material.metallicRoughnessTexture = Image.fromarray((packed * 255).round().astype(np.uint8))
    material.metallicFactor = 0.0; material.roughnessFactor = 1.0
    mesh.export(target_glb)
    return dict(colour_strength=strength, lightness_shift=round(float(mean_c[0] - mean_s[0]), 2), ab_shift=[round(float(v), 2) for v in (mean_c[1:] - mean_s[1:])],
                contrast_ratio=round(contrast, 3), roughness_range=[round(float(roughness.min()), 3), round(float(roughness.max()), 3)], metallic=0.0)
