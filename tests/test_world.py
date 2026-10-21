import io
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pydantic import ValidationError
from apps.api import store,jobs
from apps.api.main import app
from apps.api.world_plan import WorldPlan,template,terrain


@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path)
    qa_project()
    return TestClient(app)


def test_real_quantized_terrain_determinism_and_layout_rejection():
    plan=template('runavelle','Two lanes','Recorded context')
    raw,roads,zones,qa=terrain(plan)
    second=terrain(WorldPlan.model_validate_json(plan.model_dump_json()))
    assert raw.dtype==np.dtype('<u2') and np.array_equal(raw,second[0])
    assert np.array_equal(roads,second[1]) and qa['road_connectivity']
    assert all(qa['spawn_to_goal'].values()) and not np.any(roads&zones)
    stream=io.BytesIO();Image.fromarray(raw).save(stream,format='PNG');stream.seek(0)
    assert np.array_equal(np.asarray(Image.open(stream)),raw)
    assert not np.array_equal(raw,terrain(plan.model_copy(update={'seed':43}))[0])
    invalid=plan.model_dump();invalid['build_zones'][1]=invalid['build_zones'][0]|{'id':'overlap'}
    with pytest.raises(ValidationError,match='overlap'):WorldPlan.model_validate(invalid)
    invalid=plan.model_dump();invalid['goal']['x']=float('nan')
    with pytest.raises(ValidationError):WorldPlan.model_validate(invalid)
    invalid=plan.model_dump();invalid['roads']=invalid['roads'][:1]
    with pytest.raises(ValueError,match='spawn'):terrain(WorldPlan.model_validate(invalid))


def test_world_api_immutable_approval_and_idempotency(client):
    preview=client.post('/api/world/preview-plan',json=dict(project_id='runavelle',name='QA map',prompt='Two explicit lanes'))
    assert preview.status_code==200 and preview.json()['enqueued_jobs']==0
    body=dict(plan=preview.json()['plan'],request_id='world-plan-qa-1')
    saved=client.post('/api/world/plans',json=body)
    assert saved.status_code==201,saved.text
    result=saved.json();identifier=result['artifact']['id'];asset_id=result['asset_id']
    assert client.post('/api/world/plans',json=body).json()==result
    conflict=body|dict(plan=body['plan']|dict(seed=43))
    assert client.post('/api/world/plans',json=conflict).status_code==409
    request=dict(request_id='world-generate-qa-1',render_gpu=False)
    assert client.post(f'/api/world/plans/{identifier}/generate',json=request).status_code==409
    assert jobs.listing()==[]
    assert client.post('/api/studio/concept',json=dict(asset_id=asset_id,request_id='blocked-world-concept',prompt='Map context')).status_code in [409,422]
    assert client.post(f'/api/world/plans/{identifier}/approve',json=dict(reviewer='QA only',notes='Layout approval; no artistic claim')).status_code==200
    assert client.post(f'/api/world/plans/{identifier}/generate',json=request|dict(commercial=True)).status_code==409
    # Tampering fails checksum before any job can be admitted.
    store.safe_path(result['artifact']['relative_path']).write_text('{}')
    assert client.post(f'/api/world/plans/{identifier}/generate',json=request).status_code==409
    assert jobs.listing()==[]
    assert jobs.resource_class(dict(kind='world_unity',use_gpu=True))=='gpu'
    assert jobs.resource_class(dict(kind='world_unity',use_gpu=False))=='cpu'
