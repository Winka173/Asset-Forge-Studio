"""Deterministic concept ranking for image-to-3D input suitability (no AI judgment).

A concept is only as useful as the geometry it can drive: the subject must be whole (not touching the frame),
reasonably sized, on a clean background, and — when the project has a style anchor — close to its palette.
Eligibility is conjunctive (cropped subjects are rejected); soft criteria only rank eligible concepts.
"""
import numpy as np
from PIL import Image

POLICY_VERSION = 1


def _rgb(path, size=256):
    with Image.open(path) as im:
        return np.asarray(im.convert('RGB').resize((size, size), Image.BILINEAR), dtype=np.float32) / 255.0


def foreground(rgb):
    """Pixels that differ from the border colour; concepts are generated on plain studio backgrounds."""
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    background = np.median(border, axis=0)
    distance = np.linalg.norm(rgb - background, axis=-1)
    return distance > max(0.08, float(np.percentile(np.linalg.norm(border - background, axis=-1), 95)) * 1.5), border, background


def _palette(rgb, mask, bins=6):
    pixels = rgb[mask] if mask.any() else rgb.reshape(-1, 3)
    hist, _ = np.histogramdd(pixels, bins=bins, range=[(0, 1)] * 3)
    return hist.ravel() / max(hist.sum(), 1)


def subject_box(rgb):
    """Bounding box from edge density: plain studio backgrounds have almost no gradients, even when the subject's
    colours are close to the background (grey stone on grey), which defeats colour-distance segmentation."""
    # Strongest per-channel change: equal-luminance colour edges (orange on grey) vanish in a grey image.
    gradient = np.zeros(rgb.shape[:2], dtype=np.float32)
    gradient[:, 1:] += np.abs(np.diff(rgb, axis=1)).max(axis=-1); gradient[1:, :] += np.abs(np.diff(rgb, axis=0)).max(axis=-1)
    band = np.concatenate([gradient[:3].ravel(), gradient[-3:].ravel(), gradient[:, :3].ravel(), gradient[:, -3:].ravel()])
    edges = gradient > max(0.03, float(np.percentile(band, 99)) * 1.5)
    size = edges.shape[0]
    rows = np.nonzero(edges.sum(axis=1) > size * 0.005)[0]; cols = np.nonzero(edges.sum(axis=0) > size * 0.005)[0]
    if not len(rows) or not len(cols):
        return None, edges
    density = [float(edges[:3].mean()), float(edges[-3:].mean()), float(edges[:, :3].mean()), float(edges[:, -3:].mean())]
    return dict(bbox=[int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())], edge_density=density), edges


def measure(path, anchor_path=None):
    rgb = _rgb(path)
    box, _ = subject_box(rgb)
    if box is None:
        return dict(policy=POLICY_VERSION, eligible=False, reason='No foreground subject detected')
    x0, y0, x1, y1 = box['bbox']; size = rgb.shape[0]
    # Flat subject regions crossing the frame have no gradient at the border, so also look for a side whose pixels
    # split away from that side's dominant background colour.
    sides = [rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]
    split = [float((np.linalg.norm(s - np.median(s, axis=0), axis=-1) > 0.12).mean()) for s in sides]
    touches = sum(d > 0.02 or f > 0.03 for d, f in zip(box['edge_density'], split))
    occupancy = (x1 - x0 + 1) * (y1 - y0 + 1) / size / size
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    background_noise = float(np.linalg.norm(border - np.median(border, axis=0), axis=-1).mean())
    result = dict(policy=POLICY_VERSION, occupancy=round(occupancy, 4), touches_frame_edges=touches,
                  background_noise=round(background_noise, 4), bbox=box['bbox'])
    if touches:
        return result | dict(eligible=False, reason='Subject touches the frame edge; image-to-3D would lose the cropped part')
    if occupancy < 0.06:
        return result | dict(eligible=False, reason='Subject too small for reliable reconstruction')
    framing = 1.0 - min(1.0, abs(occupancy - 0.45) / 0.45)
    clean = max(0.0, 1.0 - background_noise / 0.15)
    score = 0.35 * framing + 0.25 * clean
    if anchor_path:
        anchor = _rgb(anchor_path)
        abox, _ = subject_box(anchor)
        crop = lambda img, b: img[b['bbox'][1]:b['bbox'][3] + 1, b['bbox'][0]:b['bbox'][2] + 1] if b else img
        a, c = crop(rgb, box), crop(anchor, abox)
        palette = float(np.minimum(_palette(a, foreground(a)[0]), _palette(c, foreground(c)[0])).sum())  # histogram intersection
        result['palette_similarity'] = round(palette, 4)
        score += 0.4 * palette
    else:
        score += 0.4 * 0.5  # neutral when there is no anchor to compare against
    return result | dict(eligible=True, score=round(score, 4))


def rank(choices, anchor_path=None):
    """choices: [(artifact, path)] → [(artifact, measurements)] eligible-first, best score first."""
    measured = [(artifact, measure(path, anchor_path)) for artifact, path in choices]
    return sorted(measured, key=lambda m: (not m[1]['eligible'], -m[1].get('score', 0), m[0]['id']))
