"""Particle effects for flipbooks (Blender particle system, no simulation cache): sparks, embers, debris, coins, level-up rays.

Imported by fx_flipbook.py: build(name, req, out) creates the scene and saves fx_scene.blend; the flipbook render step
then renders it like the gas presets (Cycles CPU, transparent film, crop, Stylized look, optional seamless loop).
"""
import math
import bpy
import numpy as np

# domain: framing size in metres; end/first: frames; loop: continuous emission rendered as a seamless loop.
PARTICLES = {
    'sparks': dict(domain=2.0, end=30, first=2, loop=False, count=140, start=1, stop=3, life=18, normal=2.0, random=1.0, gravity=1.0, shape='streak', colour=(1.0, 0.72, 0.25), emit=12.0, z=0.5),
    'embers': dict(domain=2.0, end=150, first=50, loop=True, count=260, start=1, stop=150, life=70, normal=0.6, random=0.4, gravity=-0.25, shape='dot', colour=(1.0, 0.45, 0.1), emit=8.0, z=0.1),
    'debris': dict(domain=3.0, end=30, first=2, loop=False, count=60, start=1, stop=2, life=40, normal=1.8, random=0.8, gravity=0.6, shape='chunk', colour=(0.42, 0.38, 0.33), emit=0.0, z=0.3),
    'coins': dict(domain=2.0, end=30, first=2, loop=False, count=30, start=1, stop=3, life=36, normal=1.6, random=0.5, gravity=0.7, up=0.8, shape='coin', colour=(1.0, 0.78, 0.22), emit=1.5, z=0.25),
    'levelup': dict(domain=2.0, end=48, first=4, loop=False, count=70, start=1, stop=24, life=26, normal=0.0, random=0.05, gravity=-0.3, up=1.4, shape='ray', colour=(1.0, 0.88, 0.45), emit=10.0, z=0.02, ring=True),
}


def _material(name, colour, emit):
    mat = bpy.data.materials.new(name); mat.use_nodes = True; bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*colour, 1); bsdf.inputs['Roughness'].default_value = 0.4
    if emit: bsdf.inputs['Emission Color'].default_value = (*colour, 1); bsdf.inputs['Emission Strength'].default_value = emit
    if name.endswith('coin'): bsdf.inputs['Metallic'].default_value = 1.0
    return mat


def _instance(shape, size, mat):
    if shape == 'streak': bpy.ops.mesh.primitive_cube_add(size=1); obj = bpy.context.object; obj.scale = (size * 2.2, size * 0.25, size * 0.25)  # long along X: 'VEL' rotation points X along the motion
    elif shape == 'chunk': bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=size); obj = bpy.context.object
    elif shape == 'coin': bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=size, depth=size * 0.25); obj = bpy.context.object; obj.rotation_euler = (math.pi / 2, 0, 0)
    elif shape == 'ray': bpy.ops.mesh.primitive_cube_add(size=1); obj = bpy.context.object; obj.scale = (size * 0.15, size * 0.15, size * 6)  # rays stay vertical (no particle rotation)
    else: bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=size); obj = bpy.context.object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.data.materials.append(mat); obj.location = (0, 0, -100); obj.hide_render = False
    return obj


def build(name, req, out):
    p = PARTICLES[name]; size = p['domain']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene; scene.frame_start = 1; scene.frame_end = p['end']; scene.render.fps = 24
    rng = np.random.default_rng(int(req['seed']))
    colour = tuple(int(req['color'][i:i + 2], 16) / 255 for i in (1, 3, 5)) if req.get('color') else p['colour']
    if p.get('ring'): bpy.ops.mesh.primitive_circle_add(vertices=48, radius=size * 0.32, fill_type='NGON', location=(0, 0, size * p['z']))
    else: bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=size * 0.06, location=(0, 0, size * p['z']))
    emitter = bpy.context.object; emitter.name = 'FX_Emitter'; emitter.show_instancer_for_render = False  # hiding the emitter would hide its particles too
    emitter.modifiers.new('Particles', 'PARTICLE_SYSTEM'); system = emitter.particle_systems[0]; s = system.settings
    system.seed = int(req['seed']) % 100000
    s.count = p['count']; s.frame_start = p['start']; s.frame_end = p['stop']; s.lifetime = p['life']; s.lifetime_random = 0.4
    s.normal_factor = p['normal']; s.factor_random = p['random']; s.effector_weights.gravity = p['gravity']
    s.object_align_factor = (0, 0, p.get('up', 0.0))  # initial upward speed (rays rise straight, coins pop up)
    s.use_rotations = True; s.rotation_factor_random = 1.0; s.angular_velocity_mode = 'RAND'; s.angular_velocity_factor = 6.0
    s.render_type = 'OBJECT'; s.particle_size = 1.0; s.size_random = 0.5
    s.instance_object = _instance(p['shape'], size * 0.03, _material('FX_' + p['shape'], colour, p['emit']))
    if p['shape'] == 'ray': s.use_rotations = False
    if p['shape'] == 'streak': s.use_rotations = True; s.rotation_mode = 'VEL'; s.rotation_factor_random = 0.0; s.phase_factor_random = 0.0; s.angular_velocity_mode = 'NONE'
    if name == 'embers':
        bpy.ops.object.effector_add(type='TURBULENCE', location=(0, 0, size / 2)); field = bpy.context.object.field
        field.strength = 1.5; field.size = size * 0.2; field.seed = int(rng.integers(0, 128))
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'fx_scene.blend'))
    return dict(bake_seconds=0.0, sim_frames=p['end'], domain_m=size, kind='particles')
