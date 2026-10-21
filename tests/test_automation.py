import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs,batch,automation
from apps.api.main import app


@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)


def test_actual349_dry_plan_and_bounded_automatic_queue(client):
    source=Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md'
    if not source.is_file():pytest.skip('Actual Runavelle source unavailable')
    response=client.post('/api/batches/import',files=dict(file=(source.name,source.read_bytes())),data=dict(project_id='runavelle',mode='Maximum Quality Batch'))
    assert response.status_code==201,response.text[:500]
    value=response.json();prefix='/api/batches/'+value['id']
    assert len(value['items'])==349 and sum(i['selected'] for i in value['items'])==349
    dry=client.post(prefix+'/run-all',json=dict(dry_run=True)).json()
    assert dry['plan']['total']==349 and dry['plan']['future']==37 and jobs.listing()==[]
    assert all(i['spec_provenance'] for i in dry['items'])
    assert dry['items'][0]['spec_provenance']['target_width_m']['kind']=='explicit'
    assert dry['items'][-1]['spec_provenance']['target_width_m']['kind']=='defaulted'
    response=client.post(prefix+'/run-all',json={});assert response.status_code==200,response.text[:500]
    assert 0<len(jobs.listing())<=2
    persisted=batch.batch(value['id']);assert sum(i['started'] for i in persisted['items'])==349
    assert all(not i['confirmed'] for i in persisted['items'])
    before={j['id'] for j in jobs.listing()};client.post(prefix+'/control',json=dict(action='pause'));automation.advance(value['id']);assert before=={j['id'] for j in jobs.listing()}
    assert batch.batch(value['id'])['paused']
    client.post(prefix+'/control',json=dict(action='resume'));assert before=={j['id'] for j in jobs.listing()}
    automation.startup_recovery();assert batch.batch(value['id'])['paused']


def test_recovery_opt_in_and_explicit_pause_remain_durable(client):
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Tower')).json();identifier=value['id']
    settings=automation.Workflow(auto_resume=True).model_dump()
    automation.start(identifier,workflow=settings)
    automation.startup_recovery();assert not batch.batch(identifier)['paused']
    client.post('/api/batches/'+identifier+'/control',json=dict(action='pause'))
    automation.startup_recovery();assert batch.batch(identifier)['paused']
    assert not app.openapi()['paths']['/api/automation/single']['post'].get('deprecated',False)


def test_single_auto_idempotency_and_source_seeds(client):
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Tower',prompt='A tall stone archer tower')).json()
    body=dict(asset_id=model['id'],request_id='single-auto-durable-test',quality='Maximum',engine='trellis2_community',seeds=[91,92])
    first=client.post('/api/automation/single',json=body);assert first.status_code==201,first.text[:500]
    second=client.post('/api/automation/single',json=body);assert second.status_code==201,second.text[:500]
    assert first.json()['batch_id']==second.json()['batch_id']
    row=batch.batch(first.json()['batch_id'])['items'][0]
    assert row['seeds']==[91,92] and row['quality_lock'] and row['candidates']==2
    assert not row['automation']['human_approved']
    assert len(jobs.listing())==1
    bad=dict(body,seeds=[1]);assert client.post('/api/automation/single',json=bad).status_code==409


def test_explicit_engine_policy_not_silently_changed(client):
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt=json.dumps([dict(name='Shape only',prompt='Tower',preferred_engine='triposg')]),format='json')).json()
    result=automation.start(value['id'])
    assert result['items'][0]['automation']['engines']==[]
    assert result['items'][0]['automation']['status']=='blocked' and jobs.listing()==[]


def test_project_edit_preserves_workflow_and_delivery_preferences(client):
    assert client.post('/api/automation/projects/runavelle',json=automation.Workflow(auto_resume=True).model_dump()).status_code==200
    assert client.post('/api/export-profiles/projects/runavelle',json=dict(manifest=False)).status_code==200
    response=client.post('/api/projects/runavelle',json=dict(name='Renamed Runavelle',description='Preserve saved presets'))
    assert response.status_code==200,response.text
    assert automation.project_workflow('runavelle')['auto_resume']
    from apps.api.export_profiles import resolve_project_settings
    assert not resolve_project_settings('runavelle')['manifest']


def test_batch_style_snapshot_survives_project_edit(client):
    client.post('/api/projects/runavelle',json=dict(name='Runavelle',default_style='Original navy and ivory'))
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Tower')).json()
    client.post('/api/projects/runavelle',json=dict(name='Runavelle',default_style='Future project style'))
    automation.start(value['id'])
    concept=jobs.listing()[0]
    assert concept['payload']['project_style_snapshot']['default_style']=='Original navy and ivory'
    assert 'Future project style' not in concept['payload']['prompt']
