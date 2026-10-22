"""Scene authority: all imported sources are pinned; primitives are explicit studio floor."""
import json
import math
import sys
import hashlib
from pathlib import Path
import bpy
from mathutils import Vector,Euler,Matrix

request=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'));spec=request['scene'];cache=Path(request['cache']);output=Path(request['output'])
(output/'scene.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=spec['samples'];scene.cycles.use_denoising=True
scene.render.resolution_x=spec['width'];scene.render.resolution_y=spec['height'];scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.render.fps=spec['fps']
scene.world=bpy.data.worlds.new('Cinematic World');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.035,.045,.065,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.35
conversion=Matrix.Rotation(math.pi/2,4,'X');groups={}
for obj in spec['objects']:
    before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=request['sources'][obj['artifact_id']]);imported=[o for o in bpy.data.objects if o not in before]
    root=bpy.data.objects.new(obj['name'],None);scene.collection.objects.link(root)
    for child in imported:
        if child.parent not in imported:child.parent=root
    transform=Matrix.LocRotScale(Vector(obj['position']),Euler([math.radians(v) for v in obj['rotation']],'XYZ').to_quaternion(),Vector(obj['scale']))
    root.matrix_basis=conversion@transform@conversion.inverted();root.hide_render=not obj['visible'];groups[obj['id']]=root
    if not obj['visible']:
        for child in imported:child.hide_render=True
for obj in spec['objects']:
    if obj['parent_id']:groups[obj['id']].parent=groups[obj['parent_id']]
if spec['ground']:
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.01));floor=bpy.context.object;floor.name='Explicit Studio Floor (not an environment map)'
    material=bpy.data.materials.new('Studio Floor');material.diffuse_color=(.065,.075,.09,1);floor.data.materials.append(material)
def area(name,position,power,color,size):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.color=color;data.shape='DISK';data.size=size
    obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=position;obj.rotation_euler=(-obj.location).to_track_quat('-Z','Y').to_euler()
area('Key',(5,-6,10),1800,(.75,.85,1) if spec['lighting']=='moonlight' else (1,.88,.73),8)
area('Rim',(-6,5,8),2200,(.35,.5,1),7);area('Fill',(-5,-5,5),1000,(.7,.8,1),8)
data=bpy.data.cameras.new('Cinematic camera');camera=bpy.data.objects.new('Cinematic camera',data);scene.collection.objects.link(camera);scene.camera=camera;data.lens=40;data.clip_start=.05;data.clip_end=2000
bpy.ops.wm.save_as_mainfile(filepath=str(output/'source.blend'))
total=sum(round(s['duration']*spec['fps']) for s in spec['shots']);done=0;rendered=0;reused=0;placements=[]
for shot in spec['shots']:
    count=round(shot['duration']*spec['fps']);directory=cache/shot['id'];directory.mkdir(exist_ok=True)
    for frame in range(count):
        target=directory/f'{frame:06d}.png';valid=False
        receipt=target.with_suffix('.sha256')
        if target.is_file() and receipt.is_file():
            try:
                valid=hashlib.sha256(target.read_bytes()).hexdigest()==receipt.read_text()
                image=bpy.data.images.load(str(target),check_existing=False);valid=valid and tuple(image.size)==(spec['width'],spec['height']);bpy.data.images.remove(image)
            except Exception:valid=False
        if valid:reused+=1;done+=1;continue
        scene.frame_set(frame)
        subject=groups.get(shot['target_id']);bpy.context.view_layer.update()
        points=[child.matrix_world@Vector(corner) for root in ([subject] if subject else groups.values()) for child in root.children_recursive if child.type=='MESH' for corner in child.bound_box]
        if subject and subject.type=='MESH':points.extend(subject.matrix_world@Vector(c) for c in subject.bound_box)
        center=sum(points,Vector())/len(points) if points else Vector((0,0,1))
        ratio=frame/max(1,count-1);azimuth=math.radians(shot['azimuth']+(shot['amount']*ratio if shot['movement']=='orbit' else 0));elevation=math.radians(shot['elevation']);distance=shot['distance']*(1-.35*ratio if shot['movement']=='dolly' else 1)
        direction=Vector((math.sin(azimuth)*math.cos(elevation),-math.cos(azimuth)*math.cos(elevation),math.sin(elevation)))
        camera.location=center+direction*distance;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
        temporary=directory/f'{frame:06d}.part.png';scene.render.filepath=str(temporary);bpy.ops.render.render(write_still=True);temporary.replace(target)
        receipt.write_text(hashlib.sha256(target.read_bytes()).hexdigest())
        placements.append(dict(shot=shot['id'],frame=frame,camera=list(camera.location),target=list(center)))
        rendered+=1;done+=1;print(f'AFS_FRAME {done}/{total}',flush=True)
report=dict(status='PASS_FRAME_RENDER',rendered_frames=rendered,reused_frames=reused,total_frames=total,source_objects=len(spec['objects']),camera_samples=placements,config_hash=request['config_hash'],scope='Explicit scene/shot parameters; no semantic prompt interpretation or artistic QA',animation='Existing imported clips evaluate; no generated motion or retargeting',audio='silent')
(output/'render_report.json').write_text(json.dumps(report,indent=2))
