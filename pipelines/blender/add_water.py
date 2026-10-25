"""Add a water surface inside a model's basin (well, fountain, pool) as its own mesh named "Water".

blender -b --factory-startup --python add_water.py -- --input in.glb --output out.glb [--color #1fa8d8] [--fill 0.6]
A top-down height map (BVH ray casts) finds the low region at the middle of the model. The level rises until that
region starts to grow past its walls or reaches the model's edge (spill); the surface sits at --fill of that depth above the typical floor. The water is a separate object (emissive, semi-transparent) so an engine shader can replace it.
Nothing is changed when no enclosed basin exists.
"""
import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def add_water(objects, color='#1fa8d8', fill=0.6, grid=161, name=''):
    """Returns (the new "Water" object or None, a report). The model's own objects are not changed."""
    water = None
    deps = bpy.context.evaluated_depsgraph_get(); verts, polys = [], []
    for o in objects:
        mesh = o.evaluated_get(deps).to_mesh(); base = len(verts)
        verts += [o.matrix_world @ v.co for v in mesh.vertices]; polys += [[base + i for i in poly.vertices] for poly in mesh.polygons]
    tree = BVHTree.FromPolygons(verts, polys); pts = np.array([tuple(v) for v in verts])
    lo, hi = pts.min(axis=0), pts.max(axis=0); n = grid
    xs = np.linspace(lo[0], hi[0], n); ys = np.linspace(lo[1], hi[1], n); height = np.full((n, n), lo[2])
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            hit = tree.ray_cast(Vector((x, y, hi[2] + 1)), Vector((0, 0, -1)))
            if hit[0]: height[i, j] = hit[0].z
    # The basin is the low region at the middle of the model. Raise the level until that region reaches the model's edge
    # (the water would run off) and keep the last level that still held it. A courtyard behind walls is rejected by size.
    ci, cj = np.meshgrid(np.arange(n), np.arange(n), indexing='ij'); centre = np.hypot(ci - n / 2, cj - n / 2) < n * 0.25
    def central(region):
        from collections import deque
        seen = np.zeros_like(region); best = []
        for start in zip(*np.nonzero(region & centre)):
            if seen[start]: continue
            queue = deque([start]); seen[start] = True; cells = []
            while queue:
                i, j = queue.popleft(); cells.append((i, j))
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    p2, q2 = i + di, j + dj
                    if 0 <= p2 < n and 0 <= q2 < n and region[p2, q2] and not seen[p2, q2]: seen[p2, q2] = True; queue.append((p2, q2))
            if len(cells) > len(best): best = cells
        return best
    def leaks(cells): return any(i in (0, n - 1) or j in (0, n - 1) for i, j in cells)
    # Steep walls keep the area nearly flat while the level rises; the rim is where it starts to grow again (terraces,
    # the outside). Holes smaller than 1% of the grid (a shaft, gaps between rocks) are not the basin yet.
    spill = None; best = []; first = None; start = None
    for level in np.linspace(float(height[centre].min()), hi[2], 240):
        cells = central(height < level)
        if cells and (leaks(cells) or (first and len(cells) > 1.15 * first)): spill = level; break
        if cells: best = cells
        # The floor is not flat: measure the walls' plateau once the level is 0.3 m above where the floor began.
        if start is None and len(cells) >= 0.01 * n * n: start = level
        if first is None and start is not None and level >= start + 0.3: first = len(cells)
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]; footprint = (hi[0] - lo[0]) * (hi[1] - lo[1]); area = len(best) * dx * dy
    report = dict(input=name, added=False, reason='no enclosed basin at the middle of the model')
    floor = np.array([height[c] for c in best]) if best else np.zeros(1)
    floor_z = float(np.percentile(floor, 50))
    if best and spill is not None and area > 0.5 * footprint: report['reason'] = 'the low region is a courtyard, not a basin'; best = []
    if best and spill is not None and spill - floor_z > 0.3 and area >= 0.005 * footprint:
        top = spill
        # The basin floor is bumpy (rocks, a hole by a pillar): measure from its typical height and keep the surface above
        # nearly all of it so the floor does not poke through the water.
        level = min(top - 0.02, max(floor_z + fill * (top - floor_z), float(np.percentile(floor, 92)) + 0.04))
        region = central(height < level) or best
        # One more cell under the walls so the stone hides the stepped grid edge.
        inside = set(region); region = sorted(inside | {(i + di, j + dj) for i, j in inside for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)) if 0 <= i + di < n and 0 <= j + dj < n})
        bm = bmesh.new()
        for i, j in region:
            x, y = xs[i], ys[j]
            corners = [bm.verts.new((x - dx / 2, y - dy / 2, level)), bm.verts.new((x + dx / 2, y - dy / 2, level)), bm.verts.new((x + dx / 2, y + dy / 2, level)), bm.verts.new((x - dx / 2, y + dy / 2, level))]
            bm.faces.new(corners)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=min(dx, dy) * 0.01)
        data = bpy.data.meshes.new('Water'); bm.to_mesh(data); bm.free()
        water = bpy.data.objects.new('Water', data); bpy.context.scene.collection.objects.link(water)
        rgb = tuple(int(color[k:k + 2], 16) / 255 for k in (1, 3, 5))
        mat = bpy.data.materials.new('Water'); mat.use_nodes = True; bsdf = mat.node_tree.nodes['Principled BSDF']
        bsdf.inputs['Base Color'].default_value = (*rgb, 1); bsdf.inputs['Roughness'].default_value = 0.05; bsdf.inputs['Alpha'].default_value = 0.6; mat.surface_render_method = 'BLENDED'
        bsdf.inputs['Emission Color'].default_value = (*rgb, 1); bsdf.inputs['Emission Strength'].default_value = 0.35
        water.data.materials.append(mat)
        area = len(region) * dx * dy
        report.pop('reason'); report.update(added=True, level_m=round(level, 3), basin_floor_m=round(float(floor_z), 3), spill_level_m=round(float(top), 3), area_m2=round(area, 2), cells=len(region))
    return water, report


def main():
    p = argparse.ArgumentParser(); p.add_argument('--input', required=True); p.add_argument('--output', required=True)
    p.add_argument('--color', default='#1fa8d8'); p.add_argument('--fill', type=float, default=0.6); p.add_argument('--grid', type=int, default=161)
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=a.input)
    _, report = add_water([o for o in bpy.context.scene.objects if o.type == 'MESH'], a.color, a.fill, a.grid, Path(a.input).name)
    bpy.ops.export_scene.gltf(filepath=a.output, export_format='GLB')
    Path(a.output).with_suffix('.water.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('RESULT', json.dumps(report))


if __name__ == '__main__':
    main()
