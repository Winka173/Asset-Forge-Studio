import json
import time

import pytest
import trimesh
from fastapi.testclient import TestClient

from apps.api import jobs, store
from apps.api.main import app


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    # Blender QA uses CPU; isolate its lock so an active production GPU job cannot
    # make these state-machine assertions time out. Each app still shares its lock.
    monkeypatch.setattr(jobs, 'WORKER_LOCK', tmp_path / 'worker.lock')
    return tmp_path


def test_lock_prevents_concurrent_workers(database):
    with jobs.exclusive_worker_lock():
        with pytest.raises(OSError):
            with jobs.exclusive_worker_lock():
                pytest.fail('Second worker acquired a held lock')


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
        assert client.post(f'/api/jobs/{job["id"]}/cancel').status_code == 409
        assert len(client.get('/api/status').json()['artifacts']) == 2
