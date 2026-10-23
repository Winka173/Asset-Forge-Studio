"""Actual GLB normal/triangle data; negative fixtures are never successful AI outputs."""
import numpy as np
import trimesh
from apps.api.inspection import inspect_glb
from apps.api.surface_diagnostics import derived_vertex_normals,measure


def test_derived_normals_match_independent_small_mesh_reference_without_mutation():
    vertices=np.array([[0.,0,0],[2,0,0],[0,1,0],[0,0,3],[5,5,5]])
    faces=np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
    mesh=trimesh.Trimesh(vertices=vertices,faces=faces,process=False)
    # Independent upstream reference restricted to four faces. The production
    # path must not call this quadratic fallback for large neural output.
    expected=trimesh.geometry.weighted_vertex_normals(len(vertices),faces,mesh.face_normals,mesh.face_angles,use_loop=True)
    actual=derived_vertex_normals(mesh)
    assert np.allclose(actual,expected,atol=1e-12)
    assert np.array_equal(actual[-1],[0,0,0])
    result=measure(mesh)
    assert 'derived angle-weighted' in result['vertex_normals_source']
    assert 'vertex_normals' not in mesh._cache.cache
    assert np.array_equal(mesh.vertices,vertices) and np.array_equal(mesh.faces,faces)


def test_missing_normals_real_glb_is_inspected_without_normal_property(tmp_path,monkeypatch):
    mesh=trimesh.creation.icosphere(subdivisions=3)
    path=tmp_path/'real-geometry-no-normals.glb'
    path.write_bytes(trimesh.exchange.gltf.export_glb(trimesh.Scene(mesh),include_normals=False))
    from apps.api.inspection import glb_document
    assert 'NORMAL' not in glb_document(path)['meshes'][0]['primitives'][0]['attributes']
    def forbidden(*args,**kwargs):raise AssertionError('Inspection must not invoke the quadratic normal fallback')
    monkeypatch.setattr(trimesh.Trimesh,'vertex_normals',property(forbidden))
    result=inspect_glb(path)
    assert result['triangles']==len(mesh.faces)
    assert result['surface_diagnostics']['all_vertex_normals_finite']
    assert 'derived angle-weighted' in result['surface_diagnostics']['meshes'][0]['vertex_normals_source']


def test_degenerate_geometry_derived_normals_are_finite_at_multiple_scales():
    for scale in (.001,1,1000):
        mesh=trimesh.Trimesh(vertices=np.array([[0.,0,0],[1,0,0],[2,0,0],[0,1,0]])*scale,
                             faces=[[0,1,2],[0,1,3],[0,0,0]],process=False)
        result=measure(mesh)
        assert result['finite_vertex_normals'] and result['zero_area_triangles']==2
        assert result['faces_opposing_mean_vertex_normal']==0


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
