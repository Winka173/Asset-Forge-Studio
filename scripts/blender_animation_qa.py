"""Headless deformation comparison of an existing clip and its retimed version."""
import json
import sys
from pathlib import Path
import bpy
import numpy as np


def sample(path,start,end):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE'];meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if not rigs or not meshes:raise ValueError('Expected an actually skinned mesh and armature')
    if not any(o.animation_data and (o.animation_data.action or o.animation_data.nla_tracks) for o in rigs):raise ValueError('No actual armature animation was imported')
    fps=bpy.context.scene.render.fps/bpy.context.scene.render.fps_base;frames=[]
    for ratio in (0,.2,.4,.6,.8,1):
        bpy.context.scene.frame_set(0,subframe=0);seconds=start+(end-start)*ratio;frame=seconds*fps
        bpy.context.scene.frame_set(int(frame),subframe=frame-int(frame));graph=bpy.context.evaluated_depsgraph_get();vertices=[]
        for obj in meshes:
            evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh()
            try:
                # Bounded deterministic vertex samples keep dense meshes within RAM.
                stride=max(1,len(mesh.vertices)//20000)
                for index in range(0,len(mesh.vertices),stride):vertices.append(tuple(evaluated.matrix_world@mesh.vertices[index].co))
            finally:evaluated.to_mesh_clear()
        values=np.asarray(vertices,dtype=np.float64)
        if not np.isfinite(values).all():raise ValueError('Deformation produced non-finite vertices')
        frames.append(values)
    return frames,dict(armatures=len(rigs),bones=sum(len(r.data.bones) for r in rigs),sampled_vertices=len(frames[0]),mesh_vertices=sum(len(o.data.vertices) for o in meshes),skins_present=any(any(m.type=='ARMATURE' for m in obj.modifiers) for obj in meshes))


request=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
before,source=sample(request['source_clip'],request['before']['start_seconds'],request['before']['end_seconds'])
after,output=sample(request['output_clip'],request['after']['start_seconds'],request['after']['end_seconds'])
if source!=output:raise ValueError('Skeleton, vertex or skin counts changed')
errors=[float(np.max(np.linalg.norm(a-b,axis=1))) for a,b in zip(before,after)]
scale=max(1.,float(np.ptp(before[0],axis=0).max()));tolerance=scale*1e-4
if max(errors)>tolerance:raise ValueError(f'Retimed deformation differs: {max(errors)} > {tolerance}')
motion=max(float(np.max(np.linalg.norm(frame-before[0],axis=1))) for frame in before[1:])
if motion<1e-6:raise ValueError('No measurable motion in the source clip; do not claim animation was validated')
report=dict(status='PASS_DEFORMATION_RETIME',source=source,output=output,samples=6,max_pose_error=max(errors),tolerance=tolerance,source_motion_m=motion,
            loop_seam_vertex_distance=float(np.max(np.linalg.norm(after[0]-after[-1],axis=1))),vertex_sampling='Deterministic stride, at most approximately 20000 vertices per mesh at six temporal samples; not exhaustive deformation proof',root_motion_quality='not_evaluated',foot_contact_quality='not_evaluated',artistic_quality='not_reviewed')
Path(request['report']).write_text(json.dumps(report,indent=2),encoding='utf-8')
print('AFS_ANIMATION_QA_PASS',flush=True)
