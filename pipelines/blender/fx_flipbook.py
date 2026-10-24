"""Simulated fire / smoke / explosion flipbook with Blender Mantaflow (local, no AI inference).

Two Blender processes, as headless Mantaflow renders are fragile after a bake in the same session:
  blender -b --factory-startup --python fx_flipbook.py -- --request request.json --phase bake
  blender -b --factory-startup --python fx_flipbook.py -- --request request.json --phase render
The bake writes the scene and the gas cache to output/; render opens that scene, renders evenly spaced frames with
Cycles on the CPU to float EXR at twice the cell size, crops every frame to the union of the effect, tone-maps the
HDR flame and takes alpha from smoke coverage or flame brightness (whichever is larger), so fire does not vanish
when alpha-blended. Frames are downsampled to the cell size and tiled into one sprite sheet.
request: {"preset": "fire|smoke|explosion", "resolution": 64-192, "frames": 16|36|64, "cell": 128-512,
          "samples", "seed", "color": "#rrggbb"|null, "output"}
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np

# Simulation length (24 fps) and the frame the sheet starts at, so a continuous fire is shown once established.
PRESETS = {
    'fire': dict(domain=2.0, flow='BOTH', end=96, first=30, burst=None, fuel=1.2, density=0.6, temperature=1.2, vorticity=0.25, smoke_density=3.0),
    'smoke': dict(domain=3.0, flow='SMOKE', end=96, first=24, burst=None, fuel=0.0, density=1.0, temperature=0.6, vorticity=0.15, smoke_density=8.0),
    'explosion': dict(domain=4.0, flow='BOTH', end=72, first=9, burst=10, fuel=3.0, density=1.4, temperature=3.0, vorticity=0.45, smoke_density=6.0),
}


def args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True); parser.add_argument('--phase', choices=('bake', 'render'), required=True)
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:])


def bake(req, out):
    preset = PRESETS[req['preset']]; size = preset['domain']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene; scene.frame_start = 1; scene.frame_end = preset['end']; scene.render.fps = 24
    bpy.ops.mesh.primitive_cube_add(size=size, location=(0, 0, size / 2)); domain = bpy.context.object; domain.name = 'FX_Domain'
    settings = domain.modifiers.new('Fluid', 'FLUID'); settings.fluid_type = 'DOMAIN'; d = settings.domain_settings
    d.domain_type = 'GAS'; d.resolution_max = int(req['resolution']); d.use_adaptive_domain = False
    d.cache_directory = str(out / 'cache'); d.cache_type = 'ALL'; d.cache_frame_start = 1; d.cache_frame_end = preset['end']
    d.vorticity = preset['vorticity']; d.use_dissolve_smoke = req['preset'] == 'fire'; d.dissolve_speed = 40
    d.flame_vorticity = preset['vorticity']; d.burning_rate = 0.5 if req['preset'] == 'explosion' else 0.75; d.flame_smoke = 1.0 if req['preset'] != 'fire' else 0.4
    radius = size * (0.18 if req['preset'] == 'explosion' else 0.12)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=radius, location=(0, 0, size * (0.4 if req['preset'] == 'explosion' else 0.12)))
    emitter = bpy.context.object; emitter.name = 'FX_Emitter'
    flow = emitter.modifiers.new('Fluid', 'FLUID'); flow.fluid_type = 'FLOW'; f = flow.flow_settings
    f.flow_type = preset['flow']; f.flow_behavior = 'INFLOW'; f.flow_source = 'MESH'; f.surface_distance = radius * 0.5
    f.fuel_amount = preset['fuel']; f.density = preset['density']; f.temperature = preset['temperature']
    f.use_initial_velocity = req['preset'] == 'explosion'; f.velocity_normal = 4.0 if req['preset'] == 'explosion' else 0
    # Seeded turbulence field breaks up the even ball/column shapes; the seed also jitters the emitter.
    rng = np.random.default_rng(int(req['seed'])); emitter.location.x += float(rng.uniform(-0.02, 0.02)) * size; emitter.rotation_euler = tuple(rng.uniform(0, math.tau, 3))
    bpy.ops.object.effector_add(type='TURBULENCE', location=(0, 0, size / 2)); field = bpy.context.object.field
    field.strength = {'fire': 1.0, 'smoke': 1.5, 'explosion': 6.0}[req['preset']]; field.size = size * 0.15; field.seed = int(req['seed']) % 128
    if preset['burst']:  # one burst: emission switches off after a few frames
        for name in ('fuel_amount', 'density', 'temperature'):
            f.keyframe_insert(name, frame=preset['burst'])
            setattr(f, name, 0.0); f.keyframe_insert(name, frame=preset['burst'] + 1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'fx_scene.blend'))
    bpy.context.view_layer.objects.active = domain; domain.select_set(True)
    started = time.monotonic()
    with bpy.context.temp_override(object=domain, active_object=domain, scene=scene):
        result = bpy.ops.fluid.bake_all()
    if 'FINISHED' not in result: raise RuntimeError(f'Mantaflow bake did not finish: {result}')
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'fx_scene.blend'))
    return dict(bake_seconds=round(time.monotonic() - started, 1), sim_frames=preset['end'], domain_m=size)


def material(domain, req):
    preset = PRESETS[req['preset']]
    mat = bpy.data.materials.new('FX_Volume'); mat.use_nodes = True; nodes = mat.node_tree.nodes; links = mat.node_tree.links
    nodes.clear(); output = nodes.new('ShaderNodeOutputMaterial'); volume = nodes.new('ShaderNodeVolumePrincipled')
    density = nodes.new('ShaderNodeAttribute'); density.attribute_name = 'density'
    scale = nodes.new('ShaderNodeMath'); scale.operation = 'MULTIPLY'; scale.inputs[1].default_value = preset['smoke_density']
    links.new(density.outputs['Fac'], scale.inputs[0]); links.new(scale.outputs[0], volume.inputs['Density'])
    smoke = (0.08, 0.08, 0.08, 1) if req['preset'] != 'smoke' else (0.55, 0.55, 0.55, 1)
    if req.get('color'):
        rgb = [int(req['color'][i:i + 2], 16) / 255 for i in (1, 3, 5)]
        if req['preset'] == 'smoke': smoke = (*rgb, 1)
    volume.inputs['Color'].default_value = smoke
    if req['preset'] != 'smoke':
        flame = nodes.new('ShaderNodeAttribute'); flame.attribute_name = 'flame'
        boost = nodes.new('ShaderNodeMath'); boost.operation = 'MULTIPLY'; boost.inputs[1].default_value = 3.0
        links.new(flame.outputs['Fac'], boost.inputs[0]); links.new(boost.outputs[0], volume.inputs['Blackbody Intensity'])
        volume.inputs['Temperature'].default_value = 1500.0
        if req.get('color'):  # tinted (magic) flame: emission colour instead of blackbody
            links.new(boost.outputs[0], volume.inputs['Emission Strength']); volume.inputs['Blackbody Intensity'].default_value = 0
            for link in list(links):
                if link.to_socket == volume.inputs['Blackbody Intensity']: links.remove(link)
            volume.inputs['Emission Color'].default_value = (*[int(req['color'][i:i + 2], 16) / 255 for i in (1, 3, 5)], 1)
    links.new(volume.outputs['Volume'], output.inputs['Volume'])
    domain.data.materials.clear(); domain.data.materials.append(mat)


FLAME_RAMP = np.array([(0.45, 0.14, 0.08), (0.92, 0.32, 0.10), (1.0, 0.62, 0.16), (1.0, 0.92, 0.48)], np.float32)  # ember, red, orange, yellow core


def stylize(cell, flame=False):
    """Cartoon look for stylized/low-poly games: flat colour bands, crisp three-step opacity, slightly richer colour.
    The simulation's shapes and timing are kept; only the shading is simplified."""
    rgb, alpha = cell[..., :3], cell[..., 3]
    peak = rgb.max(axis=-1, keepdims=True); banded = np.clip(np.ceil(peak * 4) / 4, 0.25, 1.0)
    rgb = rgb * np.where(peak > 1e-4, banded / np.maximum(peak, 1e-4), 0)
    mean = rgb.mean(axis=-1, keepdims=True); rgb = np.clip(mean + (rgb - mean) * 1.25, 0, 1)
    if flame:  # warm (fire-lit) pixels take the cartoon flame ramp by brightness band; smoke stays grey
        warm = (cell[..., 0] - cell[..., 2] > 0.15)[..., None]
        # Bands by brightness rank inside the flame (tone-mapped fire is uniformly bright): 25% yellow core, 35% orange, 25% red, 15% ember.
        lum = cell[..., :3].mean(axis=-1); hot = warm[..., 0] & (alpha > 0.12)
        if hot.any():
            cuts = np.quantile(lum[hot], [0.15, 0.40, 0.75]); band = np.searchsorted(cuts, lum)
            rgb = np.where(hot[..., None], FLAME_RAMP[band], rgb)
    stepped = np.where(alpha < 0.12, 0.0, np.where(alpha < 0.45, 0.6, 1.0)).astype(np.float32)
    padded = np.pad(stepped, 1, mode='edge')  # one-pixel soften so the hard steps do not alias
    soft = sum(padded[1 + dy:1 + dy + stepped.shape[0], 1 + dx:1 + dx + stepped.shape[1]] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
    return np.dstack([rgb, soft]).astype(np.float32)


def render(req, out):
    preset = PRESETS[req['preset']]
    bpy.ops.wm.open_mainfile(filepath=str(out / 'fx_scene.blend'))
    scene = bpy.context.scene; domain = bpy.data.objects['FX_Domain']; bpy.data.objects['FX_Emitter'].hide_render = True
    material(domain, req)
    size = preset['domain']
    camera = bpy.data.cameras.new('FX_Camera'); camera.type = 'ORTHO'; camera.ortho_scale = size * 1.02
    cam = bpy.data.objects.new('FX_Camera', camera); scene.collection.objects.link(cam); scene.camera = cam
    cam.location = (0, -size * 4, size / 2); cam.rotation_euler = (math.pi / 2, 0, 0)
    sun = bpy.data.objects.new('FX_Sun', bpy.data.lights.new('FX_Sun', 'SUN')); sun.data.energy = 3.0; sun.rotation_euler = (0.9, 0.2, 0.6); scene.collection.objects.link(sun)
    world = bpy.data.worlds.new('FX_World'); world.use_nodes = True; world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.0; scene.world = world
    r = scene.render; r.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = int(req.get('samples', 64)); scene.cycles.use_denoising = True
    scene.cycles.volume_step_rate = 1.0; scene.cycles.volume_max_steps = 256
    r.film_transparent = True; work = int(req['cell']) * 2; r.resolution_x = r.resolution_y = work; r.resolution_percentage = 100
    r.image_settings.file_format = 'OPEN_EXR'; r.image_settings.color_mode = 'RGBA'; r.image_settings.color_depth = '32'
    scene.view_settings.view_transform = 'Standard'
    import OpenImageIO as oiio
    count = int(req['frames']); picks = np.linspace(preset['first'], preset['end'], count).round().astype(int)
    frames_dir = out / 'frames'; frames_dir.mkdir(exist_ok=True); started = time.monotonic(); frames = []
    for index, frame in enumerate(picks):
        scene.frame_set(int(frame)); r.filepath = str(frames_dir / f'frame_{index:03d}.exr')
        bpy.ops.render.render(write_still=True)
        frames.append(oiio.ImageBuf(r.filepath).get_pixels(oiio.FLOAT)[..., :4])  # premultiplied linear RGBA, top row first
        print(f'STAGE Render flipbook frame {index + 1}/{count}', flush=True)
    exposure = float(req.get('exposure', 1.0)); graded = []
    for premult in frames:
        rgb = np.clip(premult[..., :3], 0, None); peak = rgb.max(axis=-1, keepdims=True)
        light = rgb * np.where(peak > 1e-6, (1 - np.exp(-peak * exposure)) / np.maximum(peak, 1e-6), exposure)  # HDR to 0..1, hue kept (fire stays orange)
        alpha = np.clip(np.maximum(premult[..., 3], light.max(axis=-1)), 0, 1)
        graded.append(np.dstack([np.where(alpha[..., None] > 1e-4, light / np.maximum(alpha[..., None], 1e-4), 0).clip(0, 1) ** (1 / 2.2), alpha]))
    # Bounds from rows/columns with real coverage over the effect's life (denoiser speckle ignored).
    union = np.max([g[..., 3] for g in graded], axis=0) > 0.15
    ys = np.nonzero(union.mean(axis=1) > 0.01)[0]; xs = np.nonzero(union.mean(axis=0) > 0.01)[0]
    margin = int(work * 0.04)
    if len(xs):  # square crop around everything the effect covers over its life, centred, inside the frame
        side = min(work, max(xs.max() - xs.min(), ys.max() - ys.min()) + 2 * margin)
        cx, cy = (xs.max() + xs.min()) // 2, (ys.max() + ys.min()) // 2
        x0 = int(np.clip(cx - side // 2, 0, work - side)); y0 = int(np.clip(cy - side // 2, 0, work - side))
    else: side, x0, y0 = work, 0, 0
    cell = int(req['cell']); cells = []
    for g in graded:
        crop = np.ascontiguousarray(g[y0:y0 + side, x0:x0 + side]); straight = crop.copy(); straight[..., :3] *= crop[..., 3:]  # resize premultiplied
        resized = oiio.ImageBufAlgo.resize(oiio.ImageBuf(straight), roi=oiio.ROI(0, cell, 0, cell, 0, 1, 0, 4)).get_pixels(oiio.FLOAT)
        a = resized[..., 3:]; resized[..., :3] = np.where(a > 1e-4, resized[..., :3] / np.maximum(a, 1e-4), 0)
        cells.append(stylize(resized.clip(0, 1), flame=req['preset'] != 'smoke' and not req.get('color')) if req.get('look', 'stylized') == 'stylized' else resized.clip(0, 1))
    columns = int(math.ceil(math.sqrt(count))); rows = int(math.ceil(count / columns))
    sheet = np.zeros((rows * cell, columns * cell, 4), np.float32)
    for index, pixels in enumerate(cells):
        y, x = divmod(index, columns); sheet[y * cell:(y + 1) * cell, x * cell:(x + 1) * cell] = pixels
    oiio.ImageBuf(sheet).write(str(out / 'flipbook.png'), oiio.UINT8)
    coverage = [float((c[..., 3] > 0.02).mean()) for c in cells]
    changes = [float(np.abs(cells[i + 1] - cells[i]).mean()) for i in range(len(cells) - 1)]
    edge = max(float(np.concatenate([c[0, :, 3], c[-1, :, 3], c[:, 0, 3], c[:, -1, 3]]).mean()) for c in cells)
    checks = dict(alpha_present=all(v > 0.002 for v in coverage[1:]), not_clipped=edge < 0.35, animates=bool(changes) and min(changes) > 1e-4)
    return dict(render_seconds=round(time.monotonic() - started, 1), sheet=str(out / 'flipbook.png'), columns=columns, rows=rows, cell_px=cell, frames=count,
                crop_m=round(side / work * size * 1.02, 3), sim_frames_used=[int(v) for v in picks], playback_fps=round(count / ((preset['end'] - preset['first'] + 1) / 24), 2),
                alpha_coverage=[round(v, 4) for v in coverage], edge_alpha=round(edge, 4), checks=checks,
                blending='straight alpha (alpha includes flame brightness); also usable additive', loop='not seamless; plays once')


def main():
    a = args(); req = json.loads(Path(a.request).read_text(encoding='utf-8')); out = Path(req['output']); out.mkdir(parents=True, exist_ok=True)
    report_path = out / 'flipbook.json'; report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else dict(preset=req['preset'], request=req)
    report.update(bake(req, out) if a.phase == 'bake' else render(req, out)); report['blender'] = bpy.app.version_string
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
