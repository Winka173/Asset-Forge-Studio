"""State, migration and revision invariants; real geometry fixtures, no claimed AI generation."""
import json
from pathlib import Path
import pytest
import trimesh
from fastapi.testclient import TestClient
from apps.api import store,studio,jobs,batch,automation,statuses,revisions,export_profiles
from apps.api.main import app

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)

def source(client):
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Tower',prompt='Stone tower height 9 m, blue roof.')).json()
    path=store.DATA/'box.glb';path.write_bytes(trimesh.creation.box(extents=[3,9,3]).export(file_type='glb'))
    record=store.add_artifact(path,'candidate','Unit geometry fixture.glb',dict(project_id='runavelle',asset_id=model['id'],stage='blender_processed'))
    return model,record,path

def test_legacy_migration_no_invented_approval_and_export_dimensions(client):
    model,record,path=source(client);model['status']='Under Review';studio.save_asset(model)
    first=statuses.refresh_all()[model['id']];assert first['art_review_status']=='not_reviewed' and first['production_status']=='needs_attention'
    assert (store.DATA/'backups/studio-before-production-status-v1.sqlite').is_file()
    with store.connect() as db:assert db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]==1
    exported=export_profiles.export_asset('runavelle',model['id'],record['id']);current=statuses.refresh_all()[model['id']]
    assert current['production_status']=='completed' and current['qa_status']=='passed' and current['export_status']=='exported' and current['art_review_status']=='not_reviewed' and not current['attention_required']
    assert current['status']=='Completed' and current['original_prompt']==model['prompt'] and current['legacy_status']=='Under Review'
    doc=json.loads((Path(exported['export_directory'])/'manifest.json').read_text());assert doc['qa_status']=='passed' and doc['art_review_status']=='not_reviewed'
    assert statuses.refresh_all()[model['id']]['production_status']=='completed'

def test_revision_cpu_queue_idempotency_constraints_and_capability_truth(client):
    model,record,path=source(client);before=path.read_bytes();export_profiles.export_asset('runavelle',model['id'],record['id'])
    body=dict(parent_artifact_id=record['id'],prompt='Uniformly scale to height 18 m',request_id='revision-unit-1234')
    r=client.post(f'/api/production/assets/{model["id"]}/revisions',json=body);assert r.status_code==201,r.text
    saved=r.json();assert client.post(f'/api/production/assets/{model["id"]}/revisions',json=body).json()==saved
    current=studio.asset(model['id']);assert current['prompt']==model['prompt'] and len(current['revisions'])==1 and current['revisions'][0]['quality']=='Maximum'
    rev=current['revisions'][0];assert rev['effective_specification']['dimensions']['target_height_m']==18 and rev['original_prompt_sha256']==current['original_prompt_sha256']
    assert len(jobs.listing())==1 and jobs.listing()[0]['payload']['kind']=='blender' and jobs.listing()[0]['payload']['target_height_m']==18
    assert path.read_bytes()==before
    unsupported=client.post(f'/api/production/assets/{model["id"]}/revisions/plan',json=body|dict(prompt='Turn the roof red',method='modify_existing'));assert unsupported.status_code==400
    plan=client.post(f'/api/production/assets/{model["id"]}/revisions/plan',json=body|dict(prompt='Turn the roof red'));assert plan.json()['method']=='regenerate'

