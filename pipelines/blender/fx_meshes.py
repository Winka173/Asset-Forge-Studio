"""Mesh effects exported as GLB: shockwave ring, shield bubble, ground crack decal, projectile trail.

blender -b --factory-startup --python fx_meshes.py -- --request request.json
request: {"kind", "color": "#rrggbb", "seed", "output"}
Unlit-looking emissive materials with alpha textures (alpha blend); the shockwave carries a scale animation. Fading
over time and scrolling textures are left to the engine's shader (glTF has no portable material animation).
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np


def image(name, rgba):
    h, w = rgba.shape[:2]; img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels = np.flipud(rgba).astype(np.float32).ravel(); img.pack()
    return img


def material(name, colour, texture, emit=4.0):
    mat = bpy.data.materials.new(name); mat.use_nodes = True; nodes = mat.node_tree.nodes; links = mat.node_tree.links
    bsdf = nodes['Principled BSDF']; tex = nodes.new('ShaderNodeTexImage'); tex.image = texture
    bsdf.inputs['Base Color'].default_value = (*colour, 1); bsdf.inputs['Emission Color'].default_value = (*colour, 1); bsdf.inputs['Emission Strength'].default_value = emit
    links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha']); links.new(tex.outputs['Color'], bsdf.inputs['Emission Color'])
    mat.blend_method = 'BLEND' if hasattr(mat, 'blend_method') else None
    return mat


def ring_texture(colour, size=256):
    v = np.linspace(0, 1, size)[:, None] * np.ones((1, 8))  # v runs inner -> outer edge
    alpha = np.exp(-((v - 0.65) / 0.18) ** 2); rgb = np.ones((size, 8, 3)) * colour
    return np.dstack([rgb, alpha])


def shield_texture(colour, size=512):
    yy, xx = np.mgrid[0:size, 0:size * 2] / size
    hexes = np.minimum(np.abs(np.sin(xx * math.pi * 14)), np.abs(np.sin((xx * 0.5 + yy * 0.866) * math.pi * 14)))
    lines = np.clip(1 - hexes * 6, 0, 1); rim = np.clip(np.abs(yy - 0.5) * 2, 0, 1) ** 3
    alpha = np.clip(0.12 + 0.55 * lines + 0.5 * rim, 0, 1)
    return np.dstack([np.ones(alpha.shape + (3,)) * colour, alpha])


def crack_texture(colour, rng, size=512):
    canvas = np.zeros((size, size)); c = size // 2
    def walk(y, x, angle, length, width):
        for _ in range(length):
            angle += rng.normal(0, 0.25); y += math.sin(angle) * 2; x += math.cos(angle) * 2
            iy, ix = int(y), int(x)
            if not (2 <= iy < size - 2 and 2 <= ix < size - 2): return
            canvas[iy - width:iy + width + 1, ix - width:ix + width + 1] = 1
            if rng.random() < 0.02 and width > 0: walk(y, x, angle + rng.choice([-1, 1]) * rng.uniform(0.5, 1.1), length // 2, width - 1)
    for k in range(7): walk(c, c, k / 7 * math.tau + rng.normal(0, 0.2), size // 2, 2)
    from_center = np.hypot(*np.mgrid[0:size, 0:size] - c) / c; glow = canvas * np.clip(1 - from_center, 0.2, 1)
    rgb = np.dstack([glow * colour[0] + (1 - glow) * 0.05, glow * colour[1] + (1 - glow) * 0.04, glow * colour[2] + (1 - glow) * 0.03])
    return np.dstack([rgb, np.clip(canvas, 0, 1)])


def trail_texture(colour, size=256):
    u = np.linspace(0, 1, size * 2)[None, :]; v = np.linspace(-1, 1, size)[:, None]
    alpha = (u ** 1.5) * np.exp(-(v / 0.45) ** 2); return np.dstack([np.ones(alpha.shape + (3,)) * colour, alpha])


def build(req):
    kind = req['kind']; colour = tuple(int(req.get('color', '#ffb347')[i:i + 2], 16) / 255 for i in (1, 3, 5)); rng = np.random.default_rng(int(req.get('seed', 42)))
    bpy.ops.wm.read_factory_settings(use_empty=True); scene = bpy.context.scene; scene.render.fps = 24
    if kind == 'shockwave':
        mesh = bpy.data.meshes.new('Shockwave'); bm = bmesh.new(); seg = 64; uv = bm.loops.layers.uv.new()
        inner = [bm.verts.new((0.7 * math.cos(a), 0.7 * math.sin(a), 0)) for a in np.linspace(0, math.tau, seg, endpoint=False)]
        outer = [bm.verts.new((1.0 * math.cos(a), 1.0 * math.sin(a), 0)) for a in np.linspace(0, math.tau, seg, endpoint=False)]
        for i in range(seg):
            j = (i + 1) % seg; f = bm.faces.new((inner[i], inner[j], outer[j], outer[i]))
            for loop, (u, v) in zip(f.loops, ((i / seg, 0), ((i + 1) / seg, 0), ((i + 1) / seg, 1), (i / seg, 1))): loop[uv].uv = (u, v)
        bm.to_mesh(mesh); bm.free(); obj = bpy.data.objects.new('Shockwave', mesh); scene.collection.objects.link(obj)
        obj.data.materials.append(material('Shockwave', colour, image('shockwave', ring_texture(colour))))
        for frame, s in ((1, 0.1), (18, 1.0)): obj.scale = (s, s, s); obj.keyframe_insert('scale', frame=frame)
        scene.frame_start, scene.frame_end = 1, 18
    elif kind == 'shield':
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0); obj = bpy.context.object; obj.name = 'Shield'
        bpy.ops.object.shade_smooth(); obj.data.materials.append(material('Shield', colour, image('shield', shield_texture(colour)), emit=2.5))
    elif kind == 'crack':
        bpy.ops.mesh.primitive_plane_add(size=2.0); obj = bpy.context.object; obj.name = 'GroundCrack'; obj.location.z = 0.01
        obj.data.materials.append(material('GroundCrack', colour, image('crack', crack_texture(colour, rng)), emit=3.0))
    elif kind == 'trail':
        bpy.ops.mesh.primitive_plane_add(size=1.0); obj = bpy.context.object; obj.name = 'Trail'; obj.scale = (3.0, 0.35, 1); obj.rotation_euler = (math.pi / 2, 0, 0)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        obj.data.materials.append(material('Trail', colour, image('trail', trail_texture(colour)), emit=5.0))
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.16, location=(1.5, 0, 0)); head = bpy.context.object; head.name = 'TrailHead'
        head.data.materials.append(material('TrailHead', colour, image('head', np.ones((4, 4, 4))), emit=8.0))
    else:
        raise ValueError(f'Unknown mesh effect {kind}')
    out = Path(req['output']); out.mkdir(parents=True, exist_ok=True); glb = out / f'{kind}.glb'
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', export_animations=kind == 'shockwave', export_image_format='AUTO')
    report = dict(kind=kind, glb=str(glb), bytes=glb.stat().st_size, colour=req.get('color'), animated=kind == 'shockwave', blender=bpy.app.version_string,
                  checks=dict(glb_written=glb.stat().st_size > 1000), notes='Alpha-blended emissive material; fade and texture scrolling belong to the engine shader')
    (out / 'fx_mesh.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--request', required=True)
    build(json.loads(Path(a.parse_args(sys.argv[sys.argv.index('--') + 1:]).request).read_text(encoding='utf-8')))
