"""Validator fixtures are not generated/artist-approved game assets."""
import json
import trimesh
from apps.api import store,studio,quality_evaluation
from engines.quality import fingerprint


def test_empty_named_node_cannot_replace_required_geometry(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    model=studio.create_asset(studio.AssetInput(project_id='runavelle',name='Validator fixture',prompt='Castle'))
    names=['keep','gate_arch','corner_tower_nw','corner_tower_ne','corner_tower_sw','corner_tower_se','curtain_wall_north','curtain_wall_west','curtain_wall_east','curtain_wall_south_west','curtain_wall_south_east']
    scene=trimesh.Scene()
    for name in names:scene.add_geometry(trimesh.creation.box(),node_name=name,geom_name=name)
    source=tmp_path/'raw.glb';scene.export(source)
    spec=dict(route='procedural_castle',bounds_m=[1,1,1]);digest=fingerprint(spec)
    folder=tmp_path/'jobs/fixture/output';folder.mkdir(parents=True)
    assembly=folder/'assembly.json';assembly.write_text(json.dumps(dict(spec_sha256=digest,checks=dict(fixture=True),contacts=[],portal_clearance=[],blender_version='synthetic validator fixture')))
    (folder.parent/'manifest.json').write_text(json.dumps(dict(assembly_report_sha256=store.digest(assembly))))
    raw=store.add_artifact(source,'candidate','Validator fixture / raw',dict(project_id='runavelle',asset_id=model['id'],job_id='fixture',assembly_report=assembly.relative_to(tmp_path).as_posix()))
    # Keep the required name but remove the node's mesh: a valid container whose
    # identity labels alone must never satisfy a structural gate.
    scene.delete_geometry('corner_tower_nw');target=tmp_path/'ghost-tower.glb';scene.export(target)
    record=store.add_artifact(target,'candidate','Validator fixture / missing geometry',dict(project_id='runavelle',asset_id=model['id'],parent_id=raw['id']))
    report=quality_evaluation.evaluate(dict(asset_id=model['id'],asset_generation_spec=spec),record)
    assert report['gates'][0]['outcome']=='PASS'  # Actual finite, nonempty GLB.
    assert not report['eligible']
    assert 'corner_tower_nw' in report['gates'][1]['evidence']['missing']


def test_component_labels_cannot_hide_changed_geometry(tmp_path):
    source=trimesh.Scene();source.add_geometry(trimesh.creation.box(),node_name='keep',geom_name='keep')
    original=tmp_path/'original.glb';source.export(original)
    altered=trimesh.Scene();altered.add_geometry(trimesh.creation.box(extents=[.3,1,1]),node_name='keep',geom_name='keep')
    target=tmp_path/'altered.glb';altered.export(target)
    checks=quality_evaluation.compare_component_geometry(original,target,{'keep'},1.,1e-5)
    assert len(checks)==1 and not checks[0]['passed']
    assert checks[0]['triangle_count_unchanged']
    same=quality_evaluation.compare_component_geometry(original,original,{'keep'},1.,1e-5)
    assert same[0]['passed'] and same[0]['max_vertex_distance_m']==0


def test_explicit_roof_color_is_measured_from_embedded_material(tmp_path):
    from PIL import Image
    import numpy as np
    from trimesh.visual.material import PBRMaterial
    mesh=trimesh.creation.box()
    mesh.visual=trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),material=PBRMaterial(name='roof',baseColorTexture=Image.new('RGB',(8,8),(135,59,50))))
    scene=trimesh.Scene();scene.add_geometry(mesh,node_name='keep_roof',geom_name='keep_roof')
    target=tmp_path/'roof.glb';scene.export(target)
    assert quality_evaluation.roof_color_check(target,'#873b32')['passed']
    assert not quality_evaluation.roof_color_check(target,'#263b59')['passed']
