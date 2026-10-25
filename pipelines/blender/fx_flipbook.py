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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fx_particles import PARTICLES, build as build_particles  # noqa: E402

# Simulation length (24 fps) and the frame the sheet starts at, so a continuous effect is shown once established.
# radius/z: emitter size and height as a share of the domain; field: turbulence or vortex strength; loop: crossfaded seamless loop.
BASE = dict(burst=None, fuel=0.0, velocity=0.0, dissolve=False, radius=0.12, z=0.12, field=('TURBULENCE', 1.0), loop=False, tint=None, flame_smoke=0.4, burning=0.75)
PRESETS = {name: dict(BASE, **values) for name, values in {
    'fire': dict(domain=2.0, flow='BOTH', end=96, first=30, fuel=1.2, density=0.6, temperature=1.2, vorticity=0.25, smoke_density=3.0, dissolve=True, loop=True),
    'campfire': dict(domain=1.4, flow='BOTH', end=120, first=40, fuel=1.0, density=0.4, temperature=1.0, vorticity=0.3, smoke_density=2.0, dissolve=True, radius=0.16, z=0.06, field=('TURBULENCE', 0.8), loop=True),
    'torch': dict(domain=1.0, flow='BOTH', end=120, first=40, fuel=1.4, density=0.3, temperature=1.3, vorticity=0.35, smoke_density=1.5, dissolve=True, radius=0.07, z=0.2, field=('TURBULENCE', 0.6), loop=True),
    'smoke': dict(domain=3.0, flow='SMOKE', end=96, first=24, density=1.0, temperature=0.6, vorticity=0.15, smoke_density=8.0, field=('TURBULENCE', 1.5), loop=True),
    'steam': dict(domain=2.0, flow='SMOKE', end=96, first=24, density=0.7, temperature=1.5, vorticity=0.3, smoke_density=4.0, dissolve=True, radius=0.08, z=0.08, field=('TURBULENCE', 1.2), loop=True, tint='#f2f4f7'),
    'poison': dict(domain=2.5, flow='SMOKE', end=120, first=36, density=0.9, temperature=0.25, vorticity=0.2, smoke_density=6.0, radius=0.2, z=0.06, field=('TURBULENCE', 1.0), loop=True, tint='#6fcf3c'),
    'magic': dict(domain=2.0, flow='BOTH', end=120, first=36, fuel=0.6, density=0.3, temperature=0.8, vorticity=0.5, smoke_density=1.5, dissolve=True, radius=0.1, z=0.2, field=('VORTEX', 3.0), loop=True, tint='#8a5cff'),
    'explosion': dict(domain=4.0, flow='BOTH', end=72, first=9, burst=10, fuel=3.0, density=1.4, temperature=3.0, vorticity=0.45, smoke_density=6.0, velocity=4.0, radius=0.18, z=0.4, field=('TURBULENCE', 6.0), flame_smoke=1.0, burning=0.5),
    'dust': dict(domain=3.0, flow='SMOKE', end=60, first=3, burst=6, density=1.6, temperature=0.2, vorticity=0.3, smoke_density=7.0, velocity=2.5, radius=0.14, z=0.08, field=('TURBULENCE', 3.0), tint='#a38b6c'),
}.items()}


def args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True); parser.add_argument('--phase', choices=('bake', 'render'), required=True)
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:])


