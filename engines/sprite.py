"""2D sprite cutout from a plain-background concept: deterministic, license-clean, no segmentation model.

Background = pixels close to the per-row edge colour (handles vertical studio gradients) that connect to the image
border. Soft alpha from colour distance, colour decontamination against the local background, then square
transparent exports. Measured, not assumed: callers keep the quality report next to the files.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

POLICY_VERSION = 1
NEAR, FAR = 14.0, 42.0  # RGB distance: <= NEAR is background, >= FAR is subject, soft in between
SIZES = (256, 512, 1024)


def _background(rgb):
    """Per-row edge colour (vertical studio gradients), trusted only where it agrees with the whole border.

    An object touching the left/right frame must not become the background colour of its rows.
    """
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    overall = np.median(border, axis=0)
    rows = np.median(np.concatenate([rgb[:, :4], rgb[:, -4:]], axis=1), axis=1)  # (h, 3)
    trusted = np.linalg.norm(rows - overall, axis=1) < 40
    if trusted.any():
        index = np.arange(len(rows))
        rows = np.stack([np.interp(index, index[trusted], rows[trusted, c]) for c in range(3)], axis=1)
    else:
        rows = np.repeat(overall[None], len(rows), axis=0)
    return rows[:, None, :]  # (h, 1, 3)


def _reachable(candidate):
    """Background-like pixels connected to the border (4-neighbour dilation inside the candidate mask)."""
    reach = np.zeros_like(candidate)
    reach[0, :] = candidate[0, :]; reach[-1, :] = candidate[-1, :]; reach[:, 0] = candidate[:, 0]; reach[:, -1] = candidate[:, -1]
    while True:
        grown = reach.copy()
        grown[1:] |= reach[:-1]; grown[:-1] |= reach[1:]; grown[:, 1:] |= reach[:, :-1]; grown[:, :-1] |= reach[:, 1:]
        grown &= candidate
        if (grown == reach).all(): return reach
        reach = grown


def _shadow(rgb, background):
    """Cast/contact shadow: same chromaticity as the background, darker, but not near-black."""
    lum = rgb.sum(axis=2) + 1e-3; bg_lum = background.sum(axis=2) + 1e-3
    chroma = np.linalg.norm(rgb / lum[..., None] - background / bg_lum[..., None], axis=2)
    ratio = lum / bg_lum
    return (chroma < 0.035) & (ratio > 0.35) & (ratio < 1.0)


def _components(mask, keep_ratio=0.02):
    """Keep connected opaque regions at least keep_ratio of the largest (drops watermark text and specks)."""
    h, w = mask.shape; labels = np.zeros((h, w), np.int32); sizes = [0]
    for y0, x0 in zip(*np.nonzero(mask)):
        if labels[y0, x0]: continue
        label = len(sizes); stack = [(y0, x0)]; labels[y0, x0] = label; count = 0
        while stack:
            y, x = stack.pop(); count += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = label; stack.append((ny, nx))
        sizes.append(count)
    if len(sizes) == 1: return mask, 0
    largest = max(sizes); keep = np.array([False] + [n >= keep_ratio * largest for n in sizes[1:]])
    return keep[labels], int((~keep[1:]).sum())


def cutout(path):
    image = Image.open(path).convert('RGB'); rgb = np.asarray(image).astype(np.float32)
    background = _background(rgb)
    distance = np.linalg.norm(rgb - background, axis=2)
    shadow = _shadow(rgb, background)
    reach = _reachable((distance < FAR) | shadow)
    alpha = np.where(reach, np.where(shadow, 0.0, np.clip((distance - NEAR) / (FAR - NEAR), 0, 1)), 1.0)
    # Component analysis on a 256px grid keeps the main object(s) and drops detached text/specks.
    small = np.asarray(Image.fromarray((alpha > 0.5).astype(np.uint8) * 255).resize((256, 256), Image.NEAREST)) > 0
    kept, dropped = _components(small)
    alpha *= np.asarray(Image.fromarray(kept.astype(np.uint8) * 255).resize(alpha.shape[::-1], Image.NEAREST).filter(ImageFilter.MaxFilter(5))) > 0
    alpha = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32) / 255
    safe = np.maximum(alpha[..., None], 1e-3)
    colour = np.clip((rgb - (1 - alpha[..., None]) * background) / safe, 0, 255)  # remove background tint from soft edges
    rgba = np.dstack([colour, alpha * 255]).astype(np.uint8)
    opaque = alpha > 0.5; h, w = alpha.shape
    border = np.concatenate([alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]])
    report = dict(policy_version=POLICY_VERSION, subject_fraction=round(float(opaque.mean()), 4),
                  border_opaque_fraction=round(float((border > 0.5).mean()), 4),
                  background_rgb=[round(float(v), 1) for v in np.median(background, axis=0)[0]],
                  dropped_islands=dropped, method='edge-connected colour keying, shadow removal and main-component selection; no segmentation model')
    report['usable'] = 0.02 <= report['subject_fraction'] <= 0.9 and report['border_opaque_fraction'] < 0.02
    if not opaque.any(): return None, report
    ys, xs = np.nonzero(opaque); box = [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1]
    return Image.fromarray(rgba, 'RGBA').crop(box), report


def export(sprite, folder, sizes=SIZES, margin=0.06):
    """Square, centred, transparent PNGs; never upscales past the source detail silently (reported)."""
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True); files = []
    side = int(max(sprite.size) * (1 + 2 * margin))
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(sprite, ((side - sprite.width) // 2, (side - sprite.height) // 2))
    for size in sizes:
        target = folder / f'sprite_{size}.png'
        canvas.resize((size, size), Image.LANCZOS).save(target, optimize=True)
        files.append(dict(path=target, size=size, upscaled=size > side))
    return files
