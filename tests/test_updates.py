"""Update safety is exercised without fabricating upstream versions or installs."""
import json
import threading
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs,updates
from apps.api.main import app

def test_update_policy_and_activation_respect_pinned_work(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path);c=TestClient(app)
    assert c.get('/api/updates').json()['status']=='not_checked'
    assert c.post('/api/updates/policy',json=dict(auto_check=False,auto_update_media=False)).status_code==200
    assert not updates.state()['policy']['auto_check']
    assert c.post('/api/updates/install-media').status_code==409
    # A queued render must keep its exact tool paths, even before it starts.
    job=jobs.enqueue(dict(kind='cinematic_render',effective_config_hash='immutable-tool-paths'))
    assert not updates.activate(dict(version='must-not-activate'))
    assert 'active_media' not in updates.state()
    jobs.transition(job['id'],'CANCELLED')
    # Initial fallback is retained as a real rollback target (None = external tool).
    assert updates.activate(dict(version='pointer-only-test'))
    assert updates.state()['previous_media'] is None
    updates.save(policy=dict(auto_check=False,auto_update_media=True))
    assert c.post('/api/updates/rollback-media').status_code==200
    assert updates.state()['active_media'] is None
    assert not updates.state()['policy']['auto_update_media']

def test_untrusted_download_and_tampered_tool_never_activate(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    job=jobs.enqueue(dict(kind='tool_update',candidate=dict(url='https://example.com/evil.zip',sha256='0'*64,bytes=1)))
    folder=tmp_path/'jobs'/job['id'];folder.mkdir(parents=True)
    jobs.worker.execute(job)
    assert jobs.get(job['id'])['status']=='FAILED'
    assert 'Untrusted' in jobs.get(job['id'])['error']
    assert not updates.state().get('active_media')
    source=tmp_path/'tools/ffmpeg/test/ffmpeg.exe';source.parent.mkdir(parents=True);source.write_bytes(b'not executable; tamper check only')
    updates.save(active_media=dict(ffmpeg=str(source),ffprobe=str(source),hashes=dict(ffmpeg='0'*64,ffprobe='0'*64)))
    with pytest.raises(ValueError,match='changed'):updates.active_media()
    assert jobs.resource_class(job['payload'])=='cpu'

def test_actual_installed_managed_codec_if_acceptance_available(tmp_path,monkeypatch):
    evidence=store.ROOT/'.local/update-acceptance/Library/studio.sqlite'
    if not evidence.is_file():pytest.skip('Real downloaded portable media acceptance not available')
    import sqlite3
    with sqlite3.connect(evidence) as db:
        row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(updates.KEY,)).fetchone()
    value=json.loads(row[0]).get('active_media')
    if not value:pytest.skip('Real portable codec has not finished validation')
    monkeypatch.setattr(store,'DATA',evidence.parent)
    actual=updates.active_media()
    assert updates.command_version(actual['ffmpeg'])==value['version']
    assert updates.command_version(actual['ffprobe'])==value['version']
    assert value['qa']=='PASS_REAL_H264_ENCODE_PROBE_DECODE'
