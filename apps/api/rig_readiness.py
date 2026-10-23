"""Measured rig-readiness indicators for characters/creatures; evidence for later auto-rigging, not a rig.

Arm gap: share of chest-height rows whose front silhouette splits into arm | torso | arm (width alone is fooled by held weapons).
Symmetry: voxel IoU of the surface against its mirror image across each horizontal axis (best of X/Z, facing unknown).
"""
import numpy as np
import trimesh

POLICY_VERSION = 1


def measure(path, rig_class, samples=60000, grid=40):
    scene = trimesh.load(path, file_type='glb', force='scene', process=False)
    meshes = [trimesh.Trimesh(trimesh.transform_points(scene.geometry[key].vertices, transform), scene.geometry[key].faces, process=False)
              for node in scene.graph.nodes_geometry for transform, key in [scene.graph[node]] if len(scene.geometry[key].faces)]
    mesh = trimesh.util.concatenate(meshes)
    points, _ = trimesh.sample.sample_surface(mesh, samples, seed=7)
    low, high = points.min(axis=0), points.max(axis=0); extent = high - low  # glTF: Y is up
    height = float(extent[1]); spread = float(max(extent[0], extent[2]) / max(height, 1e-6))
    def occupancy(p):
        cells = np.clip(((p - low) / np.maximum(extent, 1e-6) * (grid - 1)).round().astype(int), 0, grid - 1)
        volume = np.zeros((grid, grid, grid), bool); volume[cells[:, 0], cells[:, 1], cells[:, 2]] = True; return volume
    base = occupancy(points); ious = []
    for axis in (0, 2):
        mirrored = points.copy(); mirrored[:, axis] = low[axis] + high[axis] - mirrored[:, axis]
        other = occupancy(mirrored); ious.append(float((base & other).sum() / max(1, (base | other).sum())))
    symmetry = max(ious)
    report = dict(policy_version=POLICY_VERSION, rig_class=rig_class, height_units=round(height, 4), spread_ratio=round(spread, 3), symmetry_iou=round(symmetry, 3))
    if rig_class == 'humanoid':
        # Front silhouette at chest height: arms clear of the torso show as separate runs (arm | torso | arm).
        best = 0.0
        for axis in (0, 2):
            u = ((points[:, axis] - low[axis]) / max(extent[axis], 1e-6) * 63).round().astype(int)
            v = ((points[:, 1] - low[1]) / max(height, 1e-6) * 63).round().astype(int)
            silhouette = np.zeros((64, 64), bool); silhouette[v, u] = True
            rows = [silhouette[r] for r in range(35, 48)]  # 55-75 % of height
            runs = [int(np.sum(row[1:] & ~row[:-1]) + row[0]) for row in rows]
            best = max(best, float(np.mean([n >= 3 for n in runs])))
        report['arm_gap_rows'] = round(best, 3)
        report['limbs_clear'] = best >= 0.5
    report['symmetric'] = symmetry >= 0.55
    report['method'] = 'Surface samples: horizontal spread / height and mirrored voxel IoU; heuristic evidence, no skeleton or skinning tested'
    return report
