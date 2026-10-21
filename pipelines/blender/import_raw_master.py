"""Preserve native neural geometry as an editable Blender master, without inventing UV/PBR."""
import argparse
import json
import sys
from pathlib import Path
import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_asset import sha, write

p = argparse.ArgumentParser(); p.add_argument('--source', required=True); p.add_argument('--output', required=True)
args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
source, output = Path(args.source).resolve(), Path(args.output).resolve()
if output.exists(): raise ValueError('Require a new immutable master version folder')
output.mkdir(parents=True)
with np.load(source, allow_pickle=False) as data:
    vertices = np.asarray(data['vertices'], dtype=np.float32)
    faces = np.asarray(data['faces'], dtype=np.int32)
if not np.isfinite(vertices).all() or faces.min() < 0 or faces.max() >= len(vertices): raise ValueError('Invalid native geometry')
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new('NativeNeuralGeometry')
mesh.vertices.add(len(vertices)); mesh.vertices.foreach_set('co', vertices.ravel())
mesh.loops.add(3*len(faces)); mesh.loops.foreach_set('vertex_index', faces.ravel())
mesh.polygons.add(len(faces)); mesh.polygons.foreach_set('loop_start', np.arange(len(faces),dtype=np.int32)*3)
mesh.polygons.foreach_set('loop_total', np.full(len(faces),3,dtype=np.int32))
mesh.update(calc_edges=True)
obj = bpy.data.objects.new('ArcherTower_native_geometry',mesh); bpy.context.scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active=obj; obj.select_set(True)
target = output/'native_geometry.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(target),compress=True)
bpy.ops.wm.open_mainfile(filepath=str(target))
reopened = bpy.data.objects['ArcherTower_native_geometry']
if len(reopened.data.polygons)!=len(faces): raise ValueError('Native master triangle count changed on reopen')
write(output/'report.json', {'status':'NEEDS_REVIEW','source_sha256':sha(source),'blend_sha256':sha(target),
    'triangles':len(faces),'vertices':len(vertices),'reopen':'PASS','coordinate_system':'native TRELLIS Z-up, canonical uncalibrated units',
    'uv':'NOT_AVAILABLE_IN_NATIVE_GEOMETRY','pbr':'Sparse PBR field retained in source NPZ; this .blend is geometry only',
    'commercial_use':'EVALUATION_ONLY_PENDING_AUDIT','human_approval':'NOT_TESTED'})
print('NATIVE_GEOMETRY_MASTER_REOPEN_PASS',len(faces),flush=True)
