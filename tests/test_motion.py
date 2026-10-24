import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import store,jobs,motion

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)

def test_missing_install_blocks_instead_of_faking(client,monkeypatch):
    monkeypatch.setattr(motion,'installed',lambda:False)
    response=client.post('/api/motion',json=dict(project_id='runavelle',prompt='a knight swings a sword',request_id='motion-unit-0'))
    assert response.status_code==409 and jobs.listing()==[] and client.get('/api/motion/capabilities').json()['installed'] is False

def test_motion_is_one_idempotent_gpu_job_at_upstream_quality(client,monkeypatch):
    monkeypatch.setattr(motion,'installed',lambda:True)
    body=dict(project_id='runavelle',prompt='a knight swings a sword',duration=3,request_id='motion-unit-1')
    first=client.post('/api/motion',json=body);assert first.status_code==201,first.text
    first=first.json();assert client.post('/api/motion',json=body).json()==first and len(jobs.listing())==1
    payload=first['job']['payload'];config=payload['effective_config']
    assert jobs.resource_class(payload)=='gpu' and config['steps']==100 and config['text_encoder_device']=='cpu' and not config['artistic_approval']
    view=client.get(f"/api/motion/assets/{first['asset_id']}").json()
    assert view['asset']['asset_type']=='animation' and [j['id'] for j in view['jobs']]==[first['job']['id']]
    assert client.post('/api/motion',json=dict(body,request_id='motion-unit-2',duration=30)).status_code==422

def test_character_must_be_a_rigged_model_of_this_game(client,monkeypatch,tmp_path):
    monkeypatch.setattr(motion,'installed',lambda:True)
    file=tmp_path/'rig.glb';file.write_bytes(b'glTF');other=tmp_path/'plain.glb';other.write_bytes(b'glTF2')
    rig=store.add_artifact(file,'rigged','Knight / rigged',dict(project_id='runavelle',asset_id='a1'))
    plain=store.add_artifact(other,'candidate','Knight',dict(project_id='runavelle',asset_id='a1'))
    assert [c['id'] for c in client.get('/api/motion/characters',params=dict(project_id='runavelle')).json()]==[rig['id']]
    body=dict(project_id='runavelle',prompt='a knight waves',request_id='motion-unit-rig')
    assert client.post('/api/motion',json=dict(body,character_artifact_id=plain['id'])).status_code==409
    made=client.post('/api/motion',json=dict(body,request_id='motion-unit-rig2',character_artifact_id=rig['id'])).json()
    assert made['job']['payload']['effective_config']['character_sha256']==rig['sha256']
