"""Hue-preserving rendering harmonization toward the project style anchor.

Aligns the subject's lightness distribution and chroma level (CIE Lab/LCh) partially toward the anchor's subject,
while every pixel keeps its hue: a requested red dragon stays red, but shares the anchor's contrast and
saturation level. Background pixels are untouched. Deterministic; the original image stays immutable.
"""
import numpy as np
from PIL import Image

POLICY_VERSION = 1
_M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def _to_lab(rgb):
    c = rgb / 255.0; c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ _M.T / _WHITE
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def _to_rgb(lab):
    fy = (lab[..., 0] + 16) / 116; fx = fy + lab[..., 1] / 500; fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], axis=-1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * _WHITE
    c = xyz @ np.linalg.inv(_M).T
    c = np.where(c > 0.0031308, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.clip(c * 255, 0, 255)


def subject_mask(rgb):
    """Object pixels: not part of the edge-connected background (gradient-aware, shared with the sprite cutout)."""
    from .sprite import _background, _reachable, _shadow, FAR
    background = _background(rgb.astype(np.float32))
    distance = np.linalg.norm(rgb - background, axis=2)
    return ~_reachable((distance < FAR) | _shadow(rgb, background))


def stats(rgb, mask=None):
    lab = _to_lab(rgb); mask = subject_mask(rgb) if mask is None else mask
    lightness = lab[..., 0][mask]; chroma = np.hypot(lab[..., 1], lab[..., 2])[mask]
    return dict(l_mean=float(lightness.mean()), l_std=float(lightness.std()), c_mean=float(chroma.mean()), fraction=float(mask.mean()))


def harmonize(image_path, anchor_path, strength=0.5):
    """Returns (RGB image, report). strength 0 = unchanged, 1 = full match of lightness/chroma statistics."""
    rgb = np.asarray(Image.open(image_path).convert('RGB')).astype(np.float64)
    anchor = np.asarray(Image.open(anchor_path).convert('RGB')).astype(np.float64)
    mask = subject_mask(rgb); anchor_mask = subject_mask(anchor)
    if mask.mean() < 0.01 or anchor_mask.mean() < 0.01:
        # Colour keying found no object (low contrast against its background): never guess statistics.
        return Image.fromarray(rgb.astype(np.uint8)), dict(policy_version=POLICY_VERSION, strength=0.0, skipped='No measurable object in the image or the anchor')
    target = stats(anchor, anchor_mask); before = stats(rgb, mask)
    lab = _to_lab(rgb); lightness, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    chroma = np.hypot(a, b); hue = np.arctan2(b, a)
    l_scale = 1 + strength * (target['l_std'] / max(before['l_std'], 1e-3) - 1)
    l_new = (lightness - before['l_mean']) * l_scale + before['l_mean'] + strength * (target['l_mean'] - before['l_mean'])
    # Near-grey pixels have an unstable hue: the chroma change fades in with chroma and is bounded.
    factor = np.clip(1 + strength * (target['c_mean'] / max(before['c_mean'], 1e-3) - 1), 0.6, 1.8)
    c_new = chroma * (1 + (factor - 1) * np.clip(chroma / 10, 0, 1))
    out = np.stack([np.clip(l_new, 0, 100), c_new * np.cos(hue), c_new * np.sin(hue)], axis=-1)
    result = rgb.copy(); result[mask] = _to_rgb(out)[mask]
    after = stats(result, mask)
    hue_shift = np.degrees(np.abs(np.angle(np.exp(1j * (np.arctan2(_to_lab(result)[..., 2], _to_lab(result)[..., 1]) - hue)))))[mask & (chroma > 12)]
    report = dict(policy_version=POLICY_VERSION, strength=strength, anchor=target, before=before, after=after,
                  median_hue_shift_degrees=round(float(np.median(hue_shift)) if hue_shift.size else 0.0, 3))
    return Image.fromarray(result.astype(np.uint8)), report
