"""Checkpoint integrity/admission tests; synthetic arrays are not AI output."""
import io
import json
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from apps.api import store,studio,jobs,native_checkpoint
from apps.api.main import app
from engines import mesh_checkpoint
from engines.quality import fingerprint


@pytest.fixture
def checkpoint(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    asset=studio.create_asset(studio.AssetInput(project_id='runavelle',name='Negative checkpoint fixture',prompt='Tower'))
    stream=io.BytesIO();Image.new('RGB',(16,16),'navy').save(stream,'PNG')
    source=client.post('/api/import/reference',params=dict(project_id='runavelle',asset_id=asset['id']),files=dict(file=('source.png',stream.getvalue()))).json()
    config=dict(geometry=dict(export_triangle_target=1000000))
    payload=dict(kind='inference',engine='trellis2_community',project_id='runavelle',asset_id=asset['id'],artifact_id=source['id'],seed=43,steps=32,pipeline_type='1024_cascade',texture_size=4096,effective_config=config,effective_config_hash=fingerprint(config))
    job=jobs.enqueue(payload);folder=tmp_path/'jobs'/job['id']/'output';folder.mkdir(parents=True)
    arrays=dict(vertices=np.array([[0,0,0],[1,0,0],[0,1,0]],dtype=np.float32),faces=np.array([[0,1,2]],dtype=np.int32),attrs=np.ones((1,6),dtype=np.float16),coords=np.array([[0,0,0]],dtype=np.int32))
    request=payload|dict(export_triangle_target=1000000)
    layout=dict(base_color=slice(0,3),metallic=slice(3,4),roughness=slice(4,5),alpha=slice(5,6))
    metadata=mesh_checkpoint.save(folder,arrays,request,source['sha256'],'pinned-revision',layout,1/1024)
    receipt=folder/'mesh_checkpoint.json';binding=dict(sha256=store.digest(receipt),native_sha256=metadata['native_sha256'])
    (folder/'generation.json').write_text(json.dumps(dict(model_revision='pinned-revision',native_checkpoint=binding)),'utf-8')
    jobs.transition(job['id'],'RUNNING');jobs.transition(job['id'],'BLOCKED','Server stopped during finishing')
    return client,jobs.get(job['id']),folder,arrays,request,source


def test_checkpoint_resume_is_idempotent_scoped_and_never_infers_success(checkpoint):
    client,job,folder,arrays,request,source=checkpoint
    response=client.get(f'/api/production/jobs/{job["id"]}/native-checkpoint').json();assert response['available']
    assert response['geometry']['triangles']==1 and not list(folder.glob('*.glb'))
    endpoint=f'/api/production/jobs/{job["id"]}/resume-finishing'
    a=client.post(endpoint,json=dict(request_id='same-native-resume'));b=client.post(endpoint,json=dict(request_id='same-native-resume'))
    assert a.status_code==b.status_code==201 and a.json()['id']==b.json()['id']
    assert client.post(endpoint,json=dict(request_id='different-but-active')).json()['id']==a.json()['id']
    with store.connect() as db:
        assert db.execute('SELECT response FROM studio_requests WHERE id=?',('finish:'+job['id']+':different-but-active',)).fetchone()
    result=a.json();assert result['status']=='QUEUED' and jobs.resource_class(result['payload'])=='gpu'
    assert result['payload']['effective_config_hash']==job['payload']['effective_config_hash']
    assert result['payload']['resume_mesh_checkpoint']==job['id']
    assert native_checkpoint.checkpoint_for(jobs.get(result['id']))['metadata']['native_sha256']==store.digest(folder/'raw_master.npz')
    assert len(jobs.listing())==2
    # One stable asset row; an interrupted ancestor is history, not the current
    # pipeline. It must not hide the future completed model after recovery.
    overview=client.get('/api/production').json()
    assert len(overview['standalone'])==1 and overview['standalone'][0]['id']==job['id']
    assert [stage['id'] for stage in overview['standalone'][0]['jobs']]==[result['id']]


def test_corruption_or_changed_scope_never_resumes(checkpoint):
    client,job,folder,arrays,request,source=checkpoint
    changed=job|dict(payload=job['payload']|dict(asset_id='another-asset',resume_mesh_checkpoint=job['id']))
    with pytest.raises(ValueError,match='scope/config'):native_checkpoint.checkpoint_for(changed)
    (folder/'raw_master.npz').write_bytes(b'not a native mesh')
    result=client.get(f'/api/production/jobs/{job["id"]}/native-checkpoint').json();assert not result['available']
    assert client.post(f'/api/production/jobs/{job["id"]}/resume-finishing',json=dict(request_id='invalid-checkpoint')).status_code==409
    assert len(jobs.listing())==1


def test_automatic_retry_uses_the_verified_boundary_and_preserves_quality(checkpoint):
    from apps.api import quality_repair,automation
    _,job,folder,_,_,_=checkpoint
    value=dict(id='negative-admission-fixture',automation=dict(settings=automation.Workflow().model_dump()))
    item=dict(asset_id=job['payload']['asset_id'],attempt=0,automation={})
    plan=quality_repair.planner.stage(value,item,job,jobs.listing())
    assert plan['action']=='retry_stage' and plan['resume_mesh_checkpoint']==job['id']
    child=quality_repair.submit_stage_retry(plan,job)
    assert child['payload']['steps']==32 and child['payload']['texture_size']==4096
    assert child['payload']['resume_checkpoint_sha256']==store.digest(folder/'mesh_checkpoint.json')
    assert quality_repair.submit_stage_retry(plan,job)['id']==child['id']
    assert not list(folder.glob('*.glb'))  # Admission is not generated output.


def test_geometry_is_validated_before_any_finishing(checkpoint):
    _,_,folder,arrays,request,source=checkpoint
    for invalid in [arrays|dict(vertices=np.array([[float('nan'),0,0]])),arrays|dict(faces=np.array([[0,1,999]])),arrays|dict(attrs=np.ones((1,5))),arrays|dict(coords=np.array([[9999,0,0]]))]:
        with pytest.raises(ValueError):mesh_checkpoint.inspect_arrays(invalid,1024)
    with pytest.raises(ValueError,match='source/config/model'):
        mesh_checkpoint.verify(folder/'mesh_checkpoint.json',request|dict(steps=24),source['sha256'],'pinned-revision')


def test_current_concept_policy_cannot_bypass_locked_conditioning(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    config=dict(composition_policy=3,input_prompt='One complete tower',negative_prompt='collage',inference_steps=50,resolution=1024,seed=43)
    job=jobs.enqueue(dict(kind='concept',prompt='Changed castle',negative_prompt='collage',steps=50,size=1024,seed=43,effective_config=config,effective_config_hash=fingerprint(config)))
    jobs.worker.execute(job)
    assert jobs.get(job['id'])['status']=='BLOCKED'
    assert 'locked conditioning' in jobs.get(job['id'])['error']
    assert not (tmp_path/'jobs'/job['id']/'output').exists()