def test_revision_stage_publish_rollback_preserves_game_files(client):
    model,v1,path=source(client);first=export_profiles.export_asset('runavelle',model['id'],v1['id']);model=studio.asset(model['id']);model['published_artifact_id']=v1['id']
    p2=store.DATA/'box-v2.glb';p2.write_bytes(trimesh.creation.box(extents=[6,18,6]).export(file_type='glb'));v2=store.add_artifact(p2,'candidate','Unit revision fixture.glb',dict(project_id='runavelle',asset_id=model['id'],stage='blender_processed'))
    model['revisions']=[dict(id='unit-revision',artifact_id=v2['id'],parent_artifact_id=v1['id'],previous_delivery_ids=[first['id']],state='staged',export_settings=export_profiles.resolve_project_settings('runavelle'))];studio.save_asset(model)
    assert not (store.DATA/'revision-previews').exists()
    settings=export_profiles.resolve_project_settings('runavelle');settings['output_directory']=export_profiles.revision_output_directory()
    staged=export_profiles.export_asset('runavelle',model['id'],v2['id'],settings=settings);assert staged['delivery_scope']=='staged' and Path(staged['export_directory']).is_relative_to(store.DATA/'revision-previews')
    game_index=Path(first['project_manifest']);assert json.loads(game_index.read_text())['assets'][model['id']]['export_version']==first['id']
    client.post(f'/api/production/assets/{model["id"]}/review-policy',json=dict(review_policy='manual_approval'))
    assert client.post(f'/api/production/assets/{model["id"]}/versions/{v2["id"]}/publish',json={}).status_code==409
    r=client.post('/api/production/artistic-review',json=dict(entries=[dict(asset_id=model['id'],artifact_id=v2['id'],decision='approved')],reviewer='Unit test reviewer'));assert r.status_code==200,r.text
    published=client.post(f'/api/production/assets/{model["id"]}/versions/{v2["id"]}/publish',json={});assert published.status_code==200,published.text
    assert json.loads(game_index.read_text())['assets'][model['id']]['export_version']==published.json()['id']
    client.post(f'/api/production/assets/{model["id"]}/review-policy',json=dict(review_policy='auto'))
    rollback=client.post(f'/api/production/assets/{model["id"]}/versions/{v1["id"]}/publish',json={});assert rollback.status_code==200,rollback.text
    assert json.loads(game_index.read_text())['assets'][model['id']]['export_version']==first['id'] and p2.exists() and path.exists()
    assert studio.asset(model['id'])['published_artifact_id']==v1['id'] and jobs.listing()==[]

def test_short_prompt_enrichment_preserves_explicit_values_and_original(client):
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Tiny prompt',prompt='Stone tower height 9 m')).json()
    result=client.post('/api/automation/single',json=dict(asset_id=model['id'],request_id='short-prompt-test123',quality='Maximum')).json()
    current=studio.asset(model['id']);spec=current['resolved_specification'];assert current['prompt']=='Stone tower height 9 m' and spec['dimensions']['target_height_m']==9 and spec['provenance']['target_height_m']['kind']=='explicit'
    assert spec['provenance']['target_width_m']['kind']=='defaulted' and current['original_prompt']==current['prompt']
    assert batch.batch(result['batch_id'])['items'][0]['confirmed'] is False
    automation.startup_recovery();assert batch.batch(result['batch_id'])['paused']

def test_library_real_import_hash_dedup_and_bounded_349_listing(client):
    actual=store.WORKSPACE/'.local/fixtures/ArcherTowerLOD2.glb'
    if not actual.exists():pytest.skip('Actual Archer Tower GLB fixture unavailable')
    first=client.post('/api/library/import',files={'file':('Archer.glb',actual.read_bytes(),'model/gltf-binary')},data={'project_id':'runavelle'})
    assert first.status_code==201,first.text
    second=client.post('/api/library/import',files={'file':('SameArcher.glb',actual.read_bytes(),'model/gltf-binary')},data={'project_id':'runavelle'})
    assert second.status_code==201 and second.json()['duplicate'] and first.json()['asset_id']==second.json()['asset_id']
    assert len(jobs.listing())==1 and jobs.listing()[0]['payload']['kind']=='blender'
    assert client.get('/api/library?project_id=runavelle').json()['items'][0]['production_status']!='completed'
    source=Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md'
    if source.exists():
        manifest=client.post('/api/batches/import',files={'file':(source.name,source.read_bytes())},data={'project_id':'runavelle'});assert len(manifest.json()['items'])==349
        page=client.get('/api/library?project_id=runavelle&offset=0&limit=50').json();assert page['total']==350 and len(page['items'])==50
        assert client.get('/api/library?project_id=runavelle&search=ARCHER_TOWER_T3').json()['total']==1
    count=len(jobs.listing());client.get('/api/library?project_id=runavelle');assert len(jobs.listing())==count
    invalid=client.post('/api/library/import',files={'file':('broken.glb',b'invalid')},data={'project_id':'runavelle'});assert invalid.status_code==400


