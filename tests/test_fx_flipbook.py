import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import store,jobs,fx_flipbook

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    from apps.api import local_tools
    monkeypatch.setattr(local_tools,'executable',lambda kind:'blender.exe');return TestClient(app)

def test_simulation_is_decided_from_the_prompt_and_recorded():
    pick=lambda prompt:fx_flipbook.resolve(fx_flipbook.Flipbook(project_id='p',prompt=prompt,request_id='unit-resolve'))
    assert pick('Big explosion with debris')==('explosion',dict(kind='explicit',source='Named in the prompt'))
    assert pick('khói bốc lên từ ống khói')[0]=='smoke' and pick('ngọn lửa trại')[0]=='fire'
    preset,why=pick('smoke after the explosion');assert preset=='smoke' and why['kind']=='inferred'
    assert pick('magic aura')==('fire',dict(kind='defaulted',source='No fire, smoke or explosion named; fire is the default simulation'))

def test_flipbook_is_an_idempotent_cpu_job_with_recorded_quality(client):
    body=dict(project_id='runavelle',prompt='Campfire',request_id='fxflip-unit-1')
    first=client.post('/api/fx/flipbook',json=body);assert first.status_code==201,first.text
    first=first.json();assert client.post('/api/fx/flipbook',json=body).json()==first and len(jobs.listing())==1
    payload=first['job']['payload'];config=payload['effective_config']
    assert jobs.resource_class(payload)=='cpu' and config['look']=='stylized' and config['preset']=='fire' and config['resolution']==128 and config['frames']==36 and not config['artistic_approval']
    again=client.post('/api/fx/flipbook',json=dict(body,request_id='fxflip-unit-2',asset_id=first['asset_id'],preset='smoke',quality='Fast')).json()
    assert again['asset_id']==first['asset_id'] and again['job']['payload']['effective_config']['resolution']==64
    assert client.post('/api/fx/flipbook',json=dict(body,request_id='fxflip-unit-3',color='red')).status_code==422

def test_workspace_lists_only_flipbook_jobs(client):
    made=client.post('/api/fx/flipbook',json=dict(project_id='runavelle',prompt='Explosion',request_id='fxflip-unit-ws')).json()
    view=client.get(f"/api/fx/flipbook/assets/{made['asset_id']}").json()
    assert view['sheets']==[] and [j['id'] for j in view['jobs']]==[made['job']['id']] and view['jobs'][0]['payload']['effective_config']['preset']=='explosion'
