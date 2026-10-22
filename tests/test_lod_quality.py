"""Real Blender geometry, not generated-asset or artistic success fixtures."""
import json
import subprocess
import pytest
from apps.api import store,jobs
from apps.api.local_tools import executable


def test_measured_surface_error_uses_shared_world_coordinates(tmp_path):
    blender=executable('blender')
    if not blender:pytest.skip('Real Blender is not installed')
    script=tmp_path/'measure.py';output=tmp_path/'measure.json'
    script.write_text('''import bpy,sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[-2])
from lod_quality import SurfaceReference
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,radius=1,location=(3,2,4))
high=bpy.context.object
reference=SurfaceReference([high],samples=4096)
identity=reference.compare([high])
bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=1,location=(3,2,4))
low=bpy.context.object
coarse=reference.compare([low]);repeated=reference.compare([low])
low.location.x+=2
bpy.context.view_layer.update()
shifted=reference.compare([low])
Path(sys.argv[-1]).write_text(json.dumps(dict(identity=identity,coarse=coarse,repeated=repeated,shifted=shifted)))
''','utf-8')
    with jobs.resource_slot('cpu'):
        result=subprocess.run([blender,'-b','-t','2','--factory-startup','--python-exit-code','1','--python',str(script),'--',str(store.ROOT/'pipelines/blender'),str(output)],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout[-1500:]+result.stderr[-1500:]
    data=json.loads(output.read_text())
    assert data['identity']['symmetric_sampled_max_relative_diagonal']<1e-5
    assert data['coarse']['symmetric_p95_relative_diagonal']>0.001
    assert data['coarse']==data['repeated']
    assert data['shifted']['symmetric_p95_relative_diagonal']>0.1
    assert data['coarse']['target_triangles']<data['coarse']['master_triangles']