def test_incomplete_batch_missing_input_does_not_block_other_asset(client):
    text=json.dumps([{'id':'EMPTY','name':'Empty entry','prompt':''},{'id':'SHORT','name':'Tower','prompt':'Stone tower height 9 m'}])
    r=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt=text,format='json'));assert r.status_code==201,r.text
    identifier=r.json()['id'];result=client.post(f'/api/batches/{identifier}/run-all',json={});assert result.status_code==200,result.text
    value=batch.batch(identifier);empty=next(i for i in value['items'] if i['source_asset_id']=='EMPTY');valid=next(i for i in value['items'] if i['source_asset_id']=='SHORT')
    assert empty['automation']['status']=='blocked' and empty['automation']['stage']=='Needs Input'
    assert any(j['payload']['asset_id']==valid['asset_id'] for j in jobs.listing())
    assert not any(j['payload']['asset_id']==empty['asset_id'] for j in jobs.listing())
    before={j['id'] for j in jobs.listing()};automation.startup_recovery();assert batch.batch(identifier)['paused'] and before=={j['id'] for j in jobs.listing()}


def test_grouped_missing_input_resolution_keeps_original_and_quality(client):
    text=json.dumps([{'id':'EMPTY','name':'Empty entry','prompt':''},{'id':'NAME','name':'Timber cottage','prompt':''}])
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt=text,format='json',mode='Maximum Quality Batch')).json()
    identifier=value['id'];client.post(f'/api/batches/{identifier}/run-all',json={})
    saved=batch.batch(identifier);empty=next(i for i in saved['items'] if i['source_asset_id']=='EMPTY');named=next(i for i in saved['items'] if i['source_asset_id']=='NAME')
    assert named['resolved_prompt']=='Timber cottage' and studio.asset(named['asset_id'])['original_prompt']==''
    assert named['quality']=='Maximum' and any(j['payload']['asset_id']==named['asset_id'] for j in jobs.listing())
    result=client.post('/api/production/resolve-input',json=dict(group_id=identifier,asset_ids=[empty['asset_id']],prompt='Stone tower height 9 m'))
    assert result.status_code==200,result.text
    assert result.json()['completed']==[empty['asset_id']]
    model=studio.asset(empty['asset_id']);assert model['original_prompt']=='' and model['prompt']=='Stone tower height 9 m'
    assert model['resolved_specification']['dimensions']['target_height_m']==9
    assert next(i for i in batch.batch(identifier)['items'] if i['asset_id']==empty['asset_id'])['quality']=='Maximum'

def test_library_metadata_changes_preserve_latest_master_and_review_state(client):
    from apps.api import library
    model,record,path=source(client)
    studio.save_asset(studio.asset(model['id']) | dict(master_artifact_id=record['id'],revisions=[dict(id='preserve-worker-version')],art_review_status='not_reviewed'))
    library.patch_metadata(model['id'],dict(tags=['review-later']))
    current=studio.asset(model['id'])
    assert current['master_artifact_id']==record['id'] and current['revisions']==[dict(id='preserve-worker-version')]
    assert current['tags']==['review-later'] and current['art_review_status']=='not_reviewed'
    unsorted=client.get('/api/library?project_id=runavelle&category=Unsorted').json()
    assert [a['id'] for a in unsorted['items']]==[model['id']]
    for action in ('archive','restore'):
        result=client.post('/api/library/bulk',json=dict(asset_ids=[model['id']],action=action)).json()
        assert not result['errors'] and result['completed'][0]['asset_id']==model['id']
    assert studio.asset(model['id'])['archived'] is False and path.exists() and not jobs.listing()