def bake(req, out):
    if req['preset'] in PARTICLES: return build_particles(req['preset'], req, out)
    preset = PRESETS[req['preset']]; size = preset['domain']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene; scene.frame_start = 1; scene.frame_end = preset['end']; scene.render.fps = 24
    bpy.ops.mesh.primitive_cube_add(size=size, location=(0, 0, size / 2)); domain = bpy.context.object; domain.name = 'FX_Domain'
    settings = domain.modifiers.new('Fluid', 'FLUID'); settings.fluid_type = 'DOMAIN'; d = settings.domain_settings
    d.domain_type = 'GAS'; d.resolution_max = int(req['resolution']); d.use_adaptive_domain = False
    d.cache_directory = str(out / 'cache'); d.cache_type = 'ALL'; d.cache_frame_start = 1; d.cache_frame_end = preset['end']
    d.vorticity = preset['vorticity']; d.use_dissolve_smoke = preset['dissolve']; d.dissolve_speed = 40
    d.flame_vorticity = preset['vorticity']; d.burning_rate = preset['burning']; d.flame_smoke = preset['flame_smoke']
    radius = size * preset['radius']
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=radius, location=(0, 0, size * preset['z']))
    emitter = bpy.context.object; emitter.name = 'FX_Emitter'
    flow = emitter.modifiers.new('Fluid', 'FLUID'); flow.fluid_type = 'FLOW'; f = flow.flow_settings
    f.flow_type = preset['flow']; f.flow_behavior = 'INFLOW'; f.flow_source = 'MESH'; f.surface_distance = radius * 0.5
    f.fuel_amount = preset['fuel']; f.density = preset['density']; f.temperature = preset['temperature']
    f.use_initial_velocity = preset['velocity'] > 0; f.velocity_normal = preset['velocity']
    # Seeded field breaks up even ball/column shapes (vortex swirls magic); the seed also jitters the emitter.
    rng = np.random.default_rng(int(req['seed'])); emitter.location.x += float(rng.uniform(-0.02, 0.02)) * size; emitter.rotation_euler = tuple(rng.uniform(0, math.tau, 3))
    kind, strength = preset['field']
    bpy.ops.object.effector_add(type=kind, location=(0, 0, size / 2)); field = bpy.context.object.field
    field.strength = strength
    if kind == 'TURBULENCE': field.size = size * 0.15; field.seed = int(req['seed']) % 128
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
    gas = preset['flow'] == 'SMOKE'; colour = req.get('color') or preset['tint']  # manual tint, else the preset's own (poison green, magic violet)
    smoke = (0.55, 0.55, 0.55, 1) if gas else (0.08, 0.08, 0.08, 1)
    if colour and gas: smoke = (*[int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)], 1)
    volume.inputs['Color'].default_value = smoke
    if not gas:
        flame = nodes.new('ShaderNodeAttribute'); flame.attribute_name = 'flame'
        boost = nodes.new('ShaderNodeMath'); boost.operation = 'MULTIPLY'; boost.inputs[1].default_value = 3.0
        links.new(flame.outputs['Fac'], boost.inputs[0]); links.new(boost.outputs[0], volume.inputs['Blackbody Intensity'])
        volume.inputs['Temperature'].default_value = 1500.0
        if colour:  # tinted (magic) flame: emission colour instead of blackbody
            links.new(boost.outputs[0], volume.inputs['Emission Strength']); volume.inputs['Blackbody Intensity'].default_value = 0
            for link in list(links):
                if link.to_socket == volume.inputs['Blackbody Intensity']: links.remove(link)
            volume.inputs['Emission Color'].default_value = (*[int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)], 1)
    links.new(volume.outputs['Volume'], output.inputs['Volume'])
    domain.data.materials.clear(); domain.data.materials.append(mat)


FLAME_RAMP = np.array([(0.45, 0.14, 0.08), (0.92, 0.32, 0.10), (1.0, 0.62, 0.16), (1.0, 0.92, 0.48)], np.float32)  # ember, red, orange, yellow core


