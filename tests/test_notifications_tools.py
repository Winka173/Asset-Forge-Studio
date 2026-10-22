"""Inbox events use real persisted job transitions; tool probes are read-only."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs,local_tools
from apps.api.main import app


@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)


def test_notification_sqlite_history_read_clear_and_cross_game_filters(client):
    a=client.post('/api/assets',json=dict(project_id='runavelle',name='Source A')).json()
    other=client.post('/api/projects',json=dict(name='Another game')).json()
    b=client.post('/api/assets',json=dict(project_id=other['id'],name='Source B')).json()
    assert client.get('/api/notifications').json()['total']==0
    # Explicit failed-stage regression fixtures; these are not generated assets.
    for asset in (a,b):
        job=jobs.enqueue(dict(kind='concept',asset_id=asset['id'],project_id=asset['project_id']))
        jobs.transition(job['id'],'RUNNING');jobs.transition(job['id'],'FAILED','Unit-only failure; no successful output claimed')
    value=client.get('/api/notifications').json();assert value['total']==value['unread_count']==2
    assert all(n['kind']=='failed' and n['target'].startswith('job/') for n in value['items'])
    scoped=client.get('/api/notifications',params=dict(project_id='runavelle',kind='failed')).json()
    assert scoped['total']==1 and scoped['items'][0]['asset_name']=='Source A'
    identifier=scoped['items'][0]['id']
    assert client.post('/api/notifications/read',json=dict(ids=[identifier])).json()['updated']==1
    assert client.get('/api/notifications').json()['unread_count']==1
    assert client.get('/api/notifications',params=dict(unread=True)).json()['total']==1
    assert client.post('/api/notifications/clear',json=dict(all=True,project_id='runavelle')).json()['updated']==1
    assert client.get('/api/notifications').json()['total']==1  # repeated sync never resurrects cleared history
    assert len(jobs.listing())==2 and len(client.get('/api/projects').json())==2
    assert client.post('/api/notifications/read',json=dict(all=True)).status_code==200
    assert client.get('/api/notifications').json()['unread_count']==0
    first=client.get('/api/notifications',params=dict(limit=1)).json()
    assert first['next_offset']==1 and not first['has_more']


def test_invalid_tool_selection_keeps_saved_configuration_and_recheck_available(client):
    r=client.post('/api/tools/select',json=dict(tool='blender',path=str(store.DATA/'missing.exe')))
    assert r.status_code==400 and 'does not exist' in r.json()['detail']
    assert local_tools.config()=={}
    invalid=store.DATA/'wrong-tool.exe';invalid.write_bytes(b'Not an executable')
    assert client.post('/api/tools/select',json=dict(tool='blender',path=str(invalid))).status_code==400
    value=client.post('/api/tools/detect',json={});assert value.status_code==200,value.text
    assert {v['tool'] for v in value.json()['tools']}=={'blender','unity','unreal'}
    unreal=next(t for t in value.json()['tools'] if t['tool']=='unreal')
    assert not unreal['selected'] or not unreal['selected']['pipeline_supported']
    assert jobs.listing()==[]


def test_actual_local_blender_unity_probe_and_persistent_selection(client):
    blender=Path.home()/'Tools/blender-4.5.14-windows-x64/blender.exe'
    unity=Path('C:/Program Files/Unity/Hub/Editor/6000.4.8f1/Editor/Unity.exe')
    if not blender.is_file() or not unity.is_file():pytest.skip('Actual installed tools unavailable')
    for tool,path in [('blender',blender),('unity',unity)]:
        response=client.post('/api/tools/select',json=dict(tool=tool,path=str(path)))
        assert response.status_code==200,response.text
        assert response.json()['pipeline_supported'] and response.json()['validated']
        assert Path(local_tools.executable(tool)).resolve()==path.resolve()
    before=local_tools.config()
    assert client.post('/api/tools/select',json=dict(tool='unity',path=str(blender))).status_code==400
    assert local_tools.config()==before
    from engines.unity_editor import probe
    assert probe()['installed']
    local_tools.CACHE.clear()
    assert all(t['selected'] for t in client.get('/api/tools').json()['tools'] if t['tool']!='unreal')
    assert jobs.listing()==[]
