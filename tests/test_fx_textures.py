import numpy as np
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import store
from engines.vfx_textures import generate, seam_error, KINDS

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)

def test_every_kind_tiles_seamlessly_and_is_deterministic():
    for kind in KINDS:
        a=generate(kind,256,3);assert a.shape==(256,256) and a.dtype==np.uint8 and seam_error(a)<1.3 and a.std()>5
        assert (a==generate(kind,256,3)).all() and not (a==generate(kind,256,4)).all()

def test_texture_is_saved_once_per_settings(client):
    body=dict(project_id='runavelle',kind='flame_mask',size=512,seed=9)
    first=client.post('/api/fx/textures',json=body);assert first.status_code==201,first.text
    assert client.post('/api/fx/textures',json=body).json()['id']==first.json()['id']
    assert [t['metadata']['kind'] for t in client.get('/api/fx/textures',params=dict(project_id='runavelle')).json()]==['flame_mask']