def stylize(cell, flame=False, accent=None):
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
    if accent:  # project palette: smoke and the ember band lean 25% toward the accent; the hot core stays fire-coloured
        tone = np.array([int(accent[i:i + 2], 16) / 255 for i in (1, 3, 5)], np.float32)
        cool = ~((cell[..., 0] - cell[..., 2] > 0.15)[..., None]) | (rgb.sum(axis=-1, keepdims=True) < 1.0)
        rgb = np.where(cool, rgb * 0.75 + tone * 0.25 * np.maximum(rgb.max(axis=-1, keepdims=True), 0.35), rgb)
    stepped = np.where(alpha < 0.12, 0.0, np.where(alpha < 0.45, 0.6, 1.0)).astype(np.float32)
    padded = np.pad(stepped, 1, mode='edge')  # one-pixel soften so the hard steps do not alias
    soft = sum(padded[1 + dy:1 + dy + stepped.shape[0], 1 + dx:1 + dx + stepped.shape[1]] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
    return np.dstack([rgb, soft]).astype(np.float32)


def render(req, out):
    particles = req['preset'] in PARTICLES
    preset = dict(PARTICLES[req['preset']], flow='PARTICLES', tint=None) if particles else PRESETS[req['preset']]
    bpy.ops.wm.open_mainfile(filepath=str(out / 'fx_scene.blend'))
    scene = bpy.context.scene
    if not particles: bpy.data.objects['FX_Emitter'].hide_render = True
    if not particles: material(bpy.data.objects['FX_Domain'], req)
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
    count = int(req['frames']); extra = max(2, count // 4) if preset['loop'] else 0
    picks = np.linspace(preset['first'], preset['end'], count + extra).round().astype(int)
    if particles:  # particle systems are evaluated frame by frame from the start; walk them once to fill the cache
        for f in range(scene.frame_start, int(picks[-1]) + 1): scene.frame_set(f)
    frames_dir = out / 'frames'; frames_dir.mkdir(exist_ok=True); started = time.monotonic(); frames = []
    for index, frame in enumerate(picks):
        scene.frame_set(int(frame)); r.filepath = str(frames_dir / f'frame_{index:03d}.exr')
        bpy.ops.render.render(write_still=True)
        frames.append(oiio.ImageBuf(r.filepath).get_pixels(oiio.FLOAT)[..., :4])  # premultiplied linear RGBA, top row first
        print(f'STAGE Render flipbook frame {index + 1}/{count + extra}', flush=True)
    if extra:  # seamless loop: the first frames fade in from the frames after the end (premultiplied, so a straight mix)
        for i in range(extra): frames[i] = frames[i] * (i / extra) + frames[count + i] * (1 - i / extra)
        frames = frames[:count]
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
        cells.append(stylize(resized.clip(0, 1), flame=preset['flow'] != 'SMOKE' and not (req.get('color') or preset['tint']), accent=req.get('accent')) if req.get('look', 'stylized') == 'stylized' else resized.clip(0, 1))
    columns = int(math.ceil(math.sqrt(count))); rows = int(math.ceil(count / columns))
    sheet = np.zeros((rows * cell, columns * cell, 4), np.float32)
    for index, pixels in enumerate(cells):
        y, x = divmod(index, columns); sheet[y * cell:(y + 1) * cell, x * cell:(x + 1) * cell] = pixels
    oiio.ImageBuf(sheet).write(str(out / 'flipbook.png'), oiio.UINT8)
    coverage = [float((c[..., 3] > 0.02).mean()) for c in cells]
    changes = [float(np.abs(cells[i + 1] - cells[i]).mean()) for i in range(len(cells) - 1)]
    edge = max(float(np.concatenate([c[0, :, 3], c[-1, :, 3], c[:, 0, 3], c[:, -1, 3]]).mean()) for c in cells)
    checks = dict(alpha_present=sum(v > 0.002 for v in coverage) >= 0.6 * len(coverage), not_clipped=edge < 0.35,  # one-shot bursts may fade to nothing at the end
                  animates=bool(changes) and float(np.median(changes)) > 1e-4)
    return dict(render_seconds=round(time.monotonic() - started, 1), sheet=str(out / 'flipbook.png'), columns=columns, rows=rows, cell_px=cell, frames=count,
                crop_m=round(side / work * size * 1.02, 3), sim_frames_used=[int(v) for v in picks[:count]], playback_fps=round(count / (max(1, int(picks[count] if extra else picks[-1] + 1) - int(picks[0])) / 24), 2),
                alpha_coverage=[round(v, 4) for v in coverage], edge_alpha=round(edge, 4), checks=checks,
                blending='straight alpha (alpha includes flame brightness); also usable additive', loop='seamless loop' if extra else 'plays once')


def main():
    a = args(); req = json.loads(Path(a.request).read_text(encoding='utf-8')); out = Path(req['output']); out.mkdir(parents=True, exist_ok=True)
    report_path = out / 'flipbook.json'; report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else dict(preset=req['preset'], request=req)
    report.update(bake(req, out) if a.phase == 'bake' else render(req, out)); report['blender'] = bpy.app.version_string
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
