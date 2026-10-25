"""Seamless (tileable) textures for effect shaders: noise, flame mask, dissolve, caustics, streaks, cells.

Built in the frequency domain (random phases, power-law amplitudes) or with wrapped distances, so every texture tiles
exactly on both axes. Pure numpy; deterministic per seed.
"""
import numpy as np

KINDS = ('noise', 'flame_mask', 'dissolve', 'caustics', 'streaks', 'cells')


def _fbm(size, rng, slope=2.0, anisotropy=(1.0, 1.0)):
    fy = np.fft.fftfreq(size)[:, None] * anisotropy[0]; fx = np.fft.fftfreq(size)[None, :] * anisotropy[1]
    radius = np.sqrt(fx * fx + fy * fy); radius[0, 0] = 1.0
    spectrum = (rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))) / radius ** (slope / 2)
    spectrum[0, 0] = 0
    field = np.real(np.fft.ifft2(spectrum))
    return (field - field.min()) / max(float(np.ptp(field)), 1e-9)


def _cells(size, rng, points=24):
    sites = rng.random((points, 2)) * size; yy, xx = np.mgrid[0:size, 0:size]
    best = np.full((size, size), np.inf); second = np.full((size, size), np.inf)
    for sy, sx in sites:  # wrapped distance: the pattern repeats across tile edges
        dy = np.abs(yy - sy); dx = np.abs(xx - sx); d = np.hypot(np.minimum(dy, size - dy), np.minimum(dx, size - dx))
        second = np.where(d < best, best, np.minimum(second, d)); best = np.minimum(best, d)
    edge = second - best
    return 1 - np.clip(edge / max(float(np.percentile(edge, 60)), 1e-9), 0, 1)


def generate(kind, size=1024, seed=42):
    if kind not in KINDS: raise ValueError(f'Unknown texture kind {kind}')
    rng = np.random.default_rng(seed)
    if kind == 'noise': value = _fbm(size, rng)
    elif kind == 'dissolve': value = _fbm(size, rng, slope=1.6)
    elif kind == 'flame_mask':  # tongues rising: stretched noise, brighter at the bottom; still tiles vertically for scrolling
        value = np.clip(_fbm(size, rng, slope=2.2, anisotropy=(0.35, 1.0)) * 1.3 - 0.15, 0, 1)
    elif kind == 'caustics':
        warp = _fbm(size, rng, slope=2.4); value = 1 - np.abs(np.sin(warp * np.pi * 6)); value = value ** 3
    elif kind == 'streaks': value = _fbm(size, rng, slope=2.0, anisotropy=(0.08, 1.0))
    else: value = _cells(size, rng)
    return (np.clip(value, 0, 1) * 255).round().astype(np.uint8)


def seam_error(image):
    """Mean absolute step across the wrap seam relative to an inner step; ~1 means seamless."""
    a = image.astype(np.float32)
    seam = np.abs(a[:, 0] - a[:, -1]).mean() + np.abs(a[0, :] - a[-1, :]).mean()
    inner = np.abs(a[:, 1] - a[:, 0]).mean() + np.abs(a[1, :] - a[0, :]).mean()
    return float(seam / max(inner, 1e-6))
