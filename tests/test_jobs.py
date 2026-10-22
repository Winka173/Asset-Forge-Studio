import json
import time

import pytest
import trimesh
from fastapi.testclient import TestClient

from apps.api import jobs, store
from apps.api.main import app


@pytest.fixture
def database(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    qa_project()
    # Blender QA uses CPU; isolate its lock so an active production GPU job cannot
    # make these state-machine assertions time out. Each app still shares its lock.
    monkeypatch.setattr(jobs, 'WORKER_LOCK', tmp_path / 'worker.lock')
    return tmp_path


def test_lock_prevents_concurrent_workers(database):
    with jobs.exclusive_worker_lock():
        with pytest.raises(OSError):
            with jobs.exclusive_worker_lock():
                pytest.fail('Second worker acquired a held lock')


@pytest.mark.parametrize('fbx',[False,True])
def test_blender_child_respects_optional_export_profile(database,fbx):
    parent=jobs.enqueue(dict(kind='inference',auto_blender=True,project_id='runavelle',asset_id='fixture',batch_id='export-fixture'))
    with store.connect() as db:db.execute('INSERT INTO batches (id,project_id,payload) VALUES (?,?,?)',('export-fixture','runavelle',json.dumps(dict(automation=dict(export_settings=dict(fbx=fbx))))))
    folder=database/'jobs'/parent['id'];folder.mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps(dict(candidate_artifact='fixture-only-no-model-claim')))
    parent['status']='REVIEW_REQUIRED'  # Admission fixture, no execution or success fabricated.
    child=jobs.ensure_blender(parent)
    assert child['payload']['export_fbx'] is fbx
    assert jobs.ensure_blender(parent) is None


def test_transitions_cancel_retry_and_recovery(database):
    first = jobs.enqueue({'kind': 'blender', 'artifact_id': 'missing'})
    with pytest.raises(ValueError): jobs.transition(first['id'], 'REVIEW_REQUIRED')
    jobs.transition(first['id'], 'CANCELLED')
    second = jobs.retry(first['id'])
    assert second['id'] != first['id'] and second['payload']['retry_of'] == first['id']
    assert jobs.get(first['id'])['status'] == 'CANCELLED'
    jobs.transition(second['id'], 'RUNNING')
    worker = jobs.Worker(); worker.start()
    try:
        deadline = time.monotonic() + 5
        while jobs.get(second['id'])['status'] != 'BLOCKED' and time.monotonic() < deadline: time.sleep(0.05)
        assert jobs.get(second['id'])['status'] == 'BLOCKED'
    finally: worker.close()


def test_real_blender_queue_and_output_download(database):
    # Actual Blender subprocess, not mocked success. No concept-to-3D claim.
    with TestClient(app) as client:
        mesh = trimesh.creation.box(extents=[2, 10, 3]).export(file_type='glb')
        source = client.post('/api/import/candidate', files={'file': ('qa_box.glb', mesh)}).json()
        queued = client.post('/api/jobs/blender', json={'artifact_id': source['id'], 'render': False}).json()
        assert queued['payload']['export_fbx'] is False
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            job = jobs.get(queued['id'])
            if job['status'] in jobs.TERMINAL: break
            time.sleep(0.1)
        assert job['status'] == 'REVIEW_REQUIRED', job
        files = client.get(f'/api/jobs/{job["id"]}/files').json()
        manifest_url = next(f['url'] for f in files if f['name'] == 'manifest.json')
        manifest = client.get(manifest_url).json()
        assert manifest['source_sha256'] == source['sha256']
        assert manifest['checks']['export_reopen'] == 'PASS'
        assert len(manifest['glb_inspections']) == 4
        assert not list((database/'jobs'/queued['id']/'output').glob('*.fbx'))
        assert (database/'jobs'/queued['id']/'output/master.blend').exists()
        assert client.post(f'/api/jobs/{job["id"]}/cancel').status_code == 409
        assert len(client.get('/api/status').json()['artifacts']) == 2


def test_enhance_pins_project_fbx_default_and_honors_explicit_overrides(database):
    from apps.api import export_profiles,studio
    client=TestClient(app);path=database/'actual-box.glb';path.write_bytes(trimesh.creation.box().export(file_type='glb'))
    record=store.add_artifact(path,'candidate','Actual geometry.glb',dict(project_id='runavelle'))
    def queued(**fields):
        response=client.post('/api/jobs/blender',json=dict(artifact_id=record['id'],render=False,**fields))
        assert response.status_code==201,response.text
        return response.json()
    glb_only=queued();assert glb_only['payload']['export_fbx'] is False
    project=studio.project('runavelle');project['export_settings']={'selective_export':dict(preset='custom',fbx=True)}
    with store.connect() as db:db.execute('UPDATE projects SET payload=? WHERE id=?',(json.dumps(project),'runavelle'))
    assert export_profiles.resolve_project_settings('runavelle')['fbx']
    assert queued()['payload']['export_fbx'] is True
    assert queued(export_fbx=False)['payload']['export_fbx'] is False
    assert queued(export_fbx=True)['payload']['export_fbx'] is True
    assert jobs.get(glb_only['id'])['payload']['export_fbx'] is False
    assert all(j['status']=='QUEUED' for j in jobs.listing())  # Admission test, not claimed generation.


@pytest.mark.parametrize('fbx',[False,True])
def test_standalone_automatic_child_keeps_admitted_fbx_choice(database,fbx):
    config=dict(quality='Maximum',texture=dict(size=4096),geometry=dict(export_triangle_target=1000000))
    parent=jobs.enqueue(dict(kind='inference',auto_blender=True,project_id='runavelle',asset_id='admission-only',blender_export_fbx=fbx,effective_config=config))
    folder=database/'jobs'/parent['id'];folder.mkdir(parents=True);(folder/'manifest.json').write_text(json.dumps(dict(candidate_artifact='admission-only-no-generated-model')))
    parent['status']='REVIEW_REQUIRED'  # Boundary-admission fixture only, no inference success claim.
    child=jobs.ensure_blender(parent)
    assert child['payload']['export_fbx'] is fbx and child['payload']['effective_config']==config
