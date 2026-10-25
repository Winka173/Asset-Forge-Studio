import io
import json
import zipfile
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from apps.api import store,jobs
from apps.api.main import app
from apps.api.manifest import parse


@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path)
    qa_project()
    return TestClient(app)


def test_tier_manifest_exact_assets_and_missing_dimensions():
    text='- Castle T1–T3\n- Archer Tower T1–T3\n- Magic Tower T1–T3\n- House T1–T3\n- A modular Wall/Gate'
    rows,warnings=parse(text)
    assert len(rows)==14 and [r['name'] for r in rows][-2:]==['Wall','Gate']
    assert all(r['target_width_m'] is None and not r['confirmed'] for r in rows)
    assert warnings  # no local LLM is falsely presented as running.
    csv,_=parse('name,width_m,depth_m,height_m\nTower,2,3,8','csv')
    assert csv[0]['target_height_m']==8
    table,_=parse('| name | width_m | depth_m | height_m |\n|---|---|---|---|\n| Gate | 4 | 2 | 6 |','markdown')
    assert table[0]['name']=='Gate'
    with pytest.raises(ValueError):parse('An ambiguous paragraph without an explicit asset list')


def test_manifest_review_pause_resume_and_no_fabricated_outputs(client):
    created=client.post('/api/batches/analyze',json=dict(project_id='runavelle',name='QA planning',master_prompt='- Castle T1-T3',mode='Maximum Quality Batch')).json()
    assert len(created['items'])==3 and created['paused']
    row=created['items'][0];prefix='/api/batches/'+created['id']
    assert client.post(prefix+'/run',json=dict(selected_ids=[row['asset_id']])).status_code==409
    assert jobs.listing()==[]
    edit=client.post(prefix+'/items/'+row['asset_id'],json=dict(quality='Fast'))
    assert edit.status_code==409
    confirmed=client.post(prefix+'/items/'+row['asset_id'],json=dict(quality='Fast',quality_override_confirmed=True,quality_override_reason='Explicit QA override')).json()
    assert confirmed['items'][0]['quality_override_history'][0]['approved']
    data=client.get(prefix+'/export?format=zip&selection=all')
    archive=zipfile.ZipFile(io.BytesIO(data.content));report=json.loads(archive.read('export_report.json'))
    assert not report['included_assets'] and len(report['omitted_assets'])==3
    assert not any(n.endswith('.glb') for n in archive.namelist())
    original_ids={i['asset_id'] for i in created['items']}
    copy=client.post(prefix+'/control',json=dict(action='duplicate')).json()
    assert not original_ids.intersection(i['asset_id'] for i in copy['items'])


def test_single_batch_quality_parity_retry_and_hash_guard(client):
    from engines.adapters import ADAPTERS
    from engines.quality import fingerprint
    if not ADAPTERS['triposg'].installed:pytest.skip('Requires actual preinstalled local engine/checkpoints')
    pixels=io.BytesIO();Image.new('RGBA',(32,32),(0,0,0,0)).save(pixels,format='PNG')
    ref=client.post('/api/import/reference',files=dict(file=('qa.png',pixels.getvalue()))).json()
    single=client.post('/api/assets',json=dict(project_id='runavelle',name='QA Single',prompt='Archer Tower')).json()
    manifest=[dict(name='QA Batch',prompt='Archer Tower',preferred_engine='triposg',candidates=2,reference_ids=[ref['id']],target_width_m=3,target_depth_m=3,target_height_m=10,confirmed=True)]
    batch=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt=json.dumps(manifest),format='json',mode='Maximum Quality Batch')).json()
    item=batch['items'][0]
    approved=client.post(f'/api/assets/{item["asset_id"]}/concepts/{ref["id"]}/approve',json=dict(reviewer='QA config parity only'))
    assert approved.status_code==200
    first=client.post('/api/studio/generate',json=dict(asset_id=single['id'],artifact_id=ref['id'],request_id='single-parity-request',engine='triposg',quality='Maximum',seeds=[42,43],auto_blender=True,benchmark_height_m=10)).json()
    assert all(j['payload']['blender_export_fbx'] is False for j in first['jobs'])
    result=client.post(f'/api/batches/{batch["id"]}/run',json=dict(selected_ids=[item['asset_id']]))
    assert result.status_code==200,result.text
    batched=[j for j in jobs.listing() if j['payload'].get('batch_id')==batch['id']]
    assert len(batched)==2
    for expected in first['jobs']:
        actual=next(j for j in batched if j['payload']['seed']==expected['payload']['seed'])
        assert actual['payload']['effective_config']==expected['payload']['effective_config']
        assert actual['payload']['effective_config_hash']==expected['payload']['effective_config_hash']
        assert actual['payload']['effective_config']['blender']['enabled']
    before=len(jobs.listing());client.post(f'/api/batches/{batch["id"]}/control',json=dict(action='resume'))
    assert len(jobs.listing())==before  # no successful/queued work is regenerated on resume.
    job=batched[0];jobs.transition(job['id'],'BLOCKED','OOM verification fixture; not an executed GPU run')
    retried=jobs.retry(job['id'])
    assert retried['payload']['effective_config']==job['payload']['effective_config']
    assert retried['payload']['steps']==50 and retried['payload']['engine']=='triposg'
    corrupt=dict(job['payload']);corrupt['effective_config']=dict(corrupt['effective_config'],inference_steps=1)
    invalid=jobs.enqueue(corrupt);jobs.Worker().execute(invalid)
    assert jobs.get(invalid['id'])['status']=='BLOCKED'
    assert 'hash mismatch' in jobs.get(invalid['id'])['error']
    assert fingerprint(corrupt['effective_config'])!=corrupt['effective_config_hash']
    changed=dict(job['payload'],steps=1)
    invalid_execution=jobs.enqueue(changed);jobs.Worker().execute(invalid_execution)
    assert jobs.get(invalid_execution['id'])['status']=='BLOCKED'
    assert 'Execution settings differ' in jobs.get(invalid_execution['id'])['error']


