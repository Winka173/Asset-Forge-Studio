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


def test_actual349_only_explicitly_admitted_asset_in_production_and_new_click_restarts_terminal_attempt(client):
    source=Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md'
    if not source.exists():pytest.skip('Actual Runavelle source unavailable')
    response=client.post('/api/batches/import',files={'file':(source.name,source.read_bytes())},data=dict(project_id='runavelle'))
    assert response.status_code==201
    value=response.json();prefix='/api/batches/'+value['id'];first=value['items'][0]
    assert client.get('/api/production').json()['groups']==[]
    selected=dict(selected_ids=[first['asset_id']],automatic=True,regenerate_completed=True,request_id='production-one-explicit-click')
    assert client.post(prefix+'/run',json=selected).status_code==200
    overview=client.get('/api/production').json();group=overview['groups'][0]
    assert len(overview['groups'])==1 and len(group['items'])==group['admitted_count']==1
    assert group['imported_count']==349 and group['items'][0]['id']==first['asset_id']
    assert group['counts']['draft']==0 and len(jobs.listing())==1
    old=jobs.listing()[0];assert old['payload']['user_prompt']==first['prompt']
    assert client.post(prefix+'/run',json=selected).status_code==200
    assert len(jobs.listing())==1 and batch.batch(value['id'])['items'][0]['attempt']==0
    # A second click while the stage is active also preserves the single attempt.
    assert client.post(prefix+'/run',json=selected|dict(request_id='production-one-active-click')).status_code==200
    assert len(jobs.listing())==1
    jobs.transition(old['id'],'CANCELLED','Explicit test cancellation; no output fabricated')
    dry=client.post(prefix+'/run-all',json=dict(dry_run=True,regenerate_completed=True,request_id='production-all-dry-plan'))
    assert dry.status_code==200 and dry.json()['plan']['total']==349
    assert len(jobs.listing())==1 and batch.batch(value['id'])['items'][0]['attempt']==0
    assert client.post(prefix+'/run',json=selected|dict(request_id='production-one-new-click')).status_code==200
    stored=batch.batch(value['id']);assert stored['items'][0]['attempt']==1
    assert stored['items'][0]['generation_history'][0]['attempt']==0
    assert len(jobs.listing())==2 and {j['payload']['batch_attempt'] for j in jobs.listing()}=={0,1}
    group=client.get('/api/production').json()['groups'][0]
    assert len(group['items'])==1 and len(group['items'][0]['jobs'])==1
    assert group['items'][0]['jobs'][0]['batch_attempt']==1
    assert len(client.get('/api/production/assets/'+first['asset_id']).json()['stages'])==2
    assert client.post(prefix+'/run',json=selected).status_code==200  # retry an old HTTP action
    assert len(jobs.listing())==2 and batch.batch(value['id'])['items'][0]['attempt']==1
    assert client.post(prefix+'/run',json=selected|dict(selected_ids=[value['items'][1]['asset_id']])).status_code==409


def test_new_attempt_never_inherits_prior_candidate_artistic_approval(client):
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Prior version versus new run')).json()
    asset_id=value['items'][0]['asset_id'];prefix='/api/batches/'+value['id']
    first=dict(automatic=True,selected_ids=[asset_id],request_id='art-projection-initial',regenerate_completed=True)
    assert client.post(prefix+'/run',json=first).status_code==200
    old=jobs.listing()[0];jobs.transition(old['id'],'CANCELLED','Unit fixture: old attempt ended')
    # Projection fixture only: no generated file, QA, or successful export is claimed.
    with store.connect() as db:
        db.execute('INSERT INTO artifacts (id,role,name,relative_path,sha256,created_at,metadata,project_id,asset_id) VALUES (?,?,?,?,?,?,?,?,?)',
                   ('old-version-candidate','candidate','Prior version','unit-only/old.glb','unit-only',store.now(),json.dumps(dict(job_id=old['id'])),'runavelle',asset_id))
        row=db.execute('SELECT payload FROM assets WHERE id=?',(asset_id,)).fetchone();model=json.loads(row['payload'])
        model['approvals']=[dict(artifact_id='old-version-candidate',reviewer='Unit fixture only',decision='approved')]
        model['master_artifact_id']='old-version-candidate'
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(model),asset_id))
    assert client.post(prefix+'/run',json=first|dict(request_id='art-projection-new-run')).status_code==200
    detail=client.get('/api/production/assets/'+asset_id).json()['asset']
    assert detail['master_artifact_id']=='old-version-candidate'
    assert detail['art_review_status']=='not_reviewed' and detail['qa_status']=='not_run' and detail['export_status']=='not_exported'

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


def test_waiting_assets_explain_what_they_wait_for(client):
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Tower',prompt='A stone tower')).json()
    client.post('/api/automation/single',json=dict(asset_id=model['id'],request_id='wait-reason-0001',quality='Maximum',engine='trellis2_community',seeds=[42]))
    waiting=lambda:next(i for g in client.get('/api/production').json()['groups'] for i in g['items'] if i['id']==model['id'])['waiting']
    assert client.post('/api/production/control',json=dict(scope='all',action='pause')).status_code==200
    reason=waiting();assert reason['code']=='paused_all' and reason['since']
    assert client.post('/api/production/control',json=dict(scope='all',action='resume')).status_code==200
    # Another asset holds the GPU: the queued stage names it.
    other=client.post('/api/assets',json=dict(project_id='runavelle',name='Castle',prompt='A castle')).json()
    busy=jobs.enqueue(dict(kind='inference',engine='trellis2_community',asset_id=other['id'],project_id='runavelle'));jobs.transition(busy['id'],'RUNNING')
    mine=[j for j in jobs.listing() if j['payload'].get('asset_id')==model['id'] and j['status']=='QUEUED']
    assert mine and jobs.resource_class(mine[0]['payload'])=='gpu'
    reason=waiting();assert reason['code']=='gpu' and 'Castle' in reason['message']
