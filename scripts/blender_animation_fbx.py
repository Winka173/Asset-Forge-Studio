"""FBX bridge for the explicitly limited single-clip Unity validation profile."""
import json
import math
import sys
from pathlib import Path
import bpy
import numpy as np

request=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps=120
    if str(path).lower().endswith('.fbx'):bpy.ops.import_scene.fbx(filepath=str(path))
    else:bpy.ops.import_scene.gltf(filepath=str(path))

def samples():
    result=[]
    for ratio in (0,.2,.4,.6,.8,1):
        frame=request['duration']*ratio*120
        bpy.context.scene.frame_set(int(frame),subframe=frame-int(frame))
        graph=bpy.context.evaluated_depsgraph_get();values=[]
        for obj in sorted((o for o in bpy.context.scene.objects if o.type=='MESH'),key=lambda o:o.name):
            evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh()
            try:values.extend(tuple(evaluated.matrix_world@v.co) for v in mesh.vertices)
            finally:evaluated.to_mesh_clear()
        value=np.asarray(values,dtype=np.float64)
        if not np.isfinite(value).all():raise ValueError('Nonfinite deformation')
        result.append(value)
    return result

load(request['source']);before=samples()
scene=bpy.context.scene;scene.frame_start=0;scene.frame_end=round(request['duration']*120)
scene.frame_set(0)
bpy.ops.export_scene.fbx(filepath=request['fbx'],use_selection=False,object_types={'MESH','ARMATURE','EMPTY'},
    add_leaf_bones=False,use_armature_deform_only=False,bake_anim=True,bake_anim_use_nla_strips=False,
    bake_anim_use_all_actions=False,bake_anim_use_all_bones=True,bake_anim_simplify_factor=0,
    bake_anim_step=1,use_mesh_modifiers=False,axis_forward='-Z',axis_up='Y',path_mode='COPY',embed_textures=False)
load(request['fbx']);after=samples()
# FBX can reorder vertices. Compare each frame's geometry as a point cloud;
# Unity performs independent bone-weight, clip and measurable-motion checks.
from mathutils.kdtree import KDTree
errors=[]
for a,b in zip(before,after):
    if len(a)!=len(b):raise ValueError('FBX vertex count changed')
    tree=KDTree(len(b))
    for index,position in enumerate(b):tree.insert(position,index)
    tree.balance();errors.append(max(tree.find(position)[2] for position in a))
tolerance=max(1.,float(np.ptp(before[0],axis=0).max()))*.002
if max(errors)>tolerance:raise ValueError(f'FBX deformation comparison failed: {max(errors)} > {tolerance}')
Path(request['report']).write_text(json.dumps(dict(status='PASS_FBX_DEFORMATION',samples=6,max_point_cloud_error=max(errors),tolerance=tolerance,
    source_vertices=len(before[0]),source_dimensions=np.ptp(before[0],axis=0).tolist(),source_motion_m=max(float(np.linalg.norm(frame-before[0],axis=1).max()) for frame in before[1:]),
    scope='Six frame point-cloud comparison; vertex order is not assumed, not exhaustive animation proof'),indent=2))
