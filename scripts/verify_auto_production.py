"""Actual local GPU subset; full source is imported, only three chosen assets execute."""
import os,json,time,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=Path(__file__).resolve().parents[1]
run=root/'.local/auto-production'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());run.mkdir(parents=True)
os.environ['AFS_DATA']=str(run/'Library')
from fastapi.testclient import TestClient
from apps.api import store,jobs,batch,automation
from apps.api.main import app
source=Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md'
report=dict(status='RUNNING',run=str(run),checks=[],mid_inference_resume=False,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
(root/'.local/auto-production/latest.txt').write_text(str(run))
try:
    client=TestClient(app)
    project=client.post('/api/projects',json=dict(name='Runavelle automatic real subset')).json()
    game=run/'GameAssets';game.mkdir()
    r=client.post('/api/export-profiles/projects/'+project['id'],json=dict(output_directory=str(game)));assert r.status_code==200,r.text
    response=client.post('/api/batches/import',files=dict(file=(source.name,source.read_bytes())),data=dict(project_id=project['id'],mode='Maximum Quality Batch'))
    assert response.status_code==201,response.text[:500]
    value=response.json();identifier=value['id'];report['batch_id']=identifier
    assert len(value['items'])==349 and sum(i['selected'] for i in value['items'])==349 and not jobs.listing()
    dry=client.post('/api/batches/'+identifier+'/run-all',json=dict(dry_run=True)).json();assert dry['plan']['total']==349 and dry['plan']['future']==37 and not jobs.listing()
    report['checks'].append(dict(name='actual349_all_including_future_dry_plan_no_gpu',passed=True,plan=dry['plan']))
    chosen=[]
    for fragment in ('ARCHER_TOWER_T3','HOUSE_T1','FUT_ENV_FOREST_WATCH_POST'):
        chosen.append(next(i for i in value['items'] if fragment in i['source_asset_id']))
    report['source_ids']=[i['source_asset_id'] for i in chosen]
    # Explicit tested textured engine policy, Maximum unchanged, one asset in-flight for pause proof.
    workflow=automation.Workflow(max_active_assets=1).model_dump();client.post('/api/automation/projects/'+project['id'],json=workflow)
    for item in chosen:
        r=client.post(f'/api/batches/{identifier}/items/{item["asset_id"]}',json=dict(preferred_engine='trellis2_community'));assert r.status_code==200,r.text[:500]
    with TestClient(app) as client:
        time.sleep(1)
        response=client.post('/api/batches/'+identifier+'/run',json=dict(selected_ids=[i['asset_id'] for i in chosen],automatic=True));assert response.status_code==200,response.text[:500]
        paused=False;start=time.monotonic()
        while time.monotonic()-start<10800:
            value=batch.batch(identifier);states=[i.get('automation',{}).get('status') for i in value['items'] if i['asset_id'] in {c['asset_id'] for c in chosen}]
            summary=[(j['payload']['kind'],j['status'],j['id'][:8]) for j in jobs.listing()]
            print(json.dumps(dict(seconds=round(time.monotonic()-start),states=states,jobs=summary)),flush=True)
            (run/'progress.json').write_text(json.dumps(dict(states=states,jobs=summary,report=report),indent=2))
            if states.count('exported')>=1:
                client.post('/api/batches/'+identifier+'/control',json=dict(action='pause'));paused=True;break
            if any(s in ('failed','blocked') for s in states):
                raise AssertionError(json.dumps([i['automation'] for i in value['items'] if i.get('automation')],indent=2))
            time.sleep(10)
        assert paused,'First export timeout'
        while any(j['status'] not in jobs.TERMINAL and j['status']!='QUEUED' for j in jobs.listing()):time.sleep(2)
        before={j['id'] for j in jobs.listing() if j['status']=='REVIEW_REQUIRED'}
        completed=[i for i in batch.batch(identifier)['items'] if i.get('automation',{}).get('status')=='exported']
        assert completed and (game/project['id']/'manifest.json').is_file()
        report['checks'].append(dict(name='incremental_export_before_batch_end_then_safe_pause',passed=True,completed_assets=[i['asset_id'] for i in completed],completed_job_ids=sorted(before)))
    with TestClient(app) as client:
        time.sleep(3);assert batch.batch(identifier)['paused']
        assert before<={j['id'] for j in jobs.listing() if j['status']=='REVIEW_REQUIRED'}
        client.post('/api/batches/'+identifier+'/control',json=dict(action='resume'))
        start=time.monotonic()
        while time.monotonic()-start<10800:
            value=batch.batch(identifier);states=[i.get('automation',{}).get('status') for i in value['items'] if i['asset_id'] in {c['asset_id'] for c in chosen}]
            print(json.dumps(dict(resumed_seconds=round(time.monotonic()-start),states=states)),flush=True)
            if states.count('exported')==3:break
            if any(s in ('failed','blocked') for s in states):raise AssertionError(json.dumps([i['automation'] for i in value['items'] if i.get('automation')],indent=2))
            time.sleep(10)
        assert states.count('exported')==3,'Subset incomplete'
        current=jobs.listing();assert before<={j['id'] for j in current if j['status']=='REVIEW_REQUIRED'}
        for done in completed:assert not any(j['payload'].get('retry_of') in before for j in current if j['payload'].get('asset_id')==done['asset_id'])
        report['jobs']=[dict(id=j['id'],status=j['status'],kind=j['payload']['kind'],asset_id=j['payload'].get('asset_id'),effective_config=j['payload'].get('effective_config'),error=j.get('error')) for j in current]
        report['assets']=[i for i in batch.batch(identifier)['items'] if i['asset_id'] in {c['asset_id'] for c in chosen}]
        report['checks'].append(dict(name='restart_manual_resume_three_real_outputs_without_regenerating_completed',passed=True))
    report['status']='PASS_REAL_GPU_AUTOMATIC_PRODUCTION'
except BaseException as exc:
    report.update(status='FAILED',error=str(exc));raise
finally:
    (run/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('REPORT '+str(run/'report.json'),flush=True)
