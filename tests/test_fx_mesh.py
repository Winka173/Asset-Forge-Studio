import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import store,jobs

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    from apps.api import local_tools
    monkeypatch.setattr(local_tools,'executable',lambda kind:'blender.exe');return TestClient(app)

def test_mesh_effect_is_an_idempotent_cpu_job(client):
    body=dict(project_id='runavelle',kind='shockwave',color='#66ccff',request_id='fxmesh-unit-1')
    first=client.post('/api/fx/mesh',json=body);assert first.status_code==201,first.text
    assert client.post('/api/fx/mesh',json=body).json()==first.json() and len(jobs.listing())==1
    assert jobs.resource_class(first.json()['job']['payload'])=='cpu'
    assert client.post('/api/fx/mesh',json=dict(body,kind='laser',request_id='fxmesh-unit-2')).status_code==422
