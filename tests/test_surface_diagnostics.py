"""Actual GLB normal/triangle data; negative fixtures are never successful AI outputs."""
import numpy as np
import trimesh
from apps.api.inspection import inspect_glb


def test_glb_measures_opposed_normals_and_collapsed_triangles(tmp_path):
    vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[1,0,1],[0,0.00001,1],[0,0,2],[1,0,2],[2,0,2]],dtype=float)
    mesh=trimesh.Trimesh(vertices=vertices,faces=[[0,1,2],[3,4,5],[6,7,8]],vertex_normals=np.tile([0,0,-1.],(9,1)),process=False)
    path=tmp_path/'negative-geometry.glb';path.write_bytes(mesh.export(file_type='glb'))
    report=inspect_glb(path)['surface_diagnostics']
    assert report['totals']==dict(triangles=3,zero_area_triangles=1,very_thin_triangles=2)
    assert report['faces_opposing_mean_vertex_normal']==2
    assert report['all_vertex_normals_finite']
    assert report['meshes'][0]['vertex_normals_source']=='loaded GLB normals'
    assert report['status']=='MEASURED_OBSERVATIONS_NOT_ART_APPROVAL'


def test_shape_quality_is_scale_invariant_and_instances_not_double_counted(tmp_path):
    values=[]
    for scale in [.001,1000]:
        mesh=trimesh.creation.box();mesh.apply_scale(scale);scene=trimesh.Scene()
        scene.add_geometry(mesh,geom_name='shared',node_name='first')
        transform=np.eye(4);transform[0,3]=3*scale
        scene.graph.update(frame_to='second',matrix=transform,geometry='shared')
        path=tmp_path/f'box-{scale}.glb';path.write_bytes(scene.export(file_type='glb'))
        result=inspect_glb(path);d=result['surface_diagnostics']
        assert d['geometry_count']==1 and d['totals']['triangles']==12
        assert result['mesh_instances']==2 and result['triangles']==24
        assert d['faces_opposing_mean_vertex_normal']==0
        values.append(d['meshes'][0]['triangle_quality_p01'])
    assert abs(values[0]-values[1])<1e-6