def test_batch_config_edit_preserves_previous_job_and_needs_explicit_run(client):
    row=dict(name='Revision QA',prompt='Original prompt',target_width_m=2,target_depth_m=2,target_height_m=5,confirmed=True)
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt=json.dumps([row]),format='json')).json()
    item=value['items'][0];prefix=f'/api/batches/{value["id"]}'
    original=jobs.enqueue(dict(kind='concept',batch_id=value['id'],asset_id=item['asset_id'],batch_attempt=0,prompt='Original prompt'))
    jobs.transition(original['id'],'BLOCKED','Fixture: no inference executed')
    result=client.post(prefix+'/items/'+item['asset_id'],json=dict(prompt='Revised prompt')).json()['items'][0]
    assert result['attempt']==1 and not result['started']
    assert result['config_revision_history'][0]['changed_fields']==['prompt']
    assert jobs.get(original['id'])['payload']['prompt']=='Original prompt'
    assert len(jobs.listing())==1


def test_batch_scheduling_failure_does_not_block_other_assets(client,monkeypatch):
    from apps.api import studio
    from fastapi import HTTPException
    rows=[dict(name=name,prompt=name,target_width_m=2,target_depth_m=2,target_height_m=5,confirmed=True) for name in ['Broken input','Valid input']]
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt=json.dumps(rows),format='json')).json()
    attempted=[]
    def submit(body):
        attempted.append(body.asset_id)
        if body.asset_id==value['items'][0]['asset_id']:raise HTTPException(409,'Checkpoint missing; quality preserved')
        return jobs.enqueue(dict(kind='concept',asset_id=body.asset_id,batch_id=body.batch_id))
    monkeypatch.setattr(studio,'concept',submit)
    result=client.post('/api/batches/'+value['id']+'/run',json={})
    assert result.status_code==200,result.text
    assert len(attempted)==2 and len(jobs.listing())==1
    assert result.json()['items'][0]['status']=='Failed/Blocked'
    assert 'Checkpoint missing' in result.json()['items'][0]['last_error']


def test_desktop_api_requires_session_token(client,monkeypatch):
    monkeypatch.setenv('AFS_API_TOKEN','isolated-test-token')
    assert client.get('/api/desktop/health').status_code==401
    assert client.get('/api/desktop/health',headers={'X-AFS-Token':'wrong'}).status_code==401
    assert client.get('/api/desktop/health',headers={'X-AFS-Token':'isolated-test-token'}).status_code==200
    assert client.get('/api/desktop/health?afs_token=isolated-test-token').status_code==200
    assert client.post('/api/assets',headers={'Origin':'https://untrusted.example','X-AFS-Token':'isolated-test-token'},json={}).status_code==403


def test_simultaneous_first_library_connections(client):
    from concurrent.futures import ThreadPoolExecutor
    def open_library(_):
        with store.connect() as db:
            return db.execute('PRAGMA user_version').fetchone()[0],db.execute('SELECT count(*) FROM projects').fetchone()[0]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(open_library,range(32)))
    assert results==[(3,1)]*32


def test_one_sentence_request_lists_named_assets_as_2d_sprites(client,monkeypatch):
    import engines.request_split as request_split
    from apps.api import studio
    monkeypatch.setattr(request_split,'split',lambda text:([dict(name=n,prompt='A '+e,output='3d') for n,e in (('hiệp sĩ','knight'),('cung thủ','archer'))],'stub'))
    batch=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='cho tôi 2 model 2d của hiệp sĩ, cung thủ',mode='Maximum Quality Batch')).json()
    # 2D follows the user's words even when the model says 3d; the asset becomes a sprite asset.
    assert [(i['name'],i['output']) for i in batch['items']]==[('hiệp sĩ','2d'),('cung thủ','2d')]
    assert studio.asset(batch['items'][0]['asset_id'])['asset_type']=='sprite_2d' and batch['import_diagnostics']['parser_method']=='local_ai_request_split'
    rejected=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='x'*3100,mode='Maximum Quality Batch'))
    assert rejected.status_code==400
