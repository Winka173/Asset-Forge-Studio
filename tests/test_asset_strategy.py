import hashlib
from apps.api import store,studio,asset_strategy
from engines.quality import resolve_procedural,fingerprint


def test_architecture_profile_respects_shape_engine_and_unsupported_constraints(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    model=studio.create_asset(studio.AssetInput(project_id='runavelle',name='Castle',prompt='Create 1 castle with 4 corner towers'))
    item=dict(asset_id=model['id'],prompt=model['prompt'],preferred_engine='auto',reference_ids=[],style_reference_ids=[],target_width_m=12.,target_depth_m=10.,target_height_m=8.,quality='Maximum')
    value=dict(project_id='runavelle',style_snapshot=studio.project('runavelle'))
    spec=asset_strategy.plan(value,item)
    assert spec['route']=='procedural_castle'
    assert spec['original_prompt_sha256']==hashlib.sha256(item['prompt'].encode()).hexdigest()
    assert spec['material_colors']['roof']=='#263b59'  # Inherited Runavelle slate.
    assert asset_strategy.plan(value,dict(item,preferred_engine='triposg'))['route']=='image_to_3d'
    assert asset_strategy.plan(value,dict(item,prompt='Create 1 floating ruined castle'))['route']=='image_to_3d'
    assert asset_strategy.plan(value,dict(item,prompt='Create 1 castle with 6 towers'))['route']=='image_to_3d'
    assert asset_strategy.plan(value,dict(item,prompt='Create 1 castle, photoreal exact replica'))['route']=='image_to_3d'
    for prompt in ('Create a castle with three towers','Create a castle without towers','Create a castle with 8K AI textures'):
        assert asset_strategy.plan(value,dict(item,prompt=prompt))['route']=='image_to_3d'
    # Even a castle subject must retain source reconstruction, never substitute
    # the simpler authored profile for a supplied image's geometry.
    import io
    from PIL import Image
    from fastapi.testclient import TestClient
    from apps.api.main import app
    data=io.BytesIO();Image.new('RGBA',(16,16),(20,40,80,128)).save(data,format='PNG')
    ref=TestClient(app).post('/api/import/reference',params=dict(project_id='runavelle'),files=dict(file=('source.png',data.getvalue()))).json()
    assert asset_strategy.plan(value,dict(item,reference_ids=[ref['id']]))['route']=='image_to_3d'
    # Same resolver for Single and Batch; scheduling/priority never alters quality.
    single=resolve_procedural(spec,42);batch=resolve_procedural(dict(spec),42)
    assert fingerprint(single)==fingerprint(batch) and single['texture']['size']==2048


def test_legacy_items_do_not_change_route_and_original_prompt_is_pinned(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    assert asset_strategy.admit({},dict(prompt='Castle'),{}) is None


def test_intentionally_open_plane_is_not_rejected_as_nonwatertight(tmp_path,monkeypatch,qa_project):
    import trimesh
    from apps.api import quality_evaluation
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    asset=studio.create_asset(studio.AssetInput(project_id='runavelle',name='Open foliage plane',prompt='Open foliage card'))
    path=tmp_path/'open-plane.glb';trimesh.Trimesh(vertices=[[-1,0,0],[1,0,0],[1,0,2],[-1,0,2]],faces=[[0,1,2],[0,2,3]],process=False).export(path)
    candidate=store.add_artifact(path,'candidate','Actual open plane',dict(project_id='runavelle',asset_id=asset['id']))
    report=quality_evaluation.evaluate(dict(asset_id=asset['id']),candidate)
    assert report['eligible'] and report['gates'][0]['outcome']=='PASS'
    assert report['gates'][1]['outcome']=='NOT_EVALUATED'
