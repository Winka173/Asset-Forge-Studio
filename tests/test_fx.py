import json
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import store,studio,jobs

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)

def test_plan_explicit_values_provenance_and_no_gpu_admission(client):
    r=client.post('/api/fx/plan',json=dict(project_id='runavelle',prompt='Ice sword slash, 3 seconds',overrides=dict(intensity=2.1))).json()
    assert r['recipe']['element']=='ice' and r['recipe']['duration']==3 and r['recipe']['intensity']==2.1
    assert r['provenance']['element']['kind']=='explicit' and r['provenance']['segments']['kind']=='defaulted' and jobs.listing()==[]
    assert client.post('/api/fx/plan',json=dict(project_id='runavelle',prompt='fire and ice')).status_code==422
    assert client.post('/api/fx/plan',json=dict(project_id='runavelle',overrides=dict(project_id='other'))).status_code==422

def test_recipe_versions_idempotent_same_global_gpu_queue_and_cross_project_guards(client):
    body=dict(recipe=dict(project_id='runavelle',name='Fire slash',element='fire'),request_id='fx-unit-idempotent')
    response=client.post('/api/fx/build',json=body);assert response.status_code==201,response.text
    first=response.json();assert client.post('/api/fx/build',json=body).json()==first
    assert len(jobs.listing())==1 and jobs.resource_class(first['job']['payload'])=='gpu'
    assert first['job']['payload']['effective_config']['quality']=='Maximum'
    assert not first['job']['payload']['effective_config']['ai_inference']
    recipe=store.get_artifact(first['recipe_id']);original=store.safe_path(recipe['relative_path']).read_bytes()
    second=client.post('/api/fx/build',json=dict(body,asset_id=first['asset_id'],request_id='fx-unit-next-version',recipe=body['recipe']|dict(element='ice'))).json()
    assert second['asset_id']==first['asset_id'] and second['recipe_id']!=first['recipe_id'] and len(jobs.listing())==2
    assert store.safe_path(recipe['relative_path']).read_bytes()==original
    other=client.post('/api/projects',json=dict(name='Other game')).json()
    assert client.post('/api/fx/build',json=dict(body,asset_id=first['asset_id'],request_id='fx-cross-project',recipe=body['recipe']|dict(project_id=other['id']))).status_code==409
    assert len(client.get('/api/fx/assets/'+first['asset_id']).json()['recipes'])==2
    assert studio.asset(first['asset_id'])['asset_type']=='vfx'

def test_missing_native_engine_and_invalid_recipes_do_not_fake_outputs(client,monkeypatch):
    from engines import unity_editor
    monkeypatch.setattr(unity_editor,'probe',lambda:dict(installed=False))
    response=client.post('/api/fx/build',json=dict(recipe=dict(project_id='runavelle',name='Missing engine'),request_id='fx-unit-missing-engine'))
    assert response.status_code==409 and jobs.listing()==[]
    with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]==0
    assert client.post('/api/fx/build',json=dict(recipe=dict(project_id='runavelle',name='Invalid',duration=0),request_id='fx-unit-invalid')).status_code==422


def test_revision_plan_inherits_recipe_and_preserves_explicit_overrides(client):
    created=client.post('/api/fx/build',json=dict(recipe=dict(project_id='runavelle',name='Ice slash',element='ice',duration=4,radius=3.2,segments=96),request_id='inheritance-test-recipe')).json()
    base=dict(project_id='runavelle',base_recipe_id=created['recipe_id'])
    inherited=client.post('/api/fx/plan',json=base|dict(prompt='Make the arc brighter')).json()
    assert inherited['recipe']['element']=='ice' and inherited['recipe']['radius']==3.2
    assert inherited['recipe']['duration']==4 and inherited['recipe']['segments']==96
    assert inherited['provenance']['radius']['kind']=='inherited'
    explicit=client.post('/api/fx/plan',json=base|dict(prompt='Fire slash, 3 seconds',overrides=dict(intensity=3))).json()
    assert explicit['recipe']['element']=='fire' and explicit['recipe']['duration']==3 and explicit['recipe']['intensity']==3
    assert explicit['recipe']['radius']==3.2 and explicit['recipe']['segments']==96
    assert len(jobs.listing())==1

def test_multiple_fx_results_share_asset_queue_and_retry_without_duplicates(client):
    body=dict(recipe=dict(project_id='runavelle',name='Five alternatives',element='ice',seed=2147483646),request_id='fx-multi-result-request',count=5)
    response=client.post('/api/fx/build-candidates',json=body);assert response.status_code==201,response.text
    result=response.json();assert result['count']==5 and result['gpu_concurrency']==1 and result['quality']=='Maximum'
    assert len({r['asset_id'] for r in result['results']})==1 and len(jobs.listing())==5
    workspace=client.get('/api/fx/assets/'+result['asset_id']).json()
    assert [r['recipe']['seed'] for r in workspace['recipes']]==[2147483646,2147483647,0,1,2]
    assert all(jobs.resource_class(j['payload'])=='gpu' and j['payload']['effective_config']['quality']=='Maximum' for j in jobs.listing())
    assert all(r['artifact']['metadata']['candidate_group']==result['candidate_group'] for r in workspace['recipes'])
    assert client.post('/api/fx/build-candidates',json=body).json()==result and len(jobs.listing())==5
    assert client.post('/api/fx/build-candidates',json=body|dict(count=4)).status_code==409
    assert client.post('/api/fx/build-candidates',json=body|dict(count=6)).status_code==422
    assert client.post('/api/fx/build-candidates',json=body|dict(count=0)).status_code==422
    assert studio.asset(result['asset_id'])['original_prompt']==''


def test_partial_fx_admission_retries_only_missing_children(client,monkeypatch):
    from apps.api import fx
    from fastapi import HTTPException
    real=fx.build;calls=[]
    def interrupted(body):
        calls.append(body.request_id)
        if len(calls)==2:raise HTTPException(503,'Test interrupted admission; no generated output simulated')
        return real(body)
    monkeypatch.setattr(fx,'build',interrupted)
    body=dict(recipe=dict(project_id='runavelle',name='Crash safe alternatives'),request_id='fx-partial-admission',count=3)
    assert client.post('/api/fx/build-candidates',json=body).status_code==503
    assert len(jobs.listing())==1
    monkeypatch.setattr(fx,'build',real)
    result=client.post('/api/fx/build-candidates',json=body);assert result.status_code==201,result.text
    assert len(jobs.listing())==3 and len({j['payload']['asset_id'] for j in jobs.listing()})==1
    assert len(client.get('/api/fx/assets/'+result.json()['asset_id']).json()['recipes'])==3


def test_alternative_status_includes_running_sibling_at_pause_boundary(client):
    from apps.api import statuses
    result=client.post('/api/fx/build-candidates',json=dict(recipe=dict(project_id='runavelle',name='Group status'),request_id='fx-group-status-123',count=2)).json()
    first=result['results'][0]['job']['id'];jobs.transition(first,'RUNNING')
    assert statuses.refresh_all()[result['asset_id']]['production_status']=='generating'
    client.post('/api/production/control',json=dict(scope='all',action='pause'))
    assert statuses.refresh_all()[result['asset_id']]['production_status']=='generating'
    jobs.transition(first,'FAILED','Test failure projection only; no successful output simulated')
    current=statuses.refresh_all()[result['asset_id']]
    assert current['production_status']=='failed' and current['attention_required']
