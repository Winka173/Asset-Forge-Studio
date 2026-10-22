"""Real licensed skinned GLBs; no synthetic success or auto-rig quality claim."""
import json
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs,automation
from apps.api.main import app
from engines.animation_clip import clips,read,retime,time_values,write


def fixture():
    source=store.ROOT/'.local/fixtures/RiggedFigure.glb'
    if not source.is_file():pytest.skip('Actual licensed rigged figure fixture unavailable')
    return source


def test_real_clip_retime_preserves_binary_skin_and_unselected_animations(tmp_path):
    source=fixture();document,binary=read(source)
    document['animations'].append(json.loads(json.dumps(document['animations'][0])))
    original=tmp_path/'two-clips.glb';write(original,document,binary)
    output=tmp_path/'retimed.glb';result=retime(original,output,0,.75)
    assert result['geometry_skin_materials_unchanged'] and result['original_binary_prefix_preserved']
    after,data=read(output)
    assert data[:len(binary)]==binary
    assert after['animations'][1]==document['animations'][1]
    assert clips(output)['clips'][0]['duration_seconds']==pytest.approx(1.25/.75)
    assert clips(output)['clips'][1]['duration_seconds']==pytest.approx(1.25)
    for before,sampler in zip(document['animations'][0]['samplers'],after['animations'][0]['samplers']):
        np.testing.assert_allclose(time_values(after,data,sampler['input']),time_values(document,binary,before['input'])/.75)
    for speed in (0,5,float('nan')):
        with pytest.raises(ValueError):retime(original,output,0,speed)


def test_real_animation_revision_shared_cpu_queue_deformation_QA_staged_export_rollback(tmp_path,monkeypatch,qa_project):
    from apps.api.local_tools import executable
    if not executable('blender'):pytest.skip('Actual Blender unavailable')
    source=fixture();monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Real rigged character motion QA',prompt='Original immutable character description')).json()
    imported=client.post('/api/import/candidate',params=dict(project_id='runavelle',asset_id=model['id']),files={'file':(source.name,source.read_bytes(),'model/gltf-binary')}).json()
    original_hash=store.digest(source);prefix='/api/production/assets/'+model['id']
    info=client.get(prefix+'/animation-clips',params={'artifact_id':imported['id']}).json()
    assert info['bones']==19 and info['clips'][0]['duration_seconds']==1.25
    # Establish an actual prior delivery so the edited version must be staged.
    exported=client.post('/api/export-profiles/assets/'+model['id'],json={'artifact_id':imported['id']})
    assert exported.status_code==200,exported.text
    before=exported.json();game_files={p:p.read_bytes() for p in Path(before['export_directory']).rglob('*') if p.is_file()}
    body=dict(parent_artifact_id=imported['id'],prompt='Set clip 1 speed to 0.75x',method='modify_existing',request_id='actual-animation-retime-test')
    plan=client.post(prefix+'/revisions/plan',json=body);assert plan.status_code==200,plan.text
    assert plan.json()['method']=='animation_retime' and not jobs.listing()
    created=client.post(prefix+'/revisions',json=body);assert created.status_code==201,created.text
    assert client.post(prefix+'/revisions',json=body).json()==created.json()
    job=jobs.listing()[0];assert len(jobs.listing())==1 and jobs.resource_class(job['payload'])=='cpu' and job['payload']['kind']=='animation_retime'
    worker=jobs.Worker()
    with jobs.resource_slot('cpu'):worker.execute(job)
    result=jobs.get(job['id']);assert result['status']=='REVIEW_REQUIRED',result.get('error')
    automation.advance(created.json()['group_id'])
    detail=client.get(prefix).json();revision=detail['asset']['revisions'][-1]
    assert revision['state']=='staged' and revision['qa_status']=='passed'
    assert detail['asset']['art_review_status']=='not_reviewed'
    assert detail['asset']['original_prompt']==model['prompt']
    record=next(a for a in detail['artifacts'] if a['id']==revision['artifact_id'])
    assert record['metadata']['animation_qa']['status']=='PASS_DEFORMATION_RETIME'
    assert record['metadata']['animation_qa']['max_pose_error']<record['metadata']['animation_qa']['tolerance']
    assert clips(store.safe_path(record['metadata'].get('relative_path') or store.get_artifact(record['id'])['relative_path']))['clips'][0]['duration_seconds']==pytest.approx(1.25/.75)
    assert store.digest(source)==original_hash
    assert all(p.read_bytes()==data for p,data in game_files.items())
    assert any(e.get('delivery_scope')=='staged' for e in detail['exports'])
    assert client.post(prefix+'/versions/'+record['id']+'/publish').status_code==200
    assert client.post(prefix+'/versions/'+imported['id']+'/publish').status_code==200
    assert client.get(prefix).json()['asset']['published_artifact_id']==imported['id']


def test_status_poll_does_not_undo_concurrent_real_publication(tmp_path,monkeypatch,qa_project):
    from apps.api import statuses,revisions,studio
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Concurrent publication QA',prompt='Preserve original')).json()
    source=fixture()
    imported=client.post('/api/import/candidate',params=dict(project_id='runavelle',asset_id=model['id']),files={'file':(source.name,source.read_bytes(),'model/gltf-binary')}).json()
    listing=jobs.listing;published=[]
    def publish_after_status_snapshot():
        if not published:
            published.append(revisions.publish(model['id'],imported['id']))
        return listing()
    monkeypatch.setattr(jobs,'listing',publish_after_status_snapshot)
    result=statuses.refresh_all()
    assert published[0]['status']=='COMPLETED'
    assert result[model['id']]['published_artifact_id']==imported['id']
    assert studio.asset(model['id'])['published_artifact_id']==imported['id']
