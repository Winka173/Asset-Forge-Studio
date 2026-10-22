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
