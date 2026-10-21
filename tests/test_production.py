import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs,batch,automation,production
from apps.api.main import app

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)

def actual_batch(client):
    source=Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md'
    if not source.exists():pytest.skip('Actual Runavelle source unavailable')
    r=client.post('/api/batches/import',files={'file':(source.name,source.read_bytes())},data={'project_id':'runavelle'});assert r.status_code==201
    value=r.json();r=client.post('/api/batches/'+value['id']+'/run-all',json={});assert r.status_code==200
    return batch.batch(value['id'])

def test_global_workspace_real349_bounded_snapshot_and_scoped_pause(client):
    value=actual_batch(client);r=client.get('/api/production');assert r.status_code==200
    overview=r.json();group=overview['groups'][0];assert len(group['items'])==349 and sum(i['future'] for i in group['items'])==37
    assert len(r.content)<400_000 and b'master_prompt' not in r.content and len(jobs.listing())<=2
    item=next(i for i in group['items'] if i['jobs']);job=jobs.get(item['jobs'][0]['id'])
    body=dict(scope='asset',group_id=group['id'],asset_id=item['id'])
    assert client.post('/api/production/control',json=body|dict(action='pause')).status_code==200
    assert not production.eligible(job['payload'])
    from apps.api.main import shutdown_jobs
    assert job['id'] not in {j['id'] for j in shutdown_jobs()}
    assert client.post('/api/production/control',json=body|dict(action='prioritize',priority='next')).status_code==200
    assert next(i for i in batch.batch(group['id'])['items'] if i['asset_id']==item['id'])['priority']==100
    assert client.post('/api/production/control',json=body|dict(action='resume')).status_code==200
    assert production.eligible(job['payload'])
    client.post('/api/production/control',json=dict(scope='all',action='pause'));assert production.global_paused() and not production.eligible(job['payload'])
    assert production.overview()['paused'] # separate read; SQLite-backed across processes
    client.post('/api/production/control',json=dict(scope='all',action='resume'));assert not production.global_paused()
    bad=client.post('/api/production/control',json=body|dict(asset_id='outside',action='pause'));assert bad.status_code==404
    client.post('/api/production/control',json=dict(scope='batch',group_id=group['id'],action='cancel'))
    client.post('/api/production/control',json=dict(scope='all',action='resume'))
    assert batch.batch(group['id'])['paused'] and batch.batch(group['id'])['production_cancelled']

def test_persistent_events_legacy_job_and_fair_priority(client):
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Stage event QA')).json()
    j=jobs.enqueue(dict(kind='concept',project_id='runavelle',asset_id=model['id']))
    jobs.transition(j['id'],'RUNNING');jobs.transition(j['id'],'FAILED','unit-only stage failure')
    events=jobs.get(j['id'])['payload']['stage_events'];assert [e['state'] for e in events]==['RUNNING','FAILED']
    r=client.get('/api/production/assets/'+model['id']);assert r.status_code==200,r.text
    assert r.json()['stages'][0]['events']==events and r.json()['artifacts']==[]
    young=j|dict(created_at=store.now());old=j|dict(created_at='2020-01-01T00:00:00+00:00')
    assert production.scheduling_score(old,0)>production.scheduling_score(young,100)
    assert client.get('/api/production').json()['standalone'][0]['id']==j['id']


def test_production_event_stream_ends_on_desktop_shutdown():
    import asyncio
    from types import SimpleNamespace
    from apps.api.production import events
    class Request:
        app=SimpleNamespace(state=SimpleNamespace(shutting_down=True))
        async def is_disconnected(self):return False
    async def run():
        response=await events(Request())
        return [chunk async for chunk in response.body_iterator]
    assert asyncio.run(run())==[]


def test_actual349_reimport_is_lossless_and_keeps_one_asset_identity(client):
    source=Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md'
    if not source.exists():pytest.skip('Actual Runavelle source unavailable')
    def upload(mode='Quality Batch',project='runavelle'):
        r=client.post('/api/batches/import',files={'file':(source.name,source.read_bytes())},data={'project_id':project,'mode':mode})
        assert r.status_code==201,r.text
        return r.json()
    first=upload();assert len(first['items'])==349
    assert sum(i['source_status']=='FUTURE' for i in first['items'])==37
    assert sum(i['source_status']!='FUTURE' for i in first['items'])==312
    for repeat in range(2):
        again=upload();assert again['id']==first['id'] and again['reused_import']
        assert [(i['asset_id'],i['prompt']) for i in again['items']]==[(i['asset_id'],i['prompt']) for i in first['items']]
    item=first['items'][0]
    with store.connect() as db:
        model=json.loads(db.execute('SELECT payload FROM assets WHERE id=?',(item['asset_id'],)).fetchone()[0])
        model['master_artifact_id']='preserve-actual-master-pointer';model['original_prompt']=model['prompt']
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(model),model['id']))
    maximum=upload('Maximum Quality Batch')
    assert [i['asset_id'] for i in maximum['items']]==[i['asset_id'] for i in first['items']]
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]==349
        saved=json.loads(db.execute('SELECT payload FROM assets WHERE id=?',(model['id'],)).fetchone()[0])
    assert saved['master_artifact_id']==model['master_artifact_id'] and saved['original_prompt']==item['prompt']
    assert len(saved['source_import_history'])==2
    other=client.post('/api/projects',json={'name':'Different game'}).json()
    separate=upload(project=other['id'])
    assert not set(i['asset_id'] for i in separate['items']) & set(i['asset_id'] for i in first['items'])
    assert jobs.listing()==[]


def test_standalone_stages_are_nested_and_asset_pause_survives_handoff(client):
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='One asset three stages')).json()
    payload=dict(kind='concept',project_id='runavelle',asset_id=model['id'])
    first=jobs.enqueue(payload);jobs.transition(first['id'],'RUNNING');jobs.transition(first['id'],'FAILED','Explicit failed-stage fixture')
    second=jobs.enqueue(payload|dict(kind='blender'))
    overview=client.get('/api/production').json()
    assert len(overview['standalone'])==1 and len(overview['standalone'][0]['jobs'])==2
    root=overview['standalone'][0]['id'];assert root==first['id']
    assert overview['standalone'][0]['display_name']==model['name']
    body=dict(scope='job',job_id=root)
    assert client.post('/api/production/control',json=body|dict(action='pause')).status_code==200
    third=jobs.enqueue(payload|dict(kind='concept'))
    assert not production.eligible(third['payload'])
    assert not production.eligible(jobs.get(second['id'])['payload'])
    assert client.post('/api/production/control',json=body|dict(action='resume')).status_code==200
    assert production.eligible(jobs.get(third['id'])['payload'])
    assert len(client.get('/api/production').json()['standalone'])==1
    client.post('/api/production/control',json=body|dict(action='pause'))
    client.post('/api/production/control',json=dict(scope='all',action='resume'))
    assert production.eligible(jobs.get(third['id'])['payload'])
    client.post('/api/production/control',json=body|dict(action='cancel'))
    assert all(jobs.get(j['id'])['status']=='CANCELLED' for j in (second,third))
