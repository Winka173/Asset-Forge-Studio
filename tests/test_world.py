import io
import hashlib
import json
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


def test_world_revisions_preserve_original_latest_worker_metadata_and_approval(client,monkeypatch):
    from apps.api import studio
    plan=template('runavelle','First layout','Original immutable notes').model_dump()
    first=client.post('/api/world/plans',json=dict(plan=plan,request_id='world-revision-original')).json()
    asset_id=first['asset_id'];source=store.safe_path(first['artifact']['relative_path']);original_bytes=source.read_bytes()
    approval=dict(reviewer='Technical layout reviewer',notes='Not artistic approval')
    path='/api/world/plans/'+first['artifact']['id']+'/approve'
    assert client.post(path,json=approval).status_code==200
    assert client.post(path,json=approval).status_code==200
    original_asset=studio.asset
    def concurrently_completed(identifier):
        stale=original_asset(identifier)
        if identifier==asset_id:
            latest=original_asset(identifier);latest['master_artifact_id']='preserved-existing-master';latest['worker_checkpoint']={'phase':'finished','hash':'recorded'}
            latest['settings']['worker_metadata']='keep me';studio.save_asset(latest)
        return stale
    # A worker finishes after the endpoint's initial read but before its write transaction.
    with monkeypatch.context() as patch:
        patch.setattr(studio,'asset',concurrently_completed)
        response=client.post('/api/world/plans',json=dict(plan=plan|dict(name='Revised layout',prompt='Revision delta notes',seed=43),asset_id=asset_id,request_id='world-revision-second'))
    assert response.status_code==201,response.text
    second=response.json();value=original_asset(asset_id)
    assert value['prompt']==value['original_prompt']==plan['prompt']
    assert value['original_prompt_sha256']==hashlib.sha256(plan['prompt'].encode()).hexdigest()
    assert value['master_artifact_id']=='preserved-existing-master'
    assert value['worker_checkpoint']==dict(phase='finished',hash='recorded') and value['settings']['worker_metadata']=='keep me'
    assert len(value['settings']['world_plan_approvals'])==1
    workspace=client.get('/api/world/assets/'+asset_id).json()
    assert [p['approval_current'] for p in workspace['plans']]==[True,False]
    assert workspace['plans'][1]['plan']['prompt']=='Revision delta notes'
    assert source.read_bytes()==original_bytes and not list(source.parent.glob('*.tmp'))
    assert client.get('/api/library',params={'project_id':'runavelle'}).json()['items'][0]['version_count']==2
    assert jobs.listing()==[]


def test_legacy_world_original_prompt_recovers_from_first_immutable_source(client):
    from apps.api import studio
    plan=template('runavelle','Legacy layout','First historical notes').model_dump()
    first=client.post('/api/world/plans',json=dict(plan=plan,request_id='legacy-world-original')).json()
    value=studio.asset(first['asset_id']);value.pop('original_prompt');value.pop('original_prompt_sha256');value['prompt']='Old implementation overwrote this';studio.save_asset(value)
    response=client.post('/api/world/plans',json=dict(plan=plan|dict(prompt='New revision'),asset_id=value['id'],request_id='legacy-world-revision'))
    assert response.status_code==201,response.text
    stored=studio.asset(value['id']);assert stored['original_prompt']==plan['prompt']
    assert stored['original_prompt_sha256']==hashlib.sha256(plan['prompt'].encode()).hexdigest()
    assert len(client.get('/api/world/assets/'+value['id']).json()['plans'])==2


def test_one_click_map_records_an_automatic_technical_approval_and_queues_the_build(client,monkeypatch):
    from apps.api import studio,world
    monkeypatch.setattr(world,'generate',lambda identifier,body:dict(status='QUEUED',plan=identifier,request=body.request_id))
    body=dict(project_id='runavelle',name='Two lanes',prompt='Two-lane tower-defense map',width_m=128,depth_m=128,seed=7,request_id='world-auto-qa-1')
    result=client.post('/api/world/auto',json=body).json()
    asset=studio.asset(result['asset_id']);approvals=asset['settings']['world_plan_approvals']
    assert result['build']['plan']==result['plan_id'] and result['approval']=='automatic technical'
    assert [a['kind'] for a in approvals]==['automatic'] and 'Not an artistic approval' in approvals[0]['notes']
    # Retrying the same click reuses the saved plan and does not stack approvals.
    again=client.post('/api/world/auto',json=body).json()
    assert again['plan_id']==result['plan_id'] and len(studio.asset(result['asset_id'])['settings']['world_plan_approvals'])==1
