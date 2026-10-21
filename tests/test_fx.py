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
